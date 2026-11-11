"""A native mov-rcx-to-rax leaf can replace a shared call by a copy."""
from types import SimpleNamespace as NS

from il2cpp import Expr, Lifter


VA = 0x1234
CANDS = [('method', 0), ('generic', 1)]


def setup(code=b'\x48\x8b\xc1\xc3'):
    lift = Lifter.__new__(Lifter)
    lift.bin = NS(is_exec_va=lambda va: va == VA,
                  read=lambda va, n: code[:n])
    return lift


def test_exact_native_leaf_and_pure_registers_return_rcx():
    lift = setup()
    value = Expr('this.type', None, 'obj')
    args = [value, Expr('0', None, 'int'), None, None]
    assert lift._shared_identity_value(VA, CANDS, args, []) is value


def test_near_match_or_single_owner_declines():
    value = Expr('this.type', None, 'obj')
    args = [value, Expr('0', None, 'int')]
    assert setup(b'\x48\x8b\xc1\x90')._shared_identity_value(
        VA, CANDS, args, []) is None
    assert setup()._shared_identity_value(VA, CANDS[:1], args, []) is None


def test_side_effecting_or_unknown_inputs_decline():
    lift = setup()
    value = Expr('graph.GetType()', None, 'obj')
    assert lift._shared_identity_value(
        VA, CANDS, [value, Expr('0', None, 'int')], []) is None
    value = Expr('this.type', None, 'obj')
    assert lift._shared_identity_value(
        VA, CANDS, [value, Expr('DoWork()', None, 'obj')], []) is None
    assert lift._shared_identity_value(
        VA, CANDS, [value], [(0, Expr('DoWork()', None, 'obj'))]) is None
    value._unk = True
    assert lift._shared_identity_value(VA, CANDS, [value], []) is None


def test_address_and_float_values_decline():
    lift = setup()
    for value in (Expr('&s_8', None, 'ptr'), Expr('real1', None, 'float')):
        assert lift._shared_identity_value(VA, CANDS, [value], []) is None
