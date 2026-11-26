from iced_x86 import Decoder
import pytest

from il2cpp.this_home import _reloads


def cleanup_reload(*, before='', at_pad='', load='488b7c2430', save='48894c2408',
                   unwind='190a02000a320670'):
    # One normal edge carries RDI=this. An independent in-frame continuation
    # must recover it from entry+8 (the pad's RSP is entry-0x28).
    va = 0x2000
    pro = bytes.fromhex(save + ' 57 4883ec20 488bf9 ' + before)
    pad = bytes.fromhex(at_pad + load)
    start = va + len(pro) + 2
    data = pro + bytes([0xeb,len(pad)]) + pad + bytes.fromhex('488bcf 4883c420 5f c3')
    insns = list(Decoder(64, data, ip=va))
    return _reloads(insns, [start], bytes.fromhex(unwind)), start + len(bytes.fromhex(at_pad))


def test_pad_recovers_receiver_from_fixed_frame_not_register_seed():
    sites, load = cleanup_reload(at_pad='31ff')  # actual RDI is not this on pad entry
    assert sites == {load:True}


@pytest.mark.parametrize('changes', [dict(save='4889542408'), dict(load='8b7c2430'),
                                     dict(load='488b7c2438'), dict(unwind='190a02000a220670'),
                                     dict(at_pad='c644243401'), dict(before='488d4c2430'),
                                     dict(before='488bc4'), dict(before='4883ec08')])
def test_unproved_or_overlapping_home_declines(changes):
    sites, _ = cleanup_reload(**changes)
    assert not sites


def large_frame(*, after='', xmmoff='d8', scaled_alloc='16', scaled_save='09'):
    # Entry RSP in RAX, a single nonvolatile push and a 176-byte frame.
    # [rax-0x28] is [framed rsp+0x90]; [framed rsp+0xc0] is entry+8.
    pro = bytes.fromhex('488bc4 48894808 56 4881ecb0000000 0f2970' + xmmoff)
    assert len(pro) == 19
    normal = bytes.fromhex(after + ' 488bf1 eb08')
    pad = bytes.fromhex('488bb424c0000000')
    tail = bytes.fromhex('488bce 4881c4b0000000 5e c3')
    va = 0x4000
    start = va + len(pro) + len(normal)
    unwind = bytes.fromhex('19130500 1368' + scaled_save + '00 0f01' + scaled_alloc + '00 0860')
    return _reloads(list(Decoder(64, pro + normal + pad + tail, ip=va)), [start], unwind), start


def test_entry_rsp_alias_large_frame_and_xmm_save_match_unwind():
    sites, pad = large_frame()
    assert sites == {pad:True}


@pytest.mark.parametrize('changes', [dict(xmmoff='c8'), dict(xmmoff='d8', scaled_alloc='15'),
                                     dict(xmmoff='d8', scaled_save='08'),
                                     dict(xmmoff='d8', after='48895008'),  # alias clobbers home
                                     dict(xmmoff='d8', after='488bc8')])    # entry RSP escapes
def test_unverified_large_frame_declines(changes):
    sites, _ = large_frame(**changes)
    assert not sites
