"""Register-only computation is pure only with traced, initialized inputs."""
from iced_x86 import Decoder, Register as R
import pytest

from il2cpp.simd_getter import _scratch_inputs


def kernel(change=''):
    # Saved xmm6 is one four-float result. A second result is read via
    # the new RAX. Establish each surplus register independently.
    seq = '0f1038 0f28c6 0f28cf 0f28d7 0fc6d755 0f28de f30f59c7 '
    return list(Decoder(64,bytes.fromhex(seq + change),ip=0x4000))


def test_xmm0_through_3_derive_from_the_two_snapshots():
    seed, lanes = _scratch_inputs(kernel(),R.XMM6)
    assert seed.ip == 0x4000 and {R.XMM0,R.XMM1,R.XMM2,R.XMM3} <= lanes


@pytest.mark.parametrize('tail', ['f30f5906',     # possible fault: field load, not a register product
                                 'f30f59c4',     # unaccounted-for color/FP argument in xmm4
                                 'e800100000',   # intervening call with effects
                                 '0f104708',     # another memory source
                                 '0f1038',       # repeated sret read
                                 'f30f1106'])    # store with observable effects
def test_no_blanket_exemption_for_fp_expressions(tail):
    assert _scratch_inputs(kernel(tail),R.XMM6) is None
