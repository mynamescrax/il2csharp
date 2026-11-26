"""A complete 8+4 byte struct-return copy before a reference getter."""
import re

from il2cpp.binary import PE
from il2cpp.csharp import FA_LITERAL, FA_STATIC, field_attrs
from il2cpp.prelude import HAVE_ICED
from il2cpp.shared_getter import getter_alias
from il2cpp.text import reg_name, sdisp

if HAVE_ICED:
    from iced_x86 import MemorySizeExt, Mnemonic as M, OpKind as K, Register as R


def _window(blocks, block, idx):
    # RAX echoes the sret buffer. Two register copies cover it exactly. The
    # dword scratch is then overwritten by the receiver; the XMM snapshot
    # is still physically present but has already contributed to the store.
    if idx < 3 or idx+5 != len(block.insns):
        return None
    producer, z, xy, lo, hi, reload, test, null = block.insns[idx-3:]
    if block.bid+1 >= len(blocks):
        return None
    use = blocks[block.bid+1]
    if len(use.insns) < 2 or use.preds != [block.bid] or use.bid not in block.succs:
        return None
    zero, getter = use.insns[:2]
    seq = block.insns[idx-3:] + [zero, getter]
    if any(a.next_ip != b.ip for a,b in zip(seq,seq[1:])) or any(i.has_segment_prefix for i in seq):
        return None
    def mem(i, n, base, width):
        return (i.op_kind(n) == K.MEMORY and i.memory_base == base and i.memory_index == R.NONE and
                MemorySizeExt.size(i.memory_size) == width)
    obj = lo.memory_base
    if (producer.mnemonic != M.CALL or producer.op0_kind != K.NEAR_BRANCH64 or
            z.mnemonic != M.MOV or z.op0_register != R.ECX or not mem(z,1,R.RAX,4) or z.memory_displacement != 8 or
            xy.mnemonic != M.MOVSD or xy.op0_register != R.XMM0 or not mem(xy,1,R.RAX,8) or xy.memory_displacement != 0 or
            obj not in (R.RBX,R.RDI,R.RSI,R.R12,R.R13,R.R14,R.R15) or
            lo.mnemonic != M.MOVSD or lo.op1_register != R.XMM0 or not mem(lo,0,obj,8) or
            hi.mnemonic != M.MOV or hi.op1_register != R.ECX or not mem(hi,0,obj,4) or
            hi.memory_displacement != lo.memory_displacement+8 or
            reload.mnemonic != M.MOV or reload.op0_register != R.RCX or not mem(reload,1,obj,8) or
            test.mnemonic != M.TEST or test.op0_register != R.RCX or test.op1_register != R.RCX or
            null.mnemonic != M.JE or null.op0_kind != K.NEAR_BRANCH64 or null.near_branch_target == zero.ip or
            zero.mnemonic != M.XOR or zero.op0_register != R.EDX or zero.op1_register != R.EDX or
            getter.mnemonic != M.CALL or getter.op0_kind != K.NEAR_BRANCH64):
        return None
    return producer, lo, reload, getter


def _own_field(il, td, off, size):
    """One whole instance field at off; don't fold partial/overlapping storage."""
    if td.flags & 0x18 == 0x10 or not 0 <= td.index < len(il.field_offsets):
        return None
    offsets = il.field_offsets[td.index]
    if not offsets or len(offsets) != td.field_count:
        return None
    found = None
    for pos, fi in zip(offsets, il.meta.type_fields(td)):
        f = il.meta.fields[fi]
        if not 0 <= f.type < len(il.types):
            return None
        if field_attrs(il,f) & (FA_LITERAL | FA_STATIC) or pos >= off + size:
            continue
        ty = il.types[f.type]
        width = il._sf_field_size(ty,0)
        if not width or width < 0 or pos < 0x10:
            return None
        if pos + width > off:
            if found or pos != off or width != size:
                return None
            row = (il.instance_field_chain(td.index) or {}).get(off)
            if not row or row[1] != f.type:
                return None
            found = 'this.' + row[0], ty
    return found


def copied_sret_before_getter(lift, block, idx):
    site = _window(lift._blocks, block, idx)
    if not site:
        return None
    il = lift.il
    if not isinstance(getattr(il,'bin',None), PE) or not il.bin.is64:
        return None
    producer, store, reload, getter = site
    base = dict.get(lift.regs, reg_name(store.memory_base))
    td = lift._current_td
    if (td.is_valuetype or lift._current_method.is_static or not base or base._unk or base.text != 'this' or
            il._closed_type_key(base.ty) != (0x12,td.index,0)):
        return None
    cands = il.addr_candidates.get(producer.near_branch_target, ())
    if len(cands) != 1 or cands[0][0] != 'method' or not 0 <= cands[0][1] < len(il.meta.methods):
        return None
    m = il.meta.methods[cands[0][1]]
    rt = il.types[m.return_type] if 0 <= m.return_type < len(il.types) else None
    if (m.addr != producer.near_branch_target or not rt or il._type_enum(rt) != 0x11 or not il.returns_sret(rt) or
            not 0 <= rt[0] < len(il.meta.typedefs) or il._sf_field_size(rt,0) != 12):
        return None
    vt = il.meta.typedefs[rt[0]]
    fields = il.instance_field_chain(vt.index) or {}
    if (not vt.is_valuetype or vt.flags & 0x18 == 0x10 or set(fields) != {16,20,24} or
            any(not 0 <= ti < len(il.types) or il._closed_type_key(il.types[ti]) != (0x0c,0) for _,ti in fields.values())):
        return None
    echo = dict.get(lift.regs, 'RAX')
    if (not echo or echo.kind != 'ptr' or not re.fullmatch(r'&(?:s_[a-fA-F0-9]+|t\d+)',echo.text) or
            echo.ty != rt or lift.slot_types.get(echo.text[1:]) != rt or
            getattr(lift, '_last_sret', None) != (producer.ip, echo)):
        return None
    dst = _own_field(il, td, sdisp(store.memory_displacement), 12)
    ref = _own_field(il, td, sdisp(reload.memory_displacement), 8)
    if (not dst or il._closed_type_key(dst[1]) != (0x11,vt.index,0) or not ref or
            il._type_enum(ref[1]) != 0x12 or ref[1][1] & (1<<29) or len(il.addr_candidates.get(getter.near_branch_target, ())) < 2):
        return None
    alias = getter_alias(lift, getter.near_branch_target, ref[1][0])
    if not alias or alias[1] is None:
        return None  # this window ends in a verified no-FP-input reference getter
    lane = dict.get(lift.regs, 'XMM0')
    if lane is None or lane._unk:
        return None
    return dst[0], echo.text[1:], ref, getter.ip, lane


def copied_product(lift, ins, method, rest, values):
    """C# can't call op_Multiply by name. Use * for the copied result
    only when both emitted operands have the exact operator parameter types."""
    il = lift.il
    block = getattr(getattr(lift, 'out', None), 'block', None)
    if (not block or method.name != 'op_Multiply' or
            not method.is_static or method.flags & 7 != 6 or not method.flags & 0x800 or
            method.generic_container != -1 or len(rest) != 2 or len(values) < 3 or
            il.addr_candidates.get(ins.near_branch_target) != [('method', method.index)]):
        return None
    ps = il.meta.method_params(method)
    if len(ps) != 2 or any(not 0 <= p.type < len(il.types) for p in ps):
        return None
    types = [il.types[p.type] for p in ps]
    # By-value arguments reconstructed by _stack_struct already carry their
    # exact C# type in the initializer. Otherwise retain the copied-home gate.
    initialized = all(ty and text.startswith('new %s { ' % il.type_name(ty)) and text.endswith(' }')
                      for text,ty in zip(rest,types))
    if not initialized and (len(block.insns) < 8 or block.insns[-8].ip != ins.ip or
                            not _window(lift._blocks, block, len(block.insns)-5)):
        return None
    for text, value, ty in zip(rest, values[1:3], types):
        if (not value or value._unk or not re.fullmatch(r'&(?:s_[\da-fA-F]+|t\d+)', value.text) or
                not ty or il._type_enum(ty) != 0x11 or ty[1] & (1<<29) or not 0 <= ty[0] < len(il.meta.typedefs) or
                (not initialized and (value.text != '&' + text or il._closed_type_key(lift.slot_types.get(text)) != il._closed_type_key(ty)))):
            return None
    if method.declaring != types[0][0]:
        return None
    keys = [il._closed_type_key(t) for t in types]
    for ti in {t[0] for t in types}:
        for mi in il.meta.type_methods(il.meta.typedefs[ti]):
            other = il.meta.methods[mi]
            if mi != method.index and other.name == method.name and other.param_count == 2:
                ops = il.meta.method_params(other)
                if any(not 0 <= p.type < len(il.types) for p in ops) or [il._closed_type_key(il.types[p.type]) for p in ops] == keys:
                    return None
    return '%s * %s' % tuple(rest)
