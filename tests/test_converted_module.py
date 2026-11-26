from iced_x86 import Decoder
import pytest

from il2cpp.converted_module import _distinct, _setup, _writes_only_result


def decode(code):
    return list(Decoder(64, bytes.fromhex(code), ip=0x1000))


def test_incoming_home_is_distinct_from_sret_and_indirect_argument():
    size, entry = 0xc0, 0xd8
    assert _distinct(0xe0,0x50,0x30,size,entry)
    assert _distinct(0xb0,0x50,0x30,size,entry)
    for invalid in (0,0x18,0x48,0x50,size,entry,entry+9,entry+40):
        assert not _distinct(invalid,0x50,0x30,size,entry)
    assert not _distinct(0xe0,0x50,0x40,size,entry)


@pytest.mark.parametrize('old,new', [('48894557','894557'),('4531c0','31d2'),
                                    ('0f57c9','0f57c0'),('488d4dd7','488d55d7'),
                                    ('48894557','48894557 894d5b')])
def test_conversion_setup_needs_whole_reference_and_abi(old,new):
    code='4531c0 48894557 0f57c9 488d4dd7'
    assert _setup(None,decode(code),0x79)==(0xd0,0x50,'0f')
    assert _setup(None,decode(code.replace(old,new)),0x79) is None


@pytest.mark.parametrize('change',['none','echo other','out of bounds','caller stack','wrong barrier','partial result'])
def test_converter_writes_only_private_stack_and_full_echoed_result(change):
    # Synthetic frame/base and relocation. Require all 32 result bytes and
    # the returned hidden address, independently of the setter's source type.
    raw='53 4883ec40 488bd9 0f1103 0f114b10 488d4c2420 31d2 e820000000 488bc3 4883c440 5b c3'
    seq=decode(raw); barrier=next(i.near_branch_target for i in seq if i.near_branch_target)
    if change=='echo other': raw=raw.replace('488bc3','488bc1')
    if change=='out of bounds': raw=raw.replace('0f114b10','0f114b18')
    if change=='caller stack': raw=raw.replace('488d4c2420','488d4c2450')
    if change=='wrong barrier': barrier+=4
    if change=='partial result': raw=raw.replace('0f114b10','0f114b08')
    assert _writes_only_result(decode(raw),{barrier}) == (change=='none')
