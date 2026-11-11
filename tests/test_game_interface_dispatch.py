"""Interface-offset dispatch naming (mi 25368 CheckAllReady).

Ground truth: three back-to-back interfaceOffsets searches for
IEnumerable<PlayerRef>/IEnumerator/IEnumerator<PlayerRef> resolve to
GetEnumerator/MoveNext/get_Current. They missed on three crisp gates
(slot decl prefix, typeof-ref span ending at the slot, _N arity key);
all three now resolve with every decline preserved.
"""
import pytest

from test_game_goldens import game_decompiler

pytestmark = pytest.mark.game


def test_check_all_ready_names_all_dispatches(game_decompiler):
    il, dec = game_decompiler
    m = il.meta.methods[25368]
    assert m.name == 'CheckAllReady'
    assert hex(m.addr) == '0x1806df770'
    text = '\n'.join(dec.lift_method(m, il.meta.typedefs[m.declaring]))
    # fix 125/126 re-pin: temps renumbered (obj25 -> obj24, obj32 -> obj33).
    assert 'object obj24 = enumerable12.GetEnumerator();' in text
    assert 'bool obj33 = obj5.MoveNext();' in text
    assert 'Fusion.PlayerRef playerRef1 = obj5.Current;' in text
    assert '/*indirect*/' not in text


def test_boxed_bool_folds_and_unbox_declines(game_decompiler):
    il, dec = game_decompiler
    m = il.meta.methods[25368]
    text = '\n'.join(dec.lift_method(m, il.meta.typedefs[m.declaring]))
    assert 'if (!obj33)' in text
    m2 = il.meta.methods[25872]
    assert m2.name == 'Update'
    assert hex(m2.addr) == '0x180547380'
    text2 = '\n'.join(dec.lift_method(m2, il.meta.typedefs[m2.declaring]))
    assert 'bool obj33 = enumerator3.MoveNext();' in text2
    assert 'object obj48 = enumerator7.MoveNext();' in text2


def test_structural_nullary_family_binds_once(game_decompiler):
    """The fixture's different-prologue dispatchers (0x180002210 and
    0x180002380) resolve structurally instead of by byte template: the
    enumerator call must render exactly once, the loop must reuse the
    bound temp rather than re-render the call on replay, and the
    IDisposable sites become real `Dispose` calls."""
    il, dec = game_decompiler
    m = il.meta.methods[26761]
    assert m.name == 'Rpc_CMD_Downed'
    assert hex(m.addr) == '0x18057b080'
    text = '\n'.join(dec.lift_method(m, il.meta.typedefs[m.declaring]))
    assert 'sub_180002210' not in text
    assert 'sub_180002380' not in text
    assert text.count('.GetEnumerator()') == 1
    assert text.count('.MoveNext()') == 1
    assert '.Current' in text
    assert '.Dispose();' in text


def test_idisposable_calls_fold_to_null_conditional(game_decompiler):
    il, dec = game_decompiler
    m = il.meta.methods[27447]
    assert m.name == 'EncryptJsonToBase64'
    text = '\n'.join(dec.lift_method(m, il.meta.typedefs[m.declaring]))
    assert '?.Dispose();' in text
    assert 'sub_180002380' not in text
