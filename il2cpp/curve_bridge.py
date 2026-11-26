"""Liveness of a curve update followed by heap callbacks and a proved join arm.

Only validate the intervening instructions. They are still lifted in place,
including their receiver reads, null checks, calls, and exceptional exits.
"""
from il2cpp.module_curve import _chain_spans, _dead_scratch, _float_literal, _update_window
from il2cpp.prelude import HAVE_ICED
from il2cpp.shared_action import _raises_on_null
from il2cpp.sret_copy import _own_field
from il2cpp.text import sdisp

if HAVE_ICED:
    from iced_x86 import Mnemonic as M, OpKind as K, Register as R, RegisterExt
    _GPRS = (R.RCX, R.RDX, R.R8, R.R9)
    _NONVOL = (R.RBX, R.RBP, R.RDI, R.RSI, R.R12, R.R13, R.R14, R.R15)
    _ZERO = ('zero',)
    _BOOL = ('bool',)


def _call_result(il, ins, gprs, floats):
    """A unique non-generic call whose complete Win64 signature is supplied
    by known heap references and initialized scalars (no stack arguments)."""
    ids = il.addr_candidates.get(ins.near_branch_target, ())
    if len(ids) != 1 or ids[0][0] != 'method' or not 0 <= ids[0][1] < len(il.meta.methods):
        return None
    m = il.meta.methods[ids[0][1]]
    pos = int(not m.is_static)
    if (m.addr != ins.near_branch_target or m.generic_container != -1 or m.flags & 0x40 or
            not 0 <= m.declaring < len(il.meta.typedefs) or il.meta.typedefs[m.declaring].generic_container != -1 or
            not 0 <= m.return_type < len(il.types) or not 0 <= m.param_count < len(_GPRS)-pos or
            (pos and gprs.get(R.RCX) != (0x12,m.declaring,0))):
        return None
    ps = il.meta.method_params(m)
    if len(ps) != m.param_count:
        return None
    for p in ps:
        if not 0 <= p.type < len(il.types):
            return None
        key = il._closed_type_key(il.types[p.type])
        if key == (2,0) and gprs.get(_GPRS[pos]) in (_ZERO,_BOOL):
            pass
        elif key != (0x0c,0) or R.XMM0+pos not in floats:
            return None
        pos += 1
    ret = il._closed_type_key(il.types[m.return_type])
    if gprs.get(_GPRS[pos]) == _ZERO and ret in ((1,0),(0x0c,0)):
        return ret
    return None


def _to_arm(lift, td, by_ip, start, saved, arms, snapshots):
    # The preceding call invalidated every volatile. Even nonvolatile
    # inputs must be freshly defined, except the already proved saved this.
    gprs = {saved: (0x12,td.index,0)}; floats = set(); ip = start
    for _ in range(96):
        if ip in arms:
            arm = arms[ip]
            owner = lift.il._nested_owner(arm.member[1][0])
            return arm if (arm.saved_this == saved and gprs.get(R.RCX) == (0x12,owner,0) and
                           gprs.get(R.RDX) == _ZERO) else None
        i = by_ip.get(ip)
        if i is None or i.has_segment_prefix or i.memory_index != R.NONE:
            return None
        dst, src = i.op0_register, i.op1_register
        if i.mnemonic == M.MOV and dst in _GPRS+_NONVOL and i.memory_base == saved:
            if dst == saved:
                return None
            field = _own_field(lift.il,td,sdisp(i.memory_displacement),8)
            key = lift.il._closed_type_key(field[1]) if field else None
            if not key or key[0] != 0x12 or key[-1] != 0:
                return None
            gprs[dst] = key
            if dst in _NONVOL:
                # Later callbacks may replace this field. A saved native
                # receiver must remain the original object at its next use.
                snapshots[i.ip] = (field,dst)
        elif i.mnemonic == M.MOV and dst in _GPRS and src in gprs:
            gprs[dst] = gprs[src]
        elif i.mnemonic == M.TEST and dst == src and gprs.get(dst,(None,))[0] == 0x12:
            null = by_ip.get(i.next_ip)
            if not null or null.mnemonic != M.JE or null.op0_kind != K.NEAR_BRANCH64 or not _raises_on_null(lift,null):
                return None
            ip = null.next_ip
            continue
        elif i.mnemonic == M.XOR and dst == src and dst in (R.ECX,R.EDX,R.R8D,R.R9D):
            gprs[RegisterExt.full_register(dst)] = _ZERO
        elif i.mnemonic == M.MOV and dst in (R.DL,R.R8L) and i.op1_kind == K.IMMEDIATE8 and i.immediate8 in (0,1):
            gprs[RegisterExt.full_register(dst)] = _BOOL  # no wider value is known
        elif i.mnemonic == M.MOVSS and RegisterExt.is_xmm(dst) and _float_literal(lift.il,i) is not None:
            floats.add(dst)
        elif i.mnemonic == M.XORPS and dst == src and RegisterExt.is_xmm(dst):
            floats.add(dst)
        elif i.mnemonic == M.MOVAPS and RegisterExt.is_xmm(dst) and src in floats:
            floats.add(dst)
        elif i.mnemonic == M.MULSS and dst in floats and src in floats:
            pass
        elif i.mnemonic == M.CALL and i.op0_kind == K.NEAR_BRANCH64:
            ret = _call_result(lift.il,i,gprs,floats)
            if ret is None:
                return None
            gprs = {r:v for r,v in gprs.items() if r in _NONVOL}
            floats = {r for r in floats if R.XMM6 <= r <= R.XMM15}
            if ret == (0x0c,0):
                floats.add(R.XMM0)
        else:
            return None
        ip = i.next_ip
    return None


def _receiver_before_store(lift, block, td, saved):
    if len(block.preds)!=1 or len(block.insns)<2:
        return None
    seq = lift._blocks[block.preds[0]].insns
    if len(seq)<4:
        return None
    load,store,test,null = seq[-4:]
    if (load.mnemonic != M.MOV or load.op0_register != R.RCX or load.memory_base != saved or
            store.mnemonic != M.MOVSS or store.op0_kind != K.MEMORY or store.memory_base != saved or
            any(i.has_segment_prefix or i.memory_index != R.NONE for i in (load,store)) or
            test.mnemonic != M.TEST or test.op0_register != R.RCX or test.op1_register != R.RCX or
            null.mnemonic != M.JE or null.op0_kind != K.NEAR_BRANCH64 or not _raises_on_null(lift,null) or
            any(a.next_ip!=b.ip for a,b in zip((load,store,test,null),(store,test,null,block.insns[0])))):
        return None
    field = _own_field(lift.il,td,sdisp(load.memory_displacement),8)
    distance = _own_field(lift.il,td,sdisp(store.memory_displacement),4)
    if field and lift.il._closed_type_key(field[1])==(0x12,field[1][0],0) and distance and lift.il._closed_type_key(distance[1])==(0x0c,0):
        return load.ip, (field,R.RCX)
    return None


def prefixes_before_join(lift, method, td, blocks, frame, arms):
    """Certify a prefix's scratch through the callbacks, the selected arm
    (which fully overwrites its outgoing argument), and its common tail."""
    plans, loads = {}, {}
    if not arms:
        return plans, loads
    by_ip = lift._module_tail_insns  # built by the successful join tail proof
    targets = {by_ip[ip].near_branch_target for ip in arms}
    for b in blocks:
        for j,ins in enumerate(b.insns):
            if (ins.mnemonic != M.CALL or ins.op0_kind != K.NEAR_BRANCH64 or
                    ins.near_branch_target not in targets or ins.ip in arms):
                continue
            plan = _update_window(lift,b,j,frame)
            if plan is None:
                continue
            for saved in {a.saved_this for a in arms.values()}:
                receiver = _receiver_before_store(lift,b,td,saved)
                if receiver is None:
                    continue
                snapshots = dict([receiver])
                arm = _to_arm(lift,td,by_ip,b.insns[plan.apply].next_ip,saved,arms,snapshots)
                if not arm:
                    continue
                spans = _chain_spans(plan,arm.plan)
                if spans and _dead_scratch(lift,arm.setter.next_ip,spans,frame,method=method,saved_this=saved):
                    plans[ins.ip] = plan
                    loads.update(snapshots)
                    break
    return plans, loads
