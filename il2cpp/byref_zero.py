"""Prove dword zero initializers through Win64 by-reference parameters."""
from il2cpp.binary import PE
from il2cpp.metadata import source_params
from il2cpp.names import safe_ident
from il2cpp.prelude import *  # noqa: F401,F403
from il2cpp.runtime.meta import IMM_OPS
from il2cpp.text import reg_name
from il2cpp.x64 import ARG_REGS, VOLATILE, _reg_size


def entry_ref_args(lift, method, insns):
    if not isinstance(getattr(lift, 'bin', None), PE) or not insns or insns[0].ip != method.addr:
        return {}
    il = lift.il
    if not method.param_count or not 0 <= method.return_type < len(il.types):
        return {}
    rt = il.types[method.return_type]
    if not il._return_abi_is_known(rt):
        return {}
    first = int(not method.is_static) + int(il.returns_sret(rt))
    facts = {}
    for reg, p in zip(ARG_REGS[first:], source_params(il.meta, method)):
        pt = il.types[p.type] if 0 <= p.type < len(il.types) else None
        if pt and pt[1] & (1 << 29) and il._type_enum(pt) in (8, 12):
            facts[reg] = (safe_ident(p.name), '0' if il._type_enum(pt) == 8 else '0f')
    return facts


def entry_ref_zeros(lift, method, insns, pads=()):
    facts = entry_ref_args(lift, method, insns)
    return _scan(insns, facts, getattr(lift, 'rt_init_meta', None), pads) if facts else {}


def _scan(insns, facts, init_meta, pads):
    # Track only entry GPR addresses, full-width copies of those addresses,
    # and registers whose low 32 bits are zero. No stack or heap reload is
    # address proof. Stop before a back-edge target or secondary EH entry.
    start = insns[0].ip
    end = min((p for p in pads if p >= start), default=insns[-1].next_ip)
    for ins in insns:
        if ins.flow_control == FlowControl.INDIRECT_BRANCH:
            return {}
        if (ins.flow_control in (FlowControl.CONDITIONAL_BRANCH, FlowControl.UNCONDITIONAL_BRANCH)
                and start <= ins.near_branch_target <= ins.ip):
            end = min(end, ins.near_branch_target)

    prefix = insns[:96]
    starts = {ins.ip for ins in prefix}
    joins, sites = {}, {}
    def common(a, b):
        return {r: v for r, v in a.items() if b.get(r) == v}
    for ins in prefix:
        if ins.ip >= end:
            break
        if ins.ip in joins:
            facts = common(facts, joins.pop(ins.ip))
        mn, a, b = ins.mnemonic, ins.op0_kind, ins.op1_kind
        if mn in (Mnemonic.JE, Mnemonic.JNE) and a == OpKind.NEAR_BRANCH64:
            target = ins.near_branch_target
            if start <= target < prefix[-1].next_ip and target not in starts:
                break
            joins[target] = common(facts, joins[target]) if target in joins else facts.copy()
        elif mn == Mnemonic.CALL and a == OpKind.NEAR_BRANCH64 and ins.near_branch_target == init_meta:
            for r in VOLATILE:
                facts.pop(r, None)
        elif mn == Mnemonic.MOV and a == OpKind.MEMORY:
            ref = facts.get(reg_name(ins.memory_base))
            if (isinstance(ref, tuple) and _reg_size(ins.memory_base) == 8 and
                    ins.memory_displacement == 0 and ins.memory_index == IReg.NONE and
                    not ins.has_segment_prefix and MemorySizeExt.size(ins.memory_size) == 4 and
                    ((b in IMM_OPS and ins.immediate(1) == 0) or
                     (b == OpKind.REGISTER and _reg_size(ins.op1_register) == 4 and
                      facts.get(reg_name(ins.op1_register)) == 0))):
                sites[ins.ip] = ref
        elif mn in (Mnemonic.MOV, Mnemonic.LEA, Mnemonic.XOR) and a == OpKind.REGISTER:
            r = reg_name(ins.op0_register)
            width = _reg_size(ins.op0_register)
            if width not in (4, 8) or r == 'RSP':
                break
            value = None
            if mn == Mnemonic.MOV and b == OpKind.REGISTER:
                src = facts.get(reg_name(ins.op1_register))
                if width == 8 or src == 0:
                    value = src
            elif ((mn == Mnemonic.XOR and b == OpKind.REGISTER and ins.op0_register == ins.op1_register)
                  or (mn == Mnemonic.MOV and b in IMM_OPS and ins.immediate(1) == 0)):
                value = 0
            facts.pop(r, None)
            if value is not None:
                facts[r] = value
        elif not (mn in (Mnemonic.CMP, Mnemonic.TEST, Mnemonic.PUSH, Mnemonic.NOP, Mnemonic.ENDBR64)
                  or (mn == Mnemonic.SUB and ins.op0_register == IReg.RSP and b in IMM_OPS)):
            break
    return sites
