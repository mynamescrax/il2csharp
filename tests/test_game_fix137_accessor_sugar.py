"""Fix 137: accessor calls use the member syntax their property rows declare.

Ground truth (disasm):
- AdaptiveFovByAspect.ApplyFovIfNeeded 0x1806060C0: `mov rcx,[rbx+30h];
  movss xmm1,...; jmp 0x182B89A10` -- a tail jump into
  Camera.set_fieldOfView: `this._cam.fieldOfView = real1; return;`, not
  the explicit accessor call `this._cam.set_fieldOfView(real1)` (CS0571).
- AddRandomVelocity.Update 0x180513900: the struct-return call of the
  static getter Random.get_onUnitSphere reads `Random.onUnitSphere`.
- AudiencePath.DrawCurved 0x1804FDEC0: the static setter Gizmos.set_color
  is an assignment.
- <PrivateImplementationDetails>.ComputeStringHash 0x18068CBC0: String's
  indexer row is named Chars, so `s.get_Chars(i)` (CS1061) is `s[i]`.
"""
import pytest

from test_game_goldens import game_decompiler

pytestmark = pytest.mark.game


def _lift(il, dec, mi, name):
    m = il.meta.methods[mi]
    assert m.name == name
    return '\n'.join(dec.lift_method(m, il.meta.typedefs[m.declaring]))


def test_instance_setter_tail_is_an_assignment(game_decompiler):
    il, dec = game_decompiler
    text = _lift(il, dec, 24208, 'ApplyFovIfNeeded')
    assert 'this._cam.fieldOfView = real1; return;' in text
    assert 'set_fieldOfView' not in text


def test_static_struct_getter_reads_the_property(game_decompiler):
    il, dec = game_decompiler
    text = _lift(il, dec, 23902, 'Update')
    assert 'UnityEngine.Random.onUnitSphere' in text
    assert 'get_onUnitSphere' not in text


def test_static_setter_is_an_assignment(game_decompiler):
    il, dec = game_decompiler
    text = _lift(il, dec, 23554, 'DrawCurved')
    assert 'UnityEngine.Gizmos.color = color1;' in text
    assert 'set_color' not in text


def test_chars_indexer_row_reads_as_an_index(game_decompiler):
    il, dec = game_decompiler
    text = _lift(il, dec, 12710, 'ComputeStringHash')
    assert 's[num1]' in text
    assert 'get_Chars' not in text
