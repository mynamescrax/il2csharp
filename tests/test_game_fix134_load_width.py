"""Fix 134: width-less raw field loads keep their native width.

Ground truth (disasm):
- InputSystem TouchscreenStateEvent OnStateEvent 0x18264A0D0:
  `mov ebx,[rax+14h]; ... cmp ebx,eax` -- the event's FourCC type is a
  dword compared with TouchState.Format, not a 1-byte
  `((byte*)inputEventPtr2 + 0x14)[0]`.
- KeybindsManager.Update 0x180547380: `call unbox; mov esi,[rax];
  mov ecx,esi` -- the unboxed KeyCode is a dword read.
Fix 134e: the `<T>(arg).Length` call paren survives _member_fold.
"""
import re

import pytest

from test_game_goldens import game_decompiler

pytestmark = pytest.mark.game


def _lift(il, dec, mi, name):
    m = il.meta.methods[mi]
    assert m.name == name
    return '\n'.join(dec.lift_method(m, il.meta.typedefs[m.declaring]))


def test_fourcc_type_read_is_a_dword(game_decompiler):
    il, dec = game_decompiler
    text = _lift(il, dec, 32833, 'OnStateEvent')
    assert '((int*)((byte*)inputEventPtr2 + 0x14))[0]' in text
    assert '((byte*)inputEventPtr2 + 0x14)[0]' not in text.replace(
        '((int*)((byte*)inputEventPtr2 + 0x14))[0]', '')
    assert '__w_' not in text


def test_unboxed_keycode_read_is_a_dword(game_decompiler):
    il, dec = game_decompiler
    text = _lift(il, dec, 25872, 'Update')
    assert re.search(r'int num\d+ = \(\(int\*\)\(\(byte\*\)obj\d+ \+ 0x0\)\)\[0\];', text)
    assert '__w_' not in text


def test_generic_call_argument_paren_survives(game_decompiler):
    il, dec = game_decompiler
    text = _lift(il, dec, 25872, 'Update')
    assert 'FindObjectsOfType<ChangeTextToKeybind>(true).Length' in text
    assert 'FindObjectsByType<ChangeTextToKeybind>(FindObjectsSortMode.None).Length' in text
    assert '>true.Length' not in text and '>FindObjectsSortMode.None.Length' not in text
