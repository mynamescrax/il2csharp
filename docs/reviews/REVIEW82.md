# Review 82 — semantic local names and conservative object typing

Date: 2026-09-09. This is a complete private replacement of the supplied
`il2csharp/` folder and supersedes Review 81. The original game DLL and metadata
remain byte-for-byte unchanged. They were read statically and never executed.
Keep these licensed fixtures private.

## Outcome

Review 82 makes generated C# substantially easier to read without hiding values
the decompiler still does not understand:

- concretely typed locals now use deterministic type-derived names such as
  `gameObject1`, `transform1`, `type1`, `text1`, `byteArray1`,
  `simulationMessagePtr1`, and `enumerator1`;
- genuinely untracked `object` locals keep the honest `objN` spelling;
- single-definition `object` declarations become `string`, `System.Type`, or a
  concrete array type only when the right-hand side proves that static reference
  type and the local has no later write or by-reference/address escape.

Across all 11,107 generated C# files:

- concrete declarations still named `objN` fell **115,093 → 802**
  (**-114,291 / -99.303%**);
- total `objN` identifier occurrences fell **1,425,443 → 1,101,280**
  (**-324,163 / -22.741%**);
- syntax-provable `object objN = ...` declarations fell **414 → 21**;
  393 became typed array/string/`System.Type` declarations;
- typed `foreach (... objN in ...)` declarations fell **781 → 496**;
- 113,921 ordinary declarations now carry semantic local names.

The 11,200-file inventory and 2,907,732 generated C# lines are unchanged.
Review 81's sqrt output is unchanged: 439 `Math.Sqrt` expressions and zero raw
`sub_1804ce6d8` references. The `unknown` token count is also unchanged; this
release does not disguise unresolved values as cleaner names.

## 1. Rename only after all semantic and structural passes

Existing post-processing deliberately recognizes the compact
`numN`/`flagN`/`realN`/`objN` vocabulary. Renaming those tokens earlier would
silently disable copy propagation, dead-local elimination, control-flow sugar,
and other regex-backed analyses. Review 82 runs `_semantic_local_names` only at
the final render boundary, after interface-dispatch naming and every structural
pass.

The name stem comes only from the declaration type already emitted by metadata
and type propagation. Namespace and generic arguments do not contaminate the
identifier: `List<GameObject>` becomes `list1`, `System.Type` becomes `type1`,
`RTHandle` becomes `rtHandle1`, and `TMP_CharacterInfo[]` becomes
`tmpCharacterInfoArray1`. Acronyms, arrays, pointers, interfaces, generic
parameters, and nested names are normalized deterministically.

No new type fact is invented for this naming step. An `object objN` declaration
stays `objN`, so unknown native values remain visually distinct from recovered
objects.

## 2. Preserve C# scope and source text

A semantic candidate is refused when the same native token has conflicting or
untracked declarations. Candidate names are checked against every existing body
identifier and against metadata parameter names, including unused parameters
that do not appear in the body. Names are unique method-wide, which is stricter
than relying on disjoint C# scopes.

Identifier replacement is token-aware and skips quoted strings, character
literals, line comments, and block comments. A string containing `"obj1"` stays
byte-for-byte the same even when local `obj1` becomes `gameObject1`.

A focused regression caught `return obj1 == 36;` being mistaken for a second
local declaration because the declaration scanner saw the first `=` in `==`.
The final gate now requires a real assignment token and excludes control heads;
the native `char` example renders `char character1 = value;` consistently.

## 3. Refine only self-typed reference expressions

A second final-boundary pass can replace `object objN` when the right-hand side
itself proves one of three reference types:

- `new T[n, ...]` → the matching array type, including rectangular/jagged rank;
- a string literal → `string`;
- exact `typeof(T)` → `System.Type`.

The local must have exactly one definition and no `ref`, `out`, `in`, or address
escape. A later assignment could require the wider `object` type; a by-reference
call is invariant in C# and must keep its declared slot type. `new T()` is not
included because `T` could be a value type and changing an object local could
change boxing identity. Commas inside array-size calls do not become array-rank
commas, and uncertain generic/comparison expressions remain untouched.

The 21 retained syntax-shaped declarations are documented in
`validation_reports/review82/naming_audit.json`; they are duplicated definitions,
later writes, or deliberately uncertain dimension expressions, not missed broad
rewrites.

## Representative output

- `FPSController obj1` → `FPSController fpsController1`;
- `GameObject obj41` → `GameObject gameObject1`;
- `System.Type obj8` → `System.Type type1`;
- `string[] obj19` → `string[] textArray1`;
- `byte[] obj9` → `byte[] byteArray1`;
- `SimulationMessage* obj6` → `SimulationMessage* simulationMessagePtr1`;
- `object obj133 = new string[8]` →
  `string[] textArray2 = new string[8]`;
- unknown indirect-call results remain `object objN`.

The complete generated diff is compressed in
`validation_reports/review82/output_changes.diff.gz`. The same 64 MethodDefs as
Review 80/81 are frozen in `tests/goldens_review82.json`; 21 change, and
`snapshot_transform_proof.json` proves all 64 current snapshots equal exactly the
new final-boundary transform applied to their Review 81 bodies.

## Validation

- **293 tests passed**: 210 portable, 64 snapshot, and 19 native-fixture tests.
- Fresh strict build: **11,107 C# type files, 91 project files, 115,658 lifted
  bodies, 0 failed bodies, 0 structured fallbacks, and 0 type-emission failures**.
- Complete syntax gate: **11,107/11,107 files clean; 0 bad files, parser errors,
  missing nodes, or recovery nodes**.
- Direct structured sweep: **116,178 methods, 0 crashes, 0 unclosed/underflowed
  braces, 0 dangling gotos, and 0 empty argument lists**.
- Versus Review 81: **37,140 method bodies changed, 0 structural changes, and
  0 new crashes**. Sweep line count and the known 8,067 into-block gotos across
  2,047 methods are unchanged.
- Generated output: **5,398 C# files changed, 0 files added/removed, and 0 C#
  line-count change**. `unknown`, `Math.Sqrt`, and raw-helper metrics are stable.
- Source format remains exact: `il2csharp.py` has UTF-8 BOM + CRLF;
  `decompiler.py` has CRLF without a BOM.

Evidence lives in `validation_reports/review82/`: source/output/snapshot diffs,
object-name census and guard residue, test/build/parse/sweep logs, full method
manifests, hashes, clean-promotion verification, and extracted-release checks.

## Limits

This is a readability and narrowly proved reference-type release, not a claim
that all `objN` values are resolved. The remaining 116,839 `object objN`
declarations are intentionally untracked, ambiguous, native-pointer, shared-body,
indirect-call, merge, or other unresolved values. Renaming them speculatively
would make incorrect code look authoritative.

The complete generated C# tree was not compiled or executed. No .NET SDK was
available in this environment, and clean parsing is not semantic equivalence.
The supplied game was not run. Shared/virtual/indirect ABIs, cyclic allocation
identity, wider vector/struct tracking, legal goto restructuring, definite
assignment, references, and ARM64 validation remain open.

## Reproduce

See `REPLACEMENT.md` for Windows installation instructions.

```bash
python -m pip install -r requirements-dev.txt
PYTHONHASHSEED=0 python -m pytest -m "not game"
PYTHONHASHSEED=0 python il2csharp.py testgame --strict -o rebuilt_out
python tools/validate_corpus.py parse rebuilt_out --report work/rebuilt_parse.json
META=testgame/ShiftAtMidnight_Data/il2cpp_data/Metadata/global-metadata.dat
PYTHONHASHSEED=0 python tools/validate_corpus.py sweep \
  --metadata "$META" --binary testgame/GameAssembly.dll \
  --report work/rebuilt_sweep.json
python tools/verify_release.py
```

Set `IL2CSHARP_METADATA`, `IL2CSHARP_BINARY`, and `PYTHONHASHSEED=0` before
running all 293 tests.
