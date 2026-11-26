"""A closed Task kickoff in a protected branch of another method."""
from bisect import bisect_right

from il2cpp.async_start import _addr, _builder_copy, _call, _covers, _ordinary_task_members, _rr, _slot_load, _start_binding, _task_captures, _zero_tiles
from il2cpp.binary import PE
from il2cpp.awaiter import _spec_entry
from il2cpp.captured_home import _ancestors, _borrow_calls, _predecessors, _register_arguments
from il2cpp.expr import Expr, acc_get
from il2cpp.metadata import source_params
from il2cpp.names import safe_ident
from il2cpp.prelude import HAVE_ICED
from il2cpp.sret_copy import _own_field
from il2cpp.text import reg_name, sdisp
from il2cpp.this_home import _fixed_frame
from il2cpp.x64 import KLASS_INITIALIZED, VOLATILE

if HAVE_ICED:
    from iced_x86 import FlowControl as F, InstructionInfoFactory, MemorySizeExt, Mnemonic as M, OpAccess, OpKind as K, Register as R, RegisterExt


def _awaiter_borrow(il,seq,k,pred):
    """Other stack byref in an async continuation: sized by the MethodRef's
    first byref MVAR, not just by the displacement of its LEA."""
    if k<2 or k+1>=len(seq):return False
    slot,machine,addr,call=seq[k-2:k+2]
    if (any(pred[b.ip]!={a.ip} for a,b in zip(seq[k-2:k+1],seq[k-1:k+2])) or slot.mnemonic!=M.MOV or slot.memory_base!=R.RIP or
            slot.op0_register!=R.R9 or machine.mnemonic!=M.MOV or machine.op0_register!=R.R8 or
            machine.op1_kind!=K.REGISTER or not _addr(addr,R.RDX) or call.op0_kind!=K.NEAR_BRANCH64):return False
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


def _frame_isolated(lift,m,seq,eh,start,end,ranges,pred):
    """Verify local extents, all normal entries and EH boundaries. Do not
    erase storage shared with surrounding code or cross a protected span."""
    il=lift.il
    if not eh.get('try_ranges'):return False
    rva=m.addr-il.bin.image_base; n=bisect_right(il._eh4_begins,rva)-1
    if n<0 or il._eh4_entries[n][0]!=rva:return False
    _,finish,ui=il._eh4_entries[n]
    if not m.addr<=start<end<=il.bin.image_base+finish:return False
    raw=il.bin.read(il.bin.image_base+ui,4) or b''
    if len(raw)!=4:return False
    frame=_fixed_frame(seq,il.bin.read(il.bin.image_base+ui,4+2*raw[2]) or b'')
    if not frame or frame[2]:return False
    pro=[i for i in seq if i.next_ip<=m.addr+raw[1]]
    if not pro or pro[-1].mnemonic!=M.SUB:return False
    size=pro[-1].immediate(1);pop=[i.op0_register for i in reversed(pro) if i.mnemonic==M.PUSH]
    if any(not 32<=a<b<=size for a,b in ranges) or any(start<=p<end for p in eh['pads']):return False
    spans=[(a,b) for _,_,_,ss in eh['try_ranges'] for a,b in ss]
    if not any(a<=start<end<=b for a,b in spans) or any(start<x<end for ab in spans for x in ab):return False
    epilogue=set();fac=InstructionInfoFactory();bounds=_borrow_calls(il,seq,pred)
    for k,i in enumerate(seq):
        if i.ip<pro[-1].next_ip or start<=i.ip<end or i.ip in epilogue:continue
        if i.has_segment_prefix or i.flow_control in (F.INDIRECT_BRANCH,F.INDIRECT_CALL):return False
        if i.flow_control in (F.CONDITIONAL_BRANCH,F.UNCONDITIONAL_BRANCH,F.CALL):
            if i.op0_kind!=K.NEAR_BRANCH64 or start<i.near_branch_target<end:return False
            if i.flow_control==F.CALL:
                if m.addr<=i.near_branch_target<seq[-1].next_ip:return False
                if (i.ip not in bounds and i.near_branch_target!=lift.rt_init_meta and
                        il.bin.exports.get(i.near_branch_target)!='il2cpp_runtime_class_init' and not _register_arguments(il,i.near_branch_target)):return False
                continue
        if i.mnemonic==M.ADD and i.op0_register==R.RSP:
            tail=seq[k+1:k+len(pop)+2]
            if (i.op1_kind not in (K.IMMEDIATE8TO64,K.IMMEDIATE32TO64) or i.immediate(1)!=size or len(tail)!=len(pop)+1 or
                    any(x.mnemonic!=M.POP or x.op0_register!=r for x,r in zip(tail,pop)) or tail[-1].mnemonic!=M.RET):return False
            epilogue.update(x.ip for x in tail);continue
        if i.memory_index==R.RSP or any(i.op_kind(j)==K.REGISTER and RegisterExt.full_register(i.op_register(j))==R.RSP for j in range(i.op_count)):return False
        if i.memory_base==R.RSP:
            if i.memory_index!=R.NONE:return False  # displacement alone cannot bound a dynamic access
            off=sdisp(i.memory_displacement);width=MemorySizeExt.size(i.memory_size)
            if i.mnemonic==M.LEA:
                if (off<max(b for _,b in ranges) or k+1>=len(seq) or seq[k+1].flow_control!=F.CALL or
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
        return None if m.addr in left or any(p in left for p in eh['pads']) else hits[0]
    load=reaching(reg,begin)
    if not load or load.mnemonic!=M.MOV or load.op0_register!=reg or load.op1_kind!=K.MEMORY or load.has_segment_prefix or load.memory_index!=R.NONE:return None
    base=load.memory_base
    if base not in (R.RBX,R.RBP,R.RDI,R.RSI,R.R12,R.R13,R.R14,R.R15):return None
    park=reaching(base,load.ip)
    if not park or not _rr(park,M.MOV,base,R.RCX):return None
    for i in seq:
        if i.ip==park.ip:break
        if i.flow_control!=F.NEXT or any(u.access in writes and RegisterExt.full_register(u.register)==R.RCX for u in fac.info(i).used_registers()):return None
    row=_own_field(il,td,16+sdisp(load.memory_displacement),8)
    if row and il._closed_type_key(row[1])==(0x12,owner.index,0):return load.ip,row,reg_name(reg)


def _region(lift,m,td,blocks,b,seq,eh):
    il=lift.il;ins=b.insns
    calls=[j for j,i in enumerate(ins) if i.mnemonic==M.CALL]
    if b.bid<4 or len(calls)!=5 or calls[0]!=2 or any(ins[j].op0_kind!=K.NEAR_BRANCH64 for j in calls):return None
    create,wb,cap,start,get=calls
    if (not _addr(ins[1],R.RCX) or cap!=wb+4 or start!=cap+5 or get!=start+3 or ins[wb].near_branch_target not in lift.rt_wbarrier or
            not _call(ins[cap],ins[wb].near_branch_target) or not _rr(ins[start+1],M.XOR,R.EDX,R.EDX)):return None
    flag,token,machine,builder=ins[cap+1:start];slot=_slot_load(token,R.R8)
    if (not slot or not _addr(machine,R.RDX) or not _addr(builder,R.RCX) or not _addr(ins[get-1],R.RCX) or
            builder.memory_displacement!=ins[get-1].memory_displacement or flag.mnemonic!=M.MOV or flag.memory_base!=R.RSP or
            flag.op1_kind!=K.IMMEDIATE32 or flag.immediate32!=0xffffffff):return None
    outer=il._nested_owner(td.index)
    if outer is None or not td.is_valuetype or m.is_static:return None
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
    cmp,branch=h;ready=init[-1];klass,guard,hot=g[-3:];kslot=_slot_load(klass,R.RCX);u=il.decode_slot(kslot) if kslot else None
    if (not u or u.get('kind')!=1 or il._closed_type_key(u.get('type'))!=bk or cmp.mnemonic!=M.CMP or cmp.memory_base!=R.RIP or
            cmp.memory_size!=1 or cmp.op1_kind!=K.IMMEDIATE8 or cmp.immediate8 or branch.mnemonic!=M.JNE or branch.near_branch_target!=g[0].ip or
            ready.mnemonic!=M.MOV or ready.memory_base!=R.RIP or ready.ip_rel_memory_address!=cmp.ip_rel_memory_address or ready.op1_kind!=K.IMMEDIATE8 or ready.immediate8!=1 or
            {x.ip_rel_memory_address for x in init[:-1:2]}!={slot,kslot} or any(x.mnemonic!=M.LEA or x.op0_register!=R.RCX or x.memory_base!=R.RIP for x in init[:-1:2]) or
            not all(_call(x,lift.rt_init_meta) for x in init[1:-1:2]) or guard.mnemonic!=M.CMP or guard.memory_base!=R.RCX or guard.memory_displacement!=KLASS_INITIALIZED or
            guard.op1_kind!=K.IMMEDIATE8TO32 or guard.immediate8to32 or hot.mnemonic!=M.JNE or hot.near_branch_target!=ins[0].ip or
            cl.insns[0].mnemonic!=M.CALL or cl.insns[0].op0_kind!=K.NEAR_BRANCH64 or il.bin.exports.get(cl.insns[0].near_branch_target)!='il2cpp_runtime_class_init'):return None
    tiles=_zero_tiles(g[:-3],None)
    if tiles is None or not _covers(tiles[0],home,width):return None
    pred=_predecessors(seq,eh)
    if not pred or not _frame_isolated(lift,m,seq,eh,cmp.ip,ins[get].next_ip,[(home,home+width),(src,src+w)],pred):return None
    group=ins[wb+1:cap];reg=next((i.op1_register for i in group if i.op0_kind==K.MEMORY and i.memory_base==R.RSP),R.NONE)
    if reg not in (R.RBX,R.RBP,R.RDI,R.RSI,R.R12,R.R13,R.R14,R.R15):return None
    source=_source(il,m,td,seq,eh,cmp.ip,reg,owner,pred)
    if not source:return None
    capfields=_task_captures(il,sm,home,width,None,{reg:('owner',(0x12,outer,0))},[group])
    if not capfields or len(capfields)!=1:return None
    return ins[0].ip,(ty,rt,task,bf[0][5:],sf[0][5:],capfields[0][0],source,get),source


def inline_tasks(lift,m,td,blocks,eh):
    plans={};loads={};il=lift.il
    if not HAVE_ICED or not eh or not isinstance(getattr(il,'bin',None),PE) or not il.bin.is64:return plans,loads
    seq=[i for b in blocks for i in b.insns]
    if not seq or len(seq)>1024 or any(a.next_ip!=b.ip for a,b in zip(seq,seq[1:])):return plans,loads
    for b in blocks:
        if len(b.insns)<4 or not _rr(b.insns[0],M.XOR,R.EDX,R.EDX):continue
        site=_region(lift,m,td,blocks,b,seq,eh)
        if site:
            ip,plan,(load,row,reg)=site;plans[ip]=plan;loads[load]=(row,reg)
    return plans,loads


def emit_kickoff(lift,ip,plan,values):
    ty,rt,task_ty,builder,state,capture,(load,_,reg),end=plan
    value=dict.get(lift.regs,reg)
    if value is None or value._unk or value is not values.get(load):return None
    machine='nestedStateMachine'+lift.new_var()[1:];task=lift.new_var();tn=lift.il.type_name(ty);btn=lift.il.type_name(rt)
    while machine in {safe_ident(p.name) for p in source_params(lift.meta,lift._current_method)}:machine+='Local'
    lift._var_types[task]=task_ty;field=machine+'.'+builder
    for line in (f'{tn} {machine} = default;',f'System.Runtime.CompilerServices.RuntimeHelpers.RunClassConstructor(typeof({btn}).TypeHandle);',
                 f'{field} = {btn}.Create();',f'{machine}.{capture} = {value.text};',f'{machine}.{state} = -1;',
                 f'{field}.Start<{tn}>(ref {machine});',f'var {task} = {acc_get(field+".Task")};'):
        lift.emit(ip,line,None)
    for reg in (*VOLATILE,*('XMM%d'%n for n in range(6))):lift.regs.pop(reg,None)
    lift.regs['RAX']=Expr(task,task_ty,'obj');lift.flags=None;lift._fresh_unknowns()
    return end
