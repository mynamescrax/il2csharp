from il2cpp.prelude import *  # noqa: F401,F403
from il2cpp.cfg import LBL
from il2cpp.terminator import RET, first_terminator

class _StructureMixin:
    def _structure(self, blocks, bmap, m) -> List[str]:
        # reachable blocks only (dead chunks after ret/jmp poison dominators);
        # switch targets are already wired by _prewire_switches.
        self.ip2bid = {b.insns[0].ip: b.bid for b in blocks if b.insns}
        self._forward_empty(blocks)
        reach = set()
        stack = [0]
        while stack:
            x = stack.pop()
            if x in reach:
                continue
            reach.add(x)
            for sx in blocks[x].succs:
                if sx >= 0 and sx not in reach:
                    stack.append(sx)
        self.reach = reach
        rblocks = [blocks[i] for i in sorted(reach)]
        rrpo = [b for b in self.rpo if b in reach]
        dom = self._dominators(blocks, rrpo, reach)
        pdom = self._postdominators(blocks, rrpo, reach)
        self.pdom = {k: v for k, v in pdom.items()}
        self.loop_of_hdr = self._loops(blocks, dom, reach)
        self._sw_depth = 0
        self._seh_regions = []
        self._boxed_bool_tmps = set()
        self._bstack = []
        self._pclose = []
        if getattr(self, 'eh', None) and self.eh.get('pads'):
            self._seh_prepare(blocks, bmap, dom, reach)
        raw: List[str] = []
        self._seq(blocks, 0, set(), set(), raw, 0)
        # any goto target that never got inlined gets its body appended
        for _round in range(64):
            have = set()
            want = set()
            for st in raw:
                if st.startswith(LBL) and st.endswith(':'):
                    have.add(st[len(LBL):-1])
                elif 'goto L_' in st:
                    want.update(re.findall(r'goto (L_[0-9a-f]+);', st))
            todo = []
            for lab in sorted(want - have):
                bid = self.ip2bid.get(int(lab[2:], 16), -1)
                if bid >= 0 and not blocks[bid].consumed:
                    todo.append(bid)
            if not todo:
                break
            for bid in todo:
                if blocks[bid].consumed:
                    continue
                sub: List[str] = []
                self._seq(blocks, bid, set(), set(), sub, 0)
                self._seh_close_sublist(sub, blocks, 0)
                if sub:
                    raw.append('')
                    raw.extend(sub)
        if self._seh_regions:
            # the walk may have abandoned one or more regions without
            # reaching their close point (early returns inside loops/
            # switches); drop each orphaned `try {` rather than ship
            # unbalanced braces. Highest try_idx first, so an earlier
            # region's recorded index isn't shifted by a later removal.
            orphans = sorted((s for s in self._seh_regions
                               if s.get('opened') and not s.get('closed')
                               and s.get('try_idx') is not None and s.get('try_out') is raw),
                              key=lambda s: s['try_idx'], reverse=True)
            for seh in orphans:
                ti = seh['try_idx']
                if ti < len(raw) and raw[ti] == 'try' and raw[ti + 1] == '{':
                    raw = raw[:ti] + raw[ti + 2:]
                    seh['closed'] = True
                    seh.setdefault('orphaned', True)
            # deferred closes that never got a brace-pop flush: emit into
            # the list where their try-brace lives so the braces stay paired
            while self._pclose:
                seh = self._pclose.pop(0)
                lst = seh.get('try_out') or raw
                if not seh.get('clause_end'):
                    self._seh_emit_clause(blocks, lst, 0, seh)
            if any(s.get('clause_end') for s in self._seh_regions):
                raw = self._seh_dedupe(raw)
        if self.phi_alias:
            al = self.phi_alias
            raw = [self._TOKRX.sub(lambda mm: al.get(mm.group(1), mm.group(1)), s)
                   for s in raw]
        raw = self._resolve_labels(raw)
        raw = self._tidy_gotos(raw)
        raw = self._drop_redundant_gotos(raw)
        raw = self._resolve_labels(raw)
        raw = self._hoist_shared_tails(raw)
        raw = self._resolve_labels(raw)
        raw = self._drop_dead_copies(raw)
        raw = self._drop_dead_temps(raw)
        raw = [self._fold_consts(x) for x in raw]
        raw = self._for_sugar(raw)
        raw = self._foreach_sugar(raw)
        # fix 50: a for-head cond re-rendering a call a preceding
        # decl holds folds to the token (probe_b41_forhead.py proved
        # the native loop does not re-call); after _foreach_sugar so
        # the foreach matcher sees the input it always did
        raw = self._forhead_call_fold(raw)
        raw = self._switch_to_if(raw)
        raw = self._rename_locals(raw, m)
        raw = self._phi_decl_hoist(raw)
        raw = self._bool_sugar(raw, m)
        raw = self._flag_inline(raw)
        raw = self._compound_assign(raw)
        raw = self._ternary(raw)
        raw = self._null_conditional(raw)
        raw = self._null_ternary_sugar(raw)
        raw = self._redundant_else(raw)
        raw = self._lock_sugar(raw)
        raw = self._using_sugar(raw)
        raw = self._is_sugar(raw)
        raw = self._image_table_fold(raw)
        raw = self._sfblob_dedupe(raw)
        raw = self._class_init_strip(raw)
        raw = self._member_fold(raw)
        # fix 72c: again, after the fold -- the byte-cast store twin
        # and the named spelling _fold_static_addrs just minted only
        # coexist from here on (at the call above neither exists).
        raw = self._sfblob_dedupe(raw)
        # after _member_fold so the RHS reads the folded `.Instance`, not
        # the raw `.<Instance>k__BackingField` -- see _singleton_cse.
        raw = self._singleton_cse(raw)
        raw = self._value_cse(raw)
        raw = self._subexpr_cse(raw)
        raw = self._copy_prop(raw)
        # fix 49: bare self-copies are no-ops even loop-carried;
        # _copy_prop's substitution MINTS them (backedge phi copy
        # whose source resolves to the same local), so the drop
        # runs right after it (probe_b41_stages.py: 0->12 there,
        # 12->12 everywhere later)
        raw = self._selfcopy_drop(raw)
        # F2-C1 sits here: assignments still carry lifter spellings
        # (copy-prop already transparent) and dead decls drop after.
        raw = self._single_field_assign_fold(raw, m)
        raw = self._drop_dead_locals(raw)
        # fix 51b: later passes MINT shapes the early run (before
        # _drop_dead_temps) can never see -- dead-store drops empty the
        # arms around gotos, _redundant_else restructures siblings --
        # so the hoist runs once more on the final shapes
        # (classify_into2 SOUND=47 at b41_out1 is this residue)
        raw = self._hoist_shared_tails(raw)
        # fix 45: later passes unblock pairs the first run (after
        # _bool_sugar) refused -- _copy_prop substitutes flag-to-flag
        # copies and _drop_dead_locals deletes dead flag decls, so a
        # multi-mention pair can be single-use by the pipeline end
        # (193 adjacent pairs in AC at b39_out1). Same guards; loop
        # heads still never match (exact if-head shapes only).
        raw = self._flag_inline(raw)
        raw = self._elseif_flatten(raw)
        raw = self._phi_chain_decl_hoist(raw)
        # fix 72e: the flat chains the flattener just produced are
        # the switch-synthesis input; nothing after this point
        # restructures them
        raw = self._switch_synth(raw)
        raw = self._hash_string_switch(raw)
        # fix 55: LAST -- `_drop_dead_locals` (flow-insensitive) and
        # `_copy_prop`'s sweep (blocked by any later goto) both run
        # before the late `_hoist_shared_tails` mints more dead
        # last-defs, and neither can drop a store whose destination is
        # read only EARLIER in the method. This one can, when no
        # backward flow reaches that earlier read.
        raw = self._drop_dead_lastdef(raw)
        # fix 75b: the cached-delegate backer triple folds to
        # the ?? spelling (the cctor artifact, the shared-ctor
        # call and the phi copies go with it)
        raw = self._delegate_cache_fold(raw)
        raw = self._fence_void_calls(raw, m)
        raw = self._shared_equality_ops(raw, m)
        raw = self._shared_stub_casts(raw, m)
        raw = self._shared_conv_resolve(raw, m)
        raw = self._escape_keywords(raw)
        raw = self._fresh_array_brackets(raw)
        rendered = self._name_interface_dispatch(self._render(raw))
        # fix 99: `_render` drops empty pure-cond `if`s (e.g. an emptied
        # class-init guard `if (!(k.initialized != 0)) { }`), orphaning the
        # pure loads they alone read (`System.Type objN = typeof(X)`).
        # No DCE runs after render, so those dead lines survived into
        # output (12.7k dead typeof decls tree-wide) and were then renamed
        # `Type typeN` by `_semantic_local_names`. Re-run the proven
        # `_drop_dead_locals` on the rendered lines: same predicate (pure
        # RHS incl. pure-loads drop, impure calls stay), now seeing
        # post-render shapes. Render preserves statement order, so dropping
        # a pure unread line cannot reorder or erase any side effect.
        rendered = self._drop_dead_locals(rendered)
        # dead `unknown` stores overwritten next: the flow-insensitive
        # drop above keeps any temp read later, so an overwritten
        # first definition survives; this folds exactly those pairs
        # (adjacent overwrite, pure unknown RHS, no use between).
        rendered = self._drop_dead_unknown_store(rendered)
        return self._null_zero_rewrite(
            self._boxed_bool_null_fold(
                self._semantic_local_names(rendered, m)), m)

    # ------------------------------------------------------------------
    # ------------------------------------------------------------------
    # witness counts over this binary's 4,526 pad-bearing methods are
    # strongly bimodal -- 3269, 304, 181, 177, 39, 11, then 6, 5, 4, 3 --
    # and every straggler resolves to a shared generic thunk that chains
    # into a Dispose, so the cut sits inside the 6..11 gap
    # measured over all 4,526 pad-bearing methods, AFTER the named-plumbing
    # and noreturn filters below: 3347, 183, then 13, 13, 8. Cutting in that
    # 183 -> 13 gap (14x) keeps only the decisively witnessed helpers; the
    # first draft used 10, which sat inside a dense 13/13/12/8 cluster of
    # scan-continuation artifacts. -- fix 91
    _EH_HELPER_MIN_WITNESSES = 25
    # a role decided 13:12 is a coin flip, and the two roles render
    # differently (`throw;` vs `throw x;`), so require a decisive margin
    _EH_HELPER_MIN_DOMINANCE = 4

    @staticmethod
    def _phi_match_brace(lines, open_idx):
        """Index of the line closing the brace opened at open_idx, or None."""
        d = 0
        for k in range(open_idx, len(lines)):
            d += lines[k].count('{') - lines[k].count('}')
            if k > open_idx and d <= 0:
                return k
        return None

    @staticmethod
    def _phi_tail_decl(s):
        """(type, tok, rhs) for a `T x = rhs;` tail line, else None. The `=`
        must be lone (no ==/=>/compound); `var` never qualifies."""
        t = s.strip()
        if not t.endswith(';'):
            return None
        eq = -1
        for k, c in enumerate(t):
            if c != '=':
                continue
            prev = t[k - 1] if k > 0 else ''
            nxt = t[k + 1] if k + 1 < len(t) else ''
            if prev in ('=', '!', '<', '>', '+', '-', '*', '/', '%',
                        '&', '|', '^') or nxt in ('=', '>'):
                continue
            eq = k
            break
        if eq < 0:
            return None
        lhs, rhs = t[:eq].rstrip(), t[eq + 1:].strip()
        if rhs.endswith(';'):
            rhs = rhs[:-1].strip()
        if not rhs:
            return None
        m = re.match(r'^(.+?)\s+([A-Za-z_@]\w*)$', lhs)
        if not m:
            return None
        typ = m.group(1)
        if typ == 'var' \
                or not re.fullmatch(r'[A-Za-z_@][\w@.<>,\[\]*? ]+', typ):
            return None
        return typ, m.group(2), rhs

    def _phi_decl_match(self, lines, i, allow_non_tail=False):
        """Full hoist match at i, or None: `if (c) { ..; T x = a; } else
        { ..; T x = b; }` with x read after the join. Returns (indent,
        tok, typ, tc, ec, a1, a2, rhs1, rhs2) with absolute assignment indices.
        Every guard must hold: same token, same declared type word, tails
        last in their arms, no flow-break in either arm, no earlier read
        of x in the arms, no earlier visible decl/assignment of x, no
        address-taken anywhere, a later read of x, and arms longer than
        the lone tail (the pure single-assignment shape belongs to the
        ternary, which folds it with its declaration intact)."""
        n = len(lines)
        s = lines[i].strip()
        if not (s.startswith('if (') and s.endswith(')')):
            return None
        if i + 1 >= n or lines[i + 1].strip() != '{':
            return None
        tc = self._phi_match_brace(lines, i + 1)
        if tc is None or tc + 2 >= n:
            return None
        if lines[tc].strip() != '}' or lines[tc + 1].strip() != 'else' \
                or lines[tc + 2].strip() != '{':
            return None
        ec = self._phi_match_brace(lines, tc + 2)
        if ec is None:
            return None
        then = lines[i + 2:tc]
        els = lines[tc + 3:ec]
        nn1 = [k for k, b in enumerate(then) if b.strip()]
        nn2 = [k for k, b in enumerate(els) if b.strip()]
        if not nn1 or not nn2:
            return None
        if len(nn1) == 1 and len(nn2) == 1:
            return None
        # Prefer the historical twin-tail proof. A separate phi copy
        # can follow a receiver declaration; admit that only when there
        # is exactly one matching declaration pair in these arms.
        p1 = self._phi_tail_decl(then[nn1[-1]])
        p2 = self._phi_tail_decl(els[nn2[-1]])
        if p1 is not None and p2 is not None and p1[:2] == p2[:2]:
            k1, k2 = nn1[-1], nn2[-1]
        else:
            if not allow_non_tail:
                return None
            d1 = [(k, p) for k, line in enumerate(then)
                  if (p := self._phi_tail_decl(line)) is not None]
            d2 = [(k, p) for k, line in enumerate(els)
                  if (p := self._phi_tail_decl(line)) is not None]
            pairs = [(k1, q1, k2, q2) for k1, q1 in d1 for k2, q2 in d2
                     if q1[:2] == q2[:2]]
            if len(pairs) != 1:
                return None
            k1, p1, k2, p2 = pairs[0]
        typ, tok, rhs1 = p1
        rhs2 = p2[2]
        rx = re.compile(r'(?<![\w.])%s(?![\w])' % re.escape(tok))
        flow = re.compile(r'^(?:return|goto|throw|break|continue)\b')
        for body in (then, els):
            for b in body:
                if flow.match(b.strip()):
                    return None
        a1 = i + 2 + k1
        a2 = tc + 3 + k2
        for k in list(range(i + 2, a1)) + list(range(a1 + 1, tc)):
            if rx.search(lines[k]):
                return None
        for k in list(range(tc + 3, a2)) + list(range(a2 + 1, ec)):
            if rx.search(lines[k]):
                return None
        if rx.search(rhs1) or rx.search(rhs2):
            return None
        addr = re.compile(r'(?<!&)&(?!&)\s*%s\b|\b(?:ref|out|in)\s+%s\b'
                          % (re.escape(tok), re.escape(tok)))
        if any(addr.search(b) for b in lines):
            return None
        decl = re.compile(r'(?<![\w.])%s(?![\w])\s*(=(?![=>])|;)'
                          % re.escape(tok))
        tdecl = re.compile(
            r'[A-Za-z_@][\w@.<>,\[\]*?]*\s+%s(?![\w])'
            r'(?=\s*(?:=(?![=])|;|\bin\b|\)))' % re.escape(tok))
        for k in range(i):
            if decl.search(lines[k]) or tdecl.search(lines[k]):
                return None
        read = False
        for k in range(ec + 1, n):
            if tdecl.search(lines[k]):
                return None
            if rx.search(lines[k]):
                read = True
        if not read:
            return None
        indent = lines[i][:len(lines[i]) - len(lines[i].lstrip())]
        return indent, tok, typ, tc, ec, a1, a2, rhs1, rhs2

    def _phi_decl_hoist(self, lines, _round=0):
        """Hoist twin arm declarations above their `if`/`else`.

        `if (c) { ..; T x = a; } else { ..; T x = b; }` with x read after
        the join leaves x scoped to each arm (block-scoped declarations
        from `_rename_locals`): strip both tail decls to bare assignments
        and hoist one `T x;` above the `if`. See `_phi_decl_match` for the
        full guard list. A temp hoisted at two diamonds would redeclare,
        so a temp matching twice declines everywhere. Runs between
        `_rename_locals` (decl spellings exist) and `_bool_sugar` (which
        is flag-only and never sees the hoisted bare decl)."""
        n = len(lines)
        found = []
        for q in range(n):
            prior_decl = (q > 0 and re.match(
                r'^\s*[A-Za-z_@][\w@.<>,\[\]*? ]+\s+[A-Za-z_@]\w*\s*;$',
                lines[q - 1]))
            hit = self._phi_decl_match(lines, q, _round > 0 and prior_decl)
            if hit is not None:
                found.append((q, hit))
        counts = {}
        for _, hit in found:
            counts[hit[1]] = counts.get(hit[1], 0) + 1
        at = {q: hit for q, hit in found if counts[hit[1]] == 1}
        if not at:
            return lines
        out = []
        i = 0
        while i < n:
            hit = at.get(i)
            if hit is None:
                out.append(lines[i])
                i += 1
                continue
            indent, tok, typ, tc, ec, a1, a2, rhs1, rhs2 = hit
            l1 = lines[a1]
            ind1 = l1[:len(l1) - len(l1.lstrip())]
            l2 = lines[a2]
            ind2 = l2[:len(l2) - len(l2.lstrip())]
            out.append('%s%s %s;' % (indent, typ, tok))
            out.extend(lines[i:a1])
            out.append('%s%s = %s;' % (ind1, tok, rhs1))
            out.extend(lines[a1 + 1:tc + 3])
            out.extend(lines[tc + 3:a2])
            out.append('%s%s = %s;' % (ind2, tok, rhs2))
            out.extend(lines[a2 + 1:ec + 1])
            i = ec + 1
        return self._phi_decl_hoist(out, _round + 1) if _round < 15 else out

    def _phi_chain_decl_hoist(self, lines):
        """Hoist one temp assigned at the tail of every if/else-if/else arm.

        Each arm must reach the join, assign the same concrete declaration
        exactly once, and leave no earlier use. A later read proves the
        declaration is needed outside the arms. Without a final else the
        value is not defined on every path, so that shape always declines.
        """
        matches = []
        n = len(lines)
        for i, line in enumerate(lines):
            if not (line.strip().startswith('if (') and line.strip().endswith(')')):
                continue
            arms, heads = [], []
            head = i
            while head + 1 < n and lines[head + 1].strip() == '{':
                close = self._phi_match_brace(lines, head + 1)
                if close is None:
                    break
                arms.append((head + 2, close))
                heads.append(head)
                nxt = close + 1
                if nxt + 1 >= n:
                    break
                s = lines[nxt].strip()
                if s.startswith('else if (') and s.endswith(')'):
                    head = nxt
                    continue
                if s == 'else' and lines[nxt + 1].strip() == '{':
                    ec = self._phi_match_brace(lines, nxt + 1)
                    if ec is not None:
                        arms.append((nxt + 2, ec))
                    break
                break
            if len(arms) < 3 or len(heads) != len(arms) - 1:
                continue
            tails = []
            for start, end in arms:
                live = [k for k in range(start, end) if lines[k].strip()]
                if not live:
                    break
                hit = self._phi_tail_decl(lines[live[-1]])
                if hit is None:
                    break
                tails.append((live[-1], hit, len(live)))
            if len(tails) != len(arms) or all(t[2] == 1 for t in tails):
                continue
            typ, tok = tails[0][1][:2]
            # `object` is the unresolved-value marker; hoisting its
            # path-local 0/1 aliases would claim a join type we cannot prove.
            if typ in ('object', 'dynamic'):
                continue
            if any(t[1][:2] != (typ, tok) for t in tails):
                continue
            rx = re.compile(r'(?<![\w.])%s(?!\w)' % re.escape(tok))
            if any(rx.search(lines[k]) for h in heads[1:] for k in (h,)):
                continue
            if any(rx.search(lines[k]) for (start, _), (tail, _, _) in zip(arms, tails)
                   for k in range(start, tail)):
                continue
            if any(rx.search(t[1][2]) for t in tails):
                continue
            flow = re.compile(r'^(?:return|goto|throw|break|continue)\b')
            if any(flow.match(lines[k].strip()) for start, end in arms
                   for k in range(start, end)):
                continue
            addr = re.compile(r'(?<!&)&(?!&)\s*%s\b|\b(?:ref|out|in)\s+%s\b'
                              % (re.escape(tok), re.escape(tok)))
            if any(addr.search(s) for s in lines):
                continue
            prior = re.compile(r'(?<![\w.])%s(?!\w)\s*(?:=(?!=)|;)' % re.escape(tok))
            if any(prior.search(s) for s in lines[:i]):
                continue
            end = arms[-1][1]
            if not any(rx.search(s) for s in lines[end + 1:]):
                continue
            later_decl = re.compile(
                r'[A-Za-z_@][\w@.<>,\[\]*?]*\s+%s(?!\w)(?=\s*(?:=(?!=)|;))'
                % re.escape(tok))
            if any(later_decl.search(s) for s in lines[end + 1:]):
                continue
            matches.append((i, end, typ, tok, tails))
        chosen = []
        for hit in matches:
            if chosen and hit[0] <= chosen[-1][1]:
                continue
            if sum(x[3] == hit[3] for x in matches) != 1:
                continue
            chosen.append(hit)
        out = list(lines)
        for i, _, typ, tok, tails in reversed(chosen):
            for k, decl, _ in tails:
                indent = out[k][:len(out[k]) - len(out[k].lstrip())]
                out[k] = '%s%s = %s;' % (indent, tok, decl[2])
            indent = out[i][:len(out[i]) - len(out[i].lstrip())]
            out.insert(i, '%s%s %s;' % (indent, typ, tok))
        return out

    def _ensure_eh_helper_set(self):
        """Prove the program's throw helpers once, from the whole binary.

        Fix 90 made helper naming per-method, which is honest but narrow:
        a method with no EH pad of its own can never name a helper, so
        throw renderings collapsed and bare helper calls took their place.
        Over a fixed 400-method sample, counted with identical needles in
        both configurations, this set restores 11 -> 17 throw renderings and
        takes residual calls to the proven helpers from 6 to 0. Corpus-wide
        figures belong in the review writeup, measured, not here: the first
        draft of this docstring quoted 3,113 -> 267 and 460 -> 3,366, and
        those two scans had counted with different needles.

        Program-wide evidence restores that coverage. Two cheaper sources
        were tried first and rejected on measurement:
          * the helper's callee -- the stubs funnel into unnamed native
            plumbing, and one sink is shared by five unregistered helpers
            and thirty-six registered managed methods, so it would
            re-admit AsyncTaskMethodBuilder.SetException, the exact defect
            fix 90 removed;
          * a linear window at each pad instead of real blocks -- 0.6s,
            but it inverted role dominance for 0x1804356b0 (truly 283
            rethrow / 24 raise, approximated as 617 / 1829), which would
            emit `throw x;` where `throw;` belongs.

        So this runs the real shape detection over every pad-bearing
        method (1.7s for 4,526 here) and keeps only targets _eh_helper_ok
        already accepts -- which now also rejects runtime plumbing the
        lifter can already name, and any routine with a reachable `ret` --
        and then only where at least _EH_HELPER_MIN_WITNESSES independent
        methods agree, by a margin of _EH_HELPER_MIN_DOMINANCE. Here that
        proves exactly two: 0x180435740 rethrow (3403 witnesses vs 126) and
        0x180435670 raise (183 vs 25). An earlier draft trusted the witness
        count alone and published six, three of which were runtime plumbing
        and one of which simply returns. -- fix 91
        """
        L = self.L
        if getattr(L, 'eh_helper_set', None) is not None:
            return
        # publish the sentinel before scanning: the scan calls straight
        # back into _seh_helpers, and a half-built set must never be
        # observable to a render
        L.eh_helper_set = {}
        il = getattr(L, 'il', None)
        meta = getattr(il, 'meta', None)
        if meta is None or not hasattr(il, 'eh_regions'):
            return
        votes = {'rethrow_va': {}, 'raise_va': {}}
        for m in getattr(meta, 'methods', ()) or ():
            addr = getattr(m, 'addr', 0)
            if not addr:
                continue
            try:
                eh = il.eh_regions(addr)
            except Exception:
                continue
            if not eh or not (eh.get('pads') or ()):
                continue
            try:
                self.eh = eh
                insns, skip = self._decode(m)
                if not insns:
                    continue
                self.skip_ips = skip
                self.entry_ip = insns[0].ip
                self.last_ip = insns[-1].next_ip
                self._flat_insns = insns
                self._flat_ip_idx = {ins.ip: i for i, ins in enumerate(insns)}
                blocks, bmap = self._make_blocks(
                    insns, skip, self._scan_jump_table_leaders(insns))
                if not blocks or len(blocks) > 3000:
                    continue
                self._pad_bids = set()
                for p in eh.get('pads') or ():
                    bi = bmap.get(p)
                    if bi is not None:
                        self._pad_bids.add(bi)
                L.rethrow_va = None
                L.raise_va = None
                self._seh_helpers(blocks, bmap)
            except Exception:
                continue
            for role in ('rethrow_va', 'raise_va'):
                va = getattr(L, role, None)
                if va:
                    votes[role][va] = votes[role].get(va, 0) + 1
        proven = {}
        for va in sorted(set(votes['rethrow_va']) | set(votes['raise_va'])):
            nre = votes['rethrow_va'].get(va, 0)
            nra = votes['raise_va'].get(va, 0)
            if max(nre, nra) < self._EH_HELPER_MIN_WITNESSES:
                continue
            # 0x1804346b0 is noreturn, so plausibly a helper, but it was
            # witnessed 12 rethrow / 13 raise: nothing in that split says
            # which role it plays, so it must not be published at all
            lo = min(nre, nra)
            if lo and max(nre, nra) < lo * self._EH_HELPER_MIN_DOMINANCE:
                continue
            proven[va] = 'rethrow_va' if nre >= nra else 'raise_va'
        L.eh_helper_set = proven
        L.rethrow_va = None
        L.raise_va = None

    def _eh_helper_ok(self, va):
        """True when `va` can be an il2cpp EH runtime helper.

        The pad shapes alone are too weak to name one: across 4,526
        pad-bearing methods they picked 51 registered managed methods as the
        rethrow helper -- AsyncTaskMethodBuilder.SetException,
        Debug.LogException, Marshal.FreeHGlobal, even DateTime.AddYears --
        so every method calling one of those rendered `throw;` in place of
        the call. A real helper is unregistered native code: no MethodDef
        owns it and it is not an export. -- fix 90
        """
        if not va:
            return False
        il = getattr(self.L, 'il', None)
        if il is None:
            return True
        if va in (getattr(il, 'addr_to_method', None) or {}):
            return False
        # addr_candidates is a defaultdict; .get keeps this probe side-effect free
        cands = getattr(il, 'addr_candidates', None)
        if cands is not None and cands.get(va):
            return False
        b = getattr(il, 'bin', None)
        if b is not None and va in (getattr(b, 'exports', None) or {}):
            return False
        # ...and it must not be plumbing the lifter has ALREADY named. The
        # pad shapes taught 0x180435420 as the rethrow in 181 methods, but
        # it is a jmp thunk onto il2cpp_codegen_initialize_runtime_metadata:
        # rendering its call sites as `throw;` ate the
        # il2cpp_codegen_initialize_runtime_metadata(typeof(...)) lines and
        # cascaded into the following allocation. 0x1804356a0 and
        # 0x1804356b0 are raise_IndexOutOfRangeException and
        # raise_NullReferenceException -- real throw helpers, but each
        # raises one specific new exception and already carries an honest
        # evidence-derived name, so flattening them to a bare `throw;`
        # loses which exception is thrown. Mirror the naming path: if the
        # lifter can name the target, a structural guess must not relabel
        # it. -- fix 91
        L = self.L
        names = getattr(L, 'rt_names', None) or {}
        if va in names:
            return False
        for attr in ('rt_init_meta', 'rt_alloc', 'rt_value_box', 'rt_sqrt'):
            if va == getattr(L, attr, None):
                return False
        for attr in ('rt_arrnew', 'rt_wbarrier'):
            if va in (getattr(L, attr, None) or ()):
                return False
        twin = getattr(L, '_is_class_init_twin', None)
        if twin is not None:
            try:
                if twin(va):
                    return False
            except Exception:
                pass
        final = getattr(L, '_thunk_final', None)
        if final is not None:
            try:
                t = final(va)
            except Exception:
                t = None
            # _thunk_final also walks `sub rsp,N; call T` noreturn
            # forwarders, and genuine throw helpers are shaped exactly like
            # that, so only a resolution the lifter can NAME disqualifies
            # the candidate -- never the mere fact that it resolves
            if t is not None and t != va:
                if t in names or t == getattr(L, 'rt_init_meta', None):
                    return False
                if b is not None and t in (getattr(b, 'exports', None) or {}):
                    return False
        # ...and a throw helper never comes back. 0x180002650 was taught as
        # the rethrow helper by 45 pad-bearing methods, yet its body is
        # `movsxd rdx,[rcx+10h]; ...; ret` -- ordinary code the pad scan
        # only reached because the real helper ahead of it was skipped.
        # Four more returning routines were accepted the same way, so every
        # method calling one of them rendered a fabricated `throw;`.
        if self._eh_helper_returns(va):
            return False
        return True

    def _eh_helper_returns(self, va):
        """True when `va` positively contains a reachable `ret`.

        An il2cpp throw helper is noreturn by construction: its call site is
        followed by int3 padding, which _make_blocks already reads as
        ('abort',). A `ret` before that padding is therefore proof the
        target is not a throw helper, whatever the pad shapes voted, and
        unlike a witness count it is a property of the callee alone -- so
        it screens the per-method evidence and the program-wide set alike.
        Only positive evidence rejects: an unreadable target, undecodable
        bytes, or a routine still without a terminator after 512
        instructions keep the previous behaviour. The scan is the first
        terminator of `il2cpp.terminator.first_terminator`, not a fixed
        window: the old 64-instruction window let a routine whose `ret`
        sits at instruction 87 (0x18205f580 here) pass as a throw helper.
        -- fix 91, fix 143
        """
        cache = getattr(self, '_eh_returns_cache', None)
        if cache is None:
            cache = self._eh_returns_cache = {}
        if va in cache:
            return cache[va]
        il = getattr(self.L, 'il', None)
        b = getattr(il, 'bin', None) if il is not None else None
        res = first_terminator(b, va) == RET
        cache[va] = res
        return res

    def _seh_helpers(self, blocks, bmap):
        """Name the EH runtime helpers from the pad shapes, before lifting:
        the rethrow is the call in the branch target of the pad's wrapper
        test; the raise is the final call of a trapping pad.

        Both are per-method evidence only: lift_method clears them for every
        method, and a candidate must pass _eh_helper_ok -- an unqualified
        call is skipped, not accepted. -- fix 90
        """
        L = self.L
        for p in self.eh.get('pads') or ():
            bi = bmap.get(p)
            if bi is None:
                continue
            comp = []
            seen = set()
            stack = [bi]
            while stack:
                x = stack.pop()
                if x in seen:
                    continue
                seen.add(x)
                comp.append(x)
                for s in blocks[x].succs:
                    if s >= 0 and s not in seen:
                        stack.append(s)
            for cb in comp:
                for ins in blocks[cb].insns:
                    if ins.flow_control == FlowControl.CONDITIONAL_BRANCH                             and ins.op0_kind == OpKind.NEAR_BRANCH64:
                        tb = bmap.get(ins.near_branch_target)
                        if tb is None:
                            continue
                        for w in blocks[tb].insns:
                            if w.mnemonic == Mnemonic.CALL and w.op0_kind == OpKind.NEAR_BRANCH64:
                                if not self._eh_helper_ok(w.near_branch_target):
                                    continue
                                L.rethrow_va = w.near_branch_target
                                return
            for cb in sorted(comp, reverse=True):
                if blocks[cb].term and blocks[cb].term[0] == 'abort':
                    for w in reversed(blocks[cb].insns):
                        if w.mnemonic == Mnemonic.CALL and w.op0_kind == OpKind.NEAR_BRANCH64:
                            if not self._eh_helper_ok(w.near_branch_target):
                                continue
                            L.raise_va = w.near_branch_target
                            return

    _GETCLASS_RX = re.compile(r'^\s*(?:[A-Za-z_][\w.]*\s+)?(\w+) = ([\w.]+)\.getClass\(\);')
    _DEPTH_RX = re.compile(
        r'(\w+)\.typeHierarchyDepth < ((?:typeof\([^)]*\))|\w+)\.typeHierarchyDepth')
    _HIER_RX = re.compile(
        # fix 61c gave a 16-bit zero-extension its own mask spelling;
        # accept both so a source-width change cannot silently stop
        # this batch-16 pattern from matching
        # fix 68c: _bool_sugar's balanced-paren walk (fix 68) now
        # strips this mask's own wrapper along with it -- nothing
        # needs those parens once the mask is gone -- so they can no
        # longer be assumed present either.
        r'\*\((\w+)\.typeHierarchy \+ \(?((?:typeof\([^)]*\))|\w+)\.typeHierarchyDepth(?: & 0xFF(?:FF)?/\*z\*/)?\)?\*8 - 0x8\) != (\2|\w+)')

    _IMG_TABLE_RX = re.compile(
        r'\*\(&data_180000000 \+ ((?:(?!&data_180000000).)+?) \+ (0x[0-9a-f]+)\)'
        r' \+ &data_180000000\b')
