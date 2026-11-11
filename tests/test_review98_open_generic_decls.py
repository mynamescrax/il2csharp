"""Fix 98: open-generic declaration hints close over the `new` RHS.

A tracked hint like `UnityAction<T0>` / `EventCallback<TEventType>` /
`Func<TSource, bool>` is an unresolved generic parameter (VAR/MVAR at
some depth), while the same line's `new UnityAction<float>()` is the
exact closed allocation identity. The declaration now propagates the
closed RHS spelling when the generic definition matches (same short
base, same arity) and the RHS is textually closed. Anything else --
different bases (`IList<T>` vs `new List<int>()`), open RHS, non-`new`
RHS, closed/unknown tracked types -- keeps the old spelling.
"""

from il2cpp import Decompiler


OPEN_T = (6506052600, 0x15 << 16)
CLOSED_T = (300, 0x08 << 16)


def make_dec(type_name_map, has_var_map=None):
    dec = Decompiler.__new__(Decompiler)
    dec._var_types = {}
    dec.L = type("L", (), {})()
    dec.L._var_types = {}
    dec.L.slot_types = {}
    dec.L._type_hints = {}
    dec.L.il = type("I", (), {})()
    dec.L.il.type_name = lambda t: type_name_map.get(t, "object")
    if has_var_map is not None:
        dec._type_has_var = lambda t: has_var_map.get(t)
    return dec


def decl(tok, rhs, type_name, has_var):
    dec = make_dec({tok: type_name} if isinstance(tok, tuple) else {},
                   {tok: has_var} if isinstance(tok, tuple) else None)
    # simpler: build maps keyed by the tuple token value
    return dec


def decl_type(tracked, tn, rhs, has_var):
    dec = make_dec({tracked: tn}, {tracked: has_var})
    dec._var_types = {tracked: tracked} if False else {}
    # _decl_type_of looks up tok in slot/_var_types/_type_hints; use hints
    dec.L._type_hints = {"t1": tracked}
    dec.L.il.type_name = lambda t, tn0=tn: tn0
    dec._type_has_var = lambda t, hv=has_var: hv
    return dec._decl_type_of("t1", rhs)


def test_unityaction_closes():
    assert decl_type(OPEN_T, "UnityEngine.Events.UnityAction<T0>",
                     "new UnityEngine.Events.UnityAction<float>()", True) == \
        "UnityEngine.Events.UnityAction<float>"


def test_eventcallback_closes():
    assert decl_type(OPEN_T, "EventCallback<TEventType>",
                     "new EventCallback<PointerUpEvent>()", True) == \
        "EventCallback<PointerUpEvent>"


def test_func_two_args_close():
    assert decl_type(OPEN_T, "Func<TSource, bool>",
                     "new Func<Npc, bool>()", True) == \
        "Func<Npc, bool>"


def test_nested_generic_rhs_closes():
    assert decl_type(
        OPEN_T, "Func<TKey, TValue>",
        "new Func<string, CallSite<Func<CallSite, object, object>>>()",
        True) == "Func<string, CallSite<Func<CallSite, object, object>>>"


def test_qualified_predicate_closes_over_namespace():
    # TMPro.* namespaces must not read as open generic parameters
    assert decl_type(OPEN_T, "System.Predicate<T>",
                     "new System.Predicate<TMPro.KerningPair>()", True) == \
        "System.Predicate<TMPro.KerningPair>"
    assert Decompiler.__new__(Decompiler)._args_contain_open_param(
        "System.Predicate<TMPro.KerningPair>") is False
    assert Decompiler.__new__(Decompiler)._args_contain_open_param(
        "System.Predicate<T>") is True
    assert Decompiler.__new__(Decompiler)._args_contain_open_param(
        "Func<string, CallSite<Func<CallSite, object, object>>>") is False


def test_different_base_keeps_open():
    assert decl_type(OPEN_T, "IList<T>", "new List<int>()", True) == "IList<T>"


def test_open_rhs_keeps_open():
    assert decl_type(OPEN_T, "List<T>", "new List<TKey>()", True) == "List<T>"


def test_non_new_rhs_keeps_open():
    assert decl_type(OPEN_T, "Enumerator<T>", "obj8.GetEnumerator()", True) == \
        "Enumerator<T>"


def test_array_rhs_keeps_open():
    assert decl_type(OPEN_T, "List<T>", "new List<int>[4]", True) == "List<T>"


def test_closed_tracked_keeps_spelling():
    assert decl_type(CLOSED_T, "List<Transform>",
                     "new List<Transform>()", False) == "List<Transform>"


def test_unknown_tracked_keeps_spelling():
    assert decl_type(OPEN_T, "UnityAction<T0>",
                     "new UnityAction<float>()", None) == "UnityAction<T0>"


def test_arity_mismatch_keeps_open():
    assert decl_type(OPEN_T, "Func<TSource, TResult>",
                     "new Func<int>()", True) == "Func<TSource, TResult>"


def test_concrete_t_names_not_open():
    # Transform/Type/Timer start with T but are closed concrete types
    dec = Decompiler.__new__(Decompiler)
    assert not dec._OPEN_PARAM_RX.search("List<Transform>")
    assert not dec._OPEN_PARAM_RX.search("Func<Type, bool>")
    assert not dec._OPEN_PARAM_RX.search("Comparison<Timer>")
    assert dec._OPEN_PARAM_RX.search("UnityAction<T0>")
    assert dec._OPEN_PARAM_RX.search("Func<TSource, bool>")
    assert dec._OPEN_PARAM_RX.search("EventCallback<TEventType>")


def test_new_rhs_type_parsing():
    dec = Decompiler.__new__(Decompiler)
    assert dec._new_rhs_type("new UnityAction<float>()") == "UnityAction<float>"
    assert dec._new_rhs_type(
        "new UnityEngine.Events.UnityAction<float>(a, b)") == \
        "UnityEngine.Events.UnityAction<float>"
    assert dec._new_rhs_type("new List<int>[4]") is None
    assert dec._new_rhs_type("obj8.GetEnumerator()") is None
    assert dec._new_rhs_type("new Foo()") is None
    assert dec._new_rhs_type("new Foo<Bar") is None


def test_split_generic_nested():
    dec = Decompiler.__new__(Decompiler)
    base, args = dec._split_generic(
        "Func<string, CallSite<Func<CallSite, object, object>>>")
    assert base == "Func"
    assert args == ["string", "CallSite<Func<CallSite, object, object>>"]
    base, args = dec._split_generic("UnityAction<float>")
    assert (base, args) == ("UnityAction", ["float"])
    base, args = dec._split_generic("int")
    assert (base, args) == ("int", [])


def test_rename_locals_end_to_end():
    # through the real _rename_locals path with a stubbed openness proof
    dec = Decompiler.__new__(Decompiler)
    dec._var_types = {"t1006": OPEN_T}
    dec.L = type("L", (), {})()
    dec.L._var_types = {}
    dec.L.slot_types = {}
    dec.L._type_hints = {}
    dec.L.il = type("I", (), {})()
    dec.L.il.type_name = lambda t: "UnityAction<T0>" if t == OPEN_T else "object"
    dec._type_has_var = lambda t: True if t == OPEN_T else None
    dec.L._gp_blocked = ()
    out = dec._rename_locals(
        ["var t1006 = new UnityAction<float>();"])
    assert out == ["UnityAction<float> obj1 = new UnityAction<float>();"]
