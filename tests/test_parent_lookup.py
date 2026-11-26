from types import SimpleNamespace as NS

import pytest
from iced_x86 import Decoder

from il2cpp.awaiter import _unused_return
from il2cpp.parent_lookup import _same_entry


@pytest.mark.parametrize('suffix,dead', [('488bd8 c3',True), ('f30f11442420 c3',False)])
def test_closed_parent_lookup_supplies_rax_but_does_not_prove_xmm0_dead(suffix,dead):
    start=0x1000; seq=list(Decoder(64,bytes.fromhex('488b1500010000 488bcb e800010000 '+suffix),ip=start))
    lift=NS(_blocks=[NS(insns=seq)],_parent_lookup_windows={start:seq[2].next_ip})
    assert _unused_return(lift,start)==dead


@pytest.mark.parametrize('change',['same helper','different helper','different condition'])
def test_relocated_append_clone_needs_same_operations_and_destinations(change):
    def code(addr,helper,branch):
        return bytes.fromhex('4885c9')+bytes([branch,5,0xe8])+(helper-(addr+10)).to_bytes(4,'little',signed=True)+b'\xc3'
    a,b=0x1000,0x2000
    images={a:code(a,0x3000,0x74),b:code(b,0x3000+(change=='different helper'),0x75 if change=='different condition' else 0x74)}
    il=NS(bin=NS(is_exec_va=lambda p:p in images,read=lambda p,n:images[p][:n]),function_extent=lambda p:(p,p+len(images[p])))
    assert _same_entry(il,a,b)==(change=='same helper')
