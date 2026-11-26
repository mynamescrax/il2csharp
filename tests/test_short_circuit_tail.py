from types import SimpleNamespace as NS

from il2cpp import Decompiler


def fold(lines):
    d = Decompiler.__new__(Decompiler)
    d.L = NS(il=NS(_type_enum=lambda t: t[1] >> 16), _var_types={k:(0, 2 << 16) for k in ('t1','t2')})
    d.phi_names = {'v3'}
    return d._short_circuit_tail(lines, 'L_100')


def test_two_tests_one_body_needs_both_empty_gate_edges():
    lines = ['var t1 = A();', 'if (t1)', '{', 'L_100:', 'Use();', '}', 'else', '{',
             'var t2 = B();', 'if (!t2)', '{', '}', 'else', '{', 'goto L_100;', '}', '}']
    assert fold(lines) == ['if ((A()) || (B()))', '{', 'Use();', '}']
    # A live phi transfer, even of a bare value, cannot vanish in ||.
    assert fold(lines[:14] + ['v3 = value;'] + lines[14:] + ['Use(v3);']) is None
    assert fold(lines[:11] + ['Audit();'] + lines[11:]) is None
    assert fold(lines + ['if (again) goto L_100;']) is None
