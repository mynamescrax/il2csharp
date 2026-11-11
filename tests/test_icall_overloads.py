"""icall annotations pick the overload the runtime signature names.

The old scan returned the first same-named metadata row, so
`UnityEngine.Object::FindObjectsOfType(System.Type,System.Boolean)` seated
the one-parameter overload and `_call` trimmed the real second argument
away. The runtime's own resolve string carries the exact parameter list;
`_icall_sig_params` tokenizes it and `_icall_pick_overload` settles an
overload set by unique arity, or -- among same-arity candidates -- by
normalized parameter types. Ambiguity declines to the text-only
annotation instead of guessing an identity.
"""
from types import SimpleNamespace as NS

from il2cpp import Il2Cpp, MethodDef, ParamDef

INT = (0, 0x08 << 16)
BYREF_INT = (0, (0x08 << 16) | (1 << 29))
R4 = (0, 0x0c << 16)
STRING = (0, 0x0e << 16)


def _il(specs, types, names):
    """Il2Cpp facade with just what the icall helpers read.

    `specs` is a list of (param type index tuple, static).
    """
    params = []
    methods = []
    for i, (ps, static) in enumerate(specs):
        start = len(params)
        params.extend(ParamDef('p%d' % k, 0, t) for k, t in enumerate(ps))
        methods.append(MethodDef(i, 'M%d' % i, 0, 1, start, -1, 0,
                                 0x10 if static else 0, 0, 0, len(ps)))

    def method_params(m):
        return params[m.parameter_start:m.parameter_start + m.param_count]

    il = Il2Cpp.__new__(Il2Cpp)
    il.meta = NS(methods=methods, method_params=method_params)
    il.types = types
    il.type_name = lambda ty: names.get(ty, '?')
    return il


# ------------------------------------------------------- signature split


def test_sig_params_simple():
    assert Il2Cpp._icall_sig_params('A.B::C(System.Type,System.Boolean)') == \
        ['System.Type', 'System.Boolean']


def test_sig_params_respects_generic_nesting():
    sig = ('X::M(System.Action`6<UnityEngine.Object[],System.IntPtr,'
           'System.Int32,System.Int32,System.Action`1<Y>>,System.Boolean)')
    assert Il2Cpp._icall_sig_params(sig) == [
        'System.Action`6<UnityEngine.Object[],System.IntPtr,System.Int32,'
        'System.Int32,System.Action`1<Y>>',
        'System.Boolean']


def test_sig_params_empty_and_unparseable():
    assert Il2Cpp._icall_sig_params('A.B::C()') == []
    assert Il2Cpp._icall_sig_params('A.B::C') is None
    assert Il2Cpp._icall_sig_params('A.B::C(System.Type') is None


# ------------------------------------------------------------- type key


def _key(text, byref=False):
    return Il2Cpp.__new__(Il2Cpp)._icall_type_key(text, byref=byref)


def test_type_key_maps_cli_primitives():
    assert _key('System.Int32') == 'int'
    assert _key('System.Single') == 'float'
    assert _key('System.Boolean') == 'bool'
    assert _key('System.SByte*') == 'sbyte*'
    assert _key('System.Int32&') == 'int&'
    assert _key('int', byref=True) == 'int&'


def test_type_key_nested_and_generic_spellings():
    assert _key('UnityEngine.ObjectDispatcher/TypeTrackingFlags') == \
        'UnityEngine.ObjectDispatcher.TypeTrackingFlags'
    assert _key('System.Action`6<System.Int32,System.IntPtr>') == \
        'System.Action_6<int,System.IntPtr>'


def test_type_key_keeps_a_pointer_distinct_from_an_array():
    assert _key('System.SByte*') == 'sbyte*'
    assert _key('sbyte[]') == 'sbyte[]'
    assert _key('System.SByte*') != _key('sbyte[]')


def test_type_key_does_not_rewrite_a_dotted_lookalike():
    assert _key('Foo.System.Int32') == 'Foo.System.Int32'


# ------------------------------------------------------------- overload


def _pick(il, sig, cands):
    return il._icall_pick_overload(sig, cands)


def test_pick_unique_arity_solves():
    il = _il([((0,), True), ((0, 1), True)], [INT, STRING],
             {INT: 'System.Type', STRING: 'System.Boolean'})
    assert _pick(il, 'A.B::C(System.Type,System.Boolean)', [0, 1]) == 1


def test_pick_same_arity_matches_types():
    il = _il([((0,), True), ((1,), True)], [INT, STRING, BYREF_INT],
             {INT: 'System.Int32', STRING: 'string', BYREF_INT: 'System.Int32'})
    # both declare one parameter; only mi 0 declares System.Int32
    assert _pick(il, 'A.B::C(System.Int32)', [0, 1]) == 0


def test_pick_same_arity_byref_matches():
    il = _il([((0, 2, 2), True), ((1, 2, 2), True)],
             [INT, STRING, BYREF_INT],
             {INT: 'System.Int32', STRING: 'string', BYREF_INT: 'System.Int32'})
    sig = 'A.B::C(System.Int32,System.Int32&,System.Int32&)'
    assert _pick(il, sig, [0, 1]) == 0


def test_pick_declines_a_tied_type_match():
    il = _il([((0,), True), ((0,), True)], [INT],
             {INT: 'System.Int32'})
    # identical normalized parameter types cannot tell the two rows
    # apart -> decline, not first-row
    assert _pick(il, 'A.B::C(System.Int32)', [0, 1]) is None


def test_pick_declines_an_unmatched_arity():
    il = _il([((0,), True)], [INT], {0: 'System.Int32'})
    assert _pick(il, 'A.B::C(System.Int32,System.Boolean)', [0]) is None


def test_pick_ignores_an_out_of_range_row():
    il = _il([((0,), True)], [INT], {0: 'System.Int32'})
    assert _pick(il, 'A.B::C(System.Int32)', [0, 9]) == 0


def test_pick_declines_an_unparseable_signature():
    il = _il([((0,), True)], [INT], {0: 'System.Int32'})
    assert _pick(il, 'A.B::C', [0]) is None
    assert _pick(il, None, [0]) is None
