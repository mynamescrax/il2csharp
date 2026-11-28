"""Optional composite-format logging followed by an independent enum read.

The equality edge and the in-range fallthrough both enter the same action.
Prove its original arguments and the post-log mode sample, including the
failure edges, before replacing this small Win64 wrapper.
"""
import json
from il2cpp.array_origin import _graph,_SAVED
from il2cpp.boxed_quotient import _home
from il2cpp.closed_factory import _frame,_usage_guards,_class_init
from il2cpp.dictionary_ctor import _method,_rr,_slot
from il2cpp.equivalent_binary import _amd64
from il2cpp.metadata import source_params
from il2cpp.names import safe_ident
from il2cpp.plain_property import plain_alias
from il2cpp.prelude import HAVE_ICED
from il2cpp.sret_copy import _own_field
from il2cpp.text import sdisp
from il2cpp.x64 import KLASS_INITIALIZED
if HAVE_ICED:
    from iced_x86 import Mnemonic as M,Register as R,RegisterExt as RX,OpKind as K,MemorySizeExt as MS


def _cmp0(i,r):return _rr(i,M.TEST,r,r)


def _branch(i,op,target):return i.mnemonic==op and i.op0_kind==K.NEAR_BRANCH64 and i.near_branch_target==target


def _object_type(il,k,r,ty):
    addr=_slot(k,r,M.MOV);u=il.decode_slot(addr) if addr else None
    return bool(u and u.get('kind')==1 and il._closed_type_key(u.get('type'))==il._closed_type_key(ty))


def _box(l,frame,seq,k,lea,st,box,reg,ty):
    return (box.is_call_near and box.near_branch_target==l.rt_value_box and _object_type(l.il,k,R.RCX,ty) and
            lea.mnemonic==M.LEA and lea.op0_register==R.RDX and lea.memory_base==R.RSP and st.mnemonic==M.MOV and
            st.memory_base==R.RSP and st.op1_register==reg and st.op0_kind==K.MEMORY and st.memory_displacement==lea.memory_displacement and
            MS.size(st.memory_size)==4 and _home(seq,frame,lea,st))


def _signature(il,i,params,returns,*,static):
    m=_method(il,i)
    if (not m or m.is_static!=static or m.flags&0x40 or m.generic_container!=-1 or not 0<=m.return_type<len(il.types) or
            il._closed_type_key(il.types[m.return_type]) not in returns):return None
    ps=il.meta.method_params(m)
    if len(ps)!=len(params) or len(ps)!=m.param_count or any(not 0<=p.type<len(il.types) or il._closed_type_key(il.types[p.type])!=k for p,k in zip(ps,params)):return None
    return m


def logged_selection(l,m,td,s,eh):
    if not HAVE_ICED or eh or not 56<=len(s)<=90 or m.param_count!=2 or m.is_static or td.is_valuetype or td.generic_container!=-1 or m.generic_container!=-1:return None
    il=l.il;key=il._closed_type_key
    if (not _amd64(il.bin) or il.meta.version!=31 or not 0<=m.return_type<len(il.types) or key(il.types[m.return_type])!=(1,0) or
            sum(i.is_call_near and i.near_branch_target==l.rt_value_box for i in s)!=2 or
            any(i.has_segment_prefix or i.has_lock_prefix or i.memory_index!=R.NONE for i in s) or any(a.next_ip!=b.ip for a,b in zip(s,s[1:]))):return None
    ps=source_params(il.meta,m)
    if len(ps)!=2 or any(not 0<=p.type<len(il.types) for p in ps):return None
    target,payload=(il.types[p.type] for p in ps);runner,player=(safe_ident(p.name) for p in ps)
    if (not target or key(target)!=(0x12,target[0],0) or not payload or key(payload)!=(0x11,payload[0],0) or
            not 0<=target[0]<len(il.meta.typedefs) or not 0<=payload[0]<len(il.meta.typedefs) or il.value_type_size(payload[0])!=4 or
            il.meta.typedefs[payload[0]].generic_container!=-1 or not il.meta.typedefs[payload[0]].is_valuetype or
            runner==player or set((runner,player))&{'loggedMode','modeBits','message','boxedPlayer'}):return None
    g=_graph(il,s);frame=_frame(il,m,s) if g else None
    if not frame:return None
    pred,_=g;k,epi,ret,size,spans,late,saved=frame
    guarded=_usage_guards(l,s,pred,kinds=(1,5));
    if not guarded:return None
    skip,ready,flags=guarded
    if len(ready)!=1 or ret!=len(s)-5 or epi<=k:return None
    # Filter only verified metadata plumbing (never its gap) and the one
    # recorded, always-executed nonvolatile save in the optional log guard.
    w=[i for i in s[k+1:epi] if i.ip not in skip and i.ip not in late]
    if len(w)!=44 or len(late)!=1:return None
    p,rr,me,guard,omit,kp,ap,sp,bp,park,t1,j1,load,ae,se,ke,be,lit,zh,eb,pb,fmt,logger,msg,ci,hot,init,zero,arg,log,join,t2,j2,again,cmp,accept,bias,limit,exclude,hid,original,recv,self_,act=w
    pr,reg,owner=RX.full_register(p.op0_register),rr.op0_register,me.op0_register;save=park.op0_register
    if (not RX.is_gpr32(p.op0_register) or not _rr(p,M.MOV,p.op0_register,R.R8D) or not _rr(rr,M.MOV,reg,R.RDX) or not _rr(me,M.MOV,owner,R.RCX) or
            not {reg,owner,pr,save}<=set(saved)&_SAVED or len({reg,owner,pr,save})!=4 or
            next(iter(late))!=guard.next_ip or list(late.values())[0][0]!=save or
            guard.mnemonic!=M.CMP or guard.memory_base!=owner or MS.size(guard.memory_size)!=1 or guard.op1_kind!=K.IMMEDIATE8 or guard.immediate8 or
            not _branch(omit,M.JE,t2.ip) or not _rr(park,M.MOV,save,R.RAX) or not _cmp0(t1,reg) or not _cmp0(t2,reg) or
            not _branch(j1,M.JE,s[ret+3].ip) or not _branch(j2,M.JE,s[ret+1].ip) or not _branch(join,M.JMP,again.ip)):return None
    if any(not raiser.is_call_near or trap.mnemonic!=M.INT3 or l._named_raise_throw(raiser.near_branch_target,l._call_name(raiser.near_branch_target))!='System.NullReferenceException' for raiser,trap in (s[ret+1:ret+3],s[ret+3:ret+5])):return None
    flag=_own_field(il,td,sdisp(guard.memory_displacement),1);off=sdisp(again.memory_displacement)
    if (not flag or key(flag[1])!=(2,0) or load.mnemonic!=M.MOV or again.mnemonic!=M.MOV or load.op0_register!=R.ECX or again.op0_register!=R.EAX or
            load.memory_base!=reg or again.memory_base!=reg or sdisp(load.memory_displacement)!=off):return None
    alias=plain_alias(l,target[0],off,4)
    if not alias:return None
    name,et=alias;enum=il.meta.typedefs[et[0]] if key(et)==(0x11,et[0],0) and 0<=et[0]<len(il.meta.typedefs) else None
    if not enum or not enum.is_enum or enum.generic_container!=-1 or il.value_type_size(enum.index)!=4:return None
    # The two halves of the box operation borrow different four-byte
    # homes. No pointer is reused and every argument register is explicit.
    depth=size+8*(sum(i.mnemonic==M.PUSH for i in s[:k]));fr=(size,depth,spans)
    if (not _box(l,fr,s,kp,ap,sp,bp,p.op0_register,payload) or not _box(l,fr,s,ke,ae,se,be,R.ECX,et) or ap.memory_displacement==ae.memory_displacement or
            not _rr(zh,M.XOR,R.R9D,R.R9D) or not _rr(eb,M.MOV,R.R8,R.RAX) or not _rr(pb,M.MOV,R.RDX,save)):return None
    strings=_signature(il,fmt,[(14,0),(28,0),(28,0)],{(14,0)},static=True);sink=_signature(il,log,[(28,0)],{(1,0)},static=True)
    a=_slot(lit,R.RCX,M.MOV);u=il.decode_slot(a) if a else None;lc=_slot(logger,R.RCX,M.MOV);klass=il.decode_slot(lc) if lc else None
    if (not strings or [t.index for t in il.meta.typedefs if t.namespace=='System' and t.name=='String']!=[strings.declaring] or il.typedef_full(strings.declaring)!='System.String' or strings.name!='Format' or strings.flags&7!=6 or not sink or
            sink.flags&7!=6 or not sink.name.isidentifier() or safe_ident(sink.name)!=sink.name or not u or u.get('kind')!=5 or not 0<=u['idx']<len(il.meta.string_literals) or
            not klass or klass.get('kind')!=1 or klass.get('td')!=sink.declaring or il.meta.typedefs[sink.declaring].generic_container!=-1 or
            set(next(iter(ready.values())))!={a,lc,kp.ip_rel_memory_address,ke.ip_rel_memory_address} or next(iter(ready))!=guard.ip or
            not _rr(msg,M.MOV,save,R.RAX) or ci.mnemonic!=M.CMP or ci.memory_base!=R.RCX or ci.memory_displacement!=KLASS_INITIALIZED or
            MS.size(ci.memory_size)!=4 or ci.op1_kind!=K.IMMEDIATE8TO32 or ci.immediate8to32 or not _branch(hot,M.JNE,zero.ip) or
            not init.is_call_near or not _class_init(il,init.near_branch_target) or not _rr(zero,M.XOR,R.EDX,R.EDX) or not _rr(arg,M.MOV,R.RCX,save)):return None
    action=_signature(il,act,[key(target),key(payload)],{(1,0),(2,0)},static=False)
    if (not action or action.declaring!=td.index or not action.name.isidentifier() or safe_ident(action.name)!=action.name or
            not _rr(hid,M.XOR,R.R9D,R.R9D) or not _rr(original,M.MOV,R.R8D,p.op0_register) or not _rr(recv,M.MOV,R.RDX,reg) or not _rr(self_,M.MOV,R.RCX,owner) or
            any(i.op0_register!=R.EAX or i.op1_kind not in (K.IMMEDIATE8TO32,K.IMMEDIATE32) for i in (cmp,bias,limit)) or
            cmp.mnemonic!=M.CMP or bias.mnemonic!=M.ADD or limit.mnemonic!=M.CMP or not _branch(accept,M.JE,hid.ip) or not _branch(exclude,M.JA,s[epi].ip)):return None
    # No other incoming edge or action after the call: its result is dead.
    if set(pred[hid.ip])!={accept.ip,exclude.ip} or set(pred[s[epi].ip])!={exclude.ip,act.ip}:return None
    cl=il.typedef_full(sink.declaring)
    if not all(x.isidentifier() and safe_ident(x)==x for x in cl.split('.')):return None
    eq=cmp.immediate(1)&0xffffffff;add=bias.immediate(1)&0xffffffff;hi=limit.immediate(1)&0xffffffff;literal=json.dumps(il.meta.string_literal(u['idx']),ensure_ascii=True)
    return [f'if ({flag[0]})','{',f'    object boxedPlayer = (object){player};',f'    var loggedMode = {runner}.{name};',f'    string message = string.Format({literal}, boxedPlayer, (object)loggedMode);',f'    global::System.Runtime.CompilerServices.RuntimeHelpers.RunClassConstructor(typeof(global::{cl}).TypeHandle);',f'    global::{cl}.{sink.name}((object)message);','}',f'uint modeBits = unchecked((uint){runner}.{name});',f'if (modeBits == {eq}u || unchecked(modeBits + {add}u) <= {hi}u)','{',f'    this.{action.name}({runner}, {player});','}','return;']
