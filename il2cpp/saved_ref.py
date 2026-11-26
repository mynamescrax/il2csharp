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


def _saved_array(il,call,after):
    if call.op0_kind!=K.NEAR_BRANCH64:return False
    ids=il.addr_candidates.get(call.near_branch_target,())
    if len(ids)!=1 or ids[0][0]!='method' or not 0<=ids[0][1]<len(il.meta.methods):return False
    m=il.meta.methods[ids[0][1]]
    if not 0<=m.return_type<len(il.types):return False
    rt=il.types[m.return_type]
    if not rt or il._type_enum(rt)!=0x1d or il._closed_type_key(rt)!=(0x1d,(14,0),0):return False
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


def capture_saved_reference(lift,ins,mi,recv,result,dispatch):
    fact=getattr(lift,'_saved_references',{}).get(ins.ip)
    if not fact or mi is None or not 0<=mi<len(lift.meta.methods):return False
    il=lift.il;m=il.meta.methods[mi];key=il._closed_type_key;rt=result.ty
    if (not rt or m.generic_container!=-1 or not 0<=m.return_type<len(il.types) or key(il.types[m.return_type])!=key(rt) or
            m.flags&0x800 or not 0<=m.declaring<len(il.meta.typedefs) or il.meta.typedefs[m.declaring].generic_container!=-1):return False
    if key(rt)!=(0x1d,(14,0),0) and (key(rt)!=(0x12,rt[0],0) or not 0<=rt[0]<len(il.meta.typedefs) or il.meta.typedefs[rt[0]].generic_container!=-1):return False
    if fact[0]=='method':
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
    local=lift.new_var();lift._var_types[local]=rt;lift._type_hints[local]=rt
    lift.emit(ins.ip,'var %s = %s;'%(local,acc_get(result.text)),None)
    lift.regs['RAX']=Expr(local,rt,'obj')
    return True
