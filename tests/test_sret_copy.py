"""A surplus FP lane is evidence only after the complete value was stored."""
from types import SimpleNamespace as NS

import pytest
from iced_x86 import Decoder

from il2cpp.binary import PE
from il2cpp.expr import Expr
from il2cpp.shared_getter import shared_getter
from il2cpp.sret_copy import _window


def window(change=None):
    # Different field offsets and register allocation from the game.
    head = 'e810000000 8b4808 f20f1000 f20f114738 894f40 488b4f18 4885c9 740b'
    if change == 'overlapping source': head = head.replace('8b4808','8b4804')
    if change == 'not a full copy': head = head.replace('894f40','894f3c')
    if change == 'different xmm': head = head.replace('f20f114738','f20f114f38')
    if change == 'lost high dword': head = head.replace('894f40','895740')
    if change == 'intervening effect': head = head.replace('894f40','e800020000 894f40')
    a = list(Decoder(64,bytes.fromhex(head),ip=0x3000))
    b = list(Decoder(64,bytes.fromhex('31d2 e800010000'),ip=a[-1].next_ip))
    blocks=[NS(bid=0,insns=a,succs=[1,2]),NS(bid=1,insns=b,preds=[0,2] if change=='extra entry' else [0])]
    return _window(blocks,blocks[0],3)


@pytest.mark.parametrize('change',[None,'overlapping source','not a full copy','different xmm','lost high dword',
                                   'intervening effect','extra entry'])
def test_only_complete_uninterrupted_copy_is_a_witness(change):
    assert (window(change) is not None) == (change is None)


@pytest.mark.parametrize('change',[None,'other site','same text not same value','other lane','unevaluated extra'])
def test_extra_value_exemption_is_per_getter_and_register(change):
    image = PE.__new__(PE)
    il=NS(bin=image,_type_enum=lambda t:t[1]>>16&255,_public_getter_aliases={(0x2200,3):('parent','Transform')})
    recv=Expr('local',(3,0x12<<16),'obj'); low=Expr('*(home + 0)',None,'float')
    lift=NS(il=il,_cur_ip=0x1234,_stored_getter_lane=(0x5678 if change=='other site' else 0x1234,low))
    xmm=[Expr(low.text) if change=='same text not same value' else low]
    if change=='other lane': xmm.insert(0,None)
    if change=='unevaluated extra': xmm.append(Expr('ReadAgain()'))
    assert bool(shared_getter(lift,0x2200,['local'],[recv,Expr('0')],xmm)) == (change is None)
