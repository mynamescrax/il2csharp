"""Protect the core sources from whole-file line-ending churn."""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BOM = b"\xef\xbb\xbf"
PKG = ROOT / "il2cpp"


def test_launcher_keeps_its_bom_and_crlf_contract():
    launcher = (ROOT / "il2csharp.py").read_bytes()

    assert launcher.startswith(BOM)
    assert launcher.count(b"\r\n") == launcher.count(b"\n")


def test_package_sources_are_crlf_without_bom():
    sources = sorted(PKG.rglob("*.py"))
    assert len(sources) > 30

    total = 0
    for path in sources:
        data = path.read_bytes()
        assert not data.startswith(BOM), path
        assert data.count(b"\r\n") == data.count(b"\n"), path
        total += data.count(b"\n")

    # the two monoliths were ~18k lines between them; the package keeps them
    assert total > 17_000
