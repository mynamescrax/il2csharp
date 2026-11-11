from il2cpp.prelude import *  # noqa: F401,F403
from il2cpp.cfg import _LIT_RX, _in_string


class _LateDecompiler:
    """Late-bound stand-in for il2cpp.dec.Decompiler.

    This module is imported while il2cpp.dec is still initialising, so the
    class is looked up on first attribute use rather than at import time.
    """

    def __getattr__(self, name):
        from il2cpp.dec import Decompiler as _D
        return getattr(_D, name)

    def __setattr__(self, name, value):
        from il2cpp.dec import Decompiler as _D
        setattr(_D, name, value)


Decompiler = _LateDecompiler()

class _SugarMixin:
    def _image_table_fold(self, lines: List[str]) -> List[str]:
        """`*(&data_180000000 + i*4 + T) + &data_180000000` is the runtime's
        RVA function-table idiom: the il2cpp-section tables (invoker/thunk
        pointer arrays) hold rel32 offsets the code reads and rebases to a
        VA. The double-base dance collapses to one named table access; the
        index arithmetic stays exactly as composed."""
        out = []
        for s in lines:
            m = self._IMG_TABLE_RX.search(s)
            if m:
                va = 0x180000000 + int(m.group(2), 16)
                s = s[:m.start()] + '*(data_%x + %s)' % (va, m.group(1)) + s[m.end():]
            out.append(s)
        return out

    def _is_sugar(self, lines: List[str]) -> List[str]:
        """The inlined il2cpp IsInst fast path: a depth pre-check
        (`objType.typeHierarchyDepth < typeof(T).typeHierarchyDepth`, taken
        when definitely-not-T) and the hierarchy check
        (`objType.typeHierarchy[T.depth - 1] != typeof(T)`). With the
        `klass = recv.getClass()` link both become `recv is T`."""
        link = {}
        tlink = {}
        for s in lines:
            m = self._GETCLASS_RX.match(s)
            if m:
                link[m.group(1)] = m.group(2)
            m = re.match(r'^\s*(?:[A-Za-z_][\w.]*\s+)?(\w+) = (typeof\([^)]*\));', s)
            if m:
                tlink[m.group(1)] = m.group(2)[7:-1]

        def ty_of(t: str) -> str:
            # the is-RHS is a type name, not a typeof() expression
            if t.startswith('typeof(') and t.endswith(')'):
                return t[7:-1]
            return tlink.get(t, t)

        def same_t(a: str, b: str) -> bool:
            if a.startswith('typeof('):
                a = a[7:-1]
            if b.startswith('typeof('):
                b = b[7:-1]
            return a == b or tlink.get(a) == tlink.get(b)

        def rw_cond(c: str) -> str:
            m = self._DEPTH_RX.search(c)
            if m:
                k = link.get(m.group(1), m.group(1))
                return c[:m.start()] + '!(%s is %s)' % (k, ty_of(m.group(2))) + c[m.end():]
            m = self._HIER_RX.search(c)
            if m and same_t(m.group(2), m.group(3)):
                k = link.get(m.group(1), m.group(1))
                return c[:m.start()] + '!(%s is %s)' % (k, ty_of(m.group(2))) + c[m.end():]
            return c

        out = []
        for s in lines:
            if '.typeHierarchyDepth' not in s and '.typeHierarchy ' not in s:
                out.append(s)
                continue
            m = re.match(r'^(\s*)(if|while) \((.*)\)\s*$', s)
            if m:
                out.append('%s%s (%s)' % (m.group(1), m.group(2),
                                          rw_cond(m.group(3))))
                continue
            m = re.match(r'^(\s*)return (.*);\s*$', s)
            if m and ('typeHierarchy' in m.group(2)):
                out.append('%sreturn %s;' % (m.group(1), rw_cond(m.group(2))))
                continue
            out.append(s)
        # a rewritten condition no longer names the link temps: drop the
        # `objN = recv.getClass();` / `objN = typeof(T);` decls whose only
        # remaining occurrence is the declaration itself
        drops = set()
        for t in set(link) | set(tlink):
            tr = re.compile(r'(?<![\w.])%s(?![\w])' % re.escape(t))
            if sum(1 for s in out if tr.search(s)) <= 1:
                drops.add(t)
        if drops:
            drx = re.compile(r'^\s*(?:[A-Za-z_][\w.]*(?:<[^=]*?>)?(?:\[\d*\])*(?:\* )?)?(%s) = '
                             % '|'.join(re.escape(d) for d in sorted(drops)))
            out = [s for s in out if not drx.match(s)]
        return out

    # fix 72b: closure-class members start with `<>` (`<>9__1_0`, the
    # `<>c` singleton `<>9`) -- `\w+` never matched them, so a named
    # delegate-cache store was never marked seen and its byte-cast
    # twin (fix 72c) always survived.
    _SF_NAMED_RX = re.compile(
        r'^\s*(typeof\([^)]*\)|[\w.]+)\.((?:<>)*\w+) = (.*);\s*$')
    _SF_BLOB_RX = re.compile(
        r'^\s*((?:typeof\([^)]*\)|[\w.]+)\.__static_fields)(?: \+ (0x[0-9a-f]+|\d+))? = (.*);\s*$')
    # fix 72c: the same twin through the residual-pointer render --
    # the store's address composed through an ADD, so `_render`'s
    # `*(E + N)` spelling became `((byte*)BLOB + N)[0] = v;`
    # (1,403 sites, most of them the __c delegate-cache slot).
    _SF_BCAST_RX = re.compile(
        r'^\s*\(\(byte\*\)((?:typeof\([^)]*\)|[\w.<>]+)\.__static_fields)'
        r'(?: \+ (0x[0-9a-f]+|\d+))?\)\[0\] = (.*);\s*$')
    # fix 72d: the twin's spelling AT DEDUPE TIME is the star-deref
    # store (renamed_locals mints it, _render re-spells it into the
    # byte-cast form at the very end) -- the spelling the original
    # blob regex and the byte-cast regex both miss.
    _SF_BSTAR_RX = re.compile(
        r'^\s*\*\(((?:typeof\([^)]*\)|[\w.<>]+)\.__static_fields)'
        r'(?: \+ (0x[0-9a-f]+|\d+))?\) = (.*);\s*$')

    _CLSINIT_IF_RX = re.compile(
        r'^\s*if \(!?\(?'
        r'((?:typeof\([^)]*\)|[\w.]+)\.initialized'
        r'|\*\((?:obj|num|flag|real)\d+ \+ (?:0xe4|224)\))'
        r'\s*(==|!=)\s*((?:obj|num|flag|real)\d+|0)'
        r'\)?\)?\s*$')
    _CLSINIT_IF2_RX = re.compile(
        r'^\s*if \(!?\(?((?:obj|num|flag|real)\d+)'
        r'\s*(==|!=)\s*'
        r'((?:typeof\([^)]*\)|[\w.]+)\.initialized)'
        r'\)?\)?\s*$')
    _CLSINIT_BODY_RX = re.compile(
        r'^(?:[\w.]+ = )?il2cpp_runtime_class_init\((?:[\w.]+|typeof\([^)]*\))\);$')
    # dead register copies and hoisted klass loads MSVC schedules inside the
    # guard block (both side-effect-free; the block's only live effect is
    # the class-init call itself)
    _CLSINIT_COPY_RX = re.compile(
        r'^(?:obj|num|flag|real)\d+ = (?:(?:obj|num|flag|real)\d+|typeof\([^)]*\));$')
    # a stray `objN = il2cpp_runtime_class_init(...)` outside a stripped
    # guard: the helper returns the klass, so the assignment reads as a
    # plain klass load (which _drop_dead_locals removes once unused)
    _CLSINIT_ASSIGN_RX = re.compile(
        r'^(?:(object|Type)\s+)?(\w+) = il2cpp_runtime_class_init'
        r'\((?:typeof\(([^)]*)\)|([\w.]+))\);$')

    # fix 61c: a 16-bit zero-extension now spells its own mask, so the
    # identity strip has to know both widths. fix 68: the strip itself
    # moved off a character-class regex onto _bzext_strip's balanced-
    # paren walk -- see its docstring, and work/patch_b68_bzext.py.
    _BZEXT_ANCHOR_RX = re.compile(r' & 0xFF(?:FF)?/\*z\*/')
    _BZEXT_KW = frozenset(('if', 'while', 'switch', 'for', 'foreach',
                          'using', 'lock', 'catch', 'fixed'))

    @staticmethod
    def _bzext_strip(s):
        """Zero-extension of a byte is the identity (`b & 0xFF == b`
        for both byte and bool in C#); strip the `/*z*/`-marked mask
        wherever it survives. Two shapes (batch 58 sizing, work/
        census_b68_bzext.py): WRAPPED -- il2csharp.py's `_mk` always
        builds the mask as `(%s & %s/*z*/)`, so a close paren
        immediately follows the marker by construction whenever that
        wrapper is still there -- and BARE -- no wrapper at all,
        because the renderer's own precedence logic (fix 61a) already
        knew none was needed (`x = ok & 0xFF/*z*/;`).
        For the wrapped shape, walk backward from the close paren to
        its TRUE match (nesting-aware, so a call/cast/indexer inside
        the masked expression is transparent to it) rather than
        assuming the first close paren after the marker belongs to
        the mask, then refuse to touch that pair (falling back to
        deleting the marker text alone) whenever it is NOT actually
        the mask's own droppable wrapper: (1) the span between the
        parens holds a top-level comma, or goes negative-depth on a
        stray literal paren -- an enclosing call/group with sibling
        arguments whose own wrapper was already dropped, e.g.
        `Resize(a, b, x & 0xFF/*z*/)` (fix 68); or (2) -- fix 68b,
        found by a unit test, not a build -- what immediately
        PRECEDES the open paren is itself a required delimiter: an
        identifier/`)`/`]`/`>` touching it with no space is call/
        indexer/generic-close syntax, and whitespace then one of
        if/while/switch/for/foreach/using/lock/catch/fixed is a
        statement condition -- both grammatically MANDATORY parens
        that a single-content mask (no comma to catch it under (1))
        can leave looking exactly like a droppable wrapper, e.g.
        `while (canceled & 0xFF/*z*/)`. `return (`/`throw (` end in
        a keyword too but are checked by name and left OPTIONAL --
        C# never requires those parens. String/char literals are
        blanked (length-preserving) before any of this -- a real
        corpus line has a literal `(` inside a string argument that
        would otherwise miscount the walk. Every deletion removes
        only the marker text itself or, when the wrapper is confirmed
        mask-owned, that plus its own matching parens -- never a
        paren belonging to anything else."""
        pos = 0
        while True:
            blank = _LIT_RX.sub(lambda mm: 'x' * len(mm.group(0)), s)
            am = Decompiler._BZEXT_ANCHOR_RX.search(blank, pos)
            if am is None:
                return s
            end = am.end()
            if end < len(blank) and blank[end] == ')':
                depth = 1
                j = end - 1
                open_idx = None
                while j >= 0:
                    c = blank[j]
                    if c == ')':
                        depth += 1
                    elif c == '(':
                        depth -= 1
                        if depth == 0:
                            open_idx = j
                            break
                    j -= 1
                if open_idx is not None:
                    span = blank[open_idx + 1:am.start()]
                    d = 0
                    reject = False
                    for c in span:
                        if c in '([':
                            d += 1
                        elif c in ')]':
                            d -= 1
                            if d < 0:
                                reject = True
                                break
                        elif c == ',' and d == 0:
                            reject = True
                            break
                    if not reject:
                        before = blank[open_idx - 1] if open_idx > 0 else ''
                        if before and before in '=+-*/%&|^!~?:,([{;':
                            pass
                        elif before.isspace():
                            wm = re.search(r'([A-Za-z_]\w*)\s*$', blank[:open_idx])
                            if wm and wm.group(1) in Decompiler._BZEXT_KW:
                                reject = True
                        elif before != '':
                            reject = True
                    if not reject:
                        s = s[:open_idx] + s[open_idx + 1:am.start()] + s[end + 1:]
                        pos = open_idx
                        continue
            s = s[:am.start()] + s[end:]
            pos = am.start()

    _BK_RX = re.compile(r'<([A-Za-z_]\w*)>k__BackingField')
    _STATIC_ADDR_RX = re.compile(
        r'(typeof\(([A-Za-z_][\w.]*(?:<[^()]*>)?)\)\.__static_fields'
        r'(?: \+ (0x[0-9a-fA-F]+|\d+))?)')

    def _member_fold(self, lines: List[str]) -> List[str]:
        """Two render-quality folds, both literal-aware:
        - compiler auto-property fields render as `<Foo>k__BackingField`;
          the diamond/suffix is metadata noise -- the accessor pair IS the
          property, so the field reads `Foo`.
        - a `typeof(T).__static_fields + N` blob whose offset resolves
          through the metadata static-field map reads `typeof(T).field`
          (same as the klass-chain named-store path). Intermediate hops of
          a longer address chain (blob followed by more arithmetic) stay
          raw -- the named form would fold the wrong offset."""
        out = []
        for s in lines:
            parts = re.split(r'("[^"\\]*(?:\\.[^"\\]*)*")', s)
            for k in range(0, len(parts), 2):
                parts[k] = self._fold_static_addrs(parts[k])
                parts[k] = self._BK_RX.sub(r'\1', parts[k])
                # stale receiver parens (fix 40d): a fix-40 fold
                # parenthesized the then-complex receiver, and a
                # rewrite here (accessor -> property) simplified the
                # inside to a plain token/dotted text. `(token).` is
                # never a cast (casts take an operand, not a dot).
                # fix 134e: a `(` glued to `>`/`)`/`]` is a CALL
                # paren (`Find<T>(true).Length`, `f()(x).y`) --
                # stripping it glued callee to argument
                # (`Find<T>true.Length`). Rendered binary operators
                # are space-separated, so `>(` is never `a > (b)`.
                parts[k] = re.sub(r'(?<![\w.>)\]])\(([\w.]+)\)\.', r'\1.', parts[k])
            out.append(''.join(parts))
        return out

    def _fold_static_addrs(self, text):
        m = self._STATIC_ADDR_RX.search(text)
        while m:
            # fix 72b: look PAST whitespace -- rendered chains are
            # space-separated, so the old one-char check saw `' '`
            # and an intermediate `+ N` hop folded anyway (naming
            # the first offset's field for an address past it). The
            # tuple also avoids `'' in '+-*/'` (empty string is a
            # substring of anything), which silently disabled the
            # guard at end-of-string.
            after = text[m.end():].lstrip()[:1]
            if after in ('+', '-', '*', '/'):
                return text
            # fix 72b: a `.` after the blob is the lifter's own
            # unresolved-offset miss spelling (`.__static_N`);
            # naming the blob as its offset-0 field while the
            # suffix claims another offset minted a
            # confidently-wrong name. Leave it honest (fix 72 in
            # il2csharp.py resolves the resolvable ones upstream).
            if after == '.':
                return text
            fi = self._static_field_name(m.group(2), m.group(3))
            if fi is None:
                return text
            start = m.start()
            end = m.end()
            pre = text[start - 1] if start > 0 else ''
            # a `(` immediately before the blob is the enclosing CALL's
            # paren (write_barrier(typeof...) -- do not swallow it; a bare
            # (blob) with a matching `)` after is the blob's own group.
            # `pre == '(' and after == ')'` alone CANNOT tell those apart:
            # in a SINGLE-ARGUMENT call (`NotifyPropertyChanged(blob);`) the
            # `(` is the call's open paren and the `)` is its close paren,
            # and swallowing both glued the callee to its argument
            # (`NotifyPropertyChangedtypeof(X).field;`). The batch-16
            # write_barrier fix only held because that call has a second
            # arg, so `after` was `,`. Disambiguate one char further out: a
            # call paren attaches directly to the callee identifier, a
            # grouping paren never does.
            pre2 = text[start - 2] if start > 1 else ''
            call_paren = bool(pre2) and (pre2.isalnum() or pre2 == '_')
            # fix 58d: this decompiler also spells callees with a trailing
            # annotation -- `Method() /*indirect*/(args)`, `sub_X/*shared
            # body, N candidates*/(args)`. The char before those call
            # parens is `/`, not an identifier char, so the test above
            # read them as grouping parens and glued the callee to its
            # argument. A call paren attaches directly to the callee's
            # closing comment just as it does to its identifier.
            if not call_paren and start > 2 and text[start - 3:start - 1] == '*/':
                call_paren = True
            if pre == '(' and after == ')' and not call_paren:
                start = start - 1
                end = end + 1
            text = '%stypeof(%s).%s%s' % (text[:start], m.group(2), fi,
                                          text[end:])
            m = self._STATIC_ADDR_RX.search(text, start + 10)
        return text

    _SF_DECL_RX = re.compile(r'^([\w.<>\[\], ]+)\s+([A-Za-z_]\w*)\s*=\s*(.+);$')
    _SF_RHS_RX = re.compile(r'^([A-Za-z_]\w*)\.([A-Za-z_]\w*)$')
    _SF_KW = frozenset(
        'this typeof null true false default sizeof nameof checked unchecked'.split())

    def _decl_types(self, lines, masked):
        """Temp/param name -> set of declared type texts (masked scan)."""
        out = {}
        for st, mm in zip(lines, masked):
            m = self._SF_DECL_RX.match(mm)
            if not m:
                continue
            ty, nm = m.group(1).strip(), m.group(2)
            if not nm or nm in self._SF_KW:
                continue
            a, b = m.span(1)
            if st[a:b] != mm[a:b]:
                continue
            out.setdefault(nm, set()).add(ty)
        return out

    def _single_field_assign_fold(self, lines, m):
        """`T t = X.f` -> `T t = X` for single-field structs (F2-C1).

        The lifter renders whole-struct value flows through field-lane
        spellings (`offset._ticks`); when the destination is that same
        single-field struct type, the field hop is provably the whole
        value and the fold removes an uncompilable mismatch. Requires:
        exact one-field typedef (non-enum), the field name matches, the
        base is a bare temp with exactly one declared type equal to T
        (lifeter maps, body decls, or method params), and T is also
        X's recorded type. Mismatched consumers (int/ulong lanes, enums,
        object decls, unknown types, calls, complex bases) keep today's
        spelling. Masked matching keeps literals/comments honest.
        """
        try:
            L = getattr(self, 'L', None)
            il = getattr(L, 'il', None)
            if L is None or il is None:
                return lines
            masked = []
            in_bc = False
            for st in lines:
                mm, in_bc = self._mask_literals(st, in_bc)
                masked.append(mm)
            decls = self._decl_types(lines, masked)
            params = {}
            try:
                if m is not None:
                    for p in L.meta.method_params(m):
                        pn = getattr(p, 'name', None)
                        if pn and pn not in self._SF_KW:
                            params[pn] = p.type
            except Exception:
                params = {}
            out = list(lines)
            for i, (st, mm) in enumerate(zip(lines, masked)):
                m2 = self._SF_DECL_RX.match(mm)
                if m2 is not None:
                    a, b = m2.span(3)
                    if st[a:b] != mm[a:b]:
                        continue
                    t, rhs = m2.group(2), m2.group(3).strip()
                    tds0 = decls.get(t, set())
                    if len(tds0) != 1:
                        continue
                    ttn = next(iter(tds0))
                else:
                    m3 = re.match(r'^([A-Za-z_]\w*)\s*=\s*(.+);$', mm)
                    if not m3:
                        continue
                    t, rhs = m3.group(1), m3.group(2).strip()
                    a, b = m3.span(2)
                    if st[a:b] != mm[a:b]:
                        continue
                    tds0 = decls.get(t, set())
                    if len(tds0) != 1:
                        continue
                    ttn = next(iter(tds0))
                mr = self._SF_RHS_RX.match(rhs)
                if not mr:
                    continue
                x, f = mr.group(1), mr.group(2)
                if x in self._SF_KW:
                    continue
                tdi = self._td_idx_by_name(ttn)
                if tdi is None:
                    continue
                try:
                    tdo = L.meta.typedefs[tdi]
                    chain = il.instance_field_chain(tdi) or {}
                except Exception:
                    continue
                if getattr(tdo, 'is_enum', False) or not getattr(tdo, 'is_valuetype', False) or len(chain) != 1:
                    continue
                try:
                    (foff, (fname, _fti)), = chain.items()
                except Exception:
                    continue
                if fname != f:
                    continue
                xty = self._sf_temp_type(L, decls, params, x)
                if xty is None:
                    continue
                try:
                    xtd = L._td_of(xty) if hasattr(L, '_td_of') else None
                except Exception:
                    xtd = None
                if xtd != tdi:
                    continue
                s0, s1 = mm.find(rhs), mm.find(rhs) + len(rhs)
                out[i] = st[:s0] + x + st[s1:]
            return out
        except Exception:
            return lines

    def _sf_temp_type(self, L, decls, params, x):
        """Il2CppType tuple for temp X, else None (maps, decls, params)."""
        try:
            for mp in ('_var_types', '_type_hints', 'slot_types'):
                try:
                    mm = getattr(L, mp, None)
                    v = mm.get(x) if mm else None
                except Exception:
                    v = None
                if isinstance(v, tuple):
                    return v
            tds = decls.get(x, set())
            if len(tds) == 1:
                tdi = self._td_idx_by_name(next(iter(tds)))
                if tdi is not None:
                    return (tdi, 0x11 << 16)
            if x in params:
                try:
                    pt = L.il.types[params[x]] \
                        if 0 <= params[x] < len(L.il.types) else None
                except Exception:
                    pt = None
                if isinstance(pt, tuple):
                    return pt
        except Exception:
            pass
        return None

    def _td_idx_by_name(self, full):
        # Per INSTANCE, never per class: the values are TypeDef indices, which
        # are binary-local (CLAUDE.md), so a class-level map hands a second
        # Decompiler -- a second fixture -- another binary's indices, and
        # _static_field_name then names another type's static field.
        c = self.__dict__.setdefault('_tdname_cache', None)
        if c is None:
            c = {}
            try:
                for i, td in enumerate(self.L.meta.typedefs):
                    c.setdefault((td.namespace, td.name), i)
            except Exception:
                c = {}
            self.__dict__['_tdname_cache'] = c
        if '.' in full:
            ns, nm0 = full.rsplit('.', 1)
        else:
            ns, nm0 = '', full
        return c.get((ns, nm0))

    def _static_field_name(self, full, off):
        td = self._td_idx_by_name(full)
        if td is None:
            return None
        try:
            sm = self.L.il.static_off_names(td)
        except Exception:
            return None
        if not sm:
            return None
        if off:
            try:
                k = int(off, 16) if off.startswith('0x') else int(off)
            except ValueError:
                return None
        else:
            k = 0
        # fix 72b: static_off_path is the lifter's own resolution
        # authority now -- a direct hit is the field's name, a miss
        # can resolve an inner component through the owning static
        # field's value type (`+ zeroVector_off + 8` -> zeroVector.z).
        ent = self.L.il.static_off_path(td, k)
        return ent[0] if ent is not None else None

    def _sfblob_dedupe(self, lines: List[str]) -> List[str]:
        """The static-field stores render twice: once through the named
        field (`typeof(X).fieldName = v;`, from the klass chain) and once
        through the blob register (`typeof(X).__static_fields + N = v;`,
        the use-count re-render with the type dropped). Keep the named
        one, drop the blob twin that assigns the same value -- but only
        when the key writes one unambiguous offset (Dec F6)."""
        # fix 72c: two-phase -- named twins are collected first, so
        # a blob/byte-cast twin is dropped wherever it sits relative
        # to its named twin (the old single pass kept both when the
        # twin rendered first).
        seen = {}          # (owner, value) -> True
        for s in lines:
            m = self._SF_NAMED_RX.match(s)
            if m and '.__static' not in m.group(2):
                seen[(m.group(1), m.group(3))] = True
        # Dec F6: (owner, value) alone is not the twin's identity -- two
        # static fields of one type can receive the same value. The named
        # store only proves the blob write redundant when that key has a
        # single offset spelling; with several the twin is ambiguous, so
        # keep them all (raw is honest).
        offsets = {}       # (owner, value) -> set of offset spellings
        blob = []          # one match per line, aligned with `lines`
        for s in lines:
            m = self._SF_BLOB_RX.match(s) or self._SF_BSTAR_RX.match(s) \
                or self._SF_BCAST_RX.match(s)
            blob.append(m)
            if m:
                owner = m.group(1)[: -len('.__static_fields')]
                offsets.setdefault((owner, m.group(3)),
                                   set()).add(m.group(2))
        out = []
        for s, m in zip(lines, blob):
            if m:
                owner = m.group(1)[: -len('.__static_fields')]
                key = (owner, m.group(3))
                if seen.get(key) and len(offsets.get(key, ())) <= 1:
                    continue
            out.append(s)
        return out

    def _class_init_strip(self, lines):
        """The runtime's one-time class-init guard: `if (k.initialized == 0) {
        il2cpp_runtime_class_init(k); }` is bookkeeping; drop it. Guards that
        compare the flag against a register temp (the lifter's reads through
        the klass object) or deref the klass pointer directly (`*(objN +
        0xe4) == 0`) are the same shape as long as the guard body's own
        class-init argument is the same klass. The preceding
        `Type objN = typeof(X);` dies in _drop_dead_locals when nothing else
        reads it."""
        out = []
        i, n = 0, len(lines)
        while i < n:
            m = self._CLSINIT_IF_RX.match(lines[i])
            lhs = m.group(1) if m else None
            if not m:
                m2 = self._CLSINIT_IF2_RX.match(lines[i])
                lhs = m2.group(3) if m2 else None
            tok = None
            if m or m2:
                if lhs.startswith('*'):
                    tm = re.match(r'\*\(((?:obj|num|flag|real)\d+) \+', lhs)
                    tok = tm.group(1) if tm else None
                else:
                    tok = lhs[: -len('.initialized')]
                if i + 1 < n and lines[i + 1].strip() == '{':
                    j = i + 2
                    ok = True
                    saw = False
                    while j < n and lines[j].strip() != '}':
                        t = lines[j].strip()
                        if self._CLSINIT_COPY_RX.match(t):
                            pass
                        else:
                            bm = self._CLSINIT_BODY_RX.match(t)
                            if bm:
                                arg = t[t.find('(') + 1:t.rfind(')')]
                                if tok is None or arg == tok:
                                    saw = True
                                else:
                                    ok = False
                                    break
                            else:
                                ok = False
                                break
                        j += 1
                    if ok and saw and (j + 1 >= n or lines[j + 1].strip() != 'else'):
                        i = j + 1
                        continue
            am = self._CLSINIT_ASSIGN_RX.match(lines[i])
            if am:
                if am.group(3):
                    val = 'typeof(%s)' % am.group(3)
                else:
                    val = am.group(4)
                decl = ('%s ' % am.group(1)) if am.group(1) else ''
                lines[i] = '%s%s = %s;' % (decl, am.group(2), val)
            out.append(lines[i])
            i += 1
        return out

    def _bool_sugar(self, lines, m=None):
        """Zero-extension of a byte is the identity in C# (`b & 0xFF` == b
        for byte and bool alike), so the MOVZX noise strips safely; flagN
        locals then read as real booleans. When the current method's return
        type is bool, `return (cond ? 1 : 0);` folds to `return cond;`."""
        if m is not None:
            try:
                rt = self.L.il.types[m.return_type]
                ret_is_bool = bool(rt) and self.L.il._type_enum(rt) == 0x02
            except Exception:
                ret_is_bool = False
        else:
            ret_is_bool = False
        out = []
        for s in lines:
            s = self._bzext_strip(s)
            if ret_is_bool:
                if s in ('return 0;', 'return 1;'):
                    s = 'return true;' if s == 'return 1;' else 'return false;'
                m = re.match(r'^return \(([^?]+?) \? 1 : 0\);$', s)
                if m and (re.search(r'[<>!=]', m.group(1)) or re.fullmatch(r'flag\d+', m.group(1).strip())):
                    s = 'return %s;' % m.group(1)
            # flagN locals are bool by construction: `cond ? 1 : 0` renders
            # of a setcc fold back to the bare condition. The condition must
            # not itself contain a ternary (junk renders from setcc chains
            # like `a ? 1 : 0 | b != 0 ? 1 : 0` stay as-is).
            # flagN locals are bool by construction: `cond ? 1 : 0` renders
            # of a setcc fold back to the bare condition. The plain (no
            # trailing-parens) forms guard with [^?] so a condition that is
            # itself a ternary (junk renders like `a ? 1 : 0 | b != 0 ? 1 : 0`)
            # is never unfolded; the paren-wrapped form was validated
            # tree-wide in earlier batches and stays exactly as is.
            # paren-wrapped forms use the same [^?] guard as the plain
            # ones below: a lazy (.+?) spans a `&`-joined pair of
            # ternaries (`(A ? 1 : 0) & (B ? 1 : 0)`), dropping the outer
            # parens asymmetrically into unparseable text (101899 etc.).
            s = re.sub(r'\b(flag\d+) = \(([^?]+?) \? 1 : 0\);$', r'\1 = \2;', s)
            s = re.sub(r'\bbool (flag\d+) = \(([^?]+?) \? 1 : 0\);$', r'bool \1 = \2;', s)
            s = re.sub(r'\bbool (flag\d+) = ([^?]+?) \? 1 : 0;$', r'bool \1 = \2;', s)
            s = re.sub(r'\b(flag\d+) = ([^?]+?) \? 1 : 0;$', r'\1 = \2;', s)
            s = re.sub(r'\bbool (flag\d+) = ([^?]+?) \? 1 : 0;$', r'bool \1 = \2;', s)
            s = re.sub(r'\b(flag\d+) = 0;$', r'\1 = false;', s)
            s = re.sub(r'\bbool (flag\d+) = 0;$', r'bool \1 = false;', s)
            s = re.sub(r'\b(flag\d+) = 1;$', r'\1 = true;', s)
            s = re.sub(r'\bbool (flag\d+) = 1;$', r'bool \1 = true;', s)
            s = re.sub(r'\b(flag\d+) != 0\b', r'\1', s)
            s = re.sub(r'\b(flag\d+) == 0\b', r'!\1', s)
            out.append(s)
        return out

    _FLAG_DECL_RX = re.compile(r'^bool (flag\d+) = (.*);$')

    def _flag_inline(self, lines: List[str]) -> List[str]:
        """`bool flagN = <cond>; if (flagN)` -> `if (<cond>)`: the branch
        machinery hoists a condition result into a single-use temp
        immediately before its only consumer, the if head (150 decls in
        InventoryManager.cs at b38: 104 `if (flagN)`, 32 `if (!flagN)`,
        14 `if (!(flagN))`; 2,343 AC sites). Fires only when the decl and
        the if are the ONLY literal-aware mentions of the token in the
        body -- any other mention (reassignment, a ternary or later-if
        read, a shadowing redecl, an arm-body read) keeps the temp, which
        also guarantees an impure cond is never evaluated twice. Strict
        adjacency, exact-shape heads only. Loop heads are deliberately
        NOT inlined: the temp holds a value set once that the loop head
        re-reads each iteration, so inlining the condition would
        re-evaluate it -- a semantic change. fix 44; unit mirror
        work/flag_test.py."""
        out = []
        i = 0
        n = len(lines)
        while i < n:
            s = lines[i].strip()
            m = self._FLAG_DECL_RX.match(s)
            if m is None:
                out.append(lines[i])
                i += 1
                continue
            flag = m.group(1)
            j = i + 1
            while j < n and not lines[j].strip():
                j += 1
            neg = None
            if j < n:
                t = lines[j].strip()
                if t == 'if (%s)' % flag:
                    neg = False
                elif t in ('if (!(%s))' % flag, 'if (!%s)' % flag):
                    neg = True
                # 45b: the pre-render head is often the double
                # negation (the branch machinery's setcc feed);
                # _render normalizes it only after every pass
                elif t in ('if (!(!(%s)))' % flag, 'if (!(!%s))' % flag):
                    neg = False
            if neg is None:
                out.append(lines[i])
                i += 1
                continue
            rx = re.compile(r'\b%s\b' % re.escape(flag))
            extra = False
            for k, s2 in enumerate(lines):
                if k in (i, j):
                    continue
                for mm in rx.finditer(s2):
                    if not _in_string(s2, mm.start()):
                        extra = True
                        break
                if extra:
                    break
            if extra:
                out.append(lines[i])
                i += 1
                continue
            cond = m.group(2)
            for _ in range(4):
                if cond[:1] == '(' and cond[-1:] == ')' \
                        and self._paren_wraps_whole(cond):
                    cond = cond[1:-1]
                else:
                    break
            head = 'if (%s)' % (('!(%s)' % cond) if neg else cond)
            indent = lines[j][:len(lines[j]) - len(lines[j].lstrip())]
            out.append(indent + head)
            i = j + 1
        return out

    @staticmethod
    def _paren_wraps_whole(s):
        """True when s starts with '(' and that paren closes exactly at
        the last char -- string-literal aware, so a ')' or '(' inside a
        literal cannot skew the depth count."""
        masked = _LIT_RX.sub(lambda mm: '""' if mm.group(0).startswith('"')
                             else "''", s)
        depth = 0
        for k, c in enumerate(masked):
            if c == '(':
                depth += 1
            elif c == ')':
                depth -= 1
                if depth == 0:
                    return k == len(masked) - 1
        return False

