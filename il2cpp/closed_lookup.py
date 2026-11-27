"""Explicit MethodRef for a Win64 nullary instance lookup returning its method type parameter."""
from il2cpp.awaiter import _spec_entry
from il2cpp.binary import PE
from il2cpp.array_origin import _graph,_definitions
from il2cpp.generic_array import object_shared_entry
from il2cpp.names import safe_ident
from il2cpp.csharp import source_field_name
from il2cpp.shared_field import reference_field_at
from il2cpp.text import sdisp
from il2cpp.prelude import HAVE_ICED

if HAVE_ICED:
    from iced_x86 import InstructionInfoFactory, Mnemonic as M, OpAccess, OpKind as K, Register as R, RegisterExt
    _INFO=InstructionInfoFactory();_WRITES={OpAccess.WRITE,OpAccess.COND_WRITE,OpAccess.READ_WRITE,OpAccess.READ_COND_WRITE}
    _SAVED={R.RBX,R.RBP,R.RDI,R.RSI,R.R12,R.R13,R.R14,R.R15}


def _receiver(il,method,byip,pred,site,owner,*,initial=None,this_only=False,producers=None):
    """All paths: a complete copy of reference-type this or a registered
    reference return. A typed phi alone may have an unknown predecessor."""
    work=[(site,R.RCX if initial is None else initial)];seen=set();proved=False
    while work:
        ip,reg=work.pop()
        if (ip,reg) in seen:continue
        if len(seen)>=256:return False
        seen.add((ip,reg))
        if ip==method.addr:
            # An internal backedge can reach the prologue with a different
            # RCX; only the external entry supplies the Win64 this argument.
            if (pred[ip] or method.is_static or reg!=R.RCX or il.meta.typedefs[method.declaring].is_valuetype or
                    not 0<=method.return_type<len(il.types) or il.returns_sret(il.types[method.return_type]) or
                    owner not in il.base_chain_tds(method.declaring)):return False
            proved=True;continue
        if not pred[ip]:return False
        for p in pred[ip]:
            i=byip[p]
            if i.mnemonic==M.CALL and reg not in _SAVED:
                ids=il.addr_candidates.get(i.near_branch_target,())
                if this_only or reg!=R.RAX or len(ids)!=1 or ids[0][0]!='method' or not 0<=ids[0][1]<len(il.meta.methods):return False
                src=il.meta.methods[ids[0][1]]
                if src.addr!=i.near_branch_target or src.generic_container!=-1 or not 0<=src.return_type<len(il.types):return False
                ty=il.types[src.return_type]
                if not ty or il._closed_type_key(ty)!=(0x12,ty[0],0) or owner not in il.base_chain_tds(ty[0]):return False
                if producers is not None:producers[p]=src.index
                proved=True;continue
            if i.mnemonic==M.MOV and i.op0_register==reg and RegisterExt.is_gpr64(i.op1_register):work.append((p,i.op1_register));continue
            if any(u.access in _WRITES and RegisterExt.full_register(u.register)==reg for u in _INFO.info(i).used_registers()):return False
            work.append((p,reg))
    return proved


def _field_input(il,method,byip,pred,call,owner):
    """Trace the *value* passed in RCX to a field load of entry this."""
    defs=_definitions(byip,pred,method.addr,call.ip,R.RCX)
    if len(defs)!=1:return None
    ip,r=defs.pop();i=byip[ip]
    if (i.mnemonic!=M.MOV or i.op0_register!=r or not RegisterExt.is_gpr64(r) or i.op1_kind!=K.MEMORY or
            i.memory_index!=R.NONE or i.has_segment_prefix or i.has_lock_prefix or not RegisterExt.is_gpr64(i.memory_base) or
            not _receiver(il,method,byip,pred,ip,method.declaring,initial=i.memory_base,this_only=True)):return None
    row=reference_field_at(il,method.declaring,sdisp(i.memory_displacement))
    if not row:return None
    decl,fi,ty=row
    if (decl!=method.declaring or not 0<=ty[0]<len(il.meta.typedefs) or il._closed_type_key(ty)!=(0x12,ty[0],0) or
            il.meta.typedefs[ty[0]].generic_container!=-1 or owner not in il.base_chain_tds(ty[0])):return None
    return ip,('this.'+safe_ident(source_field_name(il,fi)),ty)


def spec_lookup(il,slot,call):
    """Prove the closed signature and entry; receiver proof is separate."""
    if (not call.is_call_near or slot.mnemonic!=M.MOV or slot.op0_register!=R.RDX or slot.op1_kind!=K.MEMORY or
            slot.memory_base!=R.RIP or slot.has_segment_prefix or slot.has_lock_prefix):return None
    u=il.decode_slot(slot.ip_rel_memory_address) or {};si=u.get('idx',-1)
    if u.get('kind')!=6 or not 0<=si<len(il.method_specs):return None
    mi,ci,gi=il.method_specs[si]
    if ci!=-1 or gi<0 or not 0<=mi<len(il.meta.methods):return None
    md=il.meta.methods[mi];args=il._method_spec_type_args(gi)
    if (md.is_static or md.flags&7!=6 or md.flags&(0x40|0x800) or md.param_count or not 0<=md.declaring<len(il.meta.typedefs) or
            not 0<=md.generic_container<len(il.meta.generic_containers) or not 0<=md.return_type<len(il.types) or
            safe_ident(md.name)!=md.name or md.name.startswith(('get_','set_','add_','remove_')) or not args or len(args)!=1 or not args[0]):return None
    td=il.meta.typedefs[md.declaring];rt=il.types[md.return_type];own,n,meth,first=il.meta.generic_containers[md.generic_container]
    if (td.generic_container!=-1 or td.is_valuetype or td.flags&0x20 or (own,n,meth)!=(mi,1,1) or il._type_enum(rt)!=0x1e or
            rt[0]!=first or rt[1]&(1<<29) or il._closed_type_key(args[0])!=(0x12,args[0][0],0) or
            not 0<=args[0][0]<len(il.meta.typedefs) or il.meta.typedefs[args[0][0]].generic_container!=-1 or
            il._closed_type_key(il.candidate_return_type(('generic',si)))!=il._closed_type_key(args[0])):return None
    target=call.near_branch_target;entry=_spec_entry(il,si,mi)
    if entry!=target and (si in il._awaiter_spec_indices[mi] or object_shared_entry(il,mi)!=target):return None
    return si,md,args[0]


def closed_lookup_sites(lift,method,blocks,pads,*,producers=None,conversions=None,element_loads=None,field_inputs=None,previous_inputs=None,virtuals=None):
    il=lift.il
    result={}
    if not HAVE_ICED or pads or not isinstance(getattr(il,'bin',None),PE) or not il.bin.is64:return result
    possible=[]
    for b in blocks:
        for j,call in enumerate(b.insns):
            if not j or call.mnemonic!=M.CALL or call.op0_kind!=K.NEAR_BRANCH64:continue
            k=j-1
            # Saving a nonvolatile in the caller's home area is independent
            # of the register arguments. Keep the actual store in the lift.
            park=b.insns[k]
            if (park.mnemonic==M.MOV and park.op0_kind==K.MEMORY and park.memory_base==R.RSP and park.memory_index==R.NONE and
                    not park.has_segment_prefix and park.op1_register in _SAVED):k-=1
            if k<0:continue
            recv=b.insns[k]
            if (recv.mnemonic==M.MOV and recv.op0_register==R.RCX and recv.op1_kind==K.REGISTER and
                    RegisterExt.is_gpr64(recv.op1_register) and recv.op1_register!=R.RDX):k-=1
            if k<0:continue
            slot=b.insns[k]
            if (slot.mnemonic==M.MOV and slot.op0_register==R.RDX and slot.op1_kind==K.MEMORY and slot.memory_base==R.RIP and
                    not slot.has_segment_prefix):possible.append(b.insns[k:j+1])
    if not possible:return result
    seq=[i for b in blocks for i in b.insns];approve=None;certified={}
    if virtuals is not None and any(i.is_call_near_indirect for i in seq):
        from il2cpp.virtual_edges import certified_edge
        def approve(i,by,pred,extent):
            fact=certified_edge(lift,method,i,by,pred,extent)
            if fact is not None:certified[i.ip]=fact
            return fact is not None
    graph=_graph(il,seq,allow_tail=True,runtime_tails=lift.rt_wbarrier,chained=True,virtual_edges=approve)
    if not graph or seq[0].ip!=method.addr:return result
    if certified:virtuals.update(certified)
    pred,_=graph;byip={i.ip:i for i in seq}
    for setup in possible:
        if any(x.next_ip!=z.ip or pred[z.ip]!=[x.ip] for x,z in zip(setup,setup[1:])):continue
        slot,call=setup[0],setup[-1];spec=spec_lookup(il,slot,call)
        if not spec:continue
        si,md,actual=spec
        sources={}; from_element=False
        if element_loads:
            defs=_definitions(byip,pred,method.addr,call.ip,R.RCX)
            if len(defs)==1:
                ip,r=defs.pop();arr=element_loads.get(ip)
                if arr is not None and byip[ip].op0_register==r:
                    elem=il.type_from_ptr(arr[0])
                    from_element=bool(elem and il._closed_type_key(elem)==(0x12,elem[0],0) and md.declaring in il.base_chain_tds(elem[0]))
        ordinary=from_element or _receiver(il,method,byip,pred,call.ip,md.declaring,producers=sources)
        field=None if ordinary or field_inputs is None else _field_input(il,method,byip,pred,call,md.declaring)
        previous=None
        if not ordinary and not field and previous_inputs is not None and result:
            defs=_definitions(byip,pred,method.addr,call.ip,R.RCX)
            if len(defs)==1:
                ip,r=defs.pop()
                if r==R.RAX and ip in result and md.declaring in il.base_chain_tds(result[ip][2][0]):previous=ip
        if ordinary or field or previous is not None:
            result[call.ip]=(si,md.declaring,actual,md.name,False)
            if field:field_inputs[call.ip]=field
            elif previous is not None:previous_inputs[call.ip]=previous
            elif producers is not None:producers.update(sources)
    if result and conversions is not None:
        from il2cpp.truth_operator import truth_owner
        for i in seq:
            if i.mnemonic!=M.CALL or i.op0_kind!=K.NEAR_BRANCH64:continue
            ids=il.addr_candidates.get(i.near_branch_target,())
            if len(ids)!=1 or ids[0][0]!='method' or not 0<=ids[0][1]<len(il.meta.methods):continue
            m=il.meta.methods[ids[0][1]]
            if m.addr!=i.near_branch_target or not truth_owner(il,m):continue
            defs=_definitions(byip,pred,method.addr,i.ip,R.RCX)
            if len(defs)==1:
                p,r=defs.pop()
                if r==R.RAX and p in result and m.declaring in il.base_chain_tds(result[p][2][0]):conversions[i.ip]=p
    return result
