from types import SimpleNamespace as NS

import pytest
from iced_x86 import Decoder, Mnemonic

from il2cpp import captured_home as home


def cleanup(monkeypatch, *, span=24, extra='', prefix='', descriptor='48'):
    # Save the reference at +78. Pass a pointer to +60 via a second copy of
    # a two-qword cleanup descriptor. A borrow of 24 bytes just fits; even
    # one more byte may change the saved reference. All offsets are bytes.
    code = bytes.fromhex(prefix + ' 48897c2478 488d442460 4889442438 '
                         '0f10442438 0f11442448 488b4c24' + descriptor +
                         ' e800100000 ' + extra + ' 90 eb05 488b7c2478 c3')
    ins = list(Decoder(64, code, ip=0x4000))
    nop, pad = ins[-4].ip, ins[-2].ip
    eh = dict(pads=[pad], try_pads=[[pad]], try_ranges=[(0,0,1,[(nop,ins[-3].ip)])])
    pred = home._predecessors(ins, eh)
    call = next(i.ip for i in ins if i.mnemonic == Mnemonic.CALL)
    store = next(i.ip for i in ins if i.op1_register and i.memory_displacement == 0x78)
    monkeypatch.setattr(home, '_borrow_calls', lambda *_: {call: (span, False)})
    il = NS(bin=NS(read=lambda va,n: b'\x90'*n, exports={}))
    return home._intact(il, ins, pred, eh, ins[0].ip, store, pad, 0x78, 0xb0, {})


def test_descriptor_borrow_ending_at_spill(monkeypatch):
    assert cleanup(monkeypatch, extra='4889442470')


@pytest.mark.parametrize('changes', [
    dict(span=25),                         # indirect overlapping write via call
    dict(extra='4889442471'),              # direct overlapping write
    dict(extra='488b442448 48895018'),     # descriptor -> &local -> [local+24]
    dict(extra='488b442448 488901'),       # stored beyond our frame
    dict(extra='488b442448 4c8b2443'),     # contains a stack pointer as scaled index
    dict(prefix='7505'),                   # one path skips saving RDI
])
def test_unproven_health_of_the_spill_declines(monkeypatch, changes):
    assert not cleanup(monkeypatch, **changes)


def test_unrestored_handler_cannot_contribute_rdi():
    # Even with a valid reload, a second handler reaching the use without
    # passing through that reload is a conflicting predecessor.
    ins = list(Decoder(64,bytes.fromhex('488b7b28 eb05 488b7c2478 488bcf c3'),ip=0x2000))
    pred = home.defaultdict(set, {ins[1].ip:{ins[0].ip}, ins[3].ip:{ins[1].ip,ins[2].ip}})
    assert home._rdi_paths(ins, pred, [ins[2].ip], ins[0].ip, ins[2].ip)
    assert not home._rdi_paths(ins, pred, [ins[2].ip,ins[3].ip], ins[0].ip, ins[2].ip)
