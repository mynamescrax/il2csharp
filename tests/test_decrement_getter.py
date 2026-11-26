from types import SimpleNamespace as NS

import pytest
from iced_x86 import Decoder

from il2cpp import Expr
from il2cpp.decrement_getter import _parameter_home


@pytest.mark.parametrize('prefix,ok', [('',True), ('89442448',False), ('488d4c2448 e800010000',False), ('4883ec08',False)])
def test_parameter_address_needs_the_original_spill(prefix,ok):
    t=(3,0x11<<16); m=NS(addr=0x1000,is_static=False,return_type=0)
    il=NS(types=[(0,1<<16),t],eh_regions=lambda _:None,_return_abi_is_known=lambda _:True,
          returns_sret=lambda _:False,_closed_type_key=lambda x:(0x11,3,0) if x==t else None,
          meta=NS(method_params=lambda _: [NS(name='player',type=1)]))
    seq=list(Decoder(64,bytes.fromhex('89542410 4883ec38 '+prefix+' 33d2 488d4c2448 e810000000'),ip=m.addr))
    lift=NS(il=il,_current_method=m,stack_values={'s_10':Expr('player',t,'obj')},slot_types={'s_10':t},
            _blocks=[NS(insns=seq)],rsp_delta=-0x38,_call_name=lambda _:'unrecognized')
    assert _parameter_home(lift,seq[-1],seq[-2],'s_10',16)==(t if ok else None)
