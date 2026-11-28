"""Bounded reads of managed ref-to-reference parameters.

A GPR saved from the incoming ref is an address *of a variable*, not the
old object or that object's klass. Certify the uses of that address over
all paths; only bind a load where every reaching state has that address.
"""
from il2cpp.array_origin import _graph,_definitions
from il2cpp.closed_lookup import spec_lookup
from il2cpp.equivalent_binary import _amd64
from il2cpp.expr import Expr,acc_get
from il2cpp.gc_mark import mark_only
from il2cpp.metadata import source_params
from il2cpp.names import safe_ident
from il2cpp.prelude import HAVE_ICED
from il2cpp.text import reg_name

if HAVE_ICED:
    from iced_x86 import Mnemonic as M,Register as R,RegisterExt as RX,OpKind as K,MemorySizeExt as MS,OpAccess as A
    from il2cpp.array_origin import _INFO,_WRITES
    _ARG=(R.RCX,R.RDX,R.R8,R.R9)


def _inputs(l,i,by,pred,entry):
    """Exact implicit inputs and whether a managed result overwrites RAX."""
    il=l.il;va=i.near_branch_target
    if va==l.rt_init_meta or il.bin.exports.get(va)=='il2cpp_runtime_class_init':return {R.RCX},False
    # _named_raise_throw certifies a zero-argument nonreturning thunk.
    if l._named_raise_throw(va,l._call_name(va)):return set(),False
    ids=il.addr_candidates.get(va,())
    if len(ids)==1 and ids[0][0]=='method' and 0<=ids[0][1]<len(il.meta.methods):
        f=il.meta.methods[ids[0][1]]
        if (f.addr==va and f.generic_container==-1 and 0<=f.return_type<len(il.types) and f.param_count>=0):
            ty=il.types[f.return_type];key=il._closed_type_key(ty);nr=f.param_count+int(not f.is_static)+1+int(il.returns_sret(ty))
            return set(_ARG[:nr]),key and not key[-1] and key[0] in (0x12,0x1c,0x0e,0x1d,8,9,10,11)
    if not i.is_call_near:return None
    defs=_definitions(by,pred,entry,i.ip,R.RDX)
    if len(defs)==1:
        p,reg=defs.pop()
        if reg==R.RDX and spec_lookup(il,by[p],i):return {R.RCX,R.RDX},True


def bounded_cell(l,m,s,g,input_reg):
    """None for a possible escape; otherwise the exact full loads/stores.
    Passing the address to the verified GC card mark is an address-only
    use. Passing it to an unknown call, storing it, or offsetting it is not.
    """
    by={i.ip:i for i in s};pred,succ=g;todo=[(m.addr,frozenset([input_reg]),False)];seen=set();evidence={};calls={};marks=set();writes=set()
    while todo:
        ip,live,assigned=todo.pop()
        if (ip,live,assigned) in seen:continue
        if len(seen)>2048:return None
        seen.add((ip,live,assigned));i=by[ip];after=set(live)
        load=False
        if i.is_call_near or i.is_jmp_short_or_near and i.near_branch_target not in by:
            if i.ip not in calls:
                calls[ip]=_inputs(l,i,by,pred,m.addr)
                if i.near_branch_target in l.rt_wbarrier and mark_only(l.il,i.near_branch_target):marks.add(ip)
            if ip not in marks:
                q=calls[ip]
                if not q or q[0]&live:return None
                if q[1]:after.discard(R.RAX)
            # Do not assume a void routine killed a volatile pointer.
        elif i.mnemonic==M.RET:
            if R.RAX in live:return None
        elif i.mnemonic==M.MOV and i.op1_kind==K.REGISTER and RX.full_register(i.op1_register) in live:
            if (not RX.is_gpr64(i.op1_register) or not RX.is_gpr64(i.op0_register) or i.op0_register==R.RSP):return None
            after.add(i.op0_register)
        elif i.memory_base in live or i.memory_index in live:
            if (i.mnemonic!=M.MOV or i.memory_base not in live or i.memory_index!=R.NONE or i.memory_displacement or
                    i.has_segment_prefix or i.has_lock_prefix or MS.size(i.memory_size)!=8):return None
            if i.op1_kind==K.MEMORY and RX.is_gpr64(i.op0_register) and i.op0_register!=R.RSP:load=True;after.discard(i.op0_register)
            elif i.op0_kind==K.MEMORY and RX.is_gpr64(i.op1_register) and i.op1_register not in live:writes.add(ip);assigned=True
            else:return None
        else:
            for u in _INFO.info(i).used_registers():
                r=RX.full_register(u.register)
                if r not in live:continue
                if u.access!=A.WRITE or RX.size(u.register)<4:return None
                after.discard(r)
        if load and not assigned:return None
        evidence.setdefault(ip,set()).add(load)
        todo.extend((n,frozenset(after),assigned) for n in succ[ip])
    return {p for p,states in evidence.items() if states=={True}},writes


def ref_loads(l,m,td,blocks,pads):
    out={};il=l.il
    if (not HAVE_ICED or pads or m.param_count<1 or m.generic_container!=-1 or td.generic_container!=-1 or
            not _amd64(getattr(il,'bin',None)) or il.meta.version!=31 or not 0<=m.return_type<len(il.types)):return out
    ps=source_params(il.meta,m);base=int(not m.is_static)+int(il.returns_sret(il.types[m.return_type]));targets=[]
    for k,p in enumerate(ps,base):
        if k>=4 or not 0<=p.type<len(il.types):continue
        t=il.types[p.type]
        if not t or not t[1]&(1<<29):continue
        ty=(t[0],t[1]&~(1<<29));key=il._closed_type_key(ty)
        if key==(0x12,ty[0],0) and 0<=ty[0]<len(il.meta.typedefs) and il.meta.typedefs[ty[0]].generic_container==-1:targets.append((_ARG[k],safe_ident(p.name),ty))
    if (not targets or any(n.startswith('t') and n[1:].isdigit() for n in (safe_ident(p.name) for p in ps))):return out
    s=[i for b in blocks for i in b.insns];g=_graph(il,s,allow_tail=True,chained=True,nested_chains=True,runtime_tails=l.rt_wbarrier)
    if not g or s[0].ip!=m.addr:return out
    for reg,name,pointee in targets:
        fact=bounded_cell(l,m,s,g,reg)
        if not fact or not fact[1]:continue
        for ip in fact[0]:out[ip]=name,pointee
    return out


def read_cell(l,i,row):
    name,ty=row;n=l.new_var();l._var_types[n]=l._type_hints[n]=ty
    l.emit(i.ip,f'var {n} = {acc_get(name)};',None);l.set_reg(reg_name(i.op0_register),Expr(n,ty,'obj'))
