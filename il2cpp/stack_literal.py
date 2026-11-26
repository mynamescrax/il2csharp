"""Recover canonical Boolean bytes and immutable managed string references at
Win64 stack argument positions. A slot's display name is not its type."""
from il2cpp.prelude import HAVE_ICED
from il2cpp.text import sdisp
from il2cpp.runtime.meta import meta_lit_repr
from il2cpp.binary import PE
from il2cpp.x64 import KLASS_VTABLE

if HAVE_ICED:
    from iced_x86 import FlowControl as F, InstructionInfoFactory, MemorySizeExt, Mnemonic as M, OpAccess, OpKind as K, Register as R, RegisterExt
    _INFO=InstructionInfoFactory();_WRITE={OpAccess.WRITE,OpAccess.COND_WRITE,OpAccess.READ_WRITE,OpAccess.READ_COND_WRITE}


def stack_literal(il,seq,end,offset,ty):
    key=il._closed_type_key(ty)
    if key not in ((2,0),(0x0e,0)):return None
    width=1 if key==(2,0) else 8;source=None
    for i in reversed(seq[max(0,end-24):end]):
        if (i.flow_control!=F.NEXT or i.is_invalid or i.has_segment_prefix or i.has_lock_prefix or
                any(u.access in _WRITE and RegisterExt.full_register(u.register)==R.RSP for u in _INFO.info(i).used_registers())):return None
        if source is not None:
            if any(u.access in _WRITE and RegisterExt.full_register(u.register)==source for u in _INFO.info(i).used_registers()):
                if i.mnemonic!=M.MOV or i.op0_register!=source or i.memory_base!=R.RIP:return None
                use=il.decode_slot(i.ip_rel_memory_address) or {};idx=use.get('idx',-1)
                if use.get('kind')==5 and 0<=idx<len(il.meta.string_literals):
                    val=il.meta.string_literal(idx)
                    # Only the untruncated printable subset. Never use a
                    # disassembly preview or an untyped native C string.
                    if val.isascii() and all(32<=ord(c)<127 for c in val) and len(val.replace('\\','\\\\').replace('"','\\"'))<=96:
                        return meta_lit_repr(val)
                return None
            continue
        for access in _INFO.info(i).used_memory():
            if access.access not in _WRITE:continue
            if (i.op0_kind!=K.MEMORY or i.memory_base!=R.RSP or i.memory_index!=R.NONE or
                    access.base!=R.RSP or access.index!=R.NONE or i.mnemonic in (M.BT,M.BTC,M.BTR,M.BTS)):return None
            off=sdisp(i.memory_displacement);n=MemorySizeExt.size(i.memory_size)
            if not n:return None
            if off>=offset+width or off+n<=offset:continue
            if i.mnemonic!=M.MOV or off!=offset:return None
            if width==1:
                if i.op1_kind not in (K.IMMEDIATE8,K.IMMEDIATE32,K.IMMEDIATE32TO64):return None
                low=i.immediate(1)&255
                return ('true' if low else 'false') if low in (0,1) else None
            if n!=8 or not RegisterExt.is_gpr64(i.op1_register):return None
            source=i.op1_register
    return None


def stack_literal_args(lift,method,first,out):
    block=getattr(getattr(lift,'out',None),'block',None);ip=getattr(lift,'_cur_ip',0);il=lift.il
    if (not HAVE_ICED or not block or not ip or not isinstance(getattr(il,'bin',None),PE) or not il.bin.is64 or method.generic_container!=-1 or
            not 0<=method.return_type<len(il.types) or il._type_enum(il.types[method.return_type])==0x15):return
    j=next((j for j,i in enumerate(block.insns) if i.ip==ip),None)
    if j is None or block.insns[j].mnemonic!=M.CALL:return
    call=block.insns[j]
    if call.op0_kind==K.NEAR_BRANCH64:
        if method.addr!=call.near_branch_target or il.addr_candidates.get(method.addr)!=[('method',method.index)]:return
    elif call.op0_kind==K.MEMORY:
        slot=getattr(lift,'vt_recv_slot',None);recv=getattr(lift,'vt_recv',None)
        if (slot is None or call.memory_displacement!=KLASS_VTABLE+16*slot or call.memory_index!=R.NONE or
                not recv or not recv.ty or recv.kind!='obj' or il._closed_type_key(recv.ty)!=(0x12,recv.ty[0],0) or
                il.vtable_method(recv.ty[0],slot)!=method.index or method.slot!=slot or not method.flags&0x40):return
    else:return
    for k,p in enumerate(il.meta.method_params(method),first):
        if k<4 or k>=len(out) or not 0<=p.type<len(il.types):continue
        val=stack_literal(il,block.insns,j,32+8*(k-4),il.types[p.type])
        if val is not None:out[k]=val
