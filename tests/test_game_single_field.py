"""Single-field assign fold (F2-C1) ground truth pins."""
import pytest

from test_game_goldens import game_decompiler

pytestmark = pytest.mark.game


def test_timespan_assign_folds_to_whole(game_decompiler):
    il, dec = game_decompiler
    m = il.meta.methods[1741]
    assert "FormatCustomized" in m.name
    text = "\n".join(dec.lift_method(m, il.meta.typedefs[m.declaring]))
    assert "System.TimeSpan timeSpan2;" in text  # fix 125/126: hoisted declaration
    assert "timeSpan2 = offset;" in text
    assert "timeSpan2 = offset._ticks" not in text


def test_timespan_assign_folds_roundrip(game_decompiler):
    il, dec = game_decompiler
    m = il.meta.methods[1742]
    assert "FormatCustomized" in m.name
    text = "\n".join(dec.lift_method(m, il.meta.typedefs[m.declaring]))
    assert "System.TimeSpan timeSpan2 = offset;" in text


def test_ulong_lane_keeps_lane(game_decompiler):
    il, dec = game_decompiler
    m = il.meta.methods[97284]
    assert m.name == "Initialize"
    text = "\n".join(dec.lift_method(m, il.meta.typedefs[m.declaring]))
    assert "ulong num1 = fusionStatBuffer1._lastBufferInsertTime._dateData;" in text
