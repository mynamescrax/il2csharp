from types import SimpleNamespace as NS

from iced_x86 import Decoder, Register as R
import pytest

from il2cpp.indexed_particle import _entry_copy, _setup


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
