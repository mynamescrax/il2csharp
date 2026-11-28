"""Pointer identity at a reference CompareExchange retry inside an event accessor.

Delegate == compares invocation lists; CMP RAX,saved compares addresses.
Only change the predicate for the observed return from this particular CAS.
"""
from il2cpp.array_origin import _definitions,_graph
from il2cpp.csharp import FA_INITONLY,FA_STATIC,FA_LITERAL,field_attrs,source_field_name
from il2cpp.equivalent_binary import _amd64
from il2cpp.names import safe_ident
from il2cpp.prelude import HAVE_ICED
from il2cpp.text import reg_name,sdisp
from il2cpp.x64 import KLASS_STATIC_FIELDS

if HAVE_ICED:
    from iced_x86 import Mnemonic as M,OpKind as K,Register as R,MemorySizeExt as MS,RegisterExt as RX
    from il2cpp.array_origin import _SAVED,_INFO,_WRITES


def _event_storage(il,m,td,off):
    meta=il.meta;ps=meta.method_params(m)
    if len(ps)!=1 or not 0<=ps[0].type<len(il.types):return None
    target=il._closed_type_key(il.types[ps[0].type]);rows=[]
    for k in range(td.event_count):
        name,t,add,remove,*_=meta.events[td.event_start+k]
        if (m.index-td.method_start in (add,remove) and 0<=t<len(il.types) and
                il._closed_type_key(il.types[t])==target):rows.append(meta.getstr(name))
    if len(rows)!=1 or not target or target[-1] or target[0] not in (0x12,0x15):return None
    dtype=il.td_of_ty(il.types[ps[0].type])
    if dtype is None or not any(il.typedef_full(t)=='System.MulticastDelegate' for t in il.base_chain_tds(dtype)):return None
    if not 0<=td.index<len(il.field_offsets):return None
    offsets=il.field_offsets[td.index];fields=[]
    if not offsets or len(offsets)!=td.field_count:return None
    for pos,fi in zip(offsets,meta.type_fields(td)):
        f=meta.fields[fi];flags=field_attrs(il,f)
        if not flags&FA_STATIC or flags&FA_LITERAL:continue
        if not 0<=f.type<len(il.types) or pos<0:return None
        ty=il.types[f.type];width=il._sf_field_size(ty,0)
        if not width or width<0:return None
        if pos<off+8 and off<pos+width:
            if pos!=off or width!=8 or f.name!=rows[0] or il._closed_type_key(ty)!=target or flags&FA_INITONLY:return None
            fields.append((safe_ident(source_field_name(il,fi)),ty))
    return fields[0] if len(fields)==1 else None


def _root(il,by,pred,entry,i,reg,td):
    # The blob must come from this exact type's registered TypeInfo cell;
    # a coincidentally identical address offset on another owner is not a field.
    defs=_definitions(by,pred,entry,i.ip,reg)
    if len(defs)!=1:return None
    p,r=defs.pop();blob=by[p]
    if (blob.mnemonic!=M.MOV or blob.op0_register!=r or blob.op1_kind!=K.MEMORY or blob.memory_index!=R.NONE or
            blob.memory_displacement!=KLASS_STATIC_FIELDS or blob.has_segment_prefix):return None
    klass=_definitions(by,pred,entry,p,blob.memory_base);slots=set()
    if not klass:return None
    for ip,r in klass:
        lo=by[ip]
        if lo.mnemonic!=M.MOV or lo.op0_register!=r or lo.memory_base!=R.RIP or lo.has_segment_prefix:return None
        slot=lo.ip_rel_memory_address;u=il.decode_slot(slot) or {}
        if u.get('kind')!=1 or u.get('td')!=td.index or il._closed_type_key(u.get('type'))!=(0x12,td.index,0):return None
        slots.add(slot)
    return next(iter(slots)) if len(slots)==1 else None


def retry_sites(lift,m,td,blocks,pads):
    out={};il=lift.il
    if (not HAVE_ICED or pads or not m.is_static or m.param_count!=1 or not td.event_count or td.generic_container!=-1 or m.generic_container!=-1 or
            not _amd64(getattr(il,'bin',None)) or il.meta.version!=31 or not 0<=m.return_type<len(il.types) or il._closed_type_key(il.types[m.return_type])!=(1,0)):return out
    wins=[b.insns[-8:] for b in blocks if len(b.insns)>=8 and b.insns[-1].mnemonic==M.JNE and b.insns[-4].is_call_near and b.insns[-4].near_branch_target in lift.rt_interlocked]
    if not wins:return out
    seq=[i for b in blocks for i in b.insns];by={i.ip:i for i in seq};g=_graph(il,seq,chained=True,nested_chains=True)
    if not g:return out
    pred,succ=g
    for w in wins:
        blob,comp,addr,replace,cas,obs,cmp,again=w;entry=again.near_branch_target
        if (entry>=blob.ip or entry not in by or any(a.next_ip!=z.ip or pred[z.ip]!=[a.ip] for a,z in zip(w,w[1:])) or
                any(i.has_lock_prefix or i.has_segment_prefix or i.memory_index!=R.NONE for i in w) or
                blob.mnemonic!=M.MOV or blob.op0_register!=R.RCX or blob.memory_base!=R.RCX or blob.memory_displacement!=KLASS_STATIC_FIELDS or
                comp.mnemonic!=M.MOV or comp.op0_register!=R.R8 or comp.op1_register not in _SAVED or
                addr.mnemonic!=M.ADD or addr.op0_register!=R.RCX or addr.op1_kind not in (K.IMMEDIATE8TO64,K.IMMEDIATE32TO64) or
                replace.mnemonic!=M.MOV or replace.op0_register!=R.RDX or replace.op1_register not in _SAVED or
                obs.mnemonic!=M.MOV or obs.op1_register!=R.RAX or obs.op0_register!=comp.op1_register or
                cmp.mnemonic!=M.CMP or cmp.op0_register!=R.RAX or cmp.op1_register not in _SAVED or cmp.op1_register==obs.op0_register):continue
        off=addr.immediate(1);field=_event_storage(il,m,td,off)
        if not field or not _root(il,by,pred,m.addr,addr,R.RCX,td):continue
        # Require the word in the helper to be an actual known write barrier.
        va=cas.near_branch_target;raw=il.bin.read(va+22,4)
        if not lift._is_interlocked_helper(va) or not raw or len(raw)!=4:continue
        barrier=va+26+int.from_bytes(raw,'little',signed=True)
        from il2cpp.gc_mark import mark_only
        if not mark_only(il,barrier):continue
        definitions=_definitions(by,pred,m.addr,cas.ip,R.R8)
        if definitions!=_definitions(by,pred,m.addr,cmp.ip,cmp.op1_register) or (cas.ip,R.RAX) not in definitions or len(definitions)!=2:continue
        initial,=definitions-{(cas.ip,R.RAX)};first=by[initial[0]]
        if (first.mnemonic!=M.MOV or first.op0_register!=obs.op0_register or not MS.size(first.memory_size)==8 or
                first.op1_kind!=K.MEMORY or first.memory_index!=R.NONE or first.has_segment_prefix or first.memory_displacement!=off or
                _root(il,by,pred,m.addr,first,first.memory_base,td)!=_root(il,by,pred,m.addr,addr,R.RCX,td)):continue
        # Every path from this iteration's header must save the current
        # value before CAS. Matching reaching origins alone allows an old
        # iteration's expected register to survive a conditional skip.
        ip=entry;save=None
        for _ in range(8):
            i=by[ip]
            if i.mnemonic==M.MOV and i.op0_register==cmp.op1_register and i.op1_register==obs.op0_register:save=i;break
            if i.mnemonic not in (M.XOR,M.MOV) or i.op0_register in (cmp.op1_register,obs.op0_register) or succ[ip]!=(i.next_ip,) or pred[i.next_ip]!=[ip]:break
            ip=i.next_ip
        if not save:continue
        todo=[cas.ip];seen=set();good=True
        while todo:
            ip=todo.pop()
            if ip==save.ip or ip in seen:continue
            if ip==entry or ip==m.addr or len(seen)>256:good=False;break
            if any(u.access in _WRITES and RX.full_register(u.register) in (cmp.op1_register,obs.op0_register) for u in _INFO.info(by[ip]).used_registers()):good=False;break
            seen.add(ip);todo.extend(pred[ip])
        if good:out[cas.ip]=(again.ip,cmp.ip,field[0],field[1],td.index,reg_name(cmp.op1_register))
    return out
