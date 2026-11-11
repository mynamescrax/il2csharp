from il2cpp.prelude import *  # noqa: F401,F403
from il2cpp.common import u16, u32, u64

class Section:
    def __init__(self, name, addr, size, offset, rawsize, chars):
        self.name, self.addr, self.size = name, addr, size
        self.offset, self.rawsize, self.chars = offset, rawsize, chars

    @property
    def is_exec(self): return bool(self.chars & 0x20000000)
    @property
    def is_data(self): return bool(self.chars & 0x40000000)
    @property
    def is_bss(self): return self.rawsize == 0 and self.size > 0


class Binary:
    """Base: byte access + VA mapping."""
    is64 = True

    def __init__(self, d: bytes):
        self.d = d
        self.sections: List[Section] = []
        self.exports: Dict[int, str] = {}
        self.image_base = 0

    def va2off(self, va) -> Optional[int]:
        for s in self.sections:
            if s.addr <= va < s.addr + max(s.size, s.rawsize):
                if va - s.addr < s.rawsize:
                    return s.offset + (va - s.addr)
                return None
        return None

    def valid_va(self, va) -> bool:
        for s in self.sections:
            if s.addr <= va < s.addr + max(s.size, s.rawsize):
                return True
        return False

    def sec_of(self, va) -> Optional[str]:
        for s in self.sections:
            if s.addr <= va < s.addr + max(s.size, s.rawsize):
                return s.name
        return None

    def is_exec_va(self, va) -> bool:
        return any(s.addr <= va < s.addr + s.size and s.is_exec for s in self.sections)

    def read(self, va, n) -> Optional[bytes]:
        o = self.va2off(va)
        return self.d[o:o + n] if o is not None else None

    def qword(self, va) -> Optional[int]:
        o = self.va2off(va)
        return u64(self.d, o) if o is not None else None

    def dword(self, va) -> Optional[int]:
        o = self.va2off(va)
        return u32(self.d, o) if o is not None else None

    def cstr(self, va, maxlen=256) -> Optional[str]:
        o = self.va2off(va)
        if o is None: return None
        e = self.d.find(b'\x00', o, o + maxlen)
        if e < 0: return None
        try:
            return self.d[o:e].decode('utf-8')
        except UnicodeDecodeError:
            return None

    def read_qword_array(self, va, count) -> List[int]:
        o = self.va2off(va)
        if o is None: return []
        return list(struct.unpack_from('<%dQ' % count, self.d, o))


class PE(Binary):
    def __init__(self, d: bytes):
        super().__init__(d)
        pe = u32(d, 0x3c)
        if d[pe:pe + 4] != b'PE\x00\x00':
            raise ValueError('not a PE file')
        self.nsec = u16(d, pe + 6)
        optsz = u16(d, pe + 20)
        magic = u16(d, pe + 24)
        self.is64 = magic == 0x20b
        fmt = '<Q' if self.is64 else '<I'
        self.image_base = struct.unpack_from(fmt, d, pe + 24 + 24)[0]
        sec_off = pe + 24 + optsz
        for i in range(self.nsec):
            b = sec_off + i * 40
            name = d[b:b + 8].rstrip(b'\x00').decode('ascii', 'replace')
            vsz, va, rsz, ro = struct.unpack_from('<IIII', d, b + 8)
            chars = u32(d, b + 36)
            self.sections.append(Section(name, self.image_base + va, vsz, ro, rsz, chars))
        self._parse_exports(pe + 24, optsz)

    def _parse_exports(self, opt_off, optsz):
        d = self.d
        try:
            if self.is64:
                exp_rva = u32(d, opt_off + 112)
            else:
                exp_rva = u32(d, opt_off + 96)
            if not exp_rva: return
            eo = self.va2off(self.image_base + exp_rva)
            if eo is None: return
            n_names = u32(d, eo + 24)
            addr_rva = u32(d, eo + 28)
            names_rva = u32(d, eo + 32)
            ords_rva = u32(d, eo + 36)
            ao = self.va2off(self.image_base + addr_rva)
            no = self.va2off(self.image_base + names_rva)
            oo = self.va2off(self.image_base + ords_rva)
            if ao is None or no is None or oo is None: return
            for i in range(n_names):
                nrva = u32(d, no + i * 4)
                s = self.cstr(self.image_base + nrva)
                if not s: continue
                ordinal = u16(d, oo + i * 2)
                fva = u32(d, ao + ordinal * 4)
                self.exports[self.image_base + fva] = s
        except Exception:
            pass


class ELF(Binary):
    def __init__(self, d: bytes):
        super().__init__(d)
        if d[:4] != b'\x7fELF':
            raise ValueError('not an ELF file')
        self.is64 = d[4] == 2
        self.e_machine = struct.unpack_from('<H', d, 0x12)[0]
        if self.is64:
            e_phoff = u64(d, 0x20)
            phentsize = u16(d, 0x36)
            phnum = u16(d, 0x38)
            for i in range(phnum):
                b = e_phoff + i * phentsize
                p_type, p_flags = struct.unpack_from('<II', d, b)
                p_offset, p_vaddr, _, p_filesz, p_memsz = struct.unpack_from('<QQQQQ', d, b + 8)
                if p_type != 1:  # PT_LOAD
                    continue
                chars = 0
                if p_flags & 1: chars |= 0x20000000
                if p_flags & 2: chars |= 0x40000000
                self.sections.append(Section('seg%d' % i, p_vaddr, p_memsz, p_offset, p_filesz, chars))
        else:
            raise ValueError('32-bit ELF not supported')

    # ELF symbols for exports
    def load_symbols(self):
        d = self.d
        try:
            e_shoff = u64(d, 0x28)
            e_shentsize = u16(d, 0x3a)
            e_shnum = u16(d, 0x3c)
            for i in range(e_shnum):
                b = e_shoff + i * e_shentsize
                sh_type = u32(d, b + 4)
                if sh_type != 11 and sh_type != 2:  # SHT_DYNSYM / SHT_SYMTAB
                    continue
                sh_offset = u64(d, b + 24)
                sh_size = u64(d, b + 32)
                sh_link = u32(d, b + 40)
                str_off = u64(d, e_shoff + sh_link * e_shentsize + 24)
                for j in range(sh_size // 24):
                    sb = sh_offset + j * 24
                    st_name = u32(d, sb)
                    st_info = u8(d, sb + 4)
                    st_shndx = u16(d, sb + 6)
                    st_value = u64(d, sb + 8)
                    if st_value == 0 or st_shndx == 0 or not (st_info & 0x12):
                        continue
                    e = d.find(b'\x00', str_off + st_name)
                    nm = d[str_off + st_name:e].decode('utf-8', 'replace')
                    if nm:
                        self.exports.setdefault(st_value, nm)
        except Exception:
            pass

    def apply_relocations(self):
        """Apply .rela.dyn R_AARCH64_RELATIVE relocs (Android ARM64).

        Unity Android .so files ship with zeroed addends in
        .data.rel.ro: every absolute data pointer reads as 0 until
        the RELA entries are applied (true value = r_addend, load
        bias 0 in our VA space). Cpp2IL does the same before its
        registration search. Returns slots patched. No-op for PEs,
        relocation-free ELFs and missing section tables, and never
        touches executable sections.
        """
        d = self.d
        self.reloc_applied = 0
        try:
            e_shoff = u64(d, 0x28)
            e_shentsize = u16(d, 0x3a)
            e_shnum = u16(d, 0x3c)
            e_shstrndx = u16(d, 0x3e)
            if not e_shoff or not e_shnum or e_shstrndx >= e_shnum:
                return 0
            sb = e_shoff + e_shstrndx * e_shentsize
            str_off = u64(d, sb + 24)
            rela = None
            for i in range(e_shnum):
                bb = e_shoff + i * e_shentsize
                if u32(d, bb + 4) != 4:  # SHT_RELA
                    continue
                e2 = d.find(b'\x00', str_off + u32(d, bb))
                if d[str_off + u32(d, bb):e2].decode('ascii', 'replace') != '.rela.dyn':
                    continue
                rela = (u64(d, bb + 24), u64(d, bb + 32))
                break
            if not rela:
                return 0
            roff, rsz = rela
            m = bytearray(d)
            n = 0
            for (r_offset, r_info, r_addend) in struct.iter_unpack('<QQq', bytes(d[roff:roff + rsz])):
                if (r_info & 0xFFFFFFFF) != 1027:  # R_AARCH64_RELATIVE
                    continue
                if self.is_exec_va(r_offset):
                    continue
                o = self.va2off(r_offset)
                if o is None:
                    continue
                struct.pack_into('<Q', m, o, r_addend & 0xFFFFFFFFFFFFFFFF)
                n += 1
            if n:
                self.d = bytes(m)
            self.reloc_applied = n
            return n
        except Exception:
            return 0


def u8(d, o): return d[o]


def load_binary(path: str) -> Optional[Binary]:
    d = open(path, 'rb').read()
    if d[:2] == b'MZ':
        return PE(d)
    if d[:4] == b'\x7fELF':
        e = ELF(d)
        e.load_symbols()
        e.apply_relocations()
        return e
    return None


# ----------------------------------------------------------------------------
# IL2CPP context: registrations, codegen modules, types, field offsets
# ----------------------------------------------------------------------------
