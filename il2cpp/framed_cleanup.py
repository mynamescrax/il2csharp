"""Win64 base-tail argument provenance across bounded, by-value struct cleanup."""
from il2cpp.awaiter import _spec_entry
from il2cpp.prelude import HAVE_ICED
from il2cpp.text import sdisp

if HAVE_ICED:
    from iced_x86 import FlowControl as F, Mnemonic as M, OpKind as K, Register as R, RegisterExt
    _SAVED={R.RBX,R.RSI,R.RDI,R.R12,R.R13,R.R14,R.R15}


def _rr(i,mn,dst,src): return i.mnemonic==mn and i.op0_register==dst and i.op1_register==src


def _frame_pair(start,out):
    """Use the post-SUB RSP as origin. R11 must point at the pushed RBP,
    and the three home restores must undo the three pre-PUSH stores."""
    if len(start)!=11 or len(out)!=11: return None
    s1,s2,s3,push,bp,sub,check,flag,arg,recv,branch=start
    zero,zx,rdx,rcx,frame,r1,r2,r3,reset,pop,jump=out
    if (push.mnemonic!=M.PUSH or push.op0_register!=R.RBP or bp.mnemonic!=M.LEA or bp.op0_register!=R.RBP or bp.memory_base!=R.RSP or
            sub.mnemonic!=M.SUB or sub.op0_register!=R.RSP or sub.op1_kind!=K.IMMEDIATE32TO64 or
            frame.mnemonic!=M.LEA or frame.op0_register!=R.R11 or frame.memory_base!=R.RSP or
            not _rr(reset,M.MOV,R.RSP,R.R11) or pop.mnemonic!=M.POP or pop.op0_register!=R.RBP or
            jump.mnemonic!=M.JMP or jump.op0_kind!=K.NEAR_BRANCH64): return None
    size=sub.immediate32to64; bias=size+sdisp(bp.memory_displacement)
    if not 0x20<=size<=0xffff or size%16 or not 0<bias<size or frame.memory_displacement!=size: return None
    homes={i.op1_register for i in (s1,s2,s3)}
    if len(homes)!=3 or not homes<=_SAVED: return None
    for save,restore,off in zip((s1,s2,s3),(r1,r2,r3),(8,16,24)):
        if (save.mnemonic!=M.MOV or save.memory_base!=R.RSP or save.memory_displacement!=off or restore.mnemonic!=M.MOV or
                restore.memory_base!=R.R11 or restore.memory_displacement!=off+8 or restore.op0_register!=save.op1_register): return None
    if (check.mnemonic!=M.CMP or check.memory_base!=R.RCX or check.memory_size!=1 or check.op1_kind!=K.IMMEDIATE8 or check.immediate8 or
            branch.mnemonic!=M.JE or branch.op0_kind!=K.NEAR_BRANCH64 or branch.near_branch_target!=zero.ip or
            flag.mnemonic!=M.MOVZX or not RegisterExt.is_gpr32(flag.op0_register) or flag.op1_register!=R.R8L or
            not _rr(arg,M.MOV,arg.op0_register,R.RDX) or not _rr(recv,M.MOV,recv.op0_register,R.RCX) or
            {arg.op0_register,recv.op0_register,RegisterExt.full_register(flag.op0_register)}!=homes or
            not _rr(zero,M.XOR,R.R9D,R.R9D) or zx.mnemonic!=M.MOVZX or zx.op0_register!=R.R8D or
            not RegisterExt.is_gpr8(zx.op1_register) or zx.op1_register in (R.AH,R.BH,R.CH,R.DH) or
            RegisterExt.full_register(zx.op1_register)!=RegisterExt.full_register(flag.op0_register) or
            not _rr(rdx,M.MOV,R.RDX,arg.op0_register) or not _rr(rcx,M.MOV,R.RCX,recv.op0_register)): return None
    return size,bias,recv.op0_register


def _struct_use(il,owner,seq,frame):
    """A hidden sret pointer and a distinct byref receiver. Prove the
    extent of each borrow from the closed type and its registered call."""
    if len(seq)<9: return 0
    size,bias,this=frame;zero,buf,self_arg,get,slot,borrow=seq[:6]
    if (not _rr(zero,M.XOR,R.R8D,R.R8D) or buf.mnemonic!=M.LEA or buf.op0_register!=R.RCX or buf.memory_base!=R.RBP or
            not _rr(self_arg,M.MOV,R.RDX,this) or get.mnemonic!=M.CALL or get.op0_kind!=K.NEAR_BRANCH64 or
            slot.mnemonic!=M.MOV or slot.op0_register!=R.RDX or slot.memory_base!=R.RIP or
            borrow.mnemonic!=M.LEA or borrow.op0_register!=R.RCX or borrow.memory_base!=R.RBP): return 0
    ids=il.addr_candidates.get(get.near_branch_target,())
    if len(ids)!=1 or ids[0][0]!='method' or not 0<=ids[0][1]<len(il.meta.methods): return 0
    getter=il.meta.methods[ids[0][1]]
    if (getter.addr!=get.near_branch_target or getter.declaring!=owner or getter.is_static or getter.flags&0x40 or getter.param_count or
            getter.generic_container!=-1 or not getter.name.startswith('get_') or not 0<=getter.return_type<len(il.types)): return 0
    ty=il.types[getter.return_type];key=il._closed_type_key(ty)
    if not key or key[0]!=0x15 or key[1][0]!=0x11 or key[-1] or not il.returns_sret(ty): return 0
    width=il._sf_field_size(ty,0);a=bias+sdisp(buf.memory_displacement);b=bias+sdisp(borrow.memory_displacement)
    if (not width or not 16<=width<=128 or width%16 or min(a,b)<0x20 or max(a,b)+width>size or abs(a-b)<width or b%16): return 0
    n=6+2*(width//16)
    if n>=len(seq): return 0
    for k in range(width//16):
        load,store=seq[6+2*k:8+2*k]
        if (load.mnemonic!=M.MOVUPS or not R.XMM0<=load.op0_register<=R.XMM5 or load.memory_base!=R.RAX or load.memory_displacement!=16*k or
                store.mnemonic!=M.MOVAPS or store.op1_register!=load.op0_register or store.memory_base!=R.RBP or
                bias+sdisp(store.memory_displacement)!=b+16*k): return 0
    use=seq[n]; u=il.decode_slot(slot.ip_rel_memory_address) or {};si=u.get('idx',-1)
    if use.mnemonic!=M.CALL or use.op0_kind!=K.NEAR_BRANCH64 or u.get('kind')!=6 or not 0<=si<len(il.method_specs): return 0
    mi,ci,gi=il.method_specs[si];args=il._method_spec_type_args(ci)
    if gi!=-1 or not args or tuple(il._closed_type_key(t) for t in args)!=key[2] or not 0<=mi<len(il.meta.methods): return 0
    md=il.meta.methods[mi]
    if (md.declaring!=key[1][1] or md.is_static or md.flags&0x40 or md.param_count or md.generic_container!=-1 or
            not 0<=md.return_type<len(il.types) or md.name not in ('get_Count','Clear') or
            il._closed_type_key(il.types[md.return_type])!=((8,0) if md.name=='get_Count' else (1,0)) or
            _spec_entry(il,si,mi)!=use.near_branch_target): return 0
    return n+1


def framed_cleanup_tail(lift,block,jump):
    il=lift.il;blocks=lift._blocks;method=lift._current_method
    if (not blocks or blocks[-1] is not block or not block.insns or jump.ip!=block.insns[-1].ip or block.succs or
            not blocks[0].is_entry or blocks[0].preds or not blocks[0].insns or blocks[0].insns[0].ip!=method.addr or
            il.function_extent(method.addr)!=(method.addr,jump.next_ip) or il.eh_regions(method.addr)): return False
    seq=[i for b in blocks for i in b.insns]
    if (any(a.next_ip!=b.ip for a,b in zip(seq,seq[1:])) or any(i.has_segment_prefix or i.has_lock_prefix or
            i.has_rep_prefix or i.has_repne_prefix or i.memory_index!=R.NONE for i in seq)): return False
    if any(i.op0_kind!=K.NEAR_BRANCH64 or not il.bin.is_exec_va(i.near_branch_target) or
           method.addr<=i.near_branch_target<jump.next_ip for i in seq if i.flow_control==F.CALL): return False
    frame=_frame_pair(blocks[0].insns,block.insns)
    if not frame: return False
    size,bias,this=frame
    body=seq[len(blocks[0].insns):-len(block.insns)]; entries={i.ip for i in body}|{block.insns[0].ip};targets=set();k=0
    while k<len(body):
        i=body[k]
        if _rr(i,M.XOR,R.R8D,R.R8D):
            n=_struct_use(il,method.declaring,body[k:],frame)
            if not n: return False
            entries.difference_update(x.ip for x in body[k+1:k+n]);k+=n;continue
        k+=1
        if i.mnemonic==M.LEA and i.op0_register==R.RCX and i.memory_base==R.RIP:
            if k>=len(body): return False
            call=body[k]
            if call.mnemonic!=M.CALL or call.op0_kind!=K.NEAR_BRANCH64 or call.near_branch_target!=lift.rt_init_meta: return False
            entries.discard(call.ip);k+=1;continue
        if i.flow_control in (F.CONDITIONAL_BRANCH,F.UNCONDITIONAL_BRANCH) and i.op0_kind==K.NEAR_BRANCH64:
            targets.add(i.near_branch_target);continue
        if i.flow_control!=F.NEXT: return False
        if i.memory_base==R.RBP:
            if (i.mnemonic!=M.MOVUPS or not R.XMM0<=i.op1_register<=R.XMM5 or
                    not 0x20<=bias+sdisp(i.memory_displacement)<=size-16): return False
            continue
        # Outside the bounded calls/copies only scalar tests, zeroing scratch
        # XMM lanes, and byte flags remain. No aliases of the frame, no
        # reloads of the saved input registers from arbitrary memory.
        if (i.mnemonic in (M.CMP,M.MOV) and i.op0_kind==K.MEMORY and i.memory_base in (this,R.RIP) and
                i.memory_size==1 and i.op1_kind==K.IMMEDIATE8 and i.immediate8 in (0,1)): continue
        if _rr(i,M.TEST,R.EAX,R.EAX): continue
        if i.mnemonic==M.XORPS and i.op0_register==i.op1_register and R.XMM0<=i.op0_register<=R.XMM5: continue
        return False
    return targets<=entries
