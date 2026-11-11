"""Payload-builder typing for InventoryManager.Rpc_CMD_UpdateInventoryForHost.

Ground truth (mi 25626, VA 0x180704750): three int[] params kept in
callee-saved registers (ids in RBP), a `SimulationMessage.Allocate` +
0x1c payload cursor, aligned CopyFromArray offset chains, and
`[offset + cursor]` stores. Every assertion names a present-tense
defect the old output had (unbound obj1, object arithmetic, twin
temps); see the fix notes in il2cpp/lifter/{state,insn,values}.py.
"""
import pytest

from test_game_goldens import game_decompiler

pytestmark = pytest.mark.game

MI = 25626


def body(game_decompiler):
    il, dec = game_decompiler
    m = il.meta.methods[MI]
    assert m.name == 'Rpc_CMD_UpdateInventoryForHost'
    assert hex(m.addr) == '0x180704750'
    return '\n'.join(dec.lift_method(m, il.meta.typedefs[m.declaring]))


def test_lengths_are_named_not_raw_or_unbound(game_decompiler):
    text = body(game_decompiler)
    assert 'obj1' not in text
    assert 'trash_.Length' in text
    assert 'inventoryIds_.Length' in text
    assert 'inventoryAmounts_.Length' in text
    assert '+ 0x18)[0]' not in text


def test_payload_cursor_is_a_typed_pointer(game_decompiler):
    text = body(game_decompiler)
    assert 'byte* bytePtr1 = (byte*)simulationMessagePtr1 + 0x1c;' in text
    assert 'object obj' not in text


def test_stores_use_typed_widths_and_pointer_first_order(game_decompiler):
    text = body(game_decompiler)
    assert '((int*)((byte*)bytePtr1 + 0x8))[0] = inventoryIds_.Length;' in text
    assert '((int*)((byte*)bytePtr1 + num3*1 + 0x0))[0] = inventoryAmounts_.Length;' in text
    assert '((int*)((byte*)bytePtr1 + num5*1 + 0x0))[0] = trash_.Length;' in text
    assert '*1 + 0x0' not in text.replace('num3*1', '').replace('num5*1', '')
    assert 'bytePtr1*' not in text


def test_offset_chain_has_one_typed_temp_per_extent(game_decompiler):
    text = body(game_decompiler)
    assert text.count('int num5 = num4 + (Fusion.Native.CopyFromArray<int>(') == 1
    assert text.count('num4 + bytePtr1, inventoryAmounts_)') == 1
    assert 'simulationMessagePtr1->Offset' in text
    assert 'this._runner.SendRpc(simulationMessagePtr1);' in text
