"""Two reference-to-sret accessor chains reached through distinct loads of
the same mutable field. A property spelled twice need not return one object."""
from il2cpp.array_origin import _definitions,_graph
from il2cpp.closed_lookup import _receiver
from il2cpp.csharp import declares_member_name,source_field_name
from il2cpp.equivalent_binary import _amd64
from il2cpp.names import safe_ident
from il2cpp.module_curve import fixed_frame
from il2cpp.prelude import HAVE_ICED
from il2cpp.shared_field import reference_field_at
from il2cpp.text import sdisp

if HAVE_ICED:
    from iced_x86 import Mnemonic as M,OpKind as K,Register as R,RegisterExt as RX


def _property(lift,call):
    il=lift.il;ids=il.addr_candidates.get(call.near_branch_target,()) if call.is_call_near else ()
    if len(ids)!=1 or ids[0][0]!='method' or not 0<=ids[0][1]<len(il.meta.methods):return None
    md=il.meta.methods[ids[0][1]];p=lift._accessor_prop(md.index)
    if (md.addr==call.near_branch_target and md.param_count==0 and not md.is_static and md.flags&7==6 and not md.flags&0x40 and
            md.generic_container==-1 and p and p[0]=='get' and not p[2] and md.name=='get_'+p[1] and p[1].isidentifier() and
            safe_ident(p[1])==p[1] and 0<=md.return_type<len(il.types)):return md,p[1],il.types[md.return_type]


def reacquired_accessors(lift,method,td,blocks,pads):
    il=lift.il;fields={};calls={};possible=[];groups={}
    if not HAVE_ICED or pads or method.is_static or td.is_valuetype or not _amd64(getattr(il,'bin',None)) or il.meta.version!=31:return fields,calls
    seq=[i for b in blocks for i in b.insns]
    for j in range(3,len(seq)-6):
        a=seq[j]
        if not a.is_call_near or not seq[j+6].is_call_near:continue
        w=seq[j-3:j+7];t1,n1,z1,_,t2,n2,z2,buf,receiver,b=w
        if (t1.mnemonic!=M.TEST or t1.op0_register!=t1.op1_register or t1.op0_register!=R.RCX or
                t2.mnemonic!=M.TEST or t2.op0_register!=t2.op1_register or t2.op0_register!=R.RAX or
                n1.mnemonic!=M.JE or n2.mnemonic!=M.JE or n1.near_branch_target!=n2.near_branch_target or
                z1.mnemonic!=M.XOR or z1.op0_register!=z1.op1_register or z1.op0_register!=R.EDX or z2.mnemonic!=M.XOR or
                z2.op0_register!=z2.op1_register or z2.op0_register!=R.R8D or buf.mnemonic!=M.LEA or buf.op0_register!=R.RCX or
                buf.memory_base not in (R.RSP,R.RBP) or receiver.mnemonic!=M.MOV or receiver.op0_register!=R.RDX or receiver.op1_register!=R.RAX or
                any(i.memory_index!=R.NONE or i.has_segment_prefix or i.has_lock_prefix for i in w)):continue
        p=_property(lift,a);q=_property(lift,b)
        if not p or not q or not p[2] or il._closed_type_key(p[2])!=(0x12,q[0].declaring,0) or not il.returns_sret(q[2]):continue
        possible.append((w,p,q))
    if len(possible)<2:return fields,calls
    g=_graph(il,seq,chained=True,allow_tail=True,runtime_tails=lift.rt_wbarrier);by={i.ip:i for i in seq}
    if not g or seq[0].ip!=method.addr:return fields,calls
    pred,_=g;frame=fixed_frame(lift,method,blocks,pads,immediate=True,extended_saves=True)
    if not frame:return fields,calls
    guards={b.insns[-1].ip for b in blocks if b.insns and b.term and b.term[0]=='jmp' and b.succs==[b.bid+1]}
    for w,p,q in possible:
        buf=w[-3];off=sdisp(buf.memory_displacement)+(frame[0] if buf.memory_base==R.RBP else 0);width=il._sf_field_size(q[2],0)
        if not width or width<=0 or not 32<=off<=frame[1]-width or w[1].ip not in guards or w[5].ip not in guards:continue
        if any(a.next_ip!=b.ip or pred[b.ip]!=[a.ip] for a,b in zip(w,w[1:])):continue
        throw=by.get(w[1].near_branch_target)
        if not throw or not throw.is_call_near or lift._named_raise_throw(throw.near_branch_target,lift._call_name(throw.near_branch_target))!='System.NullReferenceException':continue
        defs=_definitions(by,pred,method.addr,w[0].ip,R.RCX)
        if len(defs)!=1:continue
        ip,r=defs.pop();load=by[ip]
        if (load.mnemonic!=M.MOV or load.op0_register!=r or not RX.is_gpr64(r) or r in (R.RSP,R.RBP) or load.op1_kind!=K.MEMORY or
                not RX.is_gpr64(load.memory_base) or load.memory_index!=R.NONE or load.has_segment_prefix or
                not _receiver(il,method,by,pred,ip,td.index,initial=load.memory_base,this_only=True)):continue
        fld=reference_field_at(il,td.index,sdisp(load.memory_displacement))
        if not fld or fld[0]!=td.index:continue
        chain=il.base_chain_tds(fld[2][0]);owner=p[0].declaring
        if owner not in chain or any(declares_member_name(il,il.meta.typedefs[t],p[1]) for t in chain[:chain.index(owner)]):continue
        group=groups.setdefault((fld[1],p[0].index),[]);group.append((ip,w[3].ip,w[-1].ip,q[0].index,fld[2]))
    for (fi,first),rows in groups.items():
        if len({r[0] for r in rows})<2:continue
        for ip,a,b,second,ty in rows:
            fields[ip]='this.'+safe_ident(source_field_name(il,fi)),ty
            calls[a]=first;calls[b]=second
    return fields,calls
