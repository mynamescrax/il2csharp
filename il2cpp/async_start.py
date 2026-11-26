"""Recover a complete Win64 async-void kickoff from its typed stack writes.

The shared Start address is not an identity. Its closed MethodRef, the two
addresses passed by reference, and the Create result copied between them
must all agree with the generated state machine's metadata layout.
"""
import re

from il2cpp.awaiter import _spec_entry
from il2cpp.binary import PE
from il2cpp.metadata import source_params
from il2cpp.names import safe_ident
from il2cpp.prelude import HAVE_ICED
from il2cpp.sret_copy import _own_field

if HAVE_ICED:
    from iced_x86 import Mnemonic as M, OpKind as K, Register as R, RegisterExt
    _SAVED={R.RBX,R.RBP,R.RDI,R.RSI,R.R12,R.R13,R.R14,R.R15}


def _rr(i,m,dst,src): return i.mnemonic==m and i.op0_register==dst and i.op1_register==src


def _addr(i,dst): return i.mnemonic==M.LEA and i.op0_register==dst and i.memory_base==R.RSP


def _call(i,va): return i.mnemonic==M.CALL and i.op0_kind==K.NEAR_BRANCH64 and i.near_branch_target==va


def _adjust(i,m):
    if i.mnemonic==m and i.op0_register==R.RSP and i.op1_kind in (K.IMMEDIATE8TO64,K.IMMEDIATE32TO64):
        return i.immediate(1)


def _frame(pro,epi):
    """One fixed allocation, optional home saves/push, exactly reversed."""
    if not pro or len(epi)<2 or epi[-1].mnemonic!=M.RET or epi[-1].op_count: return None
    size=_adjust(pro[-1],M.SUB)
    if size is None or not 32<=size<=4096:return None
    pro=pro[:-1]; epi=epi[:-1];saved=set(); pushed=None
    if pro and pro[-1].mnemonic==M.PUSH:
        pushed=pro[-1].op0_register
        if pushed not in _SAVED or epi[-1].mnemonic!=M.POP or epi[-1].op0_register!=pushed:return None
        pro=pro[:-1];epi=epi[:-1]
    depth=size+8*int(pushed is not None)
    if depth%16!=8 or not epi:return None
    base=R.RSP;bias=depth
    if _addr(epi[0],R.R11):
        if epi[0].memory_displacement!=size or not _rr(epi[-1],M.MOV,R.RSP,R.R11):return None
        base=R.R11;bias=depth-size;epi=epi[1:-1]
    elif _adjust(epi[-1],M.ADD)==size: epi=epi[:-1]
    else:return None
    if len(pro)!=len(epi):return None
    homes=set()
    for i,r in zip(pro,epi):
        reg=i.op1_register;off=i.memory_displacement
        if (i.mnemonic!=M.MOV or i.memory_base!=R.RSP or reg not in _SAVED or reg in saved or reg==pushed or
                off not in (8,16,24,32) or off in homes or r.mnemonic!=M.MOV or r.op0_register!=reg or
                r.memory_base!=base or r.memory_displacement!=bias+off):return None
        saved.add(reg);homes.add(off)
    if pushed is not None:saved.add(pushed)
    return size,saved


def _closed_start(il,method,td,slot,start,create):
    usage=il.decode_slot(slot) or {}; si=usage.get('idx',-1)
    if usage.get('kind')!=6 or not 0<=si<len(il.method_specs):return None
    mi,ci,gi=il.method_specs[si];actual=il._method_spec_type_args(gi)
    if ci!=-1 or not 0<=mi<len(il.meta.methods) or not actual or len(actual)!=1:return None
    ty=actual[0];key=il._closed_type_key
    if not ty or key(ty)!=(0x11,ty[0],0) or not 0<=ty[0]<len(il.meta.typedefs):return None
    sm=il.meta.typedefs[ty[0]];m=il.meta.methods[mi];bt=il.meta.typedefs[m.declaring];ps=il.meta.method_params(m)
    if (not sm.is_valuetype or sm.generic_container!=-1 or il._nested_owner(sm.index)!=td.index or
            not re.fullmatch('<'+re.escape(method.name)+r'>d__\d+',sm.name) or
            not bt.is_valuetype or bt.generic_container!=-1 or il.typedef_full(bt.index)!='System.Runtime.CompilerServices.AsyncVoidMethodBuilder' or
            m.name!='Start' or m.is_static or m.flags&7!=6 or m.flags&0x40 or not 0<=m.generic_container<len(il.meta.generic_containers) or
            len(ps)!=1 or m.param_count!=1 or not 0<=ps[0].type<len(il.types) or not 0<=m.return_type<len(il.types) or key(il.types[m.return_type])!=(1,0) or
            _spec_entry(il,si,mi)!=start.near_branch_target):return None
    owner,count,is_method,first=il.meta.generic_containers[m.generic_container];pt=il.types[ps[0].type]
    if ((owner,count,is_method)!=(mi,1,1) or not pt or il._type_enum(pt)!=0x1e or not pt[1]&(1<<29) or pt[0]!=first or
            not any(0<=ii<len(il.types) and il.type_name(il.types[ii])=='System.Runtime.CompilerServices.IAsyncStateMachine'
                    for ii in il.meta.interfaces[sm.interfaces_start:sm.interfaces_start+sm.interfaces_count])):return None
    ids=il.addr_candidates.get(create.near_branch_target,())
    if len(ids)!=1 or ids[0][0]!='method' or not 0<=ids[0][1]<len(il.meta.methods):return None
    factory=il.meta.methods[ids[0][1]]
    if (factory.name!='Create' or factory.addr!=create.near_branch_target or factory.declaring!=bt.index or not factory.is_static or
            factory.flags&7!=6 or factory.param_count or factory.generic_container!=-1 or not 0<=factory.return_type<len(il.types)):return None
    rt=il.types[factory.return_type]
    if key(rt)!=(0x11,bt.index,0) or not il.returns_sret(rt) or il.value_type_size(bt.index)!=32:return None
    return sm,ty,bt,rt


def _covers(tiles,base,width):
    pos=base
    for off,n in sorted(tiles):
        if off!=pos:return False
        pos+=n
    return pos==base+width


def async_void_start(lift,method,td,seq,eh):
    il=lift.il
    if (not HAVE_ICED or eh or not 25<=len(seq)<=96 or method.is_static or td.is_valuetype or method.param_count>3 or
            not isinstance(getattr(il,'bin',None),PE) or not il.bin.is64 or il.meta.version!=31 or
            method.generic_container!=-1 or td.generic_container!=-1 or not 0<=method.return_type<len(il.types) or
            il._closed_type_key(il.types[method.return_type])!=(1,0) or seq[-1].mnemonic!=M.RET):return None
    calls=[k for k,i in enumerate(seq) if i.mnemonic==M.CALL]
    if len(calls)<4 or any(seq[k].op0_kind!=K.NEAR_BRANCH64 for k in calls):return None
    init,create,*barriers,start=calls
    if (not _call(seq[init],lift.rt_init_meta) or any(seq[k].near_branch_target not in lift.rt_wbarrier for k in barriers) or
            seq[0].ip!=method.addr or il.function_extent(method.addr)!=(method.addr,seq[-1].next_ip) or
            any(a.next_ip!=b.ip for a,b in zip(seq,seq[1:])) or any(i.has_segment_prefix or i.has_lock_prefix or i.has_rep_prefix or
            i.has_repne_prefix or i.memory_index!=R.NONE for i in seq)):return None
    cmp_pos=next((k for k,i in enumerate(seq[:init]) if i.mnemonic==M.CMP),-1)
    if cmp_pos<0 or cmp_pos+3>init or init+2>=create:return None
    frame=_frame(seq[:cmp_pos],seq[start+1:])
    if not frame:return None
    size,saved=frame;cmp=seq[cmp_pos];branch,load,_,ready=seq[init-2:init+2];slot=load.ip_rel_memory_address
    if (cmp.memory_base!=R.RIP or cmp.memory_size!=1 or cmp.op1_kind!=K.IMMEDIATE8 or cmp.immediate8 or branch.mnemonic!=M.JNE or
            branch.near_branch_target!=seq[init+2].ip or load.mnemonic!=M.LEA or load.op0_register!=R.RCX or load.memory_base!=R.RIP or
            ready.mnemonic!=M.MOV or ready.memory_base!=R.RIP or ready.op1_kind!=K.IMMEDIATE8 or ready.immediate8!=1 or
            cmp.ip_rel_memory_address!=ready.ip_rel_memory_address):return None
    proof=_closed_start(il,method,td,slot,seq[start],seq[create])
    if not proof:return None
    sm,ty,bt,rt=proof; width=il.value_type_size(sm.index)
    # Parameter names/types describe entry slots only. Track actual full-width
    # moves into callee-saves before the first metadata call can clobber them.
    inputs={R.RCX:('this',(0x12,td.index,0))}; regs={}; used=set()
    params=source_params(il.meta,method)
    if len(params)!=method.param_count:return None
    for p,gpr,dword in zip(params,(R.RDX,R.R8,R.R9),(R.EDX,R.R8D,R.R9D)):
        if not 0<=p.type<len(il.types):return None
        key=il._closed_type_key(il.types[p.type]); name=safe_ident(p.name)
        if not key or key[0] not in (8,0x0e,0x12) or key[-1] or not name.isidentifier():return None
        inputs[dword if key==(8,0) else gpr]=(name,key)
    for i in seq[cmp_pos+1:init-2]:
        src,dst=i.op1_register,i.op0_register
        if (i.mnemonic!=M.MOV or src not in inputs or src in used or dst==R.NONE or RegisterExt.full_register(dst) not in saved or
                any(RegisterExt.full_register(r)==RegisterExt.full_register(dst) for r in regs) or RegisterExt.size(src)!=RegisterExt.size(dst)):return None
        used.add(src);regs[dst]=inputs[src]

    # Find the actual byref borrows, not just two equal-looking local names.
    k=barriers[-1]+1
    if not 4<=start-k<=7:return None
    spec,machine,builder=seq[k:k+3]
    if (spec.mnemonic!=M.MOV or spec.op0_register!=R.R8 or spec.memory_base!=R.RIP or spec.ip_rel_memory_address!=slot or
            not _addr(machine,R.RDX) or not _addr(builder,R.RCX)):return None
    home=machine.memory_displacement; field=builder.memory_displacement; off=field-home+16
    bf=_own_field(il,sm,off,32); bk=il._closed_type_key(rt)
    if (not bf or bf[0]!='this.<>t__builder' or il._closed_type_key(bf[1])!=bk or bf[1][1]&0x27!=6 or
            not width or width<=0 or not 32<=home<=size-width or not home<=field<=home+width-32):return None
    init_seq=seq[init+2:create]
    if len(init_seq)<4 or not _rr(init_seq[0],M.XORPS,R.XMM0,R.XMM0) or not _addr(init_seq[1],R.RCX):return None
    buf=init_seq[1].memory_displacement
    if not 32<=buf<=size-32 or not (buf+32<=home or home+width<=buf):return None
    idx=2;clear_rax=_rr(init_seq[idx],M.XOR,R.EAX,R.EAX);idx+=int(clear_rax)
    if not _rr(init_seq[idx],M.XOR,R.EDX,R.EDX):return None
    tiles=[]
    for i in init_seq[idx+1:]:
        if i.memory_base!=R.RSP:return None
        if i.mnemonic==M.MOVUPS and i.op1_register==R.XMM0:n=16
        elif clear_rax and i.mnemonic==M.MOV and i.op1_register==R.RAX:n=8
        else:return None
        tiles.append((i.memory_displacement,n))
    if not _covers(tiles,home,width):return None
    copy=seq[create+1:barriers[0]]
    if (len(copy)!=6 or not _rr(copy[0],M.XOR,R.EDX,R.EDX) or not _addr(copy[1],R.RCX) or copy[1].memory_displacement!=field):return None
    for n,(a,b) in enumerate(zip(copy[2::2],copy[3::2])):
        if (a.mnemonic!=M.MOVUPS or not R.XMM0<=a.op0_register<=R.XMM5 or a.memory_base!=R.RAX or a.memory_displacement!=16*n or
                b.mnemonic!=M.MOVUPS or b.op1_register!=a.op0_register or b.memory_base!=R.RSP or b.memory_displacement!=field+16*n):return None

    writes=[('<>t__builder',il.typedef_full(bt.index)+'.Create()')];seen={bf[0]}
    def capture(store,ref):
        reg=store.op1_register
        if store.mnemonic!=M.MOV or store.memory_base!=R.RSP or reg not in regs:return False
        val,key=regs[reg]; n=8 if ref else 4; dest=store.memory_displacement
        if (key!=(8,0))!=ref or not home<=dest<=home+width-n:return False
        row=_own_field(il,sm,dest-home+16,n)
        if not row or row[0] in seen or row[1][1]&0x27!=6 or il._closed_type_key(row[1])!=key:return False
        seen.add(row[0]);writes.append((row[0][5:],val));return True
    for prev,nxt in zip(barriers,barriers[1:]):
        group=seq[prev+1:nxt]
        if len(group)!=3:return None
        arg,store,ptr=group
        if (not _rr(arg,M.MOV,R.RDX,store.op1_register) or not _addr(ptr,R.RCX) or ptr.memory_displacement!=store.memory_displacement or
                not capture(store,True)):return None
    if not all(capture(i,False) for i in seq[k+3:start-1]):return None
    state=seq[start-1];row=_own_field(il,sm,state.memory_displacement-home+16,4)
    if (state.mnemonic!=M.MOV or state.memory_base!=R.RSP or state.op1_kind!=K.IMMEDIATE32 or state.immediate32!=0xffffffff or
            not home<=state.memory_displacement<=home+width-4 or not row or row[0]!='this.<>1__state' or row[0] in seen or
            row[1][1]&0x27!=6 or il._closed_type_key(row[1])!=(8,0)):return None
    name='stateMachine';names={v[0] for v in inputs.values()}
    while name in names:name+='Local'
    tn=il.type_name(ty); writes.append(('<>1__state','-1'))
    return ([f'{tn} {name} = default;']+[f'{name}.{member} = {value};' for member,value in writes]+
            [f'{name}.<>t__builder.Start<{tn}>(ref {name});'])
