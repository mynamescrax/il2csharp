from types import SimpleNamespace as NS

from iced_x86 import Decoder, Register as R

from il2cpp.toggle import _dead,_flags_dead


def graph(raw):
    s=list(Decoder(64,bytes.fromhex(raw),ip=0x1000));by={i.ip:i for i in s}
    succ={i.ip:tuple(k for k in (i.next_ip,) if k in by) for i in s}
    return s,by,succ


def test_second_branch_can_observe_carry_after_both_gprs_die():
    # TEST CL,CL sets CF=0. The first JE/JNE is modeled using the saved
    # Boolean, but mustn't manufacture a new truth value for a later JAE.
    test=Decoder(64,b'\x84\xc9').decode();s,by,succ=graph('b800000000 b900000000 7301 c3 c3')
    succ[s[2].ip]=(s[3].ip,s[4].ip)
    assert _dead(None,by,succ,s[0].ip,R.RAX) and _dead(None,by,succ,s[0].ip,R.RCX)
    assert not _flags_dead(None,by,succ,s[0].ip,test.rflags_modified)


def test_void_call_does_not_certify_upper_rax_overwrite():
    s,by,succ=graph('e8fb0f0000 0fb6cc c3');md=NS(addr=0x2000,return_type=0)
    lift=NS(meta=NS(methods=[md]),il=NS(addr_candidates={0x2000:[('method',0)]},types=[(0,1<<16)],_closed_type_key=lambda t:(1,0)),
            _call_name=lambda va:'Callback',_named_raise_throw=lambda va,name:None)
    assert not _dead(lift,by,succ,s[0].ip,R.RAX)
