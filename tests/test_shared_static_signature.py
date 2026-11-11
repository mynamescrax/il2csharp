"""Typed operands select static shared owners only with a common ABI."""
from types import SimpleNamespace as NS

from il2cpp import Expr, Lifter, MethodDef, ParamDef


BOOL = (0, 0x02 << 16)
TYPE = (1, 0x12 << 16)
RUNTIME_TYPE = (2, 0x12 << 16)
TIME_SPAN = (3, 0x11 << 16)
LONG = (0, 0x0a << 16)


def setup():
    lift = Lifter.__new__(Lifter)
    lift.meta = NS(
        methods=[MethodDef(i, 'op_Inequality', i + 1, 0, 0, -1,
                           0, 0x10, 0, 0, 2) for i in range(3)],
        typedefs=[NS(flags=0) for _ in range(4)],
        method_params=lambda m: [ParamDef('a', 0, m.index + 1 if m.index < 3 else 1),
                                 ParamDef('b', 0, m.index + 1 if m.index < 3 else 1)],
    )
    lift.il = NS(
        types=[BOOL, TYPE, RUNTIME_TYPE, TIME_SPAN],
        _type_enum=lambda ty: (ty[1] >> 16) & 0xff,
        returns_sret=lambda ty: False,
        base_chain_tds=lambda td: (2, 1) if td == 2 else (td,),
    )
    return lift, [('method', i) for i in range(3)]


def test_type_argument_selects_type_operator():
    lift, cands = setup()
    args = [Expr('unknown', None, '?'), Expr('type', TYPE, 'obj')]
    assert lift._shared_static_signature_target(cands, args) == ('method', 0)


def test_derived_type_may_bind_base_or_derived_operator():
    lift, cands = setup()
    args = [Expr('unknown', None, '?'), Expr('runtimeType', RUNTIME_TYPE, 'obj')]
    assert lift._shared_static_signature_target(cands, args) is None


def test_typed_integer_operand_conflicts_with_timespan_signature():
    lift, cands = setup()
    args = [Expr('offset._ticks', LONG, 'int'),
            Expr('nullOffset', TIME_SPAN, 'obj')]
    assert lift._shared_static_signature_target(cands, args) is None


def test_two_identical_signatures_remain_ambiguous():
    lift, cands = setup()
    lift.meta.methods.append(MethodDef(3, 'Equals', 1, 0, 0, -1,
                                       0, 0x10, 0, 0, 2))
    args = [Expr('unknown', None, '?'), Expr('type', TYPE, 'obj')]
    assert lift._shared_static_signature_target(
        cands + [('method', 3)], args) is None


def test_incompatible_candidate_abi_declines():
    lift, cands = setup()
    args = [Expr('unknown', None, '?'), Expr('type', TYPE, 'obj')]
    lift.meta.methods[2].flags = 0
    assert lift._shared_static_signature_target(cands, args) is None


def test_stale_typed_register_beyond_arity_declines():
    lift, cands = setup()
    args = [Expr('unknown', None, '?'), Expr('type', TYPE, 'obj'),
            Expr('stale', TIME_SPAN, 'obj')]
    assert lift._shared_static_signature_target(cands, args) is None


def test_object_or_interface_candidate_blocks_exact_class_selection():
    lift, cands = setup()
    args = [Expr('unknown', None, '?'), Expr('type', TYPE, 'obj')]
    lift.il.types.append((0, 0x1c << 16))
    lift.meta.methods.append(MethodDef(3, 'Equals', 0, 0, 0, -1,
                                       0, 0x10, 0, 0, 2))
    lift.meta.method_params = lambda m: [ParamDef('a', 0, 4),
                                         ParamDef('b', 0, 4)] if m.index == 3 else [
                                             ParamDef('a', 0, m.index + 1),
                                             ParamDef('b', 0, m.index + 1)]
    assert lift._shared_static_signature_target(
        cands + [('method', 3)], args) is None
    lift.il.types[4] = TYPE
    lift.meta.typedefs[1].flags = 0x20
    assert lift._shared_static_signature_target(cands, args) is None
    lift.meta.typedefs[1].flags = 0
    lift.il._system_object_td = lambda: 1
    assert lift._shared_static_signature_target(cands, args) is None
