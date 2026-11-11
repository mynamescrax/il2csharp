"""Interface-zero game pins (mi 5694 AppendFormatHelper)."""
import pytest

from test_game_goldens import game_decompiler

pytestmark = pytest.mark.game


def test_custom_formatter_zero_is_null(game_decompiler):
    il, dec = game_decompiler
    m = il.meta.methods[5694]
    assert m.name == "AppendFormatHelper"
    text = "\n".join(dec.lift_method(m, il.meta.typedefs[m.declaring]))
    assert "if (customFormatter12 == null)" in text
    assert "customFormatter12 == 0" not in text
    assert "customFormatter12 != 0" not in text


def test_object_zero_keeps_zero(game_decompiler):
    il, dec = game_decompiler
    m = il.meta.methods[5694]
    assert m.name == "AppendFormatHelper"
    text = "\n".join(dec.lift_method(m, il.meta.typedefs[m.declaring]))
    assert "if (obj90 == 0)" in text  # fix 125/126 renumber (was obj83)
    assert "if (readOnlySpan11 == 0)" in text
