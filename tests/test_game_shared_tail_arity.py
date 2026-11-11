"""One shared body, one argument list: tails stop inventing a trailing zero.

Ground truth (game fixture): MSVC folds the no-arg `GetHashCode` forwarders
onto one body -- `xor edx,edx; jmp 0x181b14c10` -- so `ConstructorInfo`
(mi 8752) and the two `IEqualityComparer<object>` implementations (mi
13198, 78202) tail-jump an address that `Delegate.GetHashCode` (mi 3961)
also *calls* with one argument. `_call` was already bounded by the largest
declared arity among the address's candidates; the tails were not, so the
same VA printed `(this.m_target)` at the call site and `(this, 0)` at the
tail. The zero is callee-zeroed plumbing (`xor edx,edx` right ahead of the
jmp`), not a parameter.

The trim only removes a trailing run of literal zeros. `List<T>.CopyTo`'s
forwarder (0x180df9c30, three candidates) really does read the registers a
missing sharer left behind, so mi 24077 keeps its four-argument spelling.
"""
import pytest

from test_game_goldens import game_decompiler

pytestmark = pytest.mark.game


def lift_text(game_decompiler, mi, name, va):
    il, dec = game_decompiler
    m = il.meta.methods[mi]
    assert m.name == name
    assert hex(m.addr) == va
    return '\n'.join(dec.lift_method(m, il.meta.typedefs[m.declaring]))


def test_gethashcode_forwarder_tail_drops_the_zeroed_register(game_decompiler):
    text = lift_text(game_decompiler, 8752, 'GetHashCode', '0x181baa7b0')
    assert 'return (int)sub_181b14c10/*shared body, 13 candidates*/(this);' \
        in text
    assert ', 0)' not in text


def test_gethashcode_twins_resolved_by_receiver_are_unchanged(game_decompiler):
    for mi in (8771, 8790):
        text = lift_text(game_decompiler, mi, 'GetHashCode', '0x181baa7b0')
        assert 'return this.GetHashCode(); /* tail */' in text
        assert 'shared body' not in text


def test_equality_comparer_gethashcode_tails_match_the_call_shape(game_decompiler):
    for mi in (13198, 78202):
        text = lift_text(game_decompiler, mi,
                         'System.Collections.Generic.IEqualityComparer<System.Object>'
                         '.GetHashCode', '0x181dcec20')
        assert 'return (int)sub_181b14c10/*shared body, 13 candidates*/(obj);' \
            in text


def test_the_same_body_called_keeps_one_argument(game_decompiler):
    # the call site of 0x181b14c10 was already trimmed by 21j; the tails
    # now agree with it instead of contradicting it
    text = lift_text(game_decompiler, 3961, 'GetHashCode', '0x181cf8580')
    assert 'sub_181b14c10/*shared body, 13 candidates*/(this.m_target)' in text


def test_shared_clone_forwarder_tail_drops_the_zeroed_register(game_decompiler):
    text = lift_text(game_decompiler, 1231, 'Clone', '0x181c07770')
    assert 'return sub_181cf6c90/*shared body, 2 candidates*/(this);' in text


def test_extra_registers_the_body_really_reads_keep_their_spelling(game_decompiler):
    # List<T>.CopyTo's shared body (0x180df9c30) dispatches on registers a
    # registry-missed sharer reads; a non-zero extra argument is untouched
    text = lift_text(game_decompiler, 24077, 'SelectNuisanceType', '0x18051ee30')
    assert 'sub_180df9c30/*shared body, 3 candidates*/(list18, this.nuisanceType,' \
        in text
