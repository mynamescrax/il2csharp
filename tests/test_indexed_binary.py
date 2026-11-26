"""Prove that a saved vector is one 12-byte value even on loop reentry."""
from iced_x86 import Decoder
import pytest

from il2cpp.captured_home import _normal_predecessors
from il2cpp.indexed_binary import _saved_pair,_echo_copy


@pytest.mark.parametrize('change',['unchanged','clobber XY','clobber Z','wrong Z offset','partial entry'])
def test_nonvolatile_pair_requires_one_live_getter(change):
    # Save a getter echo into XMM4+4 and R12D, then traverse a loop
    # containing an unrelated call. Changed reaching bytes must decline.
    use='f2440f11442438 4489642440';head='e8fb010000 f2440f1000 448b6008'
    if change=='wrong Z offset':head=head.replace('6008','6004')
    latch={'clobber XY':'450f57c0','clobber Z':'4531e4'}.get(change,'90')
    # Jump past the XY save along an alternate path into the Z definition.
    entry='750a' if change=='partial entry' else '90'
    raw=bytes.fromhex(entry+' '+head+' '+use+' e8fb010000 '+latch);back=-(len(bytes.fromhex(use))+5+len(bytes.fromhex(latch))+2)
    seq=list(Decoder(64,raw+b'\x75'+bytes([back%256])+b'\xc3',ip=0xab000));byip={i.ip:i for i in seq}
    result=_saved_pair(byip,_normal_predecessors(seq),seq[4],seq[5]);assert bool(result)==(change=='unchanged')


@pytest.mark.parametrize('change',['unchanged','nonvolatile scratch','bad copy','swapped base'])
def test_result_echo_must_cover_first_argument(change):
    raw='4533c0 488d542438 488d4c2468 f20f1008 8b4008 f20f114c2468 89442470 e800010000'
    if change=='nonvolatile scratch':raw=raw.replace('1008','1030').replace('114c','1174')
    if change=='bad copy':raw=raw.replace('4008','4004')
    if change=='swapped base':raw=raw.replace('114c2468','114c2438')
    seq=list(Decoder(64,bytes.fromhex(raw),ip=0x95000));assert _echo_copy(seq,(96,272,296))==((104,56) if change=='unchanged' else None)
