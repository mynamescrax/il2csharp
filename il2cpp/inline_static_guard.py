"""Recover the public getter at a fresh, null-checked static reference read.
The caller inlines the same one-slot guard as the registered getter: no
extra class initialization, call, or read may be moved across that load."""
from il2cpp.array_origin import _graph,_definitions
from il2cpp.equivalent_binary import _amd64,_writable
from il2cpp.csharp import FA_INITONLY
from il2cpp.shared_field import whole_field_at
from il2cpp.prelude import HAVE_ICED
from il2cpp.static_getter import alias_for_slot
from il2cpp.text import reg_name,sdisp
from il2cpp.x64 import KLASS_STATIC_FIELDS

if HAVE_ICED:
    from iced_x86 import Mnemonic as M,MemorySizeExt,OpKind as K,Register as R,RegisterExt as RX


def _direct_use(il,by,pred,start,reg,owner):
    ip=start
    for _ in range(8):
        i=by.get(ip)
        if not i or i.has_segment_prefix or i.has_lock_prefix or i.memory_index!=R.NONE:return False
        if i.mnemonic==M.MOV and i.memory_base==reg and i.op0_kind==K.MEMORY and i.op1_kind==K.IMMEDIATE8 and i.immediate8 in (0,1):
            field=whole_field_at(il,owner,sdisp(i.memory_displacement),1)
            return bool(field and field[0]==owner and il._closed_type_key(field[2])==(2,0) and not field[2][1]&FA_INITONLY)
        if reg!=R.RCX:return False
        if i.mnemonic in (M.CALL,M.JMP):
            ids=il.addr_candidates.get(i.near_branch_target,()) if i.op0_kind==K.NEAR_BRANCH64 else ()
            if len(ids)!=1 or ids[0][0]!='method' or not 0<=ids[0][1]<len(il.meta.methods):return False
            m=il.meta.methods[ids[0][1]]
            return m.declaring==owner and m.addr==i.near_branch_target and not m.is_static and not m.flags&0x40 and m.generic_container==-1
        if not (i.mnemonic in (M.MOV,M.MOVSS) and i.memory_base==R.RIP and i.op0_register in (R.RDX,R.R8,R.R9,R.XMM1,R.XMM2,R.XMM3) or
                i.mnemonic==M.XOR and i.op0_register==i.op1_register and i.op0_register in (R.EDX,R.R8D,R.R9D) or
                i.mnemonic==M.ADD and i.op0_register==R.RSP and i.op1_kind in (K.IMMEDIATE32TO64,K.IMMEDIATE8TO64) or
                i.mnemonic==M.POP and i.op0_register in (R.RBX,R.RDI,R.RSI,R.RBP,R.R12,R.R13,R.R14,R.R15)):return False
        if pred.get(i.next_ip)!=[ip]:return False
        ip=i.next_ip
    return False


def checked_statics(lift,method,blocks,pads):
    il=lift.il;out={};candidates=[]
    if not HAVE_ICED or pads or il.meta.version!=31 or not _amd64(getattr(il,'bin',None)):return out
    seq=[i for b in blocks for i in b.insns]
    for k,i in enumerate(seq):
        if (k<8 or k+1==len(seq) or i.mnemonic!=M.TEST or i.op0_register!=i.op1_register or not RX.is_gpr64(i.op0_register) or
                seq[k+1].mnemonic!=M.JE or seq[k-1].mnemonic!=M.MOV or seq[k-2].memory_displacement!=KLASS_STATIC_FIELDS):continue
        w=seq[k-8:k+2];cmp,skip,lea,init,set_,klass,fields,value,test,guard=w
        if (any(x.has_segment_prefix or x.has_lock_prefix or x.memory_index!=R.NONE for x in w) or
                cmp.mnemonic!=M.CMP or cmp.memory_base!=R.RIP or MemorySizeExt.size(cmp.memory_size)!=1 or
                skip.mnemonic!=M.JNE or skip.near_branch_target!=klass.ip or lea.mnemonic!=M.LEA or lea.op0_register!=R.RCX or lea.memory_base!=R.RIP or
                not init.is_call_near or init.near_branch_target!=lift.rt_init_meta or set_.mnemonic!=M.MOV or set_.memory_base!=R.RIP or
                set_.ip_rel_memory_address!=cmp.ip_rel_memory_address or set_.op1_kind!=K.IMMEDIATE8 or set_.immediate8!=1 or
                klass.mnemonic!=M.MOV or klass.memory_base!=R.RIP or klass.ip_rel_memory_address!=lea.ip_rel_memory_address or not RX.is_gpr64(klass.op0_register) or
                fields.mnemonic!=M.MOV or fields.memory_base!=klass.op0_register or not RX.is_gpr64(fields.op0_register) or
                value.op1_kind!=K.MEMORY or value.op0_register!=test.op0_register or value.memory_base!=fields.op0_register or
                any(x.op0_register in (R.RSP,R.RBP) for x in (klass,fields,value))):continue
        candidates.append(w)
    if not candidates:return out
    slots={b.insns[-1].ip:tuple(b.switch_targets) for b in blocks if b.switch_targets}
    graph=_graph(il,seq,allow_tail=True,chained=True,switch_slots=slots)
    if not graph or seq[0].ip!=method.addr:return out
    pred,_=graph;by={i.ip:i for i in seq}
    for w in candidates:
        cmp,skip,lea,init,set_,klass,fields,value,test,guard=w
        if any(a.next_ip!=b.ip or set(pred[b.ip])!=({a.ip,skip.ip} if b is klass else {a.ip}) for a,b in zip(w,w[1:])):continue
        if cmp.op1_kind==K.REGISTER:
            reg=RX.full_register(cmp.op1_register);defs=_definitions(by,pred,method.addr,cmp.ip,reg)
            if not defs or any(by[p].mnemonic!=M.XOR or by[p].op0_register!=by[p].op1_register or
                               RX.size(by[p].op0_register)<4 or RX.full_register(by[p].op0_register)!=r for p,r in defs):continue
        elif cmp.op1_kind!=K.IMMEDIATE8 or cmp.immediate8:continue
        throw=by.get(guard.near_branch_target)
        if not throw or not throw.is_call_near or lift._named_raise_throw(throw.near_branch_target,lift._call_name(throw.near_branch_target))!='System.NullReferenceException':continue
        slot=klass.ip_rel_memory_address;flag=cmp.ip_rel_memory_address;offset=sdisp(value.memory_displacement)
        def private_flag(f):
            sec=_writable(il.bin,f,1)
            return sec and not slot<=f<slot+8 and (f>=sec.addr+sec.rawsize or il.bin.read(f,1)==b'\0')
        data=_writable(il.bin,slot,8)
        if (not private_flag(flag) or not data or slot%8 or slot+8>data.addr+data.rawsize or
                any(x.ip not in (cmp.ip,set_.ip) and x.is_ip_rel_memory_operand and
                    x.ip_rel_memory_address<=flag<x.ip_rel_memory_address+max(1,MemorySizeExt.size(x.memory_size)) for x in seq)):continue
        alias=alias_for_slot(il,slot,lift.rt_init_meta,offset)
        if not alias:continue
        member,ty=alias;td=il.meta.typedefs[ty[0]];name=member.rsplit('.',1)[-1]
        if il._closed_type_key(ty)!=(0x12,td.index,0) or not _direct_use(il,by,pred,guard.next_ip,value.op0_register,td.index):continue
        matches=[md for j in il.meta.type_methods(td) if (md:=il.meta.methods[j]).name=='get_'+name and md.param_count==0]
        if len(matches)!=1:continue
        getter=matches[0];addr=getter.addr
        if (getter.addr==method.addr or method.declaring==td.index or ('method',getter.index) not in il.addr_candidates.get(addr,()) or
                lift._accessor_prop(getter.index)!=('get',name,0)):continue
        # _slot matched the complete registered getter; its CMP starts at
        # +4, with a signed RIP displacement at +6 and trailing imm8.
        raw=il.bin.read(addr+6,4)
        # Independently inlined copies need not share their one-shot byte.
        # Both cold arms initialize only this same, idempotent TypeInfo slot.
        if not raw or not private_flag(addr+11+int.from_bytes(raw,'little',signed=True)):continue
        out[value.ip]=('field_value',('global::'+member,ty),reg_name(value.op0_register),'obj')
    return out
