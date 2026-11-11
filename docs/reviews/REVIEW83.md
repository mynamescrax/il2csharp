# Review 83 — provable shared-body return types and preserved side effects

**Completed:** 2026-09-10  
**Scope:** ambiguous native addresses shared by multiple metadata methods  
**Authority:** `validation_reports/review83/summary.json`

Review 82 made concrete locals readable but deliberately left genuine unknown
results as `object objN`. The largest high-confidence family was not a naming
problem: IL2CPP often maps several managed methods to one native body. The exact
method identity can remain ambiguous even when **every possible owner declares
the same closed return type**.

Review 83 uses that all-candidate fact without inventing a method name. The call
still renders honestly as `sub_<va>/*shared body, N candidates*/`, but its return
register, local type, Boolean use, `void` side effect, and observed struct-return
buffer can now be handled correctly.

## Outcome

- **7,402 of 13,721** ambiguous shared addresses have an exact, ABI-supported
  return-type consensus across all **34,930** of their candidates.
- Generated `object objN` declarations fell **116,839 → 113,155**
  (**-3,684 / -3.153%**).
- Shared-call `object` result declarations fell **11,031 → 5,368**
  (**-5,663 / -51.337%**).
- **3,543** previously lost calls now remain as explicit side-effect statements;
  every one has metadata consensus `void`.
- **2,550** shared calls now render directly in conditions; every one has
  metadata consensus `bool`.
- The complete output keeps the same **11,200 files**: **11,107 C# type files**
  plus 91 project files. There are 1,376 changed C# files and no additions or
  removals.
- The strict build recovered all **115,658 bodies** with 0 failures, 0 structured
  fallbacks, and 0 type-emission failures.
- All **11,107** generated C# files pass the tree-sitter syntax gate with 0
  ERROR, MISSING, or recovery nodes.
- The direct **116,178-method** sweep has 0 crashes, 0 brace/dangling/empty-arg
  failures, and no structural-metric changes from Review 82.
- **318 tests pass:** 228 portable, 64 licensed snapshots, and 26 native-backed
  semantic assertions.

The recovered game was not compiled or executed. A clean syntax gate is not a
semantic-equivalence claim, and this remains recovered inspection/development
source rather than a drop-in game project.

## 1. Consensus means every candidate

`Il2Cpp.shared_return_type(target)` considers the complete metadata-owner set for
one ambiguous native address. It returns a type only when every candidate is
readable, fully closed, structurally identical, and covered by the current
Win64 return ABI model.

The proof is deliberately stricter than matching printed names:

- primitive, class, pointer, array, and generic-instantiation identity is
  compared structurally;
- parameter/field attribute bits do not change identity, while `byref` does;
- root `VAR`/`MVAR` returns are inflated from the candidate's MethodSpec class or
  method arguments;
- an open generic anywhere below the root declines rather than printing `T` as
  if it were concrete;
- one unreadable candidate, one disagreement, or one unsupported ABI class
  declines the entire address.

Census of all 13,721 ambiguous addresses:

| Result | Addresses |
|---|---:|
| Exact supported consensus | 7,402 |
| Open or unreadable candidate | 2,255 |
| Candidate type disagreement | 4,047 |
| Unsupported ABI or ref-return model | 17 |

The top consensus types are `void` (4,107 addresses), `bool` (899), `int`
(748), `float` (131), `object` (108), and `string` (101). `object` remains
`object`; consensus is evidence, not a promise that every result becomes more
specific.

## 2. ABI and ordering gates

A common managed type is not enough by itself. Review 83 also requires a return
ABI that the lifter can state exactly:

- by-reference returns decline because source-level `ref` return rendering is
  not complete;
- value types require a known, positive exact size;
- generic value types decline because an instantiated native size is not yet
  available;
- rare opaque runtime/modifier classes decline;
- a struct return is folded only when the current call actually supplies an
  observed address as its hidden output buffer.

The ambiguous-call arity trim now runs before struct-return folding, using the
inflated consensus type for the hidden-buffer slot. That prevents stale register
values from leaking back into source arguments after the buffer is removed.

Typed shared calls are materialized at the call instruction. This preserves the
old unresolved-call ordering guarantee: adding type evidence must not move an
identity-ambiguous call across a constructor, store, or other visible effect.

## 3. Representative generated changes

Boolean results no longer take an `object` detour:

```csharp
if (sub_181af7520/*shared body, 2 candidates*/(this.animName, "walk"))
{
    // ...
}
```

Floating-point consensus selects XMM0 and keeps the actual value:

```csharp
float real1 = sub_182bac5e0/*shared body, 2 candidates*/(targetMaterial, num2);
targetMaterial.SetFloat(TextShaderUtilities.ID_GradientScale, real1);
```

A shared `void` body remains visible instead of disappearing with an unused
unknown result:

```csharp
sub_182695690/*shared body, 2 candidates*/(&obj2, 0);
obj2.isTapRelease = false;
```

An observed hidden buffer becomes a struct assignment, with stale native
register arguments trimmed:

```csharp
obj15 = sub_1825bd360/*shared body, 2 candidates*/(0);
obj15 = sub_1825bd360/*shared body, 2 candidates*/(1);
```

The guarded negative case remains honest:

```csharp
object obj3 = sub_182539ee0/*shared body, 2 candidates*/(default, default, default);
```

That call has a consensus struct type, but no observed address return buffer at
that call site, so Review 83 does not force the fold.

## 4. Exact transform proof

The normal full sweep was split into two disjoint assembly partitions to finish
within the available run window. The merged inventory exactly matches Review
82 and has no overlapping MethodDefs. Its direct comparison reports 6,351
changed hashes and 0 structural changes.

Starting a second partition with fresh decompiler state also exposes 2,029
pre-existing order/state-sensitive render hashes. To avoid claiming those as
Review 83 work, the release re-lifted the entire 6,351-method comparison set from
Review 82 and Review 83 sources in the **same fixed order and isolated
processes**:

- 4,322 bodies are genuinely source-changed;
- 2,029 bodies are identical under fixed-order parity and are classified as
  partition-state-only deltas;
- all 4,322 genuine changes entered the shared-return consensus lookup;
- all 4,322 observed a proven non-null consensus result;
- 0 unchanged fixed-order bodies exercised the new lookup.

This proof is in `validation_reports/review83/changed_method_scope.json`; the two
compressed per-method manifests and their source fingerprints are retained
beside it.

## 5. Snapshot and full-output evidence

The same 64 MethodDef rows are frozen in `tests/goldens_review83.json`. Sixty are
byte-for-byte unchanged from Review 82. Four change:

1. one shared Boolean result becomes a direct condition;
2. two Touchscreen bodies regain required shared `void` calls;
3. one HDR render callback regains its shared `void` material call.

`validation_reports/review83/snapshot_changes.diff` contains the complete four-
method diff. The full generated-tree diff is retained as
`output_changes.diff.gz`.

The rendered semantic audit independently scans every output call form:

| Form | Count | Metadata consensus | Mismatches |
|---|---:|---|---:|
| Bare shared call statement | 3,543 | `void` | 0 |
| Shared call used directly as a condition | 2,550 | `bool` | 0 |

## 6. Validation

| Gate | Result |
|---|---:|
| Portable tests | 228 passed |
| Frozen native snapshots | 64 passed |
| Native semantic tests | 26 passed |
| Complete test suite | **318 passed** |
| Strict all-assembly build | 11,107 C# files; 115,658 bodies; 0 failures/fallbacks |
| Tree-sitter C# syntax | 11,107 files; 0 bad / 0 ERROR / 0 MISSING / 0 recovery |
| Direct structured sweep | 116,178 methods; 0 crashes |
| Structural sweep delta | 0 |
| Output inventory | 11,200 before / 11,200 after; no add/remove |

The strict build was also split into two assembly partitions. Their one
substring-overlap assembly (`Unity.InputSystem.dll`, selected by both
`Unity.InputSystem.dll` and `System.dll`) was byte-identical in all 345 emitted
files before merge. The unique aggregate is 91 assemblies, 11,107 type files, and
115,658 bodies.

A .NET SDK was unavailable, so the focused Review 80 compiled-pattern smoke was
not rerun and the complete generated tree was not compiled.

## Limits and next work

- 113,155 `object objN` declarations remain. Many need producer, stack-slot,
  copy/store, or alias provenance rather than a return-type rule.
- 4,633 Review 82 shared-object result sites had no address consensus; mixed
  candidates require call-site receiver/rgctx proof, not majority voting.
- Generic value-type instantiated size, source-level ref returns, and
  non-address hidden return buffers need explicit ABI models.
- Broader virtual and indirect target recovery remains separate from direct
  shared-address consensus.
- 8,067 into-block gotos remain across 2,047 methods, plus definite-assignment,
  project-reference, constructor/SEH, and other compilation blockers.
- General packed SIMD/vector tracking, cyclic allocation identity, ARM64
  semantics, and independent fixtures remain open.

## Reproduce

With dependencies installed and fixture variables set:

```text
PYTHONHASHSEED=0 python -m pytest -q
```

The complete offline gates use `tools/validate_corpus.py`:

```text
PYTHONHASHSEED=0 python tools/validate_corpus.py sweep \
  --metadata "$IL2CSHARP_METADATA" --binary "$IL2CSHARP_BINARY" \
  --report validation_reports/review83/recheck_sweep.json

python tools/validate_corpus.py parse final_out \
  --report validation_reports/review83/recheck_parse.json
```

Use `--strict` and a fresh output directory for emission. Do not execute the
supplied binary; all release validation is static.
