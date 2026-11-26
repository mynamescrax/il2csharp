"""Win64 leaf projections: two indexed dwords from an unboxed struct are
interleaved by UNPCKLPS and returned, without numeric conversion, in RAX."""
from il2cpp.csharp import FA_INITONLY
from il2cpp.equivalent_binary import _amd64
from il2cpp.names import safe_ident
from il2cpp.prelude import HAVE_ICED
from il2cpp.sret_copy import _own_field
from il2cpp.text import sdisp

if HAVE_ICED:
    from iced_x86 import Mnemonic as M, OpKind as K, Register as R


def _field(il,td,off,write=False):
    row=_own_field(il,td,16+off,4)
    if row is None:return None
    name,ty=row;name=name.removeprefix('this.')
    if (not name.isidentifier() or safe_ident(name)!=name or ty[1]&7!=6 or write and ty[1]&FA_INITONLY or
            il._closed_type_key(ty)!=(0xc,0)):return None
    return name


def packed_projection(lift,m,td,seq,eh):
    if (not HAVE_ICED or eh or len(seq)!=5 or seq[-1].mnemonic!=M.RET or seq[-1].op_count or
            seq[-2].mnemonic!=M.MOVQ or seq[-2].op0_register!=R.RAX or seq[-3].mnemonic!=M.UNPCKLPS):return None
    il=lift.il;key=il._closed_type_key
    if (not _amd64(il.bin) or il.meta.version!=31 or m.addr!=seq[0].ip or ('method',m.index) not in il.addr_candidates.get(m.addr,()) or
            m.generic_container!=-1 or td.generic_container!=-1 or not 0<=m.return_type<len(il.types) or
            any(i.has_segment_prefix or i.has_lock_prefix or i.memory_index!=R.NONE for i in seq) or
            any(a.next_ip!=b.ip for a,b in zip(seq,seq[1:]))):return None
    rt=il.types[m.return_type]
    if not rt or key(rt)!=(0x11,rt[0],0) or not 0<=rt[0]<len(il.meta.typedefs) or il.value_type_size(rt[0])!=8 or il.returns_sret(rt):return None
    dst=il.meta.typedefs[rt[0]]
    if not dst.is_valuetype or dst.is_enum or dst.generic_container!=-1 or dst.declaring!=-1:return None
    if m.is_static:
        ps=il.meta.method_params(m)
        if m.param_count!=1 or len(ps)!=1 or not 0<=ps[0].type<len(il.types):return None
        pt=il.types[ps[0].type]
        if not pt or key(pt)!=(0x11,pt[0],0) or not 0<=pt[0]<len(il.meta.typedefs):return None
        src=il.meta.typedefs[pt[0]];obj=safe_ident(ps[0].name)
        # A value of these sizes is passed indirectly under the Win64 ABI.
        if il.value_type_size(src.index) not in (12,16) or not obj.isidentifier():return None
    else:
        if m.param_count or not td.is_valuetype:return None
        src,obj=td,'this'
    size=il.value_type_size(src.index)
    if not src.is_valuetype or src.is_enum or src.generic_container!=-1 or not size or size<4:return None
    # Only registers volatile across an x64 call may be used as scratch in
    # this frameless body. Track the actual low lanes, independent of names.
    defs={};loads=[]
    for i in seq[:2]:
        if not R.XMM0<=i.op0_register<=R.XMM5:return None
        if i.mnemonic==M.MOVSS and i.op1_kind==K.MEMORY and i.memory_base==R.RCX:
            off=sdisp(i.memory_displacement);field=_field(il,src,off)
            if not field or off<0 or off+4>size:return None
            defs[i.op0_register]=len(loads);loads.append(field)
        elif i.mnemonic==M.MOVAPS and i.op1_register in defs:
            defs[i.op0_register]=defs[i.op1_register]
        else:return None
    mix,ret=seq[2:4];lo=defs.get(mix.op0_register);hi=defs.get(mix.op1_register)
    if lo is None or hi is None or ret.op1_register!=mix.op0_register:return None
    fields=[_field(il,dst,off,True) for off in (0,4)]
    if None in fields or fields[0]==fields[1]:return None
    # Avoid calling even an explicit parameterless value-type constructor.
    # Do the loads in native order (and a repeated lane needs only one read).
    temps=['lane0','lane1'];out='projected'
    if obj in (*temps,out):return None
    return ([f'float {temp} = {obj}.{f};' for temp,f in zip(temps,loads)]+
            [f'global::{il.typedef_full(dst.index)} {out} = default;',f'{out}.{fields[0]} = {temps[lo]};',
             f'{out}.{fields[1]} = {temps[hi]};',f'return {out};'])
