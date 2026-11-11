from il2cpp.prelude import *  # noqa: F401,F403
from il2cpp.cfg import LBL, _LIT_RX, _in_string

class _DataflowMixin:
    def _drop_dead_copies(self, lines: List[str]) -> List[str]:
        """Remove phi copies nothing reads. A copy's own left-hand side does not
        count as a use, so self-referential ones (`v1 = v1 + 1`) die too.

        A phi copy's RHS is `pb.end_state.get(k)` -- always a snapshot of a
        value already computed somewhere in the predecessor, never a fresh
        invocation -- so an impure (call-shaped) one is NOT automatically a
        real side effect the way an ordinary dead-temp candidate would be:
        the call that produced it was already emitted as its own statement
        by the normal exec_block path (batch 23c, found live-tracing
        `ControllerLayoutMenu.SetupKeysFromCurrentLanguage`, VA
        0x1806A18F0: ~25 independent `if (x == null) throw;` guards funnel
        into ONE shared handler that only calls `raise_NullReferenceException()`
        and reads none of them, yet each edge's dead, unread copy of an
        upstream `.GetMiscText(...)` call survived as a phantom duplicate
        because this function refused to drop ANY impure RHS,
        unconditionally). Dropping every dead impure copy outright would be
        unsound if one were ever the ONLY surviving record of a call's
        effect, so the bar is the same exact-text-twin proof `_wb_finish`/
        `_sfblob_dedupe` already use elsewhere in this file: an unread
        impure copy drops only when its RHS text is proven to survive
        elsewhere too (keep the first occurrence of any given text, never
        drop the last one standing).

        Liveness (which pure copies survive) is mark-and-sweep
        reachability, not a flat occurrence count -- same defect, same
        fix shape, as `_drop_dead_locals` (batch 25): a flat count can't
        see past a mutual copy CYCLE (`v25 = v5;` / `v5 = v25;`, each
        counting as a "use" of the other forever). Seed live from every
        token a non-candidate line reads or writes, PLUS every impure
        candidate's RHS tokens unconditionally: an impure copy either
        survives itself (live, or duplicate-protected per above) or is
        dropped only because an exact-text twin survives in its place --
        and that twin, being textually identical, names the same tokens
        -- so either way the tokens are genuinely live. That sidesteps a
        live/protected chicken-and-egg: only a PURE candidate's own
        liveness is an open question here, and pure candidates never go
        through duplicate protection. Propagate through live pure
        candidates to a fixed point; anything never reached, including
        every member of a dead cycle, drops."""
        rx = re.compile(r'^(v\d+) = (.*);$')
        for _ in range(8):
            cand = []  # (nm, rhs) if this line is a phi-copy candidate
            for st in lines:
                s = st.strip()
                m = rx.match(s)
                nm = m.group(1) if (m and m.group(1) in self.phi_names) else None
                cand.append((nm, m.group(2) if nm else None))
            live = set()
            for st, (nm, rhs) in zip(lines, cand):
                if nm is None:
                    live.update(self._TOKRX.findall(st.strip()))
                elif self._impure(rhs):
                    live.update(t for t in self._TOKRX.findall(rhs) if t != nm)
            changed = True
            while changed:
                changed = False
                for nm, rhs in cand:
                    if nm is not None and nm in live and not self._impure(rhs):
                        for tok in self._TOKRX.findall(rhs):
                            if tok != nm and tok not in live:
                                live.add(tok)
                                changed = True
            rhs_all = [(self._RHS_TEXT_RX.search(st.strip()).group(1)
                        if self._RHS_TEXT_RX.search(st.strip()) else None)
                       for st in lines]
            # remaining[text] counts every line (any shape, phi copy or
            # not) sharing that exact RHS text -- a real statement
            # elsewhere with the same text always counts, so it always
            # protects a dead impure twin even though it never enters
            # `drop` itself. Decrementing as candidates are approved keeps
            # a run of N dead impure duplicates of the same text from all
            # qualifying against each other in one pass and erasing every
            # trace of the call -- one survivor is always left standing.
            remaining = Counter(t for t in rhs_all if t is not None)
            drop = set()
            for i, (nm, rhs) in enumerate(cand):
                if nm is None or nm in live:
                    continue
                if not self._impure(rhs):
                    drop.add(i)
                    continue
                if remaining[rhs_all[i]] > 1:
                    drop.add(i)
                    remaining[rhs_all[i]] -= 1
            if not drop:
                break
            lines = [st for i, st in enumerate(lines) if i not in drop]
        return lines

    _TTOK_RX = re.compile(r'(?<![\w.])(t\d+)(?![\w])')
    _TDEF_RX = re.compile(r'^(?:var )?(t\d+) = (.*);$')
    _CMT_RX = re.compile(r'/\*.*?\*/')

    _IMPURE_GTX = re.compile(r'[\w\]\)]\s*\(|>\(')

    def _impure(self, rhs: str) -> bool:
        """Impurity test for DCE guards only (CSE purity keeps the bare
        _IMPURE: the rpc pin depends on folding `CopyFromArray<int>`).
        Blind to interposed block comments (`sub_VA/*shared body*/(...)`
        defeated the bare shape; 108722's orphaned call dropped as pure)
        and to generic-instantiation brackets (`Schedule<T>(...)` missed
        `>` before `(`; 32832's blocks vanished). `>(` with no space keeps
        `x > (y)` / `a >> (b)` pure. ponytail: DCE-only scope; CSE keeps
        folding generic calls (pinned behavior) until a golden demands
        otherwise."""
        return bool(self._IMPURE_GTX.search(self._CMT_RX.sub('', rhs)))

    def _drop_dead_temps(self, lines: List[str]) -> List[str]:
        """Drop `var tN = ...;` materializations nothing reads. Kill-on-write
        binds a stale expression defensively at every store; when the register
        turns out to be dead after the store the temp is never referenced."""
        for _ in range(16):
            counts = {}
            for st in lines:
                for tok in set(self._TTOK_RX.findall(self._CMT_RX.sub('', st))):
                    counts[tok] = counts.get(tok, 0) + 1
            out = []
            for st in lines:
                m = self._TDEF_RX.match(st.strip())
                if m and counts.get(m.group(1), 0) <= 1                         and not (self._impure(m.group(2))
                         and not self._PURE_LOAD_RX.match(m.group(2))):
                    continue
                out.append(st)
            if len(out) == len(lines):
                return lines
            lines = out
        return lines

    # ------------------------------------------------------------------
    _LOC_RX = re.compile(r'(?<![\w.])(obj\d+|num\d+|flag\d+|real\d+|v\d+|t\d+)(?![\w])')
    # optional declaration prefix: `var `, a (possibly generic/qualified)
    # type name, or nothing -- a plain assignment. The grammar cannot
    # swallow `this.field =` (no space before the local token).
    _LDEF_RX = re.compile(r'^(?:(?:var|(?:ref )?[A-Za-z_][\w.]*(?:<[^=]*?>)?(?:\[\d*\])*(?:\*+)?) )?'
                          r'(obj\d+|num\d+|flag\d+|real\d+|v\d+|t\d+) = (.*);$')

    def _drop_dead_locals(self, lines: List[str]) -> List[str]:
        """Drop assignments to renamed locals nothing ever reads. SSA
        destruction leaves per-edge copies and instruction observations
        (`objN = expr;`) whose value dies immediately; a local whose only
        occurrence in the body is its own assignment is dead. Impure right
        sides (calls) stay: they execute for effect.

        Liveness is mark-and-sweep reachability, not a flat occurrence
        count. A flat count is blind to a mutual copy CYCLE: `obj25 =
        obj5;` and `obj5 = obj25;` each count as a "use" of the other, so
        neither line's count ever drops to <=1 no matter how many peeling
        passes run -- a live-looking cycle that never actually escapes to
        any real (non-copy) statement (batch 25, ground-truthed against
        InventoryManager.DropEverything's raw disassembly: ten such
        cycles, all 100% unread, rendered as ~20 permanent phantom
        locals). Fix: seed "live" from every token a non-candidate line
        (one this pass would never remove regardless of count -- impure,
        goto-bearing, or not an assignment to a renamed local at all)
        reads or writes, then propagate backward along candidate `dst =
        rhs;` lines -- if dst is live, every local token in its rhs
        becomes live too -- until fixed point. Anything never reached,
        including every member of a cycle with no external reader, is
        dead."""
        for _ in range(4):
            parsed = []  # (is_candidate, lhs, rhs) per line, in order
            for st in lines:
                s = st.strip()
                m = self._LDEF_RX.match(s)
                if m and not (self._impure(m.group(2))
                              and not self._PURE_LOAD_RX.match(m.group(2))) \
                        and 'goto' not in m.group(2):
                    parsed.append((True, m.group(1), m.group(2)))
                else:
                    parsed.append((False, None, None))
            live = set()
            for st, (is_cand, _lhs, _rhs) in zip(lines, parsed):
                if is_cand:
                    continue
                live.update(self._LOC_RX.findall(self._CMT_RX.sub('', st)))
            changed = True
            while changed:
                changed = False
                for is_cand, lhs, rhs in parsed:
                    if is_cand and lhs in live:
                        for tok in self._LOC_RX.findall(rhs):
                            if tok not in live:
                                live.add(tok)
                                changed = True
            out = [st for st, (is_cand, lhs, _rhs) in zip(lines, parsed)
                   if not (is_cand and lhs not in live)]
            if len(out) == len(lines):
                return lines
            lines = out
        return lines

    # ------------------------------------------------------------------
    _LD_ESC_RX = re.compile(
        r'(?:&|\b(?:ref|out)\s+)(obj\d+|num\d+|flag\d+|real\d+|v\d+|t\d+)')
    _LD_GOTO_RX = re.compile(r'\bgoto\s+([A-Za-z_]\w*)\s*;')
    _LD_LBL_RX = re.compile(r'^([A-Za-z_]\w*):')
    _LD_LOOP_RX = re.compile(r'^(?:while|for|foreach|do)\b')
    # the population is local-to-local copies and constant stores (the
    # census's exact shape). A pure MEMBER load is deliberately excluded:
    # dropping `objN = this.foo.bar;` would drop a NullReferenceException
    # along with the store.
    _LD_RHS_RX = re.compile(
        r'^(?:obj\d+|num\d+|flag\d+|real\d+|v\d+|t\d+|this|null|true|false'
        r'|-?(?:0x[0-9a-fA-F]+|\d+(?:\.\d+)?)[fdmulFDMUL]{0,2})$')

    # ------------------------------------------------------------------
    # fix 75b: the Roslyn/MCS cached-delegate backer triple. After fix
    # 75 the merge renders as two phi copies around the fork, so the
    # whole compiler pattern is recognisable and folds to the ?? spelling,
    # dropping the cctor artifact, the unresolved shared-ctor call and
    # the phi copies:
    #   T objA = CACHE;                       T objA = CACHE ?? (CACHE = new T(a1, a2));
    #   [objB = objA;]                        <later uses of objB -> objA>
    #   if (objA == null) | if (!(objA != null))
    #   {
    #       [if (X.initialized != objA) { }]  (the cctor artifact, empty)
    #       T objC = new T();
    #       object objD = sub_.../*..*/(objC, a1, a2);
    #       CACHE = objC;
    #       [dead spills: single-occurrence LHS, side-effect-free RHS]
    #       [objB = objC;]
    #   }
    # Guards: the arm carries NOTHING else; the decl's cache text and the
    # store's LHS agree exactly; objA/objB have no other assignments; the
    # ctor call's LHS, the new token and every spill LHS occur nowhere
    # else; spill RHS is side-effect-free (_DC_PURE_RX -- _PURE_LOAD_RX
    # rejects digit-leading `<>9`-style member names, which is exactly
    # the singleton spill's spelling, so this pass carries its own).
    _DC_CACHE_RX = re.compile(r'^(.+)\.(<>9__\w+)$')
    _DC_DECL_RX = re.compile(
        r'^((?:ref )?[A-Za-z_][\w.]*(?:<[^=]*?>)?(?:\[\d*\])* )?(\w+) = (.+);$')
    _DC_COPY_RX = re.compile(r'^(\w+) = (\w+);$')
    _DC_NEW_RX = re.compile(
        r'^([\w.<>,\[\] ]+ )?(\w+) = new ([\w.<>,\[\] ]+)\(\);$')
    _DC_CTOR_RX = re.compile(
        r'^([\w.<>,\[\] ]+ )?(\w+) = (sub_[0-9a-fA-F]+)\s*\((.*)\);$')
    _DC_PURE_RX = re.compile(
        r'^typeof\([^()]*\)(?:\.[\w<>]+)*$'
        r'|^(?:-?\d+|0x[0-9a-fA-F]+|true|false|null|this)$'
        r'|^[A-Za-z_][\w]*(?:\.[\w<>]+)*$')
    _DC_HEAD_RX = (re.compile(r'^if \(!\((\w+) != null\)\)$'),
                   re.compile(r'^if \((\w+) == null\)$'))

    @staticmethod
    def _dc_tokens(tok):
        return re.compile(r'(?<![\w.])%s(?![\w])' % re.escape(tok))

    @staticmethod
    def _dc_strip_cmts(s):
        out = []
        i = 0
        while i < len(s):
            if s.startswith('/*', i) and not _in_string(s, i):
                j = s.find('*/', i + 2)
                if j < 0:
                    break
                out.append(' ')
                i = j + 2
                continue
            out.append(s[i])
            i += 1
        return ''.join(out)

    @staticmethod
    def _dc_split_args(s):
        args = []
        depth = 0
        cur = []
        i = 0
        while i < len(s):
            c = s[i]
            if c == '"':
                j = i + 1
                while j < len(s):
                    if s[j] == '"' and s[j - 1] != '\\':
                        break
                    j += 1
                cur.append(s[i:j + 1])
                i = j + 1
                continue
            if c in '([':
                depth += 1
            elif c in ')]':
                depth -= 1
            elif c == ',' and depth == 0:
                args.append(''.join(cur).strip())
                cur = []
                i += 1
                continue
            cur.append(c)
            i += 1
        tail = ''.join(cur).strip()
        if tail:
            args.append(tail)
        return args

    def _dc_tok_count(self, lines, tok):
        rx = self._dc_tokens(tok)
        return sum(len(rx.findall(l)) for l in lines)

    def _dc_is_assign(self, lines, tok):
        """Lines assigning tok (`... tok = ...` at statement head)."""
        rx = re.compile(r'^(?:[\w.<>,\[\] ]+ )?%s = ' % re.escape(tok))
        hits = 0
        for l in lines:
            if rx.match(l.strip()):
                hits += 1
        return hits

    def _delegate_cache_fold(self, lines: List[str]) -> List[str]:
        out = list(lines)
        n = len(out)
        i = 0
        while i < n:
            st = out[i].strip()
            dm = self._DC_DECL_RX.match(st)
            if not dm:
                i += 1
                continue
            lhs = dm.group(2)
            cache = dm.group(3).strip()
            if not self._DC_CACHE_RX.match(cache):
                i += 1
                continue
            p = i + 1
            while p < n and not out[p].strip():
                p += 1
            objB = None
            if p < n:
                pm = self._DC_COPY_RX.match(out[p].strip())
                if pm and pm.group(2) == lhs:
                    objB = pm.group(1)
                    p += 1
                    while p < n and not out[p].strip():
                        p += 1
            if p >= n:
                i += 1
                continue
            hs = out[p].strip()
            hm = None
            for rx in self._DC_HEAD_RX:
                hm = rx.match(hs)
                if hm:
                    break
            if not hm or hm.group(1) != lhs:
                i += 1
                continue
            q = p + 1
            while q < n and not out[q].strip():
                q += 1
            if q >= n or out[q].strip() != '{':
                i += 1
                continue
            depth = 1
            close = -1
            k = q + 1
            while k < n:
                s2 = out[k].strip()
                if s2 == '{':
                    depth += 1
                elif s2.startswith('}'):
                    depth -= 1
                    if depth == 0:
                        close = k
                        break
                k += 1
            if close < 0:
                i += 1
                continue
            e = close + 1
            while e < n and not out[e].strip():
                e += 1
            if e < n and out[e].strip().startswith('else'):
                i += 1
                continue
            inner = [out[x].strip() for x in range(q + 1, close) if out[x].strip()]
            idx = 0
            ok = True
            # optional cctor artifact: an empty if whose compare is
            # `<X>.initialized` against the register-zero (objA or 0)
            if idx < len(inner) and inner[idx].startswith('if (') \
                    and '.initialized' in inner[idx]:
                m4 = re.match(r'^if \(!?\((.+\.initialized) (?:!=|==) (\w+)\)\)$',
                              inner[idx])
                if not m4:
                    ok = False
                else:
                    cmp_tok = m4.group(2)
                    if cmp_tok not in ('0', lhs):
                        ok = False
                    elif idx + 2 < len(inner) and inner[idx + 1] == '{' \
                            and inner[idx + 2] == '}':
                        idx += 3
                    else:
                        ok = False
            if not ok:
                i += 1
                continue
            # the allocation
            nm = self._DC_NEW_RX.match(inner[idx]) if idx < len(inner) else None
            if not nm:
                i += 1
                continue
            new_tok = nm.group(2)
            new_ty = nm.group(3)
            idx += 1
            # the shared ctor body call
            cs = self._dc_strip_cmts(inner[idx]) if idx < len(inner) else ''
            cmm = self._DC_CTOR_RX.match(cs)
            if not cmm:
                i += 1
                continue
            ctor_tok = cmm.group(2)
            args_list = self._dc_split_args(cmm.group(4))
            if not args_list or args_list[0] != new_tok:
                i += 1
                continue
            extra = args_list[1:]
            idx += 1
            # the cache store
            sm = re.match(r'^(.+?\.<>9__\w+) = (\w+);$', inner[idx]) \
                if idx < len(inner) else None
            if not sm or sm.group(1) != cache or sm.group(2) != new_tok:
                i += 1
                continue
            idx += 1
            # trailing dead spills + the optional arm-edge phi copy
            final_copy = False
            while idx < len(inner):
                s3 = inner[idx]
                if objB and self._DC_COPY_RX.match(s3) \
                        and s3 == '%s = %s;' % (objB, new_tok):
                    final_copy = True
                    idx += 1
                    break
                lm = self._DC_DECL_RX.match(s3)
                if lm and lm.group(2) and lm.group(2) != lhs:
                    spill = lm.group(2)
                    rhs = lm.group(3).strip()
                    if self._dc_tok_count(out, spill) == 1 \
                            and (not self._IMPURE.search(rhs)
                                 or self._DC_PURE_RX.match(rhs)):
                        idx += 1
                        continue
                ok = False
                break
            if not ok or idx != len(inner) or (objB and not final_copy):
                i += 1
                continue
            # global single-definition / no-escape guards
            if objB:
                if self._dc_is_assign(out, objB) != 2:
                    i += 1
                    continue
                if self._dc_tok_count(out[:i + 1], objB):
                    i += 1
                    continue
            if self._dc_is_assign(out, lhs) != 1:
                i += 1
                continue
            if self._dc_tok_count(out, new_tok) != self._dc_tok_count(inner, new_tok):
                i += 1
                continue
            if self._dc_tok_count(out, ctor_tok) != self._dc_tok_count(inner, ctor_tok):
                i += 1
                continue
            ctor_lhs_tok = cmm.group(2)
            if self._dc_tok_count(out, ctor_lhs_tok) != 1:
                i += 1
                continue
            # rewrite
            type_prefix = dm.group(1) or ''
            new_decl = '%s%s = %s ?? (%s = new %s(%s));' % (
                type_prefix, lhs, cache, cache, new_ty, ', '.join(extra))
            tail_start = close + 1
            out = out[:i] + [new_decl] + out[tail_start:]
            n = len(out)
            if objB:
                rx = self._dc_tokens(objB)
                for t in range(i + 1, len(out)):
                    l2 = out[t]
                    if not rx.search(l2):
                        continue
                    out[t] = rx.sub(
                        lambda mm: lhs if not _in_string(l2, mm.start())
                        else mm.group(0), l2)
            i += 1
        return out

    def _drop_dead_lastdef(self, lines: List[str]) -> List[str]:
        """fix 55 (batch 48): drop a local's LAST definition when no
        backward flow can carry it to an earlier read.

        `_drop_dead_locals` above is occurrence-based and flow-
        insensitive -- a single mention anywhere, including only BEFORE
        the store, marks the token live and protects every definition of
        it. That is 78.5% of the 19,720 no-later-read pure copies at
        b47_out1 (work/census_b48_noread.py); `_copy_prop`'s backward
        sweep refuses another 55% for sitting above any later `goto`,
        and 16.3% are minted by the LATE `_hoist_shared_tails` after
        both sweeps have already run.

        Soundness: a store whose destination has no occurrence at any
        later line can only be observed by reaching an EARLIER line that
        reads it, and that needs backward flow. So the drop is refused
        when the line is inside a loop frame, inside the span of a
        backward `goto` (label at k, goto at j>=k protects [k, j] --
        a goto-formed loop is a loop), or when the destination is ever
        address-taken (a callee holds the pointer; nothing in the
        statement text tracks what it does with it). Right sides stay
        bare tokens and literals so no exception-raising load is ever
        dropped with the store.

        Iterated to a fixpoint: dropping one last-def can make the
        definition above it a last-def in turn."""
        # early-out: the measured yield is 405 lines tree-wide, so the
        # per-method cost must be near zero. One cheap match per line
        # (no scrubbing, no occurrence map) rules out the large
        # majority of methods, which carry no candidate at all.
        for st in lines:
            m0 = self._LDEF_RX.match(st.strip())
            if m0 and self._LD_RHS_RX.match(m0.group(2).strip()):
                break
        else:
            return lines
        for _ in range(6):
            n = len(lines)
            clean = [self._CMT_RX.sub('', _LIT_RX.sub('""', s.strip()))
                     for s in lines]
            # loop frames, by brace level
            in_loop = [False] * n
            frames = []
            last_ctrl = ''
            for i, s in enumerate(clean):
                in_loop[i] = any(frames)
                if s == '{':
                    frames.append(bool(self._LD_LOOP_RX.match(last_ctrl)))
                    in_loop[i] = any(frames)
                elif s.startswith('}'):
                    if frames:
                        frames.pop()
                last_ctrl = s
            # backward-goto spans: `goto L` at j with L defined at k<=j
            label_at = {}
            for i, s in enumerate(clean):
                m = self._LD_LBL_RX.match(s)
                if m:
                    label_at.setdefault(m.group(1), i)
            back = [False] * n
            for j, s in enumerate(clean):
                for g in self._LD_GOTO_RX.finditer(s):
                    k = label_at.get(g.group(1))
                    if k is not None and k <= j:
                        for x in range(k, j + 1):
                            back[x] = True
            escaped = set()
            for s in clean:
                escaped.update(m.group(1) for m in self._LD_ESC_RX.finditer(s))
            # occurrences of each local, by line
            occ = {}
            for i, s in enumerate(clean):
                for tok in set(self._LOC_RX.findall(s)):
                    occ.setdefault(tok, []).append(i)
            drop = set()
            for i, s in enumerate(clean):
                if in_loop[i] or back[i]:
                    continue
                m = self._LDEF_RX.match(s)
                if not m or not self._LD_RHS_RX.match(m.group(2).strip()):
                    continue
                dst = m.group(1)
                if dst in escaped or dst == m.group(2).strip():
                    continue
                if any(j > i and j not in drop for j in occ.get(dst, ())):
                    continue
                drop.add(i)
            if not drop:
                return lines
            lines = [st for i, st in enumerate(lines) if i not in drop]
        return lines

    _DU_KEYWORDS = frozenset((
        'var', 'ref', 'in', 'out', 'scoped', 'readonly', 'const',
        'fixed', 'volatile', 'else', 'if', 'for', 'foreach', 'while',
        'do', 'switch', 'using', 'lock', 'try', 'return', 'throw',
        'goto', 'case', 'default', 'new'))

    def _dead_unknown_head(self, l1, l2):
        """Fold an adjacent dead `unknown` store, or None.

        Returns ('drop',) to delete the first line, ('strip', text)
        to replace it with a bare declaration, or None to keep both.
        Ground truth: LagCompensationUtils 63027
        (`vector32 = unknown;` + `vector32 = 0;`, ~16 twins) and
        GraphCollision 105032 (pointer-slot twin). An adjacent
        overwrite with no line between is unconditionally sequenced,
        so the first store is dead iff its right side is
        side-effect-free (bare `unknown` always is) and the second
        right side never reads the destination. Labels, `==`, calls
        in the destination, and `var`/`ref`/keyword declarations
        all decline; fields were never evidenced, so only bare,
        index/slot, and plain-typed locals qualify. Never raises.
        """
        try:
            return self._dead_unknown_head_inner(l1, l2)
        except Exception:
            return None

    def _dead_unknown_head_inner(self, l1, l2):
        m1 = re.match(r'^(\s*)(.+?)(?:(?<![\w=!<>])=(?!=))(.+?);\s*$', l1)
        if m1 is None:
            return None
        ind, lhs, rhs = m1.group(1), m1.group(2).strip(), m1.group(3).strip()
        if rhs != 'unknown' or ':' in lhs:
            return None
        if re.search(r'\w\s*\(', lhs) or re.search(r'\bnew\b', lhs):
            return None
        if re.fullmatch(r'[A-Za-z_]\w*', lhs):
            mode, key, head = 'drop', lhs, None
        elif lhs.endswith(']') and '[' in lhs:
            mode, key, head = 'drop', lhs, None
        else:
            dm = re.match(r'^(.+?)\s+([A-Za-z_]\w*)$', lhs)
            if dm is None:
                return None
            if not dm.group(1).strip() or dm.group(1).strip().split()[0] in self._DU_KEYWORDS:
                return None
            mode, key = 'strip', dm.group(2)
            head = ind + dm.group(1).strip() + ' ' + dm.group(2) + ';'
        m2 = re.match(r'^(\s*)(.+?)(?:(?<![\w=!<>])=(?!=))(.+?);\s*$', l2)
        if m2 is None:
            return None
        lhs2, rhs2 = m2.group(2).strip(), m2.group(3).strip()
        if mode == 'strip':
            if lhs2 != key:
                return None
        elif lhs2 != key:
            return None
        toks_lhs = set(re.findall(r'[A-Za-z_]\w*', lhs))
        toks_rhs = set(re.findall(r'[A-Za-z_]\w*', rhs2))
        if toks_lhs & toks_rhs:
            return None
        if mode == 'drop':
            return ('drop',)
        return ('strip', head)

    def _drop_dead_unknown_store(self, lines: List[str]) -> List[str]:
        """Drop `LHS = unknown;` overwritten by the next statement.

        Runs on rendered lines just before `_semantic_local_names`,
        after every restructuring pass, so the adjacency it sees is
        final; the flow-insensitive `_drop_dead_locals` cannot drop
        these (the destination is read later), and this pass cannot
        disturb it (one deleted pure line, zero uses between).
        """
        out = []
        i, n = 0, len(lines)
        while i < n:
            if i + 1 < n:
                r = self._dead_unknown_head(lines[i], lines[i + 1])
                if r is not None:
                    if r[0] == 'strip':
                        out.append(r[1])
                    i += 1
                    continue
            out.append(lines[i])
            i += 1
        return out

    # ------------------------------------------------------------------
    _CP_REFOUT_RX = re.compile(
        r'(?:(?:\b(?:ref|out))\s+|&)(obj\d+|num\d+|flag\d+|real\d+|v\d+|t\d+)')
    _CP_KILLDEF_RX = re.compile(
        r'(?<![\w.])(obj\d+|num\d+|flag\d+|real\d+|v\d+|t\d+)'
        r'\s*(?:(?:\+\+|--)|(?:\+=|-=|\*=|/=|%=|&=|\|=|\^=|<<=|>>=)|=(?![=]))')
    _CP_BARE_RX = re.compile(r'^(?:obj\d+|num\d+|flag\d+|real\d+|v\d+|t\d+|this)$')
    _CP_CTRL_RX = re.compile(r'^(while|for|foreach|do|if|else|switch|using|lock|try)\b')
    _CP_BREAK_RX = re.compile(r'^(?:return\b|throw\b|goto\b|break;|continue;)')

    def _cp_subst(self, s, active, skip_spans):
        if not active:
            return s
        cspans = [m.span() for m in self._CMT_RX.finditer(s)]
        out = []
        last = 0
        for m in self._LOC_RX.finditer(s):
            rep = active.get(m.group(1))
            if rep is None:
                continue
            i = m.start()
            if _in_string(s, i) or any(a <= i < b for a, b in cspans) \
                    or any(a <= i < b for a, b in skip_spans):
                continue
            # `&tok`/`ref tok`/`out tok` bind the SLOT, not the value --
            # never substitute there (and the kill scan rebinds them)
            if i > 0 and s[i - 1] == '&':
                continue
            if re.search(r'\b(?:ref|out)\s+$', s[:i]):
                continue
            out.append(s[last:i])
            out.append(rep)
            last = m.end()
        if not out:
            return s
        out.append(s[last:])
        return ''.join(out)

    _CP_DECL_RX = re.compile(r'^\s*(?!return\b)([A-Za-z_@][^=;(){}]*?)\s+'
                             r'(obj\d+|num\d+|flag\d+|real\d+|t\d+)\s*=(?![=])')
    _CP_OBJECT_TYPES = frozenset(('object', 'System.Object'))

    def _copy_prop(self, lines: List[str]) -> List[str]:
        """Forward substitution for pure local-to-local copies (todo SS3
        #3: 171k `objN = objM;` + 2.1k `objN = this;` lines), then a
        backward last-def-dead sweep. A copy's uses are rewritten to the
        source while it provably still holds the same value: any
        redefinition of either side, a `ref`/`out`/`&` of it, a label /
        catch / finally join, a flow-break line, or the closing `}` of
        the level that recorded it ends the substitution (conservative
        -- correctness never depends on dominance here, only on
        straight-line textual order). The sweep then drops pure
        assignments no later line reads (loop-keyword frames and any
        later `goto` block the drop: a back edge can re-read the value
        on the next iteration even when no text-later read exists)."""
        LOC = self._LOC_RX
        out = []
        active = {}
        decl_ty = {}
        for _st in lines:
            _m = self._CP_DECL_RX.match(_st.strip())
            if _m and _m.group(2) not in decl_ty:
                decl_ty[_m.group(2)] = _m.group(1).strip()
        frames = []          # per brace level: [keys added there, is_loop]
        in_loop = []         # per emitted line: inside any loop frame
        last_ctrl = ''
        for st in lines:
            ind = st[:len(st) - len(st.lstrip())]
            s = st.strip()
            if not s:
                out.append(st)
                in_loop.append(any(f[1] for f in frames))
                continue
            if s == '{':
                frames.append([[], last_ctrl in ('while', 'for', 'foreach', 'do')])
                out.append(st)
                in_loop.append(any(f[1] for f in frames))
                last_ctrl = ''
                continue
            if s == '}':
                if frames:
                    for k in frames.pop()[0]:
                        active.pop(k, None)
                out.append(st)
                in_loop.append(any(f[1] for f in frames))
                last_ctrl = ''
                continue
            if (s.endswith(':') and (re.match(r'^L_[0-9a-fA-F]+:$', s)
                                     or s.startswith(LBL) or s.startswith('case ')
                                     or s == 'default:')) \
                    or s.startswith(('catch', 'finally')):
                active.clear()
                out.append(st)
                in_loop.append(any(f[1] for f in frames))
                last_ctrl = ''
                continue
            cspans = [m.span() for m in self._CMT_RX.finditer(s)]
            kill_spans = []
            kills = []
            for m in self._CP_KILLDEF_RX.finditer(s):
                if _in_string(s, m.start()) \
                        or any(a <= m.start(1) < b for a, b in cspans):
                    continue
                kills.append(m.group(1))
                kill_spans.append(m.span(1))
            for m in self._CP_REFOUT_RX.finditer(s):
                if _in_string(s, m.start()):
                    continue
                kills.append(m.group(1))
                kill_spans.append(m.span(1))
            s2 = self._cp_subst(s, active, kill_spans)
            for tok in kills:
                active.pop(tok, None)
                for k in [k for k, v in active.items() if v == tok]:
                    del active[k]
            m = self._LDEF_RX.match(s)
            if m and self._CP_BARE_RX.match(m.group(2)) \
                    and m.group(1) != m.group(2):
                src = active.get(m.group(2), m.group(2))
                dt = decl_ty.get(m.group(1))
                st = decl_ty.get(src)
                if dt is None or st is None \
                        or dt in self._CP_OBJECT_TYPES \
                        or st in self._CP_OBJECT_TYPES or dt == st:
                    active[m.group(1)] = src
                # else: declared concrete types disagree (a struct home
                # copied over a typed temp, or vice versa) -- the copy is
                # not value-preserving, so it never registers; both sides
                # keep their own proved spellings.
                if frames:
                    frames[-1][0].append(m.group(1))
            if self._CP_BREAK_RX.match(s2):
                active.clear()
            mc = self._CP_CTRL_RX.match(s)
            last_ctrl = mc.group(1) if mc else ''
            out.append(ind + s2)
            in_loop.append(any(f[1] for f in frames))
        # ---- backward last-def-dead sweep ----------------------------
        for _ in range(4):
            n = len(out)
            reads_after = Counter()
            goto_after = False
            drop = [False] * n
            for i in range(n - 1, -1, -1):
                s = out[i].strip()
                if not drop[i] and s:
                    m = self._LDEF_RX.match(s)
                    if m and not in_loop[i] and not goto_after \
                            and reads_after.get(m.group(1), 0) == 0 \
                            and 'goto' not in m.group(2) \
                            and not (self._impure(m.group(2))
                                     and not self._PURE_LOAD_RX.match(m.group(2))):
                        drop[i] = True
                if not drop[i] and s:
                    sm = self._LDEF_RX.match(s)
                    body = s[sm.end(1):] if sm else s
                    body = self._CMT_RX.sub('', _LIT_RX.sub('""', body))
                    for t in LOC.findall(body):
                        reads_after[t] += 1
                    if re.search(r'\bgoto\b', s):
                        goto_after = True
            if not any(drop):
                break
            out = [st for i, st in enumerate(out) if not drop[i]]
            in_loop = [fl for i, fl in enumerate(in_loop) if not drop[i]]
        return out


    _SELFCOPY_RX = re.compile(
        r'^((?:obj\d+|num\d+|flag\d+|real\d+|v\d+|t\d+)) = \1;'
        r'(?:\s*/\*.*\*/)?$')

    def _selfcopy_drop(self, lines: List[str]) -> List[str]:
        """fix 49 (todo lead #1): bare `X = X;` self-copies drop
        unconditionally. The lifter mints them as loop-phi copies
        (first statements of a for body); _copy_prop never registers
        them (its dst != src guard) and its backward dead sweep
        refuses in-loop drops, so they survived to output (103 AC
        lines at b40_out2). Assigning a local its own current value
        is a no-op whatever surrounds it -- loop-carried,
        address-taken, in an arm: the slot already holds exactly
        the value being written. Only whole bare-token statements
        match; `X += X`, `X = X + 1`, member self-assigns and decl
        lines are not the shape."""
        out = []
        for st in lines:
            if self._SELFCOPY_RX.match(st.strip()):
                continue
            out.append(st)
        return out

    # ------------------------------------------------------------------
    _SINGLETON_DECL_RX = re.compile(
        r'^(?:(?:var|[A-Za-z_][\w.<>]*(?:\[\])?) )?(obj\d+|t\d+) = typeof\(([\w.]+)\)\.Instance;$')
    _CSE_CTRL_RX = re.compile(
        r'^(?:if\s*\(|else\b|while\s*\(|for\s*\(|foreach\s*\(|switch\s*\(|'
        r'case\b|default:|try\b|catch\b|finally\b|do\b|return\b|break;|continue;|goto\b)')

    _SJS_TYOF_TEMP_RX = re.compile(
        r'^(?:(?:var|[A-Za-z_][\w.<>]*(?:\[\])?) )?(obj\d+|t\d+) = typeof\(([\w.]+)\);$')
    _SJS_HAZ_RX = re.compile(
        r'typeof\(([\w.]+)\)(?:\.[\w.]+)*\s*'
        r'(?:=[^=>]|[-+*/%&|^]=|<<=|>>=|\+\+|--)')
    _SJS_SFBLOB_RX = re.compile(r'typeof\(([\w.]+)\)\.__static_fields')
    _SJS_INST_STORE_RX = re.compile(
        r'((?:typeof\([\w.]+\))|[\w.\[\]]+)\s*\.Instance\s*'
        r'(?:=[^=>]|[-+*/%&|^]=|<<=|>>=|\+\+|--)')
    _SJS_ASSIGN_RX = re.compile(
        r'([A-Za-z_]\w*)\s*(?:(?:[-+*/%&|^]|<<|>>)?=(?![=>])|\+\+|--)')
    _SJS_BYREF_RX = re.compile(r'(?:&|\bref\b|\bout\b)\s*([A-Za-z_]\w*)')
    _SJS_STRLIT_SPLIT = re.compile(r'("(?:[^"\\]|\\.)*")')

    def _singleton_cse(self, lines: List[str]) -> List[str]:
        """fix 46 (todo lead #1): ONE `typeof(X).Instance` fetch per type
        per method. The load itself is pure (the Unity singleton pattern
        compiles to a plain static-slot read), but the lifter
        re-materializes it into a fresh temp after every call that
        clobbers the register holding it -- 1,175 redundant fetches in
        Assembly-CSharp at b38, three inside five statements in
        InventoryManager.PickupNewObj. The first fetch decl hoists to
        the method head (a pure load evaluated early is invisible),
        later fetch decls drop and alias to it, and INLINE spellings
        rewrite to the canon token -- `(typeof(T).Instance).member`,
        bare `objK = typeof(T).Instance;` assignment sites, and the
        `Type objK = typeof(T); objK.Instance` temp path included.

        Calls between fetches no longer reset the cache: that is the
        documented, accepted trade (a called method could in principle
        reassign the static mid-method; these singletons are set once
        in Awake, and one temp per method is what the source read).
        What still disqualifies, conservatively: any store to the
        type's statics in this method (`*typeof(T).Instance = v`,
        `typeof(T).field = v`), an unresolved `typeof(T).
        __static_fields` mention, a store to `.Instance` through a
        receiver whose type is unprovable from text (disqualifies
        every type -- the receiver could be any of them), and any
        fetch token that is reassigned or taken byref anywhere (its
        value is not the fetch everywhere, so aliasing it would merge
        two values). Mint: a type whose only fetches are inline
        spellings gets a fresh `var objN = typeof(T).Instance;` head
        decl. Unit mirror: work/cse_test.py."""
        def mask(s):
            # even parts are code, odd parts are string literals
            return ''.join(p if k % 2 == 0 else ''
                           for k, p in enumerate(self._SJS_STRLIT_SPLIT.split(s)))

        stripped = [st.strip() for st in lines]
        assigns = {}
        byref = set()
        for s in stripped:
            ms = mask(s)
            for mm in self._SJS_ASSIGN_RX.finditer(ms):
                assigns[mm.group(1)] = assigns.get(mm.group(1), 0) + 1
            for mm in self._SJS_BYREF_RX.finditer(ms):
                byref.add(mm.group(1))
        fetch = {}          # idx -> (token, type) for EVERY decl-fetch line
        for i, s in enumerate(stripped):
            mm = self._SINGLETON_DECL_RX.match(s)
            if mm:
                fetch[i] = (mm.group(1), mm.group(2))
        tyof_temp = {}      # token -> type, single-assignment typeof temps
        for s in stripped:
            mm = self._SJS_TYOF_TEMP_RX.match(s)
            if mm and assigns.get(mm.group(1), 0) == 1 and mm.group(1) not in byref:
                tyof_temp[mm.group(1)] = mm.group(2)
        # hazards: statics stores / unresolved blobs / Instance stores
        bad = set()
        for s in stripped:
            ms = mask(s)
            for mm in self._SJS_HAZ_RX.finditer(ms):
                bad.add(mm.group(1))
            for mm in self._SJS_SFBLOB_RX.finditer(ms):
                bad.add(mm.group(1))
            for mm in self._SJS_INST_STORE_RX.finditer(ms):
                if not mm.group(1).startswith('typeof('):
                    # `.Instance = v` through an unprovable receiver:
                    # no type in this method folds
                    return lines
        # participating fetch decls (token never reassigned, never byref)
        by_ty = {}
        for i in sorted(fetch):
            tok, ty = fetch[i]
            if ty in bad or assigns.get(tok, 0) != 1 or tok in byref:
                continue
            by_ty.setdefault(ty, []).append(i)
        part = {i for v in by_ty.values() for i in v}
        skip = set(fetch) - part      # their fetch stays an independent read

        # inline spelling census per type (decl lines and skip lines
        # excluded). Candidates come from decl fetches, typeof-temps
        # AND a direct spelling pre-scan -- the mint path has no decl
        # to announce the type (46c).
        spell = 'typeof(%s).Instance'
        cand = set(list(by_ty) + list(tyof_temp.values()))
        for s in stripped:
            for mm in re.finditer(r'typeof\(([\w.]+)\)\.Instance', mask(s)):
                cand.add(mm.group(1))
        inline_ct = {}
        temp_of = {ty: [k for k, v in tyof_temp.items() if v == ty]
                   for ty in cand}
        for i, s in enumerate(stripped):
            if i in part or i in skip:
                continue
            ms = mask(s)
            for ty in cand:
                if ty in bad:
                    continue
                c = ms.count(spell % ty)
                for kp in temp_of.get(ty, ()):
                    c += len(re.findall(r'(?<![\w.])%s\.Instance\b' % re.escape(kp), ms))
                if c:
                    inline_ct[ty] = inline_ct.get(ty, 0) + c
        # fold decision + canon selection
        drop = set()
        alias = {}
        hoist = []          # (first_site_idx, canon_decl_text)
        canon_tok = {}
        minted = 0
        maxobj = 0
        for mm in re.finditer(r'\bobj(\d+)\b', '\n'.join(stripped)):
            maxobj = max(maxobj, int(mm.group(1)))
        for ty in sorted(set(list(by_ty) + list(inline_ct)),
                         key=lambda t: (by_ty.get(t, [len(lines) + 1])[0],
                                        -inline_ct.get(t, 0))):
            sites = by_ty.get(ty, [])
            if len(sites) + inline_ct.get(ty, 0) < 2:
                continue
            if sites:
                ci = sites[0]
                tok = fetch[ci][0]
                text = stripped[ci]
                drop.add(ci)
                for j in sites[1:]:
                    alias[fetch[j][0]] = tok
                    drop.add(j)
            else:
                minted += 1
                tok = 'obj%d' % (maxobj + minted)
                text = 'var %s = %s;' % (tok, spell % ty)
            canon_tok[ty] = tok
            hoist.append((sites[0] if sites else len(lines) + 1, text))
        if not hoist:
            return lines
        hoist.sort(key=lambda t: t[0])
        out = [text for _, text in hoist]
        toks = '|'.join(re.escape(t) for t in canon_tok.values())
        paren_rx = re.compile(r'\((%s)\)\.' % toks)
        for i, st in enumerate(lines):
            if i in drop or i in skip:
                continue
            parts = self._SJS_STRLIT_SPLIT.split(st)
            for k in range(0, len(parts), 2):
                seg = parts[k]
                for ty, tok in canon_tok.items():
                    seg = seg.replace(spell % ty, tok)
                    for kp in temp_of.get(ty, ()):
                        seg = re.sub(r'(?<![\w.])%s\.Instance\b' % re.escape(kp),
                                     tok, seg)
                seg = self._LOC_RX.sub(
                    lambda m2: alias.get(m2.group(1), m2.group(1)), seg)
                seg = paren_rx.sub(r'\1.', seg)
                parts[k] = seg
            out.append(''.join(parts))
        return out

    _VAL_DECL_RX = re.compile(
        r'^(?:(var|[A-Za-z_][\w.<>]*(?:\[\])?) )?(obj\d+|t\d+) = (.+);$')
    _VAL_PURETYOF_RX = re.compile(r'typeof\([\w.]+\)')
    _VAL_KILL_ASSIGN_RX = re.compile(
        r'([A-Za-z_]\w*)\s*(?:(?:[-+*/%&|^]|<<|>>)?=(?![=>])|\+\+|--)')
    _VAL_KILL_BYREF_RX = re.compile(r'(?:&|\bref\b|\bout\b)\s*([A-Za-z_]\w*)')
    _VAL_STRLIT_SPLIT = re.compile(r'("(?:[^"\\]|\\.)*")')

    def _value_cse(self, lines: List[str]) -> List[str]:
        """fix 47 (todo lead #2): fold same-block decls whose RHS is the
        SAME pure-load text (`InputActionAsset objN = this.playerInput.
        actions;` x14 in InventoryManager.Update at b39 -- the lifter
        re-materializes a member read after every call). Identical RHS
        text + same type prefix -> later decls drop and alias to the
        first. Calls between decls do NOT reset (the documented
        singleton-class trade); a store to ANY identifier named in the
        cached RHS does (the load's base/index changed), as does a
        ref/out/& of one, and every brace/label/control head (block-
        local runs only). Bare-token RHS is copy_prop's domain; an RHS
        with call parens (past the pure `typeof(T)` carve-out) or a
        ternary `?` is never cached. Unit mirror: work/cse_test.py."""
        def mask(s):
            return ''.join(p if k % 2 == 0 else ''
                           for k, p in enumerate(self._VAL_STRLIT_SPLIT.split(s)))

        alias = {}
        drop = set()
        # a decl may only fold when its token is assigned exactly
        # once in the body (this line): a multi-assigned token holds
        # other values elsewhere, and renaming would merge them
        # (47c -- BurstSolverImpl.ApplyFrame's duplicated stores)
        n_assigns = {}
        for st in lines:
            ms0 = mask(st.strip())
            for mm in self._VAL_KILL_ASSIGN_RX.finditer(ms0):
                n_assigns[mm.group(1)] = n_assigns.get(mm.group(1), 0) + 1
        avail = {}       # (type_text, rhs) -> canon token
        depth_of = {}    # canon token -> brace depth at its decl
        idents = {}      # canon token -> set of identifiers in its line
        depth = 0
        for i, st in enumerate(lines):
            s = st.strip()
            if not s:
                continue
            if s == '{':
                depth += 1
                continue
            if s == '}':
                depth -= 1
                for k2 in [k2 for k2, dd in depth_of.items() if dd > depth]:
                    for kk in [kk for kk, vv in avail.items() if vv == k2]:
                        del avail[kk]
                    idents.pop(k2, None)
                    depth_of.pop(k2, None)
                continue
            # join points end every run (a jump-in can skip the canon's
            # initialization); ctrl HEADS do not -- same-block textual
            # order is init order, and arm stores still kill below
            if self._LBLDEF_RX.match(s) or 'goto ' in s \
                    or s.startswith(('case ', 'default:', 'catch', 'finally')):
                avail = {}
                idents = {}
                depth_of = {}
                continue
            ms = mask(s)
            m = self._VAL_DECL_RX.match(s)
            tok = m.group(2) if m else None
            key = None
            # fix 96: a `new` allocation mints a fresh object identity on
            # every execution -- it is never a pure load, even
            # parameterless (`new T()` slips past _IMPURE: `>` is not in
            # its lead class and `new ` breaks word-paren adjacency, and
            # `new T[n]` has no parens at all). Caching one aliases
            # distinct objects (AudioVolumeSliders.Start's two
            # UnityAction<float> listeners folded into one).
            rhs3 = m.group(3) if m else ''
            if m and '?' not in rhs3 and ('.' in rhs3 or '[' in rhs3) \
                    and not re.match(r'new\s', rhs3) \
                    and not self._IMPURE.search(self._VAL_PURETYOF_RX.sub('', rhs3)):
                key = (m.group(1) or '', rhs3)
            if key is not None and n_assigns.get(tok, 0) == 1:
                hit = avail.get(key)
                if hit is not None and depth_of.get(hit, -1) <= depth:
                    alias[tok] = hit
                    drop.add(i)
                    continue
            # kills: stores / byrefs touching a cached entry's identifiers,
            # from ANY depth (a crossed arm's store must still kill)
            if avail:
                kills = {mm.group(1) for mm in self._VAL_KILL_ASSIGN_RX.finditer(ms)}
                kills |= {mm.group(1) for mm in self._VAL_KILL_BYREF_RX.finditer(ms)}
                if kills:
                    for k2 in [k2 for k2, iv in idents.items() if iv & kills]:
                        for kk in [kk for kk, vv in avail.items() if vv == k2]:
                            del avail[kk]
                        idents.pop(k2, None)
                        depth_of.pop(k2, None)
            if key is not None:
                avail[key] = tok
                depth_of[tok] = depth
                idents[tok] = {mm.group(0) for mm in re.finditer(r'[A-Za-z_]\w*', ms)}
        if not drop:
            return lines
        out = [st for i, st in enumerate(lines) if i not in drop]
        rx = re.compile(r'\b(%s)\b' % '|'.join(re.escape(t) for t in alias))
        return [rx.sub(lambda mm: alias.get(mm.group(1), mm.group(1)), st)
                for st in out]

    _SUB_DECL_TOK_RX = re.compile(r'^(num\d+|obj\d+|t\d+)$')
    _SUB_OP_RX = re.compile(r'[.\[?+\-*/%&|^><]')
    _SUB_NEW_RX = re.compile(r'(?<![\w.])new\s')
    _SUB_UNSTABLE_RX = re.compile(r'(?<![\w.])(?:flag\d+|real\d+|v\d+|s_[0-9a-fA-F]+)(?![\w])')

    def _sub_split_ternary(self, frag):
        """Split the first `cond ? a : b` at its own nesting depth, or
        None when the shape is not exactly that (nested/missing colons
        decline; `??`, `?.` and quoted text never reach here -- the caller
        filters them first). Depth is relative: real ternaries sit inside
        grouping parens (`(T) - 1`), so absolute depth-0 matching would
        miss every one. Parts may carry unbalanced parens; purity checks
        do not care, and rewrites are literal text swaps."""
        n = len(frag)
        depth = 0
        q = -1
        dq = 0
        i = 0
        while i < n:
            c = frag[i]
            if c in '([{':
                depth += 1
            elif c in ')]}':
                depth -= 1
            elif c == '?':
                q = i
                dq = depth
                break
            i += 1
        if q < 0:
            return None
        depth = dq
        for j in range(q + 1, n):
            c = frag[j]
            if c in '([{':
                depth += 1
            elif c in ')]}':
                depth -= 1
            elif c == ':' and depth == dq and frag[j + 1:j + 2] != ':':
                return (frag[:q], frag[q + 1:j], frag[j + 1:])
        return None

    def _sub_pure(self, frag):
        """True when `frag` is a reusable pure computation: the exact
        `_value_cse` purity test (`_IMPURE` over the typeof-carved text),
        plus no allocation identity (`new`), no lambdas, no quoted text,
        no `??`/`?.`, and at least one member/index/ternary/arithmetic
        operator (bare-token copies stay in `_copy_prop`'s domain). A `?`
        must split as a well-formed ternary; unstable namespaces
        (bool/float bit-temps, phi `v`-temps, stack homes) decline --
        their passes own them. All checks run on the whole fragment:
        impurity anywhere (even inside one ternary arm) declines the
        whole seed."""
        if not frag:
            return False
        if '"' in frag or "'" in frag or '=>' in frag:
            return False
        if re.search(r'\?\?|\?\.', frag):
            return False
        if self._SUB_NEW_RX.search(frag):
            return False
        if self._IMPURE.search(self._VAL_PURETYOF_RX.sub('', frag)):
            return False
        if self._SUB_UNSTABLE_RX.search(frag):
            return False
        if '?' in frag and self._sub_split_ternary(frag) is None:
            return False
        if not self._SUB_OP_RX.search(frag):
            return False
        return True

    def _sub_code_spans(self, line):
        """(start, end) code spans of `line`: string literals cut out via
        the literal split and `//` tails cut per segment, so a rewrite
        can never land inside either. Block comments are refused by the
        caller when a match would overlap one."""
        spans = []
        parts = self._VAL_STRLIT_SPLIT.split(line)
        off = 0
        for k, p in enumerate(parts):
            if k % 2 == 0:
                cut = p.find('//')
                seg = p if cut < 0 else p[:cut]
                spans.append((off, off + len(seg)))
            off += len(p)
        return spans

    def _sub_comment_spans(self, line):
        spans = []
        i = 0
        n = len(line)
        while True:
            j = line.find('/*', i)
            if j < 0:
                break
            k = line.find('*/', j + 2)
            if k < 0:
                spans.append((j, n))
                break
            spans.append((j, k + 2))
            i = k + 2
        return spans

    def _sub_replace_seg(self, seg, frag, tok):
        """First whole-token occurrence of `frag` in one code segment.
        A match extended by an identifier char on the right is a longer
        name, not this value; a match preceded by an identifier char, `.`
        or `>` is a member suffix, not this value (same discipline as
        `_bind_replace`). Member access, calls, indexing and operators
        ON the value still fold. One redundant paren layer left around
        the bare temp strips: temps are atoms, grouping proves nothing.
        Returns (new_seg, hit)."""
        j = seg.find(frag)
        if j < 0:
            return seg, False
        n = len(frag)
        before = seg[j - 1] if j > 0 else ''
        after = seg[j + n] if j + n < len(seg) else ''
        if (before and (before.isalnum() or before in '_.>$')) \
                or (after and (after.isalnum() or after == '_')):
            return seg, False
        new = seg[:j] + tok + seg[j + n:]
        pre = j - 1
        post = j + len(tok)
        # only a grouping paren may go: a call/type/index context
        # (`name(tok)`, `C<T>(tok)`, `a[i](tok)`, `sub_X/*c*/(tok)`)
        # needs its parens to stay a call, while nested grouping
        # (`f((tok))`) still folds.
        if pre >= 0 and post < len(new) and new[pre] == '(' and new[post] == ')' \
                and not (pre > 0 and (new[pre - 1].isalnum() or new[pre - 1] in '_.>]/$')):
            return new[:pre] + tok + new[post + 1:], True
        return new, True

    def _subexpr_cse(self, lines: List[str]) -> List[str]:
        """Nested pure-subexpression reuse (blocker 4: power-of-two fill).
        `_value_cse` folds only whole-RHS duplicate decls of `obj/t`
        temps and declines `?`; the lifter binds per expression object,
        so two executions of one pure text never share a temp. This pass
        closes exactly that gap for pure subexpressions: an anchor decl
        (`num`/`obj`/`t` temp, single-assigned, pure RHS) lends its token
        to later occurrences of its RHS text inside other decl RHSs
        (`num3 = num2 | num2 >> 16` instead of re-expanding `T-1`).
        Soundness mirrors the strictest existing passes: depth-scoped
        anchors (like `_value_cse`), full reset on labels/gotos/case/
        catch/finally plus return/throw/break/continue (like `_copy_prop`),
        store/byref kills from any depth, no use across loop frames or
        backward-goto spans (like `_drop_dead_lastdef`), single-assignment
        anchors never address-taken (like `_value_cse`), and the fix-58b
        invariant holds because call-shaped and `new` fragments can never
        seed (a second identical call is a second execution)."""
        for _ in range(4):
            n = len(lines)
            clean = [self._CMT_RX.sub('', _LIT_RX.sub('""', s.strip()))
                     for s in lines]
            in_loop = [False] * n
            frames = []
            last_ctrl = ''
            for i, s in enumerate(clean):
                in_loop[i] = any(frames)
                if s == '{':
                    frames.append(bool(self._LD_LOOP_RX.match(last_ctrl)))
                    in_loop[i] = any(frames)
                elif s.startswith('}'):
                    if frames:
                        frames.pop()
                last_ctrl = s
            label_at = {}
            for i, s in enumerate(clean):
                m = self._LD_LBL_RX.match(s)
                if m:
                    label_at.setdefault(m.group(1), i)
            back = [False] * n
            for j, s in enumerate(clean):
                for g in self._LD_GOTO_RX.finditer(s):
                    k = label_at.get(g.group(1))
                    if k is not None and k <= j:
                        for x in range(k, j + 1):
                            back[x] = True
            n_assigns = {}
            taken = set()
            for st in lines:
                ms = ''.join(p if k % 2 == 0 else ''
                             for k, p in enumerate(self._VAL_STRLIT_SPLIT.split(st.strip())))
                for mm in self._VAL_KILL_ASSIGN_RX.finditer(ms):
                    n_assigns[mm.group(1)] = n_assigns.get(mm.group(1), 0) + 1
                for mm in self._VAL_KILL_BYREF_RX.finditer(ms):
                    taken.add(mm.group(1))
            anchors = []
            anchor_at = {}
            depth = 0
            for i, st in enumerate(lines):
                s = st.strip()
                if s == '{':
                    depth += 1
                    continue
                if s == '}':
                    depth -= 1
                    continue
                m = self._LDEF_RX.match(s)
                if not m:
                    continue
                tok, rhs = m.group(1), m.group(2)
                if not self._SUB_DECL_TOK_RX.match(tok):
                    continue
                if n_assigns.get(tok, 0) != 1 or tok in taken:
                    continue
                if not self._sub_pure(rhs):
                    continue
                idents = {mm.group(0) for mm in re.finditer(r'[A-Za-z_]\w*', rhs)}
                anchors.append((i, tok, rhs, idents, depth))
                anchor_at[i] = len(anchors) - 1
            if not anchors:
                return lines
            avail = []
            depth = 0
            changed = False
            for i, st in enumerate(lines):
                s = st.strip()
                if s == '{':
                    depth += 1
                    continue
                if s == '}':
                    depth -= 1
                    avail = [a for a in avail if a[4] <= depth]
                    continue
                if self._LBLDEF_RX.match(s) or 'goto ' in s \
                        or s.startswith(('case ', 'default:', 'catch', 'finally')) \
                        or self._CP_BREAK_RX.match(s):
                    avail = []
                    continue
                ms = ''.join(p if k % 2 == 0 else ''
                             for k, p in enumerate(self._VAL_STRLIT_SPLIT.split(s)))
                kills = {mm.group(1) for mm in self._VAL_KILL_ASSIGN_RX.finditer(ms)}
                kills |= {mm.group(1) for mm in self._VAL_KILL_BYREF_RX.finditer(ms)}
                if kills:
                    avail = [a for a in avail if not (a[3] & kills)]
                if i in anchor_at:
                    avail.append(anchors[anchor_at[i]])
                m = self._LDEF_RX.match(s)
                if not m or not self._SUB_DECL_TOK_RX.match(m.group(1)):
                    continue
                for a_idx, a_tok, a_frag, a_id, a_dep in sorted(
                        [a for a in avail if a[0] < i and not in_loop[a[0]]
                         and not in_loop[i] and not back[a[0]] and not back[i]],
                        key=lambda a: -len(a[2])):
                    if a_tok == m.group(1):
                        continue
                    spans = self._sub_code_spans(st)
                    cspans = self._sub_comment_spans(st)
                    done = False
                    for b, e in spans:
                        seg = st[b:e]
                        if a_frag not in seg:
                            continue
                        new_seg, hit = self._sub_replace_seg(seg, a_frag, a_tok)
                        if not hit:
                            continue
                        j = seg.find(a_frag)
                        if any(j + b < ce and j + b + len(a_frag) > cb for cb, ce in cspans):
                            continue
                        lines[i] = st[:b] + new_seg + st[e:]
                        changed = True
                        done = True
                        break
                    if done:
                        break
            if not changed:
                return lines
        return lines

    # ------------------------------------------------------------------
    _ENTER_RX = re.compile(r'^System\.Threading\.Monitor\.Enter\((.+), (&[\w.]+)\);$')
    _EXIT_RX = re.compile(r'^System\.Threading\.Monitor\.Exit\((.+)\);$')
    _LBLDEF_RX = re.compile(r'^L_[0-9a-fA-F]+:$')
    _GOTO_RX = re.compile(r'goto (L_[0-9a-fA-F]+)')
