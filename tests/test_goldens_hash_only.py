"""`tools/goldens_hash_only.py` keeps the pins and drops the game text."""
import hashlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from goldens_hash_only import hash_only  # noqa: E402


def test_hash_only_replaces_bodies_and_keeps_pins():
    body = ["object obj1 = 1;", "return;"]
    data = {"description": "x", "metadata_sha256": "m", "binary_sha256": "b",
            "focus_indices": [1],
            "methods": [{"mi": 1, "va": "0x10", "type": "T", "name": "M",
                         "body": body}]}
    out = hash_only(data)
    snap = out["methods"][0]
    assert "body" not in snap
    assert snap["body_sha256"] == hashlib.sha256(
        "\n".join(body).encode("utf-8")).hexdigest()
    assert snap["body_lines"] == 2
    assert (snap["mi"], snap["va"], snap["type"], snap["name"]) == \
        (1, "0x10", "T", "M")
    assert out["focus_indices"] == [1]
    assert out["metadata_sha256"] == "m"
    assert out["binary_sha256"] == "b"
    assert "hash-only" in out["description"]
    # the input document is not mutated
    assert data["methods"][0]["body"] == body
