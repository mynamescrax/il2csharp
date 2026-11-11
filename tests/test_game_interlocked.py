"""The Interlocked.CompareExchange helper renders as the managed call.

Ground truth: FusionNetworkManager.add_OnVoiceConnectionReady (mi 26409)
uses the helper for its event field; the render must carry the `ref`
location and both values, and must not leave `sub_18043f880`.
"""
import pytest

from test_game_goldens import game_decompiler

pytestmark = pytest.mark.game


def test_event_add_renders_interlocked_compare_exchange(game_decompiler):
    il, dec = game_decompiler
    m = il.meta.methods[26409]
    assert m.name == 'add_OnVoiceConnectionReady'
    text = '\n'.join(dec.lift_method(m, il.meta.typedefs[m.declaring]))
    assert ('System.Threading.Interlocked.CompareExchange(ref '
            'FusionNetworkManager.__field_OnVoiceConnectionReady') in text
    assert 'sub_18043f880' not in text
