"""Fix 129b: a vtable slot declared on the receiver's own generic
definition binds its class VARs from the receiver's GENERICINST arguments.

Ground truth: Computer.ShouldRankBefore (VA 0x18069C700) calls
`Comparer<float>.Default.Compare(candidate.score, existing.score)` through
vtable slot 6.  `Compare(T, T)` with T=float passes both values in
XMM1/XMM2; reading the unbound VAR as integer-class took the stale RDX/R8
scratch (`Compare(comparer11.getClass().vtable[6], obj4)`).
"""
import pytest

from test_game_goldens import game_decompiler

pytestmark = pytest.mark.game


def test_comparer_float_compare_reads_xmm_args(game_decompiler):
    il, dec = game_decompiler
    for td in il.meta.typedefs:
        if td.name == 'Computer' and not td.namespace:
            break
    else:
        raise AssertionError('Computer not found')
    for mi in range(td.method_start, td.method_start + td.method_count):
        m = il.meta.methods[mi]
        if m.name == 'ShouldRankBefore':
            break
    else:
        raise AssertionError('ShouldRankBefore not found')
    text = '\n'.join(dec.lift_method(m, td))
    assert '.Compare(candidate.score, existing.score)' in text
    assert 'vtable[6], ' not in text
