"""The on-disk case offsets must survive PE base relocation unchanged."""
from struct import pack,pack_into
from types import SimpleNamespace as NS

import pytest

from il2cpp.bounded_switch import _unrelocated


@pytest.mark.parametrize('word,want',[(0xa078,True),(0xa07c,False),(0xa08b,False),(0xa08c,True),
                                     (0x0080,True),(0x3080,False)])
def test_table_requires_unmodified_interval(word,want):
    base=0x180000000;pe=0x80;opt=pe+24;d=bytearray(0x200)
    pack_into('<I',d,0x3c,pe);d[pe:pe+6]=b'PE\0\0\x64\x86';pack_into('<H',d,pe+20,240)
    pack_into('<H',d,opt,0x20b);pack_into('<I',d,opt+108,16);pack_into('<II',d,opt+152,0x3000,12)
    reloc=pack('<IIHH',0x1000,12,word,0)
    binary=NS(d=d,image_base=base,sections=[NS(addr=base+0x3000,size=12,rawsize=12)],
              read=lambda va,n:reloc if (va,n)==(base+0x3000,12) else None)
    assert _unrelocated(binary,base+0x1080,base+0x108c) is want
