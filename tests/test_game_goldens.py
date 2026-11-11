"""Optional licensed-fixture tests; keep the supplied private fixtures private.

The original goldens_review77.json is retained unchanged. Review 84 keeps the
same 64 MethodDefs and freezes its constructor/allocation bodies only after the
complete strict-build, parse, direct-sweep, and output-audit gates.
"""
import hashlib
import json
import os
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from corpus_common import load, sha256

GOLDEN_PATH = Path(__file__).with_name("goldens_review84.json")
GOLDENS = json.loads(GOLDEN_PATH.read_text(encoding="utf-8")) if GOLDEN_PATH.exists() else {}
SNAPSHOTS = GOLDENS.get("methods", [None])


@pytest.fixture(scope="module")
def game_decompiler():
    metadata, binary = (os.environ.get(name) for name in ("IL2CSHARP_METADATA", "IL2CSHARP_BINARY"))
    if not metadata or not binary:
        pytest.skip("Set IL2CSHARP_METADATA and IL2CSHARP_BINARY to run licensed-fixture snapshots.")
    if not GOLDENS:
        pytest.skip("Generate snapshots only after the documented full gates.")
    assert os.environ.get("PYTHONHASHSEED") == "0", "Use PYTHONHASHSEED=0 for snapshot comparisons."
    assert sha256(metadata) == GOLDENS["metadata_sha256"], "Different metadata fixture."
    assert sha256(binary) == GOLDENS["binary_sha256"], "Different native binary fixture."
    il = load(Path(__file__).resolve().parents[1], metadata, binary)
    from il2cpp import Lifter
    from il2cpp import Decompiler
    return il, Decompiler(Lifter(il))


@pytest.mark.game
@pytest.mark.parametrize("snapshot", SNAPSHOTS, ids=[
    f"mi-{s['mi']}-{s['name']}" if s is not None else "not-generated" for s in SNAPSHOTS
])
def test_real_method_snapshot(game_decompiler, snapshot):
    il, dec = game_decompiler
    m = il.meta.methods[snapshot["mi"]]
    assert hex(m.addr) == snapshot["va"]
    actual = dec.lift_method(m, il.meta.typedefs[m.declaring])
    if "body" in snapshot:
        assert actual == snapshot["body"]
        return
    # hash-only (public) variant: the same pin without the game-derived text
    digest = hashlib.sha256("\n".join(actual).encode("utf-8")).hexdigest()
    assert digest == snapshot["body_sha256"]