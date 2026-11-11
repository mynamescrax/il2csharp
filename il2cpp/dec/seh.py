from il2cpp.prelude import *  # noqa: F401,F403
from il2cpp.cfg import LBL
from il2cpp.text import imm_of, reg_name

class _SehMixin:
    def _seh_catch_type(self, pad_va):
        """The managed filter of a typed catch compiles into the pad head as
        the inlined IsInst fast path against a cached klass:

            mov rD,[rel CELL]            ; the catch type (usage slot)
            mov rK,[ex]                  ; ex->klass
            movzx a, byte [rD+0x130]     ; T.typeHierarchyDepth
            cmp [rK+0x130], a            ; ex depth < T depth -> rethrow
            mov rT,[rK+0xC8]             ; ex->klass.typeHierarchy
            cmp [rT + c*8 - 8], rD       ; hierarchy[T.depth-1] != T -> rethrow

        Returns the type name when the sequence resolves, else None. The
        tight triple (depth load + depth compare + scaled hierarchy compare
        against the same klass register) never matches the using-statement
        dispose guards, which only run one IsInst."""
        L = self.L
        b = L.il.bin
        off = b.va2off(pad_va)
        if off is None:
            return None
        dec = Decoder(64, b.d[off:off + 280], ip=pad_va)
        insns = []
        for ins in dec:
            insns.append(ins)
            if len(insns) >= 30:
                break
        kreg = kcell = None
        kreg_i = -99
        for i, ins in enumerate(insns):
            if ins.mnemonic == Mnemonic.MOV and ins.op0_kind == OpKind.REGISTER \
                    and ins.op1_kind == OpKind.MEMORY and ins.memory_base == IReg.RIP:
                u = L.il.decode_slot(ins.ip_rel_memory_address)
                if u is not None and str(u.get('text') or '').startswith('typeof('):
                    kreg, kcell, kreg_i = reg_name(ins.op0_register), u, i
            elif kreg is not None and i - kreg_i <= 12 \
                    and ins.mnemonic == Mnemonic.MOVZX \
                    and ins.op0_kind == OpKind.REGISTER and ins.op1_kind == OpKind.MEMORY \
                    and reg_name(ins.memory_base) == kreg and ins.memory_displacement == 0x130:
                depth_reg = reg_name(ins.op0_register)
                # the filter is pure register/branch code: any call inside the
                # window means the IsInst belongs to handler body logic
                if any(w.mnemonic == Mnemonic.CALL for w in insns[kreg_i:i + 1]):
                    continue
                for j in range(i + 1, min(i + 5, len(insns))):
                    w = insns[j]
                    if w.mnemonic == Mnemonic.CMP and w.op0_kind == OpKind.MEMORY \
                            and w.memory_displacement == 0x130 \
                            and w.op1_kind == OpKind.REGISTER \
                            and reg_name(w.op1_register) == depth_reg \
                            and reg_name(w.memory_base) != kreg:
                        # the depth mismatch must branch; both mismatch branches
                        # share the rethrow target in a genuine filter
                        nxt = insns[j + 1] if j + 1 < len(insns) else None
                        if nxt is None or nxt.flow_control not in (
                                FlowControl.CONDITIONAL_BRANCH,):
                            continue
                        depth_tgt = nxt.near_branch_target
                        for k in range(j + 2, min(j + 8, len(insns))):
                            x = insns[k]
                            if x.mnemonic != Mnemonic.CMP or x.op0_kind != OpKind.MEMORY \
                                    or x.memory_index == IReg.NONE or x.memory_index_scale != 8 \
                                    or x.op1_kind != OpKind.REGISTER \
                                    or reg_name(x.op1_register) != kreg:
                                continue
                            if any(y.mnemonic == Mnemonic.CALL for y in insns[j + 1:k + 1]):
                                continue
                            d = x.memory_displacement
                            if d < 0:
                                d += 1 << 64
                            if d != (1 << 64) - 8:
                                continue
                            nxt2 = insns[k + 1] if k + 1 < len(insns) else None
                            if nxt2 is None or nxt2.flow_control != FlowControl.CONDITIONAL_BRANCH \
                                    or nxt2.near_branch_target != depth_tgt:
                                continue
                            return kcell['text'][7:-1]
        return None

    def _seh_prepare(self, blocks, bmap, dom, reach):
        """Plan try/catch/finally emission for the __CxxFrameHandler4 pads,
        one region per TryBlockMapEntry4 -- `self._seh_regions`, outer-to-
        inner ordered (see Il2Cpp._eh4_regions).

        The pads and the exact try span both come from the ehdata tables
        now (Il2Cpp._eh4_parse decodes dispIPtoStateMap): `region['start']`
        is mapped to a block via `_block_of_va`, since ehdata state
        boundaries land wherever the compiler put them, not at our branch-
        derived block leaders. Everything else -- the exception slot, catch
        type, close point, and the compiled finally's normal-path duplicate
        -- is still located structurally per region, scoped to that
        region's own funclets so an unrelated try's pad can't be picked up
        by the close/ex-slot scans.

        A try whose own span didn't resolve exactly (multi-span: reached
        from several switch/goto entry points, ~11% of try entries -- see
        Il2Cpp._eh4_regions) is not given its own region: tried once
        (scoped to just that try's own funclets, structural open-scan
        instead of the exact VA), the structural "zero-store before the
        pad" open-heuristic turned out to key off a wrapper slot the
        switch's sibling cases share, not a per-case one -- three sibling
        case bodies each got their own region, all landing on the same
        open block and nesting three deep with the first two never
        reaching their close. Exact-only is the safe half of the win;
        recovering the multi-span trys needs the pad's own continuation
        address (not decoded), not a heuristic. If no try in the method
        resolved exactly, the whole flat pad list is treated as one
        region, exactly as before ehdata region decoding existed."""
        self._seh_starts = sorted(bmap.items())
        regions_data = (self.eh.get('regions') or []) if self.eh else []
        out_regions = []
        for rd in regions_data:
            open_bid = self._block_of_va(rd['start'], blocks)
            if open_bid is None:
                continue
            r = self._seh_build_region(rd['pads'], blocks, bmap, reach, open_bid,
                                       rd.get('end'), rd.get('end1'))
            if r is not None:
                out_regions.append(r)
        if not out_regions:
            r = self._seh_build_region(self.eh['pads'], blocks, bmap, reach, None)
            if r is not None:
                out_regions.append(r)
        self._seh_regions = out_regions

    def _seh_build_region(self, funclet_vas, blocks, bmap, reach, open_bid, end=None, end1=None):
        """One region: `funclet_vas` are this try's own catch/finally
        entries. `open_bid` is the exact try-start block if already known
        (ehdata path), else None to fall back to the structural scan (the
        reachable block that zero-initialises the wrapper slot the pad
        tests -- `mov qword [rsp+K],0` / pad tail `mov rcx,[rsp+K]; test;
        jne rethrow`). `end` is the ehdata span's exclusive end VA; the
        close block is the block containing `end-1` -- the last protected
        instruction -- when it resolves (else the structural pad-rejoin
        scan below). `end1` is the FIRST span's exclusive end, which a
        finally-shaped try uses instead (its extra spans are the
        funclet-dedup tail in foreign code -- see Il2Cpp._eh4_regions)."""
        seh = {'open': None, 'close': None, 'opened': False, 'closed': False,
               'pads': [], 'kind': 'catch'}
        pad_bids = [bmap[p] for p in funclet_vas if p in bmap]
        if not pad_bids:
            return None
        # pad component: everything reachable from this try's own pads that
        # is not reachable from the entry
        comp = set()
        stack = list(pad_bids)
        while stack:
            x = stack.pop()
            if x in comp or x in reach:
                continue
            comp.add(x)
            for s in blocks[x].succs:
                if s >= 0:
                    stack.append(s)
        if not comp:
            return None
        seh['pads'] = sorted(comp)
        # exception slot: loaded then tested inside the pad component
        ex_slot = None
        for bi in sorted(comp):
            insns = blocks[bi].insns
            for i, ins in enumerate(insns):
                if ins.mnemonic == Mnemonic.MOV and ins.op0_kind == OpKind.REGISTER \
                        and ins.op1_kind == OpKind.MEMORY \
                        and ins.memory_base == IReg.RSP and ins.memory_index == IReg.NONE \
                        and reg_name(ins.op0_register) in ('RCX', 'RDX', 'RAX', 'RBX', 'RSI', 'RDI'):
                    rg = reg_name(ins.op0_register)
                    k = i + 1
                    while k < len(insns) and k < i + 4:
                        w = insns[k]
                        if w.mnemonic in (Mnemonic.TEST, Mnemonic.CMP) \
                                and w.op0_kind == OpKind.REGISTER \
                                and reg_name(w.op0_register) == rg:
                            ex_slot = ins.memory_displacement
                            break
                        # a write to the same register re-binds it; the
                        # next test belongs to the newer load
                        if w.op0_kind == OpKind.REGISTER \
                                and reg_name(w.op0_register) == rg:
                            break
                        k += 1
                    if ex_slot is not None:
                        break
            if ex_slot is not None:
                break
        seh['ex_slot'] = ex_slot
        seh['kind'] = 'finally' if ex_slot is not None else 'catch'
        if seh['kind'] == 'catch' and funclet_vas:
            seh['catch_type'] = self._seh_catch_type(funclet_vas[0])
        # try entry: the exact ehdata-derived block, else the reachable
        # block that zeroes the exception slot
        pad_ip = min(blocks[bi].insns[0].ip for bi in comp)
        if open_bid is None:
            if ex_slot is not None:
                for b in blocks:
                    if b.bid not in reach:
                        continue
                    for ins in b.insns:
                        if ins.mnemonic == Mnemonic.MOV and ins.op0_kind == OpKind.MEMORY \
                                and ins.memory_base == IReg.RSP and ins.memory_index == IReg.NONE \
                                and ins.memory_displacement == ex_slot and imm_of(ins, 1) == 0 \
                                and ins.memory_size in (5, 3):
                            open_bid = b.bid
                            break
                    if open_bid is not None:
                        break
            else:
                # catch-throw shape: the pad never tests the wrapper slot,
                # but the try entry still zero-initialises it; take the
                # last such store before the pad
                for b in blocks:
                    if b.bid not in reach:
                        continue
                    for ins in b.insns:
                        if ins.ip >= pad_ip:
                            continue
                        if ins.mnemonic == Mnemonic.MOV and ins.op0_kind == OpKind.MEMORY \
                                and ins.memory_base == IReg.RSP and ins.memory_index == IReg.NONE \
                                and imm_of(ins, 1) == 0 and ins.memory_size == 5:
                            open_bid = b.bid
        if open_bid is None:
            return None
        # continuation: where the pad component rejoins normal flow; the
        # exact ehdata close (block containing the span's last protected
        # byte) takes priority when it resolves. A finally-shaped try uses
        # its FIRST span's end (a later span is the funclet-dedup tail,
        # usually inside foreign code -- see Il2Cpp._eh4_regions).
        close_bid = None
        if end is not None and (end1 is None or seh['kind'] != 'finally'):
            close_bid = self._block_of_va(end - 1, blocks)
        elif end1 is not None:
            close_bid = self._block_of_va(end1 - 1, blocks)
        if close_bid is None:
            for bi in sorted(comp):
                for s in blocks[bi].succs:
                    if s in reach:
                        close_bid = s
                        break
                if close_bid is not None:
                    break
        seh['ret_close'] = close_bid is None or close_bid == open_bid
        if seh['ret_close']:
            close_bid = None
        if close_bid is None and not seh['ret_close']:
            return None
        # finally duplicate on the normal path: a reachable block whose
        # statements match the pad's leading statements
        if seh['kind'] == 'finally':
            pad_stmts = []
            for bi in sorted(comp):
                pad_stmts.extend(blocks[bi].stmts)
                if blocks[bi].stmts:
                    break
            norm = lambda s: re.sub(r'(?<![\w.])(?:obj|v|t|num|flag|real)\d+(?![\w])', 'X', s)
            pad_norm = [norm(s) for s in pad_stmts]
            if pad_norm:
                for b in blocks:
                    if b.bid not in reach or b.bid == open_bid or b.bid in comp:
                        continue
                    bn = [norm(s) for s in b.stmts]
                    if not bn or bn != pad_norm[:len(bn)]:
                        continue
                    nxt = b.succs[0] if b.succs else -1
                    b.stmts = []
                    b.cond = None
                    b.ret = None
                    b.term = ('jmp', nxt) if nxt >= 0 else ('stop',)
                    seh['dup'] = seh.get('dup', 0) + 1
                    break
        seh['open'] = open_bid
        seh['close'] = close_bid
        return seh

    _NORM_RX = re.compile(r'(?<![\w.])(?:obj|v|t|num|flag|real)\d+(?![\w])')

    def _seh_dedupe_kill(self, raw, seh):
        """The compiled finally/catch duplicates its body on the normal
        path inside the try; the kill-index set for one region's clause,
        against the given `raw` (all regions are measured against the SAME
        pre-removal `raw` by the caller, so one region's kill set can't be
        invalidated by another's). Statements are compared with temp names
        normalised away (the pad lifts with fresh unknowns, so its argument
        spellings differ)."""
        body_i = seh.get('body_idx')
        end_i = seh.get('clause_end')
        try_i = seh.get('try_idx')
        if body_i is None or end_i is None or try_i is None:
            return set()
        body = raw[body_i:end_i - 1]
        def norm(s):
            t = self._NORM_RX.sub('X', s.strip())
            # the pad lifts with fresh unknown registers, so calls there
            # carry extra untracked args the normal path trimmed
            return re.sub(r'X(?:,\s*X)+', 'X', t)
        wanted = [norm(s) for s in body
                  if s.strip() and not s.startswith(LBL) and len(s.strip()) > 3]
        kill = set()
        for w in wanted:
            if w in ('{', '}', 'else', 'try'):
                continue
            for k in range(try_i + 1, body_i - 3):
                if k in kill:
                    continue
                if norm(raw[k]) == w and raw[k].strip().endswith(';'):
                    kill.add(k)
                    break
        return kill

    def _seh_dedupe(self, raw):
        """Run the duplicate-normal-path detection for every region that
        emitted a clause -- against the original `raw`, since removal
        indices from different regions would otherwise invalidate each
        other -- then remove the union in one pass."""
        kill = set()
        for seh in self._seh_regions:
            if seh.get('clause_end'):
                kill |= self._seh_dedupe_kill(raw, seh)
        if not kill:
            return raw
        return [s for k, s in enumerate(raw) if k not in kill]

    def _seh_emit_clause(self, blocks, out, depth, seh):
        sub: List[str] = []
        # the pads are entered by the exception dispatcher, never by flow:
        # the clause walk must stop at the first entry-reachable block, or
        # a funclet whose tail re-joins the main flow drags the WHOLE rest
        # of the method into the clause (ScriptableRenderer.Execute: the
        # ret-close finally's body was the entire remaining ~300 lines).
        stop = {seh['close']} | set(self.reach)
        self._seh_in_clause = True
        try:
            self._seq(blocks, seh['pads'][0], stop, set(), sub, depth + 1)
        finally:
            self._seh_in_clause = False
        cleaned = []
        for s in sub:
            # labels stay: a goto *inside* the clause to a block the clause
            # walk consumed is legal C#, and stripping the marker here left
            # that goto dangling with no label anywhere in the method (1,981
            # sites tree-wide). `_resolve_labels` drops the unused ones.
            cleaned.append(s)
        while cleaned and cleaned[-1].startswith('return'):
            cleaned.pop()
        if self._bstack:
            self._bstack.pop()
        out.append('}')
        ct = seh.get('catch_type')
        if seh['kind'] == 'finally':
            out.append('finally')
        elif ct:
            out.append('catch (%s)' % ct)
        else:
            out.append('catch')
        out.append('{')
        self._brace_push('catch')
        seh['body_idx'] = len(out)
        out.extend(cleaned)
        out.append('}')
        self._brace_pop(blocks, out, depth)
        seh['clause_end'] = len(out)

    # ------------------------------------------------------------------
    # region-stack: self._seh_regions is outer-to-inner ordered (a wider
    # [tryLow,tryHigh] state range is never nested inside a narrower one --
    # see Il2Cpp._eh4_regions). Opens walk outer-to-inner so an outer `try {`
    # always precedes an inner one recorded at the same block; closes walk
    # the reverse (inner-to-outer) so an inner `}` always precedes the
    # outer's, matching how nested clauses must brace.
    def _seh_open_here(self, cur, out):
        for seh in self._seh_regions:
            if cur == seh['open'] and not seh['opened']:
                seh['opened'] = True
                seh['try_idx'] = len(out)
                seh['try_out'] = out
                out.append('try')
                out.append('{')
                self._bstack.append('try')
                seh['brace_pos'] = len(self._bstack)

    def _seh_close_one(self, seh, blocks, out, depth):
        """Common close path for `_seh_close_here`/`_seh_close_all_open`/
        `_seh_close_sublist`: emit the `} catch/finally` clause when the
        try's own brace is (or is about to be) the innermost open brace --
        otherwise, when the close fired inside a fork/loop/case frame (an
        `if`/`else` body, a `while` body, a switch-case body), defer it to
        `_flush_pclose` at that frame's closing `}`. Without the deferral,
        the clause landed in the MIDDLE of another statement's braces and
        rendered `try { } else { }` / `try { } if (...)` -- invalid C# at
        1,026 sites tree-wide (try-with-bad-follower scan), the deeper part
        invisible to the per-file brace audit because every brace still
        pairs up."""
        seh['closed'] = True
        if seh.get('clause_end'):
            return
        if (self._bstack and len(self._bstack) > seh.get('brace_pos', 0)) \
                or seh.get('try_out') is not out:
            # deferred: the try's own brace is not (or not in THIS buffer)
            # the innermost open brace -- emit when the owning walk pops
            # down to `brace_pos` (_flush_pclose). A cross-buffer close
            # (try opened in the main method list, closed while a switch-
            # case sub-walk runs in a scratch list) must NOT emit here:
            # the clause would close the try at the wrong nesting depth
            # (d__100.MoveNext: finally mid-switch, `} finally {` inside
            # the case body).
            self._pclose.append(seh)
        else:
            self._seh_emit_clause(blocks, out, depth, seh)

    def _flush_pclose(self, blocks, out, depth):
        """Emit deferred closes whose try-brace has become the innermost
        open brace again (every enclosing fork/loop brace was popped).
        The queue is NOT popped FIFO: an outer region's close can fire
        before an inner one (FocusController.SwitchFocus: the inner
        region's close fires mid-else-arm, while the outer ret-close
        deferred earlier), so the matching entry is found by brace depth
        -- emitting front-to-back only works when deferrals arrive in
        postorder, which ehdata close blocks do not guarantee."""
        while True:
            hit = -1
            for i, seh in enumerate(self._pclose):
                if seh.get('brace_pos') == len(self._bstack):
                    hit = i
                    break
            if hit < 0:
                return
            seh = self._pclose.pop(hit)
            self._seh_emit_clause(blocks, out, depth, seh)

    def _seh_close_top_try(self, blocks, out, depth):
        """An arm walk returned with an unclosed `try` frame on top of the
        brace stack (its close block lives on a loop-exit arm the walk
        rendered as a bare `break;`, e.g. WorkStealingQueue.LocalPop):
        close it here, before the fork emits its own closing `}` --
        otherwise the fork's `_brace_pop` eats the `try` frame and the
        finally clause lands after the enclosing `}` (rendered
        `} finally` unbracketed). A Fix-A-hoisted try is skipped: its
        close lives past the join and the join leg continues inside it."""
        if not self._bstack or self._bstack[-1] != 'try':
            return
        for seh in reversed(self._seh_regions):
            if seh.get('opened') and not seh.get('closed') \
                    and seh.get('brace_pos') == len(self._bstack) \
                    and seh.get('try_out') is out \
                    and not seh.get('hoisted'):
                self._seh_close_one(seh, blocks, out, depth)
                return

    def _brace_push(self, tag):
        self._bstack.append(tag)

    def _brace_pop(self, blocks, out, depth):
        """Pop one open frame and flush any region close deferred to it.
        A LIVE `try` frame on top (its region never reached its close
        block -- SocketNativeSource.ReceiveLoop: the try sits inside a
        `while (true)` whose body walk abandons at the header and the
        close only fires on the post-loop continuation) is closed HERE,
        so its clause lands at its own `}`, not after the loop's --
        except a Fix-A-hoisted try, whose close lives past the join and
        must stay open for the join leg."""
        if self._bstack:
            if self._bstack[-1] == 'try':
                self._seh_close_top_try(blocks, out, depth)
            self._bstack.pop()
        self._flush_pclose(blocks, out, depth)

    def _brace_pop_silent(self):
        """Pop a frame whose `}` closed but where a deferred close must NOT
        land (the if-fork of an if/else: the `else` is still to come)."""
        if self._bstack:
            self._bstack.pop()

    def _seh_close_here(self, cur, blocks, out, depth):
        for seh in reversed(self._seh_regions):
            if seh['opened'] and not seh['closed'] and cur == seh['close']:
                self._seh_close_one(seh, blocks, out, depth)

    def _arm_reach(self, blocks, start, stop):
        """Blocks walkable from `start` without crossing `stop` -- the
        conservative superset of what an arm sub-walk can touch, used to
        decide whether a try's open block lies inside a fork arm (Fix A:
        region opens in an arm but closes beyond the join must have its
        `try` hoisted above the fork, or the arm's brace pop eats it)."""
        if start < 0:
            return set()
        seen = {start}
        stack = [start]
        while stack:
            x = stack.pop()
            if x in stop:
                continue
            for s in blocks[x].succs:
                if s >= 0 and s not in seen:
                    seen.add(s)
                    if len(seen) <= 800:
                        stack.append(s)
        return seen

    def _seh_close_overdue(self, blocks, out, depth, from_bid, stop=None):
        """Close open regions a walk is abandoning without reaching their
        close block: the `cur in stop` early return fires for every fork-
        join J, but a region whose close block lies BEYOND J (or in dead
        code never walked -- e.g. an ehdata close landing on the `abort`
        tail after a ret) is left open, and the fork arm's `_brace_pop`
        then pops the stray `try` frame instead of its own `if` (the
        TryAdjustYear class: clause emitted after the method's final `}`,
        rendered `} catch` unbracketed). Close only when the close block
        is unreachable from `from_bid` here -- a region whose close is
        reachable past the join legitimately continues once the parent
        walk resumes at `cur`. `stop` (when given) is the abandoning
        walk's stop set: a close only reachable by crossing a stop block
        (a loop back-edge through the header) is NOT legitimately
        reachable -- the walk can never get there (the WorkSteakingQueue.
        LocalPop class: try opened right after a loop-header fork, close
        only reachable via the header it abandoned)."""
        if not self._seh_regions:
            return
        seen = {from_bid} if from_bid >= 0 else set()
        if from_bid >= 0:
            stack = [from_bid]
            while stack:
                x = stack.pop()
                if stop is not None and x in stop:
                    continue
                for s in blocks[x].succs:
                    if s >= 0 and s not in seen:
                        seen.add(s)
                        if len(seen) <= 800:
                            stack.append(s)
        for seh in reversed(self._seh_regions):
            if seh.get('opened') and not seh.get('closed') \
                    and seh.get('try_out') is out:
                # only close a region that is currently the DEEPEST brace
                # frame: one sitting under an open fork frame is closed by
                # that frame's pop+flush once the walk returns -- closing
                # it here defers it into _pclose and the flush fires at
                # the WRONG arm boundary (a Fix-A-hoisted try whose close
                # lives past the join must stay open for the join leg).
                if seh.get('brace_pos') != len(self._bstack):
                    continue
                cb = seh.get('close')
                if cb is None or cb not in seen:
                    self._seh_close_one(seh, blocks, out, depth)

    def _seh_close_all_open(self, blocks, out, depth):
        """A `return`/stop/abort point inside one or more open tries closes
        all of them (innermost first) -- the walk is leaving the region
        without reaching its recorded close block. Inside a CLAUSE walk
        (this method re-walking the pads of another region) only the
        deepest open frame is closed: an outer region whose try-brace
        lies under the clause's frames must survive to the end of the
        main walk, or its clause is deferred and flushed between the
        clause's `}`s (UIElementsUtility.DoDispatch: the outer ret-close
        finally landed inside the inner finally's body)."""
        for seh in reversed(self._seh_regions):
            if seh['opened'] and not seh['closed']:
                if getattr(self, '_seh_in_clause', False) \
                        and seh.get('brace_pos') < len(self._bstack):
                    continue
                self._seh_close_one(seh, blocks, out, depth)

    def _seh_close_sublist(self, sub, blocks, depth):
        """A goto-target sublist or switch-case body that opened a try must
        close it before merging into the parent output, or the recorded
        index points into a list nobody will repair."""
        for seh in reversed(self._seh_regions):
            if seh.get('opened') and not seh.get('closed') and seh.get('try_out') is sub:
                self._seh_close_one(seh, blocks, sub, depth)

    def _block_of_va(self, va, blocks):
        """Block id whose instruction range contains `va` (leader-only
        `bmap`/`ip2bid` won't have it directly -- ehdata try-state
        boundaries land wherever the compiler put them, not at our
        branch-derived block leaders)."""
        starts = self._seh_starts
        import bisect as _bi
        i = _bi.bisect_right(starts, (va, float('inf'))) - 1
        if i < 0:
            return None
        _, bid = starts[i]
        b = blocks[bid]
        if b.insns and b.insns[0].ip <= va < b.insns[-1].next_ip:
            return bid
        return None

    def _forward_empty(self, blocks):
        """Route edges around blocks that carry nothing but an unconditional
        jump; they only exist to host a label nobody needs to see."""
        def skip_to(bid, seen):
            while True:
                b = blocks[bid]
                if b.bid in seen or b.is_entry or b.stmts or b.cond is not None \
                        or b.ret is not None or not b.term or b.term[0] not in ('jmp', 'fall'):
                    return bid
                nxt = b.term[1]
                if nxt < 0 or nxt == bid:
                    return bid
                if (bid, nxt) in self.phi_copies:
                    return bid
                seen.add(bid)
                bid = nxt

        changed = False
        for b in blocks:
            if not b.succs:
                continue
            new = []
            for s in b.succs:
                t = skip_to(s, {b.bid}) if s >= 0 else s
                if t != s and (b.bid, s) in self.phi_copies:
                    t = s      # keep the edge that carries the phi copies
                if t != s:
                    changed = True
                new.append(t)
            if new != b.succs:
                b.succs = []
                for t in new:
                    if t not in b.succs:
                        b.succs.append(t)
                if b.term:
                    k = b.term[0]
                    if k in ('jmp', 'fall'):
                        b.term = (k, new[0])
                    elif k == 'jcc':
                        b.term = ('jcc', new[0] if len(new) > 0 else -1,
                                  new[1] if len(new) > 1 else -1)
        if not changed:
            return
        # jcc with both edges collapsed to the same block is not a branch anymore
        for b in blocks:
            if b.term and b.term[0] == 'jcc' and b.term[1] == b.term[2] >= 0:
                b.term = ('jmp', b.term[1])
                b.cond = None
        for b in blocks:
            b.preds = []
        for b in blocks:
            for s in b.succs:
                if 0 <= s < len(blocks):
                    blocks[s].preds.append(b.bid)

    _GOTO_RX = re.compile(r'^goto (L_[0-9a-f]+);$')
