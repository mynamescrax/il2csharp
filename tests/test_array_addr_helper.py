"""Bounds-checked element-address helpers are named and trimmed.

Ground truth: 0x1803ed830 (stride 0x178 via imul) and 0x1803ed860
(stride 0x60 via lea/shl) compute RCX+0x20+index*stride with an
unsigned OOB guard -- the Il2CppArray SZARRAY layout. Today they spray
four stale args; naming routes through `il2cpp_array_addr` with arity 2
(array, index). The stride rides in rt_array_addr for the indexed
render follow-up.
"""
from types import SimpleNamespace as NS

from il2cpp import Lifter

BODY_A = bytes.fromhex(
    '4883ec283b511873134869c2780100004883c0204803c14883c428c3e84f7e0400cc')
BODY_B = bytes.fromhex(
    '4883ec283b51187314488d045248c1e0054883c0204803c14883c428c3e81e7e0400cc')


def lifter_for(body, target=0x5000, cands=None):
    lift = Lifter.__new__(Lifter)
    lift.il = NS(addr_candidates=cands or {},
                 function_extent=lambda va: (target, target + len(body)))
    lift.bin = NS(read=lambda va, n: body if va == target else None,
                  is_exec_va=lambda va: va == target,
                  exports={})
    return lift, target


def test_imul_variant_proves_stride():
    lift, target = lifter_for(BODY_A)
    assert lift._is_array_addr_helper(target) == 0x178


def test_lea_variant_proves_stride():
    lift, target = lifter_for(BODY_B)
    assert lift._is_array_addr_helper(target) == 0x60


def test_rejects_mutated_skeleton():
    bad = bytearray(BODY_A)
    bad[5] ^= 0xFF                      # the [rcx+0x18] length guard
    lift, target = lifter_for(bytes(bad))
    assert lift._is_array_addr_helper(target) is None
    bad2 = bytearray(BODY_B)
    bad2[14] ^= 0xFF                    # the shl stride multiply
    lift2, target2 = lifter_for(bytes(bad2))
    assert lift2._is_array_addr_helper(target2) is None


def test_rejects_misdirected_guard():
    bad = bytearray(BODY_A)
    bad[8] = 0x00                       # jae no longer lands on the call
    lift, target = lifter_for(bytes(bad))
    assert lift._is_array_addr_helper(target) is None


def test_rejects_registered_targets():
    lift, target = lifter_for(BODY_A, cands={0x5000: [('method', 0)]})
    assert lift._is_array_addr_helper(target) is None


def test_lazy_name_memoizes():
    lift, target = lifter_for(BODY_A)
    lift.rt_names = {}
    assert lift._array_addr_name(target) == 'il2cpp_array_addr'
    assert lift.rt_names[target] == 'il2cpp_array_addr'
    assert lift._array_addr_name(target) == 'il2cpp_array_addr'


def test_lazy_name_declines_mutated_body():
    bad = bytearray(BODY_A)
    bad[5] ^= 0xFF
    lift, target = lifter_for(bytes(bad))
    lift.rt_names = {}
    assert lift._array_addr_name(target) is None
    assert target not in lift.rt_names


def test_lazy_name_caches_stride_not_true():
    lift, target = lifter_for(BODY_A)
    lift.rt_names = {}
    assert lift._array_addr_name(target) == 'il2cpp_array_addr'
    assert lift.__dict__.get('rt_array_addr', {}).get(target) == 0x178
    lift2, target2 = lifter_for(BODY_B)
    lift2.rt_names = {}
    assert lift2._array_addr_name(target2) == 'il2cpp_array_addr'
    assert lift2.__dict__.get('rt_array_addr', {}).get(target2) == 0x60
