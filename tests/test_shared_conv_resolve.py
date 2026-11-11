"""Unanimous conversion families resolve at caller-proven casts.

A shared address whose every candidate is the same static one-parameter
conversion (op_Implicit/op_Explicit) with distinct returns executes
identical machine code, so `(T)sub_X/*shared*/(arg)` with T naming
exactly one return renders `T.op_Implicit(arg)`. Ground truth: the
Angle/StyleFloat/TimeValue triple at 0x182da54f0 (game pins in
tests/test_game_op_implicit.py).
"""
from types import SimpleNamespace as NS

from il2cpp import Decompiler

FT = (0, 0x0C << 16)
RA = (1, 0x11 << 16)
RB = (2, 0x11 << 16)
RC = (3, 0x11 << 16)
NAMES = {FT: 'float', RA: 'Ns.Angle', RB: 'Ns.StyleFloat', RC: 'Ns.TimeValue'}


def make_dec(cands, ret_names, param_same=True):
    types = [FT, RA, RB, RC]
    tds = [NS(namespace='Ns', name=n.split('.')[-1]) for n in
           ['Ns.Angle', 'Ns.StyleFloat', 'Ns.TimeValue']]
    td_by_ret = {'Ns.Angle': 0, 'Ns.StyleFloat': 1, 'Ns.TimeValue': 2}
    methods = []
    name2idx = {'Ns.Angle': 1, 'Ns.StyleFloat': 2, 'Ns.TimeValue': 3}
    for i, (kind, rn) in enumerate(zip(cands, ret_names)):
        methods.append(NS(name='op_Implicit', is_static=True,
                          param_count=1, generic_container=-1,
                          return_type=name2idx[rn], declaring=td_by_ret[rn]))
    il = NS(addr_candidates={0x1000: [(k, i) for i, k in enumerate(cands)]},
            types=types,
            type_name=lambda t: NAMES[t],
            returns_sret=lambda rt: False)
    meta = NS(methods=methods, typedefs=tds,
              method_params=lambda m: [NS(type=0)])
    d = Decompiler.__new__(Decompiler)
    d.L = NS(il=il, meta=meta)
    return d


def run(d, lines):
    return d._shared_conv_resolve(list(lines), None)


DECL = 'float real2 = real1 * 2.0f;'


def test_fire_angle():
    d = make_dec(['method'] * 3,
                 ['Ns.Angle', 'Ns.StyleFloat', 'Ns.TimeValue'])
    out = run(d, [DECL,
                  'Ns.Angle angle1 = (Ns.Angle)sub_1000/*shared body, 3 candidates*/(real2);'])
    assert out[1] == 'Ns.Angle angle1 = Ns.Angle.op_Implicit(real2);'


def test_fire_literal():
    d = make_dec(['method'] * 3,
                 ['Ns.Angle', 'Ns.StyleFloat', 'Ns.TimeValue'])
    out = run(d, ['Ns.StyleFloat s = (Ns.StyleFloat)sub_1000/*shared body, 3 candidates*/(0f);'])
    assert out[0] == 'Ns.StyleFloat s = Ns.StyleFloat.op_Implicit(0f);'


def test_fire_complex_arg():
    d = make_dec(['method'] * 3,
                 ['Ns.Angle', 'Ns.StyleFloat', 'Ns.TimeValue'])
    out = run(d, [DECL,
                  'Ns.Angle a = (Ns.Angle)sub_1000/*shared body, 3 candidates*/((x - real1) * t + real1);'])
    assert out[1] == 'Ns.Angle a = Ns.Angle.op_Implicit((x - real1) * t + real1);'


def test_decline_unmatched_cast():
    d = make_dec(['method'] * 2, ['Ns.Angle', 'Ns.StyleFloat'])
    line = 'Ns.TimeValue v = (Ns.TimeValue)sub_1000/*shared body, 2 candidates*/(real2);'
    assert run(d, [DECL, line])[1] == line


def test_decline_duplicate_returns():
    d = make_dec(['method'] * 2, ['Ns.Angle', 'Ns.Angle'])
    line = 'Ns.Angle a = (Ns.Angle)sub_1000/*shared body, 2 candidates*/(real2);'
    assert run(d, [DECL, line])[1] == line


def test_decline_generic_sharer():
    d = make_dec(['generic', 'method', 'method'],
                 ['Ns.Angle', 'Ns.StyleFloat', 'Ns.TimeValue'])
    line = 'Ns.Angle a = (Ns.Angle)sub_1000/*shared body, 3 candidates*/(real2);'
    assert run(d, [DECL, line])[1] == line


def test_decline_bare_object_arg():
    d = make_dec(['method'] * 3,
                 ['Ns.Angle', 'Ns.StyleFloat', 'Ns.TimeValue'])
    lines = ['object obj1 = foo();',
             'Ns.Angle a = (Ns.Angle)sub_1000/*shared body, 3 candidates*/(obj1);']
    assert run(d, lines)[1] == lines[1]


def test_decline_unknown_bare_arg():
    d = make_dec(['method'] * 3,
                 ['Ns.Angle', 'Ns.StyleFloat', 'Ns.TimeValue'])
    line = 'Ns.Angle a = (Ns.Angle)sub_1000/*shared body, 3 candidates*/(mystery);'
    assert run(d, [line])[0] == line


def test_decline_double_literal():
    d = make_dec(['method'] * 3,
                 ['Ns.Angle', 'Ns.StyleFloat', 'Ns.TimeValue'])
    line = 'Ns.Angle a = (Ns.Angle)sub_1000/*shared body, 3 candidates*/(1.0);'
    assert run(d, [line])[0] == line


def test_decline_multi_arg():
    d = make_dec(['method'] * 3,
                 ['Ns.Angle', 'Ns.StyleFloat', 'Ns.TimeValue'])
    line = 'Ns.Angle a = (Ns.Angle)sub_1000/*shared body, 3 candidates*/(real2, real2);'
    assert run(d, [DECL, line])[1] == line


def test_decline_no_marker():
    d = make_dec(['method'] * 3,
                 ['Ns.Angle', 'Ns.StyleFloat', 'Ns.TimeValue'])
    line = 'Ns.Angle a = (Ns.Angle)sub_1000(real2);'
    assert run(d, [DECL, line])[1] == line


def test_decline_bang_prefix():
    d = make_dec(['method'] * 3,
                 ['Ns.Angle', 'Ns.StyleFloat', 'Ns.TimeValue'])
    line = 'if (!(Ns.Angle)sub_1000/*shared body, 3 candidates*/(real2)) {}'
    assert run(d, [DECL, line])[1] == line


def test_decline_literal_text():
    d = make_dec(['method'] * 3,
                 ['Ns.Angle', 'Ns.StyleFloat', 'Ns.TimeValue'])
    line = 'string s = "(Ns.Angle)sub_1000(real2)";'
    assert run(d, [line])[0] == line


def test_arg_ok_units():
    d = make_dec(['method'] * 3,
                 ['Ns.Angle', 'Ns.StyleFloat', 'Ns.TimeValue'])
    ok = d._shared_conv_arg_ok
    assert ok('real2', {'real2': 'float'})
    assert ok('num1', {'num1': 'int'})
    assert ok('0f', {}) and ok('0', {}) and ok('0x10', {})
    assert not ok('obj1', {'obj1': 'object'})
    assert not ok('mystery', {})
    assert not ok('1.0', {}) and not ok('', {})
    assert ok('(a - b) * t', {})
