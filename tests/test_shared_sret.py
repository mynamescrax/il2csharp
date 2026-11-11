"""Exact pointee and common-ABI proofs for shared struct-return calls."""
from types import SimpleNamespace as NS

import pytest

from il2cpp import Expr, Lifter, MethodDef, ParamDef

INT = (0, 0x08 << 16)
VECTOR = (0, 0x11 << 16)
HIT = (1, 0x11 << 16)
RAY = (2, 0x11 << 16)
INT_PTR = (0x5000, 0x0F << 16)
VOID_PTR = (0x6000, 0x0F << 16)
GENERIC = (0x7000, 0x15 << 16)


def setup():
    lift = Lifter.__new__(Lifter)
    methods = [
        MethodDef(0, "get_point", 1, 0, 0, -1, 1, 0, 0, 0, 0),
        MethodDef(1, "get_origin", 2, 0, 0, -1, 2, 0, 0, 0, 0),
        MethodDef(2, "ReadVector", 3, 0, 0, -1, 3, 0x10, 0, 0, 1),
    ]
    lift.meta = NS(
        methods=methods,
        typedefs=[NS(is_valuetype=i != 3, generic_container=-1) for i in range(4)],
        method_params=lambda m: [ParamDef("source", 0, 1)] if m.is_static else [],
    )
    lift.il = NS(
        types=[VECTOR, INT_PTR],
        _type_enum=lambda t: (t[1] >> 16) & 0xFF if t else 0,
        returns_sret=lambda t: t == VECTOR,
        value_type_size=lambda td: 12 if td == 0 else None,
        type_from_ptr=lambda p: INT if p == INT_PTR[0] else (0, 0x01 << 16),
    )
    lift.slot_types, lift._type_hints = {}, {}
    args = [Expr("&s_20", None, "ptr"), Expr("&hit", HIT, "ptr")]
    return lift, [("method", i) for i in range(3)], args


def test_rdx_receiver_not_rcx_buffer_selects_the_owner():
    lift, cands, args = setup()
    args[0].ty = RAY  # buffer type must never choose get_origin
    assert lift._shared_sret_receiver_target(cands, args) == ("method", 0)


def test_stack_lea_uses_real_pointee_metadata():
    lift, cands, args = setup()
    args[1] = Expr("&s_80", None, "ptr")
    lift.slot_types["s_80"] = HIT
    lift._type_hints["s_80"] = (HIT[0], HIT[1] | 6)
    assert lift._shared_sret_receiver_target(cands, args) == ("method", 0)


def test_static_pointer_owner_can_be_uniquely_proven_too():
    lift, cands, args = setup()
    args[1] = Expr("&value", INT, "ptr")
    assert lift._shared_sret_receiver_target(cands, args) == ("method", 2)


def test_byref_bit_and_field_attributes_do_not_change_pointee_identity():
    lift, cands, args = setup()
    args[1].ty = (HIT[0], HIT[1] | 6 | (1 << 29))
    assert lift._shared_sret_receiver_target(cands, args) == ("method", 0)


@pytest.mark.parametrize("which", [0, 1])
def test_unwritten_argument_is_not_proof(which):
    lift, cands, args = setup()
    args[which]._unk = True
    assert lift._shared_sret_receiver_target(cands, args) is None


@pytest.mark.parametrize("which", [0, 1])
@pytest.mark.parametrize("text", ["unknown", "value", "&a + 8", "&data_1000"])
def test_only_concrete_address_taken_lvalues_are_accepted(which, text):
    lift, cands, args = setup()
    args[which].text = text
    assert lift._shared_sret_receiver_target(cands, args) is None


def test_unknown_receiver_not_inferred_from_return_buffer():
    lift, cands, args = setup()
    args[0].ty, args[1].ty = HIT, None
    assert lift._shared_sret_receiver_target(cands, args) is None


def test_conflicting_slot_and_expression_types_remain_unresolved():
    lift, cands, args = setup()
    lift.slot_types["hit"] = RAY
    assert lift._shared_sret_receiver_target(cands, args) is None


def test_duplicate_receiver_owner_is_ambiguous():
    lift, cands, args = setup()
    lift.meta.methods[1].declaring = 1
    assert lift._shared_sret_receiver_target(cands, args) is None


@pytest.mark.parametrize("which", [0, 1, 2])
def test_every_candidate_must_have_the_proven_sret_abi(which):
    lift, cands, args = setup()
    lift.il.types.append(INT)
    lift.meta.methods[which].return_type = 2
    assert lift._shared_sret_receiver_target(cands, args) is None


def test_unknown_size_is_not_sret_proof():
    lift, cands, args = setup()
    lift.il.value_type_size = lambda td: None
    assert lift._shared_sret_receiver_target(cands, args) is None


def test_differently_sized_return_buffers_are_not_one_abi():
    lift, cands, args = setup()
    lift.il.types.append(RAY)
    lift.meta.methods[1].return_type = 2
    lift.il.returns_sret = lambda ty: True
    lift.il.value_type_size = lambda td: 12 if td == 0 else 24
    assert lift._shared_sret_receiver_target(cands, args) is None


@pytest.mark.parametrize("kind", ["owner", "method", "registered"])
def test_generic_candidate_cannot_create_false_uniqueness(kind):
    lift, cands, args = setup()
    if kind == "owner":
        lift.meta.typedefs[2].generic_container = 0
    elif kind == "method":
        lift.meta.methods[1].generic_container = 0
    else:
        cands.append(("generic", 0))
    assert lift._shared_sret_receiver_target(cands, args) is None


@pytest.mark.parametrize("pt", [INT, VOID_PTR, GENERIC])
def test_static_by_value_or_opaque_parameter_is_not_a_pointer_proof(pt):
    lift, cands, args = setup()
    lift.il.types[1] = pt
    assert lift._shared_sret_receiver_target(cands, args) is None


def test_instance_with_additional_parameters_stays_unresolved():
    lift, cands, args = setup()
    lift.meta.methods[1].param_count = 1
    assert lift._shared_sret_receiver_target(cands, args) is None


def test_static_byref_parameter_uses_pointee_identity():
    lift, cands, args = setup()
    lift.il.types[1] = (INT[0], INT[1] | (1 << 29))
    args[1] = Expr("&value", INT, "ptr")
    assert lift._shared_sret_receiver_target(cands, args) == ("method", 2)
