"""A normal invocation with a discarded result just before a void epilogue.

Bind the effect at the CALL, before RET can count a phantom result use.
Require the actual argument setup; knowing that RAX dies proves neither
the receiver nor the width of outgoing stack arguments.
"""
from il2cpp.array_origin import _graph
from il2cpp.awaiter import _unused_return
from il2cpp.closed_lookup import _receiver
from il2cpp.equivalent_binary import _amd64
from il2cpp.prelude import HAVE_ICED
from il2cpp.stack_local_frame import stack_local_frame, _saves, _epilogue
from bisect import bisect_right
from struct import pack
from il2cpp.names import safe_ident

if HAVE_ICED:
    from iced_x86 import Mnemonic as M, OpKind as K, Register as R, MemorySizeExt as MS, RegisterExt as RX
    from il2cpp.array_origin import _INFO, _WRITES


def _terminal_frame(il,seq,by,pred,site,block,n):
    """The terminal site must use the root frame. A path-local saved GPR
    in an earlier chained region need not be popped in this epilogue."""
    base=il.bin.image_base;starts=il._eh4_begins;root=bisect_right(starts,seq[0].ip-base)-1
    loc=bisect_right(starts,site-base)-1
    if root<0 or loc<root:return False
    row=il._eh4_entries[root];cur=il._eh4_entries[loc]
    if row[0]+base!=seq[0].ip or not cur[0]+base<=site<cur[1]+base or block.insns[-1].next_ip>cur[1]+base:return False
    if loc!=root:
        raw=il.bin.read(base+cur[2],16)
        if raw!=b'\x21\x00\x00\x00'+pack('<III',*row):return False
    ui=base+row[2];h=il.bin.read(ui,4);k=next((j for j,i in enumerate(seq[:32]) if i.mnemonic==M.SUB and i.op0_register==R.RSP),None)
    if (k is None or not h or len(h)!=4 or h[0]!=1 or h[3] or seq[k].op1_kind not in (K.IMMEDIATE8TO64,K.IMMEDIATE32TO64)):return False
    saves=_saves(seq,k,il.bin.read(ui,4+2*h[2]) or b'')
    if not saves or _epilogue(block.insns,len(block.insns)-1,saves[0],saves[3],saves[4])!=n+1:return False
    seen=set();todo=[site]
    while todo:
        ip=todo.pop()
        if ip in seen:continue
        if len(seen)>2048 or not pred[ip]:return False
        seen.add(ip)
        for p in pred[ip]:
            if p==seq[k].ip:continue
            i=by[p]
            if not i.is_call_near and any(u.access in _WRITES and RX.full_register(u.register)==R.RSP for u in _INFO.info(i).used_registers()):return False
            todo.append(p)
    return True


def _constant_arguments(lift,callee,seq,frame):
    # Small static wrappers with four dword register arguments and a fifth
    # at +32; the hidden MethodInfo is a *separate* qword at +40.
    il=lift.il;ps=il.meta.method_params(callee)
    if not callee.is_static or callee.param_count!=len(ps) or len(ps)!=5 or len(seq)!=6 or frame[0]<48:return None
    regs=(R.ECX,R.EDX,R.R8D,R.R9D);values={}
    for i in seq:
        if i.has_segment_prefix or i.has_lock_prefix:return None
        if i.mnemonic==M.XOR and i.op0_kind==i.op1_kind==K.REGISTER and i.op0_register==i.op1_register and i.op0_register in regs:
            key=regs.index(i.op0_register);v=0
        elif i.mnemonic==M.MOV and i.op0_register in regs and i.op1_kind==K.IMMEDIATE32:
            key=regs.index(i.op0_register);v=i.immediate32
        elif (i.mnemonic==M.MOV and i.op0_kind==K.MEMORY and i.memory_base==R.RSP and i.memory_index==R.NONE and
              (i.memory_displacement,MS.size(i.memory_size),i.op1_kind) in ((32,4,K.IMMEDIATE32),(40,8,K.IMMEDIATE32TO64))):
            key=4 if i.memory_displacement==32 else 5;v=i.immediate(1)
        else:return None
        if key in values:return None
        values[key]=v
    if set(values)!=set(range(6)) or values[5]:return None
    args=[]
    for j,p in enumerate(ps):
        if not 0<=p.type<len(il.types):return None
        ty=il.types[p.type];key=il._closed_type_key(ty);v=values[j];n=v if v<1<<31 else v-(1<<32)
        if key==(8,0):args.append(str(n));continue
        if not key or key[0]!=0x11 or key[-1] or not 0<=ty[0]<len(il.meta.typedefs):return None
        td=il.meta.typedefs[ty[0]];members=il.enum_members(td.index)
        if (not td.is_enum or td.generic_container!=-1 or il.value_type_size(td.index)!=4 or not members or n not in members):return None
        args.append((il.type_name(ty),members[n]))
    return args


def terminal_effects(lift,method,td,blocks,pads):
    il=lift.il;out={}
    if (not HAVE_ICED or pads or not _amd64(getattr(il,'bin',None)) or il.meta.version!=31 or
            td.generic_container!=-1 or method.generic_container!=-1 or not 0<=method.return_type<len(il.types) or
            il._closed_type_key(il.types[method.return_type])!=(1,0)):return out
    sites=[]
    for b in blocks:
        if not b.insns or b.insns[-1].mnemonic!=M.RET or b.insns[-1].op_count or b.insns[-1].stack_pointer_increment!=8:continue
        n=len(b.insns)-2
        while n>=0 and b.insns[n].mnemonic==M.POP:n-=1
        if n<=0 or b.insns[n].mnemonic!=M.ADD or b.insns[n].op0_register!=R.RSP or not b.insns[n-1].is_call_near:continue
        c=b.insns[n-1];ids=il.addr_candidates.get(c.near_branch_target,())
        if len(ids)!=1 or ids[0][0]!='method' or not 0<=ids[0][1]<len(il.meta.methods):continue
        m=il.meta.methods[ids[0][1]]
        if (m.addr!=c.near_branch_target or m.generic_container!=-1 or m.flags&(0x40|0x800) or not m.name.isidentifier() or
                safe_ident(m.name)!=m.name or m.name.startswith(('get_','set_','op_','add_','remove_')) or
                not 0<=m.return_type<len(il.types) or il.meta.typedefs[m.declaring].generic_container!=-1):continue
        key=il._closed_type_key(il.types[m.return_type])
        if m.is_static and m.param_count==5 and key==(2,0) or (not m.is_static and not m.param_count and
                m.declaring==td.index and key and key[0]==0x12 and not key[-1]):sites.append((b,n-1,m))
    if not sites:return out
    seq=[i for b in blocks for i in b.insns];g=_graph(il,seq,chained=True)
    if not g or seq[0].ip!=method.addr:return out
    by={i.ip:i for i in seq};pred,_=g
    for b,n,m in sites:
        c=b.insns[n]
        if not _unused_return(lift,c.next_ip):continue
        if m.is_static:
            frame=stack_local_frame(lift,method,blocks,pads)
            if (b.bid!=0 or len(blocks)!=1 or n!=7 or b.insns[0].mnemonic!=M.SUB or b.insns[0].op0_register!=R.RSP or
                    not frame or il.meta.typedefs[m.declaring].declaring!=-1 or m.flags&7!=6):continue
            args=_constant_arguments(lift,m,b.insns[1:n],frame)
            if args is not None:out[c.ip]=m.index,args
        else:
            if n<2:continue
            # This call has no stack arguments; earlier byref homes elsewhere
            # in the caller need not be renamed. Check the actual prologue,
            # outstanding RSP depth and this epilogue against the unwind row.
            if not _terminal_frame(il,seq,by,pred,c.ip,b,n):continue
            z,r=b.insns[n-2:n]
            if (z.mnemonic==M.XOR and z.op0_register==z.op1_register==R.EDX and r.mnemonic==M.MOV and r.op0_register==R.RCX and
                    z.next_ip==r.ip and r.next_ip==c.ip and pred[r.ip]==[z.ip] and pred[c.ip]==[r.ip] and
                    _receiver(il,method,by,pred,c.ip,m.declaring,this_only=True)):
                out[c.ip]=m.index,None
    return out


def terminal_statement(lift,plan,mi,call,receiver):
    target,args=plan
    if mi!=target:return False
    m=lift.meta.methods[target]
    if args is None:
        if (not receiver or receiver._unk or receiver.text!='this' or lift.il._closed_type_key(receiver.ty)!=(0x12,m.declaring,0) or
                call!='this.'+m.name+'()'):return False
    else:
        short=lift.meta.typedefs[m.declaring].name; full=lift.il.typedef_full(m.declaring)
        if not any(call.startswith(n+'.'+m.name+'(') for n in {short,full}) or not call.endswith(')'):return False
        printed=call.split('(',1)[1][:-1].split(', ')
        if len(printed)!=len(args):return False
        for text,arg in zip(printed,args):
            if isinstance(arg,str):
                if text!=arg:return False
            else:
                ty,member=arg
                if text not in (ty+'.'+member,ty.rsplit('.',1)[-1]+'.'+member):return False
    # _flush_pending_calls checks statement text for a previous materialized
    # use. Do not let this separate invocation conceal an older pending one.
    if any(e is not None and e.text and e.text in call for e,_,_ in getattr(lift,'_pending_calls',())):return False
    lift.emit(lift._cur_ip,call+';',None)
    return True
