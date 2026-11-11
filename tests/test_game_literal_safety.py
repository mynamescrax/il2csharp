"""Promoted-tree ground truth: literals survive the text passes.

Both fixes come from the dec audit 2026-09-28; the sites are the exact
ones the audit demonstrated on the fixture.
"""
import pytest

from test_game_goldens import game_decompiler

pytestmark = pytest.mark.game


def body(game_decompiler, mi):
    il, dec = game_decompiler
    method = il.meta.methods[mi]
    return "\n".join(dec.lift_method(method, il.meta.typedefs[method.declaring]))


def test_json_wire_name_keeps_its_dollar(game_decompiler):
    # BSON `$id`: `_render`'s blanket `$` -> `_` corrupted the literal
    # (`"_id"`); only declaration text kept the dollar.
    text = body(game_decompiler, 80053)
    assert 'JsonToken.PropertyName, "$id"' in text
    assert 'JsonToken.PropertyName, "_id"' not in text


def test_diffgram_namespace_keeps_its_v1(game_decompiler):
    # `_rename_locals` substituted vN tokens inside the literal:
    # `urn:schemas-microsoft-com:xml-diffgram-v1` rendered `...-obj24`.
    text = body(game_decompiler, 85538)
    assert 'urn:schemas-microsoft-com:xml-diffgram-v1' in text
    assert 'diffgram-obj' not in text
