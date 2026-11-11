"""Bounds-checked element-address helpers render named with two args.

Ground truth: TMP_Text.CalculatePreferredValues (mi 96360) addresses
TMP_CharacterInfo elements through 0x1803ed830; today that sprays two
stale residues after (array, index). Naming routes through
`il2cpp_array_addr` with arity 2.
"""
import pytest

from test_game_goldens import game_decompiler

pytestmark = pytest.mark.game


def test_character_info_sites_render_named(game_decompiler):
    il, dec = game_decompiler
    m = il.meta.methods[96360]
    assert m.name == 'CalculatePreferredValues'
    text = '\n'.join(dec.lift_method(m, il.meta.typedefs[m.declaring]))
    assert 'sub_1803ed830' not in text
    assert 'il2cpp_array_addr(tmpCharacterInfoArray25, this.m_characterCount + 1)' in text


def test_generate_text_mesh_renders_named(game_decompiler):
    il, dec = game_decompiler
    m = il.meta.methods[96741]
    assert m.name == 'GenerateTextMesh'
    text = '\n'.join(dec.lift_method(m, il.meta.typedefs[m.declaring]))
    assert 'sub_1803ed830' not in text
    assert 'il2cpp_array_addr(tmpCharacterInfoArray1, this.m_characterCount)' in text
