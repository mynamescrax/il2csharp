"""Copy a whole sret at its actual packed load, independently of the storage
name reused for later calls. Also park the receiver of a paired read/write
when the *same reaching field load* supplies both instance calls."""
import re

from il2cpp.array_origin import _definitions,_graph
from il2cpp.closed_lookup import _receiver
from il2cpp.csharp import source_field_name
from il2cpp.equivalent_binary import _amd64
from il2cpp.expr import Expr,acc_get
from il2cpp.names import safe_ident
from il2cpp.prelude import HAVE_ICED
from il2cpp.shared_field import reference_field_at
from il2cpp.simd_getter import _float4,_packed_return
from il2cpp.text import reg_name,sdisp

if HAVE_ICED:
    from iced_x86 import InstructionInfoFactory,MemorySizeExt,Mnemonic as M,OpAccess as A,Register as R,RegisterExt as RX,OpKind as K
    _INFO=InstructionInfoFactory()


def _whole_uses(lift,load,by,succ):
    """Do not turn a later partial XY spill into a whole struct assignment.
    Only complete, uninterpreted stack transfers while these bytes are live."""
    reg=RX.full_register(load.op0_register);work=list(succ[load.ip]);seen=set();stored=False
    while work:
        ip=work.pop()
        if ip in seen:continue
        if len(seen)>=256:return False
        seen.add(ip);i=by[ip];uses=[u for u in _INFO.info(i).used_registers() if RX.full_register(u.register)==reg]
        if uses:
            if (len(uses)==1 and uses[0].access==A.WRITE and i.mnemonic in (M.MOVAPS,M.MOVUPS,M.MOVDQA) and
                    i.op0_register==load.op0_register and i.op1_kind==K.MEMORY and i.memory_base==R.RSP and
                    i.memory_index==R.NONE and not i.has_segment_prefix):continue
            if (i.mnemonic not in (M.MOVDQA,M.MOVAPS,M.MOVUPS) or i.op0_kind!=K.MEMORY or i.op1_register!=load.op0_register or
                    i.memory_base!=R.RSP or i.memory_index!=R.NONE or i.has_segment_prefix or MemorySizeExt.size(i.memory_size)!=16):return False
            stored=True
        if i.is_call_near:
            va=i.near_branch_target
            if lift._named_raise_throw(va,lift._call_name(va))=='System.NullReferenceException':continue
            if not lift.il.addr_candidates.get(va):return False
        if not succ[ip]:return False
        work.extend(succ[ip])
    return stored


def _accessor(lift,i):
    il=lift.il;ids=il.addr_candidates.get(i.near_branch_target,())
    if len(ids)!=1 or ids[0][0]!='method' or not 0<=ids[0][1]<len(il.meta.methods):return None
    m=il.meta.methods[ids[0][1]];p=lift._accessor_prop(m.index)
    if (not p or p[2] or m.addr!=i.near_branch_target or m.is_static or m.flags&0x40 or m.flags&7!=6 or
            m.generic_container!=-1 or not 0<=m.return_type<len(il.types)):return None
    rt=il.types[m.return_type];params=il.meta.method_params(m)
    if p[0]=='get' and m.param_count==0 and il.returns_sret(rt):return m,p,R.RDX,rt
    if (p[0]=='set' and m.param_count==1 and len(params)==1 and il._closed_type_key(rt)==(1,0) and
            0<=params[0].type<len(il.types)):return m,p,R.RCX,il.types[params[0].type]


def copied_values(lift,method,td,blocks,pads):
    il=lift.il;fields={};loads={};copy=[];sites=[]
    if (not HAVE_ICED or pads or method.is_static or td.is_valuetype or td.generic_container!=-1 or method.generic_container!=-1 or
            not 0<=method.return_type<len(il.types) or il._closed_type_key(il.types[method.return_type])!=(1,0) or
            not _amd64(getattr(il,'bin',None)) or il.meta.version!=31):return fields,loads
    # Do not scan whole-program registrations. First find an actual 16-byte
    # read of the echo into a nonvolatile register in this body.
    for b in blocks:
        for j,load in enumerate(b.insns):
            if load.mnemonic!=M.MOVUPS or not _packed_return(load) or not R.XMM6<=load.op0_register<=R.XMM15:continue
            n=j-1
            if n>=0:
                gap=b.insns[n]
                if ((gap.mnemonic==M.MOV and RX.is_gpr64(gap.op0_register) and gap.op1_kind==K.MEMORY) or
                        gap.mnemonic==M.XOR and gap.op0_register==gap.op1_register==R.ECX):
                    if gap.op0_register in (R.RAX,R.RSP,R.RBP) or gap.has_segment_prefix:continue
                    n-=1
            if n<0 or not b.insns[n].is_call_near:continue
            call=b.insns[n];ty=_float4(lift,call);sig=_accessor(lift,call)
            if ty and sig and sig[1][0]=='get':copy.append((call,load,ty,b.insns[n:j+1]))
    if not copy:return fields,loads
    seq=[i for b in blocks for i in b.insns];by={i.ip:i for i in seq};g=_graph(il,seq,chained=True,nested_chains=True)
    if not g or seq[0].ip!=method.addr:return fields,loads
    pred,succ=g
    for call,load,ty,w in copy:
        if all(a.next_ip==b.ip and pred[b.ip]==[a.ip] for a,b in zip(w,w[1:])) and _whole_uses(lift,load,by,succ):loads[load.ip]=call.ip,ty
    if not loads:return fields,loads
    for i in seq:
        if not i.is_call_near:continue
        s=_accessor(lift,i)
        if not s:continue
        md,p,r,ty=s;key=il._closed_type_key(ty)
        if not key or key[0]!=0x11 or key[-1] or not il.returns_sret(ty):continue
        defs=_definitions(by,pred,method.addr,i.ip,r)
        if len(defs)!=1:continue
        pos,reg=defs.pop();load=by[pos]
        if (load.mnemonic!=M.MOV or load.op0_register!=reg or reg not in (R.RBX,R.RSI,R.RDI,R.R12,R.R13,R.R14,R.R15) or
                load.op1_kind!=K.MEMORY or not RX.is_gpr64(load.memory_base) or load.memory_index!=R.NONE or load.has_segment_prefix or
                not _receiver(il,method,by,pred,pos,td.index,initial=load.memory_base,this_only=True)):continue
        row=reference_field_at(il,td.index,sdisp(load.memory_displacement))
        if not row or row[0]!=td.index or row[2][0]!=md.declaring:continue
        sites.append((pos,p[0],p[1],key,row))
    get={(ip,name,key) for ip,kind,name,key,row in sites if kind=='get'}
    for ip,kind,name,key,row in sites:
        if kind=='set' and (ip,name,key) in get:fields[ip]='this.'+safe_ident(source_field_name(il,row[1])),row[2]
    return fields,loads


def bind_value(lift,ins,plan):
    producer,ty=plan;echo=dict.get(lift.regs,'RAX')
    if (not echo or getattr(lift,'_last_sret',None)!=(producer,echo) or echo.kind!='ptr' or not re.fullmatch(r'&t\d+',echo.text) or
            getattr(echo,'_stack_offset',None) is None or echo.ty!=ty or lift.slot_types.get(echo.text[1:])!=ty):return False
    src=echo.text[1:];frag=lift._aggregate_load(ins);parts=getattr(frag,'_parts',None)
    layout=lift.il.instance_field_chain(ty[0]);wanted=[(k*4,src+'.'+layout[16+k*4][0],0,4) for k in range(4)]
    if not parts or [(lo,val.text,off,n) for lo,val,off,n in parts]!=wanted:return False
    name=lift.new_var();params={safe_ident(p.name) for p in lift.meta.method_params(lift._current_method)}
    while name in params:name=lift.new_var()
    lift._var_types[name]=lift._type_hints[name]=ty
    lift.emit(ins.ip,f'var {name} = {acc_get(echo.text[1:])};',None)
    # Keep the original packed display and four dword fragments. Publishing
    # the entire struct as the printable XMM/stack value widens a later
    # MOVSD reload/store; only change which evaluation supplies each lane.
    value=Expr(frag.text,frag.ty,'float')
    value._parts=[(lo,Expr(name+v.text[len(src):],v.ty,v.kind),off,n) for lo,v,off,n in parts]
    lift.regs[reg_name(ins.op0_register)]=value;return True
