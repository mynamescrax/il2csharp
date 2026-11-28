"""A managed reference saved from RAX before a class guard or an addressed
stack home. Capture the already resolved call at its instruction, so later
register/stack renders cannot execute the producer again."""
from il2cpp.equivalent_binary import _amd64
from il2cpp.prelude import HAVE_ICED
from il2cpp.x64 import KLASS_INITIALIZED, KLASS_VTABLE

if HAVE_ICED:
    from iced_x86 import FlowControl as F, InstructionInfoFactory, Mnemonic as M, OpAccess, OpKind as K, Register as R, RegisterExt
    _SAVED={R.RBX,R.RDI,R.RSI,R.RBP,R.R12,R.R13,R.R14,R.R15}
    _INFO=InstructionInfoFactory();_WRITE={OpAccess.WRITE,OpAccess.READ_WRITE,OpAccess.COND_WRITE,OpAccess.READ_COND_WRITE}


def reference_vector(il,rt):
    """Only SZARRAY of a closed, by-value reference element. Keeping a
    reference is independent of proving a later header or element load."""
    if not rt or il._type_enum(rt)!=0x1d:return False
    key=il._closed_type_key(rt)
    if not key or key[0]!=0x1d or key[-1]!=0:return False
    elem=key[1]
    if elem==(14,0):return True
    if not elem or elem[0]!=0x12 or elem[-1] or not 0<=elem[1]<len(il.meta.typedefs):return False
    td=il.meta.typedefs[elem[1]]
    return not td.is_valuetype and td.generic_container==-1


def _saved_array(il,call,after):
    if call.op0_kind!=K.NEAR_BRANCH64:return False
    ids=il.addr_candidates.get(call.near_branch_target,())
    if len(ids)!=1 or ids[0][0]!='method' or not 0<=ids[0][1]<len(il.meta.methods):return False
    m=il.meta.methods[ids[0][1]]
    if not 0<=m.return_type<len(il.types):return False
    rt=il.types[m.return_type]
    if not reference_vector(il,rt):return False
    ip=call.next_ip
    for i in after:
        if i.ip!=ip or i.flow_control!=F.NEXT or i.has_segment_prefix or i.has_lock_prefix:return False
        if i.mnemonic==M.MOV and i.op1_register==R.RAX:
            if i.op0_register in _SAVED or i.op0_kind==K.MEMORY and i.memory_base==R.RSP and i.memory_index==R.NONE:return True
        if any(u.access in _WRITE and RegisterExt.full_register(u.register)==R.RAX for u in _INFO.info(i).used_registers()):return False
        ip=i.next_ip
    return False


def saved_references(lift,blocks):
    il=lift.il;sites={}
    if not HAVE_ICED or not _amd64(getattr(il,'bin',None)) or il.meta.version!=31:return sites
    for b in blocks:
        seq=b.insns
        for j,call in enumerate(seq[:-2]):
            if call.mnemonic!=M.CALL:continue
            if _saved_array(il,call,seq[j+1:j+7]):
                sites[call.ip]=il.addr_candidates[call.near_branch_target][0];continue
            a,b2=seq[j+1:j+3]
            if (a.mnemonic!=M.MOV or call.next_ip!=a.ip or a.next_ip!=b2.ip or
                    any(i.has_segment_prefix or i.memory_index!=R.NONE or i.has_lock_prefix for i in (a,b2))):continue
            if a.op0_kind==K.MEMORY and a.memory_base==R.RSP and a.op1_register==R.RAX:
                if b2.mnemonic!=M.LEA or not RegisterExt.is_gpr64(b2.op0_register) or b2.memory_base!=R.RSP or b2.memory_displacement!=a.memory_displacement:continue
            elif (a.op0_register==R.RCX and a.memory_base==R.RIP and b2.mnemonic==M.MOV and b2.op1_register==R.RAX and b2.op0_register in _SAVED and
                  j+3<len(seq) and seq[j+3].mnemonic==M.CMP and seq[j+3].memory_base==R.RCX and seq[j+3].memory_displacement==KLASS_INITIALIZED):
                if (il.decode_slot(a.ip_rel_memory_address) or {}).get('kind')!=1:continue
            else:continue
            if call.op0_kind==K.NEAR_BRANCH64:
                ids=il.addr_candidates.get(call.near_branch_target,())
                if len(ids)==1 and ids[0][0]=='method':sites[call.ip]=ids[0]
            elif call.op0_register==R.RAX and j>=4:
                # VirtualInvokeData for a one-argument virtual method: its
                # function and MethodInfo come from the very same klass. The
                # existing call resolver must also see that receiver at RCX.
                klass,arg,ptr,info=seq[j-4:j];d=ptr.memory_displacement
                if (all(x.next_ip==y.ip for x,y in zip(seq[j-4:j],seq[j-3:j+1])) and
                        all(not x.has_segment_prefix and x.memory_index==R.NONE for x in (klass,ptr,info)) and
                        klass.mnemonic==M.MOV and klass.op0_register==R.R8 and klass.memory_base==R.RCX and not klass.memory_displacement and
                        arg.mnemonic==M.MOV and arg.op0_register==R.EDX and arg.op1_kind==K.IMMEDIATE32 and
                        ptr.mnemonic==M.MOV and ptr.op0_register==R.RAX and ptr.memory_base==R.R8 and d>=KLASS_VTABLE and (d-KLASS_VTABLE)%16==0 and
                        info.mnemonic==M.MOV and info.op0_register==R.R8 and info.memory_base==R.R8 and info.memory_displacement==d+8):
                    sites[call.ip]=('virtual',(d-KLASS_VTABLE)//16)
    return sites


def parked_properties(lift,method,blocks,pads):
    """A public static reference getter saved before another receiver use.
    Validate each call independently; a second use of the same getter may
    run only on the success edge and may return a different object."""
    from il2cpp.array_origin import _graph
    from il2cpp.names import safe_ident
    il=lift.il;result={};windows=[]
    if not HAVE_ICED or pads or not _amd64(getattr(il,'bin',None)) or il.meta.version!=31:return result
    for b in blocks:
        for k in range(1,len(b.insns)-1):
            zero,call,save=b.insns[k-1:k+2]
            if (zero.mnemonic!=M.XOR or zero.op0_register!=zero.op1_register or zero.op0_register!=R.ECX or
                    not call.is_call_near or save.mnemonic!=M.MOV or save.op1_register!=R.RAX or save.op0_register not in _SAVED):continue
            ids=il.addr_candidates.get(call.near_branch_target,())
            if len(ids)!=1 or ids[0][0]!='method' or not 0<=ids[0][1]<len(il.meta.methods):continue
            md=il.meta.methods[ids[0][1]];prop=lift._accessor_prop(md.index)
            if (md.addr==call.near_branch_target and md.is_static and not md.param_count and md.generic_container==-1 and
                    not md.flags&0x40 and md.flags&7==6 and prop and prop[0]=='get' and not prop[2] and md.name=='get_'+prop[1] and
                    prop[1].isidentifier() and safe_ident(prop[1])==prop[1] and 0<=md.return_type<len(il.types) and
                    reference_vector(il,il.types[md.return_type])):windows.append((b.insns[k-1:k+2],md))
        for k in range(1,len(b.insns)-2):
            zero,call,load,save=b.insns[k-1:k+3]
            if (not call.is_call_near or zero.mnemonic!=M.XOR or zero.op0_register!=zero.op1_register or zero.op0_register!=R.ECX or
                    load.mnemonic!=M.MOV or load.op0_register!=R.RCX or load.op1_kind!=K.MEMORY or
                    load.memory_index!=R.NONE or load.has_segment_prefix or save.mnemonic!=M.MOV or save.op1_register!=R.RAX or save.op0_register not in _SAVED):continue
            ids=il.addr_candidates.get(call.near_branch_target,())
            if len(ids)!=1 or ids[0][0]!='method' or not 0<=ids[0][1]<len(il.meta.methods):continue
            md=il.meta.methods[ids[0][1]];prop=lift._accessor_prop(md.index)
            if (not md.is_static or md.param_count or md.generic_container!=-1 or md.flags&7!=6 or md.flags&0x40 or
                    md.addr!=call.near_branch_target or not prop or prop[0]!='get' or prop[2] or safe_ident(prop[1])!=prop[1] or
                    not prop[1].isidentifier() or md.name!='get_'+prop[1] or not 0<=md.return_type<len(il.types) or
                    not 0<=md.declaring<len(il.meta.typedefs) or il.meta.typedefs[md.declaring].declaring!=-1):continue
            ty=il.types[md.return_type]
            if not ty or il._closed_type_key(ty)!=(0x12,ty[0],0) or not 0<=ty[0]<len(il.meta.typedefs) or il.meta.typedefs[ty[0]].generic_container!=-1:continue
            windows.append((b.insns[k-1:k+3],md))
    if not windows:return result
    seq=[i for b in blocks for i in b.insns];g=_graph(il,seq,allow_tail=True,chained=True,runtime_tails=lift.rt_wbarrier)
    if not g or seq[0].ip!=method.addr:return result
    for w,md in windows:
        if all(a.next_ip==b.ip and g[0][b.ip]==[a.ip] for a,b in zip(w,w[1:])):result[w[1].ip]=('getter',md.index)
    return result


def capture_saved_reference(lift,ins,mi,recv,result,dispatch):
    fact=getattr(lift,'_saved_references',{}).get(ins.ip)
    if not fact or mi is None or not 0<=mi<len(lift.meta.methods):return False
    il=lift.il;m=il.meta.methods[mi];key=il._closed_type_key;rt=result.ty
    if (not rt or m.generic_container!=-1 or not 0<=m.return_type<len(il.types) or key(il.types[m.return_type])!=key(rt) or
            m.flags&0x800 and fact[0]!='getter' or not 0<=m.declaring<len(il.meta.typedefs) or il.meta.typedefs[m.declaring].generic_container!=-1):return False
    if not reference_vector(il,rt) and (key(rt)!=(0x12,rt[0],0) or not 0<=rt[0]<len(il.meta.typedefs) or il.meta.typedefs[rt[0]].generic_container!=-1):return False
    if fact[0] in ('method','getter'):
        if (fact[1]!=mi or m.addr!=ins.near_branch_target or
                m.flags&0x40 and not (m.flags&0x20 or il.meta.typedefs[m.declaring].flags&0x100)):return False
    else:
        if (not recv or recv is not dispatch or recv.kind!='obj' or not recv.ty or key(recv.ty)!=(0x12,recv.ty[0],0) or
                not 0<=recv.ty[0]<len(il.meta.typedefs) or il.meta.typedefs[recv.ty[0]].flags&0x20 or il.vtable_method(recv.ty[0],fact[1])!=mi or m.slot!=fact[1] or
                m.is_static or not m.flags&0x40 or m.param_count!=1):return False
        ps=il.meta.method_params(m)
        if len(ps)!=1 or not 0<=ps[0].type<len(il.types):return False
        pt=il.types[ps[0].type];pk=key(pt)
        if pt and pk==(0x11,pt[0],0) and 0<=pt[0]<len(il.meta.typedefs):
            t=il.meta.typedefs[pt[0]]
            if not t.is_enum or not 0<=t.element<len(il.types):return False
            pk=key(il.types[t.element])
        if pk not in ((8,0),(9,0)):return False
    # Unlike a late use-bind, no text has escaped this result yet. In
    # particular an identical earlier call is a separate evaluation.
    from il2cpp.expr import Expr,acc_get
    local=lift.new_var()
    if fact[0]=='getter':
        from il2cpp.metadata import source_params
        from il2cpp.names import safe_ident
        caller=getattr(lift,'_current_method',None)
        taken={safe_ident(p.name) for p in source_params(lift.meta,caller)} if caller else set()
        while local in taken:local=lift.new_var()
    lift._var_types[local]=rt;lift._type_hints[local]=rt
    lift.emit(ins.ip,'var %s = %s;'%(local,result.text if result.text.startswith('__accget(') else acc_get(result.text)),None)
    value=Expr(local,rt,'arr' if fact[0]=='getter' and reference_vector(il,rt) else 'obj');lift.regs['RAX']=value
    if fact[0]=='getter':lift._parked_getter_values.add(value)
    if reference_vector(il,rt):lift._captured_arrays[ins.ip]=value
    return True


def tested_string_operator(lift,ins,mi,args,regs):
    """An immediately tested comparison of a returned string with a literal.
    Both operands are typed, and no pending discarded comparison is emitted."""
    il=lift.il;m=il.meta.methods[mi]
    if (not m.is_static or m.param_count!=2 or len(args)!=2 or m.addr!=ins.near_branch_target or
            not m.flags&0x800 or m.flags&7!=6 or il.addr_candidates.get(m.addr)!=[('method',mi)] or
            il.meta.typedefs[m.declaring].namespace!='System' or il.meta.typedefs[m.declaring].name!='String' or
            getattr(getattr(lift,'_current_method',None),'index',mi)==mi or not 0<=m.return_type<len(il.types) or
            il._closed_type_key(il.types[m.return_type])!=(2,0)):return None
    ps=il.meta.method_params(m)
    if len(ps)!=2 or any(not 0<=p.type<len(il.types) or il._closed_type_key(il.types[p.type])!=(14,0) for p in ps):return None
    a,b=regs[:2]
    if (not a or a._unk or il._closed_type_key(a.ty)!=(14,0) or not b or b._unk or b.kind!='str' or
            not b.text.startswith('"') or not b.text.endswith('"') or a is b or
            il.bin.read(ins.next_ip,3) not in (b'\x84\xc0\x74',b'\x84\xc0\x75') and il.bin.read(ins.next_ip,4) not in (b'\x84\xc0\x0f\x84',b'\x84\xc0\x0f\x85')):return None
    return '((%s) %s (%s))'%(args[0],'==' if m.name=='op_Equality' else '!=',args[1])
