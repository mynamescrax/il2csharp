"""Fix 126: phi copies never read an unknown register (il2cpp/dec/analyze.py).

An `_unk` register value (never written / clobbered) on a phi in-edge used to
materialize as `phi = vN;` with vN defined nowhere (CS0103 at every such
copy, ~57k sites on the fixture). The edge now carries no copy, and a phi
whose every source is unknown is itself unknown, transitively.
"""
from types import SimpleNamespace

from il2cpp import Decompiler
from il2cpp.expr import Expr

FLAGS = '!flags'


def _unk(name):
    e = Expr(name, None, '?')
    e._unk = True
    return e


def _blk(preds, end_state):
    return SimpleNamespace(preds=list(preds), end_state=end_state)


def _dec():
    dec = Decompiler.__new__(Decompiler)
    dec.L = SimpleNamespace(out=None, _note_use=lambda v: None,
                            _aggregate_phi_types={}, _u=500, _cur_ip=0)
    dec.phi_pre = {}
    dec._var_types = {}
    return dec


def _loop_blocks(entry_val, body_val):
    # 0 entry -> 1 header <- 2 latch
    return {
        0: _blk([], {'RBX': entry_val}),
        1: _blk([0, 2], None),
        2: _blk([1], {'RBX': body_val}),
    }


def test_unknown_entry_edge_gets_no_copy_but_back_edge_does():
    blocks = _loop_blocks(_unk('v3'), Expr('v40', None, 'int'))
    dec = _dec()
    dec._build_phi_copies(blocks, {(1, 'RBX'): 'v40'}, FLAGS)
    # back edge carries the phi itself (no copy), entry is unknown (no copy)
    assert dec.phi_copies == {}

    blocks = _loop_blocks(_unk('v3'), Expr('v41 + 1', None, 'int'))
    dec = _dec()
    dec._build_phi_copies(blocks, {(1, 'RBX'): 'v41'}, FLAGS)
    assert dec.phi_copies == {(2, 1): ['v41 = v41 + 1;']}


def test_known_entry_value_still_copies():
    blocks = _loop_blocks(Expr('this.count', None, 'int'), Expr('v41 + 1', None, 'int'))
    dec = _dec()
    dec._build_phi_copies(blocks, {(1, 'RBX'): 'v41'}, FLAGS)
    assert dec.phi_copies[(0, 1)] == ['v41 = this.count;']
    assert dec.phi_copies[(2, 1)] == ['v41 = v41 + 1;']


def test_all_unknown_phi_propagates_through_a_chain():
    # 0 -> 1 (phi A over unk sources from 0 and 3), 1 -> 2 (phi B = A | unk)
    phi_a = Expr('v50', None, '?')
    blocks = {
        0: _blk([], {'RSI': _unk('v4')}),
        3: _blk([], {'RSI': _unk('v9')}),
        1: _blk([0, 3], {'RSI': phi_a}),
        4: _blk([], {'RSI': _unk('v11')}),
        2: _blk([1, 4], None),
    }
    phi = {(1, 'RSI'): 'v50', (2, 'RSI'): 'v51'}
    assert Decompiler._unknown_phis(blocks, phi, FLAGS) == {'v50', 'v51'}
    dec = _dec()
    dec._build_phi_copies(blocks, phi, FLAGS)
    assert dec.phi_copies == {}


def test_one_real_source_makes_the_phi_known():
    phi_a = Expr('v50', None, '?')
    blocks = {
        0: _blk([], {'RSI': _unk('v4')}),
        3: _blk([], {'RSI': Expr('arg', None, 'obj')}),
        1: _blk([0, 3], {'RSI': phi_a}),
        4: _blk([], {'RSI': _unk('v11')}),
        2: _blk([1, 4], None),
    }
    phi = {(1, 'RSI'): 'v50', (2, 'RSI'): 'v51'}
    assert Decompiler._unknown_phis(blocks, phi, FLAGS) == set()
    dec = _dec()
    dec._build_phi_copies(blocks, phi, FLAGS)
    assert dec.phi_copies == {(3, 1): ['v50 = arg;'], (1, 2): ['v51 = v50;']}


def test_flags_phis_are_never_candidates():
    blocks = {0: _blk([], {FLAGS: _unk('v1')}), 1: _blk([0], None)}
    assert Decompiler._unknown_phis(blocks, {(1, FLAGS): 'v2'}, FLAGS) == set()
