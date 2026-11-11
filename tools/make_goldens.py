"""Freeze MethodDef-keyed snapshots ONLY after clean build/parse/sweep gates.

This is the portable suite, not the historical work/goldens.json. The original
goldens_review77.json is retained as provenance; the current default is the
Review 84 version. Review every changed snapshot before using --replace. Never
accept output merely because it parses: native examples and the audit diff matter.
"""
import argparse
import json
from pathlib import Path

from corpus_common import load, sha256, source_fingerprints


def select_indices(methods, count, focus):
    native = [m.index for m in methods if m.addr]
    available = set(native)
    if not set(focus) <= available:
        raise ValueError("a requested focus MethodDef has no native code")
    selected = set(focus)
    if count < len(selected) or count > len(native):
        raise ValueError("invalid sample count")
    remaining = count - len(selected)
    if remaining:
        for i in range(remaining):
            selected.add(native[i * (len(native) - 1) // max(remaining - 1, 1)])
    # Fill any overlap between the evenly-spaced sample and focus rows.
    for mi in native:
        if len(selected) == count:
            break
        selected.add(mi)
    return sorted(selected)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source", default=str(Path(__file__).resolve().parents[1]))
    ap.add_argument("--metadata", required=True)
    ap.add_argument("--binary", required=True)
    ap.add_argument("--sweep-report", required=True)
    ap.add_argument("--parse-report", required=True)
    ap.add_argument("--focus-indices", default=None,
                    help="comma-separated MethodDef rows; preserves existing focus rows when replacing")
    ap.add_argument("--count", type=int, default=64)
    ap.add_argument("--output", default=str(Path(__file__).resolve().parents[1] / "tests/goldens_review84.json"))
    ap.add_argument("--description", default="Focused native regressions plus a deterministic corpus spread; not a semantic oracle.")
    ap.add_argument("--replace", action="store_true")
    ap.add_argument("--full", action="store_true",
                    help="write full bodies (local review only); the default "
                         "is hash-only, the public-safe form")
    args = ap.parse_args()
    import os
    if os.environ.get("PYTHONHASHSEED") != "0":
        raise SystemExit("Run with PYTHONHASHSEED=0.")
    target = Path(args.output)
    if target.exists() and not args.replace:
        raise SystemExit("Refusing to overwrite snapshots without --replace.")
    sweep = json.loads(Path(args.sweep_report).read_text())
    gate = json.loads(Path(args.parse_report).read_text())
    if sweep["crashes"] or gate["bad_files"] or gate["errors"] or gate["missing"] or not gate["files"]:
        raise SystemExit("A clean direct sweep and nonempty clean built-tree parse gate are required.")
    current = source_fingerprints(args.source)
    recorded = sweep["source_sha256"]
    for name in sorted(set(current) | set(recorded)):
        if current.get(name) != recorded.get(name):
            raise SystemExit(f"Source changed after the gated sweep: {name}")
    for kind in ("metadata", "binary"):
        if sha256(getattr(args, kind)) != sweep[kind + "_sha256"]:
            raise SystemExit(f"Fixture changed after the sweep: {kind}")
    il = load(args.source, args.metadata, args.binary)
    from il2cpp import Lifter
    from il2cpp import Decompiler

    if args.focus_indices is not None:
        focus = [int(x) for x in args.focus_indices.split(",") if x.strip()]
    elif target.exists():
        previous = json.loads(target.read_text(encoding="utf-8"))
        if any(previous.get(k) != sweep[k] for k in ("metadata_sha256", "binary_sha256")):
            raise SystemExit("Different fixture: provide --focus-indices explicitly (empty string for spread only).")
        focus = previous.get("focus_indices", [])
    else:
        focus = [1354, 2157, 2158]  # the supplied Windows fixture's native float-tail checks
    indices = select_indices(il.meta.methods, args.count, focus)
    dec = Decompiler(Lifter(il))
    snapshots = []
    for mi in indices:
        m = il.meta.methods[mi]
        td = il.meta.typedefs[m.declaring]
        snapshots.append({
            "mi": mi, "va": hex(m.addr),
            "type": ((td.namespace + ".") if td.namespace else "") + td.name,
            "name": m.name,
            "body": dec.lift_method(m, td),
        })
    result = {
        "description": args.description,
        "metadata_sha256": sweep["metadata_sha256"],
        "binary_sha256": sweep["binary_sha256"],
        "source_sha256": sweep["source_sha256"],
        "focus_indices": focus,
        "methods": snapshots,
    }
    if not args.full:
        # Public-safe default: pins stay (mi/va/type/name + body sha256),
        # the game-derived text does not. `--full` writes it for local review.
        from goldens_hash_only import hash_only
        result = hash_only(result)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {len(snapshots)} {'full-body' if args.full else 'hash-only'} "
          f"snapshots, keyed by MethodDef row, to {target}")


if __name__ == "__main__":
    main()