# il2csharp

`il2csharp` is an IL2CPP → C# decompiler with real method bodies:
`global-metadata.dat` + `GameAssembly.dll` / `libil2cpp.so` in, a C# source
tree out, with every method body reconstructed from the native x64 code and
cross-referenced against IL2CPP metadata.

**Current source (2026-11-26):** On the second *Shift At Midnight* v31 build,
the strict game-script rebuild lifted 6,791 bodies into 503 files with no
failures or fallbacks. All files passed the syntax gate. The latest census
still has **396 unresolved shared calls** and **3,188 `object objN`
declarations**. See [recovery notes and compiled behavior checks](docs/todo.md#shift-at-midnight-second-v31-build-2026-11-25).

**Promoted fixture: r11 (2026-10-01).** 1435 tests passed (1197 portable + 238 game
fixture-backed); the strict build covers 11,183 files / 114,458 bodies with
0 failures or structured fallbacks; the brace audit and the tree-sitter
parse gate are clean. The recovered game **does not yet compile** — clean
parsing and passing tests are not semantic equivalence. Current work and
the remaining compiler backlog live in [`docs/todo.md`](docs/todo.md).

## Example

Unlike signature-only dumpers (Il2CppDumper) or heavyweight binary
decompilers (Ghidra headless), every method gets an actual reconstructed
body:

```csharp
public static void ResetSave(int saveSlot) // RVA: 0x1805adb30
{
    System.IO.File.Delete(System.String.Concat(t0, "/", saveSlot.ToString(), "save.data"));
    UnityEngine.Debug.Log(System.String.Concat("Save file deleted: ", saveSlot.ToString()));
    SaveSystem.SavePlayerPrefs();
}
```

## Quick start

Requires Python 3.9+ and [`iced-x86`](https://pypi.org/project/iced-x86/)
for body lifting (bodies are skipped gracefully without it):

```text
pip install -r requirements.txt

python il2csharp.py --demo --strict
```

**No game needed:** `--demo` creates a small v31 metadata file and x64 PE in a
temporary directory and runs them through the normal decompiler. Open
`il2csharp_out_demo/Assembly-CSharp/Demo/ScoreRules.cs` to see the recovered
arithmetic, branch and byte-order conversion. A successful strict run reports
**3 type files, 9 lifted bodies, 0 failures** across two assemblies. Use `-o`
to pick a different output folder.

For a game, run `python il2csharp.py <target> -o <outdir>`.
`<target>` is a game folder (containing `<Data>/il2cpp_data` and
`GameAssembly.dll`) or a direct path to `global-metadata.dat` / the binary.
Common options: `--only Assembly-CSharp`, `--metadata FILE --binary FILE`,
`--decls-only`, `--strict`, `--asm`, `--probe`, `--workers N` (parallel
assembly emission; 0 = half the cores, max 8); run with `--help` for the
full list.

## Output

One `.cs` file per type, laid out like a project and openable in an IDE via
the generated `.csproj` files:

```text
<out>/
  Assembly-CSharp/                 # one folder per assembly (+ .csproj)
    SaveSystem.cs                  # one file per type, nested types inside
    FIMSpace/ProceduralAnimation/...  # namespace folders
  mscorlib/
    System/Collections/Generic/List_1.cs
  script.json                      # Il2CppDumper-style address map
  stringliteral.json               # all managed string literals
```

Each type file carries full declarations (fields with offsets, properties,
events) and every method its lifted body with a `// RVA/VA` comment.

## Supported targets

* Metadata **v24.2 – v31 and v39** (Unity 2019 – Unity 6.4); primary testing
  on v31 (Unity 6000.0.69f1) and v39 (Unity 6000.3.10f1, Windows x64).
* **PE32+ (x64)** `GameAssembly.dll`; basic ELF64 `libil2cpp.so`.
* x64 codegen (Windows and Linux/Android conventions).

## What gets recovered

A short sample of the native-construct coverage:

* calls — direct, virtual, delegate and icall thunks render
  `Type.Method(args)` / `recv.Method(...)` with real metadata names;
* properties, indexers, events, `lock`, `using`, `foreach`, `is`,
  null-conditional, ternaries and string interpolation;
* `new`/array allocation, field and element stores, GC write barriers,
  Win64 struct returns (sret);
* metadata usage slots (`typeof(X)`, string literals, static-field refs),
  jump tables, `try`/`catch`/`finally` (SEH), counting loops;
* constant typing/folding, precedence-aware parentheses, dead-local
  cleanup, type-derived local names.

Full mapping with ground-truth notes:
[`docs/construct-mapping.md`](docs/construct-mapping.md).

## How it works

1. **Metadata frontend** parses every table of `global-metadata.dat`.
2. **Binary frontend** locates the registration structs structurally, then
   decodes codegen modules, generic method tables, field offsets and
   vtables.
3. **Lifter** symbolically executes the real x64 instruction extent over
   iced-x86 (two passes for phi merges), carrying an IL2CPP type tuple and
   a coarse kind per value.
4. **Decompiler** builds a CFG, recovers loops/conditionals/SEH regions,
   then runs a fixed-order statement pipeline (`for`, `switch`, `lock`,
   `using`, `foreach`, interpolation, DCE, renaming).
5. **Emitter** writes one file per type plus project files and JSON maps.

Architecture details: [`CLAUDE.md`](CLAUDE.md) and
[`docs/reference.md`](docs/reference.md).

## Project layout

```text
il2csharp.py        CLI launcher
il2cpp/             the package: metadata/binary frontends, runtime,
                    lifter/, dec/ pipeline, emitter/headers/cli
tests/              portable unit tests + fixture-backed regressions
tools/              inspect_methods.py, validate_corpus.py, validator kit
docs/               reference docs, review log, public-release checklist
validation_reports/ frozen gate evidence
```

`final_out/` (last promoted output), `testgame/` (licensed fixture) and
`work/` (probes and gates) are local-only and git-ignored; a fresh clone
contains the decompiler, tests, tools and docs. See
[`docs/public_release.md`](docs/public_release.md) for the fixture rules
and the 2026-09-28 history-scrub record.

## Testing

```text
python -m pip install -r requirements-dev.txt
python -m pytest -q tests/test_demo.py  # end-to-end, no game
python -m pytest -q -m "not game"   # portable
python -m pytest -q                 # + fixture-backed (needs testgame/)
```

The demo tests compare serial and parallel output byte-for-byte and check
the recovered bodies and address map. With a .NET 8+ SDK installed, they
also build both generated projects offline and run score and timer checks
against the emitted C#. Only that behavior check needs .NET.

Corpus gates on a built tree:

```text
python tools/validate_corpus.py parse  <built-tree> --report parse.json
python tools/validate_corpus.py sweep  --metadata <file> --binary <file> --report sweep.json
```

Latest r11 evidence: `validation_reports/promotion_r11.json` (aggregate
`735f2e9a…1707f`, 0 mismatches); r10 audit evidence: `validation_reports/audit_batch3.json`.
Gate history and methodology: [`docs/reference.md`](docs/reference.md).

## Limitations

* The recovered tree **does not compile yet** (last whole-tree Roslyn
  probe: 10,602 errors in the fix-123 era; the remaining classes are
  ranked in `docs/todo.md`).
* Shared-body collisions keep an honest
  `sub_x/*shared body, N candidates*/` marker when identity cannot be
  proven.
* Some constructs are only partially recovered (multi-span SEH trys,
  enumerator-based `foreach`, unresolved stack-frame slots, scratch
  `data_`/`sub_` names).
* Mach-O and 32-bit binaries are unsupported; klass offsets are calibrated
  for Unity 6 / metadata v31; newer metadata layouts carry their own
  section table instead of the v24-v31 header.

Full list with evidence:
[`docs/construct-mapping.md#not-yet-done`](docs/construct-mapping.md#not-yet-done).

## License

MIT — see [`LICENSE`](LICENSE). It covers the decompiler source, tests,
tools and docs only; it does not cover any game data or decompiled output,
which must not be redistributed.

## Development

[`docs/README.md`](docs/README.md) maps every document,
[`CLAUDE.md`](CLAUDE.md) holds the architecture and validation guardrails,
and [`AGENTS.md`](AGENTS.md) is the new-session tutorial.
