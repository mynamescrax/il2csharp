"""A shared body's printed arguments follow the all-candidates slot classes.

`_call` bounds an ambiguous shared body's argument list by the largest
declared arity among its candidates (batch 21j). That bound fixes the COUNT
but not the LANE: the raw list is GPR-first with tracked XMM values appended,
so truncating it printed the stale RCX value where a float parameter lives
and dropped the real XMM argument (mi 20081's `Angle.op_Implicit` family at
0x182da54f0, the `mulss xmm0,xmm0` square leaf 0x1826e1660).
`_shared_slot_classes` proves every candidate agrees on the class of every
slot; `_shared_positional_args` rebuilds the list by ABI position.
Disagreement, a generic spec, or an unreadable row keeps the raw spelling.
"""
from types import SimpleNamespace as NS

from il2cpp import Expr, Lifter, MethodDef, ParamDef

VOID = (0, 0x01 << 16)
INT = (0, 0x08 << 16)
R4 = (0, 0x0c << 16)
R8 = (0, 0x0d << 16)
BYREF_R4 = (0, (0x0c << 16) | (1 << 29))
VALUETYPE = (0, 0x11 << 16)

T = 0x3000

PARAMS = {
    'i': ParamDef('i', 0, 1),
    'f': ParamDef('f', 0, 2),
    'd': ParamDef('d', 0, 3),
    'brf': ParamDef('brf', 0, 4),
    'vt': ParamDef('vt', 0, 5),
}


def _lifter(specs, cands, sret_type=None):
    """Lifter with just the metadata the two helpers read.

    `specs` is a list of (param name tuple, static, return type index).
    """
    params = []
    methods = []
    for i, (ps, static, rt) in enumerate(specs):
        start = len(params)
        params.extend(PARAMS[p] for p in ps)
        methods.append(MethodDef(i, 'M%d' % i, 0, rt, start, -1, 0,
                                 0x10 if static else 0, 0, 0, len(ps)))

    def method_params(m):
        return params[m.parameter_start:m.parameter_start + m.param_count]

    lift = Lifter.__new__(Lifter)
    lift.meta = NS(methods=methods, params=params, method_params=method_params)
    lift.il = NS(
        addr_candidates={T: list(cands)},
        addr_to_method={},
        types=[VOID, INT, R4, R8, BYREF_R4, VALUETYPE],
        method_specs=[],
        returns_sret=lambda t: t == sret_type,
    )
    lift._xmm_pending = []
    return lift


C1 = [('method', 0), ('method', 1)]


# ---------------------------------------------------------------- classes


def test_classes_single_float_parameter():
    lift = _lifter([(('f',), True, 1), (('f',), True, 1)], C1)
    assert lift._shared_slot_classes(C1) == 'x'


def test_classes_counts_the_instance_receiver():
    lift = _lifter([(('f',), False, 1), (('f',), False, 1)], C1)
    assert lift._shared_slot_classes(C1) == 'gx'


def test_classes_counts_the_hidden_sret_buffer():
    lift = _lifter([(('f',), True, 5), (('f',), True, 5)], C1, sret_type=VALUETYPE)
    # with the all-candidates consensus the buffer is provable ...
    assert lift._shared_slot_classes(C1, VALUETYPE) == 'gx'
    # ... and each candidate's own value-type return classifies the same
    assert lift._shared_slot_classes(C1) == 'gx'


def test_classes_byref_float_is_a_gpr_slot():
    # a byref float is an address: pointer-class even though its pointee
    # is R4 (mirrors _positional_args / fix 53)
    lift = _lifter([(('brf',), True, 1), (('brf',), True, 1)], C1)
    assert lift._shared_slot_classes(C1) == 'g'


def test_classes_reads_double_as_xmm():
    lift = _lifter([(('d',), True, 1), (('d',), True, 1)], C1)
    assert lift._shared_slot_classes(C1) == 'x'


def test_classes_declines_on_disagreement():
    lift = _lifter([(('f',), True, 1), (('i',), True, 1)], C1)
    assert lift._shared_slot_classes(C1) is None


def test_classes_declines_a_generic_candidate():
    lift = _lifter([(('f',), True, 1)], [('method', 0), ('generic', 0)])
    assert lift._shared_slot_classes([('method', 0), ('generic', 0)]) is None


def test_classes_declines_an_unreadable_row():
    lift = _lifter([(('f',), True, 1)], [('method', 0), ('method', 9)])
    assert lift._shared_slot_classes([('method', 0), ('method', 9)]) is None


def test_classes_declines_an_out_of_range_param_type():
    lift = _lifter([(('f',), True, 1)], [('method', 0)])
    lift.meta.methods[0] = MethodDef(0, 'M0', 0, 1, 0, -1, 0, 0x10, 0, 0, 1)
    lift.meta.params[:] = [ParamDef('bad', 0, 99)]
    assert lift._shared_slot_classes([('method', 0)]) is None


def test_classes_declines_empty_candidates():
    lift = _lifter([], [])
    assert lift._shared_slot_classes([]) is None
    assert lift._shared_slot_classes(None) is None


# ------------------------------------------------------------ positional


def test_positional_takes_the_float_from_the_xmm_lane():
    lift = _lifter([], [])
    lift._xmm_pending = [(0, Expr('0f', R4, 'float'))]
    # the raw list is GPR-first: truncating it to one slot keeps 'obj1'
    assert lift._shared_positional_args(['obj1', '0f'], 'x') == ['0f']


def test_positional_keeps_gpr_positions_and_replaces_only_floats():
    lift = _lifter([], [])
    lift._xmm_pending = [(1, Expr('real2', R4, 'float'))]
    assert lift._shared_positional_args(
        ['this', 'stale', '_', '_'], 'gx') == ['this', 'real2']


def test_positional_prints_placeholder_for_untracked_lanes():
    lift = _lifter([], [])
    assert lift._shared_positional_args(['this'], 'gx') == ['this', '_']
    assert lift._shared_positional_args([], 'x') == ['_']


def test_positional_matches_the_xmm_ordinal_not_the_order():
    lift = _lifter([], [])
    lift._xmm_pending = [(1, Expr('v1', R4, 'float')),
                         (0, Expr('v0', R8, 'float'))]
    assert lift._shared_positional_args(['a', 'b'], 'x') == ['v0']
    assert lift._shared_positional_args(['a', 'b'], 'gx') == ['a', 'v1']
