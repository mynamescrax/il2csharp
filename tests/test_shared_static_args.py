"""Do not guess a shared function unless argument identity and ABI agree."""
from types import SimpleNamespace as NS

import pytest

from il2cpp import Expr, Lifter, MethodDef, ParamDef

INT = (0, 0x08 << 16)
UINT = (0, 0x09 << 16)
FLOAT = (0, 0x0C << 16)
MASK = (0, 0x11 << 16)
OTHER_MASK = (1, 0x11 << 16)
GENERIC = (0x1000, 0x15 << 16)


def setup(params=(MASK, OTHER_MASK, INT), returns=None):
    returns = returns or [INT] * len(params)
    types = list(params) + list(returns)
    methods = [MethodDef(i, 'op_Implicit', 0, len(params)+i, i, -1,
                         1, 0x10, 0, 0, 1) for i in range(len(params))]
    lift = Lifter.__new__(Lifter)
    lift.meta = NS(methods=methods,
                   typedefs=[NS(is_valuetype=True), NS(is_valuetype=True)],
                   method_params=lambda m: [ParamDef('value', 0, m.index)])
    lift.il = NS(types=types, _type_enum=lambda ty: (ty[1] >> 16) & 0xFF,
                 returns_sret=lambda ty: False)
    cands = [('method', m.index) for m in methods]
    return lift, cands


def test_unique_struct_parameter_selects_the_real_conversion():
    lift, cands = setup()
    assert lift._shared_static_arg_target(cands, [Expr('mask', MASK, 'obj')]) == ('method', 0)


def test_field_attributes_do_not_change_type_identity():
    lift, cands = setup()
    field_type = (MASK[0], MASK[1] | 6)
    assert lift._shared_static_arg_target(cands, [Expr('this.mask', field_type, 'obj')]) == ('method', 0)


def test_multiple_methods_with_the_same_parameter_remain_ambiguous():
    lift, cands = setup((MASK, MASK, INT))
    assert lift._shared_static_arg_target(cands, [Expr('mask', MASK, 'obj')]) is None


@pytest.mark.parametrize('actual', [
    Expr('mask', None, 'obj'), Expr('value', INT, 'int'),
    Expr('&mask', MASK, 'ptr'), Expr('type', MASK, 'klass'),
    Expr('mask', (MASK[0], MASK[1] | (1 << 29)), 'ptr'),
])
def test_insufficient_or_address_evidence_is_not_a_proof(actual):
    lift, cands = setup()
    assert lift._shared_static_arg_target(cands, [actual]) is None


def test_entry_seed_is_not_argument_evidence():
    lift, cands = setup()
    actual = Expr('v1', MASK, 'obj'); actual._unk = True
    assert lift._shared_static_arg_target(cands, [actual]) is None


@pytest.mark.parametrize('bad', [FLOAT, GENERIC, (0x1234, 0x0F << 16), (0, 0x12 << 16),
                                 (0, (0x08 << 16) | (1 << 29))])
def test_different_parameter_abi_keeps_the_marker(bad):
    lift, cands = setup((MASK, bad))
    assert lift._shared_static_arg_target(cands, [Expr('mask', MASK, 'obj')]) is None


def test_instance_candidate_cannot_be_rejected_using_a_static_argument():
    lift, cands = setup()
    lift.meta.methods[1].flags = 0
    assert lift._shared_static_arg_target(cands, [Expr('mask', MASK, 'obj')]) is None


def test_hidden_sret_buffer_cannot_be_mistaken_for_an_argument():
    lift, cands = setup(returns=[INT, MASK, INT])
    lift.il.returns_sret = lambda ty: ty == MASK
    assert lift._shared_static_arg_target(cands, [Expr('mask', MASK, 'obj')]) is None


def test_generic_owner_prevents_false_uniqueness():
    lift, cands = setup()
    cands.append(('generic', 0))
    assert lift._shared_static_arg_target(cands, [Expr('mask', MASK, 'obj')]) is None


def test_two_argument_candidate_requires_its_own_proof():
    lift, cands = setup()
    lift.meta.methods[1].param_count = 2
    assert lift._shared_static_arg_target(cands, [Expr('mask', MASK, 'obj')]) is None
