"""Ground truth for the RBP-frame recovery: mi 24062 WrapRopePlayerController.

`push rbp; mov rbp,rsp; sub rsp,50h` -- a textbook frame-pointer method --
used to emit 21 sites of fabricated pointer arithmetic on the never-written
RBP seed:

    ((byte*)obj9 - 0x30)[0] = vector31;     // movsd [rbp-30h], xmm6
    ((float*)obj9 - 0x28)[0] = real1;        // mov   [rbp-28h], ebx
    this.rb.AddForce((obj9 - 0x30), ForceMode.Acceleration);

`obj9` is not a pointer, and because it was *named* the statements were legal
C#, so the parse gate saw nothing. With the frame recovered the same slots
become typed UnityEngine.Vector3 locals feeding a real Vector3.Normalize
call and the real AddForce API.
"""
import re

import pytest

from test_game_goldens import game_decompiler

pytestmark = pytest.mark.game

MI = 24062
# a cast parenthesisation -- (byte*) -- sits between the deref paren and the
# base name, so the pattern must allow ")obj9" after the star.
FABRICATED = re.compile(
    r"\(\(\s*(?:byte|float|int|uint|long|short)\s*\*\)\s*\w+\s*[-+]\s*0x[0-9a-f]+\s*\)")


def _body(game_decompiler):
    il, dec = game_decompiler
    m = il.meta.methods[MI]
    text = dec.lift_method(m, il.meta.typedefs[m.declaring])
    return "\n".join(text if isinstance(text, list) else text.splitlines())


def test_method_is_a_frame_pointer_method(game_decompiler):
    il, _dec = game_decompiler
    m = il.meta.methods[MI]
    assert m.name == "Update"
    assert il.meta.typedefs[m.declaring].name == "WrapRopePlayerController"


def test_no_fabricated_pointer_arithmetic(game_decompiler):
    hits = FABRICATED.findall(_body(game_decompiler))
    assert not hits, "fabricated (T*)x - 0xNN sites: %r" % (hits[:5],)


def test_frame_slots_become_typed_vector3_locals(game_decompiler):
    text = _body(game_decompiler)
    assert "UnityEngine.Vector3 vector32" in text
    assert re.search(r"UnityEngine\.Vector3\.\w+\(vector\d+\)", text), \
        "the Vector3 home is no longer a typed local"


def test_real_unity_api_call_is_recovered(game_decompiler):
    text = _body(game_decompiler)
    assert "this.rb.AddForce(" in text
    assert "ForceMode.Acceleration" in text


def test_stack_map_has_no_raw_unsigned_key(game_decompiler):
    from il2cpp import Lifter
    il, _dec = game_decompiler
    m = il.meta.methods[MI]
    lf = Lifter(il)
    lf.lift(m, il.meta.typedefs[m.declaring])
    bad = [k for k in lf.stack_map if k > (1 << 63)]
    assert not bad, "raw 64-bit unsigned displacement keys: %r" % (bad[:5],)
    assert lf.stack_map, "no stack homes recorded"
    assert all(not n.startswith("s_ffff") for n in lf.stack_map.values()), \
        "a 64-bit name leaked into a slot name: %r" % (lf.stack_map,)
