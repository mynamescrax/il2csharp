# Review 79 — struct-return calls, array identity, and C# build readiness

Date: 2026-09-08. This is a complete private replacement of the supplied
`il2csharp/` folder. The original game DLL and metadata are retained byte-for-byte.
They were read statically, **never executed**. Keep these licensed fixtures private.

## Outcome and limits

- **252 tests passed**: 180 portable tests, the same 64 MethodDef snapshot cases,
  and 8 native-backed assertions across Reviews 78/79.
- Full strict rebuild: **11,107 C# type files, 91 project files, 115,658 lifted
  bodies; 0 failed bodies, 0 structured fallbacks, 0 type-emission failures**.
- Complete syntax gate: **0 bad files / 0 ERROR / 0 MISSING / 0 recovery nodes**.
- Full direct sweep: **116,178 methods / 0 crashes**. 2,485 body hashes changed
  from the verified uploaded source; 0 methods changed structural audit metrics.
- The instruction-generated C# smoke **compiled and ran successfully** on .NET 8.
  A second smoke compiled an actual emitter-generated netstandard2.1 project
  containing unsafe code, with 0 warnings and 0 errors.

**This is not a build or execution of the entire recovered game.** The complete
`final_out/` still contains unresolved values/calls, invalid goto scopes,
missing assembly references, partial SIMD semantics, and other reconstruction
limits. A clean tree-sitter gate is not C# compilation or semantic equivalence.
No full-game build, gameplay run, ARM64 validation, or performance improvement
is claimed. The compiled smokes cover only the small patterns described below.

## Baseline was verified before editing

Unlike the mismatch diagnosed in Review 78, this upload's source and tests agree:
all **193 supplied tests passed unchanged**. The supplied complete output was
syntax-checked again, and the unchanged source was directly swept with the same
validator and `PYTHONHASHSEED=0` used for the final source. The original Review 77
snapshot file is retained unchanged as `tests/goldens_review77.json`.

## 1. Resolve the shared two-pointer struct-return family

At the shared native body `0x180895b20`, **RCX is a 12-byte return buffer and RDX
is the input pointer**. Its nine owners include RaycastHit.get_point,
Bounds.get_center, Ray.get_origin, and a static ReadVector3(int*) function.
A receiver-only guess from RCX can choose a type belonging to the output buffer.

`Lifter._shared_sret_receiver_target` now requires:

1. Concrete address-taken lvalues for both slots, not uninitialized registers.
2. One consistent source-pointee identity from the expression/slot/type hints.
3. Every candidate to return a known, equally sized hidden-buffer value and to
   consume exactly one source pointer: an instance value-type receiver without
   parameters, or one explicit pointer/byref static parameter.
4. A unique exact pointee match. Generic/unknown layouts, mixed ABIs, opaque
   pointers, inconsistent hints, and duplicate identities stay unresolved.

The return buffer's type is **never** used to select the receiver. The old RCX
base-chain heuristic stands down if an sret candidate is present. Unresolved
shared calls also retain the hidden-buffer slot in their argument bound rather
than dropping the actual receiver.

Native-backed `InventoryManager.Shoot` (MI 25687) now renders both point reads as
`buffer = hit.point;`. The existing sret path returns the buffer alias in RAX,
so subsequent component reads name `.x`/`.z` instead of dereferencing an untyped
`sub_...` result. No game name or native address is hardcoded in the resolver.
This does not solve every generic, virtual, tail-call, or register-held-buffer ABI.

## 2. One native array allocation must remain one object

The existing use-count binder intentionally skips short/non-call text. As a
result, `new string[11]` and `new byte[1025]` could be printed again at every use,
creating separate arrays in the recovered C# instead of one shared allocation.

`_array_allocation` materializes a typed local **at the allocation instruction**,
not by rewriting arbitrary matching text later. Distinct identical allocations
get different identities; register copies and subsequent stores reuse the
original reference. Dry-pass identities remain stable without emitting code.

This rollout is guarded by **actual CFG acyclicity**. A backward branch to a
shared return/error tail is not automatically a loop, so a topological test
allows proven acyclic bodies such as Shoot. Real cycles and unresolved indirect
dispatch retain the previous conservative representation. The older
`_memory_rhs_loop_guard` is untouched; this does not fix loop-header liveness.

A separate small fix allows a string-array element's LEA to render its real
address (`&array[index]`). It then matches the preceding plain store, so the
existing GC-barrier twin suppression removes the duplicate pointer write.
No global text deduplication or potentially effectful store deletion was added.

Shoot's 11-element and 7-element logging arrays now each allocate once, receive
exactly one store per index, and pass that same reference to `string.Concat`.
The Steamworks `set_m_rgchTags` body (MI 98685) likewise retains its one native
1025-byte allocation before the encoding call. Its remaining stack-argument
recovery gap is not hidden or claimed fixed.

## 3. Keep SQRTSS's C# result a float

`Math.Sqrt` returns double, but the native `SQRTSS` instruction returns single
precision. Its output is now `(float)Math.Sqrt(value)`, which works on Unity
profiles without requiring MathF. `SQRTSD` remains a double expression. An
unavailable source stays unknown rather than becoming a fabricated zero.

The native `Quaternion.Normalize` body (MI 55666, `sqrtss` at `0x182bd4ba6`)
provides a real example. The compiled smoke checks both widths, finite values,
signed zero, subnormal/large inputs, infinity, and NaN/domain cases under the
normal .NET floating-point environment. It does not model arbitrary MXCSR modes.

**The packed CVTPS2PD/SQRTPD pipeline and native sqrt/domain-error helper remain
open.** No IsNaN rename or broad SIMD/helper-ABI claim was made.

## 4. Generated projects accept the unsafe code the emitter writes

Every emitted `.csproj` now sets `AllowUnsafeBlocks=true`. Previously the output
contained `unsafe { ... }` blocks while the generated project did not permit
them. This removes that configuration-level compiler blocker without suppressing
real diagnostics, inventing dependencies, or promising a full project build.

## Regression and output review

- New portable tests cover positive proofs and conservative rejection cases,
  distinct allocation identities, register aliases, array-store/barrier twins,
  acyclic backward tails versus real cycles, scalar root types, and actual
  generated project settings.
- Original 64 snapshot cases were retained. **63 bodies are byte-identical**;
  only MI 98685 changed. Its full native instructions and before/after diff were
  reviewed, and `goldens_review79.json` was produced **after** the complete
  strict build, parse gate, and sweep. The old snapshot was not silently edited.
- Review 78's formerly unresolved-point assertion now checks the proved `.point`
  result instead of pinning the old bug. Its other assertions remain active.
- The complete output comparison reports 1,189 changed C# files, not just
  timestamps/line endings. Selected changed output was read again after the build.
- InventoryManager's raw `sub_` tokens fall **407 → 308**;
  shared point calls **87 → 0**;
  raw string-array pointer twins **18 → 0**.
  Its 264 gotos and 10 unknown tokens are unchanged,
  not hidden with fabricated values. These are file-level lexical measurements.
- Remaining into-block gotos: **13,642 sites in 2,997 methods**. This remains
  a real full-compilation blocker, not a cosmetic issue.

Evidence: `validation_reports/review79/README.md`, `summary.json`, source diff,
full method manifests/comparisons, output diff, native before/after records,
compiler smoke source/logs, and final release-copy test/checksum results.
Historical Review 77/78 documents and work notes remain available, clearly marked.

## Reproduce

See `REPLACEMENT.md` for Windows setup and direct-overwrite instructions.

```bash
python -m pip install -r requirements-dev.txt
PYTHONHASHSEED=0 python -m pytest -m "not game"
PYTHONHASHSEED=0 python il2csharp.py testgame --strict -o rebuilt_out
python tools/validate_corpus.py parse rebuilt_out --report work/rebuilt_parse.json
PYTHONHASHSEED=0 python tools/validate_corpus.py sweep --metadata testgame/ShiftAtMidnight_Data/il2cpp_data/Metadata/global-metadata.dat --binary testgame/GameAssembly.dll --report work/rebuilt_sweep.json
python tools/csharp_smoke.py --out work/csharp-smoke --dotnet dotnet
python tools/verify_release.py
```

Set `IL2CSHARP_METADATA` and `IL2CSHARP_BINARY` to the supplied fixture paths,
and `PYTHONHASHSEED=0`, before running all 252 tests. The compiler smoke requires
an installed .NET 8 SDK; the Python tests do not. No game executable is launched.
