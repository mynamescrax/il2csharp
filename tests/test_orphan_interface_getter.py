"""An explicit MethodDef is a property only when its interface says so."""
import pytest

from dotnet_case import run_case
from test_member_recovery import fixture
from test_review113_type_decls import I_INT, td_base
from test_review114_method_flags import method


def orphan():
    impl = method(0x1e1, 'Example.ICounter.get_Count', addr=0x1234)
    getter = method(0xdc6, 'get_Count')
    impl.return_type = getter.return_type = I_INT
    impl.param_count = getter.param_count = 0
    impl.slot = 12
    impl.body = ['return ++reads;']
    e, td = fixture([impl])
    iface = td_base(index=1, name='ICounter', flags=0xa1, methods=[1])
    iface.property_start, iface.property_count, iface.method_start = 0, 1, 1
    td.interfaces_start, td.interfaces_count = 0, 1
    e.meta.typedefs.append(iface)
    e.meta.methods.append(getter)
    e.meta.properties.append(('Count', 0, -1))
    e.meta.interfaces = [len(e.il.types)]
    it = (1, 0x12 << 16)
    e.il.types = [*e.il.types, it]
    type_name = e.il.type_name
    e.il.type_name = lambda t: 'Example.ICounter' if t == it else type_name(t)
    e.il._type_enum = lambda t: t[1] >> 16 & 255
    return e, td, impl


def test_recovered_getter_executes_via_interface(tmp_path):
    e, td, _ = orphan()
    lines = []
    e.emit_type(td, lines, '')
    source = '\n'.join(lines)
    assert 'get_Count()' not in source
    assert '0x1234 Slot: 12' in source
    runner = tmp_path / 'runner'
    runner.mkdir()
    (runner / 'Program.cs').write_text('''
Example.ICounter counter = new Sample();
if (counter.Count != 1 || counter.Count != 2) throw new System.Exception();
System.Console.WriteLine("explicit getter OK");
namespace Example { public interface ICounter { int Count { get; } } }
public partial class Sample { private int reads; }
''' + source, encoding='utf-8')
    assert 'explicit getter OK' in run_case(tmp_path, runner)


@pytest.mark.parametrize('case', ['ordinary method', 'setter', 'wrong return', 'other interface'])
def test_do_not_invent_an_explicit_property(case):
    e, td, impl = orphan()
    if case == 'ordinary method':
        e.meta.typedefs[1].property_count = 0
    elif case == 'setter':
        e.meta.properties[0] = ('Count', 0, 1)
    elif case == 'wrong return':
        e.meta.methods[1].return_type = 0
    else:
        impl.name = 'Other.ICounter.get_Count'
    assert e._orphan_interface_getter(impl, td) is None
