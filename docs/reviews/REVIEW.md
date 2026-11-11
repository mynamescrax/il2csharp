> **Historical document — Review 77.** Retained as provenance, not current
> release instructions. Review 79 is current; see `REVIEW79.md`, the live
> `todo.md`, and `validation_reports/review79/`. Past counts and unresolved
> statuses below describe their original release, not today's replacement.

# Review 77 — Windows x64 correctness and reproducible validation

> Historical Review 77 report. For the current replacement, see `REVIEW78.md`.
> Inspection of the uploaded RAR found that its actual source hashes matched
> this review's **baseline**, not its final source. Review 78 restores the
> missing code, adds new guarded fixes, and supplies the complete generated tree.
> The original report below is preserved as history, not a current claim.

Date: 2026-09-08

This handoff starts from the six uploaded project files and the supplied
`GameAssembly.dll` / `global-metadata.dat` pair. The game inputs are read-only
test fixtures: they were not executed, modified, or bundled with this project.
No existing `final_out/` directory was promoted or replaced.

## Implemented

### 1. Recover the real arguments of resolved direct tail calls

The structured and linear JMP handlers both skipped the ordinary call's
signature-aware argument preparation. They read only RCX/RDX/R8/R9, even when a
declared floating-point argument lived in XMM0–3. A meaningful-looking GPR could
be completely unrelated: class initialization often left `typeof(Math)` in RCX.

Both handlers now call `Lifter._tail_method_args`:

- Select floating-point arguments by their **Win64 parameter position**,
  including the receiver position; do not reuse a stale parallel GPR.
- Refresh XMM evidence at the tail site, not from a previous call.
- Apply the existing metadata-aware `ref`, Boolean-literal and by-value-struct
  argument rules, with pointee/local type hints.
- Do not interpret a byref float as an XMM argument.
- Keep genuine pointer parameters as addresses.
- Do not fill an unmodelled fifth/stack argument with a leftover XMM value.
- Do not reuse a previous delegate call's generic-class substitutions.
- Preserve the existing low-level path for hidden-sret and generic-return
  tails. Unresolved/shared-target paths are not guessed.

Native checks include:

| MethodDef | Native VA | Check |
| --- | --- | --- |
| 1354 | `0x181C0EB10` | Convert.ToInt32(float): native `cvtss2sd` feeds XMM0 |
| 2157 | `0x181CA4A60` | Math.Round(double, int): XMM0, RDX, R8 |
| 2158 | `0x181CA4DF0` | Math.Round(double, MidpointRounding): same positional ABI |
| 4687 / 4688 | `0x181D168B0` / `0x181D16D80` | ExecutionContext.Capture/FastCapture forward a byref stack slot |
| 12162 | `0x181C65640` | UnmanagedMemoryStream.Position calls Interlocked.Read by reference |
| 23546 / 23547 | `0x180500390` / `0x180500540` | AudioVolumeSliders forwards its float parameter and a true Boolean |
| 25663 | `0x180709D80` | InventoryManager.SpeedBoost loads the three-second Invoke delay into XMM2 |
| 31361 / 31362 | `0x1825D2FB0` / `0x1825D2FF0` | InputInteractionContext's TriggerState is a byref argument |
| 31371 | `0x1825D2CF0` | ControlIsActuated forwards TriggerState in RCX and threshold in XMM1 |

Examples from actual recovered output:

```csharp
// Before:
return Math.Round(typeof(Math), digits, 0);
return Convert.ToInt32(typeof(Convert));
return InputActionState.IsActuated(&this.m_TriggerState, obj3);

// After:
return Math.Round(value, digits, 0);
return Convert.ToInt32((double)(value));
return InputActionState.IsActuated(ref this.m_TriggerState, threshold);
```

Gameplay wrappers now also retain values such as
`this.SetMusicVolumeInternal(volume, true)` and
`this.Invoke("SpeedBoostFinish", 3.0f)` instead of unrelated/undefined GPR
temporaries. The native load into XMM2 and its constant pool were inspected.

### 2. Repair unknown pointer operands before pointer-syntax rewriting

The uploaded baseline contains invalid expressions in
`Unity.InputSystem/UnityEngine/InputSystem/Touchscreen.cs` and
`Obi/Obi/BurstDensityConstraintsBatch.cs`.

Two ordering defects share the same fix:

- `*(? + p)` was converted to `((byte*)? + p)[0]`. The new cast's closing `)`
  made the unknown-token scanner misclassify the operand as a ternary question
  mark; select completion then invented `: default`.
- `?*4` was interpreted as an unknown followed by a dereference of constant 4,
  not multiplication, because the unary-dereference guard does not consider
  `?` a value character.

The **existing quote/select-aware scanner** now runs before `_unsafify`, as well
as at its original post-pass position. That preserves `unknown` as an honest
placeholder without guessing an address or a value:

```csharp
// Native-style renderer input:
var result = *(ptr + ?*4 + 0x0);

// Recovered pointer arithmetic:
var result = ((byte*)ptr + unknown*4 + 0x0)[0];
```

Tests pin both repairs and real ternaries, negative/unary-pointer arms, quoted
question marks, and unknown return operands. No historical `sim_rewrite.py`
was supplied; the new tests invoke the actual renderer instead of copying its
rules, and the final sources are rebuilt and swept again.

### 3. Make the advertised CLI work

- Flat dump folders and direct binary paths now locate the matching metadata.
- A direct metadata path in the standard Unity layout reaches the correct
  game-root binary; the old file-path traversal stopped one directory short.
- `--metadata` and `--binary` support separately located or renamed files.
- Ambiguous discovery fails with an actionable message instead of selecting
  the first directory-walk result. An explicitly selected directory is not
  paired with an unrelated parent-directory binary.
- `--types` is no longer an ignored option. It matches full type names
  case-insensitively, traversing the actual nestedTypes relation. A nested
  match retains its entire top-level owner file. Symbol/string/header outputs
  remain unfiltered.
- Negative `--max-methods` values are rejected.
- Missing-backend diagnostics distinguish iced-x86 from Capstone.

A real-game direct-binary smoke test with `--only Assembly-CSharp --types
inventorymanager --decls-only --strict` emitted exactly
`Assembly-CSharp/InventoryManager.cs`; its syntax gate was clean.

### 4. Expose fallback and emission failures

Build summaries now distinguish failed method bodies, structured-to-linear
fallback attempts, and failed type emission. `-v` identifies a fallback's
MethodDef, native VA and exception. A fallback that also fails counts in both
the fallback-attempt and failed-body totals.

`--strict` returns nonzero when requested body lifting is unavailable or uses a
linear fallback. Unrecoverable body/type-emission failures return nonzero in
ordinary mode too. Output is still written where available; strict mode is an
exit-status policy, not a transactional rollback.

### 5. Add a portable test and validation kit

- Dependency lists for x64, optional ARM64, and development tools.
- Unit tests for ABI handling, input discovery, filters, failure reporting,
  renderer ordering, and validator edge cases.
- A fresh optional real-game snapshot suite, keyed by **MethodDef row**, not
  shared native address. These are not the missing historical 50 goldens.
- A direct structured-lift sweep, per-method hash manifests, parser gate,
  before/after comparison, native-method inspection, and gated snapshot
  generation.
- CRLF-preserving `.gitattributes`. Both original Python sources retain CRLF
  (and `il2csharp.py` retains its original UTF-8 BOM); new tools/tests use LF.

## Validation results

Validated against the **supplied Windows x64 game**, using Python 3.13.14,
iced-x86 1.21.0, tree-sitter 0.26.0 and tree-sitter-c-sharp 0.23.5.
Both direct sweeps use the same final validator and `PYTHONHASHSEED=0`.

| Check | Uploaded baseline | Updated source |
| --- | ---: | ---: |
| Emitted C# type files | 11,107 | 11,107 |
| Emitted method bodies | 115,658 | 115,658 |
| Failed method bodies | 0 | 0 |
| Structured fallbacks / type emit failures | Not separately instrumented | 0 / 0 |
| Files rejected by syntax gate | 2 | **0** |
| Parser ERROR / MISSING / RECOVERY nodes | 0 / 0 / 8 | **0 / 0 / 0** |
| Native-backed MethodDefs swept | 116,178 | 116,178 |
| Direct-lift crashes | 0 | **0** |
| Unclosed / underflow braces | 0 / 0 | 0 / 0 |
| Dangling gotos / empty argument slots | 0 / 0 | 0 / 0 |
| Into-block gotos (affected methods) | 13,642 (2,997) | 13,642 (2,997) |

- **136 tests passed:** 72 unit tests and 64 fresh real-game snapshots. The
  unavailable historical 50-snapshot suite was not run.
- The full updated emission completed with **`--strict`, exit 0**.
- **10,470 files are byte-identical; 637 changed**, with no files added or
  removed. The direct sweep changed **1,647 method-body hashes**, with no new
  crashes or per-method changes to the recorded structural audit metrics.
- The tail helper changed **1,186 argument sites across 1,145 methods** in the
  direct sweep. These observations are not a semantic proof of every method.
- The repeated baseline sweep reproduced **all 116,178 method-body hashes**.

`validation_reports/` contains the measured summaries, full per-method hash
manifests, tail-argument observations, before/after diffs, native inspections,
and build/test logs. `summary.json` records source and fixture SHA-256 hashes.
The proprietary game inputs and full generated trees are deliberately excluded.
**Clean parsing is not successful C# compilation or semantic equivalence.**

## Important validation details

On tree-sitter 0.26.0 with tree-sitter-c-sharp 0.23.5, the original tree's two
invalid files had **eight zero-width recovery identifiers**. Their ancestors
had `has_error=True`, but the leaf nodes were not labeled ERROR or MISSING.
Counting only those ordinary node types would therefore report misleading
zeros. The bundled parser gate rejects all unexplained root error flags and
reports these nodes separately as `RECOVERY`.

During development, the first empty-argument audit incorrectly masked string
operands to whitespace, mistaking calls such as `f(a, "text", b)` for empty
arguments. That was fixed and unit-pinned, as were valid array ranks and unbound
generic arities. A partial audit refresh was rejected when a subset re-lift did
not match the original full-sweep body hash at MethodDef 5481. The baseline was
therefore rerun from scratch with the final validator; discarded first-pass
counts are not used as before/after results.

These checks have different meanings:

- A parse gate checks **syntax**, not C# compilation.
- A structural sweep does not establish definite assignment or alias safety.
- Snapshots catch changes, including changes to existing mistakes; they are
  not semantic ground truth.
- The inspected native examples establish the targeted fixes, not correctness
  of every recovered method.
- Concurrent validation jobs are not a controlled performance benchmark.

## Reproduce

From this project's root (`il2csharp/`; the local game fixture lives in
`testgame/` — gitignored, read-only, never bundled):

```bash
python -m pip install -r requirements-dev.txt
PYTHONHASHSEED=0 python -m pytest -m "not game"

export IL2CSHARP_METADATA=/path/to/global-metadata.dat
export IL2CSHARP_BINARY=/path/to/GameAssembly.dll
PYTHONHASHSEED=0 python -m pytest

PYTHONHASHSEED=0 python il2csharp.py --metadata "$IL2CSHARP_METADATA" --binary "$IL2CSHARP_BINARY" --only Assembly-CSharp --strict -o out
python tools/validate_corpus.py parse out --report work/parse.json
PYTHONHASHSEED=0 python tools/validate_corpus.py sweep --metadata "$IL2CSHARP_METADATA" --binary "$IL2CSHARP_BINARY" --report work/sweep.json
```

Omit `--only Assembly-CSharp` for a full emitted tree. The sweep above already
walks all native methods; use its own `--only` option for a scoped sweep.

In PowerShell, set environment variables before invoking the same Python tools:

```powershell
$env:PYTHONHASHSEED = "0"
$env:IL2CSHARP_METADATA = "C:\path\global-metadata.dat"
$env:IL2CSHARP_BINARY = "C:\path\GameAssembly.dll"
python -m pytest
```

Do not regenerate snapshots merely to make a failing test green. First rebuild,
run both gates, compare per-file/per-method results and inspect the native
evidence. `tools/make_goldens.py --help` documents its required gate reports.

## Remaining priorities

1. **ABI gaps:** hidden-sret/generic-return direct tails, stack arguments beyond
   the first four positions, and constructor-initializer recovery. The tail
   constructor special case still has its old hardcoded no-argument base call;
   this review does not claim to fix it.
2. **Read-before-def and loop liveness:** unknown stores, stack slots and
   loop-carried copies remain the larger upstream correctness work. Do not
   hide them with wider trimming or arbitrary defaults.
3. **Existing structural work:** multi-span SEH, illegal goto scopes, coroutine
   and state-machine reconstruction, plus the remaining static-address cases.
4. **ARM64 semantics:** the supplied fixture is Windows x64. The Android
   registration/CFG scaffold is retained, but AAPCS64 entry binding, instruction
   semantics, ADRP reference recovery and ARM64 native goldens need a matching
   ELF/metadata fixture. No ARM64 validation is claimed here.

Updated scope and history also appear in `todo.md`, `new.md`, `README.md` and
`CLAUDE.md`.

### Evening note, 2026-09-08 (partial rebuild + InventoryManager read)

After this review's validation closed, a full rebuild into `final_out/`
was started and ABORTED mid-run (the Assembly-CSharp results were
already in hand). The disk tree is PARTIAL: 6 assemblies
(Assembly-CSharp 391 files, mscorlib, System, System.Xml,
Unity.InputSystem, UnityEngine.UIElementsModule), built from this
review's source. It is NOT a candidate: do not gate, promote, or
regenerate snapshots off it. The line above ("no `final_out/` promoted
or replaced") describes this review's own validation and still holds.

`InventoryManager.cs` from that partial tree (12,435 lines) was read end
to end and three unknown-feeding callees were probed to ground truth;
findings and five sized leads are recorded in `new.md` §0au and
`todo.md`'s head. `todo.md`/`new.md`/`README.md`/`CLAUDE.md` now name
this review as the current source state.