"""Metadata-safe constructor chains and single-identity object allocation."""
from types import SimpleNamespace as NS

import pytest

from il2cpp import Emitter, Expr, Il2Cpp, Lifter, MethodDef

VOID = (0, 0x01 << 16)
INT = (0, 0x08 << 16)
OBJECT = (0, 0x1C << 16)


def class_ty(index, *, byref=False):
    return (index, (0x12 << 16) | ((1 << 29) if byref else 0))


def value_ty(index):
    return (index, 0x11 << 16)


def typedef(index, name, namespace="", *, parent=-1, value=False, generic=-1):
    return NS(index=index, name=name, namespace=namespace, parent=parent,
              is_valuetype=value, generic_container=generic)


def method(index, declaring, *, name=".ctor", params=0, static=False,
           return_type=0, generic=-1):
    return MethodDef(index, name, declaring, return_type, 0, generic, 1,
                     0x10 if static else 0, 0, 0xFFFF, params)


def bare_il(typedefs, types):
    il = Il2Cpp.__new__(Il2Cpp)
    il.meta = NS(typedefs=typedefs)
    il.types = types
    il.bin = NS()
    il._bases_cache = {}
    return il


def make_lifter(methods, chain=(0, 1), *, caller_name=".ctor",
                caller_declaring=0, typedefs=None, method_specs=()):
    typedefs = typedefs or [typedef(0, "Child"), typedef(1, "Base")]
    lift = Lifter.__new__(Lifter)
    lift.meta = NS(methods=methods, typedefs=typedefs,
                   method_params=lambda m: [])
    lift.il = NS(
        types=[VOID, INT],
        method_specs=list(method_specs),
        _type_enum=lambda ty: (ty[1] >> 16) & 0xFF if ty else 0,
        base_chain_tds=lambda td: tuple(chain) if td == chain[0] else (td,),
    )
    lift.bin = NS()
    lift._current_method = method(99, caller_declaring, name=caller_name)
    lift._current_td = typedefs[caller_declaring]
    return lift


def fresh(text="new Child()", ty=None):
    e = Expr(text, class_ty(0) if ty is None else ty, "obj")
    e._alloc = text
    return e


def test_inheritance_caches_are_isolated_per_il2cpp_instance():
    first = Il2Cpp(NS(typedefs=[]), NS())
    second = Il2Cpp(NS(typedefs=[]), NS())
    assert first._bases_cache is not second._bases_cache
    assert first._chain_cache is not second._chain_cache
    first._bases_cache[0] = (0,)
    first._chain_cache[0] = {16: ("value", 0)}
    assert second._bases_cache == {}
    assert second._chain_cache == {}


def test_object_parent_edge_reaches_unique_system_object():
    tds = [typedef(0, "Child", parent=0), typedef(1, "Object", "System")]
    il = bare_il(tds, [OBJECT])
    assert il.base_chain_tds(0) == (0, 1)
    assert il.td_of_ty(OBJECT) == 1


def test_class_and_object_parent_edges_form_complete_chain():
    tds = [typedef(0, "Child", parent=0), typedef(1, "Base", parent=1),
           typedef(2, "Object", "System")]
    il = bare_il(tds, [class_ty(1), OBJECT])
    assert il.base_chain_tds(0) == (0, 1, 2)


@pytest.mark.parametrize("objects", [[], [typedef(1, "Object", "Other")],
                                      [typedef(1, "Object", "System"),
                                       typedef(2, "Object", "System")]])
def test_object_edge_declines_without_one_canonical_system_object(objects):
    tds = [typedef(0, "Child", parent=0)] + objects
    il = bare_il(tds, [OBJECT])
    assert il.base_chain_tds(0) == (0,)
    assert il.td_of_ty(OBJECT) is None


def test_inheritance_cycle_stops_without_duplicate_typedefs():
    tds = [typedef(0, "A", parent=0), typedef(1, "B", parent=1)]
    il = bare_il(tds, [class_ty(1), class_ty(0)])
    assert il.base_chain_tds(0) == (0, 1)


def test_this_in_constructor_selects_unique_parameterless_ancestor_ctor():
    methods = [method(0, 1), method(1, 7, name="Run")]
    lift = make_lifter(methods)
    recv = Expr("this", class_ty(0), "obj")
    assert lift._shared_parameterless_ctor_target(
        [("method", 0), ("method", 1)], recv) == ("method", 0)


def test_fresh_allocation_selects_its_own_parameterless_ctor():
    methods = [method(0, 0), method(1, 7, name="Run")]
    lift = make_lifter(methods)
    assert lift._shared_parameterless_ctor_target(
        [("method", 0), ("method", 1)], fresh()) == ("method", 0)


def test_current_type_candidate_is_not_a_base_initializer_proof():
    lift = make_lifter([method(0, 0)])
    recv = Expr("this", class_ty(0), "obj")
    assert lift._shared_parameterless_ctor_target([("method", 0)], recv) is None


def test_two_matching_ancestor_ctors_remain_ambiguous():
    tds = [typedef(0, "Child"), typedef(1, "Base"), typedef(2, "Object", "System")]
    lift = make_lifter([method(0, 1), method(1, 2)], chain=(0, 1, 2), typedefs=tds)
    recv = Expr("this", class_ty(0), "obj")
    assert lift._shared_parameterless_ctor_target(
        [("method", 0), ("method", 1)], recv) is None


def test_matching_generic_ctor_blocks_false_concrete_uniqueness():
    methods = [method(0, 1)]
    lift = make_lifter(methods, method_specs=[(0, -1, -1)])
    recv = Expr("this", class_ty(0), "obj")
    assert lift._shared_parameterless_ctor_target(
        [("method", 0), ("generic", 0)], recv) is None


@pytest.mark.parametrize("change", ["parameter", "static", "nonvoid",
                                     "generic_method", "generic_owner"])
def test_inexact_constructor_abi_or_open_identity_declines(change):
    tds = [typedef(0, "Child"), typedef(1, "Base")]
    m = method(0, 1)
    if change == "parameter":
        m.param_count = 1
    elif change == "static":
        m.flags = 0x10
    elif change == "nonvoid":
        m.return_type = 1
    elif change == "generic_method":
        m.generic_container = 0
    else:
        tds[1].generic_container = 0
    lift = make_lifter([m], typedefs=tds)
    recv = Expr("this", class_ty(0), "obj")
    assert lift._shared_parameterless_ctor_target([("method", 0)], recv) is None


@pytest.mark.parametrize("recv", [
    Expr("this", None, "obj"),
    Expr("this", class_ty(0), "ptr"),
    Expr("this", class_ty(0, byref=True), "obj"),
    Expr("other", class_ty(0), "obj"),
    fresh("new Child(1)"),
])
def test_unproved_receiver_or_allocation_declines(recv):
    lift = make_lifter([method(0, 1)])
    assert lift._shared_parameterless_ctor_target([("method", 0)], recv) is None


def test_unknown_and_value_type_receivers_decline():
    lift = make_lifter([method(0, 1)])
    unknown = Expr("this", class_ty(0), "obj")
    unknown._unk = True
    assert lift._shared_parameterless_ctor_target([("method", 0)], unknown) is None
    lift.meta.typedefs[0].is_valuetype = True
    value = Expr("this", value_ty(0), "obj")
    assert lift._shared_parameterless_ctor_target([("method", 0)], value) is None


def test_this_is_not_constructor_evidence_outside_a_constructor():
    lift = make_lifter([method(0, 1)], caller_name="Run")
    recv = Expr("this", class_ty(0), "obj")
    assert lift._shared_parameterless_ctor_target([("method", 0)], recv) is None


def test_initializer_kind_distinguishes_this_base_and_unrelated_targets():
    tds = [typedef(0, "Child"), typedef(1, "Base"), typedef(2, "Ancestor"),
           typedef(3, "Other")]
    lift = make_lifter([], chain=(0, 1, 2), typedefs=tds)
    recv = Expr("this", class_ty(0), "obj")
    assert lift._constructor_initializer_kind(method(0, 0), recv) == "this"
    assert lift._constructor_initializer_kind(method(1, 1), recv) == "base"
    assert lift._constructor_initializer_kind(method(2, 2), recv) == "base"
    assert lift._constructor_initializer_kind(method(3, 3), recv) is None
    assert lift._constructor_initializer_kind(method(4, 1), Expr("other", class_ty(0), "obj")) is None


def completion_lifter(*, dry=False):
    lift = Lifter.__new__(Lifter)
    lift.il = NS()
    lift.out = []
    lift.var_n = 0
    lift._var_types = {}
    lift._gp_blocked = set()
    lift._cur_ip = 0x1234
    lift.dry = dry
    return lift


def test_unbound_fresh_allocation_is_completed_and_bound_once():
    lift = completion_lifter()
    recv = fresh()
    assert lift._complete_fresh_constructor(recv, ["name", "false"])
    assert recv.text == "t0" and recv._alloc is None
    assert lift.out == [(0x1234, "var t0 = new Child(name, false);", None)]
    assert lift._var_types["t0"] == class_ty(0)
    assert not lift._complete_fresh_constructor(recv, [])


def test_already_bound_fresh_allocation_patches_its_exact_declaration():
    lift = completion_lifter()
    recv = fresh()
    recv.text = "t0"
    recv._defpos = (None, 0)
    lift.out = [(0x1000, "var t0 = new Child();", None),
                (0x1005, "t0.field = 1;", None)]
    assert lift._complete_fresh_constructor(recv, ["value"])
    assert lift.out == [(0x1000, "var t0 = new Child(value);", None),
                        (0x1005, "t0.field = 1;", None)]
    assert recv.text == "t0" and recv._alloc is None


def test_missing_bound_declaration_does_not_guess_or_consume_provenance():
    lift = completion_lifter()
    recv = fresh()
    recv.text = "t0"
    lift.out = [(0x1000, "var t1 = new Child();", None)]
    assert not lift._complete_fresh_constructor(recv, ["value"])
    assert recv._alloc == "new Child()"


def test_dry_pass_tracks_same_temp_without_emitting_a_declaration():
    lift = completion_lifter(dry=True)
    recv = fresh()
    assert lift._complete_fresh_constructor(recv, ["value"])
    assert recv.text == "t0" and recv._alloc is None and lift.out == []


def test_expr_copy_keeps_allocation_identity_until_constructor_completion():
    recv = fresh()
    copy = Lifter._copy_expr(recv)
    assert copy is not recv and copy._alloc == "new Child()"


def test_constructor_pseudo_calls_promote_with_arguments():
    emitter = Emitter.__new__(Emitter)
    init, body = emitter._ctor_body(["this..ctor(name, false);", "this.value = name;", "return;"])
    assert init == "this(name, false)"
    assert body == ["this.value = name;"]


def test_legacy_shared_chain_keeps_object_only_for_an_object_receiver():
    tds = [typedef(0, "Child"), typedef(1, "Base"),
           typedef(2, "Object", "System")]
    lift = make_lifter([], chain=(0, 1, 2), typedefs=tds)
    lift.il._system_object_td = lambda: 2
    assert lift._legacy_shared_receiver_chain(0) == {0, 1}
    lift.il.base_chain_tds = lambda td: (2,)
    assert lift._legacy_shared_receiver_chain(2) == {2}
