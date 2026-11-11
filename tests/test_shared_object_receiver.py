"""Object's folded instance body needs a complete candidate proof."""
from types import SimpleNamespace as NS

from il2cpp import Expr, Lifter, MethodDef


def setup():
    lift = Lifter.__new__(Lifter)
    methods = [
        MethodDef(0, 'Clone', 1, 0, 0, -1, 0, 0, 0, 0, 0),
        MethodDef(1, 'MemberwiseClone', 0, 0, 0, -1, 0, 0, 0, 0, 0),
    ]
    lift.meta = NS(methods=methods)
    lift.il = NS(
        types=[(0, 0x1c << 16)],
        _type_enum=lambda ty: (ty[1] >> 16) & 0xff,
        _system_object_td=lambda: 0,
        base_chain_tds=lambda td: (td, 0) if td != 0 else (0,),
        returns_sret=lambda ty: False,
    )
    lift._td_of = lambda ty: ty[0]
    return lift, [('method', 0), ('method', 1)]


def test_unrelated_derived_receiver_selects_object_owner():
    lift, candidates = setup()
    recv = Expr('this', (2, 0x12 << 16), 'obj')
    assert lift._shared_object_receiver_target(candidates, recv) == ('method', 1)


def test_delegate_receiver_keeps_both_owners_ambiguous():
    lift, candidates = setup()
    recv = Expr('this', (1, 0x12 << 16), 'obj')
    assert lift._shared_object_receiver_target(candidates, recv) is None


def test_generic_or_static_candidate_declines():
    lift, candidates = setup()
    recv = Expr('this', (2, 0x12 << 16), 'obj')
    assert lift._shared_object_receiver_target(candidates + [('generic', 4)], recv) is None
    lift.meta.methods[0].flags |= 0x10
    assert lift._shared_object_receiver_target(candidates, recv) is None
