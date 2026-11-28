"""Native/unwind agreement for a fixed, RSP-relative Win64 frame."""
from bisect import bisect_right

from il2cpp.binary import PE
from il2cpp.inline_task import _kickoff_frame
from il2cpp.prelude import HAVE_ICED
from il2cpp.text import sdisp

if HAVE_ICED:
    from iced_x86 import (FlowControl as F, InstructionInfoFactory, MemorySizeExt,
                          Mnemonic as M, OpAccess, OpKind as K, Register as R, RegisterExt)

    _INFO = InstructionInfoFactory()
    _WRITE = {OpAccess.WRITE, OpAccess.COND_WRITE, OpAccess.READ_WRITE, OpAccess.READ_COND_WRITE}
    _GPR = {R.RBX, R.RBP, R.RSI, R.RDI, R.R12, R.R13, R.R14, R.R15}
    _NONVOL = _GPR | set(range(R.ZMM6, R.ZMM15 + 1))
    _IMM = (K.IMMEDIATE8TO64, K.IMMEDIATE32TO64)


def _slot_move(i, *, load=False):
    """Full-width nonvolatile transfer using final RSP and a constant offset."""
    mem = int(load)
    if (i.op_count != 2 or i.op_kind(mem) != K.MEMORY or i.op_kind(1-mem) != K.REGISTER or
            i.memory_base != R.RSP or i.memory_index != R.NONE or i.has_segment_prefix):
        return None
    r = i.op_register(1-mem)
    if i.mnemonic == M.MOV and r in _GPR:
        width = 8
    elif i.mnemonic in (M.MOVAPS, M.MOVUPS, M.MOVDQA, M.MOVDQU) and R.XMM6 <= r <= R.XMM15:
        width = 16
    else:
        return None
    return r, sdisp(i.memory_displacement), width


def _saves(seq, k, raw):
    start = seq[0].ip
    alloc = seq[k]
    n = alloc.next_ip - start
    if len(raw) < 6 or raw[0] != 1 or raw[3] or raw[1] != raw[4] or not 0 < n <= raw[1]:
        return None

    # Split the late UWOP_SAVE_NONVOL / UWOP_SAVE_XMM128 rows off the
    # ordinary home/push/alloc prologue. These are actual code offsets, not
    # a count of instructions to skip: calls and branches can intervene.
    by_end = {i.next_ip-start: i for i in seq[k+1:] if i.next_ip-start <= raw[1]}
    pos = 4
    prev = 256
    late = {}
    while pos < len(raw) and raw[pos] > n:
        end = raw[pos]
        if end >= prev or pos+4 > len(raw) or end not in by_end:
            return None
        i = by_end[end]
        slot = _slot_move(i)
        if slot is None:
            return None
        reg, off, width = slot
        op = (RegisterExt.number(reg) << 4) | (4 if width == 8 else 8)
        if raw[pos+1] != op or off != width * int.from_bytes(raw[pos+2:pos+4], 'little'):
            return None
        late[i.ip] = slot
        prev = end
        pos += 4

    codes = raw[pos:]
    prefix = bytes((1, n, len(codes)//2, 0)) + codes
    frame = _kickoff_frame(seq[:k+1], prefix, plain=True)
    if not frame:
        return None
    depth = -frame[1]
    size = alloc.immediate(1)
    if depth % 16 != 8:
        return None

    # The validated early home stores precede all pushes. Unwind records
    # these stores at allocation end, but their *native* base is entry RSP.
    pushed = []
    homes = []
    for i in seq[:k]:
        if i.mnemonic == M.PUSH:
            pushed.append(i.op0_register)
        elif i.op1_register != R.RCX:
            homes.append((i.op1_register, depth + sdisp(i.memory_displacement), 8))
        elif any(h[1] == depth+8 for h in homes):
            return None  # receiver home overwrites an earlier nonvolatile save
    moves = homes + list(late.values())
    if len({r for r, _, _ in moves} | set(pushed)) != len(moves) + len(pushed):
        return None
    if any(not (0x20 <= off and off+width <= size or
                depth+8 <= off and off+width <= depth+40) for _, off, width in moves):
        return None  # not the outgoing shadow, return address, or stack arguments
    spans = tuple(sorted([(off, width) for _, off, width in moves] +
                         [(depth-8*j, 8) for j in range(1, len(pushed)+1)]))
    if any(a+w > b for (a, w), (b, _) in zip(spans, spans[1:])):
        return None
    return size, depth, spans, pushed, moves, late


def _epilogue(seq, j, size, pushed, moves):
    """Find the first instruction of this exit's contiguous, complete restore."""
    start = j - len(pushed) - 1 - len(moves)
    if start < 0:
        return None
    add = seq[start+len(moves)]
    if (add.mnemonic != M.ADD or add.op0_register != R.RSP or add.op1_kind not in _IMM or
            add.immediate(1) != size or
            any(i.mnemonic != M.POP or i.op0_register != r for i, r in
                zip(seq[start+len(moves)+1:j], reversed(pushed)))):
        return None
    if {_slot_move(i, load=True) for i in seq[start:start+len(moves)]} != set(moves):
        return None
    return start


def stack_local_frame(lift, method, blocks, pads, *, incoming=None):
    """Return (allocation_size, entry_depth, saved_spans), or None.

    Entry RSP is final RSP + entry_depth. The sorted (offset, width) spans
    use final RSP, including pushes and caller-home saves. A local's full
    extent, including any byref use, must fit in [32, allocation_size) and
    avoid *all* these spans. This frame proof does not bound escaped pointers.
    """
    il = lift.il
    if (not HAVE_ICED or not isinstance(getattr(il, 'bin', None), PE) or not il.bin.is64 or
            pads or not blocks or blocks[0].preds):
        return None
    if not getattr(il, '_eh4_begins', None) and not (hasattr(il, '_eh4_init') and il._eh4_init()):
        return None
    rva = method.addr - il.bin.image_base
    idx = bisect_right(il._eh4_begins, rva) - 1
    if idx < 0 or il._eh4_entries[idx][0] != rva:
        return None
    _, end, ui = il._eh4_entries[idx]
    hi = il.bin.image_base + end
    seq = [i for b in blocks for i in b.insns]
    if (not seq or seq[0].ip != method.addr or seq[-1].next_ip != hi or any(i.is_invalid for i in seq) or
            any(a.next_ip != b.ip for a, b in zip(seq, seq[1:]))):
        return None
    addr = il.bin.image_base + ui
    header = il.bin.read(addr, 4) or b''
    if len(header) != 4 or header[0] != 1 or header[3] or not header[2]:
        return None
    raw = il.bin.read(addr, 4 + 2*header[2]) or b''
    if len(raw) != 4 + 2*header[2]:
        return None
    k = next((j for j, i in enumerate(seq) if i.mnemonic == M.SUB and i.op0_register == R.RSP), None)
    if k is None or seq[k].op1_kind not in _IMM:
        return None
    frame = _saves(seq, k, raw)
    if frame is None:
        return None
    size, depth, spans, pushed, moves, late = frame

    # Pre-mark every normal exit, including direct external tail jumps. A
    # branch may reach its first restore, never skip one or enter at RET.
    body = seq[k+1:]
    epi = set()
    interior = set()
    for j, i in enumerate(body):
        external = (i.flow_control == F.UNCONDITIONAL_BRANCH and i.op0_kind == K.NEAR_BRANCH64 and
                    not method.addr <= i.near_branch_target < hi)
        if i.flow_control != F.RETURN and not external:
            continue
        if not external and (i.mnemonic != M.RET or i.op_count or i.stack_pointer_increment != 8):
            return None
        first = _epilogue(body, j, size, pushed, moves)
        if first is None or body[first].ip < method.addr + header[1]:
            return None
        epi.update(x.ip for x in body[first:j+1])
        interior.update(x.ip for x in body[first+1:j+1])
    if not epi:
        return None

    starts = {i.ip for i in body}
    saved_at = {RegisterExt.full_register(r): seq[k].next_ip for r in pushed + [r for r, _, _ in moves]}
    save_ends = []
    for i in body:
        if i.ip in late:
            saved_at[RegisterExt.full_register(late[i.ip][0])] = i.next_ip
            save_ends.append(i.next_ip)
    protected = spans + ((depth, 8),)  # also guard the native return address
    for i in body:
        if i.ip in epi or i.ip in late:
            continue
        fc = i.flow_control
        if fc in (F.UNCONDITIONAL_BRANCH, F.CONDITIONAL_BRANCH):
            t = i.near_branch_target
            if (i.op0_kind != K.NEAR_BRANCH64 or t not in starts or t in interior or
                    bisect_right(save_ends, i.ip) != bisect_right(save_ends, t)):
                return None
        elif fc in (F.CALL, F.INDIRECT_CALL):
            if (size < 32 or i.mnemonic != M.CALL or i.stack_pointer_increment != -8 or
                    fc == F.CALL and (i.op0_kind != K.NEAR_BRANCH64 or method.addr <= i.near_branch_target < hi)):
                return None
        elif i.mnemonic in (M.INT3, M.UD2):
            continue  # explicit trap, no normal return
        elif fc != F.NEXT:
            return None
        if fc != F.UNCONDITIONAL_BRANCH and i.next_ip not in starts:
            return None  # no fallthrough out of the registered extent

        if (i.memory_base == R.ESP or i.memory_index in (R.RSP, R.ESP) or
                any(i.op_kind(j) == K.REGISTER and RegisterExt.full_register(i.op_register(j)) == R.RSP
                    for j in range(i.op_count))):
            return None
        if i.memory_base == R.RSP:
            off = sdisp(i.memory_displacement)
            # For a memory bit-string operand the register bit index selects
            # a word *beyond* the nominal effective address/operand width.
            if i.mnemonic in (M.BT, M.BTC, M.BTR, M.BTS) and i.op1_kind == K.REGISTER:
                return None
            # A caller may prove a bounded scalar borrow in incoming Win64
            # shadow space. Keep its entire width off the save/return spans.
            borrow = (incoming or {}).get(i.ip) if i.mnemonic == M.LEA else None
            in_home = borrow == 4 and not off % 4 and depth+8 <= off and off+4 <= depth+40
            if i.mnemonic == M.LEA and (i.op0_register not in (R.RCX, R.RDX, R.R8, R.R9) or
                                        not (32 <= off < size or in_home)):
                return None  # allow local argument borrows, not a second stack base
            width = (borrow if in_home else 1) if i.mnemonic == M.LEA else MemorySizeExt.size(i.memory_size)
            if (i.has_segment_prefix or i.memory_index != R.NONE or not width or
                    any(off < a+w and a < off+width for a, w in protected)):
                return None
        for u in _INFO.info(i).used_registers():
            if u.access in _WRITE:
                r = RegisterExt.full_register(u.register)
                if (r == R.RSP and fc not in (F.CALL, F.INDIRECT_CALL) or
                        r in _NONVOL and (r not in saved_at or i.ip < saved_at[r])):
                    return None
    return size, depth, spans
