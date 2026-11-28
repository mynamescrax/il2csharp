"""Array and receiver snapshots for a checked, sampled reference element.

The sample may replace both fields and mutate the saved array. Capture
the two reference loads at their own IPs; leave the element read *after*
the sample and after the native bounds check.
"""
from il2cpp.array_origin import _definitions,_graph
from il2cpp.closed_lookup import _receiver,_field_input
from il2cpp.csharp import source_field_name
from il2cpp.equivalent_binary import _amd64
from il2cpp.metadata import source_params
from il2cpp.names import safe_ident
from il2cpp.prelude import HAVE_ICED
from il2cpp.saved_ref import reference_vector
from il2cpp.shared_field import whole_field_at
from il2cpp.shared_icall import _alias
from il2cpp.text import sdisp

if HAVE_ICED:
    from iced_x86 import Mnemonic as M,OpKind as K,MemorySizeExt as MS,Register as R,RegisterExt as RX
    _PARK={R.RBX,R.RSI,R.RDI,R.R12,R.R13,R.R14,R.R15}


def sampled_elements(lift,method,td,blocks,pads):
    il=lift.il;out={}
    if (not HAVE_ICED or pads or method.is_static or method.param_count!=1 or method.generic_container!=-1 or td.is_valuetype or td.generic_container!=-1):return out
    seq=[i for b in blocks for i in b.insns];windows=[]
    for n in range(6,len(seq)-10):
        call=seq[n]
        if (call.is_call_near and seq[n+1].mnemonic==M.CMP and seq[n+2].mnemonic==M.JAE and
                seq[n+5].mnemonic==M.MOVSXD and seq[n+9].mnemonic==M.MOV and seq[n+10].is_call_near):windows.append(seq[n-5:n+11])
    if (not windows or not _amd64(getattr(il,'bin',None)) or il.meta.version!=31 or not 0<=method.return_type<len(il.types) or
            il._closed_type_key(il.types[method.return_type])!=(1,0)):return out
    ps=source_params(il.meta,method)
    if len(ps)!=1 or not 0<=ps[0].type<len(il.types) or il._closed_type_key(il.types[ps[0].type])!=(12,0):return out
    pname=safe_ident(ps[0].name)
    if pname.startswith('t') and pname[1:].isdigit():return out
    g=_graph(il,seq,chained=True,nested_chains=True);by={i.ip:i for i in seq}
    if not g or seq[0].ip!=method.addr:return out
    pred,_=g
    for w in windows:
        length,hidden,recv,zero,park,call,cmp,fail,test,nul,extend,h,vol,this,element,use=w
        if (any(i.has_segment_prefix or i.has_lock_prefix for i in w) or
                any(a.next_ip!=b.ip or pred[b.ip]!=[a.ip] for a,b in zip(w,w[1:]))):continue
        arr,holder=park.op0_register,recv.op0_register
        if (arr not in _PARK or holder not in _PARK or arr==holder or length.mnemonic!=M.MOV or length.op0_register!=R.EDX or
                length.op1_kind!=K.MEMORY or length.memory_index!=R.NONE or length.memory_displacement!=24 or
                hidden.mnemonic!=M.XOR or hidden.op0_register!=hidden.op1_register or hidden.op0_register!=R.R8D or
                recv.mnemonic!=M.MOV or recv.op1_kind!=K.MEMORY or recv.memory_index!=R.NONE or not RX.is_gpr64(recv.memory_base) or
                zero.mnemonic!=M.XOR or zero.op0_register!=zero.op1_register or zero.op0_register!=R.ECX or
                park.mnemonic!=M.MOV or park.op1_register!=length.memory_base or not RX.is_gpr64(park.op1_register) or
                cmp.op0_register!=R.EAX or cmp.op1_kind!=K.MEMORY or cmp.memory_base!=arr or cmp.memory_index!=R.NONE or
                cmp.memory_displacement!=24 or MS.size(cmp.memory_size)!=4 or test.mnemonic!=M.TEST or test.op0_register!=test.op1_register or
                test.op0_register!=holder or nul.mnemonic!=M.JE or extend.op0_register!=R.RDX or extend.op1_register!=R.EAX or
                h.mnemonic!=M.XOR or h.op0_register!=h.op1_register or h.op0_register!=R.R9D or
                vol.mnemonic!=M.MOVAPS or vol.op0_register!=R.XMM2 or not R.XMM6<=vol.op1_register<=R.XMM15 or
                this.mnemonic!=M.MOV or this.op0_register!=R.RCX or this.op1_register!=holder or
                element.op0_register!=R.RDX or element.op1_kind!=K.MEMORY or element.memory_base!=arr or element.memory_index!=R.RDX or
                element.memory_index_scale!=8 or element.memory_displacement!=32):continue
        throws=[by.get(i.near_branch_target) for i in (fail,nul)]
        if any(not x or not x.is_call_near or lift._named_raise_throw(x.near_branch_target,lift._call_name(x.near_branch_target))!=exc for x,exc in
               zip(throws,('System.IndexOutOfRangeException','System.NullReferenceException'))):continue
        sample=_alias(il,call.near_branch_target)
        if not sample or [il._closed_type_key(t) for t in sample[1]]!=[(8,0),(8,0)]:continue
        if any(il._closed_type_key(il.types[il.meta.methods[mi].return_type])!=(8,0)
               for _,mi in il.addr_candidates[call.near_branch_target]):continue
        ids=il.addr_candidates.get(use.near_branch_target,())
        if len(ids)!=1 or ids[0][0]!='method' or not 0<=ids[0][1]<len(il.meta.methods):continue
        consumer=il.meta.methods[ids[0][1]];cp=il.meta.method_params(consumer)
        if (consumer.addr!=use.near_branch_target or consumer.is_static or consumer.flags&(0x40|0x800) or consumer.generic_container!=-1 or
                len(cp)!=2 or consumer.param_count!=2 or not 0<=consumer.return_type<len(il.types) or
                not all(0<=p.type<len(il.types) for p in cp) or il._closed_type_key(il.types[consumer.return_type])!=(1,0) or
                il._closed_type_key(il.types[cp[1].type])!=(12,0)):continue
        receiver=_field_input(il,method,by,pred,use,consumer.declaring)
        if not receiver or receiver[0]!=recv.ip or il._closed_type_key(receiver[1][1])!=(0x12,consumer.declaring,0):continue
        defs=_definitions(by,pred,method.addr,length.ip,length.memory_base)
        if len(defs)!=1:continue
        p,reg=defs.pop();load=by[p]
        if (_definitions(by,pred,method.addr,element.ip,arr)!={(p,reg)} or reg in (R.RBP,R.RSP) or load.mnemonic!=M.MOV or load.op0_register!=reg or
                load.op1_kind!=K.MEMORY or not RX.is_gpr64(load.memory_base) or load.memory_index!=R.NONE or load.has_segment_prefix or
                not _receiver(il,method,by,pred,p,td.index,initial=load.memory_base,this_only=True)):continue
        row=whole_field_at(il,td.index,sdisp(load.memory_displacement),8)
        if not row or row[0]!=td.index or not reference_vector(il,row[2]) or il._closed_type_key(row[2])[1]!=il._closed_type_key(il.types[cp[0].type]):continue
        out[p]=('this.'+safe_ident(source_field_name(il,row[1])),row[2],'arr')
        out[recv.ip]=(*receiver[1],'obj')
    return out
