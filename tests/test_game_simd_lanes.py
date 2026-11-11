"""SIMD consumer-side recovery pins (tails + direct calls + guard).

Ground truth: 67525 saturate builds float2 splats natively (tail);
67836 smoothstep passes them to direct clamp calls; 80548 carries
integers through the same movq shape and must stay unknown.
"""
import pytest

from test_game_goldens import game_decompiler

pytestmark = pytest.mark.game


def lift_text(game_decompiler, mi, name, va):
    il, dec = game_decompiler
    m = il.meta.methods[mi]
    assert m.name == name
    assert hex(m.addr) == va
    return '\n'.join(dec.lift_method(m, il.meta.typedefs[m.declaring]))


def test_tail_splat_renders_composites(game_decompiler):
    text = lift_text(game_decompiler, 67525, 'saturate', '0x1826f83f0')
    assert 'clamp(x, (float2)(0.0f, 0.0f), (float2)(1.0f, 1.0f))' in text
    assert 'unknown' not in text


def test_direct_splat_renders_composites(game_decompiler):
    text = lift_text(game_decompiler, 67836, 'smoothstep', '0x1826fd540')
    assert 'math.clamp(unknown, (float2)(0.0f, 0f), (float2)(1.0f, 1.0f));' in text
    assert 'math.clamp(unknown, (float2)(0.0f, 0f), (float2)(1.0f, 1.0f)).x;' in text


def test_integer_carry_stays_unknown(game_decompiler):
    text = lift_text(game_decompiler, 80548, 'Execute', '0x181eab2f0')
    assert '(unknown >> 32)' in text
    assert '(float2)(' not in text
