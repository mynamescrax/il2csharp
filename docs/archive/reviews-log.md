# il2csharp — state & history (split out of todo.md 2026-08-22)

## 0bg. Follow-up promotion — float shortening, cmov merge-type, exact-type stamp (2026-09-19)

Follow-up authority: `docs/todo.md` (Current work) and
`validation_reports/followups_sweep.json`, `followups_parse.json`,
`followups_promotion_verification.json`.
Promoted 2026-09-19: `final_out/` now holds `work/promote_out`
(11,274 files, candidate and promoted aggregate
`db4685236a910b5fbcd3a2a6bbd1b5a631989c7082d09764292dd055d0c36105`,
0 mismatches; supersedes the fix-123 tree).

Three unnumbered follow-ups over the fix-123 baseline: shortest round-trip
float32 literals with fixed-point tie-break (`0.07f`, `0.1f`, `10000.0f`);
entry stack-parameter names/types surviving the pass wipe with slot reloads
restoring the recorded kind (GetChars `baseDecoder`); exact runtime type on
klass-equality cmov select (GetChars `Decoder.bits/bitCount/firstByte`,
spreading to delegate types, `_source`/`_token`, shared-call resolution,
enum members; two sampled methods shed `unsafe`).

Validation: 795 tests pass (669 portable + 126 game); strict build
11,181 C# files / 114,458 bodies / 0 failures or fallbacks; parser 0 bad
files / 0 ERROR / 0 MISSING; direct sweep 116,178 methods / 0 crashes.
The 64 goldens regenerated with 6 reviewed body changes; `work/promote_out`
is byte-identical to `final_out/`.

## 0bf. Fix 97 — bare first-use temp declarations + 97e render repair (2026-09-14)

Fix 97 authority: `docs/todo.md` (Current work) and
`validation_reports/review97e_sweep.json`, `review97e_vs97.json`,
`review97e_parse.json`, `review97e_promotion_verification.json`.
Promoted 2026-09-14: `final_out/` now holds `work/review97_out`
(11,200 files, candidate and promoted aggregate
`93a4eb7b84ca9bf28bad1bb625ba9103082d3ac7ce0028a2bfb5f9d87a2f1386`,
0 mismatches; the fix-94 tree is kept at
`bckups/final_out_review94`, the Review 89 tree at
`bckups/final_out_review89`). Post-promotion parse recheck
`validation_reports/review97e_recheck_parse_final.json` (11,107 files,
0 bad).

Bare first-use temps (`objN = rhs;` with no prior declaration) now
declare from the same tracked-type lookup as `var` lines, with
scope-aware re-declaration in sibling blocks (97c) and `= default` only
for zero-valued numerics under a type they cannot spell (97b/97d);
companions cover typed `bool flagN` sugar, ternary arm declarations,
and typed hop temps. Full-corpus effect vs fix 94: 39,478 bodies
changed (declaration additions), 0 crashes, 0 structural changes.

Fix 97e repaired the parse gate the first build tripped: 26 ERROR nodes
in 23 files where `_strip_dangling_default` dropped a `: default` false
arm across a call's parens/commas in the true arm
(`? call() ;`). The strip is now paren-depth aware
(`??`/`?.`/nullable `?` never open an arm); the 97e sweep changes
exactly those 25 methods, 0 structural. The 64 goldens regenerate with
0 body changes (none covered); regressions:
`tests/test_review97_bare_decls.py` (21 portable, 6 for the render).

Validation: 483 tests pass (365 portable + 118 game); strict build
11,107 C# files / 115,658 bodies / 0 failures or fallbacks; parser 0 bad
files; direct sweep 116,178 methods / 0 crashes.

Open next: 511 remaining `return sub_*shared body` tails, the
`UnityAction<T0>` LHS (61 sites), dead `typeof(Object)` lines, and the
Review 87 byte-store/noreturn-EH/leftover lists (see `docs/todo.md`).

## 0be. Review 87 — zero-based MethodSpec instantiation indices (2026-09-11)

Review 87 authority: `REVIEW87.md` and
`validation_reports/review85/sweep4.json`, `sweep4_comparison.json`,
`parse4.json`. Promoted 2026-09-12: `final_out/` now holds
`work/review89_out/` (11,200 files, candidate and promoted aggregate
`0b906f7d1c8ab400a8718f745df1182bad9e9ffbb55a2bea18c30f51839323b5`,
0 mismatches; record
`validation_reports/review85/promotion_verification_review89.json`,
post-promotion parse recheck
`validation_reports/review85/recheck_parse_final.json`). The fix-91 tree is
kept at `bckups/final_out_review88`.

Review 85's last open item -- the wrong generic argument in
`Object.Instantiate<Font>` -- turned out not to be a Font problem. Both
MethodSpec index readers (`generic_method_name`,
`_method_spec_type_args`) assumed `classIndexIndex`/`methodIndexIndex`
are one-based with 0 absent. IL2CPP stores them zero-based with -1
absent, so every generic call site was named after the neighbouring
instantiation row: wrong, but always a real type name, which is why it
went unnoticed.

The base is proved from the data alone. Over all 175,736 specs the
zero-based read agrees with the declaring container's generic arity in
100% of cases (32,671 method rows, 144,977 class rows, zero exceptions);
the one-based read contradicts 2,749. Absence is spelled -1 (30,759 class
rows, 143,065 method rows) and never 0 -- two real specs carry
`classIndexIndex` 0. Probes: `work/review89_spec_arity_census.py`,
`work/review89_spec_index_base.py`, `work/review89_instantiate_scan.py`,
`work/review89_shared_generic.py`.

Full-corpus effect, all name-only: 16,119 bodies changed, 0 new crashes, 0
new structural changes versus Review 84 (the same 4 fix-91 entries).
`Instantiate<Font>` falls 66 -> 0 (`GameObject` 66);
`EpilepsyHandler` 49 -> `ComputeShader` 49. The 64 snapshots regenerate
with exactly 5 reviewed generic-name changes (mi 21027, 32832, 32837,
80616, 109664 -- each checked against its owning type or field types).

Validation: 435 tests pass (317 portable + 64 snapshots + 54 native);
strict build 11,107 C# files / 115,658 bodies / 0 failures or fallbacks;
parser 0 bad files; direct sweep 116,178 methods / 0 crashes.
Regressions: `tests/test_review89_spec_indices.py` (11 portable).
Numbering note: the "candidate fix 92" reserved earlier for the two named
raisers is renumbered to candidate fix 93; fix 92 is this shipment.

Open next: untyped `((byte*)objN + 0x0)[0]` stores; candidate fix 93; five
sub-threshold noreturn EH targets and per-method/proven-set agreement;
then the Review 84 list (15 constructor leftovers, 112,423 `object objN`,
13,254 empty allocations, ABI gaps, 8,067 into-block gotos,
vector/ARM64/fixture breadth).

## 0bd. Review 86 — deterministic, evidence-based EH helper naming (2026-09-11)

Review 86 authority: `REVIEW86.md` and
`validation_reports/review85/promotion_verification.json`. Fixes 90, 91,
91b, 91c; the gated tree (`work/review88_out`) was promoted over
`final_out/` with candidate and promoted aggregate sha256 both
`0ef7607e317dbb00f59ad72ccaa8089b36ccf0a79c42bae7f525ebeb30118d00`
over 11,200 files, 0 mismatches. The previous tree is kept at
`bckups/final_out_r84`. `work/review86_out` was never promoted.

Review 85 section 7 first diagnosed order-dependent helper discovery;
the follow-up census showed the defect was worse: 99 distinct rethrow
targets and 9 raise targets across 4,526 pad-bearing methods, 51 of the
rethrow targets ordinary registered methods (`SetException`,
`LogException`, `FreeHGlobal`, even `DateTime.AddYears`), each caller
printing `throw;` over a real call. Fix 90 clears helper VAs per method
and requires unregistered native targets. Fix 91 proves the pair once
from the whole binary (`0x180435740` rethrow 3,403 witnesses,
`0x180435670` raise 183); fix 91b rejects plumbing the lifter can already
name through jmp thunks; fix 91c rejects routines with a reachable `ret`.
Accepted set for this binary: exactly those two targets; thresholds
`_EH_HELPER_MIN_WITNESSES = 25`, `_EH_HELPER_MIN_DOMINANCE = 4`.

Validation at promotion: 424 tests; strict build 11,107 / 115,658 / 0
failures; parse 0/0/0/0; direct sweep 116,178 / 0 crashes with 4
attributed structural entries; 64 goldens regenerated with 0 changes.
Residue: 3,550 `throw` renderings, 0 raw proven-helper calls.
Regressions: `tests/test_review87_eh_helpers.py`,
`tests/test_review88_eh_helper_set.py`.

## 0bc. Review 85 — enum member identity, integer literals, signed immediates (2026-09-10)

Review 85 authority: `REVIEW85.md` and `validation_reports/review85/`.
Five source fixes (85-89) plus one validation-tool fix: enum member
tables decode zigzag through the underlying element type (eight member
names confirmed wrong before, e.g. `DateTimeKind.Utc` -> `Local`);
enum-valued call arguments fold to `Type.Member` (`FileMode.Open`);
`_int_lit` no longer strips hex `d`/`f` as float suffixes (`0x3d` was 3);
literal-base LEA composition folds (`(0 + 0x3)` -> `3`); immediates
reinterpret at every signed width (`4294967294` -> `-2`, 188 rewrites in
the first 4,000 methods). Deliberately untouched: untyped byte-store
lvalues (no declared width) and `_field_expr` dereference form.

Corpus effect: 10,758 bodies changed, 0 structural, net -526 lines; 1,913
of the changed bodies are partition-state EH render deltas, honestly
documented as not caused by the fixes. Validation: 399 tests (289
portable + 64 snapshots + 46 native); strict build 11,107 / 115,658 / 0;
parse 0/0/0/0; direct sweep 116,178 / 0 crashes. Goldens: 9 changed, every
line an enum-member fold. New defect diagnosed, not fixed: order-dependent
EH helper naming -- resolved by Review 86 above.

## 0bb. Review 84 — constructor chains and single-identity allocation (2026-09-10)

Review 84 authority: `REVIEW84.md` and
`validation_reports/review84/summary.json`. This is the complete current
replacement; the original game fixtures remain byte-identical and were read
statically, never executed.

The central fix joins the two native halves of managed object construction.
`il2cpp_object_new(typeof(T))` now mints an `Expr` with exact `_alloc`
provenance. That provenance survives copies and binding until one resolved
`.ctor` either completes the unbound expression as `new T(args)` or patches the
one exact earlier `new T()` declaration. Failure to find exactly one declaration
declines; there is no global textual deduplication or type-name guess.

Constructor recovery has a separate proof boundary from ordinary shared-call
resolution. Typed current-constructor `this` may select one closed
zero-parameter ancestor constructor; an exact fresh allocation may select its
own or an ancestor constructor. The candidate must be an instance `.ctor` with
`void` return and zero declared parameters. Generic candidates, multiple
eligible ancestors, unknown/byref/value-type receivers, mismatched ABIs, and
malformed metadata all decline. Resolved parameterized targets retain
metadata-trimmed arguments. Same-type targets become `: this(args)` and ancestor
targets become `: base(args)` through the emitter's internal pseudo form.

Unity 6000's terminal `IL2CPP_TYPE_OBJECT` parent edge is now mapped to the one
unique `System.Object` TypeDef. Inheritance cycles stop without duplicate rows,
and inheritance/field caches are per `Il2Cpp` instance rather than shared across
binary-local TypeDef indices. The old broad receiver heuristic intentionally
removes Object from derived chains, preserving unrelated shared-call behavior
while constructor proof uses the complete chain.

Full-output changes versus Review 83:

- standalone constructor allocations: 13,292 → 0;
- empty allocation declarations: 21,624 → 13,254 (-8,370 / -38.707%);
- `sub_180506120` markers: 2,958 → 160 (-2,798 / -94.591%);
- legacy `this.ctor(...)` text: 2,186 → 45 (-2,141 / -97.941%);
- `: base(...)` initializers: 5,960 → 9,530;
- `: this(...)` initializers: 0 → 325;
- `object objN` declarations: 113,155 → 112,423 (-732);
- C# lines: 2,913,021 → 2,892,453 (-20,568);
- changed C# files: 4,428, with the same 11,200-file inventory.

Validation: 358 tests pass (260 portable, 64 frozen native snapshots, 34 native
semantic assertions); strict build 11,107 C# files / 115,658 bodies / 0
failures or fallbacks; parser 0 bad files; direct sweep 116,178 methods / 0
crashes / 0 structural changes; constructor-only sweep 11,737 methods / 0
crashes. The same 64 snapshot MethodDefs are retained: 56 unchanged and eight
reviewed constructor/allocation changes.

Open next: exact evidence for 12 ambiguous shared-address constructors and three
complex legacy constructor calls; provenance for 112,423 remaining object
locals; the meaning of 13,254 remaining empty allocations; virtual/indirect
constructor targets; cyclic allocation dominance/alias identity; definite
assignment, project references, SEH, and 8,067 into-block gotos; broader ABI,
vector, ARM64, and independent-fixture work.

## 0ba. Review 83 — provable shared-body return types and preserved side effects (2026-09-10)

Review 83 authority: `REVIEW83.md` and
`validation_reports/review83/summary.json`. This is the complete current
`final_out/`; Review 82 and older sections below are baseline history.

The next large readability/correctness target after semantic local naming was
shared native code. One address can own many MethodDefs, so choosing one method
would be dishonest. The new `shared_return_type` path instead requires every
candidate to yield the same fully closed structural type and a supported Win64
return ABI. Root MethodSpec `VAR`/`MVAR` returns inflate from exact class/method
arguments. Unreadable or open candidates, disagreements, generic value types,
ref returns, and unsupported ABI classes decline atomically.

The call keeps its `sub_<va>/*shared body, N candidates*/` name. Consensus only
supplies the result facts common to every possible owner. Struct returns also
require an observed address buffer at the individual call site; ambiguous arity
trims before buffer folding, and typed shared calls bind immediately to preserve
native call order.

Full-corpus effect:

- ambiguous addresses: 13,721; exact supported consensus: 7,402;
- `object objN` declarations: 116,839 → 113,155 (-3,684 / -3.153%);
- shared-call object declarations: 11,031 → 5,368 (-5,663 / -51.337%);
- 3,543 explicit shared side-effect calls, all consensus `void`;
- 2,550 direct shared conditions, all consensus `bool`;
- 1,376 changed C# files, with the 11,200-file inventory unchanged.

The full direct-sweep comparison initially reported 6,351 changed hashes. Because
Review 83's sweep used two fresh assembly partitions, fixed-order isolated
Review 82/83 parity was run across that complete set: 4,322 are genuine source
changes and every one observed a proven consensus result; 2,029 are pre-existing
partition-state render deltas and are identical under parity. Structural metrics
never change.

Release gates: **318 tests (228 portable + 64 snapshots + 26 native); strict
build 11,107 C# files / 115,658 bodies / 0 failures or fallbacks; parse 0 bad /
0 ERROR / 0 MISSING / 0 recovery; direct sweep 116,178 methods / 0 crashes.**
The same 64 snapshots are frozen: 60 unchanged and four reviewed changes (one
Boolean condition, three restored `void` call sites).

The game and DLL were not executed; the complete C# was not compiled. Open work
starts with call-site proof for no-consensus shared bodies, producer/stack/alias
provenance for 113,155 remaining object declarations, instantiated generic-
valuetype sizes and ref returns, broader virtual/indirect targets, 8,067 inward
gotos, general packed lanes, cyclic allocation identity, and ARM64 semantics.

## 0az. Review 82 — semantic local names and conservative object typing (2026-09-09)

Review 82 authority: `REVIEW82.md` and
`validation_reports/review82/summary.json`. This was the complete Review 82
`final_out/`; Review 83 now supersedes it.

Review 82 addresses the user's primary readability complaint without laundering
unknown native values into confident-looking names:

1. `_semantic_local_names` runs only at the final render boundary. A declaration
   whose emitted type is already concrete gets a deterministic type-derived
   stem: `GameObject gameObject1`, `System.Type type1`, `string[] textArray1`,
   `SimulationMessage* simulationMessagePtr1`, `IEnumerator enumerator1`, etc.
   An untracked `object objN` remains `objN`.
2. Candidate names avoid every identifier in the body and every metadata
   parameter name, including unused parameters. Token rewriting skips string and
   character literals and line/block comments. The compact local vocabulary is
   preserved until all existing semantic/control-flow passes finish.
3. A separate conservative refinement changes single-definition `object` locals
   only when an array creation, string literal, or exact `typeof` right-hand side
   proves the static reference type and no ref/out/in/address escape exists.
   `new T()` is excluded because T may be a value type and boxing identity would
   change. Array rank counts only top-level commas.
4. The declaration scanner requires a true assignment and rejects control heads;
   `return obj1 == 36` can no longer masquerade as a second declaration and block
   `char character1`.

Full-tree result: concrete typed `objN` declarations **115,093 → 802
(-99.303%)**, all `objN` occurrences **1,425,443 → 1,101,280 (-324,163 /
-22.741%)**, syntax-provable object declarations **414 → 21**, and typed
foreach-object declarations **781 → 496**. The 21 type-refinement residues are
protected duplicated/reassigned/uncertain shapes, not a widened guess.

Release gates: **293 tests (210 portable + 64 snapshots + 19 native); strict
build 11,107 C# files / 91 projects / 115,658 bodies with 0 failures or
fallbacks; parser 11,107/11,107 clean; direct sweep 116,178 methods / 0 crashes /
0 structural changes versus Review 81.** The output keeps all 11,200 files and
2,907,732 C# lines; 5,398 C# files change only at the final readability/type
boundary. `unknown`, sqrt, helper, goto, and structural totals are unchanged.
All 64 snapshots exactly equal the new final-boundary transform applied to their
Review 81 bodies.

No .NET SDK was available. The full recovered C# tree and game were not compiled
or executed. The next object-focused work must recover real producer/type/alias
provenance for the remaining 116,839 `object objN` declarations, especially
unknown register seeds, copies/stores, stack slots, shared bodies, and indirect
calls; cosmetic renaming is explicitly not a substitute.

## 0ay. Review 81 — proved packed sqrt and scalar return ABI (2026-09-09)

Review 81 authority: `REVIEW81.md` and
`validation_reports/review81/summary.json`. This was the complete Review 81
`final_out/`; Review 82 now supersedes it.

Review 81 closes Review 80's first open priority without globally pretending
that packed SIMD is scalar:

1. An unregistered sqrt/domain wrapper is discovered only as one unique unknown
   call target with bounded executable extent, XMM0 double spill/reload, a
   `SQRTSD` path, RIP-relative `"sqrt"` literal, and `RET`. No fixture address or
   managed name is hardcoded.
2. `_sqrt_low_lane_sites` proves the exact `UCOMISD; JA helper; SQRTPD` diamond
   before recording any packed instruction address. The helper arm's scalar
   XMM0 ABI proves the high lane dead. Only those addresses model low-lane
   `CVTPS2PD`/`CVTDQ2PD`, `SQRTPD`, and normal-arm `CVTPD2PS`; unpaired packed
   opcodes remain conservative.
3. The helper consumes/returns XMM0 double and renders `Math.Sqrt`, eliminating
   stale GPR argument sprays and fabricated RAX results. Pure branch-arm roots
   remain inline through their merge so no arm-local temporary leaks scope.
4. `_return_value_register` selects XMM0 for by-value R4/R8 and RAX for all other
   scalar/reference returns. The structured path, flat fallback, call results,
   and indirect tails share it. Seven ref-float and one ref-double fixture
   methods prove why the byref-bit guard is required; all eight bodies remain
   byte-identical.

The distinct-native-body census finds 975 `CVTPS2PD`, 211 `SQRTPD`, and 634
`CVTPD2PS` sites. All 211 roots match the proved helper diamond; 155 relevant
conversions and 15 normal-arm packed narrowings are modeled. Of 248 helper
transfer sites, 211 are paired calls, 29 are direct scalar calls, and eight are
direct tail jumps. The 205-MethodDef output
audit has 0 exceptions, 0 raw helper calls, and 374 `Math.Sqrt` expressions.
`Fimp_JoystickInput.Update` remains an explicit limit: its scalar result feeds an
unmodeled `UNPCKLPS` vector pack, so no source root survives to the rendered
argument.

Release gates: **285 tests; strict build 11,107 C# files / 91 projects / 115,658 bodies, 0 failures or fallbacks; parser 11,107/11,107 files clean with 0 errors, missing, or recovery nodes; direct sweep
116,178 methods / 0 crashes / 0 structural changes versus Review 80.** The same 64 Review 80 snapshot MethodDefs remain
byte-identical. Representative reviewed outputs include Vector3.Normalize,
Vector2/Vector3 magnitude, EntryDoor.GetXZDistance, Sse.sqrt_ps,
TimeSeries.QuantileNormal, and Obi `<FindPath>b__1`.

No .NET SDK was available for a current compiler-smoke rerun. The whole recovered
game was not compiled or executed. Remaining priorities begin with broader
shared/virtual call ABIs, cyclic array identity, mixed packed struct/vector
tracking, lexical goto/SEH/definite-assignment/reference blockers, and ARM64.

## 0ax. Review 80 — loop-header semantics and lexical-tail repair (2026-09-09)

Review 80 authority: `REVIEW80.md` and
`validation_reports/review80/summary.json`. **This was the complete Review 80
`final_out/`; Review 81 now supersedes it. Review 79 and the stack-argument
follow-up below are older baseline history.**

The uploaded source reproduced 255/255 tests. Review 80 closes the loop-header
placement lead without weakening the indirect-control-flow or cyclic-allocation
guards:

1. `_emit_loop_replaying_header` runs a nonempty natural-loop header through the
   ordinary CFG sequencer inside `while (true)`. The first visit may enter its
   own stop set once; the back edge returns to that stop. Header statements,
   both in-loop successors, edge copies, exits, and SEH bookkeeping therefore
   execute in native order instead of being frozen/dropped before the loop.
2. `_memory_rhs_needs_loop_guard` now permits modeled direct loops but retains
   the honest fallback for unresolved/potential indirect dispatch. Array
   allocation remains separately cycle-guarded until dominance, identity, and
   alias lifetime are proved.
3. `_loop_shared_entry_gate` folds only a single-predecessor, statement-free,
   phi/SEH-free gate into a short-circuit loop exit. ReceiveLoop MI 28576 no
   longer jumps into its shared body's lexical scope.
4. `_replay_consumed_linear_to_stop` duplicates an already-rendered tail only
   after proving the complete acyclic single-successor path to the current exact
   stop, with no entry/pad/SEH crossing. Failure is atomic.
5. Source BOM/CRLF is restored and pinned by a test. The compiled C# smoke now
   executes an actual loop-emitter fragment whose runtime result fails if the
   header is frozen.

Native-reviewed outcomes: ReadSpan MI 11974 recomputes `_charLen - _charPos` and
retains its refill branch; DrawCurved MI 23566 retains all six direction arms;
Touchscreen.OnStateEvent MI 32833 retests state per iteration;
ViscosityVorticityJob.Execute MI 80548 moves pair work inside the loop and names
`this.pairs`. No target-specific name/address is hardcoded.

Release gates: **265 tests (188 portable + 64 snapshots + 13 native assertions);
11,107 C# files / 115,658 bodies; failures/fallbacks/type failures 0/0/0; parser
0/0/0/0; direct sweep 116,178 / 0 crashes.** 7,797 method hashes changed.
Into-block gotos fall 13,641/2,996 methods → **8,067/2,047**. Of the 1,615
methods with an audit delta, 1,532 improve and 83 increase; the increases remain
reported and are still open compilation blockers. Direct output lines rise
149,011 as omitted loop paths recover and proved tails duplicate legally.

The same 64 snapshot MethodDefs are retained in a new versioned file. 59 remain
byte-identical; MIs 11974, 32833, 32837, 39789, and 80548 changed after
native/CFG review and only after the complete gates. Review 77/79 snapshots remain untouched. The output
was rebuilt in a clean directory, compared before promotion, then promoted as a
complete tree. Core source formats and fixture hashes are verified.

Open next: packed low-lane SIMD and sqrt/helper ABI; broader shared/virtual ABIs;
cyclic array identity; mixed packed fields and unresolved values; the remaining
goto/SEH/definite-assignment/reference blockers; and ARM64 validation. The whole
recovered game has not been compiled or run.

## 0aw. Review 79 — ABI/alias fixes and compiled C# pattern checks (2026-09-08)

Current authority: `REVIEW79.md`, `REPLACEMENT.md`, and
`validation_reports/review79/summary.json`. **This is the current complete
`final_out/`, not the historical partial or b76 output described below.**

The uploaded Review 78 source reproduced 193/193 tests. New changes:

1. `_shared_sret_receiver_target` proves the common two-pointer, known-size ABI
   of every shared candidate. RCX is the output buffer, RDX the source pointer;
   exact source-pointee identity resolves RaycastHit.get_point in Shoot without
   treating the buffer as a receiver. Generic/unknown/mixed/duplicate cases stay
   unresolved. Shared fallback argument bounds now include hidden sret buffers.
2. `_array_allocation` gives each native array allocation its own typed identity
   at its instruction. The CFG topological test accepts acyclic backward shared
   tails but stands down on real cycles and unresolved indirect dispatch. Both
   Shoot logging arrays now allocate once and reach Concat through that reference.
3. String-element LEAs preserve `&array[index]`, making the existing local
   store/barrier twin check work. No cross-block textual-store dedup was added.
4. SQRTSS emits `(float)Math.Sqrt(...)`; SQRTSD stays double and unavailable
   inputs remain unknown. The packed sqrt/domain-helper lead remains open.
5. Generated `.csproj` files enable unsafe blocks. `tools/csharp_smoke.py`
   compiles/runs instruction-generated array/sret/scalar-root patterns and builds
   an actual generated unsafe project. These passed, but the whole game has not
   been compiled or executed.

Release gates: **252 tests (180 portable + 64 snapshots + 8 native assertions);
11,107 C# files / 115,658 lifted bodies; failures/fallbacks/type failures 0/0/0;
strict build exit 0; parser 0/0/0/0; direct sweep 116,178 / 0 crashes.**
2,485 method hashes changed, 0 structural-metric changes; remaining
into-block gotos 13,642/2,997 methods. See the complete per-method and per-file
reports rather than inferring semantics from totals.

The original 64-case snapshot file remains byte-identical. The current version
uses exactly those MethodDefs and, at the Review 79 cutoff, changed only MI
98685's native-proved single byte-array allocation; it was reviewed and
generated after build/parse/sweep. The frozen source was rebuilt into a fresh
directory, never overlaid onto a partial tree. Final ZIP contents were
re-extracted and verified. Core CRLF/BOM and supplied fixture hashes are
preserved; all shipped Markdown docs now point to this release, while
historical content remains intact.

2026-09-09 follow-up source changes (not a new full-tree release audit):
resolved direct-call/tail Win64 argument rendering now rebuilds ABI positions,
recovers contiguous stack arguments, tracks fixed-frame `rsp` alloc/free for
stack-slot identity, and names 5th+ incoming stack parameters at method entry.
The licensed snapshot fixture was refreshed against the same 64 MethodDefs, and
MI 98685 plus eight other native-backed methods changed accordingly.

Open next: loop-header placement/liveness; cyclic allocation identity; packed
CVTPS2PD/SQRTPD plus helper XMM/error ABI; broader shared/virtual stack-argument
recovery; mixed packed fields; unknown values; goto/SEH/definite assignment;
full-project references and ARM64 semantics. See the current section of
`todo.md`.


## 0av. Review 78 — private full replacement (2026-09-08)

`REVIEW78.md` and `validation_reports/review78/` are authoritative for this
release. The uploaded source actually matched Review 77's pre-review baseline
(56/136 supplied tests failed), despite the newer notes. Those missing fixes
were restored, then the native-grounded work below was added. The ZIP now
contains a complete strict-built `final_out/`: 11,107 type files /
115,658 bodies / 0 failed / 0 fallbacks / 0 type emit failures; syntax gate
0/0/0/0; full direct sweep 116,178 methods / 0 crashes. Tests:
193 passed (125 portable + 64 unchanged original snapshots + 4 new native
assertions). Historical b42/b76/partial-tree status below describes earlier
states, **not the current replacement**. No snapshot was regenerated.

Completed in this release:
- Restore the actual Review 77 tail/renderer/CLI/strict-reporting source changes.
- Decode 16-bit immediate stores; split fully proven adjacent Boolean writes
  without losing the second field (`AutoLetGoOfClick` sets both flags).
- Recover register/memory arithmetic in proven-acyclic bodies, fixing ReloadSMG's
  `30 - unknown`; keep cyclic/indirect-dispatch methods conservative after a
  native-proven unsafe loop-hoist was caught and rejected.
- Preserve array typing through address arithmetic; remove ReloadSMG's `int <- int[]`
  poisoning without fabricating values.
- Resolve the narrow all-static, one-GPR-argument shared value-type conversion
  family; Shoot's LayerMask conversion is now named from exact parameter type.
- Add portable inspection/checksum support and complete replacement output.

Open next (the old leads' diagnoses were not all correct):
1. Loop-header statement placement/liveness. In ReadSpan (MI 11974), native
   back edge `0x181c57577 -> 0x181c57470` must recompute `_charLen - _charPos`.
   The rejected wider memory-RHS change hoisted that value before `while`.
   Fix placement/proven liveness before widening the guard; do not accept a
   clean parse or refreshed snapshot as proof.
2. `sub_1804ce6d8` is a **sqrt/domain-error helper**, NOT an IsNaN predicate.
   Callers use unmodelled `cvtps2pd` / `sqrtpd` low-lane operations and an XMM
   argument/result. Prove that full ABI/normal/error path before naming it.
3. RaycastHit shared `get_point`: RCX is the hidden Vector3 return buffer;
   the receiver is RDX. Needs sret-aware receiver/slot type resolution. The
   narrow static conversion fix deliberately does not cover this family.
4. String-Concat array-store twins and allocation/alias correctness remain open.
5. Mixed-field packed initialization (not all-Boolean), broader loop-carried
   copies, unknown values, goto scope/SEH, remaining ABI gaps and ARM64 semantics.

The unchanged game DLL/metadata are included only in this private replacement
at the user's request. See `REPLACEMENT.md`; no native execution or C# build
was performed. Clean syntax is not a promise that the recovered game compiles.

todo.md now carries ONLY open work (next-session leads + open
backlog items). This file keeps the record: the archived
batch-closed stack and batch writeups (§0, §0b-§0q), current
numbers (§1), the retired gate-family attack list (§2), the
backlog trail with every completed item (§3), the working-loop
rules (§4), the batch-19 writeup (§5), baselines/promotion/known
artifacts (§6), gotchas (§7), and compressed history (§8).
Cross-references like "§0p" or "§4" resolve against THIS file.

Lineage: continue.md + HANDOFF.md + the pre-split todo.md were
merged into the old todo.md on 2026-08-19; this file is its
history half.

> 2026-09-08 consolidation (paths): the old parent folder was folded into
> this repo — sibling `../work/` merged into `work/`, the game folder
> moved to `testgame/` (gitignored), five loose scripts moved to `tools/`,
> backup zips kept in the parent folder. Everything below keeps its
> original paths (`../work/`, `il2csharp/final_out/`, sibling `bXX_out1`
> trees, `Shift At Midnight` at the old root); read those as `work/`,
> `final_out/`, reaped batch trees, and `testgame/`.

