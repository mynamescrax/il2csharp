"""Render a material write only on the snapshotted getter result."""
from types import SimpleNamespace as NS

import pytest

from il2cpp import Expr
from il2cpp.material_setter import assignment


@pytest.mark.parametrize('case', ['field', 'constructed', 'new receiver', 'other material', 'other type', 'hidden input'])
def test_material_assignment_keeps_operand_identity(case):
    receiver_ty = (5,0x12 << 16); material_ty = (6,0x12 << 16)
    renderer = Expr('t17',receiver_ty,'obj')
    rhs = None if case == 'constructed' else 'this.finish'
    value = Expr(rhs or 't18', material_ty,'obj')
    regs = {'RCX':renderer, 'RDX':value, 'R8':Expr('0')}
    if case=='new receiver': regs['RCX']=Expr(renderer.text,renderer.ty,renderer.kind)
    if case=='other material': regs['RDX']=Expr('this.old',material_ty,'obj')
    if case=='other type': regs['RDX']=Expr(value.text,receiver_ty,'obj')
    if case=='hidden input': regs['R8']=Expr('context')
    lift = NS(il=NS(_closed_type_key=lambda t:(0x12,t[0],0)),regs=regs,
              _material_sites={2:(1,rhs,6,5)}, _material_values={1:renderer})
    result=assignment(lift,NS(ip=2))
    assert result == (f't17.sharedMaterial = {value.text} /* shared implementation */;' if case in ('field','constructed') else None)
