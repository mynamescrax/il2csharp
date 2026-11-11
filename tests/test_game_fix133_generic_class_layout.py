"""Fix 133 (game): open generic collection layouts and a lifted body.

Native: AudiencePath.SpawnPeople 0x1804FEDF0 reads the list count with
`mov ebx,[rdi+18h]` (4 bytes) -- List<T>._size at 0x18."""
import os

import pytest

pytestmark = pytest.mark.game


@pytest.fixture(scope='module')
def game_decompiler():
    metadata, binary = (os.environ.get(n) for n in ('IL2CSHARP_METADATA', 'IL2CSHARP_BINARY'))
    if not metadata or not binary:
        pytest.skip('fixture env required')
    from pathlib import Path
    from tools.corpus_common import load
    il = load(Path(__file__).resolve().parents[1], metadata, binary)
    from il2cpp import Decompiler, Lifter
    return il, Decompiler(Lifter(il))


def _td(il, ns, name):
    hits = [i for i, t in enumerate(il.meta.typedefs) if t.namespace == ns and t.name == name]
    assert len(hits) == 1
    return hits[0]


def _names(il, td):
    return {off: v[0] for off, v in (il.instance_field_chain(td) or {}).items()}


def test_list_and_dictionary_layouts(game_decompiler):
    il, _ = game_decompiler
    lst = _names(il, _td(il, 'System.Collections.Generic', 'List`1'))
    assert lst == {0x10: '_items', 0x18: '_size', 0x1c: '_version', 0x20: '_syncRoot'}
    dic = _names(il, _td(il, 'System.Collections.Generic', 'Dictionary`2'))
    assert dic[0x10] == '_buckets' and dic[0x18] == '_entries' and dic[0x20] == '_count'
    assert 0 not in lst and 0 not in dic       # the object header is not a field


def test_list_count_reads_size(game_decompiler):
    il, dec = game_decompiler
    m = il.meta.methods[23555]
    assert m.name == 'SpawnPeople' and hex(m.addr) == '0x1804fedf0'
    body = '\n'.join(dec.lift_method(m, il.meta.typedefs[m.declaring]))
    assert 'int num1 = list11._size - 1;' in body
    assert '__addr(list11) + 0x18' not in body and '(list11 + 0x18)' not in body


def test_items_type_closes_through_the_receiver(game_decompiler):
    # fix 133b: `List<Glyph>._items` is `Glyph[]` at the caller, not the
    # definition's unbound `T[]` (b4 leaked CS0246 'T' +322)
    il, dec = game_decompiler
    m = il.meta.methods[95397]
    assert m.name == 'TryAddCharacters'
    body = '\n'.join(dec.lift_method(m, il.meta.typedefs[m.declaring]))
    assert 'UnityEngine.TextCore.Glyph[] glyphArray1 = this.m_GlyphTable._items;' in body
    assert 'uint[] uintArray2 = this.m_GlyphIndexList._items;' in body
    assert 'T[] ' not in body
