from types import SimpleNamespace as NS

from iced_x86 import Decoder, Register as R
import pytest

from il2cpp.indexed_particle import _entry_copy, _setup, _spilled_setup


def getter(change=None):
    # Different index/base and different stride from the game.
    code = 'f2410f1006 488d4c2440 4963c4 4533c0 486bd070 f20f11442430 4883c220 4803d6'
    if change:
        a,b = change; code = code.replace(a,b)
    return _setup(list(Decoder(64,bytes.fromhex(code))),R.RSI,R.R12D,112,False)


def test_array_address_uses_the_metadata_stride_and_guarded_index():
    assert getter()


@pytest.mark.parametrize('change', [('486bd070','486bd074'), # wrong stride
    ('4963c4','4963c5'), ('4883c220','4883c218'), ('4803d6','4803d7'),
    ('4533c0','4533c9'), ('488d4c2440','488d4c2430'),      # output aliases XY spill
    ('4963c4','418bc4')])                                   # zero- not sign-extended
def test_incomplete_array_address_declines(change):
    assert not getter(change)


def test_whole_saved_array_required_on_every_path():
    def block(code,preds,entry=False):
        return NS(insns=list(Decoder(64,bytes.fromhex(code))),preds=preds,is_entry=entry)
    original=block('488bf2',[],True)  # RSI <- full entry RDX
    paths=[original,block('90',[0,2]),block('e800010000',[1])]
    assert _entry_copy(paths,1,R.RSI,R.RDX)
    paths[2]=block('40b601',[1])      # SIL only overwritten on back edge
    assert not _entry_copy(paths,1,R.RSI,R.RDX)


@pytest.mark.parametrize('change',['ok','bad stride','other index','other array','out overlaps','z gap','out of frame','wrong metadata arg'])
def test_sret_address_is_separate_from_whole_interleaved_spill(change):
    # An independently scheduled loop over 76-byte values. RSI is the
    # array, R12D its index; R10 holds the sign-extended index. RBP+0x18
    # is RSP+0x98 in this frame, not the SP-relative outgoing home.
    raw='4d63d4 488d4d18 496bd24c 44897c2438 4533c0 4803d6 f20f11742430 4883c220'
    patch={'bad stride':('d24c','d250'),'other index':('63d4','63d5'),'other array':('03d6','03d7'),
           'out overlaps':('4d18','4db0'),'z gap':('2438','243c'),'out of frame':('4d18','4d78'),
           'wrong metadata arg':('4533c0','4533c9')}
    if change in patch:raw=raw.replace(*patch[change])
    seq=list(Decoder(64,bytes.fromhex(raw),ip=0x7000))
    assert _spilled_setup(seq,R.RSI,R.R12D,76,(0x80,0xc0,0xe0))==(0x98 if change=='ok' else None)
