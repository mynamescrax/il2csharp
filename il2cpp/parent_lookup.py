"""Prove closed reference-type component lookups immediately after a folded call."""
import re

from il2cpp.awaiter import _spec_entry
from il2cpp.binary import PE
from il2cpp.expr import acc_get
from il2cpp.generic_array import object_shared_entry
from il2cpp.prelude import HAVE_ICED
from il2cpp.sret_copy import _own_field
from il2cpp.static_getter import alias_for_slot

if HAVE_ICED:
    from iced_x86 import Decoder, FlowControl as F, InstructionInfoFactory, Mnemonic as M, OpAccess, OpKind as K, Register as R, RegisterExt


def _integer_lookup_body(il,target):
    """Cross-check the registered instance ABI against the shared code. No
    SIMD operands; on every path any RAX read (including RET) must follow
    a full definition. Credit an implicit definition only for a registered
    reference-returning call; an arbitrary runtime helper might preserve RAX.
    """
    lo,hi=il.function_extent(target)
    if lo!=target or not 0<hi-lo<=256 or not il.bin.is_exec_va(target): return False
    raw=il.bin.read(lo,hi-lo)
    if not raw or len(raw)!=hi-lo: return False
    seq={i.ip:i for i in Decoder(64,raw,ip=lo)}; info=InstructionInfoFactory()
    seen=set();work=[(lo,False)];returned=False; typed_lookup=False
    while work:
        ip,defined=work.pop()
        if (ip,defined) in seen: continue
        seen.add((ip,defined));i=seq.get(ip)
        if i is None or i.is_invalid or i.has_segment_prefix: return False
        for u in info.info(i).used_registers():
            r=u.register
            if RegisterExt.is_vector_register(r): return False
            if RegisterExt.full_register(r)==R.RAX:
                if u.access!=OpAccess.WRITE and not defined: return False
                if u.access==OpAccess.WRITE and RegisterExt.size(r)>=4: defined=True
        if i.mnemonic==M.RET:
            if not defined or i.op_count: return False
            returned=True; continue
        if i.mnemonic==M.INT3: continue
        if i.flow_control==F.CALL and i.op0_kind==K.NEAR_BRANCH64:
            dest=i.near_branch_target
            if not il.bin.is_exec_va(dest) or lo<=dest<hi: return False
            ids=il.addr_candidates.get(dest,())
            if len(ids)==1 and ids[0][0]=='method' and 0<=ids[0][1]<len(il.meta.methods):
                m=il.meta.methods[ids[0][1]]
                rt=il.types[m.return_type] if 0<=m.return_type<len(il.types) else None
                if m.addr==dest and rt and il._closed_type_key(rt)==(0x12,rt[0],0):
                    defined=True
                    if (not m.is_static and m.name=='GetComponentInParent' and m.declaring==rt[0] and
                            il.typedef_full(m.declaring)=='UnityEngine.Component' and m.param_count==2 and m.generic_container==-1):
                        ps=il.meta.method_params(m)
                        if len(ps)==2 and all(0<=p.type<len(il.types) for p in ps) and [il.type_name(il.types[p.type]) for p in ps]==['System.Type','bool']:
                            typed_lookup=True
        elif i.flow_control in (F.CONDITIONAL_BRANCH,F.UNCONDITIONAL_BRANCH) and i.op0_kind==K.NEAR_BRANCH64:
            work.append((i.near_branch_target,defined))
            if i.flow_control==F.UNCONDITIONAL_BRANCH: continue
        elif i.flow_control!=F.NEXT: return False
        work.append((i.next_ip,defined))
    return returned and typed_lookup


def parent_lookup_sites(il,blocks,pads):
    """The MethodRef in RDX closes the operation; the reference-sharing
    entry for M<object> supplies its code when M<T> has no distinct row.
    Return both the render bindings and the exact return-liveness windows.
    """
    bindings={}; windows={}
    if (not HAVE_ICED or pads or not isinstance(getattr(il,'bin',None),PE) or not il.bin.is64 or
            getattr(il.meta,'version',None)!=31): return bindings,windows
    for b in blocks:
        for j,i in enumerate(b.insns):
            if j<3 or i.mnemonic!=M.CALL or i.op0_kind!=K.NEAR_BRANCH64: continue
            base,slot,recv=b.insns[j-3:j]
            if (base.mnemonic!=M.CALL or base.op0_kind!=K.NEAR_BRANCH64 or len(il.addr_candidates.get(base.near_branch_target,()))<2 or
                    slot.mnemonic!=M.MOV or slot.op0_register!=R.RDX or slot.memory_base!=R.RIP or slot.has_segment_prefix or
                    recv.mnemonic!=M.MOV or recv.op0_register!=R.RCX or recv.op1_register not in (R.RBX,R.RSI,R.RDI,R.RBP,R.R12,R.R13,R.R14,R.R15) or
                    base.next_ip!=slot.ip or slot.next_ip!=recv.ip or recv.next_ip!=i.ip): continue
            usage=il.decode_slot(slot.ip_rel_memory_address) or {}; si=usage.get('idx',-1)
            if usage.get('kind')!=6 or not 0<=si<len(il.method_specs): continue
            mi,ci,gi=il.method_specs[si]
            if not 0<=mi<len(il.meta.methods) or ci!=-1 or gi<0: continue
            m=il.meta.methods[mi]; actual=il._method_spec_type_args(gi)
            if (m.name!='GetComponentInParent' or il.typedef_full(m.declaring)!='UnityEngine.Component' or
                    m.is_static or m.param_count or m.flags&7!=6 or m.flags&0x40 or not 0<=m.generic_container<len(il.meta.generic_containers) or
                    not actual or len(actual)!=1 or not actual[0] or il._closed_type_key(actual[0])!=(0x12,actual[0][0],0) or
                    m.declaring not in il.base_chain_tds(actual[0][0]) or not 0<=m.return_type<len(il.types)): continue
            own,n,ismethod,param=il.meta.generic_containers[m.generic_container]; rt=il.types[m.return_type]
            if ((own,n,ismethod)!=(mi,1,1) or not rt or il._type_enum(rt)!=0x1e or rt[0]!=param or rt[1]&(1<<29) or
                    il._closed_type_key(il.candidate_return_type(('generic',si)))!=il._closed_type_key(actual[0])): continue
            target=i.near_branch_target
            if (object_shared_entry(il,mi)!=target or _spec_entry(il,si,mi) not in (None,0,target) or
                    not _integer_lookup_body(il,target)): continue
            bindings[i.ip]=(si,m.declaring,actual[0],m.name,False); windows[slot.ip]=i.next_ip
    return bindings,windows


def _same_entry(il,canonical,target):
    """Reference sharing may use a local copy of a registered function.
    Compare every instruction byte including addressing modes. Only direct
    rel32/rel8 transfers may relocate, to the same internal offset or the
    exact same external helper (including resize and write barrier)."""
    if not canonical or not il.bin.is_exec_va(canonical) or not il.bin.is_exec_va(target): return False
    if canonical==target: return True
    def normalized(addr):
        lo,hi=il.function_extent(addr)
        if lo!=addr or not 0<hi-lo<=128: return None
        raw=il.bin.read(lo,hi-lo)
        if not raw or len(raw)!=hi-lo: return None
        d=Decoder(64,raw,ip=lo); result=[]; local=set(); starts=set()
        for i in d:
            if i.is_invalid or i.is_ip_rel_memory_operand: return None
            starts.add(i.ip-lo); op=raw[i.ip-lo:i.next_ip-lo]; dest=None
            if i.op0_kind==K.NEAR_BRANCH64:
                off=d.get_constant_offsets(i)
                if off.immediate_size not in (1,4) or off.immediate_offset+off.immediate_size!=len(op): return None
                op=op[:off.immediate_offset]; t=i.near_branch_target
                if lo<=t<hi: dest=('in',t-lo);local.add(t-lo)
                else: dest=('out',t)
            elif i.flow_control not in (F.NEXT,F.RETURN,F.INTERRUPT): return None
            result.append((op,dest,i.len))
        return result if local<=starts else None
    original=normalized(canonical)
    return original is not None and original==normalized(target)


def _list_member(il,slot,target,name,elem):
    u=il.decode_slot(slot) or {}; si=u.get('idx',-1)
    if u.get('kind')!=6 or not 0<=si<len(il.method_specs): return None
    mi,ci,gi=il.method_specs[si]; ts=il._method_spec_type_args(ci)
    if not 0<=mi<len(il.meta.methods) or gi!=-1 or not ts or len(ts)!=1 or il._closed_type_key(ts[0])!=elem: return None
    m=il.meta.methods[mi];td=il.meta.typedefs[m.declaring];ps=il.meta.method_params(m)
    if (il.typedef_full(td.index)!='System.Collections.Generic.List`1' or not 0<=td.generic_container<len(il.meta.generic_containers) or
            m.name!=name or m.is_static or m.flags&7!=6 or (m.flags&0x40 and not m.flags&0x20) or m.generic_container!=-1 or
            len(ps)!=m.param_count or len(ps)!=1 or not 0<=ps[0].type<len(il.types) or not 0<=m.return_type<len(il.types) or
            il._closed_type_key(il.types[m.return_type])!=((1 if name=='Add' else 2),0)): return None
    own,n,ismethod,param=il.meta.generic_containers[td.generic_container]; pt=il.types[ps[0].type]
    if (own,n,ismethod)!=(td.index,1,0) or not pt or pt[0]!=param or il._type_enum(pt)!=0x13 or pt[1]&(1<<29): return None
    entry=_spec_entry(il,si,mi)
    if not entry:
        cache=il.__dict__.setdefault('_reference_list_entries',{})
        if mi not in cache:
            ptrs={_spec_entry(il,k,mi) for k,(j,c,g) in enumerate(il.method_specs) if j==mi and g==-1
                  and (args:=il._method_spec_type_args(c)) and len(args)==1 and il._closed_type_key(args[0])==(0x1c,0)}
            cache[mi]=ptrs.pop() if len(ptrs)==1 else None
        entry=cache[mi]
    if _same_entry(il,entry,target): return (0x15,(0x12,td.index,0),(elem,),0)


def _manager_field(lift,blocks,use,key):
    """Fresh checked singleton + list field, with no operation in between."""
    if len(use.preds)!=1: return None
    field=blocks[use.preds[0]]
    if len(field.insns)!=3 or len(field.preds)!=1 or field.succs!=[use.bid]: return None
    owner=blocks[field.preds[0]]
    if len(owner.insns)!=5 or owner.succs!=[field.bid] or len(owner.stmts)!=1: return None
    k,blob,ref,test,null=owner.insns;load,check,fail=field.insns
    seq=owner.insns+field.insns+[use.insns[0]]
    if (any(a.next_ip!=b.ip for a,b in zip(seq,seq[1:])) or any(i.has_segment_prefix or i.memory_index!=R.NONE for i in seq) or
            k.mnemonic!=M.MOV or k.op0_register!=R.RAX or k.memory_base!=R.RIP or
            blob.mnemonic!=M.MOV or blob.op0_register!=R.RCX or blob.memory_base!=R.RAX or blob.memory_displacement!=0xb8 or
            ref.mnemonic!=M.MOV or ref.op0_register!=R.RAX or ref.memory_base!=R.RCX or ref.memory_displacement or
            test.mnemonic!=M.TEST or test.op0_register!=test.op1_register or test.op0_register!=R.RAX or
            load.mnemonic!=M.MOV or load.op0_register!=R.RCX or load.memory_base!=R.RAX or
            check.mnemonic!=M.TEST or check.op0_register!=check.op1_register or check.op0_register!=R.RCX or
            null.mnemonic!=M.JE or fail.mnemonic!=M.JE or fail.near_branch_target!=null.near_branch_target): return None
    il=lift.il;dest=next((b for b in blocks if b.insns and b.insns[0].ip==fail.near_branch_target),None)
    if not dest or dest.insns[0].mnemonic!=M.CALL or dest.insns[0].op0_kind!=K.NEAR_BRANCH64: return None
    throw=dest.insns[0].near_branch_target
    if lift._named_raise_throw(throw,lift._call_name(throw))!='System.NullReferenceException': return None
    prop=alias_for_slot(il,k.ip_rel_memory_address,lift.rt_init_meta); obj=(owner.end_state or {}).get('RAX')
    if (not prop or not obj or obj._unk or il._closed_type_key(obj.ty)!=il._closed_type_key(prop[1]) or not re.fullmatch(r't\d+',obj.text) or
            not re.fullmatch('var '+obj.text+r' = [\w.<>]+;',owner.stmts[0])): return None
    row=_own_field(il,il.meta.typedefs[prop[1][0]],load.memory_displacement,8)
    if not row or row[1][1]&7!=6 or il._closed_type_key(row[1])!=key: return None
    return owner,'var %s = %s;'%(obj.text,acc_get(prop[0])),obj.text+row[0][4:]


def fold_lookup_list_tail(lift,blocks):
    if not getattr(lift,'_parent_lookup_windows',None): return
    il=lift.il
    for b in blocks:
        # Remove returns a bool, and unlike the unregistered Add tail this
        # call already lifts. Recover just the public owner getter once the
        # captured item, list type and closed Remove binding also agree.
        if len(b.insns)==3 and len(b.preds)==1:
            slot,src,call=b.insns
            if (slot.mnemonic==M.MOV and slot.op0_register==R.R8 and slot.memory_base==R.RIP and not slot.has_segment_prefix and
                    slot.next_ip==src.ip and src.next_ip==call.ip and src.mnemonic==M.MOV and src.op0_register==R.RDX and
                    src.op1_register==R.RBX and call.mnemonic==M.CALL and call.op0_kind==K.NEAR_BRANCH64):
                incoming=blocks[b.preds[0]].end_state or {}; arg=incoming.get('RBX'); rcx=incoming.get('RCX'); result=(b.end_state or {}).get('RAX')
                if (arg and rcx and result and any(lift._material_values.get(ip) is arg for ip in lift._parent_lookup_sites) and
                        result.text=='%s.Remove(%s)'%(rcx.text,arg.text)):
                    key=_list_member(il,slot.ip_rel_memory_address,call.near_branch_target,'Remove',il._closed_type_key(arg.ty))
                    owner=_manager_field(lift,blocks,b,key) if key and il._closed_type_key(rcx.ty)==key else None
                    if owner and owner[2]==rcx.text: owner[0].stmts[0]=owner[1]
        if len(b.insns)!=5 or b.succs or len(b.stmts)!=1: continue
        add,item,sp,pop,tail=b.insns
        if (add.mnemonic!=M.MOV or add.op0_register!=R.R8 or add.memory_base!=R.RIP or add.has_segment_prefix or
                item.mnemonic!=M.MOV or item.op0_register!=R.RDX or item.op1_register!=R.RBX or
                sp.mnemonic!=M.ADD or sp.op0_register!=R.RSP or sp.op1_kind!=K.IMMEDIATE8TO64 or sp.immediate8to64!=32 or
                pop.mnemonic!=M.POP or pop.op0_register!=R.RBX or tail.mnemonic!=M.JMP or tail.op0_kind!=K.NEAR_BRANCH64): continue
        arg=(b.end_state or {}).get('RDX');rcx=(b.end_state or {}).get('RCX')
        if (not arg or not re.fullmatch(r't\d+',arg.text) or not rcx or not any(
                lift._material_values.get(ip) is arg for ip in lift._parent_lookup_sites)): continue
        elem=il._closed_type_key(arg.ty);key=_list_member(il,add.ip_rel_memory_address,tail.near_branch_target,'Add',elem)
        if not key or il._closed_type_key(rcx.ty)!=key: continue
        last=_manager_field(lift,blocks,b,key)
        if not last or last[2]!=rcx.text or not b.stmts[0].startswith('sub_%x(%s, %s, '%(tail.near_branch_target,rcx.text,arg.text)): continue
        for q in blocks[:last[0].bid]:
            if len(q.insns)!=5: continue
            slot,src,call,test,skip=q.insns
            if (slot.mnemonic!=M.MOV or slot.op0_register!=R.R8 or slot.memory_base!=R.RIP or slot.has_segment_prefix or
                    src.mnemonic!=M.MOV or src.op0_register!=R.RDX or src.op1_register!=R.RBX or call.mnemonic!=M.CALL or call.op0_kind!=K.NEAR_BRANCH64 or
                    test.mnemonic!=M.TEST or test.op0_register!=test.op1_register or test.op0_register!=R.AL or skip.mnemonic!=M.JNE or
                    _list_member(il,slot.ip_rel_memory_address,call.near_branch_target,'Contains',elem)!=key): continue
            first=_manager_field(lift,blocks,q,key)
            if not first or not any(first[2]+'.Contains('+arg.text+');' in st for st in q.stmts): continue
            first[0].stmts[0]=first[1]; last[0].stmts[0]=last[1]
            b.stmts[0]='%s.Add(%s); return;'%(rcx.text,arg.text)
            break
