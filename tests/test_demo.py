"""Exercise the public CLI and the emitted projects without a game install."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

from il2cpp.cli import main
from dotnet_case import run_case


CLI = Path(__file__).resolve().parents[1] / 'il2csharp.py'


def demo(cwd, *options):
    run = subprocess.run([sys.executable, str(CLI), '--demo', '--strict', *options],
                         cwd=cwd, text=True, capture_output=True, timeout=60,
                         env=dict(os.environ, PYTHONHASHSEED='0'))
    assert run.returncode == 0, run.stdout + run.stderr
    return run.stdout


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8'))


@pytest.mark.parametrize('conflict', [('game',), ('--metadata', 'm'), ('--binary', 'b')])
def test_demo_rejects_real_inputs(conflict, capsys):
    with pytest.raises(SystemExit) as ex:
        main(['il2csharp', '--demo', *conflict])
    assert ex.value.code == 2
    assert '--demo cannot be combined' in capsys.readouterr().err


def test_demo_serial_and_parallel_emit_the_same_tree(tmp_path):
    # Build in an empty CWD with no target; demo must not reuse a game output.
    serial = tmp_path / 'il2csharp_out_demo'
    parallel = tmp_path / 'parallel'
    summary = json.loads(demo(tmp_path, '--quiet', '--json'))
    assert Path(summary['out']) == serial
    assert (summary['files'], summary['lifted']) == (3, 9)
    assert summary['emit_failed'] == summary['failed'] == summary['fallbacks'] == 0
    assert 'workers: 2 processes' in demo(tmp_path, '--workers', '2', '-o', str(parallel))

    def tree(root):
        return {p.relative_to(root): p.read_bytes() for p in root.rglob('*') if p.is_file()}

    assert tree(serial) == tree(parallel)
    assert not (tmp_path / 'il2csharp_out').exists()


def test_demo_address_map_and_recovered_bodies(tmp_path):
    out = tmp_path / 'out'
    demo(tmp_path, '--bodies', '-o', str(out))
    entries = read_json(out / 'script.json')['ScriptMethod']
    bodies = read_json(out / 'bodies.json')
    methods = {e['Name']: bodies[hex(e['Address'])] for e in entries}
    assert len(methods) == len(bodies) == 9
    assert 'return score + bonus;' in methods['Demo.ScoreRules.AddBonus(int, int)']
    assert 'ReverseEndianness(' in methods['Demo.ScoreRules.DecodeNetworkScore(int)']
    assert 'this.score = points;' in methods['Demo.ScoreBoard.SetScore(int)']
    assert 'return this.remaining <= 0;' in methods['Demo.RoundTimer.HasExpired()']
    assert read_json(out / 'stringliteral.json') == [{'index': 0, 'value': 'Round complete!'}]


def test_demo_generated_projects_execute(tmp_path):
    demo(tmp_path, '-o', 'out')
    runner = tmp_path / 'runner'
    runner.mkdir()
    shutil.copy(Path(__file__).with_name('demo') / 'Program.cs', runner)
    output = run_case(tmp_path, runner, ('../out/Assembly-CSharp/Assembly-CSharp.csproj',
                                         '../out/Demo.Clock/Demo.Clock.csproj'))
    assert 'demo behavior OK' in output
