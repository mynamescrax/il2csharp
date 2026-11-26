"""Recover a full Win64 float4 sret store from four scalar SSE results."""
import re

from il2cpp.binary import PE
from il2cpp.expr import _R4_TY
from il2cpp.prelude import HAVE_ICED
from il2cpp.simd_getter import _float4, _packed_return, _scratch_inputs
from il2cpp.sret_copy import _own_field
from il2cpp.text import reg_name

if HAVE_ICED:
    from iced_x86 import FlowControl as F, InstructionInfoFactory, Mnemonic as M, OpAccess, OpKind as K, Register as R, RegisterExt
    _INFO = InstructionInfoFactory()
    _WRITE = {OpAccess.WRITE, OpAccess.COND_WRITE, OpAccess.READ_WRITE, OpAccess.READ_COND_WRITE}


def _writes(i, r):
    return any(u.access in _WRITE and RegisterExt.full_register(u.register) == RegisterExt.full_register(r)
               for u in _INFO.info(i).used_registers())


def _pack(seq, j):
    """Walk the selectors backwards, not the order of the MOVSS opcodes.
    A restore is harmless only after its last contributing lane was read."""
    store = seq[j]
    dst, address = store.op1_register, store.memory_base
    if (store.mnemonic != M.MOVUPS or store.op0_kind != K.MEMORY or not RegisterExt.is_xmm(dst) or
            address not in (R.RBX,R.RSI,R.RDI,R.R12,R.R13,R.R14,R.R15) or store.memory_index != R.NONE or
            store.memory_displacement or store.has_segment_prefix):
        return None
    lanes = [(dst,k) for k in range(4)]
    shifts = inserts = 0
    for n in range(j-1, max(-1,j-33), -1):
        i = seq[n]
        if i.next_ip != seq[n+1].ip or i.has_segment_prefix:
            break
        if i.mnemonic == M.SHUFPS and i.op0_register == i.op1_register == dst and i.op2_kind == K.IMMEDIATE8:
            lanes = [(r, (i.immediate8 >> (2*k)) & 3 if r == dst else k) for r,k in lanes]
            shifts += 1
        elif i.mnemonic == M.MOVSS and i.op0_register == dst and RegisterExt.is_xmm(i.op1_register):
            lanes = [(i.op1_register,0) if (r,k) == (dst,0) else (r,k) for r,k in lanes]
            inserts += 1
        elif (i.mnemonic in (M.MOV,M.MOVAPS) and i.op0_kind == K.REGISTER and i.op1_kind == K.MEMORY and
                i.memory_base in (R.RSP,R.R11) and i.memory_index == R.NONE):
            if any(_writes(i,r) for r,_ in lanes) or _writes(i,address):
                break
        elif not (i.mnemonic == M.MOV and i.op0_register == R.RAX and i.op1_register == address):
            break
        if shifts == 4:
            if inserts == 3 and len({r for r,k in lanes if k == 0}) == 4:
                return n, tuple(r for r,_ in lanes)
            break
    return None


def _inputs(path, seq, start, regs, getters, ty, lift):
    """Check arithmetic inputs independently of the rendered register text.
    Begin at a certified four-float computation, track nonvolatile scalars
    across calls, and accept only a full sret load, the matching scalar
    spill/reload, register shuffles, and single-precision arithmetic in the
    final kernel. An unmodelled instruction must not lend stale lanes."""
    for p in path[1:]:
        if len(p.insns) < 4 or p.insns[-3].ip not in getters:
            continue
        getter, reads, _ = getters[p.insns[-3].ip]
        spill = p.insns[-4]
        seed = next(i for i in p.insns if i.ip == reads[0])
        right = max(j for j,i in enumerate(p.insns[:-4]) if i.mnemonic == M.CALL)
        scratch = _scratch_inputs(p.insns[right+1:-4], seed.op0_register)
        if not scratch:
            continue
        known = {r for r in scratch[1] if R.XMM6 <= r <= R.XMM15}
        chain = list(reversed(path[:path.index(p)]))
        body = p.insns[-3:] + [i for b in chain for i in (seq[:start] if b is path[0] else b.insns)]
        last_call = max((j for j,i in enumerate(body) if i.mnemonic == M.CALL), default=-1)
        if last_call < 0 or _float4(lift,body[last_call]) != ty:
            continue
        for i in body[:last_call+1]:
            # Snapshot plans exclude address-taking/FP operations from the
            # guarded fallthrough. In the following arm, don't trust a
            # carried register after *any* partial or full write.
            known = {r for r in known if not _writes(i,r)}
            if (_writes(i,spill.memory_base) or (i.memory_base == spill.memory_base and
                    i.mnemonic != M.NOP)):
                break
        else:
            # The reload is a read of the actual stack slot, not substitution
            # of a guessed constant for its contents. Only its low lane is valid.
            masks = {r:1 for r in known}
            loaded = reloaded = False
            for i in body[last_call+1:]:
                dst, src = i.op0_register, i.op1_register
                if i.has_segment_prefix:
                    break
                if _packed_return(i) and not loaded:
                    masks[dst] = 15
                    loaded = True
                elif (i.mnemonic == M.MOVSS and RegisterExt.is_xmm(dst) and i.op1_kind == K.MEMORY and
                      i.memory_base == spill.memory_base and i.memory_index == R.NONE and
                      i.memory_displacement == spill.memory_displacement and not reloaded):
                    masks[dst] = 1
                    reloaded = True
                elif i.mnemonic == M.MOVAPS and RegisterExt.is_xmm(dst) and RegisterExt.is_xmm(src):
                    masks[dst] = masks.get(src, 0)
                elif i.mnemonic == M.SHUFPS and RegisterExt.is_xmm(dst) and RegisterExt.is_xmm(src) and i.op2_kind == K.IMMEDIATE8:
                    masks[dst] = sum(1<<k for k in range(4) if masks.get(dst if k<2 else src,0) &
                                     (1 << ((i.immediate8 >> (2*k)) & 3)))
                elif i.mnemonic in (M.ADDSS,M.SUBSS,M.MULSS) and RegisterExt.is_xmm(dst) and RegisterExt.is_xmm(src):
                    masks[dst] = masks.get(dst,0) & (14 | (masks.get(src,0) & 1))
                elif not (i.mnemonic == M.LEA and i.op0_register == R.R11 and i.memory_base == R.RSP and i.memory_index == R.NONE):
                    break
            else:
                if loaded and reloaded and all(masks.get(r,0) & 1 for r in regs):
                    return getter
    return None


def return_plans(lift, method, blocks, pads, getters):
    """In an acyclic single-entry path, prove the sret pointer survives to
    the pack. Preserve separate values for packed loads of call results: a
    later producer can use the same physical stack home."""
    il = lift.il
    plans, fresh = {}, set()
    if (not getters or not HAVE_ICED or not isinstance(getattr(il,'bin',None), PE) or not il.bin.is64 or pads or
            not 0 <= method.return_type < len(il.types)):
        return plans, fresh
    ty = il.types[method.return_type]
    if (not ty or il._type_enum(ty) != 0x11 or ty[1] & (1<<29) or not 0 <= ty[0] < len(il.meta.typedefs) or
            il.typedef_full(ty[0]) != 'UnityEngine.Quaternion' or not il.returns_sret(ty)):
        return plans, fresh
    td = il.meta.typedefs[ty[0]]
    if not td.is_valuetype or il.value_type_size(td.index) != 16:
        return plans, fresh
    fields = []
    for off in (16,20,24,28):
        field = _own_field(il, td, off, 4)
        if (not field or il._closed_type_key(field[1]) != (0x0c,0) or field[1][1] & 7 != 6 or
                field[1][1] & 0x20 or not re.fullmatch(r'this\.[A-Za-z_]\w*',field[0])):
            return plans, fresh
        fields.append(field[0][5:])
    for b in blocks:
        seq = b.insns
        if not seq or seq[-1].mnemonic != M.RET:
            continue
        for j,i in enumerate(seq):
            pack = _pack(seq,j)
            if not pack:
                continue
            # All normal paths to this store go through the entry save. An
            # unknown incoming edge or a later partial/clobbering write fails.
            path = [b]
            while len(path[-1].preds) == 1 and path[-1].preds[0] < path[-1].bid:
                path.append(blocks[path[-1].preds[0]])
            if path[-1].preds or not path[-1].is_entry:
                continue
            base = i.memory_base
            prior = [x for p in reversed(path) for x in (p.insns if p is not b else seq[:j])]
            defs = [n for n,x in enumerate(prior) if _writes(x,base)]
            if len(defs) != 1:
                continue
            n, = defs
            save = prior[n]
            if (save.mnemonic != M.MOV or save.op0_register != base or save.op1_register != R.RCX or
                    any(_writes(x,R.RCX) or x.flow_control != F.NEXT for x in prior[:n])):
                continue
            # In the pack block the four sources must be four independent
            # scalar arithmetic outputs, not preserved highs of an old XMM.
            start, regs = pack
            def scalar(r):
                last = next((x for x in reversed(seq[:start]) if _writes(x,r) or x.flow_control != F.NEXT), None)
                return last is not None and last.mnemonic in (M.ADDSS,M.SUBSS,M.MULSS) and last.op0_register == r and RegisterExt.is_xmm(last.op1_register)
            if not all(scalar(r) for r in regs):
                continue
            origin = _inputs(path, seq, start, regs, getters, ty, lift)
            if origin is None:
                continue
            plans[seq[start].ip] = i.ip, regs, tuple(fields), origin
            for p in path:
                producer = None
                for x in p.insns:
                    if x.flow_control == F.CALL:
                        producer = x if _float4(lift,x) == ty else None
                    elif producer is not None and _packed_return(x):
                        fresh.add(producer.ip)
                        producer = None
                    elif producer is not None and (_writes(x,R.RAX) or x.flow_control != F.NEXT):
                        producer = None
    return plans, fresh


def capture_return(lift, regs):
    values = []
    for r in regs:
        e = dict.get(lift.regs, reg_name(r))
        v = lift._lane_value(e, 0, _R4_TY)
        if (not v or v._unk or not v.ty or lift.il._closed_type_key(v.ty) != (0x0c,0) or
                not re.fullmatch(r'(?:t\d+(?:\.[xyzw])?|s_[a-fA-F0-9]+)(?: [*+\-] (?:t\d+(?:\.[xyzw])?|s_[a-fA-F0-9]+))*',v.text)):
            return None
        values.append(v.text)
    return values


def emit_return(lift, ins, fields, values):
    ty = lift.il.types[lift._current_method.return_type]
    for r in (reg_name(ins.memory_base),'RAX'):
        e = dict.get(lift.regs,r)
        if not e or e._unk or e.kind != 'ptr' or e.text != '&__ret' or e.ty != ty:
            return False
    src = dict.get(lift.regs,reg_name(ins.op1_register))
    parts = getattr(src,'_parts',())
    if len(parts) != 4 or any(lo != k*4 or off or size != 4 or v._unk or v.text != values[k] or
                              lift.il._closed_type_key(v.ty) != (0x0c,0) for k,(lo,v,off,size) in enumerate(parts)):
        return False
    lift.emit(ins.ip, '__ret = new %s { %s };' % (lift.il.type_name(ty), ', '.join(
        '%s = %s' % pair for pair in zip(fields,values))), None)
    return True
