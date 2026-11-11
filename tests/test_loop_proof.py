"""Loop-carried IsInst proof primitive pins (no source change).

Provenance: docs/todo.md loop-carried proof loss (~25 sites, needs
dry-header discriminating test, not a textual rule) + landing-9
soundness kernel (params/fields/statics never prove exact).

Covers il2cpp/expr.py::_merge_arr_proof only -- the merge-unanimity
in il2cpp/dec/analyze.py:479-484 composes this primitive per path.
A textual fold rule without these discriminants would over-fire.
"""
from il2cpp.expr import Expr, _merge_arr_proof


def _arr(ty):
    e = Expr("arr", ty, "arr")
    e._newarr = True
    return e


def test_newarr_proven_returns_ty():
    ty = (0x1D, 0x1234)
    assert _merge_arr_proof(_arr(ty)) == ty


def test_dry_proof_returns_ty():
    ty = (0x1D, 0x1234)
    e = Expr("arr", ty, "arr")
    e._dry_proof = (ty, True)
    assert _merge_arr_proof(e) == ty


def test_plain_unproven_declines():
    assert _merge_arr_proof(Expr("arr", (0x1D, 0x1234), "arr")) is None


def test_newarr_without_ty_declines():
    e = Expr("arr", None, "arr")
    e._newarr = True
    assert _merge_arr_proof(e) is None


def test_malformed_dry_proof_declines():
    e = Expr("arr", (0x1D, 0x1234), "arr")
    e._dry_proof = ("not-a-ty", True)
    assert _merge_arr_proof(e) is None
    e2 = Expr("arr", (0x1D, 0x1234), "arr")
    e2._dry_proof = None
    assert _merge_arr_proof(e2) is None


def test_non_expr_declines():
    assert _merge_arr_proof(None) is None
    assert _merge_arr_proof("arr") is None
