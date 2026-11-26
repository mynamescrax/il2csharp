from iced_x86 import Decoder, Register as R
import pytest
from il2cpp.ref_vectors import _copies


def copies(change=None):
    # Change the source field register and frame locations. Split and
    # interleave the two copies, passing the *destinations* in RCX and RDX.
    code = ('4531c0 488d542450 488d4c2440 f20f1000 f20f11442440 8b4008 '
            'f20f104638 89442448 8b4640 89442458 f20f11442450')
    if change=='short input': code=code.replace('f20f1000','f30f1000')
    if change=='wrong component': code=code.replace('8b4640','8b463c')
    if change=='wrong address': code=code.replace('488d542450','488d542448')
    if change=='missing high store': code=code.replace('89442448','90')
    if change=='unknown register': code=code.replace('89442448','89542448')
    if change=='extra effect': code=code.replace('8b4640','e800200000 8b4640')
    return _copies(list(Decoder(64,bytes.fromhex(code),ip=0x3450)))


def test_ref_arguments_are_addresses_of_independent_full_copies():
    assert copies() == [((R.RAX,0),(R.RSP,0x40)),((R.RSI,0x38),(R.RSP,0x50))]


@pytest.mark.parametrize('change',['short input','wrong component','wrong address','missing high store',
                                   'unknown register','extra effect'])
def test_incomplete_reference_copy_proof_declines(change):
    assert copies(change) is None
