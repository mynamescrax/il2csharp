"""Lifetime witnesses for a frame also used for value formatting. A stack
LEA, including one above a kickoff, is not by itself a bounded borrow."""
from il2cpp.async_start import _rr
from il2cpp.prelude import HAVE_ICED
from il2cpp.text import sdisp

if HAVE_ICED:
    from iced_x86 import Decoder, Mnemonic as M, OpKind as K, Register as R, RegisterExt


def _string_method(il,target,owner):
    ids=il.addr_candidates.get(target,())
    if len(ids)!=1 or ids[0][0]!='method':return False
    md=il.meta.methods[ids[0][1]]
    return (md.addr==target and not md.is_static and not md.param_count and md.generic_container<0 and
            md.name=='ToString' and il.typedef_full(md.declaring)==owner and 0<=md.return_type<len(il.types) and
            il._type_enum(il.types[md.return_type])==0x0e)


def formatting_uses(il,seq,pred,ranges):
    """Return just the proved accesses, not an interval to exempt from the
    branch or frame scan. The box is fully constructed before Enum.ToString
    and the only result escaping either formatting call is a string."""
    bounded=set()
    for k,addr in enumerate(seq[:-1]):
        if (addr.mnemonic!=M.LEA or addr.op0_register!=R.RCX or addr.memory_base!=R.RSP or addr.memory_index!=R.NONE or
                addr.has_segment_prefix):continue
        off=sdisp(addr.memory_displacement);call=seq[k+1]
        if call.mnemonic!=M.CALL or call.op0_kind!=K.NEAR_BRANCH64 or pred[call.ip]!={addr.ip}:continue
        if off>=max(b for _,b in ranges):
            # A no-argument forwarding thunk on a uint64 receiver: the
            # borrowed eight bytes are above both local homes.
            t=call.near_branch_target;raw=il.bin.read(t,7) or b'';stub=list(Decoder(64,raw,ip=t))
            if (len(stub)==2 and _rr(stub[0],M.XOR,R.EDX,R.EDX) and stub[1].mnemonic==M.JMP and
                    stub[1].op0_kind==K.NEAR_BRANCH64 and _string_method(il,stub[1].near_branch_target,'System.UInt64')):bounded.add(addr.ip)
            continue
        if k<6 or not any(a<=off and off+20<=b for a,b in ranges) or not _string_method(il,call.near_branch_target,'System.Enum'):continue
        window=seq[k-6:k+2];slot,klass,monitor,load,value,null,_,_=window
        if (any(pred[y.ip]!={x.ip} for x,y in zip(window,window[1:])) or any(i.has_segment_prefix or i.memory_index!=R.NONE for i in window) or
                slot.mnemonic!=M.MOV or slot.memory_base!=R.RIP or not RegisterExt.is_gpr64(slot.op0_register)):continue
        u=il.decode_slot(slot.ip_rel_memory_address) or {};ty=u.get('type');td=u.get('td')
        if (u.get('kind')!=1 or td is None or not 0<=td<len(il.meta.typedefs) or not il.meta.typedefs[td].is_enum or
                il._closed_type_key(ty)!=(0x11,td,0) or il._sf_field_size(ty,0)!=4):continue
        if (any(i.mnemonic!=M.MOV or i.op0_kind!=K.MEMORY or i.memory_base!=R.RSP or sdisp(i.memory_displacement)!=off+n
                for i,n in ((klass,0),(monitor,8),(value,16))) or klass.op1_register!=slot.op0_register or
                monitor.op1_kind!=K.IMMEDIATE32TO64 or monitor.immediate32to64!=-1 or
                load.mnemonic!=M.MOV or load.op1_kind!=K.MEMORY or not RegisterExt.is_gpr32(load.op0_register) or
                value.op1_register!=load.op0_register or not _rr(null,M.XOR,R.EDX,R.EDX)):continue
        bounded.update(i.ip for i in (klass,monitor,value,addr))
    return bounded
