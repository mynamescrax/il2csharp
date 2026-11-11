"""The interface slow-path resolve helper is named and trimmed.

Ground truth: SecurityParser.OnStartElement (mi 122) calls 0x18043dc60 on
the miss path of its inlined fast-path loop with (obj, iface, slot) in
RCX/RDX/R8. The printed 4th arg duplicates the iface (R9 spray residue
from the loop). Naming routes through `il2cpp_interface_get_method`
with arity 3, dropping the duplicate.
"""
import pytest

from test_game_goldens import game_decompiler

pytestmark = pytest.mark.game


def test_security_parser_renders_the_named_resolve_helper(game_decompiler):
    il, dec = game_decompiler
    m = il.meta.methods[122]
    assert m.name == 'OnStartElement'
    text = '\n'.join(dec.lift_method(m, il.meta.typedefs[m.declaring]))
    assert 'sub_18043dc60' not in text
    assert 'il2cpp_interface_get_method(attrs, typeof(Mono.Xml.SmallXmlParser.IAttrList), 0)' in text
