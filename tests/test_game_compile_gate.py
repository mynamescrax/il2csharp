"""Real-SDK compile gate on the promoted mscorlib tree (needs fixture).

Compiles final_out/mscorlib with Roslyn and requires zero syntax
errors (CS1xxx). Binding errors are reported, not gated: game trees
have no reference closure here and mscorlib self-hosts. Skips when
no dotnet SDK is present. Proves the emitter output is compiler
ingestible end to end, beyond tree-sitter parse gates.
"""
import os
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

pytestmark = pytest.mark.game

sdk_present = shutil.which("dotnet") is not None
pytestmark = [pytestmark,
              pytest.mark.skipif(not sdk_present, reason="no dotnet SDK")]


def test_mscorlib_zero_syntax_errors():
    from compile_gate import run_gate
    tree = ROOT / "final_out" / "mscorlib"
    assert tree.is_dir(), "promoted tree required"
    assert os.environ.get("PYTHONHASHSEED") == "0"
    rep = run_gate(str(tree), timeout=900)
    assert rep.get("tool_error") is None, rep
    assert rep["files"] > 1300, rep
    assert rep["syntax"] == 0, rep
