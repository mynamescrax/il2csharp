"""Prove the module and the edited curve independently on both edges of a setter."""
from typing import NamedTuple

from il2cpp.expr import acc_get
from il2cpp.module_curve import _dead_scratch, _probe_preserves_size, _window
from il2cpp.module_getter import _accessor
from il2cpp.prelude import HAVE_ICED
from il2cpp.shared_action import _raises_on_null
from il2cpp.sret_copy import _own_field
from il2cpp.text import sdisp

if HAVE_ICED:
    from iced_x86 import (FlowControl as F, InstructionInfoFactory, Mnemonic as M,
                          OpAccess, OpKind as K, Register as R, RegisterExt)
    _INFO = InstructionInfoFactory()
    _WRITES = {OpAccess.WRITE, OpAccess.READ_WRITE, OpAccess.COND_WRITE, OpAccess.READ_COND_WRITE}


class _Arm(NamedTuple):
    producer_ip: int
    last: int
    plan: object
    member: tuple
    edit: object
    setter: object
    join_end: int
    saved_this: int


def _saved_this(lift, blocks, reg):
    def writes(i, r):
        return any(u.access in _WRITES and RegisterExt.full_register(u.register) == r for u in _INFO.info(i).used_registers())

    entry = blocks[0].insns
    save = next((n for n,i in enumerate(entry) if writes(i,reg)), None)
    if save is None or entry[save].mnemonic != M.MOV or entry[save].op0_register != reg or entry[save].op1_register != R.RCX:
        return False
    for i in entry[:save]:
        if i.mnemonic == M.CALL and i.op0_kind == K.NEAR_BRANCH64 and _probe_preserves_size(lift,i.near_branch_target):
            continue
        if i.flow_control != F.NEXT or writes(i,R.RCX):
            return False
    for b in blocks:
        for n,i in enumerate(b.insns):
            if b is blocks[0] and n <= save:
                continue
            if writes(i,reg):
                # probed_frame already established that the POPs belong to a
                # terminal epilogue; never trust a restored register on reentry.
                if (i.mnemonic != M.POP or i.op0_register != reg or b.insns[-1].mnemonic != M.RET or
                        any(x.mnemonic != M.POP for x in b.insns[n+1:-1])):
                    return False
    return True


def _arm(lift, b, join, frame, td):
    if b.succs != [join.bid] or len(b.preds) != 1 or len(b.insns) < 4:
        return None
    seq = b.insns
    # Concatenate only the executed edge. Neither a branch to an interior
    # instruction nor another effect between the lane loads and stores counts.
    if seq[-1].mnemonic == M.JMP and seq[-1].op0_kind == K.NEAR_BRANCH64 and seq[-1].near_branch_target == join.insns[0].ip:
        if seq[-2].next_ip != seq[-1].ip:
            return None
        seq = seq[:-1]
    elif seq[-1].flow_control != F.NEXT or seq[-1].next_ip != join.insns[0].ip:
        return None
    zero, producer = seq[:2]
    if (zero.mnemonic != M.XOR or zero.op0_register != R.EDX or zero.op1_register != R.EDX or
            zero.next_ip != producer.ip or producer.mnemonic != M.CALL or producer.op0_kind != K.NEAR_BRANCH64):
        return None
    pred = lift._blocks[b.preds[0]].insns
    if len(pred) < 3:
        return None
    load,test,null = pred[-3:]; reg = load.memory_base
    if (load.mnemonic != M.MOV or load.op0_register != R.RCX or load.op1_kind != K.MEMORY or
            reg not in (R.RBX,R.RSI,R.RDI,R.R12,R.R13,R.R14,R.R15) or load.memory_index != R.NONE or load.has_segment_prefix or
            test.mnemonic != M.TEST or test.op0_register != R.RCX or test.op1_register != R.RCX or
            null.mnemonic != M.JE or null.op0_kind != K.NEAR_BRANCH64 or null.near_branch_target == null.next_ip or
            load.next_ip != test.ip or test.next_ip != null.ip or null.next_ip != zero.ip or not _raises_on_null(lift,null)):
        return None
    field = _own_field(lift.il,td,sdisp(load.memory_displacement),8)
    if not field or lift.il._closed_type_key(field[1]) != (0x12,field[1][0],0):
        return None
    combined = seq + join.insns[:8]
    plan = _window(lift,combined,1,frame,edge=(seq[-1].ip,join.insns[0].ip))
    if not plan or not (plan.edit < len(seq) <= plan.apply):
        return None
    ids = lift.il.addr_candidates[plan.getter.near_branch_target]
    owner = lift.meta.methods[ids[0][1]].declaring
    member = _accessor(lift,producer.near_branch_target,field[1][0],owner)
    if member:
        # The field read in the preceding null guard has no intervening
        # user code before the call. Preserve both it and the getter from CSE.
        text = acc_get(acc_get(field[0])+'.'+member[0])+' /* shared getter */'
        return _Arm(producer.ip,len(seq)-1,plan,(text,member[1]),combined[plan.edit],combined[plan.apply],plan.apply-len(seq),reg)
    return None


def joined_updates(lift, method, td, blocks, frame):
    """Only distribute the common setter when *every* incoming edge is
    proved. No managed work runs between an arm's last load and the call."""
    arms, consumed, saved = {}, {}, {}
    if not frame or method.is_static or td.is_valuetype or lift.il._closed_type_key(lift.il.types[method.return_type]) != (1,0):
        return arms,consumed
    for join in blocks:
        if (len(join.preds) != 2 or len(set(join.preds)) != 2 or not join.insns or
                join.insns[0].mnemonic != M.XOR or join.insns[0].op0_register != R.R8D):
            continue
        a,b = (_arm(lift,blocks[k],join,frame,td) for k in join.preds)
        if not a or not b or a.join_end != b.join_end or a.saved_this != b.saved_this or a.producer_ip == b.producer_ip:
            continue
        end, reg = a.join_end, a.saved_this
        if reg not in saved:
            saved[reg] = _saved_this(lift,blocks,reg)
        if not saved[reg]:
            continue
        spans = set(a.plan.spans) | set(b.plan.spans)
        if not _dead_scratch(lift,join.insns[end].next_ip,spans,frame,method=method,saved_this=reg):
            continue
        arms[a.producer_ip] = a
        arms[b.producer_ip] = b
        consumed[join.insns[0].ip] = end
    return arms, consumed
