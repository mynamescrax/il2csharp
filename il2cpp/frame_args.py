"""Early RBP-relative Win64 reads of incoming managed reference parameters."""
from il2cpp.binary import PE
from il2cpp.metadata import source_params
from il2cpp.names import safe_ident
from il2cpp.prelude import *  # noqa: F401,F403
from il2cpp.runtime.meta import IMM_OPS
from il2cpp.text import sdisp
from il2cpp.x64 import _reg_size

if HAVE_ICED:
    from iced_x86 import RegisterExt


def entry_reference_loads(lift, m, insns, skip, pads):
    if (not insns or not isinstance(getattr(lift, 'bin', None), PE) or
            not lift.bin.is64 or insns[0].ip != m.addr or getattr(m, 'param_count', 0) < 3):
        return {}
    il = lift.il
    rt = il.types[m.return_type] if 0 <= m.return_type < len(il.types) else None
    if not il._return_abi_is_known(rt):
        return {}
    first = int(not m.is_static) + int(il.returns_sret(rt))
    capture = (insns[0].mnemonic == Mnemonic.MOV and insns[0].op0_register == IReg.RAX and
               insns[0].op1_register == IReg.RSP)
    homes = {}
    for slot, p in enumerate(source_params(il.meta, m), first):
        ty = il.types[p.type] if 0 <= p.type < len(il.types) else None
        if slot >= 4 and ty and il._type_enum(ty) in ((0x0e,0x12) if capture else (0x0e,)) and not ty[1] & (1 << 29):
            homes[8 + slot * 8] = (safe_ident(p.name), ty)
    if not homes:
        return {}
    return _prefix_loads(insns, homes, skip, pads, getattr(lift, 'rt_init_meta', None))


def _prefix_loads(insns, homes, skip, pads, init):
    # The ordinary slot map uses current RSP. For a frame pointer the
    # displacement is relative to the RSP captured *before* frame allocation.
    # Limit the correction to the prologue and pristine incoming homes.
    start = insns[0].ip
    end = min((p for p in pads if p >= start), default=insns[-1].next_ip)
    for ins in insns:
        if ins.flow_control == FlowControl.INDIRECT_BRANCH:
            return {}
        if (ins.flow_control in (FlowControl.CONDITIONAL_BRANCH, FlowControl.UNCONDITIONAL_BRANCH)
                and start <= ins.near_branch_target <= ins.ip):
            end = min(end, ins.near_branch_target)

    sites = {}
    sp, bp = 0, None
    entry_rax = False
    guard_end = None
    for i in insns[:256]:
        if i.ip >= end:
            break
        mn, a, b = i.mnemonic, i.op0_kind, i.op1_kind
        if i.has_segment_prefix:
            break
        if guard_end == i.ip:
            guard_end = None
        if guard_end is not None:
            # On the cold arm accept only metadata slot setup, its known
            # helper (preserves RBP/RSP), and the RIP-relative flag store.
            if i.ip not in skip or not (
                mn == Mnemonic.LEA and i.op0_register == IReg.RCX and i.is_ip_rel_memory_operand or
                mn == Mnemonic.CALL and a == OpKind.NEAR_BRANCH64 and i.near_branch_target == init or
                mn == Mnemonic.MOV and a == OpKind.MEMORY and i.is_ip_rel_memory_operand and b in IMM_OPS
            ):
                break
            continue
        if (i.ip == start and mn == Mnemonic.MOV and i.op0_register == IReg.RAX and i.op1_register == IReg.RSP):
            entry_rax = True
        elif (entry_rax and mn == Mnemonic.MOV and i.memory_base == IReg.RAX and i.memory_index == IReg.NONE and
              a == OpKind.MEMORY and b == OpKind.REGISTER and _reg_size(i.op1_register) == 8 and
              i.memory_displacement in (8,16,24,32)):
            continue  # home saves do not touch incoming stack parameters
        elif (entry_rax and bp is None and mn == Mnemonic.LEA and i.op0_register == IReg.RBP and
              i.memory_base == IReg.RAX and i.memory_index == IReg.NONE):
            bp = sdisp(i.memory_displacement)
            entry_rax = False
        elif mn == Mnemonic.JNE and i.ip in skip and a == OpKind.NEAR_BRANCH64:
            entry_rax = False
            guard_end = i.near_branch_target
        elif mn == Mnemonic.CMP and i.ip in skip and i.is_ip_rel_memory_operand:
            continue
        elif mn == Mnemonic.PUSH and a == OpKind.REGISTER and _reg_size(i.op0_register) == 8:
            sp -= 8
        elif mn == Mnemonic.SUB and i.op0_register == IReg.RSP and b in IMM_OPS and 0 <= i.immediate(1) < 2**31:
            sp -= i.immediate(1)
        elif mn == Mnemonic.MOV and i.op0_register == IReg.RBP and i.op1_register == IReg.RSP and bp is None:
            bp = sp
            entry_rax = False
        elif (mn in (Mnemonic.MOV, Mnemonic.MOVAPS, Mnemonic.MOVZX) and
               a == OpKind.REGISTER and b == OpKind.REGISTER):
            if RegisterExt.full_register(i.op0_register) == IReg.RAX:
                entry_rax = False
            if any(RegisterExt.full_register(r) in (IReg.RSP, IReg.RBP) for r in (i.op0_register, i.op1_register)):
                break
        elif (mn in (Mnemonic.MOV, Mnemonic.MOVAPS) and a == OpKind.MEMORY and b == OpKind.REGISTER
              and i.memory_base == IReg.RSP and i.memory_index == IReg.NONE and not i.has_segment_prefix):
            # A save/spill must end below the first stack parameter.
            if sp + sdisp(i.memory_displacement) + MemorySizeExt.size(i.memory_size) > 0x28:
                break
        elif (bp is not None and mn == Mnemonic.MOV and a == OpKind.REGISTER and b == OpKind.MEMORY
              and _reg_size(i.op0_register) == 8 and i.op0_register not in (IReg.RSP, IReg.RBP)
              and i.memory_base == IReg.RBP and i.memory_index == IReg.NONE and not i.has_segment_prefix):
            home = bp + sdisp(i.memory_displacement)
            if home in homes:
                sites[i.ip] = homes[home]
        else:
            break
    return sites
