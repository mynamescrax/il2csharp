"""A saved singleton invokes a nonvirtual reference factory with a closed
component lookup, a position sample, a readonly struct and a null callback.
Verify the hidden stack argument independently of the visible null.
"""
from il2cpp.array_origin import _graph,_SAVED
from il2cpp.closed_factory import _frame,_class_init,_usage_guards,_alias
from il2cpp.closed_lookup import spec_lookup
from il2cpp.accessor_chain import _property
from il2cpp.dictionary_ctor import _method,_slot,_rr
from il2cpp.equivalent_binary import _amd64,_writable
from il2cpp.names import safe_ident
from il2cpp.packed_call import _float_fields
from il2cpp.prelude import HAVE_ICED
from il2cpp.static_getter import alias_for_slot
from il2cpp.sret_copy import _own_field
from il2cpp.text import sdisp
from il2cpp.x64 import KLASS_INITIALIZED,KLASS_STATIC_FIELDS
if HAVE_ICED:
    from iced_x86 import Mnemonic as M,Register as R,RegisterExt as RX,OpKind as K,MemorySizeExt as MS


def _load(i,r,base,off,op=None):return i.mnemonic==(op or M.MOV) and i.op0_register==r and i.op1_kind==K.MEMORY and i.memory_base==base and i.memory_displacement==off


def _store(i,base,off,r,op=None):return i.mnemonic==(op or M.MOV) and i.op0_kind==K.MEMORY and i.op1_register==r and i.memory_base==base and i.memory_displacement==off


def singleton_factory(l,m,td,s,eh):
    if not HAVE_ICED or eh or not 62<=len(s)<=86 or m.is_static or m.param_count or td.is_valuetype or td.generic_container!=-1 or m.generic_container!=-1:return None
    il=l.il;key=il._closed_type_key
    if (not _amd64(il.bin) or il.meta.version!=31 or not 0<=m.return_type<len(il.types) or key(il.types[m.return_type])!=(1,0) or
            not any(i.mnemonic==M.MOV and i.op1_register==R.RAX and i.op0_register in _SAVED for i in s) or
            any(i.has_segment_prefix or i.has_lock_prefix or i.memory_index!=R.NONE for i in s) or any(a.next_ip!=b.ip for a,b in zip(s,s[1:]))):return None
    g=_graph(il,s,chained=True,nested_chains=True);frame=_frame(il,m,s) if g else None
    if not frame:return None
    k,ep,ret,size,spans,late,saved=frame;pred,_=g
    if ep<27 or ret+3!=len(s) or len(late)!=1:return None
    tail=s[ep-25:ep];cmp,xy,z,spill,hot,lea,init,reload,ready,klass,blob,test,jnull,quat,zero,rot,pos,lo,hidden,component,recv,rotcopy,hi,nullarg,act=tail
    guard=_usage_guards(l,s[:ep-25],pred)
    if not guard:return None
    skip,us,flags=guard;w=[i for i in s[k+1:ep-25] if i.ip not in skip and i.ip not in late]
    if len(w)!=24:return None
    me,*ops=w;owner=me.op0_register
    if owner not in saved or not _rr(me,M.MOV,owner,R.RCX):return None
    mg=None;rest=ops[8:]
    for a,c,b,q in (ops[:4],ops[4:8]):
        slot=_slot(a,R.RCX,M.MOV)
        if (not slot or mg not in (None,slot) or c.mnemonic!=M.CMP or c.memory_base!=R.RCX or c.memory_displacement!=KLASS_INITIALIZED or c.op1_kind!=K.IMMEDIATE8TO32 or c.immediate8to32 or
                b.mnemonic!=M.JNE or b.near_branch_target!=q.next_ip or not q.is_call_near or not _class_init(il,q.near_branch_target)):return None
        mg=slot
    km,static,ref,fobj,t0,j0,spec,c0,trans,park,t1,j1,zinfo,h,c1=rest
    # Both guards initialize the factory owner. The later one-slot protocol
    # cannot be shared with the distinct readonly aggregate or lookup slot.
    if (not mg or _slot(km,R.RAX,M.MOV)!=mg or not _load(static,R.RCX,R.RAX,KLASS_STATIC_FIELDS) or ref.op0_register not in saved or
            not _load(ref,ref.op0_register,R.RCX,ref.memory_displacement) or len(us)!=2 or us.get(ops[0].ip)!={mg,spec.ip_rel_memory_address} or us.get(ops[4].ip)!={mg} or
            not _load(fobj,R.RCX,owner,fobj.memory_displacement) or not _rr(t0,M.TEST,R.RCX,R.RCX) or not _load(trans,R.RDX,owner,trans.memory_displacement) or
            park.op0_register not in saved or not _rr(park,M.MOV,park.op0_register,R.RAX) or len({owner,ref.op0_register,park.op0_register})!=3 or
            not _rr(t1,M.TEST,R.RDX,R.RDX) or not _rr(zinfo,M.XOR,R.R8D,R.R8D) or h.mnemonic!=M.LEA or h.op0_register!=R.RCX or h.memory_base!=R.RSP):return None
    if next(iter(late))!=km.next_ip or next(iter(late.values()))[0]!=park.op0_register:return None
    md=_method(il,act);lookup=spec_lookup(il,spec,c0);getter=_property(l,c1)
    if not md or not lookup or not getter or not il.returns_sret(getter[2]) or not 0<=md.return_type<len(il.types):return None
    kret=key(il.types[md.return_type]);ps=il.meta.method_params(md);u=il.decode_slot(mg) or {};fi=_own_field(il,td,sdisp(fobj.memory_displacement),8);tf=_own_field(il,td,sdisp(trans.memory_displacement),8)
    if (md.is_static or md.flags&0x40 or md.flags&7!=6 or md.generic_container!=-1 or not md.name.isidentifier() or safe_ident(md.name)!=md.name or
            u.get('kind')!=1 or u.get('td')!=md.declaring or not kret or kret[0]!=0x12 or kret[-1] or md.param_count!=len(ps) or len(ps)!=4 or
            not all(0<=p.type<len(il.types) for p in ps) or not fi or not tf or key(fi[1])!=(0x12,lookup[1].declaring,0) or key(tf[1])!=(0x12,getter[0].declaring,0)):return None
    a,bt,rt,callback=[il.types[p.type] for p in ps];cb=key(callback)
    if (key(a)!=key(lookup[2]) or key(a)!=kret or key(bt)!=key(getter[2]) or len(_float_fields(il,bt) or ())!=3 or len(_float_fields(il,rt) or ())!=4 or
            not cb or cb[-1] or not (cb[0]==0x12 or cb[0]==0x15 and cb[1][0]==0x12)):return None
    # Avoid selecting a different overload for null, even if its return
    # type and the first three parameter names happened to agree.
    if any(il.meta.methods[n].name==md.name and n!=md.index for ti in il.base_chain_tds(md.declaring) for n in il.meta.type_methods(il.meta.typedefs[ti])):return None
    prop=alias_for_slot(il,mg,l.rt_init_meta,ref.memory_displacement,guarded=True)
    flag=cmp.ip_rel_memory_address;rotation=_slot(klass,R.RAX,M.MOV);slot=_slot(lea,R.RCX,M.LEA);depth=size+8*sum(x.mnemonic==M.PUSH for x in s[:k]);tmp=spill.memory_displacement
    if (not prop or cmp.mnemonic!=M.CMP or cmp.memory_base!=R.RIP or cmp.op1_kind!=K.IMMEDIATE8 or cmp.immediate8 or not _writable(il.bin,flag,1) or
            flag in flags or any(v<=flag<v+8 for vals in us.values() for v in vals) or not slot or slot!=rotation or any(slot<=p<slot+8 for p in (*flags,flag)) or
            not _load(xy,xy.op0_register,R.RAX,0,M.MOVSD) or not R.XMM0<=xy.op0_register<=R.XMM5 or not _load(z,z.op0_register,R.RAX,8) or
            not RX.is_gpr32(z.op0_register) or RX.full_register(z.op0_register) not in saved-{ref.op0_register,park.op0_register} or not _store(spill,R.RSP,tmp,xy.op0_register,M.MOVSD) or
            hot.mnemonic!=M.JNE or hot.near_branch_target!=klass.ip or not init.is_call_near or init.near_branch_target!=l.rt_init_meta or not _load(reload,xy.op0_register,R.RSP,tmp,M.MOVSD) or
            ready.mnemonic!=M.MOV or ready.memory_base!=R.RIP or ready.ip_rel_memory_address!=flag or ready.op1_kind!=K.IMMEDIATE8 or ready.immediate8!=1 or
            not _load(blob,R.RCX,R.RAX,KLASS_STATIC_FIELDS) or not _rr(test,M.TEST,ref.op0_register,ref.op0_register)):return None
    if (not all(j.mnemonic==M.JE and j.near_branch_target==s[ret+1].ip for j in (j0,j1,jnull)) or not s[ret+1].is_call_near or s[-1].mnemonic!=M.INT3 or
            l._named_raise_throw(s[ret+1].near_branch_target,l._call_name(s[ret+1].near_branch_target))!='System.NullReferenceException'):return None
    sec=_writable(il.bin,flag,1)
    if flag<sec.addr+sec.rawsize and il.bin.read(flag,1)!=b'\0':return None
    alias=_alias(l,m,slot,sdisp(quat.memory_displacement),rt,flags|{flag:{slot}})
    p0=h.memory_displacement;p1=rot.memory_displacement
    if (not alias or not _load(quat,quat.op0_register,R.RCX,quat.memory_displacement,M.MOVUPS) or not R.XMM0<=quat.op0_register<=R.XMM5 or quat.op0_register==xy.op0_register or
            not _rr(zero,M.XOR,R.EAX,R.EAX) or not _load(rot,R.R9,R.RSP,p1,M.LEA) or not _load(pos,R.R8,R.RSP,p0,M.LEA) or
            not _store(lo,R.RSP,p0,xy.op0_register,M.MOVSD) or not _store(hidden,R.RSP,40,R.RAX) or not _rr(component,M.MOV,R.RDX,park.op0_register) or
            not _rr(recv,M.MOV,R.RCX,ref.op0_register) or not _store(rotcopy,R.RSP,p1,quat.op0_register,M.MOVAPS) or not _store(hi,R.RSP,p0+8,z.op0_register) or
            not _store(nullarg,R.RSP,32,R.RAX) or p1%16 or p0%4 or not 48<=p0<=size-12 or not 48<=p1<=size-16 or not depth+8<=tmp<=depth+32):return None
    spans_=sorted([*spans,(p0,12),(p1,16),(tmp,8),(32,16),(depth,8)])
    if any(a+n>b for (a,n),(b,_) in zip(spans_,spans_[1:])):return None
    cl=il.typedef_full(md.declaring);actual=il.type_name(a)
    if any(not all(p.isidentifier() and safe_ident(p)==p for p in t.split('.')) for t in (actual,cl)):return None
    return [f'global::System.Runtime.CompilerServices.RuntimeHelpers.RunClassConstructor(typeof(global::{cl}).TypeHandle);',f'var factory = global::{prop[0]};',f'var prefab = {fi[0]}.{lookup[1].name}<global::{actual}>();',f'var position = {tf[0]}.{getter[1]};','if (factory is null) { throw new global::System.NullReferenceException(); }',f'factory.{md.name}(prefab, position, global::{alias}, null);','return;']
