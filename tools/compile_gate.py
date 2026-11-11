"""Compile gate for emitted trees (decl-gate v2, last item).

Runs Roslyn over one emitted image directory and reports error
counts split into syntax (gated: must be zero) versus binding
(report only: game images have no reference closure here, and
mscorlib self-hosts, so unresolved externals are expected noise).
Called after diff_decls passes; never merged into decl grammar.

Usage: python compile_gate.py --tree <imgdir> [--assembly NAME]
         [--csc-dll PATH] [--timeout SEC]
Exit: 0 iff zero syntax errors, 1 on syntax errors, 2 on usage errors.
"""
import argparse
import glob
import os
import re
import subprocess
import sys
import tempfile

ERR_RX = re.compile(
    r"^(.*)\((\d+)(?:,(\d+))?\):\s+(error|warning)\s+(CS\d+)\s*:\s*(.*)$")


def find_csc(explicit=None):
    """Locate csc.dll (SDK Roslyn) or a csc executable, else None."""
    if explicit:
        return explicit if os.path.isfile(explicit) else None
    roots = []
    try:
        dr = os.environ.get("DOTNET_ROOT", r"C:\Program Files\dotnet")
        sdk = os.path.join(dr, "sdk")
        if os.path.isdir(sdk):
            for v in sorted(os.listdir(sdk), reverse=True):
                cand = os.path.join(sdk, v, "Roslyn", "bincore", "csc.dll")
                if os.path.isfile(cand):
                    return cand
    except Exception:
        pass
    try:
        import shutil
        for name in ("csc", "csc.exe", "dotnet"):
            hit = shutil.which(name)
            if hit:
                return hit
    except Exception:
        pass
    return None


def iter_sources(root):
    out = []
    for dp, _, fns in os.walk(root):
        for fn in fns:
            if fn.endswith(".cs"):
                out.append(os.path.join(dp, fn))
    return sorted(out)


def classify(output):
    """(syntax, binding, top) from csc output text.

    Syntax = CS1xxx (parse/declaration level); everything else with
    a CS code counts as binding. Lines that do not parse as csc
    diagnostics are ignored. top lists (code, count) most common.
    """
    syntax = 0
    binding = 0
    counts = {}
    for ln in (output or "").splitlines():
        m = ERR_RX.match(ln.strip())
        if not m or m.group(4) != "error":
            continue
        try:
            num = int(m.group(5)[2:])
        except Exception:
            continue
        counts[m.group(5)] = counts.get(m.group(5), 0) + 1
        if 1000 <= num < 2000:
            syntax += 1
        else:
            binding += 1
    top = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:10]
    return syntax, binding, top


def run_gate(tree, csc_dll=None, timeout=600):
    """Compile every .cs under tree; return dict report. Never raises."""
    rep = {"files": 0, "syntax": 0, "binding": 0, "top": [],
           "tool_error": None}
    try:
        sources = iter_sources(tree)
    except Exception as e:
        rep["tool_error"] = "walk: %r" % (e,)
        return rep
    rep["files"] = len(sources)
    if not sources:
        rep["tool_error"] = "no .cs files"
        return rep
    csc = find_csc(csc_dll)
    if csc is None:
        rep["tool_error"] = "no compiler found"
        return rep
    rsp = None
    out_dll = None
    try:
        fd, rsp = tempfile.mkstemp(prefix="gateresp_", suffix=".rsp")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            for s in sources:
                f.write('"%s"\n' % s)
        fd2, out_dll = tempfile.mkstemp(prefix="gateout_", suffix=".dll")
        os.close(fd2)
        if csc.lower().endswith("csc.dll"):
            cmd = ["dotnet", csc, "/t:library", "/nologo", "/unsafe",
                   "/langversion:latest", "/out:" + out_dll, "@" + rsp]
        else:
            cmd = [csc, "/t:library", "/nologo", "/unsafe",
                   "/langversion:latest", "/out:" + out_dll, "@" + rsp]
        pr = subprocess.run(cmd, capture_output=True, text=True,
                            timeout=timeout)
        text = (pr.stdout or "") + "\n" + (pr.stderr or "")
        s, b, top = classify(text)
        rep["syntax"], rep["binding"], rep["top"] = s, b, top
        rep["returncode"] = pr.returncode
    except subprocess.TimeoutExpired:
        rep["tool_error"] = "compiler timeout"
    except Exception as e:
        rep["tool_error"] = "run: %r" % (e,)
    finally:
        for p in (rsp, out_dll):
            try:
                if p and os.path.isfile(p):
                    os.remove(p)
            except Exception:
                pass
    return rep


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--tree", required=True)
    ap.add_argument("--assembly", default="?")
    ap.add_argument("--csc-dll", default=None)
    ap.add_argument("--timeout", type=int, default=600)
    args = ap.parse_args()
    if not os.path.isdir(args.tree):
        print("no such tree: %s" % args.tree)
        return 2
    rep = run_gate(args.tree, args.csc_dll, args.timeout)
    if rep.get("tool_error"):
        print("tool error: %s" % rep["tool_error"])
        return 2
    print("%s: %d files, syntax=%d binding=%d" % (
        args.assembly, rep["files"], rep["syntax"], rep["binding"]))
    for code, n in rep["top"]:
        print("  %s x%d" % (code, n))
    return 0 if rep["syntax"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
