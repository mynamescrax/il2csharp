"""Bare-`?` operands render `unknown` (LegsAnimator gate); protected shapes stay."""
import re

from il2cpp import Decompiler

BARE_Q = re.compile(r'(?<![\w.?"]) \?(?![.?])')


def render1(ln):
    return Decompiler.__new__(Decompiler)._render([ln])[0]


def _assert_no_bare_q(out):
    assert 'unknown' in out, out
    assert not BARE_Q.search(out), out


def test_star_unknown_operand():
    _assert_no_bare_q(render1('x = a * ?;'))


def test_plus_unknown_operand_in_parens():
    _assert_no_bare_q(render1('y = (b - ?) * c;'))


def test_question_in_string_untouched():
    assert render1('s = "?";') == 's = "?";'


def test_ternary_untouched():
    assert render1('y = c ? a : b;') == 'y = c ? a : b;'


def test_null_conditional_untouched():
    assert render1('y = o?.m;') == 'y = o?.m;'


def test_coalesce_untouched():
    assert render1('y = a ?? b;') == 'y = a ?? b;'
