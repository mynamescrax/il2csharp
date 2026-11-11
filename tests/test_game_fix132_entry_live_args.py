"""Fix 132: a plain `sub_` call passes the registers its callee reads.

Ground truth (disasm, FIMSpace.FEngineering.GetAngleDeg(Vector3)
0x18061F9C0): `movss xmm1,[rcx+8]; movss xmm0,[rcx]; call 0x1804D05A8;
mulss xmm0,[c]; ret`. 0x1804D05A8 (atan2f, no metadata owner) reads
XMM0/XMM1 before writing them and never reads RCX/RDX/R8/R9, so the call
is `sub_1804d05a8(v.x, v.z)`; the following `mulss xmm0` reads the
float result in XMM0. The spray rendered
`object obj1 = sub_1804d05a8(v, obj2, obj3, obj4); return obj5 * ...`
(four undeclared names, real arguments dropped).
"""
import pytest

from test_game_goldens import game_decompiler

pytestmark = pytest.mark.game


def _lift(il, dec, mi, name):
    m = il.meta.methods[mi]
    assert m.name == name
    return '\n'.join(dec.lift_method(m, il.meta.typedefs[m.declaring]))


def test_float_helper_gets_its_xmm_arguments_and_result(game_decompiler):
    il, dec = game_decompiler
    text = _lift(il, dec, 28756, 'GetAngleDeg')
    assert 'float real1 = (float)sub_1804d05a8(v.x, v.z);' in text
    assert 'return real1 * 57.29578f;' in text
    assert 'obj' not in text


def test_stack_home_lanes_are_the_arguments(game_decompiler):
    # GetAngleDeg(Vector2) 0x18061F9E0 spills RCX and reloads both lanes
    il, dec = game_decompiler
    text = _lift(il, dec, 28757, 'GetAngleDeg')
    assert '(float)sub_1804d05a8(v.x, v.y)' in text


def test_entry_live_proof_on_the_fixture(game_decompiler):
    from il2cpp.entrylive import entry_live_args
    il, _ = game_decompiler
    assert entry_live_args(il, 0x1804d05a8) == ('x', 'x', '', '')   # atan2f
    assert entry_live_args(il, 0x1804cdfe0) == ('x', '', '', '')    # 1-arg libm
