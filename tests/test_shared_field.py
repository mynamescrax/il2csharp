from types import SimpleNamespace as NS

import pytest

from il2cpp import Expr
from il2cpp.binary import PE
from il2cpp.shared_field import _scratch_lane, saved_fp_consumers, shared_field_read
from iced_x86 import Decoder


def probe(*, code='488b4118c3', private=True, virtual=False, overlap=False,
          return_index=1, recv='this', extra='0', own=False):
    va = 0x4000
    image = PE.__new__(PE)
    image.is_exec_va = lambda p: p == va
    image.read = lambda p,n: bytes.fromhex(code)[:n]
    field_name = '<Parent>k__BackingField' if private else 'parent'
    ty = (2, (0x12 << 16) | (1 if private else 6))
    types = [ty, (2, 0x12 << 16), (0, 0x0a << 16)]
    child = NS(is_valuetype=False, generic_container=-1, flags=1, parent=1, fields=[1] if overlap else [])
    base = NS(is_valuetype=False, generic_container=-1, flags=1, parent=-1, fields=[0],
              method_start=0, method_count=1, property_start=0, property_count=1)
    m = NS(name='get_Parent', addr=va, declaring=1, generic_container=-1, is_static=False,
           param_count=0, return_type=return_index, flags=4 | (0x40 if virtual else 0))
    meta = NS(typedefs=[child,base], fields=[NS(name=field_name,type=0), NS(name='overlap',type=0)],
              properties=[('Parent',0,-1)], methods=[m,NS(declaring=2)], type_fields=lambda td:td.fields,
              getstr=lambda s:s)
    il = NS(meta=meta,bin=image,addr_candidates={va:[('method',0),('method',1)]},
            types=types, field_offsets=[[0x14] if overlap else [],[0x18]],
            base_chain_tds=lambda t: (1,) if t==1 else (0,1),
            _sf_field_size=lambda t,depth:8, _type_enum=lambda t:t[1] >> 16 & 255,
            _source_field_names={0:'__field_Parent' if private else 'parent'})
    receiver = int(own)
    lift = NS(il=il, _current_method=NS(is_static=False, declaring=receiver))
    return shared_field_read(lift, va, [Expr(recv, (receiver, 0x12 << 16), 'obj'), Expr(extra)], [])


def test_shared_leaf_reads_accessible_storage_or_verified_backing_getter():
    assert probe()[0] == 'base.Parent'
    assert probe(private=False)[0] == 'base.parent'
    assert probe(own=True)[0] == 'this.__field_Parent'


@pytest.mark.parametrize('changes', [dict(code='8b4118c390'), dict(code='488b4118cc'),
                                     dict(code='488b4120c3'), dict(overlap=True), dict(virtual=True),
                                     dict(recv='other'), dict(extra='SideEffect()'), dict(return_index=2)])
def test_inexact_field_read_declines(changes):
    assert probe(**changes) is None


@pytest.mark.parametrize('bad', [None, 'deferred getter', 'reference receiver', 'missing lane', 'wrong width', 'unbound arithmetic'])
def test_discarded_xmm_cannot_conceal_a_deferred_read(bad):
    vector = (2,(0x12 if bad=='reference receiver' else 0x11)<<16)
    scalar = (3, 0x0c<<16 | 6)
    meta = NS(typedefs=[None,None,NS(is_valuetype=True,generic_container=-1)], type_fields=lambda _: [0],
              fields=[NS(type=0,name='x')])
    il=NS(meta=meta, types=[scalar], _source_field_names={0:'x'},
          _closed_type_key=lambda t:(0x0c,0) if t==scalar else (t[1]>>16,t[0],0))
    lift=NS(il=il,_var_types={'t1':vector,'t2':scalar})
    lane=Expr('t1.x * t2',scalar,'float')
    pack=Expr('?',None,'bits'); pack._parts=[(n*4,lane,0,4) for n in range(4)]
    if bad=='deferred getter': pack._parts[-1]=(12,Expr('t1.Fetch().x',scalar,'float'),0,4)
    if bad=='missing lane': pack._parts.pop()
    if bad=='wrong width': pack._parts[1]=(4,lane,0,8)
    if bad=='unbound arithmetic': del lift._var_types['t2']
    assert _scratch_lane(lift,pack)==(bad is None)


@pytest.mark.parametrize('save,match', [('0f28f0', True), ('0f28e0', False),
                                        ('0f28f1', False), ('f30f10f0', False)])
def test_scalar_capture_requires_full_nonvolatile_save_from_result(save, match):
    code = bytes.fromhex('e800100000 33d2 488bcb ' + save + ' e800200000')
    ins = list(Decoder(64, code, ip=0x1000))
    expected = {0x1000: (ins[-1].near_branch_target, 'RBX')} if match else {}
    assert saved_fp_consumers([NS(insns=ins)]) == expected
    # A jump into the save or field call breaks the producer/use witness.
    assert not saved_fp_consumers([NS(insns=ins[:3]), NS(insns=ins[3:])])
