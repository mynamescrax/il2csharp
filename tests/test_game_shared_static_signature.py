"""A closed Type argument disambiguates the folded inequality operators."""
import pytest

from test_game_goldens import game_decompiler

pytestmark = pytest.mark.game


def test_type_operator_is_named_but_timespan_layout_declines(game_decompiler):
    il, dec = game_decompiler
    method = il.meta.methods[1745]
    assert method.name == 'ExpandPredefinedFormat'
    assert hex(method.addr) == '0x181c80a70'
    text = '\n'.join(dec.lift_method(method, il.meta.typedefs[method.declaring]))
    assert text.count('System.Type.op_Inequality(') == 2
    assert text.count('sub_18061a510/*shared body, 17 candidates*/') == 2
