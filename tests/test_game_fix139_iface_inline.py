"""Fix 139: inlined interface dispatch renders as a managed interface call.

Ground truth (disasm):
- FusionNetworkManager.Update 0x180560FF0: 0x1805611c7..0x180561278 scans
  the receiver klass's interface table for INetworkTRSPTeleport, misses
  into the resolve helper 0x18043DC60 (slot 0), and `call [rax]`s the
  entry with (receiver, &position, &rotation, [rax+8]) -- the call is
  INetworkTRSPTeleport.Teleport(Vector3?, Quaternion?).
- SmallXmlParser.ReadContent 0x181AE2070: slot 2 of IContentHandler
  (OnStartElement(name, attrs)); the scan counter lives in RDI (callee-
  saved) and is dead at the join, so the prune still applies.
- ASN1.GetBytes 0x181ACFDD0: the miss arm copies the entry (`mov rdx,rax`)
  and the join loads `mov rax,[rdx]; call rax` -- IEnumerator.MoveNext.
"""
import pytest

from test_game_goldens import game_decompiler

pytestmark = pytest.mark.game


def _lift(il, dec, mi, name):
    m = il.meta.methods[mi]
    assert m.name == name
    return [ln.strip() for ln in dec.lift_method(m, il.meta.typedefs[m.declaring])]


def _no_scan(lines):
    text = '\n'.join(lines)
    assert 'il2cpp_interface_get_method' not in text
    assert '0x12e' not in text and '0xb0)' not in text and '0x138' not in text


def test_teleport_through_interface(game_decompiler):
    il, dec = game_decompiler
    lines = _lift(il, dec, 26440, 'Update')
    assert any(ln.startswith('networkTrspTeleport1.Teleport(') for ln in lines)
    _no_scan(lines)


def test_callee_saved_counter_dead_at_join(game_decompiler):
    il, dec = game_decompiler
    lines = _lift(il, dec, 141, 'ReadContent')
    assert 'this.handler.OnStartElement(this.ReadName(), this.attributes);' in lines
    assert not any('IContentHandler), 2)' in ln for ln in lines)


def test_entry_copied_before_join(game_decompiler):
    il, dec = game_decompiler
    lines = _lift(il, dec, 277, 'GetBytes')
    assert ('if (!enumerator1.MoveNext())' in lines
            or 'if (!(enumerator1.MoveNext()))' in lines)
    assert not any('typeof(System.Collections.IEnumerator)' in ln for ln in lines)
