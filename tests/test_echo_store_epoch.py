from types import SimpleNamespace as NS

from iced_x86 import Decoder
import pytest

from il2cpp.echo_field import emit_copy
from il2cpp.expr import Expr, _R4_TY


@pytest.mark.parametrize('change', ['none','stale echo','other home','missing W','wrong tile','overlap'])
def test_full_destination_store_needs_current_echo_and_four_distinct_dwords(change):
    load, store = Decoder(64, bytes.fromhex('0f10000f114338'), ip=0x1000)
    ty = (17,0x11<<16); echo = Expr('&t1000',ty,'ptr'); echo._stack_offset = -24
    layout = {16+n*4:(c,0) for n,c in enumerate('rgba')}
    parts = [(n*4,Expr('t1000.'+c,_R4_TY,'float'),0,4) for n,c in enumerate('rgba')]
    expected = echo
    if change == 'stale echo':expected = Expr(echo.text,ty,'ptr')
    if change == 'other home':echo._stack_offset += 8
    if change == 'missing W':parts.pop()
    if change == 'wrong tile':parts[1] = (4,Expr('t1001.g',_R4_TY,'float'),0,4)
    if change == 'overlap':parts[1] = (0,parts[1][1],0,4)
    events=[]; packed=Expr('?',None,'bits');packed._parts=parts
    l=NS(regs={'RAX':echo,'RBX':Expr('this')},_last_sret=(0xff0,expected),slot_types={'t1000':ty},rsp_delta=-56,
         il=NS(instance_field_chain=lambda _:layout),_aggregate_load=lambda _:packed,
         _kill_stale=lambda dest:events.append(dest),emit=lambda ip,s,_:events.append(s))
    assert emit_copy(l,store,(0xff0,load,ty,'this.color',32,56)) == (change=='none')
    assert events==(['this.color','this.color = t1000;'] if change=='none' else [])
