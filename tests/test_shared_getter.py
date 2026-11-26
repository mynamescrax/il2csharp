from types import SimpleNamespace as NS

import pytest

from il2cpp import Expr
from il2cpp.binary import PE
from il2cpp.shared_getter import shared_getter


def probe(*, code='8b4118c3', flags=0x886, prop='Position', recv_td=0, extra='0', here=0):
    addr = 0x2000
    data = bytes.fromhex(code)
    image = PE.__new__(PE)
    image.read = lambda p,n:data[p-addr:p-addr+n]
    image.is_exec_va = lambda p:p==addr
    def method(name, flags):
        return NS(addr=addr, declaring=0, name='get_'+name, is_static=False, param_count=0,
                  generic_container=-1, return_type=0, flags=flags)
    td = NS(is_valuetype=False, flags=1, declaring=-1, generic_container=-1, property_count=2,
            property_start=0, method_count=2, method_start=0)
    meta = NS(typedefs=[td], methods=[method('Inner',0x884),method('Position',flags)],
              properties=[('Inner',0,-1),(prop,1,-1)],getstr=lambda x:x)
    il = NS(meta=meta,bin=image,types=[(0,8<<16)],addr_candidates={addr:[('method',1),('method',0)]},
            _type_enum=lambda ty:ty[1]>>16&255,function_extent=lambda va:(addr,addr+len(data)))
    receiver = Expr('this.field',(recv_td,0x12<<16),'obj')
    return shared_getter(NS(il=il,_current_method=NS(addr=here)),addr,[receiver.text],[receiver,Expr(extra)],[])


def test_public_alias_replaces_shared_getters():
    assert probe() == '__accget(this.field.Position) /* shared getter */'


def test_unused_scalar_constant_is_not_an_effectful_argument():
    assert probe(extra='1.0f') == probe()
    assert probe(extra='ReadScale() * 1.0f') is None


@pytest.mark.parametrize('change', [dict(code='4885c974048b4118c38b02c3'),  # alternate arm reads RDX
                                    dict(flags=0x8c6), dict(flags=0x884), dict(prop='Other'),
                                    dict(recv_td=1), dict(extra='Advance()'), dict(here=0x2000)])
def test_need_context_independence_and_accessible_nonvirtual_getter(change):
    assert probe(**change) is None
