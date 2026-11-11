"""Element-class IsInst fold: `sub_x(obj, elemclass(arr))` -> `obj as E`.

Ground truth: the klass argument `[arrklass+0x40]` is
Il2CppClass.element_class. A same-method newarr fixes the array's
runtime klass to exactly E[] (array covariance is why params, fields,
statics and `as`-refinements can never prove this), so the fold fires
only with newarr provenance; everything else keeps the honest marker.
mi 84 (Type[]) and mi 471 (BigInteger[]) fold and absorb; mi 30694
folds the allocated array but keeps the field-loaded one; object
elements (mi 2717/4020), `as`-refined arrays (mi 10829), static fields
(mi 200) and unknown provenance (mi 7021/32342) decline. Closed
generic-instance elements (slice 1: mi 113247/105419/123638) fold the
same way; nested arrays (mi 102073) decline.
"""
import pytest

from test_game_goldens import game_decompiler

pytestmark = pytest.mark.game


def _body(game_decompiler, mi):
    il, dec = game_decompiler
    m = il.meta.methods[mi]
    return '\n'.join(dec.lift_method(m, il.meta.typedefs[m.declaring]))


def test_allocated_type_array_folds(game_decompiler):
    text = _body(game_decompiler, 84)
    assert '((byte*)((byte*)typeArray2 + 0x0)[0] + 0x40)[0]' not in text
    assert 'sub_180434690' not in text
    assert 'typeArray2[num6] = type1;' in text


def test_allocated_biginteger_array_folds(game_decompiler):
    text = _body(game_decompiler, 471)
    assert 'sub_180434690' not in text
    assert 'return bigIntegerArray1;' in text


def test_allocated_inputcontrol_array_folds_but_field_declines(game_decompiler):
    text = _body(game_decompiler, 30694)
    assert '((byte*)((byte*)inputControlArray2 + 0x0)[0] + 0x40)[0]' not in text
    assert text.count('sub_180434690') == 1
    site = next(ln for ln in text.split('\n') if 'sub_180434690' in ln)
    assert 'inputControlArray5' in site


def test_static_field_array_declines(game_decompiler):
    text = _body(game_decompiler, 200)
    assert '((byte*)((byte*)tailoringInfoArray2 + 0x0)[0] + 0x40)[0]' in text


def test_object_element_arrays_decline(game_decompiler):
    assert _body(game_decompiler, 2717).count('sub_180434690') == 3
    text = _body(game_decompiler, 4020)
    assert '((byte*)((byte*)new object[1] + 0x0)[0] + 0x40)[0]' in text


def test_as_refined_array_declines(game_decompiler):
    text = _body(game_decompiler, 10829)
    assert '((byte*)objectArray1.getClass() + 0x40)[0]' in text


def test_unknown_provenance_declines(game_decompiler):
    text = _body(game_decompiler, 7021)
    # fix 125/126 re-pin: the klass operand now prints as typeof(...); the
    # call still declines to fold to `as` (unknown provenance).
    assert ('(System.Runtime.Remoting.Messaging.IMethodCallMessage)sub_180434690(obj75, '
            'typeof(System.Runtime.Remoting.Messaging.IMethodCallMessage))') in text
    text = _body(game_decompiler, 32342)
    assert '((byte*)this.touchControlArray.getClass() + 0x40)[0]' in text


def test_closed_generic_instance_elements_fold(game_decompiler):
    text = _body(game_decompiler, 113247)
    assert text.count('sub_180434690') == 0
    assert 'structWrapper1Array1 = new ExitGames.Client.Photon.StructWrapping.StructWrapper_1<byte>[256];' in text


def test_closed_comparer_array_folds(game_decompiler):
    text = _body(game_decompiler, 105419)
    assert text.count('sub_180434690') == 0
    assert 'comparer1Array1[0x0] = comparer11;' in text


def test_proof_typed_open_array_folds(game_decompiler):
    text = _body(game_decompiler, 123638)
    assert text.count('sub_180434690') == 0
    assert 'processor1Array1[0x0] = this.proc;' in text
    assert 'v.RemoveProcessor(processor1Array1);' in text


def test_nested_array_elements_decline(game_decompiler):
    assert _body(game_decompiler, 102073).count('sub_180434690') == 3
