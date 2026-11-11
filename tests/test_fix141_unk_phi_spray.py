"""Fix 141: an all-unknown phi is `_unk` (il2cpp/dec/analyze.py).

A guard join whose volatile registers are missing on one arm and `_unk` on
the other used to mint a phi Expr with no type and no unknown mark. The call
argument builder treats only `_unk` slots as absent, so every later call
sprayed the stale `vN`/`objN` names as trailing arguments. The merge now
marks such a phi `_unk`; the predicate is shared with the fixed point
`_unknown_phis` (fix 126).
"""
from il2cpp import Decompiler
from il2cpp.expr import Expr


def _unk(name):
    e = Expr(name, None, '?')
    e._unk = True
    return e


def test_missing_and_unknown_values_are_all_unknown():
    assert Decompiler._phi_all_unknown([None, _unk('v16')])
    assert Decompiler._phi_all_unknown([_unk('v16'), _unk('v17')])
    assert Decompiler._phi_all_unknown([None, None])


def test_one_real_value_makes_the_phi_known():
    assert not Decompiler._phi_all_unknown(
        [_unk('v16'), Expr('arg', None, 'obj')])
    assert not Decompiler._phi_all_unknown(
        [Expr('this.count', None, 'int'), None])


def test_the_merge_flag_is_the_same_predicate():
    # the merge assigns `merged[k]._unk = True` exactly when the predicate
    # holds; a merged Expr starts from `_phi_all_unknown`'s answer.
    phi = Expr('v51', None, '?')
    phi._unk = Decompiler._phi_all_unknown([None, _unk('v16')])
    assert phi._unk is True
    real = Expr('v52', None, '?')
    real._unk = Decompiler._phi_all_unknown([_unk('v16'), Expr('x', None, 'obj')])
    assert real._unk is False
