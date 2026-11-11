from il2cpp.prelude import *  # noqa: F401,F403
from il2cpp.arm64 import Arm64Lifter, is_arm64_binary
from il2cpp.common import compressed_int, csharp_type_name, i32, i64, read_compressed_uint, u16, u32, u64
from il2cpp.csharp import FA_INITONLY, FA_LITERAL, FA_STATIC, FIELD_VIS, METH_VIS, TYPE_VIS, UsingTracker, field_attrs, nameof_sugar, strip_namespaces, collision_heads, source_field_name
from il2cpp.lifter import Lifter
from il2cpp.metadata import ImageDef, MethodDef, TypeDef
from il2cpp.names import repr_f32, repr_f64, safe_ident, sanitize, sanitize_qualifier
from il2cpp.runtime.core import Il2Cpp
from il2cpp.runtime.meta import meta_lit_repr
from il2cpp.text import MANGLED_IDENT_RX, reindent
from il2cpp import rawaddr
from il2cpp.pinvoke import dllimport_attribute, stub_arguments

class Emitter:
    def __init__(self, il2: Il2Cpp, out_dir: str, asm_comments=False,
                 with_bodies=True, max_methods=None, verbose=False, type_filter=None,
                 publicize=False, raw_addr=False):
        self.il = il2
        self.publicize = publicize
        self.raw_addr = raw_addr
        self.meta = il2.meta
        self.out_dir = out_dir
        self.asm_comments = asm_comments
        self.with_bodies = with_bodies
        self.max_methods = max_methods
        self.verbose = verbose
        self.type_filter = type_filter.casefold() if type_filter else None
        self.decompiler_error = None
        _a64 = with_bodies and HAVE_CAPSTONE and is_arm64_binary(il2.bin)
        if _a64:
            self.lifter = Arm64Lifter(il2, asm_comments=asm_comments)
        elif with_bodies and HAVE_ICED and not is_arm64_binary(il2.bin):
            self.lifter = Lifter(il2, asm_comments=asm_comments)
        else:
            self.lifter = None
        self.decompiler = None
        if self.lifter:
            try:
                from il2cpp.dec import Decompiler
                from il2cpp.arm64_dec import Arm64Decompiler
                self.decompiler = (Arm64Decompiler(self.lifter) if _a64
                                   else Decompiler(self.lifter))
            except Exception as ex:
                self.decompiler_error = str(ex)
                self.decompiler = None
        self.lifted = 0
        self.failed = 0
        self.fallbacks = 0
        self.emit_failed = 0
        self.bodies = {}

    # -- type header ------------------------------------------------------
    def _type_generic_params(self, td: TypeDef) -> str:
        """`<T, ...>` from the typedef's generic container, else ''."""
        # A nested container holds mirrored owner parameters plus its
        # own trailing ones: declare only the own suffix (possibly none).
        # Unprovable splits keep the legacy full-container rendering.
        try:
            if self.il._nested_owner(td.index) is not None:
                own = self.il._nested_own_params(td)
                if own is not None:
                    return '<%s>' % ', '.join(own) if own else ''
        except Exception:
            pass
        gparams = ''
        if td.generic_container != -1 and not td.is_enum:
            gc = self.meta.generic_containers[td.generic_container]
            gp = []
            for k in range(gc[1]):
                gi = gc[3] + k
                if gi < len(self.meta.generic_parameters):
                    gp.append(self.meta.generic_parameters[gi][1])
            gparams = '<%s>' % ', '.join(gp) if gp else ''
        return gparams

    _arity_qualifier_cache = None

    def _arity_qualifier(self, dotted, td=None):
        """Append the metadata arity suffix to an explicit-interface qualifier
        (`NS.IFoo<T>` -> `NS.IFoo_1<T>`) so it spells the same identifier the
        interface declaration does. Qualifiers come from metadata name strings
        that never record arity, so arity is proved by matching (namespace,
        dotted path, top-level argument count) against exactly one typedef
        row; anything else declines unchanged."""
        if '<' not in dotted or '>' not in dotted:
            return dotted
        try:
            exact = self._iface_qualifier(dotted, td)
            if exact is not None:
                return exact
            cache = self._arity_qualifier_cache
            if cache is None:
                cache = {}
                for td in self.meta.typedefs:
                    try:
                        nm = td.name or ''
                    except Exception:
                        continue
                    if '`' not in nm:
                        continue
                    m = re.match(r'^(.*)`(\d+)$', nm)
                    if not m:
                        continue
                    short, arity = m.group(1), int(m.group(2))
                    parts = [short]
                    seen = 0
                    ns = getattr(td, 'namespace', '')
                    try:
                        dd = self.il._nested_owner(td.index)
                        while dd is not None and seen < 8:
                            dt = self.meta.typedefs[dd]
                            parts.append((dt.name or '').split('`')[0])
                            seen += 1
                            # the namespace lives on the outermost owner;
                            # nested rows carry none of their own.
                            if getattr(dt, 'namespace', ''):
                                ns = dt.namespace
                            dd = self.il._nested_owner(dd)
                    except Exception:
                        pass
                    path = '.'.join(reversed(parts))
                    cache.setdefault((ns, path), []).append(arity)
                self._arity_qualifier_cache = cache
            head, rest = dotted.split('<', 1)
            args = '<' + rest
            depth = commas = 0
            has_arg = False
            for ch in args[1:]:
                if ch == '<':
                    depth += 1
                elif ch == '>':
                    if depth == 0:
                        break
                    depth -= 1
                elif ch == ',' and depth == 0:
                    commas += 1
                elif ch not in ', ':
                    has_arg = True
            if not has_arg:
                return dotted
            argc = commas + 1
            # a nested qualifier (`N.Outer.Inner<X>`) may split namespace
            # from path at any dot; accept only a globally unique proof.
            segs = head.split('.')
            proofs = []
            for k in range(len(segs)):
                ns = '.'.join(segs[:k])
                path = '.'.join(segs[k:])
                cands = [a for a in cache.get((ns, path), []) if a == argc]
                if len(cands) == 1:
                    proofs.append('%s%s_%d%s' % (ns + '.' if ns else '', path, argc, args))
            if len(proofs) != 1:
                return dotted
            return proofs[0]
        except Exception:
            return dotted

    def _iface_qualifier(self, dotted, td=None):
        """Render an explicit-interface qualifier from the declaring type's
        own interface list (binary truth) instead of the arity-less metadata
        name string. Matches (namespace, short name, top-level argument
        count) against each implemented interface tuple and, on exactly one
        match, returns that tuple's rendered spelling — identical to the
        base-list spelling, nested arguments included. Returns None to let
        the typedef-name proof below decide, or to decline unchanged."""
        if td is None:
            return None
        try:
            head, rest = dotted.split('<', 1)
            args = '<' + rest
            if '.' in head:
                qns, _, qpath = head.rpartition('.')
            else:
                qns, qpath = '', head
            depth = commas = 0
            has_arg = False
            for ch in args[1:]:
                if ch == '<':
                    depth += 1
                elif ch == '>':
                    if depth == 0:
                        break
                    depth -= 1
                elif ch == ',' and depth == 0:
                    commas += 1
                elif ch not in ', ':
                    has_arg = True
            if not has_arg:
                return None
            qargc = commas + 1
            hits = []
            for k in range(getattr(td, 'interfaces_count', 0)):
                ii = self.meta.interfaces[td.interfaces_start + k]
                tup = self.il.types[ii] if 0 <= ii < len(self.il.types) else None
                if tup is None:
                    continue
                rendered = self.il.type_name(tup)
                if '<' not in rendered or '>' not in rendered:
                    continue
                rhead, rrest = rendered.split('<', 1)
                if '.' in rhead:
                    rns, _, rpath = rhead.rpartition('.')
                else:
                    rns, rpath = '', rhead
                rpath = re.sub(r'_\d+$', '', rpath)
                rdepth = rcommas = 0
                rhas = False
                for ch in ('<' + rrest)[1:]:
                    if ch == '<':
                        rdepth += 1
                    elif ch == '>':
                        if rdepth == 0:
                            break
                        rdepth -= 1
                    elif ch == ',' and rdepth == 0:
                        rcommas += 1
                    elif ch not in ', ':
                        rhas = True
                if not rhas:
                    continue
                if rpath == qpath and (not qns or rns == qns) and rcommas + 1 == qargc:
                    hits.append(rendered)
            if len(hits) != 1:
                return None
            return hits[0]
        except Exception:
            return None

    def _is_blob_container(self, td) -> bool:
        """True for compiler-generated static-data blob containers.

        Roslyn `__StaticArrayInitTypeSize=N` and Mono `$ArrayType=N`
        nested structs are always empty (no fields, no methods, hence
        no properties or events either) and carry no source contract.
        A private one exposed by an assembly-visible field fails
        CS0052, while internal always compiles (over-visible never
        errors), so the pattern renders internal. Anything with
        members, another visibility, or another name keeps truth."""
        try:
            nm = td.name or ''
            if not re.match(r'^(?:__StaticArrayInitTypeSize=\d+|\$ArrayType=\d+)$', nm):
                return False
            if not td.is_valuetype or td.method_count or td.field_count:
                return False
            if (td.flags & 7) != 3:
                return False
            return self.il._nested_owner(td.index) is not None
        except Exception:
            return False

    def _pub(self, vis):
        """Fix 127, opt-in `--publicize`: every declared accessibility
        renders `public` (types, nested types, fields, methods, ctors,
        properties, events, delegates), the way a publicized reference
        assembly does. Native code reads private backing fields and
        internal members across images because IL2CPP inlines accessors
        and ignores accessibility, so a faithful body cannot compile
        against the faithful declarations (CS0122). Off by default: the
        default tree keeps the metadata's accessibility. An empty
        modifier (explicit interface implementation, interface member,
        static ctor) stays empty."""
        if vis and getattr(self, 'publicize', False):
            return 'public '
        return vis

    def type_decl_line(self, td: TypeDef) -> List[str]:
        f = td.flags
        vis = TYPE_VIS.get((f >> 0) & 7, '')
        ebase = ''  # `: uint` suffix for non-int enums (set below)
        if td.declaring < 0 and (f & 7) > 1:
            vis = 'internal '  # a nested form on a top-level row: unreadable
        if self._is_blob_container(td):
            vis = 'internal '
        vis = self._pub(vis)
        lines = []
        if f & 0x20:
            # interfaces are implicitly abstract: 0x80 is always set
            # alongside 0x20, so excluding abstract here misread nearly
            # every interface as a class (fix 113).
            kw = vis + 'partial interface'
        elif td.is_enum:
            kw = vis + 'enum'
            # a non-int underlying must spell (`enum E : uint`): int is
            # the default and large members/defaults fail without it
            # (DesiredAccess 2148532224, CS0221). ponytail: keyword table
            # only; unprovable keeps bare `enum`.
            try:
                _et = self.il.types[td.element] \
                    if 0 <= td.element < len(self.il.types) else None
                _ukw = {0x04: 'sbyte', 0x05: 'byte', 0x06: 'short',
                        0x07: 'ushort', 0x09: 'uint', 0x0a: 'long',
                        0x0b: 'ulong'}.get(self.il._type_enum(_et) if _et is not None else 0x08)
                if _ukw:
                    ebase = ' : ' + _ukw
            except Exception:
                pass
        elif td.is_valuetype:
            kw = vis + 'partial struct'
        elif (f & 0x80) and (f & 0x100):
            # abstract + sealed with no instance content anywhere
            # (census over the fixture) is a static utility class.
            kw = vis + 'static partial class'
        else:
            kw = vis + 'partial class'
            if f & 0x80:
                kw = vis + 'abstract ' + kw[len(vis):]
            if f & 0x100:
                kw = vis + 'sealed ' + kw[len(vis):]
        name = td.name
        gparams = self._type_generic_params(td)
        base = []
        if td.parent >= 0 and not td.is_enum and not td.is_valuetype \
                and not (td.flags & 0x20):
            # interfaces inherit interfaces only (via interfaces[]
            # below); a class-typed parent slot on one is malformed.
            pt = self.il.types[td.parent] if td.parent < len(self.il.types) else None
            pn = self.il.type_name(pt) if pt else None
            if pn and pn != 'object':
                base.append(pn)
        if td.interfaces_count:
            for k in range(td.interfaces_count):
                ii = self.meta.interfaces[td.interfaces_start + k]
                t = self.il.types[ii] if ii < len(self.il.types) else None
                if t:
                    base.append(self.il.type_name(t))
        if td.is_valuetype and not td.is_enum and not base:
            pass
        hdr = '%s %s%s%s' % (kw, safe_ident(sanitize(name)), gparams, ebase if td.is_enum else '')
        if base:
            hdr += ' : ' + ', '.join(base)
        lines.append(hdr)
        return lines

    def enum_body(self, td: TypeDef) -> List[str]:
        out = []
        for k, fi in enumerate(self.meta.type_fields(td)):
            if k == 0:
                continue  # value__
            f = self.meta.fields[fi]
            v = self.default_value_of(fi)
            out.append('        %s = %s,' % (safe_ident(sanitize(f.name)), v if v is not None else '?'))
        return out

    def default_value_of(self, field_row, decl_ty=None) -> Optional[str]:
        dv = self.meta.field_default_values.get(field_row)
        if not dv:
            return None
        ti, di = dv
        return self.parse_default(ti, di, decl_ty=decl_ty)

    _UNDER_RANGE = {0x04: (-0x80, 0x7f), 0x05: (0, 0xff),
                    0x06: (-0x8000, 0x7fff), 0x07: (0, 0xffff),
                    0x08: (-0x80000000, 0x7fffffff), 0x09: (0, 0xffffffff),
                    0x0a: (-0x8000000000000000, 0x7fffffffffffffff),
                    0x0b: (0, 0xffffffffffffffff),
                    0x18: (-0x80000000, 0x7fffffff), 0x19: (-0x80000000, 0x7fffffff)}

    def _enum_default_cast(self, enum_ty, text, te=0):
        """Cast a bare underlying literal to its proved enum type
        (`(CompareFunction)4`, CS0266/CS1750 shapes A+C). Unprovable (no
        enum_members table) keeps today's raw int. Negatives parenthesize
        (CS0075: `(E)(-32)`); out-of-underlying-range constants wrap
        `unchecked` (CS0221). ponytail: cast, never member names -- names
        stay on the fold paths."""
        if enum_ty is None:
            return text
        try:
            v = int(text, 0)
        except Exception:
            return '(%s)%s' % (enum_ty, text)
        inner = '(%d)' % v if v < 0 else str(v)
        r = self._UNDER_RANGE.get(te)
        if r is not None and not r[0] <= v <= r[1]:
            return 'unchecked((%s)%s)' % (enum_ty, inner)
        return '(%s)%s' % (enum_ty, inner)

    def _proved_enum_name(self, ty):
        """C# spelling of ty when it proves an enum (enum_members table
        present), else None. The default blob records underlying types,
        so the enum must come from the declaration site (param/field
        type), never the blob. ponytail: proof-or-raw; genericinst (0x15)
        declines until observed."""
        try:
            if not isinstance(ty, tuple):
                return None
            if (ty[1] >> 16) & 0xFF not in (0x55, 0x11, 0x12):
                return None
            if not 0 <= ty[0] < len(self.meta.typedefs):
                return None
            if self.il.enum_members(ty[0]) is None:
                return None
            return self.il.type_name(ty)
        except Exception:
            return None

    def _param_default_suffix(self, m, k, p, pt, seen_opt):
        """` = <default>` suffix for one signature parameter (CS1737).
        A null-row (`data_idx == -1`) param after an earlier optional
        renders `= default` (refs, nullables and structs zero-init;
        `= null` would be illegal for structs). Byref never defaults;
        undecodable stays bare. Returns (suffix, seen_opt). ponytail:
        decline-by-default; the genuine-mid strip lives at the loop
        (order+arity preserved, so call sites cannot tell)."""
        key = m.parameter_start + k
        row = self.meta.param_default_values.get(key)
        byref = (pt[1] >> 29) & 1 if pt else 0
        if row and not byref:
            dv = self.parse_default(*row, param=True, decl_ty=pt)
            if dv:
                return ' = %s' % dv, True
            if row[1] is not None and row[1] < 0 and seen_opt:
                return ' = default', True
        return '', seen_opt

    def _strip_mid_defaults(self, ps, info):
        """Drop rendered defaults before the first bare follower
        (genuine-mid shape, 5 methods: a defaulted param ahead of a
        row-less required one). Trailing defaults stay. Order and arity
        never change, so positional call sites are unaffected."""
        if any(info) and not all(info):
            for i, v in enumerate(info):
                if v and any(not w for w in info[i + 1:]):
                    ps[i] = ps[i].rsplit(' = ', 1)[0]
        return ps

    def parse_default(self, type_idx, data_idx, param=False, decl_ty=None) -> Optional[str]:
        if data_idx is None or data_idx < 0:
            return None
        t = self.il.types[type_idx] if 0 <= type_idx < len(self.il.types) else None
        if t is None:
            return None
        te = self.il._type_enum(t)
        d = self.meta.d
        off = self.meta.dv_off + data_idx
        # v29+ stores i4/u4/string (and enums over those underlyings) in the
        # WriteCompressedUInt32 format; everything else stays raw fixed-size.
        v29 = self.meta.version >= 29
        enum_ty = None
        rte = te  # range-check type: blob te unless an enum proves narrower
        try:
            if te in (0x55, 0x11):  # enum: encode via the underlying type
                td = self.meta.typedefs[t[0]] if t[0] < len(self.meta.typedefs) else None
                if not td or td.element < 0:
                    return None
                enum_ty = self._proved_enum_name(t)
                te = self.il._type_enum(self.il.types[td.element])
            if enum_ty is None and decl_ty is not None:
                # the blob records underlying types; the enum comes
                # from the declaration site (param/field type). The range
                # check also follows the enum (blob u4 vs enum i4:
                # DesiredAccess 2148532224 needs unchecked).
                enum_ty = self._proved_enum_name(decl_ty)
                if enum_ty is not None:
                    try:
                        _dt = self.meta.typedefs[decl_ty[0]] \
                            if 0 <= decl_ty[0] < len(self.meta.typedefs) else None
                        _et = self.il.types[_dt.element] \
                            if _dt is not None and 0 <= _dt.element < len(self.il.types) else None
                        if _et is not None:
                            rte = self.il._type_enum(_et)
                    except Exception:
                        pass
            if te == 0x02:
                return 'true' if d[off] else 'false'
            if te in (0x04, 0x05):
                v = d[off]
                return self._enum_default_cast(enum_ty, str(v - 0x100 if te == 0x04 and v >= 0x80 else v), rte)
            if te == 0x03:
                c = chr(u16(d, off))
                if c.isprintable():
                    return "'%s'" % c
                return "'\\u%04x'" % u16(d, off)
            if te in (0x06, 0x07):
                v = u16(d, off)
                return self._enum_default_cast(enum_ty, str(v - 0x10000 if te == 0x06 and v >= 0x8000 else v), rte)
            if te == 0x08:
                return self._enum_default_cast(enum_ty, str(compressed_int(d, off)[0] if v29 else i32(d, off)), rte)
            if te == 0x09:
                return self._enum_default_cast(enum_ty, str(read_compressed_uint(d, off)[0] if v29 else u32(d, off)), rte)
            if te == 0x0a:
                return self._enum_default_cast(enum_ty, str(i64(d, off)), rte)
            if te == 0x0b:
                return self._enum_default_cast(enum_ty, str(u64(d, off)), rte)
            if te in (0x18, 0x19):
                return self._enum_default_cast(enum_ty, str(i32(d, off)), rte)
            if te == 0x0c:
                return repr_f32(struct.unpack_from('<f', d, off)[0])
            if te == 0x0d:
                return repr_f64(struct.unpack_from('<d', d, off)[0])
            if te == 0x0e:
                if v29:
                    ln, lnlen = compressed_int(d, off)
                else:
                    ln, lnlen = i32(d, off), 4
                s = d[off + lnlen:off + lnlen + max(0, min(ln, 512))].decode('utf-8', 'replace')
                return meta_lit_repr(s)
        except Exception:
            return None
        return None

    def _explicit_impl_qualifier(self, m, td):
        """Interface head for an undotted explicit implementation, else None.

        A private+final+virtual method (`0x61` bits) with a plain name is
        the explicit-implementation shape (compiler-generated async and
        iterator `MoveNext`/`SetStateMachine` ship exactly so, with the
        dotted name missing from metadata). It implements the unique
        directly-listed interface method with the same name and the same
        rendered return/parameter types; anything else (no match, several
        matches, static, dotted already) declines and keeps today's
        spelling."""
        try:
            f = m.flags
            if m.is_static or (f & 7) != 1 or (f & 0x60) != 0x60:
                return None
            if not m.name or '.' in m.name or m.name.startswith('.'):
                return None
            ps = self.meta.method_params(m)
            pt = self.il.types[m.return_type] \
                if 0 <= m.return_type < len(self.il.types) else None
            want = (m.name, self.il.type_name(pt) if pt else None,
                    tuple(self.il.type_name(self.il.types[p.type]
                                        if 0 <= p.type < len(self.il.types)
                                        else None) for p in ps))
            hits = []
            for k in range(getattr(td, 'interfaces_count', 0)):
                ii = self.meta.interfaces[td.interfaces_start + k]
                tup = self.il.types[ii] if 0 <= ii < len(self.il.types) else None
                if tup is None:
                    continue
                idx = None
                if self.il._type_enum(tup) in (0x11, 0x12):
                    idx = tup[0]
                if idx is None or not 0 <= idx < len(self.meta.typedefs):
                    continue
                itd = self.meta.typedefs[idx]
                for mj in range(itd.method_start, itd.method_start + itd.method_count):
                    m2 = self.meta.methods[mj]
                    ps2 = self.meta.method_params(m2)
                    pt2 = self.il.types[m2.return_type] \
                        if 0 <= m2.return_type < len(self.il.types) else None
                    got = (m2.name, self.il.type_name(pt2) if pt2 else None,
                           tuple(self.il.type_name(self.il.types[p.type]
                                               if 0 <= p.type < len(self.il.types)
                                               else None) for p in ps2))
                    if got == want:
                        hits.append(self.il.type_name(tup))
                        break
            if len(hits) != 1:
                return None
            return hits[0]
        except Exception:
            return None

    # -- members ------------------------------------------------------------
    def method_sig(self, m: MethodDef, td: TypeDef, extern_=False) -> str:
        # CLI finalizers cannot spell `override void Finalize()`
        # (CS0249 x61); C# wants a destructor. Guarded to the exact
        # finalizer shape (instance, non-generic, parameterless, void)
        # so FinalizeXxx lookalikes and overloads keep today's spelling.
        # ponytail: reuses ctor_sig's class spelling (keeps _N arity,
        # drops <T>; nested td yields the innermost name); bodies and
        # RVA comments pass through untouched.
        if m.name == 'Finalize' and not m.is_static and m.generic_container == -1:
            if not self.meta.method_params(m):
                rt = self.il.types[m.return_type] if 0 <= m.return_type < len(self.il.types) else None
                if rt is not None and self.il.type_name(rt) == 'void':
                    return '~%s()' % safe_ident(sanitize(td.name))
        f = m.flags
        vis = self._pub(METH_VIS.get(f & 7, ''))
        # CLI MethodAttributes: Final=0x20, Virtual=0x40,
        # NewSlot=0x100, Abstract=0x400. TypeAttributes use different bits.
        explicit = '.' in m.name
        qual = None if explicit else self._explicit_impl_qualifier(m, td)
        if qual is not None:
            explicit = True
        mods = '' if explicit else vis
        if m.is_static:
            mods += 'static '
        if td.flags & 0x20:
            mods = 'static ' if m.is_static else ''
            if m.is_static and f & 0x400:
                mods += 'abstract '
        elif not explicit:
            if f & 0x400:
                mods += 'abstract '
                if f & 0x40 and not f & 0x100:
                    mods += 'override '
            elif f & 0x40 and not m.is_static:
                if not f & 0x100:
                    mods += 'sealed override ' if f & 0x20 else 'override '
                elif not f & 0x20:
                    mods += 'virtual '
                # Final+NewSlot implements an interface without exposing
                # an overridable C# member; it is not a sealed override.
        rt = self.il.types[m.return_type] if 0 <= m.return_type < len(self.il.types) else None
        rtname = self.il.type_name(rt) if rt else 'void'
        if rtname == 'void':
            pass
        # explicit-interface `IFoo.Bar`: escape the member component only.
        # The qualifier keeps its generic structure: a blanket sanitize()
        # here would eat the commas (`IDictionary<TKey, TValue>`), so split
        # first and sanitize each half through its own rule.
        raw = csharp_type_name(m.name)
        if '.' in raw:
            head, _, tail = raw.rpartition('.')
            name = sanitize_qualifier(self._arity_qualifier(head, td)) + '.' + safe_ident(tail)
        elif qual is not None:
            name = sanitize_qualifier(self._arity_qualifier(qual, td)) + '.' + safe_ident(raw)
        else:
            name = safe_ident(raw)
        gp = ''
        if m.generic_container != -1:
            gc = self.meta.generic_containers[m.generic_container]
            gplist = []
            for k in range(gc[1]):
                gi = gc[3] + k
                if gi < len(self.meta.generic_parameters):
                    gplist.append(self.meta.generic_parameters[gi][1])
            gp = '<%s>' % ', '.join(gplist) if gplist else ''
        ps = []
        info = []
        seen_opt = False
        params = self.meta.method_params(m)
        for k, p in enumerate(params):
            pt = self.il.types[p.type] if 0 <= p.type < len(self.il.types) else None
            tn = self.il.type_name(pt) if pt else 'object'
            byref = (pt[1] >> 29) & 1 if pt else 0
            pmod = 'ref ' if byref else ''
            suf, seen_opt = self._param_default_suffix(m, k, p, pt, seen_opt)
            ps.append('%s%s %s%s' % (pmod, tn, safe_ident(p.name), suf))
            info.append(bool(suf))
        ps = self._strip_mid_defaults(ps, info)
        if m.name in ('op_Explicit', 'op_Implicit') and m.is_static \
                and '.' not in m.name and m.generic_container == -1 and len(params) == 1 \
                and not any(' = ' in s for s in ps):
            # conversion-operator twins (Decimal.op_Explicit x4...): the
            # whole group renders `explicit/implicit operator`, since no
            # two same-signature members may coexist (CS0111 x10).
            # ponytail: group-scoped (singletons + non-colliding call
            # sites untouched); byref params render by value (operators
            # cannot take ref; the view read is pure); params with
            # defaults decline (operator-illegal).
            try:
                _pts = tuple(self.il.types[p.type] for p in params)
                _conv = self.il.op_collision_conv(m.declaring, m.name, _pts)
            except Exception:
                _conv = None
            if _conv is not None:
                _umods = mods
                _ops = [s[4:] if s.startswith('ref ') else s for s in ps]
                if '*' in rtname or any('*' in s for s in _ops):
                    _umods += 'unsafe '
                return '%s%s operator %s(%s)' % (_umods, _conv, rtname, ', '.join(_ops))
        if '*' in rtname or any('*' in s for s in ps):
            mods += 'unsafe '
        if extern_:
            mods += 'extern '
        return '%s%s %s%s(%s)' % (mods, rtname, name, gp, ', '.join(ps))

    def _unity_serialized(self, td: TypeDef, field_name: str) -> bool:
        """[SerializeField]: a MonoBehaviour / ScriptableObject descendant.
        The caller has already established that this is a non-public
        instance field (public fields serialize without the attribute);
        whether Unity really serializes this one is not knowable without
        the custom-attribute blob, so it stays a well-scoped guess."""
        if not field_name:
            return False
        cache = self.__dict__.setdefault('_us_cache', {})
        cached = cache.get(td.index)
        if cached is None:
            cached = False
            cur = td.index
            hops = 0
            while 0 <= cur < len(self.meta.typedefs) and hops < 12:
                t = self.meta.typedefs[cur]
                if t.parent < 0 or t.parent >= len(self.il.types):
                    break
                pt = self.il.types[t.parent]
                pn = self.il.type_name(pt).split('<')[0]
                if pn in ('UnityEngine.MonoBehaviour', 'UnityEngine.ScriptableObject'):
                    cached = True
                    break
                if self.il._type_enum(pt) not in (0x11, 0x12) \
                        or not (0 <= pt[0] < len(self.meta.typedefs)):
                    break
                if pt[0] == cur:
                    break
                cur = pt[0]
                hops += 1
            cache[td.index] = cached
        return cached

    def _is_delegate_td(self, td: TypeDef) -> bool:
        """True for user delegate types (MulticastDelegate subclasses).

        System.Delegate/MulticastDelegate themselves stay classes.
        Cached per emitter instance (td.index is binary-local).
        """
        try:
            hit = self.__dict__.setdefault('_delegate_cache', {}).get(td.index)
            if hit is not None:
                return hit
            res = False
            if (td.namespace, td.name) not in (
                    ('System', 'Delegate'),
                    ('System', 'MulticastDelegate')):
                try:
                    chain = self.il.base_chain_tds(td.index)
                except Exception:
                    chain = ()
                for ti in chain[1:]:
                    t2 = self.meta.typedefs[ti] \
                        if 0 <= ti < len(self.meta.typedefs) else None
                    if t2 is not None and t2.name in (
                            'MulticastDelegate', 'Delegate'):
                        res = True
                        break
            self.__dict__.setdefault('_delegate_cache', {})[td.index] = res
            return res
        except Exception:
            return False

    def _delegate_invoke(self, td: TypeDef):
        """The instance Invoke MethodDef of a delegate typedef, else None."""
        try:
            for mi in self.meta.type_methods(td):
                m = self.meta.methods[mi]
                if m.name == 'Invoke' and not m.is_static:
                    return m
            return None
        except Exception:
            return None

    def _delegate_viable(self, td: TypeDef) -> bool:
        """True when the typedef can render as a delegate declaration.

        Needs the instance Invoke (the signature source) and no
        fields, properties, events, or nested types (a `delegate`
        declaration cannot carry them). Cached per emitter instance.
        """
        try:
            hit = self.__dict__.setdefault(
                '_delegate_viable_cache', {}).get(td.index)
            if hit is not None:
                return hit
            res = self._delegate_invoke(td) is not None \
                and not list(self.meta.type_fields(td)) \
                and not td.property_count and not td.event_count \
                and not td.nested_count
            self.__dict__.setdefault(
                '_delegate_viable_cache', {})[td.index] = res
            return res
        except Exception:
            return False

    def emit_delegate(self, td: TypeDef, out: List[str], pre: str) -> bool:
        """`delegate R Name(params);` for a user delegate type.

        The runtime-provided .ctor/Invoke/BeginInvoke/EndInvoke
        members are covered by the declaration itself.
        """
        try:
            inv = self._delegate_invoke(td)
            vis = TYPE_VIS.get((td.flags >> 0) & 7, '')
            if td.declaring < 0 and (td.flags & 7) > 1:
                vis = 'internal '
            vis = self._pub(vis)
            rt = self.il.types[inv.return_type] \
                if 0 <= inv.return_type < len(self.il.types) else None
            rtname = self.il.type_name(rt) if rt else 'void'
            ps = []
            for p in self.meta.method_params(inv):
                pt = self.il.types[p.type] \
                    if 0 <= p.type < len(self.il.types) else None
                tn = self.il.type_name(pt) if pt else 'object'
                byref = (pt[1] >> 29) & 1 if pt else 0
                ps.append('%s%s %s' % ('ref ' if byref else '', tn,
                                       safe_ident(p.name)))
            nm = safe_ident(sanitize(td.name)) + \
                self._type_generic_params(td)
            unsafe = 'unsafe ' if '*' in rtname or any(
                '*' in p for p in ps) else ''
            out.append('')
            if (td.flags & 0x2000) and not td.is_enum \
                    and not td.is_valuetype:
                # qualified so the using tracker imports System; the file
                # boundary strips it back when unambiguous.
                out.append(pre + '[System.Serializable]')
            out.append('%s%s%sdelegate %s %s(%s);' % (
                pre, vis, unsafe, rtname, nm, ', '.join(ps)))
            return True
        except Exception:
            return False

    _STATE_MACHINE_RX = re.compile(r'^<([^>]+)>d__(\d+)$')

    def _state_machine_note(self, td: TypeDef) -> Optional[str]:
        """`// iterator state machine for Foo (...)` above a compiler-generated
        `<Foo>d__N` type, else None.

        The name only nominates the type: the typedef must own a MoveNext
        (the method is the proof; 543 of 543 nominated types on the fixture
        have one, but a name is not evidence) and the interface list picks
        the label -- IAsyncStateMachine is async, IEnumerator is iterator.
        A type that lists both or neither gets no note rather than a guess.
        """
        m = self._STATE_MACHINE_RX.match(td.name or '')
        if m is None:
            return None
        try:
            if not any(self.meta.methods[mi].name == 'MoveNext'
                       or (self.meta.methods[mi].name or '').endswith('.MoveNext')
                       for mi in self.meta.type_methods(td)):
                return None
            kinds = set()
            for k in range(td.interfaces_count):
                ii = self.meta.interfaces[td.interfaces_start + k]
                tup = self.il.types[ii] if 0 <= ii < len(self.il.types) else None
                if tup is None:
                    continue
                base = re.sub(r'_\d+$', '', self.il.type_name(tup).split('<')[0])
                if base == 'System.Runtime.CompilerServices.IAsyncStateMachine':
                    kinds.add('async')
                elif base in ('System.Collections.IEnumerator',
                              'System.Collections.Generic.IEnumerator'):
                    kinds.add('iterator')
        except Exception:
            return None
        if len(kinds) != 1:
            return None
        return ('// %s state machine for %s (compiler-generated; MoveNext '
                'drives the inlined original body)' % (kinds.pop(), m.group(1)))

    def _gate_header(self) -> Optional[str]:
        """First line of every type file in a compile-gate build, else None.

        `--publicize` and `--raw-addr` exist so the Roslyn gate measures
        lifting errors instead of accessibility noise; their output must
        never be mistaken for the faithful tree. Default output is
        unchanged."""
        parts = []
        if getattr(self, 'publicize', False):
            parts.append('every member is public and readonly is dropped (--publicize)')
        if getattr(self, 'raw_addr', False):
            parts.append('`(byte*)E` raw bases route through __addr(E) (--raw-addr)')
        if not parts:
            return None
        return ('// COMPILE-GATE OUTPUT -- NOT FAITHFUL SOURCE: %s. '
                'Built to measure compiler errors, not to read.' % '; '.join(parts))

    def emit_type(self, td: TypeDef, out: List[str], indent='    ') -> bool:
        pre = indent
        if self._is_delegate_td(td) and self._delegate_viable(td):
            self.emit_delegate(td, out, pre)
            return True
        hdr = self.type_decl_line(td)
        out.append('')
        note = self._state_machine_note(td)
        if note:
            out.append(pre + note)
        comment = []
        if td.generic_container != -1:
            pass
        if (td.flags & 0x2000) and not td.is_enum and not td.is_valuetype:
            out.append(pre + '[System.Serializable]')
        out.append(pre + hdr[0])
        out.append(pre + '{')
        if td.is_enum:
            out.extend(self.enum_body(td))
            out.append(pre + '}')
            return True
        # Preserve real storage; accessors must not recursively read themselves.
        fmax = self.meta.type_fields(td)
        for fi in fmax:
            f = self.meta.fields[fi]
            ft = self.il.types[f.type] if 0 <= f.type < len(self.il.types) else None
            if ft is None:
                continue
            fn = safe_ident(sanitize(source_field_name(self.il, fi)))
            fa = field_attrs(self.il, f)
            ftname = self.il.type_name(ft)
            is_static_field = bool(fa & FA_STATIC)
            off_note = self.field_off_note(td, fi, is_static_field)
            vis = self._pub(FIELD_VIS.get(fa & 7, 'public '))
            # const is FieldAttributes.Literal, NOT `has a decodable
            # default value` -- RVA data blobs carry a dv row too, and 14
            # of them decoded to an int and printed as const.
            if fa & FA_LITERAL:
                dv = self.default_value_of(fi, ft)
                if dv is not None:
                    out.append(pre + '    %sconst %s %s = %s;' % (
                        vis, ftname, fn, dv))
                    continue
                # a literal we cannot decode: `const T X;` does not compile
                is_static_field = True
                fa |= FA_INITONLY
            mods = vis
            if is_static_field:
                mods += 'static '
            # fix 127: `--publicize` also drops `readonly` -- inlined
            # native ctors/initializers store to init-only fields from
            # other types (CS0191 once the CS0122 wall is gone)
            if fa & FA_INITONLY and not getattr(self, 'publicize', False):
                mods += 'readonly '
            if '*' in ftname:
                mods += 'unsafe '
            # [SerializeField] only means something on a field Unity would
            # not serialize by itself, i.e. a non-public instance field
            attr = ''
            if not is_static_field and (fa & 7) != 6 \
                    and self._unity_serialized(td, f.name):
                attr = '[UnityEngine.SerializeField] '
            out.append(pre + '    %s%s%s %s;%s' % (
                attr, mods, ftname, fn, off_note))
        # properties: accessors render inside the property, not as methods
        accessor_idxs = set()
        for k in range(td.property_count):
            pr = self.meta.properties[td.property_start + k]
            for x in (pr[1], pr[2]):
                if x is not None and x >= 0 and 0 <= td.method_start + x < len(self.meta.methods):
                    accessor_idxs.add(td.method_start + x)
            self.emit_property(td, out, pre, pr)
        # C# has add/remove syntax but no raise accessor: keep raise as a
        # normal method instead of silently dropping its native body.
        for k in range(td.event_count):
            ev = self.meta.events[td.event_start + k]
            if self.emit_event(td, out, pre, ev):
                for x in ev[2:4]:
                    if self._rel_method(td, x) is not None:
                        accessor_idxs.add(td.method_start + x)
        # methods
        skip_delegate = self._is_delegate_td(td) \
            and self._delegate_viable(td)
        for mi in self.meta.type_methods(td):
            if mi in accessor_idxs:
                continue
            m = self.meta.methods[mi]
            if skip_delegate and (m.name in ('.ctor', '.cctor', 'Invoke')
                                  or m.name.startswith(
                                      ('BeginInvoke', 'EndInvoke'))):
                # covered by the delegate declaration itself
                continue
            self.emit_method(m, td, out, pre + '    ')
        # nested types
        for k in range(td.nested_count):
            ni = self.meta.nested_types[td.nested_start + k]
            if 0 <= ni < len(self.meta.typedefs):
                self.emit_type(self.meta.typedefs[ni], out, pre + '    ')
        out.append(pre + '}')
        return True

    def field_off_note(self, td, fi, is_static):
        """Trailing `// 0x..` comment for a field declaration. Generic type
        definitions have no field-offset table (offsets live per
        instantiation), so every lookup there returns 0 -- print nothing
        rather than a fake `0x0`."""
        fo = self.il.field_offsets[td.index] \
            if td.index < len(self.il.field_offsets) else None
        if fo is None or td.generic_container != -1:
            return ''
        off = self.field_off_display(td, fi)
        if not off and not is_static:
            return ''  # no instance field can sit in the object header
        return ' // static @0x%x' % off if is_static else ' // 0x%x' % off

    def field_off_display(self, td, fi):
        fo = self.il.field_offsets[td.index] if td.index < len(self.il.field_offsets) else None
        if fo is None:
            return 0
        for k, off in enumerate(fo):
            if td.field_start + k == fi:
                return off
        return 0

    def prop_type(self, getter):
        if getter is None:
            return 'object'
        t = self.il.types[getter.return_type] if 0 <= getter.return_type < len(self.il.types) else None
        return self.il.type_name(t) if t else 'object'

    def render_params(self, m: MethodDef) -> str:
        ps = []
        info = []
        seen_opt = False
        params = self.meta.method_params(m)
        for k, p in enumerate(params):
            pt = self.il.types[p.type] if 0 <= p.type < len(self.il.types) else None
            tn = self.il.type_name(pt) if pt else 'object'
            byref = (pt[1] >> 29) & 1 if pt else 0
            pmod = 'ref ' if byref else ''
            suf, seen_opt = self._param_default_suffix(m, k, p, pt, seen_opt)
            ps.append('%s%s %s%s' % (pmod, tn, safe_ident(p.name), suf))
            info.append(bool(suf))
        ps = self._strip_mid_defaults(ps, info)
        return ', '.join(ps)

    def ctor_sig(self, m: MethodDef, td: TypeDef) -> str:
        """Instance/static constructor signature: public ClassName() /
        static ClassName() -- no return type, no .ctor name."""
        # Match the emitted type identifier, including its arity suffix.
        # C# constructors omit <T>, but must retain Box_1 in Box_1<T>.
        cname = safe_ident(sanitize(td.name))
        if m.name == '.cctor':
            return 'static %s()' % cname
        vis = self._pub(METH_VIS.get((m.flags >> 0) & 7, 'public '))
        params = self.render_params(m)
        if '*' in params:
            return '%sunsafe %s(%s)' % (vis, cname, params)
        return '%s%s(%s)' % (vis, cname, params)

    def ctor_base_initializer(self, td: TypeDef) -> Optional[str]:
        """: base() when the parent is a real class (not object/valuetype)."""
        if td.is_valuetype or td.is_enum or td.parent < 0:
            return None
        if td.parent >= len(self.il.types):
            return None
        pn = self.il.type_name(self.il.types[td.parent])
        if not pn or pn.split('<')[0] in ('object', 'System.Object',
                                          'System.ValueType', 'System.Enum'):
            return None
        return 'base()'

    _CTORCALL_RX = re.compile(r'^(this|base)\.\.ctor\s*\((.*?)\)\s*;(?:\s*return\s*;)?\s*$')

    def _ctor_body(self, lines: List[str]):
        """Pull base..ctor()/this..ctor() calls out of a constructor body:
        returns (initializer-or-None, body). Trailing bare returns on an
        otherwise finished ctor disappear with the promoted call."""
        init = None
        out = []
        for st in lines:
            m = self._CTORCALL_RX.match(st.strip())
            if m:
                init = '%s(%s)' % (m.group(1), m.group(2).strip())
                continue
            out.append(st)
        while out and out[-1].strip() == 'return;':
            out.pop()
        return init, out

    def _void_tail_strip(self, body, m):
        rt = self.il.types[m.return_type] if 0 <= m.return_type < len(self.il.types) else None
        if rt is not None and ((rt[1] >> 16) & 0xFF) == 0x01:
            while body and body[-1].strip() == 'return;':
                body.pop()
        return body

    def _lift_body(self, m: MethodDef, td: TypeDef, abstract=False):
        """Lift a body or emit an explicit unavailable-body throw.

        Only abstract declarations return None; only actual lifts are counted.
        """
        if abstract:
            return None
        has_body = m.addr and self.with_bodies and self.lifter
        if self.max_methods is not None and self.lifted >= self.max_methods:
            has_body = False
        if not has_body:
            return ['throw new global::System.NotImplementedException("Method body was not recovered.");']
        structured_error = None
        if self.decompiler is not None:
            try:
                body = self._void_tail_strip(self.decompiler.lift_method(m, td), m)
                self.lifted += 1
                self._record_body(m, body)
                return body
            except Exception as ex:
                structured_error = ex
        self.fallbacks += 1
        if self.verbose:
            print('warning: structured lift fallback mi=%d VA=%#x %s.%s: %s' % (
                m.index, m.addr, td.name, m.name,
                structured_error or getattr(self, 'decompiler_error', None) or
                'structured backend unavailable'), file=sys.stderr)
        try:
            body = self.lifter.lift(m, td)
            self.lifted += 1
            # The linear fallback has no type analysis: object, not var.
            body = [re.sub(r'^(\s*)var (\w+)( = )', r'\1object \2\3', l)
                    for l in body]
            body = self._void_tail_strip(body, m)
            self._record_body(m, body)
            return body
        except Exception as ex:
            self.failed += 1
            return ['/* lift failed: %s */' % ex]

    def _rel_method(self, td: TypeDef, rel: int) -> Optional[MethodDef]:
        """Property/event accessor rows store method indices RELATIVE to the
        type's method range (metadata v27+); -1 means the accessor is absent."""
        if rel is None or rel < 0:
            return None
        mi = td.method_start + rel
        return self.meta.methods[mi] if 0 <= mi < len(self.meta.methods) else None

    def _member_name(self, raw, td):
        raw = csharp_type_name(raw)
        if '.' in raw:
            head, _, tail = raw.rpartition('.')
            return sanitize_qualifier(self._arity_qualifier(head, td)) + '.' + safe_ident(tail)
        return safe_ident(sanitize(raw))

    def _accessor_modifiers(self, td, present, explicit=False):
        """Use the most accessible accessor, preserving method dispatch flags."""
        if not present:
            return '' if td.flags & 0x20 or explicit else 'public '
        # Accessibility is a lattice: protected + internal has their union.
        vis = {getattr(a, 'flags', 6) & 7 for a in present}
        access = 6 if 6 in vis else 5 if 5 in vis or {3, 4} <= vis else max(vis)
        chosen = next((a for a in present if getattr(a, 'flags', 6) & 7 == access), present[0])
        f = getattr(chosen, 'flags', 6)
        mods = '' if explicit or td.flags & 0x20 else self._pub(METH_VIS.get(access, ''))
        if all(a.is_static for a in present):
            mods += 'static '
        abstract = all(getattr(a, 'flags', 0) & 0x400 for a in present)
        if td.flags & 0x20:
            if all(a.is_static for a in present) and abstract:
                mods += 'abstract '
        elif not explicit:
            if abstract:
                mods += 'abstract '
                if f & 0x40 and not f & 0x100:
                    mods += 'override '
            elif f & 0x40 and not chosen.is_static:
                if not f & 0x100:
                    mods += 'sealed override ' if f & 0x20 else 'override '
                elif not f & 0x20:
                    mods += 'virtual '
        return mods

    def _accessor_lines(self, m, td, aliases=None):
        if getattr(m, 'flags', 0) & 0x400:
            return None
        body = self._lift_body(m, td)
        if body is None or not aliases:
            return body
        # Only parameter tokens, never member names or literal/comment text.
        from il2cpp.dec.highlevel import _HighLevelMixin
        mapping = {safe_ident(k): v for k, v in aliases.items() if safe_ident(k) != v}
        if not mapping:
            return body
        comment = False
        result = []
        for line in body:
            # Temporarily protect qualified member tokens from parameter rename.
            protected = {}
            def protect(match):
                key = '__accessor_member_%d__' % len(protected)
                protected[key] = match.group(0)
                return key
            text = re.sub(r'\.\s*(?:' + '|'.join(re.escape(k) for k in mapping) + r')\b', protect, line)
            text, comment = _HighLevelMixin._replace_semantic_names(text, mapping, comment)
            for key, value in protected.items():
                text = text.replace(key, value)
            result.append(text)
        return result

    def _emit_accessor(self, out, pre, kind, m, body, visibility=''):
        if getattr(m, 'addr', 0):
            base = getattr(self.il.bin, 'image_base', 0)
            out.append('%s// RVA: 0x%X VA: 0x%X' % (pre, m.addr - base, m.addr))
        if body is None:
            out.append(pre + visibility + kind + ';')
            return
        out.append(pre + visibility + kind)
        out.append(pre + '{')
        out.extend(pre + '    ' + line.rstrip() if line.strip() else '' for line in body)
        out.append(pre + '}')

    def emit_property(self, td: TypeDef, out: List[str], pre: str, pr,
                      bk_offs=None):
        getter = self._rel_method(td, pr[1])
        setter = self._rel_method(td, pr[2])
        present = [a for a in (getter, setter) if a is not None]
        raw = self.meta.getstr(pr[0])
        pname = self._member_name(raw, td)
        explicit = '.' in raw
        gparams = list(self.meta.method_params(getter)) if getter else []
        sparams = list(self.meta.method_params(setter)) if setter else []
        ptype = self.prop_type(getter)
        if not getter and sparams:
            pt = sparams[-1].type
            ptype = self.il.type_name(self.il.types[pt]) if 0 <= pt < len(self.il.types) else 'object'
        index_params = gparams if getter else sparams[:-1]
        if index_params:
            prefix = pname.rpartition('.')[0] + '.' if explicit else ''
            params = ', '.join('%s %s' % (self.il.type_name(self.il.types[p.type]), safe_ident(p.name)) for p in index_params)
            pname = prefix + 'this[' + params + ']'
        mods = self._accessor_modifiers(td, present, explicit)
        if '*' in ptype or any('*' in self.il.type_name(self.il.types[p.type]) for p in index_params):
            mods += 'unsafe '
        aliases = {p.name: safe_ident(q.name) for p, q in zip(sparams[:-1], index_params)}
        if sparams:
            aliases[sparams[-1].name] = 'value'
        gbody = self._accessor_lines(getter, td) if getter else None
        sbody = self._accessor_lines(setter, td, aliases) if setter else None
        off = (bk_offs or {}).get(raw, '')
        header = '%s    %s%s %s' % (pre, mods, ptype, pname)
        # Keep compact bodyless declarations (abstract/interface/signatures).
        vis = {getattr(a, 'flags', 6) & 7 for a in present}
        unequal = len(present) == 2 and len(vis) > 1 and not explicit and not td.flags & 0x20 \
            and not getattr(self, 'publicize', False)
        def access(a):
            if not unequal:
                return ''
            v = METH_VIS.get(getattr(a, 'flags', 6) & 7, '')
            return '' if mods.startswith(v) else v
        if gbody is None and sbody is None:
            out.append(header + ' { ' + (access(getter) + 'get; ' if getter else '') + (access(setter) + 'set; ' if setter else '') + '}' + off)
            return
        out.extend([header + off, pre + '    {'])
        for kind, m, body in (('get', getter, gbody), ('set', setter, sbody)):
            if m is not None:
                self._emit_accessor(out, pre + '        ', kind, m, body, access(m))
        out.append(pre + '    }')

    def emit_event(self, td, out, pre, ev):
        add = self._rel_method(td, ev[2])
        remove = self._rel_method(td, ev[3])
        if add is None or remove is None:
            # Malformed/unrepresentable event: retain its ordinary methods.
            out.append(pre + '    // Event has no complete add/remove pair: ' + safe_ident(sanitize(self.meta.getstr(ev[0]))))
            return False
        raw = self.meta.getstr(ev[0])
        name = self._member_name(raw, td)
        mods = self._accessor_modifiers(td, [add, remove], '.' in raw)
        ty = self.il.type_name(self.il.types[ev[1]]) if 0 <= ev[1] < len(self.il.types) else 'System.Action'
        header = pre + '    ' + mods + 'event ' + ty + ' ' + name
        bodies = []
        for m in (add, remove):
            params = list(self.meta.method_params(m))
            aliases = {params[-1].name: 'value'} if params else {}
            bodies.append(self._accessor_lines(m, td, aliases))
        if all(getattr(a, 'flags', 0) & 0x400 for a in (add, remove)):
            out.append(header + ';')
            return True
        out.extend([header, pre + '    {'])
        for kind, m, body in zip(('add', 'remove'), (add, remove), bodies):
            self._emit_accessor(out, pre + '        ', kind, m, body)
        out.append(pre + '    }')
        return True

    def _pinvoke_decl(self, m: MethodDef, td: TypeDef, pre: str):
        """`[DllImport(...)] static extern ...;` for a P/Invoke method.

        A `[DllImport]` method has no managed body: IL2CPP compiles it to a
        marshalling stub whose `PInvokeArguments` (module, entry point,
        calling convention, charset, exact-spelling) is still in the bytes.
        Reading it back is the original declaration, so the lifted
        marshalling plumbing is replaced by what the source actually said.
        Only a proven PInvokeImpl flag and a fully decoded struct qualify;
        everything else keeps its lifted body. -- fix 145
        """
        cache = self.__dict__.setdefault('_pinvoke_cache', {})
        va = m.addr
        if va not in cache:
            try:
                cache[va] = stub_arguments(self.il.bin, va)
            except Exception:
                cache[va] = None
        args = cache[va]
        if not args:
            return None
        attr = dllimport_attribute(args, m.name)
        if attr is None:
            return None
        rva = m.addr - self.il.bin.image_base if hasattr(self.il.bin, 'image_base') else m.addr
        sig = self.method_sig(m, td, extern_=True)
        return ['%s%s' % (pre, attr),
                '%s%s; // RVA: 0x%X VA: 0x%X' % (pre, sig, rva, m.addr)]

    def emit_method(self, m: MethodDef, td: TypeDef, out: List[str], pre: str):
        is_ctor = m.name in ('.ctor', '.cctor')
        if not is_ctor and m.addr and (m.flags & 0x2000):
            decl = self._pinvoke_decl(m, td, pre)
            if decl:
                out.extend(decl)
                return
        sig = self.ctor_sig(m, td) if is_ctor else self.method_sig(m, td)
        abstract = bool(m.flags & 0x400) and not is_ctor
        body = self._lift_body(m, td, abstract)
        ctor_init = None
        if is_ctor:
            if body:
                ctor_init, body = self._ctor_body(body)
            if m.name == '.ctor' and not ctor_init:
                ctor_init = self.ctor_base_initializer(td)
        if abstract:
            out.append('%s%s; // RVA: 0x%x VA: 0x%x' % (pre, sig, m.addr or 0, m.addr or 0)
                       if m.addr else '%s%s;' % (pre, sig))
            return
        if m.addr:
            slot_note = ' Slot: %d' % m.slot if m.slot != 0xFFFF else ''
            rva = m.addr - self.il.bin.image_base if hasattr(self.il.bin, 'image_base') else m.addr
            out.append('%s// RVA: 0x%X VA: 0x%X%s' % (pre, rva, m.addr, slot_note))
        out.append('%s%s%s' % (pre, sig, (' : ' + ctor_init) if ctor_init else ''))
        out.append('%s{' % pre)
        if body:
            for l in body:
                if not l.strip():
                    out.append('')
                elif l.startswith(' '):
                    # structured output already carries relative indentation
                    out.append(pre + l.rstrip())
                else:
                    out.append(pre + l.rstrip())
        out.append('%s}' % pre)

    # -- assembly: one .cs file per top-level type --------------------------
    def file_name_for(self, td: TypeDef) -> str:
        m = re.match(r'^(.*?)(?:`(?:\d+))?$', td.name)
        base = re.sub(r'[^A-Za-z0-9_.-]', '_', m.group(1)).strip('._-') or 'Type'
        return base

    def seg(self, part: str) -> str:
        segm = re.sub(r'[^A-Za-z0-9_.-]', '_', part).strip('.')
        return segm or '_'

    _SUB_REF_RX = re.compile(r'(?<![\w@.])sub_([0-9a-f]+)(?![\w])')

    @classmethod
    def _stub_collect(cls, text):
        """All `sub_<hex>` VAs referenced as calls in emitted text."""
        if not text:
            return set()
        return set(m.group(1) for m in cls._SUB_REF_RX.finditer(text))

    @classmethod
    def _real_sub_names(cls, meta):
        """`sub_<hex>` spellings that are REAL metadata method names."""
        try:
            return frozenset(
                md.name[4:] for md in meta.methods
                if (md.name or '').startswith('sub_')
                and re.fullmatch(r'sub_[0-9a-f]+', md.name or ''))
        except Exception:
            return frozenset()

    def _stub_owners(self, va):
        """Short honesty note per VA: owner count/names, or unregistered."""
        try:
            cands = self.il.addr_candidates.get(int(va, 16)) or []
            if not cands:
                return 'unregistered native target'
            names = []
            for c in cands[:4]:
                try:
                    if c[0] == 'method':
                        m = self.meta.methods[c[1]]
                        td = self.meta.typedefs[m.declaring]
                        names.append('%s.%s' % (td.name, m.name))
                    elif c[0] == 'generic':
                        names.append(str(self.il.generic_method_name(c[1]))[:70])
                    else:
                        names.append(str(c[0]))
                except Exception:
                    names.append('?')
            more = '' if len(cands) <= 4 else ' +%d more' % (len(cands) - 4)
            return '%d owners: %s%s' % (len(cands), ', '.join(names), more)
        except Exception:
            return 'unresolved target'

    _STUB_ASM_MAX_INSN = 16
    _STUB_ASM_MAX_BYTES = 64

    def _stub_asm_lines(self, va):
        """First native instructions at one stub VA as `//` comment lines.

        Honest SOME-code for unresolved shared/unregistered targets: the
        bytes are real, no managed owner is selected, and every failure
        declines to no lines (the throwing stub below stays the body)."""
        try:
            addr = int(va, 16)
        except Exception:
            return []
        try:
            if not HAVE_ICED:
                return []
            if is_arm64_binary(self.il.bin):
                return []
            b = self.il.bin
            if not b.is_exec_va(addr):
                return []
            code = b.read(addr, self._STUB_ASM_MAX_BYTES)
            if not code:
                return []
            dec = Decoder(64, code, DecoderOptions.NONE)
            dec.ip = addr
            fmt = Formatter(FormatterSyntax.NASM)
            fmt.digit_separator = ''
            out = []
            for ins in dec:
                out.append('    // 0x%x: %s' % (ins.ip, fmt.format(ins)))
                if ins.mnemonic in (Mnemonic.RET, Mnemonic.INT3, Mnemonic.UD2):
                    break
                if len(out) >= self._STUB_ASM_MAX_INSN:
                    break
            return out
        except Exception:
            return []

    def _stub_file_text(self, vas):
        """One global stub class for an assembly's referenced VAs."""
        head = [
            '// <auto-generated>',
            '// Unresolved shared/unregistered native call targets referenced',
            '// by the recovered bodies of this assembly. Each `sub_VA` names',
            '// one native address: either compiled bodies shared by the',
            '// listed metadata owners, or an unregistered native helper.',
            '// Signatures are unknown, so every stub takes any arguments',
            '// and returns object, throwing on invocation; call sites carry',
            '// caller-proven `(T)` casts where the need is proven.',
            '// Where the address decodes, its first native instructions are',
            '// listed as comments; the managed owner stays unresolved.',
            '// Generated by il2csharp; never hand-edit.',
            'internal static class __SharedBodyStubs',
            '{',
        ]
        tail = ['}']
        body = []
        for va in sorted(vas):
            body.append('    // 0x%s: %s' % (va, self._stub_owners(va)))
            asm = self._stub_asm_lines(va)
            if asm:
                body.append('    // native code at this address (no managed owner selected):')
                body.extend(asm)
            body.append('    internal static object sub_%s(params object[] args)' % va)
            body.append('    {')
            body.append('        throw new System.NotImplementedException('
                        '"unresolved shared native body 0x%s");' % va)
            body.append('    }')
        return '\n'.join(head + body + tail) + '\n'

    def _matches_type_filter(self, td):
        """A nested match retains its entire top-level owner file."""
        if not self.type_filter:
            return True
        pending = [(td.index, td.namespace)]
        visited = set()
        while pending:
            ti, prefix = pending.pop()
            if ti in visited or not 0 <= ti < len(self.meta.typedefs):
                continue
            visited.add(ti)
            child = self.meta.typedefs[ti]
            full = (prefix + '.' if prefix else '') + child.name
            if self.type_filter in full.casefold():
                return True
            for k in range(child.nested_start, child.nested_start + child.nested_count):
                if 0 <= k < len(self.meta.nested_types):
                    pending.append((self.meta.nested_types[k], full))
        return False

    def _asm_paths(self, img: ImageDef):
        """(assembly name, its output directory) for one image."""
        asm_name = self.seg(img.name[:-4] if img.name.lower().endswith('.dll') else img.name)
        return asm_name, os.path.join(self.out_dir, asm_name)

    def _plan_top_files(self, img: ImageDef):
        """`[(typedef, final_base_name)]` for every top-level file of an image.

        Metadata order, `<Module>` and type-filter misses skipped, colliding
        base names de-duplicated (`Name`, `Name_2`, ...) -- decided once and
        up front, so no two workers can ever pick the same file name. Pure
        function of the metadata: every process computes the same plan.
        """
        _asm_name, asm_dir = self._asm_paths(img)
        plan = []
        used = {}
        for ti in range(img.type_start, min(img.type_start + img.type_count, len(self.meta.typedefs))):
            td = self.meta.typedefs[ti]
            if td.declaring >= 0:
                continue
            if td.name == '<Module>' or not self._matches_type_filter(td):
                continue
            ns = td.namespace
            rel = [self.seg(x) for x in ns.split('.')] if ns else []
            dirp = os.path.join(asm_dir, *rel)
            base = self.file_name_for(td)
            key = (dirp, base.lower())
            used[key] = used.get(key, 0) + 1
            if used[key] > 1:
                base += '_%d' % used[key]
            plan.append((td, base))
        return plan

    def _top_weight(self, td: TypeDef) -> int:
        """Cost proxy of one top-level file: its native method bodies plus
        those of every nested type it carries (nested types share the file),
        plus one for the file itself."""
        total = 1
        stack = [td]
        seen = set()
        while stack:
            cur = stack.pop()
            if cur.index in seen:
                continue
            seen.add(cur.index)
            for mi in self.meta.type_methods(cur):
                if self.meta.methods[mi].addr:
                    total += 1
            for k in range(cur.nested_start, cur.nested_start + cur.nested_count):
                if 0 <= k < len(self.meta.nested_types):
                    ni = self.meta.nested_types[k]
                    if 0 <= ni < len(self.meta.typedefs):
                        stack.append(self.meta.typedefs[ni])
        return total

    def _emit_one_top(self, td: TypeDef, img: ImageDef, base: str):
        """Emit and write one top-level file; returns `(stub VAs, raw_used)`.

        Everything a file needs lives here and nothing crosses types: the
        `sub_<va>` stub union, the `--raw-addr` helper flag and the project
        file are per-image products that `write_assembly_tail` builds from
        what each call returns.
        """
        _asm_name, asm_dir = self._asm_paths(img)
        ns = td.namespace
        rel = [self.seg(x) for x in ns.split('.')] if ns else []
        dirp = os.path.join(asm_dir, *rel)
        buf = []
        try:
            indent = '    ' if ns else ''
            self.emit_type(td, buf, indent)
        except Exception as ex:
            self.emit_failed += 1
            if self.verbose:
                print('warning: type emission failed %s: %s' % (td.name, ex), file=sys.stderr)
            buf = ['// emit failed for %s: %s' % (td.name, ex)]
        subs = self._stub_collect('\n'.join(buf))
        tr = UsingTracker(self.il)
        for l in buf:
            tr.add_text(l)
        uses_set = set(tr.used)   # own ns too: in scope inside its block
        if uses_set:
            dup = collision_heads("\n".join(buf), ns, uses_set, self._short_ns_index())
            buf = strip_namespaces(buf, uses_set, ns, dup)
        members = self._nameof_members(uses_set)
        if members:
            # the enum must be referenced elsewhere in the file too:
            # nameof's argument does not survive compilation, so a file
            # that never names the enum almost surely had a plain string
            toks = set(re.findall(r'[A-Za-z_]\w*', '\n'.join(buf)))
            members = {mn: en for mn, en in members.items() if en in toks}
            if members:
                buf = nameof_sugar(buf, members)
        # Fix 128, opt-in `--raw-addr`: `(byte*)E` -> `(byte*)__addr(E)`
        raw = False
        if getattr(self, 'raw_addr', False):
            buf, raw = rawaddr.rewrite_lines(buf)
        hdr = ['// Decompiled by il2csharp | %s | TypeDefIndex: %d' % (img.name, td.index)]
        _gate = self._gate_header()
        if _gate:
            hdr.insert(0, _gate)
        uses = tr.render(skip=[ns] if ns else [])
        if uses:
            hdr.append('')
            hdr.extend(uses)
        if self._stub_collect('\n'.join(buf)):
            hdr.append('')
            hdr.append('using static __SharedBodyStubs;')
        if raw:
            hdr.append('')
            hdr.append('using static %s;' % rawaddr.CLASS)
        if ns:
            hdr.append('')
            hdr.append('namespace %s' % ns)
            hdr.append('{')
            content = '\n'.join(hdr) + '\n' + '\n'.join(buf) + '\n}\n'
        else:
            content = '\n'.join(hdr) + '\n' + '\n'.join(buf) + '\n'
        # lay every line at its real brace depth (see `reindent`): the
        # threaded-`indent` emitters drift a level and bodies read as
        # sitting outside their own braces. No-op on correct files.
        if os.environ.get('IL2CSHARP_NO_REINDENT') != '1':
            content = reindent(content)
        # a label in front of `}`/EOF needs a statement after it
        # (C# rule; tree-sitter MISSING). The structured path
        # fixes this in `_final_text`; the legacy flat lift never
        # runs it, so do it at the file boundary.
        _fl = content.split('\n')
        for _li in range(len(_fl)):
            if not re.match(r'^\s*L_[0-9a-fA-F]+:$', _fl[_li]):
                continue
            _lj = _li + 1
            while _lj < len(_fl) and not _fl[_lj].strip():
                _lj += 1
            if _lj >= len(_fl) or _fl[_lj].lstrip().startswith('}'):
                _fl[_li] = _fl[_li] + ' ;'
        content = '\n'.join(_fl)
        # generated identifiers carry IL-only characters (`<>c`,
        # `<Foo>d__13`, `<>9__0_0`) that no C# grammar accepts; mangle
        # them deterministically at the file boundary so declarations
        # and every reference move together
        content = MANGLED_IDENT_RX.sub(
            lambda m: m.group(0).replace('<', '_').replace('>', '_')
            .replace('.', '_').replace('|', '_'), content)
        os.makedirs(dirp, exist_ok=True)
        with open(os.path.join(dirp, base + '.cs'), 'w', encoding='utf-8') as fh:
            fh.write(content)
        return subs, raw

    def write_assembly_tail(self, img: ImageDef, all_sub, any_raw) -> int:
        """The per-image files no single type owns: the `sub_<va>` stub class,
        the `--raw-addr` helper and the .csproj. Returns files written
        (the project file is not counted, as before)."""
        asm_name, asm_dir = self._asm_paths(img)
        os.makedirs(asm_dir, exist_ok=True)
        written = 0
        all_sub = set(v for v in all_sub if v not in self._real_sub_names(self.meta))
        if all_sub:
            with open(os.path.join(asm_dir, '__SharedBodyStubs.cs'), 'w', encoding='utf-8') as fh:
                fh.write(self._stub_file_text(all_sub))
            written += 1
        if any_raw:
            with open(os.path.join(asm_dir, rawaddr.CLASS + '.cs'), 'w', encoding='utf-8') as fh:
                fh.write(rawaddr.helper_file_text())
            written += 1
        with open(os.path.join(asm_dir, asm_name + '.csproj'), 'w', encoding='utf-8') as fh:
            fh.write('<Project Sdk="Microsoft.NET.Sdk">\n'
                     '  <PropertyGroup>\n'
                     '    <TargetFramework>netstandard2.1</TargetFramework>\n'
                     '    <AssemblyName>%s</AssemblyName>\n'
                     '    <EnableDefaultCompileItems>true</EnableDefaultCompileItems>\n'
                     '    <AllowUnsafeBlocks>true</AllowUnsafeBlocks>\n'
                     '    <LangVersion>latest</LangVersion>\n'
                     '    <NoWarn>CS0169;CS0649;CS0108;CS0114;CS8019</NoWarn>\n'
                     '  </PropertyGroup>\n'
                     '</Project>\n' % asm_name)
        return written

    def write_assembly_split(self, img: ImageDef) -> int:
        """One image, serially: plan, emit every file, write the tail. The
        process pool runs the same two calls over chunks of the same plan."""
        written = 0
        all_sub = set()
        any_raw = False
        for td, base in self._plan_top_files(img):
            subs, raw = self._emit_one_top(td, img, base)
            all_sub |= subs
            any_raw = any_raw or raw
            written += 1
        return written + self.write_assembly_tail(img, all_sub, any_raw)

    def _short_ns_index(self):
        """short typedef name (sans arity) -> namespaces. Built once per
        emitter; metadata does not change during a build."""
        idx = getattr(self, "_short_ns_idx", None)
        if idx is None:
            idx = {}
            for td in self.meta.typedefs:
                try:
                    nm = (td.name or "").split("`")[0]
                except Exception:
                    continue
                if nm:
                    idx.setdefault(nm, set()).add(getattr(td, "namespace", ""))
            self._short_ns_idx = idx
        return idx

    def _nameof_members(self, ns_set) -> dict:
        """member name -> enum short name for top-level enums in the given
        namespaces. A short name shared by two enums in scope is dropped
        (the qualified member would not resolve)."""
        if getattr(self, '_enum_ns_idx', None) is None:
            idx = {}
            for td in self.meta.typedefs:
                if td.is_enum and td.declaring < 0:
                    idx.setdefault(td.namespace, []).append(td)
            self._enum_ns_idx = idx
        short_count = {}
        for ns in ns_set:
            for td in self._enum_ns_idx.get(ns, ()):
                short_count[td.name] = short_count.get(td.name, 0) + 1
        members = {}
        for ns in ns_set:
            for td in self._enum_ns_idx.get(ns, ()):
                if short_count[td.name] > 1:
                    continue
                for fi in self.meta.type_fields(td)[1:]:
                    name = sanitize(self.meta.fields[fi].name)
                    if name not in members:
                        members[name] = td.name
        return members

    def write_script_json(self, path):
        import json
        methods = []
        for m in self.meta.methods:
            if not m.addr or m.image < 0:
                continue
            td = self.meta.typedefs[m.declaring] if 0 <= m.declaring < len(self.meta.typedefs) else None
            if td is None:
                continue
            ns = (td.namespace + '.') if td.namespace else ''
            params = ', '.join(
                self.il.type_name(self.il.types[p.type]) if 0 <= p.type < len(self.il.types) else 'object'
                for p in self.meta.method_params(m))
            methods.append({'Name': '%s%s.%s(%s)' % (ns, td.name, m.name, params),
                            'Address': m.addr})
        strings = [{'Address': sva, 'Value': lit} for sva, lit in self.il.string_slots()]
        with open(path, 'w', encoding='utf-8') as fh:
            json.dump({'ScriptMethod': methods, 'ScriptString': strings}, fh, indent=1)

    def write_string_literals(self, path):
        import json
        lits = [{'index': i, 'value': self.meta.string_literal(i)}
                for i in range(len(self.meta.string_literals))]
        with open(path, 'w', encoding='utf-8') as fh:
            json.dump(lits, fh, indent=1, ensure_ascii=False)

    def _record_body(self, m, body):
        if not getattr(m, 'addr', 0) or not body:
            return
        self.bodies[m.addr] = '\n'.join(l.rstrip() for l in body)

    def write_bodies(self, path):
        import json
        payload = {'0x%x' % addr: text for addr, text in sorted(self.bodies.items())}
        with open(path, 'w', encoding='utf-8') as fh:
            json.dump(payload, fh, indent=1, ensure_ascii=False)

