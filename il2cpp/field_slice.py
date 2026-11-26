"""Recognize a Win64 leaf that returns twelve bytes of its receiver by value."""
import re

from il2cpp.equivalent_binary import _amd64
from il2cpp.prelude import HAVE_ICED
from il2cpp.text import sdisp

if HAVE_ICED:
    from iced_x86 import Decoder, MemorySizeExt, OpKind as K, Register as R, RegisterExt

    _SCRATCH = {R.RAX, R.RCX, R.RDX, R.R8, R.R9, R.R10, R.R11}


# Canonical scalar MOVSD/MOVSS and dword/qword MOV encodings. Check the
# bytes because a decoder can silently discard a redundant legacy prefix.
# REX.R selects a high scratch register; the two pointer bases need no REX.B.
_MEM = re.compile(rb'(?:[\xf2\xf3]\x0f[\x10\x11]|[\x44\x48\x4c]?[\x89\x8b])')
_ECHO = (b'\x48\x8b\xc1', b'\x48\x89\xc8')
_LEAD = re.compile(rb'(?:[\xf2\xf3]\x0f\x10|[\x44\x48\x4c]?\x8b|\x48\x89\xc8)')
_MAX_BYTES = 4 * 9 + 3 + 1  # four scalar memory moves, echo, RET


def _body(il, target, lead=_LEAD):
    b = getattr(il, 'bin', None)
    if not getattr(b, 'd', None) or not _amd64(b):
        return None
    for s in b.sections:
        size = min(s.size, s.rawsize)
        delta = target - s.addr
        if s.is_exec and 0 <= delta < size:
            pos = s.offset + delta
            stop = pos + min(_MAX_BYTES, size - delta)
            break
    else:
        return None

    # Most call targets aren't candidates. No decoder or boundary lookups
    # on ordinary prologues, thunks or bodies without a nearby plain RET.
    if not lead.match(b.d, pos, stop) or b.d.find(b'\xc3', pos, stop) < 0:
        return None
    start, end = il.function_extent(target)
    if start != target or end <= target:
        return None
    end = min(end, target + stop - pos)
    # A frameless leaf need not have .pdata; its fallback extent can span
    # other functions. MethodDef order also omits generic entries/thunks.
    for nxt in (il.next_function_start(target), il.next_method_start(target)):
        if nxt is not None:
            end = min(end, nxt)
    entries = getattr(il, 'addr_to_method', {})
    exports = b.exports
    for va in range(target + 1, end):
        if va in entries or va in exports:
            end = va
            break
    # Decode the same bounded image view as the other native proofs. The
    # raw section above is only an inexpensive rejection filter.
    return b.read(target, end - target)


def field_offset(il, target):
    """Return the source byte displacement for a proved 8+4 copy, else None."""
    code = _body(il, target) if HAVE_ICED else None
    if not code:
        return None
    # Register values are either entry pointers or (source offset, width).
    # Using full register identities also kills a pointer on a dword write.
    regs = {R.RCX: 'out', R.RDX: 'in'}
    stores = {}
    for step, i in enumerate(Decoder(64, bytes(code))):
        pos = i.ip
        if step == 5:
            offset = stores.get(0)
            if (code[pos:pos + i.len] == b'\xc3' and regs.get(R.RAX) == 'out' and
                    offset is not None and stores.get(8) == offset + 8):
                return offset
            return None
        if code[pos:pos + i.len] in _ECHO and regs[R.RCX] == 'out':
            regs[R.RAX] = 'out'
            continue
        if not _MEM.match(code, pos) or i.memory_index != R.NONE:
            return None
        width = MemorySizeExt.size(i.memory_size)
        disp = sdisp(i.memory_displacement)
        if i.op1_kind == K.MEMORY and i.op0_kind == K.REGISTER:
            reg = RegisterExt.full_register(i.op0_register)
            # Snapshot both lanes before either store: the two incoming
            # pointers aren't known distinct from the callee bytes alone.
            if (stores or regs.get(i.memory_base) != 'in' or disp < 0 or
                    not (reg in _SCRATCH or R.XMM0 <= i.op0_register <= R.XMM5)):
                return None
            regs[reg] = (disp, width)
        elif i.op0_kind == K.MEMORY and i.op1_kind == K.REGISTER:
            lane = regs.get(RegisterExt.full_register(i.op1_register))
            if (regs.get(i.memory_base) != 'out' or not isinstance(lane, tuple) or
                    lane[1] != width or (disp, width) not in ((0, 8), (8, 4)) or disp in stores):
                return None
            stores[disp] = lane[0]
        else:
            return None
    return None
