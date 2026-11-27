"""A nested state frame loads its state and parks its owner before dispatch.
Those loads run once per invocation, before either entry or resume work."""
from il2cpp.array_origin import _graph
from il2cpp.closed_lookup import _receiver
from il2cpp.csharp import source_field_name
from il2cpp.equivalent_binary import _amd64
from il2cpp.expr import Expr,acc_get
from il2cpp.names import safe_ident
from il2cpp.prelude import HAVE_ICED
from il2cpp.shared_field import reference_field_at
from il2cpp.sret_copy import _own_field
from il2cpp.text import reg_name,sdisp

if HAVE_ICED:
    from iced_x86 import Mnemonic as M,OpKind as K,Register as R,RegisterExt
    _SAVED={R.RBX,R.RSI,R.RDI,R.R12,R.R13,R.R14,R.R15}


def dispatch_fields(lift,method,blocks,pads):
    il=lift.il;out={}
    if (not HAVE_ICED or pads or not _amd64(getattr(il,'bin',None)) or il.meta.version!=31 or method.is_static or
            method.param_count or not 0<=method.return_type<len(il.types) or il._closed_type_key(il.types[method.return_type])!=(2,0)):return out
    td=il.meta.typedefs[method.declaring];owner=il._nested_owner(td.index)
    if owner is None or not 0<=owner<len(il.meta.typedefs) or td.is_valuetype or td.generic_container!=-1:return out
    pairs=[]
    for b in blocks:
        s=b.insns
        if len(s)<4 or s[-1].mnemonic!=M.JNE or s[-2].mnemonic!=M.TEST or s[-2].op0_register!=s[-2].op1_register or s[-2].op0_register!=R.EAX:continue
        j=len(s)-3;p=s[j]
        if p.mnemonic==M.MOV and p.op0_kind==K.MEMORY and p.memory_base==R.RSP and p.op1_register in _SAVED:j-=1
        if j<1:continue
        state,holder=s[j-1:j+1];base=holder.memory_base
        if (state.mnemonic!=M.MOV or state.op0_register!=R.EAX or state.op1_kind!=K.MEMORY or state.memory_base!=base or
                holder.mnemonic!=M.MOV or holder.op0_register not in _SAVED or base not in _SAVED or base==holder.op0_register or
                any(x.has_segment_prefix or x.has_lock_prefix or x.memory_index!=R.NONE for x in s[j-1:])):continue
        pairs.append(s[j-1:])
    if not pairs:return out
    seq=[i for b in blocks for i in b.insns];graph=_graph(il,seq,chained=True,allow_tail=True,runtime_tails=lift.rt_wbarrier)
    if not graph or seq[0].ip!=method.addr:return out
    pred,_=graph;by={i.ip:i for i in seq}
    for w in pairs:
        state,holder=w[:2];cmp=by.get(w[-1].near_branch_target);test=by.get(cmp.next_ip) if cmp else None
        if (not cmp or not test or cmp.mnemonic!=M.CMP or cmp.op0_register!=R.EAX or cmp.op1_kind!=K.IMMEDIATE8TO32 or
                cmp.immediate8to32!=1 or test.mnemonic!=M.JNE or test.near_branch_target==test.next_ip or
                w[-1].near_branch_target==w[-1].next_ip or pred[cmp.ip]!=[w[-1].ip] or pred[test.ip]!=[cmp.ip] or
                any(a.next_ip!=b.ip or pred[b.ip]!=[a.ip] for a,b in zip(w,w[1:])) or
                not _receiver(il,method,by,pred,state.ip,td.index,initial=state.memory_base,this_only=True)):continue
        field=reference_field_at(il,td.index,sdisp(holder.memory_displacement));n=_own_field(il,td,sdisp(state.memory_displacement),4)
        if not field or field[0]!=td.index or il._closed_type_key(field[2])!=(0x12,owner,0) or not n or il._closed_type_key(n[1])!=(8,0):continue
        out[state.ip]=(n[0],n[1],'int');out[holder.ip]=('this.'+safe_ident(source_field_name(il,field[1])),field[2],'obj')
    return out


def bind_dispatch_field(lift,ins,row):
    member,ty,kind=row;name=lift.new_var();lift._var_types[name]=lift._type_hints[name]=ty
    lift.emit(ins.ip,'var %s = %s;'%(name,acc_get(member)),None);lift.regs[reg_name(ins.op0_register)]=Expr(name,ty,kind)
