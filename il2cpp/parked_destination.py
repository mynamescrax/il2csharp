"""Bind an acquired destination before evaluating an aggregate setter's argument.

The saved object may be null. No null check belongs at the snapshot itself:
the source getters run before the setter dereferences that destination.
"""
from il2cpp.accessor_chain import _property
from il2cpp.array_origin import _graph,_definitions,_SAVED
from il2cpp.closed_lookup import _receiver
from il2cpp.equivalent_binary import _amd64
from il2cpp.metadata import source_params
from il2cpp.names import safe_ident
from il2cpp.packed_call import _float_fields
from il2cpp.prelude import HAVE_ICED
from il2cpp.text import sdisp

if HAVE_ICED:
    from iced_x86 import Mnemonic as M,OpKind as K,Register as R


def destination_reads(l,m,td,blocks,pads):
    il=l.il;out={}
    if not HAVE_ICED or pads or m.is_static or m.generic_container!=-1 or td.is_valuetype or td.generic_container!=-1:return out
    seq=[i for b in blocks for i in b.insns]
    w=[(i,seq[j+1:j+8]) for j,i in enumerate(seq[:-7]) if i.mnemonic==M.TEST and i.op0_register==i.op1_register and i.op0_register in _SAVED and seq[j+1].mnemonic==M.JE and seq[j+2].mnemonic==M.MOVSD and seq[j+3].mnemonic==M.LEA]
    if not w or not _amd64(il.bin) or il.meta.version!=31 or any(n.startswith('t') and n[1:].isdigit() for n in (safe_ident(p.name) for p in source_params(il.meta,m))):return out
    by={i.ip:i for i in seq};g=_graph(il,seq,chained=True,nested_chains=True,allow_tail=True,runtime_tails=l.rt_wbarrier)
    if not g or seq[0].ip!=m.addr:return out
    pred,_=g
    for check,window in w:
        null,lo,home,hi,hidden,receiver,low_store=window
        if (check.op0_kind!=K.REGISTER or check.op1_kind!=K.REGISTER or not null.near_branch_target in by or
                lo.op1_kind!=K.MEMORY or lo.memory_base!=R.RAX or lo.memory_displacement or home.op0_register!=R.RDX or home.memory_base!=R.RSP or
                hi.mnemonic!=M.MOV or hi.op0_register!=R.EAX or hi.memory_base!=R.RAX or hi.memory_displacement!=8 or
                hidden.mnemonic!=M.XOR or hidden.op0_register!=hidden.op1_register or hidden.op0_register!=R.R8D or receiver.mnemonic!=M.MOV or
                receiver.op0_register!=R.RCX or receiver.op1_register!=check.op0_register or low_store.mnemonic!=M.MOVSD or
                low_store.memory_base!=R.RSP or low_store.memory_displacement!=home.memory_displacement or low_store.op1_register!=lo.op0_register):continue
        high_store=by.get(low_store.next_ip);setter=by.get(high_store.next_ip) if high_store else None
        if (not setter or not setter.is_call_near or high_store.mnemonic!=M.MOV or high_store.op1_register!=R.EAX or
                high_store.memory_base!=R.RSP or high_store.memory_displacement!=home.memory_displacement+8):continue
        chain=[check,*window,high_store,setter]
        if (any(i.has_lock_prefix or i.has_segment_prefix or i.memory_index!=R.NONE for i in chain) or
                any(v.next_ip!=z.ip or pred[z.ip]!=[v.ip] for v,z in zip(chain,chain[1:])) or len(pred[check.ip])!=1):continue
        src=by[pred[check.ip][0]];get=_property(l,src);throw=by[null.near_branch_target]
        if (not get or src.next_ip!=check.ip or not il.returns_sret(get[2]) or len(_float_fields(il,get[2]) or ())!=3 or
                not throw.is_call_near or l._named_raise_throw(throw.near_branch_target,l._call_name(throw.near_branch_target))!='System.NullReferenceException'):continue
        ids=il.addr_candidates.get(setter.near_branch_target,())
        if len(ids)!=1 or ids[0][0]!='method' or not 0<=ids[0][1]<len(il.meta.methods):continue
        q=il.meta.methods[ids[0][1]];p=l._accessor_prop(q.index);ps=il.meta.method_params(q)
        if (not p or p[0]!='set' or p[1]!=get[1] or p[2] or q.addr!=setter.near_branch_target or q.declaring!=get[0].declaring or
                q.is_static or q.flags&0x40 or q.flags&7!=6 or q.generic_container!=-1 or len(ps)!=q.param_count or len(ps)!=1 or
                not 0<=ps[0].type<len(il.types) or not 0<=q.return_type<len(il.types) or il._closed_type_key(il.types[q.return_type])!=(1,0) or
                il._closed_type_key(il.types[ps[0].type])!=il._closed_type_key(get[2])):continue
        defs=_definitions(by,pred,m.addr,check.ip,check.op0_register)
        if len(defs)!=1 or _definitions(by,pred,m.addr,setter.ip,R.RCX)!=defs:continue
        ip,r=defs.pop();origin=by[ip];prop=_property(l,origin)
        if (r!=R.RAX or not prop or il._closed_type_key(prop[2])!=(0x12,q.declaring,0) or not ip<src.ip or
                not _receiver(il,m,by,pred,origin.ip,td.index,initial=R.RCX,this_only=True)):continue
        # Ordinary direct instance property, including the hidden null
        # MethodInfo. Do not bind a guess from an unrelated stale RDX.
        defs=_definitions(by,pred,m.addr,origin.ip,R.RDX)
        if len(defs)!=1:continue
        pos,reg=defs.pop();z=by[pos]
        if z.mnemonic==M.XOR and z.op0_register==z.op1_register==R.EDX and reg==R.RDX:out[ip]=prop[0].index
    return out
