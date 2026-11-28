"""Signed MOVD / CVTDQ2PS operands of a scalar quotient and comparison.

The high three dwords of both converted registers are positive zero. Only
use a scalar display when no later instruction observes those high lanes.
"""
from il2cpp.array_origin import _graph, _definitions, _reachable
from il2cpp.closed_lookup import _receiver
from il2cpp.equivalent_binary import _amd64
from il2cpp.expr import Expr, acc_get, _INT_TY, _R4_TY
from il2cpp.metadata import source_params
from il2cpp.names import safe_ident
from il2cpp.prelude import HAVE_ICED
from il2cpp.sret_copy import _own_field
from il2cpp.text import reg_name,sdisp

if HAVE_ICED:
    from iced_x86 import Mnemonic as M,OpKind as K,Register as R,RegisterExt as RX,OpAccess as A
    from il2cpp.array_origin import _INFO


def _low_only(lift,by,succ,site,regs):
    # Do not silently expose the scalar rendering in a packed store, even
    # if a later overwrite would make the final float look right again.
    todo=[(n,frozenset(regs)) for n in succ[site]];seen=set()
    while todo:
        ip,live=todo.pop()
        if not live or (ip,live) in seen:continue
        if len(seen)>256:return False
        seen.add((ip,live));i=by[ip];left=set(live)
        for r in live:
            uses=[u for u in _INFO.info(i).used_registers() if RX.full_register(u.register)==RX.full_register(r)]
            if not uses:continue
            if (len(uses)==1 and uses[0].access==A.WRITE and i.op0_register==r and
                    i.mnemonic in (M.MOVD,M.MOVQ,M.MOVUPS,M.MOVAPS,M.MOVDQA,M.MOVDQU)):
                left.discard(r);continue
            if (i.mnemonic in (M.COMISS,M.UCOMISS) and i.op0_register==r or
                i.mnemonic in (M.COMISS,M.UCOMISS) and i.op1_register==r):continue
            return False
        if i.is_call_near or i.is_jmp_short_or_near and i.near_branch_target not in by:
            if lift._named_raise_throw(i.near_branch_target,lift._call_name(i.near_branch_target))=='System.NullReferenceException':continue
            if i.is_call_near:return False
            ids=lift.il.addr_candidates.get(i.near_branch_target,())
            if len(ids)!=1 or ids[0][0]!='method' or not 0<=ids[0][1]<len(lift.meta.methods):return False
            m=lift.meta.methods[ids[0][1]];il=lift.il
            if m.addr!=i.near_branch_target or m.generic_container!=-1 or m.is_static or m.param_count!=1 or il._closed_type_key(il.types[m.return_type])!=(1,0):return False
            ps=il.meta.method_params(m)
            if len(ps)!=1 or il._closed_type_key(il.types[ps[0].type])!=(12,0):return False
            if R.XMM1 in left:return False  # do not silently print a packed source as this argument
            # Incoming XMM0/2/3 etc are not arguments to this one-float
            # instance call. Do not treat volatile as a definite overwrite:
            # follow its continuations with the original live set.
        if not succ[ip] and not (i.mnemonic in (M.RET,M.INT3,M.UD2) or i.is_jmp_short_or_near):return False
        todo.extend((n,frozenset(left)) for n in succ[ip])
    return True


def ratio_sites(lift,method,td,blocks,pads):
    actions={};calls={};il=lift.il
    if not HAVE_ICED or pads or method.is_static or td.is_valuetype or td.generic_container!=-1:return actions,calls
    wins=[]
    for b in blocks:
        for j,i in enumerate(b.insns[:-1]):
            if (i.mnemonic!=M.DIVSS or i.op1_kind!=K.REGISTER or i.op0_register==i.op1_register or
                    b.insns[j+1].mnemonic not in (M.COMISS,M.UCOMISS)):continue
            regs=(i.op0_register,i.op1_register)
            if i.op0_register not in (b.insns[j+1].op0_register,b.insns[j+1].op1_register):continue
            if any(not R.XMM0<=r<=R.XMM5 for r in regs):continue
            def sources(r):
                uses=[k for k in range(max(0,j-12),j) if any(RX.full_register(u.register)==RX.full_register(r) for u in _INFO.info(b.insns[k]).used_registers())]
                if len(uses)<2:return None
                load,cvt=(b.insns[k] for k in uses[-2:])
                if (load.mnemonic==M.MOVD and load.op0_register==r and cvt.mnemonic==M.CVTDQ2PS and
                        cvt.op0_register==cvt.op1_register==r):return load,cvt
            a,c=sources(regs[0]),sources(regs[1]);
            if a and c:wins.append((b,i,a,c))
    if (not wins or not _amd64(getattr(il,'bin',None)) or il.meta.version!=31 or method.generic_container!=-1 or
            il._closed_type_key(il.types[method.return_type])!=(1,0) or
            any(n.startswith('t') and n[1:].isdigit() for n in (safe_ident(p.name) for p in source_params(il.meta,method)))):return actions,calls
    seq=[i for b in blocks for i in b.insns];by={i.ip:i for i in seq};g=_graph(il,seq,chained=True,nested_chains=True,allow_tail=True)
    if not g or seq[0].ip!=method.addr:return actions,calls
    pred,succ=g
    for b,div,a,c in wins:
        regs=(div.op0_register,div.op1_register)
        w=[i for i in b.insns if min(a[0].ip,c[0].ip)<=i.ip<=div.next_ip]
        if (any(i.is_call_near or i.has_lock_prefix or i.has_segment_prefix for i in w) or
                any(u.next_ip!=v.ip or pred[v.ip]!=[u.ip] for u,v in zip(w,w[1:])) or
                not _low_only(lift,by,succ,div.ip,regs)):continue
        reads={};producers={}
        # Do not move the field capture ahead of another lazy callback.
        # Every earlier ordinary poll has a closed scalar getter ABI and
        # is materialized at its actual producer, on its own path.
        prior = _reachable(pred,pred[w[0].ip])
        for ip in prior:
            call=by[ip]
            if not call.is_call_near or call.near_branch_target==lift.rt_init_meta:continue
            ids=il.addr_candidates.get(call.near_branch_target,())
            if len(ids)!=1 or ids[0][0]!='method' or not 0<=ids[0][1]<len(il.meta.methods):break
            m=il.meta.methods[ids[0][1]];prop=lift._accessor_prop(m.index)
            if (not prop or prop[0]!='get' or prop[2] or not m.is_static or m.param_count or m.generic_container!=-1 or
                    m.addr!=call.near_branch_target or not 0<=m.return_type<len(il.types) or il._closed_type_key(il.types[m.return_type])!=(8,0)):
                break
            producers[ip]=m.index
        if any(by[ip].is_call_near and by[ip].near_branch_target!=lift.rt_init_meta and ip not in producers
               for ip in prior):continue
        for load,cvt in (a,c):
            src=None
            if (load.op1_kind==K.MEMORY and RX.is_gpr64(load.memory_base) and load.memory_index==R.NONE and
                    _receiver(il,method,by,pred,load.ip,td.index,initial=load.memory_base,this_only=True)):
                row=_own_field(il,td,sdisp(load.memory_displacement),4)
                if row and il._closed_type_key(row[1])==(8,0):src=('field',row[0])
            elif load.op1_kind==K.REGISTER and RX.is_gpr32(load.op1_register):
                defs=_definitions(by,pred,method.addr,load.ip,RX.full_register(load.op1_register))
                if len(defs)==1:
                    pos,reg=defs.pop();call=by[pos];ids=il.addr_candidates.get(call.near_branch_target,()) if call.is_call_near else ()
                    if (reg==R.RAX and len(ids)==1 and ids[0][0]=='method' and 0<=ids[0][1]<len(il.meta.methods)
                            and pos not in _reachable(succ,succ[pos])):
                        m=il.meta.methods[ids[0][1]]
                        if (m.addr==call.near_branch_target and m.generic_container==-1 and il._closed_type_key(il.types[m.return_type])==(8,0)):
                            producers[pos]=m.index;src=('return',(reg_name(load.op1_register),pos))
            if src is None:break
            reads[load.ip]=src;reads[cvt.ip]=('convert',load.ip)
        else:
            reads[div.ip]=('divide',(a[1].ip,c[1].ip))
            actions.update(reads);calls.update(producers)
    return actions,calls


def ratio_step(lift,i,action,values):
    dest=reg_name(i.op0_register);kind,arg=action
    if kind=='field':
        n=lift.new_var();lift._var_types[n]=_INT_TY;lift.emit(i.ip,f'var {n} = {acc_get(arg)};',None);v=Expr(n,_INT_TY,'int')
    elif kind=='return':
        reg,pos=arg;v=dict.get(lift.regs,reg);sample=lift._sample_call_values.get(pos)
        if (v is None or v._unk or lift.il._closed_type_key(v.ty)!=(8,0) or sample is None or
                v.text!=sample.text or not (v.text.startswith('t') and v.text[1:].isdigit())):return False
    elif kind=='convert':
        v=values.get(arg)
        if v is None or dict.get(lift.regs,dest) is not v:return False
        # No semantic replacement until *both* inputs reach the divide.
        values[i.ip]=v
        return False
    else:
        a,b=(values.get(k) for k in arg);src=reg_name(i.op1_register)
        if (a is None or b is None or dict.get(lift.regs,dest) is not a or dict.get(lift.regs,src) is not b):return False
        cvt='(float)('+b.text+')'
        lift.regs[src]=Expr(cvt,_R4_TY,'float')
        lift.regs[dest]=Expr('((float)('+a.text+') / '+cvt+')',_R4_TY,'float')
        return True
    values[i.ip]=v;lift.regs[dest]=v;return True
