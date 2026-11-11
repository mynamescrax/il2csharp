"""Native-backed assertions for the newly resolved ABI/alias families."""
import re

import pytest

from test_game_goldens import game_decompiler
from test_game_review78 import body

pytestmark = pytest.mark.game


def test_shoot_uses_one_array_per_native_logging_allocation(game_decompiler):
    text = body(game_decompiler, 25687)
    arrays = re.findall(r"string\[\] (textArray\d+) = new string\[(11|7)\];", text)
    assert sorted(length for _, length in arrays) == ["11", "7"]
    for variable, length in arrays:
        stores = re.findall(r"\b" + variable + r"\[(0x[0-9a-f]+|\d+)\] = ", text)
        assert sorted(int(i, 0) for i in stores) == list(range(int(length)))
        assert f"string.Concat({variable})" in text
    assert "(new string[" not in text
    assert "byte*)new string[" not in text


def test_shoot_sret_point_reads_are_not_untyped_pointer_dereferences(game_decompiler):
    text = body(game_decompiler, 25687)
    assert "sub_180895b20" not in text
    # fix 97: declared (and semantically named) member reads; the bare
    # `objN = objM.point` spelling is gone but the proof is unchanged.
    assert len(re.findall(r"\w+ = \w+\.point;", text)) == 2
    assert re.search(r"\w+ = \w+\.z;", text)


def test_string_byte_buffer_is_allocated_once_before_encoding(game_decompiler):
    text = body(game_decompiler, 98685)
    match = re.search(r"byte\[\] (byteArray\d+) = new byte\[1025\];", text)
    assert match and text.count("new byte[1025]") == 1
    assert text.index("new byte[1025]") < text.index("Encoding.UTF8")
    assert re.search(r"\b" + match.group(1) + r"\[num\d+\] = 0;", text)


def test_string_encoding_keeps_the_native_stack_buffer_arguments(game_decompiler):
    text = body(game_decompiler, 98685)
    m = re.search(
        r"byte\[\] (byteArray\d+) = new byte\[1025\];.*?Encoding\.UTF8;.*?GetBytes\(value, 0, \(\(byte\*\)value \+ 0x10\)\[0\], (byteArray\d+), 0\);",
        text,
        re.S,
    )
    assert m and m.group(1) == m.group(2)


def test_quaternion_scalar_sqrt_preserves_float_result_width(game_decompiler):
    text = body(game_decompiler, 55666)
    assert "(float)Math.Sqrt(" in text
    assert not re.search(r"=\s*Math\.Sqrt\(", text)