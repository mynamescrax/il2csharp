from iced_x86 import Decoder, Register as R
import pytest

from il2cpp.simd_return import _pack


def sources(last='39', before='', after='', store='0f1103'):
    # Synthetic register allocation: pack XMM0,1,2,3 to [rbx]. A different
    # selector should produce a correspondingly different output mapping.
    code = ('0fc6c0e1 f30f10c1 0fc6c0c6 ' + before + ' f30f10c2 ' + after +
            ' 0fc6c027 f30f10c3 0fc6c0' + last + ' ' + store)
    seq = list(Decoder(64,bytes.fromhex(code),ip=0x4000))
    return _pack(seq,len(seq)-1)


def test_shuffle_selectors_determine_component_order():
    assert sources() == (0, (R.XMM0,R.XMM1,R.XMM2,R.XMM3))
    assert sources(last='36') == (0, (R.XMM1,R.XMM0,R.XMM2,R.XMM3))


def test_restoring_register_after_consumption_preserves_packed_lane():
    restore = '0f28542420'  # movaps xmm2,[rsp+20h]
    assert sources(after=restore) == sources()
    assert sources(before=restore) is None


@pytest.mark.parametrize('changes',[dict(last='00'),dict(before='e800010000'),dict(store='f30f1103'),
                                    dict(store='0f114304'),dict(store='0f11040b')])
def test_unproved_lane_or_incomplete_destination_is_not_a_struct_return(changes):
    assert sources(**changes) is None
