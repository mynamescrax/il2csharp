"""Resolve a shared Win64 load leaf by its receiver layout, not by picking an owner."""
import re

from il2cpp.binary import PE
from il2cpp.csharp import FA_LITERAL, FA_STATIC, field_attrs, source_field_name
from il2cpp.names import safe_ident
from il2cpp.prelude import HAVE_ICED
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


def _read(il, addr, receiver):
    # Exact qword load from RCX into the return register, followed by RET.
    # A narrower load, a different ABI or any intervening effect declines.
    if not il.bin.is_exec_va(addr):
        return None
    code = il.bin.read(addr, 5)
    if not code or len(code) != 5 or code[:3] != b'\x48\x8b\x41' or code[4] != 0xc3:
        return None
    off = int.from_bytes(code[3:4], 'little', signed=True)
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
            if field_attrs(il, f) & (FA_LITERAL | FA_STATIC):
                continue
            if not offsets or k >= len(offsets) or offsets[k] < 0x10 or not 0 <= f.type < len(il.types):
                return None
            pos, ty = offsets[k], il.types[f.type]
            if pos >= off + 8:
                continue
            size = il._sf_field_size(ty, 0)
            if not size:
                return None
            if pos + size > off:
                if (match or pos != off or size != 8 or not ty or ty[1] & (1 << 29) or
                        il._type_enum(ty) != 0x12):
                    return None
                match = (ti, fi, ty)
    if not match:
        return None
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
    for extra in [*args[1:4], *xmm]:
        if extra and not extra._unk and not re.fullmatch(r'[A-Za-z_]\w*|-?\d+(?:\.\d+)?[fd]?', extra.text or ''):
            return None
    cache = il.__dict__.setdefault('_shared_field_reads', {})
    key = (addr, current.declaring)
    if key not in cache:
        cache[key] = _read(il, *key)
    return cache[key]
