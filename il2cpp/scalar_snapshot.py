"""Capture a mutable scalar field and a registered scalar getter in native
order when a nonvolatile lane carries the field across the call."""
from il2cpp.array_origin import _graph
from il2cpp.closed_lookup import _receiver
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


def _property(lift,i,kind):
    il=lift.il
    if i.mnemonic!=M.CALL or i.op0_kind!=K.NEAR_BRANCH64:return None
    ids=il.addr_candidates.get(i.near_branch_target,())
    if len(ids)!=1 or ids[0][0]!='method' or not 0<=ids[0][1]<len(il.meta.methods):return None
    m=il.meta.methods[ids[0][1]];p=lift._accessor_prop(m.index)
    if (not p or p[0]!=kind or p[2] or m.addr!=i.near_branch_target or m.generic_container!=-1 or m.flags&0x40 or
            not 0<=m.return_type<len(il.types)):return None
    key=il._closed_type_key
    if kind=='get':return (m,p[1]) if not m.param_count and key(il.types[m.return_type])==(0x0c,0) else None
    ps=il.meta.method_params(m)
    if m.param_count==len(ps)==1 and 0<=ps[0].type<len(il.types) and key(il.types[ps[0].type])==(0x0c,0) and key(il.types[m.return_type])==(1,0):return m,p[1]


def _scaled_write(lift,method,td,s,pred,byip):
    """Prove the original property receiver and the factor held across a
    second getter. The divisor, by contrast, is read after that call."""
    first,gain,zero,park,rate,div,hidden,recv,mul,sub,arg,setter=s
    if any(pred[b.ip]!=[a.ip] or a.next_ip!=b.ip for a,b in zip(s,s[1:])) or any(i.has_segment_prefix or i.memory_index!=R.NONE for i in s):return None
    a=_property(lift,first,'get');q=_property(lift,setter,'set');clock=_property(lift,rate,'get')
    if not (a and q and clock) or (a[0].declaring,a[1])!=(q[0].declaring,q[1]) or a[0].is_static or q[0].is_static or not clock[0].is_static:return None
    r=recv.op1_register;y=gain.op0_register;x=park.op0_register
    if (gain.mnemonic!=M.MOVSS or gain.op1_kind!=K.MEMORY or not R.XMM6<=y<=R.XMM15 or
            zero.mnemonic!=M.XOR or zero.op0_register!=zero.op1_register or zero.op0_register!=R.ECX or
            park.mnemonic!=M.MOVAPS or park.op1_register!=R.XMM0 or not R.XMM6<=x<=R.XMM15 or x==y or
            div.mnemonic!=M.DIVSS or div.op0_register!=R.XMM0 or div.op1_kind!=K.MEMORY or
            hidden.mnemonic!=M.XOR or hidden.op0_register!=hidden.op1_register or hidden.op0_register!=R.R8D or
            recv.mnemonic!=M.MOV or recv.op0_register!=R.RCX or r not in _SAVED or
            mul.mnemonic!=M.MULSS or mul.op0_register!=R.XMM0 or mul.op1_register!=y or
            sub.mnemonic!=M.SUBSS or sub.op0_register!=x or sub.op1_register!=R.XMM0 or
            arg.mnemonic!=M.MOVAPS or arg.op0_register!=R.XMM1 or arg.op1_register!=x):return None
    use=_last(byip,pred,first.ip,R.RCX,method.addr)
    if not use or use=='this' or use.mnemonic!=M.MOV or use.op0_register!=R.RCX or use.op1_register!=r:return None
    load=_last(byip,pred,use.ip,r,method.addr)
    again=_last(byip,pred,recv.ip,r,method.addr)
    if not again or again=='this' or not load or load=='this' or again.ip!=load.ip:return None
    if (not load or load=='this' or load.mnemonic!=M.MOV or load.op0_register!=r or load.op1_kind!=K.MEMORY or
            load.has_segment_prefix or load.memory_index!=R.NONE or any(not _receiver(lift.il,method,byip,pred,i.ip,td.index,
                        initial=i.memory_base,this_only=True) for i in (load,gain,div))):return None
    fld=lambda i,n:_own_field(lift.il,td,sdisp(i.memory_displacement),n)
    ref,scale,denom=fld(load,8),fld(gain,4),fld(div,4);key=lift.il._closed_type_key
    if (not ref or key(ref[1])!=(0x12,a[0].declaring,0) or not scale or not denom or any(key(f[1])!=(0x0c,0) for f in (scale,denom))):return None
    return {load.ip:ref,gain.ip:scale},{first.ip:a[0].index,rate.ip:clock[0].index}


def scalar_sites(lift,method,td,blocks,pads):
    fields={};calls={};result=fields,calls;il=lift.il
    if (not HAVE_ICED or pads or method.is_static or td.is_valuetype or not isinstance(getattr(il,'bin',None),PE) or
            not il.bin.is64 or not 0<=method.return_type<len(il.types) or il.returns_sret(il.types[method.return_type])):return result
    sites=[];updates=[]
    for b in blocks:
        for j,call in enumerate(b.insns[:-1]):
            if call.mnemonic!=M.CALL or call.op0_kind!=K.NEAR_BRANCH64:continue
            if j+12<=len(b.insns) and b.insns[j+4].mnemonic==M.CALL and b.insns[j+5].mnemonic==M.DIVSS and b.insns[j+11].mnemonic==M.CALL:updates.append(b.insns[j:j+12])
            k=j+1;use=b.insns[k]
            if use.mnemonic in _ARITH and use.op0_register==use.op1_register==R.XMM0:
                k+=1
                if k==len(b.insns):continue
                use=b.insns[k]
            if use.mnemonic in _ARITH and R.XMM6<=use.op0_register<=R.XMM15 and use.op1_register==R.XMM0:sites.append(b.insns[j:k+1])
    if not (sites or updates):return result
    seq=[i for b in blocks for i in b.insns];graph=_graph(il,seq,allow_tail=True,chained=True)
    if not graph:return result
    pred,_=graph;byip={i.ip:i for i in seq};key=il._closed_type_key
    for s in updates:
        p=_scaled_write(lift,method,td,s,pred,byip)
        if p:fields.update(p[0]);calls.update(p[1])
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
        # Metadata-init branches can interrupt a unique-predecessor walk
        # without changing the saved this. Check *all* raw incoming paths.
        if not _receiver(il,method,byip,pred,load.ip,td.index,initial=load.memory_base,this_only=True):continue
        row=_own_field(il,td,sdisp(load.memory_displacement),4)
        if not row or key(row[1])!=(0x0c,0):continue
        fields[load.ip]=row;calls[call.ip]=mi
    return result


def capture_field(lift,ins,row):
    field,ty=row;name=lift.new_var();lift._var_types[name]=ty
    lift.emit(ins.ip,'var %s = %s;'%(name,acc_get(field)),None)
    lift.regs[reg_name(ins.op0_register)]=Expr(name,ty,'float' if lift.il._type_enum(ty)==0x0c else 'obj')
