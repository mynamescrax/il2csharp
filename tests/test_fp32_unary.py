"""Unregistered pure-FP32-unary leaf proof: gates and declines.

Portable coverage for the il2cpp/lifter/state.py recognizer, the
calls.py consumer gate, and the highlevel.py cast skip. The positive
case uses 17 hand-encoded x64 bytes (stable ISA encodings, no fixture):
sub rsp,8 / movss xmm1,xmm0 / addss xmm0,xmm1 / add rsp,8 / ret.
"""
from types import SimpleNamespace

from iced_x86 import Mnemonic

from il2cpp.lifter.calls import _CallsMixin, _fp32_arg_ok
from il2cpp.lifter.state import _StateMixin


BASE = 0x1000
# sub rsp,8; movss xmm1,xmm0; addss xmm0,xmm1; add rsp,8; ret
CALLEE_OK = bytes([
    0x48, 0x83, 0xEC, 0x08,
    0xF3, 0x0F, 0x10, 0xC8,
    0xF3, 0x0F, 0x58, 0xC1,
    0x48, 0x83, 0xC4, 0x08,
    0xC3,
])
# mov eax,ecx (reads a GPR argument register)
GPR_READ = bytes([0x8B, 0xC1])
# sub rsp,8; xor eax,eax (zero idiom, no XMM0 traffic); add rsp,8; ret
NO_XMM = bytes([0x48, 0x83, 0xEC, 0x08, 0x31, 0xC0,
                0x48, 0x83, 0xC4, 0x08, 0xC3])
# mulss xmm0,dword ptr [rip+0]
MULSS_NEXT = bytes([0xF3, 0x0F, 0x59, 0x05, 0x00, 0x00, 0x00, 0x00])


class _FakeState(_StateMixin):
    pass


class _FakeCalls(_CallsMixin):
    pass


def _call_self(bin):
    self = _FakeCalls.__new__(_FakeCalls)
    self.bin = bin
    return self


def _fake(code, registered=False):
    il = SimpleNamespace(
        addr_candidates={BASE: [('method', 0)]} if registered else {},
        addr_to_method={},
        function_extent=lambda va: (BASE, BASE + len(code)),
        bin=SimpleNamespace(
            is_exec_va=lambda va: va == BASE,
            read=lambda va, n: code if va == BASE else None,
            exports={},
        ),
    )
    self = _FakeState.__new__(_FakeState)
    self.il = il
    self.bin = il.bin
    return self


def test_table_lists_core_shapes():
    self = _fake(CALLEE_OK)
    tab, _v3, _names = self._fp32_table()
    assert tab[Mnemonic.MOV][0] == 'w1'
    assert tab[Mnemonic.ADDSS][0] == 'rw1'
    assert tab[Mnemonic.VMULSS][0] == 'vex3'
    assert tab[Mnemonic.CMP][0] == 'rall'
    assert Mnemonic.PUSH not in tab


def test_fires_on_minimal_unary():
    self = _fake(CALLEE_OK)
    assert self._fp32_inputs(BASE, 0) == frozenset({'XMM0'})
    assert self._is_fp32_unary_leaf(BASE) is True


def test_declines_registered_target():
    self = _fake(CALLEE_OK, registered=True)
    assert self._fp32_inputs(BASE, 0) is None
    assert self._is_fp32_unary_leaf(BASE) is False


def test_declines_gpr_input():
    self = _fake(GPR_READ + CALLEE_OK)
    inputs = self._fp32_inputs(BASE, 0)
    assert inputs is not None and 'RCX' in inputs
    assert self._is_fp32_unary_leaf(BASE) is False


def test_declines_missing_xmm0():
    self = _fake(NO_XMM)
    assert self._fp32_inputs(BASE, 0) == frozenset()
    assert self._is_fp32_unary_leaf(BASE) is False


# mulss xmm0,xmm1 reads a second vector register: a binary op is not
# unary, so the proof must decline instead of dropping an argument
BINARY_OP = bytes([0x48, 0x83, 0xEC, 0x08, 0xF3, 0x0F, 0x59, 0xC1,
                   0x48, 0x83, 0xC4, 0x08, 0xC3])


def test_declines_binary_op():
    self = _fake(BINARY_OP)
    assert self._fp32_inputs(BASE, 0) == frozenset({'XMM0', 'XMM1'})
    assert self._is_fp32_unary_leaf(BASE) is False


# Frameless leaf: no entry sub; XMM0 is read first, the [rsp+8]
# spill is written in the entry block (dominating) and read back
# covered. Same shape with the spill read first joins SHADOWARG
# (caller-home input) and declines.
FRAMELESS_OK = bytes([
    0x0F, 0x28, 0xC8,
    0xF3, 0x0F, 0x11, 0x4C, 0x24, 0x08,
    0xF3, 0x0F, 0x10, 0x44, 0x24, 0x08,
    0xF3, 0x0F, 0x58, 0xC1,
    0xC3,
])
FRAMELESS_READ_FIRST = bytes([
    0xF3, 0x0F, 0x10, 0x4C, 0x24, 0x08,
    0xC3,
])


def test_frameless_shadow_rules():
    self = _fake(FRAMELESS_OK)
    assert self._fp32_inputs(BASE, 0) == frozenset({'XMM0'})
    assert self._is_fp32_unary_leaf(BASE) is True
    self = _fake(FRAMELESS_READ_FIRST)
    assert 'SHADOWARG' in (self._fp32_inputs(BASE, 0) or frozenset())
    assert self._is_fp32_unary_leaf(BASE) is False


def test_scalar_next_gate():
    bin = SimpleNamespace(read=lambda va, n: MULSS_NEXT)
    ins = SimpleNamespace(ip=0x1000, next_ip=0x2000)
    assert _CallsMixin._fp32_scalar_next(
        _call_self(bin), ins) == 'f'
    bin2 = SimpleNamespace(read=lambda va, n: b'\xC3')
    assert _CallsMixin._fp32_scalar_next(
        _call_self(bin2), ins) is None
    bin3 = SimpleNamespace(read=lambda va, n: None)
    assert _CallsMixin._fp32_scalar_next(
        _call_self(bin3), ins) is None


# test rbx,rbx / je past-the-consume / movss xmm12,[rip] / mulss xmm0,xmm12
WALK_FIRE = bytes([
    0x48, 0x85, 0xDB,
    0x74, 0x0E,
    0xF3, 0x44, 0x0F, 0x10, 0x25, 0x00, 0x00, 0x00, 0x00,
    0xF3, 0x41, 0x0F, 0x59, 0xC4,
])
# same stream with the je landing exactly on the mulss (merge, not clean)
WALK_REJOIN = bytes([
    0x48, 0x85, 0xDB,
    0x74, 0x09,
    0xF3, 0x44, 0x0F, 0x10, 0x25, 0x00, 0x00, 0x00, 0x00,
    0xF3, 0x41, 0x0F, 0x59, 0xC4,
])
# movaps xmm0,xmm1 (XMM0 clobber) then the mulss
WALK_CLOBBER = bytes([0x0F, 0x28, 0xC1]) + bytes([
    0xF3, 0x41, 0x0F, 0x59, 0xC4,
])
# a second call before the mulss (volatile clobber)
WALK_CALL = bytes([0xE8, 0x00, 0x00, 0x00, 0x00]) + bytes([
    0xF3, 0x41, 0x0F, 0x59, 0xC4,
])
# 17 nops push the mulss past the 16-instruction cap
WALK_FAR = bytes([0x90] * 17) + bytes([0xF3, 0x0F, 0x59, 0x05,
                                       0x00, 0x00, 0x00, 0x00])


def _walk(stream):
    base = 0x2000
    bin = SimpleNamespace(
        read=lambda va, n: stream[va - base:va - base + n]
        if 0 <= va - base < len(stream) else None)
    ins = SimpleNamespace(ip=0x1000, next_ip=base)
    return _CallsMixin._fp32_scalar_next(_call_self(bin), ins)


def test_walk_fires_past_flags_and_branch():
    assert _walk(WALK_FIRE) == 'f'


def test_walk_declines_rejoin_clobber_call_distance():
    assert _walk(WALK_REJOIN) is None
    assert _walk(WALK_CLOBBER) is None
    assert _walk(WALK_CALL) is None
    assert _walk(WALK_FAR) is None


# cvtss2sd xmm1,xmm0 / cvttss2si eax,xmm0 / movaps xmm6,xmm0
CONV_FIRE = bytes([0xF3, 0x0F, 0x5A, 0xC8])
TRUNC_FIRE = bytes([0xF3, 0x0F, 0x2C, 0xC0])
COPY_FIRE = bytes([0x0F, 0x28, 0xF0])


def test_walk_fires_conversions_and_copy():
    assert _walk(CONV_FIRE) == 'f'
    assert _walk(TRUNC_FIRE) == 'f'
    assert _walk(COPY_FIRE) == 'f'


# cvttsd2si eax,xmm0 / cvtsd2si eax,xmm0 (double consumes) fire 'd';
# cvtsd2ss (double to float narrowing) is not evidenced and declines
SD_FIRE = bytes([0xF2, 0x0F, 0x2C, 0xC0])
SD_FIRE2 = bytes([0xF2, 0x0F, 0x2D, 0xC0])
SD_NARROW = bytes([0xF2, 0x0F, 0x5A, 0xC8])


def test_walk_double_consume_width():
    assert _walk(SD_FIRE) == 'd'
    assert _walk(SD_FIRE2) == 'd'
    assert _walk(SD_NARROW) is None


def test_arg_ok_spellability():
    assert _fp32_arg_ok('volume') is True
    assert _fp32_arg_ok('t2 & float.NaN') is True
    assert _fp32_arg_ok('a?.b') is True
    assert _fp32_arg_ok('a ?? b') is True
    assert _fp32_arg_ok('t2 & float.NaN & (double)(?)') is False
    assert _fp32_arg_ok('?') is False
