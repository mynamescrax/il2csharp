"""Recover Win64 async kickoffs from their typed stack writes.

The shared Start address is not an identity. Its closed MethodRef, the two
addresses passed by reference, and the Create result copied between them
must all agree with the generated state machine's metadata layout.
"""
from il2cpp.awaiter import _spec_entry
from il2cpp.binary import PE
from il2cpp.metadata import source_params
from il2cpp.names import safe_ident
from il2cpp.prelude import HAVE_ICED
from il2cpp.sret_copy import _own_field
from il2cpp.text import sdisp
from il2cpp.x64 import KLASS_INITIALIZED

if HAVE_ICED:
    from iced_x86 import Decoder, MemorySizeExt, Mnemonic as M, OpKind as K, Register as R, RegisterExt
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


def _start_binding(il,method,td,slot,start):
    usage=il.decode_slot(slot) or {}; si=usage.get('idx',-1)
    if usage.get('kind')!=6 or not 0<=si<len(il.method_specs):return None
    mi,ci,gi=il.method_specs[si];actual=il._method_spec_type_args(gi)
    if not 0<=mi<len(il.meta.methods) or not actual or len(actual)!=1:return None
    ty=actual[0];key=il._closed_type_key
    if not ty or key(ty)!=(0x11,ty[0],0) or not 0<=ty[0]<len(il.meta.typedefs):return None
    sm=il.meta.typedefs[ty[0]];m=il.meta.methods[mi];bt=il.meta.typedefs[m.declaring];ps=il.meta.method_params(m)
    if (not sm.is_valuetype or sm.generic_container!=-1 or il._nested_owner(sm.index)!=td.index or
            not bt.is_valuetype or
            m.name!='Start' or m.is_static or m.flags&7!=6 or m.flags&0x40 or not 0<=m.generic_container<len(il.meta.generic_containers) or
            len(ps)!=1 or m.param_count!=1 or not 0<=ps[0].type<len(il.types) or not 0<=m.return_type<len(il.types) or key(il.types[m.return_type])!=(1,0) or
            _spec_entry(il,si,mi)!=start.near_branch_target):return None
    owner,count,is_method,first=il.meta.generic_containers[m.generic_container];pt=il.types[ps[0].type]
    if ((owner,count,is_method)!=(mi,1,1) or not pt or il._type_enum(pt)!=0x1e or not pt[1]&(1<<29) or pt[0]!=first or
            not any(0<=ii<len(il.types) and il.type_name(il.types[ii])=='System.Runtime.CompilerServices.IAsyncStateMachine'
                    for ii in il.meta.interfaces[sm.interfaces_start:sm.interfaces_start+sm.interfaces_count])):return None
    return sm,ty,bt,ci


def _closed_start(il,method,td,slot,start,create):
    binding=_start_binding(il,method,td,slot,start)
    if not binding:return None
    sm,ty,bt,ci=binding; key=il._closed_type_key
    if ci!=-1 or bt.generic_container!=-1 or il.typedef_full(bt.index)!='System.Runtime.CompilerServices.AsyncVoidMethodBuilder':return None
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


def _task_frame(pro,epi):
    # MSVC may establish RBP between PUSH RBP and the stack allocation.
    # Everything after SUB uses one coordinate system: post-allocation RSP.
    bias=None
    if len(pro)>=3 and _addr(pro[-2],R.RBP):
        if pro[-3].mnemonic!=M.PUSH or pro[-3].op0_register!=R.RBP:return None
        bias=sdisp(pro[-2].memory_displacement)
        pro=pro[:-2]+pro[-1:]
    frame=_frame(pro,epi)
    if not frame:return None
    size,saved=frame
    if bias is not None:
        bias+=size
        if not 0<bias<size:return None
        saved=saved-{R.RBP}
    return size,saved,bias


def _home(i,bias):
    if i.memory_base==R.RSP:return sdisp(i.memory_displacement)
    if i.memory_base==R.RBP and bias is not None:return bias+sdisp(i.memory_displacement)
    return None


def _borrow(i,reg,bias):
    return _home(i,bias) if i.mnemonic==M.LEA and i.op0_register==reg else None


def _saved_inputs(il,method,td,moves,saved,*,enums=False):
    inputs={R.RCX:('this',(0x12,td.index,0))}; regs={};used=set()
    params=source_params(il.meta,method)
    if len(params)!=method.param_count:return None
    for p,gpr,dword in zip(params,(R.RDX,R.R8,R.R9),(R.EDX,R.R8D,R.R9D)):
        if not 0<=p.type<len(il.types):return None
        ty=il.types[p.type];key=il._closed_type_key(ty);name=safe_ident(p.name)
        if not key or key[-1] or not name.isidentifier():return None
        if enums and key[0]==0x11 and 0<=ty[0]<len(il.meta.typedefs):
            enum=il.meta.typedefs[ty[0]]
            if (not enum.is_enum or il._sf_field_size(ty,0)!=4 or not 0<=enum.element<len(il.types) or
                    il._closed_type_key(il.types[enum.element]) not in ((8,0),(9,0))):return None
            reg=dword
        elif key==(8,0):reg=dword
        elif key[0] in (0x0e,0x12):reg=gpr
        else:return None
        inputs[reg]=(name,key)
    for i in moves:
        src,dst=i.op1_register,i.op0_register
        if (i.mnemonic!=M.MOV or src not in inputs or src in used or dst==R.NONE or RegisterExt.full_register(dst) not in saved or
                any(RegisterExt.full_register(r)==RegisterExt.full_register(dst) for r in regs) or RegisterExt.size(src)!=RegisterExt.size(dst)):return None
        used.add(src);regs[dst]=inputs[src]
    return inputs,regs


def _slot_load(i,reg):
    if i.mnemonic==M.MOV and i.op0_register==reg and i.memory_base==R.RIP:return i.ip_rel_memory_address


def _task_member(il,slot,call,bt,ci,name,ret):
    """The Create and Task MethodRefs must use Start's class instantiation."""
    u=il.decode_slot(slot) or {};si=u.get('idx',-1)
    if u.get('kind')!=6 or not 0<=si<len(il.method_specs):return False
    mi,c,g=il.method_specs[si]
    if c!=ci or g!=-1 or not 0<=mi<len(il.meta.methods):return False
    m=il.meta.methods[mi]
    return (m.declaring==bt.index and m.name==name and m.generic_container==-1 and not m.param_count and
            m.is_static==(name=='Create') and m.flags&7==6 and not m.flags&0x40 and
            il._closed_type_key(il.candidate_return_type(('generic',si)))==ret and _call(call,_spec_entry(il,si,mi)))


def _builder_copy(seq,source,dest,width,bias,echo=False):
    """Follow byte ranges through volatile XMM scratch in instruction order.
    Require the barrier on the builder field and exactly one whole copy."""
    pieces={};writes=[];borrow=zero=False
    for i in seq:
        if not zero and _rr(i,M.XOR,R.EDX,R.EDX):zero=True;continue
        if not borrow and _borrow(i,R.RCX,bias)==dest:borrow=True;continue
        if i.mnemonic not in (M.MOVUPS,M.MOVDQU,M.MOVSD,M.MOVSS):return False
        n=MemorySizeExt.size(i.memory_size);reg=i.op0_register
        if i.op1_kind==K.MEMORY and R.XMM0<=reg<=R.XMM5:
            pos=sdisp(i.memory_displacement) if echo and i.memory_base==R.RAX else None
            if not echo:
                home=_home(i,bias);pos=home-source if home is not None else None
            if pos is None or not 0<=pos<=width-n:return False
            pieces[reg]=(pos,n)
        elif i.op0_kind==K.MEMORY and i.op1_register in pieces:
            pos,w=pieces[i.op1_register]
            if w!=n or _home(i,bias)!=dest+pos:return False
            writes.append((pos,n))
        else:return False
    return borrow and zero and _covers(writes,0,width)


def _zero_tiles(seq,bias):
    """Stack byte ranges definitely initialized before class initialization.
    Follow the value zero rather than requiring a particular scratch lane."""
    zeros=set();tiles=[]
    for i in seq:
        dst=i.op0_register
        if _rr(i,M.XORPS,dst,dst) and R.XMM0<=dst<=R.XMM5:zeros.add(dst);continue
        if _rr(i,M.XOR,dst,dst) and dst in (R.EAX,R.EDX,R.R8D,R.R9D,R.R10D,R.R11D):
            zeros.add(RegisterExt.full_register(dst));continue
        off=_home(i,bias)
        if off is None or i.op0_kind!=K.MEMORY:return None
        if i.mnemonic in (M.MOVDQU,M.MOVAPS,M.MOVUPS) and i.op1_register in zeros:
            if i.mnemonic==M.MOVAPS and off%16:return None
            n=16
        elif i.mnemonic==M.MOV and (i.op1_kind==K.IMMEDIATE32TO64 and i.immediate32to64==0 or i.op1_register in zeros):n=8
        else:return None
        tiles.append((off,n))
    return tiles,zeros


def _zero_sret_echo(il,target,width):
    """A folded Create must do exactly a default-value write and echo its
    destination. Derive the size from the closed builder, not its address."""
    if not il.bin.is_exec_va(target):return False
    raw=il.bin.read(target,128) or b''; zeros=set();writes=[];echo=False
    for i in Decoder(64,raw,ip=target):
        if i.is_invalid or i.has_segment_prefix or i.has_lock_prefix or i.has_rep_prefix or i.has_repne_prefix or i.memory_index!=R.NONE:return False
        reg=i.op0_register
        if i.mnemonic==M.RET:return not i.op_count and echo and _covers(writes,0,width)
        if _rr(i,M.MOV,R.RAX,R.RCX):echo=True;zeros.discard(R.RAX);continue
        if i.mnemonic==M.XOR and i.op1_register==reg and reg in (R.EAX,R.EDX,R.R8D,R.R9D,R.R10D,R.R11D):
            zeros.add(RegisterExt.full_register(reg))
            if reg==R.EAX:echo=False
        elif i.mnemonic==M.XORPS and i.op1_register==reg and R.XMM0<=reg<=R.XMM5:zeros.add(reg)
        elif (i.mnemonic in (M.MOV,M.MOVUPS,M.MOVDQU,M.MOVSD,M.MOVSS) and i.op0_kind==K.MEMORY and i.memory_base==R.RCX and
              i.op1_kind==K.REGISTER and (i.op1_register in zeros or RegisterExt.is_gpr(i.op1_register) and RegisterExt.full_register(i.op1_register) in zeros)):
            n=MemorySizeExt.size(i.memory_size);off=sdisp(i.memory_displacement)
            if not 0<=off<=width-n:return False
            writes.append((off,n))
        else:return False
    return False


def _ordinary_task_members(lift,bt,ci,rt,bk,rk,create,get):
    il=lift.il
    if (ci!=-1 or bt.generic_container!=-1 or il.typedef_full(bt.index)!='System.Runtime.CompilerServices.AsyncTaskMethodBuilder' or
            bk!=(0x11,bt.index,0)):return False
    for call,name,is_static,result in ((create,'Create',True,bk),(get,'get_Task',False,rk)):
        rows=[j for j in il.meta.type_methods(bt) if il.meta.methods[j].name==name and not il.meta.methods[j].param_count]
        if len(rows)!=1:return False
        j=rows[0];m=il.meta.methods[j];ids=il.addr_candidates.get(call.near_branch_target,())
        if (not _call(call,m.addr) or ('method',j) not in ids or m.declaring!=bt.index or m.is_static!=is_static or m.flags&7!=6 or m.flags&0x40 or
                m.generic_container!=-1 or not 0<=m.return_type<len(il.types) or il._closed_type_key(il.types[m.return_type])!=result):return False
        if not is_static and (len(ids)!=1 or lift._accessor_prop(j)!=('get','Task',0)):return False
    return _zero_sret_echo(il,create.near_branch_target,il._sf_field_size(rt,0))


def _task_captures(il,sm,base,width,bias,regs,groups,scalars=()):
    """Record actual stores in order. Each barrier must describe the sole
    reference store in its group; an interleaved scalar store needs no barrier."""
    writes=[]; seen=set()
    for barrier,group in [(True,g) for g in groups]+[(False,scalars)]:
        source=addr=reference=None
        for i in group:
            if barrier and i.mnemonic==M.MOV and i.op0_register==R.RDX and source is None:
                source=i.op1_register;continue
            if barrier and i.mnemonic==M.LEA and i.op0_register==R.RCX and addr is None:
                addr=_borrow(i,R.RCX,bias)
                if addr is None:return None
                continue
            off=_home(i,bias); reg=i.op1_register
            if off is None or i.mnemonic!=M.MOV or reg not in regs:return None
            val,key=regs[reg];ref=key[0] in (0x0e,0x12);n=8 if ref else 4
            if not base<=off<=base+width-n or RegisterExt.size(reg)!=n:return None
            row=_own_field(il,sm,off-base+16,n)
            if not row or row[0] in seen or row[1][1]&0x27!=6 or il._closed_type_key(row[1])!=key:return None
            if ref:
                if not barrier or reference is not None:return None
                reference=(reg,off)
            seen.add(row[0]);writes.append((row[0][5:],val))
        if barrier and reference!=(source,addr):return None
    return writes


def async_task_start(lift,method,td,seq,eh):
    """Task or Task<T>: capture inputs, start the closed machine by reference,
    then read Task on the same builder field after Start has returned."""
    il=lift.il
    if (not HAVE_ICED or eh or not seq or method.is_static or method.param_count>3 or td.is_valuetype or
            method.generic_container!=-1 or td.generic_container!=-1 or not isinstance(getattr(il,'bin',None),PE) or
            not il.bin.is64 or not 0<=method.return_type<len(il.types)):return None
    result=il.types[method.return_type];key=il._closed_type_key
    if not result or il._type_enum(result) not in (0x12,0x15):return None
    task=il.td_of_ty(result); rk=key(result)
    plain=il._type_enum(result)==0x12
    if task is None or not rk or il.typedef_full(task)!=('System.Threading.Tasks.Task' if plain else 'System.Threading.Tasks.Task`1'):return None
    if plain and rk!=(0x12,task,0):return None
    calls=[k for k,i in enumerate(seq) if i.mnemonic==M.CALL]
    ninit=2 if plain else 4 # plain Create/get_Task carry null MethodInfo; generic members each load a MethodRef
    if (len(calls)<ninit+5 or any(seq[k].op0_kind!=K.NEAR_BRANCH64 for k in calls) or seq[0].ip!=method.addr or
            il.function_extent(method.addr)!=(method.addr,seq[-1].next_ip) or any(a.next_ip!=b.ip for a,b in zip(seq,seq[1:])) or
            any(i.has_segment_prefix or i.has_lock_prefix or i.has_rep_prefix or i.has_repne_prefix or i.memory_index!=R.NONE for i in seq)):return None
    init=calls[0]; cl,create,wb,*captures,start,get=calls[ninit:];cap=captures[-1] if captures else wb
    hot_idx=calls[ninit-1]+2
    if (calls[:ninit]!=list(range(init,init+ninit*2,2)) or init<3 or cl-hot_idx<4 or create!=cl+3 or wb<=create+1 or
            start<cap+5 or get!=start+3 or any(seq[k].near_branch_target!=lift.rt_init_meta for k in calls[:ninit]) or
            seq[wb].near_branch_target not in lift.rt_wbarrier or any(seq[k].near_branch_target!=seq[wb].near_branch_target for k in captures)):return None
    p=next((j for j,i in enumerate(seq[:init-2]) if i.mnemonic==M.CMP),-1)
    if p<0:return None
    cmp=seq[p];branch=seq[init-2];ready=seq[hot_idx-1]; klass=seq[hot_idx];guard=seq[cl-2];hot=seq[cl-1]
    frame=_task_frame(seq[:p],seq[get+1:])
    if (not frame or cmp.memory_base!=R.RIP or cmp.memory_size!=1 or cmp.op1_kind!=K.IMMEDIATE8 or cmp.immediate8 or
            branch.mnemonic!=M.JNE or branch.near_branch_target!=klass.ip or ready.mnemonic!=M.MOV or ready.memory_base!=R.RIP or
            ready.ip_rel_memory_address!=cmp.ip_rel_memory_address or ready.op1_kind!=K.IMMEDIATE8 or ready.immediate8!=1):return None
    size,saved,bias=frame
    parked=_saved_inputs(il,method,td,seq[p+1:init-2],saved,enums=True)
    if not parked:return None
    inputs,regs=parked
    klass_slot=_slot_load(klass,R.RCX); start_slot=_slot_load(seq[cap+1],R.R8);slots=[klass_slot,start_slot]
    create_ctx,get_ctx=seq[cl+1],seq[start+1]
    if plain:
        if not all(_rr(i,M.XOR,R.EDX,R.EDX) for i in (create_ctx,get_ctx)):return None
    else:
        create_slot=_slot_load(create_ctx,R.RDX);get_slot=_slot_load(get_ctx,R.RDX);slots.extend((create_slot,get_slot))
    if not all(slots) or len(set(slots))!=ninit:return None
    inits=[seq[k-1] for k in calls[:ninit]]
    if (any(i.mnemonic!=M.LEA or i.op0_register!=R.RCX or i.memory_base!=R.RIP for i in inits) or
            {i.ip_rel_memory_address for i in inits}!=set(slots)):return None
    binding=_start_binding(il,method,td,start_slot,seq[start])
    if not binding:return None
    sm,ty,bt,ci=binding
    u=il.decode_slot(klass_slot) or {};rt=u.get('type');bk=key(rt)
    if u.get('kind')!=1 or u.get('td')!=bt.index or not bk or not il.returns_sret(rt):return None
    builder_width=il._sf_field_size(rt,0)
    if not builder_width or builder_width<=0:return None
    if plain:
        if not _ordinary_task_members(lift,bt,ci,rt,bk,rk,seq[create],seq[get]):return None
    else:
        args=il._method_spec_type_args(ci)
        if (not args or len(args)!=1 or not key(args[0]) or il.typedef_full(bt.index)!='System.Runtime.CompilerServices.AsyncTaskMethodBuilder`1' or
                rk!=(0x15,(0x12,task,0),(key(args[0]),),0) or bk!=(0x15,(0x11,bt.index,0),rk[2],0) or
                not _task_member(il,create_slot,seq[create],bt,ci,'Create',bk) or not _task_member(il,get_slot,seq[get],bt,ci,'get_Task',rk)):return None
        get_spec=il.decode_slot(get_slot)['idx']
        if lift._accessor_prop(il.method_specs[get_spec][0])!=('get','Task',0):return None
    if (guard.mnemonic!=M.CMP or guard.memory_base!=R.RCX or guard.memory_displacement!=KLASS_INITIALIZED or hot.mnemonic!=M.JNE or hot.near_branch_target!=seq[cl+1].ip or
            il.bin.exports.get(seq[cl].near_branch_target)!='il2cpp_runtime_class_init'):return None

    machine,builder=seq[cap+2:cap+4];state=seq[start-1];source=seq[create-1];after=seq[get-1]
    buf=_borrow(source,R.RCX,bias);home=_borrow(machine,R.RDX,bias);dest=_borrow(builder,R.RCX,bias);width=il.value_type_size(sm.index)
    if (None in (buf,home,dest) or not width or width<builder_width or not 32<=home<=size-width or not 32<=buf<=size-builder_width or
            not (buf+builder_width<=home or home+width<=buf) or not home<=dest<=home+width-builder_width or _borrow(after,R.RCX,bias)!=dest or
            not _builder_copy(seq[create+1:wb],buf,dest,builder_width,bias,echo=plain)):return None
    bf=_own_field(il,sm,dest-home+16,builder_width)
    if not bf or key(bf[1])!=bk or bf[1][1]&0x27!=6:return None
    zeroes=_zero_tiles(seq[hot_idx+1:cl-2],bias)
    if zeroes is None:return None
    tiles,regs_zero=zeroes
    if not (guard.op1_kind==K.IMMEDIATE8TO32 and guard.immediate8to32==0 or
            guard.op1_kind==K.REGISTER and RegisterExt.is_gpr32(guard.op1_register) and RegisterExt.full_register(guard.op1_register) in regs_zero):return None
    if not (_covers(tiles,home,width) or _covers(tiles+[(dest,builder_width)],home,width)):return None
    writes=_task_captures(il,sm,home,width,bias,regs,(seq[a+1:b] for a,b in zip([wb]+captures,captures)),seq[cap+4:start-1])
    if writes is None:return None
    off=_home(state,bias)
    if off is None or not home<=off<=home+width-4:return None
    sf=_own_field(il,sm,off-home+16,4)
    if (not sf or key(sf[1])!=(8,0) or sf[1][1]&0x27!=6 or any(f==sf[0][5:] for f,_ in writes) or state.mnemonic!=M.MOV or
            state.op1_kind!=K.IMMEDIATE32 or state.immediate32!=0xffffffff):return None
    tn=il.type_name(ty); builder_name=il.type_name(rt)
    name='stateMachine'
    while name in {v[0] for v in inputs.values()}:name+='Local'
    receiver=f'{name}.{bf[0][5:]}'
    return ([f'{tn} {name} = default;',
            f'System.Runtime.CompilerServices.RuntimeHelpers.RunClassConstructor(typeof({builder_name}).TypeHandle);',
            f'{receiver} = {builder_name}.Create();']+[f'{name}.{f} = {v};' for f,v in writes]+
            [f'{name}.{sf[0][5:]} = -1;',f'{receiver}.Start<{tn}>(ref {name});',f'return {receiver}.Task;'])


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
    parked=_saved_inputs(il,method,td,seq[cmp_pos+1:init-2],saved)
    if not parked:return None
    inputs,regs=parked

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
