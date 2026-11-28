"""Receiver proof for a closed nullary lookup on a checked constant array index."""
from il2cpp.array_origin import _graph
from il2cpp.closed_lookup import _receiver,spec_lookup
from il2cpp.equivalent_binary import _amd64
from il2cpp.prelude import HAVE_ICED
from il2cpp.sret_copy import _own_field
from il2cpp.saved_ref import reference_vector
from il2cpp.text import sdisp
if HAVE_ICED:
    from iced_x86 import Mnemonic as M,OpKind as K,Register as R,RegisterExt as RX,MemorySizeExt as MS


def fixed_lookup_elements(l,m,td,blocks,pads):
    if not HAVE_ICED or pads or m.is_static or td.is_valuetype or td.generic_container!=-1:return {}
    il=l.il;seq=[i for b in blocks for i in b.insns];wins=[]
    for k,c in enumerate(seq):
        if k>=9 and c.is_call_near and seq[k-1].memory_base==R.RIP and seq[k-1].op0_register==R.RDX and seq[k-5].mnemonic==M.JBE:wins.append(seq[k-9:k+1])
    if not wins or not _amd64(il.bin) or il.meta.version!=31:return {}
    g=_graph(il,seq,chained=True,nested_chains=True,allow_tail=True,runtime_tails=l.rt_wbarrier)
    if not g or seq[0].ip!=m.addr:return {}
    pred,_=g;by={i.ip:i for i in seq};out={}
    for w in wins:
        field,test,nre,cmp,ior,read,test2,null,slot,call=w;reg=field.op0_register
        if (any(i.has_segment_prefix or i.has_lock_prefix or i.memory_index!=R.NONE for i in w) or
                any(a.next_ip!=b.ip or pred[b.ip]!=[a.ip] for a,b in zip(w,w[1:])) or
                field.mnemonic!=M.MOV or field.op1_kind!=K.MEMORY or not RX.is_gpr64(reg) or reg in (R.RSP,R.RBP) or
                test.mnemonic!=M.TEST or test.op0_register!=test.op1_register or test.op0_register!=reg or nre.mnemonic!=M.JE or
                cmp.mnemonic!=M.CMP or cmp.op0_kind!=K.MEMORY or cmp.memory_base!=reg or cmp.memory_displacement!=24 or MS.size(cmp.memory_size)!=4 or
                cmp.op1_kind not in (K.IMMEDIATE8TO32,K.IMMEDIATE32) or read.mnemonic!=M.MOV or read.op0_register!=R.RCX or read.memory_base!=reg or
                read.memory_displacement!=32+8*(cmp.immediate(1)&0xffffffff) or
                test2.mnemonic!=M.TEST or test2.op0_register!=test2.op1_register or test2.op0_register!=R.RCX or null.mnemonic!=M.JE or
                nre.near_branch_target!=null.near_branch_target):continue
        a=by.get(nre.near_branch_target);b=by.get(ior.near_branch_target)
        if (not a or not b or not a.is_call_near or not b.is_call_near or
                l._named_raise_throw(a.near_branch_target,l._call_name(a.near_branch_target))!='System.NullReferenceException' or
                l._named_raise_throw(b.near_branch_target,l._call_name(b.near_branch_target))!='System.IndexOutOfRangeException' or
                not _receiver(il,m,by,pred,field.ip,td.index,initial=field.memory_base,this_only=True)):continue
        row=_own_field(il,td,sdisp(field.memory_displacement),8);spec=spec_lookup(il,slot,call)
        if not row or not spec or not reference_vector(il,row[1]):continue
        elem=il.type_from_ptr(row[1][0])
        if elem and il._closed_type_key(elem)==(0x12,spec[1].declaring,0):out[read.ip]=row[1]
    return out
