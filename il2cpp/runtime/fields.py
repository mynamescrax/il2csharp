from il2cpp.prelude import *  # noqa: F401,F403
from il2cpp.common import csharp_type_name, u64
from il2cpp.csharp import FA_LITERAL, FA_STATIC, field_attrs, source_field_name
from il2cpp.names import safe_ident


def _storage_name(il, fi):
    # Preserve the backing-field marker through expression binding. The
    # existing late member fold removes it after evaluation order is fixed.
    name = source_field_name(il, fi)
    raw = il.meta.fields[fi].name
    if name != raw and raw.startswith('<') and raw.endswith('>k__BackingField'):
        return '<' + name + '>k__BackingField'
    return name
from il2cpp.runtime.meta import meta_lit_repr

class _FieldsMixin:
    def decode_slot(self, slot_va) -> Optional[dict]:
        """Decode a lazy metadata usage slot; returns annotation dict."""
        cache = self.__dict__.setdefault('_slot_cache', {})
        if slot_va in cache:
            return cache[slot_va]
        q = self.bin.qword(slot_va)
        r = None
        if q and (q & 1) and (q >> 32) == 0:
            kind = (q >> 29) & 7
            idx = (q & 0x1FFFFFFE) >> 1
            if kind in self.USG_KINDS:
                r = {'kind': kind, 'idx': idx, 'raw': q}
                if kind == 1 or kind == 2:  # TypeInfo / Il2CppType
                    t = self.types[idx] if idx < len(self.types) else None
                    if t:
                        r['type'] = t
                        r['td'] = self.td_of_ty(t)
                        r['text'] = 'typeof(%s)' % self.type_name(t)
                elif kind == 3:  # MethodDef
                    if idx < len(self.meta.methods):
                        r['method'] = idx
                        r['text'] = self.method_simple_name(idx)
                elif kind == 4:  # FieldInfo
                    if idx < len(self.meta.fields):
                        f = self.meta.fields[idx]
                        owner = self._field_owner(idx)
                        r['field'] = idx
                        r['text'] = ('%s.%s' % (owner, _storage_name(self, idx))) if owner else _storage_name(self, idx)
                        r['ftype'] = f.type
                elif kind == 5:  # StringLiteral
                    if idx < len(self.meta.string_literals):
                        r['text'] = meta_lit_repr(self.meta.string_literal(idx))
                elif kind == 6:  # MethodRef
                    r['text'] = self.generic_method_name(idx)
        elif q is None:
            # BSS cell filled at runtime by the il2cpp startup (see
            # scan_runtime_class_cache): the cell caches a well-known
            # Il2CppClass looked up by name
            m = getattr(self, 'bss_usage_map', None)
            r = m.get(slot_va) if m else None
            if r is None:
                ic = getattr(self, 'icall_cells', None)
                sig = ic.get(slot_va) if ic else None
                if sig:
                    ann = self._icall_annotation(sig)
                    if isinstance(ann, dict):
                        # keep the whole annotation: fix 66 needs its
                        # `method` index, not only the rendered text
                        r = dict(ann)
                        r['icall'] = True
        cache[slot_va] = r
        return r

    def scan_icall_cache(self):
        """icall thunk caches: BSS cells caching native function pointers
        resolved from signature strings. The fill site is the fixed shape
        `lea rcx,[rel SIG]; call resolve_icall; mov [rel CELL],rax`, so a
        byte-scan over the code sections maps every CELL to its signature
        and the cell reads render the managed method instead of data_NNN.
        (The usage-slot swallow then hides the lazy-fill guard.)"""
        b = self.bin
        pat = b'\x48\x8d\x0d'      # lea rcx,[rip+disp32]
        from collections import Counter
        cnt = Counter()
        raw_hits = []
        for sec in b.sections:
            if not sec.is_exec or sec.is_bss or sec.rawsize < 32:
                continue
            data = b.read(sec.addr, sec.rawsize)
            if not data:
                continue
            pos = 0
            while True:
                p = data.find(pat, pos)
                if p < 0:
                    break
                pos = p + 1
                # lea rcx,[rel SIG]  (7 bytes)
                # call rel32        (5 bytes, at p+7)
                # mov [rel CELL],rax (7 bytes, at p+12)
                if p + 19 > len(data) or data[p + 7] != 0xE8 \
                        or data[p + 12:p + 15] != b'\x48\x89\x05':
                    continue
                sig_va = sec.addr + p + 7 + int.from_bytes(
                    data[p + 3:p + 7], 'little', signed=True)
                call_tgt = sec.addr + p + 12 + int.from_bytes(
                    data[p + 8:p + 12], 'little', signed=True)
                cell = sec.addr + p + 19 + int.from_bytes(
                    data[p + 15:p + 19], 'little', signed=True)
                raw_hits.append((sig_va, call_tgt, cell))
                cnt[call_tgt] += 1
        if not raw_hits:
            self.icall_cells = {}
            return
        helper = cnt.most_common(1)[0][0]
        self.rt_icall_resolve = helper
        cells = {}
        for sig_va, tgt, cell in raw_hits:
            if tgt != helper:
                continue
            s = b.cstr(sig_va, 512)
            if not s or '::' not in s or len(s) < 5:
                continue
            cells[cell] = s
        self.icall_cells = cells

    def scan_runtime_class_cache(self):
        """The il2cpp runtime caches well-known Il2CppClass pointers
        (MonoType, Type, Thread, Object, ...) in BSS cells filled once by
        name during startup:

            lea r8,[rel NAME] ; lea rdx,[rel names-table] ; mov rcx,[rel base]
            call helper ; mov [rel CELL], rax

        The file image has no bytes at CELL (it lives in the virtual tail of
        .data), so map each cell to the name whose lookup fills it; decode_slot
        then serves reads of [rip+CELL] as typeof(Name) -- and the class-init
        guard swallower recognises them, since the klass arrives with kind 2.
        Store sites are found by byte-pattern (REX.W 89 /r with mod=00 rm=101);
        the feeding name is the nearest preceding lea whose target reads as a
        C string that resolves to a typedef -- the shared names-table lea
        (``"System\0Void\0..."``) fails resolution and is skipped."""
        self.bss_usage_map: Dict[int, dict] = {}
        b = self.bin
        by_name: Dict[str, List[int]] = {}
        for i, td in enumerate(self.meta.typedefs):
            by_name.setdefault(td.name, []).append(i)
        ty_of_td: Dict[int, tuple] = {}
        for t in self.types:
            if t:
                te = (t[1] >> 16) & 0xFF
                if te in (0x11, 0x12) and 0 <= t[0] < len(self.meta.typedefs):
                    ty_of_td.setdefault(t[0], t)
        for sec in b.sections:
            if not sec.is_exec or not sec.rawsize:
                continue
            data = b.d[sec.offset:sec.offset + sec.rawsize]
            for rex in (0x48, 0x4C):
                for reg in range(8):
                    pat = bytes((rex, 0x89, 0x05 | (reg << 3)))
                    pos = data.find(pat)
                    while pos >= 0:
                        disp = int.from_bytes(data[pos + 3:pos + 7], 'little',
                                              signed=True)
                        X = sec.addr + pos + 7 + disp
                        if X not in self.bss_usage_map and b.valid_va(X) \
                                and b.va2off(X) is None:
                            usg = self._runtime_cell_usage(data, pos, sec.addr,
                                                           by_name, ty_of_td)
                            if usg is not None:
                                self.bss_usage_map[X] = usg
                        pos = data.find(pat, pos + 1)

    def _runtime_cell_usage(self, data, pos, sec_addr, by_name, ty_of_td):
        """Name-lookup annotation for one BSS store at data[pos], or None."""
        lo = max(0, pos - 56)
        # a helper call must sit between the name lea and the store
        if data.rfind(b'\xe8', lo, pos) < 0:
            return None
        cands = []
        for rex in (0x48, 0x4C):
            for reg in range(8):
                pat = bytes((rex, 0x8D, 0x05 | (reg << 3)))
                p = data.rfind(pat, lo, pos)
                if p >= 0:
                    disp = int.from_bytes(data[p + 3:p + 7], 'little', signed=True)
                    cands.append((p, sec_addr + p + 7 + disp))
        cands.sort(reverse=True)          # nearest lea first
        for _, tva in cands:
            s = self.bin.cstr(tva, 97)    # the NUL must fall inside the window
            if not s or not (2 <= len(s) <= 96):
                continue
            tds = by_name.get(s)
            if not tds:
                # icall thunk cache: the cell holds a native function pointer
                # resolved from a signature string
                # ("UnityEngine.AndroidJNI::DeleteLocalRef(System.IntPtr)")
                if '::' in s:
                    return self._icall_annotation(s)
                continue
            td_idx = None
            for cand in tds:
                if self.meta.typedefs[cand].namespace == 'System':
                    td_idx = cand
                    break
            if td_idx is None:
                if len(tds) != 1:
                    # Several same-named typedefs and no System candidate:
                    # the stored name string alone does not prove which row
                    # the runtime lookup used, so first-row luck is a
                    # plausible-wrong annotation. Decline it.
                    return None
                td_idx = tds[0]
            td = self.meta.typedefs[td_idx]
            full = ('%s.%s' % (td.namespace, td.name)) if td.namespace else td.name
            # 71c: ty_of_td can miss this type entirely (System.String
            # has no CLASS/VALUETYPE row -- its rows are STRING/
            # SZARRAY forms), which is how typeof(string) arrived with
            # ty=None and every static read off it fell to __static_N.
            # td_idx is known HERE; carry it for the Expr stamp.
            return {'kind': 2, 'text': 'typeof(%s)' % csharp_type_name(full),
                    'type': ty_of_td.get(td_idx), 'td': td_idx}
        return None

    def _declaring_full(self, ti: int) -> Optional[str]:
        """Full name of the type that DECLARES typedef `ti`, or None.

        `Il2CppTypeDefinition.declaringTypeIndex` indexes `self.types`,
        not `meta.typedefs`; the type's `data` field is the outer
        typedef row when its enum is CLASS (0x12) or VALUETYPE (0x11).
        """
        if not (0 <= ti < len(self.meta.typedefs)):
            return None
        d = self.meta.typedefs[ti].declaring
        if not (0 <= d < len(self.types)):
            return None
        t = self.types[d]
        if not t or ((t[1] >> 16) & 0xFF) not in (0x11, 0x12):
            return None
        if not (0 <= t[0] < len(self.meta.typedefs)):
            return None
        return self.typedef_full(t[0])

    def _icall_annotation(self, sig):
        """Method annotation for an icall signature string: resolved to the
        managed method when the declaring type and name exist in metadata,
        else the bare `Type::Method` part of the signature."""
        tpart, sep, mrest = sig.partition('::')
        mname = mrest.split('(', 1)[0]
        if not sep or not mname:
            return None
        if not hasattr(self, '_td_by_full'):
            self._td_by_full: Dict[str, List[int]] = {}
            for i in range(len(self.meta.typedefs)):
                self._td_by_full.setdefault(self.typedef_full(i), []).append(i)
        tds = self._td_by_full.get(tpart) or self._td_by_full.get(
            tpart.replace('/', '.'))
        if not tds and '/' in tpart:
            # fix 66b: `typedef_full` does not qualify a nested type, so a
            # signature naming one (`UnityEngine.ParticleSystem/MainModule`)
            # matches neither the raw form nor the dotted fallback.  Match
            # the inner name and confirm the DECLARING type is the outer one.
            # `declaring` is a TYPE index (not a typedef index -- that is
            # also why typedef_full's own walk never fires for a nested
            # type), so go through `types` to reach the outer typedef row.
            outer, _, inner = tpart.rpartition('/')
            tds = [i for i in (self._td_by_full.get(inner) or [])
                   if self._declaring_full(i) == outer] or None
        if tds:
            cands = []
            for td in tds:
                cands.extend(
                    mi for mi in self.meta.type_methods(self.meta.typedefs[td])
                    if self.meta.methods[mi].name == mname)
            mi = self._icall_pick_overload(sig, cands)
            if mi is not None:
                    m = self.meta.methods[mi]
                    t2 = self.meta.typedefs[m.declaring] \
                        if 0 <= m.declaring < len(self.meta.typedefs) else None
                    if t2 is not None:
                        ns2 = (t2.namespace + '.') if t2.namespace else ''
                        # `method` is the whole point of resolving here:
                        # a call through the cell is a call to THIS
                        # method, and `_call` needs the index (not just
                        # the text) to trim arguments and hint types.
                        return {'kind': 3, 'method': mi, 'icall': True,
                                'text': '%s.%s' % (
                                    csharp_type_name(ns2 + t2.name),
                                    m.name.lstrip('.'))}
        # Unresolved: keep the best-effort name, but spell the separator
        # with `.`. This text is not a comment -- it lands in
        # `regs['RAX']` as an `fptr` Expr and `_call` renders `e.text` as
        # the CALLEE, so `ParticleSystem.MainModule::get_duration(...)`
        # was emitted verbatim. `::` is the namespace-alias qualifier and
        # is only legal after an alias identifier, so `A.B::c` is a hard
        # syntax error; `.` costs no honesty (the name is best-effort
        # either way) and parses.
        return {'kind': 3, 'icall': True,
                'text': '%s.%s' % (csharp_type_name(tpart),
                                   safe_ident(mname.lstrip('.')))}

    _ICALL_PRIM = {
        'System.SByte': 'sbyte', 'System.Byte': 'byte',
        'System.Int16': 'short', 'System.UInt16': 'ushort',
        'System.Int32': 'int', 'System.UInt32': 'uint',
        'System.Int64': 'long', 'System.UInt64': 'ulong',
        'System.Single': 'float', 'System.Double': 'double',
        'System.Boolean': 'bool', 'System.Char': 'char',
        'System.Void': 'void',
    }

    @staticmethod
    def _icall_sig_params(sig):
        """Top-level parameter tokens of an icall signature, or None.

        The runtime's own resolve string spells the callee's full
        parameter list (`Type::Method(System.Type,System.Boolean)`); a
        plain comma split must respect the nesting of generic arguments,
        arrays and pointer groups.
        """
        if not sig:
            return None
        i = sig.find('(')
        if i < 0 or not sig.endswith(')'):
            return None
        inner = sig[i + 1:-1].strip()
        if not inner:
            return []
        out, depth, cur = [], 0, ''
        for ch in inner:
            if ch in '<[(':
                depth += 1
            elif ch in '>])':
                depth -= 1
            if ch == ',' and depth == 0:
                out.append(cur.strip())
                cur = ''
            else:
                cur += ch
        out.append(cur.strip())
        return out

    def _icall_type_key(self, text, byref=False):
        """Normalize one parameter type for signature comparison.

        The signature spells CLI primitives (`System.Int32`) where
        metadata renders C# keywords (`int`), nested types with `/`
        where metadata uses `.`, and generic arity with a backtick
        (`Action`6`) where metadata uses an underscore. The primitive
        substitution runs on token boundaries so nested generic
        arguments and pointer/byref markers stay attached: a pointer is
        not an array, and a byref is not a value.
        """
        t = (text or '').replace('/', '.').replace(' ', '')
        t = re.sub(r'`(\d+)', r'_\1', t)
        for cli, kw in self._ICALL_PRIM.items():
            t = re.sub(r'(?<![\w.])' + re.escape(cli) + r'(?!\w)', kw, t)
        if byref and not t.endswith('&'):
            t += '&'
        return t

    def _icall_pick_overload(self, sig, cands):
        """The one same-named overload whose parameter list matches `sig`.

        The old scan returned the first metadata row with the name, so an
        overload with a different arity seated `_call`'s trim and a real
        native argument disappeared (`UnityEngine.Object::
        FindObjectsOfType(System.Type,System.Boolean)` rendered
        `FindObjectsOfType(type)`; mi 124214's `(sbyte*, int)` rendered
        `ToSByteArray(array)`). The signature string carries the exact
        parameter list, so an overload set is settled by a unique arity,
        or -- among same-arity candidates -- by normalized parameter
        types. Anything else declines to the text-only annotation rather
        than guessing an identity.
        """
        if not cands:
            return None
        want = self._icall_sig_params(sig)
        if want is None:
            return None
        same = [mi for mi in cands
                if 0 <= mi < len(self.meta.methods)
                and self.meta.methods[mi].param_count == len(want)]
        if len(same) == 1:
            return same[0]
        if not same:
            return None
        want_keys = [self._icall_type_key(t) for t in want]
        typed = []
        for mi in same:
            got = []
            for p in self.meta.method_params(self.meta.methods[mi]):
                ty = self.types[p.type] if 0 <= p.type < len(self.types) else None
                got.append(self._icall_type_key(
                    self.type_name(ty) if ty is not None else None,
                    byref=bool(ty is not None and (ty[1] >> 29) & 1)))
            if got == want_keys:
                typed.append(mi)
        return typed[0] if len(typed) == 1 else None

    def _field_owner(self, field_index) -> str:
        cache = self.__dict__.setdefault('_fo_cache', {})
        if field_index in cache:
            return cache[field_index]
        owner = '?'
        lo, hi = 0, len(self.meta.typedefs) - 1
        while lo <= hi:
            mid = (lo + hi) // 2
            t = self.meta.typedefs[mid]
            if field_index < t.field_start:
                hi = mid - 1
            elif field_index >= t.field_start + t.field_count:
                lo = mid + 1
            else:
                owner = self.typedef_full(mid)
                break
        cache[field_index] = owner
        return owner

    def field_offset_map(self, td_index) -> Optional[Dict[int, str]]:
        """instance-field offset -> name for a typedef (own fields only).
        Static fields are skipped: they live in the __static_fields
        blob and their blob offsets collide with instance offsets
        (Vector3.z@0x18 vs static upVector@0x18 -- last-wins here
        silently kept the static)."""
        fo = self.field_offsets[td_index] if td_index < len(self.field_offsets) else None
        td = self.meta.typedefs[td_index]
        if fo is None:
            return None
        m = {}
        for k, off in enumerate(fo):
            fi = td.field_start + k
            if fi < len(self.meta.fields) \
                    and not (field_attrs(self, self.meta.fields[fi])
                             & (FA_STATIC | FA_LITERAL)):
                m[off] = _storage_name(self, fi)
        return m

    _chain_cache: Dict[int, Optional[Dict[int, tuple]]] = {}

    def value_type_size(self, td_index) -> Optional[int]:
        """sizeof() a value type, object header excluded, straight from
        Il2CppMetadataRegistration.typeDefinitionsSizes -- exact, unlike
        the field-offset guessing this codebase used before (a struct
        whose single field is itself a 64-byte struct has one field at
        offset 0x10 and no larger offset anywhere). None when the size
        is not knowable statically: an open generic definition stores 0.
        """
        ts = getattr(self, 'type_sizes', None)
        if not ts or not (0 <= td_index < len(ts)):
            return None
        return ts[td_index]

    def op_collision_conv(self, td_idx, name, ptypes):
        """'explicit'/'implicit' when static op_ twins sharing (td, name,
        param types) have 2+ distinct returns (Decimal.op_Explicit x4),
        else None. Same name+params cannot coexist as methods (CS0111);
        C# spells the whole group as conversion operators. Byref groups
        are included with the `ref` dropped: user operators cannot take
        ref params, and the real sources take these views by value (a
        pure view read; a mutating conversion would be pathological).
        Cached per Il2Cpp lifetime; metadata never changes during a
        build. ponytail: one shared proof for emitter decls and lifter
        call recasts; singletons cost one dict hit."""
        try:
            key = tuple((self.type_name(t), bool((t[1] >> 29) & 1)) for t in ptypes)
        except Exception:
            return None
        try:
            cache = getattr(self, '_op_collision_cache', None)
            if cache is None:
                cache = self._op_collision_cache = {}
            tbl = cache.get(td_idx)
            if tbl is None:
                tbl = {}
                td = self.meta.typedefs[td_idx] \
                    if 0 <= td_idx < len(self.meta.typedefs) else None
                if td is not None:
                    for mj in self.meta.type_methods(td):
                        m3 = self.meta.methods[mj]
                        if m3.name not in ('op_Explicit', 'op_Implicit') or not m3.is_static:
                            continue
                        try:
                            p3 = self.meta.method_params(m3)
                            k3 = tuple((self.type_name(self.types[p.type]), bool((self.types[p.type][1] >> 29) & 1)) for p in p3)
                            r3 = self.type_name(self.types[m3.return_type])
                        except Exception:
                            continue
                        tbl.setdefault((m3.name, k3), set()).add(r3)
                cache[td_idx] = tbl
            rets = tbl.get((name, key), set())
            if len(rets) < 2:
                return None
            return 'explicit' if name == 'op_Explicit' else 'implicit'
        except Exception:
            return None

    def returns_sret(self, rty) -> bool:
        """Does a call returning `rty` spend an argument register on a
        hidden return buffer? Win64/MSVC returns a trivially copyable
        struct of size 1, 2, 4 or 8 by value (in RAX, or XMM0 when it is
        all floats -- either way no buffer) and everything else through a
        caller-supplied pointer in the FIRST argument slot, which shifts
        the receiver and every parameter one register right.

        Disasm ground truth (work/probe_b51_sretabi.py):
          Panel.get_IMGUIEventInterests 0x182ef7bc0, size 3, instance,
            no parameters -- `movzx eax,word [rdx+188h]; mov [rcx],ax;
            ...; mov rax,rcx`: RCX is the buffer, `this` is RDX, and the
            buffer comes back in RAX. 3 is not one of the by-value sizes,
            which is exactly what a field-offset guess cannot see.
          TimeZoneInfo.get_BaseUtcOffset 0x18063aab0, size 8, instance --
            `mov rax,[rcx+30h]; ret`: RCX is `this`, no buffer at all.
          AdjustmentRule.get_DaylightTransitionStart 0x180935e40, size 24
            -- buffer RCX, `this` RDX, `mov rax,rcx`.

        A GENERICINST (0x15) return uses the hidden buffer exactly when
        its closed layout proves a non-trivial size (S6: the 72-byte
        closed Enumerator); anything unproven keeps the old stand-down
        (fix 54), as do by-value sizes and byref returns.
        """
        if rty is None:
            return False
        bits = rty[1]
        if (bits >> 29) & 1:
            return False               # byref: a pointer, comes back in RAX
        te = (bits >> 16) & 0xFF
        if te == 0x15:
            sz = self._sf_field_size(rty, 0)
            if sz is None:
                return False
            return sz not in (1, 2, 4, 8)
        if te != 0x11:
            return False
        sz = self.value_type_size(rty[0])
        if sz is None:
            return True                # unknown size: keep the old
                                       # unconditional-shift behaviour
        return sz not in (1, 2, 4, 8)

    def instance_field_chain(self, td_index) -> Optional[Dict[int, tuple]]:
        """offset -> (name, field type idx) merged over the whole base chain."""
        if td_index in self._chain_cache:
            return self._chain_cache[td_index]
        merged: Dict[int, tuple] = {}
        cur = td_index
        hops = 0
        while cur is not None and 0 <= cur < len(self.meta.typedefs) and hops < 16:
            td = self.meta.typedefs[cur]
            fo = self.field_offsets[cur] if cur < len(self.field_offsets) else None
            if fo and not td.is_valuetype:
                # fix 133: an open generic class level stores all-zero
                # instance offsets; lay it out (or skip it) instead of
                # naming the object header after its first field
                fo = self._class_level_offsets(cur, fo)
            if fo:
                for k, off in enumerate(fo):
                    fi = td.field_start + k
                    # instance fields only: statics' blob offsets
                    # collide with instance offsets (see
                    # field_offset_map)
                    if fi < len(self.meta.fields) and off not in merged \
                            and not (field_attrs(self, self.meta.fields[fi])
                                     & (FA_STATIC | FA_LITERAL)):
                        merged[off] = (_storage_name(self, fi), self.meta.fields[fi].type)
            nxt = td.parent
            if nxt >= 0 and nxt < len(self.types) and self.types[nxt]:
                t = self.types[nxt]
                te = (t[1] >> 16) & 0xFF
                if te in (0x11, 0x12):
                    cur = t[0] if t[0] < len(self.meta.typedefs) else None
                elif te == 0x15:
                    o = self.bin.va2off(t[0])
                    if o is not None:
                        tt = self.type_from_ptr(u64(self.bin.d, o))
                        if tt and ((tt[1] >> 16) & 0xFF) in (0x11, 0x12) and tt[0] < len(self.meta.typedefs):
                            cur = tt[0]
                        else:
                            cur = None
                    else:
                        cur = None
                else:
                    cur = None
            else:
                cur = None
            hops += 1
        self._chain_cache[td_index] = merged or None
        return merged or None

    # element types whose storage never depends on generic arguments:
    # primitives, string, pointers, class/array references, object
    _LAYOUT_INVARIANT_TE = frozenset((0x02, 0x03, 0x04, 0x05, 0x06, 0x07,
                                      0x08, 0x09, 0x0a, 0x0b, 0x0c, 0x0d,
                                      0x0e, 0x0f, 0x12, 0x14, 0x18, 0x19,
                                      0x1b, 0x1c, 0x1d))

    def _inst_field_ks(self, td):
        """Local indices of a typedef's instance (non-static) fields."""
        out = []
        for k in range(td.field_count):
            fi = td.field_start + k
            if fi < len(self.meta.fields) and not (
                    field_attrs(self, self.meta.fields[fi]) & (FA_STATIC | FA_LITERAL)):
                out.append(k)
        return out

    def _class_field_size_align(self, ty):
        """(size, align) of an argument-invariant class field type, else None."""
        if ty is None:
            return None
        if (ty[1] >> 29) & 1:
            return 8, 8
        te = (ty[1] >> 16) & 0xFF
        if te == 0x15:
            g = self.td_of_ty(ty)
            if g is None or self.meta.typedefs[g].is_valuetype:
                return None
            return 8, 8
        if te in self._LAYOUT_INVARIANT_TE:
            sa = self._sf_ty_size_align(ty, (), 1)
            if sa is None:
                return None
            return sa[0], max(1, min(sa[1], 8))
        return None                     # VAR / struct by value: arg-dependent

    def _class_level_offsets(self, td_index, fo):
        """Fix 133: one class level's offsets -- the binary's, or rebuilt.

        Returns `fo` itself when any instance offset is non-zero (the
        real table) or the level has no instance fields. An all-zero
        table is an open generic definition: returns a rebuilt list
        (static entries untouched) when the level is argument-invariant
        and its parent's instance size is known, else None -- the level
        then names nothing, never offset 0 (the object header).
        """
        try:
            td = self.meta.typedefs[td_index]
            inst = [k for k in self._inst_field_ks(td) if k < len(fo)]
            if not inst or any(fo[k] for k in inst):
                return fo
            cache = self.__dict__.setdefault('_class_level_cache', {})
            if td_index in cache:
                return cache[td_index]
            cache[td_index] = None      # cycle guard
            if (getattr(td, 'flags', 0) & 0x18) == 0x10:
                return None             # explicit layout
            cur = self._class_instance_end(td.parent, 0)
            if cur is None:
                return None
            out = list(fo)
            for k in inst:
                sa = self._class_field_size_align(
                    self.types[self.meta.fields[td.field_start + k].type])
                if sa is None:
                    return None
                sz, al = sa
                cur = (cur + al - 1) & ~(al - 1)
                out[k] = cur
                cur += sz
            cache[td_index] = out
            return out
        except Exception:
            return None

    def _class_instance_end(self, parent_type_index, depth):
        """Fix 133: header-inclusive instance size of a parent, or None.

        No parent / System.Object -> 0x10. A class with a real offset
        table -> its recorded instance size (type_sizes is
        header-excluded). A class without instance fields -> its own
        parent's end. A rebuilt generic level -> its last field's end,
        rounded to 8 like every IL2CPP class instance size.
        """
        try:
            if depth > 8:
                return None
            if parent_type_index < 0 or parent_type_index >= len(self.types):
                return 0x10
            t = self.types[parent_type_index]
            if not t:
                return 0x10
            te = (t[1] >> 16) & 0xFF
            if te == 0x1c:
                return 0x10
            if te == 0x12:
                ptd = t[0]
            elif te == 0x15:
                ptd = self.td_of_ty(t)
            else:
                return None
            if ptd is None or not (0 <= ptd < len(self.meta.typedefs)):
                return None
            row = self.meta.typedefs[ptd]
            inst = self._inst_field_ks(row)
            if not inst:
                return self._class_instance_end(row.parent, depth + 1)
            pfo = self.field_offsets[ptd] if ptd < len(self.field_offsets) else None
            if not pfo:
                return None
            lvl = self._class_level_offsets(ptd, pfo)
            if lvl is None:
                return None
            if lvl is pfo:
                ts = self.type_sizes[ptd] if ptd < len(self.type_sizes) else None
                return ts + 0x10 if ts else None
            end = 0
            for k in inst:
                if k >= len(lvl):
                    return None
                sa = self._class_field_size_align(
                    self.types[self.meta.fields[row.field_start + k].type])
                if sa is None:
                    return None
                end = max(end, lvl[k] + sa[0])
            return (end + 7) & ~7
        except Exception:
            return None

    _bases_cache: Dict[int, Tuple[int, ...]] = {}

    def _system_object_td(self) -> Optional[int]:
        """The unique System.Object TypeDef, or None on malformed metadata."""
        if hasattr(self, '_system_object_td_index'):
            return self._system_object_td_index
        hits = [i for i, td in enumerate(self.meta.typedefs)
                if td.namespace == 'System' and td.name == 'Object']
        self._system_object_td_index = hits[0] if len(hits) == 1 else None
        return self._system_object_td_index

    def _system_array_td(self) -> Optional[int]:
        """The unique System.Array TypeDef, or None on malformed metadata."""
        if hasattr(self, '_system_array_td_index'):
            return self._system_array_td_index
        hits = [i for i, td in enumerate(self.meta.typedefs)
                if td.namespace == 'System' and td.name == 'Array']
        self._system_array_td_index = hits[0] if len(hits) == 1 else None
        return self._system_array_td_index

    def base_chain_tds(self, td_index) -> Tuple[int, ...]:
        """(td_index, its parent, its parent's parent, ...) up to object.

        This mirrors instance_field_chain's CLASS/VALUETYPE/GENERICINST walk,
        but also maps IL2CPP_TYPE_OBJECT (0x1c). Unity 6000 encodes the final
        parent edge that way, so stopping before it hid System.Object from
        constructor and receiver proofs despite this helper's contract.
        """
        if td_index in self._bases_cache:
            return self._bases_cache[td_index]
        chain = []
        cur = td_index
        hops = 0
        while cur is not None and 0 <= cur < len(self.meta.typedefs) \
                and cur not in chain and hops < 16:
            chain.append(cur)
            td = self.meta.typedefs[cur]
            nxt = td.parent
            cur = None
            if nxt >= 0 and nxt < len(self.types) and self.types[nxt]:
                t = self.types[nxt]
                te = (t[1] >> 16) & 0xFF
                if te in (0x11, 0x12) and t[0] < len(self.meta.typedefs):
                    cur = t[0]
                elif te == 0x1c:
                    obj = self._system_object_td()
                    if obj is not None and obj not in chain:
                        cur = obj
                elif te == 0x15:
                    o = self.bin.va2off(t[0])
                    if o is not None:
                        tt = self.type_from_ptr(u64(self.bin.d, o))
                        if tt and ((tt[1] >> 16) & 0xFF) in (0x11, 0x12) and tt[0] < len(self.meta.typedefs):
                            cur = tt[0]
            hops += 1
        result = tuple(chain)
        self._bases_cache[td_index] = result
        return result

    def static_offset_map(self, td_index) -> Optional[Dict[int, str]]:
        fo = self.field_offsets[td_index] if td_index < len(self.field_offsets) else None
        td = self.meta.typedefs[td_index]
        if fo is None:
            return None
        m = {}
        for k, fi in enumerate(range(td.field_start, td.field_start + td.field_count)):
            f = self.meta.fields[fi]
            if (f.token >> 24) == 0x04 and (self.field_static(fi)):  # FieldDef row & static flag
                m[fo[k]] = _storage_name(self, fi)
        return m

    def td_of_ty(self, ty) -> Optional[int]:
        """TypeDef for CLASS/VALUETYPE/OBJECT or GENERICINST-of-class.

        Kept in step with Lifter._td_of so usage-slot annotations and call-site
        receiver proofs agree about the terminal System.Object encoding.
        """
        if ty is None:
            return None
        data, bits = ty
        te = (bits >> 16) & 0xFF
        if te in (0x11, 0x12):
            return data if 0 <= data < len(self.meta.typedefs) else None
        if te == 0x1c:
            return self._system_object_td()
        if te == 0x15:
            synth = self.__dict__.get('_synthetic_insts', {}).get(data)
            if synth is not None:
                base_tup = synth[0]
                if base_tup:
                    te2 = self._type_enum(base_tup)
                    if te2 in (0x11, 0x12) and base_tup[0] < len(self.meta.typedefs):
                        return base_tup[0]
                return None
            o = self.bin.va2off(data)
            if o is None:
                return None
            t = self.type_from_ptr(u64(self.bin.d, o))
            if t:
                te2 = self._type_enum(t)
                if te2 in (0x11, 0x12) and t[0] < len(self.meta.typedefs):
                    return t[0]
        return None

    def static_off_names(self, td_index) -> Optional[Dict[int, tuple]]:
        """offset -> (name, field type idx), same shape as
        `instance_field_chain` -- a static field's own type is metadata,
        same as any other field's, but the offset->name lookup used to
        throw it away (a static field read always rendered `.ty = None`,
        so `typeof(X).Instance` losing its own `X` type meant every
        further deref off the result -- `Instance.someField` -- could
        never resolve to a real member name either)."""
        if td_index in self._static_names_cache:
            return self._static_names_cache[td_index]
        td = self.meta.typedefs[td_index]
        fo = self.field_offsets[td_index] if td_index < len(self.field_offsets) else None
        if fo is None:
            self._static_names_cache[td_index] = None
            return None
        m = {}
        for k in range(td.field_count):
            fi = td.field_start + k
            # 71a: static-blob storage only. Literal consts have no
            # runtime slot (every fo row forced to 0x0) and shadow
            # the first real static under setdefault (DateTime's 37
            # literals named s_daysToMonth365's own offset
            # TicksPerMillisecond); instance fields' header-relative
            # offsets collide with blob offsets (same collision
            # field_offset_map filters, from the instance side).
            a = field_attrs(self, self.meta.fields[fi])
            if not (a & FA_STATIC) or (a & FA_LITERAL):
                continue
            m.setdefault(fo[k], (_storage_name(self, fi), self.meta.fields[fi].type))
        self._static_names_cache[td_index] = m
        return m

    def static_off_path(self, td_index, disp, ty=None):
        """offset -> (dotted path, field type) for a static-blob
        read, or None. A direct hit is the field's own (name, type).
        A miss resolves the largest static field base <= disp whose
        own value type's instance chain contains
        (disp - base + 0x10): static VALUE-TYPE storage in the blob is
        unboxed -- no 0x10 header, unlike the instance path -- so a
        read at [blob + zeroVector_off + 8] is the Vector3 component
        zeroVector.z (fix 72; probe_b72_static.py). Fix 73 generalized
        the miss walk to RECURSE through nested value-type members
        (the UIElements *Property statics are BindingIds -- 0x98
        bytes, a PropertyPath at chain 0x10 -- probe_b73_uiprop.py).
        Fix 74 adds the genericinst route: a static field whose type
        is a VALUETYPE-underlying GENERICINST (0x15) has no runtime
        layout row of its own -- the open definition's field_offsets
        row is all zeros and type_sizes[td] is None (probed 160/161
        open value types) -- so the instantiation's layout is
        RECONSTRUCTED from the open td's field list plus the gc class
        arguments (VAR fields substituted), IL2CPP sequential rules.
        Ground truth: TMP_Text..cctor copies the constructed
        TMP_TextProcessingStack<MaterialReference> into blob+0x10 as
        5x16B + 8B = 0x58 bytes (probe_b74_disasm.py) and the
        declaration-order reconstruction gives itemStack@0x10,
        index@0x18, m_DefaultItem@0x20 (MaterialReference 0x38),
        m_Capacity@0x58, m_RolloverSize@0x5c, m_Count@0x60 -- exact.
        The returned second element is now the Il2CppType TUPLE, not
        the field-table index (a substituted generic field has no
        index); padding and past-the-field disps stay honest (None).
        Fix 76 adds the closed-generic-CLASS route: when the open
        row is degenerate (all zeros -- open generics carry no
        runtime layout) and `ty` is the GENERICINST itself, the
        instantiation's static blob is RECONSTRUCTED declaration-
        order with natural alignment (the fix-74 rule) and searched
        the same way (EventBase<T>.EventCategory@0x10,
        BaseField<string>.mixedValueString@0x208, probe_b76)."""
        sm = self.static_off_names(td_index)
        if not sm:
            return self._sf_closed_static_disp(td_index, disp, ty)
        ent = sm.get(disp)
        if ent is not None:
            return (ent[0], self._sf_ty_of(ent[1]))
        best = None
        for off, (nm, ftidx) in sm.items():
            if off < disp and (best is None or off > best[0]):
                best = (off, nm, ftidx)
        if best is None:
            return self._sf_closed_static_disp(td_index, disp, ty)
        off, nm, ftidx = best
        fty = self._sf_ty_of(ftidx)
        sub = self._sf_field_path(fty, disp - off + 0x10, 1,
                                  frozenset())
        if sub is None:
            return self._sf_closed_static_disp(td_index, disp, ty)
        return ('%s.%s' % (nm, sub[0]), sub[1])

    def _sf_closed_static_map(self, td_index, args):
        """off -> (name, substituted type tuple) for a CLOSED generic
        CLASS instantiation whose open definition carries no runtime
        static layout. Declaration order, natural alignment capped 8
        (the fix-74 rule); VAR field types substituted through `args`.
        Cached per (td, args) -- failures too."""
        key = ('c', td_index, args)
        cache = self.__dict__.setdefault('_sf_infl_cache', {})
        if key in cache:
            return cache[key]
        td = self.meta.typedefs[td_index]
        cur = 0
        m = {}
        for k in range(td.field_count):
            fi = td.field_start + k
            f = self.meta.fields[fi]
            a = field_attrs(self, f)
            if not (a & FA_STATIC) or (a & FA_LITERAL):
                continue
            ty = self.types[f.type] \
                if 0 <= f.type < len(self.types) else None
            st = self._sf_subst(ty, args)
            sa = self._sf_ty_size_align(st, args, 0) \
                if st is not None else None
            if sa is None:
                cache[key] = None
                return None
            sz, al = sa
            al = min(max(al, 1), 8)
            cur = (cur + al - 1) // al * al
            m.setdefault(cur, (_storage_name(self, fi), st))
            cur += sz
        cache[key] = m
        return m

    def _sf_closed_static_disp(self, td_index, disp, ty):
        """the fix-76 fallback for static_off_path: `ty` is the
        GENERICINST base type itself. Fires only on a degenerate open
        row (all zeros) whose td matches the instantiation -- a td
        WITH a real row stays owned by the existing logic."""
        if ty is None or self._type_enum(ty) != 0x15:
            return None
        if self.td_of_ty(ty) != td_index:
            return None
        if not (0 <= td_index < len(self.meta.typedefs)):
            return None
        td = self.meta.typedefs[td_index]
        fo = self.field_offsets[td_index] \
            if td_index < len(self.field_offsets) else None
        if fo is None or any(fo[:td.field_count]):
            return None
        args = self._generic_inst_args(ty)
        if args is None:
            return None
        cm = self._sf_closed_static_map(td_index, args)
        if not cm:
            return None
        ent = cm.get(disp)
        if ent is not None:
            return (ent[0], self._sf_ty_of(ent[1]))
        best = None
        for off, (nm, st) in cm.items():
            if off < disp and (best is None or off > best[0]):
                best = (off, nm, st)
        if best is None:
            return None
        off, nm, st = best
        sub = self._sf_field_path(st, disp - off + 0x10, 1,
                                   frozenset())
        if sub is None:
            return None
        return ('%s.%s' % (nm, sub[0]), sub[1])

    def _sf_ty_of(self, ent_ty):
        """a chain entry's type: instance chains carry the field-table
        INDEX, inflated-layout chains carry the (substituted) type
        TUPLE -- normalize to the tuple."""
        if isinstance(ent_ty, int):
            return self.types[ent_ty] if 0 <= ent_ty < len(self.types) else None
        return ent_ty

    def _generic_inst_args(self, ty):
        """concrete Il2CppType tuples of a GENERICINST's class_inst
        arguments (the Lifter._generic_class_args twin, up on Il2Cpp
        so the static-blob walk can substitute open-generic fields)."""
        if ty is None or self._type_enum(ty) != 0x15:
            return None
        synth = self.__dict__.get('_synthetic_insts', {}).get(ty[0])
        if synth is not None:
            return tuple(synth[1])
        o = self.bin.va2off(ty[0])
        if o is None:
            return None
        io = self.bin.va2off(u64(self.bin.d, o + 8))
        if io is None:
            return None
        argc = u64(self.bin.d, io)
        argv = u64(self.bin.d, io + 8)
        out = []
        for k in range(min(argc, 16)):
            tp = self.bin.qword(argv + k * 8) if argv else None
            out.append(self.type_from_ptr(tp) if tp else None)
        return tuple(out)

    def _sf_subst(self, ty, args):
        """substitute a VAR (0x13) through the enclosing
        instantiation's class args. MVAR (0x1e) cannot appear in a
        field type -> fail honest."""
        if ty is None:
            return None
        te = self._type_enum(ty)
        if te == 0x13:
            if not args:
                return None
            gi = ty[0]
            if 0 <= gi < len(self.meta.generic_parameters):
                ordn = self.meta.generic_parameters[gi][4]
                if 0 <= ordn < len(args) and args[ordn] is not None:
                    a = args[ordn]
                    if self._type_enum(a) in (0x13, 0x1e):
                        return None
                    return a
            return None
        if te == 0x1e:
            return None
        return ty

    def _sf_subst_args(self, gargs, args):
        out = []
        for a in gargs or ():
            s = self._sf_subst(a, args)
            if s is None:
                return None
            out.append(s)
        return tuple(out)

    # size == natural alignment for every primitive/ref on x64. Enum
    # space is Il2CppTypeEnum: 0x18 IntPtr / 0x19 UIntPtr / 0x1a fnptr /
    # 0x1c object are all 8-byte refs here. TypedReference (0x16) is
    # deliberately unmapped -> honest None (no corpus site).
    _SF_PRIM = {0x01: 1, 0x02: 1, 0x03: 2, 0x04: 1, 0x05: 1, 0x06: 2,
                0x07: 2, 0x08: 4, 0x09: 4, 0x0a: 8, 0x0b: 8, 0x0c: 4,
                0x0d: 8, 0x18: 8, 0x19: 8, 0x1a: 8, 0x1c: 8}

    def _sf_ty_size_align(self, ty, args, depth):
        """(header-excluded size, alignment) of a concrete type tuple,
        or None when that is not knowable statically. This is the
        LAYOUT-BUILDING authority (inflated chains) -- alignment IS
        needed here, unlike the span check (_sf_field_size), which
        must stay alignment-free: fix 72/73's span check read
        type_sizes directly, and an alignment recursion that fails on
        an exotic field type would kill otherwise-valid descents."""
        if ty is None:
            return None
        te = self._type_enum(ty)
        if (ty[1] >> 29) & 1:
            return (8, 8)
        if te in self._SF_PRIM:
            n = self._SF_PRIM[te]
            return (n, n)
        if te in (0x0e, 0x0f, 0x12, 0x14, 0x1d):
            return (8, 8)
        if te == 0x15:
            td2 = self.td_of_ty(ty)
            if td2 is None or not (0 <= td2 < len(self.meta.typedefs)):
                return None
            if not self.meta.typedefs[td2].is_valuetype:
                return (8, 8)
            sz = self.type_sizes[td2] if td2 < len(self.type_sizes) else None
            if sz is not None:
                al = self._sf_vt_align(td2, args, depth)
                return None if al is None else (sz, al)
            gargs = self._generic_inst_args(ty)
            sargs = self._sf_subst_args(gargs, args) \
                if gargs is not None else None
            if sargs is None:
                return None
            lay = self._sf_infl_chain(td2, sargs, depth)
            if lay is None:
                return None
            return (lay[1], lay[2])
        if te == 0x11:
            td2 = ty[0]
            if not (0 <= td2 < len(self.meta.typedefs)) \
                    or not self.meta.typedefs[td2].is_valuetype:
                return None
            sz = self.type_sizes[td2] if td2 < len(self.type_sizes) else None
            if sz is None:
                return None
            al = self._sf_vt_align(td2, None, depth)
            return None if al is None else (sz, al)
        return None

    def _sf_vt_align(self, td_index, args, depth):
        """alignment of a value type: max natural alignment of its
        instance fields, capped 8 (x64). Needs the REAL field list;
        VAR fields need `args`, so an open type without them fails
        honest. Cached per (td, args)."""
        key = ('a', td_index, args)
        cache = self.__dict__.setdefault('_sf_infl_cache', {})
        if key in cache:
            return cache[key]
        if depth > 6:
            return None
        td = self.meta.typedefs[td_index]
        al = 1
        for k in range(td.field_count):
            fi = td.field_start + k
            f = self.meta.fields[fi]
            a = field_attrs(self, f)
            if a & (FA_STATIC | FA_LITERAL):
                continue
            ty = self._sf_subst(self.types[f.type], args)
            if ty is None:
                return None
            sa = self._sf_ty_size_align(ty, args, depth + 1)
            if sa is None:
                return None
            al = max(al, sa[1])
        al = min(al, 8)
        cache[key] = al
        return al

    def _sf_infl_chain(self, td_index, args, depth):
        """(chain, size, align) of a valuetype INSTANTIATION whose open
        definition has no runtime layout row: the field list walked in
        declaration order with natural alignment (IL2CPP sequential
        rules), VAR fields substituted through `args`. Chain offsets
        are header-relative like instance_field_chain's; values carry
        the SUBSTITUTED type tuple so deeper descents need no context.
        The struct's own alignment rides back (a nested genericinst
        field's host layout needs it). Cached per (td, args) --
        failures too."""
        key = ('l', td_index, args)
        cache = self.__dict__.setdefault('_sf_infl_cache', {})
        if key in cache:
            return cache[key]
        if depth > 4:
            return None
        td = self.meta.typedefs[td_index]
        chain = {}
        cur = 0
        maxa = 1
        bad = False
        for k in range(td.field_count):
            fi = td.field_start + k
            f = self.meta.fields[fi]
            a = field_attrs(self, f)
            if a & (FA_STATIC | FA_LITERAL):
                continue
            ty = self._sf_subst(self.types[f.type], args)
            if ty is None:
                bad = True
                break
            if self._type_enum(ty) == 0x15 and self._closed_type_key(ty) is None:
                # a nested open instantiation (a KVP field inside an
                # Enumerator chain): close it through the enclosing args
                # so deeper descents see concrete field types. Fields can
                # never mention method params, so MVAR declines honestly.
                ty = self._subst_closed(ty, args, None)
                if ty is None:
                    bad = True
                    break
            sa = self._sf_ty_size_align(ty, args, depth + 1)
            if sa is None:
                bad = True
                break
            sz, al = sa
            off = (cur + al - 1) & ~(al - 1)
            chain[off + 0x10] = (_storage_name(self, fi), ty)
            cur = off + sz
            maxa = max(maxa, al)
        if bad or not chain:
            cache[key] = None
            return None
        size = (cur + maxa - 1) & ~(maxa - 1)
        res = (chain, size, min(maxa, 8))
        cache[key] = res
        return res

    def _sf_field_size(self, fty, depth):
        """header-excluded size of a chain field's type, or None --
        the SPAN CHECK's authority. No alignment here (see
        _sf_ty_size_align's note): fix 72/73 read type_sizes directly
        and the span check must keep that exactness."""
        if fty is None:
            return None
        te = self._type_enum(fty)
        if (fty[1] >> 29) & 1:
            return 8
        if te in self._SF_PRIM:
            return self._SF_PRIM[te]
        if te in (0x0e, 0x0f, 0x12, 0x14, 0x1d):
            return 8
        if te == 0x11:
            td2 = fty[0]
            if not (0 <= td2 < len(self.meta.typedefs)) \
                    or not self.meta.typedefs[td2].is_valuetype:
                return None
            return self.type_sizes[td2] if td2 < len(self.type_sizes) else None
        if te == 0x15:
            td2 = self.td_of_ty(fty)
            if td2 is None:
                return None
            if not self.meta.typedefs[td2].is_valuetype:
                return 8
            sz = self.type_sizes[td2] if td2 < len(self.type_sizes) else None
            if sz is not None:
                return sz
            gargs = self._generic_inst_args(fty)
            if gargs is None:
                return None
            lay = self._sf_infl_chain(td2, gargs, depth)
            return None if lay is None else lay[1]
        return None

    def _sf_field_path(self, fty, key, depth, seen):
        """descend into a FIELD's type at header-relative `key` ->
        (dotted path, type tuple). The fix-73 recursion, generalized:
        0x11/0x12 walk the REAL instance chain (type_sizes span);
        0x15 walks the instantiation's layout -- the real row when the
        open definition carries one, else the reconstructed inflated
        chain (fix 74). Depth-capped 4; cycle-guarded by `seen` (which
        must seed EMPTY: self-typed statics like Vector3.zeroVector
        are legitimate first hops -- the batch-73 lesson)."""
        if fty is None or depth > 4:
            return None
        te = self._type_enum(fty)
        if (fty[1] >> 29) & 1:
            return None
        if te in (0x11, 0x12):
            td2 = fty[0]
            if not (0 <= td2 < len(self.meta.typedefs)) or td2 in seen:
                return None
            if not self.meta.typedefs[td2].is_valuetype:
                return None
            sz = self.type_sizes[td2] if td2 < len(self.type_sizes) else None
            if sz is None:
                return None
            ch = self.instance_field_chain(td2)
            if not ch:
                return None
            return self._sf_chain_walk(ch, sz, key, depth,
                                       seen | {td2})
        if te == 0x15:
            td2 = self.td_of_ty(fty)
            if td2 is None or not (0 <= td2 < len(self.meta.typedefs)) \
                    or td2 in seen:
                return None
            if not self.meta.typedefs[td2].is_valuetype:
                return None
            sz = self.type_sizes[td2] if td2 < len(self.type_sizes) else None
            fo = self.field_offsets[td2] \
                if td2 < len(self.field_offsets) else None
            if sz is not None and fo and any(fo):
                ch = self.instance_field_chain(td2)
                if not ch:
                    return None
                return self._sf_chain_walk(ch, sz, key, depth,
                                           seen | {td2})
            gargs = self._generic_inst_args(fty)
            if gargs is None:
                return None
            lay = self._sf_infl_chain(td2, gargs, depth)
            if lay is None:
                return None
            return self._sf_chain_walk(lay[0], lay[1], key, depth,
                                       seen | {td2})
        return None

    def _sf_chain_walk(self, chain, size, key, depth, seen):
        """one level of the inner walk over `chain` (a value type's
        instance layout, header-relative; `size` the header-excluded
        struct size). Exact hit wins; otherwise the largest entry < key
        whose own type SPANS the key descends -- the span test keeps
        padding and past-the-field reads honest."""
        if depth > 4 or not chain:
            return None
        ent = chain.get(key)
        if ent is not None:
            return (ent[0], self._sf_ty_of(ent[1]))
        best = None
        for off, (nm, ft) in chain.items():
            if off < key and (best is None or off > best[0]):
                best = (off, nm, ft)
        if best is None:
            return None
        off, nm, ft = best
        fty = self._sf_ty_of(ft)
        fsz = self._sf_field_size(fty, depth + 1)
        if fsz is None:
            return None
        if off + fsz <= key:
            return None
        sub = self._sf_field_path(fty, key - off + 0x10, depth + 1,
                                  seen)
        if sub is None:
            return None
        return ('%s.%s' % (nm, sub[0]), sub[1])

    def field_static(self, field_row_index) -> bool:
        """fields[] rows don't carry flags; approximate via attribute default presence is
        impossible - so use metadata field flags via Il2CppFieldDefaultValues? We mark all
        low-offset entries (<0x10) as static candidates at call sites instead."""
        return False

    # function bounds from PE .pdata / fallback
