from types import SimpleNamespace as NS

from iced_x86 import Decoder
import pytest

from il2cpp.stack_literal import stack_literal


@pytest.mark.parametrize('raw,key,expected',[
    ('c644242001 f20f11442440',2,'true'),
    ('c744242000000000',2,'false'),('c644242002',2,None),
    ('c644242001 488944241d',2,None),('c644242001 ff442420',2,None),
    ('c644242001 8901',2,None),('c644242001 e800100000',2,None),
    ('488b0500100000 4889442420',14,'"A\\\"B"'),
    ('488b0500100000 b011 4889442420',14,None),('488b0500100000 89442420',14,None),
    ('488b0500100000 4889442420 c644242700',14,None),
])
def test_literal_needs_intact_stack_bytes(raw,key,expected):
    seq=list(Decoder(64,bytes.fromhex(raw),ip=0x8000))
    il=NS(_closed_type_key=lambda t:(t,0),meta=NS(string_literals=[None],string_literal=lambda n:'A"B'),
          decode_slot=lambda p:{'kind':5,'idx':0} if p==0x9007 else None)
    assert stack_literal(il,seq,len(seq),32,key)==expected
