from il2cpp.prelude import *  # noqa: F401,F403
from il2cpp.binary import Binary, ELF
from il2cpp.common import i64, u32, u64
from il2cpp.metadata import Metadata, MethodDef
from il2cpp.runtime.meta import CodeGenModule

class _RegistrationMixin:
    def __init__(self, meta: Metadata, bin_: Binary):
        self.meta = meta
        self.bin = bin_
        self.code_reg_va = 0
        self.meta_reg_va = 0
        self.verbose = False
        # fix 72: per-typedef cache for static_off_names (it rebuilt
        # the dict on every sfblob read; the inner walk reads it again)
        self._static_names_cache = {}
        # These were historically class attributes.  TypeDef indices are
        # workspace-local, so sharing their results across Il2Cpp instances
        # can return another binary's inheritance/field chain.
        self._chain_cache = {}
        self._bases_cache = {}

    def log(self, *a):
        if self.verbose:
            print(*a, file=sys.stderr)

    @property
    def all_namespaces(self) -> set:
        """Every namespace referenced by a typedef, plus parent namespaces
        of dotted ones ('A.B' also yields 'A')."""
        if not hasattr(self, '_ns_set'):
            ns = set()
            for td in self.meta.typedefs:
                if td.namespace:
                    ns.add(td.namespace)
                    parts = td.namespace.split('.')
                    for k in range(1, len(parts)):
                        ns.add('.'.join(parts[:k]))
            self._ns_set = ns
        return self._ns_set

    # ------------------------------------------------------------------
    def find_registrations(self):
        b = self.bin
        _uv = self._unity_version()
        if isinstance(b, ELF) and _uv and not _uv.startswith('6000.'):
            self.find_registrations_android()
            return
        # 1. locate image-name strings in the binary -> candidate name VAs
        name_vas = set()
        for img in self.meta.images:
            nm = (img.name + '\x00').encode()
            pos = 0
            while True:
                i = b.d.find(nm, pos)
                if i < 0: break
                pos = i + 1
                va = self._off2va(i)
                if va is not None:
                    name_vas.add(va)
        if not name_vas:
            raise RuntimeError('no image name strings found in binary')
        # single pass over data qwords: find pointers to those strings that
        # look like Il2CppCodeGenModule { name, count, ptr... }
        module_vas = set()
        for s in b.sections:
            if not s.is_data or not s.rawsize: continue
            qs = b.read_qword_array(s.addr, s.rawsize // 8)
            for j, q in enumerate(qs):
                if q not in name_vas: continue
                mva = s.addr + j * 8
                mp_count = b.qword(mva + 8)
                mp = b.qword(mva + 16)
                if 0 <= mp_count < 5_000_000 and (mp == 0 or b.valid_va(mp)):
                    module_vas.add(mva)
        if not module_vas:
            raise RuntimeError('could not find any Il2CppCodeGenModule')
        self.log('module structs found:', len(module_vas))

        # 2. find the pointer array: contiguous run of module pointers
        slots = {}
        for s in b.sections:
            if not s.is_data or not s.rawsize: continue
            qs = b.read_qword_array(s.addr, s.rawsize // 8)
            for j, q in enumerate(qs):
                if q in module_vas:
                    slots[s.addr + j * 8] = q
        vas = sorted(slots)
        # longest contiguous run with step 8
        runs = []
        start = prev = vas[0]
        for v in vas[1:]:
            if v - prev == 8:
                prev = v
            else:
                runs.append((start, prev)); start = prev = v
        runs.append((start, prev))
        runs.sort(key=lambda r: r[1] - r[0])
        lo, hi = runs[-1]
        count = (hi - lo) // 8 + 1
        self.log('module array: %#x..%#x (%d entries)' % (lo, hi, count))
        module_list = [slots[lo + k * 8] for k in range(count)]

        # 3. find pointer to array + count before it
        self.code_gen_modules_field = 0
        img_count = len(self.meta.images)
        for s in b.sections:
            if not s.is_data or not s.rawsize: continue
            qs = b.read_qword_array(s.addr, s.rawsize // 8)
            for j in range(len(qs) - 1):
                if qs[j + 1] == lo and qs[j] == count:
                    self.code_gen_modules_field = s.addr + (j + 1) * 8
                    break
            if self.code_gen_modules_field:
                break
        if not self.code_gen_modules_field:
            raise RuntimeError('codeGenModules pointer not found')
        self.log('codeGenModules field @ %#x count=%d' % (self.code_gen_modules_field, count))

        # 4. CodeRegistration: walk back pairs. Determine v31 (2 extra leading
        #    fields: methodPointersCount+methodPointers = 0) vs v29 layout.
        self.modules: Dict[str, CodeGenModule] = {}
        for mv in module_list:
            name = b.cstr(b.qword(mv) or 0)
            if not name: continue
            self.modules[name] = CodeGenModule(
                name, b.qword(mv + 8) or 0, b.qword(mv + 16) or 0,
                b.qword(mv + 24) or 0, b.qword(mv + 32) or 0,
                b.qword(mv + 40) or 0, b.qword(mv + 56) or 0, b.qword(mv + 72) or 0)

        X = self.code_gen_modules_field
        def q(at): return b.qword(X + at * 8)
        # shared tail: [-3/-2]=wrFactory, [-1/+0]=codeGenModules
        self.unresolved_static_call_ptrs = q(-6)
        self.unresolved_instance_call_ptrs = q(-7)
        self.unresolved_virtual_call_count = q(-9)
        self.unresolved_virtual_call_ptrs = q(-8)
        self.invoker_pointers_count = q(-11)
        self.invoker_pointers = q(-10)
        self.generic_adjustor_thunks = q(-12)
        self.generic_method_pointers_count = q(-14)
        self.generic_method_pointers = q(-13)
        # count precedes its wrapper array in the struct (the order the
        # Android loader reads): -16 is the count, -15 the wrappers.
        self.reverse_p_invoke_count = q(-16)
        self.reverse_p_invoke_wrappers = q(-15)
        self.code_reg_va = X - 18 * 8
        self.log('CodeRegistration @ %#x' % self.code_reg_va)

        # 5. MetadataRegistration: [TD, ptr, TD, ptr] anchor
        self._find_metadata_registration()
        self._load_metadata_registration()
        self._build_method_address_map()
        try:
            self.scan_runtime_class_cache()
        except Exception:
            self.bss_usage_map = {}
        try:
            self.scan_icall_cache()
        except Exception:
            self.icall_cells = {}

    # ---------------------------------------------------------------
    # Android / pre-Unity-6 ARM64 registration support (Chiki's Chase
    # batch: libil2cpp.so + metadata v31 built by Unity 2022.3.41f1).
    # Deltas vs the classic (Unity 6 / x64 PE) path: (1) absolute data
    # pointers are valid only after .rela.dyn application
    # (ELF.apply_relocations, same as Cpp2IL); (2) every non-executable
    # section is scanned, not just writable data; (3) the search is
    # mscorlib-anchored with a module-list backtrack (Cpp2IL
    # FindCodeRegistrationPost2019, v27+ variant); (4)
    # Il2CppCodeRegistration is 17 qwords (X-128); (5) the metareg
    # keeps the classic pair order (only q2/q3 goes unconsumed -- open
    # shape). Registration addresses verified pair-by-pair against
    # Cpp2IL's own successful run on this exact dump (codereg
    # 0x2A98DE0, metareg 0x2B79C08, 73/73 modules).
    # ---------------------------------------------------------------
    def _unity_version(self):
        """Unity release embedded in the binary ('2022.3.41f1'), else ''."""
        import re as _re
        try:
            m = _re.search(
                rb'\b(?:20\d\d\.\d+\.[a-z0-9]+|6000\.\d+\.[a-z0-9]+)',
                self.bin.d)
            if m:
                return m.group(0).decode('ascii', 'replace')
        except Exception:
            pass
        return ''

    def _ptrs_to(self, va):
        """All VAs (in non-executable sections) whose qword equals va."""
        b = self.bin
        needle = struct.pack('<Q', va & 0xFFFFFFFFFFFFFFFF)
        out = []
        for s in b.sections:
            if s.is_exec or not s.rawsize:
                continue
            seg = b.d[s.offset:s.offset + s.rawsize]
            pos = 0
            while True:
                j = seg.find(needle, pos)
                if j < 0:
                    break
                pos = j + 1
                out.append(s.addr + j)
        return out

    @staticmethod
    def _sane_count(v, limit=0x70000):
        return v is not None and 0 <= v <= limit

    def _valid_module_at(self, mv):
        """(name, count, table) if mv looks like an Il2CppCodeGenModule."""
        b = self.bin
        p = b.qword(mv)
        nm = b.cstr(p) if p else None
        if not nm or len(nm) > 80:
            return None
        cnt = b.qword(mv + 8)
        mp = b.qword(mv + 16)
        if not self._sane_count(cnt):
            return None
        if mp and not b.valid_va(mp):
            return None
        return (nm, cnt, mp or 0)

    def _strict_codereg(self, cb, cnt, base):
        """True if cb looks like a 17-qword Il2CppCodeRegistration
        whose trailing [count, array] pair is (cnt, base)."""
        b = self.bin
        w = [b.qword(cb + i * 8) for i in range(17)]
        if any(v is None for v in w):
            return False
        for ci in (0, 2, 5, 7, 11, 13):
            if not self._sane_count(w[ci]):
                return False
        for pi in (1, 3, 4, 6, 8, 9, 10, 12, 14):
            if w[pi] and not b.valid_va(w[pi]):
                return False
        return w[15] == cnt and w[16] == base

    def find_registrations_android(self):
        b, meta = self.bin, self.meta
        nimg = len(meta.images)
        # -- 1. mscorlib-anchored module discovery --
        name_vas = set()
        pos = 0
        while True:
            i = b.d.find(b'mscorlib.dll\x00', pos)
            if i < 0:
                break
            pos = i + 1
            va = self._off2va(i)
            if va is not None:
                name_vas.add(va)
        if not name_vas:
            raise RuntimeError('android: mscorlib name string not found')
        mods = {}
        for nv in sorted(name_vas):
            for mv in self._ptrs_to(nv):
                vm = self._valid_module_at(mv)
                if vm and vm[0] == 'mscorlib.dll':
                    mods[mv] = vm
        if not mods:
            raise RuntimeError('android: no mscorlib codegen module')
        self.log('android module structs found:', len(mods))
        # -- 2. module-list backtrack -> X (codeGenModules field) --
        entries = []
        for mv in sorted(mods):
            entries.extend(self._ptrs_to(mv))
        entries = sorted(set(entries))
        if not entries:
            raise RuntimeError('android: module not referenced by any list')
        best = None
        for back in range(max(0, nimg - 10), 400):
            for e in sorted(entries):
                base = e - back * 8
                for xref in sorted(self._ptrs_to(base)):
                    cnt = b.dword(xref - 8)
                    if cnt is None or not (0 < cnt <= 400):
                        continue
                    if b.qword(xref) != base:
                        continue
                    if not self._strict_codereg(xref - 16 * 8, cnt, base):
                        continue
                    # implied-index check: the array must parse to valid
                    # modules with mscorlib.dll exactly at this entry's slot
                    try:
                        slot = (e - base) // 8
                        names = []
                        for k in range(cnt):
                            mv = b.qword(base + k * 8)
                            p = b.qword(mv) if mv else 0
                            nm = b.cstr(p) if p else None
                            names.append(nm or '')
                        if not (0 <= slot < cnt):
                            continue
                        if names[slot] != 'mscorlib.dll':
                            continue
                        if sum(1 for n in names if n) * 2 < cnt:
                            continue
                    except Exception:
                        continue
                    best = (xref, base, cnt)
                    break
                if best:
                    break
            if best:
                break
        if not best:
            raise RuntimeError('android: codegen module list not found')
        X, array_base, cg_count = best
        self.code_gen_modules_field = X
        self.log('android codeGenModules field @ %#x count=%d' % (X, cg_count))
        # -- 3. CodeRegistration: 17 qwords, X-128 (v31.1 layout). The
        # relative offsets match the classic path exactly; only the base
        # differs (X-16*8, not X-18*8). --
        def q(at):
            return b.qword(X + at * 8)
        if q(-1) != cg_count or q(0) != array_base:
            raise RuntimeError('android: codereg tail incoherent')
        for ci in (-16, -14, -11, -9):
            if not self._sane_count(q(ci)):
                raise RuntimeError('android: bad codereg count field')
        for pi in (-15, -13, -12, -10, -8, -7, -6):
            pv = q(pi)
            if pv and not b.valid_va(pv):
                raise RuntimeError('android: bad codereg pointer field')
        self.unresolved_static_call_ptrs = q(-6)
        self.unresolved_instance_call_ptrs = q(-7)
        self.unresolved_virtual_call_count = q(-9)
        self.unresolved_virtual_call_ptrs = q(-8)
        self.invoker_pointers_count = q(-11)
        self.invoker_pointers = q(-10)
        self.generic_adjustor_thunks = q(-12)
        self.generic_method_pointers_count = q(-14)
        self.generic_method_pointers = q(-13)
        self.reverse_p_invoke_count = q(-16)
        self.reverse_p_invoke_wrappers = q(-15)
        self.code_reg_va = X - 16 * 8
        self.log('android CodeRegistration @ %#x' % self.code_reg_va)
        # -- 4. full module table (same struct as the classic path) --
        self.modules = {}
        for k in range(cg_count):
            mv = b.qword(array_base + k * 8)
            if not mv:
                continue
            name = b.cstr(b.qword(mv) or 0)
            if not name:
                continue
            self.modules[name] = CodeGenModule(
                name, b.qword(mv + 8) or 0, b.qword(mv + 16) or 0,
                b.qword(mv + 24) or 0, b.qword(mv + 32) or 0,
                b.qword(mv + 40) or 0, b.qword(mv + 56) or 0, b.qword(mv + 72) or 0)
        self.log('android modules parsed:', len(self.modules))
        # -- 5. MetadataRegistration (existing anchor + 2022 map) --
        self._find_metadata_registration()
        m = self.meta_reg_va
        td = len(meta.typedefs)
        # sizes anchor holds in both eras; the codereg strict-check
        # above is the real version gate.
        if (b.qword(m + 10 * 8) or 0) != td:
            raise RuntimeError('android: metareg sizes anchor missing')
        self._metareg2022 = True
        try:
            self._load_metadata_registration()
        finally:
            self._metareg2022 = False
        self._build_method_address_map()
        try:
            self.scan_runtime_class_cache()
        except Exception:
            self.bss_usage_map = {}
        try:
            self.scan_icall_cache()
        except Exception:
            self.icall_cells = {}

    def _apply_metareg2022_map(self, q):
        """Unity 2022.3 (v31.1) metareg map: same pair order as the
        classic map -- every pair shape-verified on metareg 0x2B79C08
        (gentable quads, type {data,bits}, spec triples, per-typedef
        offset ints, sizes) -- except q2/q3 is NOT consumed as
        generic-insts (4893 pointers into the shared pool, not
        {argc,argv} structs; open shape, punted to the bodies phase.
        generic_method_name() degrades gracefully without it)."""
        self.generic_classes_count = q(0)
        self.generic_classes = q(1)
        self.generic_insts_count = 0
        self.generic_insts = 0
        self.generic_method_table_count = q(4)
        self.generic_method_table = q(5)
        self.types_count = q(6)
        self.types_ptr = q(7)
        self.method_specs_count = q(8)
        self.method_specs_ptr = q(9)
        self.field_offsets_count = q(10)
        self.field_offsets_ptr = q(11)
        self.type_sizes_count = q(12)
        self.type_sizes_ptr = q(13)
        self.log('MetadataRegistration2022 @ %#x types=%d' % (self.meta_reg_va, self.types_count))

    def _off2va(self, off):
        for s in self.bin.sections:
            if s.offset <= off < s.offset + s.rawsize:
                return s.addr + (off - s.offset)
        return None

    def _find_metadata_registration(self):
        b = self.bin
        td = len(self.meta.typedefs)
        self.meta_reg_va = 0
        for s in b.sections:
            if not s.is_data or not s.rawsize: continue
            qs = b.read_qword_array(s.addr, s.rawsize // 8)
            for j in range(len(qs) - 3):
                if qs[j] == td and qs[j + 2] == td:
                    fo_ptr, sz_ptr = qs[j + 1], qs[j + 3]
                    # validate fieldOffsets[1..3] point to int arrays starting ~0x10
                    ok = 0
                    for k in (1, 2, 3):
                        e = b.qword(fo_ptr + k * 8) if fo_ptr else None
                        if e:
                            v = b.dword(e)
                            if v is not None and 0 <= v < 0x10000:
                                ok += 1
                    if ok >= 2:
                        self.meta_reg_anchor = s.addr + j * 8
                        self.meta_reg_va = self.meta_reg_anchor - 10 * 8
                        return
        if not self.meta_reg_va:
            raise RuntimeError('MetadataRegistration not found')

    def _load_metadata_registration(self):
        b, m = self.bin, self.meta_reg_va
        def q(i): return b.qword(m + i * 8)
        self.generic_classes_count = q(0)
        self.generic_classes = q(1)
        self.generic_insts_count = q(2)
        self.generic_insts = q(3)
        self.generic_method_table_count = q(4)
        self.generic_method_table = q(5)
        self.types_count = q(6)
        self.types_ptr = q(7)
        self.method_specs_count = q(8)
        self.method_specs_ptr = q(9)
        self.field_offsets_count = q(10)
        self.field_offsets_ptr = q(11)
        self.type_sizes_count = q(12)
        self.type_sizes_ptr = q(13)
        if getattr(self, '_metareg2022', False):
            self._apply_metareg2022_map(q)
        else:
            self.log('MetadataRegistration @ %#x types=%d' % (m, self.types_count))

        # types table: array of pointers to Il2CppType {u64 data; u32 bits}
        self.type_ptrs = b.read_qword_array(self.types_ptr, self.types_count)
        self.types = []
        for p in self.type_ptrs:
            o = b.va2off(p)
            if o is None:
                self.types.append(None); continue
            data = u64(b.d, o)
            bits = u32(b.d, o + 8)
            self.types.append((data, bits))
        self._type_by_ptr = {p: t for p, t in zip(self.type_ptrs, self.types)}

        # generic insts: {i64 type_argc; ptr type_argv}
        self.generic_insts_list = []
        for i in range(self.generic_insts_count):
            p = b.qword(self.generic_insts + i * 8)
            o = b.va2off(p)
            if o is None:
                self.generic_insts_list.append(None); continue
            argc = i64(b.d, o)
            argv = u64(b.d, o + 8)
            self.generic_insts_list.append((argc, argv))

        # generic method table: {int genericMethodIndex; int methodIndex; int invokerIndex; int adjustorThunk}
        self.generic_method_table_list = []
        o = b.va2off(self.generic_method_table)
        if o is not None:
            n = self.generic_method_table_count
            raw = struct.unpack_from('<%di' % (n * 4), b.d, o)
            for i in range(n):
                self.generic_method_table_list.append(
                    (raw[i * 4], raw[i * 4 + 1], raw[i * 4 + 2], raw[i * 4 + 3]))

        # method specs: {int methodDefinitionIndex; int classIndexIndex; int methodIndexIndex}
        self.method_specs = []
        o = b.va2off(self.method_specs_ptr)
        if o is not None:
            raw = struct.unpack_from('<%di' % (self.method_specs_count * 3), b.d, o)
            for i in range(self.method_specs_count):
                self.method_specs.append((raw[i * 3], raw[i * 3 + 1], raw[i * 3 + 2]))

        # field offsets per typedef
        self.field_offsets: List[Optional[List[int]]] = []
        for i in range(self.field_offsets_count):
            p = b.qword(self.field_offsets_ptr + i * 8)
            if not p:
                self.field_offsets.append(None); continue
            o = b.va2off(p)
            nfields = self.meta.typedefs[i].field_count if i < len(self.meta.typedefs) else 0
            self.field_offsets.append(
                list(struct.unpack_from('<%di' % nfields, b.d, o)) if o is not None and nfields else None)

        # fix 59: type definition sizes -- an array of pointers to
        # Il2CppTypeDefinitionSizes {u32 instance_size; i32 native_size;
        # u32 static_fields_size; u32 thread_static_fields_size}. Read
        # into type_sizes_count/type_sizes_ptr since this loader was
        # written and never consumed; it is the binary's only EXACT
        # struct size, which the Win64 return-buffer rule needs.
        # instance_size counts the 0x10 object header, so a valuetype's
        # sizeof is instance_size - 0x10; an open generic DEFINITION
        # carries 0 (its size lives in the instantiation) and is kept
        # as None rather than a negative number.
        self.type_sizes: List[Optional[int]] = []
        for i in range(self.type_sizes_count):
            p = b.qword(self.type_sizes_ptr + i * 8)
            o = b.va2off(p) if p else None
            v = u32(b.d, o) if o is not None else 0
            self.type_sizes.append(v - 0x10 if v >= 0x10 else None)

    # ------------------------------------------------------------------
    def _build_method_address_map(self):
        """addr -> (kind, payload): kind 'method' -> GLOBAL method index; 'generic' -> spec index.
        MSVC folds identical bodies and IL2CPP shares one body across generic
        instantiations, so many addresses carry more than one true owner --
        `addr_to_method` keeps the first (for call sites that don't care which
        one, e.g. icall-cell/thunk checks); `addr_candidates` keeps all of
        them, keyed the same way, for call-site disambiguation in `_call`."""
        from collections import defaultdict
        b = self.bin
        self.addr_to_method: Dict[int, Tuple[str, int]] = {}
        self.addr_candidates: Dict[int, List[Tuple[str, int]]] = defaultdict(list)
        for img_i, img in enumerate(self.meta.images):
            mod = self.modules.get(img.name)
            if not mod or not mod.method_pointers:
                continue
            rid_map = {}
            for ti in range(img.type_start, min(img.type_start + img.type_count, len(self.meta.typedefs))):
                t = self.meta.typedefs[ti]
                for mi in range(t.method_start, t.method_start + t.method_count):
                    if mi < len(self.meta.methods):
                        rid_map[self.meta.methods[mi].rid] = mi
            ptrs = b.read_qword_array(mod.method_pointers, mod.method_pointer_count)
            for i, p in enumerate(ptrs):
                if p and b.is_exec_va(p):
                    gmi = rid_map.get(i + 1)
                    if gmi is not None:
                        self.addr_to_method.setdefault(p, ('method', gmi))
                        self.addr_candidates[p].append(('method', gmi))
        # adjustor thunks: {u32 token; u32 pad; u64 thunk}
        for mod in self.modules.values():
            if not mod.adjustor_thunks or not mod.adjustor_thunk_count:
                continue
            o = b.va2off(mod.adjustor_thunks)
            if o is None: continue
            for i in range(mod.adjustor_thunk_count):
                to, tp = o + i * 16, o + i * 16
                token = u32(b.d, to)
                thunk = u64(b.d, to + 8)
                if thunk and b.is_exec_va(thunk):
                    self.addr_to_method.setdefault(thunk, ('thunk', (mod.name, token)))
        # generic method pointers
        gmp = b.read_qword_array(self.generic_method_pointers, self.generic_method_pointers_count)
        for i, p in enumerate(gmp):
            if p and b.is_exec_va(p) and i < len(self.generic_method_table_list):
                spec_idx = self.generic_method_table_list[i][0]
                self.addr_to_method.setdefault(p, ('generic', spec_idx))
                self.addr_candidates[p].append(('generic', spec_idx))

    def method_pointer(self, image_name: str, m: MethodDef) -> int:
        mod = self.modules.get(image_name)
        if not mod or not mod.method_pointers:
            return 0
        idx = m.rid - 1
        if 0 <= idx < mod.method_pointer_count:
            ptrs = self.read_module_ptrs(mod)
            if idx < len(ptrs):
                return ptrs[idx]
        return 0

    def read_module_ptrs(self, mod: CodeGenModule) -> List[int]:
        key = mod.method_pointers
        cache = self.__dict__.setdefault('_mod_ptr_cache', {})
        if key not in cache:
            cache[key] = self.bin.read_qword_array(
                mod.method_pointers, mod.method_pointer_count)
        return cache[key]

    def method_image(self, method_index: int) -> int:
        m = self.meta.methods[method_index]
        if m.image >= 0:
            return m.image
        return -1

    def assign_images(self):
        for img_i, img in enumerate(self.meta.images):
            for ti in range(img.type_start, img.type_start + img.type_count):
                if ti >= len(self.meta.typedefs): break
                td = self.meta.typedefs[ti]
                for mi in range(td.method_start, td.method_start + td.method_count):
                    if mi < len(self.meta.methods):
                        self.meta.methods[mi].image = img_i

    def resolve_method_addrs(self):
        for i, m in enumerate(self.meta.methods):
            if m.image < 0: continue
            img = self.meta.images[m.image]
            m.addr = self.method_pointer(img.name, m)
        starts = sorted({m.addr for m in self.meta.methods if m.addr})
        self.method_starts = starts
        import bisect as _b
        self._ms_bisect = _b

    def next_method_start(self, va):
        i = self._ms_bisect.bisect_right(self.method_starts, va)
        return self.method_starts[i] if i < len(self.method_starts) else None

    # ==================================================================
    # name resolution
    # ==================================================================

    PRIM = {
        0x01: 'void', 0x02: 'bool', 0x03: 'char', 0x04: 'sbyte', 0x05: 'byte',
        0x06: 'short', 0x07: 'ushort', 0x08: 'int', 0x09: 'uint', 0x0a: 'long',
        0x0b: 'ulong', 0x0c: 'float', 0x0d: 'double', 0x0e: 'string',
        0x12: 'object', 0x16: 'System.TypedReference', 0x18: 'System.IntPtr', 0x19: 'System.UIntPtr',
    }
