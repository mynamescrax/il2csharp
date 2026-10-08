from il2cpp.prelude import *  # noqa: F401,F403
from il2cpp.cfg import Block, _objop_fold
from il2cpp.lifter import Lifter
from il2cpp.metadata import MethodDef, TypeDef
from il2cpp.stmt_text import _cond_dewrap
from il2cpp.text import imm_of, reg_name
from il2cpp.names import safe_ident
from il2cpp.expr import unwrap_accessor_markers
import collections

class _BuildMixin:
    def __init__(self, lifter: Lifter):
        self.L = lifter
        self._var_types = {}
        self.phi_copies = {}
        self.phi_names = set()
        self.phi_alias = {}
        self.phi_pre = {}
        self._sw_depth = 0
        self._sw_join = -1

    @staticmethod
    def _memory_rhs_needs_loop_guard(insns):
        """Guard only control flow the native CFG cannot prove.

        Structured direct loops replay their header block inside the loop, so
        memory-derived expressions are recomputed on every native back edge.
        An unresolved or potential indirect branch can still hide an
        unmodelled cycle and therefore keeps the conservative operand fallback.
        """
        for ins in insns or ():
            if ins.flow_control == FlowControl.INDIRECT_BRANCH:
                return True
            if (ins.flow_control in (
                    FlowControl.CONDITIONAL_BRANCH,
                    FlowControl.UNCONDITIONAL_BRANCH)
                    and ins.op0_kind != OpKind.NEAR_BRANCH64):
                return True
        return False

    @staticmethod
    def _allocation_needs_loop_guard(blocks):
        """An actual acyclic CFG permits instruction-local allocation temps.

        Backward branches to a shared error/return tail are not loops. Use
        Kahn's topological test on the prewired native CFG, while retaining
        the guard for unresolved indirect dispatch and *any* actual cycle.
        This does not relax the separate register/memory arithmetic guard.
        """
        for block in blocks:
            if any(ins.flow_control == FlowControl.INDIRECT_BRANCH
                   for ins in block.insns) and (not block.term or block.term[0] != 'switch'):
                return True
        edges = [{s for s in b.succs if 0 <= s < len(blocks)} for b in blocks]
        indegree = [0] * len(blocks)
        for successors in edges:
            for s in successors:
                indegree[s] += 1
        pending = [i for i, n in enumerate(indegree) if n == 0]
        visited = 0
        while pending:
            bid = pending.pop()
            visited += 1
            for s in edges[bid]:
                indegree[s] -= 1
                if indegree[s] == 0:
                    pending.append(s)
        return visited != len(blocks)

    @staticmethod
    def _xor_twin_load_sites(insns, bin):
        """Scalar movsd loads feeding a packed-xor twin stay raw.

        MSVC negates a double3 column as a packed pair (16B load,
        copy, broadcast, two xorps vs the same -0.0 mask, recombine,
        one 16B store) plus a scalar third lane (8B load, xorps vs
        the same mask, 8B store). The packed lanes keep member sugar
        (`val.cN`) while the scalar lane must stay a raw byte deref:
        refining it to `val.cN.z` also mistypes the store `double*`.
        Only scalar 8B loads with a same-mask, same-base packed twin
        at disp - 16 are marked; every unproven shape keeps today's
        spelling, which is at worst cosmetic -- raw is always honest.
        """
        out = set()
        if not insns or bin is None:
            return out
        _NEG0 = b'\x00\x00\x00\x00\x00\x00\x00\x80'
        _XOR = (Mnemonic.XORPS, Mnemonic.XORPD)
        _COPY = (Mnemonic.MOVAPS, Mnemonic.MOVAPD)
        _W16 = (Mnemonic.MOVUPS, Mnemonic.MOVUPD,
                Mnemonic.MOVAPS, Mnemonic.MOVAPD)
        _W8 = (Mnemonic.MOVSD, Mnemonic.MOVQ)
        _W4 = (Mnemonic.MOVSS, Mnemonic.MOVD)
        _NONW = (Mnemonic.CMP, Mnemonic.TEST, Mnemonic.COMISS,
                 Mnemonic.UCOMISS, Mnemonic.COMISD, Mnemonic.UCOMISD)

        def writes(ins, reg):
            return (ins.op0_kind == OpKind.REGISTER
                    and reg_name(ins.op0_register) == reg
                    and ins.mnemonic not in _NONW)

        def trace(reg, before):
            cur = reg
            for pos in range(before - 1, max(-1, before - 201), -1):
                ins = insns[pos]
                if ins.mnemonic == Mnemonic.CALL:
                    return None
                if not writes(ins, cur):
                    continue
                mn = ins.mnemonic
                if mn in _COPY and ins.op1_kind == OpKind.REGISTER:
                    cur = reg_name(ins.op1_register)
                    continue
                if mn in (Mnemonic.UNPCKHPD, Mnemonic.UNPCKLPD) \
                        and ins.op1_kind == OpKind.REGISTER \
                        and reg_name(ins.op1_register) == cur:
                    continue
                if mn in _W16 + _W8 + _W4 \
                        and ins.op1_kind == OpKind.MEMORY:
                    if ins.memory_base == IReg.RIP:
                        return ('const', ins.ip_rel_memory_address)
                    if ins.memory_index != IReg.NONE \
                            or ins.memory_base == IReg.NONE:
                        return None
                    w = 16 if mn in _W16 else (8 if mn in _W8 else 4)
                    return ('mem', reg_name(ins.memory_base),
                            ins.memory_displacement, w, ins.ip)
                return None
            return None

        lanes = []
        for pos, ins in enumerate(insns):
            if ins.mnemonic not in _XOR \
                    or ins.op0_kind != OpKind.REGISTER \
                    or ins.op1_kind != OpKind.REGISTER:
                continue
            dst = reg_name(ins.op0_register)
            src = reg_name(ins.op1_register)
            if dst == src:
                continue
            for lane_reg, mask_reg in ((dst, src), (src, dst)):
                lane = trace(lane_reg, pos)
                mask = trace(mask_reg, pos)
                if lane is None or mask is None or mask[0] != 'const':
                    continue
                try:
                    const = bytes(bin.read(mask[1], 8))
                except Exception:
                    continue
                if const != _NEG0 or lane[0] != 'mem':
                    continue
                lanes.append((mask[1], lane[1], lane[2], lane[3], lane[4]))
        packed = set()
        for (maddr, base, disp, w, _lip) in lanes:
            if w == 16:
                packed.add((maddr, base, disp))
        for (maddr, base, disp, w, lip) in lanes:
            if w == 8 and (maddr, base, disp - 16) in packed:
                out.add(lip)
        return out

    @staticmethod
    def _sqrt_low_lane_sites(insns, helper):
        """Prove packed instructions whose high lane cannot be observable.

        MSVC emits ``ucomisd; ja helper; sqrtpd`` diamonds even for scalar
        source Math.Sqrt.  The alternate helper consumes and returns only
        XMM0's low double, so a high lane used after the join would make the
        two native arms disagree.  Pair the exact branch, helper call and
        normal SQRTPD before allowing Lifter's scalar expression model.
        """
        out = {'root': set(), 'convert': set(), 'narrow': set()}
        if helper is None:
            return out

        non_writers = (Mnemonic.CMP, Mnemonic.TEST, Mnemonic.COMISS,
                       Mnemonic.UCOMISS, Mnemonic.COMISD, Mnemonic.UCOMISD)

        def reads(ins, reg):
            return ((ins.op0_kind == OpKind.REGISTER
                     and reg_name(ins.op0_register) == reg)
                    or (ins.op1_kind == OpKind.REGISTER
                        and reg_name(ins.op1_register) == reg))

        def writes(ins, reg):
            return (ins.op0_kind == OpKind.REGISTER
                    and reg_name(ins.op0_register) == reg
                    and ins.mnemonic not in non_writers)

        def prior_write(reg, before, floor):
            for pos in range(before - 1, floor - 1, -1):
                if writes(insns[pos], reg):
                    return pos
            return None

        moves = (Mnemonic.MOVAPS, Mnemonic.MOVAPD, Mnemonic.MOVSD)
        scalar_ops = (Mnemonic.ADDSD, Mnemonic.SUBSD,
                      Mnemonic.MULSD, Mnemonic.DIVSD)
        conversions = (Mnemonic.CVTPS2PD, Mnemonic.CVTDQ2PD)

        for call_pos, call in enumerate(insns):
            if not (call.mnemonic == Mnemonic.CALL
                    and call.op0_kind == OpKind.NEAR_BRANCH64
                    and call.near_branch_target == helper):
                continue
            alt_pos = call_pos
            source = 'XMM0'
            if (call_pos and insns[call_pos - 1].mnemonic in moves
                    and insns[call_pos - 1].op0_kind == OpKind.REGISTER
                    and reg_name(insns[call_pos - 1].op0_register) == 'XMM0'
                    and insns[call_pos - 1].op1_kind == OpKind.REGISTER):
                alt_pos -= 1
                source = reg_name(insns[alt_pos].op1_register)

            branch_pos = None
            for pos in range(alt_pos - 1, max(-1, alt_pos - 101), -1):
                branch = insns[pos]
                if (branch.mnemonic == Mnemonic.JA
                        and branch.op0_kind == OpKind.NEAR_BRANCH64
                        and branch.near_branch_target == insns[alt_pos].ip):
                    branch_pos = pos
                    break
            if branch_pos is None:
                continue

            compared = False
            for pos in range(branch_pos - 1, max(-1, branch_pos - 8), -1):
                probe = insns[pos]
                if probe.mnemonic == Mnemonic.UCOMISD and reads(probe, source):
                    compared = True
                    break
                if probe.flow_control != FlowControl.NEXT:
                    break
            if not compared:
                continue

            roots = [pos for pos in range(branch_pos + 1, alt_pos)
                     if insns[pos].mnemonic == Mnemonic.SQRTPD
                     and reads(insns[pos], source)]
            if len(roots) != 1:
                continue
            root_pos = roots[0]
            root = insns[root_pos]
            out['root'].add(root.ip)

            floor = max(0, branch_pos - 40)
            defining = prior_write(source, root_pos, floor)
            if defining is not None:
                definition = insns[defining]
                if definition.mnemonic in conversions:
                    out['convert'].add(definition.ip)
                elif (definition.mnemonic in scalar_ops
                        and definition.op1_kind == OpKind.REGISTER):
                    # One observed form subtracts a just-converted float from
                    # an existing double before the root.  SUBSD reads only
                    # that source's low lane, so the same proof applies.
                    operand = reg_name(definition.op1_register)
                    producer = prior_write(operand, defining,
                                           max(0, branch_pos - 50))
                    if (producer is not None
                            and insns[producer].mnemonic in conversions):
                        out['convert'].add(insns[producer].ip)

            root_dst = reg_name(root.op0_register)
            for pos in range(root_pos + 1, alt_pos):
                probe = insns[pos]
                if (probe.mnemonic == Mnemonic.CVTPD2PS
                        and probe.op1_kind == OpKind.REGISTER
                        and reg_name(probe.op1_register) == root_dst):
                    out['narrow'].add(probe.ip)
        return out

    # ==================================================================
    def lift_method(self, m: MethodDef, td: TypeDef) -> List[str]:
        # the proven EH helper set is evidence about the binary, not about
        # this method, so it is built once and reused. Every field the scan
        # touches is re-initialized for m in the lines below -- fix 91
        self._ensure_eh_helper_set()
        # tokens (vN/tN) repeat in every method; a stale entry from the
        # previous method would type this one's locals at random
        self._var_types = {}
        L = self.L
        # the EH helper VAs are per-method evidence, never program constants:
        # a census of 4,526 pad-bearing methods taught 99 distinct rethrow and
        # 9 distinct raise targets, two of them taught as both. Keeping the
        # previous method's value made a body's rendering depend on what was
        # lifted before it, so a pad-less caller could print `throw;` for an
        # ordinary call -- clear them for every method -- fix 90
        L.rethrow_va = None
        L.raise_va = None
        self.eh = L.il.eh_regions(m.addr) if hasattr(L.il, 'eh_regions') else None
        insns, skip = self._decode(m)
        if not insns:
            return ['/* no code */']
        L._sqrt_low_sites = self._sqrt_low_lane_sites(
            insns, getattr(L, 'rt_sqrt', None))
        L._xor_twin_loads = self._xor_twin_load_sites(insns, getattr(L, 'bin', None))
        L._memory_rhs_loop_guard = self._memory_rhs_needs_loop_guard(insns)
        self.skip_ips = skip
        self.entry_ip = insns[0].ip
        self.last_ip = insns[-1].next_ip
        # kept for _jump_table's bounds-check scan: block splitting can put a
        # switch dispatch's `cmp idxreg,N; ja default` in a PREDECESSOR block
        # of the one holding the actual `jmp reg`, so a block-local backward
        # scan alone can miss it -- this flat, unsplit view always has it.
        self._flat_insns = insns
        self._flat_ip_idx = {ins.ip: i for i, ins in enumerate(insns)}
        extra_leaders = self._scan_jump_table_leaders(insns)
        blocks, bmap = self._make_blocks(insns, skip, extra_leaders)
        if not blocks:
            return ['/* empty */']
        if len(blocks) > 3000:
            raise RuntimeError('cfg too large (%d blocks)' % len(blocks))
        self._pad_bids = set()
        if self.eh:
            for p in self.eh.get('pads') or ():
                bi = bmap.get(p)
                if bi is not None:
                    self._pad_bids.add(bi)
            self._seh_helpers(blocks, bmap)
        self._prewire_switches(blocks)
        self._prune_nonreturning(blocks)
        L._array_allocation_loop_guard = self._allocation_needs_loop_guard(blocks)
        self._analyze(m, td, blocks, bmap)
        # type inference: hints gathered during pass 2 feed the renaming pass
        for k, v in getattr(self.L, '_type_hints', {}).items():
            self._var_types.setdefault(k, v)
        if not any(b.stmts or b.cond is not None or b.ret is not None for b in blocks):
            return ['/* nothing */']
        lines = self._final_text(self._structure(blocks, bmap, m))
        lines = drop_empty_init_guards(lines)
        try:
            params = {safe_ident(p.name) for p in self.L.meta.method_params(m)}
        except Exception:
            params = set()
        params.update(('this', 'value'))
        lines, _ = hoist_escaping_locals(lines, params)
        # fix 137b: accessor markers unwrap after every purity-judging pass
        return [unwrap_accessor_markers(ln) for ln in self._sret_local_decl(lines, m)]

    _SRET_TOK_RX = re.compile(r'(?<![\w.])__ret\b')

    def _sret_local_decl(self, lines, m):
        """Declare the hidden-sret result local (`__ret`, seeded in
        _setup_entry) once at the top of the body when the body uses it.
        `default` mirrors the caller-zeroed buffer IL2CPP passes for a
        struct return; every store then writes one of its fields."""
        if not any('__ret' in ln and self._SRET_TOK_RX.search(ln) for ln in lines):
            return lines
        # an existing declaration (never `return __ret;`, which the
        # first spelling of this guard mistook for one)
        if any(re.match(r'^\s*(?!return\b|throw\b|goto\b)[\w.<>\[\]]+ __ret( =|;)', ln)
               for ln in lines):
            return lines
        try:
            rt = self.L.il.types[m.return_type]
            tn = self.L.il.type_name(rt)
        except Exception:
            return lines
        tn = re.sub(r'`\d+(?=<|$)', '', tn or '')
        if not tn or tn == 'void':
            return lines
        ind = ''
        for ln in lines:
            if ln.strip():
                ind = ln[:len(ln) - len(ln.lstrip())]
                break
        return ['%s%s __ret = default;' % (ind, tn)] + list(lines)

    def _final_text(self, raw: List[str]) -> List[str]:
        """Last-pass text cleanup over the fully structured statements:
        `default`-junk arrives from several later passes (select folds,
        `: default` fallbacks), so the de-queue/op rules run once more here
        where they can see the final spellings."""
        out = []
        for ln in raw:
            prev = None
            while prev != ln:
                prev = ln
                ln = self._DEFAULT_DEQUE_RX.sub('default', ln)
                # the FLAGS sentinel expr (`lhs\x01rhs`, `_analyze` 808/904)
                # can leak into a value slot as text; its rhs is the flag-
                # pair's rhs ('0'), never a real value. Drop the sentinel
                # tail (to the end of the statement) so the honest lhs
                # survives: `a | b\x010;` -> `a | b;`. The interpolation
                # pass's own {{/}} markers are balanced away before this
                # pass, so a bare \x01 here is always a flags leak.
                if '\x01' in ln:
                    ln = self._FLAG_SENTINEL_RX.sub(';', ln)
                ln = _objop_fold(ln)
                # objop replacements paren-wrap, stacking redundant wraps
                # in condition heads (`if (!((X == null)))`) -- strip them
                # here, after the fold, where render's _fix_cond_line
                # can no longer see them (fix 44c)
                ln = _cond_dewrap(ln)
            out.append(ln)
        # a label directly before `}` (or EOF) has no statement to
        # attach to -- C# requires one, and 169 of the 193 tree-sitter
        # MISSING rows were exactly this shape. The `;` is appended
        # HERE, the last pass of the pipeline: earlier label consumers
        # (_tidy_gotos, _drop_redundant_gotos, _hoist_shared_tails)
        # match labels by the exact `L_x:` spelling and would starve
        # on a `;`-suffixed label.
        for _i in range(len(out)):
            if not re.match(r'^L_[0-9a-fA-F]+:$', out[_i].strip()):
                continue
            _j = _i + 1
            # fix arm64scaf: // comment lines are transparent here too --
            # a label above only comments before } is equally statement-less
            while _j < len(out) and (not out[_j].strip() or out[_j].strip().startswith('//')):
                _j += 1
            if _j >= len(out) or out[_j].lstrip().startswith('}'):
                out[_i] = out[_i] + ' ;'
        return out

    # ------------------------------------------------------------------
    # A method bigger than this first window is rare -- 52 of Shift At
    # Midnight's 88,976 distinct entry points declare a span over it -- but
    # truncating one is a WRONG-OUTPUT bug, not a missing-detail one:
    # InventoryManager.Update (0x110A0 bytes) lost its whole 60-case jump
    # table, whose entries all sit past 0x10000.  So decode this much first
    # -- it covers everything else at no cost -- and widen only when the
    # trace proves the method continues past it.
    DECODE_WINDOW = 0x10000
    # Absolute safety bound on the widened pass.  `next_method_start` is the
    # method's true upper bound, but for a shared body it can be megabytes
    # away (the neighbour in address order need not be the neighbour in the
    # metadata), so it is never trusted unbounded.
    DECODE_WINDOW_MAX = 0x40000

    def _decode(self, m):
        L = self.L
        va = m.addr
        nxt = L.il.next_method_start(va) if hasattr(L.il, 'next_method_start') else None
        hard = va + self.DECODE_WINDOW_MAX
        bound = min(nxt or hard, hard)
        end = min(bound, va + self.DECODE_WINDOW)
        while True:
            code = L.bin.read(va, end - va)
            if not code:
                return None, set()
            dec = Decoder(64, code, DecoderOptions.NONE)
            dec.ip = va
            raw = []
            for ins in dec:
                raw.append(ins)
                if len(raw) >= 20000:
                    break
            if not raw:
                return raw, set()
            kept, over = self._trace_reachable(raw, va, bound)
            # Retry only when the WINDOW was the limiter: if the 20000-insn cap
            # stopped the decode short of `end`, a wider window decodes the
            # identical prefix and would just burn the work twice.
            if not over or end >= bound or raw[-1].next_ip < end:
                return kept, self._guards(kept)
            end = bound

    def _trace_reachable(self, raw, va, bound):
        """Trace control flow from the entry instead of cutting at the first
        `ret`: MSVC parks loop bodies, switch cases and cold paths after an
        early epilogue, and next_method_start over-reaches into the following
        function, so neither a linear prefix nor the whole window is the
        method.  Returns (kept instructions, overflowed), where `overflowed`
        says some followed target lay between the end of what was decoded and
        `bound` -- i.e. the decode window cut this method in half and the
        caller should widen it and try again."""
        idx = {x.ip: i for i, x in enumerate(raw)}
        win_end = raw[-1].next_ip
        over = False
        keep = set()
        work = [0]
        eh = getattr(self, 'eh', None)
        if eh:
            for pad_va in eh.get('pads') or ():
                pi = idx.get(pad_va)
                if pi is not None:
                    work.append(pi)
        tables = set()
        while work:
            i = work.pop()
            while 0 <= i < len(raw) and i not in keep:
                keep.add(i)
                ins = raw[i]
                fc = ins.flow_control
                if fc in (FlowControl.RETURN, FlowControl.INTERRUPT,
                          FlowControl.EXCEPTION):
                    break
                if fc == FlowControl.CONDITIONAL_BRANCH:
                    if ins.op0_kind == OpKind.NEAR_BRANCH64:
                        tv = ins.near_branch_target
                        t = idx.get(tv)
                        if t is not None:
                            work.append(t)
                        elif win_end <= tv < bound:
                            over = True
                    i += 1
                    continue
                if fc in (FlowControl.UNCONDITIONAL_BRANCH, FlowControl.INDIRECT_BRANCH):
                    if ins.op0_kind == OpKind.NEAR_BRANCH64:
                        tv = ins.near_branch_target
                        t = idx.get(tv)
                        if t is not None:
                            work.append(t)
                        elif win_end <= tv < bound:
                            over = True
                    elif ins.mnemonic == Mnemonic.JMP and ins.op0_kind == OpKind.REGISTER \
                            and i not in tables:
                        tables.add(i)
                        # `bound`, not the decode window: a table whose entries
                        # sit past the window must still be RECOGNIZED here, or
                        # its first out-of-range entry breaks the entry scan and
                        # the dispatch degrades to an indirect call on the raw
                        # table load -- silently dropping every case body.
                        for tgt in self._jump_table(raw, i, va, bound)[0] or ():
                            t = idx.get(tgt)
                            if t is not None:
                                work.append(t)
                            elif win_end <= tgt < bound:
                                over = True
                    break   # no fallthrough past an unconditional jump
                i += 1
        return [raw[i] for i in sorted(keep)], over

    def _guards(self, raw):
        L = self.L
        skip = set()
        for i, ins in enumerate(raw):
            if ins.mnemonic == Mnemonic.CMP and ins.op0_kind == OpKind.MEMORY \
                    and ins.memory_base == IReg.RIP and ins.memory_size == 1 \
                    and imm_of(ins, 1) == 0:
                slotA = ins.ip_rel_memory_address
                j_idx = None
                for k in range(i + 1, min(i + 5, len(raw))):
                    w = raw[k]
                    if w.flow_control == FlowControl.CONDITIONAL_BRANCH and w.op0_kind == OpKind.NEAR_BRANCH64:
                        j_idx = k
                        break
                    if w.mnemonic not in (Mnemonic.MOV, Mnemonic.MOVZX):
                        break
                if j_idx is None:
                    continue
                T = raw[j_idx].near_branch_target
                found = False
                for k in range(j_idx + 1, min(j_idx + 24, len(raw))):
                    w = raw[k]
                    if w.mnemonic == Mnemonic.MOV and w.op0_kind == OpKind.MEMORY \
                            and w.memory_base == IReg.RIP and w.memory_size == 1 \
                            and w.ip_rel_memory_address == slotA and imm_of(w, 1) == 1:
                        if w.next_ip == T or (k + 1 < len(raw) and raw[k + 1].ip == T):
                            found = True
                        break
                    if w.mnemonic not in (Mnemonic.LEA, Mnemonic.MOV, Mnemonic.CALL,
                                          Mnemonic.MOVZX, Mnemonic.XOR, Mnemonic.PUSH, Mnemonic.SUB):
                        break
                    if w.ip >= T:
                        break
                if not found:
                    continue
                skip.add(ins.ip)
                skip.add(raw[j_idx].ip)
                for k in range(j_idx + 1, len(raw)):
                    w = raw[k]
                    if w.mnemonic == Mnemonic.MOV and w.op0_kind == OpKind.MEMORY \
                            and w.memory_base == IReg.RIP and w.memory_size == 1 \
                            and w.ip_rel_memory_address == slotA:
                        skip.add(w.ip)
                        break
                    if w.mnemonic == Mnemonic.LEA and w.op0_register == IReg.RCP \
                            if False else (w.mnemonic == Mnemonic.LEA and w.op0_register == IReg.RCX
                                           and w.memory_base == IReg.RIP):
                        skip.add(w.ip)
                    elif w.mnemonic == Mnemonic.CALL and w.op0_kind == OpKind.NEAR_BRANCH64 \
                            and w.near_branch_target == L.rt_init_meta:
                        skip.add(w.ip)
        ip_idx = {x.ip: xi for xi, x in enumerate(raw)}
        for i, ins in enumerate(raw):
            if ins.ip in skip:
                continue
            if ins.mnemonic == Mnemonic.MOV and ins.op0_kind == OpKind.REGISTER \
                    and ins.op1_kind == OpKind.MEMORY and ins.memory_base == IReg.RIP:
                usg = L.il.decode_slot(ins.ip_rel_memory_address)
                if not (usg and usg.get('kind') in (1, 2)):
                    continue
                regA = reg_name(ins.op0_register)
                k = i + 1
                if k >= len(raw):
                    continue
                w = raw[k]
                if not (w.mnemonic == Mnemonic.CMP and w.op0_kind == OpKind.MEMORY
                        and reg_name(w.memory_base) == regA and w.memory_displacement == 0xE4):
                    continue
                k += 1
                if k >= len(raw):
                    continue
                w = raw[k]
                if w.flow_control != FlowControl.CONDITIONAL_BRANCH or w.op0_kind != OpKind.NEAR_BRANCH64:
                    continue
                T = w.near_branch_target
                k += 1
                # T is the guard's own merge point (the fast `jne T` path
                # jumps straight past the call, whatever the slow path does
                # first) -- a provable bound, unlike a fixed instruction-
                # count lookahead, which can run past T and swallow real
                # code when no slot-reload mov exists to stop it early
                # (batch 21: `mov rcx,rA` direct reuse instead of a second
                # `mov rA,[slot]`, e.g. AmbientMusicSystem.Awake -- the
                # zeroing of a real call's null arg and the mov loading its
                # receiver both fell inside the old m3+4 window).
                t_idx = ip_idx.get(T)
                if t_idx is None or t_idx < k:
                    continue
                for m3 in range(k, t_idx):
                    w3 = raw[m3]
                    if w3.mnemonic == Mnemonic.CALL and w3.op0_kind == OpKind.NEAR_BRANCH64:
                        tgt = w3.near_branch_target
                        nm3 = L._call_name(tgt)
                        if 'class_init' in nm3 or 'ClassInit' in nm3 or tgt not in L.il.addr_to_method:
                            # the whole guard body is bounded by T; nothing
                            # in [i+1, t_idx) can be real code (see above)
                            for q in range(i + 1, t_idx):
                                skip.add(raw[q].ip)
                        break
        # icall thunk caches: mov rA,[rel CELL->method]; test rA,rA; jne T;
        # lea rcx,[rel sig]; call helper; mov [rel CELL],rax; T:
        # keep the load (it names the method), swallow the lazy-fill branch
        for i, ins in enumerate(raw):
            if ins.mnemonic == Mnemonic.MOV and ins.op0_kind == OpKind.REGISTER \
                    and ins.op1_kind == OpKind.MEMORY and ins.memory_base == IReg.RIP:
                usg = L.il.decode_slot(ins.ip_rel_memory_address)
                if not (usg and usg.get('kind') == 3):
                    continue
                k = i + 1
                regA = reg_name(ins.op0_register)
                # the test may sit a few instructions out (thunk prologues
                # park register saves between the load and the test); nothing
                # in between may overwrite regA
                t_idx = None
                for k2 in range(k, min(k + 7, len(raw))):
                    w = raw[k2]
                    if (w.mnemonic == Mnemonic.TEST and w.op0_kind == OpKind.REGISTER
                            and reg_name(w.op0_register) == regA):
                        t_idx = k2
                        break
                    if (w.mnemonic == Mnemonic.CMP and w.op0_kind == OpKind.REGISTER
                            and reg_name(w.op0_register) == regA and imm_of(w, 1) == 0):
                        t_idx = k2
                        break
                    if w.flow_control != FlowControl.NEXT or \
                            (w.op0_kind == OpKind.REGISTER
                             and reg_name(w.op0_register) == regA):
                        break
                if t_idx is None:
                    continue
                k = t_idx + 1
                if k >= len(raw):
                    continue
                w = raw[k]
                if w.flow_control != FlowControl.CONDITIONAL_BRANCH or w.op0_kind != OpKind.NEAR_BRANCH64:
                    continue
                T = w.near_branch_target
                range_ips = []
                saw_store = False
                for q in range(k, min(k + 10, len(raw))):
                    wq = raw[q]
                    if wq.ip >= T:
                        break
                    range_ips.append(wq.ip)
                    if wq.mnemonic == Mnemonic.MOV and wq.op0_kind == OpKind.MEMORY \
                            and wq.memory_base == IReg.RIP \
                            and wq.ip_rel_memory_address == ins.ip_rel_memory_address:
                        saw_store = True
                        break
                if saw_store:
                    skip.update(range_ips)
        return skip

    # ------------------------------------------------------------------
    def _make_blocks(self, insns, skip_ips, extra_leaders=None):
        entry_ip = self.entry_ip
        last_ip = self.last_ip
        leaders = {entry_ip}
        # EH pads are entered by the exception dispatcher, not by flow: they
        # must be block leaders or their instructions glue onto whatever
        # block precedes them (typically swallowing a trailing ret block)
        for p in (getattr(self, 'eh', None) or {}).get('pads') or ():
            if entry_ip <= p < last_ip:
                leaders.add(p)
        # jump-table targets (`_scan_jump_table_leaders`, run before this):
        # a target address reached ONLY through the table -- not also via a
        # direct Jcc/JMP the loop below would already catch -- is otherwise
        # never a leader here, so `_prewire_switches` (which runs AFTER
        # blocks exist) can't split a block at it either; its code silently
        # glues onto whatever block already contains that address instead of
        # becoming its own case.
        for t in extra_leaders or ():
            if entry_ip <= t < last_ip:
                leaders.add(t)
        for ins in insns:
            fc = ins.flow_control
            if fc == FlowControl.CONDITIONAL_BRANCH and ins.op0_kind == OpKind.NEAR_BRANCH64:
                t = ins.near_branch_target
                if entry_ip <= t < last_ip:
                    leaders.add(t)
                if ins.next_ip < last_ip:
                    leaders.add(ins.next_ip)
            elif fc in (FlowControl.UNCONDITIONAL_BRANCH, FlowControl.INDIRECT_BRANCH):
                if ins.op0_kind == OpKind.NEAR_BRANCH64:
                    t = ins.near_branch_target
                    if entry_ip <= t < last_ip:
                        leaders.add(t)
                if ins.next_ip < last_ip:
                    leaders.add(ins.next_ip)   # incl. `jmp reg` jump-table dispatch
        import bisect as _bi
        leaders = sorted(leaders)
        ips = [x.ip for x in insns]
        bounds = []
        for li, lip in enumerate(leaders):
            hi = leaders[li + 1] if li + 1 < len(leaders) else last_ip
            a = _bi.bisect_left(ips, lip)
            b = _bi.bisect_left(ips, hi)
            if b > a:
                bounds.append((lip, insns[a:b]))
        bmap = {lip: i for i, (lip, _) in enumerate(bounds)}
        blocks = [Block(i, blk) for i, (_, blk) in enumerate(bounds)]
        for i, (lip, blk) in enumerate(bounds):
            b = blocks[i]
            b.is_entry = (lip == entry_ip)
            last = blk[-1]
            fc = last.flow_control
            if last.ip in skip_ips:
                if i + 1 < len(blocks):
                    b.succs.append(i + 1)
                    b.term = ('fall', i + 1)
                else:
                    b.term = ('stop',)
                continue
            if fc == FlowControl.CONDITIONAL_BRANCH and last.op0_kind == OpKind.NEAR_BRANCH64:
                t = last.near_branch_target
                ti = bmap.get(t, -1)
                fi = i + 1 if i + 1 < len(blocks) else -1
                b.term = ('jcc', ti, fi)
                if ti >= 0:
                    b.succs.append(ti)
                if fi >= 0:
                    b.succs.append(fi)
            elif fc == FlowControl.UNCONDITIONAL_BRANCH and last.op0_kind == OpKind.NEAR_BRANCH64:
                t = last.near_branch_target
                ti = bmap.get(t, -1)
                if ti >= 0:
                    b.term = ('jmp', ti)
                    b.succs.append(ti)
                else:
                    # a near jmp to an address OUTSIDE this method (MSVC tail-
                    # calling a helper -- the write-barrier idiom's tail-jmp
                    # sibling, batch 21g, is one instance; an unrelated shared
                    # copy/memcpy-style helper is another) always finishes
                    # this method's execution, same as `ret` -- NOT a dead
                    # end. Treating it as an unresolved-but-live 'stop' (like
                    # `jmp reg`, just below) instead of a plain edgeless
                    # ('jmp', -1) matters because `_prune_nonreturning` seeds
                    # its "reaches a return" set from `term[0] in ('ret',
                    # 'stop')`: leaving this out of that set silently pruned
                    # every switch case (and any other branch) that ends this
                    # way, on the reasoning meant only for throw-stub dead
                    # ends, dropping real, correct case bodies entirely.
                    b.term = ('stop',)
            elif fc == FlowControl.RETURN:
                b.term = ('ret',)
            elif fc in (FlowControl.INTERRUPT, FlowControl.EXCEPTION):
                b.term = ('abort',)  # int3/ud2: end of a non-returning stub
            elif fc in (FlowControl.UNCONDITIONAL_BRANCH, FlowControl.INDIRECT_BRANCH):
                b.term = ('stop',)   # `jmp reg`: _prewire_switches fills in the targets
            else:
                if i + 1 < len(blocks):
                    b.succs.append(i + 1)
                    b.term = ('fall', i + 1)
                else:
                    b.term = ('stop',)
        for b in blocks:
            for s in b.succs:
                blocks[s].preds.append(b.bid)
        return blocks, bmap

    # ------------------------------------------------------------------
    def _rpo(self, blocks):
        seen = {0}
        order = []
        stack = [(0, iter(blocks[0].succs))]
        while stack:
            node, it = stack[-1]
            adv = False
            for s in it:
                if s >= 0 and s not in seen:
                    seen.add(s)
                    stack.append((s, iter(blocks[s].succs)))
                    adv = True
                    break
            if not adv:
                order.append(node)
                stack.pop()
        order.reverse()
        for b in blocks:
            if b.bid not in seen:
                order.append(b.bid)
        return order

    # ------------------------------------------------------------------
# ----------------------------------------------------------------------
# C# scope repair (compile gate, docs/todo.md P1). Structuring places a
# phi/merge local's declaration at its first textual assignment, which
# is often inside one arm of an if/else or one switch section while the
# value is read after the join -- CS0103 at every later read, CS0136
# when another arm declares the same name again, CS0841 when a goto
# loop reads it above its declaration. All 58k such reads in the full
# build are one shape: the SAME minted local, one type, whose uses are
# not all inside a scope that declares it first. The repair hoists one
# bare `T name;` to the top of the lowest block enclosing every
# declaration and use, and turns each inner declaration into a plain
# assignment. Nothing is initialised: a read the native code never
# assigns on some path stays visible as CS0165 instead of being masked
# by an invented `= default`.
_HOIST_KW = frozenset((
    'return', 'goto', 'else', 'case', 'new', 'throw', 'await', 'yield',
    'using', 'var', 'ref', 'out', 'in', 'is', 'as', 'typeof', 'default',
    'checked', 'unchecked', 'lock', 'fixed', 'unsafe', 'const', 'static'))
_HOIST_DECL_RX = re.compile(
    r'^(?P<ind>\s*)(?P<ty>[A-Za-z_][\w.]*(?:<[^=;()]*>)?(?:\[,*\])*\**\??)'
    r' (?P<nm>[A-Za-z_]\w*\d)(?P<rest> = .*|);\s*$')
_HOIST_ID_RX = re.compile(r'(?<![\w.@])([A-Za-z_]\w*)\b')
_HOIST_STR_RX = re.compile(
    r'@"(?:[^"]|"")*"|"(?:[^"\\]|\\.)*"|\'(?:[^\'\\]|\\.)*\'')
# declarations the statement regex cannot see (loop/catch/using heads,
# out/pattern variables): their names are never touched
_HOIST_HEADDECL_RX = re.compile(
    r'(?:\b(?:out|is)\s+[\w.<>\[\],]+\s+([A-Za-z_]\w*)'
    r'|^\s*(?:foreach|for|catch|using|fixed)\s*\(\s*[\w.<>\[\],*]+\s+'
    r'([A-Za-z_]\w*))')


def _hoist_code(ln):
    s = _HOIST_STR_RX.sub('""', ln)
    k = s.find('//')
    if k >= 0:
        s = s[:k]
    return re.sub(r'/\*.*?\*/', '', s)


def hoist_escaping_locals(lines, params=()):
    """Return (lines, n_hoisted); see the block comment above."""
    n = len(lines)
    parent = {0: None}
    open_line = {0: -1}
    head_line = {0: -1}
    scope_of = [0] * n
    stack = [0]
    nxt = 1
    for i, ln in enumerate(lines):
        s = ln.strip()
        if s.startswith('}'):
            if len(stack) > 1:
                stack.pop()
            scope_of[i] = stack[-1]
            if s.endswith('{') and s != '}':
                parent[nxt] = stack[-1]
                open_line[nxt] = i
                head_line[nxt] = i
                stack.append(nxt)
                nxt += 1
            continue
        scope_of[i] = stack[-1]
        if s == '{':
            parent[nxt] = stack[-1]
            open_line[nxt] = i
            j = i - 1
            while j >= 0 and (not lines[j].strip()
                              or lines[j].strip().startswith('//')):
                j -= 1
            head_line[nxt] = j
            stack.append(nxt)
            nxt += 1
    if len(stack) != 1:
        return lines, 0          # unbalanced: not ours to judge

    def anc(a):
        r = []
        while a is not None:
            r.append(a)
            a = parent[a]
        return r
    decls = collections.defaultdict(list)
    uses = collections.defaultdict(list)
    excl = set(params)
    codes = [_hoist_code(ln) for ln in lines]
    for i, c in enumerate(codes):
        for hm in _HOIST_HEADDECL_RX.finditer(c):
            excl.add(hm.group(1) or hm.group(2))
        if '=>' in c or 'delegate' in c:
            # lambda parameters/captures: scope rules differ, decline
            excl.update(_HOIST_ID_RX.findall(c))
        dm = _HOIST_DECL_RX.match(c)
        body = c
        if dm and dm.group('ty') not in _HOIST_KW:
            decls[dm.group('nm')].append((i, scope_of[i], dm.group('ty')))
            body = dm.group('rest')
        for t in _HOIST_ID_RX.findall(body):
            if t[-1].isdigit():
                uses[t].append((i, scope_of[i]))
    plan = {}
    for nm, ds in decls.items():
        if nm in excl:
            continue
        tys = {d[2] for d in ds}
        if len(tys) != 1:
            continue             # conflicting types: no single honest decl
        bad = len(ds) > 1
        if not bad:
            for (ui, us) in uses.get(nm, ()):
                ua = anc(us)
                if not any(di < ui and dsc in ua for (di, dsc, _) in ds):
                    bad = True
                    break
        if not bad:
            continue
        scs = [d[1] for d in ds] + [u[1] for u in uses.get(nm, ())]
        common = anc(scs[0])
        for sc in scs[1:]:
            a = set(anc(sc))
            common = [x for x in common if x in a]
        tgt = common[0]
        # a switch block has no statement position before its first case
        # label; the declaration goes to the enclosing block instead
        while tgt != 0 and head_line[tgt] >= 0 and \
                re.match(r'^\s*switch\b', lines[head_line[tgt]]):
            tgt = parent[tgt]
        plan[nm] = (tgt, tys.pop(), ds)
    if not plan:
        return lines, 0
    out = list(lines)
    drop = set()
    for nm, (tgt, ty, ds) in plan.items():
        for (di, _, _) in ds:
            dm = _HOIST_DECL_RX.match(codes[di])
            if dm.group('rest') == '':
                drop.add(di)
            else:
                k0 = len(dm.group('ind')) + len(dm.group('ty')) + 1
                out[di] = dm.group('ind') + out[di][k0:]
    ins = collections.defaultdict(list)
    for nm, (tgt, ty, ds) in sorted(plan.items(),
                                    key=lambda kv: kv[1][2][0][0]):
        ins[open_line[tgt]].append('%s %s;' % (ty, nm))
    res = []
    if -1 in ins:
        ind = ''
        for ln in lines:
            if ln.strip():
                ind = ln[:len(ln) - len(ln.lstrip())]
                break
        res.extend(ind + d for d in ins[-1])
    for i, ln in enumerate(out):
        if i in drop:
            continue
        res.append(ln)
        if i in ins:
            ind = ln[:len(ln) - len(ln.lstrip())] + '    '
            res.extend(ind + d for d in ins[i])
    return res, len(plan)


# The runtime class-init guard whose body every earlier pass emptied
# (`if (typeof(X).initialized == 0) { }`, 24k sites; CS1061 on Type):
# a pure flag read guarding nothing is a no-op, so it is dropped. Only
# the exact empty shape with a bare-identifier/literal comparand and no
# `else` is touched; a guard that still has a body keeps it.
_EMPTY_INIT_GUARD_RX = re.compile(
    r'^\s*if \((?:!\()?typeof\([^()]*\)\.initialized (?:==|!=) '
    r'(?:\w+)\)?\)\s*$')


def drop_empty_init_guards(lines):
    out = []
    i, n = 0, len(lines)
    while i < n:
        if (i + 2 < n and _EMPTY_INIT_GUARD_RX.match(lines[i])
                and lines[i + 1].strip() == '{'
                and lines[i + 2].strip() == '}'
                and not (i + 3 < n
                         and lines[i + 3].strip().startswith('else'))):
            i += 3
            continue
        out.append(lines[i])
        i += 1
    return out
