"""Signed Int32 CDQ/IDIV: keep the fault at the division and bind both lanes.

An Int32 result in EAX/EDX is *not* a sign-extended Int64. The leaf proof
below only admits dword observations. A 64-bit base/index in a 32-bit LEA
also contributes only its low dword; LEA does not read memory or flags.
"""
from il2cpp.equivalent_binary import _amd64
from il2cpp.names import safe_ident
from il2cpp.prelude import HAVE_ICED
from il2cpp.text import sdisp

if HAVE_ICED:
    from iced_x86 import Mnemonic as M, OpKind as K, Register as R, RegisterExt
    _DWORD={R.EAX,R.ECX,R.EDX,R.R8D,R.R9D,R.R10D,R.R11D}


def _quotient(n,d):
    # The divide must still execute when both destinations are dead. checked
    # also protects this RHS from being mistaken for a pure copy during DCE.
    return f'checked({n} / {d})'


def _remainder(n,d,q):return f'unchecked({n} - {q} * {d})'


def signed_div_leaf(lift,method,td,seq,eh):
    if (not HAVE_ICED or eh or not 4<=len(seq)<=20 or seq[-1].mnemonic!=M.RET or seq[-1].op_count or
            sum(i.mnemonic==M.IDIV for i in seq)!=1 or method.param_count!=2):return None
    il=lift.il
    if (not _amd64(getattr(il,'bin',None)) or il.meta.version!=31 or method.addr!=seq[0].ip or
            method.generic_container!=-1 or td.generic_container!=-1 or ('method',method.index) not in il.addr_candidates.get(method.addr,()) or
            not 0<=method.return_type<len(il.types) or il._closed_type_key(il.types[method.return_type])!=(8,0) or
            any(i.has_segment_prefix or i.has_lock_prefix or i.is_invalid for i in seq) or
            any(a.next_ip!=b.ip or b.ip in il.addr_candidates for a,b in zip(seq,seq[1:]))):return None
    ps=il.meta.method_params(method)
    if len(ps)!=2 or any(not 0<=p.type<len(il.types) or il._closed_type_key(il.types[p.type])!=(8,0) for p in ps):return None
    names=[safe_ident(p.name) for p in ps];taken=set(names)
    if len(taken)!=2 or not all(n.isidentifier() for n in names):return None
    # Do not assign an Int32 to the instance receiver's slot. A leaf may
    # later overwrite ECX as scratch, but cannot use its incoming pointer.
    regs=dict(zip((R.ECX,R.EDX) if method.is_static else (R.EDX,R.R8D),names));lines=[];test=None;high=None
    def bind(r,expr):
        n=len(lines)+1
        while (v:='part'+str(n)) in taken:n+=1
        taken.add(v);lines.append(f'int {v} = {expr};');regs[r]=v;return v
    for j,i in enumerate(seq[:-1]):
        op=i.mnemonic;r=i.op0_register;s=i.op1_register;old=regs.get(r);src=regs.get(s)
        if op==M.CDQ:
            if high is not None or seq[j+1].mnemonic!=M.IDIV:return None
            high=regs.get(R.EAX);regs.pop(R.EDX,None);continue
        if op==M.IDIV:
            if not high or not j or seq[j-1].mnemonic!=M.CDQ or i.op0_kind!=K.REGISTER or not old or r not in _DWORD:return None
            q=bind(R.EAX,_quotient(high,old));bind(R.EDX,_remainder(high,old,q));high=test=None;continue
        if r not in _DWORD:return None
        if op==M.MOV and i.op1_kind==K.REGISTER and src:regs[r]=src
        elif op==M.MOV and i.op1_kind==K.IMMEDIATE32:
            bind(r,str(i.immediate32 if i.immediate32<1<<31 else i.immediate32-(1<<32)))
        elif op in (M.ADD,M.SUB) and old and src:
            bind(r,f'unchecked({old} {"+" if op==M.ADD else "-"} {src})');test=None
        elif op in (M.INC,M.DEC) and old:
            bind(r,f'unchecked({old} {"+" if op==M.INC else "-"} 1)');test=None
        elif op==M.LEA and i.op1_kind==K.MEMORY and i.memory_index_scale==1:
            terms=[]
            for rr in (i.memory_base,i.memory_index):
                if rr==R.NONE:continue
                k=next((k for k in regs if RegisterExt.full_register(k)==rr),None)
                if k is None:return None
                terms.append(regs[k])
            disp=sdisp(i.memory_displacement)
            if not terms or not -(1<<31)<=disp<(1<<31):return None
            expr=' + '.join(terms)
            if disp:expr+=f' {"+" if disp>0 else "-"} {abs(disp)}' if disp!=-(1<<31) else ' + int.MinValue'
            bind(r,'unchecked('+expr+')')
        elif op==M.TEST and r==s and old:test=old
        elif op in (M.CMOVS,M.CMOVNE) and test and old and src:
            bind(r,f'{test} {"<" if op==M.CMOVS else "!="} 0 ? {src} : {old}')
        else:return None
    if R.EAX not in regs:return None
    return lines+['return '+regs[R.EAX]+';']
