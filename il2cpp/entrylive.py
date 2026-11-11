"""Fix 132: entry-live argument registers of an unresolved native callee.

A plain `sub_VA` call has no metadata signature, so the lifter used to
print the four Win64 integer argument registers (RCX, RDX, R8, R9) as
they stood at the call -- whatever they held, including clobber
placeholders nothing defines -- and dropped every XMM argument once four
GPR texts were present. A float helper such as `atan2f` therefore read
`sub_1804d05a8(v, obj2, obj3, obj4)` instead of its two XMM operands.

The callee's own code is the proof. Walking every path from its entry, a
Win64 argument position `i` is live when RCX/RDX/R8/R9 (`g`) or
XMM0-XMM3 (`x`) of that position is read before it is written. The walk
is conservative everywhere it cannot see:

* a direct call or out-of-extent jump reads whatever arg registers the
  target reads (recursively, memoized, depth-bounded); an unprovable
  target reads every register still holding its entry value;
* an indirect call/jump reads every register still holding its entry
  value;
* only a WRITE access defines a register (iced's READ_WRITE merges such
  as `movss xmm0,xmm1` count as reads), and an 8/16-bit GPR write never
  does;
* the stack pointer is tracked; a read of the caller's stack-argument
  area (entry offset >= 0x28) -- or any stack-pointer arithmetic the
  walk cannot follow, falling off the function extent, or a tail jump
  into an unprovable target -- declines the whole proof (None), since
  a fifth-or-later argument makes every register position real.

The result is a tuple of four entries, each '' (dead), 'g' or 'x'
(read), or 'gx' (both read: not a plain Win64 signature; callers
decline). None = no proof; the caller keeps today's spelling.
"""
from il2cpp.prelude import *  # noqa: F401,F403

try:
    from iced_x86 import InstructionInfoFactory, OpAccess, RegisterExt, Code
    _HAVE = HAVE_ICED
except ImportError:  # pragma: no cover
    _HAVE = False

if _HAVE:
    _GPR = (IReg.RCX, IReg.RDX, IReg.R8, IReg.R9)
    _XMM = (IReg.XMM0, IReg.XMM1, IReg.XMM2, IReg.XMM3)
    _ARGS = frozenset(_GPR + _XMM)
    _VOL = frozenset((IReg.RAX, IReg.RCX, IReg.RDX, IReg.R8, IReg.R9,
                      IReg.R10, IReg.R11, IReg.XMM0, IReg.XMM1, IReg.XMM2,
                      IReg.XMM3, IReg.XMM4, IReg.XMM5))
    _READS = frozenset((OpAccess.READ, OpAccess.READ_WRITE, OpAccess.COND_READ,
                        OpAccess.READ_COND_WRITE))
    _MEM_READS = _READS
    _FAC = InstructionInfoFactory()

MAX_DEPTH = 10
MAX_STEPS = 20000
MAX_EXTENT = 0x4000
STACK_ARGS = 0x28


class _Decline(Exception):
    pass


def _norm(reg):
    """Full arg-tracking register for `reg`, or None."""
    if RegisterExt.is_xmm(reg) or RegisterExt.is_ymm(reg) or RegisterExt.is_zmm(reg):
        n = RegisterExt.number(reg)
        return IReg.XMM0 + n if n < 4 else None
    if RegisterExt.is_gpr(reg):
        f = RegisterExt.full_register(reg)
        return f if f in (IReg.RCX, IReg.RDX, IReg.R8, IReg.R9) else None
    return None


_LOWDEF_NAMES = ('MOVSS', 'MOVSD', 'CVTSS2SD', 'CVTSD2SS', 'CVTSI2SS',
                 'CVTSI2SD', 'SQRTSS', 'SQRTSD', 'RCPSS', 'RSQRTSS', 'ROUNDSS',
                 'ROUNDSD')
_LOWDEF = None


def _lowdef_xmm(ins):
    """The XMM register `ins` writes only in its low scalar lane (the
    upper-lane merge iced reports as READ_WRITE), or None. A Win64 float
    argument is exactly that low lane, so such a write defines it."""
    global _LOWDEF
    if _LOWDEF is None:
        _LOWDEF = frozenset(getattr(Mnemonic, n) for n in _LOWDEF_NAMES)
    if ins.mnemonic not in _LOWDEF or ins.op_count != 2 \
            or ins.op0_kind != OpKind.REGISTER \
            or not RegisterExt.is_xmm(ins.op0_register):
        return None
    if ins.op1_kind == OpKind.REGISTER and ins.op1_register == ins.op0_register:
        return None                       # `sqrtss xmm0,xmm0` reads it
    return ins.op0_register


def _defines(reg):
    """A WRITE of `reg` replaces the whole tracked value."""
    return not (RegisterExt.is_gpr8(reg) or RegisterExt.is_gpr16(reg))


def _cache(il):
    return il.__dict__.setdefault('_entry_live_cache', {})


def _regs(il, target, depth):
    """(live register set, reads-stack-args) for `target` with callees
    resolved `depth` levels deep, or None.

    Memoized by (target, depth): the answer is a pure function of both
    (recursion strictly lowers depth, so cycles bottom out at depth 0 as
    an unprovable callee), and output never depends on which method
    asked first."""
    if depth <= 0:
        return None
    c = _cache(il)
    key = ('r', target, depth)
    if key in c:
        return c[key]
    try:
        r = _walk(il, target, depth)
    except _Decline:
        r = None
    except Exception:
        r = None
    c[key] = r
    return r


def _walk(il, target, depth):
    start, finish = il.function_extent(target)
    if start != target or finish is None or not 0 < finish - start <= MAX_EXTENT:
        return None
    code = il.bin.read(start, finish - start)
    if not code:
        return None
    dec = Decoder(64, code, DecoderOptions.NONE)
    dec.ip = start
    insns = {}
    for ins in dec:
        insns[ins.ip] = ins
    live = set()
    stack = [False]

    def callee(t, u, tail):
        """registers of u a transfer to t may read."""
        if t is None or not il.bin.is_exec_va(t):
            if tail:
                raise _Decline()
            return set(u)
        r = _regs(il, t, depth - 1)
        if r is None:
            if tail:
                raise _Decline()
            return set(u)
        regs, reads_stack = r
        if tail and reads_stack:
            stack[0] = True
        return set(u) & regs

    seen = set()
    work = [(target, frozenset(_ARGS), 0, None)]
    steps = 0
    while work:
        ip, undef, delta, rbp = work.pop()
        while True:
            key = (ip, undef, delta, rbp)
            if key in seen:
                break
            seen.add(key)
            steps += 1
            if steps > MAX_STEPS:
                raise _Decline()
            ins = insns.get(ip)
            if ins is None or ins.code == Code.INVALID:
                raise _Decline()          # fell off the extent
            info = _FAC.info(ins)
            u = set(undef)
            # stack-argument reads (entry-relative offset >= 0x28)
            for m in info.used_memory():
                if m.access not in _MEM_READS:
                    continue
                if m.base == IReg.RSP:
                    off = m.displacement - (1 << 64 if m.displacement >= 1 << 63 else 0) - delta
                elif m.base == IReg.RBP and rbp is not None:
                    off = m.displacement - (1 << 64 if m.displacement >= 1 << 63 else 0) - rbp
                else:
                    continue
                if off >= STACK_ARGS:
                    stack[0] = True
            used = info.used_registers()
            low = _lowdef_xmm(ins)
            for ur in used:
                n = _norm(ur.register)
                if n is not None and n in u and ur.access in _READS \
                        and not (ur.register == low and ur.access == OpAccess.READ_WRITE):
                    live.add(n)
            for ur in used:
                n = _norm(ur.register)
                if n is not None and n in u and (
                        (ur.access == OpAccess.WRITE and _defines(ur.register))
                        or (ur.register == low and ur.access == OpAccess.READ_WRITE)):
                    u.discard(n)
            # stack-pointer / frame tracking
            delta, rbp = _track_sp(ins, used, delta, rbp)
            fc = ins.flow_control
            nxt = ins.next_ip
            if fc == FlowControl.NEXT:
                ip, undef = nxt, frozenset(u)
                continue
            if fc == FlowControl.RETURN:
                break
            if fc == FlowControl.CALL:
                live.update(callee(ins.near_branch_target, u, False))
                u -= _VOL
                ip, undef = nxt, frozenset(u)
                continue
            if fc == FlowControl.INDIRECT_CALL:
                live.update(u)
                u -= _VOL
                ip, undef = nxt, frozenset(u)
                continue
            if fc == FlowControl.UNCONDITIONAL_BRANCH:
                t = ins.near_branch_target
                if start <= t < finish:
                    ip, undef = t, frozenset(u)
                    continue
                live.update(callee(t, u, True))
                break
            if fc == FlowControl.CONDITIONAL_BRANCH:
                t = ins.near_branch_target
                if start <= t < finish:
                    work.append((t, frozenset(u), delta, rbp))
                else:
                    live.update(callee(t, u, True))
                ip, undef = nxt, frozenset(u)
                continue
            if fc == FlowControl.INDIRECT_BRANCH:
                raise _Decline()
            if fc in (FlowControl.INTERRUPT, FlowControl.EXCEPTION):
                break                     # int3 / ud2: path ends
            raise _Decline()
    return frozenset(live), stack[0]


def _imm(ins):
    v = ins.immediate(1)
    return v - (1 << 64) if v >= 1 << 63 else v


def _track_sp(ins, used, delta, rbp):
    """(delta, rbp) after `ins`; delta = entry RSP - current RSP.
    Raises _Decline on stack-pointer arithmetic it cannot follow."""
    mn = ins.mnemonic
    writes_rsp = any(RegisterExt.full_register(ur.register) == IReg.RSP
                     and ur.access in (OpAccess.WRITE, OpAccess.READ_WRITE,
                                       OpAccess.COND_WRITE, OpAccess.READ_COND_WRITE)
                     for ur in used)
    writes_rbp = any(RegisterExt.full_register(ur.register) == IReg.RBP
                     and ur.access in (OpAccess.WRITE, OpAccess.READ_WRITE,
                                       OpAccess.COND_WRITE, OpAccess.READ_COND_WRITE)
                     for ur in used)
    reg0 = ins.op0_register if ins.op_count > 0 and ins.op0_kind == OpKind.REGISTER else None
    if mn == Mnemonic.LEAVE:
        if rbp is None:
            raise _Decline()
        return rbp - 8, None
    if mn == Mnemonic.PUSH:
        delta += 8
    elif mn == Mnemonic.POP:
        delta -= 8
        if reg0 == IReg.RBP:
            rbp = None
        return delta, rbp
    elif mn == Mnemonic.CALL or ins.flow_control in (FlowControl.CALL,
                                                     FlowControl.INDIRECT_CALL,
                                                     FlowControl.RETURN):
        return delta, rbp
    elif writes_rsp:
        if reg0 == IReg.RSP and mn in (Mnemonic.SUB, Mnemonic.ADD) \
                and ins.op1_kind in (OpKind.IMMEDIATE8, OpKind.IMMEDIATE8TO64,
                                     OpKind.IMMEDIATE32, OpKind.IMMEDIATE32TO64):
            k = _imm(ins)
            delta += k if mn == Mnemonic.SUB else -k
        elif reg0 == IReg.RSP and mn == Mnemonic.MOV and ins.op1_kind == OpKind.REGISTER \
                and ins.op1_register == IReg.RBP and rbp is not None:
            delta = rbp
        elif reg0 == IReg.RSP and mn == Mnemonic.LEA and ins.memory_base == IReg.RBP \
                and ins.memory_index == IReg.NONE and rbp is not None:
            d = ins.memory_displacement
            d = d - (1 << 64) if d >= 1 << 63 else d
            delta = rbp - d
        else:
            raise _Decline()
    if writes_rbp and reg0 == IReg.RBP:
        if mn == Mnemonic.MOV and ins.op1_kind == OpKind.REGISTER \
                and ins.op1_register == IReg.RSP:
            rbp = delta
        elif mn == Mnemonic.LEA and ins.memory_base == IReg.RSP \
                and ins.memory_index == IReg.NONE:
            d = ins.memory_displacement
            d = d - (1 << 64) if d >= 1 << 63 else d
            rbp = delta - d
        else:
            rbp = None
    elif writes_rbp:
        rbp = None
    return delta, rbp


def entry_live_args(il, target):
    """Per-position liveness for the Win64 argument slots of `target`.

    Returns a 4-tuple of '', 'g', 'x' or 'gx', or None when the code
    does not prove it (see module doc). Memoized per Il2Cpp instance.
    Never raises.
    """
    try:
        if not _HAVE or target is None or not il.bin.is_exec_va(target):
            return None
        c = _cache(il)
        key = ('a', target)
        if key in c:
            return c[key]
        r = _regs(il, target, MAX_DEPTH)
        res = None
        if r is not None and not r[1]:
            regs = r[0]
            res = tuple(('g' if _GPR[i] in regs else '') + ('x' if _XMM[i] in regs else '')
                        for i in range(4))
        c[key] = res
        return res
    except Exception:
        return None


# Scalar SSE mnemonics by the width of the XMM *source* they read.
# `_RMW` ops also read their first (destination) operand's low lane;
# every other op0 XMM destination (movss/movsd, cvt*, sqrt*, ...) only
# writes the low lane (iced reports the upper-lane merge as READ_WRITE).
_SRC4 = ('MOVSS', 'ADDSS', 'SUBSS', 'MULSS', 'DIVSS', 'MINSS', 'MAXSS',
         'SQRTSS', 'COMISS', 'UCOMISS', 'CMPSS', 'CVTSS2SD', 'CVTSS2SI',
         'CVTTSS2SI')
_SRC8 = ('MOVSD', 'ADDSD', 'SUBSD', 'MULSD', 'DIVSD', 'MINSD', 'MAXSD',
         'SQRTSD', 'COMISD', 'UCOMISD', 'CMPSD', 'CVTSD2SS', 'CVTSD2SI',
         'CVTTSD2SI')
_RMW = ('ADDSS', 'SUBSS', 'MULSS', 'DIVSS', 'MINSS', 'MAXSS', 'COMISS',
        'UCOMISS', 'CMPSS', 'ADDSD', 'SUBSD', 'MULSD', 'DIVSD', 'MINSD',
        'MAXSD', 'COMISD', 'UCOMISD', 'CMPSD')
_WIDTH = None


def _width_tables():
    global _WIDTH
    if _WIDTH is None:
        w, rmw = {}, set()
        for n in _SRC4:
            w[getattr(Mnemonic, n)] = 4
        for n in _SRC8:
            w[getattr(Mnemonic, n)] = 8
        for n in _RMW:
            rmw.add(getattr(Mnemonic, n))
        _WIDTH = (w, frozenset(rmw))
    return _WIDTH


def _is_x0(r):
    return (RegisterExt.is_xmm(r) or RegisterExt.is_ymm(r) or RegisterExt.is_zmm(r))         and RegisterExt.number(r) == 0


# whole-register copies carry the result without typing it
_COPY_NAMES = ('MOVAPS', 'MOVUPS', 'MOVAPD', 'MOVUPD', 'MOVDQA', 'MOVDQU')
# packed ops type their XMM source lanes
_PS_NAMES = ('UNPCKLPS', 'UNPCKHPS', 'SHUFPS', 'MOVLHPS', 'ADDPS', 'SUBPS',
             'MULPS', 'DIVPS', 'MINPS', 'MAXPS', 'SQRTPS', 'CVTPS2PD')
_PD_NAMES = ('UNPCKLPD', 'UNPCKHPD', 'SHUFPD', 'ADDPD', 'SUBPD', 'MULPD',
             'DIVPD', 'MINPD', 'MAXPD', 'SQRTPD', 'CVTPD2PS')
_COPY = None


def _copy_tables():
    global _COPY
    if _COPY is None:
        packed = dict((getattr(Mnemonic, n), 4) for n in _PS_NAMES)
        packed.update((getattr(Mnemonic, n), 8) for n in _PD_NAMES)
        dest_only = frozenset(getattr(Mnemonic, n) for n in
                              ('SQRTPS', 'CVTPS2PD', 'SQRTPD', 'CVTPD2PS'))
        _COPY = (frozenset(getattr(Mnemonic, n) for n in _COPY_NAMES), packed,
                 frozenset(packed) - dest_only)
    return _COPY


def _xnum(r):
    if RegisterExt.is_xmm(r) or RegisterExt.is_ymm(r) or RegisterExt.is_zmm(r):
        return RegisterExt.number(r)
    return None


def xmm0_result_width(binary, ip, window=24):
    """Fix 132b: 4 (float) / 8 (double) when the code right after a call
    at `ip` reads the call's XMM0 result as a typed value before touching
    RAX; None otherwise. XMM0 is volatile, so a read of it right after a
    call only means the call's result.

    The result set starts as {XMM0}. A whole-register copy (`movaps
    xmm6,xmm0`) adds its destination; any other write of a member drops
    it; a later direct call drops the volatile members (XMM0-5) and makes
    RAX that call's own result. The first typed read of a member decides
    the width: a scalar SS/SD source, or a packed PS/PD source. A RAX
    touch before any later call, a type-agnostic read (xorps/andps, a
    copy to memory), an implicit XMM use, a branch, an indirect call or a
    return declines. Never raises.
    """
    try:
        if not _HAVE:
            return None
        code = binary.read(ip, window * 15)
        if not code:
            return None
        width, rmw = _width_tables()
        copies, packed, packed_rmw = _copy_tables()
        dec = Decoder(64, code, DecoderOptions.NONE)
        dec.ip = ip
        held = {0}
        rax_live = True
        for k, ins in enumerate(dec):
            if k >= window or ins.code == Code.INVALID:
                return None
            info = _FAC.info(ins)
            used = info.used_registers()
            if rax_live and any(RegisterExt.is_gpr(ur.register)
                                and RegisterExt.full_register(ur.register) == IReg.RAX
                                for ur in used):
                return None
            ops = [(j, _xnum(ins.op_register(j))) for j in range(ins.op_count)
                   if ins.op_kind(j) == OpKind.REGISTER
                   and _xnum(ins.op_register(j)) is not None]
            implicit = any(_xnum(ur.register) in held for ur in used) and \
                not any(n in held for _, n in ops)
            if implicit:
                return None
            mine = [j for j, n in ops if n in held]
            if mine:
                src = [j for j in mine if j >= 1] or \
                    ([0] if (ins.mnemonic in rmw or ins.mnemonic in packed_rmw)
                     and ins.op_count == 2 else [])
                if src:
                    if ins.mnemonic in copies and ins.op_count == 2 \
                            and ins.op0_kind == OpKind.REGISTER and ops[0][0] == 0:
                        held.add(ops[0][1])      # reg-to-reg whole copy
                        continue
                    if ins.mnemonic in width:
                        return width[ins.mnemonic]
                    if ins.mnemonic in packed:
                        return packed[ins.mnemonic]
                    return None
                # written (op0 destination, not read): no longer the result
                for j in mine:
                    held.discard(ops[[o[0] for o in ops].index(j)][1])
                if not held:
                    return None
            fc = ins.flow_control
            if fc == FlowControl.NEXT:
                continue
            if fc == FlowControl.CALL:
                held = set(n for n in held if n >= 6)
                if not held:
                    return None
                rax_live = False
                continue
            return None
        return None
    except Exception:
        return None
