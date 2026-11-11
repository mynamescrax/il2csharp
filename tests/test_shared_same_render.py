"""Identical-render shared bodies collapse without guessing identity."""
from types import SimpleNamespace as NS

from il2cpp import Expr, Lifter, MethodDef, ParamDef


INT = (0, 0x08 << 16)
STRING = (1, 0x0e << 16)


def make_lifter(methods, typedefs, types, params_of):
    lift = Lifter.__new__(Lifter)
    lift.meta = NS(methods=methods, typedefs=typedefs,
                   method_params=params_of)
    lift.il = NS(types=types, returns_sret=lambda ty: False)
    return lift


def setup_twins():
    tds = [NS(namespace='', name='Kernel', flags=0),
           NS(namespace='', name='Kernel', flags=0)]
    methods = [MethodDef(0, 'Multiply', 0, 0, 0, -1, 0, 0x10, 0, 0, 1),
               MethodDef(1, 'Multiply', 1, 0, 0, -1, 0, 0x10, 0, 0, 1)]
    lift = make_lifter(methods, tds, [INT],
                       lambda m: [ParamDef('a', 0, 0)])
    return lift, [('method', 0), ('method', 1)]


def test_identical_twins_collapse_to_first():
    lift, cands = setup_twins()
    assert lift._shared_same_render_target(cands) == ('method', 0)


def test_different_owner_names_decline():
    lift, cands = setup_twins()
    lift.meta.typedefs[1] = NS(namespace='', name='Other', flags=0)
    assert lift._shared_same_render_target(cands) is None


def test_different_param_types_decline():
    lift, cands = setup_twins()
    lift.il.types.append(STRING)
    lift.meta.method_params = lambda m: [ParamDef('a', 0, m.index)]
    assert lift._shared_same_render_target(cands) is None


def test_ctor_declines():
    lift, cands = setup_twins()
    lift.meta.methods[0] = MethodDef(0, '.ctor', 0, 0, 0, -1,
                                     0, 0, 0, 0, 1)
    lift.meta.methods[1] = MethodDef(1, '.ctor', 1, 0, 0, -1,
                                     0, 0, 0, 0, 1)
    assert lift._shared_same_render_target(cands) is None


def test_generic_kind_declines():
    lift, cands = setup_twins()
    assert lift._shared_same_render_target(
        [('method', 0), ('generic', 7)]) is None


def test_sret_return_declines():
    lift, cands = setup_twins()
    lift.il.returns_sret = lambda ty: True
    assert lift._shared_same_render_target(cands) is None


def test_single_candidate_declines():
    lift, cands = setup_twins()
    assert lift._shared_same_render_target(cands[:1]) is None
