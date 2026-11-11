"""Fix 101: bare-param declaration hints close over the same-line `new` RHS.

A tracked hint that is one bare VAR/MVAR (`T`, `T1`, `TValue`) names no
type, while the same line's `new ObiPinConstraintsBatch()` /
`new List<int>()` is the exact closed allocation identity. The
declaration now takes the RHS spelling. `T x = new C(...)` never
compiles under any binding of `T`, so no compiling method can regress.
Anything else -- non-bare tuples, non-bare spellings, open generic RHS,
bare `new T()`, non-`new`/array/initializer RHS, closed/unknown tracked
types -- keeps the old spelling.
"""

from il2cpp import Decompiler

MVART = (7, 0x1E << 16)
VART = (3, 0x13 << 16)
GINSTT = (6506052600, 0x15 << 16)
INTT = (300, 0x08 << 16)


def decl_type(tracked, tn, rhs, has_var):
    dec = Decompiler.__new__(Decompiler)
    dec._var_types = {}
    dec.L = type("L", (), {})()
    dec.L._var_types = {}
    dec.L.slot_types = {}
    dec.L._type_hints = {"t1": tracked}
    dec.L.il = type("I", (), {})()
    dec.L.il.type_name = lambda t, tn0=tn: tn0
    dec._type_has_var = lambda t, hv=has_var: hv
    return dec._decl_type_of("t1", rhs)


def test_non_generic_closes():
    assert decl_type(MVART, "T", "new ObiPinConstraintsBatch()", True) == \
        "ObiPinConstraintsBatch"


def test_class_var_closes():
    assert decl_type(VART, "TValue", "new __c__DisplayClass20_0()", True) == \
        "__c__DisplayClass20_0"


def test_generic_rhs_closes_over_bare():
    assert decl_type(MVART, "T", "new List<int>()", True) == "List<int>"
    assert decl_type(VART, "T1", "new List<Transform>(4)", True) == \
        "List<Transform>"


def test_qualified_non_generic_closes():
    assert decl_type(MVART, "T", "new Ns.Foo(a, b)", True) == "Ns.Foo"


def test_open_generic_rhs_declines():
    assert decl_type(MVART, "T", "new List<TKey>()", True) == "T"


def test_bare_new_declines():
    assert decl_type(MVART, "T", "new T()", True) == "T"
    assert decl_type(VART, "TValue", "new TValue()", True) == "TValue"


def test_dotted_target_closes():
    # superseded by test_tmpro_namespace_is_closed: qualification
    # itself is the closedness proof, whatever the first component.
    assert decl_type(MVART, "T", "new T.Foo()", True) == "T.Foo"


def test_non_new_rhs_declines():
    assert decl_type(MVART, "T", "obj15", True) == "T"
    assert decl_type(MVART, "T", "obj8.GetEnumerator()", True) == "T"
    assert decl_type(MVART, "T", "default", True) == "T"


def test_array_and_initializer_decline():
    assert decl_type(MVART, "T", "new List<int>[4]", True) == "T"
    assert decl_type(MVART, "T", "new Foo { a = 1 }", True) == "T"


def test_non_bare_tuple_declines():
    # same spelling, but the tracked tuple is a generic instantiation:
    # structure wins over the name, so the bare rule declines.
    assert decl_type(GINSTT, "T", "new Foo()", True) == "T"
    # same-base generics still close through the fix-98 path first.
    assert decl_type(GINSTT, "List<T>", "new List<int>()", True) == \
        "List<int>"


def test_non_bare_spelling_declines():
    assert decl_type(MVART, "Transform", "new Foo()", True) == "Transform"
    assert decl_type(MVART, "T[]", "new Foo()", True) == "T[]"


def test_unreadable_openness_declines():
    assert decl_type(MVART, "T", "new Foo()", None) == "T"
    assert decl_type(MVART, "T", "new Foo()", False) == "T"


def test_closed_tracked_keeps_spelling():
    assert decl_type(INTT, "int", "new Foo()", False) == "int"


def test_bare_new_rhs_type_parsing():
    dec = Decompiler.__new__(Decompiler)
    assert dec._bare_new_rhs_type("new Foo()") == "Foo"
    assert dec._bare_new_rhs_type("new Ns.Foo(a, b)") == "Ns.Foo"
    assert dec._bare_new_rhs_type("new __c__DisplayClass20_0()") == \
        "__c__DisplayClass20_0"
    assert dec._bare_new_rhs_type("new List<int>()") is None
    assert dec._bare_new_rhs_type("new T()") is None
    assert dec._bare_new_rhs_type("new Foo[4]") is None
    assert dec._bare_new_rhs_type("new Foo { a = 1 }") is None
    assert dec._bare_new_rhs_type("obj.Foo()") is None
    assert dec._bare_new_rhs_type("new Foo<Bar") is None


def test_tmpro_namespace_is_closed():
    # `TMPro` reads as a param under the bare regex, but a namespace
    # component is never a parameter (fix-98 invariant): only the last
    # dotted component decides openness.
    dec = Decompiler.__new__(Decompiler)
    assert dec._bare_new_rhs_type("new TMPro.KerningPair()") == \
        "TMPro.KerningPair"
    assert decl_type(MVART, "T", "new TMPro.KerningPair()", True) == \
        "TMPro.KerningPair"
    # dotted whatever the first component spells: qualification itself
    # is the closedness proof.
    assert dec._bare_new_rhs_type("new T.Foo()") == "T.Foo"


def test_bare_t_like_target_declines():
    # no dotted qualification to prove closedness: `TMP_Character`
    # is textually a bare parameter, so the rule declines.
    dec = Decompiler.__new__(Decompiler)
    assert dec._bare_new_rhs_type("new TMP_Character()") is None
    assert decl_type(MVART, "T", "new TMP_Character()", True) == "T"


def test_angle_target_declines():
    # `<>c__` display-class spellings are normalized only at the file
    # boundary; mid-pipeline they are not a valid declaration type.
    dec = Decompiler.__new__(Decompiler)
    assert dec._bare_new_rhs_type("new <>c__DisplayClass20_0()") is None
    assert decl_type(VART, "T1", "new <>c__DisplayClass20_0()", True) == \
        "T1"


def test_rename_locals_end_to_end():
    dec = Decompiler.__new__(Decompiler)
    dec._var_types = {"t1006": MVART}
    dec.L = type("L", (), {})()
    dec.L._var_types = {}
    dec.L.slot_types = {}
    dec.L._type_hints = {}
    dec.L.il = type("I", (), {})()
    dec.L.il.type_name = lambda t: "T" if t == MVART else "object"
    dec._type_has_var = lambda t: True if t == MVART else None
    dec.L._gp_blocked = ()
    out = dec._rename_locals(
        ["var t1006 = new ObiPinConstraintsBatch();"])
    assert out == ["ObiPinConstraintsBatch obj1 = new ObiPinConstraintsBatch();"]
