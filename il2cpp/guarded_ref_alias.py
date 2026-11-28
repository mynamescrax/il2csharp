"""Snapshot two reference operands before their owner's class guard.

The first comes from an independently checked object field. For a private
member, require its one-load public getter before spelling the reference.
"""
from il2cpp.array_origin import _graph
from il2cpp.closed_lookup import _receiver
from il2cpp.equivalent_binary import _amd64
from il2cpp.names import safe_ident
from il2cpp.plain_property import plain_alias
from il2cpp.prelude import HAVE_ICED
from il2cpp.sret_copy import _own_field
from il2cpp.metadata import source_params
from il2cpp.text import sdisp,reg_name
from il2cpp.x64 import KLASS_INITIALIZED
if HAVE_ICED:
    from iced_x86 import Mnemonic as M,Register as R,RegisterExt as RX,MemorySizeExt as MS,OpKind as K
    from il2cpp.array_origin import _SAVED


def compared_fields(l,m,td,blocks,pads):
    out={};il=l.il
    if not HAVE_ICED or pads or m.is_static or td.is_valuetype or td.generic_container!=-1 or m.generic_container!=-1:return out
    seq=[i for b in blocks for i in b.insns];wins=[seq[j-6:j+3] for j,i in enumerate(seq) if j>=6 and j+2<len(seq) and i.mnemonic==M.CMP and i.memory_displacement==KLASS_INITIALIZED and seq[j-3].memory_base==R.RIP and seq[j-2].op0_register in _SAVED and seq[j-1].op0_register in _SAVED]
    if not wins or not _amd64(il.bin) or il.meta.version!=31 or any(n.startswith('t') and n[1:].isdigit() for n in (safe_ident(p.name) for p in source_params(il.meta,m))):return out
    g=_graph(il,seq,chained=True,nested_chains=True,allow_tail=True,runtime_tails=l.rt_wbarrier);by={i.ip:i for i in seq}
    if not g or seq[0].ip!=m.addr:return out
    pred,_=g
    for w in wins:
        field,test,null,klass,load,other,cmp,hot,init=w;r=field.op0_register
        if (field.mnemonic!=M.MOV or field.op1_kind!=K.MEMORY or not RX.is_gpr64(r) or field.memory_base not in _SAVED or r==field.memory_base or
                test.mnemonic!=M.TEST or test.op0_register!=test.op1_register or test.op0_register!=r or null.mnemonic!=M.JE or
                klass.mnemonic!=M.MOV or klass.op0_register!=R.RCX or r==R.RCX or
                load.mnemonic!=M.MOV or load.memory_base!=r or other.mnemonic!=M.MOV or other.memory_base!=field.memory_base or
                cmp.memory_base!=R.RCX or cmp.op1_kind!=K.IMMEDIATE8TO32 or cmp.immediate8to32 or hot.mnemonic!=M.JNE or hot.near_branch_target!=init.next_ip or
                not init.is_call_near or il.bin.exports.get(init.near_branch_target)!='il2cpp_runtime_class_init' or
                any(i.has_lock_prefix or i.has_segment_prefix or i.memory_index!=R.NONE for i in w) or
                any(a.next_ip!=v.ip or pred[v.ip]!=[a.ip] for a,v in zip(w,w[1:]))):continue
        throw=by.get(null.near_branch_target)
        if not throw or not throw.is_call_near or l._named_raise_throw(throw.near_branch_target,l._call_name(throw.near_branch_target))!='System.NullReferenceException':continue
        if not all(_receiver(il,m,by,pred,i.ip,td.index,initial=i.memory_base,this_only=True) for i in (field,other)):continue
        f=_own_field(il,td,sdisp(field.memory_displacement),8);o=_own_field(il,td,sdisp(other.memory_displacement),8)
        if not f or not o or il._closed_type_key(f[1])!=(0x12,f[1][0],0) or il._closed_type_key(o[1])!=(0x12,o[1][0],0):continue
        alias=plain_alias(l,f[1][0],sdisp(load.memory_displacement),8)
        if not alias or il._closed_type_key(alias[1])!=il._closed_type_key(o[1]):continue
        out[load.ip]=(reg_name(r),f[0],f[1],alias[0],alias[1]);out[other.ip]=(reg_name(other.memory_base),'this',None,o[0][5:],o[1])
    return out
