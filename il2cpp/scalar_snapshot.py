"""Capture a mutable scalar field and a registered scalar getter in native
order when a nonvolatile lane carries the field across the call."""
from il2cpp.array_origin import _graph
from il2cpp.expr import Expr,acc_get
from il2cpp.prelude import HAVE_ICED
from il2cpp.binary import PE
from il2cpp.sret_copy import _own_field
from il2cpp.text import reg_name,sdisp

if HAVE_ICED:
    from iced_x86 import InstructionInfoFactory, Mnemonic as M, OpAccess, OpKind as K, Register as R, RegisterExt
    _INFO=InstructionInfoFactory();_WRITE={OpAccess.WRITE,OpAccess.READ_WRITE,OpAccess.COND_WRITE,OpAccess.READ_COND_WRITE}
    _SAVED={R.RBX,R.RBP,R.RDI,R.RSI,R.R12,R.R13,R.R14,R.R15}
    _ARITH={M.ADDSS,M.SUBSS,M.MULSS,M.DIVSS}


def _last(byip,pred,ip,reg,entry):
    """Only a unique predecessor path; a CALL kills volatile registers."""
    for _ in range(64):
        if ip==entry:return 'this' if reg==R.RCX else None
        if len(pred[ip])!=1:return None
        i=byip[pred[ip][0]];ip=i.ip
        if i.mnemonic==M.CALL and reg not in _SAVED and not R.XMM6<=reg<=R.XMM15:return None
        if any(u.access in _WRITE and RegisterExt.full_register(u.register)==RegisterExt.full_register(reg) for u in _INFO.info(i).used_registers()):return i


def scalar_sites(lift,method,td,blocks,pads):
    fields={};calls={};result=fields,calls;il=lift.il
    if (not HAVE_ICED or pads or method.is_static or td.is_valuetype or not isinstance(getattr(il,'bin',None),PE) or
            not il.bin.is64 or not 0<=method.return_type<len(il.types) or il.returns_sret(il.types[method.return_type])):return result
    sites=[]
    for b in blocks:
        for j,call in enumerate(b.insns[:-1]):
            if call.mnemonic!=M.CALL or call.op0_kind!=K.NEAR_BRANCH64:continue
            k=j+1;use=b.insns[k]
            if use.mnemonic in _ARITH and use.op0_register==use.op1_register==R.XMM0:
                k+=1
                if k==len(b.insns):continue
                use=b.insns[k]
            if use.mnemonic in _ARITH and R.XMM6<=use.op0_register<=R.XMM15 and use.op1_register==R.XMM0:sites.append(b.insns[j:k+1])
    if not sites:return result
    seq=[i for b in blocks for i in b.insns];graph=_graph(il,seq,allow_tail=True,chained=True)
    if not graph:return result
    pred,_=graph;byip={i.ip:i for i in seq};key=il._closed_type_key
    for window in sites:
        if any(pred[y.ip]!=[x.ip] for x,y in zip(window,window[1:])):continue
        call=window[0];ids=il.addr_candidates.get(call.near_branch_target,())
        if len(ids)!=1 or ids[0][0]!='method' or not 0<=ids[0][1]<len(il.meta.methods):continue
        mi=ids[0][1];m=il.meta.methods[mi];prop=lift._accessor_prop(mi)
        if (m.addr!=call.near_branch_target or not m.is_static or m.param_count or m.generic_container!=-1 or
                not prop or prop[0]!='get' or prop[2] or not 0<=m.return_type<len(il.types) or key(il.types[m.return_type])!=(0x0c,0)):continue
        zero=_last(byip,pred,call.ip,R.RCX,method.addr)
        if not zero or zero=='this' or zero.mnemonic!=M.XOR or zero.op0_register!=zero.op1_register or zero.op0_register!=R.ECX:continue
        reg=window[-1].op0_register;load=_last(byip,pred,call.ip,reg,method.addr)
        if load and load.mnemonic==M.MOVAPS and load.op0_register==reg and RegisterExt.is_xmm(load.op1_register):
            reg=load.op1_register;load=_last(byip,pred,load.ip,reg,method.addr)
        if (not load or load.mnemonic!=M.MOVSS or load.op0_register!=reg or load.op1_kind!=K.MEMORY or load.has_segment_prefix or
                load.memory_index!=R.NONE or load.memory_base not in _SAVED|{R.RCX}):continue
        base=_last(byip,pred,load.ip,load.memory_base,method.addr)
        if base!='this':
            if not base or base.mnemonic!=M.MOV or base.op0_register!=load.memory_base or base.op1_register!=R.RCX or _last(byip,pred,base.ip,R.RCX,method.addr)!='this':continue
        row=_own_field(il,td,sdisp(load.memory_displacement),4)
        if not row or key(row[1])!=(0x0c,0):continue
        fields[load.ip]=row;calls[call.ip]=mi
    return result


def capture_field(lift,ins,row):
    field,ty=row;name=lift.new_var();lift._var_types[name]=ty
    lift.emit(ins.ip,'var %s = %s;'%(name,acc_get(field)),None)
    lift.regs[reg_name(ins.op0_register)]=Expr(name,ty,'float')
