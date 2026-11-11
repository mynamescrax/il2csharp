"""Struct sizes must never be negative.

`type_sizes` is the binary's only exact struct-size table, and the Win64
return-buffer rule needs it. The loader subtracts the 0x10 object header, so
an `instance_size` below 0x10 must read as "unknown" (None) -- the comment
above the loop says exactly that. The guard used to test only for zero, so
every 0 < instance_size < 0x10 became a negative size (91 rows in the
fixture, values -15 and -8, all `<Module>` definitions). Nothing consumed
those today, but a negative size is precisely the value that would flip a
hidden-sret decision and shift every argument register.
"""
import pytest

from test_game_goldens import game_decompiler

pytestmark = pytest.mark.game


def test_type_sizes_are_never_negative(game_decompiler):
    il, _dec = game_decompiler
    sizes = il.type_sizes
    assert sizes, "no type_sizes decoded"
    negative = [(i, v) for i, v in enumerate(sizes) if v is not None and v < 0]
    assert not negative, "negative struct sizes: %r" % (negative[:5],)


def test_type_sizes_still_decode_real_value_types(game_decompiler):
    il, _dec = game_decompiler
    known = [v for v in il.type_sizes if v is not None]
    assert len(known) > 1000
    assert max(known) > 64, "largest decoded struct collapsed"


def test_open_generic_definitions_stay_none(game_decompiler):
    """The reason the negative case matters: an open generic DEFINITION
    carries instance_size 0 and must stay unknown, not become -16."""
    il, _dec = game_decompiler
    assert None in il.type_sizes
    assert -16 not in il.type_sizes
