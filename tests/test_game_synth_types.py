"""Native-backed assertions for synthetic closed nested types (blocker 1).

Some closed nested instantiations (e.g.
`Dictionary<Selectable,Navigation>.Enumerator`) have no row in
`il.types`. `_subst_closed` rebuilds them as real tuples over a
fake-VA side table, so names, keys, receiver proofs and arg lists keep
working. Anything unbound still declines -- never a half-open guess.
"""
import pytest

from test_game_goldens import game_decompiler

pytestmark = pytest.mark.game


SELECTABLE = 'UnityEngine.UI.Selectable'
NAVIGATION = 'UnityEngine.UI.Navigation'
ENUM_NAME = ('System.Collections.Generic.Dictionary_2<%s, %s>.Enumerator'
             % (SELECTABLE, NAVIGATION))


def class_args(il, first, second):
    for ii, row in enumerate(il.generic_insts_list):
        if row is None or row[0] != 2:
            continue
        args = il._argv_type_tuples(*row)
        if args and [il.type_name(a) for a in args] == [first, second]:
            return il._method_spec_type_args(ii)
    raise AssertionError('no (%s, %s) class inst' % (first, second))


def test_nested_return_substitutes_to_named_closed_type(game_decompiler):
    il, _ = game_decompiler
    args = class_args(il, SELECTABLE, NAVIGATION)
    open_ty = il.types[il.meta.methods[11337].return_type]
    assert il._closed_type_key(open_ty) is None
    syn = il._subst_closed(open_ty, args, None)
    assert syn is not None and syn[0] >= 0x70000000
    assert il.type_name(syn) == ENUM_NAME
    assert il.td_of_ty(syn) == 1514
    assert [il.type_name(a) for a in il._generic_inst_args(syn)] == [
        SELECTABLE, NAVIGATION]
    # dry/real passes and repeated calls agree (keyed cache, not id()).
    assert il._subst_closed(open_ty, args, None) == syn


def test_nested_return_declines_open_or_unreadable(game_decompiler):
    il, _ = game_decompiler
    open_ty = il.types[il.meta.methods[11337].return_type]
    assert il._subst_closed(open_ty, None, None) is None
    assert il._subst_closed(open_ty, [], None) is None
    assert il._subst_closed(None, [], None) is None


def test_candidate_return_type_closes_nested_spec_returns(game_decompiler):
    il, _ = game_decompiler
    # spec 114: <.cctor>b__0_0 returning open ChangeEvent<T>, closed by
    # its class instantiation to ChangeEvent_1<bool>.
    assert il.type_name(il.candidate_return_type(('generic', 114))) == \
        'UnityEngine.UIElements.ChangeEvent_1<bool>'


def test_synthetic_sret_needs_proved_size(game_decompiler):
    il, _ = game_decompiler
    args = class_args(il, SELECTABLE, NAVIGATION)
    open_ty = il.types[il.meta.methods[11337].return_type]
    # open shapes keep the old stand-down (fix-54): size unprovable.
    assert il.returns_sret(open_ty) is False
    syn = il._subst_closed(open_ty, args, None)
    # 72-byte closed layout proves the hidden buffer; small or unknown
    # sizes stay by-value/unknown.
    assert il._sf_field_size(syn, 0) == 72
    assert il.returns_sret(syn) is True
    # consensus still cannot agree on a valuetype instantiation (buffer
    # ABI unmodeled there): naming/typing gains only, no identity proof.
    assert il._return_abi_is_known(syn) is False
