"""Unanimous conversion families resolve at caller-proven casts.

Ground truth: the Angle/StyleFloat/TimeValue op_Implicit triple shares
0x182da54f0 (one XMM lane in, 8-byte struct out). Typed uses isolate
one candidate each: Rotate..ctor (mi 20080) stores into an Angle field,
ResolveLengthValue (mi 19412) returns StyleFloat. Untyped `object`
sites (e.g. mi 13332) keep the honest marker.
"""
import pytest

from test_game_goldens import game_decompiler

pytestmark = pytest.mark.game


def test_rotate_ctor_resolves_angle_conversion(game_decompiler):
    il, dec = game_decompiler
    m = il.meta.methods[20080]
    assert m.name == '.ctor'
    text = '\n'.join(dec.lift_method(m, il.meta.typedefs[m.declaring]))
    assert 'sub_182da54f0' not in text
    assert 'Angle.op_Implicit' in text


def test_resolve_length_value_resolves_stylefloat(game_decompiler):
    il, dec = game_decompiler
    m = il.meta.methods[19412]
    assert m.name == 'ResolveLengthValue'
    text = '\n'.join(dec.lift_method(m, il.meta.typedefs[m.declaring]))
    assert 'sub_182da54f0' not in text
    assert 'StyleFloat.op_Implicit' in text


def test_untyped_sites_keep_the_marker(game_decompiler):
    il, dec = game_decompiler
    m = il.meta.methods[13332]
    text = '\n'.join(dec.lift_method(m, il.meta.typedefs[m.declaring]))
    assert 'sub_182da54f0' in text
