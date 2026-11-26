"""A typed consumer identifies the wrapper only if it borrows the returned eight bytes."""
from types import SimpleNamespace as NS

from iced_x86 import Decoder, Mnemonic as M
import pytest

from il2cpp.binary import PE
from il2cpp.expr import Expr
from il2cpp.module_getter import module_getter


def recover(*, path='scalar', change=''):
    code = {'scalar':'31d2 4889442460 488d4c2460',
            'setter':'4531c0 4889442460 0f57c9 488d4c2460',
            'buffer':'4531c0 4889442460 488d542460 488d4c2440'}[path]
    variants = {'truncated': ('4889442460','89442460'), 'overwritten': ('4889442460','4889442460 894c2464'),
                'wrong home': ('488d4c2460','488d4c2458'), 'call in between': ('4889442460','4889442460 e800020000'),
                'wrong hidden': ('4531c0','31d2'), 'overlap': ('488d4c2440','488d4c2458'),
                'sret reversed': ('488d542460 488d4c2440','488d4c2460 488d542440')}
    if change in variants:
        code = code.replace(*variants[change])
    if change=='unproven frame':
        code=code.replace('4889442460','48894560').replace('488d4c2460','488d4d60')
    seq = list(Decoder(64, bytes.fromhex('4885c9 7440 31d2 e800010000 '+code+' e800020000'), ip=0x2400))
    nullcheck = NS(insns=seq[:2]); block = NS(insns=seq[2:],preds=[0])
    calls = [i for i in seq if i.mnemonic == M.CALL]
    producer, consumer = calls[0], calls[-1]
    addr, use = producer.near_branch_target, consumer.near_branch_target
    # Two accessible getters of the SAME owner return different one-reference value types.
    owner, other, module = range(3)
    types = [(owner,0x12<<16),(other,0x11<<16),(module,0x11<<16),(0,8<<16),(0,1<<16),(0,0x0c<<16)]
    td = [NS(index=n,is_valuetype=n!=owner,is_enum=False,flags=2 if n!=owner else 1,generic_container=-1,field_count=1) for n in range(3)]
    def method(va,dec,ret,p):
        return NS(addr=va,declaring=dec,return_type=ret,param_count=p,is_static=False,flags=6,generic_container=-1)
    ret = {'scalar':3,'setter':4,'buffer':1}[path]
    methods=[method(addr,owner,2 if change=='ambiguous result' else 1,0),method(addr,owner,2,0),method(use,module,ret,int(path=='setter'))]
    meta=NS(typedefs=td, methods=methods, type_fields=lambda t:[0], fields=[NS(type=0)], method_params=lambda m:[NS(type=5)] if m.param_count else [])
    image=PE.__new__(PE);image.is64=True;image.is_exec_va=lambda p:p==addr
    # No copied game bytes or fixture addresses: model the accepted wrapper, with a relocated barrier.
    image.read=lambda p,n: bytes.fromhex('4883ec28 48894c2430 488bd1 488d4c2430 e810000000 488b442430 4883c428 c3')
    il=NS(bin=image,meta=meta,types=types,field_offsets=[[16]]*3, addr_candidates={addr:[('method',0),('method',1)],use:[('method',2)]},
          function_extent=lambda p:(p,p+32),_nested_owner=lambda t:owner, value_type_size=lambda t:8,
          instance_field_chain=lambda t:{16:('source',0)}, _closed_type_key=lambda t:(t[1]>>16,t[0],0) if t[1]>>16 in (0x11,0x12) else (t[1]>>16,0),
          _return_abi_is_known=lambda t:True,returns_sret=lambda t:path=='buffer' and t==types[1],
          _sf_field_size=lambda t,d:16 if t==types[1] else 8)
    lift=NS(il=il,out=NS(block=block),_blocks=[nullcheck,block],_module_reads={},rt_wbarrier={addr+22+16+(change=='wrong barrier')},
            _accessor_prop=lambda mi:[('get','alpha',0),('get','beta',0),('set' if path=='setter' else 'get','attr',0)][mi])
    return module_getter(lift,producer,[Expr('source',types[0],'obj'),Expr('0'),None,None],[])


@pytest.mark.parametrize('path',['scalar','setter','buffer'])
def test_exact_module_of_borrowed_receiver_wins_over_first_alias(path):
    assert recover(path=path) == ('__accget(source.beta) /* shared getter */',(2,0x11<<16))


@pytest.mark.parametrize('path,change',[('scalar','truncated'),('scalar','overwritten'),('scalar','wrong home'),
                                       ('scalar','call in between'),('setter','wrong hidden'),('buffer','overlap'),
                                       ('buffer','sret reversed'),('scalar','wrong barrier'),('scalar','ambiguous result'),
                                       ('scalar','unproven frame')])
def test_unproved_receiver_use_preserves_marker(path,change):
    assert recover(path=path,change=change) is None
