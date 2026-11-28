"""Adjacent TEST/Jcc on a low byte of a registered scalar return.

Keep the producer evaluation at the call. A move saving its result for a
second test does not authorize polling the producer a second time.
"""
from il2cpp.array_origin import _definitions, _graph, _reachable
from il2cpp.equivalent_binary import _amd64
from il2cpp.metadata import source_params
from il2cpp.names import safe_ident
from il2cpp.prelude import HAVE_ICED
from il2cpp.text import reg_name

if HAVE_ICED:
    from il2cpp.array_origin import _INFO, _WRITES
    from iced_x86 import Mnemonic as M, OpKind as K, Register as R, RegisterExt as RX


def _low(r):
    return RX.is_gpr8(r) and r not in (R.AH, R.BH, R.CH, R.DH)


def _result(il, call, te):
    if not call.is_call_near:
        return None
    ids = il.addr_candidates.get(call.near_branch_target, ())
    if len(ids) != 1 or ids[0][0] != 'method' or not 0 <= ids[0][1] < len(il.meta.methods):
        return None
    m = il.meta.methods[ids[0][1]]
    if (m.addr == call.near_branch_target and m.generic_container == -1 and
            0 <= m.return_type < len(il.types) and il._closed_type_key(il.types[m.return_type]) == (te, 0)):
        return m.index


def _saved_argument(il, method, seq, by, pred, test):
    reg = RX.full_register(test.op0_register)
    defs = _definitions(by, pred, method.addr, test.ip, reg)
    if len(defs) != 1:
        return None
    pos, dst = defs.pop()
    save = by[pos]
    slots = (R.CL, R.DL, R.R8L, R.R9L)
    if (save.mnemonic != M.MOVZX or save.op1_kind != K.REGISTER or not RX.is_gpr32(save.op0_register) or
            RX.full_register(save.op0_register) != dst or save.op1_register not in slots or
            il.returns_sret(il.types[method.return_type])):
        return None
    index = slots.index(save.op1_register) - int(not method.is_static)
    params = source_params(il.meta, method)
    if not (0 <= index < len(params) and 0 <= params[index].type < len(il.types) and
            il._closed_type_key(il.types[params[index].type]) == (2, 0)):
        return None
    # Only copies in the single-entry straight-line prologue. Even a write
    # to AH is a write to RAX in this proof; symbolic GPR names alone alias.
    arg = RX.full_register(save.op1_register)
    for j, i in enumerate(seq):
        if pred[i.ip] != ([seq[j-1].ip] if j else []):
            return None
        if i.ip == pos:
            return safe_ident(params[index].name)
        if (i.mnemonic == M.CALL or any(u.access in _WRITES and RX.full_register(u.register) == arg
                                       for u in _INFO.info(i).used_registers())):
            return None
    return None


def mask_sites(lift, method, blocks, pads):
    """test IP -> (consumer IP, producer IP, input kind, mask/argument)."""
    sites, calls = {}, {}
    if not HAVE_ICED or pads:
        return sites, calls
    candidates = []
    for b in blocks:
        if len(b.insns) < 2:
            continue
        t, j = b.insns[-2:]
        if (t.mnemonic == M.TEST and t.op0_kind == K.REGISTER and _low(t.op0_register) and
                j.mnemonic in (M.JE, M.JNE) and t.next_ip == j.ip and
                (t.op1_kind == K.IMMEDIATE8 or t.op1_kind == K.REGISTER and
                 t.op1_register == R.AL and t.op0_register != R.AL)):
            candidates.append((t, j))
    il = lift.il
    if (not candidates or not _amd64(getattr(il, 'bin', None)) or il.meta.version != 31 or
            method.generic_container != -1 or not 0 <= method.return_type < len(il.types)):
        return sites, calls
    # _bind names its locals tN. A user parameter with that spelling must
    # never be confused with the saved return, even at a different use IP.
    if any(name.startswith('t') and name[1:].isdigit()
           for name in (safe_ident(p.name) for p in source_params(il.meta, method))):
        return sites, calls
    seq = [i for b in blocks for i in b.insns]
    if not seq or seq[0].ip != method.addr or len(seq) > 4096:
        return sites, calls
    g = _graph(il, seq, allow_tail=True, runtime_tails=lift.rt_wbarrier, chained=True, nested_chains=True)
    if not g:
        return sites, calls
    by = {i.ip:i for i in seq}
    pred, succ = g
    acyclic = {}
    for t, j in candidates:
        if pred[j.ip] != [t.ip]:
            continue
        if t.op1_kind == K.IMMEDIATE8:
            te, arg = 8, t.immediate8
            defs = _definitions(by, pred, method.addr, t.ip, RX.full_register(t.op0_register))
            if len(defs) != 1:
                continue
            pos, reg = defs.pop()
            mov = by[pos]
            if (mov.mnemonic == M.MOV and RX.is_gpr32(mov.op0_register) and
                    RX.full_register(mov.op0_register) == reg and mov.op1_register == R.EAX):
                defs = _definitions(by, pred, method.addr, pos, R.RAX)
                if len(defs) != 1:
                    continue
                pos, reg = defs.pop()
            if reg != R.RAX:
                continue
        else:
            te = 2
            arg = _saved_argument(il, method, seq, by, pred, t)
            if not arg or len(pred[t.ip]) != 1:
                continue
            pos = pred[t.ip][0]
            if by[pos].next_ip != t.ip:
                continue
        mi = _result(il, by[pos], te)
        if mi is not None:
            # A later execution of the very same call can overwrite its
            # local while a nonvolatile register still holds the old sample.
            if pos not in acyclic:
                acyclic[pos] = pos not in _reachable(succ, succ[pos])
            if not acyclic[pos]:
                continue
            sites[t.ip] = j.ip, pos, te, arg
            calls[pos] = mi
    return sites, calls


def predicate(lift, test, plan, samples):
    """Called only after executing the planned TEST in this block/pass."""
    jump, pos, te, arg = plan
    sample = samples.get(pos)
    a = dict.get(lift.regs, reg_name(test.op0_register))
    checked = a if te == 8 else dict.get(lift.regs, 'RAX')
    if (sample is None or checked is None or not lift.flags or lift.flags[0] is not a or
            sample.text != checked.text or lift.il._closed_type_key(checked.ty) != (te, 0)):
        return None
    # sample.text is the unique immutable local minted at this proved call;
    # saved nonvolatile copies sometimes contain a different Expr object.
    if te == 8:
        return jump, '(%s & %d)' % (sample.text, arg), '0'
    if (a is None or lift.il._closed_type_key(a.ty) != (2, 0) or
            a.text not in (arg, '(%s & 0xFF/*z*/)' % arg)):
        return None
    return jump, '(%s & %s)' % (arg, sample.text), 'false'
