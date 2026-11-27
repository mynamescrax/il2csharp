"""Resolve a shared Win64 load leaf by its receiver layout, not by picking an owner."""
import re

from il2cpp.binary import PE
from il2cpp.csharp import FA_LITERAL, FA_STATIC, declares_member_name, field_attrs, source_field_name
from il2cpp.names import safe_ident
from il2cpp.prelude import HAVE_ICED
from il2cpp.sret_copy import _own_field
from il2cpp.text import reg_name

if HAVE_ICED:
    from iced_x86 import Mnemonic, OpKind, Register as R


def saved_fp_consumers(blocks):
    """Find a direct call's XMM0 result saved across a second call.

    Inspect only one straight-line block: clear the hidden argument, restore
    the receiver from a nonvolatile register and save XMM0 into XMM6..15.
    The producer's return signature and the consumer's field proof are
    checked during lifting, when the receiver value is available.
    """
    sites = {}
    for block in blocks:
        ins = block.insns
        for j in range(4, len(ins)):
            consumer = ins[j]
            if consumer.mnemonic != Mnemonic.CALL or consumer.op0_kind != OpKind.NEAR_BRANCH64:
                continue
            producer, clear, receiver, save = ins[j-4:j]
            if (producer.mnemonic == Mnemonic.CALL and producer.op0_kind == OpKind.NEAR_BRANCH64
                    and clear.mnemonic == Mnemonic.XOR and clear.op0_register == clear.op1_register == R.EDX
                    and receiver.mnemonic == Mnemonic.MOV and receiver.op0_register == R.RCX
                    and receiver.op1_register in (R.RBX, R.RBP, R.RSI, R.RDI, R.R12, R.R13, R.R14, R.R15)
                    and save.mnemonic == Mnemonic.MOVAPS and save.op1_register == R.XMM0
                    and R.XMM6 <= save.op0_register <= R.XMM15
                    and all(ins[k].next_ip == ins[k+1].ip for k in range(j-4, j))):
                sites[producer.ip] = (consumer.near_branch_target, reg_name(receiver.op1_register))
    return sites


def reference_field_at(il, receiver, off, *, constructed=False):
    """Unique class reference occupying these eight bytes across all bases."""
    if off < 0x10:
        return None
    meta = il.meta
    chain = il.base_chain_tds(receiver)
    if not chain or meta.typedefs[chain[-1]].parent >= 0:
        return None
    match = None
    for ti in chain:
        td = meta.typedefs[ti]
        if td.is_valuetype or td.generic_container != -1 or td.flags & 0x18 == 0x10:
            return None
        offsets = il.field_offsets[ti] if ti < len(il.field_offsets) else None
        for k, fi in enumerate(meta.type_fields(td)):
            f = meta.fields[fi]
            if not 0 <= f.type < len(il.types) or not il.types[f.type]:
                return None
            if field_attrs(il, f) & (FA_LITERAL | FA_STATIC):
                continue
            if not offsets or k >= len(offsets) or offsets[k] < 0x10 or not 0 <= f.type < len(il.types):
                return None
            pos, ty = offsets[k], il.types[f.type]
            if pos >= off + 8:
                continue
            size = il._sf_field_size(ty, 0)
            if not size or size < 0:
                return None
            if pos + size > off:
                if match or pos != off or size != 8 or ty[1] & (1 << 29):
                    return None
                if il._type_enum(ty) != 0x12:
                    k=il._closed_type_key(ty) if constructed and il._type_enum(ty)==0x15 else None
                    if not k or k[1][0]!=0x12 or k[1][-1] or k[-1]:return None
                match = (ti, fi, ty)
    return match


def _read(il, addr, receiver):
    # The load leaf proves the displacement; field layout proves the storage.
    if not il.bin.is_exec_va(addr):
        return None
    code = il.bin.read(addr, 5)
    if not code or len(code) != 5 or code[:3] != b'\x48\x8b\x41' or code[4] != 0xc3:
        return None
    match = reference_field_at(il,receiver,int.from_bytes(code[3:4], 'little', signed=True))
    if not match:
        return None
    meta = il.meta
    chain = il.base_chain_tds(receiver)
    owner, fi, ty = match
    # `base` resolves on the immediate parent. Avoid hidden members on
    # intervening classes, and don't assume that a private field is visible.
    if owner not in chain[:2]:
        return None
    own = owner == receiver
    field = meta.fields[fi]
    vis = field_attrs(il, field) & 7
    head = 'this.' if own else 'base.'
    # The load alone gives its bits, not a managed return ABI. Require a
    # matching set of receiver-chain MethodDefs: every such owner consumes
    # just this and returns the reference stored in this exact field.
    applicable = [meta.methods[mi] for kind, mi in il.addr_candidates[addr]
                  if kind == 'method' and meta.methods[mi].declaring in chain]
    if not applicable:
        return None
    for m in applicable:
        if (m.is_static or m.param_count or m.generic_container != -1 or m.addr != addr or
                not 0 <= m.return_type < len(il.types)):
            return None
        rt = il.types[m.return_type]
        if not rt or rt[1] & (1 << 29) or il._type_enum(rt) != 0x12 or rt[0] != ty[0]:
            return None
    if own or vis in (4, 5, 6):
        return head + safe_ident(source_field_name(il, fi)), ty

    # A private auto-property backing field can still be read from a derived
    # class through its accessible nonvirtual getter if its body is exactly
    # the load above. Other same-address getters don't establish its name.
    backing = re.fullmatch(r'<([A-Za-z_]\w*)>k__BackingField', field.name)
    if not backing:
        return None
    name = backing[1]
    td = meta.typedefs[owner]
    props = [pr for pr in meta.properties[td.property_start:td.property_start + td.property_count]
             if meta.getstr(pr[0]) == name]
    if len(props) != 1 or not 0 <= props[0][1] < td.method_count:
        return None
    mi = td.method_start + props[0][1]
    m = meta.methods[mi]
    if (('method', mi) not in il.addr_candidates[addr] or m.declaring != owner or
            m.name != 'get_' + name or m.flags & 0x40 or (m.flags & 7) not in (4, 5, 6)):
        return None
    return head + safe_ident(name), ty


def _scratch_lane(lift, e):
    """Pure floating arithmetic on already bound locals/struct fields only.

    A packed Expr prints `?` even when one of its hidden lanes contains a
    deferred property read. Inspect all four lanes before discarding it.
    No dereferences, getters, indexers, user operators or calls qualify.
    """
    if e.text == '?' and e.kind == 'bits':
        parts = getattr(e, '_parts', ())
        return len(parts) == 4 and all(
            off == 4*i and start == 0 and width == 4 and lane.kind == 'float' and
            _scratch_lane(lift, lane) for i,(off,lane,start,width) in enumerate(parts))
    if e.kind != 'float' or not e.text or len(e.text) > 256:
        return False
    # A flat product/sum of float locals has no overflow or conversion effects.
    atoms = re.split(r' [*+\-] ', e.text)
    il = lift.il
    for atom in atoms:
        m = re.fullmatch(r'(t\d+)(?:\.([xyzw]))?', atom)
        if not m: return False
        ty = getattr(lift, '_var_types', {}).get(m[1])
        if not ty: return False
        key = il._closed_type_key(ty)
        if not m[2]:
            if key != (0x0c,0): return False
            continue
        if key != (0x11,ty[0],0) or not 0 <= ty[0] < len(il.meta.typedefs): return False
        td = il.meta.typedefs[ty[0]]
        if not td.is_valuetype or td.generic_container != -1: return False
        fields = [il.meta.fields[fi] for fi in il.meta.type_fields(td) if source_field_name(il,fi) == m[2]]
        if len(fields) != 1: return False
        field, = fields
        if (field_attrs(il,field) & (FA_LITERAL | FA_STATIC | 7) != 6 or
                not 0 <= field.type < len(il.types) or il._closed_type_key(il.types[field.type]) != (0x0c,0)):
            return False
    return True


def shared_field_read(lift, addr, args, xmm):
    il = lift.il
    current = getattr(lift, '_current_method', None)
    recv = args[0] if args else None
    if (not isinstance(getattr(il, 'bin', None), PE) or not il.bin.is64 or current is None or
            current.is_static or not recv or recv.kind != 'obj' or recv._unk or recv.text != 'this' or
            not recv.ty or il._type_enum(recv.ty) != 0x12 or recv.ty[1] & (1 << 29) or
            recv.ty[0] != current.declaring or len(il.addr_candidates.get(addr, ())) < 2):
        return None
    # Dropping stale ABI slots must not discard an unevaluated expression.
    for extra in args[1:4]:
        if extra and not extra._unk and not re.fullmatch(r'[A-Za-z_]\w*|-?\d+(?:\.\d+)?[fd]?', extra.text or ''):
            return None
    for extra in xmm:
        if (extra and not extra._unk and not re.fullmatch(r'[A-Za-z_]\w*|-?\d+(?:\.\d+)?[fd]?', extra.text or '') and
                not _scratch_lane(lift, extra)):
            return None
    cache = il.__dict__.setdefault('_shared_field_reads', {})
    key = (addr, current.declaring)
    if key not in cache:
        cache[key] = _read(il, *key)
    return cache[key]


# One complete Win64 forwarder: read this's field into RCX, throw on a null
# reference, otherwise restore the stack and return the shared leaf's RAX.
_NESTED_TAIL = re.compile(rb'\x48\x83\xec\x28\x48\x8b\x49(.)\x48\x85\xc9\x74\x0b'
                          rb'\x33\xd2\x48\x83\xc4\x28\xe9(.{4})\xe8(.{4})\xcc', re.S)


def nested_field_tail(lift, ins, args):
    il = lift.il
    m = getattr(lift, '_current_method', None)
    if (not isinstance(getattr(il, 'bin', None), PE) or not il.bin.is64 or not m or m.is_static or
            m.param_count or m.generic_container != -1 or not 0 <= m.return_type < len(il.types) or
            ins.ip != m.addr + 19 or len(args) != 2 or args[1] != '0'):
        return None
    helper = il.meta.typedefs[m.declaring]
    outer = il._nested_owner(helper.index)
    if (outer is None or helper.is_valuetype or helper.generic_container != -1 or
            il.function_extent(m.addr) != (m.addr, m.addr + 30) or il.eh_regions(m.addr)):
        return None
    match = _NESTED_TAIL.fullmatch(il.bin.read(m.addr, 30) or b'')
    if not match:
        return None
    def target(group):
        return m.addr + match.end(group) + int.from_bytes(match[group], 'little', signed=True)
    addr, null = target(2), target(3)
    if (addr != ins.near_branch_target or
            lift._named_raise_throw(null, lift._call_name(null)) != 'System.NullReferenceException'):
        return None
    parent = _own_field(il, helper, int.from_bytes(match[1], 'little', signed=True), 8)
    if (not parent or parent[0] != args[0] or il._closed_type_key(parent[1]) != (0x12, outer, 0)):
        return None
    # _read proves the immediate base's accessible nonvirtual getter or
    # accessible field. C# extends the enclosing type's protected access to
    # a nested helper, but only through a receiver of the enclosing type.
    field = _read(il, addr, outer)
    if not field or not field[0].startswith('base.') or il._closed_type_key(field[1]) != il._closed_type_key(il.types[m.return_type]):
        return None
    member = field[0][5:]
    if declares_member_name(il, il.meta.typedefs[outer], member):
        return None
    return '%s.%s /* shared field read */' % (parent[0], member)
