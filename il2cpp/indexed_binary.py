"""Reassemble two 12-byte by-value arguments at an indexed getter consumer.
One is the fresh sret echo. The other survives a loop in two nonvolatile
registers; require the same earlier getter result on every incoming path."""
import re

from il2cpp.captured_home import _normal_predecessors
from il2cpp.copied_getter import _copies_prefix, _sp_offset
from il2cpp.expr import Expr, _R4_TY
from il2cpp.indexed_particle import _spilled_setup
from il2cpp.module_curve import fixed_frame
from il2cpp.names import safe_ident
from il2cpp.prelude import HAVE_ICED
from il2cpp.x64 import VOLATILE

if HAVE_ICED:
    from iced_x86 import InstructionInfoFactory, Mnemonic as M, OpAccess, OpKind as K, Register as R, RegisterExt
    _INFO=InstructionInfoFactory();_WRITE={OpAccess.WRITE,OpAccess.READ_WRITE,OpAccess.COND_WRITE,OpAccess.READ_COND_WRITE}


def _reaching(seq,pred,ip,reg):
    """Stop at the last definition per path, including the loop back edge."""
    if reg not in (R.RBX,R.RBP,R.RSI,R.RDI,R.R12,R.R13,R.R14,R.R15) and not R.XMM6<=reg<=R.XMM15:return None
    seen=set();found=set();work=list(pred[ip])
    while work:
        p=work.pop()
        if p in seen:continue
        seen.add(p);i=seq.get(p)
        if i is None or len(seen)>1024:return None
        if any(u.access in _WRITE and RegisterExt.full_register(u.register)==RegisterExt.full_register(reg) for u in _INFO.info(i).used_registers()):
            found.add(p)
        elif not pred[p]:return None
        else:work.extend(pred[p]-seen)
    if len(found)==1:return seq[found.pop()]


def _saved_pair(byip,pred,lo,hi):
    x=_reaching(byip,pred,lo.ip,lo.op1_register);z=_reaching(byip,pred,hi.ip,RegisterExt.full_register(hi.op1_register))
    if (not x or not z or x.mnemonic!=M.MOVSD or x.op0_register!=lo.op1_register or z.mnemonic!=M.MOV or z.op0_register!=hi.op1_register or
            not all(i.op1_kind==K.MEMORY and i.memory_base==R.RAX and i.memory_index==R.NONE and not i.has_segment_prefix for i in (x,z)) or
            x.memory_displacement or z.memory_displacement!=8 or pred[z.ip]!={x.ip} or x.next_ip!=z.ip):return None
    p=x.ip
    for _ in range(8):
        if len(pred[p])!=1:return None
        i=byip[next(iter(pred[p]))]
        if i.next_ip!=p:return None
        if i.mnemonic==M.CALL and i.op0_kind==K.NEAR_BRANCH64:return i,x
        if (i.mnemonic not in (M.MOV,M.LEA) or i.op0_kind!=K.REGISTER or not RegisterExt.is_gpr(i.op0_register) or
                RegisterExt.full_register(i.op0_register)==R.RAX):return None
        p=i.ip


def _echo_copy(seq,frame):
    """Return destination offsets of the first and second arguments. Require
    every byte of the first to be copied from the *echoed* sret address."""
    zero,other,first,lo,hi,store,tail,call=seq
    if (any(i.has_segment_prefix or i.has_lock_prefix or i.memory_index!=R.NONE for i in seq) or
            zero.mnemonic!=M.XOR or zero.op0_register!=R.R8D or zero.op1_register!=R.R8D or
            other.mnemonic!=M.LEA or other.op0_register!=R.RDX or first.mnemonic!=M.LEA or first.op0_register!=R.RCX or
            lo.mnemonic!=M.MOVSD or lo.memory_base!=R.RAX or lo.memory_displacement or not R.XMM0<=lo.op0_register<=R.XMM5 or
            hi.mnemonic!=M.MOV or hi.op0_register!=R.EAX or hi.memory_base!=R.RAX or hi.memory_displacement!=8 or
            store.mnemonic!=M.MOVSD or store.op1_register!=lo.op0_register or tail.mnemonic!=M.MOV or tail.op1_register!=R.EAX or
            call.mnemonic!=M.CALL or call.op0_kind!=K.NEAR_BRANCH64):return None
    a,b,c,d=(_sp_offset(i,frame[0]) for i in (first,other,store,tail))
    if None not in (a,b,c,d) and c==a and d==a+8:return a,b


def binary_sites(lift,method,blocks,pads):
    reads={};stores={};uses={};result=reads,stores,uses
    if not HAVE_ICED or pads:return result
    possible=[b.insns for b in blocks if len(b.insns)>=17 and b.insns[0].mnemonic==M.MOVSXD and b.insns[8].mnemonic==M.CALL and
              b.insns[8].op0_kind==K.NEAR_BRANCH64 and _copies_prefix(lift.il,b.insns[8].near_branch_target)]
    if not possible:return result
    frame=fixed_frame(lift,method,blocks,pads,immediate=True,extended_saves=True)
    if not frame:return result
    seq=[i for b in blocks for i in b.insns];byip={i.ip:i for i in seq};pred=_normal_predecessors(seq)
    if not pred or any(a.next_ip!=b.ip for a,b in zip(seq,seq[1:])):return result
    for s in possible:
        if any(pred[b.ip]!={a.ip} for a,b in zip(s[:16],s[1:17])):continue
        copy=_echo_copy(s[9:17],frame)
        if not copy:continue
        setup=s[:8];mul=next((i for i in setup if i.mnemonic==M.IMUL),None);lo=next((i for i in setup if i.mnemonic==M.MOVSD),None)
        hi=next((i for i in setup if i.mnemonic==M.MOV and i.op0_kind==K.MEMORY),None)
        add=next((i for i in setup if i.mnemonic==M.ADD and i.op1_kind==K.REGISTER),None)
        if not mul or mul.op2_kind not in (K.IMMEDIATE8TO64,K.IMMEDIATE32TO64) or not (lo and hi and add) or lo.ip>=hi.ip:continue
        out=_spilled_setup(setup,add.op1_register,s[0].op1_register,mul.immediate(2),frame);a,b=copy
        if out is None or b!=_sp_offset(lo,frame[0]) or not 32<=a<=frame[1]-12:continue
        homes=sorted([out,a,b])
        if any(x+12>y for x,y in zip(homes,homes[1:])):continue
        saved=_saved_pair(byip,pred,lo,hi)
        if not saved or not _copies_prefix(lift.il,saved[0].near_branch_target):continue
        src,read=saved;reads[read.ip]=src.ip;stores[lo.ip]=(hi.ip,src.ip,b);uses[s[9].ip]=(s[8].ip,src.ip,a,s[16].near_branch_target)
    return result


def echo_at(lift,ip):
    echo=dict.get(lift.regs,'RAX')
    if (echo and getattr(lift,'_last_accessor_sret',None)==(ip,echo)==getattr(lift,'_last_sret',None) and echo.kind=='ptr' and re.fullmatch(r'&t\d+',echo.text) and
            getattr(echo,'_stack_offset',None) is not None and echo.ty and lift.slot_types.get(echo.text[1:])==echo.ty and
            lift.il._type_enum(echo.ty)==0x11 and lift.il.value_type_size(echo.ty[0])==12):return Expr(echo.text[1:],echo.ty,'obj')


def store_value(lift,ip,off,value):
    name=lift.slot_var(off);start=lift.rsp_delta+off;lift._kill_stale(name)
    lift.emit(ip,f'{name} = {value.text};',None)
    for a,old in lift.stack_map.items():
        if start<=a<start+12:lift.stack_values.pop(old,None)
    lift._stack_store(start,12,value);lift.stack_values[name]=value


def binary_use(lift,ins,plan,values):
    origin,src,off,target=plan;left=echo_at(lift,origin);right=values.get(src)
    if not left or not right or lift.il._closed_type_key(left.ty)!=lift.il._closed_type_key(right.ty):return False
    from il2cpp.equivalent_binary import equivalent_binary
    md=equivalent_binary(lift,target,left.ty)
    if md is None or md.flags&0x800 or safe_ident(md.name)!=md.name:return False
    store_value(lift,ins.ip,off,left)
    name=lift.new_var();lift._var_types[name]=_R4_TY
    lift.emit(ins.ip,f'var {name} = {lift.il.type_name(left.ty)}.{safe_ident(md.name)}({left.text}, {right.text});',None)
    for r in (*VOLATILE,*('XMM%d'%n for n in range(6))):lift.regs.pop(r,None)
    lift.regs['XMM0']=Expr(name,_R4_TY,'float');lift.flags=None;lift._fresh_unknowns()
    return True
