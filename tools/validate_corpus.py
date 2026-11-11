"""Reproducible, offline validation; never executes the native game binary.

The sweep directly invokes Decompiler.lift_method, so exceptions cannot be
hidden by Emitter's linear fallback. Parse is a syntax gate, NOT a C# compiler
or a claim of semantic equivalence. Structural audits are intentionally small
and have their own unit tests; their counts need not match missing legacy
work/ scripts with different definitions.
"""
import argparse
from collections import Counter
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import time

from corpus_common import load, sha256, source_fingerprints


def mask_literals(text, keep_literal_token=False):
    """Mask comments and ordinary/verbatim/interpolated string/char text.

    Preserve offsets/newlines. Interpolated strings are opaque here: their
    internal expression braces are not statement scopes.
    """
    out = list(text)
    i, n = 0, len(text)
    while i < n:
        start = i
        literal = False
        if text.startswith("//", i):
            end = text.find("\n", i + 2)
            i = n if end < 0 else end
        elif text.startswith("/*", i):
            end = text.find("*/", i + 2)
            i = n if end < 0 else end + 2
        elif text[i] in "\"'":
            literal = True
            quote = text[i]
            verbatim = quote == '"' and (
                (i > 0 and text[i - 1] == "@")
                or (i > 1 and text[i - 2:i] == "@$")
            )
            i += 1
            while i < n:
                if not verbatim and text[i] == "\\":
                    i = min(i + 2, n)
                    continue
                if text[i] == quote:
                    if verbatim and i + 1 < n and text[i + 1] == quote:
                        i += 2
                        continue
                    i += 1
                    break
                i += 1
        else:
            i += 1
            continue
        for j in range(start, i):
            if out[j] not in "\r\n":
                out[j] = " "
        if literal and keep_literal_token:
            out[start] = "0"
    return "".join(out)


TOKEN = re.compile(r"[{}]|\bgoto\s+(?P<goto>L_[0-9a-fA-F]+)\s*;|(?P<label>\bL_[0-9a-fA-F]+)\s*:")
EMPTY = re.compile(r"\(\s*,|,\s*,|,\s*\)")


def audit_body(body):
    # A literal is an operand, not an empty argument. Preserve one opaque
    # token while masking its internal braces/commas/labels.
    text = mask_literals("\n".join(body), keep_literal_token=True)
    labels, jumps = {}, []
    scope = []
    serial = underflows = 0
    for match in TOKEN.finditer(text):
        token = match.group()
        if token == "{":
            serial += 1
            scope.append(serial)
        elif token == "}":
            if scope:
                scope.pop()
            else:
                underflows += 1
        elif match.group("goto"):
            jumps.append((match.group("goto"), tuple(scope)))
        else:
            labels[match.group("label")] = tuple(scope)
    dangling = into_block = 0
    for label, origin in jumps:
        destination = labels.get(label)
        if destination is None:
            dangling += 1
        elif origin[:len(destination)] != destination:
            into_block += 1
    # Multidimensional array ranks and unbound generic arity are legal
    # comma-only groups, not missing call arguments.
    argument_text = re.sub(r"\[(?:\s*,)+\s*\]|<(?:\s*,)+\s*>", "0", text)
    return {
        "brace_unclosed": len(scope),
        "brace_underflow": underflows,
        "dangling_gotos": dangling,
        "into_block_gotos": into_block,
        "empty_args": len(EMPTY.findall(argument_text)),
    }


def write_report(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def parse_tree(args):
    import tree_sitter_c_sharp
    from tree_sitter import Language, Parser

    parser = Parser(Language(tree_sitter_c_sharp.language()))
    started = time.monotonic()
    files = sorted(Path(args.tree).rglob("*.cs"))
    bad = {}
    errors = missing = recoveries = 0
    for p in files:
        data = p.read_bytes()
        # Keep the Tree alive throughout traversal (also for older bindings).
        tree = parser.parse(data)
        root = tree.root_node
        if not root.has_error:
            continue
        stack = [root]
        nodes = []
        while stack:
            node = stack.pop()
            children = node.children
            if node.type == "ERROR" or node.is_missing:
                kind = "MISSING" if node.is_missing else "ERROR"
                errors += kind == "ERROR"
                missing += kind == "MISSING"
                nodes.append({
                    "kind": kind, "row": node.start_point.row + 1,
                    "column": node.start_point.column + 1,
                    "text": data[node.start_byte:node.end_byte].decode("utf-8", "replace")[:180],
                })
            elif node.has_error and not any(
                c.has_error or c.is_missing or c.type == "ERROR" for c in children
            ):
                # Some grammar/binding combinations expose zero-width
                # recovery identifiers with has_error=True but neither
                # is_missing nor type=="ERROR". Never turn that into a
                # falsely clean gate. Keep it a separate, explicit category.
                recoveries += 1
                nodes.append({
                    "kind": "RECOVERY", "node_type": node.type,
                    "row": node.start_point.row + 1,
                    "column": node.start_point.column + 1,
                    "zero_width": node.start_byte == node.end_byte,
                    "text": data[node.start_byte:node.end_byte].decode("utf-8", "replace")[:180],
                })
            stack.extend(c for c in reversed(children)
                         if c.has_error or c.is_missing or c.type == "ERROR")
        bad[str(p.relative_to(args.tree))] = nodes
    report = {
        "kind": "tree-sitter C# syntax gate",
        "tree": str(Path(args.tree).resolve()),
        "files": len(files), "bad_files": len(bad),
        "errors": errors, "missing": missing, "recovery_nodes": recoveries, "details": bad,
        "elapsed_seconds": round(time.monotonic() - started, 3),
    }
    write_report(args.report, report)
    print(json.dumps({k: v for k, v in report.items() if k != "details"}, indent=2))
    return 1 if bad or not files else 0


def sweep(args):
    if os.environ.get("PYTHONHASHSEED") != "0":
        raise SystemExit("Run with PYTHONHASHSEED=0 for reproducible body comparisons.")
    started = time.monotonic()
    fingerprints = {
        "metadata_sha256": sha256(args.metadata),
        "binary_sha256": sha256(args.binary),
        "source_sha256": source_fingerprints(args.source),
    }
    il = load(args.source, args.metadata, args.binary)
    from il2cpp import Lifter
    from il2cpp import Decompiler

    dec = Decompiler(Lifter(il))
    totals, affected = Counter(), Counter()
    crashes = []
    # Observe the real pass input/output, rather than guessing causes from
    # finished C# text. This wrapper never reads the counting register file.
    tail_changes = []
    current_method = [None]
    tail_helper = getattr(Lifter, "_tail_method_args", None)
    if tail_helper is not None:
        def trace_tail(lifter, mi, args_before, arg_exprs):
            method = lifter.meta.methods[mi]
            want = method.param_count + (0 if method.is_static else 1)
            legacy = list(args_before[:want])
            while legacy and legacy[-1] == "_":
                legacy.pop()
            result = tail_helper(lifter, mi, args_before, arg_exprs)
            if not getattr(lifter, "dry", True) and result != legacy:
                tail_changes.append({
                    "caller_mi": current_method[0], "callee_mi": mi,
                    "ip": hex(getattr(lifter, "_cur_ip", 0)),
                    "before": legacy, "after": list(result),
                })
            return result
        Lifter._tail_method_args = trace_tail
    methods = [m for m in il.meta.methods if m.addr]
    if args.only:
        terms = [x.casefold() for x in args.only.split(",") if x.strip()]
        methods = [m for m in methods if any(
            term in il.meta.images[m.image].name.casefold() for term in terms
        )]
    target = Path(args.report)
    manifest = target.with_suffix(".methods.jsonl.gz")
    manifest.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(manifest, "wt", encoding="utf-8", compresslevel=1) as output:
        for count, m in enumerate(methods, 1):
            current_method[0] = m.index
            td = il.meta.typedefs[m.declaring]
            row = {"mi": m.index, "va": hex(m.addr), "type": td.name, "name": m.name}
            try:
                body = dec.lift_method(m, td)
                metrics = audit_body(body)
                row.update(metrics)
                row["lines"] = len(body)
                row["sha256"] = hashlib.sha256("\n".join(body).encode("utf-8")).hexdigest()
                totals.update(metrics)
                totals["lines"] += len(body)
                affected.update({k: 1 for k, v in metrics.items() if v})
            except Exception as ex:
                row["exception"] = f"{type(ex).__name__}: {ex}"
                crashes.append(row)
            output.write(json.dumps(row, ensure_ascii=False) + "\n")
            if count % 10000 == 0:
                print(f"{count}/{len(methods)} methods; crashes={len(crashes)}", flush=True)
    if tail_helper is not None:
        Lifter._tail_method_args = tail_helper
    tail_manifest = target.with_suffix(".tail-args.jsonl.gz")
    with gzip.open(tail_manifest, "wt", encoding="utf-8", compresslevel=1) as output:
        for row in tail_changes:
            output.write(json.dumps(row, ensure_ascii=False) + "\n")
    report = {
        "kind": "direct structured-lift sweep",
        **fingerprints, "methods": len(methods), "crashes": len(crashes),
        "totals": dict(totals), "affected_methods": dict(affected),
        "crash_details": crashes, "method_manifest": manifest.name,
        "tail_argument_changes": len(tail_changes),
        "tail_argument_methods": len({r["caller_mi"] for r in tail_changes}),
        "tail_argument_manifest": tail_manifest.name,
        "elapsed_seconds": round(time.monotonic() - started, 3),
    }
    write_report(target, report)
    print(json.dumps({k: v for k, v in report.items() if k not in ("crash_details",)}, indent=2))
    return 1 if crashes else 0


def compare(args):
    a = json.loads(Path(args.before).read_text(encoding="utf-8"))
    b = json.loads(Path(args.after).read_text(encoding="utf-8"))
    if "method_manifest" in a:
        for key in ("metadata_sha256", "binary_sha256"):
            if a[key] != b[key]:
                raise SystemExit(f"Cannot compare different fixtures ({key}).")
        def rows(path, report_path):
            base = Path(report_path).resolve().parent
            raw = Path(path)
            # A manifest recorded as a bare name lives beside its own
            # report. Review 77 reports embedded machine-local absolute
            # paths instead, and a moved release keeps the manifest next
            # to its report rather than at the original machine's path.
            # `is_absolute()` cannot drive that choice: on Windows a
            # rooted POSIX path such as /old/machine/m.jsonl.gz is NOT
            # absolute (it carries a root but no drive), so the relative
            # branch joined it onto the report directory and produced
            # C:\old\machine\m.jsonl.gz -- the relocation never ran and
            # the comparison died on a foreign path. `anchor` separates
            # rooted from relative on both platforms; prefer the
            # recorded location when it exists, else the sibling name.
            first = raw if raw.anchor else base / raw
            path = first if first.exists() else base / raw.name
            with gzip.open(path, "rt", encoding="utf-8") as f:
                return {r["mi"]: r for r in map(json.loads, f)}
        old, new = rows(a["method_manifest"], args.before), rows(b["method_manifest"], args.after)
        metrics = ("brace_unclosed", "brace_underflow", "dangling_gotos", "into_block_gotos", "empty_args")
        changed, structural, new_crashes = [], [], []
        common = sorted(old.keys() & new.keys())
        for mi in common:
            x, y = old[mi], new[mi]
            if x.get("sha256") != y.get("sha256"):
                changed.append({"mi": mi, "va": y["va"], "type": y["type"], "name": y["name"],
                                "line_delta": y.get("lines", 0) - x.get("lines", 0)})
            if any(x.get(k, 0) != y.get(k, 0) for k in metrics):
                structural.append({"mi": mi, "va": y["va"],
                                   "before": {k: x.get(k, 0) for k in metrics},
                                   "after": {k: y.get(k, 0) for k in metrics}})
            if "exception" in y and "exception" not in x:
                new_crashes.append(y)
        result = {
            "common_methods": len(common),
            "added_methods": sorted(new.keys() - old.keys()),
            "removed_methods": sorted(old.keys() - new.keys()),
            "changed_method_count": len(changed),
            "structural_change_count": len(structural),
            "new_crash_count": len(new_crashes),
            "changed_methods": changed, "structural_changes": structural, "new_crashes": new_crashes,
        }
    else:
        old, new = a["details"], b["details"]
        result = {
            "before": {k: a[k] for k in ("files", "bad_files", "errors", "missing")},
            "after": {k: b[k] for k in ("files", "bad_files", "errors", "missing")},
            "newly_bad": sorted(new.keys() - old.keys()),
            "cleared": sorted(old.keys() - new.keys()),
            "changed_bad_files": [k for k in sorted(old.keys() & new.keys()) if old[k] != new[k]],
        }
        result["before"]["recovery_nodes"] = a.get("recovery_nodes", 0)
        result["after"]["recovery_nodes"] = b.get("recovery_nodes", 0)
    write_report(args.report, result)
    print(json.dumps({k: v for k, v in result.items()
                      if k not in ("changed_methods", "structural_changes", "new_crashes")}, indent=2))
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    commands = ap.add_subparsers(dest="command", required=True)
    p = commands.add_parser("parse", help="Parse every emitted .cs and save per-file errors.")
    p.add_argument("tree")
    p.add_argument("--report", required=True)
    p.set_defaults(run=parse_tree)
    p = commands.add_parser("sweep", help="Directly lift every native MethodDef; no silent fallback.")
    p.add_argument("--source", default=str(Path(__file__).resolve().parents[1]))
    p.add_argument("--metadata", required=True)
    p.add_argument("--binary", required=True)
    p.add_argument("--only")
    p.add_argument("--report", required=True)
    p.set_defaults(run=sweep)
    p = commands.add_parser("compare", help="Compare per-file gates or per-method sweep manifests.")
    p.add_argument("before")
    p.add_argument("after")
    p.add_argument("--report", required=True)
    p.set_defaults(run=compare)
    args = ap.parse_args()
    return args.run(args)


if __name__ == "__main__":
    raise SystemExit(main())