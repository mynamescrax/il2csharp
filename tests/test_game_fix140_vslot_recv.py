"""Fix 140: unresolved vtable slots resolve through the dispatch object.

Ground truth (disasm):
- ASN1.GetBytes 0x181ACFDD0: `foreach (ASN1 a in elist) a.GetBytes()` --
  IEnumerator.Current (object) is cast by the inlined hierarchy check
  against typeof(ASN1) at 0x181ad0049, then `call [r9+178h]` is slot 4,
  ASN1.GetBytes.
- AILerp.OnPathComplete: vtable slot 53 of this (klass+0x488, MethodInfo
  at klass+0x490 passed last) with RCX = &sret buffer and RDX = this --
  GetFeetPosition() returning a Vector3 through the buffer; arg0 is the
  buffer, not the receiver.
"""
import pytest

from test_game_goldens import game_decompiler

pytestmark = pytest.mark.game


def _lift(il, dec, mi, name):
    m = il.meta.methods[mi]
    assert m.name == name
    return [ln.strip() for ln in dec.lift_method(m, il.meta.typedefs[m.declaring])]


def test_castclass_narrows_the_receiver(game_decompiler):
    il, dec = game_decompiler
    lines = _lift(il, dec, 277, 'GetBytes')
    hits = [ln for ln in lines if '((Mono.Security.ASN1)enumerator1.Current).GetBytes()' in ln]
    assert len(hits) == 1
    assert not any('vtable slot' in ln for ln in lines)


def test_sret_buffer_is_not_the_receiver(game_decompiler):
    il, dec = game_decompiler
    lines = _lift(il, dec, 104143, 'OnPathComplete')
    assert any(ln.endswith('= this.GetFeetPosition();') for ln in lines)
    assert not any('vtable slot' in ln for ln in lines)


def test_sret_parameter_receiver_folds(game_decompiler):
    # BBTree.DrawDebugNode: slot 20 of TriangleMeshNode (GetVertex(int),
    # Vector3 through the buffer) on the parameter `node`, and the array
    # element receiver of SearchBoxClosestXZ -- both used to print the
    # static spelling `TriangleMeshNode.GetVertex(node, 1)` (CS1501)
    il, dec = game_decompiler
    lines = _lift(il, dec, 105366, 'DrawDebugNode')
    assert 'UnityEngine.Vector3 vector31 = node.GetVertex(1);' in lines
    assert not any('TriangleMeshNode.GetVertex(' in ln for ln in lines)
    lines = _lift(il, dec, 105369, 'SearchBoxClosestXZ')
    assert 'vector32 = triangleMeshNodeArray1[num1].ClosestPointOnNodeXZ(vector31);' in lines