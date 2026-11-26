from struct import pack
from types import SimpleNamespace as NS

import pytest

from il2cpp.binary import PE
from il2cpp.expr import Expr
from il2cpp.static_getter import static_getter


def wrapper(va, flag, load, init, *, store=None, slot=0x7000):
    code = bytearray.fromhex('4883ec28')
    def rel(hexbytes, target, tail=''):
        code.extend(bytes.fromhex(hexbytes))
        suffix = bytes.fromhex(tail)
        code.extend(pack('<i', target - (va + len(code) + 4 + len(suffix))))
        code.extend(suffix)
    rel('803d', flag, '00')
    code.extend(b'\x75\x13')
    rel('488d0d', slot)
    rel('e8', init)
    rel('c605', flag if store is None else store, '01')
    rel('488b05', load)
    return bytes(code) + bytes.fromhex('488b80b8000000 488b00 4883c428 c3')


def probe(*, load=0x7000, store=None, init=0x8000, getter_slot=0x7000, flags=0x96,
          cctor=False, extra='&data_1111'):
    va, getter = 0x1000, 0x1200
    code = {va:wrapper(va, 0x3010, load, init, store=store),
            getter:wrapper(getter, 0x4000, getter_slot, 0x8000, slot=getter_slot)}
    image = PE.__new__(PE)
    image.is_exec_va = lambda v:v in code
    image.read = lambda v,n:code[v][:n]
    ty = (0, 0x12 << 16)
    td = NS(generic_container=-1, declaring=-1, is_valuetype=False, flags=1, has_cctor=cctor,
            field_count=2, property_start=0, property_count=1, method_start=0, method_count=1)
    md = NS(name='get_Current', declaring=0, flags=flags, is_static=True, addr=getter,
            generic_container=-1, return_type=0, param_count=0)
    meta = NS(version=31, typedefs=[td], fields=[NS(name='Limit', type=2), NS(name='<Current>k__BackingField', type=1)],
              type_fields=lambda _: [0,1], properties=[('Current',0,-1)], getstr=lambda s:s, methods=[md])
    il = NS(bin=image, meta=meta, types=[ty,(0,ty[1]|0x11),(1, (8<<16)|0x51)], field_offsets=[[0,0]],
            addr_to_method={},addr_candidates={},function_extent=lambda v:(v,v+len(code[v])),
            decode_slot=lambda s:{'kind':1,'type':ty,'td':0} if s==0x7000 else None,
            type_name=lambda t:'Demo.Manager', _type_enum=lambda t:(t[1]>>16)&255)
    return static_getter(NS(il=il,rt_init_meta=0x8000), va, [Expr(extra)], [])


def test_snapshot_type_and_accessible_property_come_from_the_same_static_slot():
    assert probe() == ('Demo.Manager.Current',(0,0x12<<16))


@pytest.mark.parametrize('changes', [dict(load=0x7100),dict(store=0x3011),dict(init=0x8001),
                                     dict(getter_slot=0x7100),dict(flags=0x91),dict(cctor=True),
                                     dict(extra='SideEffect()')])
def test_unproven_accessor_twin_declines(changes):
    assert probe(**changes) is None
