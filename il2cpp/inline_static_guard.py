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


def _guarded_receiver_use(il,by,pred,start,reg,owner,throw,seq,blocks):
    """Read two public reference fields from the checked object before a
    boolean instance action. Each acquisition belongs to this guard only."""
    from il2cpp.csharp import declares_member_name,field_attrs,source_field_name
    from il2cpp.names import safe_ident
    from il2cpp.shared_field import reference_field_at
    ip=start
    for _ in range(2):
        i=by.get(ip);t=by.get(i.next_ip) if i else None;j=by.get(t.next_ip) if t else None
        if (not j or pred[t.ip]!=[i.ip] or pred[j.ip]!=[t.ip] or i.mnemonic!=M.MOV or i.op1_kind!=K.MEMORY or
                i.memory_base!=reg or not RX.is_gpr64(i.op0_register) or i.op0_register in (R.RSP,R.RBP) or
                i.has_segment_prefix or i.has_lock_prefix or i.memory_index!=R.NONE or MemorySizeExt.size(i.memory_size)!=8 or
                t.mnemonic!=M.TEST or t.op0_register!=t.op1_register or t.op0_register!=i.op0_register or
                j.mnemonic!=M.JE or j.near_branch_target!=throw.ip or pred.get(j.next_ip)!=[j.ip]):return False
        row=reference_field_at(il,owner,sdisp(i.memory_displacement))
        if not row or field_attrs(il,il.meta.fields[row[1]])&7!=6:return False
        member=source_field_name(il,row[1]);chain=il.base_chain_tds(owner)
        if (not member.isidentifier() or safe_ident(member)!=member or row[0] not in chain or
                any(declares_member_name(il,il.meta.typedefs[x],member) for x in chain[:chain.index(row[0])])):return False
        reg=i.op0_register;owner=row[2][0];ip=j.next_ip
    h=by.get(ip);v=by.get(h.next_ip) if h else None
    if (reg!=R.RCX or not v or h.mnemonic!=M.XOR or h.op0_register!=h.op1_register or h.op0_register!=R.R8D or
            pred[v.ip]!=[h.ip] or not (v.mnemonic==M.XOR and v.op0_register==v.op1_register==R.EDX or
                v.mnemonic==M.MOV and v.op0_register==R.DL and v.op1_kind==K.IMMEDIATE8 and v.immediate8 in (0,1))):return False
    use=by.get(v.next_ip)
    if not use or pred[use.ip]!=[v.ip]:return False
    if use.mnemonic==M.ADD and use.op0_register==R.RSP and use.op1_kind in (K.IMMEDIATE8TO64,K.IMMEDIATE32TO64):
        prev=use;use=by.get(prev.next_ip)
        if not use or pred[use.ip]!=[prev.ip] or not use.is_jmp_short_or_near:return False
        from il2cpp.terminal_effect import _terminal_frame
        block=next((b for b in blocks if b.insns and b.insns[-1].ip==use.ip),None)
        if not block or len(block.insns)<3 or block.insns[-3].ip!=v.ip or not _terminal_frame(il,seq,by,pred,h.ip,block,len(block.insns)-3):return False
    elif not use.is_call_near:return False
    ids=il.addr_candidates.get(use.near_branch_target,())
    if len(ids)!=1 or ids[0][0]!='method' or not 0<=ids[0][1]<len(il.meta.methods):return False
    m=il.meta.methods[ids[0][1]];ps=il.meta.method_params(m)
    return (m.addr==use.near_branch_target and m.declaring==owner and m.generic_container==-1 and not m.is_static and
            m.flags&7==6 and not m.flags&(0x40|0x800) and 0<=m.return_type<len(il.types) and il._closed_type_key(il.types[m.return_type])==(1,0) and
            m.param_count==len(ps)==1 and 0<=ps[0].type<len(il.types) and il._closed_type_key(il.types[ps[0].type])==(2,0))


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
    certified = {}
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
        if not private_flag(flag) or not data or slot%8 or slot+8>data.addr+data.rawsize:continue
        alias=alias_for_slot(il,slot,lift.rt_init_meta,offset)
        if not alias:continue
        member,ty=alias;td=il.meta.typedefs[ty[0]];name=member.rsplit('.',1)[-1]
        if pred.get(guard.next_ip)!=[guard.ip]:continue
        if il._closed_type_key(ty)!=(0x12,td.index,0):continue
        if not (_direct_use(il,by,pred,guard.next_ip,value.op0_register,td.index) or
                _guarded_receiver_use(il,by,pred,guard.next_ip,value.op0_register,td.index,throw,seq,blocks)):continue
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
        if not raw:continue
        getter_flag=addr+11+int.from_bytes(raw,'little',signed=True)
        if not private_flag(getter_flag):continue
        if getter_flag!=flag and any(x.is_ip_rel_memory_operand and
                x.ip_rel_memory_address<=getter_flag<x.ip_rel_memory_address+max(1,MemorySizeExt.size(x.memory_size)) for x in seq):continue
        plan=('field_value',('global::'+member,ty),reg_name(value.op0_register),'obj')
        certified.setdefault(flag,[]).append((slot,offset,cmp.ip,set_.ip,value.ip,plan))
    for flag,group in certified.items():
        # All accesses to the byte must belong to complete guarded reads of
        # the same slot. One mismatched/partial cold arm vetoes the group.
        if len({(slot,off) for slot,off,*_ in group}) != 1:continue
        allowed={ip for _,_,c,s,_,_ in group for ip in (c,s)}
        if any(i.is_ip_rel_memory_operand and i.ip not in allowed and
               i.ip_rel_memory_address <= flag < i.ip_rel_memory_address + max(1,MemorySizeExt.size(i.memory_size)) for i in seq):continue
        for _,_,_,_,ip,plan in group:out[ip]=plan
    return out
