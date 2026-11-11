"""B1 inline-typeof dispatch pinned on EndlessGenerationManager 25132."""
import pytest

from test_game_goldens import game_decompiler


pytestmark = pytest.mark.game


def test_scan_loop_typeof_dispatch(game_decompiler):
    il, dec = game_decompiler
    m = il.meta.methods[25132]
    assert m.name == '<GenerateNight>g__ContainsAny|4_0'
    body = '\n'.join(dec.lift_method(m, il.meta.typedefs[m.declaring]))
    assert 'values.GetEnumerator();' in body
    assert '/*indirect*/' not in body
