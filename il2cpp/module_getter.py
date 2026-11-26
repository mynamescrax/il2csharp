"""Identify a folded, one-reference value wrapper by its stack receiver use."""
import re

from il2cpp.binary import PE
from il2cpp.expr import acc_get, _recv_fold
from il2cpp.prelude import HAVE_ICED
from il2cpp.sret_copy import _own_field
from il2cpp.text import reg_name, sdisp

if HAVE_ICED:
    from iced_x86 import Mnemonic as M, OpKind as K, Register as R


def _wraps_rcx(lift, addr):
    # Save the full managed reference, issue the write barrier on that
    # slot (RCX=&slot, RDX=value), and return the complete slot in RAX.
    il = lift.il
    if il.function_extent(addr) != (addr, addr+32) or not il.bin.is_exec_va(addr):
        return False
    raw = il.bin.read(addr,32) or b''
    if (len(raw) != 32 or raw[:18] != bytes.fromhex('4883ec28 48894c2430 488bd1 488d4c2430 e8') or
            raw[22:] != bytes.fromhex('488b442430 4883c428 c3')):
        return False
    return addr+22+int.from_bytes(raw[18:22],'little',signed=True) in lift.rt_wbarrier


def _accessor(lift, addr, owner, module):
    il = lift.il
    cache = il.__dict__.setdefault('_wrapped_reference_getters', {})
    key = addr,owner,module
    if key in cache:
        return cache[key]
    cache[key] = None
    if (not 0 <= owner < len(il.meta.typedefs) or not 0 <= module < len(il.meta.typedefs) or
            il._nested_owner(module) != owner or not _wraps_rcx(lift,addr)):
        return None
    td, wrap = il.meta.typedefs[owner], il.meta.typedefs[module]
    if (td.is_valuetype or td.generic_container != -1 or not wrap.is_valuetype or wrap.is_enum or
            wrap.flags & 7 != 2 or wrap.generic_container != -1 or il.value_type_size(module) != 8 or
            set(il.instance_field_chain(module) or {}) != {0x10}):
        return None
    field = _own_field(il,wrap,0x10,8)
    if not field or il._closed_type_key(field[1]) != (0x12,owner,0):
        return None
    hits = []
    for k, index in il.addr_candidates.get(addr, ()):
        if k == 'generic' and 0 <= index < len(il.method_specs):
            mi = il.method_specs[index][0]
        elif k == 'method':
            mi = index
        else:
            return None
        if not 0 <= mi < len(il.meta.methods):
            return None
        m = il.meta.methods[mi]
        if m.declaring != owner or m.is_static or m.param_count:
            continue
        if k != 'method' or m.addr != addr or not 0 <= m.return_type < len(il.types):
            return None
        rt = il.types[m.return_type]
        if il._closed_type_key(rt) != (0x11,module,0):
            continue
        prop = lift._accessor_prop(mi)
        if (il.returns_sret(rt) or m.generic_container != -1 or m.flags & 0x40 or m.flags & 7 != 6 or
                not prop or prop[0] != 'get' or prop[2] != 0):
            return None
        hits.append((prop[1],rt))
    if len(hits) == 1:
        cache[key] = hits[0]
    return cache[key]


def _home(i):
    if i.has_segment_prefix or i.memory_index != R.NONE or i.memory_base not in (R.RSP,R.RBP):
        return None
    off = sdisp(i.memory_displacement)
    if i.memory_base == R.RSP and off < 0x20:
        return None
    return i.memory_base,off


def _receiver_use(seq, j):
    """No call, overwrite, or alternative entry between return and borrow.
    For an sret consumer the receiver moves to RDX and RCX must address a
    separate output area. Clear instructions may only prepare ABI inputs."""
    stored = None
    refs = {}
    cleared = set()
    end = seq[j].next_ip
    for i in seq[j+1:j+8]:
        if i.ip != end:
            break
        end = i.next_ip
        if i.mnemonic == M.CALL and i.op0_kind == K.NEAR_BRANCH64:
            if stored and stored in refs.values():
                return i, stored, refs, cleared
            break
        if i.mnemonic == M.MOV and i.op1_register == R.RAX and i.op0_kind == K.MEMORY and stored is None:
            stored = _home(i)
            if not stored:
                break
        elif (i.mnemonic == M.LEA and i.op0_register in (R.RCX,R.RDX) and i.op0_register not in refs and
              reg_name(i.op0_register) not in cleared and _home(i)):
            refs[i.op0_register] = _home(i)
        elif (i.mnemonic == M.XOR and i.op0_register == i.op1_register and i.op0_register in (R.EDX,R.R8D) and
              not any(reg_name(r) == reg_name(i.op0_register) for r in refs)):
            cleared.add(reg_name(i.op0_register))
        elif i.mnemonic == M.XORPS and i.op0_register == i.op1_register == R.XMM1:
            cleared.add('XMM1')
        else:
            break
    return None


def signed_module_slots(lift, blocks):
    """The display name s_N normally strips the sign. Never let RBP+N (the
    module) and RBP-N (a *different* struct's storage) share one C# local.
    Decide the spelling before either arm allocates its first home."""
    if not HAVE_ICED or not blocks or not isinstance(getattr(lift.il,'bin',None),PE) or not lift.il.bin.is64:
        return set()
    # The emitted store and subsequent LEA must use one name per home.
    # A biased `lea rbp,[rsp+C]` currently mixes absolute and relative keys
    # in those two paths. Leave these callers alone until both agree.
    if not any(i.mnemonic == M.MOV and i.op0_register == R.RBP and i.op1_register == R.RSP for i in blocks[0].insns):
        return set()
    borrowed = set()
    for b in blocks:
        for j, i in enumerate(b.insns):
            if (i.mnemonic != M.CALL or i.op0_kind != K.NEAR_BRANCH64 or
                    len(lift.il.addr_candidates.get(i.near_branch_target, ())) < 2):
                continue
            use = _receiver_use(b.insns, j)
            if use and use[1][0] == R.RBP and _wraps_rcx(lift, i.near_branch_target):
                borrowed.update(abs(off) for base,off in use[2].values() if base == R.RBP)
    if not borrowed:
        return set()
    # SP-based scratch storage in the same method can print the same name
    # as a negative BP-based receiver as well. Absolute home keys, not
    # the pretty name, continue to decide aliasing for actual stack copies.
    offsets = {sdisp(i.memory_displacement) for b in blocks for i in b.insns if i.memory_base in (R.RSP, R.RBP)}
    return {-n for n in borrowed if n > 0 and n in offsets and -n in offsets}


def module_getter(lift, ins, values, xmm, *, biased_frame=None):
    il = lift.il
    if not HAVE_ICED or not isinstance(getattr(il,'bin',None), PE) or not il.bin.is64 or len(values) != 4:
        return None
    recv, hidden, *extra = values
    if (not recv or recv._unk or recv.kind != 'obj' or not recv.ty or il._closed_type_key(recv.ty) != (0x12,recv.ty[0],0) or
            not re.fullmatch(r'[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*',recv.text) or not hidden or hidden._unk or hidden.text != '0' or
            any(e and not e._unk and not re.fullmatch(r'\w+|-?\d+(?:\.\d+)?[fd]?', e.text or '') for e in (*extra,*xmm))):
        return None
    b = getattr(getattr(lift,'out',None),'block',None)
    if not b or len(b.preds) != 1 or not 0 <= b.preds[0] < len(lift._blocks):
        return None
    pred = lift._blocks[b.preds[0]].insns
    seq = b.insns
    j = next((j for j,i in enumerate(seq) if i.ip == ins.ip),-1)
    if j not in (1,2) or len(pred)<2:
        return None
    test, null = pred[-2:]
    zero = seq[0]
    source = R.RCX if j==1 else seq[1].op1_register
    if (test.mnemonic != M.TEST or test.op0_register != source or test.op1_register != source or
            source not in (R.RCX,R.RAX,R.RBX,R.RBP,R.RSI,R.RDI,R.R12,R.R13,R.R14,R.R15) or
            null.mnemonic != M.JE or null.op0_kind != K.NEAR_BRANCH64 or null.next_ip != zero.ip or test.next_ip != null.ip or
            null.near_branch_target == zero.ip or zero.mnemonic != M.XOR or zero.op0_register != R.EDX or zero.op1_register != R.EDX or
            (j==2 and (seq[1].mnemonic != M.MOV or seq[1].op0_register != R.RCX or zero.next_ip != seq[1].ip)) or
            seq[j-1].next_ip != ins.ip or ins.op0_kind != K.NEAR_BRANCH64):
        return None
    converted = getattr(lift,'_converted_modules',{}).get(ins.ip)
    if converted:
        member = _accessor(lift,ins.near_branch_target,recv.ty[0],converted.module)
        if member:
            lift._module_conversion = converted
            return acc_get(_recv_fold(recv.text)+'.'+member[0]) + ' /* shared getter */', member[1]
    use = _receiver_use(seq,j)
    if not use:
        return None
    consumer, home, refs, cleared = use
    target = consumer.near_branch_target
    if home[0] == R.RBP and not getattr(lift, '_rbp_frame', False) and biased_frame is None:
        return None  # scratch or biased frame: no consistent emitted stack home
    cands = il.addr_candidates.get(target, ())
    if len(cands) != 1 or cands[0][0] != 'method' or not 0 <= cands[0][1] < len(il.meta.methods):
        return None
    m = il.meta.methods[cands[0][1]]
    if (m.addr != target or m.is_static or m.generic_container != -1 or not 0 <= m.return_type < len(il.types) or
            not il._return_abi_is_known(il.types[m.return_type])):
        return None
    prop = lift._accessor_prop(cands[0][1])
    if not prop or prop[2] or m.flags & 7 != 6 or m.flags & 0x40:
        return None
    rt = il.types[m.return_type]
    if il.returns_sret(rt):
        out = refs.get(R.RCX)
        size = il._sf_field_size(rt,0)
        if (prop[0] != 'get' or m.param_count or cleared != {'R8'} or refs.get(R.RDX) != home or not out or out[0] != home[0] or
                not size or size <= 0 or not (out[1]+size <= home[1] or home[1]+8 <= out[1])):
            return None
    else:
        if refs != {R.RCX:home}:
            return None
        if m.param_count == 0:
            if prop[0] != 'get' or cleared != {'RDX'}:
                return None
        elif m.param_count == 1 and prop[0] == 'set' and cleared == {'R8','XMM1'}:
            ps = il.meta.method_params(m)
            if (il._closed_type_key(rt) != (1,0) or len(ps)!=1 or not 0 <= ps[0].type < len(il.types) or
                    il._closed_type_key(il.types[ps[0].type]) != (0x0c,0)):
                return None
        else:
            return None
    member = _accessor(lift,ins.near_branch_target,recv.ty[0],m.declaring)
    if member:
        if prop[0] == 'get':
            lift._module_reads[consumer.ip] = cands[0][1]
        return acc_get(_recv_fold(recv.text)+'.'+member[0]) + ' /* shared getter */', member[1]
    return None
