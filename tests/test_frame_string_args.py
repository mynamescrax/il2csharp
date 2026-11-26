import pytest
from iced_x86 import Decoder

from il2cpp.frame_args import _prefix_loads


def sites(code, *, skip=(), pads=()):
    insns = list(Decoder(64, bytes.fromhex(code), ip=0x1000))
    return _prefix_loads(insns, {0x30: ('name', (0, 14 << 16))}, set(skip), pads, None)


def test_load_uses_captured_frame_not_current_rsp():
    # Entry-8 is captured in RBP; sub rsp,0x50 changes only RSP.
    proof = sites('55 488bec 4883ec50 4c8b7d38 c3')
    assert proof == {0x1008: ('name', (0, 14 << 16))}


@pytest.mark.parametrize('code', [
    '55 488bec 4883ec50 448b7d38 c3',        # only the low dword
    '55 488bec 4883ec50 4c8b7d30 c3',        # different stack parameter
    '55 488bec e800000000 4c8b7d38 c3',      # ordinary call before the reload
    '55 488bec 48894c2438 4c8b7d38 c3',      # parameter overwritten before read
    '55 488bec 488d4538 4c8b7d38 c3',        # address escaped
    '55 488bec 488be9 4c8b7d38 c3',          # frame register reused
    '55 488bec 4c8b7d38 ebfa',                # second path back into reload
    '55 488bec 4c8b7d38 ffe0',                # possible indirect entry
])
def test_ambiguous_reload_keeps_old_slot(code):
    assert sites(code) == {}


def test_stack_reference_above_biased_rbp_uses_entry_rsp():
    code = '488bc4 48895808 55 488d68d8 4881ec20010000 488b7d50'
    home = ('other',(7,0x12<<16))
    def probe(raw):
        seq=list(Decoder(64,bytes.fromhex(raw),ip=0x3000))
        return _prefix_loads(seq,{0x28:home},set(),(),None).get(seq[-1].ip)
    assert probe(code) == home
    assert probe(code.replace('48895808','48895828')) is None   # overwritten stack argument
    assert probe(code.replace('48895808','488bc1')) is None     # RAX no longer entry SP
    assert probe(code.replace('488b7d50','8b7d50')) is None     # truncated reference
