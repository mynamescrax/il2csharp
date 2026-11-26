from types import SimpleNamespace as NS

import pytest
from iced_x86 import Decoder, Register as R

from il2cpp.reparent import _result_origin, _saved_array_source


def origin(save, during='', *, merge=False):
    # A getter result is saved across another call; RAX then supplies the
    # argument rather than the receiver of the final call.
    ip = 0x5000
    first = list(Decoder(64,bytes.fromhex('e800010000 '+save+' e800020000 '+during),ip=ip))
    use = list(Decoder(64,bytes.fromhex('4533c0 488bd0 488bce e800030000'),ip=first[-1].next_ip))
    blocks = [NS(bid=0,insns=first,preds=[]), NS(bid=1,insns=use,preds=[0,2] if merge else [0])]
    return [v.ip if v else None for r in (R.RCX,R.RDX)
            for v in [_result_origin(blocks,blocks[1],3,r)]]


def test_child_precedes_parent_and_is_not_the_second_result():
    assert origin('488bf0') == [0x5000,0x5008]


@pytest.mark.parametrize('save,gap,merge', [('8bf0','',False), ('488bf0','40b601',False),
                                            ('488bf0','',True), ('488bca','',False)])
def test_missing_receiver_on_any_path_declines(save,gap,merge):
    assert origin(save,gap,merge=merge)[0] is None


@pytest.mark.parametrize('latch,expected', [('ffc3',(0,0)),('e800010000',(0,0)),('40b702',None),('488b7f48',None)])
def test_array_field_must_reach_the_indexed_load_on_every_iteration(latch,expected):
    # A loop back edge through a call preserves the nonvolatile RDI.
    # Even a partial write or an equally well-typed different load does not.
    blocks = [NS(bid=j,insns=list(Decoder(64,bytes.fromhex(code),ip=0x1000+j*32)),preds=preds)
              for j,(code,preds) in enumerate([('488b7f40',[]),('4863c3 488b74c720',[0,2]),(latch,[1])])]
    assert _saved_array_source(blocks,blocks[1],1,R.RDI) == expected
