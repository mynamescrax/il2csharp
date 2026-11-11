"""Fix 132e: prefix unary rendering (NEG `-`, NOT `~`) never fuses into a
predecrement or sheds grouping, and a plain `sub_` call declines XMM
argument texts that cannot parse (portable)."""
import pytest

pytest.importorskip('iced_x86')

from il2cpp.lifter.insn import _unary_txt  # noqa: E402
from il2cpp.lifter.calls import _CallsMixin  # noqa: E402
from il2cpp.text import _BIN_PREC  # noqa: E402


def test_negating_a_negation_is_not_a_predecrement():
    assert _unary_txt('-', '-(int)(x)', None) == '-(-(int)(x))'


def test_atomic_operands_stay_bare():
    assert _unary_txt('-', '(int)(x)', None) == '-(int)(x)'
    assert _unary_txt('-', 'obj.f(a, b)', None) == '-obj.f(a, b)'
    assert _unary_txt('~', 'num1', None) == '~num1'
    assert _unary_txt('-', '(a + b)', None) == '-(a + b)'


def test_composed_or_spaced_operands_are_grouped():
    assert _unary_txt('-', 'a + b', _BIN_PREC['+']) == '-(a + b)'
    assert _unary_txt('~', 'a & b', _BIN_PREC['&']) == '~(a & b)'
    assert _unary_txt('-', 'a == b', None) == '-(a == b)'
    assert _unary_txt('-', 'x as Foo', None) == '-(x as Foo)'


class _E(object):
    def __init__(self, text):
        self.text = text
        self._unk = False


class _Fake(_CallsMixin):
    def __init__(self):
        class _IL(object):
            addr_candidates = {}
        class _B(object):
            exports = {}
        self.il = _IL()
        self.bin = _B()


def test_placeholder_xmm_argument_declines(monkeypatch):
    import il2cpp.lifter.calls as calls
    monkeypatch.setattr(calls, 'entry_live_args', lambda il, t: ('x', '', '', ''))
    f = _Fake()
    none4 = [None] * 4
    ok = f._entry_live_call_args(0x1000, none4, ['_'] * 4, [_E('v.x * 2f'), None, None, None])
    assert ok == ['v.x * 2f']
    for bad in ('(obj20) * GenericMethod#571950', 'a ? b'):
        got = f._entry_live_call_args(0x1000, none4, ['_'] * 4, [_E(bad), None, None, None])
        assert got is None, bad
