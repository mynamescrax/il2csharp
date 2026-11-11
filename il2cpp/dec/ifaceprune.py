"""fix 139: prune the inlined interface-dispatch fast path.

IL2CPP inlines an interface call as a scan of the receiver class's
interface table (`movzx n,word [k+0x12E]`, `mov t,[k+0xB0]`, a
`cmp [t+i*16],iface` loop) whose hit arm computes the VirtualInvokeData
pointer `k + 0x138 + 16*(offset+slot)`, and whose miss arm calls the
resolve helper (`il2cpp_interface_get_method(obj, typeof(I), slot)`).
Both arms join with the same entry in a register and `call [entry]`.

By the runtime contract the helper returns exactly the entry the scan
finds, so forcing the entry test onto the miss arm preserves meaning:
the scan blocks become unreachable and the join sees one definition --
the helper result -- which the lifter renders as a managed interface
call. The rewrite is gated structurally: the scan region is entered only
through the test, exits only to the miss arm or the join, holds the
`0x138` entry fold and a `[k+0xB0]` table load, performs no store /
call / non-GPR write, and every callee-saved register it writes is dead
at the join (volatile ones are undefined after the miss arm's call).
Anything else declines and keeps the honest scan rendering.
"""
from iced_x86 import (InstructionInfoFactory, OpAccess, RegisterExt, Mnemonic,
                      OpKind, FlowControl, Register as IReg)

_VOL = {IReg.RAX, IReg.RCX, IReg.RDX, IReg.R8, IReg.R9, IReg.R10, IReg.R11}
_ARGR = {IReg.RCX, IReg.RDX, IReg.R8, IReg.R9}
_WR = {OpAccess.WRITE, OpAccess.READ_WRITE, OpAccess.COND_WRITE,
       OpAccess.READ_COND_WRITE}
_RD = {OpAccess.READ, OpAccess.READ_WRITE, OpAccess.COND_READ,
       OpAccess.READ_COND_WRITE}
_FAC = InstructionInfoFactory()


def _gpr_writes(ins):
    """Full GPRs written, or None when the instruction is not a pure
    register-only computation (memory store, call, stack, xmm, ...)."""
    if ins.flow_control in (FlowControl.CALL, FlowControl.INDIRECT_CALL,
                            FlowControl.RETURN, FlowControl.INTERRUPT,
                            FlowControl.EXCEPTION, FlowControl.INDIRECT_BRANCH):
        return None
    info = _FAC.info(ins)
    for um in info.used_memory():
        if um.access in _WR:
            return None
    out = set()
    for ur in info.used_registers():
        if ur.access in _WR:
            r = ur.register
            if not RegisterExt.is_gpr(r):
                return None
            f = RegisterExt.full_register(r)
            if f == IReg.RSP:
                return None
            out.add(f)
    return out


def _dead_at(blocks, start, regs, budget=400):
    """True when none of `regs` is read on any path from block `start`
    before being fully overwritten."""
    work = [(start, frozenset(regs))]
    seen = set()
    steps = 0
    while work:
        bid, live = work.pop()
        if (bid, live) in seen:
            continue
        seen.add((bid, live))
        steps += 1
        if steps > budget:
            return False
        b = blocks[bid]
        live = set(live)
        for ins in b.insns:
            if not live:
                break
            fc = ins.flow_control
            info = _FAC.info(ins)
            for ur in info.used_registers():
                if ur.access in _RD and RegisterExt.is_gpr(ur.register) \
                        and RegisterExt.full_register(ur.register) in live:
                    return False
            if fc in (FlowControl.CALL, FlowControl.INDIRECT_CALL):
                if live & _ARGR:
                    return False
                live -= _VOL
                continue
            if fc == FlowControl.RETURN:
                if IReg.RAX in live:
                    return False
                live = set()
                break
            for ur in info.used_registers():
                if ur.access == OpAccess.WRITE and RegisterExt.is_gpr(ur.register) \
                        and RegisterExt.size(ur.register) >= 4:
                    live.discard(RegisterExt.full_register(ur.register))
        if not live:
            continue
        t = b.term[0] if b.term else 'stop'
        if t in ('ret', 'abort'):
            if t == 'ret' and IReg.RAX in live:
                return False
            continue
        if t == 'stop' or not b.succs:
            return False
        for s in b.succs:
            work.append((s, frozenset(live)))
    return True


def _reads_before_write(insns, reg, call_args=_ARGR):
    """True when `reg` (full GPR) is read in `insns` before a full write.
    A call reads `call_args` (default: the Win64 argument registers)."""
    for ins in insns:
        info = _FAC.info(ins)
        for ur in info.used_registers():
            if ur.access in _RD and RegisterExt.is_gpr(ur.register) \
                    and RegisterExt.full_register(ur.register) == reg:
                return True
        if ins.flow_control in (FlowControl.CALL, FlowControl.INDIRECT_CALL):
            return reg in call_args
        for ur in info.used_registers():
            if ur.access == OpAccess.WRITE and RegisterExt.is_gpr(ur.register) \
                    and RegisterExt.size(ur.register) >= 4 \
                    and RegisterExt.full_register(ur.register) == reg:
                return False
    return False


def _dead_count_test(pb, miss_insns):
    """ips of the entry test's interface-count load and compare, once the
    test is forced: `movzx D,word [k+0x12E]` ... `cmp/test ..D..; jcc`,
    when nothing else in the test block after the load and nothing on
    the miss arm before the helper call reads D. Else ()."""
    ins = pb.insns
    if len(ins) < 3 or ins[-2].mnemonic not in (Mnemonic.CMP, Mnemonic.TEST):
        return ()
    cmp = ins[-2]
    for j in range(len(ins) - 3, -1, -1):
        x = ins[j]
        if x.mnemonic == Mnemonic.MOVZX and x.op0_kind == OpKind.REGISTER \
                and x.op1_kind == OpKind.MEMORY and x.memory_displacement == 0x12E:
            d = RegisterExt.full_register(x.op0_register)
            if d == IReg.RSP or d not in _VOL:
                return ()
            if _reads_before_write(ins[j + 1:-2], d):
                return ()
            if not any(ur.access in _RD and RegisterExt.is_gpr(ur.register)
                       and RegisterExt.full_register(ur.register) == d
                       for ur in _FAC.info(cmp).used_registers()):
                return ()
            # the resolve helper takes (obj, iface, slot) in RCX/RDX/R8
            # and never reads R9 (`_is_iface_resolve_helper`)
            if _reads_before_write(miss_insns, d,
                                   call_args={IReg.RCX, IReg.RDX, IReg.R8}):
                return ()
            return (x.ip, cmp.ip)
    return ()


def _is_rr_mov(ins):
    return ins.mnemonic == Mnemonic.MOV and ins.op0_kind == OpKind.REGISTER \
        and ins.op1_kind == OpKind.REGISTER and RegisterExt.is_gpr64(ins.op0_register) \
        and RegisterExt.is_gpr64(ins.op1_register)


def iface_fast_path_prune(blocks, names, stats=None, skip=None):
    """Rewrite every proved inline interface dispatch in `blocks` (see the
    module docstring); return the number of fast paths pruned. `names`
    maps helper VAs to runtime names. Rebuilds preds when it rewrites.
    When `skip` (the lifter's skip-ip set) is given, the forced test's
    now-dead interface-count load and compare join it, so no orphan
    `[k+0x12E]` read renders."""
    def note(k):
        if stats is not None:
            stats[k] = stats.get(k, 0) + 1
    n = 0
    for bm in blocks:
        if not bm.insns:
            continue
        k = None
        for j, ins in enumerate(bm.insns):
            if ins.mnemonic == Mnemonic.CALL and ins.op0_kind == OpKind.NEAR_BRANCH64 \
                    and names.get(ins.near_branch_target) == 'il2cpp_interface_get_method':
                k = j
        if k is None:
            continue
        note('sites')
        tail = list(bm.insns[k + 1:])
        if tail and tail[-1].mnemonic == Mnemonic.JMP:
            tail = tail[:-1]
            if not bm.term or bm.term[0] != 'jmp':
                note('d_tail')
                continue
        elif not bm.term or bm.term[0] != 'fall':
            note('d_tail')
            continue
        join = bm.term[1]
        # the resolved entry travels from RAX through register copies
        res = IReg.RAX
        ok = True
        for t in tail:
            if _is_rr_mov(t) and t.op1_register == res:
                res = t.op0_register
            else:
                ok = False
        if not ok:
            note('d_tail2')
            continue
        done = False
        for p in list(bm.preds):
            pb = blocks[p]
            if not pb.term or pb.term[0] != 'jcc':
                continue
            ti, fi = pb.term[1], pb.term[2]
            other = fi if ti == bm.bid else ti
            if other < 0 or other in (bm.bid, join) or {ti, fi} != {bm.bid, other}:
                continue
            region, stack, ok = set(), [other], True
            while stack and ok:
                x = stack.pop()
                if x in region:
                    continue
                if x == p or len(region) >= 12:
                    ok = False
                    break
                region.add(x)
                for s in blocks[x].succs:
                    if s not in (bm.bid, join):
                        stack.append(s)
            if not ok:
                continue
            allowed = region | {p}
            if any(q not in allowed for x in region for q in blocks[x].preds):
                note('d_entry')
                continue
            if any(q not in allowed for q in bm.preds):
                note('d_misspreds')
                continue
            if any(q not in region and q != bm.bid for q in blocks[join].preds):
                note('d_joinpreds')
                continue
            hits = [x for x in region if join in blocks[x].succs]
            if not hits or not any(
                    i.mnemonic == Mnemonic.ADD and i.op1_kind in (
                        OpKind.IMMEDIATE32TO64, OpKind.IMMEDIATE32)
                    and i.immediate32 == 0x138
                    for x in hits for i in blocks[x].insns):
                note('d_hit')
                continue
            if not any(i.op1_kind == OpKind.MEMORY and i.memory_displacement == 0xB0
                       for x in region for i in blocks[x].insns):
                note('d_table')
                continue
            written = set()
            for x in region:
                for i in blocks[x].insns:
                    w = _gpr_writes(i)
                    if w is None:
                        written = None
                        break
                    written |= w
                if written is None:
                    break
            if written is None:
                note('d_impure')
                continue
            # volatile registers are undefined after the miss path's call
            # (only the resolved entry survives), so no JOIN code reads
            # them; a callee-saved register the scan wrote must be dead
            written -= _VOL
            if written and not _dead_at(blocks, join, written):
                note('d_live')
                continue
            # rewrite: the entry test always takes the miss path
            pb.term = ('jmp', bm.bid)
            pb.succs = [bm.bid]
            pb.cond = None
            if skip is not None:
                skip.update(_dead_count_test(pb, bm.insns[:k + 1]))
            for x in region:
                blocks[x].succs = []
                blocks[x].term = ('abort',)
            for b in blocks:
                b.preds = []
            for b in blocks:
                for s in b.succs:
                    if 0 <= s < len(blocks):
                        blocks[s].preds.append(b.bid)
            n += 1
            done = True
            note('pruned')
            break
        if not done:
            note('d_nopred')
    return n
