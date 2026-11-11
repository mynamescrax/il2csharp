> **Historical document — Review 78.** Retained as provenance, not current
> release instructions. Review 79 is current; see `REVIEW79.md`, the live
> `todo.md`, and `validation_reports/review79/`. Past counts and unresolved
> statuses below describe their original release, not today's replacement.

# Review 78 — source recovery and native-grounded TODO fixes

Date: 2026-09-08. This is a private replacement of the supplied `il2csharp/`
project, not a modified game executable. The supplied game DLL and metadata
are included unchanged at the user's request. They were read statically, never
executed. Keep this archive private; the game assets are not redistributable
project fixtures.

## What was actually in the upload

The two source SHA-256 hashes exactly matched Review 77's **baseline**, not its
claimed final source (`validation_reports/summary.json`). The review notes,
tests and old reports had been included without the reviewed source changes.
The original suite reproduced **56 failures / 80 passes**. The archive's actual
`final_out/` held **489 C# files, all under Assembly-CSharp**; the older notes'
"six assemblies / 391 files" were not an accurate inventory of this upload.
It was not used as a baseline or as a source for new snapshots.

The missing Review 77 fixes were restored first: Win64 positional tail-call
arguments, unknown-pointer cleanup ordering, input discovery, explicit file
options, functional type filtering, and visible strict/fallback/emission
failure accounting. That restored **136/136 supplied tests** before any new
TODO implementation. No snapshot was changed to accomplish this.

## New changes

### 1. Preserve every field in a packed Boolean immediate store

`InventoryManager.AutoLetGoOfClick` (MethodDef 25620, VA `0x1806fc340`) is not a
byte `mov ...,1`, as the TODO guessed. Its body is:

```asm
mov word ptr [rcx+4F0h],101h
ret
```

The word writes **two adjacent Boolean fields**. `IMMEDIATE16` was missing
from `_src_text`, and the store renderer considered only the first field.
The corrected result is:

```csharp
this.letGoOfInteract = true;
this.letGoOfClick = true;
```

`_coalesced_bool_store` requires exact metadata coverage of every byte in a
2/4/8-byte immediate store, distinct field identities, canonical Boolean
bytes and non-explicit layout. It materializes live old field values before
either write. Mixed/padded/unproven writes are not guessed: their entire
native width is retained in a raw store, preserving the known first field's
old-value aliases. Ordinary one-byte writes remain unchanged. Standalone
word immediates now decode; signed Int16 stores retain their signed value.
This is **not** general packed struct or float-field initialization recovery.

### 2. Recover register/memory arithmetic in proven-acyclic bodies

In `<ReloadSMG>d__299.MoveNext` (MethodDef 25758), the real capacity operation
is `sub ecx,[r8+rax*4+20h]` at `0x18053eb53` (and the corresponding EDX
instruction at `0x18053eb6b`). The general GPR arithmetic handler understood
register/immediate operands but replaced memory operands with `?`. It now
reads the operand through the existing typed memory loader; three-operand
IMUL memory sources and word immediates are covered too.

The resulting capacity checks retain `30 - objN[index]`, not `30 - unknown`.
This was an **independent cause**, not merely a downstream effect of the array
local's wrong declaration as the old TODO suggested.

**Deliberate scope guard:** the first wider implementation was rejected.
MethodDef 11974 (`StreamReader.ReadSpan`) revealed that existing use-binding /
loop structuring can lift a freshly materialized loop-header field difference
outside `while`, even though native `0x181c57577` branches back to
`0x181c57470` and `_charPos` changes each iteration. New operand recovery
therefore stands down for methods with native back edges or indirect
dispatch. Those paths retain the old honest unknown. The original ReadSpan
snapshot still passes unchanged; no unsafe snapshot was accepted.
`rejected_unguarded_snapshot_diffs.txt` records the rejected experiment, not
released output. The broader loop-header/liveness problem remains open.

### 3. Do not infer an array as an integer from address arithmetic

`_hint_tok` no longer gives array expressions an Int32 hint merely because
they participate in GPR address arithmetic. In ReloadSMG, `add r8,20h` skips
the array header; it does not convert `itemStorages` from `int[]` into `int`.
The array remains typed, and the final redundant/mistyped array reload folds
away. This does not attempt general alias analysis or loop liveness.

### 4. Resolve the narrow shared static-conversion family by real types

`_shared_static_arg_target` proves a unique exact value-type parameter match
only when **every** candidate is a one-GPR-argument, one-GPR-return static
method. Receiver, pointer/byref, floating ABI, hidden-sret, generic and
multiple-match cases remain unresolved. Field/parameter attribute bits do
not change nominal type identity. No native address or game type name is
hardcoded into the resolver.

`InventoryManager.Shoot` (MethodDef 25687) now recovers
`LayerMask.op_Implicit(this.shootable)` at the eleven-owner identity body
`0x180894a90`. Its nine-owner `0x180895b20` call deliberately remains shared:
that Vector3-returning body receives the return buffer in RCX and the real
receiver in RDX. It needs a separate sret-aware receiver proof, not a guess
from argument zero.

### 5. Portable replacement and inspection tools

- `tools/inspect_methods.py --mi ...` selects exact MethodDef rows;
  `--va` still lists all shared owners of an address.
- New sweep reports reference adjacent manifests by relative name. Comparison
  also relocates legacy absolute manifest references when their old paths no
  longer exist.
- `tools/verify_release.py` checks the full replacement's `SHA256SUMS.txt`
  using only the Python standard library.
- Both core sources retain CRLF; `il2csharp.py` retains its UTF-8 BOM.
- The old partial/mixed generated folder is replaced only after the complete
  strict build and syntax gate. Generated caches are not included.

## Observed supplied-output improvements

Within the supplied `InventoryManager.cs`, genuine `unknown` tokens decrease
from **17 to 10**, raw `sub_...` calls from **439 to 407**, and the mistyped
`int <- itemStorages` declaration from **1 to 0**. Goto statements remain
**264**; this release does not claim a control-flow readability rewrite.
These figures compare the actual supplied generated file with the new one,
not a controlled full-tree source baseline. The complete direct sweeps supply
that separate comparison. See `assembly_csharp_comparison.json` and the
compressed normalized diff; generated C# line endings differ (Windows CRLF
in the upload, Linux LF in the rebuilt output), so byte changes alone are
not a content-change count. The two core Python source files retain CRLF/BOM.

## Corrected open leads

The alleged "NaN predicate" `sub_1804ce6d8` is a **square-root/domain-error
helper**, not a Boolean predicate. Its full body includes `sqrtsd`, sign/
zero/NaN checks and error handling; its error-handler name constant is the literal `sqrt`. Callers use `cvtps2pd`, compare the low
lane against zero, use `sqrtpd` on the normal path, and call the helper on
the negative-domain path. The missing packed low-lane conversion/root
semantics and correct XMM argument/result handling remain open. Naming it
`IsNaN` would have been incorrect; no such rename was shipped.

Still open: sret-aware shared RaycastHit receiver resolution; string-Concat
array-store twins and allocation/alias handling; mixed-field packed stores
(e.g. a float plus an adjacent zero); loop-header statement placement,
loop-carried liveness, unresolved values, goto scope violations, multi-span
SEH, constructor/sret/stack-argument gaps and ARM64 semantics.

## Validation

| Check | Release result |
| --- | ---: |
| Tests, including original game snapshots | **193 passed** |
| Portable tests | 125 |
| Original MethodDef snapshots, unmodified | 64 |
| New native-grounded game assertions | 4 |
| Emitted C# type files | 11,107 |
| Emitted method bodies | 115,658 |
| Failed bodies / structured fallbacks / type emission failures | 0 / 0 / 0 |
| Strict full-build exit status | 0 |
| Parser bad files / ERROR / MISSING / RECOVERY | 0 / 0 / 0 / 0 |
| Native-backed MethodDefs directly swept | 116,178 |
| Direct-lift crashes | 0 |
| Changed method-body hashes vs uploaded source | 3,492 |
| Per-method structural metric changes | 0 |
| Remaining into-block gotos (affected methods) | 13,642 (2,997) |

The repeated uploaded-source sweep and the final sweep use the same validator
and `PYTHONHASHSEED=0`. Per-method hashes and structural comparisons, native
before/after evidence, source/fixture hashes, logs and environment versions
are in `validation_reports/review78/`. `comparison.json` records the full
method-by-method delta; differences are observations, not semantic proof.
The original 64 snapshots were **not regenerated**.

**Clean parsing is not C# compilation or semantic equivalence.** No .NET build,
gameplay run, performance benchmark or ARM64 fixture validation is claimed.
Unresolved values, raw pointers, shared calls and invalid goto scopes still
prevent treating the generated output as a drop-in game source project.

## Reproduce

See `REPLACEMENT.md` for extraction and Windows environment setup. From this
project's root, after installing `requirements-dev.txt`:

```bash
PYTHONHASHSEED=0 python -m pytest -m "not game"
PYTHONHASHSEED=0 python il2csharp.py testgame --strict -o rebuilt_out
python tools/validate_corpus.py parse rebuilt_out --report work/rebuilt_parse.json
PYTHONHASHSEED=0 python tools/validate_corpus.py sweep --metadata testgame/ShiftAtMidnight_Data/il2cpp_data/Metadata/global-metadata.dat --binary testgame/GameAssembly.dll --report work/rebuilt_sweep.json
python tools/verify_release.py
```

Set `IL2CSHARP_METADATA` and `IL2CSHARP_BINARY` to the same fixture paths before
running `python -m pytest` for all 193 tests. Native checks can be reproduced
with `tools/inspect_methods.py --mi 25620 25758 25687 11974` plus those two
file options. No game executable needs to be launched.
