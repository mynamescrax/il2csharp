"""A terminal virtual call with constants and a readonly aggregate argument.
Prove both words of VirtualInvokeData and every visible Win64 argument; the
managed call still dispatches on the receiver, never to a fixed MethodDef."""
from il2cpp.async_start import _frame
from il2cpp.module_curve import _float_literal
from il2cpp.names import safe_ident
from il2cpp.prelude import HAVE_ICED
from il2cpp.readonly_sret import init_guards,plain,static_value_alias
from il2cpp.stack_literal import stack_literal
from il2cpp.stack_local_frame import stack_local_frame
from il2cpp.text import sdisp
from il2cpp.x64 import KLASS_STATIC_FIELDS,KLASS_VTABLE

if HAVE_ICED:
    from iced_x86 import Mnemonic as M, MemorySizeExt, OpKind as K, Register as R, RegisterExt


def virtual_forward(lift,method,td,blocks,seq,pads):
    if (not HAVE_ICED or pads or not 10<len(seq)<=96 or seq[0].mnemonic!=M.PUSH or
            seq[-1].mnemonic!=M.RET or seq[-4].mnemonic!=M.CALL or seq[-4].op0_kind!=K.MEMORY):return None
    il=lift.il;key=il._closed_type_key;call=seq[-4];disp=sdisp(call.memory_displacement)
    if (method.is_static or method.param_count or method.generic_container!=-1 or td.is_valuetype or td.generic_container!=-1 or
            not 0<=method.return_type<len(il.types) or key(il.types[method.return_type])!=(1,0) or
            disp<KLASS_VTABLE or (disp-KLASS_VTABLE)%16 or not plain(seq)):return None
    slot=(disp-KLASS_VTABLE)//16;mi=il.vtable_method(td.index,slot)
    if mi is None or not 0<=mi<len(il.meta.methods):return None
    sink=il.meta.methods[mi]
    if (sink.declaring!=td.index or sink.index==method.index or sink.slot!=slot or sink.is_static or sink.flags&7!=6 or
            not sink.flags&0x40 or sink.flags&0x800 or sink.generic_container!=-1 or safe_ident(sink.name)!=sink.name or
            not 0<=sink.return_type<len(il.types) or key(il.types[sink.return_type])!=(1,0)):return None
    ps=il.meta.method_params(sink)
    if len(ps)!=sink.param_count or not 4<=len(ps)<=12 or any(not 0<=p.type<len(il.types) for p in ps):return None
    frame=stack_local_frame(lift,method,blocks,pads);short=_frame(seq[:2],seq[-3:])
    if not frame or not short:return None
    g=init_guards(lift,seq,2,short[1]);
    if not g:return None
    j,park,slots=g;used=set();regs={park:('self',)};mem={}
    volatile={R.RAX,R.RCX,R.RDX,R.R8,R.R9,R.R10,R.R11}
    for i in seq[j:-4]:
        dst=i.op0_register;src=i.op1_register;d=sdisp(i.memory_displacement);base=regs.get(i.memory_base)
        if i.op0_kind==K.MEMORY:
            v=regs.get(RegisterExt.full_register(src));n=MemorySizeExt.size(i.memory_size)
            if i.op1_kind==K.IMMEDIATE8:v=('bool',i.immediate8)
            if (i.memory_base!=R.RSP or not 32<=d<=frame[0]-n or any(x<d+n and d<x+l for x,l in (*frame[2],*mem.keys())) or
                    not v or (i.mnemonic,n,v[0]) not in ((M.MOV,1,'bool'),(M.MOV,8,'str'),(M.MOV,8,'info'),
                    (M.MOV,4,'tile'),(M.MOVSD,8,'tile')) or v[0]=='tile' and v[3]!=n):return None
            mem[d,n]=v;continue
        if i.op0_kind!=K.REGISTER:return None
        r=RegisterExt.full_register(dst);v=None
        if r not in volatile and not R.XMM0<=dst<=R.XMM5:return None
        if i.mnemonic==M.MOV and RegisterExt.is_gpr64(dst) and i.memory_base==R.RIP:
            ptr=i.ip_rel_memory_address;u=il.decode_slot(ptr) or {};used.add(ptr)
            if ptr not in slots or u.get('kind') not in (1,5):return None
            v=('str',ptr) if u['kind']==5 else ('type',ptr)
        elif i.mnemonic==M.MOV and RegisterExt.is_gpr64(dst) and RegisterExt.is_gpr64(src):v=regs.get(src)
        elif i.mnemonic==M.MOV and RegisterExt.is_gpr64(dst) and base:
            if base[0]=='self' and not d:v=('klass',)
            if base[0]=='type' and d==KLASS_STATIC_FIELDS:v=('blob',base[1])
            if base[0]=='klass' and d==disp+8:v=('info',slot)
        elif i.mnemonic==M.MOV and dst in (R.AL,R.CL,R.DL,R.R8L,R.R9L,R.R10L,R.R11L) and i.op1_kind==K.IMMEDIATE8:v=('bool',i.immediate8)
        elif i.mnemonic==M.LEA and i.memory_base==R.RSP and RegisterExt.is_gpr64(dst):v=('address',d)
        elif i.mnemonic==M.MOVSS and R.XMM0<=dst<=R.XMM3 and i.memory_base==R.RIP:
            literal=_float_literal(il,i);v=('float',literal) if literal is not None else None
        elif base and base[0]=='blob' and ((i.mnemonic==M.MOV and RegisterExt.is_gpr32(dst)) or
                                            (i.mnemonic==M.MOVSD and R.XMM0<=dst<=R.XMM5)):
            v=('tile',base[1],d,MemorySizeExt.size(i.memory_size))
        if v is None:return None
        regs[r]=v
    if used!=slots or regs.get(call.memory_base)!=('klass',) or regs.get(R.RCX)!=('self',):return None
    hidden=8*(len(ps)+1);consumed={(hidden,8)}
    if mem.get((hidden,8))!=('info',slot):return None
    args=[];agg=[];arg_regs=(R.RCX,R.RDX,R.R8,R.R9)
    for pos,p in enumerate(ps,1):
        ty=il.types[p.type];k=key(ty)
        if pos<4:
            r=RegisterExt.full_register(R.XMM0+pos) if k==(0x0c,0) else arg_regs[pos];v=regs.get(r)
        else:
            n=1 if k==(2,0) else 8;consumed.add((8*pos,n));v=mem.get((8*pos,n))
        if v is None:return None
        if k==(0x0c,0) and v[0]=='float':args.append(v[1]);continue
        if k==(2,0) and v[0]=='bool' and v[1] in (0,1):args.append('true' if v[1] else 'false');continue
        if k==(0x0e,0) and v[0]=='str' and pos>=4:
            text=stack_literal(il,seq,len(seq)-4,8*pos,ty)
            if text is None:return None
            args.append(text);continue
        if k!=(0x11,ty[0],0) or v[0]!='address' or agg:return None
        a=v[1];xy=mem.get((a,8));z=mem.get((a+8,4))
        if a<hidden+8 or not xy or xy[0]!='tile' or z!=('tile',xy[1],xy[2]+8,4):return None
        prop=static_value_alias(lift,method,xy[1],xy[2],ty)
        if not prop:return None
        consumed.update(((a,8),(a+8,4)));agg.append(prop);args.append(prop)
    if not agg or consumed!=set(mem):return None
    return ['this.%s(%s);'%(sink.name,', '.join(args))]
