"""IsInst tail jumps to the proved helper fold exactly like calls do.

Ground truth: System.Attribute.GetCustomAttributes (mi 3446) tail-jumps
to 0x180434690 with a klass-kind bare `typeof(System.Attribute[])`
klass; the `_call` intrinsic has folded that shape all along, but the
dec direct-tail path rendered the honest `sub_` form. The tail-path
mirror fold renders `(obj as T)` and drops the spray tail. Opaque
klass tails (field/static klass sources) keep `sub_`: mi 200 still
carries its static-field klass load.
"""
import pytest

from test_game_goldens import game_decompiler

pytestmark = pytest.mark.game


def test_tail_typeof_folds_to_as(game_decompiler):
    il, dec = game_decompiler
    m = il.meta.methods[3446]
    assert m.name == 'GetCustomAttributes'
    text = '\n'.join(dec.lift_method(m, il.meta.typedefs[m.declaring]))
    assert 'sub_180434690' not in text
    # fix 125/126 re-pin: the temp copy is dropped, so the `as` wraps the call.
    assert ('(element.GetCustomAttributes(System.Type.GetTypeFromHandle('
            'typeof(System.Attribute)), inherit) as System.Attribute[])') in text


def test_field_klass_tail_declines(game_decompiler):
    il, dec = game_decompiler
    m = il.meta.methods[200]
    text = '\n'.join(dec.lift_method(m, il.meta.typedefs[m.declaring]))
    assert 'sub_180434690(tailoringInfo1,' in text
