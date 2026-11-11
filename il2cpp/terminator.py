"""First-terminator proof for a native routine: does it come back? (fix 143)

An il2cpp throw helper is noreturn by construction: its call site is
followed by int3 padding, and the helper itself ends in one. Deciding
"this routine returns" from a fixed-size window gives the wrong answer for
a routine whose first `ret` lies past the window -- the old screen read 256
bytes / 64 instructions, so a routine with its `ret` at instruction 87 was
published as a throw helper and every call to it rendered as a throw. The
verdict here is a property of the routine, not of the window: decode
forward to the first of

    ret          the routine returns            -> RET
    int3 / ud2   a trap, noreturn               -> TRAP
    undecodable  the bytes are not code         -> INVALID  (unknown)
    caps         512 instructions / 8192 bytes  -> CAP      (unknown)

and only `RET` is evidence against a throw helper. INVALID, CAP and
UNREADABLE never change output: the caller keeps today's accept. A
conditional or unconditional jump does not end the scan; it is the same
linear walk the old screen did, extended, so a verdict can only move from
"accepted" to "returns" where a `ret` is actually reached.

Census on the fixture (69 candidate targets, `work/overnight/
probe_noreturn.py`): 19 RET, 49 TRAP, and one target the old window gave up
on -- 0x18205f580, 87 instructions with a loop, `ret` at instruction 87 --
now RET.
"""
from il2cpp.prelude import *  # noqa: F401,F403

MAX_INSNS = 512
MAX_BYTES = 8192

RET = 'ret'
TRAP = 'trap'
INVALID = 'invalid'
CAP = 'cap'
UNREADABLE = 'unreadable'


def first_terminator(binary, va, max_insns=MAX_INSNS, max_bytes=MAX_BYTES):
    """Verdict for the routine at `va`; see the module docstring."""
    if not HAVE_ICED or binary is None:
        return UNREADABLE
    try:
        if not binary.is_exec_va(va):
            return UNREADABLE
        code = binary.read(va, max_bytes)
        if not code:
            return UNREADABLE
        dec = Decoder(64, code, DecoderOptions.NONE)
        dec.ip = va
        seen = 0
        for ins in dec:
            if ins.is_invalid:
                return INVALID
            mn = ins.mnemonic
            if mn == Mnemonic.INT3 or mn == Mnemonic.UD2:
                return TRAP
            if mn == Mnemonic.RET:
                return RET
            seen += 1
            if seen >= max_insns:
                return CAP
        return CAP
    except Exception:
        return UNREADABLE
