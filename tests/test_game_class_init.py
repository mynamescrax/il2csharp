"""The out-of-line class-init helper is recognized and elided.

Ground truth: PlayerLobbyHandler.Render (mi 26673) calls the helper before
its NetworkString comparison cluster; naming the target routes it through
the existing class-init bookkeeping, which drops the call and propagates
the klass value.
"""
import pytest

from test_game_goldens import game_decompiler

pytestmark = pytest.mark.game


def test_player_lobby_handler_render_elides_the_class_init_helper(game_decompiler):
    il, dec = game_decompiler
    m = il.meta.methods[26673]
    assert m.name == 'Render'
    text = '\n'.join(dec.lift_method(m, il.meta.typedefs[m.declaring]))
    assert 'sub_18043e360' not in text
    assert 'il2cpp_runtime_class_init' not in text
    assert 'NetworkString_1<Fusion._64>.op_Inequality' in text
