"""First-terminator proof (`il2cpp/terminator.py`) and the throw-helper screen.

A throw helper never returns, so a `ret` reached from its entry disproves
it. The old screen looked at 256 bytes / 64 instructions only; a routine
whose first `ret` is further in (0x18205f580 on the fixture: instruction 87)
was published as a throw helper. Every case here is raw bytes, no fixture.
"""
import pytest

from il2cpp.prelude import HAVE_ICED

pytestmark = pytest.mark.skipif(not HAVE_ICED, reason='iced_x86 required')

from iced_x86 import Decoder, DecoderOptions, Mnemonic  # noqa: E402

from il2cpp import Decompiler  # noqa: E402
from il2cpp.terminator import (CAP, INVALID, MAX_BYTES, MAX_INSNS, RET, TRAP,  # noqa: E402
                               UNREADABLE, first_terminator)

BASE = 0x180100000
NOP = '90'
RET_ = 'c3'
INT3 = 'cc'
UD2 = '0f0b'
SUB_RSP = '4883ec28'                  # sub rsp,28h
CALL_SELF = 'e8fbffffff'              # call rel32 (target is irrelevant here)
INVALID_OP = '06'                     # push es: not encodable in 64-bit mode


class FakeBin:
    """Just the two methods the proof reads; `blob` starts at BASE."""

    def __init__(self, blob, exec_ok=True):
        self.blob = blob
        self.exec_ok = exec_ok

    def is_exec_va(self, va):
        return self.exec_ok and BASE <= va < BASE + len(self.blob)

    def read(self, va, n):
        o = va - BASE
        return self.blob[o:o + n] if 0 <= o < len(self.blob) else None


def _code(*parts):
    return bytes.fromhex(''.join(parts))


def _old_returns(b, va):
    """The pre-fix screen, verbatim from `_eh_helper_returns`."""
    code = b.read(va, 256)
    dec = Decoder(64, code, DecoderOptions.NONE)
    dec.ip = va
    seen = 0
    for ins in dec:
        if ins.is_invalid:
            break
        if ins.mnemonic in (Mnemonic.INT3, Mnemonic.UD2):
            break
        if ins.mnemonic == Mnemonic.RET:
            return True
        seen += 1
        if seen >= 64:
            break
    return False


def test_ret_first_is_a_returner():
    assert first_terminator(FakeBin(_code(RET_)), BASE) == RET


def test_throw_thunk_traps():
    # the shape of every il2cpp raise helper: sub rsp / call / int3
    b = FakeBin(_code(SUB_RSP, CALL_SELF, INT3))
    assert first_terminator(b, BASE) == TRAP
    assert first_terminator(FakeBin(_code(NOP, UD2)), BASE) == TRAP


def test_first_terminator_wins():
    assert first_terminator(FakeBin(_code(INT3, RET_)), BASE) == TRAP
    assert first_terminator(FakeBin(_code(NOP, RET_, INT3)), BASE) == RET


def test_ret_past_the_old_window_is_found():
    # `ret` is the 78th instruction: the old 64-instruction window gave up first
    blob = _code(NOP * 77, RET_)
    b = FakeBin(blob)
    assert _old_returns(b, BASE) is False
    assert first_terminator(b, BASE) == RET


def test_ret_past_the_old_byte_window():
    # long instructions: 40 x 7 bytes = 280 bytes before the ret, inside 64 insns
    mov = '48c7c001000000'                       # mov rax,1 (7 bytes)
    b = FakeBin(_code(mov * 40, RET_))
    assert _old_returns(b, BASE) is False        # 256-byte window ends before the ret
    assert first_terminator(b, BASE) == RET


def test_instruction_cap_boundaries():
    last = FakeBin(_code(NOP * (MAX_INSNS - 1), RET_))     # ret is instruction 512
    assert first_terminator(last, BASE) == RET
    past = FakeBin(_code(NOP * MAX_INSNS, RET_))           # ret is instruction 513
    assert first_terminator(past, BASE) == CAP


def test_byte_cap_ends_the_scan_as_unknown():
    b = FakeBin(_code(NOP * 200, RET_))
    assert first_terminator(b, BASE, max_bytes=64) == CAP
    assert first_terminator(b, BASE, max_bytes=MAX_BYTES) == RET


def test_undecodable_bytes_are_unknown():
    assert first_terminator(FakeBin(_code(NOP, INVALID_OP, RET_)), BASE) == INVALID


def test_jumps_do_not_end_the_scan():
    # the walk is linear, exactly as before: a ret behind a jump is still reached
    assert first_terminator(FakeBin(_code('7400', RET_)), BASE) == RET      # je +0
    assert first_terminator(FakeBin(_code('eb00', RET_)), BASE) == RET      # jmp +0


def test_unreadable_targets_are_unknown():
    assert first_terminator(FakeBin(_code(RET_), exec_ok=False), BASE) == UNREADABLE
    assert first_terminator(FakeBin(_code(RET_)), BASE + 0x1000) == UNREADABLE
    assert first_terminator(None, BASE) == UNREADABLE


# ------------------------------------------------------------ the screen

class _L:
    def __init__(self, b):
        self.il = type('IL', (), {'bin': b})()


def _screen(blob, va=BASE):
    dec = Decompiler.__new__(Decompiler)
    dec.L = _L(FakeBin(blob))
    return dec, dec._eh_helper_returns(va)


def test_screen_rejects_a_late_returner_but_not_a_throw_thunk():
    assert _screen(_code(NOP * 77, RET_))[1] is True
    assert _screen(_code(SUB_RSP, CALL_SELF, INT3))[1] is False


def test_screen_keeps_todays_accept_for_unknowns():
    assert _screen(_code(NOP, INVALID_OP, RET_))[1] is False
    assert _screen(_code(NOP * (MAX_INSNS + 1), RET_))[1] is False
    dec = Decompiler.__new__(Decompiler)
    dec.L = type('L', (), {})()                                  # no il at all
    assert dec._eh_helper_returns(BASE) is False


def test_screen_caches_per_target():
    dec, first = _screen(_code(RET_))
    assert first is True
    dec.L.il.bin.blob = _code(INT3)                              # a stale cache must win
    assert dec._eh_helper_returns(BASE) is True
