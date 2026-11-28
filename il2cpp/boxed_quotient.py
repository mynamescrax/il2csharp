"""A signed multiply-high division whose dword output goes to value_box.

Only collapse a multiplier whose rounding error certifies one actual
positive divisor on the entire signed Int32 domain. Check the consumers,
including scratch registers and flags, before replacing the window.
"""
from il2cpp.array_origin import _graph, _definitions
from il2cpp.equivalent_binary import _amd64
from il2cpp.expr import Expr, _INT_TY
from il2cpp.metadata import source_params
from il2cpp.names import safe_ident
from il2cpp.prelude import HAVE_ICED
from il2cpp.stack_local_frame import stack_local_frame
from il2cpp.text import reg_name, sdisp

if HAVE_ICED:
    from iced_x86 import Mnemonic as M, OpKind as K, Register as R, RegisterExt as RX, MemorySizeExt as MS
    from il2cpp.array_origin import _INFO, _WRITES, _SAVED


def certified_divisor(multiplier, shift):
    # hi+n equals floor(n*m/2**32) for signed m-2**32; the sum itself
    # fits a dword. SAR k then computes floor(n*m/S). The positive error
    # below is too small to cross a quotient boundary, except that each
    # negative exact multiple rounds one below truncation. SHR 31 adds
    # exactly the correction for all negative inputs, including those.
    if not (1 << 31 <= multiplier < 1 << 32 and 0 <= shift <= 31):
        return None
    scale = 1 << (32 + shift)
    d = (scale + multiplier - 1) // multiplier
    if 2 <= d < 1 << 31 and 0 < (d * multiplier - scale) * (1 << 31) < scale:
        return d


def _boxed_dword(lift, seq, at, acc, divisor):
    # Both scratch lanes have to be overwritten before any observation;
    # RDX is used only at dword width. The exported box call replaces RAX
    # with its result and receives only the fresh RCX/RDX pointers.
    def slot(i, op, r):
        return (i.mnemonic == op and i.memory_base == R.RSP and i.memory_index == R.NONE and
                (i.op1_register == r and i.op0_kind == K.MEMORY and MS.size(i.memory_size) == 4 if op == M.MOV else
                 i.op0_register == R.RDX and i.op1_kind == K.MEMORY))
    def klass(i):
        return (i.mnemonic == M.MOV and i.op0_register == R.RCX and i.memory_base == R.RIP and
                i.op1_kind == K.MEMORY and i.memory_index == R.NONE)
    tail = seq[at:at+6]
    if len(tail) >= 4 and klass(tail[0]) and slot(tail[1], M.MOV, R.EDX) and slot(tail[2], M.LEA, R.NONE):
        k, store, addr, box = tail[:4]
    elif len(tail) == 6:
        mul, addr, sub, k, store, box = tail
        if (mul.mnemonic != M.IMUL or mul.op_count != 3 or mul.op0_register != R.ECX or mul.op1_register != R.EDX or
                mul.op2_kind not in (K.IMMEDIATE8TO32,K.IMMEDIATE32) or mul.immediate(2) != divisor or
                not slot(addr,M.LEA,R.NONE) or sub.mnemonic != M.SUB or sub.op0_register != acc or
                sub.op1_register != R.ECX or not klass(k) or not slot(store,M.MOV,acc)):
            return None
    else:
        return None
    if (store.memory_displacement != addr.memory_displacement or not box.is_call_near or
            box.near_branch_target != getattr(lift,'rt_value_box',None)):
        return None
    return box, k, addr, store, tail[0].mnemonic == M.IMUL


def _home(seq, frame, addr, store):
    size, depth, saves = frame; off = sdisp(addr.memory_displacement)
    if off % 4 or not (32 <= off and off+4 <= size or depth+8 <= off and off+4 <= depth+40):
        return False
    if any(start < off+4 and off < start+span for start,span in saves):
        return False
    # No alias to this stack address, including a frame pointer copied into
    # a register. stack_local_frame checks prologue/epilogue and RSP writes.
    alloc = next(j for j,i in enumerate(seq) if i.mnemonic == M.SUB and i.op0_register == R.RSP)
    for i in seq[alloc+1:]:
        if i.ip in (addr.ip,store.ip):continue
        if i.op1_kind == K.REGISTER and i.op1_register == R.RSP:return False
        if i.memory_base != R.RSP:continue
        start = sdisp(i.memory_displacement); width = MS.size(i.memory_size)
        if i.memory_index != R.NONE or i.mnemonic == M.LEA and start == off or (start < off+4 and off < start+width):return False
    return True


def _lookup_cells(il):
    """BSS class rows have no on-disk type token. Require an actual call to
    the exported class lookup, with exact namespace/name RIP operands, and
    a single direct register store to the cell in the image."""
    cache = il.__dict__.get('_boxed_int_lookup_cells')
    if cache is not None:
        return cache
    b = il.bin; accepted = set(); lookup = [v for v,n in b.exports.items() if n == 'il2cpp_class_from_name']
    if len(lookup) == 1:
        from bisect import bisect_right
        from iced_x86 import Decoder, FlowControl as F
        targets = {lookup[0]}
        code = b.read(lookup[0],5) or b''
        if code[:1] == b'\xe9' and len(code) == 5:
            targets.add(lookup[0]+5+int.from_bytes(code[1:],'little',signed=True))
        seen = set(); conflicts = set()
        for sec in b.sections:
            if not sec.is_exec:continue
            data = b.read(sec.addr,min(sec.size,sec.rawsize)) or b''
            for rex in (0x48,0x4c):
                for reg in range(8):
                    pat = bytes((rex,0x89,5|(reg<<3))); p = data.find(pat)
                    while p >= 0:
                        n = p; p = data.find(pat,p+1)
                        if n+7>len(data):continue
                        cell = sec.addr+n+7+int.from_bytes(data[n+3:n+7],'little',signed=True)
                        usage = getattr(il,'bss_usage_map',{}).get(cell)
                        if not usage or usage.get('text')!='typeof(int)' or usage.get('kind')!=2:continue
                        if cell in seen:conflicts.add(cell);continue
                        seen.add(cell)
                        if (n<26 or pat!=b'\x48\x89\x05' or data[n-26:n-23]!=b'\x4c\x8d\x05' or
                                data[n-19:n-16]!=b'\x48\x8d\x15' or data[n-12:n-9]!=b'\x48\x8b\x0d' or data[n-5]!=0xe8):continue
                        first=sec.addr+n-26; site=sec.addr+n; idx=bisect_right(il._starts,first)-1
                        if idx < 0:continue
                        lo,hi=il.func_ranges[idx]
                        if not lo<=first<site+7<=hi or hi-lo>0x8000:continue
                        ins=list(Decoder(64,b.read(lo,hi-lo) or b'',ip=lo)); seq=[i for i in ins if first<=i.ip<=site]
                        if len(seq)!=5 or seq[0].ip!=first or seq[-1].ip!=site or any(i.is_invalid for i in seq):continue
                        if any(i.flow_control in (F.UNCONDITIONAL_BRANCH,F.CONDITIONAL_BRANCH) and
                               first<i.near_branch_target<=site for i in ins):continue
                        a,ns,_,call,store=seq
                        if (call.near_branch_target in targets and store.ip_rel_memory_address==cell and
                                b.cstr(a.ip_rel_memory_address,32)=='Int32' and b.cstr(ns.ip_rel_memory_address,32)=='System'):
                            accepted.add(cell)
        accepted.difference_update(conflicts)
    il._boxed_int_lookup_cells = frozenset(accepted)
    return il._boxed_int_lookup_cells

def _boxed_int(il, klass):
    if il.bin.va2off(klass.ip_rel_memory_address) is None and klass.ip_rel_memory_address not in _lookup_cells(il):return False
    slot = il.decode_slot(klass.ip_rel_memory_address) or {};td = slot.get('td')
    if slot.get('kind') not in (1,2) or not isinstance(td,int) or not 0 <= td < len(il.meta.typedefs):return False
    row = il.meta.typedefs[td]
    return ((row.namespace,row.name)==('System','Int32') and row.is_valuetype and not row.is_enum and
            il.value_type_size(td)==4 and 0 <= row.byval < len(il.types) and il._closed_type_key(il.types[row.byval])==(8,0))


def boxed_divisions(lift, method, blocks, pads):
    plans = {}; il = lift.il
    if not HAVE_ICED or pads or not method.is_static or not _amd64(getattr(il,'bin',None)) or il.meta.version != 31:
        return plans
    candidates = [(b,j) for b in blocks for j,i in enumerate(b.insns[:-6])
                  if i.mnemonic == M.MOV and i.op0_register == R.EAX and i.op1_kind == K.IMMEDIATE32 and
                  b.insns[j+1].mnemonic == M.IMUL and b.insns[j+1].op_count == 1]
    if not candidates or not 0 <= method.return_type < len(il.types) or il.returns_sret(il.types[method.return_type]):
        return plans
    seq = [i for b in blocks for i in b.insns]; by = {i.ip:i for i in seq}
    g = _graph(il,seq); params = source_params(il.meta,method)
    # Only these verified 4-byte, immediate box borrows can use an incoming
    # Windows shadow home; other clients retain local-only stack leases.
    borrows = {}
    for block, j in candidates:
        w = block.insns[j:]; d = certified_divisor(w[0].immediate32,w[3].immediate8) if w[3].op1_kind==K.IMMEDIATE8 else None
        other = _boxed_dword(lift,block.insns,j+7,w[1].op0_register,d) if d else None
        if other and _boxed_int(il,other[1]):
            borrows[other[2].ip] = 4
    frame = stack_local_frame(lift, method, blocks, pads, incoming=borrows) if borrows else None
    if not g or not frame or method.addr != seq[0].ip or method.generic_container != -1:
        return plans
    pred,succ = g
    for b,j in candidates:
        first,mul,add,sar,copy,shr,fix = b.insns[j:j+7]; r = mul.op0_register
        if (not RX.is_gpr32(r) or RX.full_register(r) not in _SAVED or mul.op0_kind != K.REGISTER or
                (add.mnemonic,add.op0_register,add.op1_register) != (M.ADD,R.EDX,r) or
                sar.mnemonic != M.SAR or sar.op0_register != R.EDX or sar.op1_kind != K.IMMEDIATE8 or
                (copy.mnemonic,copy.op0_register,copy.op1_register) != (M.MOV,R.ECX,R.EDX) or
                shr.mnemonic != M.SHR or shr.op0_register != R.ECX or shr.op1_kind != K.IMMEDIATE8 or shr.immediate8 != 31 or
                (fix.mnemonic,fix.op0_register,fix.op1_register) != (M.ADD,R.EDX,R.ECX)):
            continue
        d = certified_divisor(first.immediate32,sar.immediate8)
        if d is None:
            continue
        sink = _boxed_dword(lift,b.insns,j+7,r,d)
        if sink is None:
            continue
        box, k, addr, store, rem = sink
        if (not _home(seq,frame,addr,store) or not _boxed_int(il,k) or
                any(i.mnemonic==M.LEA and i.memory_base==R.RSP and i.ip not in borrows for i in seq)):
            continue
        if rem:
            # The remainder dword zeroes the high half of N. An escaping
            # qword/copy is outside an Int32 spelling. Require only the
            # nonvolatile restore to observe/write this register from box
            # to the sole return, including any intervening direct calls.
            suffix = [i for i in b.insns if i.ip>box.ip]; uses=[i for i in suffix if any(
                RX.full_register(u.register)==RX.full_register(r) for u in _INFO.info(i).used_registers())]
            if (not suffix or suffix[-1].mnemonic!=M.RET or len(uses)!=1 or uses[0].mnemonic!=M.POP or
                    uses[0].op0_register!=RX.full_register(r)):continue
        w = [i for i in b.insns[j:] if i.ip <= box.ip]
        if any(i.has_lock_prefix or i.has_segment_prefix for i in w) or any(a.next_ip != z.ip or pred[z.ip] != [a.ip] for a,z in zip(w,w[1:])):
            continue
        # The incoming divisor argument is a saved, unmodified Int32 from
        # the entry signature. Exclude untyped/general arithmetic carries.
        defs = _definitions(by,pred,method.addr,first.ip,RX.full_register(r))
        if len(defs) != 1:
            continue
        pos,reg = defs.pop(); save = by[pos]; slots = (R.ECX,R.EDX,R.R8D,R.R9D)
        if save.mnemonic != M.MOV or save.op0_register != r or save.op1_register not in slots:
            continue
        slot = slots.index(save.op1_register)
        if slot >= len(params) or not 0 <= params[slot].type < len(il.types) or il._closed_type_key(il.types[params[slot].type]) != (8,0):
            continue
        pre = [i for i in seq if i.ip <= pos]; incoming = RX.full_register(save.op1_register)
        if (pred[method.addr] or any(pred[z.ip] != [a.ip] for a,z in zip(pre,pre[1:])) or
                any(i.is_call_near or any(u.access in _WRITES and RX.full_register(u.register)==incoming for u in _INFO.info(i).used_registers()) for i in pre[:-1])):
            continue
        # Observe no outgoing flags before overwritten/actual return. A
        # managed call/box cannot take flags as a parameter; still follow
        # its normal continuation, not an assumption that it kills flags.
        live = fix.rflags_modified; valid = False
        for i in b.insns[j+7:]:
            if i.rflags_read & live or i.is_call_near and i.near_branch_target != lift.rt_value_box and not il.addr_candidates.get(i.near_branch_target):
                break
            live &= ~i.rflags_modified
            if not live or i.mnemonic == M.RET:
                valid = True;break
        if valid:
            plans[first.ip] = reg_name(r), safe_ident(params[slot].name), d, sdisp(store.memory_displacement), frame[1]
    return plans


def apply_division(lift, plan):
    r,name,d,off,depth = plan; n = dict.get(lift.regs,r)
    if not n or n.text != name or n._unk or lift.il._closed_type_key(n.ty) != (8,0) or lift.rsp_delta != -depth:
        return False
    home = lift.slot_var(off)
    if (not home.startswith('s_') or any(lift.il._closed_type_key(tab[home]) != (8,0)
            for tab in (lift.slot_types,lift._type_hints) if home in tab)):
        return False
    # The exact home is borrowed solely by value_box(System.Int32, &home).
    lift.slot_types[home] = lift._type_hints[home] = _INT_TY
    # Keep the integer operation grouped for the remainder multiply.
    q = Expr(f'({name} / {d})', _INT_TY, 'int')
    lift.regs['RDX'] = q
    lift.regs.pop('RAX',None); lift.regs.pop('RCX',None); lift.flags = None
    return True
