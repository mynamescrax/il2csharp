"""End-to-end declaration gate on a tiny image (needs fixture).

Dumps Unity.Burst.Unsafe declarations from metadata, extracts them
from the promoted r10 tree, and requires the structural diff to be
clean. Pins the side-A harness against drift on both ends.
"""
import os
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.game

ROOT = Path(__file__).resolve().parents[1]
ONLY = "Unity.Burst.Unsafe"
ASM = "Unity.Burst.Unsafe.dll"


def _run(args, env):
    return subprocess.run(
        [sys.executable] + args, cwd=str(ROOT), capture_output=True,
        text=True, timeout=600, env=env)


def test_decl_gate_end_to_end(tmp_path, monkeypatch):
    metadata = os.environ.get("IL2CSHARP_METADATA")
    binary = os.environ.get("IL2CSHARP_BINARY")
    assert metadata and binary, "fixture env required"
    assert os.environ.get("PYTHONHASHSEED") == "0"
    env = dict(os.environ, PYTHONPATH=str(ROOT) + os.pathsep + str(ROOT / "tools"))
    dump = tmp_path / "dump.txt"
    r = _run([str(ROOT / "tools" / "dump_decls.py"),
              "--metadata", metadata, "--binary", binary,
              "--only", ONLY, "--out", str(dump)], env)
    assert r.returncode == 0, r.stderr[-2000:]
    ext = tmp_path / "ext.txt"
    r = _run([str(ROOT / "tools" / "extract_decls.py"),
              "--tree", str(ROOT / "final_out" / ONLY),
              "--assembly", ASM, "--out", str(ext)], env)
    assert r.returncode == 0, r.stderr[-2000:]
    r = _run([str(ROOT / "tools" / "diff_decls.py"),
              "--dump", str(dump), "--extracted", str(ext)], env)
    assert r.returncode == 0, r.stdout[-2000:]
