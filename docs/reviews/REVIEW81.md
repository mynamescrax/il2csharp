# Review 81 — proved packed sqrt and exact scalar return ABI

Date: 2026-09-09. This is a complete private replacement of the supplied
`il2csharp/` folder. The original game DLL and metadata are retained byte-for-byte.
They were read statically, **never executed**. Keep these licensed fixtures private.

## Outcome and limits

- **285 tests passed**: the unchanged 64 MethodDef snapshots plus portable and
  native-backed ABI/pattern assertions.
- Full strict rebuild: **11,107 C# type files and 91 project files, with 115,658 lifted bodies, 0 failed bodies, 0 structured fallbacks, and 0 type-emission failures**.
- Complete syntax gate: **all 11,107 C# files passed with 0 bad files, 0 parser errors, 0 missing nodes, and 0 recovery nodes**.
- Full direct sweep: **116,178 native methods, 0 crashes, and 0 structural changes against Review 80**.
- The 205 native methods containing this runtime's packed/helper sqrt family now
  lift with **0 crashes and 0 raw `sub_1804ce6d8` calls or tail jumps**. The
  audit renders 374 `Math.Sqrt` expressions.

The supplied Review 80 source reproduced all 265 existing tests before editing;
its frozen full sweep and output tree are the comparison baseline. This closes
that release's first priority without pretending that every SIMD or ABI shape is
solved. One helper-calling joystick method still does not expose a
source `Math.Sqrt`: the scalar result is consumed by an unmodelled `UNPCKLPS`
vector pack, so the helper call disappears but the packed struct argument remains
incomplete. General packed-lane semantics, wider vector tracking, shared/virtual
ABIs, cyclic allocation identity, remaining lexical gotos, definite assignment,
references, and ARM64 validation remain open. The whole recovered game was not
compiled or run; a clean syntax gate is not semantic equivalence.

## 1. Recognize the native sqrt helper structurally

The unregistered helper previously printed as an unknown `sub_...` call with
stale GPR arguments and a fabricated RAX result. It is now accepted only when one
unique unknown call target has the complete local signature seen in the native
function: executable bounded extent, XMM0 double spill/reload, a scalar `SQRTSD`
path, a RIP-relative `"sqrt"` error-name literal, and a return. A MethodDef or
exported target is rejected. No address, game type, or method name is hardcoded.
If the signature is absent or ambiguous on another binary, the honest unknown
fallback remains.

The recognized call consumes a double from XMM0 and produces a double in XMM0,
so both the hardware and domain/error arms render as `Math.Sqrt(value)` instead
of spraying unrelated RCX/RDX/R8/R9 state into a fake managed call. A direct
near jump to the same helper is treated as the method's XMM0 tail return.

## 2. Scalarize only proved packed low lanes

Across distinct native method bodies, the fixture contains 975 `CVTPS2PD`,
211 `SQRTPD`, and 634 `CVTPD2PS` instruction sites. Review 81 does **not**
generalize those opcodes as scalar.
`Decompiler._sqrt_low_lane_sites` authorizes only exact native diamonds whose
`JA` alternate arm calls the structurally recognized scalar helper and whose
normal arm contains one matching `SQRTPD`. It traces the low-lane producer and
normal-arm narrowing only inside that proved window.

The helper consumes and returns only XMM0's low double. Therefore a high lane
could not be a defined value shared by both arms; this is the proof that the
paired packed instruction's high lane is dead. The lifter then models only those
recorded instruction addresses:

- `CVTPS2PD`/`CVTDQ2PD` low lane → explicit `double` conversion;
- paired `SQRTPD` low lane → `Math.Sqrt`;
- paired normal-arm `CVTPD2PS` low lane → explicit `float` narrowing.

Unpaired packed instructions remain untouched. Pure sqrt expressions stay inline
across the two conditional arms, avoiding a temporary declared inside one arm
and referenced after the join.

Native census: all 211 distinct packed-root instruction sites match the helper
pattern, with 155 proved conversion sites and 15 proved normal-arm packed
narrowings. There are 248 distinct-address helper transfers: 211 packed-diamond
calls, 29 direct scalar calls, and eight direct tail jumps.

## 3. Select return registers from the managed signature

Structured `RET` handling previously preferred RAX whenever both symbolic RAX
and XMM0 were live. That is wrong for Win64 scalar `float`/`double` returns and
caused valid XMM0 expressions to be replaced by unrelated integer/object state.
Review 81 centralizes the rule and uses it for structured returns, flat fallback
returns, direct call results, and indirect tail-call returns:

- by-value `float` and `double` → XMM0;
- integer, pointer, object, generic, and by-reference returns → RAX;
- large value types remain on the existing hidden sret-buffer path.

The by-reference guard matters: the fixture has 2,518 native by-value
float/double methods but also seven `ref float` and one `ref double` methods.
Those eight retain RAX even though their metadata element enum is R4/R8.
Portable tests pin both value and by-reference placement at calls and returns.

## Representative improvements

- `Vector3.Normalize` now computes an explicit double root, narrows it once, and
  divides all components by that recovered scalar; the helper branch and stale
  object spray disappear.
- `EntryDoor.GetXZDistance` returns `(float)Math.Sqrt(...)` on both native arms
  instead of returning a stale object/pointer on the normal arm.
- `Sse.sqrt_ps` independently recovers all four source lanes as four
  `Math.Sqrt` stores, with no unknown/helper call.
- `TimeSeries.QuantileNormal` now returns the XMM0 expression
  `real4 * real2 + this._mean` rather than the unrelated live RAX local.
- `System.Math.Sqrt` and seven Unity.Mathematics double helpers recover their
  negative/domain tail arms as `return Math.Sqrt(...)`.
- Obi's `<FindPath>b__1` now returns the rooted distance times `voxelSize`.

The before/after bodies are preserved in
`validation_reports/review81/focused_changes.diff`. The existing 64 snapshot
MethodDefs remain byte-identical; none sampled this family, so their frozen
Review 80 file remains unchanged.

## Validation

- The supplied Review 80 source first reproduced all **265** existing tests.
  The final suite passes **285**: 202 portable tests, the unchanged 64-case
  snapshot, and 19 fixture-backed native assertions. Portable-only execution
  passes 202 and skips 83 licensed-fixture cases.
- A fresh strict build emitted **11,107 C# type files**, **91 project files**,
  and **115,658 lifted bodies** with 0 failed bodies, 0 structured fallbacks,
  and 0 type-emission failures.
- The syntax gate checked every one of those 11,107 C# files: 0 bad files,
  0 parser errors, 0 missing nodes, and 0 recovery nodes.
- The direct structured-lift sweep covered **116,178 methods** with 0 crashes,
  unclosed/underflowed braces, dangling gotos, or empty argument lists. Against
  Review 80, 2,047 bodies changed, there were 0 structural changes and 0 new
  crashes, and generated sweep output fell by 3,530 lines. The known lexical
  baseline remains 8,067 into-block gotos across 2,047 methods.
- Scope classification found 1,883 changed by-value float/double returns out of
  2,518, all 205 sqrt-family methods changed, and 43 methods overlap both sets.
  None of the eight by-reference float/double return bodies changed. Only two
  changed callers fall outside those direct sets; both preserve the recovered
  by-reference target.
- The rebuilt tree keeps the same 11,200-file inventory. It changes 578 C# files,
  reduces generated C# by 3,542 lines and unresolved tokens by 59, raises
  `Math.Sqrt` occurrences from 88 to 439, and removes all 271 rendered raw-helper
  references.
- The first candidate audit exposed eight direct helper tail jumps that the call
  path alone did not cover. Tail handling was added, that candidate was
  discarded, and the tests, clean strict rebuild, parser, complete direct sweep,
  output comparison, and audits were rerun from the final source.

Evidence lives in `validation_reports/review81/`: source and focused diffs,
packed/helper censuses, the 205-method sqrt output audit, complete test/build/
parse/sweep logs, per-method manifests, output comparison, hashes, and release
verification. Historical Review 77–80 evidence remains preserved and labeled.

## Reproduce

See `REPLACEMENT.md` for Windows installation and overwrite instructions.

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

Set `IL2CSHARP_METADATA` and `IL2CSHARP_BINARY` to the supplied fixture paths,
and `PYTHONHASHSEED=0`, before running all 285 tests. No .NET SDK was available
in this validation environment, so Review 80's already-passed focused compiler
smoke was retained but not re-run. No game executable was launched.
