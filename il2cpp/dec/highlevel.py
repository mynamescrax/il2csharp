from il2cpp.prelude import *  # noqa: F401,F403
from il2cpp.cfg import INT_TY, _match_brace
from il2cpp.csharp import FA_LITERAL, FA_STATIC, field_attrs
from il2cpp.metadata import MethodDef
from il2cpp.names import safe_ident
from il2cpp.stmt_text import _split_top
from il2cpp.text import mask_literals
from il2cpp.expr import _mentions

class _HighLevelMixin:
    def _jumps_into(self, lines, lo, hi) -> bool:
        """Any goto outside [lo, hi) targets a label inside the span."""
        inner = {m.group(1) for k in range(lo, min(hi, len(lines)))
                 for m in self._GOTO_RX.finditer(lines[k])}
        labels = {lines[k].strip()[:-1] for k in range(lo, min(hi, len(lines)))
                  if self._LBLDEF_RX.match(lines[k].strip())}
        for k, st in enumerate(lines):
            if lo <= k < hi:
                continue
            for m in self._GOTO_RX.finditer(st):
                if m.group(1) in labels and m.group(1) not in inner:
                    return True
        return False

    def _redundant_else(self, lines: List[str]) -> List[str]:
        """Drop an `else` arm's keyword when the if-arm provably ends
        in an unconditional flow-break (return/throw/goto/break/
        continue): control never falls past the then-arm, so the
        else-arm is plain fall-through. Its braces splice out with the
        keyword (no bare-block nesting); that cannot reassociate any
        inner else -- the inner token sequence is unchanged, and a
        dangling else after the splice would have dangled before it
        too. Brace matching counts only lines that ARE braces (the
        _seq shapes), so braces inside string literals on statement
        lines cannot skew depth. fix 41; 1,054 sites at b37_out1."""
        out = list(lines)
        while True:
            n = len(out)
            fold = None
            for i in range(n):
                if out[i].strip() != 'else':
                    continue
                j = i - 1
                while j >= 0 and not out[j].strip():
                    j -= 1
                if j < 0 or out[j].strip() != '}':
                    continue
                depth = 0
                openk = -1
                k = j
                while k >= 0:
                    t = out[k].strip()
                    if t == '}' or t.startswith('} while'):
                        depth += 1
                    elif t == '{':
                        depth -= 1
                        if depth == 0:
                            openk = k
                            break
                    k -= 1
                if openk < 1:
                    continue
                last = ''
                for q in range(j - 1, openk, -1):
                    if out[q].strip():
                        last = out[q].strip()
                        break
                if not last.startswith(('return', 'throw', 'goto ',
                                        'break;', 'continue;')):
                    continue
                nxt = i + 1
                while nxt < n and not out[nxt].strip():
                    nxt += 1
                if nxt < n and out[nxt].strip() == '{':
                    c = _match_brace(out, nxt)
                    if c is None or c < 0:
                        continue
                    fold = (i, nxt, c)
                else:
                    fold = (i,)
                break
            if fold is None:
                return out
            drop = set(fold)
            out = [ln for x, ln in enumerate(out) if x not in drop]

    def _lock_sugar(self, lines: List[str]) -> List[str]:
        """lock (obj) { ... } for the compiled Monitor shape: Enter(obj,
        &taken) ... if (taken != 0) { Exit(obj); }. MSVC duplicates the
        finally guard on every exit path, so a lock region collects every
        guard up to the next Enter of the same flag; the duplicated guards
        vanish inside the lock (Exit is implicit) and the last one closes
        the block."""
        out = list(lines)
        for _ in range(8):
            # segment: each Enter owns the guards up to the next Enter
            enters = []
            for i, st in enumerate(out):
                m = self._ENTER_RX.match(st.strip())
                if m:
                    enters.append((i, m.group(1).strip(), m.group(2)[1:]))
            hit = None
            for e, (i, obj, flag) in enumerate(enters):
                stop = enters[e + 1][0] if e + 1 < len(enters) else len(out)
                guards = []
                for k in range(i + 1, min(stop, len(out) - 3)):
                    if out[k].strip() not in ('if (%s != 0)' % flag,
                                              'if (!(%s == 0))' % flag):
                        continue
                    em = self._EXIT_RX.match(out[k + 2].strip()) \
                        if out[k + 1].strip() == '{' else None
                    if em and self._norm_obj(em.group(1)) == obj \
                            and out[k + 3].strip() == '}':
                        guards.append(k)
                if guards and stop - i < 400:
                    hit = (i, guards, obj)
                    break
            if hit is None:
                return out
            i, guards, obj = hit
            last = guards[-1]
            body = out[i + 1:last]
            for g in reversed(guards[:-1]):
                # drop each duplicated finally guard (4 balanced lines)
                body = [s for j, s in enumerate(body) if not (g - i - 1 <= j < g - i + 3)]
            out = out[:i] + ['lock (%s)' % obj, '{'] + body + ['}'] + out[last + 4:]
        return out

    @staticmethod
    def _norm_obj(s: str) -> str:
        return re.sub(r'^\*\((&?[\w.]+) \+ 0x0\)$', r'\1', s.strip())

    # ------------------------------------------------------------------
    _GUARD_HDR_RX = re.compile(r'^if \(([\w.]+) != null\)$')
    _GUARD_HDR2_RX = re.compile(r'^if \(!\(([\w.]+) == null\)\)$')
    _DISPOSE_RX = re.compile(r'^([\w.]+)\.Dispose\(\);$')
    _NEWDECL_RX = re.compile(r'^[\w.<>\[\],` ]+? ([\w.]+) = (new .+);$')

    _CASTDISP_RX = re.compile(r'^sub_\w+\(0, typeof\(System\.IDisposable\), (.+?), ')
    _HDRDREF_RX = re.compile(r'^\*\((&?[\w.\[\]]+) \+ 0x0\)$')
    _NEZERO_RX = re.compile(r'^if \((.+) != 0\)$')
    _NEZERO2_RX = re.compile(r'^if \(!\((.+) == 0\)\)$')
    _EZERO_RX = re.compile(r'^if \((.+) == 0\)$')

    @staticmethod
    def _match_brace(st: List[str], open_idx: int):
        """Index of the line closing the brace opened at open_idx ('{')."""
        d = 0
        for k in range(open_idx, len(st)):
            d += st[k].count('{') - st[k].count('}')
            if k > open_idx and d <= 0:
                return k
        return None

    def _dispose_guard_recv(self, fin: List[str]):
        """The disposable X for a dispose guard of either orientation --
        `if (R != 0) { cast(IDisposable, R); ... }` or `if (R == 0) { }
        else { cast(...); ... }` -- where R is X or its header deref
        `*(X + 0x0)` / `*(&X + 0x0)`. None for anything else.
        Returns (X, dup temps)."""
        if len(fin) < 4 or fin[1] != '{':
            return None
        m = self._NEZERO_RX.match(fin[0]) or self._NEZERO2_RX.match(fin[0])
        if m:
            if '}' not in fin[2:]:
                return None
            close = fin.index('}', 2)
            if close + 1 != len(fin):
                return None
            inner = fin[2:close]
            cond_r = m.group(1)
        else:
            m2 = self._EZERO_RX.match(fin[0])
            if not (m2 and len(fin) >= 6 and fin[2] == '}' and fin[3] == 'else'
                    and fin[4] == '{'):
                return None
            close = fin.index('}', 5)
            if close + 1 != len(fin):
                return None
            inner = fin[5:close]
            cond_r = m2.group(1)
        cm = self._CASTDISP_RX.match(inner[0]) if inner else None
        if not cm:
            return None
        dups = []
        for b in inner[1:]:
            if self._CASTDISP_RX.match(b):
                continue
            dm2 = re.match(r'^([\w.]+) = sub_\w+\(', b)
            if dm2:
                dups.append(dm2.group(1))
                continue
            if b.startswith('goto '):
                continue
            return None

        def base(r: str) -> str:
            hm = self._HDRDREF_RX.match(r.strip())
            return (hm.group(1) if hm else r.strip()).lstrip('&')

        x = base(cm.group(1))
        if base(cond_r) != x:
            return None
        return x, dups

    def _using_fold(self, lines, st, i, fb, x):
        """For a finally at i closing at fb with disposable x: fold the
        enclosing `T x = new ...; try { B } finally { dispose }` into
        `using (x) { B }`. The raw braces may drift unbalanced inside the
        try body, so the try span is located tolerantly (nearest `}`
        above the finally, nearest `try {` above that)."""
        j = i - 1
        while j >= 0 and not st[j]:
            j -= 1
        if j < 0 or st[j] != '}':
            return None
        tb = j
        k = tb - 1
        tri = None
        while k > 0:
            if st[k] == 'finally':
                return None
            if st[k] == '{' and st[k - 1] == 'try':
                tri = k - 1
                break
            k -= 1
        if tri is None:
            return None
        dm = self._NEWDECL_RX.match(st[tri - 1]) if tri > 0 else None
        reass = any(re.match(r'^%s = ' % re.escape(x), b) for b in st[tri + 2:tb])
        if not (dm and dm.group(1) == x) or reass:
            return None
        if self._jumps_into(lines, tri + 2, fb):
            return None
        seg = ['using (%s)' % x, '{'] + lines[tri + 2:tb] + ['}']
        return lines[:tri] + seg + lines[fb + 1:]

    def _using_pass(self, lines: List[str]) -> List[str]:
        st = [s.strip() for s in lines]
        n = len(lines)
        i = 0
        while i < n:
            if st[i] == 'finally' and i + 1 < n and st[i + 1] == '{':
                fb = self._match_brace(st, i + 1)
                if fb is not None:
                    g = self._dispose_guard_recv(st[i + 2:fb])
                    if g is not None:
                        x, dups = g
                        dup_live = any(
                            re.search(r'(?<![\w.])%s(?![\w])' % re.escape(d), s2)
                            for d in dups for s2 in st[:i] + st[fb + 1:])
                        if not dup_live:
                            fold = self._using_fold(lines, st, i, fb, x)
                            if fold is not None:
                                return fold
                            return lines[:i + 1] + ['{', '%s?.Dispose();' % x, '}'] \
                                + lines[fb + 1:]
            # bare in-body guard: if (R != 0) { cast(R); [dup;] } -> X?.Dispose();
            if st[i].startswith('if (') and i + 1 < n and st[i + 1] == '{' \
                    and '}' not in st[i]:
                cb = self._match_brace(st, i + 1)
                if cb is not None:
                    g = self._dispose_guard_recv(st[i:cb + 1])
                    if g is not None:
                        x, dups = g
                        dup_live = any(
                            re.search(r'(?<![\w.])%s(?![\w])' % re.escape(d), s2)
                            for d in dups for s2 in st[:i] + st[cb + 1:])
                        if not dup_live:
                            return lines[:i] + ['%s?.Dispose();' % x] + lines[cb + 1:]
            i += 1
        return lines

    def _using_sugar(self, lines: List[str]) -> List[str]:
        """using (x) { ... } for the compiled finally-dispose guard. The
        finally renders as `if (R != 0) { cast(IDisposable, R); ... }`
        with R the disposable (possibly through its header deref). The
        guard simplifies to `x?.Dispose();`, and a directly preceding
        `T x = new ...;` folds the whole try/finally into `using (x)`.
        The fixpoint folds nested usings inside-out."""
        for _ in range(12):
            new = self._using_pass(lines)
            if new == lines:
                return lines
            lines = new
        return lines

    # ------------------------------------------------------------------
    _ASGN_RX = re.compile(r'^(.+?) = (.*);$')
    _NULLCOND_RX = re.compile(r'^([\w.]+) != null$')
    _NULLCOND2_RX = re.compile(r'^!\(([\w.]+) == null\)$')

    @classmethod
    def _null_test_var(cls, cond: str):
        """X for `X != null` / `!(X == null)`, else None."""
        m = cls._NULLCOND_RX.match(cond) or cls._NULLCOND2_RX.match(cond)
        return m.group(1) if m else None

    def _ternary(self, lines: List[str]) -> List[str]:
        """Fixpoint: else-if chains fold bottom-up, each round turning one
        more single-assignment if/else into a ?: expression."""
        for _ in range(6):
            new = self._ternary_pass(lines)
            if new == lines:
                return lines
            lines = new
        return lines

    @staticmethod
    def _ternary_stripped(text):
        """Outer whitespace and wrapping parens off; the wrapper must own
        its parens (balanced inside), so `(0)` strips but `(f(0)` never
        matches. Used by the ternary bool-arm reconciliation."""
        t = (text or '').strip()
        while len(t) >= 2 and t.startswith('(') and t.endswith(')'):
            inner = t[1:-1]
            depth = 0
            ok = True
            for c in inner:
                if c == '(':
                    depth += 1
                elif c == ')':
                    depth -= 1
                    if depth < 0:
                        ok = False
                        break
            if not ok or depth != 0:
                break
            t = inner.strip()
        return t

    def _ternary_arm_is_bool(self, other, lines):
        """True when a non-literal ternary arm is proved bool: a `flagN`
        token (the rename stamps the te == 0x02 proof into the name --
        flagN locals are bool by construction), a token still carrying
        its pre-rename te == 0x02 entry in `_var_types` (the lifter
        `_fimm` proof family: 0/1 into a bool location is false/true),
        or an expression whose identical text a `bool` declaration holds
        elsewhere in this method (same text over scope-rooted names --
        `this`/fields, no rename locals a sibling scope could redeclare
        -- so the static type agrees; that sibling `bool` itself came
        from `_var_types` tracking)."""
        o = (other or '').strip()
        if not o:
            return False
        if re.fullmatch(r'flag\d+', o):
            return True
        ty = getattr(self, '_var_types', {}).get(o)
        if isinstance(ty, tuple) and len(ty) > 1 \
                and ((ty[1] >> 16) & 0xFF) == 0x02:
            return True
        if re.search(r'(?<![\w.])(?:obj\d+|num\d+|flag\d+|real\d+'
                     r'|[vst]\d+|s_[0-9a-fA-F]+)(?![\w])', o):
            return False
        for ln in lines:
            s = ln.strip()
            m = re.match(r'^bool\s+[\w.]+\s*(?<![=!<>])=(?![=>])\s*'
                         r'(.*?);\s*$', s)
            if m and self._ternary_stripped(m.group(1)) == o:
                return True
        return False

    def _ternary_pass(self, lines: List[str]) -> List[str]:
        """`if (c) { x = a; } else { x = b; }` -> `x = c ? a : b;` -- when
        both arms are a single assignment to the same lvalue. Each arm's
        assignment only ever executed under its condition, so folding
        preserves the evaluation order. A null else-arm over `x != null`
        becomes the null-conditional `x?.member` form."""
        out: List[str] = []
        i = 0
        n = len(lines)
        while i < n:
            s = lines[i].strip()
            if s.startswith('if (') and s.endswith(')') \
                    and i + 8 <= n and lines[i + 1].strip() == '{' \
                    and lines[i + 3].strip() == '}' \
                    and lines[i + 4].strip() == 'else' \
                    and lines[i + 5].strip() == '{' \
                    and lines[i + 7].strip() == '}':
                m1 = self._ASGN_RX.match(lines[i + 2].strip())
                m2 = self._ASGN_RX.match(lines[i + 6].strip())
                # fix 97: either arm may carry its declaration (`bool x`
                # vs `x`) now that first-use bare assignments declare.
                # Compare the temp, keep the declaration. `var` keeps
                # the old exact-match behavior.
                lvs = []
                for mm in (m1, m2):
                    if mm is None:
                        lvs = None
                        break
                    tm = re.fullmatch(r'(?!var\b)[A-Za-z_][\w.<>\[\]]*\s+'
                                      r'(obj\d+|num\d+|real\d+|flag\d+)', mm.group(1))
                    key = tm.group(1) if tm else mm.group(1)
                    lvs.append((mm.group(1), key, tm is not None))
                if lvs is not None and lvs[0][1] == lvs[1][1] \
                        and '&&' not in m1.group(1) and '=' not in m1.group(1)[1:] \
                        and '?' not in lines[i]:
                    lv = lvs[0][0] if lvs[0][2] or not lvs[1][2] else lvs[1][0]
                    cond = s[3:].strip()
                    if cond.startswith('(') and cond.endswith(')'):
                        cond = cond[1:-1]
                    cm = self._null_test_var(cond)
                    if cm and m2.group(2).strip() == 'null' \
                            and m1.group(2).startswith(cm + '.'):
                        out.append('%s%s = %s?.%s;' % (
                            lines[i][:len(lines[i]) - len(lines[i].lstrip())],
                            lv, cm, m1.group(2)[len(cm) + 1:]))
                        i += 8
                        continue
                    rhs_a, rhs_b = m1.group(2), m2.group(2)
                    sa = self._ternary_stripped(rhs_a)
                    sb = self._ternary_stripped(rhs_b)
                    # Bool-arm reconciliation: a phi-copy `0`/`1` arm never
                    # passes the lifter `_fimm`, so the fold keeps the int
                    # decl (`int num2 = c ? prop : 0`) and feeds 0/1 to bool
                    # params. When exactly one arm is the literal and the
                    # other is bool-proved, spell the literal `false`/`true`
                    # and take the `bool` declaration for the shared temp.
                    # The literal must be exactly `0`/`1`; anything else
                    # declines. Non-ternary statements never reach here.
                    if (sa in ('0', '1')) != (sb in ('0', '1')):
                        other = sb if sa in ('0', '1') else sa
                        if self._ternary_arm_is_bool(other, lines):
                            if sa in ('0', '1'):
                                rhs_a = 'true' if sa == '1' else 'false'
                            else:
                                rhs_b = 'true' if sb == '1' else 'false'
                            dm = re.match(r'^(.*\S)\s+([\w.]+)$', lv)
                            if dm and dm.group(1) != 'bool':
                                lv = 'bool %s' % dm.group(2)
                    out.append('%s%s = %s ? %s : %s;' % (
                        lines[i][:len(lines[i]) - len(lines[i].lstrip())],
                        lv, cond, rhs_a, rhs_b))
                    i += 8
                    continue
            out.append(lines[i])
            i += 1
        return self._bool_materialization_pass(out)

    _TERNMAT_RX = re.compile(r'^([A-Za-z_][\w.]*) = \((.*)\)\s*;$')

    @staticmethod
    def _ternmat_split(inner):
        depth = 0
        qi = None
        for n, c in enumerate(inner):
            if c in ('"', "'"):
                return None
            if c == '(':
                depth += 1
            elif c == ')':
                depth -= 1
            elif depth == 0 and c == '?':
                qi = n
                break
        if qi is None:
            return None
        cond, rest = inner[:qi], inner[qi + 1:]
        depth = 0
        for n, c in enumerate(rest):
            if c == '(':
                depth += 1
            elif c == ')':
                depth -= 1
            elif depth == 0 and c == ':':
                return cond, rest[:n], rest[n + 1:]
        return None

    def _bool_cond_proved(self, cond, lines):
        c = self._ternary_stripped(cond)
        if not c or re.search(r'(?<![=!<>])=(?![=>])', c):
            return False
        if c.startswith('!'):
            return True
        if re.search(r'\bis\b|&&|\|\||(?<![=!<>+\-*/%&|^])(?:<=|>=|==|!=|<|>)(?![=>])', c):
            return True
        return self._ternary_arm_is_bool(c, lines)

    def _bool_use_ok(self, line, tok, lines):
        for m in re.finditer(r'(?<![\w.])' + re.escape(tok) + r'(?![\w])', line):
            before, after = line[:m.start()], line[m.end():]
            if re.search(r'!\s*$', before):
                continue
            if re.search(r'==\s*(true|false)\s*$', after) or re.search(r'!=\s*(true|false)\s*$', after):
                continue
            bm = re.search(r'([\w.]+)\s*([&|]{1,2})\s*$', before)
            am = re.match(r'\s*([&|]{1,2})\s*([\w.]+)', after)
            other = None
            if bm:
                other = bm.group(1)
            elif am:
                other = am.group(2)
            if other is not None and (re.fullmatch(r'flag\d+', other) or self._ternary_arm_is_bool(other, lines)):
                continue
            return False
        return True

    def _bool_materialization_pass(self, lines):
        out = list(lines)
        for i, st in enumerate(out):
            s = st.strip()
            m = self._TERNMAT_RX.match(s)
            if m is None:
                continue
            tok, inner = m.group(1), m.group(2)
            if '.' in tok:
                continue
            sp = self._ternmat_split(inner)
            if sp is None:
                continue
            cond, arm_a, arm_b = sp
            sa, sb = self._ternary_stripped(arm_a), self._ternary_stripped(arm_b)
            if {sa, sb} != {'0', '1'}:
                continue
            if not self._bool_cond_proved(cond, out):
                continue
            ind = st[:len(st) - len(st.lstrip())]
            new_rhs = cond.strip() if sa == '1' else '!(%s)' % cond.strip()
            decl_idx, decl_ty = None, None
            for j, ln in enumerate(out):
                if j == i:
                    continue
                dm = re.match(r'^(int|bool)\s+' + re.escape(tok) + r'\s*(=.*?)?;\s*$', ln.strip())
                if dm:
                    if decl_idx is not None:
                        decl_idx = -1
                        break
                    decl_idx, decl_ty = j, dm.group(1)
                    if dm.group(2) is not None and self._ternary_stripped(dm.group(2)[1:]) not in ('0', '1'):
                        decl_idx = -1
                        break
            if decl_idx is None or decl_idx < 0:
                continue
            ok = True
            for j, ln in enumerate(out):
                if j == i or j == decl_idx:
                    continue
                if not self._bool_use_ok(ln, tok, out):
                    ok = False
                    break
                if re.search(r'(?<![\w.])' + re.escape(tok) + r'\s*(?:[+\-*/%&|^]|<<|>>)?=(?![=>])', ln):
                    ok = False
                    break
            if not ok:
                continue
            if decl_ty == 'bool':
                out[i] = '%s%s = %s;' % (ind, tok, new_rhs)
                continue
            if decl_ty != 'int':
                continue
            dl = out[decl_idx]
            dind = dl[:len(dl) - len(dl.lstrip())]
            initm = re.match(r'^int\s+' + re.escape(tok) + r'\s*=\s*(.*?)\s*;\s*$', dl.strip())
            init_txt = 'false' if initm is None or self._ternary_stripped(initm.group(1)) == '0' else 'true'
            out[decl_idx] = '%sbool %s = %s;' % (dind, tok, init_txt)
            out[i] = '%s%s = %s;' % (ind, tok, new_rhs)
        return out

    # ------------------------------------------------------------------
    def _null_conditional(self, lines: List[str]) -> List[str]:
        """`if (x != null) { x.M(...); }` -> `x?.M(...);` when the guarded
        body is a single statement rooted at the tested object."""
        out: List[str] = []
        i = 0
        n = len(lines)
        while i < n:
            s = lines[i].strip()
            m = self._null_test_var(s[4:-1].strip()) if s.startswith('if (') and s.endswith(')') else None
            if m and i + 3 < n and lines[i + 1].strip() == '{' \
                    and lines[i + 3].strip() == '}':
                st = lines[i + 2].strip()
                if st.startswith(m + '.') and not re.match(
                        r'[\w.\[\]<>]+\s*(?:[+\-*/%&|^]|\?\?)?\s*=', st[len(m) + 1:]):
                    out.append(lines[i][:len(lines[i]) - len(lines[i].lstrip())]
                               + st[:len(m)] + '?.' + st[len(m) + 1:])
                    i += 4
                    continue
            # inverted shape: if (x == null) { } else { x.M(); }
            m2 = re.match(r'^([\w.]+) == null$', s[4:-1].strip()) if s.startswith('if (') and s.endswith(')') else None
            if m2 and i + 7 < n and lines[i + 1].strip() == '{' \
                    and lines[i + 2].strip() == '}' and lines[i + 3].strip() == 'else' \
                    and lines[i + 4].strip() == '{' and lines[i + 6].strip() == '}':
                st = lines[i + 5].strip()
                if st.startswith(m2.group(1) + '.') and not re.match(
                        r'[\w.\[\]<>]+\s*(?:[+\-*/%&|^]|\?\?)?\s*=', st[len(m2.group(1)) + 1:]):
                    out.append(lines[i][:len(lines[i]) - len(lines[i].lstrip())]
                               + st[:len(m2.group(1))] + '?.' + st[len(m2.group(1)) + 1:])
                    i += 7
                    continue
            out.append(lines[i])
            i += 1
        return out

    # ------------------------------------------------------------------
    _NULLTERN_RX = re.compile(
        r'^((?:[A-Za-z_][\w.]*(?:<[^=]*?>)?(?:\[\d*\])*(?:\* )?) )?'      # decl type
        r'([\w.\[\]]+) = (\()?([\w.\[\]]+) (==|!=) null(\))? \? ([^;]+) : ([^;]+);$')

    def _null_ternary_sugar(self, lines: List[str]) -> List[str]:
        """`obj == null ? null : obj.Member` (either orientation) renders as
        `obj?.Member`; `obj != null ? obj : fallback` (either orientation)
        renders as `obj ?? fallback`. A `0` arm is the mislifted null
        constant and folds like `null`; the member arm must root at the
        tested object so swapped-arm shapes never match."""
        out = []
        for raw in lines:
            s = raw.strip()
            m = self._NULLTERN_RX.match(s)
            if not m:
                out.append(raw)
                continue
            pre, lv, popen, t, op, pclose, a, b = m.groups()
            a = a.strip()
            b = b.strip()
            # a bare integer literal can never be null -- a textual
            # `1 != null` match (AnimationCurve.cs:571) is not a real
            # nullable check; leave the honest original text alone
            # rather than synthesize `??`/`?.` sugar over it.
            if t.lstrip('-').isdigit():
                out.append(raw)
                continue
            # the condition can be parenthesized alone (`(t == null)`,
            # popen+pclose both present) or bare (neither); but the
            # WHOLE ternary can also be the parenthesized part (`(t ==
            # null ? a : b)` -- popen present, pclose absent), and the
            # closing paren that actually matches popen is then the one
            # `b`'s greedy capture just swallowed off the tail. Strip it
            # back off so the synthesized text stays balanced -- this is
            # exactly how `num1 = 1 ?? 0);` (dangling `)`) shipped.
            if popen and not pclose:
                if not b.endswith(')'):
                    out.append(raw)
                    continue
                b = b[:-1].rstrip()
            if '?' in lv or '?' in a or '?' in b:
                out.append(raw)
                continue
            ind = raw[:len(raw) - len(raw.lstrip())]
            hit = None
            if op == '==':
                if a in ('null', '0') and b.startswith(t + '.'):
                    hit = '%s?.%s' % (t, b[len(t) + 1:])
                elif b == t:
                    hit = '%s ?? %s' % (t, a)
            else:
                if b in ('null', '0') and a.startswith(t + '.'):
                    hit = '%s?.%s' % (t, a[len(t) + 1:])
                elif a == t:
                    hit = '%s ?? %s' % (t, b)
            if hit is None:
                out.append(raw)
            else:
                out.append('%s%s%s = %s;' % (ind, (pre or ''), lv, hit))
        return out

    # ------------------------------------------------------------------
    _SWHDR_RX = re.compile(r'^switch \((.+)\)$')
    _CASE_RX = re.compile(r'^case (-?\d+):$')

    def _switch_to_if(self, lines: List[str]) -> List[str]:
        """A switch with at most two case labels is an if/else-if: the jump
        table compiled away exactly that shape. Section-final `break;`
        statements belong to the switch, not to a loop, and are dropped."""
        out: List[str] = []
        i = 0
        n = len(lines)
        while i < n:
            m = self._SWHDR_RX.match(lines[i].strip())
            if not (m and i + 1 < n and lines[i + 1].strip() == '{'):
                out.append(lines[i])
                i += 1
                continue
            idx = m.group(1)
            j = i + 2
            groups: List[Tuple[List[int], int, int]] = []  # (labels, body_start, body_end)
            labels: List[int] = []
            ok = True
            while j < n:
                cs = lines[j].strip()
                cm = self._CASE_RX.match(cs)
                if cm:
                    labels.append(int(cm.group(1)))
                    j += 1
                    continue
                if cs == '{':
                    d = 1
                    k = j + 1
                    while k < n and d:
                        t = lines[k].strip()
                        d += t.count('{') - t.count('}')
                        k += 1
                    if d:
                        ok = False
                        break
                    groups.append((labels, j, k))   # body is lines[j+1:k-1]
                    labels = []
                    j = k
                    continue
                if cs == '}':
                    j += 1
                    break
                ok = False
                break
            flat = [L for g in groups for L in g[0]]
            if not ok or len(groups) < 1 or len(flat) > 2:
                out.append(lines[i])
                i += 1
                continue
            indent = lines[i][:len(lines[i]) - len(lines[i].lstrip())]
            for gi, (labs, bs, be) in enumerate(groups):
                cond = ' || '.join('%s == %d' % (idx, L) for L in labs)
                out.append('%s%s (%s)' % (indent, 'if' if gi == 0 else 'else if', cond))
                out.append(indent + '{')
                body = lines[bs + 1:be - 1]
                if body and body[-1].strip() == 'break;':
                    body = body[:-1]
                out.extend(body)
                out.append(indent + '}')
            i = j
        return out
    _INC_RX = re.compile(r'^(v\d+) = \(?\1 ([+-]) (\d+)\)?;$')
    _LEN_RX = re.compile(r'(?<![\w.])(\w+) (<|>=) \*\((.+?) \+ 0x18\)')

    def _len_sugar(self, cond: str) -> str:
        """`i < *(a + 0x18)` is an array-length test (+0x18 is
        Il2CppArray::max_length) -- unless the receiver is a List<T>,
        whose +0x18 is _size, i.e. Count."""
        def rep(m):
            recv = m.group(3)
            ty = self._var_types.get(recv)
            if ty is not None:
                try:
                    tn = self.L.il.type_name(ty)
                except Exception:
                    tn = ''
                if '.List_1<' in tn or tn.startswith('List_1<'):
                    return '%s %s %s.Count' % (m.group(1), m.group(2), recv)
            return '%s %s %s.Length' % (m.group(1), m.group(2), recv)
        masked, _ = self._mask_literals(cond, False)
        return self._sub_outside_literals(self._LEN_RX, rep, cond, masked)

    _NATIVELEN_RX = re.compile(r'(?:\(\(byte\*\)([\w.]+) \+ 0x28\)\[0\]|\*\(([\w.]+) \+ 0x28\))')

    def _native_count_sugar(self, text: str) -> str:
        """`((byte*)a + 0x28)[0]` is a native-list count load when the
        receiver is exactly Obi.ObiNativeContactList (count at +0x28).
        Anything else -- including untyped receivers -- keeps raw text."""
        def rep(m):
            recv = m.group(1) or m.group(2)
            ty = self._native_count_recv_ty(recv)
            if ty is not None:
                try:
                    tn = self.L.il.type_name(ty)
                except Exception:
                    tn = ''
                if tn == 'Obi.ObiNativeContactList':
                    return '%s.Count' % recv
            return m.group(0)
        return self._NATIVELEN_RX.sub(rep, text)

    def _native_count_recv_ty(self, recv):
        ty = self._var_types.get(recv)
        if ty is not None:
            return ty
        try:
            base, _, field = recv.partition('.')
            if base != 'this' or not field or '.' in field:
                return None
            td = getattr(self.L, '_current_td', None)
            chain = self.L.il.instance_field_chain(td.index)
            for _, (name, ti) in (chain or {}).items():
                if name == field:
                    return self.L.il.types[ti]
        except Exception:
            return None
        return None

    def _for_sugar(self, lines: List[str]) -> List[str]:
        """while + counter phi -> for. The increment is the phi copy on the back
        edge, the initial value the copy on the entry edge."""
        i = 0
        while i < len(lines):
            s = lines[i].strip()
            if not (s.startswith('while (') and s.endswith(')')) or s == 'while (true)':
                i += 1
                continue
            if i + 1 >= len(lines) or lines[i + 1].strip() != '{':
                i += 1
                continue
            close = _match_brace(lines, i + 1)
            if close < 0:
                i += 1
                continue
            cond = s[7:-1]
            found = self._find_increment(lines, i + 1, close, cond)
            if found is None:
                i += 1
                continue
            last, var, op, step = found
            # stepping by an integer constant makes this an integer counter
            self._var_types[var] = INT_TY
            init, init_idx = self._find_init(lines, i, var)
            if init == var:          # `i = i` carries nothing
                init, init_idx = None, None
            step_txt = ('%s++' % var) if (op == '+' and step == '1') else \
                       ('%s--' % var) if (op == '-' and step == '1') else \
                       ('%s %s= %s' % (var, op, step))
            decl = ''
            if init is not None and re.match(r'^-?(?:\d+|0[xX][0-9a-fA-F]+)$', init) \
                    and not self._used_outside(lines, i, close, var, init_idx):
                decl = 'int '
            head = '%s%s' % (decl, ('%s = %s' % (var, init)) if init is not None else '')
            cond = self._native_count_sugar(self._len_sugar(self._simplify_cond(cond)))
            lines[i] = 'for (%s; %s; %s)' % (head, cond, step_txt)
            del lines[last]
            if init_idx is not None:
                del lines[init_idx]
                i -= 1
            i += 1
        for i, st in enumerate(lines):
            t = st.strip()
            if t.startswith('if (') or t.startswith('while ('):
                lines[i] = self._native_count_sugar(self._len_sugar(st))
            elif '+ 0x28' in t:
                lines[i] = self._native_count_sugar(st)
        return lines


    _FHF_CALL_RX = re.compile(r'([\w.]+\([^()]*\))\.Length')
    _FHF_DECLHEAD_RX = re.compile(
        r'^[A-Za-z_][\w.<>\[\], ]*? ((?:obj\d+|num\d+|flag\d+|real\d+|v\d+|t\d+))$')
    _FHF_STOP_RX = re.compile(
        r'^(?:\{|\}|else\b|if\s*\(|while\s*\(|for\s*\(|foreach\s*\(|'
        r'switch\s*\(|case\b|default:|try\b|catch\b|finally\b|do\b|'
        r'return\b|break;|continue;|goto\b|L_[0-9a-fA-F]+:)')

    @staticmethod
    def _fhf_split(clauses):
        """split `init; cond; inc` on depth-0 semicolons, blind to the
        contents of string/char literals (a `; ` inside a tag string
        must not split the head)"""
        parts = []
        depth = 0
        cur = []
        i = 0
        L = len(clauses)
        while i < L:
            c = clauses[i]
            if c == '"' or c == "'":
                q = c
                cur.append(c)
                i += 1
                while i < L:
                    if clauses[i] == chr(92):
                        cur.append(clauses[i:i + 2])
                        i += 2
                        continue
                    cur.append(clauses[i])
                    if clauses[i] == q:
                        i += 1
                        break
                    i += 1
                continue
            if c == '(':
                depth += 1
            elif c == ')':
                depth -= 1
            elif c == ';' and depth == 0:
                parts.append(''.join(cur).strip())
                cur = []
                i += 1
                continue
            cur.append(c)
            i += 1
        parts.append(''.join(cur).strip())
        return parts

    def _fhf_holder(self, lines, i, call):
        """the token of the NEAREST preceding decl whose RHS is exactly
        `call`, same block (stops at any label/control head/brace/goto),
        <= 8 plain statements up, and nothing between stores to or
        takes by-ref the holder or any identifier the call reads"""
        suffix = '= %s;' % call
        window = []
        j = i - 1
        while j >= 0 and len(window) < 8:
            s = lines[j].strip()
            if not s:
                j -= 1
                continue
            if self._FHF_STOP_RX.match(s):
                break
            window.append((j, s))
            j -= 1
        for j, s in window:
            if not s.endswith(suffix):
                continue
            m = self._FHF_DECLHEAD_RX.match(
                s[:-len(suffix)].rstrip())
            if not m:
                continue
            tok = m.group(1)
            ids = set(re.findall(r'[A-Za-z_]\w*', call))
            ids.add(tok)
            ids.discard('this')
            for k, s2 in window:
                if k == j:
                    break
                t2 = self._CMT_RX.sub('', s2)
                for ident in ids:
                    ie = re.escape(ident)
                    if re.search(r'\b' + ie + r'\s*(?:[-+*/%&|^]|<<|>>)?=',
                                 t2) \
                            or re.search(r'&\s*' + ie + r'\b', t2) \
                            or re.search(r'\b(?:ref|out)\s+' + ie + r'\b',
                                         t2):
                        return None
            return tok
        return None

    def _forhead_call_fold(self, lines: List[str]) -> List[str]:
        """fix 50 (todo lead #1): a for-head cond re-rendering a call
        whose result a preceding decl already holds folds to the decl
        token. Ground truth InventoryManager.PickupNewObj @ 0x1807018d0
        (work/probe_b41_forhead.py): the native tag loops each call
        FindGameObjectsWithTag ONCE, before the loop -- the cond's call
        text is the lifter re-rendering the once-computed array value,
        so `i < CALL.Length` -> `i < tok.Length` restores native
        semantics. Only the cond clause rewrites, only exact call-text
        matches, and only when the decl provably still holds the call
        (see _fhf_holder). 26 adjacent sites in AC at b40_out2."""
        out = list(lines)
        for i, st in enumerate(out):
            s = st.strip()
            if not (s.startswith('for (') and s.endswith(')')):
                continue
            parts = self._fhf_split(s[5:-1])
            if len(parts) != 3:
                continue
            init, cond, inc = parts
            calls = self._FHF_CALL_RX.findall(cond)
            if not calls:
                continue
            new_cond = cond
            for call in dict.fromkeys(calls):
                tok = self._fhf_holder(out, i, call)
                if tok is not None:
                    new_cond = new_cond.replace(call + '.Length',
                                                tok + '.Length')
            if new_cond != cond:
                out[i] = '%sfor (%s; %s; %s)' % (
                    st[:len(st) - len(st.lstrip())], init, new_cond, inc)
        return out

    # ------------------------------------------------------------------
    _FORHDR_RX = re.compile(r'^for \(int (v\d+) = 0; \1 < ([\w.]+)\.Length; \1\+\+\)$')

    def _foreach_sugar(self, lines: List[str]) -> List[str]:
        """for (int i = 0; i < arr.Length; i++) over an array becomes
        foreach (T e in arr) when the counter feeds nothing but element
        reads. Both indexing styles count: arr[i] and the raw IL2CPP element
        load *(arr + i*size + hdr). Runs before local renaming so the
        element local joins the normal rename pass."""
        i = 0
        while i < len(lines):
            m = self._FORHDR_RX.match(lines[i].strip())
            if not m or i + 1 >= len(lines) or lines[i + 1].strip() != '{':
                i += 1
                continue
            close = _match_brace(lines, i + 1)
            if close < 0:
                i += 1
                continue
            idx, arr = m.group(1), m.group(2)
            body = lines[i + 2:close]
            p1 = re.compile(r'\*\(%s \+ %s\*\d+ \+ 0x[0-9a-fA-F]+\)' % (
                re.escape(arr), re.escape(idx)))
            p3 = re.compile(r'%s\[%s\]' % (re.escape(arr), re.escape(idx)))
            idx_rx = re.compile(r'(?<![\w.])%s(?![\w])' % re.escape(idx))
            ok = True
            masked = []
            for st in body:
                s = st.strip()
                # element writes disqualify (foreach elements are read-only)
                w = re.match(r'^(.+?) = ', s)
                if w and idx_rx.search(w.group(1)):
                    ok = False
                    break
                sh, _ = self._mask_literals(s, False)
                t = self._sub_outside_literals(p1, '~E~', s, sh)
                sh2, _ = self._mask_literals(t, False)
                t = self._sub_outside_literals(p3, '~E~', t, sh2)
                if idx_rx.search(t):
                    ok = False      # counter used for something else
                    break
                masked.append(t)
            if not ok:
                i += 1
                continue
            etype = self._array_elem_type(arr)
            ev = self._fresh_vtok(lines)
            newbody = [t.replace('~E~', ev) for t in masked]
            lines[i] = 'foreach (%s %s in %s)' % (etype, ev, arr)
            lines[i + 2:close] = newbody
            i += 2
        return lines

    def _fresh_vtok(self, lines) -> str:
        """A vN token used nowhere in this method and carrying no stale type
        hint (lifter hints persist across methods and would mis-name it)."""
        taken = set(self._var_types) | set(getattr(self.L, '_type_hints', {}))
        mx = 0
        for st in lines:
            for t in re.findall(r'\bv(\d+)\b', st):
                mx = max(mx, int(t))
        n = mx + 1
        while ('v%d' % n) in taken:
            n += 1
        return 'v%d' % n

    def _array_elem_type(self, arr_tok) -> str:
        t = self._var_types.get(arr_tok) or getattr(self.L, '_type_hints', {}).get(arr_tok)
        if not t or not isinstance(t, tuple):
            return 'object'
        te = (t[1] >> 16) & 0xFF
        if te != 0x1d:
            return 'object'
        inner = self.L.il.type_from_ptr(t[0])
        if inner is None:
            return 'object'
        try:
            return self.L.il.type_name(inner)
        except Exception:
            return 'object'

    def _find_increment(self, lines, open_idx, close_idx, cond):
        """The counter bump near the end of the loop body. It need not be the
        very last statement -- other phi copies often follow it -- as long as
        nothing after it reads the counter."""
        depth = 0
        tail = []
        for j in range(close_idx - 1, open_idx, -1):
            t = lines[j].strip()
            if t == '}' or t.startswith('} while'):
                depth += 1
            elif t == '{':
                depth -= 1
            elif depth == 0 and t and not t.endswith(':'):
                tail.append(j)
                if len(tail) > 6:
                    break
        for j in tail:
            m = self._INC_RX.match(lines[j].strip())
            if not m:
                continue
            var = m.group(1)
            rx = re.compile(r'(?<![\w.])%s(?![\w])' % var)
            if not rx.search(cond):
                continue
            if any(rx.search(lines[k]) for k in range(j + 1, close_idx)):
                continue
            return j, var, m.group(2), m.group(3)
        return None

    def _find_init(self, lines, wi, var):
        """Nearest preceding `var = <pure expr>;` at the same brace depth."""
        rx = re.compile(r'^%s = (.+);$' % var)
        use = re.compile(r'(?<![\w.])%s(?![\w])' % var)
        depth = 0
        for q in range(wi - 1, max(wi - 60, -1), -1):
            t = lines[q].strip()
            if t == '}':
                depth += 1
                continue
            if t == '{':
                depth -= 1
                if depth < 0:
                    break
                continue
            if depth != 0 or not t:
                continue
            m = rx.match(t)
            if m:
                return (m.group(1), q) if not self._IMPURE.search(m.group(1)) else (None, None)
            if use.search(t):
                break
        return None, None

    def _used_outside(self, lines, i, close, var, init_idx):
        rx = re.compile(r'(?<![\w.])%s(?![\w])' % var)
        for q, st in enumerate(lines):
            if i <= q <= close or q == init_idx:
                continue
            if rx.search(st):
                return True
        return False

    PREFIX = {'int': 'num', 'bool': 'flag', 'float': 'real', 'other': 'obj'}

    _COMP_OPS = {'+': '+=', '-': '-=', '*': '*=', '|': '|=', '&': '&=', '^': '^='}
    _SELF_ARITH_RX = re.compile(
        r'^([\w.\[\]]+) = \1 ([+\-*|&^]) (\d+|0x[0-9a-f]+|(?:\d+\.\d*|\.\d+)f?);$')
    # fix 97: the hop temp may carry its declaration (`int num5 = ...`)
    # now that first-use bare assignments declare. The declaration rides
    # along with the temp: the fold drops both together, so no orphan
    # decl survives. The temp group numbering is unchanged.
    _HOP_DEF_RX = re.compile(
        r'^(?:[A-Za-z_][\w.<>\[\]]* )?'
        r'((?:num|flag|real|obj)\d+|v\d+|t\d+) = ([\w.\[\]]+) ([+\-]) '
        r'(\d+|0x[0-9a-f]+|(?:\d+\.\d*|\.\d+)f?);$')
    _HOP_COPY_RX = re.compile(r'^([\w.\[\]]+) = ((?:num|flag|real|obj)\d+|v\d+|t\d+);$')

    def _compound_assign(self, lines: List[str]) -> List[str]:
        """`num1 = x + 1; x = num1;` -- the SSA temp hop -- and the direct
        `x = x + 1;` both fold to `x += 1;`. The hop temp must die at the
        copy (exactly two occurrences body-wide) and nothing may write the
        target between the two statements."""
        for _ in range(8):
            st = [s.strip() for s in lines]
            counts = {}
            for s in st:
                for tok in set(self._LOC_RX.findall(self._CMT_RX.sub('', s))):
                    counts[tok] = counts.get(tok, 0) + 1
            drop = set()
            res = []
            for i, s in enumerate(st):
                if i in drop:
                    continue
                ind = lines[i][:len(lines[i]) - len(lines[i].lstrip())]
                m = self._SELF_ARITH_RX.match(s)
                if m and '(' not in m.group(1):
                    res.append('%s%s %s %s;' % (ind, m.group(1),
                                                self._COMP_OPS[m.group(2)], m.group(3)))
                    continue
                m = self._HOP_DEF_RX.match(s)
                if m and counts.get(m.group(1), 0) == 2 and '(' not in m.group(2):
                    t, x, op, c = m.groups()
                    wrx = re.compile(r'^%s = ' % re.escape(x))
                    folded = False
                    for j in range(i + 1, min(i + 5, len(st))):
                        if j in drop or not st[j]:
                            continue
                        if wrx.match(st[j]):
                            if self._HOP_COPY_RX.match(st[j]) \
                                    and self._HOP_COPY_RX.match(st[j]).group(2) == t:
                                res.append('%s%s %s %s;' % (ind, x, self._COMP_OPS[op], c))
                                drop.add(j)
                                folded = True
                            break
                        if st[j] in ('{', '}') or st[j].endswith(':'):
                            break       # brace/label: never fold across a scope
                        if re.match(r'^%s(?![\w])' % re.escape(x), st[j]):
                            break       # compound/member write to the target
                        if re.search(r'(?<![\w.])%s(?![\w])' % re.escape(t), st[j]):
                            break       # another use of the hop temp appears
                    if not folded:
                        res.append(lines[i])
                    continue
                res.append(lines[i])
            if len(res) + len(drop) == len(lines):
                return res
            lines = res
        return lines

    _NUMERIC_DECLS = frozenset([
        'bool', 'sbyte', 'short', 'int', 'long', 'byte', 'ushort',
        'uint', 'ulong', 'char', 'float', 'double', 'decimal'])
    _FLOAT_DECLS = frozenset(['float', 'double', 'decimal'])
    _FLOAT_LIT_RX = re.compile(r'^[+-]?(\d+\.\d*|\.\d+|\d+)([eE][+-]?\d+)?[fFdD]?$')

    def _bare_rhs_needs_default(self, dt, rhs):
        """True when a zero literal RHS cannot spell its declaration type.

        Stack-slot zeroing renders `= 0` / `= 0f` under whatever type
        the slot carries. That is fine for `object` (boxing), numerics,
        and `bool` (normalized later), but `RaycastHit x = 0f` and
        `T x = 0` are not C#. `= default` is the zero value in every one
        of those shapes, so the rewrite is value-preserving. Only zero
       -valued numerics rewrite: a nonzero literal under a mismatched
        type keeps its faithful (if uncompilable) value instead of
        baking in a different one. Anything else (calls, members, null,
        strings, matching literals) is untouched. -- fix 97b
        """
        if not rhs or dt == 'object':
            return False
        short = dt.rsplit('.', 1)[-1].rstrip('?')
        r = rhs[:-1].strip() if rhs.rstrip().endswith(';') else rhs.strip()
        if r in ('true', 'false', 'default', 'null'):
            return False
        if len(r) >= 2 and r[0] == "'" and r[-1] == "'":
            return False
        if len(r) >= 2 and r[0] == '"':
            return False
        try:
            iv = int(r, 0)
            return iv == 0 and short not in self._NUMERIC_DECLS
        except ValueError:
            pass
        if self._FLOAT_LIT_RX.match(r):
            try:
                fv = float(r.rstrip('fFdD'))
            except ValueError:
                return False
            return fv == 0.0 and short not in self._FLOAT_DECLS
        return False

    def _rename_locals(self, lines: List[str], method=None) -> List[str]:
        import re as _re
        tokens = []
        shadow = []
        in_comment = False
        for st in lines:
            sh, in_comment = self._mask_literals(st, in_comment)
            shadow.append(sh)
            tokens.extend(_re.findall(
                r'(?<![\w.])(?:v\d+|t\d+|s_[0-9a-fA-F]+)(?![\w])', sh))
        seen = set()
        # Parameters already declare their names in the signature
        # (mi 113041: body params v0/v1 renamed to obj5/obj6 while
        # the emitter kept v0/v1, disconnecting every use). Never
        # rename a token matching a metadata parameter name; a lifter
        # temp sharing the spelling keeps its honest lift-stage name.
        param_names = set()
        if method is not None:
            try:
                param_names = set(safe_ident(p.name)
                                  for p in self.L.meta.method_params(method))
            except Exception:
                pass
        # A single prologue copy of a scalar metadata parameter carries its
        # exact declared type. This recovers stack homes like `s_10 = volume`
        # (float) without inferring from an unrelated later use. A second
        # write or address escape declines; existing concrete hints win.
        if method is not None:
            try:
                scalar_params = {}
                for p in self.L.meta.method_params(method):
                    ty = self.L.il.types[p.type]
                    te = (ty[1] >> 16) & 0xFF if isinstance(ty, tuple) else 0
                    if te in (0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08,
                              0x09, 0x0a, 0x0b, 0x0c, 0x0d, 0x18, 0x19):
                        scalar_params[safe_ident(p.name)] = ty
                copy_rx = _re.compile(
                    r'^\s*(?:var\s+)?((?:v\d+|t\d+|s_[0-9a-fA-F]+))\s*=\s*'
                    r'([A-Za-z_@]\w*)\s*;$')
                for st in lines:
                    if _re.match(r'^\s*(?:if|else|while|for|foreach|do|switch|'
                                 r'try|catch|finally|goto|return|throw)\b', st) \
                            or st.strip() in ('{', '}') or st.strip().endswith(':'):
                        break
                    hit = copy_rx.match(st)
                    if hit is None or hit.group(2) not in scalar_params:
                        continue
                    tok, src = hit.groups()
                    token = _re.escape(tok)
                    writes = _re.compile(r'(?<![\w.])%s(?!\w)\s*(?:[+\-*/%%&|^]?=(?!=|>)|\+\+|--)'
                                         % token)
                    escapes = _re.compile(r'(?<!&)&(?!&)\s*%s\b|\b(?:ref|out|in)\s+%s\b'
                                          % (token, token))
                    if sum(bool(writes.search(line)) for line in lines) == 1 \
                            and not any(escapes.search(line) for line in lines):
                        self._var_types.setdefault(tok, scalar_params[src])
            except (AttributeError, IndexError, TypeError):
                pass
        ordered = [t for t in tokens
                   if t not in param_names
                   and not (t in seen or seen.add(t))]
        if not ordered:
            return lines
        # Minted obj/num/flag/real names must not capture identifiers
        # the body already uses -- least of all metadata parameter
        # names (mi 124140: s_8/v4 became obj1/obj2, shadowing the
        # params, and _copy_prop then merged the dropped argument).
        # Mirror _semantic_local_names' barrier: every family token in
        # the lines (member tails excluded) plus every parameter name.
        reserved = set(_re.findall(
            r'(?<![\w.])(?:obj\d+|num\d+|flag\d+|real\d+)(?![\w])',
            '\n'.join(lines)))
        if method is not None:
            try:
                reserved.update(safe_ident(p.name)
                                for p in self.L.meta.method_params(method))
            except Exception:
                pass
        cnt = {'int': 0, 'bool': 0, 'float': 0, 'other': 0}
        names = {}

        def type_of(tok):
            t = None
            if tok.startswith('s_'):
                t = self.L.slot_types.get(tok)
            if t is None:
                t = self._var_types.get(tok)
            if t is None:
                t = self.L.__dict__.get('_var_types', {}).get(tok)
            if not t or not isinstance(t, tuple):
                return 'other'
            te = (t[1] >> 16) & 0xFF
            if te == 0x02:
                return 'bool'
            if te in (0x0c, 0x0d):
                return 'float'
            if te in (0x04, 0x05, 0x06, 0x07, 0x08, 0x09, 0x0a, 0x0b, 0x18, 0x19):
                return 'int'
            return 'other'

        for tok in ordered:
            k = type_of(tok)
            cnt[k] += 1
            candidate = '%s%d' % (self.PREFIX[k], cnt[k])
            while candidate in reserved:
                cnt[k] += 1
                candidate = '%s%d' % (self.PREFIX[k], cnt[k])
            names[tok] = candidate
        rx = _re.compile(r'(?<![\w.])(' + '|'.join(_re.escape(t) for t in names) + r')(?![\w])')
        renamed = []
        for st, sh in zip(lines, shadow):
            spans = [mm.span() for mm in rx.finditer(sh)]
            if spans:
                parts = []
                last = 0
                for a, b in spans:
                    parts.append(st[last:a])
                    parts.append(names[sh[a:b]])
                    last = b
                parts.append(st[last:])
                st = ''.join(parts)
            renamed.append(st)
        lines = renamed
        # explicit declaration types: no `var` in the output, each local is
        # declared with its tracked il2cpp type (object when untracked); the
        # first `var NAME = rhs;` occurrence fixes the type, from the rhs
        # itself for klass loads
        tok_of = {new: tok for tok, new in names.items()}
        decl = {}
        new_names = sorted(set(names.values()))
        decl_rx = _re.compile(r'^(\s*)var (' + '|'.join(_re.escape(n) for n in new_names)
                              + r')( = )(.*)$')
        # fix 97: a first-use bare assignment (`objN = rhs;` -- stack-slot
        # zeroing, phi copies, unbound call results) declares nothing, so
        # the method never compiles. Declare it exactly like a `var`
        # line, with the same tracked-type lookup; a later `var` line for
        # the same temp then keeps only its assignment. Labels, member
        # stores, comparisons and lambdas never match: the name must
        # follow the indent directly and `=` must stand alone.
        bare_rx = _re.compile(r'^(\s*)(' + '|'.join(_re.escape(n) for n in new_names)
                              + r') = (?!==|=|>)(.*)$')
        # fix 138: `_for_sugar` folds a counter's entry copy into the loop
        # head without a type when the counter outlives the loop (or its
        # init is not a literal): `for (num4 = 0; ...)`. When no enclosing
        # scope has declared the counter yet, nothing ever does (CS0103 at
        # every head/body/after-loop read, ~11.6k in gate b12). Declare it
        # bare on the line before the head, in the block that holds the
        # loop, with the same tracked-type lookup as a first-use bare
        # assignment; the later scope repair hoists it when a read escapes
        # that block. Nothing is initialised -- the head still assigns.
        forhead_rx = _re.compile(r'^(\s*)for \((' + '|'.join(_re.escape(n) for n in new_names)
                                 + r') = (?!=)([^;]*);')
        gp_blocked = getattr(self.L, '_gp_blocked', ())
        # `Foo.Method()` (bare, no `<T>`) is what a shared-generic call for a
        # reference-type argument compiles down to (`GetComponent<T>()` and
        # friends): IL2CPP calls the method's own unsubstituted signature,
        # which returns the literal generic parameter `T`. `_bind`/etc.
        # withhold that useless type (fix 21f, `_gp_blocked`) so a real hint
        # from where the result is USED (its assignment target) can type the
        # declaration instead -- and since that is the same type the call
        # itself lost, re-attach it here as `<T>` too, but only for the
        # bare-call shape this pattern actually produces (any call already
        # carrying its own `<...>` didn't need this and is left untouched).
        callno_rx = _re.compile(r'^(.*?\.\w+)\(\)(;)$')
        # Heterogeneous box-temp guard (mi 1242 `Convert.ChangeType`):
        # one stack slot is reused across switch arms with incompatible
        # types, but the tracked tuple keeps a single arm's type (first
        # or last write wins). Declaring the first occurrence with that
        # tuple breaks every other arm (`System.DateTime dateTime1 =
        # obj2; dateTime1 = flag1; ...`). When the chosen declaration is
        # a namespaced type and some single-identifier assignment to the
        # same local resolves to a different closed type, keep `object`
        # (boxing is always safe). A single conflicting sample can be
        # a mistyped lane/fragment artifact (mi 63027 `vector31 =
        # real37`), so two distinct conflicting closed types are
        # required; uncomparable (None) keys never vote. Single-
        # identifier RHS only;
        # calls/members/literals prove nothing and never fire the guard.
        # Non-namespaced (primitive) declarations are out of scope.
        def _tracked_of_post(post):
            _pre = tok_of.get(post, post)
            _t = None
            try:
                if isinstance(_pre, str) and _pre.startswith('s_'):
                    _t = self.L.slot_types.get(_pre)
            except Exception:
                _t = None
            try:
                if _t is None:
                    _mm = getattr(self, '_var_types', None)
                    if _mm:
                        _t = _mm.get(_pre)
            except Exception:
                pass
            try:
                if _t is None:
                    _t = self.L.__dict__.get('_var_types', {}).get(_pre)
            except Exception:
                pass
            try:
                if _t is None:
                    _t = getattr(self.L, '_type_hints', {}).get(_pre)
            except Exception:
                pass
            try:
                if _t is None and isinstance(_pre, str) and not _pre.startswith('s_'):
                    _t = getattr(self.L, 'slot_types', {}).get(_pre)
            except Exception:
                pass
            if _t is None and method is not None:
                _si = safe_ident
                try:
                    for _pp in self.L.meta.method_params(method):
                        if _si(_pp.name) == post:
                            _pt = self.L.il.types[_pp.type]
                            _t = _pt
                            break
                except Exception:
                    pass
            return _t if isinstance(_t, tuple) else None
        def _closed_key(_tt):
            try:
                _ck = getattr(self.L.il, '_closed_type_key', None)
                if callable(_ck):
                    return _ck(_tt)
            except Exception:
                pass
            return _tt
        def _hetero_derived(_dt0, _rt):
            """True when the RHS type provably derives from the decl type."""
            try:
                _tdof = getattr(self.L.il, 'td_of_ty', None)
                if not callable(_tdof):
                    return False
                _t0 = _tdof(_dt0)
                _t1 = _tdof(_rt)
                if _t0 is None or _t1 is None:
                    return False
                if _t0 == _t1:
                    return True
                try:
                    _bc = getattr(self.L.il, 'base_chain_tds', None)
                    if not callable(_bc):
                        return False
                    return _t0 in (_bc(_t1) or ())
                except Exception:
                    return False
            except Exception:
                return False
        # Unresolved native helpers (`sub_<hex>(...)`) carry no C#
        # signature, so an argument position there imposes no parameter
        # type on the temp: `&slot` / `slot` handed to one cannot veto the
        # retype (mi 1242 `sub_18004a890(&obj1, 13, typeof(...), c)`, a
        # box-staging slot reused across Convert.ChangeType arms). Resolved
        # callees, ref/out/in, members, indexers and returns still veto.
        _HELPER_RX = _re.compile(r'(?<![\w.])sub_[0-9A-Fa-f]+\s*$')
        def _untyped_helper_arg(_sh, _pos):
            _d = 0
            for _i in range(_pos - 1, -1, -1):
                _c = _sh[_i]
                if _c == ')':
                    _d += 1
                elif _c == '(':
                    if _d == 0:
                        return _HELPER_RX.search(_sh, 0, _i) is not None
                    _d -= 1
            return False
        _OBJ_MEMBERS = frozenset((
            'ToString', 'GetHashCode', 'GetType', 'Equals'))
        def _hetero_vetoed(_nm_post):
            """True when a later use forbids retyping the temp to object.

            Matches pre-rename spellings in the masked shadow: the
            rename is structure-preserving token substitution, while
            `shadow` is the only literal-masked view available here.
            """
            try:
                _pre = tok_of.get(_nm_post, _nm_post)
                _te = _re.escape(_pre)
                _esc_rx = _re.compile(
                    r'(?:&\s*%s\b|\b(?:ref|out|in)\s+%s\b)' % (_te, _te))
                _mem_rx = _re.compile(
                    r'(?<![\w.])(%s)\s*\.\s*([A-Za-z_]\w*)' % _te)
                _idx_rx = _re.compile(r'(?<![\w.])(%s)\s*\[' % _te)
                _ret_rx = _re.compile(r'^\s*return\s+(%s)\s*;' % _te)
                _ret_box_rx = _re.compile(
                    r'^\s*return\s+\(\s*object\s*\)')
                _declmap = {}
                _dmulti = set()
                for _sh in shadow:
                    _dm = _re.match(
                        r'^\s*([A-Za-z_@][^=;(){}]*?)\s+([A-Za-z_@]\w*)\s*=(?![=>])',
                        _sh)
                    if _dm is None:
                        continue
                    _ty, _tn = _dm.group(1).strip(), _dm.group(2)
                    if _tn in _dmulti:
                        continue
                    if _tn in _declmap:
                        if _declmap[_tn] != _ty:
                            _dmulti.add(_tn)
                            del _declmap[_tn]
                        continue
                    _declmap[_tn] = _ty
                _ref_rx = _re.compile(r'\b(?:ref|out|in)\s+(%s)(?![\w])' % _te)
                _def_rx = _re.compile(
                    r'^\s*(?:[A-Za-z_@][^=;(){}]*?\s+)?%s\s*=(?![=>])' % _te)
                _box_rx = _re.compile(
                    r'\(\s*object\s*\)\s*(?:\(\s*%s\s*\)|%s(?![\w]))' % (_te, _te))
                _objm_rx = _re.compile(
                    r'(?<![\w.])%s\s*\.\s*(?:ToString|GetHashCode|GetType|Equals)\b' % _te)
                _occ_rx = _re.compile(r'(?<![\w.@])%s(?![\w])' % _te)
                _amp_rx = _re.compile(r'&\s*(%s)(?![\w])' % _te)
                for _sh in shadow:
                    if _ref_rx.search(_sh):
                        return True
                    for _am in _amp_rx.finditer(_sh):
                        if _untyped_helper_arg(_sh, _am.start()):
                            continue
                        _bm = _re.match(
                            r'^\s*(?:[A-Za-z_@][^=;(){}]*?\s+)?([A-Za-z_@]\w*)\s*=\s*&\s*%s\s*;\s*$' % _te,
                            _sh)
                        if _bm is None:
                            return True
                        _bt = _bm.group(1)
                        # The binder's spelling is what the decl pass will print: an
                        # undeclared/`var` binder resolves through `_decl_type_of`
                        # (mi 1242 `v188 = &s_10;` prints `object obj10 = &obj1;`).
                        _bdt = _declmap.get(_bt)
                        if _bdt in (None, 'var') and _bt not in _dmulti:
                            try:
                                _bdt = self._decl_type_of(_bt, '&' + _pre)
                            except Exception:
                                _bdt = None
                        if _bt in _dmulti or _bdt not in ('object', 'System.Object'):
                            return True
                    _mm = _mem_rx.search(_sh)
                    if _mm is not None and _mm.group(2) not in _OBJ_MEMBERS:
                        return True
                    if _idx_rx.search(_sh):
                        return True
                    if _ret_rx.match(_sh) is not None \
                            and _ret_box_rx.match(_sh) is None:
                        try:
                            _rok = False
                            if method is not None:
                                _ri = getattr(method, 'return_type', -1)
                                _rty = self.L.il.types[_ri] \
                                    if 0 <= _ri < len(self.L.il.types) \
                                    else None
                                if isinstance(_rty, tuple) and \
                                        ((_rty[1] >> 16) & 0xFF) == 0x1c:
                                    _rok = True
                        except Exception:
                            _rok = False
                        if not _rok:
                            return True
                    # Box-only reads (decline-by-default): after masking the def
                    # (`X =` / `T X =`), boxing casts `(object)(X)` / `(object)X`,
                    # `&X` (proven above), builtin object members and an object-
                    # method `return X;`, ANY other occurrence is a typed read and
                    # vetoes -- call args incl. generic and nested-paren calls,
                    # field/element stores, arithmetic, casts, compound assigns
                    # (mscorlib ActivationServices `_activator = X`, MemoryStream
                    # `TryGetArray<byte>(X, ...)`, Decimal `X * k`, RuntimeType
                    # `FilterApplyMethodBase(..., (BindingFlags)(n), ..., X)`).
                    _rest = _def_rx.sub(' ', _sh, count=1)
                    _rest = _box_rx.sub(' ', _rest)
                    _rest = _amp_rx.sub(' ', _rest)
                    _rest = _objm_rx.sub(' ', _rest)
                    _rest = _ret_rx.sub(' ', _rest)
                    if _occ_rx.search(_rest):
                        return True
                return False
            except Exception:
                return False
        _hetero_assigns = {}
        try:
            _nm_alt = '|'.join(_re.escape(_n) for _n in new_names)
            _as_rx = _re.compile(r'^\s*(' + _nm_alt + r')\s*=(?!=|>)(.*);\s*$')
            for _st in lines:
                _am = _as_rx.match(_st)
                if _am is None:
                    continue
                _hetero_assigns.setdefault(_am.group(1), []).append(_am.group(2).strip())
        except Exception:
            _hetero_assigns = {}
        def _hetero_decl(_nm_post, _dt, _rhs=''):
            try:
                if '.' not in (_dt or ''):
                    return _dt
                if _dt in ('object', 'System.Object', 'System.Type'):
                    return _dt
                if _hetero_vetoed(_nm_post):
                    return _dt
                _r0 = (_rhs or '').strip()
                if _r0.endswith(';'):
                    _r0 = _r0[:-1].strip()
                if _r0 != _nm_post and _re.fullmatch(r'[A-Za-z_]\w*', _r0):
                    _hetero_assigns.setdefault(_nm_post, []).insert(0, _r0)
                _dt0 = _tracked_of_post(_nm_post)
                if _dt0 is None:
                    return _dt
                _k0 = _closed_key(_dt0)
                if _k0 is None:
                    return _dt
                _seen = set()
                for _rhs in _hetero_assigns.get(_nm_post, ()):
                    _rm = _re.fullmatch(r'([A-Za-z_]\w*)', (_rhs or '').strip())
                    if not _rm:
                        continue
                    _rn = _rm.group(1)
                    if _rn == _nm_post:
                        continue
                    _rt = _tracked_of_post(_rn)
                    if _rt is None:
                        continue
                    _k = _closed_key(_rt)
                    if _k is None or _k == _k0:
                        continue
                    if _hetero_derived(_dt0, _rt):
                        continue
                    _seen.add(_k)
                    if len(_seen) >= 2:
                        return 'object'
                return _dt
            except Exception:
                return _dt
        out = []
        depth = 0
        # fix 97c: declarations are block-scoped. A temp declared in a
        # closed sibling block is not visible here, so suppress the
        # duplicate-decl rewrite unless an enclosing (or same) scope
        # already declared it; otherwise re-declare (shadowing is legal,
        # leaking across arms is not). Same-brace-level switch sections
        # share one scope, so they keep suppressing.
        for st in lines:
            s = st.strip()
            if s == '{':
                depth += 1
            elif s == '}':
                depth -= 1
                for k2 in [k2 for k2, dd in decl.items() if dd[1] > depth]:
                    del decl[k2]
            m = decl_rx.match(st)
            if m:
                nm = m.group(2)
                rhs = m.group(4)
                if nm not in decl:
                    dt = self._decl_type_of(tok_of[nm], rhs)
                    try:
                        dt = _hetero_decl(nm, dt, rhs)
                    except Exception:
                        pass
                    if tok_of[nm] in gp_blocked and dt not in ('object', 'System.Type'):
                        cm = callno_rx.match(rhs)
                        if cm:
                            rhs = '%s<%s>()%s' % (cm.group(1), dt, cm.group(2))
                    if self._bare_rhs_needs_default(dt, rhs):
                        rhs = 'default;'
                    decl[nm] = (dt, depth)
                    st = '%s%s %s = %s' % (m.group(1), dt, nm, rhs)
                else:
                    st = '%s%s = %s' % (m.group(1), nm, rhs)
            else:
                fh = forhead_rx.match(st)
                if fh is not None and fh.group(2) not in decl:
                    nm = fh.group(2)
                    dt = self._decl_type_of(tok_of.get(nm, nm), fh.group(3) + ';')
                    try:
                        dt = _hetero_decl(nm, dt, fh.group(3) + ';')
                    except Exception:
                        pass
                    if dt and dt != 'var':
                        decl[nm] = (dt, depth)
                        out.append('%s%s %s;' % (fh.group(1), dt, nm))
                b = bare_rx.match(st)
                if b is not None and b.group(2) not in decl:
                    nm = b.group(2)
                    rhs = b.group(3)
                    dt = self._decl_type_of(tok_of.get(nm, nm), rhs)
                    try:
                        dt = _hetero_decl(nm, dt, rhs)
                    except Exception:
                        pass
                    if tok_of.get(nm, nm) in gp_blocked and dt not in ('object', 'System.Type'):
                        cm = callno_rx.match(rhs)
                        if cm:
                            rhs = '%s<%s>()%s' % (cm.group(1), dt, cm.group(2))
                    if self._bare_rhs_needs_default(dt, rhs):
                        rhs = 'default;'
                    decl[nm] = (dt, depth)
                    st = '%s%s %s = %s' % (b.group(1), dt, nm, rhs)
            out.append(st)
        try:
            out = self._numeric_obj_retype(out)
        except Exception:
            pass
        return out

    # fix 135 (CS0019 slice): an untracked temp is declared `object`, so
    # every arithmetic/compare use is `object op int` (CS0019). When every
    # definition of the temp is provably integer -- int literals, integer
    # operators, and other integer-declared locals (or itself) -- and no
    # use treats it as a reference (member/index/call, null, is/as, casts,
    # &/ref/out, __addr), declare it `int` (or `long` when a literal or a
    # source needs 64 bits) and rename it into the num family. Anything
    # unproven keeps `object`.
    _NOBJ_INT_TYPES = {
        'int': 'int', 'short': 'int', 'ushort': 'int', 'byte': 'int',
        'sbyte': 'int', 'System.Int32': 'int', 'System.Int16': 'int',
        'System.UInt16': 'int', 'System.Byte': 'int', 'System.SByte': 'int',
        'long': 'long', 'uint': 'long', 'System.Int64': 'long',
        'System.UInt32': 'long',
        # fix 136: float lanes (`obj70 > 0.6f`) -> float/double
        'float': 'float', 'System.Single': 'float',
        'double': 'double', 'System.Double': 'double'}
    _NOBJ_RANK = {'int': 0, 'long': 1, 'float': 2, 'double': 3}
    _NOBJ_FLT_RX = re.compile(
        r'^(?:\d+\.\d*|\.\d+|\d+)(?:[eE][-+]?\d+)?([fFdD]?)$')
    _NOBJ_KW = frozenset(('return', 'throw', 'yield', 'case', 'goto', 'else',
                          'new', 'await', 'using', 'lock', 'fixed'))
    _NOBJ_DECL_RX = re.compile(
        r'^\s*([A-Za-z_][\w.]*)\s+([A-Za-z_]\w*)\s*=(?!=)\s*(.*?);\s*$')
    _NOBJ_ASSIGN_RX = re.compile(
        r'^\s*([A-Za-z_]\w*)\s*(\+|-|\*|/|%|&|\||\^|<<|>>)?=(?!=)\s*(.*?);\s*$')
    _NOBJ_INCDEC_RX = re.compile(
        r'^\s*(?:([A-Za-z_]\w*)\s*(?:\+\+|--)|(?:\+\+|--)\s*([A-Za-z_]\w*))\s*;\s*$')
    _NOBJ_TOK_RX = re.compile(
        r'\s+|0[xX][0-9a-fA-F]+[lL]?'
        r'|(?:\d+\.\d*|\.\d+|\d+)(?:[eE][-+]?\d+)?[fFdD]'
        r'|(?:\d+\.\d*|\.\d+)(?:[eE][-+]?\d+)?|\d+[eE][-+]?\d+'
        r'|\d+[lL]?|<<|>>|[-+*/%&|^~()]|[A-Za-z_]\w*|.')
    _NOBJ_OCC_RX = re.compile(r'(?<![\w.@])(obj\d+)(?!\w)')
    _NOBJ_AFTER_BAD_RX = re.compile(
        r'^(?:[.\[(?]|=(?!=)|\+\+|--|(?:\+|-|\*|/|%|&|\||\^|<<|>>)=|(?:is|as)\b)')
    _NOBJ_BEFORE_BAD_RX = re.compile(
        r'(?:\)|\+\+|--|(?<!&)&|\b(?:ref|out|in|lock|throw|foreach|fixed|using|typeof|sizeof|nameof)\s*\(?)$')

    def _nobj_rhs_kind(self, rhs, cur):
        """'int'/'long' for a provably integer rhs, 'dflt' for `default`."""
        if rhs.strip() == 'default':
            return 'dflt'
        kind = 'int'
        saw = False
        for t in self._NOBJ_TOK_RX.findall(rhs):
            if t.isspace() or t in ('<<', '>>') or (len(t) == 1 and t in '-+*/%&|^~()'):
                continue
            if (t[0].isdigit() or t[0] == '.') and not t[:2] in ('0x', '0X') and \
                    (('.' in t) or t[-1] in 'fFdD' or 'e' in t or 'E' in t):
                fm = self._NOBJ_FLT_RX.match(t)
                if fm is None:
                    return None
                fk = 'float' if fm.group(1) in ('f', 'F') else 'double'
                if self._NOBJ_RANK[fk] > self._NOBJ_RANK[kind]:
                    kind = fk
                saw = True
                continue
            if t[0].isdigit():
                s = t.rstrip('lL')
                try:
                    v = int(s, 16) if s[:2] in ('0x', '0X') else int(s, 10)
                except ValueError:
                    return None
                if v > 0x7FFFFFFFFFFFFFFF:
                    return None
                if (s != t or v > 0x7FFFFFFF) and kind == 'int':
                    kind = 'long'
                saw = True
                continue
            k = cur.get(t)
            if k is None:
                return None
            if self._NOBJ_RANK[k] > self._NOBJ_RANK[kind]:
                kind = k
            saw = True
        return kind if saw else None

    def _numeric_obj_retype(self, lines):
        masked = []
        in_bc = False
        for st in lines:
            mm, in_bc = self._mask_literals(st, in_bc)
            if len(mm) != len(st):
                return lines
            masked.append(mm)
        known = {}
        objdecl = set()
        bad = set()
        for mm in masked:
            m = self._NOBJ_DECL_RX.match(mm)
            if not m or m.group(1) in self._NOBJ_KW:
                continue
            ty, nm = m.group(1), m.group(2)
            if re.fullmatch(r'obj\d+', nm):
                if ty == 'object':
                    objdecl.add(nm)
                else:
                    bad.add(nm)
            elif ty in self._NOBJ_INT_TYPES:
                known.setdefault(nm, set()).add(self._NOBJ_INT_TYPES[ty])
            else:
                known.setdefault(nm, set()).add(None)
        known = {k: next(iter(v)) for k, v in known.items()
                 if len(v) == 1 and None not in v}
        cands = objdecl - bad
        if not cands:
            return lines
        defs = {n: [] for n in cands}
        def_lines = {n: set() for n in cands}
        for i, mm in enumerate(masked):
            m = self._NOBJ_DECL_RX.match(mm)
            if m and m.group(1) == 'object' and m.group(2) in cands:
                defs[m.group(2)].append(m.group(3))
                def_lines[m.group(2)].add(i)
                continue
            m = self._NOBJ_ASSIGN_RX.match(mm)
            if m and m.group(1) in cands:
                n = m.group(1)
                rhs = m.group(3)
                if m.group(2):
                    rhs = '%s %s (%s)' % (n, m.group(2), rhs)
                defs[n].append(rhs)
                def_lines[n].add(i)
                continue
            m = self._NOBJ_INCDEC_RX.match(mm)
            if m:
                n = m.group(1) or m.group(2)
                if n in cands:
                    defs[n].append('%s + 1' % n)
                    def_lines[n].add(i)
        for i, mm in enumerate(masked):
            for om in self._NOBJ_OCC_RX.finditer(mm):
                n = om.group(1)
                if n not in cands or n in bad:
                    continue
                if '__addr' in mm or 'null' in mm:
                    bad.add(n)
                    continue
                if i in def_lines[n]:
                    continue
                a, b = om.span()
                if self._NOBJ_AFTER_BAD_RX.match(mm[b:].lstrip()) or \
                        self._NOBJ_BEFORE_BAD_RX.search(mm[:a].rstrip()):
                    bad.add(n)
        cands -= bad
        if not cands:
            return lines
        typ = {}
        stable = False
        for _round in range(32):
            changed = False
            for n in sorted(cands):
                cur = dict(known)
                cur.update(typ)
                cur[n] = typ.get(n, 'int')
                self_rx = re.compile(r'(?<![\w.])%s(?!\w)' % n)
                kinds = [self._nobj_rhs_kind(r, cur) for r in defs[n]]
                ok = bool(kinds) and all(k is not None for k in kinds) and any(
                    k in self._NOBJ_RANK and not self_rx.search(r)
                    for k, r in zip(kinds, defs[n]))
                if ok:
                    nk = max((k for k in kinds if k in self._NOBJ_RANK),
                             key=self._NOBJ_RANK.get)
                    if typ.get(n) != nk:
                        typ[n] = nk
                        changed = True
                elif n in typ:
                    del typ[n]
                    changed = True
            if not changed:
                stable = True
                break
        if not stable or not typ:
            return lines
        bitop = re.compile(r'(?:<<|>>|[&|^~%])')
        for n in [n for n in typ if typ[n] in ('float', 'double')]:
            occ = re.compile(r'(?<![\w.@])%s(?!\w)' % n)
            if any(occ.search(mm) and bitop.search(mm.replace('&&', '').replace('||', ''))
                   for mm in masked):
                del typ[n]
        if not typ:
            return lines
        joined = '\n'.join(lines)
        nxt = {}
        for fam in ('num', 'real'):
            used = [int(x) for x in re.findall(r'(?<![\w.])%s(\d+)(?!\w)' % fam, joined)]
            nxt[fam] = max(used) if used else 0
        ren = {}
        for n in sorted(typ, key=lambda s: int(s[3:])):
            fam = 'real' if typ[n] in ('float', 'double') else 'num'
            nxt[fam] += 1
            ren[n] = '%s%d' % (fam, nxt[fam])
        rx = re.compile(r'(?<![\w.@])(' + '|'.join(re.escape(n) for n in ren) + r')(?!\w)')
        out = []
        for st, mm in zip(lines, masked):
            dm = self._NOBJ_DECL_RX.match(mm)
            if dm and dm.group(1) == 'object' and dm.group(2) in ren:
                a, b = dm.span(1)
                t = typ[dm.group(2)]
                st = st[:a] + t + st[b:]
                mm = mm[:a] + t + mm[b:]
            spans = [x.span() for x in rx.finditer(mm)]
            if spans:
                parts = []
                last = 0
                for a, b in spans:
                    parts.append(st[last:a])
                    parts.append(ren[mm[a:b]])
                    last = b
                parts.append(st[last:])
                st = ''.join(parts)
            out.append(st)
        return out

    _SUB_CALL_RX = re.compile(r'sub_([0-9a-f]+)')
    _STUB_SKIP_TYPES = frozenset(
        ('object', 'System.Object', 'Object', 'void', 'System.Void'))
    _STUB_KEYWORDS = frozenset((
        'if', 'else', 'while', 'do', 'for', 'foreach', 'switch', 'case',
        'default', 'goto', 'return', 'throw', 'try', 'catch', 'finally',
        'using', 'lock', 'fixed', 'checked', 'unchecked', 'const', 'new',
        'yield', 'await', 'var', 'ref', 'in', 'out', 'scoped', 'readonly',
        'volatile', 'typeof', 'sizeof', 'nameof', 'stackalloc'))
    _STUB_DECL_RX = re.compile(
        r'^([A-Za-z_@][\w@.<>,\[\]*? ]*?)\s+([A-Za-z_@]\w*)\s*=\s*(.*);\s*$')
    _STUB_ASSIGN_RX = re.compile(
        r'^([A-Za-z_@]\w*)\s*=\s*(.*);\s*$')
    _STUB_RETURN_RX = re.compile(r'^return\s+(.*);\s*$')
    _STUB_COND_RX = re.compile(r'^(?:else\s+)?(?:if|while)\s*\((.*)\)\s*$')
    _STUB_DOWHILE_RX = re.compile(r'^\}\s*while\s*\((.*)\)\s*;?\s*$')
    _STUB_FOREACH_RX = re.compile(
        r'^foreach\s*\(\s*(.+?)\s+([A-Za-z_@]\w*)\s+in\b')
    _STUB_CATCH_RX = re.compile(
        r'^catch\s*\(\s*(.+?)\s+([A-Za-z_@]\w*)\s*\)')

    @staticmethod
    def _stub_mask_line(s):
        """Length-preserving mask: strings/chars become spaces,
        comments become \x01 (a real // tail stays recognizable).

        The sub_ scanner runs on the mask (same offsets as the line) so
        string contents and comments can never match. Interpolated holes
        mask whole: object interpolates, no cast is needed there.
        """
        out = list(s)
        i, n = 0, len(s)
        while i < n:
            ch = s[i]
            if ch == '/' and i + 1 < n and s[i + 1] == '/':
                for k in range(i, n):
                    out[k] = '\x01'
                break
            if ch == '/' and i + 1 < n and s[i + 1] == '*':
                j = s.find('*/', i + 2)
                j = n if j < 0 else j + 2
                for k in range(i, j):
                    out[k] = '\x01'
                i = j
                continue
            if ch in ('"', "'"):
                verb = i > 0 and (s[i - 1] == '@' or (
                    s[i - 1] == '$' and i > 1 and s[i - 2] == '@'))
                j = i + 1
                while j < n:
                    if verb and s[j] == '"' and j + 1 < n \
                            and s[j + 1] == '"':
                        j += 2
                        continue
                    if not verb and s[j] == '\\' and j + 1 < n:
                        j += 2
                        continue
                    if s[j] == ch:
                        break
                    j += 1
                j = min(j + 1, n)
                for k in range(i, j):
                    out[k] = ' '
                i = j
                continue
            i += 1
        return ''.join(out)

    def _stub_real_names(self):
        """`sub_<hex>` spellings that are REAL metadata method names.

        An obfuscated binary could declare one; those calls resolve for
        real and must never gain a stub or a cast. Empty on this corpus.
        """
        hit = getattr(self, '_stub_real_cache', None)
        if hit is not None:
            return hit
        out = set()
        try:
            for md in self.L.meta.methods:
                nm = md.name or ''
                if nm.startswith('sub_') \
                        and re.fullmatch(r'sub_[0-9a-f]+', nm):
                    out.add(nm[4:])
        except Exception:
            pass
        self._stub_real_cache = frozenset(out)
        return self._stub_real_cache

    @classmethod
    def _stub_type_ok(cls, ty):
        """True when `(ty)` is a well-formed cast spelling for a stub call."""
        t = (ty or '').strip()
        if not t or t in cls._STUB_SKIP_TYPES or '*' in t:
            return False
        if t.startswith('(') or ';' in t or '=' in t:
            return False
        if t.split()[0] in cls._STUB_KEYWORDS:
            return False
        return True

    @classmethod
    def _stub_call_at(cls, masked, pos):
        """Hex VA for a call-name `sub_<hex>` at pos with ident boundaries."""
        m = re.match(r'sub_([0-9a-f]+)', masked[pos:])
        if m is None:
            return None
        if pos > 0 and (masked[pos - 1].isalnum() or masked[pos - 1] in '@_.'):
            return None
        e = pos + m.end()
        if e < len(masked) and (masked[e].isalnum() or masked[e] == '_'):
            return None
        return m.group(1)

    @staticmethod
    def _stub_call_span(masked, va_end):
        """(open, close) of the call parens after a name match, else None."""
        i, n = va_end, len(masked)
        while i < n and masked[i] in ' \t\x01':
            i += 1
        if i >= n or masked[i] != '(':
            return None
        depth = 0
        for k in range(i, n):
            if masked[k] == '(':
                depth += 1
            elif masked[k] == ')':
                depth -= 1
                if depth == 0:
                    return (i, k)
        return None

    @staticmethod
    def _stub_top_qmark(masked, lo, hi):
        """Index of a top-level ternary `?` (never `??`/`?.`), else None."""
        depth = 0
        k = lo
        while k < hi:
            ch = masked[k]
            if ch == '(':
                depth += 1
            elif ch == ')':
                depth -= 1
            elif ch == '?' and depth == 0:
                nxt = masked[k + 1] if k + 1 < hi else ''
                if nxt not in ('?', '.'):
                    return k
                k += 1
            k += 1
        return None

    @staticmethod
    def _stub_top_colon(masked, lo, hi):
        depth = 0
        for k in range(lo, hi):
            if masked[k] == '(':
                depth += 1
            elif masked[k] == ')':
                depth -= 1
            elif masked[k] == ':' and depth == 0 \
                    and (k + 1 >= hi or masked[k + 1] != ':'):
                return k
        return None

    @classmethod
    def _stub_span_has_call(cls, masked, lo, hi):
        pos = lo
        while pos < hi:
            m = cls._SUB_CALL_RX.search(masked, pos, hi)
            if m is None:
                return False
            if cls._stub_call_at(masked, m.start()) is not None:
                return True
            pos = m.end()
        return False

    @staticmethod
    def _stub_top_eq(masked):
        """Index of a top-level plain `=` (never ==/=>/<=/>=/!=/compounds)."""
        depth = 0
        k, n = 0, len(masked)
        while k < n:
            ch = masked[k]
            if ch == '(':
                depth += 1
            elif ch == ')':
                depth -= 1
            elif ch == '=' and depth == 0:
                prev = masked[k - 1] if k > 0 else ''
                nxt = masked[k + 1] if k + 1 < n else ''
                if prev not in ('=', '!', '<', '>', '+', '-', '*', '/',
                                '%', '&', '|', '^') and nxt not in ('=', '>'):
                    return k
            k += 1
        return None

    def _stub_wrap_range(self, code, masked, lo, hi, ty, real, depth=0):
        """Wrap direct-position sub_ calls in masked[lo:hi] with `(ty)`.

        Grammar: CALL | `(...)` | `!`-chain | ternary (whose condition
        must be sub_-free; arms recurse). Anything else declines the
        whole span (None): a partially rewritten value would mix proven
        and unproven needs. Calls nested inside another sub_'s own
        argument list keep the object spelling (params take object).
        """
        if depth > 4:
            return None
        if 'sub_' not in masked[lo:hi]:
            return code[lo:hi]
        a, b = lo, hi
        while a < b and masked[a] in ' \t\x01':
            a += 1
        while b > a and masked[b - 1] in ' \t\x01':
            b -= 1
        if a >= b:
            return None
        bangs = 0
        while a < b and masked[a] == '!':
            bangs += 1
            a += 1
            while a < b and masked[a] in ' \t\x01':
                a += 1
        if a >= b:
            return None
        inner_ty = 'bool' if bangs else ty
        if masked[a] == '(':
            d, k = 0, a
            while k < b:
                if masked[k] == '(':
                    d += 1
                elif masked[k] == ')':
                    d -= 1
                    if d == 0:
                        break
                k += 1
            if k == b - 1:
                inner = self._stub_wrap_range(
                    code, masked, a + 1, b - 1, inner_ty, real, depth + 1)
                if inner is None:
                    return None
                return code[lo:a] + '(' + inner + ')' + code[b:hi]
        q = self._stub_top_qmark(masked, a, b)
        if q is not None:
            c = self._stub_top_colon(masked, q + 1, b)
            if c is None:
                return None
            if self._stub_span_has_call(masked, a, q):
                cond = self._stub_wrap_range(
                    code, masked, a, q, 'bool', real, depth + 1)
                if cond is None:
                    return None
            else:
                cond = code[a:q]
            arm1 = self._stub_wrap_range(
                code, masked, q + 1, c, ty, real, depth + 1)
            arm2 = self._stub_wrap_range(
                code, masked, c + 1, b, ty, real, depth + 1)
            if arm1 is None or arm2 is None:
                return None
            return code[lo:a] + cond + code[q:q + 1] + arm1 + code[c:c + 1] + arm2 + code[b:hi]
        vm = self._stub_call_at(masked, a)
        if vm is None or vm in real:
            return None
        span = self._stub_call_span(masked, a + 4 + len(vm))
        if span is None or span[1] != b - 1:
            return None
        pre = '!' * bangs
        return code[lo:a] + pre + '(%s)' % inner_ty + code[a:b] + code[b:hi]

    def _stub_exact_call(self, masked, lo, hi, real):
        """(start, end) when the span is exactly one sub_ call."""
        a, b = lo, hi
        while a < b and masked[a] in ' \t\x01':
            a += 1
        while b > a and masked[b - 1] in ' \t\x01':
            b -= 1
        if a >= b:
            return None
        vm = self._stub_call_at(masked, a)
        if vm is None or vm in real:
            return None
        span = self._stub_call_span(masked, a + 4 + len(vm))
        if span is None or span[1] != b - 1:
            return None
        return (a, span[1])

    def _stub_assign_types(self, lines, m):
        """name -> unique TYPE text from decls and params."""
        found = {}
        multi = set()

        def add(nm, ty):
            if nm in multi:
                return
            if nm in found:
                if found[nm] != ty:
                    multi.add(nm)
                    del found[nm]
                return
            found[nm] = ty

        for st in lines:
            s = st.strip()
            dm = self._STUB_DECL_RX.match(s)
            if dm is not None:
                ty = dm.group(1).strip()
                if ty.split()[0] not in self._STUB_KEYWORDS:
                    add(dm.group(2), ty)
                continue
            fm = self._STUB_FOREACH_RX.match(s)
            if fm is not None:
                add(fm.group(2), fm.group(1).strip())
                continue
            cm = self._STUB_CATCH_RX.match(s)
            if cm is not None:
                add(cm.group(2), cm.group(1).strip())
        try:
            il = self.L.il
            for p in self.L.meta.method_params(m):
                ty = il.types[p.type] if 0 <= p.type < len(il.types) else None
                if ty is not None:
                    add(p.name, il.type_name(ty))
        except Exception:
            pass
        return found

    def _stub_return_type(self, m):
        """(spelling, is_void) for the enclosing method's return."""
        try:
            il = self.L.il
            rt = il.types[m.return_type] \
                if 0 <= m.return_type < len(il.types) else None
            if rt is None:
                return None, False
            if ((rt[1] >> 16) & 0xFF) == 0x01:
                return None, True
            nm = il.type_name(rt)
            if not self._stub_type_ok(nm):
                return None, False
            return nm, False
        except Exception:
            return None, False

    def _stub_cast_line(self, line, amap, rty, is_void, real):
        """One line rewritten (or split); None to keep it. Never raises."""
        try:
            return self._stub_cast_line_inner(
                line, amap, rty, is_void, real)
        except Exception:
            return None

    def _stub_cast_line_inner(self, line, amap, rty, is_void, real):
        s = line.strip()
        if 'sub_' not in s:
            return None
        masked = self._stub_mask_line(s)
        if 'sub_' not in masked:
            return None
        ind = line[:len(line) - len(line.lstrip())]
        tail = ''
        ci = masked.find('\x01')
        if ci != -1 and s[ci:ci + 2] == '//':
            tail = ' ' + s[ci:].strip()
            s = s[:ci].rstrip()
            masked = masked[:len(s)]
        rm = self._STUB_RETURN_RX.match(s)
        if rm is not None:
            v_lo, v_hi = rm.start(1), rm.end(1)
            if is_void:
                span = self._stub_exact_call(masked, v_lo, v_hi, real)
                if span is None:
                    return None
                call = s[span[0]:span[1] + 1]
                return [ind + call + ';' + tail, ind + 'return;']
            if rty is None or not self._stub_type_ok(rty):
                return None
            new = self._stub_wrap_range(s, masked, v_lo, v_hi, rty, real)
            if new is None or new == s[v_lo:v_hi]:
                return None
            return ind + 'return ' + new + ';' + tail
        cm = self._STUB_COND_RX.match(s)
        if cm is None:
            cm = self._STUB_DOWHILE_RX.match(s)
        if cm is not None:
            v_lo, v_hi = cm.start(1), cm.end(1)
            new = self._stub_wrap_range(s, masked, v_lo, v_hi, 'bool', real)
            if new is None or new == s[v_lo:v_hi]:
                return None
            return ind + s[:v_lo] + new + s[v_hi:] + tail
        dm = self._STUB_DECL_RX.match(s)
        if dm is not None:
            ty = dm.group(1).strip()
            if ty.split()[0] in self._STUB_KEYWORDS \
                    or not self._stub_type_ok(ty):
                return None
            v_lo, v_hi = dm.start(3), dm.end(3)
            if self._stub_top_eq(masked[v_lo:v_hi]) is not None:
                return None
            new = self._stub_wrap_range(s, masked, v_lo, v_hi, ty, real)
            if new is None or new == s[v_lo:v_hi]:
                return None
            return ind + s[:v_lo] + new + s[v_hi:] + tail
        am = self._STUB_ASSIGN_RX.match(s)
        if am is not None:
            ty = amap.get(am.group(1))
            if ty is None or not self._stub_type_ok(ty):
                return None
            v_lo, v_hi = am.start(2), am.end(2)
            new = self._stub_wrap_range(s, masked, v_lo, v_hi, ty, real)
            if new is None or new == s[v_lo:v_hi]:
                return None
            return ind + s[:v_lo] + new + s[v_hi:] + tail
        return None

    _FENCE_CALL_TEXT = 'System.Threading.Thread.MemoryBarrier()'

    @classmethod
    def _fence_trivial_arg(cls, text, masked=None):
        """True when dropping an argument text loses no side effects.

        `masked` is the same argument's masked text (strings/comments
        neutral); the fix-109 typeof-member shape is checked on it so
        quoted text can never shape-match.
        """
        t = (text or '').strip()
        if not t:
            return False
        if re.fullmatch(r'[A-Za-z_@][\w@.]*', t):
            return True
        if masked is not None and cls._fence_typeof_member(
                (masked or '').strip()):
            return True
        if t in ('true', 'false', 'null', 'default'):
            return True
        if cls._fence_bare_typeof(t):
            return True
        if len(t) >= 2 and t[0] == t[-1] and t[0] in ('"', "'") \
                and '{' not in t:
            return True
        try:
            int(t, 0)
            return True
        except ValueError:
            pass
        try:
            c = t
            if c[:1] in ('+', '-'):
                c = c[1:]
            c = c.rstrip('uUlL')
            if c[-1:] in ('f', 'F', 'd', 'D', 'm', 'M'):
                c = c[:-1]
            float(c)
            return True
        except (ValueError, OverflowError):
            return False

    @staticmethod
    def _fence_typeof_end(t):
        """Index of the `)` closing the leading `typeof(`, else None."""
        try:
            m = re.match(r'typeof\s*\(', t)
            if m is None:
                return None
            depth = 0
            j = m.end() - 1
            while j < len(t):
                ch = t[j]
                if ch == '(':
                    depth += 1
                elif ch == ')':
                    depth -= 1
                    if depth == 0:
                        return j
                j += 1
            return None
        except Exception:
            return None

    @staticmethod
    def _fence_bare_typeof(t):
        """True for exactly `typeof(X)` (balanced, whole string).

        The old prefix/suffix spelling also matched `typeof(X).Get()`
        -- a call -- dropping its effects (never fired corpus-wide:
        zero such fence args pre-fix-109, but the hole was real).
        """
        try:
            j = _HighLevelMixin._fence_typeof_end(t)
            return j is not None and j == len(t) - 1
        except Exception:
            return False

    @staticmethod
    def _fence_typeof_member(t):
        """True for exactly `typeof(X).Member` on masked text. -- fix 109

        A single-level static access: no null dereference is possible
        (unlike the already-accepted `obj.f` chains, which can NRE),
        no calls, no indexers, no further member levels. `t` must be
        masked (strings/comments neutral) so quoted text can never
        shape-match. Multi-level paths, calls, indexers, operators,
        and unbalanced input decline.
        """
        try:
            j = _HighLevelMixin._fence_typeof_end(t)
            if j is None or j + 1 >= len(t):
                return False
            return re.fullmatch(r'\.[A-Za-z_@]\w*', t[j + 1:]) is not None
        except Exception:
            return False

    @classmethod
    def _fence_args_clean(cls, code, masked, open_paren, close_paren):
        """True when every argument between the parens is droppable."""
        parts = []
        depth = 0
        cur = ''
        mcur = ''
        k = open_paren + 1
        while k < close_paren:
            ch = masked[k]
            if ch == ',' and depth == 0:
                parts.append((cur, mcur))
                cur = ''
                mcur = ''
            else:
                if ch in '(<[':
                    depth += 1
                elif ch in ')>]':
                    depth = max(0, depth - 1)
                cur += code[k]
                mcur += masked[k]
            k += 1
        parts.append((cur, mcur))
        for text, mtext in parts:
            if not text.strip():
                continue
            if not cls._fence_trivial_arg(text, mtext):
                return False
        return True

    def _fence_is_self(self, m):
        """True when m IS Thread.MemoryBarrier (never self-recurse)."""
        try:
            if (m.name or '') != 'MemoryBarrier':
                return False
            td = self.L.meta.typedefs[m.declaring]
            if ((td.namespace or ''), (td.name or '')) != \
                    ('System.Threading', 'Thread'):
                return False
            return True
        except Exception:
            return True

    def _fence_caller_is_void(self, m):
        try:
            il = self.L.il
            rt = il.types[m.return_type] \
                if 0 <= m.return_type < len(il.types) else None
            return rt is not None and ((rt[1] >> 16) & 0xFF) == 0x01
        except Exception:
            return False

    @staticmethod
    def _fence_temp_dead(masks, idx, nm):
        """True when `nm` occurs nowhere else method-wide (masked)."""
        try:
            for j, mk in enumerate(masks):
                if j == idx or not mk:
                    continue
                if _mentions(mk, nm):
                    return False
            return True
        except Exception:
            return False

    def _fence_redecl_of(self, s, nm):
        """(kind, end) when stripped code line `s` re-declares `nm`.

        Kind 0 is `T nm = ...;` (same-block scope), kind 1 a
        foreach/catch binder (body scope, one deeper). `end` is the
        offset just past the declared name, so the caller can check
        whether the initializer itself reads an outer `nm`.
        Keyword-headed matches (`return x = ...`) are assignments,
        never declarations.
        """
        try:
            dm = self._STUB_DECL_RX.match(s)
            if dm is not None and dm.group(2) == nm:
                if dm.group(1).strip().split()[0] not in self._STUB_KEYWORDS:
                    return (0, dm.end(2))
            fm = self._STUB_FOREACH_RX.match(s)
            if fm is not None and fm.group(2) == nm:
                return (1, fm.end(2))
            cm = self._STUB_CATCH_RX.match(s)
            if cm is not None and cm.group(2) == nm:
                return (1, cm.end(2))
            return None
        except Exception:
            return None

    @staticmethod
    def _fence_line_depths(masks):
        """Brace depth at each line start, or None on any anomaly.

        Runs on masked lines (strings/comments already neutral), so
        every remaining brace is real. A negative depth means the
        text is not balanced single-pass input; callers decline.
        """
        try:
            depths = []
            cur = 0
            for mk in masks:
                lead = 0
                for ch in mk:
                    if ch in ' \t\x01':
                        continue
                    if ch != '}':
                        break
                    lead += 1
                st = cur - lead
                if st < 0:
                    return None
                depths.append(st)
                cur = st + mk.count('{') - (mk.count('}') - lead)
                if cur < 0:
                    return None
            return depths
        except Exception:
            return None

    def _fence_temp_dead_scoped(self, masks, codes, idx, nm, depths):
        """Scope-aware deadness for a fence-called temp. -- fix 108

        The fix-107 method-wide check treats every same-name mention
        as a read, so one colliding scratch temp (sibling scopes
        re-declare: fix 97c) pins all of them. Lexical scoping proves
        more: walking forward from the fence declaration at depth d0,
        a mention reads the fence temp only while no intervening
        re-declaration shadows it -- a same-block `T nm = ...`
        rebinds it away outright, a nested declaration or
        foreach/catch binder shadows its own subtree (tracked as
        depths, pruned as blocks close), and mentions outside the
        fence block decline exactly as before. A re-declaration
        whose own initializer reads an outer `nm`, a `T nm = ...`
        sharing its line with braces (its block depth is unplaceable
        -- binder bodies are always exactly one deeper), or a mention
        after a non-leading `}` (which the line-start depth cannot
        place) all decline too.
        Anything unrecognized declines; success needs zero genuine
        reads. Never raises.
        """
        try:
            if depths is None or idx < 0 or idx >= len(masks):
                return False
            d0 = depths[idx]
            if '{' in masks[idx] or '}' in masks[idx]:
                return False
            shadows = []
            for j in range(idx + 1, len(masks)):
                mk = masks[j]
                dj = depths[j]
                shadows = [sd for sd in shadows if sd <= dj]
                rd = self._fence_redecl_of(codes[j], nm)
                if rd is not None:
                    if dj < d0:
                        # Outer-scope declaration: a different variable
                        # (it neither reads nor rebinds the fence
                        # temp). Only outer non-declaration mentions
                        # decline, below.
                        continue
                    if _mentions(mk[rd[1]:], nm) and not shadows:
                        return False
                    if dj == d0 and rd[0] == 0:
                        if '{' in mk or '}' in mk:
                            return False
                        return True
                    if rd[0] == 0 and ('{' in mk or '}' in mk):
                        return False
                    shadows.append(dj + rd[0])
                    continue
                if not _mentions(mk, nm):
                    continue
                if dj < d0 or not shadows:
                    return False
                # A mention after a non-leading `}` binds shallower
                # than the line-start depth, where a kept shadow may
                # no longer apply -- unplaceable, decline.
                k = 0
                while k < len(mk) and mk[k] in ' \t\x01}':
                    k += 1
                if '}' in mk[k:]:
                    return False
            return True
        except Exception:
            return False

    def _fence_line(self, s, masked, ind, idx, masks, codes, depths,
                    fence_vas, void_m):
        """One line rewritten, split, or None. Never raises."""
        try:
            return self._fence_line_inner(
                s, masked, ind, idx, masks, codes, depths,
                fence_vas, void_m)
        except Exception:
            return None

    def _fence_line_inner(self, s, masked, ind, idx, masks, codes, depths,
                          fence_vas, void_m):
        tail_line = ''
        ci = masked.find('\x01')
        if ci != -1 and s[ci:ci + 2] == '//':
            tail_line = ' ' + s[ci:].strip()
            s = s[:ci].rstrip()
            masked = masked[:len(s)]
        pos, found = 0, None
        while pos < len(masked):
            m = self._SUB_CALL_RX.search(masked, pos)
            if m is None:
                break
            vm = self._stub_call_at(masked, m.start())
            if vm is not None and vm in fence_vas:
                found = (m.start(), vm)
                break
            pos = m.end()
        if found is None:
            return None
        start, va = found
        span = self._stub_call_span(masked, start + 4 + len(va))
        if span is None:
            return None
        rest = s[span[1] + 1:]
        rest_m = masked[span[1] + 1:]
        tail = ''
        is_ret = False
        mb = re.fullmatch(r';([\s\x01]*)', rest_m)
        if mb is not None:
            tail = rest[mb.start(1):]
        elif void_m:
            mr = re.fullmatch(r';\s*return;([\s\x01]*)', rest_m)
            if mr is None:
                return None
            is_ret = True
            tail = rest[mr.start(1):]
        else:
            return None
        head = s[:start]
        if head.strip() == '':
            if not self._fence_args_clean(s, masked, span[0], span[1]):
                return None
            if is_ret:
                return [ind + self._FENCE_CALL_TEXT + ';',
                        ind + 'return;' + tail + tail_line]
            return ind + self._FENCE_CALL_TEXT + ';' + tail + tail_line
        dm = self._STUB_DECL_RX.match(s)
        if dm is None:
            return None
        ty = dm.group(1).strip()
        if ty.split()[0] in self._STUB_KEYWORDS:
            return None
        if self._stub_top_eq(masked[dm.start(3):dm.end(3)]) is not None:
            return None
        nm = dm.group(2)
        v_lo, v_hi = dm.start(3), dm.end(3)
        a, b = v_lo, v_hi
        while a < b and masked[a] in ' \t\x01':
            a += 1
        while b > a and masked[b - 1] in ' \t\x01':
            b -= 1
        if a != start or b - 1 != span[1]:
            return None
        if not self._fence_temp_dead(masks, idx, nm) and \
                not self._fence_temp_dead_scoped(
                    masks, codes, idx, nm, depths):
            return None
        if not self._fence_args_clean(s, masked, span[0], span[1]):
            return None
        return ind + self._FENCE_CALL_TEXT + ';' + tail + tail_line

    def _fence_void_calls(self, lines, m):
        """Name proved fence-thunk calls `Thread.MemoryBarrier()`. -- fix 107

        The thunk (and the fence body itself) provably reads nothing and
        returns nothing, so only positions that need no value rewrite:
        bare statements, void `; return;` tails, and declarations whose
        temp is dead. Deadness is the fix-107 method-wide check plus
        the fix-108 scope-aware check (same-name mentions bound to an
        intervening re-declaration are different variables).
        Arguments must each be side-effect free -- plain values plus
        the fix-109 single-level `typeof(X).Member` static access
        (else the site keeps its stub call); conditions, returns in
        value methods, live temps, and Thread.MemoryBarrier itself
        keep today's rendering. Never raises.
        """
        try:
            if m is None:
                return lines
            fence_vas = set()
            for ln in lines:
                if 'sub_' not in ln:
                    continue
                mk = self._stub_mask_line(ln.strip())
                pos = 0
                while pos < len(mk):
                    mm = self._SUB_CALL_RX.search(mk, pos)
                    if mm is None:
                        break
                    vm = self._stub_call_at(mk, mm.start())
                    if vm is not None and vm not in fence_vas:
                        try:
                            if self.L._fence_target(int(vm, 16)) is not None:
                                fence_vas.add(vm)
                        except Exception:
                            pass
                    pos = mm.end()
            if not fence_vas:
                return lines
            if self._fence_is_self(m):
                return lines
            void_m = self._fence_caller_is_void(m)
            masks = [self._stub_mask_line(ln.strip()) for ln in lines]
            codes = []
            for ln, mk in zip(lines, masks):
                s = ln.strip()
                ci = mk.find('\x01')
                if ci != -1 and s[ci:ci + 2] == '//':
                    s = s[:ci].rstrip()
                codes.append(s)
            depths = self._fence_line_depths(masks)
        except Exception:
            return lines
        out = []
        for idx, ln in enumerate(lines):
            s = ln.strip()
            if 'sub_' not in s:
                out.append(ln)
                continue
            res = self._fence_line(
                s, masks[idx], ln[:len(ln) - len(ln.lstrip())],
                idx, masks, codes, depths, fence_vas, void_m)
            if res is None:
                out.append(ln)
            elif isinstance(res, list):
                out.extend(res)
            else:
                out.append(res)
        return out

    # GPR-passed kinds for == operands. Floats ride XMM (stale GPR
    # slots would print wrong values), structs carry ABI/padding
    # subtleties, open generics prove nothing: all decline.
    _EQ_GPR_KINDS = frozenset((
        0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08, 0x09, 0x0A, 0x0B,
        0x0E, 0x0F, 0x10, 0x12, 0x14, 0x18, 0x19, 0x1C, 0x1D))

    def _eq_addr_info(self, target):
        """Operator proof for a shared address, else None. -- fix 110

        Every candidate must be a static 2-parameter bool method named
        `op_Equality` (with `Equals` twins allowed) or unanimously
        `op_Inequality`. Address-sharing proves the bodies identical,
        so the operator spelling is behavior-exact for whichever owner
        is true -- but only where the operands' own types bind that
        same operator (checked per site, never assumed). Cached: the
        answer is binary-global. Never raises.
        """
        try:
            cache = self.__dict__.setdefault('_eq_addr_cache', {})
            if target in cache:
                return cache[target]
            res = self._eq_addr_info_inner(target)
            cache[target] = res
            return res
        except Exception:
            return None

    def _eq_addr_info_inner(self, target):
        try:
            il = self.L.il
            cands = il.addr_candidates.get(target) if target else None
            if not cands or len(cands) < 2:
                return None
            pairs = []
            names = set()
            for c in cands:
                if c[0] != 'method':
                    return None
                mi = c[1]
                if not 0 <= mi < len(self.L.meta.methods):
                    return None
                m = self.L.meta.methods[mi]
                if not m.is_static:
                    return None
                rt = il.types[m.return_type] \
                    if 0 <= m.return_type < len(il.types) else None
                if rt is None or ((rt[1] >> 16) & 0xFF) != 0x02:
                    return None
                ps = self.L.meta.method_params(m)
                if len(ps) != 2:
                    return None
                pts = []
                for p in ps:
                    pt = il.types[p.type] \
                        if 0 <= p.type < len(il.types) else None
                    if pt is None or not isinstance(pt, tuple):
                        return None
                    pts.append(pt)
                names.add(m.name)
                pairs.append((pts[0], pts[1]))
            if names <= {'op_Equality', 'Equals'} and 'op_Equality' in names:
                op = '=='
            elif names == {'op_Inequality'}:
                op = '!='
            else:
                return None
            return {'op': op, 'pairs': pairs}
        except Exception:
            return None

    def _eq_typedef_map(self):
        """Printed-type-name -> TypeDef index (short names if unique)."""
        try:
            if '_eq_tdmap' in self.__dict__:
                return self.__dict__['_eq_tdmap']
            il = self.L.il
            full = {}
            for td in self.L.meta.typedefs:
                try:
                    nm = il.type_name((td.index, 0x12 << 16))
                except Exception:
                    continue
                if nm and nm != 'object':
                    full[nm] = td.index
            short = {}
            bad = set()
            for nm, ti in full.items():
                sh = nm.split('.')[-1]
                if sh in bad:
                    continue
                if sh in short:
                    del short[sh]
                    bad.add(sh)
                else:
                    short[sh] = ti
            mp = dict(full)
            for sh, ti in short.items():
                mp.setdefault(sh, ti)
            self.__dict__['_eq_tdmap'] = mp
            return mp
        except Exception:
            return {}

    def _eq_field_type(self, td_idx, seg, static_ok):
        """Type tuple for field `seg` on td (+bases), else None.

        Literals (consts) are pure values, allowed under either root.
        Static fields resolve only under a static root; instance
        fields only under an instance root. Derived hides base.
        """
        try:
            il = self.L.il
            chain = il.base_chain_tds(td_idx)
            for ti in chain:
                if not 0 <= ti < len(self.L.meta.typedefs):
                    continue
                td = self.L.meta.typedefs[ti]
                for fi in range(td.field_start,
                                td.field_start + td.field_count):
                    if not 0 <= fi < len(self.L.meta.fields):
                        continue
                    f = self.L.meta.fields[fi]
                    if f.name != seg:
                        continue
                    a = field_attrs(il, f)
                    if a & FA_LITERAL:
                        pass
                    elif static_ok:
                        if not (a & FA_STATIC):
                            continue
                    elif a & FA_STATIC:
                        continue
                    ft = il.types[f.type] \
                        if 0 <= f.type < len(il.types) else None
                    if ft is None or not isinstance(ft, tuple):
                        return None
                    return ft
            return None
        except Exception:
            return None

    def _eq_spelling_td(self, spelling, tdmap):
        """TypeDef for a printed type spelling, else None.

        Generic spellings decline: an open `List<T>`-style map key
        never equals a closed `List<int>` operand spelling, and
        matching one would conflate instantiations.
        """
        try:
            t = (spelling or '').strip()
            if not t or '<' in t:
                return None
            return tdmap.get(t)
        except Exception:
            return None

    @staticmethod
    def _eq_int_literal(t):
        """C# keyword spelling for an integer literal, else None.

        Follows literal typing (first fitting of int / uint / long /
        ulong, suffix-forced); a literal fitting no integral type, or
        any float spelling, declines. The spelling joins normal pair
        matching, so a literal only ever rewrites beside a proven
        same-typed sibling.
        """
        try:
            s = (t or '').strip()
            neg = False
            if s[:1] in ('+', '-'):
                neg = s[:1] == '-'
                s = s[1:]
            if not s:
                return None
            force = None
            low = s.lower()
            if low.endswith(('ul', 'lu')):
                force, s = 'ulong', s[:-2]
            elif low.endswith('u'):
                force, s = 'uint', s[:-1]
            elif low.endswith('l'):
                force, s = 'long', s[:-1]
            if not s:
                return None
            if s[:2] in ('0x', '0X'):
                v = int(s, 16)
            elif s[:2] in ('0b', '0B'):
                v = int(s, 2)
            elif re.fullmatch(r'[0-9]+', s):
                v = int(s, 10)
            else:
                return None
            if neg:
                v = -v
            if force == 'ulong':
                ok = 0 <= v <= 2 ** 64 - 1
            elif force == 'uint':
                ok = 0 <= v <= 2 ** 32 - 1
            elif force == 'long':
                ok = -(2 ** 63) <= v <= 2 ** 63 - 1
            elif force is not None:
                return None
            else:
                ok = True
            if not ok:
                return None
            if force is not None:
                return force
            a = abs(v)
            if a <= 2 ** 31 - 1 or (neg and a == 2 ** 31):
                return 'int'
            if not neg and a <= 2 ** 32 - 1:
                return 'uint'
            if a <= 2 ** 63 - 1 or (neg and a == 2 ** 63):
                return 'long'
            if not neg and a <= 2 ** 64 - 1:
                return 'ulong'
            return None
        except Exception:
            return None

    def _eq_operand_spelling(self, text, mtext, m, declmap, tdmap):
        """Proven operand type spelling, else None. -- fix 110

        String literals spell `string`; bare `this` spells its
        declaring type (reference types only); bare temps read their
        unique method-wide declaration (`_stub_assign_types`:
        multi-declared names are absent, so sibling collisions
        decline); dotted paths walk metadata fields from `this`, a
        temp, or `typeof(X)` (instance/static discipline per root,
        literals allowed). Calls, indexers, operators, addresses,
        generics, and comments decline.
        """
        try:
            il = self.L.il
            t = (text or '').strip()
            mk = (mtext or '').strip()
            if not t or t.startswith('&') or '\x01' in mk:
                return None
            if re.fullmatch(r'"[^"]*"', t):
                return 'string'
            lit = self._eq_int_literal(t)
            if lit is not None:
                return lit
            if t == 'this':
                if m is None or getattr(m, 'is_static', False):
                    return None
                td = m.declaring
                if not 0 <= td < len(self.L.meta.typedefs):
                    return None
                if self.L.meta.typedefs[td].is_valuetype:
                    return None
                return il.type_name((td, 0x12 << 16))
            if re.fullmatch(r'[A-Za-z_@]\w*', t):
                if t in ('true', 'false', 'null', 'typeof'):
                    return None
                if t not in declmap:
                    return None
                return declmap[t].strip() or None
            m0 = re.match(r'typeof\s*\(', t)
            if m0 is not None:
                j = self._fence_typeof_end(t)
                if j is None or not t[j + 1:].startswith('.'):
                    return None
                inner = t[m0.end():j].strip()
                td = self._eq_spelling_td(inner, tdmap)
                if td is None:
                    return None
                tail = t[j + 2:].split('.')
                static_ok = True
            else:
                if not re.fullmatch(r'[A-Za-z_@][\w@.]*', t):
                    return None
                segs = t.split('.')
                if len(segs) < 2:
                    return None
                for sg in segs:
                    if not re.fullmatch(r'[A-Za-z_@]\w*', sg):
                        return None
                if segs[0] == 'this':
                    if m is None or getattr(m, 'is_static', False):
                        return None
                    td = m.declaring
                    if not 0 <= td < len(self.L.meta.typedefs):
                        return None
                    static_ok = False
                else:
                    if segs[0] not in declmap:
                        return None
                    td = self._eq_spelling_td(declmap[segs[0]], tdmap)
                    if td is None:
                        return None
                    static_ok = False
                tail = segs[1:]
            cur = None
            for sg in tail:
                if cur is None:
                    ft = self._eq_field_type(td, sg, static_ok)
                else:
                    td2 = self._eq_spelling_td(cur, tdmap)
                    if td2 is None:
                        return None
                    ft = self._eq_field_type(td2, sg, False)
                if ft is None:
                    return None
                cur = il.type_name(ft)
            return cur
        except Exception:
            return None

    @staticmethod
    def _eq_split_args(code, masked, open_paren, close_paren):
        """[(raw, masked)] top-level comma parts between the parens."""
        try:
            parts = []
            depth = 0
            cur = ''
            mcur = ''
            k = open_paren + 1
            while k < close_paren:
                ch = masked[k]
                if ch == ',' and depth == 0:
                    parts.append((cur, mcur))
                    cur = ''
                    mcur = ''
                else:
                    if ch in '(<[':
                        depth += 1
                    elif ch in ')>]':
                        depth = max(0, depth - 1)
                    cur += code[k]
                    mcur += masked[k]
                k += 1
            parts.append((cur, mcur))
            return parts
        except Exception:
            return None

    @staticmethod
    def _eq_parenize(text, mtext):
        """Operand text, parenthesized unless it binds atomically."""
        try:
            t = (text or '').strip()
            if not t:
                return None
            mk = (mtext or '').strip()
            if re.fullmatch(r'[A-Za-z_@][\w@.]*', mk):
                return t
            if len(t) >= 2 and t[0] == t[-1] and t[0] in ('"', "'"):
                return t
            if _HighLevelMixin._eq_int_literal(t) is not None:
                return t
            if mk.endswith(')'):
                return t
            j = _HighLevelMixin._fence_typeof_end(mk)
            if j is not None and re.fullmatch(
                    r'(?:\.[A-Za-z_@]\w*)+', mk[j + 1:]):
                return t
            return '(' + t + ')'
        except Exception:
            return None

    @staticmethod
    def _eq_paren_span(masked, open_idx):
        """(open, close) of balanced parens at open_idx, else None."""
        try:
            depth = 0
            for k in range(open_idx, len(masked)):
                if masked[k] == '(':
                    depth += 1
                elif masked[k] == ')':
                    depth -= 1
                    if depth == 0:
                        return (open_idx, k)
            return None
        except Exception:
            return None

    @staticmethod
    def _eq_split_bool(masked, lo, hi):
        """Top-level &&/|| operand spans within [lo, hi)."""
        try:
            parts = []
            depth = 0
            cur = lo
            k = lo
            while k < hi:
                ch = masked[k]
                if ch in '(<[':
                    depth += 1
                elif ch in ')>]':
                    depth = max(0, depth - 1)
                elif depth == 0 and (masked.startswith('&&', k)
                                     or masked.startswith('||', k)):
                    parts.append((cur, k))
                    k += 2
                    cur = k
                    continue
                k += 1
            parts.append((cur, hi))
            return parts
        except Exception:
            return None

    def _eq_operand_match(self, masked, olo, ohi, sub_start, call_close):
        """(olo, ohi) when the operand is bangs/parens + call, else None.

        The text before the call may only hold `!`, grouping parens,
        and blanks; the text after only closers and blanks, balanced
        with the opens. Anything else (a comparison, an enclosing
        call's argument list) is a different position. Verified from
        the call span outward, so the call's own parens can never be
        mistaken for grouping.
        """
        try:
            if not (olo <= sub_start and call_close < ohi):
                return None
            for k in range(olo, sub_start):
                if masked[k] not in '!(\t \x01':
                    return None
            for k in range(call_close + 1, ohi):
                if masked[k] not in ')\t \x01':
                    return None
            if masked[olo:sub_start].count('(') != \
                    masked[call_close + 1:ohi].count(')'):
                return None
            return (olo, ohi)
        except Exception:
            return None

    def _eq_line(self, s, masked, ind, m, declmap, tdmap, bool_spell):
        """One line with == / != folded, else None. Never raises."""
        try:
            return self._eq_line_inner(
                s, masked, ind, m, declmap, tdmap, bool_spell)
        except Exception:
            return None

    def _eq_line_inner(self, s, masked, ind, m, declmap, tdmap,
                       bool_spell):
        pos = 0
        while pos < len(masked):
            mm = self._SUB_CALL_RX.search(masked, pos)
            if mm is None:
                return None
            pos = mm.end()
            try:
                va = self._stub_call_at(masked, mm.start())
                info = self._eq_addr_info(
                    int(va, 16)) if va is not None else None
            except Exception:
                va, info = None, None
            if info is None:
                continue
            span = self._stub_call_span(masked, mm.start() + 4 + len(va))
            if span is None:
                continue
            res = self._eq_hit(
                s, masked, ind, m, declmap, tdmap, bool_spell,
                mm.start(), va, info, span)
            if res is not None:
                return res
        return None

    def _eq_hit(self, s, masked, ind, m, declmap, tdmap, bool_spell,
                start, va, info, span):
        ci = masked.find('\x01')
        tail_line = ''
        if ci != -1 and ci > span[1] and s[ci:ci + 2] == '//':
            tail_line = ' ' + s[ci:].strip()
            s = s[:ci].rstrip()
            masked = masked[:len(s)]
        # bool region per position: whole if/while test, bool decl
        # RHS, bool return value. Ternary arms, call arguments, and
        # bare computed-and-dropped statements decline.
        head = s[:start]
        region = None
        cm = re.match(r'^(?:(?:}\s*)?else\s+)?if\s*\(', head) or \
            re.match(r'^\}\s*while\s*\(', head) or \
            re.match(r'^while\s*\(', head)
        if cm is not None:
            test = self._eq_paren_span(masked, cm.end() - 1)
            if test is None:
                return None
            rest = masked[test[1] + 1:]
            ci2 = rest.find('\x01')
            if ci2 != -1:
                rest = rest[:ci2]
            if rest.strip() not in ('', '{'):
                return None
            region = (test[0] + 1, test[1])
        else:
            dm = self._STUB_DECL_RX.match(s)
            if dm is not None and dm.group(1).strip() in bool_spell:
                v_lo, v_hi = dm.start(3), dm.end(3)
                a, b = v_lo, v_hi
                while a < b and masked[a] in ' \t\x01':
                    a += 1
                while b > a and masked[b - 1] in ' \t\x01':
                    b -= 1
                if a < b:
                    region = (a, b)
            if region is None:
                rm = self._STUB_RETURN_RX.match(s)
                if rm is not None and self._eq_caller_is_bool(m):
                    region = (rm.start(1), rm.end(1))
        if region is None:
            return None
        rlo, rhi = region
        if not (rlo <= start and span[1] < rhi):
            return None
        parts = self._eq_split_args(s, masked, span[0], span[1])
        if not parts or len(parts) < 2:
            return None
        (a_raw, a_mk), (b_raw, b_mk) = parts[0], parts[1]
        if not a_raw.strip() or not b_raw.strip():
            return None
        for extra_raw, extra_mk in parts[2:]:
            if not extra_raw.strip():
                continue
            if not self._fence_trivial_arg(extra_raw, extra_mk):
                return None
        sa = self._eq_operand_spelling(a_raw, a_mk, m, declmap, tdmap)
        sb = self._eq_operand_spelling(b_raw, b_mk, m, declmap, tdmap)
        if sa is None or sb is None:
            return None
        hit = None
        for p0, p1 in info['pairs']:
            try:
                ok0 = self.L.il.type_name(p0) == sa
                ok1 = self.L.il.type_name(p1) == sb
            except Exception:
                ok0 = ok1 = False
            if not (ok0 and ok1):
                continue
            if not self._eq_gpr_pair(p0, p1):
                continue
            hit = True
            break
        if hit is None:
            return None
        ops = self._eq_split_bool(masked, rlo, rhi)
        if not ops:
            return None
        match = None
        for olo, ohi in ops:
            if olo <= start and span[1] < ohi:
                match = self._eq_operand_match(
                    masked, olo, ohi, start, span[1])
                break
        if match is None:
            return None
        ns, ne = match
        pa = self._eq_parenize(a_raw, a_mk)
        pb = self._eq_parenize(b_raw, b_mk)
        if pa is None or pb is None:
            return None
        # The [!/(/) layers the match verified stay verbatim; only
        # the call itself becomes the operator.
        pre = s[ns:start]
        post = s[span[1] + 1:ne]
        return ind + s[:ns] + pre + pa + ' ' + info['op'] + ' ' + \
            pb + post + s[ne:] + tail_line

    def _eq_gpr_pair(self, p0, p1):
        """True when both param tuples ride GPRs (no XMM/struct/open)."""
        try:
            for pt in (p0, p1):
                if not isinstance(pt, tuple):
                    return False
                if ((pt[1] >> 16) & 0xFF) not in self._EQ_GPR_KINDS:
                    return False
                if (pt[1] >> 29) & 1:
                    return False
            return True
        except Exception:
            return False

    def _eq_caller_is_bool(self, m):
        try:
            il = self.L.il
            rt = il.types[m.return_type] \
                if m is not None and 0 <= m.return_type < len(il.types) \
                else None
            return rt is not None and ((rt[1] >> 16) & 0xFF) == 0x02
        except Exception:
            return False

    _KEYWORD_TAIL_RX = None  # built lazily: (./->)(keyword)\b

    @classmethod
    def _keyword_tail_rx(cls):
        try:
            if cls._KEYWORD_TAIL_RX is None:
                from il2cpp.names import CSHARP_KEYWORDS
                alts = sorted(CSHARP_KEYWORDS, key=len, reverse=True)
                cls._KEYWORD_TAIL_RX = re.compile(
                    r'(\.|->)(' + '|'.join(alts) + r')\b')
            return cls._KEYWORD_TAIL_RX
        except Exception:
            return None

    def _escape_keywords(self, lines):
        """Escape C# keywords in member tails: `.x` -> `.x_`. -- fix 111

        A reserved word after a dot is never a keyword use, so this is
        textual and safe; strings/comments are neutral on masked lines
        and never match. Matches the emitter side, which routes every
        metadata-name declaration through `safe_ident` (same trailing-
        underscore spelling, same keyword set): declarations and uses
        agree exactly, and non-keyword lines are byte-identical.
        Never raises.
        """
        try:
            rx = self._keyword_tail_rx()
            if rx is None:
                return lines
            out = []
            for ln in lines:
                s = ln.strip()
                if '.' not in s and '->' not in s:
                    out.append(ln)
                    continue
                mk = self._stub_mask_line(s)
                hits = [(m.start(2), m.group(2)) for m in rx.finditer(mk)]
                if not hits:
                    out.append(ln)
                    continue
                ind = ln[:len(ln) - len(ln.lstrip())]
                code = s
                for st, nm in reversed(hits):
                    code = code[:st + len(nm)] + '_' + code[st + len(nm):]
                out.append(ind + code)
            return out
        except Exception:
            return lines

    _NEW_RX = re.compile(r'\bnew\b')

    @staticmethod
    def _nab_bracket_span(masked, open_idx):
        """(open, close) of balanced [...] at open_idx, else None."""
        try:
            depth = 0
            for k in range(open_idx, len(masked)):
                if masked[k] == '[':
                    depth += 1
                elif masked[k] == ']':
                    depth -= 1
                    if depth == 0:
                        return (open_idx, k)
            return None
        except Exception:
            return None

    _NEW_RX = re.compile(r'\bnew\b')

    @staticmethod
    def _nab_bracket_span(masked, open_idx):
        """(open, close) of balanced [...] at open_idx, else None."""
        try:
            depth = 0
            for k in range(open_idx, len(masked)):
                if masked[k] == '[':
                    depth += 1
                elif masked[k] == ']':
                    depth -= 1
                    if depth == 0:
                        return (open_idx, k)
            return None
        except Exception:
            return None

    def _nab_line(self, s, masked, ind):
        """One line with fresh-array brackets repaired, else None."""
        try:
            return self._nab_line_inner(s, masked, ind)
        except Exception:
            return None

    def _nab_line_inner(self, s, masked, ind):
        out = []
        k = 0
        n = len(masked)
        changed = False
        guard = 0
        while k < n:
            guard += 1
            if guard > 4 * n + 16:
                out.append(s[k:])
                break
            m = self._NEW_RX.search(masked, k)
            if m is None:
                out.append(s[k:])
                break
            ns = m.start()
            out.append(s[k:ns])
            k = ns
            q = m.end()
            while q < n and masked[q] in ' \t\x01':
                q += 1
            t = q
            if t >= n or not (masked[t].isalpha() or masked[t] in '@_'):
                out.append(s[k:q])
                k = q
                continue
            adepth = 0
            while t < n:
                ch = masked[t]
                if ch == '<':
                    adepth += 1
                    t += 1
                    continue
                if ch == '>':
                    if adepth == 0:
                        break
                    adepth -= 1
                    t += 1
                    continue
                if adepth > 0:
                    if ch in '();':
                        break
                    t += 1
                    continue
                if ch.isalnum() or ch in '@_.$:?':
                    t += 1
                    continue
                break
            while t < n and masked[t] in ' \t\x01':
                t += 1
            if t >= n or masked[t] != '[':
                # Not an array creation (`new Foo()`, `new Foo Bar`):
                # copy past `new` so any interior stays scannable.
                out.append(s[k:q])
                k = q
                continue
            span = self._nab_bracket_span(masked, t)
            if span is None:
                out.append(s[k:t + 1])
                k = t + 1
                continue
            so, sc = span
            j = sc + 1
            while j < n and masked[j] in ' \t\x01':
                j += 1
            if j < n and masked[j] == '[':
                out.append('(')
                out.append(s[ns:sc + 1])
                out.append(')')
                changed = True
                k = sc + 1
                continue
            if j < n and masked[j] == '(':
                cs = self._eq_paren_span(masked, j)
                if cs is None:
                    out.append(s[k:j + 1])
                    k = j + 1
                    continue
                parts = self._eq_split_args(s, masked, cs[0], cs[1])
                if parts is None or len(
                        [p for p in parts if p[0].strip()]) != 1:
                    out.append(s[k:j + 1])
                    k = j + 1
                    continue
                d = cs[1] + 1
                while d < n and masked[d] in ' \t\x01':
                    d += 1
                if d >= n or masked[d] != '[':
                    out.append(s[k:j + 1])
                    k = j + 1
                    continue
                ds = self._nab_bracket_span(masked, d)
                if ds is None:
                    out.append(s[k:d + 1])
                    k = d + 1
                    continue
                inner = masked[ds[0] + 1:ds[1]].strip().lower()
                if inner not in ('0', '0x0'):
                    out.append(s[k:d + 1])
                    k = d + 1
                    continue
                idx = s[cs[0] + 1:cs[1]].strip()
                out.append('(')
                out.append(s[ns:sc + 1])
                out.append(')[')
                out.append(idx)
                out.append(']')
                changed = True
                k = ds[1] + 1
                continue
            out.append(s[k:q])
            k = q
        if not changed:
            return None
        return ind + ''.join(out)

    def _fresh_array_brackets(self, lines):
        """Parenthesize fresh-array creations before brackets. -- fix 112

        `new T[N][i]` parses as an invalid rank specifier and
        `new T[N](idx)[0]` (single argument, ldelema shape) as an
        invalid call. Wrapping the creation -- `(new T[N])[i]` and
        `(new T[N])[idx]` -- is meaning-preserving everywhere (the
        allocation, size, and index texts survive verbatim) while the
        lines become valid C#. Anything else (multi-arg calls, bare
        `new T[N](args)` without a deref, unbalanced spans) declines.
        Never raises.
        """
        try:
            out = []
            for ln in lines:
                s = ln.strip()
                if 'new' not in s:
                    out.append(ln)
                    continue
                res = self._nab_line(
                    s, self._stub_mask_line(s),
                    ln[:len(ln) - len(ln.lstrip())])
                out.append(ln if res is None else res)
            return out
        except Exception:
            return lines

    def _shared_equality_ops(self, lines, m):
        """Fold unanimous == / != shared calls to operators. -- fix 110

        An address whose every candidate is a static 2-parameter bool
        `op_Equality` (`Equals` twins allowed) or unanimously
        `op_Inequality` executes the same machine code whichever owner
        is true, so the operator spelling is behavior-exact -- with no
        attribution to any one owner. Each operand must still prove
        the exact same operand type for some candidate (string
        literals, uniquely-declared temps, `this`/temp/`typeof`
        member paths through metadata; calls, indexers, operators,
        addresses, generics, and floats/structs decline), and the call
        must sit in a proven-bool position (whole if/while/do-while
        test, top-level &&/|| operand thereof, `bool` declaration
        RHS, bool return). Trailing stale slots must be droppable.
        Never raises.
        """
        try:
            if m is None:
                return lines
            if not any('sub_' in ln for ln in lines):
                return lines
            il = self.L.il
            try:
                bool_spell = {il.type_name((0, 0x02 << 16))}
            except Exception:
                bool_spell = {'bool'}
            masks = [self._stub_mask_line(ln.strip()) for ln in lines]
            codes = [ln.strip() for ln in lines]
            declmap = self._stub_assign_types(lines, m)
            tdmap = self._eq_typedef_map()
        except Exception:
            return lines
        out = []
        for idx, ln in enumerate(lines):
            s = ln.strip()
            if 'sub_' not in s:
                out.append(ln)
                continue
            ind = ln[:len(ln) - len(ln.lstrip())]
            cur_s, cur_mk = s, masks[idx]
            # A line can carry several independent == sites (`a &&
            # b` with two shared calls): rewrite each in turn, back
            # to front is unnecessary since every iteration
            # re-derives spans from the current text. Bounded: a
            # pathological line keeps its remainder.
            for _ in range(4):
                res = self._eq_line(
                    cur_s, cur_mk, ind, m, declmap, tdmap, bool_spell)
                if res is None:
                    break
                cur_s = res[len(ind):] if res.startswith(ind) \
                    else res.strip()
                cur_mk = self._stub_mask_line(cur_s)
            out.append(ind + cur_s if cur_s != s else ln)
        return out

    _RECV_CALL_RX = re.compile(r'^([A-Za-z_]\w*)\.([A-Za-z_]\w*)\s*\(')
    _RECV_STR_RX = re.compile(r'^"(?:[^"\\]|\\.)*"$')
    _RECV_INT_RX = re.compile(r"^(\d+)(u|l|ul|lu)?$", re.IGNORECASE)
    _RECV_FLOAT_RX = re.compile(r"^(\d+\.\d*|\.\d+|\d+)(e[+-]?\d+)?(f|d)?$", re.IGNORECASE)
    # literal kind -> parameter base names with an implicit conversion.
    # Deliberately narrow: floating suffixes, decimals, chars beyond the
    # plain spellings, and null decline (overload resolution would need
    # better-conversion ranking, not just applicability).
    _RECV_NUM_OK = {
        "int-lit": ("sbyte", "byte", "short", "ushort", "int", "uint",
                    "long", "ulong", "float", "double", "object"),
        "uint-lit": ("byte", "ushort", "uint", "ulong", "float", "double",
                     "object"),
        "long-lit": ("long", "ulong", "float", "double", "object"),
        "float-lit": ("float", "double", "object"),
        "double-lit": ("double", "object"),
        "string": ("string", "object"),
        "bool": ("bool", "object"),
        "char-lit": ("char", "ushort", "int", "uint", "long", "ulong",
                     "float", "double", "object"),
    }

    @classmethod
    def _recv_lit_kind(cls, arg):
        a = (arg or "").strip()
        if cls._RECV_STR_RX.match(a):
            return "string"
        if a in ("true", "false"):
            return "bool"
        m = cls._RECV_INT_RX.match(a)
        if m:
            suf = (m.group(2) or "").lower()
            try:
                v = int(m.group(1))
            except Exception:
                return None
            if suf in ("u", "ul", "lu"):
                return "uint-lit" if v <= 2**32 - 1 else None
            if suf == "l":
                return "long-lit" if v <= 2**63 - 1 else None
            if suf:
                return None
            if v <= 2**31 - 1:
                return "int-lit"
            return "uint-lit" if v <= 2**32 - 1 else "long-lit"
        m = cls._RECV_FLOAT_RX.match(a)
        if m:
            suf = (m.group(3) or "").lower()
            if suf == "f":
                return "float-lit"
            if suf in ("", "d"):
                return "double-lit"
            return None
        if len(a) == 3 and a[0] == "'" and a[2] == "'":
            return "char-lit"
        return None

    @staticmethod
    def _recv_split_args(s):
        parts, depth, cur, instr, q = [], 0, "", False, ""
        for ch in s:
            if instr:
                cur += ch
                if ch == q:
                    instr = False
                continue
            if ch in "\"'":
                instr, q, cur = True, ch, cur + ch
            elif ch in "(<[":
                depth += 1
                cur += ch
            elif ch in ")>]":
                depth -= 1
                cur += ch
            elif ch == "," and depth == 0:
                parts.append(cur)
                cur = ""
            else:
                cur += ch
        parts.append(cur)
        return parts

    def _recv_owner_index(self):
        """(name, argc) -> method rows for instance, non-generic,
        non-accessor methods. Built once per decompiler; metadata does not
        change during a build."""
        idx = self.__dict__.get("_recv_owner_index_cache")
        if idx is not None:
            return idx
        idx = {}
        try:
            for mi, m in enumerate(self.L.meta.methods):
                if m.is_static or m.generic_container != -1:
                    continue
                nm = m.name or ""
                if "." in nm or nm.startswith(("get_", "set_", "add_", "remove_")) \
                        or nm in (".ctor", ".cctor"):
                    continue
                try:
                    ps = list(self.L.meta.method_params(m))
                except Exception:
                    continue
                idx.setdefault((nm, len(ps)), []).append(mi)
        except Exception:
            pass
        self.__dict__["_recv_owner_index_cache"] = idx
        return idx

    def _recv_param_ok(self, pt, kind):
        try:
            if ((pt[1] >> 29) & 1) or kind not in self._RECV_NUM_OK:
                return False
            tn = self.L.il.type_name(pt)
            base = tn.split(".")[-1].split("<")[0]
            return base in self._RECV_NUM_OK[kind]
        except Exception:
            return False

    def _recv_has_default(self, m, k):
        try:
            return (m.parameter_start + k) in self.L.meta.param_default_values
        except Exception:
            return False

    def _recv_applicable(self, m, kinds):
        """True when a normal-form call with the given literal kinds can bind
        to m: exact arity by conversion, or fewer args with provable defaults
        for the trailing parameters (a trailing SZARRAY could also take
        `params` expansion, which this honest pass does not model, so any
        larger-arity shape without full defaults declines)."""
        try:
            ps = list(self.L.meta.method_params(m))
        except Exception:
            return False
        if len(kinds) > len(ps):
            return False
        for p, k in zip(ps, kinds):
            pt = self.L.il.types[p.type] if 0 <= p.type < len(self.L.il.types) else None
            if pt is None or not self._recv_param_ok(pt, k):
                return False
        for k in range(len(kinds), len(ps)):
            if not self._recv_has_default(m, k):
                return False
        return True

    def _unique_receiver_owner(self, name, kinds):
        """Declaring-type spelling when exactly one metadata method matches
        (name, literal applicability); else None. Cached per decompiler."""
        try:
            cache = self.__dict__.setdefault("_recv_owner_cache", {})
            key = (name, tuple(kinds))
            if key in cache:
                return cache[key]
            owners = set()
            for mi in self._recv_owner_index().get((name, len(kinds)), []):
                m = self.L.meta.methods[mi]
                if not self._recv_applicable(m, kinds):
                    continue
                td = self.L.meta.typedefs[m.declaring]
                owners.add(self._declaring_type_spelling(td))
            res = next(iter(owners)) if len(owners) == 1 else None
            if res is not None and (not self._stub_type_ok(res) or self._OPEN_PARAM_RX.search(res)):
                res = None
            cache[key] = res
            return res
        except Exception:
            return None

    def _declaring_type_spelling(self, td):
        te = 0x11 if getattr(td, "is_valuetype", False) else 0x12
        return self.L.il.type_name((td.index, (te << 16)))

    def _stub_receiver_types(self, lines):
        """temp -> proven owner type for `object X = sub_(...)` decls whose
        only other mention is one bare `X.Method(literals)` receiver call
        resolving to exactly one metadata owner. Never raises."""
        try:
            return self._stub_receiver_types_inner(lines)
        except Exception:
            return {}

    def _stub_receiver_types_inner(self, lines):
        masked_all = [self._stub_mask_line(l) for l in lines]
        decls = {}
        for i, l in enumerate(lines):
            dm = self._STUB_DECL_RX.match(l.strip())
            if dm is None or dm.group(1).strip() != "object":
                continue
            rhs = dm.group(3)
            if "sub_" not in self._stub_mask_line(rhs):
                continue
            decls.setdefault(dm.group(2), []).append(i)
        out = {}
        for nm, idxs in decls.items():
            if len(idxs) != 1:
                continue
            wpat = (r"[&]\s*NM\b|\bref\s+NM\b|\bout\s+NM\b"
                    r"|\bNM\s*(?:\+\+|--|[+\-*/%%&|^]?=(?![=>]))"
                    r"|(?:\+\+|--)NM\b").replace("NM", re.escape(nm))
            bad = False
            for i, mk in enumerate(masked_all):
                if i == idxs[0]:
                    continue
                if re.search(wpat, mk):
                    bad = True
                    break
            if bad:
                continue
            uses = []
            for i, mk in enumerate(masked_all):
                if i == idxs[0]:
                    continue
                for rm in re.finditer(r"(?<![\w.])([A-Za-z_]\w*)\.([A-Za-z_]\w*)\s*\(", mk):
                    if rm.group(1) == nm:
                        uses.append((i, rm.group(2), rm.end()))
            if len(uses) != 1:
                continue
            _, mname, epos = uses[0]
            mk = masked_all[uses[0][0]]
            depth = 0
            argtext = ""
            # epos sits just past the call's open paren, so the first
            # depth-0 close paren ends the argument span.
            for ch in mk[epos:]:
                if ch == "(":
                    depth += 1
                elif ch == ")":
                    if depth == 0:
                        break
                    depth -= 1
                argtext += ch
            raw = lines[uses[0][0]][epos:epos + len(argtext)]
            # emptiness is judged on raw text: masking blanks literals.
            args = self._recv_split_args(raw) if raw.strip() else []
            kinds = [self._recv_lit_kind(a) for a in args]
            if any(k is None for k in kinds):
                continue
            owner = self._unique_receiver_owner(mname, kinds)
            if owner is not None:
                out[nm] = owner
        return out

    def _stub_receiver_decls(self, lines):
        """Retype proven `object X = sub_(...)` decls so the existing
        caller-proven cast machinery wraps their calls. Never raises."""
        try:
            rmap = self._stub_receiver_types(lines)
        except Exception:
            return lines
        if not rmap:
            return lines
        out = []
        for l in lines:
            dm = self._STUB_DECL_RX.match(l.strip())
            if dm is not None and dm.group(1).strip() == "object" \
                    and dm.group(2) in rmap:
                ind = l[:len(l) - len(l.lstrip())]
                mk = self._stub_mask_line(l)
                semi = mk.rfind(";")
                if semi < 0:
                    out.append(l)
                    continue
                core = l[:semi].rstrip()
                out.append("%s%s;%s" % (ind, rmap[dm.group(2)] + core[len("object"):], l[semi + 1:]))
            else:
                out.append(l)
        return out

    _CONV_CAST_RX = re.compile(r'\(([^()]+)\)sub_([0-9a-f]+)')

    _CONV_NUM_TYPES = frozenset((
        'float', 'int', 'uint', 'long', 'ulong', 'short', 'ushort',
        'byte', 'sbyte', 'char', 'single', 'int32', 'uint32', 'int64',
        'uint64', 'int16', 'uint16', 'byte', 'sbyte', 'char',
    ))

    def _shared_conv_target(self, va, cast):
        """(qualifiedOwner, methodName) for a unanimous conversion family.

        A shared address whose every candidate is a readable
        non-generic static one-parameter conversion (op_Implicit /
        op_Explicit, one shared name, identical parameter tuple,
        non-byref parameter, non-sret returns with distinct type-name
        spellings) executes identical machine code whatever the true
        owner, so a caller-proven `(T)` cast naming exactly one return
        identifies the conversion without guessing among twins (there
        are none by construction: distinct returns). Anything else --
        generics, mixed names/shapes, duplicate returns, an unmatched
        cast -- declines to the honest marker. Never raises.
        """
        try:
            il = self.L.il
            cands = (getattr(il, 'addr_candidates', None) or {}).get(va)
            if not cands or len(cands) < 2:
                return None
            try:
                if va in self._stub_real_names():
                    return None
            except Exception:
                pass
            ms = []
            for c in cands:
                if not isinstance(c, tuple) or len(c) < 2 or c[0] != 'method':
                    return None
                if not (0 <= c[1] < len(self.L.meta.methods)):
                    return None
                ms.append(self.L.meta.methods[c[1]])
            names = {(m.name or '').rpartition('.')[2] for m in ms}
            if len(names) != 1 or names.pop() not in ('op_Implicit', 'op_Explicit'):
                return None
            if any((not m.is_static) or m.param_count != 1
                   or getattr(m, 'generic_container', -1) != -1 for m in ms):
                return None
            try:
                pts = []
                for m in ms:
                    ps = self.L.meta.method_params(m)
                    if len(ps) != 1:
                        return None
                    pt = il.types[ps[0].type] if 0 <= ps[0].type < len(il.types) else None
                    if pt is None or ((pt[1] >> 29) & 1):
                        return None
                    pts.append(pt)
                if any(pt != pts[0] for pt in pts):
                    return None
            except Exception:
                return None
            rets = []
            for m in ms:
                rt = il.types[m.return_type] if 0 <= m.return_type < len(il.types) else None
                if rt is None or il.returns_sret(rt):
                    return None
                try:
                    rn = il.type_name(rt)
                except Exception:
                    return None
                rets.append(rn)
            if len(set(rets)) != len(rets):
                return None
            want = (cast or '').strip()
            if rets.count(want) != 1:
                return None
            m0 = ms[rets.index(want)]
            try:
                td = self.L.meta.typedefs[m0.declaring]
            except Exception:
                return None
            if '`' in (td.name or ''):
                return None
            owner = ('%s.' % td.namespace + td.name) if td.namespace else td.name
            return (owner, m0.name)
        except Exception:
            return None

    @staticmethod
    def _shared_conv_arg_ok(arg, amap):
        """True when a single conversion argument is provably float-taking.

        The native conversion consumes one float register, so a bare
        object-typed temp would compile today (unboxing) and break as
        `T.op(arg)`. Bare tokens need a proven numeric type from the
        assign map; literals need a float/int spelling (never double);
        complex expressions fire (no corpus counterexample -- the wire
        value is the float lane). Never raises.
        """
        try:
            a = (arg or '').strip()
            if not a or a in ('_', '?'):
                return False
            if re.fullmatch(r'[A-Za-z_@]\w*', a):
                ty = (amap or {}).get(a)
                if ty is None:
                    return False
                head = re.split(r'[^A-Za-z0-9_]', ty.strip().split()[0])[-1].lower()
                return head in _HighLevelMixin._CONV_NUM_TYPES
            s = a
            if s[:1] in ('+', '-'):
                s = s[1:].strip()
            if re.fullmatch(r'[0-9A-Za-z_.]+', s):
                try:
                    int(s, 0)
                    return True
                except ValueError:
                    pass
                if s[-1:] in ('f', 'F'):
                    try:
                        float(s[:-1])
                        return True
                    except ValueError:
                        return False
                # single-token double spelling (1.0, 2d): no implicit
                # conversion to the float parameter.
                return False
            # complex expression (calls, arithmetic): the wire value is
            # the float lane; no corpus counterexample. Bare-object
            # temps are declined above.
            return True
        except Exception:
            return False

    def _shared_conv_line(self, line, amap):
        """Rewrite a proven `(T)sub_X/*shared*/(arg)` conversion call.

        The cast is fix-104 caller proof; `_shared_conv_target` adds
        the unanimous-family proof. Emits the owner's conversion call
        and drops the cast (the call now returns T). One bad span
        keeps the line. Never raises.
        """
        try:
            s = line
            masked = self._stub_mask_line(s)
            if 'sub_' not in masked or 'shared body,' not in s:
                return line
            out = []
            pos = 0
            for m in self._CONV_CAST_RX.finditer(masked):
                cast, hx = m.group(1), m.group(2)
                name_end = m.end()
                if not self._stub_type_ok(cast):
                    continue
                pre = masked[:m.start()].rstrip()
                if pre.endswith('!'):
                    continue
                span = self._stub_call_span(masked, name_end)
                if span is None:
                    continue
                if 'shared body,' not in s[name_end:span[0]]:
                    continue
                inner = masked[span[0] + 1:span[1]]
                depth = 0
                parts = []
                last = 0
                bad = False
                for k, ch in enumerate(inner):
                    if ch == '(':
                        depth += 1
                    elif ch == ')':
                        depth -= 1
                        if depth < 0:
                            bad = True
                            break
                    elif ch == ',' and depth == 0:
                        parts.append(inner[last:k])
                        last = k + 1
                if bad:
                    continue
                parts.append(inner[last:])
                if len(parts) != 1:
                    continue
                # map masked arg back: same offsets (mask preserves length)
                a0 = span[0] + 1 + (len(parts[0]) - len(parts[0].lstrip()))
                a1 = span[0] + 1 + len(parts[0].rstrip())
                atext = s[a0:a1] if a1 > a0 else parts[0].strip()
                if not self._shared_conv_arg_ok(atext, amap):
                    continue
                try:
                    va = int(hx, 16)
                except ValueError:
                    continue
                tgt = self._shared_conv_target(va, cast)
                if tgt is None:
                    continue
                owner, mname = tgt
                mname = (mname or '').rpartition('.')[2] or mname
                out.append((m.start(), span[1] + 1, '%s.%s(%s)' % (owner, mname, atext)))
            if not out:
                return line
            res = []
            pos = 0
            for a, b, rep in out:
                if a < pos:
                    return line
                res.append(s[pos:a])
                res.append(rep)
                pos = b
            res.append(s[pos:])
            return ''.join(res)
        except Exception:
            return line

    def _shared_conv_resolve(self, lines, m):
        """Resolve unanimous conversion families at proven casts.

        Runs after `_shared_stub_casts`: `(Angle)sub_182da54f0(...)`
        becomes `Angle.op_Implicit(...)` when every candidate is the
        same one-parameter conversion with distinct returns and the
        cast names exactly one. Bare-object args, doubles, multi-arg
        and unproven shapes keep today's spelling. Never raises.
        """
        try:
            amap = self._stub_assign_types(lines, m)
        except Exception:
            amap = {}
        out = []
        for ln in lines:
            try:
                out.append(self._shared_conv_line(ln, amap))
            except Exception:
                out.append(ln)
        return out

    def _shared_stub_casts(self, lines, m):
        """Caller-proven `(T)` casts over unresolved `sub_X` calls. -- fix 104

        Most shared-body references sit in `TYPE name = sub_X(...)`
        position, where the declaration TYPE is the callee's proven need
        (the object stubs return object for everything else). Whole
        conditions prove `bool`, `return` proves the method's return
        (void splits to call-then-return), plain assignments prove the
        mapped decl type. Only direct value positions rewrite (root,
        ternary arms with sub_-free conditions, `!`-chains, one paren
        layer); anything nested deeper keeps the object spelling, and
        any unparseable span declines the whole line. Real metadata
        `sub_<hex>` names (obfuscated binaries) never stub or cast.
        Never raises: one bad line keeps itself.
        """
        try:
            lines = self._stub_receiver_decls(lines)
        except Exception:
            pass
        try:
            real = self._stub_real_names()
        except Exception:
            real = frozenset()
        try:
            amap = self._stub_assign_types(lines, m)
        except Exception:
            amap = {}
        try:
            rty, is_void = self._stub_return_type(m)
        except Exception:
            rty, is_void = None, False
        out = []
        for ln in lines:
            res = self._stub_cast_line(ln, amap, rty, is_void, real)
            if res is None:
                out.append(ln)
            elif isinstance(res, list):
                out.extend(res)
            else:
                out.append(res)
        return out

    _OPEN_PARAM_RX = re.compile(r'\bT(?:\d+|[A-Z]\w*)?\b')

    @staticmethod
    def _new_rhs_type(rhs):
        """Closed `new` target type carried literally by the RHS, if any."""
        s = (rhs or '').strip()
        if not s.startswith('new '):
            return None
        s = s[4:].strip()
        depth = 0
        cut = len(s)
        for i, ch in enumerate(s):
            if ch == '<':
                depth += 1
            elif ch == '>':
                depth -= 1
                if depth < 0:
                    return None
            elif ch == '(' and depth == 0:
                cut = i
                break
            elif depth == 0 and ch in ('[', ']', '?', ';', '{', '}', '='):
                return None
        ty = s[:cut].strip()
        if not ty or '<' not in ty:
            return None
        if ty.count('<') != ty.count('>'):
            return None
        if not re.fullmatch(r'[A-Za-z_@][\w@.]*\s*<.+>', ty, re.DOTALL):
            return None
        ty = re.sub(r'`\d+(?=<|$)', '', ty).strip()
        return ty or None

    @staticmethod
    def _split_generic(ty):
        """(base, args) for one `Base<A, B>` spelling; ([], base) if not generic."""
        i = ty.find('<')
        if i < 0:
            return ty.strip(), []
        depth = 0
        end = -1
        for j in range(i, len(ty)):
            if ty[j] == '<':
                depth += 1
            elif ty[j] == '>':
                depth -= 1
                if depth == 0:
                    end = j
                    break
        if end < 0:
            return ty.strip(), []
        if ty[end + 1:].strip():
            return ty.strip(), []
        inner = ty[i + 1:end]
        args = []
        d2 = 0
        cur = ''
        for ch in inner:
            if ch == '<':
                d2 += 1
            elif ch == '>':
                d2 -= 1
            if ch == ',' and d2 == 0:
                args.append(cur.strip())
                cur = ''
            else:
                cur += ch
        args.append(cur.strip())
        return ty[:i].strip(), args

    def _type_has_var(self, ty):
        """True when the il2cpp type tuple holds VAR/MVAR at any depth."""
        try:
            il = self.L.il
            bin = il.bin
        except Exception:
            return None
        try:
            from il2cpp.common import u64
        except Exception:
            return None
        def walk(cur, depth):
            if cur is None or depth > 16:
                return None
            if not isinstance(cur, tuple) or len(cur) != 2:
                return None
            data, bits = cur
            te = (bits >> 16) & 0xFF
            if te in (0x13, 0x1e):
                return True
            if 0x01 <= te <= 0x0e or te in (0x16, 0x18, 0x19, 0x1c):
                return False
            if te in (0x11, 0x12, 0x55):
                return False
            if te in (0x0f, 0x10, 0x1d):
                try:
                    inner = il.type_from_ptr(data)
                except Exception:
                    return None
                if inner is None:
                    return None
                return walk(inner, depth + 1)
            if te == 0x14:
                try:
                    o = bin.va2off(data)
                    if o is None:
                        return None
                    ep = u64(bin.d, o)
                    inner = il.type_from_ptr(ep) if ep else None
                except Exception:
                    return None
                if inner is None:
                    return None
                return walk(inner, depth + 1)
            if te == 0x15:
                synth = getattr(il, '_synthetic_lookup', lambda v: None)(data)
                if synth is not None:
                    base_tup, arg_tups = synth
                    rb = walk(base_tup, depth + 1)
                    if rb is True:
                        return True
                    if rb is None:
                        return None
                    for a in arg_tups:
                        ra = walk(a, depth + 1)
                        if ra is True:
                            return True
                        if ra is None:
                            return None
                    return False
                try:
                    o = bin.va2off(data)
                    if o is None:
                        return None
                    basep = u64(bin.d, o)
                    instp = u64(bin.d, o + 8)
                    base = il.type_from_ptr(basep) if basep else None
                    if base is None:
                        return None
                    io = bin.va2off(instp) if instp else None
                    if io is None:
                        return None
                    args = il._argv_type_tuples(u64(bin.d, io), u64(bin.d, io + 8))
                    if args is None:
                        return None
                except Exception:
                    return None
                rb = walk(base, depth + 1)
                if rb is True:
                    return True
                if rb is None:
                    return None
                for a in args:
                    ra = walk(a, depth + 1)
                    if ra is True:
                        return True
                    if ra is None:
                        return None
                return False
            return None
        try:
            return walk(ty, 0)
        except Exception:
            return None

    _OPEN_PARAM_FULL_RX = re.compile(r'T(?:\d+|[A-Z]\w*)?')

    @staticmethod
    def _args_contain_open_param(ty):
        """True when a generic spelling carries a VAR-like argument at any depth."""
        stack = [ty]
        while stack:
            cur = stack.pop()
            try:
                base, args = _HighLevelMixin._split_generic(cur)
            except Exception:
                return False
            bshort = base.split('.')[-1].strip()
            if bshort and re.fullmatch(r'T(?:\d+|[A-Z]\w*)?', bshort):
                if not args:
                    return True
                return True
            for a in args:
                tok = re.sub(r'^(?:ref|out|in)\s+', '', a.strip())
                while True:
                    if tok.endswith('?') or tok.endswith('*'):
                        tok = tok[:-1].strip()
                        continue
                    m = re.search(r'\[[,0-9 ]*\]$', tok)
                    if m:
                        tok = tok[:m.start()].strip()
                        continue
                    break
                if not tok:
                    continue
                if '<' in tok:
                    stack.append(tok)
                else:
                    short = tok.split('.')[-1].strip()
                    if short and re.fullmatch(r'T(?:\d+|[A-Z]\w*)?', short):
                        return True
        return False

    def _closed_rhs_new_type(self, t, tn, rhs):
        """Closed `new` spelling for an open-generic tracked hint, if provable."""
        try:
            if self._type_has_var(t) is not True:
                return None
        except Exception:
            return None
        rhs_ty = self._new_rhs_type(rhs)
        if rhs_ty is None:
            return None
        if self._args_contain_open_param(rhs_ty):
            return None
        if not self._args_contain_open_param(tn):
            return None
        tbase, targs = self._split_generic(tn)
        rbase, rargs = self._split_generic(rhs_ty)
        if not targs or not rargs or len(targs) != len(rargs):
            return None
        tshort = tbase.split('.')[-1].strip()
        rshort = rbase.split('.')[-1].strip()
        if not tshort or tshort != rshort:
            return None
        if '.' in tbase and '.' in rbase and tbase.strip() != rbase.strip():
            return None
        return rhs_ty

    @staticmethod
    def _bare_new_rhs_type(rhs):
        """Closed non-generic `new` target carried literally by the RHS, if any."""
        s = (rhs or '').strip()
        if not s.startswith('new '):
            return None
        s = s[4:].strip()
        depth = 0
        cut = len(s)
        for i, ch in enumerate(s):
            if ch == '<':
                depth += 1
            elif ch == '>':
                depth -= 1
                if depth < 0:
                    return None
            elif ch == '(' and depth == 0:
                cut = i
                break
            elif depth == 0 and ch in ('[', ']', '?', ';', '{', '}', '='):
                return None
        ty = s[:cut].strip()
        if not ty or '<' in ty or '>' in ty:
            return None
        if not re.fullmatch(r'[A-Za-z_@][\w@.]*', ty):
            return None
        # only the last dotted component can be a parameter: qualified
        # names like `TMPro.KerningPair` are closed, never params
        # (fix-98 invariant). A bare T-like target (`new T()`,
        # `new TMP_Character()`) still declines.
        if re.fullmatch(r'T(?:\d+|[A-Z]\w*)?', ty.split('.')[-1].strip()):
            return None
        return ty

    def _bare_closed_new_type(self, t, tn, rhs):
        """Closed `new` spelling for a bare-param hint, if provable. -- fix 101

        A tracked hint that is one bare VAR/MVAR (`T`, `T1`, `TValue` --
        top-level 0x13/0x1e with a matching spelling) names no type at
        all, while the same line's `new ObiPinConstraintsBatch()` /
        `new List<int>()` is the exact closed allocation identity. The
        declaration then takes the RHS spelling: `T x = new C(...)`
        never compiles under any binding of `T` (no implicit conversion
        from `C` to a bare parameter exists even with constraints), so
        the declaration and its member-access uses can only gain
        compilability, and no compiling method contains such a line to
        regress. Decline on non-bare tuples (generic `List<T>` stays
        fix-98 territory), non-bare spellings, unreadable openness,
        open generic RHS (`new List<TKey>()`), bare `new T()` (no
        information) and non-`new`/array/initializer RHS. Only the last
        dotted component decides openness (`TMPro.KerningPair` is
        closed). Never invents a type: the spelling
        comes literally from the emitted RHS.
        """
        try:
            te = (t[1] >> 16) & 0xFF
        except Exception:
            return None
        if not isinstance(t, tuple) or len(t) != 2 or te not in (0x13, 0x1e):
            return None
        if not re.fullmatch(r'T(?:\d+|[A-Z]\w*)?', (tn or '').strip()):
            return None
        try:
            if self._type_has_var(t) is not True:
                return None
        except Exception:
            return None
        rhs_ty = self._new_rhs_type(rhs)
        if rhs_ty is None:
            rhs_ty = self._bare_new_rhs_type(rhs)
        elif self._args_contain_open_param(rhs_ty):
            return None
        return rhs_ty

    def _decl_type_of(self, tok, rhs='') -> str:
        """C# declaration type for one (pre-rename) local token."""
        r = (rhs or '').strip().rstrip(';').strip()
        if r.endswith('.getClass()') or (r.startswith('typeof(') and r.endswith(')')):
            return 'System.Type'      # klass loads hold the runtime type
        t = None
        if tok.startswith('s_'):
            t = self.L.slot_types.get(tok)
        if t is None:
            t = self._var_types.get(tok)
        if t is None:
            t = self.L.__dict__.get('_var_types', {}).get(tok)
        if t is None:
            t = getattr(self.L, '_type_hints', {}).get(tok)
        if not t or not isinstance(t, tuple):
            return 'object'
        try:
            tn = self.L.il.type_name(t)
        except Exception:
            return 'object'
        if tn.startswith('ref '):
            tn = tn[4:]
        tn = re.sub(r'`\d+(?=<|$)', '', tn)   # List`1<T> -> List<T>
        if not tn or tn == 'void':
            return 'object'
        try:
            closed = self._closed_rhs_new_type(t, tn, r)
        except Exception:
            closed = None
        if closed is None:
            try:
                closed = self._bare_closed_new_type(t, tn, r)
            except Exception:
                closed = None
        if closed is not None:
            return closed
        return tn

    _SEM_LOCAL_DECL_RX = re.compile(
        r'^\s*(?!(?:return|throw|yield|case|goto|if|else|while|do|for|'
        r'foreach|switch|using|lock)\b)'
        r'([A-Za-z_@][^=;(){}]*?)\s+(obj\d+)\s*=(?!=)')
    _SEM_LOCAL_FOREACH_RX = re.compile(
        r'^\s*foreach\s*\((.+?)\s+(obj\d+)\s+in\b')

    @staticmethod
    def _semantic_type_prefix(type_text: str) -> Optional[str]:
        """Readable identifier stem proved only by an emitted local type.

        `objN` stays the honesty marker for an untracked `object`.  A local
        whose declaration already says `GameObject`, `System.Type`, `T[]`,
        etc. can be renamed without inventing any new type or value fact.
        """
        t = re.sub(r'^(?:ref|out|in)\s+', '', (type_text or '').strip())
        if not t:
            return None
        # Reject statement fragments and exotic spellings this deliberately
        # small cosmetic pass cannot parse.  Ordinary metadata type names,
        # generics, arrays, pointers and nullable suffixes are sufficient.
        if not re.fullmatch(r'[A-Za-z0-9_@.<>,\[\]*? ]+', t):
            return None
        t = t.replace('global::', '').strip()
        is_array = False
        while re.search(r'\[[,0-9 ]*\]$', t):
            is_array = True
            t = re.sub(r'\[[,0-9 ]*\]$', '', t).strip()
        pointer_depth = 0
        while t.endswith('*'):
            pointer_depth += 1
            t = t[:-1].strip()
        t = t.rstrip('?').strip()
        if not t:
            return None
        if not is_array and not pointer_depth and t in ('object', 'System.Object'):
            return None

        outer = t.split('<', 1)[0].strip()
        simple = re.sub(r'`\d+$', '', outer.rsplit('.', 1)[-1].lstrip('@'))
        simple = simple.strip('_')
        if not simple:
            return None
        if len(simple) > 1 and simple[0] == 'I' and simple[1].isupper():
            simple = simple[1:]

        special = {
            'String': 'text', 'string': 'text',
            'Char': 'character', 'char': 'character',
            'Type': 'type',
            'Boolean': 'flag', 'bool': 'flag',
            'T': 'value', 'TValue': 'value', 'TResult': 'result',
            'TKey': 'key', 'TItem': 'item', 'TElement': 'element',
            'Nullable': 'value', 'ValueTuple': 'tuple',
            'KeyValuePair': 'pair', 'IGrouping': 'group',
        }
        stem = special.get(simple)
        if stem is None:
            words = re.findall(
                r'[A-Z]+(?=[A-Z][a-z]|\d|_|$)|[A-Z]?[a-z]+|\d+',
                simple.replace('__', '_'))
            if not words:
                return None
            stem = words[0].lower() + ''.join(
                word[:1].upper() + word[1:].lower() for word in words[1:])
        if is_array:
            stem += 'Array'
        if pointer_depth:
            stem += 'Ptr' if pointer_depth == 1 else 'Ptr%d' % pointer_depth
        stem = re.sub(r'[^A-Za-z0-9_]', '', stem)[:48]
        return stem if stem and stem != 'obj' else None

    @staticmethod
    def _sub_outside_literals(rx, rep, ln, masked):
        """Match on the mask, splice replacements into the original.

        Twin of the textpass helper (kept local: the two dec mixins
        must not import each other). See there for the contract.
        """
        if isinstance(rx, str):
            rx = re.compile(re.escape(rx))
        out = []
        last = 0
        for m in rx.finditer(masked):
            s, e = m.span()
            m2 = rx.match(ln, s, e)
            if m2 is None:
                continue
            out.append(ln[last:s])
            out.append(m2.expand(rep) if isinstance(rep, str) else rep(m2))
            last = e
        out.append(ln[last:])
        return ''.join(out)

    # one shared precompiled scanner (il2cpp/text.py); textpass uses it too
    _mask_literals = staticmethod(mask_literals)

    @staticmethod
    def _replace_semantic_names(line: str, names: Dict[str, str],
                                in_block_comment: bool) -> Tuple[str, bool]:
        """Replace identifier tokens while preserving literals/comments."""
        out = []
        i = 0
        n = len(line)
        while i < n:
            if in_block_comment:
                j = line.find('*/', i)
                if j < 0:
                    out.append(line[i:])
                    return ''.join(out), True
                out.append(line[i:j + 2])
                i = j + 2
                in_block_comment = False
                continue
            if line.startswith('//', i):
                out.append(line[i:])
                break
            if line.startswith('/*', i):
                in_block_comment = True
                out.append('/*')
                i += 2
                continue
            if line.startswith('@"', i):
                j = i + 2
                while j < n:
                    if line.startswith('""', j):
                        j += 2
                        continue
                    if line[j] == '"':
                        j += 1
                        break
                    j += 1
                out.append(line[i:j])
                i = j
                continue
            c = line[i]
            if c in ('"', "'"):
                delim = c
                j = i + 1
                while j < n:
                    if line[j] == '\\':
                        j += 2
                        continue
                    if line[j] == delim:
                        j += 1
                        break
                    j += 1
                out.append(line[i:j])
                i = j
                continue
            if c.isalpha() or c == '_':
                j = i + 1
                while j < n and (line[j].isalnum() or line[j] == '_'):
                    j += 1
                token = line[i:j]
                out.append(names.get(token, token))
                i = j
                continue
            out.append(c)
            i += 1
        return ''.join(out), in_block_comment

    _SEM_OBJECT_DECL_RX = re.compile(
        r'^(\s*)object\s+(obj\d+)\s*=\s*(.*);\s*$')

    @staticmethod
    def _semantic_explicit_rhs_type(rhs: str) -> Optional[str]:
        """Static reference type carried literally by a small RHS family."""
        r = (rhs or '').strip()
        if re.fullmatch(r'"(?:[^"\\]|\\.)*"', r) \
                or re.fullmatch(r'@"(?:[^"]|"")*"', r):
            return 'string'
        if re.fullmatch(r'typeof\([^()]+\)', r):
            return 'System.Type'
        # `new T[n,m][]` has the static type `T[,][]`.  Array creation is
        # always a reference type, unlike `new T()` where T could be a
        # value type and changing an object local could change boxing.
        match = re.fullmatch(
            r'new\s+([A-Za-z_@][A-Za-z0-9_@.<>, ]*)'
            r'\[([^\[\]]*)\]((?:\[[, ]*\])*)', r)
        if match:
            base, dims, tail = match.groups()
            base = base.strip()
            if re.fullmatch(r'[A-Za-z0-9_@.<>, ]+', base):
                if '<' in dims or '>' in dims:
                    return None
                rank = '[' + (',' * (len(_split_top(dims)) - 1)) + ']'
                return base + rank + tail.replace(' ', '')
        return None

    def _refine_explicit_object_locals(self, lines: List[str]) -> List[str]:
        """Refine single-definition object locals with literal RHS proof.

        Only arrays, strings and exact `typeof` expressions qualify.  A later
        write or any ref/out/in/address escape keeps `object`: stronger typing
        there could reject a valid assignment or change by-reference ABI.
        """
        candidates: Dict[str, Set[str]] = {}
        for line in lines:
            match = self._SEM_OBJECT_DECL_RX.match(line)
            if not match:
                continue
            static_type = self._semantic_explicit_rhs_type(match.group(3))
            if static_type:
                candidates.setdefault(match.group(2), set()).add(static_type)
        if not candidates:
            return lines

        approved = {}
        for token, types in candidates.items():
            if len(types) != 1:
                continue
            escaped = re.compile(
                r'(?:&\s*|\b(?:ref|out|in)\s+)%s\b' % re.escape(token))
            written = re.compile(
                r'(?<![\w.])%s\s*(?:=(?!=)|[-+*/%%&|^]=|<<=|>>=|\+\+|--)'
                % re.escape(token))
            if any(escaped.search(line) for line in lines):
                continue
            if sum(len(written.findall(line)) for line in lines) != 1:
                continue
            approved[token] = next(iter(types))
        if not approved:
            return lines

        out = []
        for line in lines:
            match = self._SEM_OBJECT_DECL_RX.match(line)
            if match and match.group(2) in approved:
                line = '%s%s %s = %s;' % (
                    match.group(1), approved[match.group(2)],
                    match.group(2), match.group(3))
            out.append(line)
        return out

    def _semantic_local_names(self, lines: List[str],
                              method: Optional[MethodDef] = None) -> List[str]:
        """Rename concretely typed `objN` locals at the final render boundary.

        Earlier cleanup passes intentionally depend on the compact
        num/flag/real/obj vocabulary.  Running here preserves every one of
        those analyses and changes identifiers only after the emitted type is
        visible.  Conflicting or `object` declarations stay unchanged.
        """
        lines = self._refine_explicit_object_locals(lines)
        prefixes: Dict[str, Set[str]] = {}
        order = []
        for line in lines:
            match = self._SEM_LOCAL_FOREACH_RX.match(line)
            if match is None:
                match = self._SEM_LOCAL_DECL_RX.match(line)
            if match is None:
                continue
            type_text, token = match.groups()
            prefix = self._semantic_type_prefix(type_text) or ''
            if token not in prefixes:
                prefixes[token] = set()
                order.append(token)
            prefixes[token].add(prefix)

        eligible = [(token, next(iter(prefixes[token]))) for token in order
                    if len(prefixes[token]) == 1 and '' not in prefixes[token]]
        if not eligible:
            return lines

        # Any existing identifier is a conservative collision barrier.  Add
        # metadata parameter names even when an unused parameter never appears
        # in the body: locals may not redeclare one in C#.
        reserved = set()
        in_comment = False
        for line in lines:
            code, in_comment = self._replace_semantic_names(line, {}, in_comment)
            reserved.update(re.findall(r'\b[A-Za-z_]\w*\b', code))
        if method is not None:
            try:
                reserved.update(safe_ident(p.name)
                                for p in self.L.meta.method_params(method))
            except Exception:
                pass

        counts: Dict[str, int] = {}
        names: Dict[str, str] = {}
        for token, prefix in eligible:
            number = counts.get(prefix, 0) + 1
            candidate = '%s%d' % (prefix, number)
            while candidate in reserved:
                number += 1
                candidate = '%s%d' % (prefix, number)
            counts[prefix] = number
            names[token] = candidate
            reserved.add(candidate)

        out = []
        in_comment = False
        for line in lines:
            replaced, in_comment = self._replace_semantic_names(
                line, names, in_comment)
            out.append(replaced)
        return out


    NEG = {'==': '!=', '!=': '==', '<': '>=', '>=': '<', '>': '<=', '<=': '>'}
