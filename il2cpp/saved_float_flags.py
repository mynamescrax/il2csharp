"""Capture an ordered SSE comparison before intervening field transfers.

The operands are sampled at COMISS. Its CF/ZF relation is still live at
the unsigned branch even when the intervening MOVs replace those fields.
"""
from il2cpp.array_origin import _graph
from il2cpp.closed_lookup import _receiver
from il2cpp.equivalent_binary import _amd64
from il2cpp.expr import _BOOL_TY, acc_get
from il2cpp.metadata import source_params
from il2cpp.names import safe_ident
from il2cpp.prelude import HAVE_ICED
from il2cpp.sret_copy import _own_field
from il2cpp.text import sdisp

if HAVE_ICED:
    from iced_x86 import Mnemonic as M,OpKind as K,Register as R,RegisterExt as RX,MemorySizeExt as MS


def comparison_sites(lift,m,td,blocks,pads):
    sites={};il=lift.il
    if not HAVE_ICED or pads or m.is_static or td.is_valuetype or td.generic_container!=-1 or m.generic_container!=-1:return sites
    runs=[]
    for b in blocks:
        s=b.insns
        if len(s)<5 or s[-1].mnemonic not in (M.JBE,M.JB,M.JA,M.JAE):continue
        j=len(s)-2
        while j>=2 and len(s)-j<=7 and s[j].mnemonic==M.MOV:j-=1
        if j>=2 and j<len(s)-2 and s[j].mnemonic in (M.COMISS,M.UCOMISS):runs.append(s[j-2:])
    if (not runs or not _amd64(getattr(il,'bin',None)) or il.meta.version!=31 or
            any(n.startswith('t') and n[1:].isdigit() for n in (safe_ident(p.name) for p in source_params(il.meta,m)))):return sites
    seq=[i for b in blocks for i in b.insns];by={i.ip:i for i in seq};g=_graph(il,seq,allow_tail=True,chained=True,nested_chains=True)
    if not g or seq[0].ip!=m.addr:return sites
    pred,_=g
    for w in runs:
        load,zero,cmp=w[:3];jump=w[-1]
        if (any(i.has_lock_prefix or i.has_segment_prefix or i.memory_index!=R.NONE for i in w) or
                any(a.next_ip!=b.ip or pred[b.ip]!=[a.ip] for a,b in zip(w,w[1:])) or
                load.mnemonic!=M.MOVSS or load.op1_kind!=K.MEMORY or not RX.is_xmm(load.op0_register) or not RX.is_gpr64(load.memory_base) or
                zero.mnemonic!=M.XORPS or zero.op0_register!=zero.op1_register or not RX.is_xmm(zero.op0_register) or zero.op0_register==load.op0_register or
                cmp.op0_register!=load.op0_register or cmp.op1_register!=zero.op0_register or
                not _receiver(il,m,by,pred,load.ip,td.index,initial=load.memory_base,this_only=True)):continue
        src=_own_field(il,td,sdisp(load.memory_displacement),4)
        if not src or il._closed_type_key(src[1])!=(12,0):continue
        # Each gap instruction is a simple non-indexed four-byte transfer
        # of a declared field on the same receiver. It cannot write flags.
        valid=True
        for i in w[3:-1]:
            row=_own_field(il,td,sdisp(i.memory_displacement),4)
            if (not row or il._closed_type_key(row[1]) not in ((8,0),(9,0),(12,0)) or i.memory_base!=load.memory_base or
                    not _receiver(il,m,by,pred,i.ip,td.index,initial=i.memory_base,this_only=True) or i.rflags_modified or MS.size(i.memory_size)!=4 or
                    not (i.op1_kind==K.MEMORY and RX.is_gpr32(i.op0_register) and RX.full_register(i.op0_register) not in (R.RSP,R.RBP) or
                         i.op0_kind==K.MEMORY and (i.op1_kind==K.IMMEDIATE32 or RX.is_gpr32(i.op1_register)))):valid=False;break
        if valid:sites[cmp.ip]=(jump.ip,src[0],'>=' if jump.mnemonic in (M.JB,M.JAE) else '>',jump.mnemonic in (M.JA,M.JAE))
    return sites


def save_comparison(lift,i,plan):
    if lift._flags_mn!=i.mnemonic or not lift.flags:return None
    a,z=lift.flags;j,field,rel,positive=plan
    if (not a or a.text!=field or a._unk or a.kind!='float' or lift.il._closed_type_key(a.ty)!=(12,0) or
            not z or z._unk or z.text not in ('0f','0.0f') or z.kind!='float'):return None
    t=lift.new_var();lift._var_types[t]=_BOOL_TY;lift.emit(i.ip,'var %s = %s;'%(t,acc_get(f'({field} {rel} 0f)')),None)
    return j,a,z,f'{t} == '+('true' if positive else 'false')
