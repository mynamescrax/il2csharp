"""A frame spill of a captured reference is a snapshot, not another `this`.

The proof is deliberately local to a fixed-frame MoveNext. Follow the edges
that can reach a cleanup reload (including the protected spans), and reject
an overlapping store or an unaccounted-for use of a stack address. In
particular, MSVC passes *pointers* to the state and enumerator to the pad in
a two-word descriptor. A disjoint LEA by itself isn't a disjoint borrow.
"""
from bisect import bisect_right
from collections import defaultdict

from il2cpp.binary import PE
from il2cpp.entrylive import entry_live_args
from il2cpp.prelude import *  # noqa: F401,F403
from il2cpp.text import reg_name, sdisp
from il2cpp.this_home import _fixed_frame

if HAVE_ICED:
    from iced_x86 import InstructionInfoFactory, OpAccess, RegisterExt
    _INFO = InstructionInfoFactory()
    _READ = {OpAccess.READ, OpAccess.COND_READ, OpAccess.READ_WRITE, OpAccess.READ_COND_WRITE}
    _WRITE = {OpAccess.WRITE, OpAccess.COND_WRITE, OpAccess.READ_WRITE, OpAccess.READ_COND_WRITE}


def _stack(i):
    return i.memory_base == IReg.RSP and i.memory_index == IReg.NONE and not i.has_segment_prefix


def _qload(i, base):
    return (i.mnemonic == Mnemonic.MOV and i.op1_kind == OpKind.MEMORY and
            RegisterExt.is_gpr64(i.op0_register) and i.memory_base == base and
            i.memory_index == IReg.NONE and not i.has_segment_prefix)


def _predecessors(insns, eh):
    """Normal edges and actual EH span-to-pad edges, not RPO adjacency."""
    ips = {i.ip for i in insns}
    pred = defaultdict(set)
    lo, hi = insns[0].ip, insns[-1].next_ip
    for i in insns:
        fc = i.flow_control
        if fc == FlowControl.INDIRECT_BRANCH or fc == FlowControl.CALL and lo <= i.near_branch_target < hi:
            return None
        if fc in (FlowControl.CONDITIONAL_BRANCH, FlowControl.UNCONDITIONAL_BRANCH):
            t = i.near_branch_target
            if i.op0_kind != OpKind.NEAR_BRANCH64 or lo <= t < hi and t not in ips:
                return None
            pred[t].add(i.ip)
        if fc in (FlowControl.NEXT, FlowControl.CONDITIONAL_BRANCH, FlowControl.CALL, FlowControl.INDIRECT_CALL):
            pred[i.next_ip].add(i.ip)
    ranges, groups = eh.get('try_ranges') or (), eh.get('try_pads') or ()
    if (not ranges or len(ranges) != len(groups) or
            {p for g in groups for p in g} != set(eh['pads'])):
        return None
    for (_, _, _, spans), pads in zip(ranges, groups):
        if not spans or not pads or any(p not in ips for p in pads):
            return None
        for a, b in spans:
            if a not in ips or b not in ips and b != hi or b <= a:
                return None
            sources = [ip for ip in ips if a <= ip < b]
            for p in pads:
                pred[p].update(sources)
    return pred


def _ancestors(pred, site, stop=None):
    seen, todo = set(), [site]
    while todo:
        ip = todo.pop()
        if ip not in seen and ip != stop:
            seen.add(ip)
            todo.extend(pred[ip] - seen)
    return seen


def _rdi_paths(insns, pred, pads, load, reload):
    """Every non-prologue RDI read must follow one of our two definitions.
    Starting at a pad always loses the incoming register contents."""
    indices = {i.ip:i for i in insns}
    succ = defaultdict(set)
    for ip in indices:
        for prev in pred[ip]:
            succ[prev].add(ip)
    roots = [insns[0].ip, *pads]
    for i in insns:
        if i.ip in (load, reload):
            continue
        if any(r.access in _WRITE and RegisterExt.full_register(r.register) == IReg.RDI
               for r in _INFO.info(i).used_registers()):
            if i.mnemonic != Mnemonic.POP:
                return False
            roots.extend(succ[i.ip])
    seen = set()
    while roots:
        ip = roots.pop()
        if ip in seen or ip in (load, reload):
            continue
        seen.add(ip)
        if ip >= load and any(r.access in _READ and RegisterExt.full_register(r.register) == IReg.RDI
                              for r in _INFO.info(indices[ip]).used_registers()):
            return False
        roots.extend(succ[ip] - seen)
    return True


def _borrow_calls(il, insns, pred):
    """Widths of closed BCL borrows. Prove the hidden MethodRef load reaches
    the call without another entry. For the struct receiver require the same
    closed enumerator as the return buffer, not an open generic size."""
    bounds, enums = {}, {}
    for j, i in enumerate(insns):
        if i.flow_control != FlowControl.CALL or j < 2:
            continue
        target = i.near_branch_target
        lea, hidden = insns[j-1], insns[j-2]
        if not (_stack(lea) and lea.mnemonic == Mnemonic.LEA and lea.op0_register == IReg.RCX and
                pred[i.ip] == {lea.ip} and lea.next_ip == i.ip):
            continue
        # TaskAwaiter.{get_IsCompleted,GetResult} borrow a single Task ref.
        # Require the registered non-generic MethodDef at this actual target.
        for k, mi in il.addr_candidates.get(target, ()):
            if k != 'method':
                continue
            m = il.meta.methods[mi]
            td = il.meta.typedefs[m.declaring]
            if (m.addr == target and not m.is_static and not m.param_count and td.is_valuetype and
                    (td.namespace, td.name) == ('System.Runtime.CompilerServices', 'TaskAwaiter') and
                    m.name in ('get_IsCompleted', 'GetResult') and il.value_type_size(td.index) == 8):
                bounds[i.ip] = (8, False)
        if not (hidden.mnemonic == Mnemonic.MOV and hidden.is_ip_rel_memory_operand and
                pred[lea.ip] == {hidden.ip} and hidden.next_ip == lea.ip):
            continue
        use = il.decode_slot(hidden.ip_rel_memory_address) or {}
        si = use.get('idx', -1)
        if use.get('kind') != 6 or not 0 <= si < len(il.method_specs):
            continue
        mi, ci, gi = il.method_specs[si]
        if not 0 <= mi < len(il.meta.methods) or ci < 0 or gi != -1:
            continue
        m = il.meta.methods[mi]
        td = il.meta.typedefs[m.declaring]
        if m.is_static or m.param_count:
            continue
        if (m.name == 'GetEnumerator' and hidden.op0_register == IReg.R8 and
                (td.namespace, td.name) == ('System.Collections.Generic', 'List`1')):
            rt = il.candidate_return_type(('generic', si))
            et = il.td_of_ty(rt) if rt else None
            if et is not None and il.returns_sret(rt) and il._nested_owner(et) == td.index:
                size = il._sf_field_size(rt, 0)
                if size and il.meta.typedefs[et].name == 'Enumerator':
                    enums[et, ci] = size
                    bounds[i.ip] = (size, True)
        elif (m.name == 'MoveNext' and hidden.op0_register == IReg.RDX and
              (td.index, ci) in enums and il._type_enum(il.types[m.return_type]) == 2):
            bounds[i.ip] = (enums[td.index, ci], False)
    return bounds


def _disjoint(start, width, slot):
    return width > 0 and (start + width <= slot or start >= slot + 8)


def _register_arguments(il, target):
    cands = il.addr_candidates.get(target, ())
    if len(cands) == 1 and cands[0][0] == 'method':
        m = il.meta.methods[cands[0][1]]
        rt = il.types[m.return_type] if 0 <= m.return_type < len(il.types) else None
        if m.addr == target and il._return_abi_is_known(rt):
            return m.param_count + int(not m.is_static) + int(il.returns_sret(rt)) + 1 <= 4
    return entry_live_args(il, target) is not None


def _intact(il, insns, pred, eh, begin, store, reload, slot, depth, runtime_names):
    """Check every path into the reload. Track addresses, including pointer
    lanes copied through xmm registers and stack descriptors. Unknown uses
    of such an address (arithmetic, escapes, partial copies, calls without
    bounded pointees) reject the proof."""
    needed = _ancestors(pred, reload)
    if min(needed) != insns[0].ip or insns[0].ip in _ancestors(pred, reload, store):
        return False  # store must dominate even the exceptional entries
    if begin not in needed or max(needed) != reload:
        return False  # no path from a later epilogue/outer pad back into this reload
    succ = defaultdict(list)
    for p in needed:
        for q in pred[p] & needed:
            succ[q].append(p)
    pads = set(eh['pads'])
    if any(p < begin for p in pads) or any(q < begin for p in needed if p >= begin for q in succ[p]):
        return False
    by_ip = {i.ip:i for i in insns}
    calls = _borrow_calls(il, insns, pred)
    # Keys are (register, byte-lane) or ('stack', offset). Values are offsets
    # relative to framed RSP. Each path carries a separate finite state.
    work, seen = [(begin, {})], set()
    while work:
        ip, state = work.pop()
        key = ip, frozenset(state.items())
        if key in seen or ip == reload:
            continue
        seen.add(key)
        if len(seen) > 4096 or len(state) > 48:
            return False
        i = by_ip[ip]
        info = _INFO.info(i)
        mn, a, b = i.mnemonic, i.op0_kind, i.op1_kind
        fc = i.flow_control
        call = fc == FlowControl.CALL
        if fc == FlowControl.INDIRECT_CALL or i.has_segment_prefix:
            return False
        if _uses_rsp_as_value(i, info, call):
            return False
        width = MemorySizeExt.size(i.memory_size)
        base = reg_name(i.memory_base)
        off = sdisp(i.memory_displacement)
        address = off if base == 'RSP' else None
        if (base, 0) in state:
            address = state[base, 0] + off
        if ((address is not None and i.memory_index != IReg.NONE) or
                (reg_name(i.memory_index), 0) in state):
            return False
        if not i.is_ip_rel_memory_operand and any(
                m.base not in (i.memory_base, IReg.RSP) or m.index != i.memory_index for m in info.used_memory()):
            return False  # implicit memory use outside the tracked operand
        if address is not None and mn != Mnemonic.LEA and ip != store and not _disjoint(address, width, slot):
            return False
        dst, src = reg_name(i.op0_register), reg_name(i.op1_register)
        transfers = {}
        copies = mn in (Mnemonic.MOV, Mnemonic.MOVUPS, Mnemonic.MOVAPS, Mnemonic.MOVSD, Mnemonic.MOVQ)
        if mn == Mnemonic.LEA and address is not None:
            if not RegisterExt.is_gpr64(i.op0_register) or not _disjoint(address, 1, slot):
                return False
            transfers[dst, 0] = address
        elif copies:
            # MOV from/to memory may move an address, not just the data it
            # points at. Reject copying a pointer into untracked memory.
            if b == OpKind.REGISTER:
                lanes = [(k,n) for (r,k),n in state.items() if r == src]
                width_src = RegisterExt.size(i.op1_register) if a != OpKind.MEMORY else width
                if lanes and (width_src < 8 or mn not in (Mnemonic.MOV, Mnemonic.MOVUPS, Mnemonic.MOVAPS)):
                    return False
            elif address is not None and b == OpKind.MEMORY:
                lanes = [(k-address,n) for (r,k),n in state.items() if r == 'stack' and k < address+width and k+8 > address]
                if any(k < 0 or k+8 > width for k,_ in lanes):
                    return False
            else:
                lanes = []
            for k,n in lanes:
                if a == OpKind.REGISTER:
                    transfers[dst,k] = n
                elif address is not None and 0x20 <= address and address + width <= depth:
                    transfers['stack',address+k] = n
                else:
                    return False
        elif not call and mn not in (Mnemonic.CMP, Mnemonic.TEST):
            live_regs = {r for r,_ in state}
            if any(r.access in _READ and reg_name(r.register) in live_regs for r in info.used_registers()):
                return False
            if address is not None and any(r == 'stack' and address < k+8 and k < address+width for r,k in state):
                return False  # unmodelled operation on an address stored in memory
        if call:
            if i.op0_kind != OpKind.NEAR_BRANCH64:
                return False
            borrowed = {r for r,k in state if r in ('RCX','RDX','R8','R9','XMM0','XMM1','XMM2','XMM3')}
            # A no-op Dispose also occurs in the cleanup. It cannot mutate
            # a pointee, even if reached through another descriptor arm.
            noop = _noop(il, i)
            runtime = il.bin.exports.get(i.near_branch_target, runtime_names.get(i.near_branch_target))
            if (not noop and ip > store and ip not in calls and runtime != 'il2cpp_runtime_class_init' and
                    not _register_arguments(il, i.near_branch_target)):
                return False  # unknown stack arguments could overlap the spill or consume a descriptor
            if borrowed and not noop:
                # Managed integer/ref parameters don't consume the duplicate
                # SIMD descriptor in XMM0. All modeled borrows have no XMM
                # arguments; a stack pointer in another GPR is ambiguous.
                if borrowed - {'XMM0','XMM1','XMM2','XMM3'} != {'RCX'} or ip not in calls:
                    return False
                span, sret = calls[ip]
                ptr = state['RCX',0]
                if not _disjoint(ptr, span, slot) or any(r == 'stack' and ptr < k+8 and k < ptr+span for r,k in state):
                    return False
                if sret:
                    transfers['RAX',0] = ptr
            for k in list(state):
                if k[0] in ('RAX','RCX','RDX','R8','R9','R10','R11','XMM0','XMM1','XMM2','XMM3','XMM4','XMM5'):
                    del state[k]
        else:
            for ur in info.used_registers():
                if ur.access in _WRITE:
                    reg = reg_name(ur.register)
                    for k in [k for k in state if k[0] == reg]:
                        if (ur.access != OpAccess.WRITE or RegisterExt.size(ur.register) < 4 or
                                reg.startswith('XMM') and mn not in (Mnemonic.MOVAPS, Mnemonic.MOVUPS)):
                            return False
                        del state[k]
            if address is not None and any(m.access in _WRITE for m in info.used_memory()):
                for k in [k for k in state if k[0] == 'stack' and address < k[1]+8 and k[1] < address+width]:
                    if address > k[1] or address+width < k[1]+8:
                        return False
                    del state[k]
        state.update(transfers)
        for nxt in succ[ip]:
            if nxt in pads:
                # No register is presumed preserved by the dispatcher. Pad
                # prefix must itself be read-only (apart from a no-op call).
                work.append((nxt, {k:v for k,v in state.items() if k[0] == 'stack'}))
            else:
                work.append((nxt, state.copy()))
    return True


def _noop(il, i):
    raw = il.bin.read(i.near_branch_target, 3) or b''
    return raw.startswith(b'\xc3') or raw == b'\xc2\x00\x00'


def _uses_rsp_as_value(i, info, call):
    # No dynamic frame, copying SP or implicit stack writes. The unwind
    # depth is valid everywhere in this slice, including the pad entry.
    return (i.memory_index == IReg.RSP or
            any(i.op_kind(j) == OpKind.REGISTER and RegisterExt.full_register(i.op_register(j)) == IReg.RSP
                for j in range(i.op_count)) or (not call and any(
                RegisterExt.full_register(r.register) == IReg.RSP and r.access in _WRITE for r in info.used_registers())))


def captured_receiver(lift, method, td, insns, eh):
    """(field load, cleanup reload, type) for one unambiguous snapshot."""
    il = lift.il
    if (not eh or il.meta.version != 31 or not td.is_valuetype or method.is_static or method.name != 'MoveNext' or
            not isinstance(il.bin, PE) or not il.bin.is64 or not insns or len(insns) > 1024 or
            not 0 <= method.return_type < len(il.types) or not il.types[method.return_type] or
            il._type_enum(il.types[method.return_type]) != 1):
        return None
    rva = method.addr - il.bin.image_base
    n = bisect_right(il._eh4_begins, rva) - 1
    if n < 0:
        return None
    bg, en, ui = il._eh4_entries[n]
    raw = il.bin.read(il.bin.image_base + ui, 4) or b''
    if bg != rva or insns[0].ip != method.addr or insns[-1].next_ip > il.bin.image_base+en or len(raw) != 4:
        return None
    unwind = il.bin.read(il.bin.image_base+ui, 4+raw[2]*2) or b''
    frame = _fixed_frame(insns, unwind)
    begin = method.addr + raw[1]
    first = next((i for i in insns if i.ip == begin), None)
    if (not frame or frame[2] or not first or first.mnemonic != Mnemonic.MOV or
            (first.op0_register,first.op1_register) != (IReg.RBX,IReg.RCX)):
        return None
    offsets = il.field_offsets[td.index] if 0 <= td.index < len(il.field_offsets) else None
    if not offsets or len(offsets) != td.field_count:
        return None
    rows = [(o,il.meta.fields[fi]) for o,fi in zip(offsets or (),il.meta.type_fields(td))
            if il.meta.fields[fi].name == '<>4__this']
    if len(rows) != 1 or td.flags & 0x18 == 0x10:
        return None
    off, field = rows[0]
    ty = il.types[field.type] if 0 <= field.type < len(il.types) else None
    if (not ty or ty[1] & (0x10 | (1 << 29)) or il._type_enum(ty) != 0x12 or
            sum(n == off for n in offsets) != 1 or il._sf_field_size(ty,0) != 8 or
            (il.instance_field_chain(td.index) or {}).get(off) != (field.name, field.type)):
        return None
    pred = _predecessors(insns, eh)
    if pred is None or any(p >= begin for i in insns if i.ip <= begin for p in pred[i.ip]):
        return None
    for ld, st in zip(insns, insns[1:]):
        if (not _qload(ld,IReg.RBX) or ld.op0_register != IReg.RDI or ld.memory_displacement+0x10 != off or
                ld.next_ip != st.ip or pred[st.ip] != {ld.ip} or not _stack(st) or
                st.mnemonic != Mnemonic.MOV or st.op1_register != IReg.RDI):
            continue
        slot = st.memory_displacement
        local_size = sum(i.immediate(1) for i in insns if i.ip < begin and i.mnemonic == Mnemonic.SUB)
        if not 0x20 <= slot or slot + 8 > local_size or any(
                a <= st.ip for _,_,_,spans in eh['try_ranges'] for a,_ in spans):
            continue
        if any(r.access in _WRITE and RegisterExt.full_register(r.register) == IReg.RBX
               for i in insns if begin < i.ip < ld.ip for r in _INFO.info(i).used_registers()):
            continue
        if any(p >= ld.ip for i in insns if i.ip <= ld.ip for p in pred[i.ip]):
            continue
        reloads = [i for i in insns if _qload(i,IReg.RSP) and i.op0_register == IReg.RDI and i.memory_displacement == slot]
        if len(reloads) != 1 or reloads[0].ip <= st.ip:
            continue
        reload = reloads[0].ip
        # The part of a pad reaching this reload must be read-only. The
        # other handlers are independent roots and must not reach it.
        relevant = _ancestors(pred,reload)
        roots = set(eh['pads']) & relevant
        if len(roots) != 1:
            continue
        pad = roots.pop()
        if (pad <= st.ip or any(i.ip in relevant and pad <= i.ip < reload and
                (any(m.access in _WRITE for m in _INFO.info(i).used_memory()) and i.flow_control != FlowControl.CALL or
                 i.flow_control == FlowControl.CALL and not _noop(il, i)) for i in insns)):
            continue
        if (_rdi_paths(insns, pred, eh['pads'], ld.ip, reload) and
                _intact(il, insns, pred, eh, begin, st.ip, reload, slot, local_size, lift.rt_names)):
            return ld.ip, reload, ty
    return None
