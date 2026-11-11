"""Same-body String aliases can render their common equality behavior."""
import pytest

from il2cpp import Expr
from test_game_goldens import game_decompiler


pytestmark = pytest.mark.game


def test_shared_string_equality_accepts_only_exact_aliases_and_typed_args(
        game_decompiler):
    il, dec = game_decompiler
    cands = il.addr_candidates[0x181AF7520]
    string_type = il.types[next(iter(il.meta.method_params(il.meta.methods[602]))).type]
    first = Expr('this.name', string_type, 'str')
    literal = Expr('"walk"', None, 'str')
    gate = dec.L._shared_string_equality

    assert gate(cands, [first, literal, Expr('0', None, 'int')], [])
    assert not gate(cands[:1], [first, literal], [])
    assert not gate(cands, [Expr('obj1', None, 'obj'), literal], [])
    assert not gate(cands, [first, Expr('Call()', None, 'obj')], [])
    assert not gate(cands, [first, literal, Expr('Call()', None, 'obj')], [])


def test_effectful_string_operand_keeps_its_evaluation(game_decompiler):
    il, dec = game_decompiler
    method = il.meta.methods[144]
    assert method.name == 'ReadReference'
    body = '\n'.join(dec.lift_method(method, il.meta.typedefs[method.declaring]))
    assert body.count('this.ReadName() == ') == 5
    assert 'sub_181af7520/*shared body' not in body
