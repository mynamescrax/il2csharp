"""Emit a hash-only variant of a golden snapshot file.

The tracked goldens carry full decompiled method bodies. They are fine in the
private repo, but a public copy must not redistribute game-derived code. This
transform keeps every pin (mi, va, type, name, focus, fixture hashes) and
replaces each `body` list with its sha256 over "\\n".join(body) plus a line
count, so `tests/test_game_goldens.py` can still verify a body it can lift
when the full file is absent.

Usage:
    python tools/goldens_hash_only.py tests/goldens_review84.json \
        --output path/to/goldens_review84.json

Refuses to overwrite its input.
"""
import argparse
import hashlib
import json
from pathlib import Path


def body_digest(body):
    return hashlib.sha256("\n".join(body).encode("utf-8")).hexdigest()


def hash_only(data):
    """Return a copy of a goldens document with bodies replaced by hashes."""
    out = dict(data)
    out["description"] = (data.get("description", "") +
                          " [hash-only public variant]").strip()
    methods = []
    for snap in data.get("methods", []):
        row = {k: v for k, v in snap.items() if k != "body"}
        body = snap.get("body")
        if isinstance(body, list):
            row["body_sha256"] = body_digest(body)
            row["body_lines"] = len(body)
        methods.append(row)
    out["methods"] = methods
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("source")
    ap.add_argument("--output", required=True)
    args = ap.parse_args()
    src = Path(args.source)
    dst = Path(args.output)
    if src.resolve() == dst.resolve():
        raise SystemExit("refusing to overwrite the input file")
    data = json.loads(src.read_text(encoding="utf-8"))
    result = hash_only(data)
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n",
                   encoding="utf-8")
    print("wrote %d hash-only snapshots -> %s" % (len(result["methods"]), dst))


if __name__ == "__main__":
    main()
