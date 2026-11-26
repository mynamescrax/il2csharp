"""Compare merged and original-image Roslyn declaration checks on a base/derived pair.

The split check builds a reference DLL from the base image's actual emitted
sources, then references it from the derived image. /refonly checks member
signatures and accessibility; it does not check recovered method bodies.
"""
import argparse
from collections import Counter
import json
from pathlib import Path
import re
import subprocess
import tempfile

if __package__:
    from .compile_corpus import roslyn_toolchain, stub_members
else:
    from compile_corpus import roslyn_toolchain, stub_members


def check_boundary(base, derived, scope='.'):
    base, derived = Path(base).resolve(), Path(derived).resolve()
    selected = (derived / scope).resolve()
    selected.relative_to(derived)  # keep derived inputs within the named image
    if base.name.casefold() == derived.name.casefold():
        raise ValueError('expected distinct base and derived image names')
    base_files = sorted(base.rglob('*.cs'))
    derived_files = sorted(selected.rglob('*.cs'))
    if not base_files or not derived_files:
        raise ValueError('base image and selected derived scope must both contain C# sources')
    stubs = derived / '__SharedBodyStubs.cs'
    if stubs.exists() and stubs not in derived_files:
        derived_files.append(stubs)
    dotnet, csc, refs = roslyn_toolchain()
    # A facade in the SDK with the same name is not the recovered assembly.
    images = {(root.name + '.dll').casefold() for root in (base, derived)}
    sdk_refs = [p for p in sorted(refs.glob('*.dll')) if p.name.casefold() not in images]
    with tempfile.TemporaryDirectory(prefix='il2csharp_boundary_') as d:
        tmp = Path(d)

        def compile_unit(output, files, extra=()):
            args = ['/nologo', '/target:library', '/refonly', '/unsafe+', '/langversion:latest',
                    f'/out:"{output}"']
            args.extend(f'/reference:"{p}"' for p in [*sdk_refs, *extra])
            args.extend(f'"{p}"' for p in files)
            rsp = tmp / 'compile.rsp'
            rsp.write_text('\n'.join(args), encoding='utf-8')
            run = subprocess.run([dotnet, str(csc), '@' + str(rsp)], capture_output=True,
                                 text=True, timeout=180)
            log = run.stdout + run.stderr
            return dict(exit_code=run.returncode, source_files=len(files),
                        errors_by_code=dict(Counter(re.findall(r'\berror (CS\d+):', log))),
                        errors=[line for line in log.splitlines() if re.search(r'\berror CS\d+:', line)])

        # Only the merged control needs a single copy of the generated stub
        # class. Keep all ordinary source files identical in both layouts.
        merged_files, members = [], {}
        for p in base_files + derived_files:
            if p.name != '__SharedBodyStubs.cs':
                merged_files.append(p)
                continue
            for name, member in stub_members(p):
                if members.setdefault(name, member) != member:
                    raise ValueError(f'conflicting shared stub {name}')
        if any(p.name == '__SharedBodyStubs.cs' for p in base_files + derived_files):
            merged_stubs = tmp / '__SharedBodyStubs.cs'
            merged_stubs.write_text('internal static class __SharedBodyStubs {\n' +
                                    '\n'.join(members[n] for n in sorted(members)) + '\n}', encoding='utf-8')
            merged_files.append(merged_stubs)
        merged = compile_unit(tmp / 'merged-control.dll', merged_files)
        base_dll = tmp / (base.name + '.dll')
        first = compile_unit(base_dll, base_files)
        second = (compile_unit(tmp / (derived.name + '.dll'), derived_files, [base_dll])
                  if first['exit_code'] == 0 else None)
    return dict(mode='declarations only (/refonly)', compiler=str(csc), references=str(refs),
                base=str(base), derived=str(derived), derived_scope=str(selected),
                merged_control=merged, base_reference=first, derived_reference=second)


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--base', required=True, help='base image directory, named after the assembly')
    ap.add_argument('--derived', required=True, help='derived image directory')
    ap.add_argument('--scope', default='.', help='optional source subdirectory of the derived image')
    ap.add_argument('--report', type=Path, required=True)
    args = ap.parse_args()
    report = check_boundary(args.base, args.derived, args.scope)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    for phase in ('merged_control', 'base_reference', 'derived_reference'):
        stage = report[phase]
        print(phase, 'skipped' if stage is None else f"exit={stage['exit_code']} {stage['errors_by_code']}")
    raise SystemExit(report['base_reference']['exit_code'] or report['derived_reference']['exit_code'])
