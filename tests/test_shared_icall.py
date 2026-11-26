"""An address collision or an icall name alone cannot prove a public alias."""
from types import SimpleNamespace as NS

import pytest

from il2cpp import Expr
from il2cpp.shared_icall import shared_icall
from synth_x64 import Asm, BASE


CELL, STRING, RESOLVE = BASE + 512, BASE + 600, BASE - 128
INT, BOOL, ENUM = (0, 8 << 16), (0, 2 << 16), (1, 0x11 << 16)


def fixture(*, store=CELL, resolver=RESOLVE, branch='7513', public_flags=0x96,
            other_param=1, others=False, signature='Example.Input::Read(Example.Key)'):
    a = Asm().raw('4053').sub_rsp(32).mov_rax_rip(CELL).raw('8bd9').test_rax_rax()
    code = a.raw(branch).lea_rcx(STRING).call(resolver).mov_rip_rax(store).raw(
        '8bcb4883c4205b48ffe0').assemble()
    def method(name, flags, p):
        return NS(name=name, addr=BASE, flags=flags, is_static=True, return_type=0,
                  declaring=0, generic_container=-1, param_count=1, p=p)
    rows = [method('Read', 0x91, other_param), method('Get', public_flags, 1)]
    il = NS(meta=NS(methods=rows, typedefs=[NS(flags=1, declaring=-1, generic_container=-1),
                                           NS(is_enum=True)], method_params=lambda m: [NS(type=m.p)]),
            addr_candidates={BASE: [('method', 0), ('method', 1)] + ([('generic', 0)] if others else [])},
            types=[BOOL, ENUM, INT], type_name=lambda t: 'Example.Key' if t == ENUM else 'int',
            _type_enum=lambda t: t[1] >> 16 & 255, value_type_size=lambda _: 4,
            icall_cells={CELL: signature}, rt_icall_resolve=RESOLVE,
            function_extent=lambda _: (BASE, BASE + len(code)),
            bin=NS(read=lambda va,n: code, cstr=lambda va,n: signature if va == STRING else None),
            _icall_annotation=lambda sig: {'method': 0}, _icall_sig_params=lambda sig: [sig.split('(')[1][:-1]],
            _icall_type_key=lambda t:t, typedef_full=lambda idx:'Example.Input',
            enum_members=lambda idx:{87: 'W'})
    return NS(il=il)


def call(lift, text='87', ty=None):
    return shared_icall(lift, BASE, [text], [Expr(text, ty, 'int')])


def test_equivalent_icall_does_not_select_an_owner():
    lift = fixture()
    assert call(lift) == 'Example.Input.Get(Example.Key.W) /* shared icall */'
    assert call(lift, 'key', ENUM) == 'Example.Input.Get(key) /* shared icall */'
    assert call(lift, 'code', INT) == 'Example.Input.Get(unchecked((Example.Key)(code))) /* shared icall */'
    assert call(lift, 'MakeFloat()', (0, 0x0c << 16)) is None
    assert call(lift, '87f', (0, 0x0c << 16)) is None
    assert call(lift, 'other', (2, 0x11 << 16)) is None
    lift._current_method = NS(addr=BASE)
    assert call(lift) is None  # would recurse from the wrapper itself


@pytest.mark.parametrize('changes', [
    {'store': CELL + 8}, {'resolver': RESOLVE + 1}, {'branch': '7512'},
    {'public_flags': 0x91}, {'other_param': 2}, {'others': True},
    {'signature': 'Example.Input::Read(System.Single)'},
])
def test_near_miss_keeps_unresolved_call(changes):
    assert call(fixture(**changes)) is None


@pytest.mark.parametrize('change',[None,'truncated address','swapped refs','wrong signature','by value','out only','wrong cell'])
def test_writable_ref_alias_requires_full_pointer_forwarding_and_exact_signature(change):
    from il2cpp.shared_icall import vector_ref_pair
    name='UnityEngine.Vector3';sig=name+'::OrthoNormalize2('+name+'&,'+name+'&)' if change!='wrong signature' else 'Other()'
    a=Asm().raw('48895c2408 57').sub_rsp(32).mov_rax_rip(CELL)
    save='488bda488bf9' if change!='truncated address' else '8bda488bf9'
    restore='488bd3488bcf' if change!='swapped refs' else '488bc3488bd7'
    code=a.raw(save).test_rax_rax().raw('7513').lea_rcx(STRING).call(RESOLVE).mov_rip_rax(CELL+8 if change=='wrong cell' else CELL).raw(restore+'488b5c24304883c4205f48ffe0').assemble()
    ty=(1,(0x11<<16) | (0 if change=='by value' else 1<<29) | (2 if change=='out only' else 0))
    methods=[NS(name=n,addr=BASE,flags=f,iflags=i,is_static=True,generic_container=-1,declaring=1,return_type=0,param_count=2)
             for n,f,i in [('OrthoNormalize2',0x91,0x1000),('OrthoNormalize',0x96,0)]]
    il=NS(meta=NS(methods=methods,method_params=lambda m:[NS(type=1),NS(type=1)]),types=[(0,1<<16),ty],
          _closed_type_key=lambda t:(1,0) if t[0]==0 else (0x11,1,t[1]>>29), typedef_full=lambda _:name,
          addr_candidates={BASE:[('method',0),('method',1)]},icall_cells={CELL:sig},rt_icall_resolve=RESOLVE,
          bin=NS(read=lambda *_:code,cstr=lambda p,_:sig if p==STRING else None),function_extent=lambda va:(va,va+len(code)),
          _icall_annotation=lambda _:{'method':0})
    assert vector_ref_pair(il,BASE) == ((1,ty) if change is None else None)
