"""The IsInst helper renders `obj as T` for typeof(T) call sites.

Ground truth: MicAudioCanvas.Awake (mi 26309) combines a delegate and
casts it back with the helper; the `typeof(Action_1<VoiceConnection>)`
klass argument proves the cast target.
"""
import pytest

from test_game_goldens import game_decompiler

pytestmark = pytest.mark.game


def test_mic_audio_canvas_awake_casts_the_delegate(game_decompiler):
    il, dec = game_decompiler
    m = il.meta.methods[26309]
    assert m.name == 'Awake'
    text = '\n'.join(dec.lift_method(m, il.meta.typedefs[m.declaring]))
    assert ' as System.Action_1<Photon.Voice.Unity.VoiceConnection>' in text
    assert 'sub_180434690' not in text
