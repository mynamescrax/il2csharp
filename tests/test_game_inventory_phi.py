"""Native RCX/RDX join in InventoryManager.UpdateInventorySlotsUI."""

import pytest

from test_game_goldens import game_decompiler


pytestmark = pytest.mark.game


def test_sprite_receiver_and_value_are_defined_on_both_arms(game_decompiler):
    il, dec = game_decompiler
    m = il.meta.methods[25624]
    assert m.name == 'UpdateInventorySlotsUI'
    assert m.addr == 0x18070B620
    body = '\n'.join(dec.lift_method(m, il.meta.typedefs[m.declaring]))
    assert 'UnityEngine.UI.Image obj22;' in body
    assert 'UnityEngine.Sprite obj23;' in body
    assert 'obj22 = image2;' in body
    assert 'obj22 = image4;' in body
    assert 'obj22.sprite = obj23;' in body
    assert 'image3.sprite = obj21;' not in body
