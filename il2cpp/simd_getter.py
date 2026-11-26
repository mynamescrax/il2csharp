"""Trace scratch XMM values back to two materialized struct returns.

This is a call-argument proof, not a rewrite of the arithmetic: nonvolatile
results, the scalar spill, and their later consumers still lift normally.
"""
from il2cpp.binary import PE
from il2cpp.expr import Expr, _R4_TY
from il2cpp.prelude import HAVE_ICED
from il2cpp.shared_getter import getter_alias
from il2cpp.sret_copy import _own_field
from il2cpp.text import reg_name, sdisp

if HAVE_ICED:
    from iced_x86 import FlowControl as FC, InstructionInfoFactory, Mnemonic as M, OpAccess, OpKind as K, Register as R, RegisterExt
    _INFO = InstructionInfoFactory()
    _WRITES = {OpAccess.WRITE, OpAccess.COND_WRITE, OpAccess.READ_WRITE, OpAccess.READ_COND_WRITE}


def _packed_return(i):
    return (i.mnemonic in (M.MOVAPS, M.MOVUPS) and RegisterExt.is_xmm(i.op0_register) and
            i.op1_kind == K.MEMORY and i.memory_base == R.RAX and i.memory_index == R.NONE and
            not i.memory_displacement and not i.has_segment_prefix)


def _scratch_inputs(seq, saved):
    """Starting after the second call: only the nonvolatile first snapshot
    is known. Admit one whole load of the new return; every register input
    must already be known, including lanes preserved by scalar operations."""
    known = {saved}
    seed = None
    for i in seq:
        dst, src = i.op0_register, i.op1_register
        if _packed_return(i):
            if seed is not None or dst == saved:
                return None
            seed = i
        elif (i.mnemonic in (M.MOVAPS, M.MOVUPS) and RegisterExt.is_xmm(dst) and
              i.op1_kind == K.REGISTER and src in known):
            pass
        elif (dst in known and i.op1_kind == K.REGISTER and src in known and
              (i.mnemonic in (M.MULSS, M.ADDSS, M.SUBSS) or
               (i.mnemonic == M.SHUFPS and i.op2_kind == K.IMMEDIATE8))):
            pass
        else:
            return None
        known.add(dst)
    if seed is not None and {R.XMM0, R.XMM1, R.XMM2, R.XMM3} <= known:
        return seed, known
    return None


def _float4(lift, call):
    il = lift.il
    if call.op0_kind != K.NEAR_BRANCH64:
        return None
    va = call.near_branch_target
    ids = il.addr_candidates.get(va, ())
    if len(ids) != 1 or ids[0][0] != 'method' or not 0 <= ids[0][1] < len(il.meta.methods):
        return None
    m = il.meta.methods[ids[0][1]]
    ty = il.types[m.return_type] if 0 <= m.return_type < len(il.types) else None
    if (m.addr != va or m.generic_container != -1 or not ty or ty[1] & (1 << 29) or
            il._type_enum(ty) != 0x11 or not 0 <= ty[0] < len(il.meta.typedefs) or not il.returns_sret(ty)):
        return None
    td = il.meta.typedefs[ty[0]]
    fields = il.instance_field_chain(td.index) or {}
    if (td.is_valuetype and td.generic_container == -1 and td.flags & 0x18 != 0x10 and
            il.value_type_size(td.index) == 16 and set(fields) == {16,20,24,28} and
            all(_own_field(il, td, off, 4) for off in fields) and
            all(0 <= ti < len(il.types) and il._closed_type_key(il.types[ti]) == (0x0c, 0) for _, ti in fields.values())):
        return ty
    return None


def keep_scalars(lift, seq):
    """Freeze nonvolatile computed low floats before the spill/reload. Do
    not bind just an XMM display string: later shuffles read its lane map."""
    regs = {reg_name(i.op0_register) for i in seq if i.mnemonic in (M.MULSS,M.ADDSS,M.SUBSS)
            and R.XMM6 <= i.op0_register <= R.XMM15}
    for reg in sorted(regs):
        e = dict.get(lift.regs,reg)
        if not e or e._unk or e.kind != 'float' or not e.ty or lift.il._type_enum(e.ty) != 0x0c:
            continue
        parts = getattr(e,'_parts',None)
        if not parts or parts[0][0] != 0 or parts[0][2:] != (0,4) or parts[0][1].text != e.text:
            continue
        name = lift.new_var()
        lift._var_types[name] = _R4_TY
        lift.emit(lift._cur_ip,'var %s = %s;' % (name,e.text),None)
        value = Expr(name,_R4_TY,'float')
        value._parts = [(0, Expr(name,_R4_TY,'float'), 0, 4), *parts[1:]]
        lift.regs[reg] = value


def snapshot_plans(lift, td, blocks, pads):
    """Per-method (fresh sret definitions, packed loads, receiver reloads).
    Require a single uninterrupted predecessor; never carry a scratch proof
    through an alternate entry, call, unknown memory operand or EH pad."""
    unique, loads, reloads = set(), {}, {}
    il = lift.il
    if pads or not isinstance(getattr(il,'bin',None), PE) or not il.bin.is64 or td.is_valuetype:
        return unique, loads, reloads
    for use in blocks:
        if len(use.preds) != 1 or len(use.insns) < 2:
            continue
        zero, getter = use.insns[:2]
        if (zero.mnemonic != M.XOR or zero.op0_register != R.EDX or zero.op1_register != R.EDX or
                getter.mnemonic != M.CALL or getter.op0_kind != K.NEAR_BRANCH64 or
                len(il.addr_candidates.get(getter.near_branch_target, ())) < 2):
            continue
        seq = blocks[use.preds[0]].insns
        if len(seq) < 8:
            continue
        spill, reload, test, null = seq[-4:]
        if (spill.mnemonic != M.MOVSS or spill.op0_kind != K.MEMORY or spill.memory_base not in (R.RSP,R.RBP) or
                spill.memory_index != R.NONE or not RegisterExt.is_xmm(spill.op1_register) or
                reload.mnemonic != M.MOV or reload.op0_register != R.RCX or
                reload.memory_base not in (R.RBX,R.RBP,R.RSI,R.RDI,R.R12,R.R13,R.R14,R.R15) or reload.memory_index != R.NONE or
                test.mnemonic != M.TEST or test.op0_register != R.RCX or test.op1_register != R.RCX or
                null.mnemonic != M.JE or null.next_ip != zero.ip or null.near_branch_target == zero.ip or zero.next_ip != getter.ip):
            continue
        pair = [j for j,i in enumerate(seq[:-4]) if i.mnemonic == M.CALL][-2:]
        if len(pair) != 2:
            continue
        left, right = pair
        if (any(a.next_ip != b.ip for a,b in zip(seq[left:], seq[left+1:])) or
                any(i.has_segment_prefix for i in seq[left:]) or not _float4(lift,seq[left]) or not _float4(lift,seq[right])):
            continue
        # Identify the read of the first echoed address before any RAX write;
        # the full packed register must survive up to and across call two.
        first = None
        for i in seq[left+1:right]:
            if first is None and _packed_return(i) and R.XMM6 <= i.op0_register <= R.XMM15:
                first = i
                continue
            live = first.op0_register if first is not None else R.RAX
            if i.flow_control != FC.NEXT or any(r.access in _WRITES and reg_name(r.register) == reg_name(live)
                                                for r in _INFO.info(i).used_registers()):
                break
        else:
            scratch = _scratch_inputs(seq[right+1:-4],first.op0_register) if first is not None else None
            if not scratch or spill.op1_register not in scratch[1]:
                continue
            field = _own_field(il, td, sdisp(reload.memory_displacement),8)
            if not field or il._type_enum(field[1]) != 0x12 or field[1][1] & (1<<29):
                continue
            alias = getter_alias(lift,getter.near_branch_target,field[1][0])
            if not alias or not alias[1]:
                continue
            producers = (seq[left].ip, seq[right].ip)
            unique.update(producers)
            reads = (first.ip, scratch[0].ip)
            loads.update(zip(reads, producers))
            reloads[reload.ip] = (getter.ip, reads, field)
    return unique, loads, reloads
