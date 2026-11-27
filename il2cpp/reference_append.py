"""Inlining a reference List<T>.Add before a guarded continuation.

Match against the registered public implementation: it supplies the exact
resize, exception and card-mark entries. Keep the item evaluation before
the receiver-field reload, and keep both paths into the continuation.
"""
import re

from il2cpp.array_origin import _graph,_definitions
from il2cpp.awaiter import _spec_entry
from il2cpp.generic_array import object_shared_entry
from il2cpp.closed_class_read import _class_entry
from il2cpp.closed_lookup import _receiver
from il2cpp.csharp import source_field_name
from il2cpp.equivalent_binary import _amd64
from il2cpp.expr import acc_get
from il2cpp.list_append import _diamond,_jump,_load,_mem,_plain,_raise_at,_rr,_sp
from il2cpp.names import safe_ident
from il2cpp.parent_lookup import _list_member
from il2cpp.prelude import HAVE_ICED
from il2cpp.shared_field import reference_field_at
from il2cpp.stack_local_frame import stack_local_frame
from il2cpp.text import reg_name,sdisp

if HAVE_ICED:
    from iced_x86 import Decoder,FlowControl as F,Mnemonic as M,OpKind as K,Register as R,RegisterExt


def _contract(lift,slot):
    il=lift.il;u=il.decode_slot(slot) or {};si=u.get('idx',-1)
    if u.get('kind')!=6 or not 0<=si<len(il.method_specs):return None
    mi,ci,gi=il.method_specs[si]
    if gi!=-1 or ci<0 or not 0<=mi<len(il.meta.methods):return None
    args=il._method_spec_type_args(ci)
    if not args or len(args)!=1 or not args[0]:return None
    elem=args[0];key=il._closed_type_key(elem)
    if key!=(0x12,elem[0],0) or not 0<=elem[0]<len(il.meta.typedefs) or il.meta.typedefs[elem[0]].generic_container!=-1:return None
    entry=_class_entry(il,si)
    listkey=_list_member(il,slot,entry,'Add',key) if entry else None
    if not listkey:return None
    lo,hi=il.function_extent(entry)
    if lo!=entry or not 0<hi-lo<=128:return None
    seq=list(Decoder(64,il.bin.read(lo,hi-lo) or b'',ip=lo))
    if len(seq)!=26 or not all(_plain(i) for i in seq):return None
    sp,inc,items,size,test,null,cmp,room,ctx1,ctx2,ctx3,restore,resize,plus,bump,check,fail,write,base,lea,back,barrier,nre,trap,ior,trap2=seq
    if (not _sp(sp,M.SUB,40) or not _mem(inc,M.INC,R.RCX,28,4) or not _load(items,M.MOV,R.R9,R.RCX,16,8) or
            not _load(size,M.MOVSXD,R.R10,R.RCX,24,4) or not _rr(test,M.TEST,R.R9,R.R9) or not _jump(null,M.JE,nre.ip) or
            not _load(cmp,M.CMP,R.R10D,R.R9,24,4) or not _jump(room,M.JB,plus.ip) or not _load(ctx1,M.MOV,R.RAX,R.R8,32,8) or
            not _load(ctx2,M.MOV,R.R8,R.RAX,192,8) or not _load(ctx3,M.MOV,R.R8,R.R8,112,8) or not _sp(restore,M.ADD,40) or
            resize.mnemonic!=M.JMP or resize.op0_kind!=K.NEAR_BRANCH64 or not il.bin.is_exec_va(resize.near_branch_target) or
            not _load(plus,M.LEA,R.EAX,R.R10,1,0) or not _mem(bump,M.MOV,R.RCX,24,4) or bump.op1_register!=R.EAX or
            not _load(check,M.CMP,R.R10D,R.R9,24,4) or not _jump(fail,M.JAE,ior.ip) or not _mem(write,M.MOV,R.R9,32,8,R.R10,8) or write.op1_register!=R.RDX or
            not _sp_add(base,R.R9,32) or not _mem(lea,M.LEA,R.R9,0,0,R.R10,8) or lea.op0_register!=R.RCX or not _sp(back,M.ADD,40) or
            barrier.mnemonic!=M.JMP or barrier.op0_kind!=K.NEAR_BRANCH64 or barrier.near_branch_target not in lift.rt_wbarrier or
            not nre.is_call_near or not ior.is_call_near or trap.mnemonic!=M.INT3 or trap2.mnemonic!=M.INT3):return None
    return listkey,key,resize.near_branch_target,barrier.near_branch_target,nre.near_branch_target,ior.near_branch_target


def _sp_add(i,r,n):return i.mnemonic==M.ADD and i.op0_register==r and i.op1_kind==K.IMMEDIATE8TO64 and i.immediate8to64==n


def _factory(il,by,pred,method,getter,prev,base,nre):
    # Do not trust a typed temp left in end_state by a modelled instruction:
    # every path has to carry the result of the same registered call in RAX.
    if len(prev.insns)<3:return False
    call,check,fail=prev.insns[-3:]
    if (not call.is_call_near or not _rr(check,M.TEST,R.RAX,R.RAX) or fail.mnemonic!=M.JE or not _raise_at(by,fail.near_branch_target,nre) or
            pred[check.ip]!=[call.ip] or pred[fail.ip]!=[check.ip] or
            _definitions(by,pred,method.addr,getter.ip,R.RCX)!={(call.ip,R.RAX)}):return False
    defs=_definitions(by,pred,method.addr,call.ip,R.R8)
    if len(defs)!=1:return False
    ip,r=defs.pop();slot=by[ip]
    if (r!=R.R8 or slot.mnemonic!=M.MOV or slot.op0_register!=R.R8 or slot.op1_kind!=K.MEMORY or
            slot.memory_base!=R.RIP or not _plain(slot)):return False
    usage=il.decode_slot(slot.ip_rel_memory_address) or {};si=usage.get('idx',-1)
    if usage.get('kind')!=6 or not 0<=si<len(il.method_specs):return False
    mi,ci,gi=il.method_specs[si]
    if ci!=-1 or gi<0 or not 0<=mi<len(il.meta.methods):return False
    m=il.meta.methods[mi];args=il._method_spec_type_args(gi);key=il._closed_type_key
    if (not m.is_static or m.param_count!=2 or m.generic_container<0 or not args or len(args)!=1 or not args[0] or
            key(args[0])!=key(base.ty) or key(il.candidate_return_type(('generic',si)))!=key(base.ty) or
            not 0<=m.return_type<len(il.types) or m.generic_container>=len(il.meta.generic_containers)):return False
    rt=il.types[m.return_type];own,n,ismethod,param=il.meta.generic_containers[m.generic_container]
    if (not rt or rt[0]!=param or rt[1]&(1<<29) or il._type_enum(rt)!=0x1e or (own,n,ismethod)!=(mi,1,1)):return False
    actual=_spec_entry(il,si,mi)
    if si not in il._awaiter_spec_indices[mi]:actual=object_shared_entry(il,mi)
    return actual==call.near_branch_target


def _continuation(lift,method,blocks,join,frame,selfreg,by,pred):
    """The only live inputs after the diamond are a saved byte and this.
    A void, nullary method may run before the common restore and return."""
    il=lift.il;s=join.insns
    if len(s)!=2 or len(join.succs)!=2 or join.stmts:return False
    test,skip=s;reg=test.op0_register
    if (reg not in (R.BL,R.BPL,R.SIL,R.DIL,R.R12L,R.R13L,R.R14L,R.R15L) or RegisterExt.full_register(reg)==selfreg or
            not _rr(test,M.TEST,reg,reg) or skip.mnemonic not in (M.JE,M.JNE) or not all(_plain(i) for i in s)):return False
    run,end=sorted((blocks[i] for i in join.succs),key=lambda b:b.bid)
    defs=_definitions(by,pred,method.addr,test.ip,RegisterExt.full_register(reg));ps=il.meta.method_params(method)
    if len(defs)!=1 or len(ps)!=1 or not 0<=ps[0].type<len(il.types) or il._closed_type_key(il.types[ps[0].type])!=(2,0):return False
    pos,r=defs.pop();park=by[pos]
    if (park.mnemonic!=M.MOVZX or not RegisterExt.is_gpr32(park.op0_register) or RegisterExt.full_register(park.op0_register)!=r or
            park.op1_register!=R.DL or pred[method.addr]):return False
    # DL is the instance method's first by-value argument, before any call
    # or write to RDX, not an arbitrary low byte parked in a saved register.
    from il2cpp.closed_lookup import _INFO,_WRITES
    while pos!=method.addr:
        if len(pred[pos])!=1:return False
        i=by[pred[pos][0]]
        if i.next_ip!=pos or i.ip>=pos or i.flow_control!=F.NEXT or any(u.access in _WRITES and RegisterExt.full_register(u.register)==R.RDX for u in _INFO.info(i).used_registers()):return False
        pos=i.ip
    if (run.bid!=join.bid+1 or end.bid!=run.bid+1 or run.preds!=[join.bid] or run.succs!=[end.bid] or
            end.succs or end.term!=('ret',) or end.stmts or end.ret or len(run.insns)!=3):return False
    zero,recv,call=run.insns
    if (not _rr(zero,M.XOR,R.EDX,R.EDX) or not _rr(recv,M.MOV,R.RCX,selfreg) or not call.is_call_near or
            skip.near_branch_target!=end.insns[0].ip or not all(_plain(i) for i in run.insns)):return False
    ids=il.addr_candidates.get(call.near_branch_target,())
    if len(ids)!=1 or ids[0][0]!='method':return False
    md=il.meta.methods[ids[0][1]]
    if (md.declaring!=method.declaring or md.is_static or md.flags&0x40 or md.param_count or md.addr!=call.near_branch_target or
            md.generic_container!=-1 or not 0<=md.return_type<len(il.types) or il._closed_type_key(il.types[md.return_type])!=(1,0)):return False
    # stack_local_frame independently verifies every epilogue against unwind.
    for i in end.insns:
        if (i.mnemonic in (M.RET,M.POP) or _sp_add(i,R.RSP,frame[0]) or i.mnemonic==M.MOV and i.memory_base==R.RSP and
                i.memory_index==R.NONE and (sdisp(i.memory_displacement),8) in frame[2] and RegisterExt.is_gpr64(i.op0_register)):continue
        return False
    return True


def fold_reference_append(dec,method,td,blocks,pads):
    lift=dec.L;il=lift.il;key=il._closed_type_key
    if (not HAVE_ICED or pads or not _amd64(getattr(il,'bin',None)) or il.meta.version!=31 or method.is_static or td.is_valuetype or
            method.generic_container!=-1 or td.generic_container!=-1 or not 0<=method.return_type<len(il.types) or key(il.types[method.return_type])!=(1,0)):return
    for h in blocks[:-8]:
        if len(h.insns)!=7 or h.insns[2].mnemonic!=M.CALL or h.insns[3].op0_register!=R.R9 or h.stmts or len(h.preds)!=1:continue
        region=_diamond(blocks,h)
        if not region:continue
        v,c,s,f,w=region;j=blocks[w.bid+1]
        if ([len(b.insns) for b in region]!=[6,2,7,4,5] or s.succs!=w.succs or w.succs!=[j.bid] or set(j.preds)!={s.bid,w.bid}):continue
        zero,recv,getter,field,item,test,null=h.insns;sr=field.memory_base
        if (not _rr(zero,M.XOR,R.EDX,R.EDX) or not _rr(recv,M.MOV,R.RCX,R.RAX) or not getter.is_call_near or
                sr not in (R.RBX,R.RDI,R.RSI) or not _load(field,M.MOV,R.R9,sr,field.memory_displacement,8) or
                not _rr(item,M.MOV,R.R10,R.RAX) or not _rr(test,M.TEST,R.R9,R.R9) or null.mnemonic!=M.JE):continue
        slot,inc,items,size,test2,null2=v.insns;cmp,room=c.insns;ctx1,arg,rcx,ctx2,ctx3,resize,leave=s.insns
        plus,bump,check,fail=f.insns;write,lea,add,arg2,wb=w.insns
        if (slot.mnemonic!=M.MOV or slot.op0_register!=R.RAX or slot.memory_base!=R.RIP or not _mem(inc,M.INC,R.R9,28,4) or
                not _load(items,M.MOV,R.RCX,R.R9,16,8) or not _load(size,M.MOVSXD,R.RDX,R.R9,24,4) or not _rr(test2,M.TEST,R.RCX,R.RCX) or
                not _jump(null2,M.JE,null.near_branch_target) or not _load(cmp,M.CMP,R.EDX,R.RCX,24,4) or not _jump(room,M.JB,plus.ip) or
                not _load(ctx1,M.MOV,R.RAX,R.RAX,32,8) or not _rr(arg,M.MOV,R.RDX,R.R10) or not _rr(rcx,M.MOV,R.RCX,R.R9) or
                not _load(ctx2,M.MOV,R.R8,R.RAX,192,8) or not _load(ctx3,M.MOV,R.R8,R.R8,112,8) or not _jump(leave,M.JMP,j.insns[0].ip) or
                not _load(plus,M.LEA,R.EAX,R.RDX,1,0) or not _mem(bump,M.MOV,R.R9,24,4) or bump.op1_register!=R.EAX or
                not _load(check,M.CMP,R.EDX,R.RCX,24,4) or fail.mnemonic!=M.JAE or not _mem(write,M.MOV,R.RCX,32,8,R.RDX,8) or
                write.op1_register!=R.R10 or not _mem(lea,M.LEA,R.RCX,0,0,R.RDX,8) or lea.op0_register!=R.RCX or
                not _sp_add(add,R.RCX,32) or not _rr(arg2,M.MOV,R.RDX,R.R10)):continue
        contract=_contract(lift,slot.ip_rel_memory_address)
        if not contract:continue
        lk,ek,slow,barrier,nre,ior=contract
        if not _jump(resize,M.CALL,slow) or not _jump(wb,M.CALL,barrier):continue
        seq=[i for b in blocks for i in b.insns];by={i.ip:i for i in seq}
        if not _raise_at(by,null.near_branch_target,nre) or not _raise_at(by,fail.near_branch_target,ior):continue
        graph=_graph(il,seq);frame=stack_local_frame(lift,method,blocks,pads)
        if not graph or not frame or not _continuation(lift,method,blocks,j,frame,sr,by,graph[0]):continue
        pred,_=graph;part=h.insns+[x for b in region for x in b.insns]
        if not all(_plain(i) for i in part) or not _receiver(il,method,by,pred,field.ip,td.index,initial=sr,this_only=True):continue
        # Raw predecessors retain the null and bounds edges pruned from the
        # structurer. Only the documented fork may enter the fast path.
        if any(pred[i.ip]!=[room.ip if i.ip==plus.ip else a.ip] for a,i in zip(part,part[1:])):continue
        removed={h.bid,*(b.bid for b in region)}
        if any(cps for (a,z),cps in dec.phi_copies.items() if a in removed):continue
        row=reference_field_at(il,td.index,sdisp(field.memory_displacement),constructed=True)
        prev=blocks[h.preds[0]];base=(prev.end_state or {}).get('RAX');es=h.end_state or {};val=es.get('R10');lst=es.get('R9')
        if pred[zero.ip]!=[prev.insns[-1].ip] or set(pred[j.insns[0].ip])!={leave.ip,wb.ip}:continue
        ids=il.addr_candidates.get(getter.near_branch_target,())
        if len(ids)!=1 or ids[0][0]!='method' or not base or not base.ty or not re.fullmatch(r't\d+',base.text) or not _factory(il,by,pred,method,getter,prev,base,nre):continue
        md=il.meta.methods[ids[0][1]];prop=lift._accessor_prop(md.index)
        if (not row or row[0]!=td.index or key(row[2])!=lk or not prop or prop[0]!='get' or prop[2] or md.param_count or md.is_static or md.flags&0x40 or
                md.addr!=getter.near_branch_target or md.flags&7!=6 or md.declaring!=base.ty[0] or key(base.ty)!=(0x12,md.declaring,0) or
                not 0<=md.return_type<len(il.types) or key(il.types[md.return_type])!=ek or not val or key(val.ty)!=ek or val is not es.get('RAX') or
                val.text!=base.text+'.'+prop[1] or not lst or key(lst.ty)!=lk or lst.text!='this.'+safe_ident(source_field_name(il,row[1]))):continue
        tmp=lift.new_var();lift._var_types[tmp]=val.ty
        h.stmts[:]=[f'var {tmp} = {acc_get(val.text)};',f'{lst.text}.Add({tmp});']
        h.succs=[j.bid];h.term=('jmp',j.bid);h.cond=h.ret=None;v.preds.remove(h.bid);j.preds[:]=[h.bid]
        return
