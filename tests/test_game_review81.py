"""Native-backed assertions for proved packed-sqrt/helper ABI recovery."""
import pytest

from test_game_goldens import game_decompiler

pytestmark = pytest.mark.game


def body(game_decompiler, mi):
    il, dec = game_decompiler
    method = il.meta.methods[mi]
    return "\n".join(dec.lift_method(method, il.meta.typedefs[method.declaring]))


def test_sqrt_helper_is_discovered_from_native_structure(game_decompiler):
    il, dec = game_decompiler
    target = dec.L.rt_sqrt
    assert target is not None
    assert target not in il.addr_candidates
    assert target not in il.bin.exports
    assert dec.L._is_scalar_sqrt_helper(target)


def test_vector_normalize_recovers_low_lane_root(game_decompiler):
    text = body(game_decompiler, 55599)
    assert "(float)(Math.Sqrt(" in text
    assert "sub_1804ce6d8" not in text
    assert "if (0f >" not in text


def test_direct_helper_float_return_uses_xmm0(game_decompiler):
    text = body(game_decompiler, 25183)
    assert text.count("return (float)(Math.Sqrt(") == 2
    assert "sub_1804ce6d8" not in text
    assert "return obj" not in text


def test_packed_float_intrinsic_recovers_every_lane_independently(game_decompiler):
    text = body(game_decompiler, 109194)
    # fix 102: the float-lane stores render width-preserving (`movss`
    # ground truth) instead of the old byte spelling; the `0f` zeroing
    # store keeps its byte form.
    for offset in ("0x0", "0x4", "0x8", "0xc"):
        assert f"((float*)((byte*)&__ret + {offset}))[0]" in text  # fix 125/126: return buffer is &__ret
    assert "((byte*)&__ret + 0x0)[0] = 0f;" in text
    assert text.count("Math.Sqrt(") == 4
    assert "sub_1804ce6d8" not in text
    assert "unknown" not in text


def test_float_return_abi_prefers_xmm0_over_live_rax(game_decompiler):
    text = body(game_decompiler, 61024)
    assert "return real4 * real2 + this._mean;" in text
    assert "return num2;" not in text


def test_direct_helper_tail_return_uses_xmm0(game_decompiler):
    text = body(game_decompiler, 2181)
    assert text.count("return Math.Sqrt(d);") == 2
    assert "sub_1804ce6d8" not in text
