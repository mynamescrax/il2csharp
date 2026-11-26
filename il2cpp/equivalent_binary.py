"""Identify a local Win64 helper by a complete, relocated MethodDef body."""
from bisect import bisect_left
from struct import unpack

from il2cpp.binary import PE
from il2cpp.prelude import HAVE_ICED

if HAVE_ICED:
    from iced_x86 import Decoder, FlowControl as F, MemorySizeExt, Mnemonic as M, OpKind as K, Register as R


def _amd64(b):
    if not isinstance(b, PE) or not b.is64:
        return False
    pe = int.from_bytes(b.d[0x3c:0x40], 'little')
    return b.d[pe:pe+6] == b'PE\0\0\x64\x86'


def _extent(il, addr):
    # function_extent has a fallback even for non-functions. Require the
    # actual RUNTIME_FUNCTION row at this entry, without triggering EH4's
    # image-wide handler search. PE .pdata is sorted by start RVA.
    b = il.bin
    starts = getattr(il, '_starts', ())
    n = bisect_left(starts, addr)
    if n == len(starts) or starts[n] != addr:
        return None
    pd = next((s for s in b.sections if s.name == '.pdata'), None)
    if not pd or (n + 1) * 12 > min(pd.size, pd.rawsize):
        return None
    row = b.read(pd.addr + 12 * n, 12)
    if not row or len(row) != 12:
        return None
    begin, end, ui = unpack('<III', row)
    size = end - begin
    if (b.image_base + begin != addr or not 0 < size <= 4096 or
            il.function_extent(addr) != (addr, addr + size) or
            (n and il.func_ranges[n-1][1] > addr) or
            (n + 1 < len(starts) and starts[n+1] < addr + size) or
            not any(s.is_exec and s.addr <= addr and addr + size <= s.addr + min(s.size, s.rawsize)
                    for s in b.sections)):
        return None
    # Same plain unwind record, not a chain, exception handler or funclet
    # whose semantics can depend on the original code addresses.
    header = b.read(b.image_base + ui, 4) if ui and not ui % 4 else None
    if not header or len(header) != 4 or header[0] != 1 or header[1] > size:
        return None
    stop = b.image_base + ui + 4 + 2 * ((header[2] + 1) & ~1)
    if not any(s.addr <= b.image_base + ui and stop <= s.addr + min(s.size, s.rawsize)
               and s.offset + stop - s.addr <= len(b.d) for s in b.sections):
        return None
    return size, ui


def _writable(b, addr, size):
    return next((s for s in b.sections if s.addr <= addr and addr + size <= s.addr + s.size
                 and s.chars & 0x80000000 and not s.is_exec), None)


def _guard(lift, seq):
    """Two operands we may rename: a zero-initialized compiler flag's
    compare and store. Nothing else in the cold arm may be conditional."""
    il = lift.il
    j = next((k for k, i in enumerate(seq) if i.flow_control != F.NEXT), None)
    if j is None or j + 4 >= len(seq):
        return None
    jump, lea, call, store, join = seq[j:j+5]
    if (jump.mnemonic != M.JNE or jump.near_branch_target != join.ip or
            lea.mnemonic != M.LEA or lea.op0_register != R.RCX or lea.memory_base != R.RIP or
            call.mnemonic != M.CALL or call.op0_kind != K.NEAR_BRANCH64 or
            call.near_branch_target != lift.rt_init_meta or
            store.mnemonic != M.MOV or store.memory_base != R.RIP or store.op0_kind != K.MEMORY or
            store.op1_kind != K.IMMEDIATE8 or store.immediate8 != 1):
        return None
    # Walk back over flag-preserving prologue instructions. Only the last
    # producer of flags can own this JNE; consumers in the gap would make
    # the flag observable outside the bookkeeping.
    k = j - 1
    while k >= 0 and not (seq[k].rflags_modified or seq[k].rflags_read):
        k -= 1
    if k < 0:
        return None
    cmp = seq[k]
    flag, slot = store.ip_rel_memory_address, lea.ip_rel_memory_address
    if (cmp.mnemonic != M.CMP or cmp.op0_kind != K.MEMORY or cmp.memory_base != R.RIP or
            cmp.op1_kind != K.IMMEDIATE8 or cmp.immediate8 != 0 or cmp.ip_rel_memory_address != flag or
            any(MemorySizeExt.size(i.memory_size) != 1 for i in (cmp, store)) or
            any(i.has_segment_prefix or i.has_lock_prefix or i.has_rep_prefix or i.has_repne_prefix
                for i in (cmp, jump, lea, call, store))):
        return None
    b = il.bin
    section, data = _writable(b, flag, 1), _writable(b, slot, 8)
    if (not section or flag < section.addr + section.rawsize and b.read(flag, 1) != b'\0' or
            slot % 8 or not data or slot + 8 > data.addr + data.rawsize or slot <= flag < slot + 8):
        return None
    # Require a real, file-backed type usage, not an arbitrary address in
    # RCX or a runtime cache guessed from its shape. The LEA's absolute VA
    # itself still participates in the instruction comparison below.
    raw = b.read(slot, 8)
    if not raw or len(raw) != 8:
        return None
    usage = int.from_bytes(raw, 'little')
    idx = (usage & 0x1ffffffe) >> 1
    if usage >> 29 not in (1, 2) or not usage & 1 or idx >= len(il.types) or not il.types[idx]:
        return None
    for n, i in enumerate(seq):
        if i.op0_kind == K.NEAR_BRANCH64 and cmp.ip < i.near_branch_target < join.ip:
            return None  # alternate entry bypassing the flag or LEA
        if n in (k, j + 3):
            continue
        if i.is_ip_rel_memory_operand or (i.memory_base == R.NONE and
                any(i.op_kind(o) == K.MEMORY for o in range(i.op_count))):
            a = i.ip_rel_memory_address if i.is_ip_rel_memory_operand else i.memory_displacement
            if a <= flag < a + max(1, MemorySizeExt.size(i.memory_size)):
                return None
        if any(i.op_kind(o) == K.IMMEDIATE64 and i.immediate(o) == flag for o in range(i.op_count)):
            return None
    return k, j + 3


def _body(lift, addr, size):
    b = lift.il.bin
    raw = b.read(addr, size)
    if not raw or len(raw) != size:
        return None
    seq = list(Decoder(64, raw, ip=addr))
    if any(i.is_invalid for i in seq) or seq[-1].mnemonic != M.RET or seq[-1].next_ip != addr + size:
        return None
    starts = {i.ip for i in seq}
    flags = _guard(lift, seq)
    for k, i in enumerate(seq):
        if i.flow_control in (F.CONDITIONAL_BRANCH, F.UNCONDITIONAL_BRANCH):
            if i.op0_kind != K.NEAR_BRANCH64 or i.near_branch_target not in starts:
                return None
            i.near_branch64 -= addr  # relative to the body, at a decoded boundary
        elif i.flow_control == F.CALL:
            if (i.op0_kind != K.NEAR_BRANCH64 or addr <= i.near_branch_target < addr + size or
                    not b.is_exec_va(i.near_branch_target)):
                return None
            # iced already resolved the rel32 to an absolute external target.
        elif i.flow_control != F.NEXT and i.mnemonic != M.RET:
            return None
        if flags and k in flags:
            i.memory_displacement = 0
        i.ip -= addr  # includes IP and instruction length in eq_all_bits
    return flags, seq


def equivalent_binary(lift, target, ty):
    """Registered equivalent of an unregistered helper with ABI float(T,T).

    T must be a closed non-generic value type. This proves the operation,
    not the origin of the caller's two values; the caller owns that proof.
    """
    il = lift.il
    if (not HAVE_ICED or not _amd64(getattr(il, 'bin', None)) or
            il.addr_candidates.get(target) or target in il.addr_to_method or not ty or
            il._closed_type_key(ty) != (0x11, ty[0], 0) or not 0 <= ty[0] < len(il.meta.typedefs)):
        return None
    td = il.meta.typedefs[ty[0]]
    if (not td.is_valuetype or td.generic_container != -1 or td.index != ty[0] or
            not 0 <= td.method_start <= td.method_start + td.method_count <= len(il.meta.methods)):
        return None
    extent = _extent(il, target)
    if not extent:
        return None
    source = _body(lift, target, extent[0])
    if not source:
        return None
    hit = None
    for mi in il.meta.type_methods(td):
        m = il.meta.methods[mi]
        if (m.declaring != td.index or not m.is_static or m.flags & 7 != 6 or m.flags & (0x40 | 0x400) or
                m.generic_container != -1 or m.param_count != 2 or not m.addr or
                not 0 <= m.return_type < len(il.types) or il._closed_type_key(il.types[m.return_type]) != (0x0c, 0)):
            continue
        ps = il.meta.method_params(m)
        if (m.parameter_start < 0 or len(ps) != 2 or any(not 0 <= p.type < len(il.types) or
                il._closed_type_key(il.types[p.type]) != (0x11, td.index, 0) for p in ps) or
                _extent(il, m.addr) != extent):
            continue
        twin = _body(lift, m.addr, extent[0])
        if (not twin or source[0] != twin[0] or len(source[1]) != len(twin[1]) or
                not all(a.eq_all_bits(b) for a, b in zip(source[1], twin[1]))):
            continue
        row = ('method', mi)
        if (hit is not None or m.index != mi or il.addr_to_method.get(m.addr) != row or
                il.addr_candidates.get(m.addr) != [row]):
            return None
        hit = m
    return hit
