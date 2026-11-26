"""Recover the behavior (not the source name) of folded Win64 icall wrappers."""
import re


# Straight-line hot/cold forwarders. On the cold path the resolver is given
# a constant signature; on both paths the saved incoming dwords are restored
# in order and control goes to the same cached function pointer. No use of
# a hidden MethodInfo. Only the four rel32 fields are allowed to vary.
def _shape(prologue, save_args, restore):
    literal = lambda h: re.escape(bytes.fromhex(h))
    return re.compile(literal(prologue + ' 48 8b 05') + b'(.{4})' + literal(save_args +
                      ' 48 85 c0 75 13 48 8d 0d') + b'(.{4})\xe8(.{4})' +
                      literal('48 89 05') + b'(.{4})' + literal(restore + ' 48 ff e0'), re.S)


_WRAPPERS = {
    1: _shape('40 53 48 83 ec 20', '8b d9', '8b cb 48 83 c4 20 5b'),
    2: _shape('48 89 5c 24 08 57 48 83 ec 20', '8b da 8b f9',
              '8b d3 8b cf 48 8b 5c 24 30 48 83 c4 20 5f'),
}

# Two full-width managed references, not the dword variant in _WRAPPERS.
_REF_PAIR = _shape('48 89 5c 24 08 57 48 83 ec 20', '48 8b da 48 8b f9',
                   '48 8b d3 48 8b cf 48 8b 5c 24 30 48 83 c4 20 5f')


def _signature(il, va, arity):
    return _wrapper_signature(il, va, _WRAPPERS.get(arity))


def _wrapper_signature(il, va, pattern):
    start, end = il.function_extent(va)
    if start != va or not 0 < end - start <= 80 or pattern is None:
        return None
    match = pattern.fullmatch(il.bin.read(va, end - start) or b'')
    if not match:
        return None
    cell, sig_ptr, resolver, store = (va + match.end(i) + int.from_bytes(
        match[i], 'little', signed=True) for i in range(1, 5))
    if cell != store or resolver != il.rt_icall_resolve:
        return None
    sig = il.icall_cells.get(cell)
    return sig if sig and il.bin.cstr(sig_ptr, 512) == sig else None


def vector_ref_pair(il, target):
    """The public OrthoNormalize and private icall must both take exactly
    two writable Vector3 refs, and both paths must forward the addresses."""
    ids = il.addr_candidates.get(target, ())
    if len(ids) != 2 or not getattr(il,'icall_cells',None):
        return None
    name = 'UnityEngine.Vector3'
    expected = name + '::OrthoNormalize2(' + name + '&,' + name + '&)'
    if _wrapper_signature(il,target,_REF_PAIR) != expected:
        return None
    impl = (il._icall_annotation(expected) or {}).get('method')
    public = []
    for kind,mi in ids:
        if kind != 'method' or not 0 <= mi < len(il.meta.methods):
            return None
        m = il.meta.methods[mi]
        if (m.addr != target or not m.is_static or m.flags & (0x40|0x800) or m.generic_container != -1 or
                m.param_count != 2 or not 0 <= m.return_type < len(il.types) or
                il._closed_type_key(il.types[m.return_type]) != (1,0) or il.typedef_full(m.declaring) != name):
            return None
        ps = il.meta.method_params(m)
        if len(ps) != 2 or any(not 0 <= p.type < len(il.types) or il._closed_type_key(il.types[p.type]) !=
                                (0x11,m.declaring,1) or il.types[p.type][1] & 3 for p in ps):
            return None
        if mi == impl and m.name == 'OrthoNormalize2' and m.iflags & 0x1000 and m.flags & 7 == 1:
            continue
        if m.name != 'OrthoNormalize' or m.flags & 7 != 6:
            return None
        public.append((mi,il.types[ps[0].type]))
    return public[0] if len(public) == 1 else None


def _alias(il, va):
    """A unique public spelling of exactly the same typed native operation."""
    cands = il.addr_candidates.get(va, ())
    if len(cands) != 2 or not getattr(il, 'icall_cells', None):
        return None
    sig_key = None
    public = []
    ids = set()
    for kind, idx in cands:
        if kind != 'method' or not 0 <= idx < len(il.meta.methods):
            return None
        m = il.meta.methods[idx]
        if (m.addr != va or not m.is_static or m.generic_container != -1 or
                m.flags & (0x40 | 0x800) or not 1 <= m.param_count <= 2 or
                not 0 <= m.declaring < len(il.meta.typedefs) or
                not 0 <= m.return_type < len(il.types)):
            return None
        td = il.meta.typedefs[m.declaring]
        if td.generic_container != -1 or td.declaring != -1 or td.flags & 7 != 1:
            return None
        ps = il.meta.method_params(m)
        if len(ps) != m.param_count or any(not 0 <= p.type < len(il.types) for p in ps):
            return None
        key = (m.declaring, m.return_type, tuple(p.type for p in ps))
        if sig_key is not None and key != sig_key:
            return None
        sig_key = key
        ids.add(idx)
        if m.flags & 7 == 6:
            public.append(m)
    if len(public) != 1:
        return None
    m = public[0]
    sig = _signature(il, va, m.param_count)
    if not sig:
        return None
    resolved = (il._icall_annotation(sig) or {}).get('method')
    if resolved not in ids:
        return None
    rt = il.types[m.return_type]
    if not rt or rt[1] & (1 << 29) or il._type_enum(rt) not in (2, 8):
        return None
    pts = [il.types[p] for p in sig_key[2]]
    for pt in pts:
        if not pt or pt[1] & (1 << 29):
            return None
        if il._type_enum(pt) != 8 and not (il._type_enum(pt) == 0x11 and
                0 <= pt[0] < len(il.meta.typedefs) and il.meta.typedefs[pt[0]].is_enum and
                il.value_type_size(pt[0]) == 4):
            return None
    params = il._icall_sig_params(sig)
    if params is None or [il._icall_type_key(t) for t in params] != [il.type_name(p) for p in pts]:
        return None
    return il.typedef_full(m.declaring) + '.' + m.name, pts


def shared_icall(lift, va, args, values):
    il = lift.il
    if va == getattr(getattr(lift, '_current_method', None), 'addr', None):
        return None
    cache = il.__dict__.setdefault('_shared_icall_aliases', {})
    if va not in cache:
        cache[va] = _alias(il, va)
    alias = cache[va]
    if not alias or len(args) != len(alias[1]) or len(values) < len(args):
        return None
    parts = []
    for text, expr, pt in zip(args, values, alias[1]):
        if expr is None or expr._unk or expr.kind in ('ptr', 'klass', 'usage') or text in ('_', '?'):
            return None
        if re.fullmatch(r'[+-]?(?:0[xX][0-9a-fA-F]+|0|[1-9][0-9]*)', text):
            n = int(text, 0)
            if not -(1 << 31) <= n < 1 << 32:
                return None
            n = (n + 2**31) % 2**32 - 2**31
            text = str(n)
            if il._type_enum(pt) == 0x11:
                tn = il.type_name(pt)
                member = (il.enum_members(pt[0]) or {}).get(n)
                text = '%s.%s' % (tn, member) if member else 'unchecked((%s)(%d))' % (tn, n)
        elif (il._type_enum(pt) == 0x11 and expr.kind == 'int' and expr.ty and
              not expr.ty[1] & (1 << 29) and il._type_enum(expr.ty) == 8):
            # The proved wrapper forwards precisely the low dword. Its enum
            # overload can therefore take a tracked Int32, not just literals;
            # unchecked preserves the bits even for unsigned enum storage.
            text = 'unchecked((%s)(%s))' % (il.type_name(pt), text)
        elif (not expr.ty or expr.ty[1] & (1 << 29) or il._type_enum(expr.ty) != il._type_enum(pt)
              or (il._type_enum(pt) == 0x11 and expr.ty[0] != pt[0])):
            return None
        parts.append(text)
    return '%s(%s) /* shared icall */' % (alias[0], ', '.join(parts))
