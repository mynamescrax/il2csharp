"""Fix 106: the parity-jump NaN fold never emits `IsNaN(<literal>)`.

No numeric literal spelling denotes NaN, so such an arm is provably
false: `ucomiss volume, 0.0f; jp L` means `IsNaN(volume)`, not
`IsNaN(volume) || IsNaN(0f)`. The `x != x` idiom (both arms live
values) is untouched, as are unknown/nullary operands.
"""

from iced_x86 import Mnemonic

from il2cpp.x64 import _is_non_nan_literal, flag_cond


def test_non_nan_literals():
    assert _is_non_nan_literal("0f")
    assert _is_non_nan_literal("0.0f")
    assert _is_non_nan_literal("0.637499988079071f")
    assert _is_non_nan_literal("15.0f")
    assert _is_non_nan_literal("-2")
    assert _is_non_nan_literal("4294967294")
    assert _is_non_nan_literal("0x10")
    assert _is_non_nan_literal("5u")
    assert _is_non_nan_literal("1e5")
    assert _is_non_nan_literal("+3.5d")


def test_live_values_are_not_literals():
    assert not _is_non_nan_literal("real1")
    assert not _is_non_nan_literal("this.volume")
    assert not _is_non_nan_literal("((byte*)obj1 + 0x10)[0]")
    assert not _is_non_nan_literal("?")
    assert not _is_non_nan_literal("null")
    assert not _is_non_nan_literal("")
    assert not _is_non_nan_literal(None)
    assert not _is_non_nan_literal("nan")
    assert not _is_non_nan_literal("inf")
    assert not _is_non_nan_literal("e5")
    assert not _is_non_nan_literal("obj1.ToString()")


def test_jp_drops_constant_arm():
    assert flag_cond(Mnemonic.UCOMISS, Mnemonic.JP, "real1", "0f") == \
        "float.IsNaN(real1)"
    assert flag_cond(Mnemonic.UCOMISS, Mnemonic.JP, "0f", "real1") == \
        "float.IsNaN(real1)"
    assert flag_cond(Mnemonic.UCOMISS, Mnemonic.JP, "this.volume",
                      "0.637499988079071f") == "float.IsNaN(this.volume)"


def test_jnp_drops_constant_arm():
    assert flag_cond(Mnemonic.UCOMISS, Mnemonic.JNP, "real1", "0f") == \
        "!(float.IsNaN(real1))"


def test_double_width():
    assert flag_cond(Mnemonic.COMISD, Mnemonic.JP, "real1", "0.0") == \
        "double.IsNaN(real1)"


def test_live_pair_unchanged():
    # the `x != x` idiom and ordinary pairs render exactly as before
    assert flag_cond(Mnemonic.UCOMISS, Mnemonic.JP, "real1", "real1") == \
        "float.IsNaN(real1) || float.IsNaN(real1)"
    assert flag_cond(Mnemonic.UCOMISS, Mnemonic.JP, "a", "b") == \
        "float.IsNaN(a) || float.IsNaN(b)"
    assert flag_cond(Mnemonic.UCOMISS, Mnemonic.JNP, "a", "b") == \
        "!(float.IsNaN(a) || float.IsNaN(b))"


def test_all_constant_declines():
    assert flag_cond(Mnemonic.UCOMISS, Mnemonic.JP, "0f", "1f") is None
    assert flag_cond(Mnemonic.UCOMISS, Mnemonic.JNP, "0f", "1f") is None


def test_unknown_guards_unchanged():
    assert flag_cond(Mnemonic.UCOMISS, Mnemonic.JP, "?", "real1") is None
    assert flag_cond(Mnemonic.UCOMISS, Mnemonic.JP, "real1", "?") is None
    assert flag_cond(Mnemonic.UCOMISS, Mnemonic.JP, "real1", "null") is None
    assert flag_cond(Mnemonic.UCOMISS, Mnemonic.JP, None, "real1") is None
    assert flag_cond(None, Mnemonic.JP, "a", "b") is None
    assert flag_cond(Mnemonic.UCOMISS, None, "a", "b") is None
