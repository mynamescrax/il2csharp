"""Edges for a densely indexed, guarded Win64 relative jump table.

Unlike the structurer's best-effort switch recovery, this evidence cannot
accept a prefix of a table or borrow a bound from a neighbouring branch.
"""
from struct import iter_unpack, unpack_from

from il2cpp.prelude import HAVE_ICED
from il2cpp.text import sdisp

if HAVE_ICED:
    from iced_x86 import Mnemonic as M, OpKind as K, Register as R, RegisterExt


def _file_span(binary, address, stop):
    overlapping = [s for s in binary.sections if s.addr < stop and address < s.addr + max(s.size,s.rawsize)]
    if len(overlapping) == 1:
        s = overlapping[0]
        if s.addr <= address < stop <= s.addr + min(s.rawsize,s.size):
            return s


def _unrelocated(binary, address, stop):
    """Loader fixups can modify a table even in a read-only section."""
    d = binary.d
    if len(d) < 64:
        return False
    pe, = unpack_from('<I', d, 0x3c)
    opt = pe + 24
    if opt > len(d) or d[pe:pe+6] != b'PE\0\0\x64\x86':
        return False
    size, = unpack_from('<H', d, pe+20)
    if size < 112 or opt+size > len(d) or d[opt:opt+2] != b'\x0b\x02':
        return False
    count, = unpack_from('<I', d, opt+108)
    if 112 + count*8 > size:
        return False
    if count <= 5:
        return True
    rva, length = unpack_from('<II', d, opt+112+5*8)
    if not rva and not length:
        return True
    start = binary.image_base + rva
    if not rva or not length or rva % 4 or _file_span(binary,start,start+length) is None:
        return False
    directory = binary.read(start,length)
    if directory is None or len(directory) != length:
        return False
    k = 0
    while k < length:
        if k%4 or length-k < 8:
            return False
        page, block = unpack_from('<II', directory, k)
        if page%4096 or not 8 <= block <= length-k or block%2:
            return False
        for word, in iter_unpack('<H',memoryview(directory)[k+8:k+block]):
            kind = word >> 12
            if kind == 0:continue
            p = binary.image_base + page + (word & 0xfff)
            if kind != 10 or (p < stop and address < p+8):return False
        k += block
    return True


def bounded_switch(binary, seq, j, ips):
    if not HAVE_ICED or j < 6:
        return None
    window = seq[j-6:j+1]
    source, cmp, guard, table_base, lookup, add, jump = window
    if (any(x.next_ip != y.ip for x,y in zip(window,window[1:])) or
            any(i.has_segment_prefix or i.has_lock_prefix for i in window)):
        return None
    idx = source.op0_register
    base = table_base.op0_register
    target = jump.op0_register
    if (source.mnemonic != M.MOVSXD or not RegisterExt.is_gpr64(idx) or source.op1_kind != K.MEMORY or
            cmp.mnemonic != M.CMP or not RegisterExt.is_gpr32(cmp.op0_register) or RegisterExt.full_register(cmp.op0_register) != idx or
            cmp.op1_kind not in (K.IMMEDIATE8TO32,K.IMMEDIATE32) or guard.mnemonic != M.JA or guard.op0_kind != K.NEAR_BRANCH64 or
            table_base.mnemonic != M.LEA or table_base.memory_base != R.RIP or not RegisterExt.is_gpr64(base) or
            lookup.mnemonic != M.MOV or not RegisterExt.is_gpr32(lookup.op0_register) or lookup.op1_kind != K.MEMORY or
            lookup.memory_base != base or lookup.memory_index != idx or lookup.memory_index_scale != 4 or
            jump.mnemonic != M.JMP or not RegisterExt.is_gpr64(target) or RegisterExt.full_register(lookup.op0_register) != target or
            add.mnemonic != M.ADD or add.op0_register != target or add.op1_register != base or
            len({base,idx,target}) != 3 or R.RSP in (base,idx,target)):
        return None
    count = cmp.immediate(1) + 1
    origin = table_base.ip_rel_memory_address
    address = origin + sdisp(lookup.memory_displacement)
    if not 3 <= count <= 512:
        return None
    stop = address + 4*count
    section = _file_span(binary,address,stop)
    if section is None or section.chars & 0x80000000 or not _unrelocated(binary,address,stop):
        return None
    data = binary.read(address,4*count)
    if not data or len(data) != 4*count:
        return None
    targets = tuple(origin + offset for offset, in iter_unpack('<I', data))
    if not set(targets) <= ips:
        return None
    return targets, (address,address+len(data)), window
