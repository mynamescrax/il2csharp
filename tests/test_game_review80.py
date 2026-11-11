"""Native-backed assertions for Review 80's loop-header correction."""
import pytest

from test_game_goldens import game_decompiler

pytestmark = pytest.mark.game


def body(game_decompiler, mi):
    il, dec = game_decompiler
    method = il.meta.methods[mi]
    return "\n".join(dec.lift_method(method, il.meta.typedefs[method.declaring]))


def test_direction_dispatch_is_not_dropped_from_draw_curved_loop(game_decompiler):
    text = body(game_decompiler, 23566)
    start = text.index("while (true)")
    end = text.index("if (this.pathPoint._size >= 2)", start)  # fix 125/126 re-pin
    loop = text[start:end]

    for direction in ("Forward", "Backward", "HugLeft", "HugRight",
                      "WeaveLeft", "WeaveRight"):
        assert f'"{direction}"' in loop
    assert "this._forward[num2] = true;" in loop
    assert "this._forward[num2] = false;" in loop
    assert "goto " not in loop


def test_receive_loop_shared_entry_is_a_legal_short_circuit_gate(game_decompiler):
    text = body(game_decompiler, 28576)
    # fix 86: both operands now name their member. The old expectation
    # (`!= 1` and `!= PhotonSocketState.Connecting`) recorded the broken
    # enum_members decode: PhotonSocketState is Connecting=1, Connected=2,
    # so literal 1 had no key in the zigzag-doubled table and stayed bare,
    # while literal 2 matched Connecting's doubled key and printed the
    # WRONG member. What this test guards -- a legal && short-circuit gate
    # ahead of Monitor.Enter, with no gotos -- is unchanged.
    gate = (
        "if ((this.__field_State != PhotonSocketState.Connecting) && "
        "(this.__field_State != PhotonSocketState.Connected))"
    )

    assert gate in text
    assert text.index(gate) < text.index("System.Threading.Monitor.Enter")
    assert "goto " not in text


def test_touchscreen_condition_is_recomputed_in_the_loop(game_decompiler):
    text = body(game_decompiler, 32833)
    marker = "num8 = unknown + this.currentStatePtr;"  # fix 125/126: num7 -> num8
    tail = text[text.index(marker):]

    assert "bool flag" not in tail.split("while (true)", 1)[0]
    assert "if (num8.isNoneEndedOrCanceled)" in tail.split("while (true)", 1)[1]


def test_viscosity_job_keeps_pair_loads_inside_iteration(game_decompiler):
    text = body(game_decompiler, 80548)

    assert "num4 = (num1 << 5) + this.pairs;" in text
    assert "num4 = (num1 << 5) + unknown;" not in text
    assert text.index("while (true)") < text.index(
        "((byte*)num4 + 0x18)"
    )
