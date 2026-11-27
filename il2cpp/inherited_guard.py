"""Bind a guarded private base-field read through its registered public leaf.

The reference is read at the MOV. The subsequent nullary Boolean query is
still invoked on that object; an authority shortcut on the outer receiver
may have a different null path or additional conditions.
"""
from il2cpp.array_origin import _graph,_definitions
from il2cpp.closed_lookup import _receiver
from il2cpp.csharp import declares_member_name
from il2cpp.equivalent_binary import _amd64
from il2cpp.names import safe_ident
from il2cpp.prelude import HAVE_ICED
from il2cpp.shared_field import reference_field_at
from il2cpp.text import sdisp

if HAVE_ICED:
    from iced_x86 import Mnemonic as M,OpKind as K,Register as R,RegisterExt


def public_load(lift,method,off):
    il=lift.il;ti=method.declaring;row=reference_field_at(il,ti,off)
    if not row or row[0]==ti or row[2][1]&7!=1 or not 0<off<128:return None
    owner,fi,ty=row;chain=il.base_chain_tds(ti);candidates=[]
    for j in il.meta.type_methods(il.meta.typedefs[owner]):
        m=il.meta.methods[j];k=lift._accessor_prop(j)
        if (m.is_static or m.declaring!=owner or m.flags&7!=6 or m.flags&0x40 or not m.addr or m.addr==method.addr or
                m.param_count or m.generic_container!=-1 or not 0<=m.return_type<len(il.types) or
                il._closed_type_key(il.types[m.return_type])!=il._closed_type_key(ty) or not k or k[0]!='get' or k[2] or
                ('method',j) not in il.addr_candidates.get(m.addr,()) or not il.bin.is_exec_va(m.addr) or
                il.bin.read(m.addr,5)!=bytes((0x48,0x8b,0x41,off,0xc3))):continue
        name=safe_ident(k[1])
        if name!=k[1] or not name.isidentifier() or any(declares_member_name(il,il.meta.typedefs[t],name) for t in chain[:chain.index(owner)]):continue
        candidates.append(('this.'+name,ty))
    return candidates[0] if len(candidates)==1 else None


def inherited_guards(lift,method,blocks,pads,virtuals=()):
    il=lift.il;sites={};windows=[]
    if (not HAVE_ICED or pads or not _amd64(getattr(il,'bin',None)) or il.meta.version!=31 or method.is_static or
            il.meta.typedefs[method.declaring].is_valuetype):return sites
    seq=[i for b in blocks for i in b.insns]
    for j in range(3,len(seq)-2):
        call=seq[j]
        if not call.is_call_near:continue
        ptr,null,zero,_,test,branch=seq[j-3:j+3]
        if (ptr.mnemonic!=M.TEST or ptr.op0_register!=ptr.op1_register or ptr.op0_register!=R.RCX or null.mnemonic!=M.JE or
                zero.mnemonic!=M.XOR or zero.op0_register!=zero.op1_register or zero.op0_register!=R.EDX or test.mnemonic!=M.TEST or
                test.op0_register!=test.op1_register or test.op0_register!=R.AL or branch.mnemonic not in (M.JE,M.JNE)):continue
        ids=il.addr_candidates.get(call.near_branch_target,())
        if len(ids)!=1 or ids[0][0]!='method' or not 0<=ids[0][1]<len(il.meta.methods):continue
        m=il.meta.methods[ids[0][1]];p=lift._accessor_prop(m.index)
        if (not p or p[0]!='get' or p[2] or m.param_count or m.addr!=call.near_branch_target or m.is_static or m.flags&7!=6 or
                m.flags&0x40 or m.generic_container!=-1 or not 0<=m.return_type<len(il.types) or il._closed_type_key(il.types[m.return_type])!=(2,0)):continue
        windows.append((seq[j-3:j+3],m))
    if not windows:return sites
    by={i.ip:i for i in seq};approve=(lambda i,*_:i.ip in virtuals) if virtuals else None
    slots={b.insns[-1].ip:tuple(b.switch_targets) for b in blocks if b.switch_targets}
    graph=_graph(il,seq,allow_tail=True,chained=True,runtime_tails=lift.rt_wbarrier,virtual_edges=approve,switch_slots=slots)
    if not graph or seq[0].ip!=method.addr:return sites
    pred,_=graph
    for w,m in windows:
        if any(pred[b.ip]!=[a.ip] or a.next_ip!=b.ip for a,b in zip(w,w[1:])):continue
        throw=by.get(w[1].near_branch_target)
        if not throw or not throw.is_call_near or lift._named_raise_throw(throw.near_branch_target,lift._call_name(throw.near_branch_target))!='System.NullReferenceException':continue
        defs=_definitions(by,pred,method.addr,w[0].ip,R.RCX)
        if len(defs)!=1:continue
        ip,r=defs.pop();load=by[ip]
        if (load.mnemonic!=M.MOV or load.op0_register!=r or not RegisterExt.is_gpr64(r) or load.op1_kind!=K.MEMORY or
                not RegisterExt.is_gpr64(load.memory_base) or load.memory_index!=R.NONE or load.has_lock_prefix or load.has_segment_prefix or
                not _receiver(il,method,by,pred,ip,method.declaring,initial=load.memory_base,this_only=True)):continue
        row=public_load(lift,method,sdisp(load.memory_displacement))
        # Name lookup on a more-derived receiver could select a different
        # 'new' property even though the direct native target is unique.
        if row and m.declaring==row[1][0]:sites[ip]=row
    return sites
