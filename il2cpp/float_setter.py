"""Fold a marshalled reference/Single setter after a proved float producer.

Both folded MethodDefs have the same physical argument positions, but the
caller matters: in particular the managed null check occurs *after* the RHS.
"""
import re

from il2cpp.array_origin import _graph
from il2cpp.closed_lookup import _receiver
from il2cpp.equivalent_binary import _amd64,_writable
from il2cpp.marshalled_getter import _INIT,_READY
from il2cpp.names import safe_ident
from il2cpp.reparent import _marshal_slot
from il2cpp.shared_action import _raises_on_null
from il2cpp.sret_copy import _own_field
from il2cpp.prelude import HAVE_ICED
from il2cpp.text import reg_name,sdisp

if HAVE_ICED:
    from iced_x86 import Mnemonic as M, OpKind as K, Register as R
    _SAVED={R.RBX,R.RDI,R.RSI,R.RBP,R.R12,R.R13,R.R14,R.R15}

# Save the incoming reference and low float across metadata initialization,
# marshalling and resolution. Follow the cache hit, miss and both null paths.
_PRO=re.compile(rb'\x40\x53\x48\x83\xec\x30\x80\x3d(.{4})\x00\x48\x8b\xd9\x0f\x29\x74\x24\x20\x0f\x28\xf1\x75(.)',re.S)
_SELF=re.compile(rb'\x48\x85\xdb\x74(.)\x48\x89\x7c\x24\x40\x48\x8b\x7b(.)\x48\x85\xff\x75\x12'
                 rb'\x48\x8b\x15(.{4})\x45\x33\xc0\x48\x8b\xcb\xe8(.{4})',re.S)
_TAIL=re.compile(rb'\x48\x8b\x05(.{4})\x48\x85\xc0\x75\x13\x48\x8d\x0d(.{4})\xe8(.{4})\x48\x89\x05(.{4})'
                 rb'\x0f\x28\xce\x48\x8b\xcf\x48\x8b\x7c\x24\x40\x0f\x28\x74\x24\x20\x48\x83\xc4\x30\x5b\x48\xff\xe0',re.S)
_NULL=re.compile(rb'\x48\x8b\x15(.{4})\x45\x33\xc0\x33\xc9\xe8(.{4})\xe8(.{4})\xcc',re.S)


def _alias(lift,addr):
    il=lift.il;ids=il.addr_candidates.get(addr,());key=il._closed_type_key
    if len(ids)!=2 or any(k!='method' or not 0<=j<len(il.meta.methods) for k,j in ids):return None
    rows=sorted((il.meta.methods[j] for _,j in ids),key=lambda m:m.is_static);prop,helper=rows;owner=prop.declaring
    if (not 0<=owner<len(il.meta.typedefs) or prop.is_static or prop.flags&7!=6 or not helper.is_static or helper.flags&7!=1 or helper.declaring!=owner or
            any(m.addr!=addr or m.generic_container!=-1 or m.flags&0x40 or not 0<=m.return_type<len(il.types) or key(il.types[m.return_type])!=(1,0) for m in rows)):return None
    td=il.meta.typedefs[owner];member=lift._accessor_prop(prop.index);ref=(0x12,owner,0);single=(0x0c,0)
    def params(m):return [key(il.types[p.type]) if 0<=p.type<len(il.types) else None for p in il.meta.method_params(m)]
    if (td.is_valuetype or td.generic_container!=-1 or td.has_cctor or td.flags&7!=1 or not member or member[0]!='set' or member[2] or
            prop.param_count!=1 or helper.param_count!=2 or params(prop)!=[single] or params(helper)!=[ref,single]):return None
    end=il.next_method_start(addr)
    if not end or not 0<end-addr<=384 or not il.bin.is_exec_va(addr):return None
    raw=il.bin.read(addr,end-addr) or b'';pro=_PRO.match(raw)
    if not pro:return None
    def rel(m,j,trailing=0):return addr+m.end(j)+trailing+int.from_bytes(m[j],'little',signed=True)
    pos=pro.end();slots=[]
    while (init:=_INIT.match(raw,pos)):
        if rel(init,2)!=lift.rt_init_meta:return None
        slots.append(rel(init,1));pos=init.end()
    ready=_READY.match(raw,pos)
    if (not ready or len(slots)!=2 or rel(ready,1,1)!=rel(pro,1,1) or rel(pro,2)!=addr+ready.end() or
            not _marshal_slot(il,slots[0],'MarshalNotNull',owner)):return None
    u=il.decode_slot(slots[1]) or {};ps=il.meta.method_params(helper)
    if u.get('kind')!=5 or not 0<=u.get('idx',-1)<len(il.meta.string_literals) or il.meta.string_literal(u['idx'])!=ps[0].name:return None
    obj=_SELF.match(raw,ready.end());tail=_TAIL.match(raw,obj.end()) if obj else None;null=_NULL.match(raw,tail.end()) if tail else None
    if (not null or rel(obj,1)!=addr+null.start() or rel(obj,3)!=slots[1] or rel(null,1)!=slots[1] or rel(null,2)!=rel(obj,4) or
            rel(tail,1)!=rel(tail,4) or rel(tail,3)!=il.rt_icall_resolve):return None
    flag=rel(pro,1,1);cell=rel(tail,1);sec=_writable(il.bin,flag,1)
    if (not sec or flag<sec.addr+sec.rawsize and il.bin.read(flag,1)!=b'\0' or not _writable(il.bin,cell,8) or
            cell%8 or any(p<=flag<p+8 or p<cell+8 and cell<p+8 for p in slots) or cell<=flag<cell+8):return None
    raiser=rel(null,3);throw=il.addr_candidates.get(rel(obj,4),())
    if (lift._named_raise_throw(raiser,lift._call_name(raiser))!='System.NullReferenceException' or len(throw)!=1 or throw[0][0]!='method' or
            not 0<=throw[0][1]<len(il.meta.methods)):return None
    t=il.meta.methods[throw[0][1]]
    if (t.addr!=rel(obj,4) or il.typedef_full(t.declaring)!='UnityEngine.Bindings.ThrowHelper' or t.name!='ThrowArgumentNullException' or not t.is_static or
            t.generic_container!=-1 or t.param_count!=2 or params(t)!=[(0x1c,0),(0x0e,0)] or not 0<=t.return_type<len(il.types) or key(il.types[t.return_type])!=(1,0)):return None
    f=(il.instance_field_chain(owner) or {}).get(int.from_bytes(obj[2],'little',signed=True))
    if not f or f[0]!='m_CachedPtr' or not 0<=f[1]<len(il.types) or key(il.types[f[1]])!=(0x18,0):return None
    sig=f'{il.typedef_full(owner)}::{helper.name}_Injected(System.IntPtr,System.Single)'
    if il.icall_cells.get(rel(tail,1))!=sig or il.bin.cstr(rel(tail,2),512)!=sig:return None
    j=(il._icall_annotation(sig) or {}).get('method',-1)
    if not 0<=j<len(il.meta.methods):return None
    inj=il.meta.methods[j]
    if (inj.declaring==owner and inj.name==helper.name+'_Injected' and inj.iflags&0x1000 and inj.is_static and inj.generic_container==-1 and
            inj.param_count==2 and params(inj)==[(0x18,0),single] and 0<=inj.return_type<len(il.types) and key(il.types[inj.return_type])==(1,0)):return owner,member[1]


def float_setters(lift,method,blocks,pads):
    actions={};il=lift.il
    if not HAVE_ICED or pads or method.is_static or not _amd64(getattr(il,'bin',None)):return actions
    sites=[b for b in blocks if len(b.preds)==1 and len(b.insns)>=4 and b.insns[0].mnemonic==M.XOR and
           b.insns[1].mnemonic==M.MOVAPS and b.insns[1].op1_register==R.XMM0 and b.insns[1].op0_register==R.XMM1]
    if not sites:return actions
    seq=[i for b in blocks for i in b.insns];graph=_graph(il,seq,allow_tail=True,chained=True,runtime_tails=lift.rt_wbarrier)
    if not graph:return actions
    pred,_=graph;byip={i.ip:i for i in seq};td=il.meta.typedefs[method.declaring];key=il._closed_type_key
    for b in sites:
        left=blocks[b.preds[0]].insns
        if len(left)<7:continue
        hi,zero,lo,field,prod,test,null=left[-7:];s=b.insns;hidden,_,receiver=s[:3];j=3
        if s[j].mnemonic==M.ADD and s[j].op0_register==R.RSP:
            if len(s)!=6 or s[j+1].mnemonic!=M.POP or s[j+1].op0_register!=field.op0_register or s[-1].mnemonic!=M.JMP:continue
            # Tail form: verify an exact reversal of the whole frame.
            from il2cpp.async_start import _adjust
            pro=blocks[0].insns[:2];size=_adjust(s[j],M.ADD)
            if (not size or size<32 or size%16 or len(pro)!=2 or pro[0].mnemonic!=M.PUSH or pro[0].op0_register!=field.op0_register or _adjust(pro[1],M.SUB)!=size or
                    len(left)!=9 or b.preds!=[0] or key(il.types[method.return_type])!=(1,0)):continue
            j+=2
        elif s[j].mnemonic!=M.CALL:continue
        call=s[j];w=left[-7:]+s[:j+1]
        if (any(i.has_segment_prefix or i.has_lock_prefix or i.memory_index!=R.NONE for i in w) or
                any(x.next_ip!=y.ip or pred[y.ip]!=[x.ip] for x,y in zip(w,w[1:]))):continue
        if (any(i.mnemonic!=M.XOR or i.op0_register!=i.op1_register or i.op0_register!=R.R8D for i in (zero,hidden)) or
                prod.mnemonic!=M.CALL or prod.op0_kind!=K.NEAR_BRANCH64 or call.op0_kind!=K.NEAR_BRANCH64 or method.addr==call.near_branch_target or
                field.mnemonic!=M.MOV or field.op1_kind!=K.MEMORY or field.op0_register not in _SAVED or test.mnemonic!=M.TEST or
                test.op0_register!=test.op1_register or test.op0_register!=field.op0_register or null.mnemonic!=M.JE or not _raises_on_null(lift,null) or
                receiver.mnemonic!=M.MOV or receiver.op0_register!=R.RCX or receiver.op1_register!=field.op0_register):continue
        rows=[_own_field(il,td,sdisp(i.memory_displacement),size) for i,size in ((hi,4),(lo,4),(field,8))]
        if any(not row for row in rows) or any(not _receiver(il,method,byip,pred,i.ip,td.index,initial=i.memory_base,this_only=True) for i in (hi,lo,field)):continue
        if (any(i.mnemonic!=M.MOVSS or i.op0_register!=r or i.op1_kind!=K.MEMORY or key(row[1])!=(0x0c,0) for i,r,row in ((hi,R.XMM1,rows[0]),(lo,R.XMM0,rows[1]))) or
                key(rows[2][1])!=(0x12,rows[2][1][0],0)):continue
        ids=il.addr_candidates.get(prod.near_branch_target,())
        if len(ids)!=1 or ids[0][0]!='method' or not 0<=ids[0][1]<len(il.meta.methods):continue
        p=il.meta.methods[ids[0][1]];ps=il.meta.method_params(p)
        if (p.addr!=prod.near_branch_target or not p.is_static or p.flags&7!=6 or p.flags&(0x40|0x800) or p.generic_container!=-1 or
                p.param_count!=2 or len(ps)!=2 or not all(0<=a.type<len(il.types) and key(il.types[a.type])==(0x0c,0) for a in ps) or
                not 0<=p.return_type<len(il.types) or key(il.types[p.return_type])!=(0x0c,0) or safe_ident(p.name)!=p.name or
                not 0<=p.declaring<len(il.meta.typedefs) or il.meta.typedefs[p.declaring].generic_container!=-1 or il.meta.typedefs[p.declaring].flags&7!=1):continue
        alias=_alias(lift,call.near_branch_target)
        if not alias or key(rows[2][1])!=(0x12,alias[0],0):continue
        for i,row,kind in ((hi,rows[0],'float'),(lo,rows[1],'float'),(field,rows[2],'obj')):
            actions[i.ip]=('field_value',row,reg_name(i.op0_register),kind)
        actions[prod.ip]=('make_float',il.typedef_full(p.declaring)+'.'+p.name,il.types[p.return_type],lo.ip,hi.ip)
        actions[call.ip]=('set_float',field.ip,prod.ip,alias[1],call.mnemonic==M.JMP)
    return actions
