"""Portable pins for the compile gate (no fixture, no SDK needed)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from compile_gate import classify, iter_sources, run_gate


def test_classify_syntax_vs_binding():
    out = ("a.cs(1,2): error CS1002: ; expected\n"
           "b.cs(3,4): error CS1513: } expected\n"
           "c.cs(5,6): error CS0246: type not found\n"
           "d.cs(7,8): warning CS0219: unused\n"
           "not a diagnostic line\n")
    s, b, top = classify(out)
    assert s == 2
    assert b == 1
    assert top[0] == ("CS1002", 1) or top[0][1] == 1


def test_classify_empty():
    assert classify("") == (0, 0, [])


def test_iter_sources_sorted(tmp_path):
    (tmp_path / "b.cs").write_text("class B{}", encoding="utf-8")
    (tmp_path / "a.cs").write_text("class A{}", encoding="utf-8")
    (tmp_path / "x.txt").write_text("nope", encoding="utf-8")
    got = iter_sources(str(tmp_path))
    assert [Path(p).name for p in got] == ["a.cs", "b.cs"]


def test_run_gate_no_sources(tmp_path):
    rep = run_gate(str(tmp_path))
    assert rep["tool_error"] == "no .cs files"


def test_run_gate_no_compiler(tmp_path, monkeypatch):
    (tmp_path / "A.cs").write_text("class A{}", encoding="utf-8")
    import compile_gate
    monkeypatch.setattr(compile_gate, "find_csc", lambda explicit=None: None)
    rep = run_gate(str(tmp_path))
    assert rep["tool_error"] == "no compiler found"


def test_run_gate_fake_compiler_counts(tmp_path, monkeypatch):
    (tmp_path / "A.cs").write_text("class A{}", encoding="utf-8")

    class P:
        stdout = "A.cs(1,1): error CS1002: ; expected\n"
        stderr = "A.cs(2,2): error CS0246: nope\n"
        returncode = 1

    import compile_gate
    monkeypatch.setattr(compile_gate, "find_csc", lambda explicit=None: "csc")
    monkeypatch.setattr(compile_gate.subprocess, "run", lambda *a, **k: P())
    rep = run_gate(str(tmp_path))
    assert rep["syntax"] == 1
    assert rep["binding"] == 1
    assert rep["files"] == 1
