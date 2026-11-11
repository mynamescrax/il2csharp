"""Parameterized interface dispatch renders the managed call.

Ground truth: GraphUpdateProcessor.ProcessRegularUpdates (mi 104498)
calls CanUpdateAsync (slot 3) through 0x180006590 with (slot, iface,
receiver, R9 arg). The R9 value is live on entry and typed, so the
site renders the one-argument managed call. Typed-unknown R9
(mi 104027, merged `default`-poisoned but exactly typed) and
multi-parameter targets with stack-home args (mi 6160) resolve too;
the writes-first impostor keeps the honest marker.
"""
import pytest

from test_game_goldens import game_decompiler

pytestmark = pytest.mark.game


def test_can_update_async_resolves(game_decompiler):
    il, dec = game_decompiler
    m = il.meta.methods[104498]
    assert m.name == 'ProcessRegularUpdates'
    text = '\n'.join(dec.lift_method(m, il.meta.typedefs[m.declaring]))
    assert 'guoSingle1.graph.CanUpdateAsync(guoSingle1.obj)' in text


def test_typed_unknown_r9_resolves(game_decompiler):
    il, dec = game_decompiler
    m = il.meta.methods[104027]
    assert m.name == 'OnEnable'
    text = '\n'.join(dec.lift_method(m, il.meta.typedefs[m.declaring]))
    assert 'sub_180006020' not in text
    assert 'this.ai.onSearchPath = action1;' in text


def test_multi_param_target_resolves(game_decompiler):
    il, dec = game_decompiler
    m = il.meta.methods[6160]
    assert m.name == 'FlushFinalBlock'
    text = '\n'.join(dec.lift_method(m, il.meta.typedefs[m.declaring]))
    assert 'sub_180003a40' not in text
    assert 'object obj3 = this._inputBufferIndex;' in text
    assert 'this._transform.TransformFinalBlock(this._inputBuffer, 0, obj3)' in text


def test_resolved_string_result_null_tests_null(game_decompiler):
    il, dec = game_decompiler
    m = il.meta.methods[5694]
    assert m.name == 'AppendFormatHelper'
    text = '\n'.join(dec.lift_method(m, il.meta.typedefs[m.declaring]))
    assert 'sub_180328e30' not in text
    assert 'customFormatter12.Format(obj163, obj80, provider)' in text  # fix 125/126 renumber
    assert 'text5 != null' in text


def test_writes_first_impostor_scores_zero(game_decompiler):
    il, dec = game_decompiler
    lif = dec.L if hasattr(dec, 'L') else None
    assert lif is not None
    assert lif._iface_dispatch_arity(0x180540f50) == 0
    assert lif._iface_dispatch_arity(0x180006020) == 1
    assert lif._iface_dispatch_arity(0x180002210) == 0
