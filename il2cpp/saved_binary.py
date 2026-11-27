"""Two copied sret operands of an unregistered float(T,T) twin. Resolve
the call without replacing any source load or widening a partial store."""
import re

from il2cpp.array_origin import _graph
from il2cpp.equivalent_binary import equivalent_binary,_amd64
from il2cpp.expr import Expr,_R4_TY
from il2cpp.indexed_binary import _saved_pair
from il2cpp.names import safe_ident
from il2cpp.packed_projection import _field
from il2cpp.prelude import HAVE_ICED
from il2cpp.stack_local_frame import _saves
from il2cpp.text import sdisp
from il2cpp.x64 import VOLATILE

if HAVE_ICED:
    from iced_x86 import InstructionInfoFactory,MemorySizeExt,Mnemonic as M,OpAccess as A,OpKind as K,Register as R,RegisterExt as RX
    _INFO=InstructionInfoFactory();_WR={A.WRITE,A.COND_WRITE,A.READ_WRITE,A.READ_COND_WRITE}


def _frame_at(il,seq,by,pred,site):
    from bisect import bisect_left
    addr=seq[0].ip;rva=addr-il.bin.image_base;j=bisect_left(il._eh4_begins,rva)
    if j==len(il._eh4_begins) or il._eh4_begins[j]!=rva:return None
    begin,end,ui=il._eh4_entries[j]
    if seq[-1].next_ip>il.bin.image_base+end:return None  # this frame proof only checks the root's saves
    ui+=il.bin.image_base;h=il.bin.read(ui,4);n=next((k for k,i in enumerate(seq[:32]) if i.mnemonic==M.SUB and i.op0_register==R.RSP),None)
    if not h or len(h)!=4 or h[0]!=1 or h[3] or n is None or seq[n].op1_kind not in (K.IMMEDIATE8TO64,K.IMMEDIATE32TO64):return None
    f=_saves(seq,n,il.bin.read(ui,4+h[2]*2) or b'')
    if not f:return None
    seen=set();work=[site]
    while work:
        k=work.pop()
        if k in seen:continue
        seen.add(k)
        if len(seen)>1024 or not pred[k]:return None
        for p in pred[k]:
            if p==seq[n].ip:continue
            i=by[p]
            if not i.is_call_near and any(u.access in _WR and RX.full_register(u.register)==R.RSP for u in _INFO.info(i).used_registers()):return None
            work.append(p)
    return f[:3]


def _getter(lift,call):
    il=lift.il;ids=il.addr_candidates.get(call.near_branch_target,())
    if len(ids)!=1 or ids[0][0]!='method' or not 0<=ids[0][1]<len(il.meta.methods):return None
    md=il.meta.methods[ids[0][1]];p=lift._accessor_prop(md.index)
    if (not p or p[0]!='get' or p[2] or md.addr!=call.near_branch_target or md.param_count or md.is_static or md.flags&0x40 or
            md.generic_container!=-1 or not 0<=md.return_type<len(il.types)):return None
    ty=il.types[md.return_type]
    if (ty and il._closed_type_key(ty)==(0x11,ty[0],0) and 0<=ty[0]<len(il.meta.typedefs) and
            il.returns_sret(ty) and il.value_type_size(ty[0])==12):
        td=il.meta.typedefs[ty[0]]
        if td.is_valuetype and not td.is_enum and td.generic_container==-1 and all(_field(il,td,o) for o in (0,4,8)):return ty


def _home(i,r):
    if i.mnemonic==M.LEA and i.op0_register==r and i.memory_base==R.RSP and i.memory_index==R.NONE:return sdisp(i.memory_displacement)


def binary_arguments(lift,method,blocks,pads):
    il=lift.il;reads={};calls={};windows=[]
    if not HAVE_ICED or pads or not _amd64(getattr(il,'bin',None)) or il.meta.version!=31:return reads,calls
    for b in blocks:
        for j in range(10,len(b.insns)):
            call=b.insns[j]
            if call.is_call_near and not il.addr_candidates.get(call.near_branch_target) and b.insns[j-10].is_call_near and b.insns[j-8].mnemonic==M.MOVSD:
                windows.append(b.insns[j-10:j+1])
    if not windows:return reads,calls
    seq=[i for b in blocks for i in b.insns];by={i.ip:i for i in seq};slots={b.insns[-1].ip:tuple(b.switch_targets) for b in blocks if b.switch_targets}
    g=_graph(il,seq,switch_slots=slots)
    if not g or seq[0].ip!=method.addr:return reads,calls
    pred={ip:set(v) for ip,v in g[0].items()}
    for w in windows:
        other,zero,lo,arg2,hi,arg1,xy,z,xy2,z2,call=w
        if (any(i.has_segment_prefix or i.has_lock_prefix or i.memory_index!=R.NONE for i in w) or
                any(a.next_ip!=b.ip or pred[b.ip]!={a.ip} for a,b in zip(w,w[1:])) or zero.mnemonic!=M.XOR or
                zero.op0_register!=zero.op1_register or zero.op0_register!=R.R8D or hi.mnemonic!=M.MOV or not RX.is_gpr32(hi.op1_register) or
                lo.memory_base!=R.RSP or hi.memory_base!=R.RSP or lo.memory_displacement+8!=hi.memory_displacement or
                not R.XMM6<=lo.op1_register<=R.XMM15 or xy.mnemonic!=M.MOVSD or not R.XMM0<=xy.op0_register<=R.XMM5 or
                xy.memory_base!=R.RAX or xy.memory_displacement or z.mnemonic!=M.MOV or z.op0_register!=R.EAX or z.memory_base!=R.RAX or z.memory_displacement!=8 or
                xy2.mnemonic!=M.MOVSD or xy2.op1_register!=xy.op0_register or z2.mnemonic!=M.MOV or z2.op1_register!=R.EAX or
                xy2.memory_base!=R.RSP or z2.memory_base!=R.RSP or xy2.memory_displacement+8!=z2.memory_displacement):continue
        a,b=_home(arg1,R.RCX),_home(arg2,R.RDX)
        if a is None or b is None or (a,b)!=(lo.memory_displacement,xy2.memory_displacement):continue
        pair=_saved_pair(by,pred,lo,hi);ty=_getter(lift,other)
        if not pair or not ty or il._closed_type_key(_getter(lift,pair[0]))!=il._closed_type_key(ty):continue
        # No copied echo address parked in another register before the
        # two loads. Fresh managed snapshots represent values, not aliases.
        if any(i.op1_kind==K.REGISTER and i.op1_register==R.RAX or i.memory_base==R.RAX for i in
               seq if pair[0].ip<i.ip<pair[1].ip):continue
        # Both hidden sret destinations are plain stack LEAs. Only accept
        # four distinct, private ranges outside the shadow and unwind saves.
        homes=[]
        for src in (pair[0],other):
            incoming=pred[src.ip];prev=by[next(iter(incoming))] if len(incoming)==1 else None
            if prev is None or prev.next_ip!=src.ip or _home(prev,R.RCX) is None:break
            homes.append(_home(prev,R.RCX))
        if len(homes)!=2:continue
        frame=_frame_at(il,seq,by,pred,call.ip)
        if not frame:continue
        size,depth,saves=frame;ranges=sorted([a,b,*homes]);
        if (any(p%16 or not 32<=p<=size-12 or any(q<p+12 and p<q+n for q,n in saves) for p in ranges) or
                any(p+12>q for p,q in zip(ranges,ranges[1:]))):continue
        target=equivalent_binary(lift,call.near_branch_target,ty)
        if not target or safe_ident(target.name)!=target.name:continue
        names=tuple(_field(il,il.meta.typedefs[ty[0]],o) for o in (0,4,8))
        reads[pair[1].ip]=(pair[0].ip,ty,homes[0]-depth);reads[zero.ip]=(other.ip,ty,homes[1]-depth)
        calls[call.ip]=(target.name,ty,names,((pair[0].ip,'RCX',a-depth),(other.ip,'RDX',b-depth)))
    return reads,calls


def save_echo(lift,plan,values):
    ip,ty,home=plan;e=dict.get(lift.regs,'RAX')
    values.pop(ip,None)
    if (e and lift._last_sret==(ip,e) and e.kind=='ptr' and re.fullmatch(r'&t\d+',e.text) and
            getattr(e,'_stack_offset',None)==home and e.ty==ty and lift.slot_types.get(e.text[1:])==ty):values[ip]=e.text[1:]


def call_binary(lift,ins,plan,values):
    name,ty,fields,args=plan;operands=[];ctx=dict.get(lift.regs,'R8')
    if not ctx or ctx.text!='0':return False
    for origin,reg,home in args:
        p=dict.get(lift.regs,reg);v=values.get(origin)
        if not v or getattr(p,'_stack_offset',None)!=home:return False
        for k,field in enumerate(fields):
            piece=lift._stack_piece(home+4*k,4,_R4_TY)
            if not piece or piece._unk or piece.text!=v+'.'+field:return False
        operands.append(v)
    result=lift.new_var();lift._var_types[result]=lift._type_hints[result]=_R4_TY
    lift.emit(ins.ip,'var %s = %s.%s(%s);'%(result,lift.il.type_name(ty),name,', '.join(operands)),None)
    for r in (*VOLATILE,*(f'XMM{i}' for i in range(6))):lift.regs.pop(r,None)
    lift.flags=None;lift._fresh_unknowns();lift.regs['XMM0']=Expr(result,_R4_TY,'float');return True
