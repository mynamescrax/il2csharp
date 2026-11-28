from types import SimpleNamespace as NS

from iced_x86 import Decoder
import pytest

from il2cpp.expr import Expr, _INT_TY, _R4_TY
from il2cpp.scalar_ratio import ratio_step


@pytest.mark.parametrize('invalid', ['left missing','right missing','left overwritten','right overwritten','none'])
def test_quotient_requires_both_live_dword_moves(invalid):
    ins=Decoder(64,bytes.fromhex('f30f5ed0'),ip=0x1050).decode()
    a,b=Expr('width',_INT_TY,'int'),Expr('height',_INT_TY,'int')
    regs={'XMM2':a,'XMM0':b};saved={0x1030:a,0x1040:b}
    if invalid=='left missing':del saved[0x1030]
    if invalid=='right missing':del saved[0x1040]
    if invalid=='left overwritten':regs['XMM2']=Expr(a.text,a.ty,a.kind)
    if invalid=='right overwritten':regs['XMM0']=Expr(b.text,b.ty,b.kind)
    before=dict(regs)
    assert ratio_step(NS(regs=regs),ins,('divide',(0x1030,0x1040)),saved)==(invalid=='none')
    if invalid!='none':assert regs==before
    else:
        assert regs['XMM2'].ty==regs['XMM0'].ty==_R4_TY
        assert '(float)(width) / (float)(height)' in regs['XMM2'].text
