"""Dead-`unknown`-store elimination: unit pins for the pair rule."""
from types import SimpleNamespace

from il2cpp.dec.dataflow import _DataflowMixin


class _FakeFlow(_DataflowMixin):
    pass


def _head(a, b):
    self = _FakeFlow.__new__(_FakeFlow)
    return self._dead_unknown_head(a, b)


def _run(lines):
    self = _FakeFlow.__new__(_FakeFlow)
    return self._drop_dead_unknown_store(lines)


def test_bare_pair_drops_first():
    assert _head('    vector32 = unknown;', '    vector32 = 0;') == ('drop',)
    assert _run(['a;', '    vector32 = unknown;', '    vector32 = 0;', 'b;']) == [
        'a;', '    vector32 = 0;', 'b;']


def test_chain_keeps_rest():
    assert _run(['    x = unknown;', '    x = 0;', '    x = 1;']) == [
        '    x = 0;', '    x = 1;']


def test_slot_and_decl_shapes():
    assert _head('    ((byte*)obj7 - 0x50)[0] = unknown;',
                 '    ((byte*)obj7 - 0x50)[0] = vector34;') == ('drop',)
    assert _head('    object obj87 = unknown;',
                 '    obj87 = 0;') == ('strip', '    object obj87;')
    assert _run(['    object obj87 = unknown;', '    obj87 = 0;']) == [
        '    object obj87;', '    obj87 = 0;']


def test_declines():
    assert _head('    x = unknown;', '    y = 0;') is None
    assert _head('    x = unknown;', '    x = x + 1;') is None
    assert _head('    x = unknown;', '    if (y) {}') is None
    assert _head('    x = unknown;', '    x == 0;') is None
    assert _head('    var t0 = unknown;', '    t0 = 0;') is None
    assert _head('    ref int x = unknown;', '    x = 0;') is None
    assert _head('    (new uint[4])[0x0] = unknown;',
                 '    (new uint[4])[0x0] = unknown;') is None
    assert _head('    case 1: x = unknown;', '    x = 0;') is None
    assert _head('L1: x = unknown;', '    x = 0;') is None
    assert _head('    this.F = unknown;', '    this.F = 0;') is None
    assert _head('    a[f()] = unknown;', '    a[f()] = 0;') is None
