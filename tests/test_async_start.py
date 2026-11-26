import pytest
from iced_x86 import Decoder,Register as R

from il2cpp.async_start import _covers,_frame


@pytest.mark.parametrize('change',['none','wrong restore displacement','different stack reset','overlapping home','wrong saved reg'])
def test_kickoff_frame_homes_must_be_restored(change):
    # One home save and one push. After allocation the saved RBX sits at
    # RSP+0x70, or R11+16 once R11 points to the saved RDI.
    pro='48895c2408 57 4883ec60'; ep='4c8d5c2460 498b5b10 498be3 5f c3'
    if change=='wrong restore displacement':ep=ep.replace('5b10','5b18')
    if change=='different stack reset':ep=ep.replace('5c2460','5c2450')
    if change=='overlapping home':pro='4889742408 '+pro
    if change=='wrong saved reg':ep=ep.replace('498b5b10','498b7310')
    seq=lambda raw:list(Decoder(64,bytes.fromhex(raw)))
    assert _frame(seq(pro),seq(ep))==((0x60,{R.RBX,R.RDI}) if change=='none' else None)


@pytest.mark.parametrize('tiles,ok', [([(32,16),(56,8),(48,8)],True), ([(32,16),(48,8)],False),
                                       ([(32,16),(40,8),(56,8)],False), ([(24,8),(32,16),(48,16)],False)])
def test_state_zeroes_cover_only_one_whole_local(tiles,ok):
    assert _covers(tiles,32,32)==ok
