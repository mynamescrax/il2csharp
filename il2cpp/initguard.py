"""Metadata-init flag guards (the `s_Il2CppMethodInitialized` idiom) -- fix 142.

IL2CPP wraps a method's lazy runtime-metadata setup in a one-shot flag:

    cmp byte [rip+X],0 ; <gap> ; jne T
    (lea rcx,[rip+Y] ; call init_meta) x N ; <body>
    mov byte [rip+X],1
  T:

The cmp, the jne, the `lea rcx` / `call init_meta` pairs and the flag store
are bookkeeping and are skipped; everything else in the gap and the body is
real code and keeps lifting. `Decompiler._guards` and the flat
`Lifter.lift` both call this one function, so the two cannot drift.

The windows come from a census of this fixture (116,178 methods, 64,017
guards, `work/overnight/probe_guard.py`), not from another binary:

* The guard branch is always `jne`, and in all 64,017 guards every
  instruction between the cmp and the jne leaves EFLAGS alone. The gap
  rule is therefore exact -- non-branching, no EFLAGS read or write, so
  the jne still consumes the cmp -- instead of a mnemonic list. The old
  rule (MOV/MOVZX within four instructions) missed 8,998 guards in 8,092
  methods: SIMD saves and spills sit in the gap, and the jne is often the
  fifth instruction or later. Recognized guards flatten at a gap of 8
  (63,651) and reach 63,980 of 64,016 at 16.
* The flag store lands at jne + 2N + 1 for N inlined inits, up to 157
  instructions, so the body is bounded by the jne target T and BODY_MAX
  is only a runaway cap. The body may hold the original mnemonics plus
  pure data moves; control flow of any kind declines (1 guard in 64,017).
* `lock or [rsp],0`, MSVC's memory barrier, counts in the body only once
  the init call has been seen. This fixture has none (0 of 116,178
  methods); other IL2CPP builds emit it ahead of the flag store.
"""
from il2cpp.prelude import *  # noqa: F401,F403
from il2cpp.text import imm_of

GAP_MAX = 16
BODY_MAX = 1024

_T = {}


def _tables():
    if not _T:
        M = Mnemonic
        _T['plain'] = frozenset((M.LEA, M.MOV, M.CALL, M.MOVZX, M.XOR, M.PUSH, M.SUB))
        _T['simd'] = frozenset((M.MOVAPS, M.MOVUPS, M.MOVSS, M.MOVSD, M.MOVQ, M.MOVD,
                                M.MOVDQA, M.MOVDQU, M.MOVSXD, M.MOVSX))
    return _T


def _flag_store(w, slot, value=None):
    return (w.mnemonic == Mnemonic.MOV and w.op0_kind == OpKind.MEMORY
            and w.memory_base == IReg.RIP and w.memory_size == 1
            and w.ip_rel_memory_address == slot
            and (value is None or imm_of(w, 1) == value))


def _is_barrier(w):
    return (w.mnemonic == Mnemonic.OR and w.has_lock_prefix
            and w.op0_kind == OpKind.MEMORY and w.memory_base == IReg.RSP
            and w.op1_kind != OpKind.REGISTER and imm_of(w, 1) == 0)


def metadata_init_guards(raw, init_meta):
    """ips to skip for every metadata-init flag guard in `raw`."""
    tb = _tables()
    plain, simd = tb['plain'], tb['simd']
    skip = set()
    n = len(raw)
    for i, ins in enumerate(raw):
        if not (ins.mnemonic == Mnemonic.CMP and ins.op0_kind == OpKind.MEMORY
                and ins.memory_base == IReg.RIP and ins.memory_size == 1
                and imm_of(ins, 1) == 0):
            continue
        slot = ins.ip_rel_memory_address
        j = None
        for k in range(i + 1, min(i + 1 + GAP_MAX, n)):
            w = raw[k]
            if w.flow_control == FlowControl.CONDITIONAL_BRANCH and w.op0_kind == OpKind.NEAR_BRANCH64:
                j = k
                break
            if w.flow_control != FlowControl.NEXT or w.rflags_read or w.rflags_modified:
                break
        if j is None:
            continue
        T = raw[j].near_branch_target
        found = False
        saw_init = False
        for k in range(j + 1, min(j + 1 + BODY_MAX, n)):
            w = raw[k]
            if _flag_store(w, slot, 1):
                if w.next_ip == T or (k + 1 < n and raw[k + 1].ip == T):
                    found = True
                break
            mn = w.mnemonic
            if mn == Mnemonic.CALL and w.op0_kind == OpKind.NEAR_BRANCH64 \
                    and w.near_branch_target == init_meta:
                saw_init = True
            if not (mn in plain
                    or (mn in simd and (w.op0_kind == OpKind.REGISTER or w.op1_kind == OpKind.REGISTER))
                    or (saw_init and _is_barrier(w))):
                break
            if w.ip >= T:
                break
        if not found:
            continue
        skip.add(ins.ip)
        skip.add(raw[j].ip)
        for k in range(j + 1, n):
            w = raw[k]
            if _flag_store(w, slot):
                skip.add(w.ip)
                break
            if w.mnemonic == Mnemonic.LEA and w.op0_register == IReg.RCX \
                    and w.memory_base == IReg.RIP:
                skip.add(w.ip)
            elif w.mnemonic == Mnemonic.CALL and w.op0_kind == OpKind.NEAR_BRANCH64 \
                    and w.near_branch_target == init_meta:
                skip.add(w.ip)
            elif _is_barrier(w):
                skip.add(w.ip)
    return skip
