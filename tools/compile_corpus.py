"""Compile a recovered tree as one diagnostic unit; never execute its output.

This deliberately bypasses per-assembly reference wiring. Duplicate generated
shared stubs are merged in a temporary file; recovered source is never edited.
A clean result would prove compilation only, not recovered behavior.
"""
import argparse
from collections import Counter
import gzip
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile


def version_key(path):
    return tuple(int(n) for n in re.findall(r"\d+", str(path)))


def stub_members(path):
    """Read whole methods, including the body, from an emitted stub class."""
    lines = iter(path.read_text(encoding='utf-8-sig').splitlines())
    for line in lines:
        m = re.match(r'^(\s*)internal static object (sub_[0-9a-f]+)\(', line)
        if not m:
            continue
        member = [line]
        # Older emitters used expression bodies on the signature line.
        if not line.rstrip().endswith(';'):
            for body_line in lines:
                member.append(body_line)
                if body_line.rstrip() == m[1] + '}':
                    break
            else:
                raise ValueError(f'{path}: unterminated stub {m[2]}')
        yield m[2], '\n'.join(member)


def roslyn_toolchain():
    dotnet = shutil.which("dotnet")
    if not dotnet:
        raise RuntimeError("A .NET SDK is required")
    root = Path(dotnet).resolve().parent
    compilers = sorted((root / "sdk").glob("*/Roslyn/bincore/csc.dll"), key=version_key)
    refs = sorted((root / "packs/Microsoft.NETCore.App.Ref").glob("*/ref/net*"), key=version_key)
    if not compilers or not refs:
        raise RuntimeError("Roslyn and .NET reference assemblies are required")
    return dotnet, compilers[-1], refs[-1]


def compile_tree(tree, report, support_sources=()):
    dotnet, compiler, references = roslyn_toolchain()
    files = sorted(Path(tree).resolve().rglob("*.cs"))
    if not files:
        raise ValueError("No C# source files found")
    support = [Path(p).resolve(strict=True) for p in support_sources]
    if any(p.suffix.lower() != '.cs' or p in files for p in support) or len(set(support)) != len(support):
        raise ValueError('compiler support inputs must be distinct .cs files outside the recovered tree')
    sources, stubs = [], {}
    inventory = hashlib.sha256()
    for path in files:
        inventory.update(path.relative_to(Path(tree).resolve()).as_posix().encode())
        inventory.update(hashlib.sha256(path.read_bytes()).digest())
        if path.name == "__SharedBodyStubs.cs":
            for name, member in stub_members(path):
                if stubs.setdefault(name, member) != member:
                    raise ValueError(f'{path}: inconsistent definitions of {name}')
        else:
            sources.append(path)
    with tempfile.TemporaryDirectory(prefix="il2csharp_compile_") as temporary:
        temp = Path(temporary)
        merged = temp / "__SharedBodyStubs.cs"
        merged.write_text("internal static class __SharedBodyStubs {\n" +
                          "\n".join(stubs[k] for k in sorted(stubs)) + "\n}")
        response = temp / "compile.rsp"
        options = ["/nologo", "/target:library", "/unsafe+", "/langversion:latest",
                   '/out:"' + str(temp / "Recovered.dll") + '"']
        options.extend('/reference:"' + str(p) + '"' for p in references.glob("*.dll"))
        options.extend('"' + str(p) + '"' for p in sources + [merged] + support)
        response.write_text("\n".join(options), encoding="utf-8")
        result = subprocess.run([dotnet, str(compiler), "@" + str(response)],
                                capture_output=True, text=True, timeout=600)
    log = result.stdout + result.stderr
    report = Path(report)
    report.parent.mkdir(parents=True, exist_ok=True)
    log_path = report.with_suffix(".log.gz")
    with gzip.open(log_path, "wt", encoding="utf-8") as stream:
        stream.write(log)
    error_files = set(re.findall(r"^(.+?)\(\d+,\d+\): error CS\d+:", log, re.MULTILINE))
    errors = Counter(re.findall(r"\berror (CS\d+):", log))
    summary = dict(tree=str(Path(tree).resolve()), source_files=len(files),
                   merged_stubs=len(stubs), compiler=str(compiler),
                   inventory_sha256=inventory.hexdigest(), log=str(log_path),
                   references=str(references), exit_code=result.returncode,
                   files_with_errors=len(error_files),
                   errors=sum(errors.values()), errors_by_code=dict(errors.most_common()),
                    scope="Single diagnostic assembly; original project wiring is not tested")
    if support:
        summary['compiler_support_sources'] = {str(p): hashlib.sha256(p.read_bytes()).hexdigest()
                                               for p in support}
    report.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return result.returncode


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tree")
    parser.add_argument("--report", required=True)
    parser.add_argument('--support-source', action='append', default=[], metavar='FILE.cs',
                        help='additional compiler-only source, hashed separately in the report (repeatable)')
    args = parser.parse_args()
    raise SystemExit(compile_tree(args.tree, args.report, args.support_source))
