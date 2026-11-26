from types import SimpleNamespace

from il2cpp import demo
from il2cpp.cli import main
from il2cpp.metadata import ParamDef, source_params
from il2cpp.names import safe_ident
from dotnet_case import run_case


def test_parameter_view_reserves_future_names_and_preserves_raw_rows():
    names = ['class', 'class_', 'arg2', 'arg2_']
    rows = [ParamDef(name, 100 + i, i) for i, name in enumerate(names)]
    meta = SimpleNamespace(method_params=lambda _: rows)
    view = source_params(meta, None)
    assert [safe_ident(p.name) for p in view] == ['class_', 'arg2__', 'arg2', 'arg2_']
    assert [(p.token, p.type) for p in view] == [(p.token, p.type) for p in rows]
    assert [p.name for p in rows] == names


def test_register_and_stack_discards_compile_as_distinct_values(tmp_path, monkeypatch):
    image, owner, field, methods = demo.TYPES[0]
    # eax = fifth stack argument - edx + ecx. The third/fourth argument
    # names are already taken, so arg1 and arg1_ cannot name the first `_`.
    combine = ('Combine', demo.INT, ('_', '_', 'arg1', 'arg1_', '_'), True,
               '8b 44 24 28 2b c2 03 c1 c3')
    monkeypatch.setattr(demo, 'TYPES', ((image, owner, field, methods + (combine,)), *demo.TYPES[1:]))
    assert main(['il2csharp', '--demo', '--strict', '--only', 'Assembly-CSharp',
                 '-o', str(tmp_path / 'out')]) == 0
    source = (tmp_path / 'out/Assembly-CSharp/Demo/ScoreRules.cs').read_text(encoding='utf-8')
    assert 'Combine(int arg1__, int arg2, int arg1, int arg1_, int arg5)' in source
    assert 'return arg5 - arg2 + arg1__;' in source
    runner = tmp_path / 'runner'
    runner.mkdir()
    (runner / 'Program.cs').write_text('''using Demo;
if (ScoreRules.Combine(7, 19, 41, 53, 31) != 19) throw new System.Exception();
System.Console.WriteLine("argument slots OK");''', encoding='utf-8')
    assert 'argument slots OK' in run_case(tmp_path, runner, ('../out/Assembly-CSharp/Assembly-CSharp.csproj',))
