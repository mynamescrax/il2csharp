"""Storage identity and real accessor bodies, including compilable execution."""
from types import SimpleNamespace as NS
from pathlib import Path
import shutil
import subprocess
import pytest

from il2cpp.csharp import source_field_name
from test_review113_type_decls import make_emitter, td_base, P, I_INT, I_VOID


def method(name, flags=6, result=I_INT, params=(), body=None):
    return NS(name=name, flags=flags, is_static=bool(flags & 0x10),
              return_type=result, ps=list(params), addr=0, body=body)


def fixture(methods=(), fields=(), props=(), events=(), flags=1):
    td = td_base(index=0, name='Sample', flags=flags, methods=range(len(methods)))
    td.property_start = td.event_start = 0
    td.property_count, td.event_count = len(props), len(events)
    td.fis = list(range(len(fields)))
    td.field_count = len(fields)
    e = make_emitter(methods=methods, fields=fields, typedefs=[td])
    e.meta.properties, e.meta.events = list(props), list(events)
    e.meta.getstr = lambda s: s
    e.il.bin = NS(image_base=0)
    e.il.field_offsets = [None]
    e._lift_body = lambda m, td: m.body
    return e, td


def prop(e, td, row):
    lines = []
    e.emit_property(td, lines, '', row)
    return '\n'.join(lines)


def test_backing_storage_is_distinct_and_collision_free():
    fields = [NS(name='<Count>k__BackingField', type=I_INT),
              NS(name='__field_Count', type=I_INT),
              NS(name='Changed', type=I_INT)]
    e, td = fixture(fields=fields, props=[('Count', -1, -1)],
                    events=[('Changed', I_INT, -1, -1, -1)])
    assert source_field_name(e.il, 0) == '__field_Count_2'
    assert source_field_name(e.il, 1) == '__field_Count'
    assert source_field_name(e.il, 2) == '__field_Changed'
    assert fields[0].name == '<Count>k__BackingField'
    other, _ = fixture(fields=[NS(name='ordinary', type=I_INT)])
    assert source_field_name(other.il, 0) == 'ordinary'


def test_actual_field_declaration_is_retained():
    row = ('Count', 0, -1)
    e, td = fixture([method('get_Count', body=['return this.__field_Count;'])],
                    [NS(name='<Count>k__BackingField', type=I_INT)], [row])
    e._unity_serialized = lambda *a: False
    lines = []
    e.emit_type(td, lines, '')
    text = '\n'.join(lines)
    assert 'int __field_Count;' in text
    assert 'return this.__field_Count;' in text
    assert 'return this.Count;' not in text


@pytest.mark.parametrize('flags, expected', [
    (6 | 0x40 | 0x100, 'public virtual'),
    (6 | 0x40, 'public override'),
    (6 | 0x40 | 0x20, 'public sealed override'),
    (4 | 0x40 | 0x100 | 0x400, 'protected abstract'),
])
def test_property_dispatch(flags, expected):
    e, td = fixture([method('get_Count', flags=flags)])
    assert expected + ' int Count' in prop(e, td, ('Count', 0, -1))


def test_setter_visibility_and_empty_body_are_preserved():
    methods = [method('get_Count', body=['return 1;']),
               method('set_Count', flags=1, result=I_VOID, params=[P(I_INT, 'value')], body=[])]
    e, td = fixture(methods)
    text = prop(e, td, ('Count', 0, 1))
    assert 'private set\n' in text
    assert 'set;' not in text


def test_write_only_type_comes_from_setter():
    e, td = fixture([method('set_Count', result=I_VOID, params=[P(I_INT, 'value')], body=[])])
    assert 'public int Count' in prop(e, td, ('Count', -1, 0))


def test_indexer_declares_its_parameters_and_rebinds_setter():
    methods = [method('get_Item', params=[P(I_INT, 'index')], body=['return index;']),
               method('set_Item', result=I_VOID, params=[P(I_INT, 'i'), P(I_INT, 'value')],
                      body=['this.buffer[i] = value;'])]
    e, td = fixture(methods)
    text = prop(e, td, ('Item', 0, 1))
    assert 'int this[int index]' in text
    assert 'this.buffer[index] = value;' in text


def test_abstract_accessors_are_never_lifted():
    e, td = fixture([method('get_Count', flags=6 | 0x400 | 0x40 | 0x100)])
    e._lift_body = lambda *args: pytest.fail('abstract body lifted')
    assert 'abstract int Count { get; }' in prop(e, td, ('Count', 0, -1))


def test_event_keeps_both_native_bodies_and_parameter_identity():
    methods = [method('add_Changed', result=I_VOID, params=[P(I_INT, 'handler')],
                      body=['this.handler = handler; // handler', 'Log("handler");']),
               method('remove_Changed', result=I_VOID, params=[P(I_INT, 'value')], body=[])]
    e, td = fixture(methods)
    lines = []
    assert e.emit_event(td, lines, '', ('Changed', I_INT, 0, 1, -1))
    text = '\n'.join(lines)
    assert 'this.handler = value; // handler' in text
    assert 'Log("handler");' in text
    assert 'remove\n' in text and 'remove;' not in text


def test_incomplete_event_keeps_methods():
    e, td = fixture([method('add_Changed')])
    lines = []
    assert not e.emit_event(td, lines, '', ('Changed', I_INT, 0, -1, -1))


def test_abstract_event_has_no_fabricated_storage():
    methods = [method('add_Changed', flags=6 | 0x400 | 0x40 | 0x100),
               method('remove_Changed', flags=6 | 0x400 | 0x40 | 0x100)]
    e, td = fixture(methods)
    lines = []
    e.emit_event(td, lines, '', ('Changed', I_INT, 0, 1, -1))
    assert lines == ['    public abstract event int Changed;']


def test_generated_members_compile_and_execute(tmp_path):
    dotnet = shutil.which('dotnet')
    if not dotnet:
        pytest.skip('.NET SDK unavailable')
    root = Path(dotnet).resolve().parent
    compilers = sorted((root/'sdk').glob('*/Roslyn/bincore/csc.dll'))
    refs = sorted((root/'packs/Microsoft.NETCore.App.Ref').glob('*/ref/net*'))
    if not compilers or not refs:
        pytest.skip('Roslyn/reference assemblies unavailable')
    e, td = fixture([
        method('get_Count', body=['return this.__field_Count;']),
        method('set_Count', flags=1, result=I_VOID, params=[P(I_INT, 'value')], body=['this.__field_Count = value;']),
        method('get_Item', params=[P(I_INT, 'i')], body=['return this.buffer[i];']),
        method('set_Item', result=I_VOID, params=[P(I_INT, 'i'),P(I_INT, 'value')], body=['this.buffer[i] = value;']),
        method('add_Changed', result=I_VOID, params=[P(I_INT, 'value')], body=['this.__field_Changed += value;', 'this.Count++;']),
        method('remove_Changed', result=I_VOID, params=[P(I_INT, 'value')], body=['this.__field_Changed -= value;', 'this.Count--;']),
    ])
    # The event type is supplied by metadata; here use a framework Action.
    old_name = e.il.type_name
    e.il.type_name = lambda t: 'System.Action' if t == ('action', 0) else old_name(t)
    e.il.types = list(e.il.types) + [('action', 0)]
    lines = []
    e.emit_event(td, lines, '', ('Changed', len(e.il.types)-1, 4, 5, -1))
    text = '\n'.join([
        'public class Sample { private int __field_Count; private int[] buffer = new int[2]; private System.Action __field_Changed;',
        prop(e, td, ('Count',0,1)), prop(e,td,('Item',2,3)), '\n'.join(lines),
        'public void Raise() { __field_Changed?.Invoke(); } }',
        'class Program { static int Main() { var x = new Sample(); int n = 0; System.Action h = () => n++; x.Changed += h; x.Raise(); x[1] = 42; x.Changed -= h; x.Raise(); return n == 1 && x.Count == 0 && x[1] == 42 ? 0 : 1; } }',
    ])
    source = tmp_path/'Members.cs'
    source.write_text(text)
    dll = tmp_path/'Members.dll'
    args = [dotnet,str(compilers[-1]),'/nologo','/target:exe','/out:'+str(dll),str(source)]
    args += ['/reference:'+str(p) for p in refs[-1].glob('*.dll')]
    run = subprocess.run(args, capture_output=True, text=True, timeout=60)
    assert run.returncode == 0, run.stdout + run.stderr
    import json
    version = refs[-1].parent.parent.name
    dll.with_suffix('.runtimeconfig.json').write_text(json.dumps({'runtimeOptions':{'tfm':refs[-1].name,'framework':{'name':'Microsoft.NETCore.App','version':version}}}))
    run = subprocess.run([dotnet,str(dll)], capture_output=True, text=True, timeout=30)
    assert run.returncode == 0, run.stdout + run.stderr


def test_explicit_interface_storage_flattens_to_one_token():
    import re
    fields = [NS(name='<IFoo.Bar>k__BackingField', type=I_INT)]
    e, td = fixture(fields=fields, props=[('IFoo.Bar', -1, -1)])
    name = source_field_name(e.il, 0)
    assert name == '__field_IFoo_Bar'
    assert re.fullmatch(r'[A-Za-z_]\w*', name)
