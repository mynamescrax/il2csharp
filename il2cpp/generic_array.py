"""Close a reference-array producer from its actual Win64 MethodRef argument."""
from il2cpp.binary import PE
from il2cpp.names import safe_ident
from il2cpp.prelude import HAVE_ICED

if HAVE_ICED:
    from iced_x86 import InstructionInfoFactory, Mnemonic as M, OpAccess, OpKind as K, Register as R, RegisterExt
    _INFO = InstructionInfoFactory()
    _WRITE = (OpAccess.WRITE, OpAccess.COND_WRITE, OpAccess.READ_WRITE, OpAccess.READ_COND_WRITE)


def object_shared_entry(il, mi):
    """Code registered for M<object>. The method index is explicit in v31;
    it isn't necessarily the ordinal of the generic method table row."""
    cache = il.__dict__.setdefault('_object_shared_entries', {})
    if mi not in cache:
        indices = set()
        for spec, index, _, _ in il.generic_method_table_list:
            if 0 <= spec < len(il.method_specs) and il.method_specs[spec][:2] == (mi, -1):
                actual = il._method_spec_type_args(il.method_specs[spec][2])
                if actual and len(actual) == 1 and il._closed_type_key(actual[0]) == (0x1c, 0):
                    indices.add(index)
        index = indices.pop() if len(indices) == 1 else -1
        cache[mi] = (il.bin.qword(il.generic_method_pointers + 8*index)
                     if 0 <= index < il.generic_method_pointers_count else None)
    return cache[mi]


def _saved_array_loads(blocks, b, call_idx, pads):
    """Loads reached ONLY with the returned array in the memory base.
    Follow cold edges as well as back edges. Unlike the type hint at a loop
    phi, a missing predecessor definition here cannot be filled by a known
    sibling. Stop tracking on any write (even partial) of the saved GPR.
    """
    if pads or len(blocks) > 512:
        return set()
    end = b.insns[call_idx].next_ip
    for i in b.insns[call_idx+1:]:
        if i.ip != end:
            return set()
        if (i.mnemonic == M.MOV and i.op1_register == R.RAX and
                i.op0_register in (R.RBX, R.RBP, R.RSI, R.RDI, R.R12, R.R13, R.R14, R.R15)):
            saved, copy = i.op0_register, i.ip
            break
        if (i.mnemonic != M.XOR or i.op0_register != i.op1_register or
                not RegisterExt.is_gpr32(i.op0_register) or i.op0_register in (R.EAX, R.ESP)):
            return set()
        end = i.next_ip
    else:
        return set()
    visits, good, bad, work = set(), set(), set(), [(0,False)]
    while work:
        bid, holds = work.pop()
        if (bid, holds) in visits:
            continue
        visits.add((bid, holds))
        for i in blocks[bid].insns:
            if i.memory_base == saved and i.memory_index != R.NONE and i.mnemonic == M.MOV:
                (good if holds else bad).add(i.ip)
            if i.ip == copy:
                holds = True
            elif holds and any(r.access in _WRITE and RegisterExt.full_register(r.register) == saved
                               for r in _INFO.info(i).used_registers()):
                holds = False
        work.extend((s, holds) for s in blocks[bid].succs if s >= 0)
    return good - bad


def ref_array_call(lift, ins, info, regs, xmm):
    """M<T>(bool) returning its own T[]. No inference from a later use of
    the result. Both the MethodRef's closed element and its code entry must
    agree, and the receiver, bool and context must arrive in ABI order."""
    il = lift.il
    if (not isinstance(getattr(il, 'bin', None), PE) or not il.bin.is64 or getattr(il.meta, 'version', None) != 31 or
            ins.op0_kind != K.NEAR_BRANCH64 or len(regs) != 4):
        return None
    recv, flag, context, extra = regs
    si = info[1]
    if (not 0 <= si < len(il.method_specs) or not recv or recv._unk or recv.kind != 'obj' or not recv.ty or recv.ty[1] & (1 << 29) or
            not 0 <= recv.ty[0] < len(il.meta.typedefs) or
            il._type_enum(recv.ty) != 0x12 or not flag or flag._unk or
            not context or context._unk or getattr(context, '_usg_idx', None) != si or
            (extra and not extra._unk) or any(e and not e._unk for e in xmm)):
        return None
    mi, ci, gi = il.method_specs[si]
    if not 0 <= mi < len(il.meta.methods):
        return None
    m = il.meta.methods[mi]
    sig = il.types[m.return_type] if 0 <= m.return_type < len(il.types) else None
    if (ci != -1 or gi < 0 or m.is_static or m.flags & 0x40 or m.flags & 7 != 6 or
            m.generic_container < 0 or m.param_count != 1 or not sig or il._type_enum(sig) != 0x1d or
            sig[1] & (1 << 29) or not 0 <= m.declaring < len(il.meta.typedefs) or
            il.meta.typedefs[m.declaring].generic_container >= 0):
        return None
    ps = il.meta.method_params(m)
    if len(ps) != 1 or not 0 <= ps[0].type < len(il.types) or il._closed_type_key(il.types[ps[0].type]) != (2, 0):
        return None
    elem = il.type_from_ptr(sig[0])
    if (not elem or il._type_enum(elem) != 0x1e or elem[1] & (1 << 29) or
            not 0 <= elem[0] < len(il.meta.generic_parameters)):
        return None
    gp = il.meta.generic_parameters[elem[0]]
    args = il._method_spec_type_args(gi)
    if (not 0 <= m.generic_container < len(il.meta.generic_containers) or
            tuple(il.meta.generic_containers[m.generic_container]) != (mi, 1, 1, elem[0]) or
            (gp[0], gp[4]) != (m.generic_container, 0) or not args or len(args) != 1 or
            not args[0] or il._type_enum(args[0]) != 0x12 or args[0][1] & (1 << 29) or
            not 0 <= args[0][0] < len(il.meta.typedefs)):
        return None
    chain = il.base_chain_tds(recv.ty[0])
    if (m.declaring not in chain or safe_ident(m.name) != m.name or
            any(il.meta.methods[j].name == m.name for t in chain[:chain.index(m.declaring)]
                for j in il.meta.type_methods(il.meta.typedefs[t]))):
        return None
    # Require uninterrupted native setup in one block, not a stale usage
    # slot left in a volatile register by an unrelated call.
    b = getattr(getattr(lift, 'out', None), 'block', None)
    if not b:
        return None
    j = next((j for j,i in enumerate(b.insns) if i.ip == ins.ip), -1)
    if j < 3:
        return None
    load, boolean, receiver, call = b.insns[j-3:j+1]
    if (load.next_ip != boolean.ip or boolean.next_ip != receiver.ip or receiver.next_ip != call.ip or
            load.mnemonic != M.MOV or load.op0_register != R.R8 or load.memory_base != R.RIP or load.has_segment_prefix or
            boolean.mnemonic != M.MOV or boolean.op0_register != R.DL or boolean.op1_kind != K.IMMEDIATE8 or
            boolean.immediate8 not in (0,1) or str(boolean.immediate8) != flag.text or
            receiver.mnemonic != M.MOV or receiver.op0_register != R.RCX or receiver.op1_kind != K.REGISTER):
        return None
    usage = il.decode_slot(load.ip_rel_memory_address) or {}
    if usage.get('kind') != 6 or usage.get('idx') != si or object_shared_entry(il, mi) != ins.near_branch_target:
        return None
    closed = lift._closed_szarray_row(args[0])
    if closed and il._closed_type_key(closed) == (0x1d, il._closed_type_key(args[0]), 0):
        sites = _saved_array_loads(lift._blocks, b, j, lift._ref_array_pads)
        lift._ref_array_loads.update((ip, closed) for ip in sites)
        return closed, m.name + '<' + il.type_name(args[0]) + '>'
    return None
