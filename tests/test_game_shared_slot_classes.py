"""The all-candidates slot-class proof recovers dropped XMM arguments.

`_call` used to bound an unresolved shared body's argument list by
truncating the raw GPR-first register spray to the largest declared arity
among candidates. When every candidate declares a float parameter, that
printed the stale RCX value and dropped the real XMM argument.
`_shared_slot_classes` proves the lane for every slot; the sites below are
the ground truth from that proof.
"""
import pytest

from test_game_goldens import game_decompiler

pytestmark = pytest.mark.game


def body(game_decompiler, mi):
    il, dec = game_decompiler
    method = il.meta.methods[mi]
    return "\n".join(dec.lift_method(method, il.meta.typedefs[method.declaring]))


def test_shared_float_leaf_recovers_the_xmm_argument(game_decompiler):
    # 0x182da54f0: Angle/StyleFloat/TimeValue.op_Implicit(float), shared
    # by three one-float-parameter static methods. The old trim printed
    # the stale sret buffer `(obj1)` and dropped XMM0's `0f`.
    text = body(game_decompiler, 20081)
    call = 'sub_182da54f0/*shared body, 3 candidates*/'
    assert f'{call}(0f)' in text
    assert f'{call}(obj1)' not in text


def test_shared_float_leaf_recovers_a_computed_argument(game_decompiler):
    # mi 20080 Rotate(Quaternion): the recovered value is the degree
    # conversion `real2`; before, the multiply was dropped and an
    # undeclared GPR temp `obj5` was printed as the argument. Landing 6
    # (unanimous conversions at proven casts) since resolves the
    # Angle/StyleFloat/TimeValue triple to `Angle.op_Implicit`, so the
    # shared marker is gone by design -- the recovered computation
    # remains its argument.
    text = body(game_decompiler, 20080)
    assert 'UnityEngine.UIElements.Angle.op_Implicit(real2)' in text
    assert 'float real2 = real1 * 57.29578f;' in text


def test_square_leaf_recovers_its_float_argument(game_decompiler):
    # 0x1826e1660 is `mulss xmm0,xmm0` (float square) shared by three
    # static float->float helpers; the stale GPR temp is gone.
    text = body(game_decompiler, 65682)
    call = 'sub_1826e1660/*shared body, 3 candidates*/'
    assert f'{call}(radius)' in text
    assert f'{call}(obj' not in text


def test_gpr_only_shared_call_keeps_its_arguments(game_decompiler):
    # 0x182bac5e0 has class 'gg': the slot-class rebuild must not disturb
    # a shared body whose slots were already printed in GPR order.
    text = body(game_decompiler, 109695)
    assert 'ID_GradientScale, real1);' in text
