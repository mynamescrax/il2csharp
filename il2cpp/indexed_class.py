"""Direct calls to an indexer on the closed generic class stored in this.
Bind each returned reference independently, including a second indexer at
the same index after a callback. Count is a separate registered load leaf.
"""
from il2cpp.array_origin import _graph
from il2cpp.closed_class_read import _class_entry,_count_property
from il2cpp.closed_lookup import _receiver
from il2cpp.csharp import source_field_name
from il2cpp.equivalent_binary import _amd64
from il2cpp.names import safe_ident
from il2cpp.prelude import HAVE_ICED
from il2cpp.shared_field import reference_field_at
from il2cpp.text import reg_name,sdisp

if HAVE_ICED:
    from iced_x86 import Mnemonic as M, Register as R,RegisterExt,OpKind as K


def _member(lift,si,call):
    il=lift.il;key=il._closed_type_key
    if not 0<=si<len(il.method_specs):return None
    mi,ci,gi=il.method_specs[si]
    if not 0<=mi<len(il.meta.methods) or gi!=-1 or ci<0:return None
    m=il.meta.methods[mi];args=il._method_spec_type_args(ci)
    if not args or len(args)!=1 or not args[0] or key(args[0])!=(0x12,args[0][0],0) or not 0<=args[0][0]<len(il.meta.typedefs):return None
    arg=args[0];et=il.meta.typedefs[arg[0]]
    if (et.is_valuetype or et.generic_container!=-1 or m.is_static or m.param_count!=1 or m.generic_container!=-1 or m.flags&7!=6 or
            m.flags&0x400 or m.flags&0x40 and not m.flags&0x20 or not 0<=m.declaring<len(il.meta.typedefs) or not 0<=m.return_type<len(il.types)):return None
    ps=il.meta.method_params(m);prop=lift._accessor_prop(mi);td=il.meta.typedefs[m.declaring];rt=il.types[m.return_type]
    if (not prop or prop[0]!='get' or prop[2]!=1 or len(ps)!=1 or not 0<=ps[0].type<len(il.types) or key(il.types[ps[0].type])!=(8,0) or
            not rt or il._type_enum(rt)!=0x13 or rt[1]&(1<<29) or td.is_valuetype or td.flags&0x20 or not 0<=td.generic_container<len(il.meta.generic_containers) or
            il.meta.generic_containers[td.generic_container]!=(td.index,1,0,rt[0]) or key(il.candidate_return_type(('generic',si)))!=key(arg) or
            _class_entry(il,si)!=call.near_branch_target):return None
    return td,ci,arg


def indexed_class_sites(lift,method,blocks,pads):
    il=lift.il;actions={}
    if not HAVE_ICED or pads or not _amd64(getattr(il,'bin',None)) or il.meta.version!=31 or method.is_static:return actions
    seq=[i for b in blocks for i in b.insns];windows=[];members={}
    for j in range(5,len(seq)):
        call=seq[j]
        if call.mnemonic!=M.CALL or call.op0_kind!=K.NEAR_BRANCH64:continue
        w=seq[j-5:j+1];load,test,null,slot,index,_=w
        if (load.mnemonic!=M.MOV or load.op0_register!=R.RCX or load.op1_kind!=K.MEMORY or not RegisterExt.is_gpr64(load.memory_base) or
                test.mnemonic!=M.TEST or test.op0_register!=test.op1_register or test.op0_register!=R.RCX or null.mnemonic!=M.JE or
                slot.mnemonic!=M.MOV or slot.op0_register!=R.R8 or slot.memory_base!=R.RIP or index.mnemonic!=M.MOV or index.op0_register!=R.EDX or
                not RegisterExt.is_gpr32(index.op1_register) or any(i.has_segment_prefix or i.has_lock_prefix or i.memory_index!=R.NONE for i in w)):continue
        usage=il.decode_slot(slot.ip_rel_memory_address) or {};si=usage.get('idx',-1)
        if usage.get('kind')!=6:continue
        member=_member(lift,si,call)
        if member:windows.append((w,si,member))
    if not windows:return actions
    g=_graph(il,seq,chained=True,allow_tail=True,runtime_tails=lift.rt_wbarrier)
    if not g or seq[0].ip!=method.addr:return actions
    pred,_=g;by={i.ip:i for i in seq};key=il._closed_type_key
    block_end={b.insns[-1].ip:b for b in blocks if b.insns};block_start={b.insns[0].ip:b.bid for b in blocks if b.insns}
    def checked(w,null):
        throw=by.get(null.near_branch_target)
        guarded=block_end.get(null.ip)
        # A null indexer invocation (or Count read) faults by dereference.
        # Do not let a still-rendered pointer test bind an overloaded ==.
        return (guarded and guarded.term==('jmp',block_start.get(null.next_ip)) and
                all(a.next_ip==b.ip and pred[b.ip]==[a.ip] for a,b in zip(w,w[1:])) and throw and throw.is_call_near and
                lift._named_raise_throw(throw.near_branch_target,lift._call_name(throw.near_branch_target))=='System.NullReferenceException')
    def own(load):
        row=reference_field_at(il,method.declaring,sdisp(load.memory_displacement),constructed=True)
        return row if row and row[0]==method.declaring and _receiver(il,method,by,pred,load.ip,row[0],initial=load.memory_base,this_only=True) else None
    for w,si,(td,ci,arg) in windows:
        load,test,null,slot,index,call=w
        if not checked(w,null):continue
        row=own(load)
        if not row or key(row[2])!=(0x15,(0x12,td.index,0),(key(arg),),0):continue
        f=('this.'+safe_ident(source_field_name(il,row[1])),row[2]);members[row[1]]=td,ci,f
        actions[load.ip]=('field_value',f,'RCX','obj');actions[call.ip]=('index_result',load.ip,si,arg)
    if not members:return actions
    for j,i in enumerate(seq):
        if j<3 or i.mnemonic!=M.MOV or not RegisterExt.is_gpr32(i.op0_register) or i.op1_kind!=K.MEMORY:continue
        test,null=seq[j-2:j];r=i.memory_base
        if (test.mnemonic!=M.TEST or test.op0_register!=r or test.op1_register!=r or not RegisterExt.is_gpr64(r) or null.mnemonic!=M.JE or
                i.has_segment_prefix or i.has_lock_prefix or i.memory_index!=R.NONE):continue
        # An optional stack save in between load and null test preserves the register.
        k=j-3;park=seq[k]
        if park.mnemonic==M.MOV and park.op0_kind==K.MEMORY and park.memory_base==R.RSP and RegisterExt.is_gpr64(park.op1_register):k-=1
        if k<0:continue
        load=seq[k];w=seq[k:j+1]
        if (load.mnemonic!=M.MOV or load.op0_register!=r or load.op1_kind!=K.MEMORY or not RegisterExt.is_gpr64(load.memory_base) or
                any(x.has_segment_prefix or x.has_lock_prefix or x.memory_index!=R.NONE for x in w) or not checked(w,null)):continue
        row=own(load)
        if not row or row[1] not in members:continue
        td,ci,f=members[row[1]];prop=_count_property(lift,td,ci,sdisp(i.memory_displacement))
        if prop:
            actions[load.ip]=('field_value',f,reg_name(r),'obj');actions[i.ip]=('count_value',load.ip,prop,reg_name(r),reg_name(i.op0_register))
    return actions
