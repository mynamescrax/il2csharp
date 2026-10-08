from il2cpp.prelude import *  # noqa: F401,F403
from il2cpp.cfg import _Sink, _TEMP_RX
from il2cpp.common import csharp_type_name
from il2cpp.expr import Expr, _BARE_TOKEN_RX, _R8_TY, _mentions, _merge_arr_proof, _recv_fold, _recv_shaped
from il2cpp.expr import _tile_proof_for as _dry_tile_proof
from il2cpp.text import imm_of, reg_name
from il2cpp.x64 import ARG_REGS, GPRS, flag_cond

class _AnalyzeMixin:
    def _analyze(self, m, td, blocks, bmap):
        L = self.L
        # _rpo appends the unreachable tail (the EH pads, entered only by the
        # exception dispatcher) after the reachable order, so they lift too
        rpo = self._rpo(blocks)
        self.rpo = rpo
        # batch 38: _bind's cross-block render-site rewrite needs the
        # CFG (reachable-from-the-declaration check); blocks[bid] and
        # Block.bid line up by construction
        L._blocks = blocks
        m_returns = self._returns_value(m)
        self.phi_pre = {}
        L._phi_bytes = {}
        L._aggregate_phi_sources = {}
        L._aggregate_phi_types = {}

        def fresh_regs(counting):
            # pass 1 never counts uses (dry), so it runs on a plain dict:
            # the counting dispatch is a measurable share of total runtime
            L.regs = L._new_regs() if counting else {}
            L._u = 0
            # Lifter.lift() normally initializes these; the decompiler path
            # never runs it, and _call reads vt_recv* unconditionally
            L.vt_recv_slot = None
            L.vt_recv = None
            L.addr_of = {}
            L.cur_va = m.addr
            L.flags = None
            for r in GPRS + ['XMM%d' % k for k in range(16)]:
                if r == 'RSP':
                    continue
                L._u += 1
                e = Expr('v%d' % L._u, None, '?')
                e._unk = True         # fix 58: never written yet
                L.regs[r] = e
            L._setup_entry(m, td)

        FLAGS = '!flags'

        def flags_text():
            if L.flags and L.flags[0] is not None and L.flags[1] is not None:
                lhs, rhs = L.flags
                lt = lhs.text if lhs else '?'
                rt = rhs.text if rhs else '?'
                return (lt, rt)
            return None

        def narrow_null_edge(b, preds):
            # Only a single incoming machine equality edge proves a value
            # is zero here. Do not infer facts from overloaded managed ==.
            if len(preds) != 1:
                return
            pred = preds[0]
            if not pred.term or pred.term[0] != 'jcc':
                return
            match = re.fullmatch(r'([\w.]+) (==|!=) null', pred.cond or '')
            if match is None:
                return
            name, op = match.groups()
            null_edge = pred.term[1] if op == '==' else pred.term[2]
            if b.bid == null_edge:
                for reg, value in list(L.regs.items()):
                    if value is not None and value.text == name:
                        L.regs[reg] = Expr('0', None, 'int')

        # JP does not consume UCOMISS flags. In the exact
        # `ucomiss; jp X; jne X` diamond, the sole-predecessor
        # fallthrough JNE reads the same comparison operands.
        jcc_fallthrough_flags = {}

        def exec_block(b, dry):
            L.out = _Sink(b)
            L.dry = dry
            L._jcc_flags = None
            carried = jcc_fallthrough_flags.get(b.bid)
            if carried is not None:
                L.flags, L._flags_mn = carried
            for ins in b.insns:
                # the branch/return/jmp handlers below render at THIS
                # instruction's ip but run here, not through L._insn;
                # without this their note_use counts under the previous
                # instruction's ip and the same-ip guard eats it (the
                # flags-cond duplicate, batch 37)
                L._cur_ip = ins.ip
                if b.switch_snap_ip is not None and ins.ip == b.switch_snap_ip:
                    e = L.regs.get(b.switch_idx_reg)
                    if e is not None and e.text and len(e.text) < 160:
                        b.switch_idx = e.text
                if ins.ip in self.skip_ips:
                    continue
                mn = ins.mnemonic
                fc = ins.flow_control
                if fc == FlowControl.RETURN:
                    rax = L.regs.get('RAX')
                    xmm0 = L.regs.get('XMM0')
                    # Win64 returns scalar Single/Double values in XMM0;
                    # integer, pointer, and object values use RAX.  Prefer the
                    # metadata-selected ABI register even when unrelated state
                    # remains live in the other register, then fall back only
                    # for incomplete/unusual native bodies.
                    if L._return_reg == 'XMM0':
                        rv = xmm0 if xmm0 is not None else rax
                    else:
                        rv = rax if rax is not None else xmm0
                    if m_returns and rv is not None:
                        # returning a bare temp constrains it to the return type
                        rti = m.return_type
                        rty = L.il.types[rti] if 0 <= rti < len(L.il.types) else None
                        if rty is not None and _BARE_TOKEN_RX.match(rv.text):
                            L._type_hints.setdefault(rv.text, rty)
                        if rv.text == '&__ret':
                            # the echoed hidden buffer: return the value
                            b.ret = '__ret'
                        else:
                            b.ret = rv.text if len(rv.text) < 160 else L._materialize(rv, 160)
                    else:
                        b.ret = ''
                    continue
                if fc == FlowControl.CONDITIONAL_BRANCH and ins.op0_kind == OpKind.NEAR_BRANCH64:
                    lhs, rhs = (L.flags or (Expr('?', None, '?'), Expr('?', None, '?')))
                    L._jcc_flags = (L.flags, getattr(L, '_flags_mn', None))
                    L._note_use(lhs)
                    L._note_use(rhs)
                    next_bid = bmap.get(ins.next_ip)
                    if next_bid is not None and next_bid != b.bid \
                            and mn == Mnemonic.JP \
                            and getattr(L, '_flags_mn', None) == Mnemonic.UCOMISS:
                        nb = blocks[next_bid]
                        if nb.preds == [b.bid] and nb.insns and \
                                nb.insns[0].mnemonic == Mnemonic.JNE \
                                and nb.insns[0].near_branch_target == ins.near_branch_target:
                            jcc_fallthrough_flags[next_bid] = \
                                ((lhs, rhs), getattr(L, '_flags_mn', None))
                    lt = lhs.text if lhs else '?'
                    rt = rhs.text if rhs else '?'
                    op = L.CMP_OPS.get(mn)
                    # an int literal compared against an enum-typed
                    # lhs names the member (`Stage != 4` -> `!=
                    # SimulationStage.Host`) -- batch 39, same
                    # metadata the store path's _fimm enum fold uses
                    if op in ('==', '!=') and lhs is not None \
                            and isinstance(lhs.ty, tuple) \
                            and (rt.lstrip('-').isdigit() and rt not in ('', '-')):
                        etd = L._td_of(lhs.ty)
                        em = L.il.enum_members(etd) if etd is not None else None
                        if em is not None and int(rt) in em:
                            rt = '%s.%s' % (
                                csharp_type_name(L.meta.typedefs[etd].name),
                                em[int(rt)])
                    if op is None:
                        # the rare flag-specific jumps (JS/JNS/JO/JNO/JP/JNP --
                        # CMP_OPS never maps them) can't splice a bare '?' in
                        # as if it were a comparison operator: it collides
                        # with C#'s own ternary token whenever lt/rt is
                        # itself ternary-shaped (a CMOV-derived value), AND
                        # even in the ordinary case the incomplete `lt ? rt`
                        # gets silently completed by the pipeline's own
                        # `: default` false-arm synthesis into VALID but
                        # confidently WRONG C# (`cond ? 0 : default` where
                        # `cond` isn't the real branch condition at all --
                        # confirmed live, AudiencePath.SpawnPeople VA
                        # 0x1804fedf0: `if (!(((byte*)obj33 + 0x18)[0] - 0x1
                        # ? 0 : default))` for a real `jp`/parity-flag
                        # branch). `unknown` is honest and always parses --
                        # same fix il2csharp.py's dead _insn copy of this
                        # handler got in batch 27; this is the real path and
                        # was missed then (confirmed live-reachable: 510
                        # sites/170 methods in Assembly-CSharp alone, via
                        # work/scan_unmapped_condbr.py).
                        # fix 60: JS/JNS and JP/JNP ARE derivable once
                        # the flag SETTER is known (Lifter._flags_mn):
                        # arithmetic parks its result in the lhs slot, so
                        # SF is that result's sign; `test a,a` puts the
                        # tested value there; an SSE compare's parity flag
                        # means an unordered (NaN) operand. `cmp a,b` is
                        # deliberately NOT derived -- SF is sign(a-b),
                        # which is not `a < b` under signed overflow, and
                        # the census finds no such site in this corpus.
                        # Anything undecided stays the honest placeholder.
                        b.cond = flag_cond(
                            getattr(L, '_flags_mn', None), mn, lt, rt) \
                            or 'unknown'
                        L.flags = None
                        continue
                    # boolean tests: test al,al -> x / !x
                    lty = lhs.ty if lhs else None
                    if lty is not None and ((lty[1] >> 16) & 0xFF) == 0x02                             and rt in ('null', '0'):
                        b.cond = lt if op in ('!=', '>') else '!%s' % lt
                    elif rt == 'null':
                        # `test r,r` renders its zero as null; only a reference
                        # comparison should read that way. A string or
                        # pointer result can carry an int kind (call
                        # results classify te < 0x10 by register, so
                        # 0x0e/0x0f land on 'int'); the type tuple is
                        # authoritative there: never 0 (mi 5694
                        # `text5 != 0` on a string, via resolved
                        # ICustomFormatter.Format).
                        _lte = None
                        try:
                            _lil = getattr(L, 'il', None)
                            _lte = _lil._type_enum(lhs.ty) \
                                if _lil is not None and lhs is not None and lhs.ty is not None else None
                        except Exception:
                            _lte = None
                        zero = '0' if (op not in ('==', '!=')
                                       or (lhs is not None and lhs.kind in ('int', 'float')
                                           and _lte not in (0x0e, 0x0f))) \
                            else 'null'
                        b.cond = '%s %s %s' % (lt, op, zero)
                    else:
                        b.cond = '%s %s %s' % (lt, op, rt)
                    L.flags = None
                    continue
                if mn == Mnemonic.JMP and ins.op0_kind in (OpKind.REGISTER,
                                                           OpKind.MEMORY):
                    # jump-table dispatch: already wired by _prewire_switches; the
                    # index expression was sampled at switch_snap_ip above.
                    if b.switch_targets:
                        continue
                    # otherwise an indirect tail call -- resolve it like a call so
                    # vtable slots still turn into real method names
                    L._call(ins, None)
                    if m_returns:
                        # fix 66d: Win64 returns R4/R8 in XMM0 and
                        # everything else in RAX.  `RAX or XMM0` always
                        # took RAX -- and `_call`'s `_fresh_unknowns`
                        # re-mints RAX on every call -- so a float tail
                        # call read a fresh `vN` while its real value sat
                        # in XMM0 (MainModule.get_duration @0x182C80520).
                        primary = L._return_reg
                        secondary = 'RAX' if primary == 'XMM0' else 'XMM0'
                        rv = L.regs.get(primary)
                        if rv is None:
                            rv = L.regs.get(secondary)
                        if rv is not None and rv.text and not _TEMP_RX.match(rv.text):
                            b.ret = rv.text if len(rv.text) < 160 \
                                else L._materialize(rv, 160)
                            # fix 66c: `jmp reg` carries ('stop',) from CFG
                            # build and 'stop' emits NOTHING, so this
                            # `b.ret` was never printed.  Harmless while
                            # `_call` also left a bound statement behind
                            # (unresolved return type); once the callee
                            # resolves, `_call` binds the result into RAX
                            # instead and the call vanished outright.  A
                            # tail jmp leaves for good, so the callee's
                            # value IS ours -- `return <call>;` is what the
                            # machine code does.  Only when a real text was
                            # recovered: an unnameable tail value keeps
                            # 'stop' rather than inventing a bare `return;`.
                            ok_ret = True
                        else:
                            ok_ret = False
                        # fix 66d: `_analyze` lifts the SAME Block objects
                        # twice (dry pass, then real), so deciding the
                        # terminator only on success let a dry-pass
                        # `('ret',)` -- and its materialized `tNNN` text,
                        # which `_TEMP_RX` does not match -- survive a real
                        # pass that declined.  Decide both together.
                        if b.term is None or b.term[0] in ('stop', 'ret'):
                            b.term = ('ret',) if ok_ret else ('stop',)
                    continue
                if mn == Mnemonic.JMP and ins.op0_kind == OpKind.NEAR_BRANCH64:
                    t = ins.near_branch_target
                    if t < self.entry_ip or t >= self.last_ip:
                        # A direct tail jump to the structurally proved
                        # sqrt wrapper returns its XMM0 double directly.
                        if t == getattr(L, 'rt_sqrt', None):
                            value = L.reg('XMM0')
                            L._hint_tok(value, _R8_TY)
                            text = value.text if value is not None and not value._unk else '?'
                            result = L._mk('Math.Sqrt(%s)' % text, _R8_TY, 'float')
                            b.ret = result.text if len(result.text) < 160 \
                                else L._materialize(result, 160)
                            b.term = ('ret',)
                            continue
                        cands = L.il.addr_candidates.get(t)
                        recv0 = L.regs.get('RCX')
                        info = None
                        if cands and len(cands) == 1:
                            info = cands[0]
                        elif cands:
                            # Constructor recovery is stricter than the legacy
                            # receiver-chain lookup: exact current-constructor
                            # context, exact fresh-allocation identity, and a
                            # unique closed zero-argument constructor ABI.
                            info = L._shared_parameterless_ctor_target(cands, recv0)
                            if info is None:
                                recv_td = L._td_of(recv0.ty) if recv0 is not None else None
                                if recv_td is None and recv0 is not None:
                                    recv_td = L._array_receiver_td(recv0.ty)
                                chain = L._legacy_shared_receiver_chain(recv_td)
                                hits = [c for c in cands if c[0] == 'method'
                                        and L.meta.methods[c[1]].declaring in chain]
                                if len(hits) == 1:
                                    info = hits[0]
                        if info is None and not cands:
                            info = L.il.addr_to_method.get(t)
                        if info or L.bin.is_exec_va(t):
                            args = []
                            arg_exprs = []
                            for r in ARG_REGS:
                                e = L.regs.get(r)
                                args.append(e.text if e else '_')
                                arg_exprs.append(e)
                            while args and args[-1] == '_':
                                args.pop()
                                arg_exprs.pop()
                            args = [a if a and a.strip() else '_' for a in args]
                            # fix 94: a shared tail's hidden instantiation
                            # argument is compiler plumbing (same proof as
                            # `_call`), and trailing stale unknowns are not
                            # arguments (fix 58). Both lists stay parallel.
                            tail_gen = None
                            tail_nm = None
                            tail_ret = None
                            if info is None and cands and len(cands) > 1:
                                tail_ret = L._shared_tail_return_target(cands)
                                tail_gen = L._tail_hidden_generic(cands, args, arg_exprs)
                                if tail_gen is not None:
                                    tail_nm = tail_gen[0]
                                    _tgi = tail_gen[2]
                                    if _tgi < len(args):
                                        args = args[:_tgi] + args[_tgi + 1:]
                                    if _tgi < len(arg_exprs):
                                        arg_exprs = arg_exprs[:_tgi] + arg_exprs[_tgi + 1:]
                                L._tail_trim_stale(args, arg_exprs)
                                if info is None and tail_ret is not None and tail_ret[0] == 'method' \
                                        and (tail_gen is None or tail_gen[1] is None):
                                    info = tail_ret
                            if info is not None and info[0] == 'method':
                                m2 = L.meta.methods[info[1]]
                                args = L._tail_method_args(info[1], args, arg_exprs)
                                init_kind = L._constructor_initializer_kind(
                                    m2, arg_exprs[0] if arg_exprs else None)
                                if init_kind is not None:
                                    L.emit(ins.ip, '%s..ctor(%s); return;' %
                                           (init_kind, ', '.join(args[1:])), None)
                                else:
                                    rc = args[0] if args else '?'
                                    if rc.startswith('&') and (
                                            '.' in rc
                                            or _BARE_TOKEN_RX.match(rc[1:])
                                            or re.match(r'^s_[0-9a-fA-F]+$', rc[1:])):
                                        rc = rc[1:]
                                    if not m2.is_static and args and rc != '?' \
                                            and (rc == 'this' or '.' in rc
                                                 or _BARE_TOKEN_RX.match(rc)
                                                 or (_recv_shaped(rc)
                                                     and not m2.name.startswith('.'))):
                                        # the _recv_shaped arm is fix 40c,
                                        # mirroring the Lifter-side rule
                                        nm2 = m2.name.lstrip('.').replace('|', '_').replace('@', '_')
                                        call = '%s.%s(%s)' % (_recv_fold(rc), nm2, ', '.join(args[1:]))
                                    else:
                                        call = '%s(%s)' % (L._info_name(info), ', '.join(args))
                                    _sg137 = L._tail_accessor(info[1], args)  # fix 137
                                    if _sg137 is not None:
                                        call = _sg137
                                    rti = m2.return_type
                                    void = 0 <= rti < len(L.il.types) and \
                                        ((L.il.types[rti][1] >> 16) & 0xFF) == 0x01
                                    L._emit_tail(ins.ip, call, None, void=void)
                            else:
                                nm = L._call_name(t)
                                if t in getattr(L, 'rt_isinst', ()) and len(arg_exprs) >= 2:
                                    # Tail-path mirror of `_call`'s IsInst intrinsic:
                                    # a direct tail jump to the proved helper with a
                                    # klass-kind bare `typeof(T)` klass folds to the
                                    # managed `as` (the spray tail is dropped, exactly
                                    # as `_call` drops it by returning early). Opaque
                                    # klass expressions keep the honest `sub_` below.
                                    _tobj, _tklass = arg_exprs[0], arg_exprs[1]
                                    if _tobj is not None and _tklass is not None \
                                            and _tklass.kind == 'klass' \
                                            and isinstance(_tklass.text, str) \
                                            and _tklass.text.startswith('typeof(') \
                                            and _tklass.text.endswith(')'):
                                        _tname = _tklass.text[len('typeof('):-1]
                                        L._emit_tail(ins.ip, '(%s as %s)' % (
                                            _tobj.text, _tname), None, marker=False)
                                        continue
                                raise_exc = L._named_raise_throw(t, nm)
                                if raise_exc is not None:
                                    L.emit(ins.ip, 'throw new %s();' % raise_exc, None)
                                elif tail_gen is not None and tail_gen[1] is not None:
                                    # fix 94: resolved through the hidden
                                    # instantiation argument -- render the
                                    # true generic callee, never the shared
                                    # marker.
                                    _tg_call, _tg_m = L._tail_generic_call(
                                        tail_gen[0], tail_gen[1], args, arg_exprs)
                                    _tg_rti = _tg_m.return_type
                                    _tg_void = 0 <= _tg_rti < len(L.il.types) and \
                                        ((L.il.types[_tg_rti][1] >> 16) & 0xFF) == 0x01
                                    L._emit_tail(ins.ip, _tg_call, None, void=_tg_void,
                                                 marker=False)
                                elif tail_ret is not None and tail_ret[0] == 'generic':
                                    _sv_xmm = list(getattr(L, '_xmm_pending', []) or [])
                                    _sv_cca = getattr(L, '_call_class_args', None)
                                    _sv_slot = dict(getattr(L, 'slot_types', {}) or {})
                                    _sv_hints = dict(getattr(L, '_type_hints', {}) or {})
                                    try:
                                        _tr_call, _tr_m = L._tail_generic_call(tail_ret[1], tail_ret[2], args, arg_exprs)
                                    except Exception:
                                        L._xmm_pending = _sv_xmm
                                        L._call_class_args = _sv_cca
                                        L.slot_types = _sv_slot
                                        L._type_hints = _sv_hints
                                        _eff_nm = tail_nm or nm
                                        if _eff_nm in L.RT_ARITY and len(args) > L.RT_ARITY[_eff_nm]:
                                            args = args[:L.RT_ARITY[_eff_nm]]
                                        elif tail_nm is None and re.fullmatch(r'sub_[0-9a-f]+', nm) and len(args) > 4:
                                            args = args[:4]
                                        L._emit_tail(ins.ip, '%s(%s)' % (_eff_nm, ', '.join(args)), None,
                                                       marker=False)
                                    else:
                                        _tr_rti = _tr_m.return_type
                                        _tr_void = 0 <= _tr_rti < len(L.il.types) and ((L.il.types[_tr_rti][1] >> 16) & 0xFF) == 0x01
                                        L._emit_tail(ins.ip, _tr_call, None, void=_tr_void,
                                                     marker=False)
                                elif t in L.rt_wbarrier and args:

                                    # a write barrier can be the very last
                                    # thing a void method does, compiled as
                                    # a tail jmp -- same conversion as the
                                    # ordinary (non-tail) case in `_call`,
                                    # via the shared helper (fix 21f/21g).
                                    dst, src2 = L._wb_operands(args, arg_exprs)
                                    L._wb_finish(ins.ip, dst, src2, None, tail=True)
                                elif nm == 'il2cpp_array_new' and args and args[0].startswith('typeof('):
                                    m0 = re.search(r'typeof\(([^[]+)(\[(,*)\])\)', args[0])
                                    if m0:
                                        rank = 1 + len(m0.group(3))
                                        dims = [a for a in args[1:1 + rank] if a and a != '_']
                                        L._emit_tail(ins.ip, 'new %s[%s]' % (
                                            m0.group(1), ']['.join(dims) if dims else '0'), None,
                                            marker=False)
                                    else:
                                        L._emit_tail(ins.ip, '%s(%s)' % (nm, ', '.join(args)), None,
                                                       marker=False)
                                else:
                                    _eff_nm = tail_nm or nm
                                    if tail_nm is None and '/*shared body,' in _eff_nm:
                                        # mirror of the lifter-side tail trim
                                        _keep = L._shared_tail_keep(t, args)
                                        if _keep is not None and 0 < _keep < len(args):
                                            args = args[:_keep]
                                            arg_exprs = arg_exprs[:_keep]
                                    if _eff_nm in L.RT_ARITY and len(args) > L.RT_ARITY[_eff_nm]:
                                        args = args[:L.RT_ARITY[_eff_nm]]
                                    elif tail_nm is None and re.fullmatch(r'sub_[0-9a-f]+', nm) and len(args) > 4:
                                        args = args[:4]
                                    L._emit_tail(ins.ip, '%s(%s)' % (_eff_nm, ', '.join(args)), None,
                                                   marker=False)
                    continue
                L._insn(ins, b.insns, 0, None, self.last_ip)

        # ---- pass 1 (dry): discover phi merge locations
        # wipe BEFORE entry setup: _setup_entry (inside fresh_regs)
        # installs the entry stack-parameter names/types, and wiping
        # after discards them -- every stack-arg load then degrades
        # to an anonymous untyped s_N (GetChars mi 5769: baseDecoder
        # arrived at the cmov merge as untyped s_88). Wipe-then-setup
        # keeps the anti-stale intent with this method's evidence.
        L.rsp_delta = 0
        L.stack_map = {}
        L.slot_types = {}
        fresh_regs(False)
        L.var_n = 1000
        entry_state = dict(L.regs)
        merge_locs = {}
        # fix 131: pass-1 twin of the pass-2 flags carry (see there)
        end_flags1 = {}

        def _flags_key1(fl):
            if not fl:
                return None
            return tuple((e.text if e is not None else None) for e in fl)

        _fl_live = {}

        def _flags_live_in(b):
            # fix 131: restore a predecessor's pair only into a block that
            # reads a flag before defining it (`setg`/`jp`/`cmovcc` right
            # after a jcc split).  A block that rewrites the flags first
            # never needs them, and handing it the pair anyway exposed the
            # operands to bounds/use-count readers (KeybindsManager.Update:
            # a loop body re-read `FOBT.Length` and the bound became a phi).
            v = _fl_live.get(b.bid)
            if v is None:
                v, done = False, 0
                for ins in b.insns:
                    if ins.rflags_read & ~done:
                        v = True
                        break
                    done |= ins.rflags_modified
                _fl_live[b.bid] = v
            return v

        _fl_touch = {}

        def _flags_touched(b):
            # any flag write, or a call (the callee clobbers them)
            v = _fl_touch.get(b.bid)
            if v is None:
                v = any(ins.rflags_modified or ins.flow_control in (
                    FlowControl.CALL, FlowControl.INDIRECT_CALL)
                    for ins in b.insns)
                _fl_touch[b.bid] = v
            return v

        def _top_call(t):
            # `recv.M(args)` / `T.M<A, B>(args)`: the whole text is one call
            t = t.strip() if t else ''
            if not t.endswith(')') or t[0] in '*(!-~&':
                return False
            depth = 0
            for j in range(len(t) - 1, -1, -1):
                c = t[j]
                if c == ')':
                    depth += 1
                elif c == '(':
                    depth -= 1
                    if depth == 0:
                        break
            head = re.sub(r'<[^<>]*>|\[[^\[\]]*\]', '', t[:j])
            return bool(head) and ' ' not in head and '(' not in head \
                and (head[-1].isalnum() or head[-1] == '_')

        def _restored_pair(fl):
            # fix 131: the successor gets private copies of the operands, so
            # its reads (bounds checks, `jae` after `cmp; jge`) never count
            # toward binding the predecessor's Expr -- a loop-header bound
            # bound that way landed in the body (`for (i = 0; i < objN;
            # ...)` with objN assigned inside).  A whole-call operand stays
            # shared: re-rendering it would duplicate the call, and binding
            # it once is the honest render (`int num1 = Compare(...); ...
            # return num1 > 0;`).  Predecessors agreeing on "no pair"
            # (math.uint2(float): both arms of `comiss; jbe` end without a
            # flag write) restore None.
            if not fl:
                return None
            return tuple((e if (e is None or _top_call(e.text))
                          else Expr(e.text, e.ty, e.kind)) for e in fl)

        for bid in rpo:
            b = blocks[bid]
            if not b.is_entry and not b.preds and bid not in self._pad_bids:
                continue
            preds_done = [blocks[p] for p in b.preds if blocks[p].end_state is not None]
            if b.is_entry or not preds_done:
                L.regs = dict(entry_state)
            else:
                merged = {}
                keys = set()
                for p in preds_done:
                    keys |= set(p.end_state)
                # sorted: set order is hash-seeded, and iterating it in
                # creation order would number the phis differently on every
                # run
                for k in sorted(keys):
                    texts = {(p.end_state.get(k).text if p.end_state.get(k) else None)
                             for p in preds_done}
                    merged[k] = None if len(texts) > 1 else next(iter(texts), None)
                L.regs = {}
                for k, v in merged.items():
                    if isinstance(v, Expr):
                        L.regs[k] = v
                    elif isinstance(v, str):
                        e = Expr(v)
                        # The text-only rebuild drops every Expr fact. Keep
                        # the frame address when all preds agree on it: an
                        # RBP / RSP-copy base that loses _stack_offset sends
                        # every later [base+N] in the dry pass to the legacy
                        # disp-keyed slot (s_50 where pass 2 says s_b0), so
                        # the dry back-edge carries no `!mem:` tile at all
                        # (FIMSpace census: 249 of 333 missing back keys).
                        sos = {getattr(p.end_state.get(k), '_stack_offset', None)
                               for p in preds_done}
                        if len(sos) == 1 and None not in sos:
                            e._stack_offset = next(iter(sos))
                        # Same for a stack tile: a unanimous whole-tile
                        # proof (same origin, closed type, offset, width,
                        # bytes) keeps the slice, so dry piece reads and
                        # the back-edge end_state pass 2 merges against see
                        # the tile instead of a sliceless text copy.
                        if k.startswith('!mem:'):
                            vs = [p.end_state.get(k) for p in preds_done]
                            tk = getattr(L.il, '_closed_type_key', lambda t: t)
                            if _dry_tile_proof(vs, tk) is not None:
                                e._slice = vs[0]._slice
                                if getattr(vs[0], '_bytes', None) is not None:
                                    e._bytes = vs[0]._bytes
                        pts = [_merge_arr_proof(p.end_state.get(k))
                               for p in preds_done]
                        if pts and all(t is not None for t in pts) \
                                and len(set(pts)) == 1 \
                                and L.il._type_enum(pts[0]) in (0x1d, 0x14):
                            e._dry_proof = (pts[0], True)
                        L.regs[k] = e
                    else:
                        L.regs[k] = Expr('?', None, '?')
                merge_locs[bid] = {k for k, v in merged.items() if v is None}
            L.flags = None
            fprev = L.regs.get(FLAGS)
            if fprev is not None and isinstance(fprev.ty, tuple) and len(fprev.ty) == 2:
                L.flags = (Expr(fprev.ty[0], None, '?'), Expr(fprev.ty[1], None, '?'))
                # fix 60: this pair is rebuilt from the predecessor's
                # carried TEXT, so which instruction set it is genuinely
                # unknown -- never inherit some other block's mnemonic
                L._flags_mn = None
            _thru = None
            if not b.is_entry and preds_done:
                _pf = [end_flags1.get(p.bid) for p in preds_done]
                if all(x is not None for x in _pf) \
                        and len({_flags_key1(x[0]) for x in _pf}) == 1:
                    _mns = {x[1] for x in _pf}
                    _thru = (_pf[0][0], next(iter(_mns)) if len(_mns) == 1 else None)
                    if _flags_live_in(b):
                        L.flags = _restored_pair(_thru[0])
                        L._flags_mn = _thru[1]
            L._carried_flags = L.flags
            narrow_null_edge(b, preds_done)
            exec_block(b, dry=True)
            b.end_state = dict(L.regs)
            _fl, _fmn = L.flags, getattr(L, '_flags_mn', None)
            if _fl is None and getattr(L, '_jcc_flags', None) is not None:
                _fl, _fmn = L._jcc_flags
            if _thru is not None and not _flags_touched(b):
                # fix 131: a block that never writes the flags passes its
                # predecessors' pair through (math.uint2(float): both arms
                # of `comiss; jbe` join on a second `jbe`)
                _fl, _fmn = _thru
            end_flags1[b.bid] = (_fl, _fmn)
            ft = flags_text()
            if ft:
                b.end_state[FLAGS] = Expr('%s%s' % ft, None, '?')
            b.stmts = []

        # ---- pass 2 (real): emit with stable phi vars
        jcc_fallthrough_flags.clear()
        L.rsp_delta = 0
        L.stack_map = {}
        L.slot_types = {}
        fresh_regs(True)
        L.var_n = 1000
        entry_state = dict(L.regs)
        phi: Dict[Tuple[int, str], str] = {}
        # fix 131: the flags pair each pass-2 block ended with.  `L.flags`
        # is lifter-global, so without a per-edge restore a block opened
        # with whatever block rpo executed last -- a `setg al` after
        # `test eax,eax; jne` read a sibling path's `shr eax,1Fh`
        # (Computer.ShouldRankBefore 0x18069C7A0: `return num1 >> 31 > 0`
        # for `return Compare(a, b) > 0`).
        end_flags = {}

        def _flags_key(fl):
            if not fl:
                return None
            return tuple((e.text if e is not None else None) for e in fl)

        for bid in rpo:
            b = blocks[bid]
            if not b.is_entry and not b.preds and bid not in self._pad_bids:
                b.stmts = []
                continue
            b.stmts = []
            preds_done = [blocks[p] for p in b.preds if blocks[p].end_state is not None]
            if b.is_entry or not preds_done:
                L.regs = L._new_regs(entry_state)
            else:
                merged = {}
                keys = set()
                for p in preds_done:
                    keys |= set(p.end_state)
                # sorted: set order is hash-seeded, and iterating it in
                # creation order would number the phis differently on every
                # run
                for k in sorted(keys):
                    vals = [p.end_state.get(k) for p in preds_done]
                    texts = [(v.text if v else None) for v in vals]
                    # a register that some pred never carried is not "the
                    # same value on every path" -- it is missing evidence
                    # (VOLATILE pops, paths that never defined it). Naming
                    # it a phi, not collapsing to None, keeps the later
                    # read honest (objN) instead of rendering `?`.
                    # Two loads can print the same array expression but
                    # denote separate native values. A later use may bind
                    # only one Expr to a temp; preserve both with a phi.
                    separate_defs = (len(set(texts)) == 1 and vals[0] is not None
                        and '[' in texts[0] and ']' in texts[0]
                        and all(v.kind == 'obj' and isinstance(v.ty, tuple) for v in vals)
                        and len({v._defpos for v in vals}) > 1
                        and any(v._uses for v in vals))
                    if len(set(texts)) == 1 and vals[0] is not None and not separate_defs:
                        merged[k] = vals[0]
                    elif k == FLAGS:
                        defined = [v for v in vals if isinstance(v, Expr) and isinstance(v.ty, tuple)]
                        if defined and len(defined) != len(vals):
                            merged[k] = defined[0]
                        else:
                            key = (bid, k)
                            if key not in phi:
                                L._u += 1
                                phi[key] = 'v%d' % L._u
                            merged[k] = Expr(phi[key], None, '?')
                    else:
                        key = (bid, k)
                        if key not in phi:
                            L._u += 1
                            phi[key] = 'v%d' % L._u
                        tys = {(v.ty if isinstance(v, Expr) and isinstance(v.ty, tuple) else None) for v in vals}
                        kinds = {(v.kind if isinstance(v, Expr) else None) for v in vals}
                        # a phi whose preds mix a type with unknowns takes
                        # the type: the unknown pred is missing evidence,
                        # not contradicting it (a loop header's entry edge
                        # is often an untyped load, its back edge the typed
                        # arithmetic that updates the counter)
                        nn = [t for t in tys if t is not None]
                        type_key = getattr(L.il, '_closed_type_key', lambda t: t)
                        pty = nn[0] if nn and len({type_key(t) for t in nn}) == 1 else None
                        if len(kinds) == 1:
                            pkind = next(iter(kinds))
                        else:
                            nnk = {k for k in kinds if k not in ('?', None)}
                            pkind = next(iter(nnk)) if len(nnk) == 1 else '?'
                        if pty is not None:
                            self._var_types.setdefault(phi[key], pty)
                        L._aggregate_phi_sources[phi[key]] = vals
                        merged[k] = Expr(phi[key], pty, pkind)
                        pts = [_merge_arr_proof(x) for x in vals]
                        if pts and all(t is not None for t in pts) \
                                and len(set(pts)) == 1 \
                                and L.il._type_enum(pts[0]) in (0x1d, 0x14):
                            merged[k]._newarr = True
                        if k.startswith('!mem:') and pty is not None:
                            width = int(k.rsplit(':', 1)[1])
                            if L.il._sf_field_size(pty, 0) == width:
                                merged[k] = L._fragment(merged[k], 0, width)
                        if k.startswith('!mem:'):
                            try:
                                from il2cpp.expr import _tile_proof_for as _tpf
                                _tp = _tpf(vals, type_key)
                            except Exception:
                                _tp = None
                            if _tp is not None:
                                try:
                                    merged[k]._tile_proof = _tp
                                except Exception:
                                    pass
                # Kill-on-write across phi copies: a copy on an in-edge
                # assigns the phi var, so any register whose text reads that
                # var would re-render with the post-copy value inside this
                # block. Bind it to a temp now; _build_phi_copies prepends
                # `temp = text;` to the copies on every in-edge.
                names_here = {n for (b2, k2), n in phi.items()
                              if b2 == bid and k2 != FLAGS}
                if names_here:
                    pre = []
                    for k in list(merged):
                        if k == FLAGS or (bid, k) in phi:
                            continue
                        v = merged[k]
                        if isinstance(v, Expr) and v.text and v.text != '?':
                            if any(_mentions(v.text, n) for n in names_here):
                                L._u += 1
                                tmp = 'v%d' % L._u
                                if isinstance(v.ty, tuple):
                                    self._var_types.setdefault(tmp, v.ty)
                                pre.append((tmp, v.text))
                                merged[k] = Expr(tmp, v.ty, v.kind)
                                if getattr(v, '_newarr', False):
                                    merged[k]._newarr = True
                                if getattr(v, '_arr_klass', None) is not None:
                                    merged[k]._arr_klass = v._arr_klass
                                if getattr(v, '_dry_proof', None) is not None:
                                    merged[k]._dry_proof = v._dry_proof
                    if pre:
                        self.phi_pre.setdefault(bid, []).extend(pre)
                L.regs = L._new_regs(merged)
            # fix 131: open the block with its predecessors' flags when
            # every predecessor already ran in this pass and they agree;
            # an entry/orphan block has none.  Disagreeing or back-edge
            # predecessors keep the legacy carry (follow-up).
            _thru = None
            if b.is_entry or not preds_done:
                L.flags, L._flags_mn = None, None
            else:
                _pf = [end_flags.get(p.bid) for p in preds_done]
                if all(x is not None for x in _pf) \
                        and len({_flags_key(x[0]) for x in _pf}) == 1:
                    _mns = {x[1] for x in _pf}
                    _thru = (_pf[0][0], next(iter(_mns)) if len(_mns) == 1 else None)
                    if _flags_live_in(b):
                        L.flags = _restored_pair(_thru[0])
                        L._flags_mn = _thru[1]
            L._carried_flags = L.flags
            ft = flags_text()
            if ft:
                L.regs[FLAGS] = Expr('%s%s' % ft, None, '?')
            narrow_null_edge(b, preds_done)
            exec_block(b, dry=False)
            b.end_state = dict(L.regs)
            _fl, _fmn = L.flags, getattr(L, '_flags_mn', None)
            if _fl is None and getattr(L, '_jcc_flags', None) is not None:
                _fl, _fmn = L._jcc_flags
            if _thru is not None and not _flags_touched(b):
                _fl, _fmn = _thru
            end_flags[b.bid] = (_fl, _fmn)

        # ---- SSA destruction: materialize each phi as a copy on its in-edges
        self.phi_names = set(phi.values())
        self._build_phi_copies(blocks, phi, FLAGS)
        L._phi_bytes = self.phi_bytes
        L._flush_pending_calls(getattr(self, 'phi_copies', None))

    # ------------------------------------------------------------------
    _TOKRX = re.compile(r'(?<![\w.])(v\d+)(?![\w])')

    def _build_phi_copies(self, blocks, phi, FLAGS):
        """A phi at block B for location k means "the value differs per path".
        Emit `phi = <value at end of P>;` on every edge P->B so the variable has
        a visible definition instead of appearing out of nowhere."""
        perblk: Dict[int, Dict[str, Dict[int, str]]] = {}
        self.phi_bytes = {}
        L = self.L
        L._cur_ip = -1
        unknown = self._unknown_phis(blocks, phi, FLAGS)
        for (bid, k), name in phi.items():
            if k == FLAGS:
                continue
            vals = {}
            for p in blocks[bid].preds:
                pb = blocks[p]
                if pb.end_state is None:
                    continue
                v = pb.end_state.get(k)
                txt = v.text if isinstance(v, Expr) else None
                if not txt or txt == '?' or len(txt) > 400:
                    continue
                # fix 126: an edge whose value is an unknown register (never
                # written / clobbered, `_unk`) or an all-unknown phi carries
                # no value, so it gets no copy. The copy `phi = vN;` read a
                # name nothing defines (CS0103) and only moved the unknown one
                # hop; leaving the edge uncopied keeps the phi var unassigned
                # on that path, which the compiler reports honestly (CS0165)
                # if -- and only if -- a later read can actually see it.
                if getattr(v, '_unk', False) or txt in unknown:
                    continue
                # the copy renders the value once more: count it, so a
                # value already rendered in a cond or stmt (the call
                # tested by test/jcc, batch 37) binds to its temp here
                # instead of re-rendering the whole text. When the bind
                # fires it rewrites the earlier sites via e._sites and
                # lands the declaration at the value's defpos; the sink
                # is neutralized so the site this records is a dud --
                # the copy text below then reads the temp name directly.
                save_out = L.out
                L.out = []
                try:
                    L._note_use(v)
                finally:
                    L.out = save_out
                vals[p] = v.text
                aggregate_ty = L._aggregate_phi_types.get(name)
                if aggregate_ty is not None:
                    size = L.il._sf_field_size(aggregate_ty, 0)
                    typed = L._piece_value(v, 0, size, aggregate_ty)
                    if typed is not None:
                        vals[p] = typed.text
                        self._var_types[name] = aggregate_ty
                raw = getattr(v, '_bytes', None)
                if raw is None:
                    sl = getattr(v, '_slice', None)
                    if sl is not None and len(sl) == 3 and sl[1] == 0 and sl[2] == 16:
                        raw = getattr(sl[0], '_bytes', None)
                if isinstance(raw, (bytes, bytearray)) and len(raw) == 16:
                    self.phi_bytes.setdefault((bid, name), {})[p] = bytes(raw)
            if vals:
                perblk.setdefault(bid, {})[name] = vals
        alias = self._coalesce_phis(perblk)
        self.phi_alias = alias
        self.phi_names = {n for names in perblk.values() for n in names
                          if n not in alias}
        groups = {}
        for bid, names in perblk.items():
            for nm, vals in names.items():
                if nm in alias:
                    continue
                for p, txt in vals.items():
                    if txt != nm:
                        groups.setdefault((p, bid), []).append((nm, txt))
        self.phi_copies = {}
        for key, cps in groups.items():
            self.phi_copies[key] = self._order_copies(cps)
        # Prepend the kill-on-write materializations: they must run before
        # any copy assigns the phi var they read, and must exist on every
        # in-edge, since the successor's body references the temp on every
        # path -- including edges that carry no copies at all. The temps
        # join phi_names here because the assignment above replaced the set.
        for bid, pre in self.phi_pre.items():
            self.phi_names.update(t for t, _ in pre)
            for p in blocks[bid].preds:
                if blocks[p].end_state is None:
                    continue
                cps = self.phi_copies.setdefault((p, bid), [])
                cps[:0] = ['%s = %s;' % (t, x) for t, x in pre]

    @staticmethod
    def _unknown_phis(blocks, phi, FLAGS):
        """Greatest fixed point of "every incoming value is unknown": a phi
        is unknown when each predecessor edge carries a missing value, an
        `_unk` register, itself, or another unknown phi. Starting from all
        phis and only ever removing keeps loop-carried unknowns (a header
        phi fed by the entry's garbage and its own back edge) unknown."""
        cand = {n for (bid, k), n in phi.items() if k != FLAGS}
        while cand:
            drop = set()
            for (bid, k), n in phi.items():
                if n not in cand:
                    continue
                for p in blocks[bid].preds:
                    es = blocks[p].end_state
                    if es is None:
                        continue
                    v = es.get(k)
                    if v is None or getattr(v, '_unk', False):
                        continue
                    t = getattr(v, 'text', None)
                    if not t or t == '?' or t == n or t in cand:
                        continue
                    drop.add(n)
                    break
            if not drop:
                break
            cand -= drop
        return cand

    def _coalesce_phis(self, perblk):
        """Two phis in the same block that take the same value on every incoming
        edge are the same variable -- IL2CPP keeps a counter in several registers
        at once, which would otherwise show up as `num1`/`num2` in lockstep."""
        alias: Dict[str, str] = {}

        def canon(n):
            seen = 0
            while n in alias and seen < 32:
                n = alias[n]
                seen += 1
            return n

        for _round in range(4):
            for names in perblk.values():
                for vals in names.values():
                    for p in list(vals):
                        vals[p] = self._TOKRX.sub(lambda m: canon(m.group(1)), vals[p])
            moved = False
            for names in perblk.values():
                live = [n for n in sorted(names, key=lambda s: int(s[1:]))
                        if n not in alias]
                for i, a in enumerate(live):
                    for b in live[i + 1:]:
                        if b not in alias and names[a] == names[b]:
                            alias[b] = a
                            moved = True
            if not moved:
                break
        return {n: canon(n) for n in alias}

    def _order_copies(self, cps):
        """Sequentialize a parallel copy: a copy that overwrites a name another
        copy still reads has to come later; true cycles get spilled to a temp."""
        out = []
        pending = list(cps)
        guard = 0
        while pending and guard < 300:
            guard += 1
            lhs = {n for n, _ in pending}
            reads = {n: set(self._TOKRX.findall(r)) & lhs for n, r in pending}
            rest = []
            progress = False
            for n, r in pending:
                if any(m != n and n in reads[m] for m, _ in pending):
                    rest.append((n, r))
                else:
                    out.append('%s = %s;' % (n, r))
                    progress = True
            if not progress and rest:
                n = rest[0][0]
                self.L._u += 1
                tmp = 'v%d' % self.L._u
                self.phi_names.add(tmp)
                ty = self._var_types.get(n)
                if ty is not None:
                    self._var_types[tmp] = ty
                out.append('%s = %s;' % (tmp, n))
                rx = re.compile(r'(?<![\w.])%s(?![\w])' % n)
                rest = [(mm, (rr if mm == n else rx.sub(tmp, rr))) for mm, rr in rest]
            pending = rest
        return out

    def _prune_nonreturning(self, blocks):
        """Drop edges into paths that can never come back. IL2CPP guards every
        member access with a null check that branches to a throw stub; those
        stubs are compiler scaffolding, and keeping them buries the real code
        (and leaves loops without an exit, which breaks postdominance)."""
        good = set()
        stack = [b.bid for b in blocks if b.term and b.term[0] in ('ret', 'stop')]
        while stack:
            x = stack.pop()
            if x in good:
                continue
            good.add(x)
            for p in blocks[x].preds:
                if p not in good:
                    stack.append(p)
        if 0 not in good:
            return              # nothing returns; the method is one big stub
        changed = False
        for b in blocks:
            if b.bid not in good or not b.succs:
                continue
            keep = [s for s in b.succs if s in good]
            if len(keep) == len(b.succs):
                continue
            changed = True
            b.succs = keep
            if not keep:
                b.term = ('abort',)
            elif b.term and b.term[0] == 'jcc':
                b.term = ('jmp', keep[0])
                b.cond = None   # the surviving edge is unconditional now
            elif b.term and b.term[0] == 'switch':
                # fix 65c: BLANK the pruned slot, never remove it -- a case
                # value is its entry's position in this list, so filtering
                # renumbers every case after the one dropped.  `_emit_switch`
                # already skips a slot whose target isn't a block leader.
                b.switch_targets = [(t if self._ip2bid(blocks, t) in good else None)
                                    for t in (b.switch_targets or [])]
            else:
                b.term = (b.term[0] if b.term else 'jmp', keep[0])
        if not changed:
            return
        for b in blocks:
            b.preds = []
        for b in blocks:
            for s in b.succs:
                if 0 <= s < len(blocks):
                    blocks[s].preds.append(b.bid)

    @staticmethod
    def _ip2bid(blocks, ip):
        for b in blocks:
            if b.insns and b.insns[0].ip == ip:
                return b.bid
        return -1

    def _scan_jump_table_leaders(self, insns):
        """Pre-scan every `jmp reg` in the method's flat instruction stream for
        a jump table, BEFORE `_make_blocks` runs. `_make_blocks` only learns
        block leaders from direct Jcc/JMP near-branch targets; a jump table's
        own targets are otherwise only decoded later, inside
        `_prewire_switches`, which runs AFTER blocks already exist -- so a
        target address not independently reached some other way was never a
        block leader, `_prewire_switches`'s `ip2bid.get(tip, -1)` silently
        drops the edge, and that case's code just glues onto whatever block
        already occupies its address range (rendering as part of a neighboring
        case's body, with no `if`/`case` of its own to gate it -- a real
        wrong-output bug, not a cosmetic one, whenever such a target wasn't
        also independently a leader for some other reason). Returns the union
        of every table's targets, meant to be folded into `_make_blocks`'s own
        leader set."""
        leaders = set()
        for j, ins in enumerate(insns):
            if ins.mnemonic == Mnemonic.JMP and ins.op0_kind == OpKind.REGISTER:
                entries, _, _ = self._jump_table(insns, j, self.entry_ip, self.last_ip)
                if entries:
                    leaders.update(entries)
        return leaders

    def _prewire_switches(self, blocks):
        """Find jump-table dispatches and wire their targets into the CFG before
        any analysis runs, so RPO / dominators / postdominators see them."""
        ip2bid = {b.insns[0].ip: b.bid for b in blocks if b.insns}
        found = False
        for b in blocks:
            if not b.insns:
                continue
            last = b.insns[-1]
            if not (last.mnemonic == Mnemonic.JMP and last.op0_kind == OpKind.REGISTER):
                continue
            info = self._scan_switch(b, last)
            if info is None:
                continue
            entries, idx_reg, snap_ip = info
            b.switch_targets = entries
            b.switch_idx_reg = idx_reg
            b.switch_snap_ip = snap_ip
            b.term = ('switch',)
            b.succs = []
            for tip in entries:
                tb = ip2bid.get(tip, -1)
                if tb >= 0 and tb not in b.succs:
                    b.succs.append(tb)
            found = True
        if not found:
            return
        for b in blocks:
            b.preds = []
        for b in blocks:
            for s in b.succs:
                if 0 <= s < len(blocks):
                    blocks[s].preds.append(b.bid)

    def _scan_switch(self, b, jmp_ins):
        r = self._jump_table(b.insns, len(b.insns) - 1, self.entry_ip, self.last_ip)
        return r if r[0] else None

    def _jump_table(self, insns, j, lo, hi):
        """Recognize MSVC jump-table dispatch at a `jmp reg`:
        A) lea rB,[rip+T]; mov rJ,[rB+rI*8]; jmp rJ
        B) lea rB,[rip+BASE]; mov rJ,[rB+rI*4+D]; add rJ,rB; jmp rJ
        with an optional `movzx rI, byte [rB+rI2+D2]` group table in front.
        Returns ([target ips], index register, ip to sample it before)."""
        from il2cpp.common import u32 as _u32, u64 as _u64
        none = (None, None, None)
        # `_prewire_switches` calls this per-BLOCK, and block splitting can
        # leave very little lookback context in `insns` before the `jmp` --
        # sometimes not even the table-base `lea`/index `mov` themselves, let
        # alone the `cmp idxreg,N` bounds check further back still (both seen
        # live on Shift At Midnight's ComputedStyle.ApplyFromComputedStyle).
        # `_decode`'s own reachability-trace caller passes the full flat list
        # already (`self._flat_ip_idx` isn't set that early), so redirect
        # only when it's both available and actually has this ip.
        flat = getattr(self, '_flat_insns', None)
        flat_idx = getattr(self, '_flat_ip_idx', None)
        jmp_ip = insns[j].ip
        if flat is not None and flat_idx is not None and jmp_ip in flat_idx:
            insns = flat
            j = flat_idx[jmp_ip]
        regJ = reg_name(insns[j].op0_register)
        for k in range(j - 1, max(j - 8, -1), -1):
            x = insns[k]
            if x.mnemonic == Mnemonic.ADD and x.op0_kind == OpKind.REGISTER \
                    and reg_name(x.op0_register) == regJ and x.op1_kind == OpKind.REGISTER:
                continue
            if x.mnemonic not in (Mnemonic.MOV, Mnemonic.MOVZX, Mnemonic.MOVSXD):
                continue
            if not (x.op0_kind == OpKind.REGISTER and reg_name(x.op0_register) == regJ
                    and x.op1_kind == OpKind.MEMORY and x.memory_index != IReg.NONE
                    and x.memory_base != IReg.NONE):
                continue
            idx_reg = reg_name(x.memory_index)
            scale = x.memory_index_scale
            disp = x.memory_displacement
            tabreg = reg_name(x.memory_base)
            snap_ip = x.ip
            # The table-base `lea rB,[rip+BASE]` is usually a few
            # instructions behind the load, but MSVC emits ONE such lea per
            # function and reuses the register for EVERY jump table in it --
            # a second dispatch reached from inside the FIRST table's case
            # bodies then has no lea anywhere near it (CurrentDayManager
            # 0x1806A6000: `lea rdx,[rel 180000000h]` at 0x1806A6924 serves
            # the table at 0x1806A7348, and the dispatch at 0x1806A69D6 --
            # 45 instructions later, reachable ONLY through that first table
            # -- reuses RDX for the table at 0x1806A737C).  So keep walking
            # back for the nearest earlier one.
            #
            # This is a linear walk over a flat list, NOT dominance, so which
            # lea reaches is a guess -- and the intervening case bodies really
            # do clobber the register on paths that don't reach here.  It is
            # safe because (a) it cannot regress anything: the walk stops at
            # the NEAREST match, so wherever a lea sat inside the old
            # 5-instruction window it still wins and nothing changes, and the
            # longer range is only reached where the old code gave up; and
            # (b) everything below VALIDATES the guess -- a wrong base fails
            # `va2off` or yields fewer than 3 targets inside this method's own
            # [lo, hi) extent, and the `cmp idxreg,N` bound caps the scan
            # independently.
            k2 = base_va = None
            for k2c in range(k - 1, -1, -1):
                y = insns[k2c]
                if not (y.mnemonic == Mnemonic.LEA and y.op0_kind == OpKind.REGISTER
                        and reg_name(y.op0_register) == tabreg
                        and y.memory_base == IReg.RIP):
                    continue
                k2, base_va = k2c, y.ip_rel_memory_address
                break
            if base_va is None:
                return none
            w = 4 if scale == 4 else 8
            tab_va = base_va + (disp if w == 4 else 0)
            off = self.L.bin.va2off(tab_va)
            if off is None:
                return none
            # The address-range break below (`lo <= tgt < hi`) only stops
            # at the FUNCTION's extent, not at this table's own end -- if
            # a second, unrelated jump table sits right after this one in
            # .rdata (two separate switches in the same method each get
            # their own table, laid out back to back), its targets still
            # fall inside the same [lo, hi) and the loop silently walks
            # into it, doubling up on entries that were never reachable
            # through THIS index register. MSVC always guards a jump-table
            # dispatch with `cmp idxreg,N; ja/jae default` immediately
            # before computing the table address; that compare's operand
            # is the true, sound entry count -- look for it and cap the
            # scan there instead of trusting the address-range break alone.
            # A sparse switch routes the operand through a byte group table
            # first (`movzx idx,byte [base+op+G]`), and the real switch
            # operand is that load's own index register.  Find it BEFORE
            # reading entries: that table is the switch's case map (fix
            # 65b), and the bounds check further back is written against
            # its index, not against the jump table's.
            grp_va = grp_idx = None
            for k3 in range(k - 1, max(k - 8, -1), -1):
                z = insns[k3]
                if z.mnemonic in (Mnemonic.MOVZX, Mnemonic.MOV, Mnemonic.MOVSX) \
                        and z.op0_kind == OpKind.REGISTER \
                        and reg_name(z.op0_register) == idx_reg \
                        and z.op1_kind == OpKind.MEMORY and z.memory_size == 1 \
                        and z.memory_index != IReg.NONE:
                    grp_idx = reg_name(z.memory_index)
                    if reg_name(z.memory_base) == tabreg:
                        grp_va = base_va + z.memory_displacement
                    snap_ip = z.ip
                    break
            cap = 512
            # `insns` is already the flat, unsplit per-method stream by
            # this point (redirected above) whenever that's available, so
            # `k2`/`k` are real flat indices -- scan the whole span
            # covering both the table-base `lea` and the index `mov`; the
            # compiler doesn't order `cmp/ja` consistently relative to
            # the `lea` (seen both before it AND sandwiched between it
            # and the `mov`).
            # floored at k-12: with a far-away reused lea (fix 64) an
            # unfloored span would sweep the whole function for a bounds
            # check.  Never binds in the old near-lea case (k2 >= k-5).
            #
            # fix 65a: walk that span BACKWARD, so the guard that actually
            # dominates the table computation wins.  MSVC emits a chain of
            # range tests before a dispatch and the earliest `cmp` on the
            # index register is routinely an unrelated one -- CookieParser
            # .Get 0x1824E70E0 has `cmp eax,1; jne` ten instructions before
            # its real `cmp eax,0Ch; ja`, and taking the first capped a
            # 13-entry table at 2, which then died on the `< 3` floor.
            # The index is followed through register copies as well
            # (`movsxd rax,ecx` at ScanReserved 0x18214D990 leaves the
            # bound written against ECX while the table is indexed by RAX).
            names = {idx_reg}
            if grp_idx:
                names.add(grp_idx)
            for ka in range(k - 1, max(k - 24, -1), -1):
                a = insns[ka]
                if a.mnemonic in (Mnemonic.MOV, Mnemonic.MOVSXD, Mnemonic.MOVZX,
                                  Mnemonic.MOVSX) \
                        and a.op0_kind == OpKind.REGISTER \
                        and a.op1_kind == OpKind.REGISTER \
                        and reg_name(a.op0_register) in names:
                    names.add(reg_name(a.op1_register))
            src, lo_i, hi_i = insns, max(min(k2, k), k - 12), max(k2, k)
            for k4 in range(hi_i, lo_i - 11, -1):
                if not (0 <= k4 < len(src)):
                    continue
                br = src[k4]
                if br.flow_control != FlowControl.CONDITIONAL_BRANCH:
                    continue
                for k5 in range(k4 - 1, max(k4 - 4, lo_i - 11), -1):
                    if not (0 <= k5 < len(src)):
                        continue
                    cm = src[k5]
                    if cm.mnemonic == Mnemonic.CMP and cm.op0_kind == OpKind.REGISTER \
                            and reg_name(cm.op0_register) in names \
                            and cm.op1_kind in (OpKind.IMMEDIATE8, OpKind.IMMEDIATE8TO32,
                                                 OpKind.IMMEDIATE32, OpKind.IMMEDIATE8TO64):
                        c0 = imm_of(cm, 1) + 1
                        if 1 <= c0 <= 4096:
                            cap = c0
                            break
                if cap != 512:
                    break
            # fix 65b: expand the jump table THROUGH the group table, so an
            # entry exists per OPERAND value instead of per table slot.
            # Every byte of the group table is a slot index, so this both
            # gives the jump table its exact length (max(group)+1 -- which
            # the [lo,hi) walk below cannot find, because the group table
            # sits immediately after the jump table and its first bytes
            # read as an out-of-method "entry" that stops the walk) and
            # makes `case N:` mean what it says downstream: `_emit_switch`
            # numbers cases by list position, and before this the position
            # was a jump-table slot (HID.DetermineLayout 0x18268AB70
            # printed Hatswitch, operand 9, as `case 1`).
            # Used only when it validates end to end; anything short of
            # that falls back to the plain read, `< 3` floor included.
            entries = []
            if grp_va is not None and cap != 512:
                go = self.L.bin.va2off(grp_va)
                if go is not None and 0 <= go and go + cap <= len(self.L.bin.d):
                    gb = self.L.bin.d[go:go + cap]
                    n = max(gb) + 1
                    # the two tables must not overlap -- if they do, this
                    # group VA is wrong and its bytes mean nothing here
                    if n <= 512 and (grp_va >= tab_va + w * n or grp_va + cap <= tab_va):
                        slots = []
                        for c in range(n):
                            if w == 8:
                                tgt = _u64(self.L.bin.d, off + c * 8)
                            else:
                                tgt = (base_va + _u32(self.L.bin.d, off + c * 4)) \
                                    & 0xFFFFFFFFFFFFFFFF
                            if not (lo <= tgt < hi):
                                break
                            slots.append(tgt)
                        if len(slots) == n:
                            entries = [slots[g] for g in gb]
            if not entries:
                for c in range(min(512, cap)):
                    if w == 8:
                        tgt = _u64(self.L.bin.d, off + c * 8)
                    else:
                        tgt = (base_va + _u32(self.L.bin.d, off + c * 4)) & 0xFFFFFFFFFFFFFFFF
                    if not (lo <= tgt < hi):
                        break
                    entries.append(tgt)
            if len(entries) < 3:
                return none
            if grp_idx:
                idx_reg = grp_idx
            return entries, idx_reg, snap_ip
        return none

    def _returns_value(self, m):
        try:
            t = self.L.il.types[m.return_type]
            return bool(t) and ((t[1] >> 16) & 0xFF) != 0x01
        except Exception:
            return True

    # ------------------------------------------------------------------
    def _dominators(self, blocks, rpo, reach):
        n = len(blocks)
        full = (1 << n) - 1
        dom = {bid: full for bid in reach}
        dom[0] = 1
        order = [b for b in rpo if b in reach and b != 0]
        changed = True
        while changed:
            changed = False
            for bid in order:
                b = blocks[bid]
                ps = [p for p in b.preds if p in reach and p in dom]
                new = full
                if ps:
                    for p in ps:
                        new &= dom[p]
                else:
                    new = 0
                new |= 1 << bid
                if new != dom.get(bid, -1):
                    dom[bid] = new
                    changed = True
        return dom

    def _postdominators(self, blocks, rpo, reach):
        n = len(blocks)
        full = (1 << n) - 1
        exits = {b.bid for b in blocks if b.bid in reach and b.term and b.term[0] in ('ret', 'stop', 'abort')}
        if not exits:
            exits = {max(reach)}
        pdom = {bid: full for bid in reach}
        for e in exits:
            pdom[e] = 1 << e
        rev = sorted(reach, reverse=True)
        changed = True
        while changed:
            changed = False
            for bid in rev:
                if bid in exits:
                    continue
                b = blocks[bid]
                ss = [x for x in b.succs if x >= 0 and x in reach and x in pdom]
                new = full
                if ss:
                    for x in ss:
                        new &= pdom[x]
                else:
                    new = 0
                new |= 1 << bid
                if new != pdom.get(bid, -1):
                    pdom[bid] = new
                    changed = True
        return pdom

    def _ipdom(self, bid, pdom):
        """Nearest join point. Postdominators of a block form a chain, so the
        immediate one is the member that all the others postdominate in turn."""
        s = pdom.get(bid, 0) & ~(1 << bid)
        if s == 0:
            return -1
        members = [i for i in range(s.bit_length()) if s & (1 << i)]
        best, best_n = -1, -1
        for cand in members:
            pc = pdom.get(cand, 0)
            if all((pc >> x) & 1 for x in members if x != cand):
                return cand
            n = bin(pc).count('1')
            if n > best_n:
                best, best_n = cand, n
        return best

    # ------------------------------------------------------------------
    def _loops(self, blocks, dom, reach):
        loops = []
        bids = {b.bid for b in blocks if b.bid in reach}
        for b in blocks:
            for s in b.succs:
                if s >= 0 and s in bids and s in dom and b.bid in dom                         and (dom[b.bid] >> s) & 1:
                    body = {s, b.bid}
                    stack = [b.bid]
                    while stack:
                        x = stack.pop()
                        for p in blocks[x].preds:
                            if p not in body:
                                body.add(p)
                                stack.append(p)
                    loops.append((s, body, b.bid))
        loops.sort(key=lambda t: len(t[1]))
        hdr = {}
        for h, body, latch in loops:
            # several back edges to one header are one loop: union the bodies,
            # otherwise the outer back edge degenerates into a goto
            if h in hdr:
                hdr[h] = (hdr[h][0] | body, hdr[h][1])
            else:
                hdr[h] = (body, latch)
        return hdr

    # ------------------------------------------------------------------
