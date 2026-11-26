"""Conflicting cell evidence stays unknown even on a repeated scan."""
from types import SimpleNamespace as NS
from il2cpp.runtime.fields import _FieldsMixin
from synth_x64 import Asm


def test_one_cell_must_agree_at_every_resolver_fill():
    il=_FieldsMixin();base=0x9000;x,y=0x8500,0x8508;sig=0xa000;helper=0xc000
    section=NS(addr=base,is_exec=True,is_bss=False,rawsize=0)
    il.bin=NS(sections=[section],qword=lambda p:None,cstr=lambda p,n:{sig:'A::First()',sig+16:'B::Other()'}.get(p))
    il.bss_usage_map={};il._icall_annotation=lambda s:{'kind':3,'text':s,'icall':True}
    def scan(*sites):
        asm=Asm(base)
        for signature,h,cell in sites:asm.lea_rcx(signature).call(h).mov_rip_rax(cell)
        raw=asm.data(b'\xcc'*32).assemble();section.rawsize=len(raw);il.bin.read=lambda p,n:raw[p-base:p-base+n];il.scan_icall_cache()
    A=(sig,helper,x);B=(sig+16,helper,x);Y=(sig,helper,y)
    scan(A,Y);assert il.decode_slot(x)['text']=='A::First()'
    il.bss_usage_map[x]=il._icall_annotation('A::First()')
    scan(A,B,A,Y,Y);assert il.icall_cells=={y:'A::First()'} and il.decode_slot(x) is None
    assert il.decode_slot(y)['text']=='A::First()' and il.rt_icall_resolve==helper
    scan(B,Y);assert il.decode_slot(x)['text']=='B::Other()'  # cached miss invalidated
    scan(A,(sig+16,helper+32,y));assert not il.icall_cells and il.rt_icall_resolve is None
    scan();assert il.decode_slot(x) is None and il.decode_slot(y) is None and il.rt_icall_resolve is None
