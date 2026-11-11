"""Element-class IsInst fold: units for the proof reader and element gate.

`_merge_arr_proof` (il2cpp/expr.py) is pure: a merge input proves its
array type exact when it carries the live `_newarr` flag with a tuple
type, or a well-formed dry unanimous-merge `_dry_proof`. Everything
else -- params, fields, `as`-refinements, malformed proofs -- declines.

`_elem_klass_name` needs only the lifter's type Surgeons: reference,
closed, non-object elements pass; value types, open generics,
pointers, generic instances and nested arrays decline.
"""
from types import SimpleNamespace as NS

from il2cpp import Expr, Lifter
from il2cpp.expr import _merge_arr_proof

ARR_TY = (0x5000, 0x1d << 16)
CLASS_TY = (7, 0x12 << 16)
OTHER_ARR = (0x6000, 0x1d << 16)


def test_proof_live_flag_with_tuple():
    e = Expr('a', ARR_TY, 'arr')
    e._newarr = True
    assert _merge_arr_proof(e) == ARR_TY


def test_proof_live_flag_without_tuple_declines():
    e = Expr('a', None, 'arr')
    e._newarr = True
    assert _merge_arr_proof(e) is None


def test_proof_unflagged_declines():
    assert _merge_arr_proof(Expr('a', ARR_TY, 'arr')) is None


def test_proof_non_expr_declines():
    assert _merge_arr_proof(None) is None
    assert _merge_arr_proof('a') is None


def test_proof_dry_proof_carries():
    e = Expr('s', None, '?')
    e._dry_proof = (ARR_TY, True)
    assert _merge_arr_proof(e) == ARR_TY


def test_proof_malformed_dry_proof_declines():
    for bad in (None, True, (None, True), (ARR_TY,), 'x', (ARR_TY, True, 1)):
        e = Expr('s', None, '?')
        e._dry_proof = bad
        assert _merge_arr_proof(e) is None


def test_proof_live_flag_wins_over_absent_dry():
    e = Expr('a', ARR_TY, 'arr')
    e._newarr = True
    assert _merge_arr_proof(e) == ARR_TY


# ---------------------------------------------------------------- gate


def _gate_lifter():
    elem_class = (7, 0x12 << 16)
    elem_object_td = (9, 0x12 << 16)
    elem_vt = (3, 0x11 << 16)
    elem_enum = (4, 0x11 << 16)
    by_ptr = {
        0x5001: elem_class,
        0x5002: (0, 0x12 << 16),
        0x5003: elem_object_td,
        0x5004: elem_vt,
        0x5005: elem_enum,
        0x5006: (0, 0x0e << 16),
        0x5007: (0, 0x08 << 16),
        0x5008: (0, 0x13 << 16),
        0x5009: (0x7000, 0x15 << 16),
        0x500A: (0x7000, 0x0f << 16),
        0x500B: (0x7000, 0x1d << 16),
    }
    names = {
        elem_class: 'System.Type',
        (0, 0x12 << 16): 'object',
        elem_object_td: 'System.Object',
        elem_vt: 'System.Int32',
        elem_enum: 'System.EnumKind',
        (0, 0x0e << 16): 'string',
        (0, 0x08 << 16): 'int',
        (0, 0x13 << 16): 'T',
    }
    tds = [None] * 10
    tds[7] = NS(is_valuetype=False, is_enum=False)
    tds[9] = NS(is_valuetype=False, is_enum=False)
    tds[3] = NS(is_valuetype=True, is_enum=False)
    tds[4] = NS(is_valuetype=True, is_enum=True)
    lift = Lifter.__new__(Lifter)
    lift.il = NS(
        type_from_ptr=lambda p: by_ptr.get(p),
        type_name=lambda t: names.get(t, 'object'),
        _type_enum=lambda t: (t[1] >> 16) & 0xFF if t else 0,
    )
    lift.meta = NS(typedefs=tds)
    return lift, by_ptr


def _arr(elem_ptr):
    return (elem_ptr, 0x1d << 16)


def test_gate_reference_class_passes():
    lift, _ = _gate_lifter()
    assert lift._elem_klass_name(_arr(0x5001), True)[0] == 'System.Type'


def test_gate_string_passes():
    lift, _ = _gate_lifter()
    assert lift._elem_klass_name(_arr(0x5006), True)[0] == 'string'


def test_gate_inexact_declines():
    lift, _ = _gate_lifter()
    assert lift._elem_klass_name(_arr(0x5001), False) is None
    assert lift._elem_klass_name(_arr(0x5001), None) is None


def test_gate_object_elements_decline():
    lift, _ = _gate_lifter()
    assert lift._elem_klass_name(_arr(0x5002), True) is None
    assert lift._elem_klass_name(_arr(0x5003), True) is None


def test_gate_value_types_decline():
    lift, _ = _gate_lifter()
    assert lift._elem_klass_name(_arr(0x5004), True) is None
    assert lift._elem_klass_name(_arr(0x5005), True) is None
    assert lift._elem_klass_name(_arr(0x5007), True) is None


def test_gate_open_generic_declines():
    lift, _ = _gate_lifter()
    assert lift._elem_klass_name(_arr(0x5008), True) is None


def test_gate_genericinst_ptr_nested_decline():
    lift, _ = _gate_lifter()
    assert lift._elem_klass_name(_arr(0x5009), True) is None
    assert lift._elem_klass_name(_arr(0x500A), True) is None
    assert lift._elem_klass_name(_arr(0x500B), True) is None


def test_gate_non_array_declines():
    lift, _ = _gate_lifter()
    assert lift._elem_klass_name((0, 0x12 << 16), True) is None
    assert lift._elem_klass_name(None, True) is None
