from types import SimpleNamespace as NS

from il2cpp.expr import Expr
from il2cpp.terminal_effect import terminal_statement


def test_later_invocation_is_not_evidence_that_an_earlier_pending_call_was_emitted():
    text='this.Poll()';recv=Expr('this',(1,0x12<<16),'obj');events=[]
    l=NS(meta=NS(methods=[NS(name='Poll',declaring=1)]), il=NS(_closed_type_key=lambda t:(0x12,1,0)),
         _cur_ip=0x300,_pending_calls=[(Expr(text),0x200,None)],emit=lambda ip,s,asm:events.append((ip,s)))
    assert not terminal_statement(l,(0,None),0,text,recv)
    assert not events and len(l._pending_calls)==1
    l._pending_calls=[]
    assert terminal_statement(l,(0,None),0,text,recv) and events==[(0x300,text+';')]
