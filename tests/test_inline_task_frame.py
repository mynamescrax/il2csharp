"""Independent Win64 frames: exercise protected entries and byte aliasing without game inputs."""
from types import SimpleNamespace as NS

from iced_x86 import Decoder
import pytest

from il2cpp.captured_home import _predecessors
from il2cpp.inline_task import _frame_isolated


@pytest.mark.parametrize('base,frame,home',[(0x14000,0x50,0x28),(0x820000,0x70,0x38)])
@pytest.mark.parametrize('change',['disjoint','overlap','indexed','split span','partial entry'])
def test_protected_local_bytes(base,frame,home,change):
    # RCX home, saved RSI, fixed allocation; two NOPs stand for the proved
    # kickoff window. A later qword load can straddle its first byte.
    pro='48894c2408 56 4883ec%02x'%frame
    branch='7501' if change=='partial entry' else '7502'
    off=home-7 if change=='overlap' else home+24
    read=('488b440c' if change=='indexed' else '488b4424')+'%02x'%off
    ep='4883c4%02x 5e c3'%frame
    seq=list(Decoder(64,bytes.fromhex(' '.join((pro,branch,'90 90',read,ep,ep))),ip=base))
    start=seq[4].ip;end=seq[6].ip;pad=seq[-3].ip;spans=[(seq[3].ip,end)]
    if change=='split span':spans=[(seq[3].ip,seq[5].ip),(seq[5].ip,end)]
    eh=dict(try_ranges=[(0,0,1,spans)],try_pads=[[pad]],pads=[pad]);pred=_predecessors(seq,eh)
    unwind=bytes([0x19,10,2,0,10,(frame//8-1)*16+2,6,0x60]);ui=0x200
    image=NS(image_base=base,read=lambda a,n:unwind[:n] if a==base+ui else b'')
    il=NS(bin=image,_eh4_begins=[0],_eh4_entries=[(0,seq[-1].next_ip-base,ui)])
    assert _frame_isolated(NS(il=il),NS(addr=base),seq,eh,start,end,[(home,home+24)],pred)==(change=='disjoint')
