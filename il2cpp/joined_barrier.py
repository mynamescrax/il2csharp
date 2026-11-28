"""Deduplicate a terminal GC mark only when every incoming arm already
performed the matching pointer-sized assignment to the same object field."""
import re
from il2cpp.array_origin import _graph
from il2cpp.closed_lookup import _receiver
from il2cpp.csharp import source_field_name
from il2cpp.equivalent_binary import _amd64
from il2cpp.metadata import source_params
from il2cpp.names import safe_ident
from il2cpp.prelude import HAVE_ICED
from il2cpp.shared_field import reference_field_at
from il2cpp.terminal_effect import _terminal_frame
from il2cpp.text import reg_name,sdisp

if HAVE_ICED:
    from iced_x86 import Decoder, Mnemonic as M, OpKind as K, Register as R,RegisterExt as RX,MemorySizeExt as MS


from il2cpp.gc_mark import mark_only


def joined_marks(lift,m,td,blocks,pads):
    ret={};calls={};writes={};il=lift.il
    if not HAVE_ICED or pads or m.is_static or td.is_valuetype or m.generic_container!=-1 or td.generic_container!=-1:return ret,calls,writes
    tails=[b for b in blocks if len(b.insns)>1 and b.insns[-1].is_jmp_short_or_near and b.insns[-1].near_branch_target in lift.rt_wbarrier and b.insns[0].mnemonic==M.LEA]
    if (not tails or not _amd64(getattr(il,'bin',None)) or il.meta.version!=31 or not 0<=m.return_type<len(il.types) or il._closed_type_key(il.types[m.return_type])!=(1,0) or
            any(n.startswith('t') and n[1:].isdigit() for n in (safe_ident(p.name) for p in source_params(il.meta,m)))):return ret,calls,writes
    seq=[i for b in blocks for i in b.insns];by={i.ip:i for i in seq};g=_graph(il,seq,chained=True,nested_chains=True,allow_tail=True,runtime_tails=lift.rt_wbarrier)
    if not g or not seq or seq[0].ip!=m.addr:return ret,calls,writes
    pred,succ=g;ordered={i.ip:k for k,i in enumerate(seq)}
    for b in tails:
        s=b.insns;addr=s[0];jump=s[-1]
        if (not mark_only(il,jump.near_branch_target) or addr.op0_register!=R.RCX or addr.memory_index!=R.NONE or addr.has_segment_prefix or
                not _terminal_frame(il,seq,by,pred,addr.ip,b,0) or not _receiver(il,m,by,pred,addr.ip,td.index,initial=addr.memory_base,this_only=True)):continue
        row=reference_field_at(il,td.index,sdisp(addr.memory_displacement));paths=pred[addr.ip]
        if not row or row[0]!=td.index or len(paths)!=2 or any(u.next_ip!=v.ip or pred[v.ip]!=[u.ip] for u,v in zip(s,s[1:])):continue
        field='this.'+safe_ident(source_field_name(il,row[1]));steps=[];qs={}
        for p in paths:
            i=by[p];k=ordered[p]
            if i.is_jmp_short_or_near:
                if k==0 or i.near_branch_target!=addr.ip or pred[p]!=[seq[k-1].ip]:break
                k-=1;i=seq[k]
            if i.mnemonic==M.MOV and i.op0_register==R.RDX and i.op1_register==R.RAX:
                if k<2 or pred[i.ip]!=[seq[k-1].ip]:break
                store=seq[k-1];src=R.RAX;producer=seq[k-2]
                ids=il.addr_candidates.get(producer.near_branch_target,()) if producer.is_call_near else ()
                if len(ids)!=1 or ids[0][0]!='method' or not 0<=ids[0][1]<len(il.meta.methods):break
                get=il.meta.methods[ids[0][1]];prop=lift._accessor_prop(get.index)
                if (not prop or prop[0]!='get' or prop[2] or get.addr!=producer.near_branch_target or get.param_count or get.generic_container!=-1 or
                        get.flags&0x40 or get.flags&7!=6 or not 0<=get.return_type<len(il.types) or
                        il._closed_type_key(il.types[get.return_type])!=il._closed_type_key(row[2]) or pred[store.ip]!=[producer.ip]):break
                qs[producer.ip]=get.index;origin=producer.ip
            else:
                store=i;src=R.RDX;origin=None
                if k==0:break
                zero=seq[k-1]
                if zero.mnemonic!=M.XOR or zero.op0_register!=zero.op1_register or zero.op0_register!=R.EDX or pred[store.ip]!=[zero.ip]:break
            if (store.mnemonic!=M.MOV or store.op1_register!=src or store.op0_kind!=K.MEMORY or MS.size(store.memory_size)!=8 or
                    store.memory_base!=addr.memory_base or store.memory_displacement!=addr.memory_displacement or store.memory_index!=R.NONE or
                    store.has_segment_prefix or store.has_lock_prefix or not _receiver(il,m,by,pred,store.ip,td.index,initial=store.memory_base,this_only=True)):break
            steps.append((store.ip,(field,origin,reg_name(src))))
        if len(steps)!=2 or len(qs)!=1:continue
        ret[jump.ip]=tuple(ip for ip,_ in steps);calls.update(qs);writes.update(steps)
    return ret,calls,writes


def store_witness(lift,plan):
    field,producer,reg=plan;v=dict.get(lift.regs,reg)
    if not v or v._unk:return False
    if producer is None:
        if v.text!='0':return False
        rhs='null'
    else:
        if lift._sample_call_values.get(producer) is not v:return False
        rhs=v.text
    return lift._last_stmt_text()==f'{field} = {rhs};'
