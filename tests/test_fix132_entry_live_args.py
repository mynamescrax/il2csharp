"""Fix 132: entry-live argument proof for plain `sub_` callees, and the
caller-proven XMM0 result width (portable: synthetic x64 bytes)."""
import pytest

pytest.importorskip('iced_x86')

from il2cpp.entrylive import entry_live_args, xmm0_result_width  # noqa: E402

BASE = 0x180001000


class _Bin(object):
    def __init__(self, blobs):
        self.blobs = blobs

    def _find(self, va):
        for b, d in self.blobs.items():
            if b <= va < b + len(d):
                return b, d
        return None, None

    def read(self, va, n):
        b, d = self._find(va)
        return None if d is None else d[va - b:va - b + n]

    def is_exec_va(self, va):
        return self._find(va)[1] is not None


class _IL(object):
    def __init__(self, blobs):
        self.bin = _Bin(blobs)

    def function_extent(self, va):
        b, d = self.bin._find(va)
        if d is None:
            return va, va + 0x1000
        return b, b + len(d)


def _sig(code, extra=None):
    blobs = {BASE: bytes.fromhex(code)}
    blobs.update(extra or {})
    return entry_live_args(_IL(blobs), BASE)


def _rel32(src_next, dst):
    return (dst - src_next).to_bytes(4, 'little', signed=True).hex()


def test_two_float_args():
    # movaps xmm4,xmm1 ; addss xmm0,xmm4 ; ret
    assert _sig('0f28e1' 'f30f58c4' 'c3') == ('x', 'x', '', '')


def test_write_before_read_is_not_an_argument():
    # xor r8d,r8d ; mov rax,rcx ; ret  -> only RCX
    assert _sig('4531c0' '4889c8' 'c3') == ('g', '', '', '')


def test_dead_interior_position():
    # mov rax,rdx ; ret  -> position 0 dead, 1 live
    assert _sig('4889d0' 'c3') == ('', 'g', '', '')


def test_low_lane_write_defines_the_float_argument():
    # movss xmm1,xmm0 (writes xmm1's low lane) ; addss xmm1,xmm1 ; ret
    assert _sig('f30f10c8' 'f30f58c9' 'c3') == ('x', '', '', '')


def test_stack_argument_read_declines():
    # mov rax,[rsp+28h] ; ret  -> fifth argument read
    assert _sig('488b442428' 'c3') is None
    # sub rsp,28h ; mov rax,[rsp+50h] ; add rsp,28h ; ret  (entry +0x28)
    assert _sig('4883ec28' '488b442450' '4883c428' 'c3') is None


def test_shadow_space_read_is_not_a_stack_argument():
    # sub rsp,28h ; mov rax,[rsp+48h] (entry +0x20) ; add rsp,28h ; ret
    assert _sig('4883ec28' '488b442448' '4883c428' 'c3') == ('', '', '', '')


def test_indirect_branch_declines():
    # jmp rax
    assert _sig('ffe0') is None


def test_tail_jump_follows_the_target():
    other = BASE + 0x100
    # jmp other ; other: mov rax,rdx ; ret
    code = 'e9' + _rel32(BASE + 5, other)
    assert _sig(code, {other: bytes.fromhex('4889d0c3')}) == ('', 'g', '', '')


def test_tail_jump_into_unprovable_target_declines():
    code = 'e9' + _rel32(BASE + 5, BASE + 0x7000000)
    assert _sig(code) is None


def test_call_to_unprovable_target_reads_everything_still_live():
    # mov ecx,1 ; call far ; ret -> RDX/R8/R9/XMM0-3 may be forwarded
    code = 'b901000000' + 'e8' + _rel32(BASE + 10, BASE + 0x7000000) + 'c3'
    assert _sig(code) == ('x', 'gx', 'gx', 'gx')


def test_call_to_provable_target_reads_only_its_arguments():
    other = BASE + 0x100
    # call other ; ret ; other: mov rax,rcx ; ret
    code = 'e8' + _rel32(BASE + 5, other) + 'c3'
    assert _sig(code, {other: bytes.fromhex('4889c8c3')}) == ('g', '', '', '')


def test_memoized_answer_is_order_independent():
    other = BASE + 0x100
    blobs = {BASE: bytes.fromhex('e8' + _rel32(BASE + 5, other) + 'c3'),
             other: bytes.fromhex('4889c8c3')}
    a = _IL(blobs)
    first = entry_live_args(a, other), entry_live_args(a, BASE)
    b = _IL(blobs)
    second = entry_live_args(b, BASE), entry_live_args(b, other)
    assert first == (second[1], second[0])


def _width(code):
    return xmm0_result_width(_Bin({BASE: bytes.fromhex(code)}), BASE)


def test_result_width_float_use():
    # mulss xmm0,[rip+0] ; ret
    assert _width('f30f590500000000' 'c3') == 4


def test_result_width_double_source():
    # cvtsd2ss xmm1,xmm0 -> XMM0 read as a double
    assert _width('f20f5ac8' 'c3') == 8


def test_result_width_follows_a_whole_register_copy_across_a_call():
    # movaps xmm6,xmm0 ; movaps xmm0,xmm7 ; call +0 ; unpcklps xmm6,xmm0
    assert _width('0f28f0' '0f28c7' 'e800000000' '0f14f0') == 4


def test_result_width_volatile_result_dies_at_a_later_call():
    # call +0 ; addss xmm0,xmm1 -> that XMM0 is the second call's result
    assert _width('e800000000' 'f30f58c1') is None


def test_result_width_declines_untyped_copy_write_and_rax():
    assert _width('0f28f0' 'c3') is None          # movaps xmm6,xmm0 ; ret
    assert _width('0f29442420' 'c3') is None      # movaps [rsp+20h],xmm0
    assert _width('f30f2ac1' 'c3') is None        # cvtsi2ss xmm0,ecx (write)
    assert _width('4889c1' 'f30f590500000000') is None   # mov rcx,rax first
    assert _width('c3') is None                   # nothing read before ret
