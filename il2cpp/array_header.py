"""A null-checked SZARRAY result followed by a full-width emptiness test."""
from il2cpp.array_origin import _definitions,_graph
from il2cpp.equivalent_binary import _amd64
from il2cpp.prelude import HAVE_ICED
from il2cpp.saved_ref import reference_vector

if HAVE_ICED:
    from iced_x86 import MemorySizeExt, Mnemonic as M, OpKind as K, Register as R, RegisterExt


def header_sites(lift,method,blocks,pads):
    il=lift.il;reads={};calls={}
    if not HAVE_ICED or pads or not _amd64(getattr(il,'bin',None)) or il.meta.version!=31:return reads,calls
    candidates=[]
    for b in blocks:
        if len(b.insns)<3:continue
        call,test,null=b.insns[-3:]
        if (call.mnemonic!=M.CALL or call.op0_kind!=K.NEAR_BRANCH64 or test.mnemonic!=M.TEST or test.op0_register!=R.RAX or
                test.op1_register!=R.RAX or null.mnemonic!=M.JE or null.op0_kind!=K.NEAR_BRANCH64):continue
        ids=il.addr_candidates.get(call.near_branch_target,())
        if len(ids)!=1 or ids[0][0]!='method' or not 0<=ids[0][1]<len(il.meta.methods):continue
        m=il.meta.methods[ids[0][1]]
        if (not m.is_static or m.generic_container!=-1 or m.addr!=call.near_branch_target or m.flags&(0x40|0x800) or
                not 0<=m.declaring<len(il.meta.typedefs) or il.meta.typedefs[m.declaring].generic_container!=-1 or
                not 0<=m.return_type<len(il.types) or not reference_vector(il,il.types[m.return_type])):continue
        candidates.append((call,test,null,m.index))
    if not candidates:return reads,calls
    seq=[i for b in blocks for i in b.insns];by={i.ip:i for i in seq}
    if seq[0].ip!=method.addr:return reads,calls
    windows=[]
    for call,test,null,mi in candidates:
        cmp=by.get(null.next_ip);throw=by.get(null.near_branch_target);branch=by.get(cmp.next_ip) if cmp else None
        if (not throw or throw.mnemonic!=M.CALL or throw.op0_kind!=K.NEAR_BRANCH64 or
                lift._named_raise_throw(throw.near_branch_target,lift._call_name(throw.near_branch_target))!='System.NullReferenceException' or
                not cmp or not branch or branch.mnemonic not in (M.JE,M.JNE) or cmp.mnemonic!=M.CMP or cmp.op0_kind!=K.MEMORY or
                cmp.memory_base!=R.RAX or cmp.memory_index!=R.NONE or cmp.memory_displacement!=24 or MemorySizeExt.size(cmp.memory_size)!=8 or
                cmp.has_segment_prefix or cmp.has_lock_prefix or not RegisterExt.is_gpr64(cmp.op1_register)):continue
        windows.append(((call,test,null,cmp,branch),mi))
    if not windows:return reads,calls
    slots={b.insns[-1].ip:tuple(b.switch_targets) for b in blocks if b.insns and getattr(b,'switch_targets',None)}
    graph=_graph(il,seq,allow_tail=True,runtime_tails=lift.rt_wbarrier,chained=True,switch_slots=slots)
    if not graph:return reads,calls
    pred,_=graph
    for w,mi in windows:
        if any(a.next_ip!=b.ip or pred[b.ip]!=[a.ip] for a,b in zip(w,w[1:])):continue
        cmp=w[-2];defs=_definitions(by,pred,method.addr,cmp.ip,cmp.op1_register)
        if not defs:continue
        if all(by[p].mnemonic==M.XOR and by[p].op0_register==by[p].op1_register and RegisterExt.full_register(by[p].op0_register)==reg and
               (RegisterExt.is_gpr32(by[p].op0_register) or RegisterExt.is_gpr64(by[p].op0_register)) for p,reg in defs):
            calls[w[0].ip]=('method',mi);reads[cmp.ip]=w[0].ip
    return reads,calls
