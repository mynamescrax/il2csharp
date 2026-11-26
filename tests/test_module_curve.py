from types import SimpleNamespace as NS
import struct

import pytest
from iced_x86 import Decoder, Register as R

from il2cpp.binary import PE
from il2cpp.curve_bridge import _call_result, _BOOL, _ZERO
from il2cpp.module_curve import _chain_spans, _copy, _dead_scratch, _separate, probed_frame


def decode(raw):
    return list(Decoder(64, bytes.fromhex(raw), ip=0x8000))


def test_argument_copy_uses_two_distinct_homes_even_for_same_displacement_magnitude():
    # BP=SP+0xe0, BP-0x50=SP+0x90. The by-value argument is SP+0x50.
    code = '0f104520 4533c0 488d542450 0f104d30 488d4db0 0f29442450 0f294c2460'
    assert _copy(decode(code),0xe0) == (0x100,0x50,{R.RCX:0x90,R.RDX:0x50})


def test_check_byte_ranges_after_converting_both_bases():
    frame = (0x100,0x420)
    module, buf = (R.RBP,-0x60), (R.RBP,0x40)
    assert _separate(frame,module,buf,0x240,0x60) == [(0x60,32),(0xa0,8),(0x140,32),(0x240,32)]
    assert _separate(frame,module,buf,0x240,0xa0) is None    # aliased starting address
    assert _separate(frame,module,buf,0x240,0x90) is None    # high 16 bytes cover receiver
    assert _separate(frame,module,buf,0x150,0x60) is None    # partially overwritten sret
    assert _separate(frame,module,buf,0x418,0x60) is None    # beyond allocated frame


def test_successive_updates_can_reuse_only_the_whole_outgoing_argument():
    def update(module, output, edit, arg):
        return NS(spans=[(module,8),(output,32),(edit,32),(arg,32)],argument=arg)
    gas = update(0x98,0x150,0x250,0x60)
    smoke = update(0xa0,0x170,0x270,0x60)
    live = _chain_spans(gas,smoke)
    assert live.count((0x60,32)) == 1 and set(live) == set(gas.spans+smoke.spans)
    assert _chain_spans(gas,update(0xa0,0x160,0x270,0x60)) is None  # overlapping return buffers
    assert _chain_spans(gas,update(0xa0,0x170,0x270,0x70)) is None  # partial argument reuse
    assert _chain_spans(gas,update(0x60,0x170,0x270,0x110)) is None # reusing the old argument as receiver


@pytest.mark.parametrize('change', ['ok','wrong allocation','clobber eax','changed bp','extra sp change'])
def test_frame_requires_unwind_match_and_stable_bias(change):
    entry, helper, unwind = 0x2000,0x5000,0x8000
    head = bytes.fromhex('55 53 488dac2418ffffff b828100000')
    call = b'\xe8' + struct.pack('<i',helper-entry-len(head)-5)
    body = head + call + bytes.fromhex('482be0') + {
        'changed bp':bytes.fromhex('6689cd'), 'extra sp change':bytes.fromhex('4883ec08')}.get(change,b'')
    seq = list(Decoder(64,body+bytes.fromhex('4881c428100000 5b 5d c3'),ip=entry))
    length=len(head)+len(call)+3
    info=bytes((1,length,4,0, length,1))+struct.pack('<H',(0x1028 if change!='wrong allocation' else 0x1018)//8)+bytes((2,0x30,1,0x50))
    code=bytes.fromhex('33c0 c3' if change=='clobber eax' else '90 c3')
    image=PE.__new__(PE); image.is64=True; image.image_base=0
    image.read=lambda va,n: {helper:code,unwind:info}[va][:n]
    il=NS(bin=image,function_extent=lambda p:(p,p+len(code)),_eh4_begins=[entry],_eh4_entries=[(entry,seq[-1].next_ip,unwind)])
    result=probed_frame(NS(il=il,bin=image,_is_stack_probe=lambda p:p==helper),NS(addr=entry),[NS(insns=seq,preds=[])],set())
    assert result == ((0x1028-0xe8,0x1028) if change=='ok' else None)


@pytest.mark.parametrize('old,new', [
    ('0f104810','0f104808'),     # high half overlaps low half
    ('0f114d40','0f114d38'),     # overlap in destination
    ('0f104810','0f104910'),     # not the return address in RAX
    ('0f114d40','0f114540'),     # wrong incoming register
    ('0f104810','f30f104810'),   # only one float
    ('0f57c9','0f57c0'),        # does not set the float argument in XMM1
    ('0f114530','0f114530 e800000000'), # another call can observe or change the value
])
def test_incomplete_curve_copy_declines(old,new):
    raw='4531c0 488d4d30 0f1000 0f114530 0f104810 0f114d40 0f57c9'
    assert _copy(decode(raw),0xe0,True) is not None
    assert _copy(decode(raw.replace(old,new)),0xe0,True) is None


def test_reload_through_either_base_keeps_the_region_live():
    def dead(code):
        insns=decode(code+' c3')
        l=NS(il=NS(types=[None],_closed_type_key=lambda t:(1,0)),_current_method=NS(return_type=0),
             _blocks=[NS(insns=insns)])
        return _dead_scratch(l,insns[0].ip,[(0xa0,8),(0x60,32)],(0x100,0x278))
    assert dead('488b9c2410010000')         # unrelated epilogue restore
    assert not dead('488b5da0')              # BP-0x60, receiver
    assert not dead('488b9c24a0000000')      # SP+0xa0 aliases receiver
    assert not dead('488b5c2478')            # last eight bytes of the curve argument


@pytest.mark.parametrize('change',['none','missing float','wrong owner','context in wrong slot','byref','unknown target','sret'])
def test_heap_callback_needs_exact_register_arguments(change):
    # Instance (bool,float) -> float: RCX=this, DL=bool, XMM2=float,
    # R9=hidden context. A valid-looking bool is not a general pointer.
    call, = decode('e800020000'); target = call.near_branch_target
    method = NS(addr=target,declaring=0,is_static=False,generic_container=-1,flags=6,param_count=2,return_type=2)
    il = NS(addr_candidates={target:[('method',0)]},types=[(2,0),(0x0c,0),(0x0c,0)],_closed_type_key=lambda t:t,
            meta=NS(methods=[method],typedefs=[NS(generic_container=-1)],method_params=lambda m:[NS(type=0),NS(type=1)]))
    gprs={R.RCX:(0x12,0,0),R.RDX:_BOOL,R.R9:_ZERO}; floats={R.XMM2}
    if change=='missing float': floats={R.XMM1}
    elif change=='wrong owner': gprs[R.RCX]=_BOOL
    elif change=='context in wrong slot': gprs[R.R8]=gprs.pop(R.R9)
    elif change=='byref': il.types[0]=(2,1)
    elif change=='unknown target': il.addr_candidates={}
    elif change=='sret': il.types[2]=(0x11,3,0)
    assert _call_result(il,call,gprs,floats) == ((0x0c,0) if change=='none' else None)
