# Review 87 - zero-based MethodSpec instantiation indices (fix 92)

**Completed:** 2026-09-11
**Scope:** generic call-target naming (`generic_method_name`) and generic
return-type inflation (`_method_spec_type_args`)
**Authority:** `validation_reports/review85/sweep4.json`,
`sweep4_comparison.json`, `parse4.json`; built tree `work/review89_out/`
(promoted 2026-09-12; `final_out/` now holds this tree)

Review 85's last open item was a wrong generic argument in
`Object.Instantiate<Font>`. It was not a Font problem. Every generic call
site in the corpus was being named after the *neighbouring* instantiation
row, because both MethodSpec index readers assumed a base the metadata
never used.

Before:

```csharp
object obj13 = Object.Instantiate<Font>(this.template.gameObject, vector31, obj14);
return sub_180b4b780(objectPool5, this, UnityEngine.Pool.ObjectPool<AllocToUpdate>.Release, obj1);
byte* bytePtr1 = System.Collections.Generic.EqualityComparer<T>.Default;
```

After:

```csharp
object obj13 = Object.Instantiate<GameObject>(this.template.gameObject, vector31, obj14);
return sub_180b4b780(objectPool5, this, UnityEngine.Pool.ObjectPool<ManagedJobData>.Release, obj1);
byte* bytePtr1 = System.Collections.Generic.EqualityComparer<int>.Default;
```

## Outcome

- `generic_method_name` and `_method_spec_type_args` read
  `classIndexIndex`/`methodIndexIndex` **zero-based**; `-1` is the only
  "no instantiation" sentinel. Row 0 is a real instantiation (two specs
  carry `classIndexIndex` 0), so 0 must not be treated as absent.
- The base is proved, not assumed: over all **175,736 specs** the
  zero-based read agrees with the declaring container's generic arity in
  **100% of cases** (32,671 method rows, 144,977 class rows, zero
  exceptions); the one-based read contradicts 2,749 of them
  (`work/review89_spec_arity_census.py`).
- Corpus effect: **16,119 method bodies changed, all name-only** (no
  line-count or inventory change), **0 new crashes, 0 new structural
  changes** versus Review 84. `Instantiate<Font>` falls 66 -> 0;
  `Instantiate<GameObject>` is now 66.
- Tests **424 -> 435** (317 portable + 64 snapshots + 54 native).
- Goldens: 5 of 64 snapshots change, each reviewed individually (section 4).
- Note on numbering: `todo.md` previously reserved "candidate fix 92"
  for rendering the two named raisers as `throw new ...`. That candidate
  is unshipped and is renumbered to **candidate fix 93**; fix 92 is the
  MethodSpec base shipped here.

## 1. What was wrong

`method_specs[i]` is `(methodDefinitionIndex, classIndexIndex,
methodIndexIndex)`. Both readers indexed `generic_insts_list` with
`[index - 1]` and treated 0 as "absent" -- i.e. they assumed the fields
are one-based. IL2CPP stores them zero-based with -1 absent:

- value range over 175,736 specs: `classIndexIndex` zero=2,
  none(-1)=30,759, max=11,389 against 12,229 inst rows; `methodIndexIndex`
  zero=0, none(-1)=143,065, max=12,228. A one-based table of 12,229 rows
  needs max <= 12,229 while zero-based needs max <= 12,228; the observed
  max satisfies both, so range alone does not decide it -- arity does.
- arity cross-check (`work/review89_spec_arity_census.py`): each spec's
  inst row must carry exactly as many type arguments as its generic
  container declares. Zero-based: 100% match on both axes. One-based:
  634 method + 2,115 class mismatches (plus 2 out-of-range).
- concrete target: `UnityEngine.Object.Instantiate` has 7 MethodDefs and
  35 referencing specs. Spec 175137 (`mi`=145) rendered `Instantiate<Font>`
  one-based and `Instantiate<GameObject>` zero-based; all 66 `Font` call
  sites in `final_out` pass game objects, prefabs, and UI holders -- never
  fonts (`work/review89_instantiate_scan.py`).

The defect was invisible for so long because the off-by-one still yields a
real type name: wrong, but always plausible-looking.

## 2. What fix 92 changed

Two read sites in `il2csharp.py`, nothing else:

- `generic_method_name`: `mrow = generic_insts_list[mi] if 0 <= mi < len`
  (same for `ci`); a `None` row (unreadable registration data) declines
  to no type arguments instead of raising.
- `_method_spec_type_args`: identical bounds check; `-1` and
  out-of-range decline to `None`, which keeps `shared_return_type`'s
  all-candidate proof honest.

`decompiler.py` never reads spec indices directly. The two remaining
`method_specs[...][0]` uses (lines 7519, 7653) take the method-definition
index, which was never base-shifted. `tests/test_shared_returns.py`'s
`generic_setup` was updated to the proved spelling (`[0, 1]` rows,
absent `-1`); `tests/test_review89_spec_indices.py` (11 tests) pins the
zero-based contract including the row-0, `-1`, out-of-range, and
unreadable-row cases.

## 3. Corpus residue, counted with identical needles

`work/review89_instantiate_scan.py` over each built tree:

| tree | generic `Instantiate<T>` sites | top argument | `Font` sites |
| --- | --- | --- | --- |
| `final_out` (one-based) | 157 | `Font` 66, `EpilepsyHandler` 49 | 66 |
| `work/review89_out` (fix 92) | 157 | `GameObject` 66, `ComputeShader` 49 | 0 |

Same 157 sites, shifted by exactly one row each: spec 175136
(`EpilepsyHandler` -> `ComputeShader`), spec 175137 (`Font` ->
`GameObject`). The neighbouring-row signature is the off-by-one itself.

## 4. The five golden changes, each reviewed

`work/review89_golden_diff.py` diffs all 64 frozen snapshots; exactly
these rows change:

| mi | method | old | new | why new is right |
| --- | --- | --- | --- | --- |
| 21027 | `ManagedJobData.Release` | `ObjectPool<AllocToUpdate>.Release` | `ObjectPool<ManagedJobData>.Release` | names its own pool type |
| 32832 | `Touchscreen.OnNextUpdate` | `Change<Obi.VInt4>`, `Change<Obi.BurstRigidbody>`, `Schedule<ApplyPositionDeltasJob>` | `Change<UnityEngine.Vector2>`, `Change<byte>`, `Schedule<AverageAnisotropyJob>` | touch delta is `Vector2`; Obi belongs to another package |
| 32837 | `Touchscreen...Reset` | `NativeArray<Obi.BurstRigidbody>`, `Change<PoseState>` | `NativeArray<byte>`, `Change<TouchPhase>` | phase state, not XR pose |
| 80616 | `BurstSkinConstraints..ctor` | `...<Obi.BurstShapeMatchingConstraintsBatch>.ctor` | `...<Obi.BurstSkinConstraintsBatch>.ctor` | names its own batch type |
| 109664 | `ParseError.Equals` | `EqualityComparer<T>`, `EqualityComparer<SpriteAtlas>` | `EqualityComparer<int>`, `EqualityComparer<string>` | matches the `position`/`message` field types |

No snapshot re-renders byte-identical under the old base once the
neighbour row is corrected; the remaining 59 are untouched.

## 5. Validation

All gates ran on the frozen sources `il2csharp.py` `e82000e0...` and
`decompiler.py` `bc675766...` against the unmodified fixtures:

| Gate | Result |
| --- | --- |
| Full suite with native fixtures | **435 passed, 0 failed** |
| Golden snapshots | 64 frozen; 5 changed (all reviewed above), 59 unchanged |
| Direct structured-lift sweep (`sweep4.json`, 570.2 s) | 116,178 methods, **0 crashes**, 2,191,996 lines, into-block gotos 8,071 across 2,048 methods, tail-arg changes 1,771 across 1,693 methods |
| Compare against `review84/final_sweep.json` | common 116,178, added 0, removed 0, changed 16,119, **structural 4, new crashes 0** |
| Strict build (`work/review89_out`, 593.2 s) | 11,107 type files, 115,658 bodies, **0 failed**, 0 structured fallbacks |
| Built-tree parse gate (`parse4.json`) | 11,107 files, 0 bad, 0 errors, 0 missing, 0 recovery nodes |

The 4 structural entries are byte-identical to the fix-91 gate (mi 37694,
38740, 38807, 48016; see `REVIEW86.md` section 8): fix 92 adds none. The
`sweep4` source hashes match the frozen sources, so the shipped-tree
candidate, the snapshots, and the gate reports describe one state.

A .NET SDK remains unavailable, so the generated tree was not compiled.

## Limits and next work

- `work/review89_out` was gated and **promoted 2026-09-12**; `final_out/`
  now holds this tree (11,200 files, aggregate
  `0b906f7d1c8ab400a8718f745df1182bad9e9ffbb55a2bea18c30f51839323b5`).
  Promotion record:
  `validation_reports/review85/promotion_verification_review89.json`; the
  fix-91 tree is kept at `bckups/final_out_review88`.
- Five noreturn but sub-threshold EH targets stay on per-method evidence
  only (see `REVIEW86.md` section 9); per-method/proven-set disagreement
  tightening is still deferred.
- **Candidate fix 93** (renumbered from 92): render
  `raise_IndexOutOfRangeException` / `raise_NullReferenceException` as
  `throw new IndexOutOfRangeException();` / `throw new
  NullReferenceException();`. Both currently render correctly as named calls.
- `((byte*)objN + 0x0)[0] = 4294967294;` still prints unsigned (Review 85
  open item 2); the store has no declared width.
- All Review 84 limits still stand: 15 constructor leftovers, 112,423
  `object objN` declarations, 13,254 empty allocations, and the open ABI,
  control-flow, and ARM64 work.

## Reproduce

```
PYTHONHASHSEED=0 python -m pytest -q
python work/review89_spec_arity_census.py
python work/review89_instantiate_scan.py work/review89_out
```

The complete offline gates use `tools/validate_corpus.py`:

```
PYTHONHASHSEED=0 python tools/validate_corpus.py sweep \
  --metadata "$IL2CSHARP_METADATA" --binary "$IL2CSHARP_BINARY" \
  --report validation_reports/review85/sweep4.json

python tools/validate_corpus.py compare \
  validation_reports/review84/final_sweep.json \
  validation_reports/review85/sweep4.json \
  --report validation_reports/review85/sweep4_comparison.json

python tools/validate_corpus.py parse work/review89_out \
  --report validation_reports/review85/parse4.json
```

Goldens regenerate only after those three gates (enforced by
`tools/make_goldens.py --replace`); the pre-regeneration backup is
`work/review89_goldens_before.json`. Do not execute the supplied binary;
all release validation is static.
