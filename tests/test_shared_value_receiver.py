"""Exact value-type pointees can identify folded instance getters."""
from types import SimpleNamespace as NS

from il2cpp import Expr, Lifter, MethodDef, ParamDef


VALUE = (1, 0x11 << 16)
OTHER = (2, 0x11 << 16)
INT = (0, 0x08 << 16)


def setup():
    lift = Lifter.__new__(Lifter)
    lift.meta = NS(
        methods=[
            MethodDef(0, 'get_value', 1, 0, 0, -1, 0, 0, 0, 0, 0),
            MethodDef(1, 'get_value', 2, 0, 0, -1, 0, 0, 0, 0, 0),
            MethodDef(2, 'get_other', 1, 0, 0, -1, 0, 0, 0, 0, 0),
        ],
        typedefs=[NS(is_valuetype=False, generic_container=-1),
                  NS(is_valuetype=True, generic_container=-1),
                  NS(is_valuetype=True, generic_container=-1)],
    )
    lift.il = NS(
        types=[INT], method_specs=[(2, -1, -1)],
        _type_enum=lambda ty: (ty[1] >> 16) & 0xff,
        returns_sret=lambda ty: False,
        candidate_return_type=lambda candidate: INT,
    )
    lift.slot_types = {'s_8': VALUE}
    lift._type_hints = {'s_8': VALUE}
    return lift, [('method', 0), ('method', 1)], Expr('&s_8', None, 'ptr')


def test_exact_stack_pointee_selects_one_owner():
    lift, candidates, recv = setup()
    assert lift._shared_value_receiver_target(candidates, recv) == ('method', 0)


def test_conflicting_or_missing_pointee_declines():
    lift, candidates, recv = setup()
    lift._type_hints['s_8'] = OTHER
    assert lift._shared_value_receiver_target(candidates, recv) is None
    lift._type_hints.clear()
    lift.slot_types.clear()
    assert lift._shared_value_receiver_target(candidates, recv) is None


def test_second_method_on_same_type_blocks_identity():
    lift, candidates, recv = setup()
    assert lift._shared_value_receiver_target(
        candidates + [('method', 2)], recv) is None


def test_static_or_sret_candidate_blocks_receiver_proof():
    lift, candidates, recv = setup()
    lift.meta.methods[1].flags |= 0x10
    assert lift._shared_value_receiver_target(candidates, recv) is None
    lift.meta.methods[1].flags &= ~0x10
    lift.il.returns_sret = lambda ty: True
    assert lift._shared_value_receiver_target(candidates, recv) is None


def test_generic_candidate_on_same_type_blocks_identity():
    lift, candidates, recv = setup()
    assert lift._shared_value_receiver_target(
        candidates + [('generic', 0)], recv) is None


def test_integer_argument_to_closed_enum_keeps_explicit_cast():
    lift, _, _ = setup()
    enum = (1, 0x11 << 16)
    lift.meta.methods = [MethodDef(0, 'Use', 0, 0, 0, -1, 0, 0x10, 0, 0, 1)]
    lift.meta.typedefs[1].is_enum = True
    lift.meta.method_params = lambda method: [ParamDef('value', 0, 1)]
    lift.il.types = [INT, enum]
    lift.il.enum_members = lambda td: None
    lift.il.type_name = lambda ty: 'Mode'
    lift._call_class_args = None
    lift._type_hints = {}
    lift._xmm_pending = []
    args = ['obj.value']
    lift._hint_arg_types(args, [Expr('obj.value', INT, 'int')], 0, INT)
    assert args == ['(Mode)(obj.value)']
