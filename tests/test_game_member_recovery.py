"""Native checks for storage/accessor identity; fixture addresses are evidence."""
import pytest
from il2cpp import Emitter
from il2cpp.csharp import source_field_name
from test_game_goldens import game_decompiler
from test_game_review78 import body

pytestmark = pytest.mark.game


def test_native_getter_reads_backing_storage_not_itself(game_decompiler):
    il, _ = game_decompiler
    m = il.meta.methods[117958]
    assert m.name == 'get_Code'
    td = il.meta.typedefs[m.declaring]
    fi = next(i for i in il.meta.type_fields(td)
              if il.meta.fields[i].name == '<Code>k__BackingField')
    assert source_field_name(il, fi) == '__field_Code'
    assert body(game_decompiler, m.index) == 'return this.__field_Code;'
    # Native mov eax,[rcx+10h]; ret -- the read is not a managed getter call.
    assert il.bin.read(m.addr, 4) == bytes.fromhex('8b4110c3')


def test_event_bodies_are_emitted_with_storage_and_addresses(game_decompiler):
    il, dec = game_decompiler
    td = il.meta.typedefs[3621]
    assert td.name == 'PlatformManager'
    e = Emitter(il, '', with_bodies=False)
    e.with_bodies = True
    e.lifter, e.decompiler = dec.L, dec
    lines = []
    ev = next(il.meta.events[td.event_start+k] for k in range(td.event_count)
              if il.meta.getstr(il.meta.events[td.event_start+k][0]) == 'OnNetworkDisconnected')
    assert e.emit_event(td, lines, '', ev)
    text = '\n'.join(lines)
    assert 'Delegate.Combine' in text and 'Delegate.Remove' in text
    assert '.__field_OnNetworkDisconnected' in text
    assert 'VA: 0x1805591D0' in text
    assert e.lifted == 2


def test_storage_names_do_not_mutate_reflection_metadata(game_decompiler):
    il, _ = game_decompiler
    td = il.meta.typedefs[3621]
    fi = next(i for i in il.meta.type_fields(td)
              if il.meta.fields[i].name == 'OnNetworkDisconnected')
    assert source_field_name(il, fi) == '__field_OnNetworkDisconnected'
    assert il.meta.fields[fi].name == 'OnNetworkDisconnected'
    offsets = il.static_off_names(td.index)
    assert offsets[8][0] == '__field_OnNetworkDisconnected'
