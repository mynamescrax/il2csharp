import pytest
from iced_x86 import Decoder,Register as R

from il2cpp.framed_cleanup import _frame_pair


@pytest.mark.parametrize('change',[None,'incorrect SP','shifted home','different push','overlapping saves','bool from other byte','receiver overwritten'])
def test_r11_restores_entry_stack_and_preserves_forwarded_arguments(change):
    # Synthetic 0x100-byte frame. In post-allocation coordinates, BP is
    # +0xc0, the pushed RBP is at +0x100, and the first home is at +0x110.
    start=bytes.fromhex('48895c2408 4889742410 48897c2418 55 488d6c24c0 4881ec00010000 '
                        '80790800 410fb6f8 488bf2 488bd9 7400')
    end=bytes.fromhex('4531c9 440fb6c7 488bd6 488bcb 4c8d9c2400010000 '
                      '498b5b10 498b7318 498b7b20 498be3 5d e900030000')
    if change=='incorrect SP': end=end.replace(bytes.fromhex('9c2400010000'),bytes.fromhex('9c2408010000'))
    if change=='shifted home': end=end.replace(bytes.fromhex('5b10'),bytes.fromhex('5b08'))
    if change=='different push': start=start.replace(bytes.fromhex('55 488d'),bytes.fromhex('57 488d'))
    if change=='overlapping saves': start=start.replace(bytes.fromhex('742410'),bytes.fromhex('742408'))
    if change=='bool from other byte': end=end.replace(bytes.fromhex('0fb6c7'),bytes.fromhex('0fb6c6'))
    if change=='receiver overwritten': end=end.replace(bytes.fromhex('488bcb'),bytes.fromhex('488bce'))
    enter=list(Decoder(64,start,ip=0x1000));leave=list(Decoder(64,end,ip=enter[-1].next_ip))
    assert _frame_pair(enter,leave)==((0x100,0xc0,R.RBX) if change is None else None)
