"""Find an accessible spelling when *all* owners implement the same property read."""
import re

from il2cpp.binary import PE
from il2cpp.entrylive import entry_live_args
from il2cpp.expr import acc_get, _recv_fold
from il2cpp.marshalled_getter import marshalled_getter
from il2cpp.names import safe_ident


def _public_alias(lift, addr, owner):
    il = lift.il
    cands = il.addr_candidates.get(addr, ())
    if len(cands) < 2 or not 0 <= owner < len(il.meta.typedefs):
        return None
    td = il.meta.typedefs[owner]
    if (td.is_valuetype or td.flags & 7 != 1 or td.flags & 0x20 or
            td.declaring != -1 or td.generic_container != -1):
        return None
    public = []
    seen = set()
    methods = []
    result = None
    for kind, mi in cands:
        if kind != 'method' or not 0 <= mi < len(il.meta.methods) or mi in seen:
            return None
        m = il.meta.methods[mi]
        if (m.declaring != owner or m.addr != addr or m.is_static or m.param_count or
                m.generic_container != -1 or m.flags & 0x40 or
                not 0 <= m.return_type < len(il.types)):
            return None
        rt = il.types[m.return_type]
        if not rt or rt[1] & (1 << 29) or il._type_enum(rt) not in (8, 0x12):
            return None
        key = (8, 0) if il._type_enum(rt) == 8 else il._closed_type_key(rt)
        if key is None or (result is not None and key != result):
            return None
        result = key
        seen.add(mi)
        if not m.name.startswith('get_'):
            if key[0] != 0x12 or m.flags & 0x800 or m.flags & 7 == 6:
                return None
            methods.append(m.name)
            continue
        name = m.name[4:]
        if not re.fullmatch(r'[A-Za-z_]\w*', name) or safe_ident(name) != name:
            return None
        props = [p for p in il.meta.properties[td.property_start:td.property_start + td.property_count]
                 if il.meta.getstr(p[0]) == name]
        if len(props) != 1 or not 0 <= props[0][1] < td.method_count or td.method_start + props[0][1] != mi:
            return None
        if m.flags & 7 == 6:
            public.append(name)
    if not public:
        return None
    if result[0] == 0x12:
        if len(public) == 1 and methods and marshalled_getter(lift, addr, owner, result, methods):
            return public[0], il.typedef_full(owner)
        return None
    # Same this, return, native address and argument list. The only ABI
    # input that can distinguish these managed identities is MethodInfo*
    # (RDX for a nullary instance getter). Check all reachable paths.
    live = entry_live_args(il, addr)
    if live is None or 'g' not in live[0] or 'g' in live[1]:
        return None
    return min(public), None  # representative, not a guess at the source name


def getter_alias(lift, addr, owner):
    cache = lift.il.__dict__.setdefault('_public_getter_aliases', {})
    key = addr, owner
    if key not in cache:
        cache[key] = _public_alias(lift, addr, owner)
    return cache[key]


def shared_getter(lift, addr, args, values, xmm):
    il = lift.il
    if (not isinstance(getattr(il, 'bin', None), PE) or not il.bin.is64 or len(args) != 1 or not values or
            addr == getattr(getattr(lift, '_current_method', None), 'addr', None)):
        return None
    recv = values[0]
    if (not recv or recv.kind != 'obj' or recv._unk or not recv.ty or recv.ty[1] & (1 << 29) or
            il._type_enum(recv.ty) != 0x12 or recv.text != args[0] or
            not re.fullmatch(r'[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*', recv.text)):
        return None
    # The register spray is not part of the property's signature. Do not
    # discard an unevaluated call or field expression in a surplus slot.
    for extra in values[1:]:
        if extra and not extra._unk and not re.fullmatch(r'[A-Za-z_]\w*|-?\d+(?:\.\d+)?[fd]?', extra.text or ''):
            return None
    alias = getter_alias(lift, addr, recv.ty[0])
    if not alias:
        return None
    name, owner = alias
    # XMM0 can still hold part of a struct return already copied into an
    # instance field. Only the exact saved expression at the proved call
    # site may be ignored, and only for the marshalled, no-FP-input wrapper.
    stored = getattr(lift, '_stored_getter_lane', None)
    scratch = getattr(lift, '_scratch_getter_lanes', None)
    for k, extra in enumerate(xmm):
        if owner and k == 0 and stored and stored[0] == lift._cur_ip and extra is stored[1]:
            continue
        if owner and scratch and scratch[0] == lift._cur_ip and k < len(scratch[1]) and extra is scratch[1][k]:
            continue
        if extra and not extra._unk and not re.fullmatch(r'[A-Za-z_]\w*|-?\d+(?:\.\d+)?[fd]?', extra.text or ''):
            return None
    text = _recv_fold(recv.text)
    if owner and re.fullmatch(r'(?:[tv]\d+|s_[a-fA-F0-9]+)', text):
        # The declared C# temp can be wider than this value (a phi or a
        # later upcast to UnityEngine.Object). Keep the receiver proof at
        # the use; a System.Object local has no `parent` property.
        text = '((%s)%s)' % (owner, text)
    return acc_get(text + '.' + name) + ' /* shared getter */'
