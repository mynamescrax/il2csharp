"""Proof of the Win64 Unity reference-getter ABI through a cached injected icall."""
import re

from il2cpp.generic_array import object_shared_entry


# Fragments are joined by their *native* branch targets. RIP displacements
# are relocations, never fixture addresses. In particular .pdata may end at
# the null check, before either the call or the two slow exits.
_ENTRY = re.compile(rb'\x40\x53\x48\x83\xec\x20\x80\x3d(.{4})\x00\x48\x8b\xd9\x75(.)', re.S)
_INIT = re.compile(rb'\x48\x8d\x0d(.{4})\xe8(.{4})', re.S)
_READY = re.compile(rb'\xc6\x05(.{4})\x01', re.S)
# Test saved RCX, load and test its cached native pointer. Load the call
# cell; on a miss resolve the signature literal, then store into that cell.
_INVOKE = re.compile(
    rb'\x48\x85\xdb\x74(.)\x48\x89\x7c\x24\x30\x48\x8b\x7b(.)\x48\x85\xff\x74(.)'
    rb'\x48\x8b\x05(.{4})\x48\x85\xc0\x75\x13\x48\x8d\x0d(.{4})\xe8(.{4})\x48\x89\x05(.{4})'
    rb'\x48\x8b\xcf\xff\xd0', re.S)
# Same marshal and call, with the destroyed-object helper in the fallthrough
# rather than after the tail return. Group 3 is now its rel32 call target.
_INLINE_INVOKE = re.compile(
    rb'\x48\x85\xdb\x74(.)\x48\x89\x7c\x24\x30\x48\x8b\x7b(.)\x48\x85\xff\x75\x0a'
    rb'\x33\xd2\x48\x8b\xcb\xe8(.{4})'
    rb'\x48\x8b\x05(.{4})\x48\x85\xc0\x75\x13\x48\x8d\x0d(.{4})\xe8(.{4})\x48\x89\x05(.{4})'
    rb'\x48\x8b\xcf\xff\xd0', re.S)
# Unmarshal RAX using a fresh MethodRef in RDX, then tail-return. The two
# null exits raise; only the destroyed-object exit takes a managed argument.
_RETURN = re.compile(rb'\x48\x8b\x15(.{4})\x48\x8b\xc8\x48\x8b\x7c\x24\x30\x48\x83\xc4\x20\x5b\xe9(.{4})', re.S)
_RAISE = re.compile(rb'\xe8(.{4})\xcc\x33\xd2\x48\x8b\xcb\xe8(.{4})\xcc', re.S)


def _unmarshal(il, slot, result, target):
    use = il.decode_slot(slot) or {}
    si = use.get('idx', -1)
    if use.get('kind') != 6 or not 0 <= si < len(il.method_specs):
        return False
    mi, ci, gi = il.method_specs[si]
    if not 0 <= mi < len(il.meta.methods) or ci != -1:
        return False
    m = il.meta.methods[mi]
    args = il._method_spec_type_args(gi)
    ps = il.meta.method_params(m)
    if (not m.is_static or m.name != 'UnmarshalUnityObject' or m.param_count != 1 or len(ps) != 1 or
            il.typedef_full(m.declaring) != 'UnityEngine.Bindings.Unmarshal' or
            not 0 <= ps[0].type < len(il.types) or il._closed_type_key(il.types[ps[0].type]) != (0x18, 0) or
            not args or len(args) != 1 or il._closed_type_key(args[0]) != result or
            il._closed_type_key(il.candidate_return_type(('generic', si))) != result):
        return False
    # The hidden slot closes T; the code pointer can be registered under
    # UnmarshalUnityObject<object>. Follow the explicit pointer index, not
    # the table row ordinal, and do not accept an unrelated generic tail.
    return object_shared_entry(il, mi) == target


def marshalled_getter(lift, addr, owner, result, method_names):
    """The incoming MethodInfo does not distinguish any alias on either
    cache path. Check the actual resolver and its unary IntPtr signature,
    not just a load of a known icall cell somewhere in the function."""
    il = lift.il
    end = il.next_method_start(addr)
    if il.meta.version != 31 or not end or not 0 < end - addr <= 512 or not il.bin.is_exec_va(addr):
        return False
    data = il.bin.read(addr, end-addr) or b''

    def rel(match, n, trailing=0):
        return addr + match.end(n) + trailing + int.from_bytes(match[n], 'little', signed=True)

    entry = _ENTRY.match(data)
    if not entry:
        return False
    pos = entry.end()
    while (init := _INIT.match(data, pos)):
        if rel(init, 2) != lift.rt_init_meta:
            return False
        pos = init.end()
    ready = _READY.match(data, pos)
    if (not ready or pos == entry.end() or rel(entry, 1, 1) != rel(ready, 1, 1) or
            rel(entry, 2) != addr + ready.end()):
        return False
    invoke = _INVOKE.match(data, ready.end())
    inline_throw = invoke is None
    if inline_throw:
        invoke = _INLINE_INVOKE.match(data, ready.end())
    if not invoke or rel(invoke, 4) != rel(invoke, 7) or rel(invoke, 6) != il.rt_icall_resolve:
        return False
    offset = int.from_bytes(invoke[2], 'little', signed=True)
    field = (il.instance_field_chain(owner) or {}).get(offset)
    if (not field or field[0] != 'm_CachedPtr' or not 0 <= field[1] < len(il.types) or
            il._closed_type_key(il.types[field[1]]) != (0x18, 0)):
        return False
    sig = il.icall_cells.get(rel(invoke, 4))
    if (not sig or il.bin.cstr(rel(invoke, 5), 512) != sig or
            not any(sig == f'{il.typedef_full(owner)}::{name}_Injected(System.IntPtr)' for name in method_names)):
        return False
    annotation = il._icall_annotation(sig) or {}
    mi = annotation.get('method', -1)
    if not 0 <= mi < len(il.meta.methods):
        return False
    injected = il.meta.methods[mi]
    ps = il.meta.method_params(injected)
    if (injected.declaring != owner or not injected.is_static or not injected.iflags & 0x1000 or
            injected.generic_container != -1 or injected.param_count != 1 or len(ps) != 1 or
            not 0 <= ps[0].type < len(il.types) or not 0 <= injected.return_type < len(il.types) or
            any(il._closed_type_key(il.types[t]) != (0x18, 0) for t in (ps[0].type, injected.return_type))):
        return False
    ret = _RETURN.match(data, invoke.end())
    if not ret or not il.bin.is_exec_va(rel(ret, 2)) or addr <= rel(ret, 2) < end or not _unmarshal(il, rel(ret, 1), result, rel(ret, 2)):
        return False
    if inline_throw:
        return (_throw_null_object(il, rel(invoke,3)) and
                _plain_null_exit(lift, addr, data, ret.end(), rel(invoke,1)))
    return _null_exits(lift, addr, data, ret.end(), rel(invoke, 1), rel(invoke, 3))


def _plain_null_exit(lift, addr, data, pos, null):
    if null != addr+pos or data[pos:pos+1] != b'\xe8' or data[pos+5:pos+6] != b'\xcc':
        return False
    target = null+5+int.from_bytes(data[pos+1:pos+5],'little',signed=True)
    return lift._named_raise_throw(target,lift._call_name(target)) == 'System.NullReferenceException'


def _null_exits(lift, addr, data, pos, null, destroyed):
    il = lift.il
    exits = _RAISE.match(data, pos)
    if not exits or null != addr + exits.start() or destroyed != addr + exits.end(1) + 1:
        return False
    raiser, throw = (addr + exits.end(i) + int.from_bytes(exits[i],'little',signed=True) for i in (1,2))
    if lift._named_raise_throw(raiser, lift._call_name(raiser)) != 'System.NullReferenceException':
        return False
    return _throw_null_object(il, throw)


def _throw_null_object(il, throw):
    cands = il.addr_candidates.get(throw, ())
    if len(cands) != 1 or cands[0][0] != 'method' or not 0 <= cands[0][1] < len(il.meta.methods):
        return False
    m = il.meta.methods[cands[0][1]]
    ps = il.meta.method_params(m)
    return (m.addr == throw and m.is_static and m.param_count == 1 and len(ps) == 1 and
            m.generic_container == -1 and il.typedef_full(m.declaring) == 'UnityEngine.Bindings.ThrowHelper' and
            m.name == 'ThrowNullReferenceException' and 0 <= m.return_type < len(il.types) and
            il._closed_type_key(il.types[m.return_type]) == (1, 0) and 0 <= ps[0].type < len(il.types) and
            il._closed_type_key(il.types[ps[0].type]) == (0x1c, 0))
