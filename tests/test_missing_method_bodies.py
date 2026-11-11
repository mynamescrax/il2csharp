"""Unavailable native bodies must be legal C# and fail explicitly if called."""
import shutil
from types import SimpleNamespace as NS

import pytest

from il2cpp.emitter import Emitter
from il2cpp.csharp import strip_namespaces
from test_member_recovery import fixture
from test_review114_method_flags import method
from test_review113_type_decls import I_INT, I_VOID, P, td_base
from tools.compile_corpus import compile_tree


@pytest.mark.parametrize('mode', ['no_address', 'declarations', 'limit'])
def test_unavailable_bodies_compile(tmp_path, mode):
    def member(name, result=I_VOID, params=(), flags=6):
        m = method(flags, name, addr=0 if mode == 'no_address' else 123)
        m.return_type, m.ps = result, list(params)
        return m

    methods = [
        member('.ctor'), member('.cctor', flags=0x10),
        member('Run'), member('Read', I_INT),
        member('get_Item', I_INT, [P(I_INT, 'index')]),
        member('set_Item', params=[P(I_INT, 'index'), P(I_INT, 'value')]),
        member('add_Changed', params=[P(I_INT, 'value')]),
        member('remove_Changed', params=[P(I_INT, 'value')]),
        member('get_Count', I_INT),
        member('IExample.Read', I_INT, flags=1 | 0x40 | 0x20 | 0x100),
    ]
    e, td = fixture(methods)
    e._lift_body = Emitter._lift_body.__get__(e)
    e.with_bodies = mode != 'declarations'
    e.lifter = NS(lift=lambda *args: pytest.fail('unavailable method lifted'))
    e.max_methods = 0 if mode == 'limit' else None
    e.lifted = e.failed = e.fallbacks = 0
    lines = ['using System;', 'public interface IExample { int Read(); }',
             'public class Sample : IExample {']
    for m in methods[:4] + methods[9:]:
        e.emit_method(m, td, lines, '    ')
    e.emit_property(td, lines, '', ('Item', 4, 5))
    e.emit_property(td, lines, '', ('Count', 8, -1))
    action = len(e.il.types)
    e.il.types = list(e.il.types) + [('action', 0)]
    type_name = e.il.type_name
    e.il.type_name = lambda t: 'System.Action' if t == ('action', 0) else type_name(t)
    e.emit_event(td, lines, '', ('Changed', action, 6, 7, -1))
    lines.append('}')
    for name, flags in [('Abstract', 0x80), ('IContract', 0x20 | 0x80)]:
        owner = td_base(name=name, flags=flags)
        lines.append(('public interface ' if flags & 0x20 else 'public abstract class ') + name + ' {')
        e.emit_method(member('Read', I_INT, flags=6 | 0x400 | 0x40 | 0x100), owner, lines, '    ')
        lines.append('}')
    # Exercise the final file pass too: global::System must not become global::.
    text = '\n'.join(strip_namespaces(lines, {'System'}))
    assert text.count('throw new global::System.NotImplementedException') == len(methods)
    assert 'abstract int Read();' in text
    assert 'int Read();' in text
    assert e.lifted == e.failed == e.fallbacks == 0
    if mode == 'no_address':
        assert 'RVA:' not in text
    (tmp_path / 'Missing.cs').write_text(text)
    if not shutil.which('dotnet'):
        pytest.skip('.NET SDK unavailable')
    assert compile_tree(tmp_path, tmp_path / 'compile.json') == 0


def test_recovered_empty_body_is_not_replaced():
    e, td = fixture()
    e.with_bodies, e.max_methods = True, None
    e.lifter = NS()
    e.decompiler = NS(lift_method=lambda *args: [])
    e.lifted = 0
    assert Emitter._lift_body(e, method(6, addr=123), td) == []
    assert e.lifted == 1
