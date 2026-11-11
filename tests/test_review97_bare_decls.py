"""Fix 97: first-use bare assignments declare their temp.

`objN = rhs;` with no prior declaration (stack-slot zeroing, phi copies,
unbound call results) left the method uncompilable. The declaration pass
now types them exactly like `var` lines, from the same tracked-type
lookup; a later `var` line for the same temp keeps only its assignment.
Companions keep downstream folds firing on the new declaration shapes:
typed `bool flagN` ternary/0/1 folds, declaration-aware ternary arms,
and typed hop-temp folding.
"""
from il2cpp import Decompiler
from types import SimpleNamespace


INT_T = (0, 0x08 << 16)
BOOL_T = (0, 0x02 << 16)
FLOAT_T = (0, 0x0C << 16)
HIT_T = (5, 0x11 << 16)
TEE_T = (6, 0x13 << 16)


def rename(lines, var_types=None, hints=None):
    dec = Decompiler.__new__(Decompiler)
    dec._var_types = dict(var_types or {})
    dec.L = type("L", (), {})()
    dec.L._var_types = {}
    dec.L.slot_types = {}
    dec.L._type_hints = dict(hints or {})
    dec.L.il = type("I", (), {})()
    dec.L.il.type_name = lambda t: {
        INT_T: "int",
        BOOL_T: "bool",
        FLOAT_T: "float",
        HIT_T: "UnityEngine.RaycastHit",
        TEE_T: "T",
    }.get(t, "object")
    return dec._rename_locals(list(lines))


def test_bare_first_use_declares_object():
    assert rename(["t1 = G();"]) == ["object obj1 = G();"]


def test_bare_first_use_integer_only_temp_is_int():
    # fix 135: an untracked temp that only ever holds integers is int
    assert rename(["t1 = 0;"]) == ["int num1 = 0;"]


def test_bare_first_use_uses_tracked_type():
    assert rename(["t1 = flag2;"], var_types={"t1": BOOL_T}) == [
        "bool flag1 = flag2;"]


def test_later_var_line_becomes_bare_assignment():
    assert rename(["t1 = 0;", "var t1 = obj2;"]) == [
        "object obj1 = 0;", "obj1 = obj2;"]


def test_var_then_bare_stays_bare():
    assert rename(["var t1 = obj2;", "t1 = obj3;"]) == [
        "object obj1 = obj2;", "obj1 = obj3;"]


def test_single_prologue_scalar_param_copy_keeps_declared_type():
    dec = Decompiler.__new__(Decompiler)
    dec._var_types = {}
    param = SimpleNamespace(name='volume', type=0)
    il = SimpleNamespace(types=[FLOAT_T], type_name=lambda ty: 'float')
    dec.L = SimpleNamespace(
        meta=SimpleNamespace(method_params=lambda method: [param]),
        il=il, slot_types={}, _var_types={}, _type_hints={})
    method = object()
    assert dec._rename_locals(['s_10 = volume;', 'Use(s_10);'], method) == [
        'float real1 = volume;', 'Use(real1);']
    dec._var_types = {}
    assert dec._rename_locals(
        ['s_10 = volume;', 's_10 = 0f;', 'Use(s_10);'], method) == [
        'object obj1 = volume;', 'obj1 = 0f;', 'Use(obj1);']
    dec._var_types = {}
    assert dec._rename_locals(
        ['s_10 = volume;', 'Use(ref s_10);'], method) == [
        'object obj1 = volume;', 'Use(ref obj1);']


def test_comparisons_labels_and_members_untouched():
    lines = [
        "if (obj1 == 0)",
        "if (obj1 != obj2)",
        "L_123:",
        "this.field1 = obj1;",
        "obj1();",
    ]
    # t1 never appears, so no rename tokens exist; lines pass through
    dec = Decompiler.__new__(Decompiler)
    dec._var_types = {}
    dec.L = type("L", (), {})()
    dec.L._var_types = {}
    dec.L.slot_types = {}
    dec.L._type_hints = {}
    dec.L.il = type("I", (), {})()
    assert dec._rename_locals(list(lines)) == lines


def test_bool_sugar_folds_typed_decl_forms():
    dec = Decompiler.__new__(Decompiler)
    dec.L = type("L", (), {})()
    dec.L.il = type("I", (), {})()
    dec.L.il.types = []
    lines = [
        "bool flag1 = (cond1 ? 1 : 0);",
        "bool flag2 = cond2 ? 1 : 0;",
        "bool flag3 = 0;",
        "bool flag4 = 1;",
        "flag5 = (cond5 ? 1 : 0);",
    ]
    assert dec._bool_sugar(list(lines)) == [
        "bool flag1 = cond1;",
        "bool flag2 = cond2;",
        "bool flag3 = false;",
        "bool flag4 = true;",
        "flag5 = cond5;",
    ]


def test_ternary_keeps_arm_declaration():
    dec = Decompiler.__new__(Decompiler)
    lines = [
        "if (cond1)",
        "{",
        "bool flag1 = obj2;",
        "}",
        "else",
        "{",
        "flag1 = obj3;",
        "}",
    ]
    assert dec._ternary_pass(list(lines)) == ["bool flag1 = cond1 ? obj2 : obj3;"]


def test_ternary_bare_arms_unchanged():
    dec = Decompiler.__new__(Decompiler)
    lines = [
        "if (cond1)",
        "{",
        "obj1 = obj2;",
        "}",
        "else",
        "{",
        "obj1 = obj3;",
        "}",
    ]
    assert dec._ternary_pass(list(lines)) == ["obj1 = cond1 ? obj2 : obj3;"]


def test_hop_fold_accepts_typed_def():
    dec = Decompiler.__new__(Decompiler)
    lines = [
        "int num5 = this.count + 1;",
        "this.count = num5;",
    ]
    out = dec._compound_assign(list(lines))
    assert out == ["this.count += 1;"]


def test_hop_fold_declines_across_a_target_write():
    dec = Decompiler.__new__(Decompiler)
    lines = [
        "int num5 = this.count + 1;",
        "this.count += 1;",
        "this.count = num5;",
    ]
    assert dec._compound_assign(list(lines)) == lines


def test_hop_fold_declines_across_a_brace_or_label():
    dec = Decompiler.__new__(Decompiler)
    for mid in ("{", "}", "L_18057b25f:"):
        lines = [
            "int num5 = this.count + 1;",
            mid,
            "this.count = num5;",
        ]
        assert dec._compound_assign(list(lines)) == lines


def test_fix_select_skips_null_operators():
    dec = Decompiler.__new__(Decompiler)
    for line in (
        "obj1 = (obj2?.Foo());",
        "obj1 = (obj2 ?? (object)obj3);",
        "obj1 = (arr?[0]);",
    ):
        assert dec._fix_select(line) == line


def test_fix_select_still_appends_to_a_real_mark():
    dec = Decompiler.__new__(Decompiler)
    assert dec._fix_select("obj1 = (cond1 ? obj2);") == \
        "obj1 = (cond1 ? obj2 : default);"


def test_struct_zero_literal_becomes_default():
    assert rename(["t1 = 0f;"], var_types={"t1": HIT_T}) == [
        "UnityEngine.RaycastHit obj1 = default;"]


def test_generic_param_zero_literal_becomes_default():
    assert rename(["t1 = 0;"], var_types={"t1": TEE_T}) == [
        "T obj1 = default;"]


def test_matching_literals_keep_rhs():
    assert rename(["t1 = 0;"], var_types={"t1": INT_T}) == [
        "int num1 = 0;"]
    assert rename(["t1 = 0f;"], var_types={"t1": FLOAT_T}) == [
        "float real1 = 0f;"]
    assert rename(["t1 = 0;"]) == ["int num1 = 0;"]


def test_nonzero_literal_keeps_faithful_value():
    # a nonzero literal under a mismatched type keeps its value instead
    # of baking in a different zero
    assert rename(["t1 = 1;"], var_types={"t1": HIT_T}) == [
        "UnityEngine.RaycastHit obj1 = 1;"]
    assert rename(["t1 = true;"], var_types={"t1": INT_T}) == [
        "int num1 = true;"]


def test_sibling_scopes_redeclare():
    lines = [
        "if (cond1)",
        "{",
        "t1 = obj2;",
        "}",
        "else",
        "{",
        "t1 = obj3;",
        "}",
    ]
    assert rename(lines) == [
        "if (cond1)",
        "{",
        "object obj1 = obj2;",
        "}",
        "else",
        "{",
        "object obj1 = obj3;",
        "}",
    ]


def test_enclosing_decl_suppresses_nested_bare():
    lines = [
        "object obj1 = obj2;",
        "if (cond1)",
        "{",
        "obj1 = obj3;",
        "}",
    ]
    # obj1 is not a rename token here (already renamed input shape is
    # unrepresentative); use t-temps through the real path instead
    assert rename(["var t1 = obj2;", "if (cond1)", "{", "t1 = obj3;", "}"]) == [
        "object obj1 = obj2;", "if (cond1)", "{", "obj1 = obj3;", "}"]


def render(lines):
    dec = Decompiler.__new__(Decompiler)
    return dec._render(list(lines))


def test_render_keeps_default_arm_over_call():
    # fix 97e: fix 97b synthesizes `: default` false arms and _ternary
    # folds them over call true-arms; _render must not orphan the tail
    # into unparseable `? call() ;` (26 ERROR nodes in 23 files).
    line = "Moppable obj10 = !(X.op_Implicit(obj7.getClass())) ? c.GetComponentInParent() : default;"
    assert render([line]) == [line]


def test_render_keeps_default_arm_over_multiarg_call():
    line = "Moppable obj10 = !(X) ? Foo(a, b) : default;"
    assert render([line]) == [line]


def test_render_keeps_chained_default_arm():
    line = "x = a ? b : c ? d : default;"
    assert render([line]) == [line]


def test_render_keeps_zero_arm():
    line = "obj10 = !(X) ? c.GetComponentInParent() : 0;"
    assert render([line]) == [line]


def test_render_strips_dangling_default_tail():
    assert render(["x = Foo(a : default);"]) == ["x = Foo(a );"]


def test_render_strips_dangling_default_after_nullable_decl():
    assert render(["int? v = Foo(a : default);"]) == ["int? v = Foo(a );"]
