"""Nullary accessors on live checked elements of a registered array return."""
import re

from il2cpp.array_origin import _definitions, _graph, _reachable
from il2cpp.field_slice import _body
from il2cpp.sret_copy import _own_field
from il2cpp.prelude import HAVE_ICED
from il2cpp.text import reg_name

if HAVE_ICED:
    from iced_x86 import Mnemonic as M, OpKind as K, Register as R, RegisterExt
    _SAVED={R.RBX,R.RBP,R.RSI,R.RDI,R.R12,R.R13,R.R14,R.R15}

_SCALAR=re.compile(rb'(?:\x66\x90)?\xf3\x0f\x10(?:\x01|\x41(.)|\x81(.{4}))\xc3',re.S)
_LEAD=re.compile(rb'(?:\x66\x90)?\xf3\x0f\x10')


def _member(lift,target,owner):
    il=lift.il;ids=il.addr_candidates.get(target,());hits=[]
    for k,j in ids:
        if k!='method' or not 0<=j<len(il.meta.methods):return None
        m=il.meta.methods[j]
        if m.declaring!=owner.index:continue
        prop=lift._accessor_prop(j)
        if (not prop or prop[0]!='get' or prop[2] or m.addr!=target or m.flags&7!=6 or m.is_static or m.flags&0x40 or
                m.param_count or m.generic_container!=-1 or not 0<=m.return_type<len(il.types)):return None
        hits.append((prop[1],il.types[m.return_type]))
    if len(hits)!=1:return None
    name,ty=hits[0];key=il._closed_type_key(ty)
    if len(ids)==1 and key==(0x12,ty[0],0):return name,ty,'RAX'
    if key!=(0x0c,0):return None
    leaf=_SCALAR.match(_body(il,target,_LEAD) or b'')
    if not leaf:return None
    off=int.from_bytes(leaf[1] or leaf[2] or b'\0','little',signed=True)
    width=il.value_type_size(owner.index);f=_own_field(il,owner,16+off,4) if width and 0<=off<=width-4 else None
    if f and il._closed_type_key(f[1])==key:return name,ty,'XMM0'


def element_reads(lift,method,blocks,pads):
    plans={};il=lift.il
    if not HAVE_ICED or pads:return plans
    candidates=[b for b in blocks if len(b.insns)>=6 and b.insns[0].mnemonic==M.MOVSXD and b.insns[2].mnemonic==M.IMUL and b.insns[5].mnemonic==M.CALL]
    if not candidates:return plans
    seq=[i for b in blocks for i in b.insns];graph=_graph(il,seq,allow_tail=True,chained=True,runtime_tails=lift.rt_wbarrier)
    if not graph:return plans
    pred,succ=graph;byip={i.ip:i for i in seq}
    for b in candidates:
        if len(b.preds)!=1:continue
        arm=blocks[b.preds[0]].insns
        if len(arm)<2:continue
        cmp,jump=arm[-2:];base=cmp.memory_base;idx=cmp.op0_register
        extend,hidden,mul,header,add,call=b.insns[:6];window=[cmp,jump]+b.insns[:6]
        if (any(i.has_segment_prefix or i.has_lock_prefix or i.memory_index!=R.NONE for i in window) or
                any(x.next_ip!=z.ip or pred[z.ip]!=[x.ip] for x,z in zip(window,window[1:])) or
                cmp.mnemonic!=M.CMP or cmp.op1_kind!=K.MEMORY or cmp.memory_displacement!=24 or base not in _SAVED or
                not RegisterExt.is_gpr32(idx) or RegisterExt.full_register(idx) not in _SAVED-{base} or
                jump.mnemonic!=M.JAE or jump.op0_kind!=K.NEAR_BRANCH64 or jump.near_branch_target==jump.next_ip):continue
        throw=byip.get(jump.near_branch_target)
        if (not throw or throw.mnemonic!=M.CALL or throw.op0_kind!=K.NEAR_BRANCH64 or
                lift._named_raise_throw(throw.near_branch_target,lift._call_name(throw.near_branch_target))!='System.IndexOutOfRangeException'):continue
        if (extend.op1_register!=idx or extend.op0_register not in (R.RAX,R.R9,R.R10,R.R11) or
                hidden.mnemonic!=M.XOR or hidden.op0_register!=hidden.op1_register or hidden.op0_register!=R.EDX or
                mul.op0_register!=R.RCX or mul.op1_register!=extend.op0_register or mul.op2_kind not in (K.IMMEDIATE8TO64,K.IMMEDIATE32TO64) or
                header.mnemonic!=M.ADD or header.op0_register!=R.RCX or header.op1_kind not in (K.IMMEDIATE8TO64,K.IMMEDIATE32TO64) or header.immediate(1)!=32 or
                add.mnemonic!=M.ADD or add.op0_register!=R.RCX or add.op1_register!=base or call.op0_kind!=K.NEAR_BRANCH64):continue
        defs=_definitions(byip,pred,method.addr,cmp.ip,base)
        if len(defs)!=1:continue
        ip,reg=defs.pop();p=byip[ip]
        if reg!=R.RAX or p.mnemonic!=M.CALL or ip in _reachable(succ,succ[ip]):continue
        ids=il.addr_candidates.get(p.near_branch_target,())
        if len(ids)!=1 or ids[0][0]!='method' or not 0<=ids[0][1]<len(il.meta.methods):continue
        md=il.meta.methods[ids[0][1]]
        if md.addr!=p.near_branch_target or md.generic_container!=-1 or not 0<=md.return_type<len(il.types):continue
        arr=il.types[md.return_type]
        if not arr or il._type_enum(arr)!=0x1d:continue
        elem=il.type_from_ptr(arr[0]);key=il._closed_type_key
        if not elem or not 0<=elem[0]<len(il.meta.typedefs) or key(elem)!=(0x11,elem[0],0) or key(arr)!=(0x1d,key(elem),0):continue
        td=il.meta.typedefs[elem[0]];stride=il.value_type_size(td.index)
        if not td.is_valuetype or td.generic_container!=-1 or not stride or mul.immediate(2)!=stride:continue
        member=_member(lift,call.near_branch_target,td)
        if member:plans[call.ip]=('element',reg_name(base),reg_name(idx),arr,*member)
    return plans
