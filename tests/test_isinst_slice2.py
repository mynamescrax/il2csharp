"""IsInst slice-2 fence pins (text-exact typeof), no fixture needed."""
from il2cpp import Lifter


def test_bare_typeof_simple():
    assert Lifter._bare_typeof_target("typeof(System.String)") == "System.String"


def test_bare_typeof_nested_generics():
    assert Lifter._bare_typeof_target(
        "typeof(System.Collections.Generic.Dictionary<string,System.Collections.Generic.List<int>>)"
    ) == "System.Collections.Generic.Dictionary<string,System.Collections.Generic.List<int>>"


def test_bare_typeof_space_paren():
    assert Lifter._bare_typeof_target("typeof (System.String)") == "System.String"


def test_bare_typeof_declines_member():
    assert Lifter._bare_typeof_target("typeof(System.String).GetMethod") is None


def test_bare_typeof_declines_call():
    assert Lifter._bare_typeof_target("typeof(System.String).GetType()") is None


def test_bare_typeof_declines_unbalanced():
    assert Lifter._bare_typeof_target("typeof(System.String") is None
    assert Lifter._bare_typeof_target("typeof(System.String))") is None


def test_bare_typeof_declines_empty():
    assert Lifter._bare_typeof_target("typeof()") is None
    assert Lifter._bare_typeof_target("typeof(  )") is None


def test_bare_typeof_declines_non_typeof():
    assert Lifter._bare_typeof_target("obj.getClass()") is None
    assert Lifter._bare_typeof_target("") is None
    assert Lifter._bare_typeof_target(None) is None


def test_bare_typeof_declines_quoted():
    assert Lifter._bare_typeof_target('"typeof(System.String)"') is None
