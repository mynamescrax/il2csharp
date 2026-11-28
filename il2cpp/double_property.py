"""Two separate calls to the same reference getter around a field update."""
from il2cpp.array_origin import _graph
from il2cpp.closed_factory import _frame,_usage_guards,_class_init
from il2cpp.dictionary_ctor import _rr,_slot,_method
from il2cpp.equivalent_binary import _amd64
from il2cpp.gc_mark import mark_only
from il2cpp.metadata import source_params
from il2cpp.names import safe_ident
from il2cpp.plain_property import plain_alias
from il2cpp.prelude import HAVE_ICED
from il2cpp.sret_copy import _own_field
from il2cpp.text import sdisp
from il2cpp.x64 import KLASS_INITIALIZED
if HAVE_ICED:
    from iced_x86 import Mnemonic as M,OpKind as K,Register as R,RegisterExt as RX,MemorySizeExt as MS


def reacquired_after_store(l,m,td,s,eh):
    if not HAVE_ICED or eh or not 25<=len(s)<=52 or m.param_count!=1 or m.is_static or m.generic_container!=-1 or td.generic_container!=-1 or td.is_valuetype:return None
    il=l.il;key=il._closed_type_key
    if (not _amd64(il.bin) or il.meta.version!=31 or not 0<=m.return_type<len(il.types) or key(il.types[m.return_type])!=(1,0) or
            sum(i.is_call_near for i in s)!=7 or any(i.has_segment_prefix or i.has_lock_prefix or i.memory_index!=R.NONE for i in s) or
            any(a.next_ip!=b.ip for a,b in zip(s,s[1:]))):return None
    g=_graph(il,s);frame=_frame(il,m,s) if g else None
    if not frame:return None
    k,epi,ret,_,_,late,saved=frame;guard=_usage_guards(l,s,g[0]);ps=source_params(il.meta,m)
    if not guard or late or ret+3!=len(s) or len(ps)!=1 or not 0<=ps[0].type<len(il.types):return None
    skip,ready,_=guard;w=[i for i in s[k+1:epi] if i.ip not in skip]
    if len(w)!=23 or len(ready)!=1:return None
    park,self_,klass,ci,hot,init,z1,call1,t1,null1,old,addr,write,mark,z2,call2,t2,null2,hidden,arg,receiver,act,done=w
    owner=self_.op0_register;pr=park.op0_register;ty=il.types[ps[0].type];param=safe_ident(ps[0].name);first=_method(il,call1);method=_method(il,act)
    if (not {pr,owner}<=saved or pr==owner or not _rr(park,M.MOV,pr,R.RDX) or not _rr(self_,M.MOV,owner,R.RCX) or
            key(ty)!=(0x12,ty[0],0) or not first or not method or not first.is_static or first.generic_container!=-1 or first.param_count or
            first.flags&7!=6 or first.flags&0x40 or not 0<=first.return_type<len(il.types) or not call2.is_call_near or call2.near_branch_target!=call1.near_branch_target):return None
    get=l._accessor_prop(first.index);rt=il.types[first.return_type];classslot=_slot(klass,R.RCX,M.MOV);us=il.decode_slot(classslot) if classslot else None
    if (not get or get[0]!='get' or get[2] or safe_ident(get[1])!=get[1] or not get[1].isidentifier() or key(rt)!=(0x12,first.declaring,0) or
            not us or us.get('kind')!=1 or us.get('td')!=first.declaring or list(ready)!=[klass.ip] or ready[klass.ip]!={classslot} or
            ci.mnemonic!=M.CMP or ci.memory_base!=R.RCX or ci.memory_displacement!=KLASS_INITIALIZED or ci.op1_kind!=K.IMMEDIATE8TO32 or ci.immediate8to32 or
            hot.mnemonic!=M.JNE or hot.near_branch_target!=z1.ip or not init.is_call_near or not _class_init(il,init.near_branch_target)):return None
    if (not _rr(z1,M.XOR,R.ECX,R.ECX) or not _rr(z2,M.XOR,R.ECX,R.ECX) or not _rr(t1,M.TEST,R.RAX,R.RAX) or not _rr(t2,M.TEST,R.RAX,R.RAX) or
            null1.mnemonic!=M.JE or null2.mnemonic!=M.JE or null1.near_branch_target!=null2.near_branch_target or null1.near_branch_target!=s[ret+1].ip or
            not s[ret+1].is_call_near or s[ret+2].mnemonic!=M.INT3 or l._named_raise_throw(s[ret+1].near_branch_target,l._call_name(s[ret+1].near_branch_target))!='System.NullReferenceException'):return None
    if (old.mnemonic!=M.MOV or old.op0_register!=R.RDX or old.memory_base!=R.RAX or addr.mnemonic!=M.LEA or addr.op0_register!=R.RCX or addr.memory_base!=owner or
            write.mnemonic!=M.MOV or write.op1_register!=R.RDX or write.memory_base!=owner or write.memory_displacement!=addr.memory_displacement or
            not mark.is_call_near or not mark_only(il,mark.near_branch_target)):return None
    alias=plain_alias(l,rt[0],sdisp(old.memory_displacement),8);dst=_own_field(il,td,sdisp(write.memory_displacement),8);end=_own_field(il,td,sdisp(done.memory_displacement),1)
    if (not alias or not dst or key(dst[1])!=key(alias[1]) or not end or key(end[1])!=(2,0) or not _rr(hidden,M.XOR,R.R8D,R.R8D) or
            not _rr(arg,M.MOV,R.RDX,pr) or not _rr(receiver,M.MOV,R.RCX,R.RAX) or method.declaring!=rt[0] or method.is_static or method.generic_container!=-1 or
            method.flags&7!=6 or method.flags&0x40 or method.param_count!=1 or not 0<=method.return_type<len(il.types) or key(il.types[method.return_type])!=(1,0) or
            not method.name.isidentifier() or safe_ident(method.name)!=method.name or done.mnemonic!=M.MOV or done.memory_base!=owner or MS.size(done.memory_size)!=1 or
            done.op1_kind!=K.IMMEDIATE8 or done.immediate8 not in (0,1)):return None
    args=il.meta.method_params(method);cl=il.typedef_full(rt[0]);root=f'global::{cl}.{get[1]}'
    if len(args)!=1 or not 0<=args[0].type<len(il.types) or key(il.types[args[0].type])!=key(ty):return None
    return [f'global::System.Runtime.CompilerServices.RuntimeHelpers.RunClassConstructor(typeof(global::{cl}).TypeHandle);',f'{dst[0]} = {root}.{alias[0]};',f'{root}.{method.name}({param});',f'{end[0]} = '+('true;' if done.immediate8 else 'false;'),'return;']
