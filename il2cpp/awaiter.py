"""Resolve shared awaiter calls on proven Win64 stack homes."""
import re

from il2cpp.binary import PE
from il2cpp.csharp import FA_LITERAL, FA_STATIC, field_attrs
from il2cpp.entrylive import entry_live_args
from il2cpp.prelude import HAVE_ICED
from il2cpp.text import reg_name, sdisp
from il2cpp.x64 import KLASS_STATIC_FIELDS, KLASS_VTABLE

if HAVE_ICED:
    from iced_x86 import Decoder, FlowControl, InstructionInfoFactory, MemorySizeExt, Mnemonic, OpAccess, OpKind, Register as IReg, RegisterExt


def _bool_getter(il, mi, owner, addr):
    m = il.meta.methods[mi]
    if (m.declaring != owner or m.addr != addr or m.name != 'get_IsCompleted' or m.is_static
            or m.flags & 7 != 6 or m.param_count or m.generic_container != -1
            or not 0 <= m.return_type < len(il.types)):
        return None
    rt = il.types[m.return_type]
    td = il.meta.typedefs[owner]
    props = il.meta.properties[td.property_start:td.property_start + td.property_count]
    if (rt and il._type_enum(rt) == 2 and not rt[1] & (1 << 29) and
            any(p[1] == mi - td.method_start and il.meta.getstr(p[0]) == 'IsCompleted' for p in props)):
        return rt
    return None


def _forwarded_bool(lift, addr, owner):
    il = lift.il
    cands = il.addr_candidates.get(addr, ())
    hits = [mi for kind, mi in cands if kind == 'method' and 0 <= mi < len(il.meta.methods)
            and il.meta.methods[mi].declaring == owner]
    if len(cands) < 2 or len(hits) != 1 or not _bool_getter(il, hits[0], owner, addr):
        return None
    # sub rsp,28h; mov rcx,[rcx]; test rcx,rcx; je null; xor edx,edx;
    # add rsp,28h; jmp Task.get_IsCompleted; null: call nullref; int3.
    if not il.bin.is_exec_va(addr) or il.function_extent(addr) != (addr, addr + 29):
        return None
    code = il.bin.read(addr, 29) or b''
    if (len(code) != 29 or not code.startswith(bytes.fromhex('4883ec28 488b09 4885c9 740b 33d2 4883c428 e9'))
            or code[23] != 0xe8 or code[28] != 0xcc):
        return None
    tail = addr + 23 + int.from_bytes(code[19:23], 'little', signed=True)
    null = addr + 28 + int.from_bytes(code[24:28], 'little', signed=True)
    methods = il.addr_candidates.get(tail, ())
    if (len(methods) != 1 or methods[0][0] != 'method' or
            lift._named_raise_throw(null, lift._call_name(null)) != 'System.NullReferenceException'):
        return None
    mi = methods[0][1]
    if not 0 <= mi < len(il.meta.methods):
        return None
    task = il.meta.methods[mi].declaring
    # The native [rcx] must be the Task field in the unboxed awaiter.
    fields = il.instance_field_chain(owner) or {}
    if (not 0 <= task < len(il.meta.typedefs) or il.typedef_full(task) != 'System.Threading.Tasks.Task' or
            set(fields) != {0x10} or il.value_type_size(owner) != 8 or not 0 <= fields[0x10][1] < len(il.types)):
        return None
    field = il.types[fields[0x10][1]]
    if not field or il._type_enum(field) != 0x12 or field[0] != task or field[1] & (1 << 29):
        return None
    return _bool_getter(il, mi, task, tail)


def _stack_mem(i):
    return i.memory_base == IReg.RSP and i.memory_index == IReg.NONE and not i.has_segment_prefix


def _completion_gate(block, ip):
    if len(block.insns) < 5:
        return None
    clear, lea, check, test, jump = block.insns[-5:]
    if (check.ip != ip or any(a.next_ip != b.ip for a,b in zip(block.insns[-5:-1], block.insns[-4:])) or
            check.mnemonic != Mnemonic.CALL or check.op0_kind != OpKind.NEAR_BRANCH64 or
            clear.mnemonic != Mnemonic.XOR or clear.op0_register != IReg.EDX or clear.op1_register != IReg.EDX or
            lea.mnemonic != Mnemonic.LEA or lea.op0_register != IReg.RCX or not _stack_mem(lea) or test.mnemonic != Mnemonic.TEST or
            test.op0_register != IReg.AL or test.op1_register != IReg.AL or jump.op0_kind != OpKind.NEAR_BRANCH64 or
            jump.mnemonic not in (Mnemonic.JE, Mnemonic.JNE)):
        return None
    return (sdisp(lea.memory_displacement), jump.near_branch_target if jump.mnemonic == Mnemonic.JE else jump.next_ip)


def _home_and_suspend(block, ip):
    """A whole RAX return stored and addressed at the same RSP in one block."""
    gate = _completion_gate(block, ip)
    if not gate or len(block.insns) < 7:
        return None
    producer, store, clear = block.insns[-7:-4]
    if (producer.mnemonic == Mnemonic.CALL and producer.op0_kind == OpKind.NEAR_BRANCH64 and
            producer.next_ip == store.ip and store.next_ip == clear.ip and store.mnemonic == Mnemonic.MOV and
            store.op0_kind == OpKind.MEMORY and store.op1_register == IReg.RAX and _stack_mem(store) and
            sdisp(store.memory_displacement) == gate[0]):
        return gate
    return None


def _class_init_guard(lift, klass, cmp, jne, init, resume, *, eax_zero=False):
    """Both the hot and cold paths reach resume with the same frame."""
    seq = (klass, cmp, jne, init, resume)
    return (all(a.next_ip == b.ip for a,b in zip(seq, seq[1:])) and not any(i.has_segment_prefix for i in seq) and
            klass.mnemonic == Mnemonic.MOV and klass.op0_register == IReg.RCX and klass.is_ip_rel_memory_operand and
            cmp.mnemonic == Mnemonic.CMP and cmp.memory_base == IReg.RCX and cmp.memory_index == IReg.NONE and
            cmp.memory_displacement == 0xe4 and MemorySizeExt.size(cmp.memory_size) == 4 and
            ((cmp.op1_kind in (OpKind.IMMEDIATE8TO32, OpKind.IMMEDIATE32) and cmp.immediate(1) == 0) or
             (eax_zero and cmp.op1_register == IReg.EAX)) and
            jne.mnemonic == Mnemonic.JNE and jne.near_branch_target == resume.ip and
            init.mnemonic == Mnemonic.CALL and init.op0_kind == OpKind.NEAR_BRANCH64 and
            lift._call_name(init.near_branch_target) == 'il2cpp_runtime_class_init')


def _yield_home(lift, block, ip, owner):
    """Byte returned into the YieldAwaiter home before its type-init guard."""
    gate = _completion_gate(block, ip)
    if not gate or len(block.insns) != 5 or block.bid < 2:
        return None
    before, cold = lift._blocks[block.bid-2:block.bid]
    if (len(before.insns) < 5 or len(cold.insns) != 1 or cold.preds != [before.bid] or
            not block.preds or not set(block.preds) <= {before.bid, cold.bid}):
        return None
    producer, store, klass, cmp, jne = before.insns[-5:]
    if (producer.mnemonic != Mnemonic.CALL or producer.op0_kind != OpKind.NEAR_BRANCH64 or
            producer.next_ip != store.ip or store.next_ip != klass.ip or store.mnemonic != Mnemonic.MOV or
            not _stack_mem(store) or store.op0_kind != OpKind.MEMORY or store.op1_register != IReg.AL or
            sdisp(store.memory_displacement) != gate[0] or
            not _class_init_guard(lift, klass, cmp, jne, cold.insns[0], block.insns[0])):
        return None
    usage = lift.il.decode_slot(klass.ip_rel_memory_address) or {}
    if usage.get('kind') == 1 and lift.il._closed_type_key(usage.get('type')) == (0x11, owner, 0):
        return gate
    return None


def _yield_bool(lift, addr, owner):
    # This leaf only clears AL. It does not prove a zero pointer, a zero EAX,
    # or the identity of the other calls sharing its entry. Here the caller
    # consumes AL and separately proves the one-byte YieldAwaiter receiver.
    il = lift.il
    cands = il.addr_candidates.get(addr, ())
    hits = [mi for kind,mi in cands if kind == 'method' and 0 <= mi < len(il.meta.methods)
            and il.meta.methods[mi].declaring == owner]
    if (len(cands) > 1 and len(hits) == 1 and il.value_type_size(owner) == 1 and
            il.bin.is_exec_va(addr) and il.bin.read(addr, 3) in (b'\x32\xc0\xc3', b'\x30\xc0\xc3')):
        return _bool_getter(il, hits[0], owner, addr)
    return None


def _yield_result_member(il, addr, owner):
    cache = il.__dict__.setdefault('_yield_result_members', {})
    key = addr, owner
    if key not in cache:
        cache[key] = None
        # Immediate ret (optionally with zero stack adjustment). No hidden
        # context, receiver access, result definition or other instruction.
        code = il.bin.read(addr, 3) if il.bin.is_exec_va(addr) else None
        cands = il.addr_candidates.get(addr, ())
        if code and (code.startswith(b'\xc3') or code == b'\xc2\x00\x00') and len(cands) > 1:
            hits = [mi for kind, mi in cands if kind == 'method' and 0 <= mi < len(il.meta.methods)
                    and il.meta.methods[mi].declaring == owner]
            if len(hits) == 1:
                m = il.meta.methods[hits[0]]
                if (m.addr == addr and m.name == 'GetResult' and not m.is_static and not m.param_count and
                        m.flags & 7 == 6 and not m.flags & 0x40 and m.generic_container == -1 and
                        0 <= m.return_type < len(il.types) and il._closed_type_key(il.types[m.return_type]) == (1, 0)):
                    cache[key] = ('method', hits[0])
    return cache[key]


def _resume_byte(lift, seq, end_state, disp, owner):
    """Resumption restores <>u__N to the exact home, then clears that field
    and resets the state. No calls, alternate addresses or wider stores."""
    if (len(seq) not in (5, 6) or any(a.next_ip != b.ip for a, b in zip(seq, seq[1:])) or
            any(i.has_segment_prefix or i.memory_index != IReg.NONE for i in seq)):
        return False
    load, store, zero, clear = seq[:4]
    reset = seq[-1]
    base = load.memory_base
    if (base not in (IReg.RBX, IReg.RSI, IReg.RDI, IReg.RBP, IReg.R12, IReg.R13, IReg.R14, IReg.R15) or
            load.mnemonic != Mnemonic.MOVZX or load.op0_register != IReg.EAX or MemorySizeExt.size(load.memory_size) != 1 or
            store.mnemonic != Mnemonic.MOV or not _stack_mem(store) or store.op1_register != IReg.AL or
            sdisp(store.memory_displacement) != disp or zero.mnemonic != Mnemonic.XOR or
            zero.op0_register != IReg.EAX or zero.op1_register != IReg.EAX or clear.mnemonic != Mnemonic.MOV or
            clear.memory_base != base or clear.memory_displacement != load.memory_displacement or clear.op1_register != IReg.AL or
            reset.memory_base != base or reset.memory_displacement != 0):
        return False
    for i in seq[4:]:
        if (i.mnemonic != Mnemonic.MOV or i.op0_kind != OpKind.MEMORY or i.op1_kind != OpKind.IMMEDIATE32 or
                i.immediate32 != 0xffffffff or MemorySizeExt.size(i.memory_size) != 4):
            return False
        if i is not reset:
            off = sdisp(i.memory_displacement)
            if not _stack_mem(i) or off <= disp < off + 4:
                return False
    td = lift._current_td
    state = (end_state or {}).get(reg_name(base))
    if (not td.is_valuetype or not state or state._unk or state.text != 'this' or not state.ty or
            lift.il._type_enum(state.ty) not in (0x11, 0x12) or state.ty[0] != td.index):
        return False
    f = (lift.il.instance_field_chain(td.index) or {}).get(sdisp(load.memory_displacement) + 0x10)
    return bool(f and re.fullmatch(r'<>u__\d+', f[0]) and 0 <= f[1] < len(lift.il.types) and
                lift.il._closed_type_key(lift.il.types[f[1]]) == (0x11, owner, 0))


def _static_reference(il, type_slot, disp):
    """Declared type of one entire, unambiguous static reference slot."""
    usage = il.decode_slot(type_slot) or {}
    ti, ty = usage.get('td'), usage.get('type')
    if (usage.get('kind') != 1 or not isinstance(ti, int) or not 0 <= ti < len(il.meta.typedefs) or
            il._closed_type_key(ty) != (0x12, ti, 0) or ti >= len(il.field_offsets) or disp < 0):
        return None
    td, offsets = il.meta.typedefs[ti], il.field_offsets[ti]
    if (td.is_valuetype or td.generic_container != -1 or td.flags & 0x18 == 0x10 or
            not offsets or len(offsets) != td.field_count):
        return None
    receiver = None
    for fi, off in zip(il.meta.type_fields(td), offsets):
        f = il.meta.fields[fi]
        if not 0 <= f.type < len(il.types) or il.types[f.type] is None:
            return None
        flags = field_attrs(il, f)
        if flags & (FA_LITERAL | FA_STATIC) != FA_STATIC or off >= disp + 8:
            continue
        ft = il.types[f.type]
        width = il._sf_field_size(ft, 0)
        if width is None or width <= 0 or off < 0:
            return None
        if off + width > disp:
            if (receiver is not None or off != disp or width != 8 or il._type_enum(ft) != 0x12 or
                    ft[1] & (1 << 29) or not 0 <= ft[0] < len(il.meta.typedefs)):
                return None
            receiver = ft[0]
    return receiver


def _nullary_dispatch_exit(lift, by_ip, first):
    """On this straight-line non-null arm the old RAX is overwritten and
    the old XMM0 is not an argument. Return the null edge still to explore.
    Match forwards from the overwrite: another edge jumping into the middle
    doesn't inherit the witness."""
    if first.mnemonic != Mnemonic.MOV or first.op0_register != IReg.RAX or first.memory_base != IReg.RIP:
        return None
    seq = [first]
    for _ in range(8):
        i = by_ip.get(seq[-1].next_ip)
        if i is None:
            return None
        seq.append(i)
    first, blob, recv, test, null, klass, ptr, method, call = seq
    def load(i, dst, base):
        return i.mnemonic == Mnemonic.MOV and i.op0_register == dst and i.memory_base == base and i.op1_kind == OpKind.MEMORY
    if (any(i.has_segment_prefix or i.memory_index != IReg.NONE for i in seq) or
            not load(blob, IReg.RCX, IReg.RAX) or blob.memory_displacement != KLASS_STATIC_FIELDS or
            not load(recv, IReg.RCX, IReg.RCX) or test.mnemonic != Mnemonic.TEST or
            test.op0_register != IReg.RCX or test.op1_register != IReg.RCX or null.mnemonic != Mnemonic.JE or
            null.op0_kind != OpKind.NEAR_BRANCH64 or not load(klass, IReg.RDX, IReg.RCX) or klass.memory_displacement or
            not load(ptr, IReg.RAX, IReg.RDX) or not load(method, IReg.RDX, IReg.RDX) or
            method.memory_displacement != ptr.memory_displacement + 8 or call.mnemonic != Mnemonic.CALL or
            call.op0_register != IReg.RAX):
        return None
    il = lift.il
    if il.meta.version != 31:
        return None
    ti = _static_reference(il, first.ip_rel_memory_address, sdisp(recv.memory_displacement))
    index, rem = divmod(sdisp(ptr.memory_displacement) - KLASS_VTABLE, 16)
    if ti is None or rem or not 0 <= index < il.meta.typedefs[ti].vtable_count:
        return None
    td = il.meta.typedefs[ti]
    if (td.is_valuetype or td.generic_container != -1 or td.vtable_start < 0 or
            td.vtable_start + index >= len(il.meta.vtable_methods)):
        return None
    mi = il.vtable_method(ti, index)
    if mi is None or not 0 <= mi < len(il.meta.methods):
        return None
    m = il.meta.methods[mi]
    rt = il.types[m.return_type] if 0 <= m.return_type < len(il.types) else None
    if (m.slot != index or m.is_static or not m.flags & 0x40 or m.param_count or m.generic_container != -1 or
            m.declaring not in il.base_chain_tds(ti) or not il._return_abi_is_known(rt) or
            il.returns_sret(rt) or il._closed_type_key(rt) is None):
        return None
    return null.near_branch_target


def _object_new_abi(lift, target):
    """Does this Win64 allocation entry forward the C API's sole RCX argument?

    The codegen thunk and exported il2cpp_object_new need not have the same
    address. Only credit a jump to the exact core called by the export with
    unchanged inputs; the discovered rt_alloc label alone isn't an ABI proof.
    """
    il = lift.il
    b = getattr(il, 'bin', None)
    if (target != getattr(lift, 'rt_alloc', None) or not isinstance(b, PE) or not b.is64 or
            not b.is_exec_va(target) or il.addr_candidates.get(target)):
        return False
    if b.exports.get(target) == 'il2cpp_object_new':
        return True
    if target in b.exports:
        return False
    exports = [va for va, name in b.exports.items() if name == 'il2cpp_object_new']
    if len(exports) != 1 or not b.is_exec_va(exports[0]):
        return False
    export = exports[0]
    thunk, wrapper = b.read(target, 5) or b'', b.read(export, 18) or b''
    # thunk: jmp core. Export: sub rsp,28h; call core; jmp epilogue;
    # exception result: xor eax,eax; epilogue: add rsp,28h; ret.
    if (len(thunk) != 5 or thunk[0] != 0xe9 or len(wrapper) != 18 or
            wrapper[:5] != bytes.fromhex('4883ec28 e8') or
            wrapper[9:] != bytes.fromhex('eb02 33c0 4883c428 c3')):
        return False
    core = target + 5 + int.from_bytes(thunk[1:], 'little', signed=True)
    return (core == export + 9 + int.from_bytes(wrapper[5:9], 'little', signed=True) and
            not export <= core < export+18 and not target <= core < target+5 and b.is_exec_va(core))


def _shared_integer_body(lift, target):
    """All paths in a short shared callee are integer-only, including the
    bounds-error arms. This establishes no XMM0 *input*, not a new XMM0
    result. The caller must still account for the old lane after the call.
    """
    il = lift.il
    if not isinstance(getattr(il, 'bin', None), PE) or not il.bin.is64 or len(il.addr_candidates.get(target, ())) < 2:
        return False
    lo, hi = il.function_extent(target)
    if lo != target or not 0 < hi-lo <= 128 or not il.bin.is_exec_va(target):
        return False
    data = il.bin.read(lo, hi-lo)
    if not data or len(data) != hi-lo:
        return False
    seq = list(Decoder(64, data, ip=lo))
    ips = {i.ip for i in seq}
    if seq[-1].mnemonic not in (Mnemonic.RET, Mnemonic.INT3) or not any(i.mnemonic == Mnemonic.RET for i in seq):
        return False
    for i in seq:
        if i.flow_control in (FlowControl.CONDITIONAL_BRANCH, FlowControl.UNCONDITIONAL_BRANCH):
            if i.op0_kind != OpKind.NEAR_BRANCH64 or i.near_branch_target not in ips:
                return False
        elif i.mnemonic == Mnemonic.CALL:
            if i.op0_kind != OpKind.NEAR_BRANCH64:
                return False
            dest = i.near_branch_target
            if lo <= dest < hi or not il.bin.is_exec_va(dest):
                return False
            cands = il.addr_candidates.get(dest, ())
            if len(cands) == 1 and cands[0][0] == 'method' and 0 <= cands[0][1] < len(il.meta.methods):
                m = il.meta.methods[cands[0][1]]
                if (m.addr == dest and m.is_static and m.param_count == 0 and m.generic_container == -1 and
                        il.typedef_full(m.declaring) == 'System.ThrowHelper' and m.name.startswith('Throw') and
                        0 <= m.return_type < len(il.types) and il._closed_type_key(il.types[m.return_type]) == (1, 0)):
                    continue
            if not lift._named_raise_throw(dest, lift._call_name(dest)):
                return False
        elif i.mnemonic not in (Mnemonic.MOV, Mnemonic.MOVSXD, Mnemonic.PUSH, Mnemonic.POP, Mnemonic.CMP,
                                Mnemonic.TEST, Mnemonic.ADD, Mnemonic.SUB, Mnemonic.XOR, Mnemonic.RET, Mnemonic.INT3):
            return False
    return True


def _unused_return(lift, after_call):
    """A plain ret does not manufacture a value. Decline if the void caller
    reads a return lane before a definition, even in a different block."""
    by_ip = {i.ip:i for b in lift._blocks for i in b.insns}
    info = InstructionInfoFactory()
    seen, work = set(), [(after_call, 3)]  # RAX and XMM0
    while work:
        ip, live = work.pop()
        if (ip, live) in seen or not live:
            continue
        if ip not in by_ip or len(seen) >= 128:
            return False
        seen.add((ip, live))
        i = by_ip[ip]
        end = getattr(lift, '_parent_lookup_windows', {}).get(ip)
        if end is not None:
            # Fresh RDX MethodInfo + RCX receiver; the reference result is
            # the lookup's own RAX. Continue checking subsequent instructions
            # for an old XMM0 read rather than assuming the lookup kills it.
            work.append((end, live & 2))
            continue
        null = _nullary_dispatch_exit(lift, by_ip, i)
        if null is not None:
            # The non-null path reaches a proved instance call (Win64 RCX:
            # this, RDX: MethodInfo). The null arm hasn't made that call.
            work.append((null, live & 2))
            continue
        for r in info.info(i).used_registers():
            lane = {'RAX':1, 'XMM0':2}.get(reg_name(r.register), 0)
            if lane & live:
                if r.access != OpAccess.WRITE:
                    return False
                if RegisterExt.size(r.register) >= (4 if lane == 1 else 16):
                    live &= ~lane
        fc = i.flow_control
        if fc == FlowControl.CALL and i.op0_kind == OpKind.NEAR_BRANCH64:
            # XMM0 can also be argument zero. A known instance call or
            # static method with a non-FP first parameter doesn't read it.
            if live & 2:
                t = i.near_branch_target
                cands = lift.il.addr_candidates.get(t, ())
                if (not cands and t == getattr(lift, 'rt_value_box', None) and
                        getattr(lift.il.bin, 'exports', {}).get(t) == 'il2cpp_value_box'):
                    # Exported C ABI: (Il2CppClass* klass, void* data).
                    # No implicit read of XMM0; RAX is the new boxed object.
                    continue
                if _object_new_abi(lift, t):
                    # Allocation consumes a class pointer, not XMM0. The
                    # returned RAX belongs to this allocator, not the leaf.
                    continue
                if len(cands) == 1 and cands[0][0] == 'method':
                    m = lift.meta.methods[cands[0][1]]
                    ps = lift.meta.method_params(m)
                    pt = lift.il.types[ps[0].type] if ps and 0 <= ps[0].type < len(lift.il.types) else None
                    gpr = pt and (pt[1] & (1 << 29) or lift.il._type_enum(pt) in (
                        *range(2,12), 0x0e, 0x0f, 0x10, 0x11, 0x12, 0x14, 0x18, 0x19, 0x1c, 0x1d))
                    if m.is_static and m.param_count and not gpr:
                        sig = entry_live_args(lift.il, t)
                        if sig is None or 'x' in sig[0]:
                            return False
                elif lift._call_name(t) not in ('il2cpp_runtime_class_init', 'il2cpp_codegen_initialize_runtime_metadata',
                                                'raise_NullReferenceException'):
                    sig = entry_live_args(lift.il, t)
                    if sig is None or 'x' in sig[0]:
                        if live != 2 or not _shared_integer_body(lift, t):
                            return False
                        work.append((i.next_ip, live))
            continue  # next Win64 call clobbers volatile return lanes
        if fc in (FlowControl.RETURN, FlowControl.EXCEPTION, FlowControl.INTERRUPT):
            continue  # caller is void
        if fc in (FlowControl.CONDITIONAL_BRANCH, FlowControl.UNCONDITIONAL_BRANCH) and i.op0_kind == OpKind.NEAR_BRANCH64:
            if fc == FlowControl.UNCONDITIONAL_BRANCH and i.near_branch_target not in by_ip:
                # A direct, nullary instance void tail takes only RCX (this)
                # and RDX (MethodInfo). Neither return lane feeds this exit.
                t = i.near_branch_target
                cands = getattr(getattr(lift, 'il', None), 'addr_candidates', {}).get(t, ())
                if len(cands) == 1 and cands[0][0] == 'method' and 0 <= cands[0][1] < len(lift.meta.methods):
                    m = lift.meta.methods[cands[0][1]]
                    if (m.addr == t and not m.is_static and not m.param_count and m.generic_container == -1 and
                            0 <= m.return_type < len(lift.il.types) and lift.il._closed_type_key(lift.il.types[m.return_type]) == (1, 0)):
                        continue
                return False
            work.append((i.near_branch_target, live))
        elif fc != FlowControl.NEXT:
            return False
        if fc != FlowControl.UNCONDITIONAL_BRANCH:
            work.append((i.next_ip, live))
    return True


def yield_result(lift, ins, regs, xmm):
    """Match the shared synchronous/resume join, before call argument hints."""
    il = lift.il
    recv = regs[0] if regs else None
    if (not recv or recv._unk or recv.kind != 'ptr' or not re.fullmatch(r'&s_[a-fA-F0-9]+', recv.text) or
            not isinstance(getattr(il, 'bin', None), PE) or not il.bin.is64):
        return None
    slot = recv.text[1:]
    ty = getattr(lift, 'slot_types', {}).get(slot)
    method = getattr(lift, '_current_method', None)
    if (not method or method.is_static or method.name != 'MoveNext' or not 0 <= method.return_type < len(il.types) or
            il._closed_type_key(il.types[method.return_type]) != (1,0) or
            not ty or il._type_enum(ty) != 0x11 or ty[1] & (1 << 29) or lift.stack_map.get(getattr(recv, '_stack_offset', None)) != slot or
            not 0 <= ty[0] < len(il.meta.typedefs) or il.typedef_full(ty[0]) != 'System.Runtime.CompilerServices.YieldAwaitable.YieldAwaiter' or
            il.value_type_size(ty[0]) != 1 or any(e and not e._unk and not re.fullmatch(r'\w+', e.text or '') for e in (*regs[1:], *xmm))):
        return None
    b = getattr(getattr(lift, 'out', None), 'block', None)
    if b is None or b.bid < 2 or len(b.insns) < 3:
        return None
    zero, lea, call = b.insns[:3]
    if (call.ip != ins.ip or call.mnemonic != Mnemonic.CALL or call.op0_kind != OpKind.NEAR_BRANCH64 or
            zero.mnemonic != Mnemonic.XOR or zero.op0_register != IReg.EDX or zero.op1_register != IReg.EDX or
            lea.mnemonic != Mnemonic.LEA or lea.op0_register != IReg.RCX or not _stack_mem(lea) or
            zero.next_ip != lea.ip or lea.next_ip != call.ip):
        return None
    blocks = lift._blocks
    guard, cold = blocks[b.bid-2:b.bid]
    if (len(guard.insns) < 3 or len(cold.insns) != 1 or cold.preds != [guard.bid] or
            not b.preds or not set(b.preds) <= {guard.bid, cold.bid}):
        return None
    disp, join = sdisp(lea.memory_displacement), guard.insns[0].ip
    prefix = guard.insns[:-3]
    if prefix and (prefix[-1].next_ip != guard.insns[-3].ip or not _resume_byte(lift, prefix, guard.end_state, disp, ty[0])):
        return None
    if not _class_init_guard(lift, *guard.insns[-3:], cold.insns[0], zero, eax_zero=bool(prefix)):
        return None
    klass = il.decode_slot(guard.insns[-3].ip_rel_memory_address) or {}
    if klass.get('kind') != 1 or il._closed_type_key(klass.get('type')) != (0x11, ty[0], 0):
        return None
    member = _yield_result_member(il, call.near_branch_target, ty[0])
    if not member or not _unused_return(lift, ins.next_ip):
        return None
    if prefix:
        return member
    if len(guard.preds) != 2:
        return None
    resume = fast = False
    for bid in guard.preds:
        p = blocks[bid]
        jump = p.insns[-1]
        if (jump.mnemonic == Mnemonic.JMP and jump.op0_kind == OpKind.NEAR_BRANCH64 and jump.near_branch_target == join and
                len(p.insns) > 1 and p.insns[-2].next_ip == jump.ip and _resume_byte(lift, p.insns[:-1], p.end_state, disp, ty[0])):
            resume = True
        elif len(p.insns) >= 5:
            getter, _, branch = p.insns[-3:]
            gate = _yield_home(lift, p, getter.ip, ty[0])
            ready = branch.next_ip if branch.mnemonic == Mnemonic.JE else branch.near_branch_target
            if (not gate or gate[0] != disp or gate[1] == join or ready != join or
                    not _yield_bool(lift, getter.near_branch_target, ty[0])):
                return None
            fast = True
        else:
            return None
    return member if resume and fast else None


def _yield_members(il, target, task, awaiter):
    """Equivalent producers only for the fieldless one-byte BCL structs."""
    cache = il.__dict__.setdefault('_yield_members', {})
    key = (target, task, awaiter)
    if key in cache:
        return cache[key]
    outer = il._nested_owner(awaiter)
    pair = []
    if (outer is not None and il.typedef_full(task) == 'System.Threading.Tasks.Task' and
            il.typedef_full(outer) == 'System.Runtime.CompilerServices.YieldAwaitable' and
            il.value_type_size(outer) == 1 and not il.meta.typedefs[outer].has_cctor and
            all(il.meta.typedefs[t].is_valuetype and not il.instance_field_chain(t) for t in (outer, awaiter))):
        for owner, name, static, result in ((task, 'Yield', True, outer), (outer, 'GetAwaiter', False, awaiter)):
            hits = [il.meta.methods[mi] for k,mi in il.addr_candidates[target] if k == 'method'
                    and 0 <= mi < len(il.meta.methods) and il.meta.methods[mi].declaring == owner
                    and il.meta.methods[mi].name == name]
            if len(hits) != 1:
                break
            m = hits[0]
            rt = il.types[m.return_type] if 0 <= m.return_type < len(il.types) else None
            if (m.addr != target or m.is_static != static or m.param_count or m.generic_container != -1 or
                    m.flags & 7 != 6 or m.flags & 0x40 or il._closed_type_key(rt) != (0x11, result, 0)):
                break
            pair.append(rt)
    cache[key] = tuple(pair) if len(pair) == 2 else None
    return cache[key]


def yield_producer(lift, ins, regs, xmm):
    """Type the two AL-only producers when the whole yield sequence agrees.

    Otherwise copy propagation could turn the typed receiver into an object
    temp. Do not apply a zero-byte result type to unrelated owners of the VA.
    """
    il = lift.il
    block = getattr(getattr(lift, 'out', None), 'block', None)
    if (not block or len(block.insns) != 10 or not isinstance(getattr(il, 'bin', None), PE) or
            not il.bin.is64 or not regs or regs[0] is None or regs[0]._unk):
        return None
    clear, factory, save, hidden, borrow, get, _, klass, _, _ = block.insns
    if (ins.ip not in (factory.ip, get.ip) or clear.mnemonic != Mnemonic.XOR or
            clear.op0_register != IReg.ECX or clear.op1_register != IReg.ECX or
            any(i.mnemonic != Mnemonic.CALL or i.op0_kind != OpKind.NEAR_BRANCH64 for i in (factory,get)) or
            factory.near_branch_target != get.near_branch_target or save.mnemonic != Mnemonic.MOV or
            not _stack_mem(save) or save.op0_kind != OpKind.MEMORY or save.op1_register != IReg.AL or
            hidden.mnemonic != Mnemonic.XOR or hidden.op0_register != IReg.EDX or hidden.op1_register != IReg.EDX or
            borrow.mnemonic != Mnemonic.LEA or borrow.op0_register != IReg.RCX or not _stack_mem(borrow) or
            borrow.memory_displacement != save.memory_displacement or
            any(a.next_ip != b.ip for a,b in zip(block.insns, block.insns[1:])) or
            any(e and not e._unk and not re.fullmatch(r'\w+', e.text or '') for e in (*regs[1:], *xmm))):
        return None
    blocks, bid = lift._blocks, block.bid
    if not 2 <= bid < len(blocks)-2:
        return None
    pre, init, check = blocks[bid-2], blocks[bid-1], blocks[bid+2]
    if (len(pre.insns) < 3 or len(init.insns) != 1 or init.preds != [pre.bid] or
            not block.preds or not set(block.preds) <= {pre.bid, init.bid} or
            not _class_init_guard(lift, *pre.insns[-3:], init.insns[0], clear) or len(check.insns) != 5):
        return None
    typeinfo = il.decode_slot(pre.insns[-3].ip_rel_memory_address) or {}
    yinfo = il.decode_slot(klass.ip_rel_memory_address) if klass.is_ip_rel_memory_operand else None
    if (typeinfo.get('kind') != 1 or not yinfo or yinfo.get('kind') != 1 or
            any(not isinstance(t.get('td'), int) or not 0 <= t['td'] < len(il.meta.typedefs) for t in (typeinfo,yinfo))):
        return None
    owner = yinfo['td']
    if (il.typedef_full(owner) != 'System.Runtime.CompilerServices.YieldAwaitable.YieldAwaiter' or
            check.insns[2].near_branch_target != get.near_branch_target):
        return None
    gate = _yield_home(lift, check, check.insns[2].ip, owner)
    if not gate or gate[0] == sdisp(save.memory_displacement) or not _yield_bool(lift, get.near_branch_target, owner):
        return None
    if not any(_saved_awaiter(lift, blocks[k], gate[0], owner, 1) for k in check.succs
               if k >= 0 and blocks[k].insns[0].ip == gate[1]):
        return None
    types = _yield_members(il, get.near_branch_target, typeinfo['td'], owner)
    if not types:
        return None
    if ins.ip == factory.ip and regs[0].text == '0':
        return 'System.Threading.Tasks.Task.Yield() /* shared implementation */', types[0]
    slot = regs[0].text[1:]
    if (ins.ip == get.ip and regs[0].kind == 'ptr' and re.fullmatch(r'&s_[a-fA-F0-9]+', regs[0].text) and
            lift.stack_map.get(getattr(regs[0], '_stack_offset', None)) == slot and
            getattr(lift.stack_values.get(slot), 'ty', None) == types[0]):
        return slot + '.GetAwaiter() /* shared implementation */', types[1]
    return None


def _spec_entry(il, si, mi):
    # A MethodRef in R9 alone could be stale. The v31 registration row
    # carries an explicit methodIndex into genericMethodPointers; its row
    # ordinal need not equal that index. Index once per builder MethodDef,
    # not once per async state machine. Conflicting rows are not evidence.
    cache = il.__dict__.setdefault('_awaiter_spec_indices', {})
    if mi not in cache:
        indices = {}
        for spec, index, _, _ in il.generic_method_table_list:
            if 0 <= spec < len(il.method_specs) and il.method_specs[spec][0] == mi:
                if indices.setdefault(spec, index) != index:
                    indices[spec] = -1
        cache[mi] = indices
    index = cache[mi].get(si, -1)
    if 0 <= index < il.generic_method_pointers_count:
        return il.bin.qword(il.generic_method_pointers + 8 * index)
    return None


def _builder_signature(il, target, method_slot, type_slot, builder_ty, owner, state):
    """A closed instance AwaitUnsafeOnCompleted(ref TAwaiter, ref TStateMachine)."""
    usage = il.decode_slot(method_slot) or {}
    si = usage.get('idx', -1)
    if usage.get('kind') != 6 or not 0 <= si < len(il.method_specs) or il.meta.version != 31:
        return False
    mi, ci, gi = il.method_specs[si]
    if not 0 <= mi < len(il.meta.methods):
        return False
    m = il.meta.methods[mi]
    if (m.name != 'AwaitUnsafeOnCompleted' or m.is_static or m.generic_container < 0 or
            m.param_count != 2 or not 0 <= m.return_type < len(il.types) or
            il._closed_type_key(il.types[m.return_type]) != (1, 0) or il.td_of_ty(builder_ty) != m.declaring or
            il.typedef_full(m.declaring) not in ('System.Runtime.CompilerServices.AsyncTaskMethodBuilder',
                                                'System.Runtime.CompilerServices.AsyncTaskMethodBuilder`1')):
        return False
    klass = il.decode_slot(type_slot) or {}
    bk = il._closed_type_key(builder_ty)
    if not bk or klass.get('kind') != 1 or il._closed_type_key(klass.get('type')) != bk:
        return False
    if ci != -1:
        ca = il._method_spec_type_args(ci)
        if not ca or bk[0] != 0x15 or bk[2] != tuple(il._closed_type_key(a) for a in ca):
            return False
    elif bk[0] != 0x11:
        return False
    args = il._method_spec_type_args(gi)
    if not args or tuple(il._closed_type_key(a) for a in args) != ((0x11, owner, 0), (0x11, state, 0)):
        return False
    params = il.meta.method_params(m)
    if len(params) != 2:
        return False
    for ordinal, p in enumerate(params):
        pt = il.types[p.type] if 0 <= p.type < len(il.types) else None
        if (not pt or il._type_enum(pt) != 0x1e or not pt[1] & (1 << 29) or
                not 0 <= pt[0] < len(il.meta.generic_parameters)):
            return False
        gp = il.meta.generic_parameters[pt[0]]
        if (gp[0], gp[4]) != (m.generic_container, ordinal):
            return False
    return _spec_entry(il, si, mi) == target


def _builder_borrow(lift, block, put_idx, disp, owner):
    """Confirm the *type* of a merged state pointer via the suspension call.

    Follow the native fall-through and the optional class initialization's
    taken edge. Both must reach the same call setup, with no intervening
    mutation/escape of the awaiter home. Don't relabel the merged base `this`.
    """
    blocks = getattr(lift, '_blocks', ())
    bid = getattr(block, 'bid', -1)
    if not 0 <= bid < len(blocks)-2 or blocks[bid] is not block:
        return False
    guard, init, setup = block.insns[put_idx+1:], blocks[bid+1].insns, blocks[bid+2].insns[:5]
    put = block.insns[put_idx]
    # A one-byte YieldAwaiter contains no managed reference. Its field
    # store goes directly to builder setup, without a GC write barrier.
    has_barrier = put.op1_register == IReg.RAX
    if len(guard) != (6 if has_barrier else 3) or len(init) != 1 or len(setup) != 5:
        return False
    seq = [put, *guard, *init, *setup]
    if any(a.next_ip != b.ip for a,b in zip(seq, seq[1:])) or any(i.has_segment_prefix for i in seq):
        return False
    klass, cmp, jne = guard[-3:]
    method, byref_state, byref_awaiter, builder, call = setup
    state = put.memory_base
    def address(i, dest, base):
        return i.mnemonic == Mnemonic.LEA and i.op0_register == dest and i.memory_base == base and i.memory_index == IReg.NONE
    def slot_load(i, dest):
        return i.mnemonic == Mnemonic.MOV and i.op0_register == dest and i.is_ip_rel_memory_operand
    def direct(i):
        return i.mnemonic == Mnemonic.CALL and i.op0_kind == OpKind.NEAR_BRANCH64
    if has_barrier:
        field, clear, barrier = guard[:3]
        if (not address(field, IReg.RCX, state) or field.memory_displacement != put.memory_displacement or
                clear.mnemonic != Mnemonic.XOR or clear.op0_register != IReg.EDX or clear.op1_register != IReg.EDX or
                not direct(barrier) or barrier.near_branch_target not in lift.rt_wbarrier):
            return False
    if not _class_init_guard(lift, klass, cmp, jne, init[0], method):
        return False
    if (not slot_load(method,IReg.R9) or byref_state.mnemonic != Mnemonic.MOV or
            byref_state.op0_register != IReg.R8 or byref_state.op1_register != state or
            not address(byref_awaiter,IReg.RDX,IReg.RSP) or sdisp(byref_awaiter.memory_displacement) != disp or
            not address(builder,IReg.RCX,state) or not direct(call) or not lift.il.bin.is_exec_va(call.near_branch_target)):
        return False
    ti = lift._current_td.index
    f = (lift.il.instance_field_chain(ti) or {}).get(sdisp(builder.memory_displacement) + 0x10)
    return bool(f and f[0] == '<>t__builder' and 0 <= f[1] < len(lift.il.types) and
                _builder_signature(lift.il, call.near_branch_target, method.ip_rel_memory_address, klass.ip_rel_memory_address,
                                   lift.il.types[f[1]], owner, ti))


def _saved_awaiter(lift, suspended, disp, owner, width=8):
    """Independent type witness: the false arm saves this value to the state
    machine's declared <>u__N awaiter field before making any further call."""
    td = lift._current_td
    if not td.is_valuetype:
        return False
    nonvolatile = (IReg.RBX, IReg.RBP, IReg.RSI, IReg.RDI, IReg.R12, IReg.R13, IReg.R14, IReg.R15)
    state_reg = None
    for j, i in enumerate(suspended.insns[:-1]):
        if i.memory_index != IReg.NONE or i.has_segment_prefix:
            return False
        if i.op0_kind == OpKind.MEMORY:
            # Only initial state bookkeeping, never another write to our home.
            if _stack_mem(i) and not (sdisp(i.memory_displacement) + 4 <= disp or
                                      disp + width <= sdisp(i.memory_displacement)):
                return False
            if i.mnemonic != Mnemonic.MOV or MemorySizeExt.size(i.memory_size) != 4:
                return False
            if not _stack_mem(i):
                if i.memory_base not in nonvolatile or state_reg not in (None,i.memory_base) or i.memory_displacement != 0:
                    return False
                state_reg = i.memory_base
            continue
        put = suspended.insns[j + 1]
        load, dest, source = ((Mnemonic.MOVZX, IReg.EAX, IReg.AL) if width == 1 else
                              (Mnemonic.MOV, IReg.RAX, IReg.RAX))
        if (i.mnemonic != load or not _stack_mem(i) or i.op0_register != dest or
                MemorySizeExt.size(i.memory_size) != width or sdisp(i.memory_displacement) != disp or
                put.mnemonic != Mnemonic.MOV or put.op0_kind != OpKind.MEMORY or put.op1_register != source or
                put.memory_index != IReg.NONE or put.has_segment_prefix or i.next_ip != put.ip):
            return False
        if put.memory_base not in nonvolatile or state_reg not in (None,put.memory_base):
            return False
        f = (lift.il.instance_field_chain(td.index) or {}).get(sdisp(put.memory_displacement) + 0x10)
        if not f or not re.fullmatch(r'<>u__\d+', f[0]) or not 0 <= f[1] < len(lift.il.types):
            return False
        ft = lift.il.types[f[1]]
        if not ft or ft[0] != owner or lift.il._type_enum(ft) != 0x11 or ft[1] & (1 << 29):
            return False
        base = dict.get(lift.regs, reg_name(put.memory_base))
        if (not base or base._unk or not base.ty or lift.il._type_enum(base.ty) not in (0x11, 0x12) or
                base.ty[0] != td.index):
            return False
        return base.text == 'this' or _builder_borrow(lift, suspended, j+1, disp, owner)
    return False


def awaiter_completion(lift, ins, regs, xmm):
    il = lift.il
    recv = regs[0] if regs else None
    if (not recv or recv._unk or recv.kind != 'ptr' or not re.fullmatch(r'&s_[a-fA-F0-9]+', recv.text) or
            not isinstance(getattr(il, 'bin', None), PE) or not il.bin.is64):
        return None
    slot = recv.text[1:]
    block = getattr(getattr(lift, 'out', None), 'block', None)
    if not block or lift.stack_map.get(getattr(recv, '_stack_offset', None)) != slot:
        return None
    yield_name = 'System.Runtime.CompilerServices.YieldAwaitable.YieldAwaiter'
    value = getattr(lift, 'stack_values', {}).get(slot)
    ty = value.ty if value is not None and not value._unk and value.kind == 'obj' else None
    if not ty or ty[1] & (1 << 29) or il._type_enum(ty) != 0x11 or not 0 <= ty[0] < len(il.meta.typedefs):
        return None
    full = il.typedef_full(ty[0])
    is_yield = full == yield_name
    if not is_yield and full != 'System.Runtime.CompilerServices.TaskAwaiter':
        return None
    owner = ty[0]
    if not il.meta.typedefs[owner].is_valuetype or il.meta.typedefs[owner].generic_container != -1:
        return None
    site = _yield_home(lift, block, ins.ip, owner) if is_yield else _home_and_suspend(block, ins.ip)
    if not site or any(e and not e._unk and not re.fullmatch(r'\w+', e.text or '') for e in (*regs[1:], *xmm)):
        return None
    disp, slow = site
    if not any(_saved_awaiter(lift, b, disp, owner, 1 if is_yield else 8) for b in (lift._blocks[k] for k in block.succs if k >= 0)
               if b.insns and b.insns[0].ip == slow):
        return None
    key = ins.near_branch_target, owner
    cache = il.__dict__.setdefault('_awaiter_forwarders', {})
    if key not in cache:
        cache[key] = (_yield_bool if is_yield else _forwarded_bool)(lift, *key)
    return (slot + '.IsCompleted', cache[key]) if cache[key] else None
