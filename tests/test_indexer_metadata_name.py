"""An indexer's C# surface syntax and its CLR property name are distinct."""
from dotnet_case import run_case
from test_member_recovery import fixture, method, prop
from test_review113_type_decls import I_INT, P


def test_custom_indexer_and_same_type_item_method_compile_and_dispatch(tmp_path):
    getter = method('get_ItemOf', params=[P(I_INT, 'i')], body=['return this.Item(i) + 1;'])
    row = ('ItemOf', 0, -1)
    e, td = fixture([getter], props=[row])
    emitted = prop(e, td, row)
    runner = tmp_path / 'runner'
    runner.mkdir()
    (runner / 'Program.cs').write_text('''
var x = new Sample();
if (x.Item(5) != 15 || x[5] != 16) throw new System.Exception("dispatch");
var members = typeof(Sample).GetDefaultMembers();
if (members.Length != 1 || members[0].Name != "ItemOf") throw new System.Exception("metadata name");
System.Console.WriteLine("indexer OK");
public class Sample {
    public int Item(int i) => i + 10;
''' + emitted + '\n}', encoding='utf-8')
    assert 'indexer OK' in run_case(tmp_path, runner)


def test_mixed_indexer_names_do_not_introduce_conflicting_attributes():
    rows = [('ItemOf', 0, -1), ('Item', 1, -1)]
    e, td = fixture([method('get_ItemOf', params=[P(I_INT)]),
                     method('get_Item', params=[P(I_INT), P(I_INT, 'j')])], props=rows)
    assert all('IndexerName' not in prop(e, td, r) for r in rows)


def test_explicit_indexer_has_no_indexer_name_attribute():
    row = ('IMap.ItemOf', 0, -1)
    e, td = fixture([method('IMap.get_ItemOf', params=[P(I_INT)])], props=[row])
    emitted = prop(e, td, row)
    assert 'IMap.this[' in emitted and 'IndexerName' not in emitted
