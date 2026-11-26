"""Snapshot a nullary instance M on C<T> returning the class's T.

The MethodRef is the second ABI argument. The canonical registration here
is C<object>.M, *not* C.M<object>. A preceding count test is independent:
expose the private dword only for a public getter returning those bytes.
"""
from il2cpp.awaiter import _spec_entry
from il2cpp.captured_home import _normal_predecessors
from il2cpp.csharp import FA_LITERAL, FA_STATIC, field_attrs
from il2cpp.equivalent_binary import _amd64
from il2cpp.names import safe_ident
from il2cpp.prelude import HAVE_ICED
from il2cpp.sret_copy import _own_field
from il2cpp.text import sdisp

if HAVE_ICED:
    from il2cpp.closed_lookup import _INFO, _WRITES, _SAVED
    from iced_x86 import FlowControl as F, MemorySizeExt, Mnemonic as M, OpKind as K, Register as R, RegisterExt


def _class_entry(il,si):
    mi,ci,gi=il.method_specs[si]
    if ci<0 or gi!=-1:return None
    va=_spec_entry(il,si,mi);indices=il._awaiter_spec_indices[mi]
    if si not in indices:
        canonical=[s for s in indices if il.method_specs[s][2]==-1 and il.method_specs[s][1]>=0 and
                   tuple(il._closed_type_key(a) for a in (il._method_spec_type_args(il.method_specs[s][1]) or ()))==((0x1c,0),)]
        if len(canonical)!=1:return None
        va=_spec_entry(il,canonical[0],mi)
    return va if va and il.bin.is_exec_va(va) else None


def _count_property(lift,td,ci,offset):
    il=lift.il;key=il._closed_type_key
    if not 0<offset<128 or td.index>=len(il.field_offsets) or td.flags&0x18==0x10:return None
    # Restrict this class-level check to direct children of Object, so no
    # inherited storage can overlap the candidate field.
    if not 0<=td.parent<len(il.types) or il.type_name(il.types[td.parent]) not in ('object','System.Object'):return None
    raw=il.field_offsets[td.index]
    if not raw or len(raw)!=td.field_count:return None
    layout=il._class_level_offsets(td.index,raw)
    if not layout:return None
    hits=0
    for fi,pos in zip(il.meta.type_fields(td),layout):
        f=il.meta.fields[fi]
        if not 0<=f.type<len(il.types) or not il.types[f.type]:return None
        if field_attrs(il,f)&(FA_STATIC|FA_LITERAL):continue
        ty=il.types[f.type];size=il._class_field_size_align(ty)
        if not size or pos<16:return None
        if pos<offset+4 and pos+size[0]>offset:
            if pos!=offset or size[0]!=4 or key(ty)!=(8,0):return None
            hits+=1
    if hits!=1:return None
    choices=[]
    for j in il.meta.type_methods(td):
        m=il.meta.methods[j]
        if (m.is_static or m.param_count or m.generic_container!=-1 or m.flags&7!=6 or m.flags&0x40 and not m.flags&0x20 or
                not 0<=m.return_type<len(il.types) or key(il.types[m.return_type])!=(8,0)):continue
        p=lift._accessor_prop(j)
        if not p or p[0]!='get' or p[2]:continue
        cache=il.__dict__.setdefault('_closed_class_spec_rows',{})
        if j not in cache:
            specs={}
            for i,(member,c,g) in enumerate(il.method_specs):
                if member==j and c>=0 and g==-1:specs.setdefault(c,[]).append(i)
            cache[j]=specs
        rows=cache[j].get(ci,())
        if len(rows)!=1:continue
        va=_class_entry(il,rows[0])
        if va and il.bin.read(va,4)==bytes((0x8b,0x41,offset,0xc3)):choices.append(safe_ident(p[1]))
    return choices[0] if len(choices)==1 else None


def _saved_self(method,seq,pred,byip,ip,r):
    """The field base survives ordinary Win64 calls. Prove its unique
    entry copy on *all* raw predecessors, including trimmed null branches."""
    if r not in _SAVED:return False
    source=None
    for i in seq[:24]:
        if i.mnemonic==M.MOV and i.op0_register==r and i.op1_register==R.RCX:
            source=i.ip;break
        if i.flow_control!=F.NEXT or any(u.access in _WRITES and RegisterExt.full_register(u.register)==R.RCX for u in _INFO.info(i).used_registers()):return False
    if not source:return False
    work=[ip];seen=set();reached=False
    while work:
        k=work.pop()
        if k in seen:continue
        if len(seen)>4096 or not pred[k]:return False
        seen.add(k)
        for p in pred[k]:
            if p==source:reached=True;continue
            if any(u.access in _WRITES and RegisterExt.full_register(u.register)==r for u in _INFO.info(byip[p]).used_registers()):return False
            work.append(p)
    # No branch can enter between entry and the initial copy with a stale RCX.
    pro=[i for i in seq if i.ip<=source]
    return reached and not pred[method.addr] and all(pred[b.ip]=={a.ip} and a.next_ip==b.ip for a,b in zip(pro,pro[1:]))


def closed_class_reads(lift,method,blocks,pads):
    il=lift.il;actions={}
    if (not HAVE_ICED or not _amd64(getattr(il,'bin',None)) or il.meta.version!=31 or pads or method.is_static or
            il.meta.typedefs[method.declaring].is_valuetype or not 0<=method.return_type<len(il.types) or il.returns_sret(il.types[method.return_type])):return actions
    key=il._closed_type_key
    seq=[i for b in blocks for i in b.insns];pred=None
    for j,i in enumerate(seq):
        if j<7 or i.mnemonic!=M.CALL or i.op0_kind!=K.NEAR_BRANCH64:continue
        load,test,null,cmp,jcc,slot,recv=seq[j-7:j];r=load.op0_register
        if (slot.mnemonic!=M.MOV or slot.op0_register!=R.RDX or slot.memory_base!=R.RIP or recv.mnemonic!=M.MOV or recv.op0_register!=R.RCX or
                recv.op1_register!=r or load.mnemonic!=M.MOV or load.op1_kind!=K.MEMORY or not RegisterExt.is_gpr64(r) or r==R.RDX or
                test.mnemonic!=M.TEST or test.op0_register!=r or test.op1_register!=r or null.mnemonic!=M.JE or
                cmp.mnemonic!=M.CMP or cmp.memory_base!=r or cmp.op0_kind!=K.MEMORY or MemorySizeExt.size(cmp.memory_size)!=4 or cmp.op1_kind!=K.IMMEDIATE8TO32 or
                jcc.flow_control!=F.CONDITIONAL_BRANCH or jcc.op0_kind!=K.NEAR_BRANCH64 or any(x.has_segment_prefix or x.memory_index!=R.NONE or x.has_lock_prefix for x in seq[j-7:j+1])):continue
        usage=il.decode_slot(slot.ip_rel_memory_address) or {};si=usage.get('idx',-1)
        if usage.get('kind')!=6 or not 0<=si<len(il.method_specs):continue
        mi,ci,gi=il.method_specs[si];args=il._method_spec_type_args(ci) if ci>=0 else None
        if gi!=-1 or not args or len(args)!=1 or not 0<=mi<len(il.meta.methods):continue
        m=il.meta.methods[mi];arg=args[0]
        if (not arg or key(arg)!=(0x12,arg[0],0) or not 0<=arg[0]<len(il.meta.typedefs) or il.meta.typedefs[arg[0]].generic_container!=-1 or
                m.is_static or m.flags&7!=6 or m.flags&(0x40|0x800) or m.generic_container!=-1 or m.param_count or safe_ident(m.name)!=m.name or
                not 0<=m.return_type<len(il.types) or not 0<=m.declaring<len(il.meta.typedefs)):continue
        td=il.meta.typedefs[m.declaring];rt=il.types[m.return_type]
        if (td.is_valuetype or td.flags&0x20 or not 0<=td.generic_container<len(il.meta.generic_containers) or not rt or il._type_enum(rt)!=0x13 or rt[1]&(1<<29) or
                il.meta.generic_containers[td.generic_container]!=(td.index,1,0,rt[0]) or key(il.candidate_return_type(('generic',si)))!=key(arg) or
                _class_entry(il,si)!=i.near_branch_target):continue
        f=_own_field(il,il.meta.typedefs[method.declaring],sdisp(load.memory_displacement),8)
        if not f or key(f[1])!=(0x15,(0x12,td.index,0),(key(arg),),0):continue
        if pred is None:
            if not seq or seq[0].ip!=method.addr or any(a.next_ip!=b.ip for a,b in zip(seq,seq[1:])):return actions
            pred=_normal_predecessors(seq);byip={x.ip:x for x in seq}
            if pred is None:return actions
        if any(pred[b.ip]!={a.ip} for a,b in zip(seq[j-7:j],seq[j-6:j+1])) or not _saved_self(method,seq,pred,byip,load.ip,load.memory_base):continue
        from il2cpp.text import reg_name
        actions[load.ip]=('field_value',f,reg_name(r),'obj')
        actions[i.ip]=('class_result',load.ip,si,m.name,arg)
        prop=_count_property(lift,td,ci,sdisp(cmp.memory_displacement))
        if prop:actions[cmp.ip]=('count_cmp',load.ip,prop,cmp.immediate8to32)
    return actions
