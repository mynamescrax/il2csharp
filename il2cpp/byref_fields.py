"""Whole-path proof for copying a checked object's fields into Win64 ref arguments."""
from il2cpp.byref_zero import entry_ref_args
from il2cpp.names import safe_ident
from il2cpp.prelude import *  # noqa: F401,F403
from il2cpp.text import reg_name
from il2cpp.x64 import VOLATILE, _reg_size

if HAVE_ICED:
    from iced_x86 import InstructionInfoFactory, OpAccess, RegisterExt
    _INFO = InstructionInfoFactory()
    _WRITES = {OpAccess.WRITE, OpAccess.COND_WRITE, OpAccess.READ_WRITE, OpAccess.READ_COND_WRITE}


# Checked reference select, Win64 v31 layout. The only relocation is the
# type-info slot. All branch destinations are part of the proof: null skips
# to the join, insufficient depth and unequal ancestor both select false,
# and only true copies the saved object into RDI. If RDI wasn't initially
# zero its value on the failure path is unknown, not a T-or-null.
_HEAD = bytes.fromhex('4c8bc0 4885c0 7437 4c8b08 488b15')
_TAIL = bytes.fromhex('0fb68230010000 41388130010000 7215 0fb6c8 498b81c8000000 '
                      '483954c8f8 7504 b001 eb02 32c0 84c0 490f45f8')
_SIZE = len(_HEAD) + 4 + len(_TAIL)


def _selected_type(il, ip):
    data = il.bin.read(ip, _SIZE) or b''
    if len(data) != _SIZE or not data.startswith(_HEAD) or not data.endswith(_TAIL):
        return None
    end = len(_HEAD) + 4
    slot = ip + end + int.from_bytes(data[len(_HEAD):end], 'little', signed=True)
    usage = il.decode_slot(slot) or {}
    ty = usage.get('type')
    if usage.get('kind') != 1 or not ty or il._type_enum(ty) != 0x12:
        return None
    ti = usage.get('td')
    if ti != ty[0] or not 0 <= ti < len(il.meta.typedefs):
        return None
    td = il.meta.typedefs[ti]
    if (td.is_valuetype or td.generic_container != -1 or td.declaring >= 0 or td.flags & 0x20 or
            not 0 <= td.byval < len(il.types) or il.types[td.byval] != ty):
        return None
    return ti


def _plain_field(il, ti, offset):
    td = il.meta.typedefs[ti]
    if td.flags & 0x18 == 0x10 or ti >= len(il.field_offsets):  # explicit layout can overlap storage
        return None
    offsets = il.field_offsets[ti]
    if not offsets or len(offsets) != td.field_count:
        return None
    matches = []
    for k, off in enumerate(offsets):
        if off != offset:
            continue
        field = il.meta.fields[td.field_start + k]
        ty = il.types[field.type] if 0 <= field.type < len(il.types) else None
        if ty and not ty[1] & 0x10:  # instance storage only
            matches.append((field, ty))
    if len(matches) != 1:
        return None
    f, ty = matches[0]
    if (ty[1] & 7 != 6 or ty[1] & (1 << 29) or il._type_enum(ty) not in (8, 12) or
            safe_ident(f.name) != f.name or
            il.instance_field_chain(ti).get(offset) != (f.name, f.type)):
        return None
    return il.type_name(il.types[td.byval]), f.name, il._type_enum(ty)


def ref_field_copies(lift, method, insns, pads=(), *, cast_sites=None):
    if not HAVE_ICED or not insns or len(insns) > 512 or not getattr(method, 'param_count', 0):
        return {}
    if not any(i.mnemonic == Mnemonic.CMOVNE for i in insns):
        return {}
    refs = entry_ref_args(lift, method, insns)
    if not refs or lift.il.meta.version != 31:
        return {}
    facts = {r: ('ref', n, 8 if z == '0' else 12) for r, (n, z) in refs.items()}
    il = lift.il
    # Only acyclic direct flow. Model an exception pad as a separate entry
    # with no register proof, and intersect *all* predecessor facts at joins.
    edges = []
    start, end = insns[0].ip, insns[-1].next_ip
    for ins in insns:
        fc = ins.flow_control
        if fc == FlowControl.INDIRECT_BRANCH:
            return {}
        if fc in (FlowControl.CONDITIONAL_BRANCH, FlowControl.UNCONDITIONAL_BRANCH):
            t = ins.near_branch_target
            if ins.op0_kind != OpKind.NEAR_BRANCH64 or start <= t <= ins.ip:
                return {}
            edges.append((ins.ip, t))
        if fc == FlowControl.CALL and start <= ins.near_branch_target < end:
            return {}
    selects = {}
    ips = {i.ip for i in insns}
    for i in insns:
        if i.mnemonic != Mnemonic.CMOVNE:
            continue
        lo, hi = i.next_ip - _SIZE, i.next_ip
        if (lo not in ips or hi not in ips or any(lo < p < hi for p in pads) or
                any(lo < t < hi and not lo <= src < hi for src, t in edges)):
            continue
        ti = _selected_type(il, lo)
        if ti is not None:
            selects[lo] = (hi, ti, i.ip)
    if not selects:
        return {}

    incoming = {p: {} for p in pads}
    incoming[start] = facts
    def send(ip, state):
        prev = incoming.get(ip)
        incoming[ip] = state.copy() if prev is None else {r:v for r,v in state.items() if prev.get(r) == v}

    sites = {}
    for i in insns:
        state = incoming.pop(i.ip, None)
        if state is None:
            continue
        if i.ip in selects:
            hi, ti, cmov = selects[i.ip]
            zero = state.get('RDI') == ('zero',)
            for r in ('RAX', 'RCX', 'RDX', 'R8', 'R9', 'RDI'):
                state.pop(r, None)
            if zero:
                state['RDI'] = ('object', ti)
                if cast_sites is not None:
                    cast_sites[i.ip] = cmov, il.types[il.meta.typedefs[ti].byval]
            send(hi, state)
            continue
        a, b = i.op0_kind, i.op1_kind
        dst, src = reg_name(i.op0_register), reg_name(i.op1_register)
        base = reg_name(i.memory_base)
        pointee = state.get(base, ())
        load = state.get(src, ())
        fact = None
        simple = (_reg_size(i.memory_base) == 8 and i.memory_index == IReg.NONE and not i.has_segment_prefix)
        if i.mnemonic == Mnemonic.MOV:
            if a == OpKind.REGISTER and b == OpKind.REGISTER and _reg_size(i.op0_register) == 8:
                fact = state.get(src)
            elif (a == OpKind.REGISTER and b == OpKind.MEMORY and _reg_size(i.op0_register) == 4
                  and simple and dst != base and pointee[:1] == ('object',)):
                field = _plain_field(il, pointee[1], i.memory_displacement)
                if field:
                    fact = ('field', i.next_ip, base, i.memory_displacement, *field)
            elif (a == OpKind.MEMORY and b == OpKind.REGISTER and _reg_size(i.op1_register) == 4
                  and simple and i.memory_displacement == 0 and pointee[:1] == ('ref',)
                  and load[:2] == ('field', i.ip) and load[-1] == pointee[2]):
                sites[i.ip] = (pointee[1], *load[2:-1])
        elif (i.mnemonic == Mnemonic.XOR and a == b == OpKind.REGISTER and
              i.op0_register == i.op1_register and _reg_size(i.op0_register) in (4, 8)):
            fact = ('zero',)
        for used in _INFO.info(i).used_registers():
            if used.access in _WRITES and RegisterExt.is_gpr(used.register):
                state.pop(reg_name(RegisterExt.full_register(used.register)), None)
        if fact:
            state[dst] = fact
        fc = i.flow_control
        if fc in (FlowControl.CALL, FlowControl.INDIRECT_CALL):
            for r in VOLATILE:
                state.pop(r, None)
        if fc in (FlowControl.CONDITIONAL_BRANCH, FlowControl.UNCONDITIONAL_BRANCH):
            send(i.near_branch_target, state)
        if fc in (FlowControl.NEXT, FlowControl.CALL, FlowControl.INDIRECT_CALL, FlowControl.CONDITIONAL_BRANCH):
            send(i.next_ip, state)
    return sites
