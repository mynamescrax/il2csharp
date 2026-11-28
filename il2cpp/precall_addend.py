"""The low Single parked before a scalar poll is not a post-poll field read."""
from il2cpp.array_origin import _graph,_reachable
from il2cpp.closed_lookup import _receiver
from il2cpp.equivalent_binary import _amd64
from il2cpp.metadata import source_params
from il2cpp.names import safe_ident
from il2cpp.prelude import HAVE_ICED
from il2cpp.scalar_snapshot import _last,_property
from il2cpp.sret_copy import _own_field
from il2cpp.text import sdisp

if HAVE_ICED:
    from iced_x86 import Mnemonic as M, Register as R, OpKind as K, RegisterExt as RX, MemorySizeExt as MS
    from il2cpp.array_origin import _INFO


def _only_scalar(il,by,succ,load):
    """MOVSS from memory clears the upper XMM lanes. An ordinary float
    local is a sufficient representation only if those lanes stay dead."""
    todo=[(n,frozenset([load.op0_register])) for n in succ[load.ip]];seen=set()
    while todo:
        ip,live=todo.pop()
        if not live or (ip,live) in seen:continue
        if len(seen)>=256:return False
        seen.add((ip,live));i=by[ip];after=set(live)
        if i.mnemonic==M.MOVAPS and i.op1_kind==K.REGISTER and i.op1_register in live:
            if not RX.is_xmm(i.op0_register):return False  # includes a full-width spill
            after.add(i.op0_register)
        else:
            for reg in live:
                uses=[u for u in _INFO.info(i).used_registers() if RX.full_register(u.register)==RX.full_register(reg)]
                if not uses:continue
                if (i.op0_register==reg and i.op1_kind==K.MEMORY and i.mnemonic in (M.MOVSS,M.MOVAPS) or
                        i.mnemonic==M.MOVAPS and i.op0_register==reg and i.op1_register not in live):
                    after.discard(reg);continue
                if i.mnemonic in (M.COMISS,M.UCOMISS,M.ADDSS) or i.mnemonic==M.MOVSS and i.op0_kind==K.MEMORY:continue
                return False
        if i.is_call_near or i.is_jmp_short_or_near and i.near_branch_target not in by:
            ids=il.addr_candidates.get(i.near_branch_target,())
            if len(ids)!=1 or ids[0][0]!='method' or not 0<=ids[0][1]<len(il.meta.methods):return False
            md=il.meta.methods[ids[0][1]];args=il.meta.method_params(md)
            if md.addr!=i.near_branch_target or md.generic_container!=-1 or not 0<=md.return_type<len(il.types) or il.returns_sret(il.types[md.return_type]):return False
            for j,p in enumerate(args,int(not md.is_static)):
                if j<4 and R.XMM0+j in live and (not 0<=p.type<len(il.types) or il._closed_type_key(il.types[p.type])!=(12,0)):return False
            # Do not treat a volatile register as definitely overwritten.
            # Follow it until a full replacement or the end of this caller.
        todo.extend((n,frozenset(after)) for n in succ[ip])
    return True


def _scalar_call(lift,call,by,pred,entry):
    # A static Single getter, or a closed ordinary method with two literal
    # Single arguments. Nothing else can have a lazy effect in these slots.
    il=lift.il;prop=_property(lift,call,'get')
    if prop and prop[0].is_static:
        zero=_last(by,pred,call.ip,R.RCX,entry)
        if zero and zero!='this' and zero.mnemonic==M.XOR and zero.op0_register==zero.op1_register==R.ECX:return prop[0].index
        return None
    ids=il.addr_candidates.get(call.near_branch_target,())
    if len(ids)!=1 or ids[0][0]!='method' or not 0<=ids[0][1]<len(il.meta.methods):return None
    m=il.meta.methods[ids[0][1]];args=il.meta.method_params(m)
    if (m.addr!=call.near_branch_target or not m.is_static or m.flags&7!=6 or m.flags&(0x800|0x40) or
            m.generic_container!=-1 or len(args)!=2 or m.param_count!=2 or not 0<=m.return_type<len(il.types) or
            il._closed_type_key(il.types[m.return_type])!=(12,0) or any(not 0<=p.type<len(il.types) or il._closed_type_key(il.types[p.type])!=(12,0) for p in args)):return None
    for r in (R.XMM0,R.XMM1):
        i=_last(by,pred,call.ip,r,entry)
        if not i or i=='this' or i.mnemonic!=M.MOVSS or i.op0_register!=r or i.op1_kind!=K.MEMORY or i.memory_base!=R.RIP or i.has_segment_prefix:return None
        p=i.ip_rel_memory_address
        if not any(s.addr<=p<=s.addr+min(s.rawsize,s.size)-4 and not s.chars&0x80000000 for s in il.bin.sections):return None
    z=_last(by,pred,call.ip,R.R8,entry)
    return m.index if z and z!='this' and z.mnemonic==M.XOR and z.op0_register==z.op1_register==R.R8D else None


def addend_sites(lift,m,td,blocks,pads):
    il=lift.il;fields={};calls={}
    if not HAVE_ICED or pads or m.is_static or m.generic_container!=-1 or td.is_valuetype or td.generic_container!=-1:return fields,calls
    hits=[(call,use) for b in blocks for call,use in zip(b.insns,b.insns[1:]) if call.is_call_near and use.mnemonic==M.ADDSS and
          use.op0_register==R.XMM0 and use.op1_kind==K.REGISTER and R.XMM6<=use.op1_register<=R.XMM15]
    if (not hits or not _amd64(getattr(il,'bin',None)) or il.meta.version!=31 or not 0<=m.return_type<len(il.types) or il._closed_type_key(il.types[m.return_type])!=(1,0) or
            any(n.startswith('t') and n[1:].isdigit() for n in (safe_ident(p.name) for p in source_params(il.meta,m)))):return fields,calls
    seq=[i for b in blocks for i in b.insns];g=_graph(il,seq,allow_tail=True,chained=True,nested_chains=True);by={i.ip:i for i in seq}
    if not g or seq[0].ip!=m.addr:return fields,calls
    pred,succ=g
    for call,use in hits:
        if pred[use.ip]!=[call.ip] or call.next_ip!=use.ip:continue
        mi=_scalar_call(lift,call,by,pred,m.addr)
        if mi is None:continue
        reg=use.op1_register;i=_last(by,pred,call.ip,reg,m.addr)
        if i and i!='this' and i.mnemonic==M.MOVAPS and i.op0_register==reg and RX.is_xmm(i.op1_register):
            reg=i.op1_register;i=_last(by,pred,i.ip,reg,m.addr)
        if (not i or i=='this' or i.mnemonic!=M.MOVSS or i.op0_register!=reg or i.op1_kind!=K.MEMORY or
                i.memory_index!=R.NONE or i.has_segment_prefix or i.has_lock_prefix or MS.size(i.memory_size)!=4 or
                not _receiver(il,m,by,pred,i.ip,td.index,initial=i.memory_base,this_only=True)):continue
        f=_own_field(il,td,sdisp(i.memory_displacement),4)
        if not f or il._closed_type_key(f[1])!=(12,0):continue
        p=call.ip
        while p!=i.ip and len(pred[p])==1:
            p=pred[p][0]
            if by[p].is_call_near or p<=i.ip:break
        if p!=i.ip or not _only_scalar(il,by,succ,i):continue
        # Do not hoist this read past a lazy producer from an unrelated
        # earlier expression. Every preceding call must already execute for
        # effect (a registered void method) or feed its own TEST/Jcc guard.
        prior=_reachable(pred,pred[i.ip]);safe=True
        for ip in prior:
            p=by[ip]
            if not p.is_call_near or p.near_branch_target==lift.rt_init_meta:continue
            ids=il.addr_candidates.get(p.near_branch_target,())
            if ids and all(k=='method' and 0<=n<len(il.meta.methods) and il.meta.methods[n].addr==p.near_branch_target and
                           0<=il.meta.methods[n].return_type<len(il.types) and il._closed_type_key(il.types[il.meta.methods[n].return_type])==(1,0) for k,n in ids):continue
            t=by.get(p.next_ip);j=by.get(t.next_ip) if t else None
            if (not t or not j or t.mnemonic!=M.TEST or t.op0_register!=t.op1_register or t.op0_register!=R.AL or
                    j.mnemonic not in (M.JE,M.JNE) or pred[t.ip]!=[ip] or pred[j.ip]!=[t.ip] or not ids or
                    len(succ[j.ip])!=2 or sum(i.ip in _reachable(succ,[n]) for n in succ[j.ip])!=1 or
                    not all(k=='method' and 0<=n<len(il.meta.methods) and il.meta.methods[n].addr==p.near_branch_target and
                            0<=il.meta.methods[n].return_type<len(il.types) and il._closed_type_key(il.types[il.meta.methods[n].return_type])==(2,0) for k,n in ids)):
                safe=False;break
        if not safe:continue
        fields[i.ip]=f;calls[call.ip]=mi
    return fields,calls
