"""Closed Task kickoffs embedded in another method's control flow."""
from bisect import bisect_right
from dataclasses import dataclass

from il2cpp.async_start import _addr, _builder_copy, _call, _covers, _ordinary_task_members, _rr, _slot_load, _start_binding, _task_captures, _zero_tiles, async_task_start
from il2cpp.binary import PE
from il2cpp.awaiter import _spec_entry
from il2cpp.captured_home import _ancestors, _borrow_calls, _normal_predecessors, _predecessors, _register_arguments
from il2cpp.expr import Expr, acc_get
from il2cpp.metadata import source_params
from il2cpp.names import safe_ident
from il2cpp.prelude import HAVE_ICED
from il2cpp.sret_copy import _own_field
from il2cpp.static_getter import guarded_alias
from il2cpp.task_reuse import formatting_uses
from il2cpp.text import reg_name, sdisp
from il2cpp.this_home import _fixed_frame
from il2cpp.x64 import KLASS_INITIALIZED, VOLATILE

if HAVE_ICED:
    from iced_x86 import Decoder, FlowControl as F, InstructionInfoFactory, MemorySizeExt, Mnemonic as M, OpAccess, OpKind as K, Register as R, RegisterExt
    _NONVOL={R.RBX,R.RBP,R.RDI,R.RSI,R.R12,R.R13,R.R14,R.R15}


def _awaiter_borrow(il,seq,k,pred):
    """Other stack byref in an async continuation: sized by the MethodRef's
    first byref MVAR, not just by the displacement of its LEA."""
    if k<2 or k+1>=len(seq):return False
    slot,machine,addr=seq[k-2:k+1];j=k+1
    # MSVC may form the builder receiver after the stack byref. It cannot
    # change the awaiter, machine, or hidden MethodRef on this path.
    if seq[j].mnemonic==M.LEA:
        recv=seq[j];j+=1
        if (j>=len(seq) or recv.op0_register!=R.RCX or recv.memory_base not in _NONVOL or recv.memory_base!=machine.op1_register or
                recv.memory_index!=R.NONE or recv.has_segment_prefix):return False
    call=seq[j]
    if (any(pred[b.ip]!={a.ip} for a,b in zip(seq[k-2:j],seq[k-1:j+1])) or slot.mnemonic!=M.MOV or slot.memory_base!=R.RIP or
             slot.op0_register!=R.R9 or machine.mnemonic!=M.MOV or machine.op0_register!=R.R8 or
            machine.op1_kind!=K.REGISTER or not _addr(addr,R.RDX) or call.mnemonic!=M.CALL or call.op0_kind!=K.NEAR_BRANCH64):return False
    u=il.decode_slot(slot.ip_rel_memory_address) or {};si=u.get('idx',-1)
    if u.get('kind')!=6 or not 0<=si<len(il.method_specs):return False
    mi,ci,gi=il.method_specs[si];args=il._method_spec_type_args(gi)
    if ci!=-1 or not args or len(args)!=2 or not 0<=mi<len(il.meta.methods):return False
    method=il.meta.methods[mi];ps=il.meta.method_params(method)
    if (method.name not in ('AwaitUnsafeOnCompleted','AwaitOnCompleted') or method.is_static or method.generic_container<0 or
            il.typedef_full(method.declaring) not in ('System.Runtime.CompilerServices.AsyncVoidMethodBuilder','System.Runtime.CompilerServices.AsyncTaskMethodBuilder') or
            len(ps)!=method.param_count or len(ps)!=2 or not all(0<=p.type<len(il.types) for p in ps)):return False
    own,n,is_method,first=il.meta.generic_containers[method.generic_container];types=[il.types[p.type] for p in ps]
    return ((own,n,is_method)==(mi,2,1) and all(il._type_enum(t)==0x1e and t[0]==first+j and t[1]&(1<<29) for j,t in enumerate(types)) and
            _spec_entry(il,si,mi)==call.near_branch_target)


def _kickoff_frame(seq,raw,*,plain=False):
    """Match home saves encoded by UWOP_SAVE_NONVOL at the end of the
    allocation. Their scaled offsets refer to final RSP, not entry RSP."""
    if len(raw)<4 or len(raw)!=4+2*raw[2] or plain and raw[0]!=1:return None
    pro=[i for i in seq if i.next_ip<=seq[0].ip+raw[1]]
    if (not pro or pro[-1].mnemonic!=M.SUB or pro[-1].op0_register!=R.RSP or
            pro[-1].op1_kind not in (K.IMMEDIATE8TO64,K.IMMEDIATE32TO64)):return None
    depth=pro[-1].immediate(1)+8*sum(i.mnemonic==M.PUSH for i in pro)
    rows=set();j=4
    while j+4<=len(raw) and raw[j+1]&15==4:
        reg=R.RAX+(raw[j+1]>>4);off=8*int.from_bytes(raw[j+2:j+4],'little')-depth
        if raw[j]!=raw[1] or reg not in _NONVOL or off not in (8,16,24,32) or (reg,off) in rows:return None
        rows.add((reg,off));j+=4
    if rows or plain:
        # Each save must actually precede any push or change of stack base.
        stores=set();store_count=0
        for i in pro:
            if i.mnemonic!=M.MOV or i.memory_base!=R.RSP:break
            if i.op0_kind!=K.MEMORY or i.memory_index!=R.NONE or i.has_segment_prefix:return None
            store_count+=1
            slot=(i.op1_register,sdisp(i.memory_displacement))
            if slot==(R.RCX,8):continue
            if slot in stores:return None
            stores.add(slot)
        if stores!=rows or len({off for _,off in rows})!=len(rows) or len({r for r,_ in rows})!=len(rows):return None
        raw=raw[:2]+bytes([raw[2]-(j-4)//2])+raw[3:4]+raw[j:]
        if plain and any(i.mnemonic!=M.PUSH for i in pro[store_count:-1]):return None
    return _fixed_frame(seq,raw,require_receiver_home=not plain)


def _frame_isolated(lift,m,seq,eh,start,end,ranges,pred,peers=()):
    """Verify local extents, all normal entries and EH boundaries. Do not
    erase storage shared with surrounding code or cross a protected span."""
    il=lift.il
    plain=eh is None
    if not plain and not eh.get('try_ranges'):return False
    rva=m.addr-il.bin.image_base; n=bisect_right(il._eh4_begins,rva)-1
    if n<0 or il._eh4_entries[n][0]!=rva:return False
    _,finish,ui=il._eh4_entries[n]
    if not m.addr<=start<end<=il.bin.image_base+finish:return False
    if plain and (seq[0].ip!=m.addr or seq[-1].next_ip!=il.bin.image_base+finish):return False
    raw=il.bin.read(il.bin.image_base+ui,4) or b''
    if len(raw)!=4:return False
    frame=_kickoff_frame(seq,il.bin.read(il.bin.image_base+ui,4+2*raw[2]) or b'',plain=plain)
    if not frame or frame[2]:return False
    pro=[i for i in seq if i.next_ip<=m.addr+raw[1]]
    if not pro or pro[-1].mnemonic!=M.SUB:return False
    size=pro[-1].immediate(1);pop=[i.op0_register for i in reversed(pro) if i.mnemonic==M.PUSH]
    if any(not 32<=a<b<=size for a,b in ranges):return False
    if not plain:
        if any(start<=p<end for p in eh['pads']):return False
        spans=[(a,b) for _,_,_,ss in eh['try_ranges'] for a,b in ss]
        if not any(a<=start<end<=b for a,b in spans) or any(start<x<end for ab in spans for x in ab):return False
    epilogue=set();fac=InstructionInfoFactory();bounds=_borrow_calls(il,seq,pred)
    bounded=formatting_uses(il,seq,pred,ranges) if peers else set()
    for k,i in enumerate(seq):
        if i.ip<pro[-1].next_ip or start<=i.ip<end or i.ip in epilogue or any(a<=i.ip<b for a,b in peers):continue
        if i.has_segment_prefix or i.flow_control in (F.INDIRECT_BRANCH,F.INDIRECT_CALL):return False
        if i.flow_control in (F.CONDITIONAL_BRANCH,F.UNCONDITIONAL_BRANCH,F.CALL):
            if i.op0_kind!=K.NEAR_BRANCH64 or start<i.near_branch_target<end:return False
            if plain and i.flow_control!=F.CALL and not pro[-1].next_ip<=i.near_branch_target<seq[-1].next_ip:return False
            if i.flow_control==F.CALL:
                if m.addr<=i.near_branch_target<seq[-1].next_ip:return False
                if (i.ip not in bounds and i.near_branch_target!=lift.rt_init_meta and
                        il.bin.exports.get(i.near_branch_target)!='il2cpp_runtime_class_init' and not _register_arguments(il,i.near_branch_target)):
                    # A one-argument metadata helper may also be reached via
                    # a jump thunk. Require the registered input slot here.
                    prev=seq[k-1]
                    if (pred[i.ip]!={prev.ip} or prev.mnemonic!=M.LEA or prev.op0_register!=R.RCX or prev.memory_base!=R.RIP or
                            not il.decode_slot(prev.ip_rel_memory_address) or
                            lift.rt_names.get(lift._thunk_final(i.near_branch_target))!='il2cpp_codegen_initialize_runtime_metadata'):return False
                continue
        if i.mnemonic==M.ADD and i.op0_register==R.RSP:
            tail=seq[k+1:k+len(pop)+2]
            if (i.op1_kind not in (K.IMMEDIATE8TO64,K.IMMEDIATE32TO64) or i.immediate(1)!=size or len(tail)!=len(pop)+1 or
                    any(x.mnemonic!=M.POP or x.op0_register!=r for x,r in zip(tail,pop)) or tail[-1].mnemonic!=M.RET):return False
            epilogue.update(x.ip for x in tail);continue
        if i.memory_index==R.RSP or any(i.op_kind(j)==K.REGISTER and RegisterExt.full_register(i.op_register(j))==R.RSP for j in range(i.op_count)):return False
        if i.memory_base==R.RSP:
            if i.memory_index!=R.NONE:return False  # displacement alone cannot bound a dynamic access
            if i.ip in bounded:continue
            off=sdisp(i.memory_displacement);width=MemorySizeExt.size(i.memory_size)
            if i.mnemonic==M.LEA:
                if (off<max(b for _,b in ranges) or k+1>=len(seq) or
                        not (i.op0_register==R.RCX and seq[k+1].ip in bounds or _awaiter_borrow(il,seq,k,pred))):return False
            elif not width or any(off<b and off+width>a for a,b in ranges):return False
        elif any(RegisterExt.full_register(r.register)==R.RSP for r in fac.info(i).used_registers()):return False
    return not any(i.near_branch_target in epilogue for i in seq if i.op0_kind==K.NEAR_BRANCH64)


def _source(il,m,td,seq,eh,begin,reg,owner,pred):
    # The native register holds an earlier snapshot of an outer reference.
    # Locate the load dominating this arm, not a later re-read of its field.
    fac=InstructionInfoFactory();writes={OpAccess.WRITE,OpAccess.READ_WRITE,OpAccess.COND_WRITE,OpAccess.READ_COND_WRITE}
    def reaching(r,ip):
        ancestors=_ancestors(pred,ip)
        if m.addr not in ancestors:return None
        hits=[i for i in seq if i.ip in ancestors and any(u.access in writes and RegisterExt.full_register(u.register)==r for u in fac.info(i).used_registers())]
        if len(hits)!=1:return None
        left=_ancestors(pred,ip,hits[0].ip)
        return None if m.addr in left or eh and any(p in left for p in eh['pads']) else hits[0]
    load=reaching(reg,begin)
    if not load or load.mnemonic!=M.MOV or load.op0_register!=reg or load.op1_kind!=K.MEMORY or load.has_segment_prefix or load.memory_index!=R.NONE:return None
    base=load.memory_base
    if base not in (R.RBX,R.RBP,R.RDI,R.RSI,R.R12,R.R13,R.R14,R.R15):return None
    park=reaching(base,load.ip)
    if not park or not _rr(park,M.MOV,base,R.RCX):return None
    for i in seq:
        if i.ip==park.ip:break
        if i.flow_control!=F.NEXT or any(u.access in writes and RegisterExt.full_register(u.register)==R.RCX for u in fac.info(i).used_registers()):return None
    row=_own_field(il,td,(16 if td.is_valuetype else 0)+sdisp(load.memory_displacement),8)
    if row and il._closed_type_key(row[1])==(0x12,owner.index,0):return load.ip,row,reg_name(reg)


def _discarded_bool(seq):
    """The only return value is false. Restores may precede the AL write,
    but no instruction can publish the Task or observe its register."""
    j=0
    while j<len(seq) and seq[j].mnemonic==M.MOV:
        i=seq[j];j+=1
        if i.op0_register not in _NONVOL or i.memory_base!=R.RSP or i.memory_index!=R.NONE or i.has_segment_prefix:return False
    if j>=len(seq) or not any(_rr(seq[j],M.XOR,r,r) for r in (R.AL,R.EAX)):return False
    tail=seq[j+1:]
    return (len(tail)>=2 and tail[0].mnemonic==M.ADD and tail[0].op0_register==R.RSP and
            all(i.mnemonic==M.POP and i.op0_register in _NONVOL for i in tail[1:-1]) and tail[-1].mnemonic==M.RET and not tail[-1].op_count)


def _checked_owner(lift,seq,cmp,reg,pred):
    """The CFG suppresses the runtime null-throw edge. Re-emit it only
    when it checks this capture on every path into the guarded region."""
    j=next(i for i,x in enumerate(seq) if x.ip==cmp.ip)
    if j<2:return False
    test,jump=seq[j-2:j]
    if (not _rr(test,M.TEST,reg,reg) or jump.mnemonic!=M.JE or pred[jump.ip]!={test.ip} or
            pred[cmp.ip]!={jump.ip}):return False
    throw=next((i for i in seq if i.ip==jump.near_branch_target),None)
    if not throw or throw.mnemonic!=M.CALL or throw.op0_kind!=K.NEAR_BRANCH64:return False
    helper=throw.near_branch_target
    return lift._named_raise_throw(helper,lift._call_name(helper))=='System.NullReferenceException'


@dataclass
class Site:
    ip:int
    plan:tuple
    begin:int
    end:int
    ranges:tuple
    zero_stores:tuple
    getter:int=0


def _public_wrapper(lift,owner,rk,identity):
    """A different class cannot instantiate a private nested machine. Use
    the registered public wrapper only if its entire body is this kickoff."""
    il=lift.il;found=[]
    for mi in il.meta.type_methods(owner):
        m=il.meta.methods[mi]
        if (not m.addr or m.is_static or m.param_count or m.flags&7!=6 or m.flags&0x40 or m.declaring!=owner.index or
                m.generic_container!=-1 or not 0<=m.return_type<len(il.types) or il._closed_type_key(il.types[m.return_type])!=rk):continue
        ex=il.function_extent(m.addr)
        if not ex or ex[0]!=m.addr or not 0<ex[1]-m.addr<=2048:continue
        seq=list(Decoder(64,il.bin.read(m.addr,ex[1]-m.addr) or b'',ip=m.addr))
        if async_task_start(lift,m,owner,seq,il.eh_regions(m.addr),identity=True)==identity:found.append(safe_ident(m.name))
    return found[0] if len(found)==1 else None


def _region(lift,m,td,blocks,b,seq,eh,pred):
    il=lift.il;ins=b.insns
    calls=[j for j,i in enumerate(ins) if i.mnemonic==M.CALL]
    if b.bid<4 or len(calls) not in (4,5) or calls[0]!=2 or any(ins[j].op0_kind!=K.NEAR_BRANCH64 for j in calls):return None
    create,wb,*barriers,start,get=calls
    scalar=not barriers;cap=wb+1 if scalar else barriers[0]
    if (not _addr(ins[1],R.RCX) or not scalar and (cap!=wb+4 or not _call(ins[cap],ins[wb].near_branch_target)) or
            start!=cap+5 or get!=start+3 or ins[wb].near_branch_target not in lift.rt_wbarrier or not _rr(ins[start+1],M.XOR,R.EDX,R.EDX)):return None
    setup=ins[cap+1:start]
    # Four independent definitions, scheduled on either side of the state store.
    flag=next((i for i in setup if i.op0_kind==K.MEMORY),None)
    token=next((i for i in setup if _slot_load(i,R.R8)),None)
    machine=next((i for i in setup if _addr(i,R.RDX)),None)
    builder=next((i for i in setup if _addr(i,R.RCX)),None)
    if None in (flag,token,machine,builder):return None
    slot=_slot_load(token,R.R8)
    if (not slot or not _addr(machine,R.RDX) or not _addr(builder,R.RCX) or not _addr(ins[get-1],R.RCX) or
            builder.memory_displacement!=ins[get-1].memory_displacement or flag.mnemonic!=M.MOV or flag.memory_base!=R.RSP or
            flag.op1_kind!=K.IMMEDIATE32 or flag.immediate32!=0xffffffff):return None
    outer=il._nested_owner(td.index)
    if outer is None or m.is_static or (eh is None)==td.is_valuetype:return None
    # A closed child may belong to another type. The capture must then
    # come from a separately proved producer of that concrete type.
    usage=il.decode_slot(slot) or {};si=usage.get('idx',-1)
    if usage.get('kind')!=6 or not 0<=si<len(il.method_specs):return None
    args=il._method_spec_type_args(il.method_specs[si][2])
    if not args or len(args)!=1 or not 0<=args[0][0]<len(il.meta.typedefs):return None
    child_owner=il._nested_owner(args[0][0]);external=child_owner!=outer
    if child_owner is None or external and (scalar or not eh):return None
    outer=child_owner
    owner=il.meta.typedefs[outer]; binding=_start_binding(il,m,owner,slot,ins[start])
    if not binding:return None
    sm,ty,bt,ci=binding;rt=il.types[bt.byval];bk=il._closed_type_key(rt)
    ids=il.addr_candidates.get(ins[get].near_branch_target,())
    if len(ids)!=1 or ids[0][0]!='method' or not 0<=ids[0][1]<len(il.meta.methods):return None
    ix=il.meta.methods[ids[0][1]].return_type
    if not 0<=ix<len(il.types):return None
    task=il.types[ix];rk=il._closed_type_key(task)
    if (not rk or rk!=(0x12,task[0],0) or il.typedef_full(task[0])!='System.Threading.Tasks.Task' or not il.returns_sret(rt) or
            not _ordinary_task_members(lift,bt,ci,rt,bk,rk,ins[create],ins[get])):return None
    home=machine.memory_displacement;src=ins[1].memory_displacement;dest=builder.memory_displacement
    width=il.value_type_size(sm.index);w=il._sf_field_size(rt,0)
    if (not width or not w or not (src+w<=home or home+width<=src) or not home<=dest<=home+width-w or
            not home<=flag.memory_displacement<=home+width-4 or not _builder_copy(ins[create+1:wb],src,dest,w,None,echo=True)):return None
    bf=_own_field(il,sm,dest-home+16,w);sf=_own_field(il,sm,flag.memory_displacement-home+16,4)
    if (not bf or il._closed_type_key(bf[1])!=bk or bf[1][1]&0x27!=6 or not sf or il._closed_type_key(sf[1])!=(8,0) or sf[1][1]&0x27!=6):return None
    head,cold,zeros,cl=blocks[b.bid-4:b.bid];h=head.insns[-2:];g=zeros.insns;init=cold.insns
    if len(h)!=2 or len(init)!=5 or len(g)<5 or len(cl.insns)!=1:return None
    region=h+init+g+cl.insns+ins[:get+1]
    if any(x.next_ip!=y.ip for x,y in zip(region,region[1:])) or any(i.has_segment_prefix or i.has_lock_prefix or i.has_rep_prefix or i.has_repne_prefix or i.memory_index!=R.NONE for i in region):return None
    cmp,branch=h;ready=init[-1];guard,hot=g[-2:]
    klasses=[(j,_slot_load(x,R.RCX)) for j,x in enumerate(g[:-2]) if _slot_load(x,R.RCX)]
    if len(klasses)!=1:return None
    j,kslot=klasses[0];u=il.decode_slot(kslot)
    tiles=_zero_tiles(g[:j]+g[j+1:-2],None)
    if tiles is None or not _covers(tiles[0],home,width):return None
    # The class load only writes RCX. A scalar zero produced while clearing
    # the machine survives into the guard if it is a different register.
    if (not u or u.get('kind')!=1 or il._closed_type_key(u.get('type'))!=bk or cmp.mnemonic!=M.CMP or cmp.memory_base!=R.RIP or
            cmp.memory_size!=1 or cmp.op1_kind!=K.IMMEDIATE8 or cmp.immediate8 or branch.mnemonic!=M.JNE or branch.near_branch_target!=g[0].ip or
            ready.mnemonic!=M.MOV or ready.memory_base!=R.RIP or ready.ip_rel_memory_address!=cmp.ip_rel_memory_address or ready.op1_kind!=K.IMMEDIATE8 or ready.immediate8!=1 or
            {x.ip_rel_memory_address for x in init[:-1:2]}!={slot,kslot} or any(x.mnemonic!=M.LEA or x.op0_register!=R.RCX or x.memory_base!=R.RIP for x in init[:-1:2]) or
            not all(_call(x,lift.rt_init_meta) for x in init[1:-1:2]) or guard.mnemonic!=M.CMP or guard.memory_base!=R.RCX or guard.memory_displacement!=KLASS_INITIALIZED or
            not (guard.op1_kind==K.IMMEDIATE8TO32 and guard.immediate8to32==0 or guard.op1_kind==K.REGISTER and
                 RegisterExt.is_gpr32(guard.op1_register) and guard.op1_register!=R.ECX and RegisterExt.full_register(guard.op1_register) in tiles[1]) or
            hot.mnemonic!=M.JNE or hot.near_branch_target!=ins[0].ip or
            cl.insns[0].mnemonic!=M.CALL or cl.insns[0].op0_kind!=K.NEAR_BRANCH64 or il.bin.exports.get(cl.insns[0].near_branch_target)!='il2cpp_runtime_class_init'):return None
    source=None;getter=0;constant=None;wrapper=None
    if scalar:
        store=ins[cap];off=sdisp(store.memory_displacement)
        if (not eh or store.mnemonic!=M.MOV or store.memory_base!=R.RSP or store.op1_kind!=K.IMMEDIATE32 or not home<=off<=home+width-4):return None
        row=_own_field(il,sm,off-home+16,4)
        if not row or row==sf or row[1][1]&0x27!=6 or il._closed_type_key(row[1])!=(8,0):return None
        capture=row[0][5:];constant=str(int.from_bytes(store.immediate32.to_bytes(4,'little'),'little',signed=True))
    else:
        group=ins[wb+1:cap];reg=next((i.op1_register for i in group if i.op0_kind==K.MEMORY and i.memory_base==R.RSP),R.NONE)
        if reg not in _NONVOL:return None
        if eh is None:
            if (not 0<=m.return_type<len(il.types) or il._closed_type_key(il.types[m.return_type])!=(2,0) or
                    get!=len(ins)-1 or b.bid+1>=len(blocks) or not _discarded_bool(blocks[b.bid+1].insns) or
                    not _checked_owner(lift,seq,cmp,reg,pred)):return None
        if external:
            j=next(k for k,x in enumerate(seq) if x.ip==cmp.ip)
            if j<5 or not _checked_owner(lift,seq,cmp,R.RAX,pred):return None
            zero,producer,save,test,jump=seq[j-5:j]
            if (not _rr(zero,M.XOR,R.ECX,R.ECX) or producer.mnemonic!=M.CALL or producer.op0_kind!=K.NEAR_BRANCH64 or
                    not _rr(save,M.MOV,reg,R.RAX) or any(pred[y.ip]!={x.ip} for x,y in zip(seq[j-5:j-1],seq[j-4:j]))):return None
            getter=producer.near_branch_target;alias=guarded_alias(il,getter,lift.rt_init_meta)
            if alias and il._closed_type_key(alias[1])==(0x12,outer,0):source=producer.ip,alias,reg_name(reg)
        else:source=_source(il,m,td,seq,eh,cmp.ip,reg,owner,pred)
        if not source:return None
        capfields=_task_captures(il,sm,home,width,None,{reg:('owner',(0x12,outer,0))},[group])
        if not capfields or len(capfields)!=1:return None
        capture=capfields[0][0]
        if external:
            wrapper=_public_wrapper(lift,owner,rk,(slot,ins[create].near_branch_target,ins[get].near_branch_target,bf[0],sf[0],((capture,'this'),)))
            if not wrapper:return None
    plan=(ty,rt,task,bf[0][5:],sf[0][5:],capture,source,get,eh is None,wrapper,constant)
    return Site(ins[0].ip,plan,cmp.ip,ins[get].next_ip,((home,home+width),(src,src+w)),
                tuple(i.ip for i in g[:-2] if i.op0_kind==K.MEMORY),getter)


def inline_tasks(lift,m,td,blocks,eh):
    plans={};loads={};getters={};zeroes=set();result=(plans,loads,getters,zeroes);il=lift.il
    if not HAVE_ICED or not isinstance(getattr(il,'bin',None),PE) or not il.bin.is64:return result
    if eh is None and (td.is_valuetype or m.is_static or not 0<=m.return_type<len(il.types) or il._type_enum(il.types[m.return_type])!=2):return result
    seq=[i for b in blocks for i in b.insns]
    if not seq or len(seq)>1024 or any(a.next_ip!=b.ip for a,b in zip(seq,seq[1:])):return result
    candidates=[b for b in blocks if len(b.insns)>=4 and _rr(b.insns[0],M.XOR,R.EDX,R.EDX) and _addr(b.insns[1],R.RCX)]
    if not candidates:return result
    pred=_normal_predecessors(seq) if eh is None else _predecessors(seq,eh)
    if not pred:return result
    groups={}
    for b in candidates:
        s=_region(lift,m,td,blocks,b,seq,eh,pred)
        if s:groups.setdefault(s.ranges,[]).append(s)
    for ranges,sites in groups.items():
        if any(a.end>b.begin for a,b in zip(sites,sites[1:])):continue
        # Atomic: exclude a peer's accesses only if every peer independently
        # proved its full initialization, closed Start, Task and entry edges.
        if not all(_frame_isolated(lift,m,seq,eh,s.begin,s.end,ranges,pred,[(p.begin,p.end) for p in sites if p is not s]) for s in sites):continue
        for s in sites:
            plans[s.ip]=s.plan;source=s.plan[6]
            if s.getter:
                load,row,reg=source
                for k,i in enumerate(seq[1:],1):
                    if _call(i,s.getter) and pred[i.ip]=={seq[k-1].ip} and _rr(seq[k-1],M.XOR,R.ECX,R.ECX):getters[i.ip]=row
            elif source:
                load,row,reg=source;loads[load]=(row,reg)
            if len(sites)>1 and (s.getter or not source):zeroes.update(s.zero_stores)
    return result


def emit_kickoff(lift,ip,plan,values):
    ty,rt,task_ty,builder,state,capture,source,end,discard,wrapper,operand=plan
    if source:
        load,_,reg=source;value=values.get(load)
        if value is None or value._unk or not wrapper and value is not dict.get(lift.regs,reg):return None
        operand=value.text
    machine='nestedStateMachine'+lift.new_var()[1:];task=lift.new_var();tn=lift.il.type_name(ty);btn=lift.il.type_name(rt)
    while machine in {safe_ident(p.name) for p in source_params(lift.meta,lift._current_method)}:machine+='Local'
    field=machine+'.'+builder
    if discard:lift.emit(ip,f'if ({operand} is null) {{ throw new System.NullReferenceException(); }}',None)
    if not discard:lift._var_types[task]=task_ty
    result=('_' if discard else 'var '+task)+' = '+acc_get(field+'.Task')+';'
    lines=(f'var {task} = {operand}.{wrapper}();',) if wrapper else (
                 f'{tn} {machine} = default;',f'System.Runtime.CompilerServices.RuntimeHelpers.RunClassConstructor(typeof({btn}).TypeHandle);',
                 f'{field} = {btn}.Create();',f'{machine}.{capture} = {operand};',f'{machine}.{state} = -1;',
                 f'{field}.Start<{tn}>(ref {machine});',result)
    for line in lines:lift.emit(ip,line,None)
    for reg in (*VOLATILE,*('XMM%d'%n for n in range(6))):lift.regs.pop(reg,None)
    if not discard:lift.regs['RAX']=Expr(task,task_ty,'obj')
    lift.flags=None;lift._fresh_unknowns()
    return end
