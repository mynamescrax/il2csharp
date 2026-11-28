"""Capture an instance scalar getter and its receiver before a static poll.

The setter can be on the far side of clamp branches. Sharing a property
name is insufficient: both instance calls must use the same field load.
"""
from il2cpp.array_origin import _graph, _reachable
from il2cpp.closed_lookup import _field_input
from il2cpp.equivalent_binary import _amd64
from il2cpp.metadata import source_params
from il2cpp.names import safe_ident
from il2cpp.prelude import HAVE_ICED
from il2cpp.scalar_snapshot import _property

if HAVE_ICED:
    from iced_x86 import Mnemonic as M, Register as R, OpKind as K


def _setter(lift, i):
    if i.is_call_near:
        return _property(lift, i, 'set')
    if not i.is_jmp_short_or_near:
        return None
    # As for an ordinary direct call, the target MethodDef owns the ABI.
    ids = lift.il.addr_candidates.get(i.near_branch_target, ())
    if len(ids) != 1 or ids[0][0] != 'method' or not 0 <= ids[0][1] < len(lift.meta.methods):
        return None
    m = lift.meta.methods[ids[0][1]]; p = lift._accessor_prop(m.index)
    ps = lift.meta.method_params(m); il = lift.il
    if (p and p[0] == 'set' and not p[2] and not m.is_static and not m.flags & 0x40 and
            m.addr == i.near_branch_target and m.generic_container == -1 and
            len(ps) == m.param_count == 1 and 0 <= ps[0].type < len(il.types) and
            il._closed_type_key(il.types[ps[0].type]) == (12, 0) and 0 <= m.return_type < len(il.types) and
            il._closed_type_key(il.types[m.return_type]) == (1, 0)):
        return m, p[1]


def scalar_pairs(lift, method, td, blocks, pads):
    fields, calls = {}, {}
    if not HAVE_ICED or pads or method.is_static or td.is_valuetype or method.generic_container != -1:
        return fields, calls
    windows = []
    for b in blocks:
        for j in range(len(b.insns)-3):
            a, z, mov, c = b.insns[j:j+4]
            if (a.is_call_near and c.is_call_near and z.mnemonic == M.XOR and z.op0_register == z.op1_register == R.ECX and
                    mov.mnemonic == M.MOVAPS and R.XMM6 <= mov.op0_register <= R.XMM15 and mov.op1_register == R.XMM0):
                windows.append((a, z, mov, c))
    il = lift.il
    if (not windows or not _amd64(getattr(il,'bin',None)) or il.meta.version != 31 or
            not 0 <= method.return_type < len(il.types) or
            il._closed_type_key(il.types[method.return_type]) != (1,0) or
            any(n.startswith('t') and n[1:].isdigit() for n in (safe_ident(p.name) for p in source_params(il.meta,method)))):
        return fields, calls
    seq = [i for b in blocks for i in b.insns]; by = {i.ip:i for i in seq}
    g = _graph(il, seq, allow_tail=True, chained=True, nested_chains=True, runtime_tails=lift.rt_wbarrier)
    if not g or seq[0].ip != method.addr:
        return fields, calls
    pred, succ = g; setters = []
    for i in seq:
        q = _setter(lift,i)
        if q and not q[0].is_static:
            row = _field_input(il,method,by,pred,i,q[0].declaring)
            if row: setters.append((q[0].declaring, q[1], row[0], i.ip))
    for a, z, mov, c in windows:
        if any(pred[v.ip] != [u.ip] or u.next_ip != v.ip for u,v in ((a,z),(z,mov),(mov,c))):
            continue
        first = _property(lift,a,'get'); clock = _property(lift,c,'get')
        if not first or first[0].is_static or not clock or not clock[0].is_static:
            continue
        reader = first[0]; row = _field_input(il,method,by,pred,a,reader.declaring)
        if not row:
            continue
        # Capturing the field must not erase a derived receiver or member
        # hiding on a derived type. First revision requires its exact owner.
        ip, fld = row
        # A lazy earlier call in a condition could otherwise be rendered
        # *after* the capture. Admit only entry paths without calls (apart
        # from initialization of metadata slots) and no incoming backedge.
        before = _reachable(pred, pred[ip])
        if (by[ip].op0_register == R.RBP or ip in before or
                any(by[k].mnemonic == M.CALL and (not by[k].is_call_near or
                    by[k].near_branch_target != getattr(lift,'rt_init_meta',None)) for k in before)):
            continue
        if il._closed_type_key(fld[1]) != (0x12, reader.declaring, 0):
            continue
        after = _reachable(succ, succ[c.ip]); possible = [site for owner, prop, load, site in setters
                    if owner == reader.declaring and prop == first[1] and load == ip and site in after]
        if len(possible) != 1 or ip in _reachable(succ,succ[ip]) or a.ip in after:
            continue
        fields[ip] = fld; calls[a.ip] = reader.index; calls[c.ip] = clock[0].index
    return fields, calls
