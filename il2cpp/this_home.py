"""Recover a saved Win64 receiver across in-frame EH continuations."""
from bisect import bisect_right

from il2cpp.binary import PE
from il2cpp.prelude import *  # noqa: F401,F403
from il2cpp.runtime.meta import IMM_OPS
from il2cpp.text import sdisp

if HAVE_ICED:
    from iced_x86 import InstructionInfoFactory, OpAccess, RegisterExt
    _INFO = InstructionInfoFactory()
    _WRITE = {OpAccess.WRITE, OpAccess.COND_WRITE, OpAccess.READ_WRITE, OpAccess.READ_COND_WRITE}


def _fixed_frame(insns, unwind, *, require_receiver_home=True):
    """Match the prologue to unwind codes. Receiver reloads need a saved RCX;
    frame-only clients can instead validate the nonvolatile home stores."""
    if (len(unwind) < 4 or unwind[0] & 7 != 1 or unwind[3] != 0 or
            len(unwind) < 4 + 2 * unwind[2]):
        return None
    start = insns[0].ip
    sp = 0
    saved = None
    codes = []
    entry_rax = False
    xmm_saves = []
    for ins in insns:
        n = ins.next_ip - start
        if n > unwind[1]:
            break
        if (ins.ip == start and ins.mnemonic == Mnemonic.MOV and ins.op0_register == IReg.RAX
                and ins.op1_register == IReg.RSP):
            entry_rax = True
        elif (ins.mnemonic == Mnemonic.MOV and ins.op0_kind == OpKind.MEMORY and
                (ins.memory_base == IReg.RSP or entry_rax and ins.memory_base == IReg.RAX) and ins.memory_index == IReg.NONE and
                not ins.has_segment_prefix and ins.op1_kind == OpKind.REGISTER):
            if (RegisterExt.full_register(ins.op1_register) == IReg.RSP or
                    entry_rax and RegisterExt.full_register(ins.op1_register) == IReg.RAX):
                return None  # do not let a copy of the frame pointer escape
            off = (sp if ins.memory_base == IReg.RSP else 0) + sdisp(ins.memory_displacement)
            if ins.op1_register == IReg.RCX and off == 8:
                if saved is not None:
                    return None
                saved = ins.ip
            elif require_receiver_home and off < 16 and off + MemorySizeExt.size(ins.memory_size) > 8:
                return None
        elif ins.mnemonic == Mnemonic.PUSH and ins.op0_register in (
                IReg.RBX, IReg.RBP, IReg.RSI, IReg.RDI, IReg.R12, IReg.R13, IReg.R14, IReg.R15):
            codes.append(bytes([n, RegisterExt.number(ins.op0_register) << 4]))  # UWOP_PUSH_NONVOL
            sp -= 8
        elif ins.mnemonic == Mnemonic.SUB and ins.op0_register == IReg.RSP and ins.op1_kind in IMM_OPS:
            size = ins.immediate(1)
            if not 8 <= size <= 0xffff * 8 or size % 8:
                return None
            if size <= 128:
                codes.append(bytes([n, ((size // 8 - 1) << 4) | 2]))  # UWOP_ALLOC_SMALL
            else:
                codes.append(bytes([n, 1]) + struct.pack('<H', size // 8))  # UWOP_ALLOC_LARGE
            sp -= size
        elif (ins.mnemonic == Mnemonic.MOVAPS and ins.op0_kind == OpKind.MEMORY and
              entry_rax and ins.memory_base == IReg.RAX and ins.memory_index == IReg.NONE and
              not ins.has_segment_prefix and IReg.XMM6 <= ins.op1_register <= IReg.XMM15):
            xmm_saves.append((len(codes), n, RegisterExt.number(ins.op1_register), sdisp(ins.memory_displacement)))
            codes.append(b'')
        else:
            return None
    for idx, n, reg, off in xmm_saves:
        if off + 16 > 0 or not 0 <= off - sp <= 0xffff * 16 or (off - sp) % 16:
            return None
        codes[idx] = bytes([n, (reg << 4) | 8]) + struct.pack('<H', (off-sp)//16)  # UWOP_SAVE_XMM128
    if (require_receiver_home and saved is None) or not codes or codes[-1][0] != unwind[1]:
        return None
    return (saved, sp, entry_rax) if unwind[4:4+2*unwind[2]] == b''.join(reversed(codes)) else None


def _reloads(insns, pads, unwind, borrows=None):
    frame = _fixed_frame(insns, unwind)
    if not frame:
        return {}
    saved, framed_sp, entry_rax = frame
    lo, hi = insns[0].ip, insns[-1].next_ip
    by_ip = {i.ip:i for i in insns}
    if not all(p in by_ip and p >= lo + unwind[1] for p in pads):
        return {}
    # Pads here are continuations in the SAME RUNTIME_FUNCTION, not child
    # funcs with their own stack. Only RSP is seeded there, never RCX/RDI.
    work = [(lo, 0, False)] + [(p, framed_sp, entry_rax) for p in pads]
    depths, seen, sites = {}, set(), {}
    while work:
        ip, sp, alias = work.pop()
        if ip in depths and sp != depths[ip]:
            return {}
        if (ip, alias) in seen:
            continue
        seen.add((ip, alias))
        i = by_ip.get(ip)
        if i is None:
            return {}
        depths[ip] = sp
        info = _INFO.info(i)
        prologue = ip < lo + unwind[1]
        if entry_rax and ip == lo:
            work.append((i.next_ip, sp, True))
            continue
        if alias and not prologue:
            # An unmodified entry-RSP alias could bypass every RSP-address
            # overlap check. Require a full definition before *any* use.
            for r in info.used_registers():
                if RegisterExt.full_register(r.register) == IReg.RAX:
                    if r.access != OpAccess.WRITE or RegisterExt.size(r.register) < 4:
                        return {}
                    alias = False
        if ip >= lo + unwind[1] and sp != framed_sp and i.mnemonic not in (Mnemonic.POP, Mnemonic.RET):
            return {}  # no dynamic frame between the prologue and terminal epilogues
        if i.memory_base == IReg.RSP:
            if i.memory_index != IReg.NONE or i.has_segment_prefix:
                return {}
            off = sp + sdisp(i.memory_displacement)
            width = MemorySizeExt.size(i.memory_size)
            if i.mnemonic == Mnemonic.LEA:
                # Extra argument-register borrows need a bounded storage
                # width. An Int32 in another shadow slot is disjoint too.
                nxt = by_ip.get(i.next_ip)
                span = (borrows or {}).get(ip, 0)
                bounded = (span > 0 and i.memory_displacement >= 0x20 and
                           (off + span <= 0 or span == 4 and 16 <= off and off + span <= 0x28))
                local = (off < 0 and i.memory_displacement >= 0x20 and nxt and (
                         i.op0_register == IReg.RCX and nxt.flow_control == FlowControl.CALL or
                         i.op0_register == IReg.RBX and nxt.mnemonic == Mnemonic.MOV and
                         nxt.memory_base == IReg.RSP and nxt.op1_register == IReg.RBX))
                if not bounded and not local:
                    return {}
            elif ip != saved and any(m.access in _WRITE for m in info.used_memory()):
                if not width or off < 16 and off + width > 8:
                    return {}
            elif (off == 8 and i.mnemonic == Mnemonic.MOV and i.op0_kind == OpKind.REGISTER
                  and RegisterExt.is_gpr64(i.op0_register) and width == 8):
                sites[ip] = True
        elif i.memory_index == IReg.RSP:
            return {}
        fc = i.flow_control
        if fc in (FlowControl.RETURN, FlowControl.INTERRUPT, FlowControl.EXCEPTION):
            continue
        if fc == FlowControl.INDIRECT_BRANCH or (fc == FlowControl.CALL and lo <= i.near_branch_target < hi):
            return {}
        if i.mnemonic in (Mnemonic.ADD, Mnemonic.SUB) and i.op0_register == IReg.RSP and i.op1_kind in IMM_OPS:
            sp += (1 if i.mnemonic == Mnemonic.ADD else -1) * i.immediate(1)
        elif i.mnemonic in (Mnemonic.PUSH, Mnemonic.POP) and RegisterExt.is_gpr64(i.op0_register) and i.op0_register != IReg.RSP:
            sp += 8 if i.mnemonic == Mnemonic.POP else -8
        elif fc not in (FlowControl.CALL, FlowControl.INDIRECT_CALL):
            if any(RegisterExt.full_register(r.register) == IReg.RSP and r.access in _WRITE for r in info.used_registers()):
                return {}
            if any(i.op_kind(k) == OpKind.REGISTER and RegisterExt.full_register(i.op_register(k)) == IReg.RSP
                   for k in range(i.op_count)):
                return {}  # alternate stack base, no alias proof
        if sp > 0:
            return {}
        if fc in (FlowControl.CONDITIONAL_BRANCH, FlowControl.UNCONDITIONAL_BRANCH):
            target = i.near_branch_target
            if i.op0_kind != OpKind.NEAR_BRANCH64 or lo <= target < lo + unwind[1]:
                return {}
            if lo <= target < hi:
                work.append((target, sp, alias))
        if fc != FlowControl.UNCONDITIONAL_BRANCH:
            work.append((i.next_ip, sp, alias))
    return sites


def _bounded_borrows(il, insns, pads):
    """Widths for immediate call-argument borrows outside the basic RCX-local pattern."""
    spans = {}
    entries = set(pads) | {x.near_branch_target for x in insns if x.flow_control in
                            (FlowControl.CONDITIONAL_BRANCH, FlowControl.UNCONDITIONAL_BRANCH)}
    for j, call in enumerate(insns):
        if j < 1 or call.flow_control != FlowControl.CALL or call.op0_kind != OpKind.NEAR_BRANCH64:
            continue
        # LEAs into parameter registers, optionally followed by the usual
        # `mov rcx,receiver`. No indexed pointer, arithmetic or intervening
        # entry into this call setup is evidence of a bounded borrow.
        k = j - 1
        x = insns[k]
        if (x.mnemonic == Mnemonic.MOV and x.op0_register == IReg.RCX and
                x.op1_register in (IReg.RBX, IReg.RSI, IReg.RDI, IReg.R12, IReg.R13, IReg.R14, IReg.R15)):
            k -= 1
        borrows = []
        while k >= 0:
            x = insns[k]
            if (x.mnemonic != Mnemonic.LEA or x.op0_register not in (IReg.RCX,IReg.RDX,IReg.R8) or
                    x.memory_base != IReg.RSP or x.memory_index != IReg.NONE or x.has_segment_prefix):
                break
            borrows.append(x)
            k -= 1
        if not borrows or len({b.op0_register for b in borrows}) != len(borrows):
            continue
        target = call.near_branch_target
        cands = il.addr_candidates.get(target, ())
        if len(cands) == 1 and cands[0][0] == 'method':
            m = il.meta.methods[cands[0][1]]
            if m.addr != target or m.generic_container != -1:
                continue
            rt = il.types[m.return_type] if 0 <= m.return_type < len(il.types) else None
        else:
            # Fully shared code: the exact MethodRef sits in R9 (slot three).
            # Require three declared static arguments and a register return;
            # an sret/instance signature would shift the positions.
            if k < 0:
                continue
            hidden = insns[k]
            if hidden.mnemonic != Mnemonic.MOV or hidden.op0_register != IReg.R9 or not hidden.is_ip_rel_memory_operand:
                continue
            usage = il.decode_slot(hidden.ip_rel_memory_address) or {}
            si = usage.get('idx', -1)
            if usage.get('kind') != 6 or not 0 <= si < len(il.method_specs):
                continue
            mi = il.method_specs[si][0]
            if not 0 <= mi < len(il.meta.methods):
                continue
            m = il.meta.methods[mi]
            rt = il.candidate_return_type(('generic', si))
            if not m.is_static or m.param_count != 3 or m.generic_container == -1:
                continue
            k -= 1
        if (not il._return_abi_is_known(rt) or il.returns_sret(rt) or
                any(insns[p+1].ip in entries or insns[p].next_ip != insns[p+1].ip for p in range(k+1,j))):
            continue
        ps = il.meta.method_params(m)
        for x in borrows:
            pos = (IReg.RCX,IReg.RDX,IReg.R8).index(x.op0_register) - int(not m.is_static)
            if pos == -1:
                td = il.meta.typedefs[m.declaring]
                if ((td.namespace, td.name, m.name) == ('System','Int32','ToString') and
                        td.is_valuetype and not ps and il._type_enum(rt) == 0x0e):
                    spans[x.ip] = 4
            elif pos < len(ps) and 0 <= ps[pos].type < len(il.types):
                pt = il.types[ps[pos].type]
                if pt and il._type_enum(pt) == 0x11 and not pt[1] & (1 << 29):
                    size = il._sf_field_size(pt, 0)
                    if size and size not in (1,2,4,8):  # indirect Win64 by-value aggregate
                        spans[x.ip] = size
    return spans


def saved_this_reloads(il, method, td, insns, eh):
    pads = (eh or {}).get('pads') or ()
    if (not pads or not isinstance(il.bin, PE) or not il.bin.is64 or method.is_static or
            td.is_valuetype or not insns or len(insns) > 1024 or not 0 <= method.return_type < len(il.types)):
        return {}
    rt = il.types[method.return_type]
    if not il._return_abi_is_known(rt) or il.returns_sret(rt):
        return {}
    rva = method.addr - il.bin.image_base
    row = bisect_right(il._eh4_begins, rva) - 1
    if row < 0:
        return {}
    begin, end, ui = il._eh4_entries[row]
    if begin != rva or insns[0].ip != method.addr or insns[-1].next_ip > il.bin.image_base + end:
        return {}
    # The frame/home must already exist before the first protected range.
    data = il.bin.read(il.bin.image_base + ui, 4) or b''
    spans = (eh or {}).get('try_ranges')
    if len(data) != 4 or not spans or any(a < method.addr + data[1] for _,_,_,ranges in spans for a,_ in ranges):
        return {}
    raw = il.bin.read(il.bin.image_base + ui, 4 + 2 * data[2]) or b''
    frame = _fixed_frame(insns, raw)
    if frame is None:
        return {}
    borrows = _bounded_borrows(il, insns, pads) if frame[2] else None
    return _reloads(insns, pads, raw, borrows)
