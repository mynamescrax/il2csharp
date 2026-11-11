"""Renamed locals must not shadow body identifiers or parameters.

Ground truth: AndroidJNI.IsSameObject (mi 124140) forwards
(IntPtr obj1, IntPtr obj2). Its dead spill renumbered to
`object obj1 = obj2`, shadowing the params, and _copy_prop merged the
dropped argument (`(obj2, obj2)`). The rename barrier reserves both.
"""
import pytest

from test_game_goldens import game_decompiler

pytestmark = pytest.mark.game


def test_forwarded_args_survive_rename(game_decompiler):
    il, dec = game_decompiler
    m = il.meta.methods[124140]
    assert m.name == 'IsSameObject'
    assert hex(m.addr) == '0x182b65cb0'
    text = '\n'.join(dec.lift_method(m, il.meta.typedefs[m.declaring]))
    assert 'return UnityEngine.AndroidJNI.IsSameObject(obj1, obj2);' in text
    assert 'object obj1 = obj2;' not in text
