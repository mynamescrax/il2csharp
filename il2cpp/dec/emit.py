from il2cpp.prelude import *  # noqa: F401,F403
from il2cpp.cfg import LBL, _abandon_at_region_close, _ends_flow
from il2cpp.text import strip_outer

class _EmitMixin:
    def _edge(self, src: int, dst: int, out: List[str]):
        """Emit the phi copies that belong on the CFG edge src -> dst."""
        cps = self.phi_copies.get((src, dst))
        if cps:
            out.extend(cps)

    def _goto(self, blocks, tgt: int) -> str:
        b = blocks[tgt]
        return 'goto L_%x;' % b.insns[0].ip if b.insns else 'break;'

    def _leave_loop(self, blocks, tgt: int) -> str:
        """Leaving a loop from inside a switch section can't use `break`."""
        if self._sw_depth > 0 and tgt >= 0 and blocks[tgt].insns:
            return self._goto(blocks, tgt)
        return 'break;'

    def _branch(self, blocks, src, tgt, stop, in_loop, out, depth):
        if tgt < 0:
            return
        self._edge(src, tgt, out)
        self._seq(blocks, tgt, stop, in_loop, out, depth)

    def _seq(self, blocks, start, stop: Set[int], in_loop: Set[int],
             out: List[str], depth: int, _enter_stop: bool = False,
             _active_loop_header: Optional[int] = None,
             _suppress_start_label: bool = False):
        if depth > 60:
            return
        cur = start
        guard = 0
        entering = True
        while 0 <= cur < len(blocks):
            initial = entering
            if cur in stop and not (_enter_stop and initial):
                # the join is reached; a try whose exact close block IS the
                # join closes here, before the walk abandons it (the ret/
                # stop handlers below never see this block)
                self._seh_close_here(cur, blocks, out, depth)
                self._seh_close_overdue(blocks, out, depth, cur, stop)
                return
            entering = False
            guard += 1
            if guard > 400:
                return
            b = blocks[cur]
            if in_loop and cur not in in_loop:
                # abandoning the loop: a region opened inside the loop whose
                # close is only reachable through the loop (past the stop set
                # the walk just gave up on) must close HERE, or the fork-
                # arm pops ahead eat its stray `try` frame (LocalPop: rendered
                # `else { try {...} break; }` with the finally after the loop)
                self._seh_close_here(cur, blocks, out, depth)
                self._seh_close_overdue(blocks, out, depth, cur, stop)
                out.append(self._leave_loop(blocks, cur))
                return
            if in_loop and cur in in_loop and _abandon_at_region_close(blocks, cur, in_loop, stop, self._seh_regions):
                # the walk reached a region's close block that lies INSIDE
                # this loop's body set but whose try opened BEFORE the loop
                # (ScriptableRenderer.InternalStartRendering: try wraps the
                # loop; the close/`finally` block got classified in the loop
                # body). Emitting the try's `}`/clause here would strand it
                # before the loop's own `}`/while -- abandon to the caller
                # and let the parent walk close the region after the loop.
                # BUT when the latch block carries its own statements they
                # belong to this iteration (23762: the navigation store on
                # the non-null path): emit them with the backedge copies
                # and fall off the end -- the structured loop itself is the
                # backedge, so no break/exit may render here. Only an empty
                # latch keeps the old break-out. (`_seh_close_overdue`
                # cannot close this region: its close == cur is already in
                # the reachable set it computes.)
                ab = blocks[cur]
                if ab.stmts:
                    if ab.insns:
                        out.append('%sL_%x:' % (LBL, ab.insns[0].ip))
                    out.extend(ab.stmts)
                    ab.consumed = True
                    hdr = next(iter(stop), -1)
                    if hdr >= 0:
                        self._edge(cur, hdr, out)
                    return
                self._seh_close_overdue(blocks, out, depth, cur, stop)
                out.append(self._leave_loop(blocks, cur))
                return
            if b.consumed:
                # A previously rendered sibling can still expose a short
                # linear tail before this branch's own stop/join. Replaying
                # that proven path is exact CFG tail duplication and avoids
                # an illegal goto into the sibling's lexical scope.
                if self._replay_consumed_linear_to_stop(
                        blocks, cur, stop, in_loop, out):
                    return
                # Otherwise a goto into already-rendered territory leaves
                # this list's walk the same way `ret`/`stop` do -- a region
                # opened in `out` that never reached its close block here
                # would otherwise dangle past every cleanup pass that only
                # knows to look at `raw`.
                self._seh_close_sublist(out, blocks, depth)
                out.append(self._goto(blocks, cur))
                return
            # nested loop header?
            if (cur != _active_loop_header and cur in self.loop_of_hdr
                    and self.loop_of_hdr[cur][0] - {cur}):
                # a try whose exact ehdata open/close block IS the loop
                # header must still open/close here: the loop branch below
                # hands the header to `_emit_loop` and never reaches the
                # open/close calls after it
                self._seh_open_here(cur, out)
                self._seh_close_here(cur, blocks, out, depth)
                exit_bid = self._emit_loop(blocks, cur, out, in_loop, depth)
                if exit_bid is None or exit_bid in stop:
                    return
                cur = exit_bid
                continue
            b.consumed = True
            self._seh_open_here(cur, out)
            self._seh_close_here(cur, blocks, out, depth)
            if b.insns and not (_suppress_start_label and initial):
                out.append('%sL_%x:' % (LBL, b.insns[0].ip))
            out.extend(b.stmts)
            term = b.term or ('stop',)
            kind = term[0]
            if kind == 'ret':
                self._flush_pclose(blocks, out, depth)
                self._seh_close_all_open(blocks, out, depth)
                out.append('return %s;' % b.ret if b.ret else 'return;')
                return
            if kind == 'switch':
                self._emit_switch(blocks, b, stop, in_loop, out, depth)
                J = self._sw_join
                if J is None or J < 0:
                    self._flush_pclose(blocks, out, depth)
                    self._seh_close_all_open(blocks, out, depth)
                    return
                if J in stop or blocks[J].consumed:
                    self._seh_close_here(J, blocks, out, depth)
                    self._seh_close_overdue(blocks, out, depth, J)
                    return
                cur = J
                continue
            if kind in ('stop', 'abort'):
                self._flush_pclose(blocks, out, depth)
                self._seh_close_all_open(blocks, out, depth)
                return
            if kind in ('jmp', 'fall'):
                t = term[1]
                if t < 0:
                    return
                self._edge(cur, t, out)
                cur = t
                continue
            if kind == 'jcc':
                _, t, f = term
                cond = b.cond or 'true'
                # loop-exit branch: exactly one edge leaves the current loop
                if in_loop and t >= 0 and f >= 0:
                    t_in = t in in_loop
                    f_in = f in in_loop
                    if t_in != f_in:
                        ex, nxt = (f, t) if t_in else (t, f)
                        out.append('if (%s)' % (cond if ex == t else '!(%s)' % cond))
                        out.append('{')
                        self._edge(cur, ex, out)
                        out.append(self._leave_loop(blocks, ex))
                        out.append('}')
                        self._edge(cur, nxt, out)
                        cur = nxt
                        continue
                J = self._ipdom(cur, self.pdom)
                if J >= 0 and (J in stop or blocks[J].consumed or J == cur):
                    J = -1
                sub_stop = stop | ({J} if J >= 0 else set())
                if J >= 0:
                    # a try region whose open block lies inside one fork arm
                    # but whose close is beyond the join must open ABOVE the
                    # fork: opening it inside the arm (its `try {` then
                    # precedes the arm's closing `}`) makes the arm's pop
                    # eat the `try` frame and render `try {} else {}` at
                    # 1,026 sites -- the arm can never close it, and
                    # hoisting keeps the fork's own frames on top of it.
                    rt = self._arm_reach(blocks, t, sub_stop) if t >= 0 else set()
                    rf = self._arm_reach(blocks, f, sub_stop) if f >= 0 else set()
                    # fix 75: the join-edge phi copies belong at the END
                    # of the test block, BEFORE the branch. The old
                    # placement emitted them after the fork, where they
                    # executed on BOTH paths whenever the branched arm
                    # also fell to the join -- clobbering the arm-edge
                    # copies; _copy_prop then substituted the surviving
                    # pre-branch value into the post-join use and its
                    # backward sweep dropped the arm copy, so the
                    # render read the pre-branch token
                    # (CameraManager.SetActiveCamera 0x180541950's
                    # cached-delegate use; 48,520 census sites / 2,198
                    # methods in Assembly-CSharp alone).
                    pre_edge = None
                    if f == J and J in rt:
                        pre_edge = f
                    elif t == J and J in rf:
                        pre_edge = t
                    if pre_edge is not None:
                        self._edge(cur, pre_edge, out)
                    for seh in self._seh_regions:
                        if seh.get('opened') or seh.get('closed'):
                            continue
                        op = seh.get('open')
                        if op is None:
                            continue
                        cl = seh.get('close')
                        if op in rt or op in rf:
                            if cl is not None and (cl in rt or cl in rf):
                                continue  # opens AND closes inside an arm
                            if cl is None:
                                # ret-close region (funclet owns the method
                                # teardown): there IS no close beyond the
                                # join, so there is nothing to hoist FOR --
                                # keep the try inside the arm where it
                                # opened, and _seh_close_top_try fires its
                                # clause when the arm's brace pops
                                # (SocketNativeSource.ReceiveLoop: hoisting
                                # it made _seh_close_top_try skip it, the
                                # frame popped unclosed at the fork, and
                                # the catch landed after the loop's `}`
                                # via the teardown `ret`).
                                continue
                            seh['opened'] = True
                            seh['hoisted'] = True
                            seh['try_idx'] = len(out)
                            seh['try_out'] = out
                            out.append('try')
                            out.append('{')
                            self._bstack.append('try')
                            seh['brace_pos'] = len(self._bstack)
                if J >= 0 and f == J:
                    out.append('if (%s)' % cond)
                    out.append('{')
                    self._brace_push('if')
                    self._branch(blocks, cur, t, sub_stop, in_loop, out, depth + 1)
                    self._seh_close_top_try(blocks, out, depth)
                    self._flush_pclose(blocks, out, depth)
                    out.append('}')
                    self._brace_pop(blocks, out, depth)
                    if pre_edge is None:
                        self._edge(cur, f, out)
                elif J >= 0 and t == J:
                    out.append('if (!(%s))' % cond)
                    out.append('{')
                    self._brace_push('if')
                    self._branch(blocks, cur, f, sub_stop, in_loop, out, depth + 1)
                    self._seh_close_top_try(blocks, out, depth)
                    self._flush_pclose(blocks, out, depth)
                    out.append('}')
                    self._brace_pop(blocks, out, depth)
                    if pre_edge is None:
                        self._edge(cur, t, out)
                else:
                    out.append('if (%s)' % cond)
                    out.append('{')
                    self._brace_push('if')
                    self._branch(blocks, cur, t, sub_stop, in_loop, out, depth + 1)
                    self._seh_close_top_try(blocks, out, depth)
                    out.append('}')
                    # no flush here: the `else` fork is still to come, so a
                    # deferred close must not land between the if's `}` and
                    # the `else` (it would render `try {} else {}`)
                    self._brace_pop_silent()
                    out.append('else')
                    out.append('{')
                    self._brace_push('else')
                    self._branch(blocks, cur, f, sub_stop, in_loop, out, depth + 1)
                    self._seh_close_top_try(blocks, out, depth)
                    self._flush_pclose(blocks, out, depth)
                    out.append('}')
                    self._brace_pop(blocks, out, depth)
                if J >= 0 and J not in stop and not blocks[J].consumed:
                    cur = J
                    continue
                return
            return

    # fix 62: the old spelling was r'^\(?(.+?) - (\d+)\)?$', whose
    # two optional parens are INDEPENDENT -- `(num1 & 0xFF) - 97`
    # matched with group(1) = `num1 & 0xFF)`, emitting the
    # unbalanced `switch (num1 & 0xFF))`. Peeling a wrapping layer
    # is strip_outer's job (it only removes BALANCED pairs); this
    # matches the subtraction and nothing else.
    _SUBK_RX = re.compile(r'^(.+?) - (\d+)$')

    def _emit_switch(self, blocks, b, stop, in_loop, out, depth):
        """Inline the case bodies of a jump-table dispatch. Targets shared by
        several case values collapse into one section with stacked labels."""
        self._sw_join = -1
        groups: List[list] = []
        order: Dict[int, int] = {}
        for cv, tip in enumerate(b.switch_targets or []):
            tb = self.ip2bid.get(tip, -1)
            if tb < 0:
                continue
            if tb not in order:
                order[tb] = len(groups)
                groups.append([tb, []])
            groups[order[tb]][1].append(cv)
        if not groups:
            return
        idx = b.switch_idx or '?'
        base = 0
        m = self._SUBK_RX.match(strip_outer(idx))
        if m:   # switch (x - k) { case 0: } is switch (x) { case k: }
            idx, base = m.group(1), int(m.group(2))
        J = self._ipdom(b.bid, self.pdom)
        if J >= 0 and (J in stop or blocks[J].consumed or J == b.bid):
            J = -1
        roots = {g[0] for g in groups}
        out.append('switch (%s)' % idx)
        out.append('{')
        self._brace_push('switch')
        self._sw_depth += 1
        for tb, cvs in groups:
            for cv in cvs:
                out.append('case %d:' % (cv + base))
            out.append('{')
            self._brace_push('case')
            sub: List[str] = []
            sub_stop = set(stop) | (roots - {tb}) | ({J} if J >= 0 else set())
            self._branch(blocks, b.bid, tb, sub_stop, in_loop, sub, depth + 1)
            # a try opened inside this case body must close before the case
            # merges into the switch output, or its recorded index points
            # into a list nobody will repair
            self._seh_close_sublist(sub, blocks, depth + 1)
            out.extend(sub)
            if not sub or not _ends_flow(sub[-1]):
                out.append('break;')
            out.append('}')
            self._brace_pop(blocks, out, depth)
        self._sw_depth -= 1
        out.append('}')
        self._brace_pop(blocks, out, depth)
        self._sw_join = J

    def _replay_consumed_linear_to_stop(
            self, blocks, start: int, stop: Set[int],
            in_loop: Set[int], out: List[str]) -> bool:
        """Duplicate a consumed straight-line CFG tail up to this arm's join.

        Structuring one sibling first can leave another sibling reaching the
        same already-consumed native blocks. A textual goto to that first arm
        is illegal C#. If every intervening block is consumed, linear, free of
        SEH boundaries, and ends exactly at this walk's stop set, replaying its
        statements and edge-phi copies is the same native path at the current
        site. Prove the complete path before emitting anything.
        """
        if not stop:
            return False
        path = []
        cur = start
        seen = set()
        for _ in range(128):
            if cur in stop:
                break
            if cur in seen or not (0 <= cur < len(blocks)):
                return False
            seen.add(cur)
            if in_loop and cur not in in_loop:
                return False
            b = blocks[cur]
            if not b.consumed or b.is_entry or cur in self._pad_bids:
                return False
            if any(cur in (seh.get('open'), seh.get('close'))
                   for seh in self._seh_regions):
                return False
            term = b.term or ('stop',)
            if term[0] not in ('jmp', 'fall') or len(b.succs) != 1:
                return False
            nxt = term[1]
            if nxt != b.succs[0] or nxt < 0:
                return False
            path.append((cur, nxt))
            cur = nxt
        else:
            return False
        if not path or cur not in stop:
            return False
        for bid, nxt in path:
            out.extend(blocks[bid].stmts)
            self._edge(bid, nxt, out)
        return True

    def _loop_shared_entry_gate(self, blocks, hdr: int,
                                body_ids: Set[int]):
        """Collapse ``header -> gate-or-shared`` into one short-circuit exit.

        This common native loop shape sends one header arm directly to the
        body and the other through a second, statement-free exit test before
        reaching that same body. Rendering the first arm consumes the shared
        body and leaves the second arm with a goto into its lexical scope.
        With one gate predecessor, no SEH boundary and no edge copies, the two
        tests are exactly ``if (header_to_gate && gate_to_exit) break``.
        """
        h = blocks[hdr]
        term = h.term or ('stop',)
        if term[0] != 'jcc' or not h.cond:
            return None
        for gate, shared in ((term[1], term[2]), (term[2], term[1])):
            if (gate not in body_ids or shared not in body_ids
                    or not (0 <= gate < len(blocks))):
                continue
            g = blocks[gate]
            gt = g.term or ('stop',)
            if (g.stmts or gt[0] != 'jcc' or not g.cond
                    or g.preds != [hdr]):
                continue
            if gate in self._pad_bids or any(
                    gate in (seh.get('open'), seh.get('close'))
                    for seh in self._seh_regions):
                continue
            if gt[1] == shared and gt[2] not in body_ids:
                exit_bid = gt[2]
            elif gt[2] == shared and gt[1] not in body_ids:
                exit_bid = gt[1]
            else:
                continue
            if not (0 <= exit_bid < len(blocks)):
                continue
            edges = ((hdr, gate), (hdr, shared),
                     (gate, shared), (gate, exit_bid))
            if any(self.phi_copies.get(edge) for edge in edges):
                continue
            to_gate = h.cond if term[1] == gate else '!(%s)' % h.cond
            to_exit = g.cond if gt[1] == exit_bid else '!(%s)' % g.cond
            to_gate = self._simplify_cond(to_gate)
            to_exit = self._simplify_cond(to_exit)
            return gate, shared, exit_bid, '(%s) && (%s)' % (to_gate, to_exit)
        return None

    def _emit_loop_replaying_header(self, blocks, hdr, out: List[str],
                                    body_ids: Set[int], exits: Set[int],
                                    depth: int) -> Optional[int]:
        """Emit a loop whose native header contains work or an internal fork.

        A natural-loop header executes on entry and after every back edge. It
        cannot be printed before ``while``: doing so freezes memory reads and
        drops a header branch when both successors remain in the loop. Replay
        that block through the ordinary sequencer inside an explicit loop. The
        first header visit is allowed through the stop set; a later back edge
        reaches the same stop and completes the iteration.
        """
        h = blocks[hdr]
        if h.insns:
            out.append('%sL_%x:' % (LBL, h.insns[0].ip))
        out.append('while (true)')
        out.append('{')
        self._brace_push('loop')
        saved_sw = self._sw_depth
        self._sw_depth = 0
        entry_gate = self._loop_shared_entry_gate(blocks, hdr, body_ids)
        if entry_gate is None:
            self._seq(blocks, hdr, {hdr}, body_ids, out, depth + 1,
                      _enter_stop=True, _active_loop_header=hdr,
                      _suppress_start_label=True)
        else:
            gate, shared, _exit_bid, exit_cond = entry_gate
            h.consumed = True
            blocks[gate].consumed = True
            out.extend(h.stmts)
            out.append('if (%s)' % exit_cond)
            out.append('{')
            self._brace_push('if')
            out.append('break;')
            out.append('}')
            self._brace_pop(blocks, out, depth + 1)
            self._seq(blocks, shared, {hdr}, body_ids, out, depth + 1)
        self._sw_depth = saved_sw
        self._seh_close_top_try(blocks, out, depth)
        out.append('}')
        self._brace_pop(blocks, out, depth)

        if not exits:
            return None
        if len(exits) == 1:
            e = next(iter(exits))
        else:
            e = min(exits, key=lambda x: self.rpo.index(x)
                    if x in self.rpo else 1 << 30)
        if blocks[e].consumed:
            out.append(self._goto(blocks, e))
            return None
        return e

    def _emit_loop(self, blocks, hdr, out: List[str], outer_loop: Set[int],
                   depth: int) -> Optional[int]:
        body_ids, latch = self.loop_of_hdr[hdr]
        h = blocks[hdr]
        exits = set()
        for bid in body_ids:
            for s in blocks[bid].succs:
                if s >= 0 and s not in body_ids:
                    exits.add(s)
        # back-edge source latch block jcc -> do-while style if header isn't the jcc
        h_term = h.term or ('stop',)
        cond_at_top = h_term[0] == 'jcc'
        top_true_in = cond_at_top and h_term[1] in body_ids
        top_false_in = cond_at_top and h_term[2] in body_ids
        latch_b = blocks[latch]
        cond_at_bottom = (not cond_at_top)
        if cond_at_bottom:
            if not (latch_b.term and latch_b.term[0] == 'jcc' and hdr in latch_b.succs):
                cand = None
                for bid in sorted(body_ids, reverse=True):
                    tb = blocks[bid]
                    if tb.term and tb.term[0] == 'jcc' and hdr in tb.succs:
                        cand = bid
                        break
                if cand is not None:
                    latch_b = blocks[cand]
                else:
                    cond_at_bottom = False
        # Header instructions execute on every iteration. The legacy compact
        # while/do spelling is sound only for an empty header with at most one
        # in-loop branch. Otherwise replay the header as an ordinary CFG block
        # inside ``while (true)`` so its statements, branch arms and edge-phi
        # copies retain native execution order.
        if h.stmts or (cond_at_top and top_true_in and top_false_in):
            return self._emit_loop_replaying_header(
                blocks, hdr, out, body_ids, exits, depth)
        h.consumed = True
        if h.insns:
            out.append('%sL_%x:' % (LBL, h.insns[0].ip))
        out.extend(h.stmts)
        hdr_exit = -1
        if cond_at_top:
            t_in = h_term[1] in body_ids
            f_in = h_term[2] in body_ids
            c = h.cond or 'true'
            if t_in and not f_in:
                out.append('while (%s)' % c)
                hdr_exit = h_term[2]
            elif f_in and not t_in:
                out.append('while (!(%s))' % c)
                hdr_exit = h_term[1]
            else:
                out.append('while (true)')
            out.append('{')
            self._brace_push('loop')
            start = h_term[1] if t_in else h_term[2]
            if start == hdr or start not in body_ids:
                start = h_term[2] if h_term[2] in body_ids and h_term[2] != hdr else None
        else:
            out.append('do')
            out.append('{')
            self._brace_push('loop')
            start = None
            for s in h.succs:
                if s in body_ids and s != hdr:
                    start = s
                    break
            if start is None:
                for bid in sorted(body_ids):
                    if bid != hdr:
                        start = bid
                        break
        # `break` inside the body refers to this loop again, not an enclosing switch
        saved_sw = self._sw_depth
        self._sw_depth = 0
        if start is not None:
            self._edge(hdr, start, out)
            self._seq(blocks, start, {hdr}, body_ids, out, depth + 1)
        else:
            # header is its own body (back-edge straight to itself): the
            # body's real work lives in the (hdr,hdr) phi copies, which
            # nothing else ever emits -- without them the loop renders
            # `while (c) { }` with the updates lost (BitVector32.ToString)
            self._edge(hdr, hdr, out)
        self._sw_depth = saved_sw
        # close a `try` frame left open on top by the body walk (its close
        # block lay past the abandoned header -- SocketNativeSource.
        # ReceiveLoop) BEFORE the loop's own `}`: emitting it at the
        # following `_brace_pop` would put the clause AFTER this `}`.
        self._seh_close_top_try(blocks, out, depth)
        out.append('}')
        if cond_at_bottom:
            c = latch_b.cond or 'true'
            back_taken = latch_b.term[1] == hdr  # taken edge returns to header
            out.append('while (%s);' % (c if back_taken else '!(%s)' % c))
        elif not cond_at_top:
            out.append('while (true);')
        # the loop's tail must land BEFORE the brace-pop flush: a try that
        # opened BEFORE the loop (TimelineAsset.clipCaps) defers its close
        # to the _brace_pop here, and `_flush_pclose` emitting `} finally`
        # between the loop's `}` and its `while (cond);` orphans the tail
        # past the clause (rendered `try { do {...} } finally {...}` followed
        # by a bare `while (cond);`). Pop after the tail so the clause lands
        # after the completed do-while.
        self._brace_pop(blocks, out, depth)
        # continue after the loop
        e = None
        if len(exits) == 1:
            e = next(iter(exits))
        elif exits:
            # pick the RPO-first exit; others will surface as leftovers/labels
            e = min(exits, key=lambda x: self.rpo.index(x) if x in self.rpo else 1 << 30)
        if e is None:
            return None
        if hdr_exit == e:
            self._edge(hdr, e, out)
        if blocks[e].consumed:
            out.append(self._goto(blocks, e))
            return None
        return e

