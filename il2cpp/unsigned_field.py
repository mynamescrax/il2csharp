"""Unsigned Jcc after a dword CMP on a declared signed instance field.

A negative iterator state is above any small positive bound in this test.
Keep the original field read at CMP and keep its specific flags epoch.
"""
from il2cpp.array_origin import _graph
from il2cpp.closed_lookup import _receiver
from il2cpp.equivalent_binary import _amd64
from il2cpp.expr import acc_get, _INT_TY
from il2cpp.metadata import source_params
from il2cpp.names import safe_ident
from il2cpp.prelude import HAVE_ICED
from il2cpp.sret_copy import _own_field
from il2cpp.text import sdisp

if HAVE_ICED:
    from iced_x86 import Mnemonic as M,MemorySizeExt as MS,OpKind as K,Register as R,RegisterExt as RX
    _OPS={M.JA:'>',M.JAE:'>=',M.JB:'<',M.JBE:'<='}


def field_bounds(lift,method,td,blocks,pads):
    plans={}
    if not HAVE_ICED or pads or method.is_static or td.is_valuetype or method.generic_container!=-1:return plans
    windows=[]
    for b in blocks:
        if len(b.insns)<2 or b.insns[-1].mnemonic not in _OPS:continue
        j=b.insns[-1];idx=len(b.insns)-2;gap=b.insns[idx]
        if (gap.mnemonic==M.MOV and RX.is_gpr64(gap.op0_register) and gap.op0_register not in (R.RSP,R.RBP) and
                (gap.op1_kind==K.REGISTER and RX.is_gpr64(gap.op1_register) or
                 gap.op1_kind==K.MEMORY and RX.is_gpr64(gap.memory_base) and gap.memory_index==R.NONE)):
            idx-=1
        if idx<0:continue
        cmp=b.insns[idx]
        if (cmp.mnemonic==M.CMP and cmp.op0_kind==K.MEMORY and MS.size(cmp.memory_size)==4 and
                cmp.op1_kind in (K.IMMEDIATE8TO32,K.IMMEDIATE32) and RX.is_gpr64(cmp.memory_base) and
                cmp.memory_index==R.NONE and not any(i.has_lock_prefix or i.has_segment_prefix for i in b.insns[idx:])):
            windows.append(b.insns[idx:])
    il=lift.il
    if (not windows or not _amd64(getattr(il,'bin',None)) or il.meta.version!=31 or
            any(n.startswith('t') and n[1:].isdigit() for n in (safe_ident(p.name) for p in source_params(il.meta,method)))):return plans
    seq=[i for b in blocks for i in b.insns];by={i.ip:i for i in seq};g=_graph(il,seq,chained=True,nested_chains=True,allow_tail=True,runtime_tails=lift.rt_wbarrier)
    if not g or seq[0].ip!=method.addr:return plans
    pred,_=g
    for w in windows:
        cmp,j=w[0],w[-1]
        if (any(i.next_ip!=n.ip or pred[n.ip]!=[i.ip] for i,n in zip(w,w[1:])) or
                not _receiver(il,method,by,pred,cmp.ip,td.index,initial=cmp.memory_base,this_only=True)):continue
        f=_own_field(il,td,sdisp(cmp.memory_displacement),4)
        if not f or il._closed_type_key(f[1])!=(8,0):continue
        if len(w)==3 and w[1].op1_kind==K.MEMORY:
            load=w[1];ref=_own_field(il,td,sdisp(load.memory_displacement),8)
            if (load.memory_base!=cmp.memory_base or not ref or il._closed_type_key(ref[1])!=(0x12,ref[1][0],0)):continue
        plans[cmp.ip]=(j.ip,f[0],cmp.immediate(1)&0xffffffff,_OPS[j.mnemonic])
    return plans


def sample_bound(lift,ins,plan):
    pair=lift.flags
    if not pair or lift._flags_mn!=M.CMP:return None
    a,z=pair;jump,field,n,op=plan
    if (not a or a._unk or a.text!=field or lift.il._closed_type_key(a.ty)!=(8,0) or
            z is None or not z.text.lstrip('-').isdigit() or int(z.text)&0xffffffff!=n):return None
    t=lift.new_var();lift._var_types[t]=_INT_TY;lift.emit(ins.ip,'var %s = %s;'%(t,acc_get(field)),None)
    return jump,a,z,'unchecked((uint)%s) %s %du'%(t,op,n)
