"""`--only` with no matching assembly must fail loudly.

Before this, a no-match run exited 0 after writing script.json /
stringliteral.json and no type files -- a plausible-empty tree. It now
returns 1 with an `error:` line and writes nothing.
"""
import os
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.game

ROOT = Path(__file__).resolve().parents[1]


def test_only_no_match_is_an_error(tmp_path):
    out = tmp_path / 'nomatch_out1'
    result = subprocess.run(
        [sys.executable, str(ROOT / 'il2csharp.py'), 'testgame',
         '-o', str(out), '--only', 'NoSuchAssembly.dll'],
        cwd=str(ROOT), capture_output=True, text=True, timeout=600,
        env=dict(os.environ, PYTHONHASHSEED='0'))
    assert result.returncode == 1, result.stdout + result.stderr
    assert '--only matched no assembly' in (result.stdout + result.stderr)
    assert not out.exists(), 'a no-match run must not write an output tree'
