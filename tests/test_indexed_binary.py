"""Prove that a saved vector is one 12-byte value even on loop reentry."""
from iced_x86 import Decoder
import pytest

from il2cpp.captured_home import _normal_predecessors
from il2cpp.indexed_binary import _saved_pair,_echo_copy


@pytest.mark.parametrize('change',['unchanged','clobber XY','clobber Z','wrong Z offset','partial entry'])
def test_nonvolatile_pair_requires_one_live_getter(change):
    # Save a getter echo into XMM4+4 and R12D, then traverse a loop
    # containing an unrelated call. Changed reaching bytes must decline.
    use='f2440f11442438 4489642440';head='e8fb010000 f2440f1000 448b6008'
    if change=='wrong Z offset':head=head.replace('6008','6004')
    latch={'clobber XY':'450f57c0','clobber Z':'4531e4'}.get(change,'90')
    # Jump past the XY save along an alternate path into the Z definition.
    entry='750a' if change=='partial entry' else '90'
    raw=bytes.fromhex(entry+' '+head+' '+use+' e8fb010000 '+latch);back=-(len(bytes.fromhex(use))+5+len(bytes.fromhex(latch))+2)
    seq=list(Decoder(64,raw+b'\x75'+bytes([back%256])+b'\xc3',ip=0xab000));byip={i.ip:i for i in seq}
    result=_saved_pair(byip,_normal_predecessors(seq),seq[4],seq[5]);assert bool(result)==(change=='unchanged')


@pytest.mark.parametrize('change',['unchanged','nonvolatile scratch','bad copy','swapped base'])
def test_result_echo_must_cover_first_argument(change):
    raw='4533c0 488d542438 488d4c2468 f20f1008 8b4008 f20f114c2468 89442470 e800010000'
    if change=='nonvolatile scratch':raw=raw.replace('1008','1030').replace('114c','1174')
    if change=='bad copy':raw=raw.replace('4008','4004')
    if change=='swapped base':raw=raw.replace('114c2468','114c2438')
    seq=list(Decoder(64,bytes.fromhex(raw),ip=0x95000));assert _echo_copy(seq,(96,272,296))==((104,56) if change=='unchanged' else None)


@pytest.mark.parametrize('defect',['none','byref parameter','overlap','wrong echo','partial transfer','other method'])
def test_aggregate_returning_call_receives_full_by_value_input(defect):
    from types import SimpleNamespace as NS
    from il2cpp.expr import Expr
    from il2cpp.indexed_binary import unary_argument
    # Return a 24-byte struct at RBP+32 from a 12-byte argument at RSP+48,
    # copied from a third home. No Unity types, method names or game addresses.
    code='e8ab000000 4531c0 488d542430 488d4d20 f20f1018 8b4008 f20f115c2430 89442438 e8de010000'
    if defect=='partial transfer':code=code.replace('89442438','89442434')
    seq=list(Decoder(64,bytes.fromhex(code),ip=0x76800));call=seq[-1];arg=(1,0x11<<16);result=(2,0x11<<16)
    md=NS(return_type=1,param_count=1,is_static=True,generic_container=-1,addr=call.near_branch_target)
    key=lambda t:(0x11,t[0],int(bool(t[1]&(1<<29))))
    il=NS(_type_enum=lambda t:0x11,_closed_type_key=key,value_type_size=lambda _:12,addr_candidates={md.addr:[('method',0)]},
          meta=NS(methods=[md],method_params=lambda m:[NS(type=0)]),types=[arg,result],returns_sret=lambda t:t==result,_sf_field_size=lambda t,_:24)
    echo=Expr('&t11',arg,'ptr');echo._stack_offset=-160+(48 if defect=='overlap' else 80);bp=Expr('&home');bp._stack_offset=64-160
    witness=seq[0].ip,echo
    l=NS(il=il,_copied_frame=(64,144,160),rsp_delta=-160,slot_types={'t11':arg},regs={'RBP':bp,'RAX':echo},_last_sret=witness,_last_accessor_sret=witness)
    if defect=='byref parameter':il.types[0]=(1,arg[1]|1<<29)
    if defect=='wrong echo':l._last_accessor_sret=None
    if defect=='other method':md.addr+=1
    got=unary_argument(l,seq,1)
    if defect=='none':assert got[:2]==(seq[-3].ip,48) and got[2].text=='t11' and got[2].ty==arg
    else:assert got is None
