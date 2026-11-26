"""Prove which freshly allocated SZARRAY reaches a native bounds check."""
from bisect import bisect_right
from struct import pack

from il2cpp.binary import PE
from il2cpp.prelude import HAVE_ICED

if HAVE_ICED:
    from iced_x86 import (FlowControl as F, InstructionInfoFactory, Mnemonic as M,
                          OpAccess, OpKind as K, Register as R, RegisterExt)
    _INFO = InstructionInfoFactory()
    _WRITES = {OpAccess.WRITE, OpAccess.COND_WRITE, OpAccess.READ_WRITE, OpAccess.READ_COND_WRITE}
    _SAVED = {R.RBX, R.RBP, R.RSI, R.RDI, R.R12, R.R13, R.R14, R.R15}


def _reachable(edges, roots):
    work, seen = list(roots), set()
    while work:
        ip = work.pop()
        if ip not in seen:
            seen.add(ip)
            work.extend(edges[ip])
    return seen


def _graph(il, seq, *, allow_tail=False, runtime_tails=(), chained=False):
    """Instruction edges, including both arms of every skipped init guard."""
    lo, hi = seq[0].ip, seq[-1].next_ip
    if il.eh_regions(lo):
        return None
    # eh_regions also returns None for an unrecognized handler. Require an
    # exact runtime-function entry and plain unwind info (no handler/chain).
    image = il.bin.image_base
    n = bisect_right(getattr(il, '_eh4_begins', ()), lo - image) - 1
    if n < 0:
        return None
    start, end, unwind = il._eh4_entries[n]
    header = il.bin.read(image + unwind, 4) or b''
    if (lo != image + start or len(header) != 4 or header[0] != 1 or
            any(a.next_ip > b.ip for a, b in zip(seq, seq[1:]))):
        return None
    parent=pack('<III',start,end,unwind)
    while chained and image+end<hi and n+1<len(il._eh4_entries):
        n+=1;entry,stop,ui=il._eh4_entries[n];h=il.bin.read(image+ui,4) or b''
        if (entry!=end or stop<=entry or len(h)!=4 or h[0]!=0x21 or
                il.bin.read(image+ui+4+2*((h[2]+1)&~1),12)!=parent):return None
        end=stop
    if hi!=image+end:return None

    pred = {i.ip: [] for i in seq}
    succ = {}
    for i in seq:
        if i.is_invalid or i.ip != lo and i.ip in il.addr_candidates:
            return None
        fc = i.flow_control
        if fc == F.NEXT:
            edges = (i.next_ip,)
        elif fc == F.CALL and i.mnemonic == M.CALL and i.op0_kind == K.NEAR_BRANCH64:
            if lo <= i.near_branch_target < hi or not il.bin.is_exec_va(i.near_branch_target):
                return None
            edges = (i.next_ip,)
        elif fc in (F.CONDITIONAL_BRANCH, F.UNCONDITIONAL_BRANCH) and i.op0_kind == K.NEAR_BRANCH64:
            edges = ((i.near_branch_target, i.next_ip) if fc == F.CONDITIONAL_BRANCH else (i.near_branch_target,))
            if (allow_tail and fc==F.UNCONDITIONAL_BRANCH and not lo<=i.near_branch_target<hi and
                    (i.near_branch_target in il.addr_candidates or i.near_branch_target in runtime_tails) and il.bin.is_exec_va(i.near_branch_target)):
                edges=()  # known tail exit: it cannot feed a later lookup
        elif i.mnemonic in (M.RET, M.INT3, M.UD2):
            edges = ()
        else:
            return None  # an indirect transfer could enter with unknown registers
        for dest in edges:
            if dest not in pred:
                return None
            pred[dest].append(i.ip)
        succ[i.ip] = edges
    if len(_reachable(succ, [lo])) != len(seq):
        return None  # disconnected roots are not ordinary entry paths
    return pred, succ


def _definitions(insns, pred, entry, site, register):
    """All reaching definitions, looking through full-width GPR copies only.

    A cycle isn't a definition: keep visiting its other incoming edges.
    Reaching the method entry without a definition invalidates the proof.
    """
    work, seen, defs = [(site, register)], set(), set()
    while work:
        ip, reg = work.pop()
        if (ip, reg) in seen:
            continue
        if ip == entry or reg == R.RSP:
            return set()
        seen.add((ip, reg))
        for p in pred[ip]:
            i = insns[p]
            if i.mnemonic == M.CALL and reg not in _SAVED:
                defs.add((p, reg))
            elif (i.mnemonic == M.MOV and i.op0_kind == i.op1_kind == K.REGISTER and
                  i.op0_register == reg and RegisterExt.is_gpr64(i.op1_register)):
                work.append((p, i.op1_register))
            elif any(u.access in _WRITES and RegisterExt.full_register(u.register) == reg
                     for u in _INFO.info(i).used_registers()):
                defs.add((p, reg))
            else:
                work.append((p, reg))
    return defs


def _concrete(il, key):
    """A closed signature key may still name a bare generic TypeDef or a
    byref. Neither describes an allocatable element of a managed vector."""
    if not key or key[-1] != 0:
        return False
    te = key[0]
    if te in (0x1d, 0x14):
        return (te != 0x14 or key[2] > 0) and _concrete(il, key[1])
    if te == 0x0f:
        return key[1] == (1, 0) or _concrete(il, key[1])
    if te in (0x11, 0x12, 0x15):
        base = key[1] if te == 0x15 else key
        if base[0] not in (0x11, 0x12) or base[-1] or not 0 <= base[1] < len(il.meta.typedefs):
            return False
        td = il.meta.typedefs[base[1]]
        if bool(td.is_valuetype) != (base[0] == 0x11):
            return False
        if te != 0x15:
            return td.generic_container == -1
        if not 0 <= td.generic_container < len(il.meta.generic_containers):
            return False
        owner, argc, method, _ = il.meta.generic_containers[td.generic_container]
        return (owner == base[1] and not method and argc == len(key[2]) > 0 and
                all(_concrete(il, arg) for arg in key[2]))
    return 2 <= te <= 0x0e or te in (0x18, 0x19, 0x1c)


def array_origin(lift, blocks, bid, base, *, through=None):
    """Return the concrete type tuple of the one allocation held at the CMP."""
    il = lift.il
    if (not HAVE_ICED or base not in _SAVED or not 0 <= bid < len(blocks) or
            not isinstance(getattr(il, 'bin', None), PE) or not il.bin.is64 or
            not getattr(lift, 'rt_arrnew', None) or getattr(lift, '_ref_array_pads', ())):
        return None
    check = blocks[bid].insns
    if (len(check) < 2 or check[-2].mnemonic != M.CMP or check[-2].memory_base != base or
            check[-2].next_ip != check[-1].ip or check[-1].mnemonic != M.JAE):
        return None
    seq = [i for b in blocks for i in b.insns]
    method = getattr(lift, '_current_method', None)
    if len(seq) > 4096 or not method or method.addr != seq[0].ip:
        return None
    graph = _graph(il, seq)
    if not graph:
        return None
    pred, succ = graph
    insns = {i.ip: i for i in seq}
    if through is not None:
        # No raw entry after the length compare may skip the check, the
        # index calculation, or either part of the sret setup.
        p=check[-2]
        while p.ip<through:
            q=insns.get(p.next_ip)
            if q is None or pred[q.ip]!=[p.ip]:return None
            p=q
        if p.ip!=through:return None
    defs = _definitions(insns, pred, method.addr, check[-2].ip, base)
    if len(defs) != 1:
        return None
    ip, reg = defs.pop()
    call = insns[ip]
    if (reg != R.RAX or call.mnemonic != M.CALL or call.near_branch_target not in lift.rt_arrnew or
            call.near_branch_target in il.addr_candidates or ip in _reachable(succ, succ[ip])):
        return None  # two executions of one allocation site are distinct objects, too

    result = None
    for p, reg in _definitions(insns, pred, method.addr, ip, R.RCX):
        load = insns[p]
        if (load.mnemonic != M.MOV or load.op0_kind != K.REGISTER or load.op0_register != reg or
                load.op1_kind != K.MEMORY or load.memory_base != R.RIP or load.has_segment_prefix):
            return None
        slot = il.decode_slot(load.ip_rel_memory_address) or {}
        ty, idx = slot.get('type'), slot.get('idx', -1)
        if (slot.get('kind') != 1 or not 0 <= idx < len(il.types) or not ty or ty != il.types[idx] or
                il._type_enum(ty) != 0x1d or not _concrete(il, il._closed_type_key(ty)) or
                result is not None and result != ty):
            return None
        result = ty
    return result
