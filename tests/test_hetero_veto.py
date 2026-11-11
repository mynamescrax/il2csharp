"""Hetero-guard veto + subclass-tolerance pins (twin-hardening)."""
from types import SimpleNamespace as NS

from il2cpp import Decompiler
from test_review97_bare_decls import rename, INT_T, BOOL_T, FLOAT_T, HIT_T
OBJ_T = (0, 0x1c << 16)
C_T = (10, 0x12 << 16)
D1_T = (11, 0x12 << 16)
D2_T = (12, 0x12 << 16)


def test_escape_veto():
    assert rename(["var t1 = t2;", "t1 = t3;", "Foo(ref t1);"],
                  {"t1": HIT_T, "t2": INT_T, "t3": FLOAT_T}) == [
        "UnityEngine.RaycastHit obj1 = num1;",
        "obj1 = real1;",
        "Foo(ref obj1);"]


def test_call_arg_veto():
    assert rename(["var t1 = t2;", "t1 = t3;", "Foo(t1);"],
                  {"t1": HIT_T, "t2": INT_T, "t3": FLOAT_T}) == [
        "UnityEngine.RaycastHit obj1 = num1;",
        "obj1 = real1;",
        "Foo(obj1);"]


def test_boxing_cast_no_veto():
    assert rename(["var t1 = t2;", "t1 = t3;", "Foo((object)(t1));"],
                  {"t1": HIT_T, "t2": INT_T, "t3": FLOAT_T}) == [
        "object obj1 = num1;",
        "obj1 = real1;",
        "Foo((object)(obj1));"]


def test_member_veto():
    assert rename(["var t1 = t2;", "t1 = t3;", "t1.Foo();"],
                  {"t1": HIT_T, "t2": INT_T, "t3": FLOAT_T}) == [
        "UnityEngine.RaycastHit obj1 = num1;",
        "obj1 = real1;",
        "obj1.Foo();"]


def test_builtin_member_no_veto():
    assert rename(["var t1 = t2;", "t1 = t3;", "t1.ToString();"],
                  {"t1": HIT_T, "t2": INT_T, "t3": FLOAT_T}) == [
        "object obj1 = num1;",
        "obj1 = real1;",
        "obj1.ToString();"]


def test_untyped_helper_amp_no_veto():
    # mi 1242: `&slot` handed to an unresolved `sub_<hex>` helper has no
    # C# parameter type, so it cannot veto the object retype.
    out = rename(["var t1 = t2;", "t1 = t3;",
                  "var t4 = sub_18004a890(&t1, 13);"],
                 {"t1": HIT_T, "t2": INT_T, "t3": FLOAT_T})
    assert out[:2] == ["object obj1 = num1;", "obj1 = real1;"]
    assert "sub_18004a890(&obj1, 13)" in out[2]


def test_untyped_helper_plain_arg_vetoes():
    # A by-value helper argument is still a value read: box-only fails.
    out = rename(["var t1 = t2;", "t1 = t3;", "sub_180006590(t1, 14);"],
                 {"t1": HIT_T, "t2": INT_T, "t3": FLOAT_T})
    assert out[0] == "UnityEngine.RaycastHit obj1 = num1;"


def test_helper_amp_with_value_read_vetoes():
    # Decimal `Buf16`: `&slot` to a helper plus an arithmetic read.
    out = rename(["var t1 = t2;", "t1 = t3;", "var t4 = sub_181d0c060(&t1, 0);",
                  "var t5 = t1 * 3;"],
                 {"t1": HIT_T, "t2": INT_T, "t3": FLOAT_T})
    assert out[0] == "UnityEngine.RaycastHit obj1 = num1;"


def test_field_store_read_vetoes():
    # ActivationServices `constructionCall4._activator = activator4`.
    out = rename(["var t1 = t2;", "t1 = t3;", "t9.f = t1;"],
                 {"t1": HIT_T, "t2": INT_T, "t3": FLOAT_T})
    assert out[0] == "UnityEngine.RaycastHit obj1 = num1;"


def test_generic_call_arg_vetoes():
    # MemoryStream `MemoryMarshal.TryGetArray<byte>(slot, ref seg)`.
    out = rename(["var t1 = t2;", "t1 = t3;",
                  "var t4 = M.TryGetArray<byte>(t1, ref t5);"],
                 {"t1": HIT_T, "t2": INT_T, "t3": FLOAT_T})
    assert out[0] == "UnityEngine.RaycastHit obj1 = num1;"


def test_nested_paren_call_arg_vetoes():
    # RuntimeType `FilterApplyMethodBase(a, (BindingFlags)(n), slot)`.
    out = rename(["var t1 = t2;", "t1 = t3;", "Foo(t6, (Bar)(t7), t1);"],
                 {"t1": HIT_T, "t2": INT_T, "t3": FLOAT_T})
    assert out[0] == "UnityEngine.RaycastHit obj1 = num1;"


def test_resolved_callee_amp_still_vetoes():
    out = rename(["var t1 = t2;", "t1 = t3;", "Foo(&t1, 13);"],
                 {"t1": HIT_T, "t2": INT_T, "t3": FLOAT_T})
    assert out[0] == "UnityEngine.RaycastHit obj1 = num1;"


def test_nested_helper_inside_resolved_call_vetoes():
    # Only the innermost enclosing call counts: `Foo(sub_x(1), &t1)`
    # hands `&t1` to the resolved `Foo`.
    out = rename(["var t1 = t2;", "t1 = t3;", "Foo(sub_18004a890(1), &t1);"],
                 {"t1": HIT_T, "t2": INT_T, "t3": FLOAT_T})
    assert out[0] == "UnityEngine.RaycastHit obj1 = num1;"


def test_undeclared_object_binder_no_veto():
    # mi 1242 `v188 = &s_10;`: the binder has no shadow decl; its printed
    # spelling comes from `_decl_type_of` (object), so it is a box binder.
    out = rename(["var t1 = t2;", "t1 = t3;", "v1 = &t1;"],
                 {"t1": HIT_T, "t2": INT_T, "t3": FLOAT_T})
    assert out[:2] == ["object obj1 = num1;", "obj1 = real1;"]


def test_return_veto_unknown_method():
    assert rename(["var t1 = t2;", "t1 = t3;", "return t1;"],
                  {"t1": HIT_T, "t2": INT_T, "t3": FLOAT_T}) == [
        "UnityEngine.RaycastHit obj1 = num1;",
        "obj1 = real1;",
        "return obj1;"]


def _typed_dec(var_types=None, il_extra=None, method=None):
    il = NS(types=[INT_T, BOOL_T, FLOAT_T, HIT_T, OBJ_T, C_T, D1_T, D2_T],
            _type_enum=lambda t: (t[1] >> 16) & 0xFF if t else 0,
            type_name=lambda t: {(0, 0x08 << 16): "int",
                                 (0, 0x02 << 16): "bool",
                                 (0, 0x0C << 16): "float",
                                 (7, 0x11 << 16): "UnityEngine.RaycastHit",
                                 (0, 0x1c << 16): "object",
                                 (10, 0x12 << 16): "System.Component",
                                 (11, 0x12 << 16): "System.Animation",
                                 (12, 0x12 << 16): "System.Animator"}.get(t, "object"),
            td_of_ty=lambda t: {C_T: 10, D1_T: 11, D2_T: 12}.get(t),
            base_chain_tds=lambda td: {11: (11, 10), 12: (12, 10)}.get(td, (td,)),
            _closed_type_key=lambda t: t)
    if il_extra:
        for k, v in il_extra.items():
            setattr(il, k, v)
    meta = NS(typedefs=[NS(is_valuetype=False, is_enum=False)] * 10 + [
        NS(is_valuetype=False, is_enum=False),
        NS(is_valuetype=False, is_enum=False),
        NS(is_valuetype=False, is_enum=False)],
        method_params=lambda mm: [])
    lift = NS(il=il, meta=meta)
    lift._td_of = lambda ty: il.td_of_ty(ty)
    d = Decompiler.__new__(Decompiler)
    d.L = lift
    d._var_types = dict(var_types or {})
    return d


def test_subclass_tolerance():
    d = _typed_dec({"t1": C_T, "t2": D1_T, "t3": D2_T})
    assert d._rename_locals(["var t1 = t2;", "t1 = t3;"], None) == [
        "System.Component obj1 = obj2;",
        "obj1 = obj3;"]


def test_unrelated_still_fires():
    d = _typed_dec({"t1": C_T, "t2": BOOL_T, "t3": INT_T})
    assert d._rename_locals(["var t1 = t2;", "t1 = t3;"], None) == [
        "object obj1 = flag1;",
        "obj1 = num1;"]


def test_return_object_method_no_veto():
    m = NS(return_type=4)
    d = _typed_dec({"t1": HIT_T, "t2": INT_T, "t3": FLOAT_T})
    assert d._rename_locals(
        ["var t1 = t2;", "t1 = t3;", "return t1;"], m) == [
        "object obj1 = num1;",
        "obj1 = real1;",
        "return obj1;"]
