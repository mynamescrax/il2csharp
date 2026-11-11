"""Native-grounded assertions for Review 78; not cosmetic snapshot updates."""
import re

import pytest

from test_game_goldens import game_decompiler

pytestmark = pytest.mark.game


def body(game_decompiler, mi):
    il, dec = game_decompiler
    m = il.meta.methods[mi]
    return '\n'.join(dec.lift_method(m, il.meta.typedefs[m.declaring]))


def test_coalesced_click_flags_both_survive(game_decompiler):
    assert body(game_decompiler, 25620).splitlines() == [
        'this.letGoOfInteract = true;', 'this.letGoOfClick = true;', 'return;']


def test_reload_smg_recovers_array_capacity_operand(game_decompiler):
    text = body(game_decompiler, 25758)
    assert '30 - unknown' not in text
    assert re.search(r'30 - intArray\d+\[', text)
    assert not re.search(r'\bint num\d+ = .*\.itemStorages;', text)
    assert re.search(r'int\[\] intArray\d+ = .*\.itemStorages;', text)


def test_shared_layer_mask_conversion_uses_argument_identity(game_decompiler):
    text = body(game_decompiler, 25687)
    assert 'UnityEngine.LayerMask.op_Implicit(this.shootable)' in text
    assert 'sub_180894a90' not in text
    # Review 79 supplies the separate RDX receiver / RCX buffer proof.
    assert 'sub_180895b20/*shared body, 9 candidates*/' not in text
    # fix 97: the point reads now carry declarations (and semantic names),
    # so the bare-temp spelling is gone; the proof is the member read
    # itself, with no shared marker or pointer deref above.
    assert re.search(r'\w+ = \w+\.point;', text)


def test_read_span_replays_header_difference_and_refill_on_every_iteration(game_decompiler):
    text = body(game_decompiler, 11974)
    before_loop = text.split('while (true)', 1)[0]
    assert 'this._charLen - this._charPos' not in before_loop
    loop = text.split('while (true)', 1)[1]
    assert 'this._charLen - this._charPos' in loop
    assert 'this._charLen - unknown' not in text
    assert '.ReadBuffer(' in loop
    assert loop.index('this._charLen - this._charPos') < loop.index('.ReadBuffer(')
