"""Recover a pair of byref vector calls around complete native 8+4 copies."""
import re

from il2cpp.binary import PE
from il2cpp.expr import Expr, acc_get
from il2cpp.csharp import FA_INITONLY
from il2cpp.prelude import HAVE_ICED
from il2cpp.shared_icall import vector_ref_pair
from il2cpp.sret_copy import _own_field
from il2cpp.text import reg_name, sdisp
from il2cpp.x64 import VOLATILE

if HAVE_ICED:
    from iced_x86 import Mnemonic as M, OpKind as K, Register as R


def _copies(seq):
    """Return the two (source,destination) locations in ABI argument order.
    Match reaching byte ranges, not just the nearest load of a register.
    Every load, store, LEA and hidden-argument definition must be accounted for.
    """
    regs, args, stores = {}, {}, {}
    zero = ax_written = False
    for i in seq:
        reg = i.memory_base
        if i.has_segment_prefix or i.memory_index != R.NONE:
            return None
        addr = reg, sdisp(i.memory_displacement)
        if i.mnemonic == M.XOR and i.op0_register == i.op1_register == R.R8D and not zero:
            zero = True
            continue
        if reg not in (R.RSP,R.RAX,R.RBX,R.RDI,R.RSI,R.R12,R.R13,R.R14,R.R15) or (reg == R.RAX and ax_written):
            return None
        if i.mnemonic == M.LEA and i.op0_register in (R.RCX,R.RDX) and i.op0_register not in args:
            args[i.op0_register] = addr
            continue
        if i.mnemonic == M.MOVSD:
            scratch, size = R.XMM0, 8
        elif i.mnemonic == M.MOV:
            scratch, size = R.EAX, 4
        else:
            return None
        if i.op0_register == scratch and i.op1_kind == K.MEMORY and scratch not in regs:
            regs[scratch] = addr
            ax_written |= scratch == R.EAX
        elif i.op0_kind == K.MEMORY and i.op1_register == scratch and scratch in regs and (addr,size) not in stores:
            stores[addr,size] = regs.pop(scratch)
        else:
            return None
    if regs or not zero or len(args) != 2 or len(stores) != 4:
        return None
    result = []
    for reg in (R.RCX,R.RDX):
        dst = args[reg]
        src = stores.get((dst,8))
        if src is None or stores.get(((dst[0],dst[1]+8),4)) != (src[0],src[1]+8):
            return None
        result.append((src,dst))
    return result


def fold_ref_vectors(lift, seq, idx):
    """Start immediately after the producer that echoed its stack sret
    address. No intermediate entry or opaque operation in either copy. The
    public call owns the mutations, including a partial mutation on throw.
    """
    if idx == 0 or idx+23 >= len(seq) or seq[idx-1].mnemonic != M.CALL or seq[idx-1].op0_kind != K.NEAR_BRANCH64:
        return None
    first, second = seq[idx+11], seq[idx+23]
    if (first.mnemonic != M.CALL or second.mnemonic != M.CALL or first.op0_kind != K.NEAR_BRANCH64 or
            second.op0_kind != K.NEAR_BRANCH64 or first.near_branch_target != second.near_branch_target or
            any(a.next_ip != b.ip for a,b in zip(seq[idx-1:idx+23],seq[idx:idx+24]))):
        return None
    one, two = _copies(seq[idx:idx+11]), _copies(seq[idx+12:idx+23])
    if not one or not two:
        return None
    (ret, a), (field, b) = one
    (post_a,c), (post_b,dest) = two
    if (ret != (R.RAX,0) or any(loc[0] != R.RSP for loc in (a,b,c)) or post_a != a or post_b != b or
            field[0] in (R.RSP,R.RAX) or dest[0] in (R.RSP,R.RAX)):
        return None
    echo = dict.get(lift.regs,'RAX')
    if (not echo or echo.kind != 'ptr' or not re.fullmatch(r'&t\d+',echo.text) or
            getattr(lift,'_last_sret',None) != (seq[idx-1].ip,echo) or getattr(echo,'_stack_offset',None) is None):
        return None
    # Three independent writable stack vectors plus the producer's source;
    # none may overlap another vector, the return address, or call shadow space.
    offsets = [x[1] for x in (a,b,c)] + [echo._stack_offset-lift.rsp_delta]
    ordered = sorted(offsets)
    if ordered[0] < 0x20 or ordered[-1]+12 > -lift.rsp_delta or any(x+12>y for x,y in zip(ordered,ordered[1:])):
        return None
    il = lift.il
    if not isinstance(getattr(il,'bin',None), PE) or not il.bin.is64:
        return None
    producers = il.addr_candidates.get(seq[idx-1].near_branch_target, ())
    if len(producers) != 1 or producers[0][0] != 'method' or not 0 <= producers[0][1] < len(il.meta.methods):
        return None
    producer = il.meta.methods[producers[0][1]]
    if (producer.addr != seq[idx-1].near_branch_target or not 0 <= producer.return_type < len(il.types) or
            il.types[producer.return_type] != echo.ty or not il.returns_sret(echo.ty)):
        return None
    alias = vector_ref_pair(il,first.near_branch_target)
    if not alias:
        return None
    mi, pt = alias
    key = (0x11,pt[0],0)
    lanes = il.instance_field_chain(pt[0]) or {}
    if (il._closed_type_key(echo.ty) != key or il.value_type_size(pt[0]) != 12 or set(lanes) != {16,20,24} or
            not all(_own_field(il,il.meta.typedefs[pt[0]],off,4) and
                    il._closed_type_key(il.types[ti]) == (0x0c,0) for off,(_,ti) in lanes.items())):
        return None
    def member(loc, writable=False):
        base = dict.get(lift.regs,reg_name(loc[0]))
        if (not base or base._unk or base.kind != 'obj' or not re.fullmatch(r'[A-Za-z_]\w*',base.text) or
                il._closed_type_key(base.ty) != (0x12,lift._current_td.index,0)):
            return None
        row = _own_field(il,lift._current_td,loc[1],12)
        if row and il._closed_type_key(row[1]) == key and not (writable and row[1][1] & FA_INITONLY):
            return base.text + row[0][4:]
    src, dst = member(field), member(dest, writable=True)
    if not src or not dst or not dst.startswith('this.'):
        return None
    # New native names represent snapshots of whole structs. Do not forward
    # initial values after a ref call: tile every post-call home from the
    # mutated local, so subsequent 8+4 reads see all three NEW components.
    names = [lift.new_var() for _ in (a,b,c)]
    n,t,n2 = names
    op = il.typedef_full(pt[0]) + '.' + il.meta.methods[mi].name
    for v in names:
        lift._var_types[v] = echo.ty
    lift.emit(first.ip, f'var {n} = {echo.text[1:]};',None)
    lift.emit(first.ip, f'var {t} = {acc_get(src)};',None)
    lift.emit(first.ip, f'{op}(ref {n}, ref {t}) /* shared icall */;',None)
    lift.emit(second.ip, f'var {n2} = {n};',None)
    lift._kill_stale(dst)
    lift.emit(second.ip, f'{dst} = {t};',None)
    lift.emit(second.ip, f'{op}(ref {n2}, ref {dst}) /* shared icall */;',None)
    for off, v in zip(offsets[:3],names):
        start = lift.rsp_delta + off
        for addr,slot in lift.stack_map.items():
            if start <= addr < start+12:
                lift.stack_values.pop(slot,None)
        lift._stack_store(start,12,Expr(v,echo.ty,'obj'))
    for reg in (*VOLATILE, *('XMM%d'%i for i in range(6))):
        lift.regs.pop(reg,None)
    lift.flags = None
    lift._fresh_unknowns()
    return idx+23
