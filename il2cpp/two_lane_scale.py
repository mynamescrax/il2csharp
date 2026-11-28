"""Bind field multipliers and a shared divisor at their separate native reads.

The products remain SSE operations. In particular, the first packed load
retains its untouched high lane; only the actual memory operand is bound.
"""
from il2cpp.accessor_chain import _property as _aggregate_getter
from il2cpp.array_origin import _graph,_reachable
from il2cpp.closed_lookup import _receiver
from il2cpp.equivalent_binary import _amd64
from il2cpp.expr import Expr,acc_get
from il2cpp.metadata import source_params
from il2cpp.names import safe_ident
from il2cpp.packed_call import _float_fields
from il2cpp.prelude import HAVE_ICED
from il2cpp.scalar_snapshot import _property
from il2cpp.sret_copy import _own_field
from il2cpp.text import reg_name,sdisp

if HAVE_ICED:
    from iced_x86 import Mnemonic as M,OpKind as K,Register as R,MemorySizeExt as MS


def operand_samples(lift,m,td,blocks,pads):
    operands={};polls={};il=lift.il
    if not HAVE_ICED or pads or m.is_static or td.is_valuetype or td.generic_container!=-1 or m.generic_container!=-1:return operands,polls
    windows=[b.insns[j-7:j+3] for b in blocks for j,i in enumerate(b.insns) if j>=7 and i.is_call_near and j+2<len(b.insns) and
             b.insns[j+1].mnemonic==b.insns[j+2].mnemonic==M.DIVSS]
    if not windows or not _amd64(il.bin) or il.meta.version!=31 or any(n.startswith('t') and n[1:].isdigit() for n in (safe_ident(p.name) for p in source_params(il.meta,m))):return operands,polls
    seq=[i for b in blocks for i in b.insns];by={i.ip:i for i in seq};graph=_graph(il,seq,chained=True,nested_chains=True)
    if not graph or seq[0].ip!=m.addr:return operands,polls
    pred,succ=graph
    for w in windows:
        src,xy,z,scale_z,spill,scale_x,zero,poll,div_x,div_z=w
        xreg,zreg=xy.op0_register,z.op0_register
        if (any(i.has_segment_prefix or i.has_lock_prefix or i.memory_index!=R.NONE for i in w) or
                any(i.next_ip!=n.ip or pred[n.ip]!=[i.ip] for i,n in zip(w,w[1:])) or
                xy.mnemonic!=M.MOVSD or z.mnemonic!=M.MOVSS or xy.memory_base!=R.RAX or z.memory_base!=R.RAX or
                xy.memory_displacement or z.memory_displacement!=8 or xy.op1_kind!=K.MEMORY or z.op1_kind!=K.MEMORY or
                not R.XMM6<=xreg<=R.XMM15 or not R.XMM6<=zreg<=R.XMM15 or xreg==zreg or
                spill.mnemonic!=M.MOVSD or spill.op0_kind!=K.MEMORY or spill.memory_base!=R.RSP or spill.op1_register!=xreg or
                zero.mnemonic!=M.XOR or zero.op0_register!=zero.op1_register or zero.op0_register!=R.ECX or
                (div_x.op0_register,div_z.op0_register)!=(xreg,zreg) or div_x.op1_register!=R.XMM0 or div_z.op1_register!=R.XMM0):continue
        prop=_aggregate_getter(lift,src);clock=_property(lift,poll,'get')
        if not prop or len(_float_fields(il,prop[2]) or ())!=3 or not il.returns_sret(prop[2]) or not clock or not clock[0].is_static:continue
        # A prior lazy effect cannot be moved after the explicit samples.
        if any(by[p].mnemonic==M.CALL and by[p].near_branch_target!=lift.rt_init_meta for p in _reachable(pred,pred[src.ip])):continue
        rows={}
        for i,r in ((scale_z,zreg),(scale_x,xreg)):
            if (i.mnemonic!=M.MULSS or i.op0_register!=r or i.op1_kind!=K.MEMORY or MS.size(i.memory_size)!=4 or
                    not _receiver(il,m,by,pred,i.ip,td.index,initial=i.memory_base,this_only=True)):break
            row=_own_field(il,td,sdisp(i.memory_displacement),4)
            if not row or il._closed_type_key(row[1])!=(12,0):break
            rows[i.ip]=row
        if len(rows)==2:operands.update(rows);polls[poll.ip]=clock[0].index
    return operands,polls


def sample_operand(lift,i,value,row):
    field,ty=row;owner=dict.get(lift.regs,reg_name(i.memory_base))
    if (not value or value._unk or value.text!=field or not owner or owner._unk or owner.text!='this' or
            lift.il._closed_type_key(value.ty)!=(12,0)):return value
    n=lift.new_var();lift._var_types[n]=lift._type_hints[n]=ty
    lift.emit(i.ip,f'var {n} = {acc_get(field)};',None)
    return Expr(n,ty,'float')
