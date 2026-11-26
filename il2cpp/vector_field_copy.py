"""A Win64 reference-type getter returning a complete vector field by hidden sret.

The same getter may legally spell a foreign private-field read when an inlined
8+4 copy is followed by a whole-field write and both scratch lanes are dead.
"""
import re

from il2cpp.awaiter import _unused_return
from il2cpp.binary import PE
from il2cpp.csharp import FA_INITONLY
from il2cpp.expr import acc_get
from il2cpp.prelude import HAVE_ICED
from il2cpp.sret_copy import _own_field

if HAVE_ICED:
    from iced_x86 import Mnemonic as M, OpKind as K, Register as R


_LEAF = re.compile(rb'\x8b\x82(.{4})\xf2\x0f\x10\x82(.{4})\xf2\x0f\x11\x01\x89\x41\x08\x48\x8b\xc1\xc3',re.S)


def vector_field_getter(lift, m):
    il = lift.il
    if (not m.name.startswith('get_') or m.param_count or m.is_static or m.flags&0x40 or
            m.flags&7 != 6 or m.generic_container != -1 or not isinstance(getattr(il,'bin',None),PE) or
            not il.bin.is64 or not 0<=m.return_type<len(il.types)):
        return None
    rt = il.types[m.return_type]
    if not rt or il._closed_type_key(rt)!=(0x11,rt[0],0) or il.type_name(rt)!='UnityEngine.Vector3': return None
    td = il.meta.typedefs[m.declaring]; prop = lift._accessor_prop(m.index)
    if (td.is_valuetype or td.generic_container!=-1 or not prop or prop[0]!='get' or prop[2]!=0 or
            not il.returns_sret(rt) or il.value_type_size(rt[0])!=12 or not il.bin.is_exec_va(m.addr)):
        return None
    code = _LEAF.fullmatch(il.bin.read(m.addr,25) or b'')
    if not code: return None
    z,xy = (int.from_bytes(d,'little',signed=True) for d in code.groups())
    if z!=xy+8: return None
    row = _own_field(il,td,xy,12)
    if row and il._closed_type_key(row[1])==il._closed_type_key(rt):
        return row[0], prop[1], xy


def copy_via_getter(lift, block):
    il = lift.il; seq = block.insns
    if len(seq)!=4 or not isinstance(getattr(il,'bin',None),PE) or not il.bin.is64 or len(block.preds)!=1:
        return False
    xy,z,lo,hi=seq
    if (xy.mnemonic!=M.MOVSD or xy.op0_register!=R.XMM0 or xy.memory_base!=R.RCX or
            z.mnemonic!=M.MOV or z.op0_register!=R.EAX or z.memory_base!=R.RAX or
            lo.mnemonic!=M.MOVSD or lo.memory_base!=R.RBX or lo.op1_register!=R.XMM0 or
            hi.mnemonic!=M.MOV or hi.memory_base!=R.RBX or hi.op1_register!=R.EAX or
            xy.memory_displacement+8!=z.memory_displacement or lo.memory_displacement+8!=hi.memory_displacement or
            any(i.has_segment_prefix or i.memory_index!=R.NONE for i in seq) or
            any(a.next_ip!=b.ip for a,b in zip(seq,seq[1:]))): return False
    m=lift._current_method; rt=il.types[m.return_type] if 0<=m.return_type<len(il.types) else None
    if m.is_static or il._closed_type_key(rt)!=(1,0): return False
    base=dict.get(lift.regs,'RBX'); rcx=dict.get(lift.regs,'RCX'); rax=dict.get(lift.regs,'RAX')
    if (not base or base.text!='this' or il._closed_type_key(base.ty)!=(0x12,m.declaring,0) or
            not rcx or not rax or rcx.text!=rax.text or not re.fullmatch(r't\d+',rcx.text) or
            not rcx.ty or il._closed_type_key(rcx.ty)!=(0x12,rcx.ty[0],0) or rcx.ty!=rax.ty): return False
    dst=_own_field(il,il.meta.typedefs[m.declaring],lo.memory_displacement,12)
    if not dst or dst[1][1]&FA_INITONLY or il.type_name(dst[1])!='UnityEngine.Vector3': return False
    td=il.meta.typedefs[rcx.ty[0]]; offset=xy.memory_displacement
    cache=il.__dict__.setdefault('_public_vector_copy_getters',{})
    key=td.index,offset
    if key not in cache:
        hits=[g[1] for j in il.meta.type_methods(td) if (g:=vector_field_getter(lift,il.meta.methods[j])) and g[2]==offset]
        cache[key]=hits[0] if len(hits)==1 else None
    if not cache[key] or not _unused_return(lift,hi.next_ip): return False
    lift._kill_stale(dst[0]); lift.emit(lo.ip, '%s = %s;'%(dst[0],acc_get(rcx.text+'.'+cache[key])),None)
    for reg in ('RAX','XMM0'): lift.regs.pop(reg,None)
    return True
