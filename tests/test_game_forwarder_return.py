"""Noreturn-shared forwarder returns on real Neon bodies.

Ground truth: each vmvn/vand/vorn family shares one 3-insn body
(`sub rsp,28h; xor r32,r32; call s8-variant; int3`) whose single
proven target throws NotImplementedException on x64, so the tail
`return Target(args);` is the exact reachable behavior.
"""
import pytest

from test_game_goldens import game_decompiler  # noqa: F401 (fixture)

pytestmark = pytest.mark.game


def _lift_text(game_decompiler, mi, name, va):
    il, dec = game_decompiler
    m = il.meta.methods[mi]
    assert m.name == name
    assert hex(m.addr) == va
    return dec.lift_method(m, il.meta.typedefs[m.declaring])


def test_game_vmvn_s16(game_decompiler):
    assert _lift_text(game_decompiler, 107037, "vmvn_s16", "0x182518120") == \
        ["return Neon.vmvn_s8(a0);"]


def test_game_vand_s16(game_decompiler):
    assert _lift_text(game_decompiler, 107049, "vand_s16", "0x182509a60") == \
        ["return Neon.vand_s8(a0, a1);"]
