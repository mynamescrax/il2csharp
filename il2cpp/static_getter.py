"""Recover an unregistered Win64 helper equivalent to a public static getter."""
import re

from il2cpp.binary import PE
from il2cpp.csharp import FA_LITERAL, FA_STATIC, field_attrs
from il2cpp.names import safe_ident


# cmp byte [flag],0; jne load; lea rcx,[slot]; call init; mov byte [flag],1;
# load: mov rax,[slot]; mov rax,[rax+static_fields]; mov rax,[rax]; epilogue.
_PREFIX = (rb'\x48\x83\xec\x28\x80\x3d(.{4})\x00\x75\x13\x48\x8d\x0d(.{4})'
                    rb'\xe8(.{4})\xc6\x05(.{4})\x01\x48\x8b\x05(.{4})'
                    rb'\x48\x8b\x80\xb8\x00\x00\x00\x48\x8b')
_EPILOGUE = rb'\x48\x83\xc4\x28\xc3'
_SHAPE = re.compile(_PREFIX + b'\x00' + _EPILOGUE,re.S)
_DISP8 = re.compile(_PREFIX + b'\x40(.)' + _EPILOGUE,re.S)


def _slot(il, va, init, offset=0):
    size = 55 if offset else 54
    if not init or not il.bin.is_exec_va(va) or il.function_extent(va) != (va, va + size):
        return None
    m = (_DISP8 if offset else _SHAPE).fullmatch(il.bin.read(va, size) or b'')
    if not m or offset and int.from_bytes(m[6],'little',signed=True)!=offset:
        return None
    # cmp and mov have a trailing imm8 after their RIP displacement.
    flag, slot, call, store, load = (va + m.end(i) + (i in (1, 4)) + int.from_bytes(
        m[i], 'little', signed=True) for i in range(1, 6))
    return slot if flag == store and slot == load and call == init else None


def _alias(il, va, init):
    return alias_for_slot(il, _slot(il, va, init), init)


def alias_for_slot(il, slot, init, offset=0):
    """Public getter for the reference at the caller's exact static-field offset."""
    if not 0<=offset<128 or offset%8: return None
    usage = il.decode_slot(slot) if slot is not None else None
    if not usage or usage.get('kind') != 1:
        return None
    ty = usage.get('type')
    ti = usage.get('td')
    if (not ty or il._type_enum(ty) != 0x12 or ti != ty[0] or
            not 0 <= ti < len(il.meta.typedefs) or ti >= len(il.field_offsets)):
        return None
    td = il.meta.typedefs[ti]
    if (td.generic_container != -1 or td.declaring >= 0 or td.is_valuetype or td.has_cctor or
            td.flags & 7 != 1 or td.flags & 0x20):
        return None
    offsets = il.field_offsets[ti]
    if not offsets or len(offsets) != td.field_count:
        return None
    fields = []
    for fi, off in zip(il.meta.type_fields(td), offsets):
        f = il.meta.fields[fi]
        attrs = field_attrs(il, f)
        if attrs & FA_STATIC and not attrs & FA_LITERAL and off < offset+8:
            if offset and off<offset:
                if off<0 or not 0<=f.type<len(il.types): return None
                size=il._sf_field_size(il.types[f.type],0)
                if not size or size<0: return None
                if off+size<=offset: continue
            fields.append((off, f))
    if len(fields) != 1 or fields[0][0] != offset:
        return None
    field = fields[0][1]
    ft = il.types[field.type] if 0 <= field.type < len(il.types) else None
    backing = re.fullmatch(r'<([A-Za-z_]\w*)>k__BackingField', field.name)
    if not ft or ft[1] & (1 << 29) or il._type_enum(ft) != 0x12 or ft[0] != ti or not backing:
        return None
    name = backing[1]
    rows = [pr for pr in il.meta.properties[td.property_start:td.property_start + td.property_count]
            if il.meta.getstr(pr[0]) == name]
    if len(rows) != 1 or not 0 <= rows[0][1] < td.method_count:
        return None
    m = il.meta.methods[td.method_start + rows[0][1]]
    if (m.declaring != ti or m.name != 'get_' + name or not m.is_static or m.param_count or
            m.flags & 7 != 6 or m.generic_container != -1 or not 0 <= m.return_type < len(il.types) or
            il.types[m.return_type] != ty or not m.addr or _slot(il, m.addr, init, offset) != slot):
        return None
    return il.type_name(ty) + '.' + safe_ident(name), ty


def static_getter(lift, va, args, xmm):
    il = lift.il
    if (not isinstance(getattr(il, 'bin', None), PE) or not il.bin.is64 or il.meta.version != 31 or
            il.addr_candidates.get(va) or il.addr_to_method.get(va)):
        return None
    cache = il.__dict__.setdefault('_static_getter_twins', {})
    if va not in cache:
        cache[va] = _alias(il, va, lift.rt_init_meta)
    if cache[va] and all(e is None or e._unk or re.fullmatch(r'[A-Za-z_]\w*|-?\d+|&data_[0-9a-f]+', e.text or '')
                         for e in (*args, *xmm)):
        return cache[va]
    return None
