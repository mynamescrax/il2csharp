"""Capture signed field operands at their native reads. The remainder is
passed to an Int32 setter, then compared to the *reloaded* divisor field.
The quotient faults at IDIV even when only the remainder is live."""
from il2cpp.array_origin import _graph,_definitions
from il2cpp.closed_lookup import _receiver
from il2cpp.equivalent_binary import _amd64
from il2cpp.expr import Expr,acc_get,_INT_TY
from il2cpp.prelude import HAVE_ICED
from il2cpp.signed_division import _quotient,_remainder
from il2cpp.shared_field import reference_field_at
from il2cpp.sret_copy import _own_field
from il2cpp.text import reg_name,sdisp

if HAVE_ICED:
    from iced_x86 import Mnemonic as M, OpKind as K, Register as R, RegisterExt, InstructionInfoFactory,OpAccess
    _INFO=InstructionInfoFactory()
    _SAVED={R.RBX,R.RDI,R.RSI,R.R12,R.R13,R.R14,R.R15}


def _dead_saved(by,succ,ip,r):
    # After the dword comparison a wide use would observe zero-extension.
    # Only prune a path at a full, unconditional kill; calls preserve r.
    work=[ip];seen=set()
    while work:
        k=work.pop()
        if k in seen:continue
        if len(seen)>512:return False
        seen.add(k);i=by[k];uses=[u for u in _INFO.info(i).used_registers() if RegisterExt.full_register(u.register)==r]
        if uses:
            if len(uses)==1 and uses[0].access==OpAccess.WRITE and RegisterExt.size(uses[0].register)>=4:continue
            return False
        if not succ[k] and i.mnemonic not in (M.UD2,M.INT3):return False
        work.extend(succ[k])
    return True


def _receiver_field(il,method,by,pred,load,declaring):
    defs=_definitions(by,pred,method.addr,load.ip,load.memory_base)
    if len(defs)!=1:return False
    ip,r=defs.pop();src=by[ip]
    if (src.mnemonic!=M.MOV or src.op0_register!=r or not RegisterExt.is_gpr64(r) or src.op1_kind!=K.MEMORY or
            not RegisterExt.is_gpr64(src.memory_base) or src.memory_index!=R.NONE or src.has_segment_prefix or
            not _receiver(il,method,by,pred,ip,method.declaring,initial=src.memory_base,this_only=True)):return False
    owner=reference_field_at(il,method.declaring,sdisp(src.memory_displacement))
    if not owner:return False
    field=reference_field_at(il,owner[2][0],sdisp(load.memory_displacement))
    return bool(field and declaring in il.base_chain_tds(field[2][0]))


def field_divisions(lift,method,blocks,pads):
    actions={};il=lift.il
    if not HAVE_ICED or pads or not _amd64(getattr(il,'bin',None)) or il.meta.version!=31 or method.is_static:return actions
    if not any(i.mnemonic==M.IDIV for b in blocks for i in b.insns):return actions
    td=il.meta.typedefs[method.declaring]
    if (td.is_valuetype or td.generic_container!=-1 or not 0<=td.parent<len(il.types) or
            il._closed_type_key(il.types[td.parent])!=(28,0)):return actions
    seq=[i for b in blocks for i in b.insns];g=_graph(il,seq,chained=True,allow_tail=True,runtime_tails=lift.rt_wbarrier)
    if not g or seq[0].ip!=method.addr:return actions
    pred,succ=g;by={i.ip:i for i in seq}
    for k,div in enumerate(seq):
        if div.mnemonic!=M.IDIV or k<4 or k+8>=len(seq):continue
        w=seq[k-4:k+9];d,n,inc,cdq,_,recv,save,test,null,zero,call,cmp,branch=w
        base=d.memory_base;dst=d.op0_register;saved=RegisterExt.full_register(save.op0_register)
        if (dst!=R.ECX or base not in _SAVED or
                any(i.mnemonic!=M.MOV or i.memory_base!=base or i.op1_kind!=K.MEMORY for i in (d,n)) or
                n.op0_register!=R.EAX or inc.mnemonic!=M.INC or inc.op0_register!=dst or cdq.mnemonic!=M.CDQ or div.op0_register!=dst or
                recv.mnemonic!=M.MOV or recv.op0_register!=R.RCX or recv.op1_kind!=K.MEMORY or recv.memory_base not in _SAVED or
                save.mnemonic!=M.MOV or save.op1_register!=R.EDX or not RegisterExt.is_gpr32(save.op0_register) or
                saved not in _SAVED or saved==base or test.mnemonic!=M.TEST or test.op0_register!=test.op1_register or test.op0_register!=R.RCX or
                null.mnemonic!=M.JE or zero.mnemonic!=M.XOR or zero.op0_register!=zero.op1_register or zero.op0_register!=R.R8D or
                call.mnemonic!=M.CALL or call.op0_kind!=K.NEAR_BRANCH64 or cmp.mnemonic!=M.CMP or cmp.op0_register!=save.op0_register or
                cmp.memory_base!=base or cmp.memory_displacement!=d.memory_displacement or branch.mnemonic not in (M.JGE,M.JL,M.JG,M.JLE,M.JE,M.JNE) or
                any(i.has_segment_prefix or i.has_lock_prefix or i.memory_index!=R.NONE for i in w) or
                any(a.next_ip!=b.ip or pred[b.ip]!=[a.ip] for a,b in zip(w,w[1:]))):continue
        raise_=by.get(null.near_branch_target)
        if (not raise_ or raise_.mnemonic!=M.CALL or raise_.op0_kind!=K.NEAR_BRANCH64 or
                lift._named_raise_throw(raise_.near_branch_target,lift._call_name(raise_.near_branch_target))!='System.NullReferenceException'):continue
        ids=il.addr_candidates.get(call.near_branch_target,())
        if len(ids)!=1 or ids[0][0]!='method':continue
        setter=il.meta.methods[ids[0][1]];prop=lift._accessor_prop(setter.index);ps=il.meta.method_params(setter)
        if (not prop or prop[0]!='set' or prop[2] or setter.addr!=call.near_branch_target or setter.is_static or
                setter.generic_container!=-1 or il.meta.typedefs[setter.declaring].generic_container!=-1 or not 0<=setter.return_type<len(il.types) or
                il._closed_type_key(il.types[setter.return_type])!=(1,0) or len(ps)!=1 or not 0<=ps[0].type<len(il.types) or
                il._closed_type_key(il.types[ps[0].type])!=(8,0) or not _receiver(il,method,by,pred,d.ip,td.index,initial=base,this_only=True) or
                not _receiver_field(il,method,by,pred,recv,setter.declaring) or not _dead_saved(by,succ,branch.ip,saved)):continue
        inputs=[_own_field(il,td,sdisp(i.memory_displacement),4) for i in (d,n)]
        if any(not row or il._closed_type_key(row[1])!=(8,0) for row in inputs):continue
        actions[d.ip]=('field',inputs[0][0]);actions[n.ip]=('field',inputs[1][0]);actions[inc.ip]=('inc',d.ip)
        actions[div.ip]=('divide',n.ip,inc.ip)
    return actions


def division_step(lift,ins,action,values):
    def bind(r,text):
        name=lift.new_var();lift._var_types[name]=lift._type_hints[name]=_INT_TY
        lift.emit(ins.ip,f'var {name} = {text};',None);v=Expr(name,_INT_TY,'int');lift.regs[r]=v;return v
    op,*args=action
    if op=='field':values[ins.ip]=bind(reg_name(ins.op0_register),acc_get(args[0]));return True
    if op=='inc':
        r=reg_name(ins.op0_register);v=values.get(args[0])
        if v and dict.get(lift.regs,r) is v:
            values[ins.ip]=bind(r,f'unchecked({v.text} + 1)');lift.flags=None;return True
    if op=='divide':
        n=values.get(args[0]);d=values.get(args[1]);r=reg_name(ins.op0_register)
        if n and d and dict.get(lift.regs,'RAX') is n and dict.get(lift.regs,r) is d:
            q=bind('RAX',_quotient(n.text,d.text));bind('RDX',_remainder(n.text,d.text,q.text));lift.flags=None;return True
    return False
