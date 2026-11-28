"""Preserve a sampled dictionary key and the one membership decision.

A comparer may mutate the owner's dictionary field. The miss arm reloads
that field before allocating a value instead of adding to the queried map.
"""
from il2cpp.array_origin import _graph,_definitions
from il2cpp.awaiter import _object_new_abi
from il2cpp.closed_class_read import _class_entry
from il2cpp.closed_lookup import _receiver
from il2cpp.equivalent_binary import _amd64
from il2cpp.metadata import source_params
from il2cpp.names import safe_ident
from il2cpp.prelude import HAVE_ICED
from il2cpp.string_ratio import _parameter
from il2cpp.sret_copy import _own_field
from il2cpp.text import sdisp
if HAVE_ICED:
    from iced_x86 import Mnemonic as M,Register as R,RegisterExt as RX,OpKind as K
    from il2cpp.array_origin import _SAVED


def membership_samples(l,m,td,blocks,pads):
    fields={};calls={};il=l.il
    if not HAVE_ICED or pads or m.is_static or m.generic_container!=-1 or td.is_valuetype or td.generic_container!=-1:return fields,calls
    s=[i for b in blocks for i in b.insns];wins=[s[j-9:j+6] for j,i in enumerate(s) if 9<=j<len(s)-5 and i.is_call_near and s[j-1].op0_register==R.EDX and s[j-2].op0_register==R.R8 and s[j+2].mnemonic==M.JNE]
    if not wins or not _amd64(il.bin) or il.meta.version!=31:return fields,calls
    ps=source_params(il.meta,m);params=[safe_ident(p.name) for p in ps]
    if len(ps)!=m.param_count or not ps or any(n.startswith('t') and n[1:].isdigit() for n in params) or il.returns_sret(il.types[m.return_type]):return fields,calls
    g=_graph(il,s,chained=True,nested_chains=True);by={i.ip:i for i in s}
    if not g or s[0].ip!=m.addr:return fields,calls
    pred,succ=g
    for w in wins:
        zero,recv,source,first,park,test,null,slot,arg,contains,flag,hit,klass,again,alloc=w
        if (any(a.next_ip!=z.ip or pred[z.ip]!=[a.ip] for a,z in zip(w,w[1:])) or any(i.has_lock_prefix or i.has_segment_prefix or i.memory_index!=R.NONE for i in w) or
                zero.mnemonic!=M.XOR or zero.op0_register!=zero.op1_register or zero.op0_register!=R.EDX or recv.mnemonic!=M.MOV or recv.op0_register!=R.RCX or recv.op1_register not in _SAVED or not source.is_call_near or
                first.mnemonic!=M.MOV or first.op0_register!=R.RCX or first.memory_base not in _SAVED or
                park.mnemonic!=M.MOV or park.op1_register!=R.EAX or not RX.is_gpr32(park.op0_register) or RX.full_register(park.op0_register) not in _SAVED or
                test.mnemonic!=M.TEST or test.op0_register!=test.op1_register or test.op0_register!=R.RCX or null.mnemonic!=M.JE or
                slot.mnemonic!=M.MOV or slot.memory_base!=R.RIP or arg.mnemonic!=M.MOV or arg.op1_register!=R.EAX or
                flag.mnemonic!=M.TEST or flag.op0_register!=flag.op1_register or flag.op0_register!=R.AL or hit.near_branch_target<=alloc.ip or
                klass.mnemonic!=M.MOV or klass.op0_register!=R.RCX or klass.memory_base!=R.RIP or again.mnemonic!=M.MOV or again.op0_register not in _SAVED or
                again.memory_base!=first.memory_base or again.memory_displacement!=first.memory_displacement or not alloc.is_call_near or not _object_new_abi(l,alloc.near_branch_target)):continue
        ids=il.addr_candidates.get(source.near_branch_target,());u=il.decode_slot(slot.ip_rel_memory_address) or {};si=u.get('idx',-1)
        if len(ids)!=1 or ids[0][0]!='method' or not 0<=ids[0][1]<len(il.meta.methods) or u.get('kind')!=6 or not 0<=si<len(il.method_specs):continue
        f=il.meta.methods[ids[0][1]];mi,ci,gi=il.method_specs[si]
        if (f.addr!=source.near_branch_target or f.is_static or f.param_count or f.generic_container!=-1 or f.flags&0x40 or
                not 0<=f.return_type<len(il.types) or il._closed_type_key(il.types[f.return_type])!=(8,0) or
                ci<0 or gi!=-1 or not 0<=mi<len(il.meta.methods) or _class_entry(il,si)!=contains.near_branch_target):continue
        if not any(0<=p.type<len(il.types) and (t:=il.types[p.type]) and il._closed_type_key(t)==(0x12,t[0],0) and
                   f.declaring in il.base_chain_tds(t[0]) and _parameter(by,pred,m.addr,recv.ip,recv.op1_register,reg) for reg,p in zip((R.RDX,R.R8,R.R9),ps)):continue
        q=il.meta.methods[mi];ot=il.meta.typedefs[q.declaring];types=il._method_spec_type_args(ci);qps=il.meta.method_params(q);ck=il._closed_type_key
        if (q.name!='ContainsKey' or il.typedef_full(ot.index)!='System.Collections.Generic.Dictionary`2' or len(types or ())!=2 or ck(types[0])!=(8,0) or
                q.is_static or q.generic_container!=-1 or q.flags&7!=6 or q.param_count!=len(qps) or len(qps)!=1 or
                not 0<=q.return_type<len(il.types) or ck(il.types[q.return_type])!=(2,0) or not 0<=qps[0].type<len(il.types) or
                ot.generic_container<0 or il._type_enum(t:=il.types[qps[0].type])!=0x13 or t[1]&(1<<29) or t[0]!=il.meta.generic_containers[ot.generic_container][3]):continue
        kt=il.decode_slot(klass.ip_rel_memory_address) or {};field=_own_field(il,td,sdisp(first.memory_displacement),8)
        if (not field or ck(field[1])!=(0x15,(0x12,q.declaring,0),tuple(map(ck,types)),0) or kt.get('kind')!=1 or ck(kt.get('type'))!=ck(types[1]) or
                not all(_receiver(il,m,by,pred,i.ip,td.index,initial=i.memory_base,this_only=True) for i in (first,again))):continue
        throw=by.get(null.near_branch_target)
        if not throw or not throw.is_call_near or l._named_raise_throw(throw.near_branch_target,l._call_name(throw.near_branch_target))!='System.NullReferenceException':continue
        fields[first.ip]=fields[again.ip]=field;calls[source.ip]=f.index;calls[contains.ip]=q.index
    return fields,calls
