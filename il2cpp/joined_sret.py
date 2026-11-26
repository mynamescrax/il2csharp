"""A join of private Win64 sret buffers, followed by one typed struct read.
Only the destination address differs. Normalize its edge definitions before
phi construction; keep the actual getter, null check and consumer in place.
"""
from il2cpp.copied_getter import _copies_prefix, _prefix_getter, _sp_offset
from il2cpp.expr import Expr
from il2cpp.module_curve import fixed_frame
from il2cpp.prelude import HAVE_ICED
from il2cpp.shared_action import _raises_on_null

if HAVE_ICED:
    from iced_x86 import FlowControl as F, InstructionInfoFactory, MemorySizeExt, Mnemonic as M, OpKind as K, Register as R, RegisterExt
    _INFO=InstructionInfoFactory()
    _ARG=(R.RCX,R.RDX,R.R8,R.R9)


def _rr(i,m,r,s):return i.mnemonic==m and i.op0_register==r and i.op1_register==s


def _lea(i,r):return i.mnemonic==M.LEA and i.op0_register==r and i.memory_index==R.NONE and not i.has_segment_prefix


def _unique(il,call):
    if call.mnemonic!=M.CALL or call.op0_kind!=K.NEAR_BRANCH64:return None
    ids=il.addr_candidates.get(call.near_branch_target,())
    if len(ids)==1 and ids[0][0]=='method' and 0<=ids[0][1]<len(il.meta.methods):
        md=il.meta.methods[ids[0][1]]
        if md.addr==call.near_branch_target and md.generic_container<0:return md


def _borrow(il,b,j):
    """Next direct call receiving this unmodified argument register. Do not
    confuse a pointer copied somewhere else with a bounded typed borrow."""
    reg=b.insns[j].op0_register
    if reg not in _ARG:return None
    for i in b.insns[j+1:]:
        if i.mnemonic==M.CALL:return i if i.op0_kind==K.NEAR_BRANCH64 else None
        if i.flow_control!=F.NEXT or any(RegisterExt.full_register(u.register)==reg for u in _INFO.info(i).used_registers()):return None


def _out_owner(il,md,reg):
    if not md or not md.is_static or not 0<=md.return_type<len(il.types) or il._closed_type_key(il.types[md.return_type])!=(2,0):return None
    ps=il.meta.method_params(md);k=_ARG.index(reg)
    if len(ps)!=md.param_count or not k<len(ps) or not 0<=ps[k].type<len(il.types):return None
    ty=il.types[ps[k].type];owner=ty[0]
    if (not ty[1]&2 or il._closed_type_key(ty)!=(0x11,owner,1) or not 0<=owner<len(il.meta.typedefs)):return None
    td=il.meta.typedefs[owner]
    if td.is_valuetype and td.generic_container==-1:return td


def _consumer(lift,b,use):
    """The echoed address is read as 8+4 bytes before a by-value setter.
    It is never returned or compared to either caller's physical address."""
    if len(b.insns)!=6 or len(use.insns)<8 or use.preds!=[b.bid]:return None
    field,src,zero,call,test,null=b.insns;recv=field.op0_register
    if (field.mnemonic!=M.MOV or field.op1_kind!=K.MEMORY or recv not in (R.RBX,R.RSI,R.RDI,R.R12,R.R13,R.R14,R.R15) or
            field.memory_base in (R.RCX,R.RSP,R.NONE) or not _lea(src,R.RDX) or src.memory_base!=R.RBP or
            not _rr(zero,M.XOR,R.R8D,R.R8D) or call.mnemonic!=M.CALL or call.op0_kind!=K.NEAR_BRANCH64 or
            not _copies_prefix(lift.il,call.near_branch_target) or not _rr(test,M.TEST,recv,recv) or null.mnemonic!=M.JE or
            not _raises_on_null(lift,null) or use.insns[0].ip!=null.next_ip):return None
    xy,arg,z,hidden,receiver,lo,hi,setter=use.insns[:8]
    if any(i.has_segment_prefix or i.has_lock_prefix or i.memory_index!=R.NONE for i in b.insns+use.insns[:8]):return None
    if (xy.mnemonic!=M.MOVSD or xy.memory_base!=R.RAX or xy.memory_displacement or not RegisterExt.is_xmm(xy.op0_register) or
            not _lea(arg,R.RDX) or arg.memory_base!=R.RSP or z.mnemonic!=M.MOV or z.op0_register!=R.EAX or z.memory_base!=R.RAX or
            z.memory_displacement!=8 or not _rr(hidden,M.XOR,R.R8D,R.R8D) or not _rr(receiver,M.MOV,R.RCX,recv) or
            lo.mnemonic!=M.MOVSD or lo.op1_register!=xy.op0_register or lo.memory_base!=R.RSP or lo.memory_displacement!=arg.memory_displacement or
            hi.mnemonic!=M.MOV or hi.op1_register!=R.EAX or hi.memory_base!=R.RSP or hi.memory_displacement!=arg.memory_displacement+8):return None
    md=_unique(lift.il,setter);prop=lift._accessor_prop(md.index) if md else None
    if not prop or prop[0]!='set' or prop[2] or md.is_static or md.param_count!=1:return None
    ps=lift.il.meta.method_params(md)
    if len(ps)==1 and 0<=ps[0].type<len(lift.il.types):return lift.il._closed_type_key(lift.il.types[ps[0].type])


def _edge_defs(blocks,pred,join):
    arms=[]
    for p in pred[join.bid]:
        b=blocks[p];seq=b.insns
        if seq[-1].mnemonic==M.JMP and seq[-1].op0_kind==K.NEAR_BRANCH64 and seq[-1].near_branch_target==join.insns[0].ip:seq=seq[:-1]
        elif seq[-1].flow_control!=F.NEXT or seq[-1].next_ip!=join.insns[0].ip:return None
        if not seq or not _lea(seq[-1],R.RCX) or seq[-1].memory_base!=R.RBP:return None
        arms.append(seq[-1])
    return arms if len(arms)>1 else None


def _predecessors(blocks):
    # Structuring prunes metadata/null edges. Rebuild native predecessors
    # here; only resolved jump tables may contribute indirect destinations.
    starts={b.insns[0].ip:b.bid for b in blocks};pred=[set() for b in blocks]
    for b in blocks:
        i=b.insns[-1];fc=i.flow_control
        if fc==F.INDIRECT_BRANCH:
            if not b.term or b.term[0]!='switch' or not b.succs:return None
            for k in b.succs:pred[k].add(b.bid)
        if fc in (F.CONDITIONAL_BRANCH,F.UNCONDITIONAL_BRANCH):
            if i.op0_kind!=K.NEAR_BRANCH64 or i.near_branch_target not in starts:return None
            pred[starts[i.near_branch_target]].add(b.bid)
        if fc in (F.NEXT,F.CONDITIONAL_BRANCH,F.CALL,F.INDIRECT_CALL) and i.next_ip in starts:pred[starts[i.next_ip]].add(b.bid)
    return pred


def _dominated(pred,site,producer):
    work=[site];seen=set();reached=False
    while work:
        k=work.pop()
        if k==producer:reached=True;continue
        if k in seen:continue
        if not k or not pred[k]:return False
        seen.add(k);work.extend(pred[k]-seen)
    return reached


def _success(prod,origin):
    if len(prod.insns)<3 or prod.insns[-3].ip!=origin.ip:return None
    test,branch=prod.insns[-2:]
    if not _rr(test,M.TEST,R.AL,R.AL) or branch.op0_kind!=K.NEAR_BRANCH64:return None
    if branch.mnemonic==M.JNE:return branch.near_branch_target
    if branch.mnemonic==M.JE:return branch.next_ip


def _closed_tail(lift,method,blocks,pred,use):
    """After the setter, only restore/return, heap calls with register-only
    signatures, and direct branches. Never transport a frame address out
    of the method or keep using the earlier sret/argument pointers."""
    if not 0<=method.return_type<len(lift.il.types) or lift.il._closed_type_key(lift.il.types[method.return_type])!=(1,0):return False
    succ=[[] for _ in blocks]
    for j,ps in enumerate(pred):
        for k in ps:succ[k].append(j)
    work=[use.bid];seen=set()
    while work:
        k=work.pop()
        if k in seen:continue
        seen.add(k)
        if len(seen)>32:return False
        b=blocks[k]
        for i in (b.insns[8:] if b is use else b.insns):
            if i.mnemonic==M.LEA or i.has_segment_prefix or i.flow_control in (F.INDIRECT_BRANCH,F.INDIRECT_CALL):return False
            if i.mnemonic==M.CALL:
                md=_unique(lift.il,i)
                if md:
                    if md.is_static or md.param_count>1 or not 0<=md.return_type<len(lift.il.types) or lift.il.returns_sret(lift.il.types[md.return_type]):return False
                    if any(not 0<=p.type<len(lift.il.types) or lift.il._closed_type_key(lift.il.types[p.type])!=(2,0) for p in lift.meta.method_params(md)):return False
                elif not lift._named_raise_throw(i.near_branch_target,lift._call_name(i.near_branch_target)):return False
        if use.bid in succ[k]:return False
        work.extend(succ[k])
    return True


def joined_srets(lift,method,blocks,pads):
    plans={};copies={};getters={};result=plans,copies,getters;il=lift.il
    if not HAVE_ICED or pads:return result
    sites=[b for b in blocks[:-1] if len(b.preds)>1 and len(b.insns)==6 and b.insns[3].mnemonic==M.CALL and _lea(b.insns[1],R.RDX)]
    sites=[(b,rt) for b in sites if (rt:=_consumer(lift,b,blocks[b.bid+1]))]
    if not sites:return result
    frame=fixed_frame(lift,method,blocks,pads,immediate=False,extended_saves=True) or fixed_frame(lift,method,blocks,pads,immediate=True,extended_saves=True)
    if not frame:return result
    bias,limit,_=frame;pred=_predecessors(blocks)
    if pred is None:return result
    accesses=[]
    for b in blocks:
        for j,i in enumerate(b.insns):
            if i.op1_register in (R.RSP,R.RBP) or i.memory_index in (R.RSP,R.RBP):return result
            if i.memory_base not in (R.RSP,R.RBP):continue
            off=_sp_offset(i,bias)
            if off is None:return result
            accesses.append((off,1 if i.mnemonic==M.LEA else MemorySizeExt.size(i.memory_size),b,j,i))
    starts={blk.insns[0].ip:blk.bid for blk in blocks}
    for b,rt in sites:
        arms=_edge_defs(blocks,pred,b)
        if not arms or pred[b.bid+1]!={b.bid} or not _closed_tail(lift,method,blocks,pred,blocks[b.bid+1]):continue
        call=b.insns[3];home=_sp_offset(b.insns[1],bias);dest=[_sp_offset(i,bias) for i in arms]
        if None in dest or home is None or not all(32<=off<=limit-12 for off in dest):continue
        if len(set(dest))!=len(dest) or any(x<y+12 for y,x in zip(sorted(dest),sorted(dest)[1:])):continue
        arm_ips={x.ip for x in arms}
        if any(any(a<off+12 and a+n>off for off in dest) and i.ip not in arm_ips for a,n,_,_,i in accesses):continue
        producers=[];readers=[]
        for a,_,blk,j,i in accesses:
            if a!=home or i.mnemonic!=M.LEA:continue
            c=_borrow(il,blk,j);md=_unique(il,c) if c else None
            td=_out_owner(il,md,i.op0_register) if c else None
            if td:producers.append((blk,c,td))
            else:readers.append((i,c,md))
        if len(producers)!=1:continue
        prod,origin,owner=producers[0];width=il.value_type_size(owner.index)
        ok=starts.get(_success(prod,origin))
        if not width or not 32<=home<=limit-width or ok is None or pred[ok]!={prod.bid} or not _dominated(pred,b.bid,ok):continue
        if any(not c or not (i.op0_register==R.RCX and md and md.declaring==owner.index and not md.is_static and not md.param_count and
                              lift._accessor_prop(md.index) or i.op0_register==R.RDX and _copies_prefix(il,c.near_branch_target) and
                              _prefix_getter(lift,c.near_branch_target,owner,'value')) for i,c,md in readers):continue
        if any(a<home+width and a+n>home and (i.mnemonic==M.LEA and a!=home or i.mnemonic!=M.LEA and
               (i.ip>=origin.ip or i.op0_kind!=K.MEMORY or a<home or a+n>home+width)) for a,n,_,_,i in accesses):continue
        getter=_prefix_getter(lift,call.near_branch_target,owner,'value')
        if not getter or il._closed_type_key(il.types[il.meta.methods[getter[0]].return_type])!=rt:continue
        # These addresses occur only at the ends of the proved input edges.
        # Either private home can stand for their common result, as RAX is
        # the only observed pointer, and its entire value is copied out.
        canonical=min(arms,key=lambda x:x.ip).memory_displacement
        for i in arms:plans[i.ip]=canonical
        copies[blocks[b.bid+1].insns[0].ip]=rt
        getters[call.ip]=getter[0]
    return result


def copied_argument(lift,store,echo):
    """One by-value parameter, copied from the materialized getter result.
    Record the complete tile (not the first float) and pass that value."""
    offset=store.memory_displacement;value=Expr(echo.text[1:],echo.ty,'obj');slot=lift.slot_var(offset)
    lift._kill_stale(slot)
    lift.emit(store.ip,f'{slot} = {value.text};',None)
    start=lift.rsp_delta+offset
    for a,old in lift.stack_map.items():
        if start<=a<start+12:lift.stack_values.pop(old,None)
    lift._stack_store(start,12,value);lift.stack_values[slot]=value
    # The setter consumes a by-value struct, not a mutable ref to the
    # outgoing argument area. The bytes there are exactly this snapshot.
    lift.regs['RDX']=Expr(echo.text,echo.ty,'ptr')
