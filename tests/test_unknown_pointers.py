"""Pin cleanup ordering through the actual renderer, including valid selects."""
import pytest
from tree_sitter import Language, Parser
import tree_sitter_c_sharp

from il2cpp import Decompiler


def render(line):
    dec = Decompiler.__new__(Decompiler)
    return "\n".join(dec._render([line]))


def assert_parseable(body):
    parser = Parser(Language(tree_sitter_c_sharp.language()))
    tree = parser.parse(("class C { void M() {\n" + body + "\n} }").encode())
    assert not tree.root_node.has_error, body


def test_unknown_pointer_base_is_not_a_ternary_condition():
    text = render("var result = *(? + state + 0xc);")
    assert "((byte*)unknown + state + 0xc)[0]" in text
    assert "?" not in text and ": default" not in text
    assert_parseable(text)


def test_unknown_index_times_four_is_multiplication_not_a_deref():
    text = render("var result = *(ptr + ?*4 + 0x0);")
    assert "unknown*4" in text
    assert "((byte*)4)" not in text
    assert "?" not in text and ": default" not in text
    assert_parseable(text)


@pytest.mark.parametrize("expression", [
    "(cond ? -value : other)",
    "(cond ? &value : other)",
    "(cond ? *4 : other)",
    "(cond ? value : other)",
])
def test_real_ternary_condition_and_arms_are_preserved(expression):
    text = render("var result = " + expression + ";")
    assert "cond ?" in text and ": other" in text
    assert "unknown" not in text
    assert_parseable(text)


def test_question_mark_in_literal_is_not_an_unknown_operand():
    text = render('f("? + state : default");')
    assert '"? + state : default"' in text
    assert "unknown" not in text
    assert_parseable(text)


def test_unknown_operand_after_return_remains_honest():
    text = render("return ?;")
    assert "return unknown;" in text
    assert_parseable(text)