# Replace the project folder — Review 84

> **HISTORICAL (Review 84 era, 2026-08).** This describes a private ZIP
> handoff whose contents included the licensed game fixtures and the
> decompiled `final_out/` tree. No public artifact may contain them; live
> state is `docs/todo.md`.

This ZIP contains a complete `il2csharp/` folder: updated source/tests/tools,
all existing development notes/work files, current validation evidence, the
supplied game DLL/metadata unchanged, and a freshly rebuilt `final_out/` with
**11,107 C# type files and 91 project files**. It is a direct replacement, not a
patch requiring a rebuild before you can inspect the cleaner output.

## Install / overwrite

1. Back up your existing `il2csharp` folder.
2. Extract this ZIP into its **parent directory**, allowing file overwrite.
   The result must be `il2csharp/il2csharp.py`, not an extra nested copy.
3. For an exact clean replacement, rename the old folder first and extract.
   This also removes unrelated local/stale files that no ZIP overwrite can
   delete.
4. From the extracted folder, optionally verify every shipped file:

```text
python tools/verify_release.py
```

`SHA256SUMS.txt` covers the replacement contents, excluding itself and disposable
Python/pytest/compiler caches. Extra local files are permitted. Intentional edits
after extraction will produce expected checksum mismatches.

This is a Python decompiler project, **not a replacement GameAssembly.dll**.
The game binary was not changed or executed. `final_out/` remains recovered C#
for inspection/development, not a ready-to-run game project.

Review 84 fixes the largest object-construction artifact: one native allocation
and its constructor now stay one C# object. Audited discarded `new T(args);`
statements fall **13,292 → 0**, empty allocation declarations fall
**21,624 → 13,254**, the dominant folded-constructor marker falls
**2,958 → 160**, and legacy `this.ctor(...)` text falls **2,186 → 45**. Real
`: base(...)` initializers rise **5,960 → 9,530** and `: this(...)` initializers
rise **0 → 325**. The proof remains conservative: exact allocation identity,
typed current-constructor `this`, one closed metadata constructor, and a known
reference-type inheritance chain are required. Ambiguous cases remain visible.

There are still 8,067 into-block gotos, 112,423 unresolved `object objN`
declarations, and broader semantic/compiler blockers. A clean syntax gate is not
proof that the recovered game is semantically equivalent or compile-ready.

## Run or test on Windows (PowerShell)

Python 3.13 was used for release validation. A .NET SDK was unavailable in this
environment; .NET 8 is needed only for the optional compiled-pattern smoke, not
for normal Python decompilation/tests.

```powershell
python -m pip install -r requirements-dev.txt
$env:PYTHONHASHSEED = "0"
$env:IL2CSHARP_METADATA = Join-Path $PWD "testgame\ShiftAtMidnight_Data\il2cpp_data\Metadata\global-metadata.dat"
$env:IL2CSHARP_BINARY = Join-Path $PWD "testgame\GameAssembly.dll"
python -m pytest -q
```

Release result: **358 passed**. Without the fixture environment variables, the
260 portable tests pass and the 98 licensed-fixture tests are skipped.

Fresh focused emission (keep generated experiments separate):

```powershell
python il2csharp.py testgame --only Assembly-CSharp --types PeopleWalkPath --strict -o clean_out
```

For the full tree, omit `--only` and `--types`. `--strict` fails on lifting
failures/fallbacks or missing backends; it is not rollback or C# compilation.
Use a new output directory when changing filters to avoid stale output.

## Optional compiled C# smoke

With the .NET 8 SDK installed:

```powershell
python tools/csharp_smoke.py --out work/csharp-smoke --dotnet dotnet
```

This generates small fragments through the real lifter/CFG loop emitter,
compiles and runs loop-header, array-identity, struct-return, and scalar-root
checks, then builds an emitter-generated unsafe project. It last passed for
Review 80 and was not rerun for Reviews 81–84 because no .NET SDK was available.
It does **not** compile `final_out/` or run the supplied game. Remaining goto
scopes, unresolved values, definite assignment, references, ABI gaps, and SIMD
semantics still prevent calling the complete recovered source compile-ready.

## Handoff map

- `REVIEW84.md`: current fixes, proof boundaries, results, and reproduction.
- `todo.md`: current open work; `new.md` §0bb: release/history record.
- `CLAUDE.md`: architecture and mandatory correctness/validation guardrails.
- `tests/goldens_review84.json`: current 64-case snapshot version.
- `tests/goldens_review83.json`, `goldens_review82.json`,
  `goldens_review80.json`, `goldens_review79.json`, and
  `goldens_review77.json`: preserved history.
- `validation_reports/review84/`: current complete evidence.
- `validation_reports/review83/`: previous release evidence.
- `REVIEW.md`, `REVIEW78.md`, `REVIEW79.md`, `REVIEW80.md`, `REVIEW81.md`,
  `REVIEW82.md`, and `REVIEW83.md`: history.
- `work/`: development archaeology. Old absolute-path probes remain historical;
  prefer portable `tools/` commands for current validation.

Keep this archive private: your supplied licensed game fixtures are not part of
an openly redistributable decompiler release. Their SHA-256 hashes are verified
unchanged in `validation_reports/review84/summary.json`.
