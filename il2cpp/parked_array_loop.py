"""A counted array traversal keeps its pre-flag array but reads live slots.
Capture only that reference, never a copy of the elements.
"""
from il2cpp.array_origin import _graph,_definitions,_reachable,_SAVED
from il2cpp.closed_lookup import _receiver
from il2cpp.equivalent_binary import _amd64
from il2cpp.metadata import source_params
from il2cpp.names import safe_ident
from il2cpp.prelude import HAVE_ICED
from il2cpp.saved_ref import reference_vector
from il2cpp.sret_copy import _own_field
from il2cpp.text import sdisp
if HAVE_ICED:
    from iced_x86 import Mnemonic as M,OpKind as K,Register as R,RegisterExt as RX,MemorySizeExt as MS


def parked_arrays(l,m,td,blocks,pads):
    out={};il=l.il
    if not HAVE_ICED or pads or m.is_static or m.generic_container!=-1 or td.is_valuetype or td.generic_container!=-1:return out
    s=[i for b in blocks for i in b.insns];wins=[s[j-6:j+18] for j in range(6,len(s)-17) if s[j].mnemonic==M.CMP and s[j+1].mnemonic==M.JGE and s[j+3].mnemonic==M.JAE]
    if not wins or not _amd64(il.bin) or il.meta.version!=31 or any(n.startswith('t') and n[1:].isdigit() for n in (safe_ident(p.name) for p in source_params(il.meta,m))):return out
    g=_graph(il,s,chained=True,nested_chains=True);by={i.ip:i for i in s}
    if not g:return out
    pred,succ=g
    for w in wins:
        arr,z,flag,initial,test,null,cmp,finished,idxcmp,oor,extend,elem,nonzero,fail,hidden,on,call,inc,copy,again=w[:20];base=arr.op0_register;reg=z.op0_register
        if (arr.mnemonic!=M.MOV or base not in _SAVED or arr.op1_kind!=K.MEMORY or z.mnemonic!=M.XOR or z.op0_register!=z.op1_register or
                not RX.is_gpr32(reg) or RX.full_register(reg) not in _SAVED or RX.full_register(reg)==base or
                flag.mnemonic!=M.MOV or flag.op0_kind!=K.MEMORY or flag.op1_kind!=K.IMMEDIATE8 or flag.immediate8 not in (0,1) or
                initial.mnemonic!=M.MOV or initial.op0_register!=R.EAX or initial.op1_register!=reg or test.mnemonic!=M.TEST or test.op0_register!=test.op1_register or test.op0_register!=base or null.mnemonic!=M.JE or
                cmp.op0_register!=R.EAX or idxcmp.op0_register!=reg or idxcmp.mnemonic!=M.CMP or
                any(i.memory_base!=base or i.memory_displacement!=24 or MS.size(i.memory_size)!=4 for i in (cmp,idxcmp)) or
                extend.mnemonic!=M.MOVSXD or extend.op1_register!=reg or not RX.is_gpr64(extend.op0_register) or
                elem.mnemonic!=M.MOV or elem.op0_register!=R.RCX or elem.memory_base!=base or elem.memory_index!=extend.op0_register or elem.memory_index_scale!=8 or elem.memory_displacement!=32 or
                nonzero.mnemonic!=M.TEST or nonzero.op0_register!=nonzero.op1_register or nonzero.op0_register!=R.RCX or fail.mnemonic!=M.JE or fail.near_branch_target!=null.near_branch_target or
                hidden.mnemonic!=M.XOR or hidden.op0_register!=hidden.op1_register or hidden.op0_register!=R.R8D or on.mnemonic!=M.MOV or on.op0_register!=R.DL or on.op1_kind!=K.IMMEDIATE8 or on.immediate8 not in (0,1) or
                not call.is_call_near or inc.mnemonic!=M.INC or inc.op0_register!=reg or copy.mnemonic!=M.MOV or copy.op0_register!=R.EAX or copy.op1_register!=reg or
                again.mnemonic!=M.JMP or again.near_branch_target!=cmp.ip or finished.near_branch_target!=again.next_ip):continue
        if (any(i.has_lock_prefix or i.has_segment_prefix or i.ip!=elem.ip and i.memory_index!=R.NONE for i in w[:20]) or
                any(a.next_ip!=v.ip or set(pred[v.ip])!=({a.ip,again.ip} if v.ip==cmp.ip else {a.ip}) for a,v in zip(w[:19],w[1:20])) or
                any(by[p].is_call_near for p in _reachable(pred,pred[arr.ip])) or not all(_receiver(il,m,by,pred,i.ip,td.index,initial=i.memory_base,this_only=True) for i in (arr,flag))):continue
        f=_own_field(il,td,sdisp(arr.memory_displacement),8);b=_own_field(il,td,sdisp(flag.memory_displacement),1)
        if not b or il._closed_type_key(b[1])!=(2,0) or not f or not reference_vector(il,f[1]):continue
        el=il.type_from_ptr(f[1][0]);ids=il.addr_candidates.get(call.near_branch_target,())
        if len(ids)!=1 or ids[0][0]!='method' or not 0<=ids[0][1]<len(il.meta.methods):continue
        q=il.meta.methods[ids[0][1]];ps=il.meta.method_params(q)
        if (q.addr!=call.near_branch_target or q.is_static or q.flags&0x40 or q.generic_container!=-1 or q.param_count!=1 or len(ps)!=1 or not 0<=ps[0].type<len(il.types) or
                il._closed_type_key(il.types[ps[0].type])!=(2,0) or not 0<=q.return_type<len(il.types) or il._closed_type_key(il.types[q.return_type])!=(1,0) or il._closed_type_key(el)!=(0x12,q.declaring,0)):continue
        if any(not (i:=by.get(j.near_branch_target)) or not i.is_call_near or l._named_raise_throw(i.near_branch_target,l._call_name(i.near_branch_target))!=e for j,e in ((null,'System.NullReferenceException'),(oor,'System.IndexOutOfRangeException'))):continue
        out[arr.ip]=(f[0],f[1],'arr')
    return out
