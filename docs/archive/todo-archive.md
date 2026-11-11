
## Previous replacement — Review 83 (2026-09-10)

`REVIEW83.md`, `new.md` §0ba, and `validation_reports/review83/` describe the
previous source and complete output; Review 84 supersedes it. Release: **318
tests; strict build 11,107 C# files / 115,658 bodies with 0 failures or
fallbacks; parser 0 bad files; direct sweep 116,178 methods / 0 crashes / 0
structural-metric changes**.

Completed in this release:

- [x] Prove a return type for an ambiguous shared native address only when every
  metadata candidate is readable, fully closed, structurally identical, and
  supported by the current Win64 return ABI. Keep the honest shared-body callee
  name; never choose a method by majority or printed-name similarity.
- [x] Inflate root `VAR`/`MVAR` returns through exact MethodSpec arguments while
  declining nested open generics, disagreements, unreadable candidates, ref
  returns, generic value types, and unsupported ABI classes.
- [x] Require an observed address buffer for each shared struct return and
  preserve call ordering and metadata-trimmed argument positions.
- [x] Reduce `object objN` declarations 116,839 → 113,155 and shared-call object
  declarations 11,031 → 5,368; restore 3,543 shared `void` side effects and
  2,550 direct Boolean conditions.
- [x] Separate 4,322 genuine source-changed bodies from 2,029 fresh-partition
  state deltas with fixed-order Review 82/83 parity.
- [x] Freeze the same 64 MethodDefs in `goldens_review83.json`: 60 unchanged and
  four reviewed semantic changes.

## Previous replacement — Review 82 (2026-09-09)

`REVIEW82.md`, `new.md` §0az, and `validation_reports/review82/` describe the
previous source and complete output; Review 83 supersedes it. Release: **293 tests; strict build 11,107 C#
files / 115,658 bodies with 0 failures or fallbacks; parser 0 bad files; direct
sweep 116,178 methods / 0 crashes / 0 structural changes versus Review 81**.
The original DLL/metadata remain unchanged and were read statically, never
executed.

Completed in this release:

- [x] Rename concrete object-family locals only at the final render boundary,
  after every structural and semantic pass. Names derive from already emitted
  types (`gameObject1`, `type1`, `textArray1`, `simulationMessagePtr1`); unknown
  `object` values remain the honest `objN` marker.
- [x] Avoid collisions with all body identifiers and metadata parameter names,
  including unused parameters, and replace identifiers without touching string
  or character literals and line/block comments.
- [x] Refine single-definition `object` locals only when a string literal, exact
  `typeof`, or array creation proves the static reference type and there is no
  later write or ref/out/in/address escape. Preserve 21 guarded residues.
- [x] Reduce concrete typed `objN` declarations 115,093 → 802 (-99.303%), total
  `objN` occurrences by 324,163 (-22.741%), and syntax-provable object
  declarations 414 → 21, with no generated line-count change.
- [x] Freeze the same 64 MethodDefs in `goldens_review82.json`; all 64 equal the
  exact new final-boundary transform of their Review 81 bodies.
- [x] Rebuild, parse, sweep, compare, promote, checksum, and package the complete
  output. Unknown/sqrt counts, 8,067 into-block gotos, and structural metrics are
  unchanged.

### Priorities at Review 82 (historical; use the current list above)

1. **Resolve real unknown object values, not just their names.** The remaining
   116,839 `object objN` declarations are dominated by unknown register seeds,
   local-copy/store provenance, stack-slot reads, shared bodies, and indirect
   calls. Trace the producing instruction and prove type/identity before
   changing a declaration; never cosmetically rename an unresolved value.
2. **Remaining shared/virtual/indirect call ABIs and receivers.** Recover generic
   or unknown sret sizes, mixed signatures, non-address return buffers, function
   pointer/vtable targets, wider stack arguments, and complete ref-return source
   rendering. Exact receiver/slot/signature evidence is required.
3. **Cyclic array allocation and alias recovery.** Header execution is correct,
   but cycles and unresolved dispatch still need placement, dominance,
   per-iteration identity, and alias-lifetime proof before allocation
   materialization can widen.
4. **Mixed packed initialization and vector/struct tracking.** Review 81 proves
   only helper-paired low lanes; general lane state, packed components,
   loop-carried types, and mixed-field stores remain open.
5. **Finish legal structured control flow and compilation readiness.** 8,067
   into-block gotos remain across 2,047 methods, along with definite assignment,
   project references, constructor/SEH, identifier/type, and ref-return issues.
6. **ARM64 semantics and independent fixtures.** Existing scaffolding is not
   validated semantic recovery.

## Previous replacement — Review 81 (2026-09-09)

`REVIEW81.md`, `new.md` §0ay, and `validation_reports/review81/` describe the
previous source and complete output; Review 82 supersedes it. Release: **285 tests; strict build 11,107 C# files / 115,658 bodies with 0 failures or fallbacks; parser 0 bad files; direct sweep 116,178 methods / 0 crashes / 0 structural changes**. The
original DLL/metadata remain unchanged and were read statically, never executed.

Completed in this release:

- [x] Discover the unregistered sqrt/domain wrapper only from its bounded native
  structure and XMM0 double ABI; no helper address/name is hardcoded.
- [x] Scalarize `CVTPS2PD`/`CVTDQ2PD`, `SQRTPD`, and `CVTPD2PS` only at exact
  instruction addresses proved by the matching helper diamond. Unpaired packed
  SIMD remains conservative.
- [x] Recover all 248 distinct helper transfers (211 paired calls, 29 direct
  calls, eight direct tail jumps) as `Math.Sqrt`; the 205-MethodDef audit has
  0 exceptions and 0 raw helper renderings.
- [x] Select XMM0 for by-value `float`/`double` returns and RAX for integer,
  object, pointer, generic, and by-reference returns across structured/flat
  RETs, resolved calls, and indirect tails. All eight ref-float/ref-double
  method bodies remain byte-identical.
- [x] Rebuild, parse, directly sweep, compare, promote, checksum, and package the
  complete output. The 64 Review 80 snapshots remain unchanged.

### Priorities at Review 81 (historical; use the current list above)

1. **Remaining shared-call ABIs.** Generic/unknown sret sizes, mixed signatures,
   non-address return buffers, indirect/virtual calls, wider stack-argument
   cases, and complete ref-return source rendering remain. Keep exact ABI/type
   proof; do not broaden matching by name.
2. **Cyclic array allocation and alias recovery.** Header execution is correct,
   but cycles and unresolved indirect dispatch still need placement, dominance,
   per-iteration identity, and alias-lifetime proof before allocation
   materialization can be widened.
3. **Mixed packed initialization and vector/struct tracking.** Review 81 proves
   only low lanes paired with one scalar helper. `Fimp_JoystickInput.Update` still
   loses a root through `UNPCKLPS`; general lane state, packed components,
   loop-carried types, and mixed-field stores remain open.
4. **Finish legal structured control flow.** **8,067 into-block gotos across
   2,047 methods remain.** Generalize sharing only with exact CFG, edge-phi,
   loop, switch, and SEH proof; avoid uncontrolled duplication.
5. **Full C# compilation readiness.** Resolve definite assignment,
   references/project dependencies, constructor/SEH issues, identifier/type
   artifacts, ref-return signatures, and other compiler diagnostics. Syntax-clean
   parsing is not a complete-project build.
6. **ARM64 semantics and independent fixtures.** Existing scaffolding is not
   validated semantic recovery. Do not infer equivalence from the x64 fixture.

## Previous replacement — Review 80 (2026-09-09)

`REVIEW80.md`, `new.md` §0ax, and `validation_reports/review80/` describe that
previous source and complete output. Baseline: 255 supplied tests passed. Release:
**265 tests; 11,107 C# files / 115,658 bodies / 0 failed / 0 fallbacks /
0 type-emission failures; syntax gate 0/0/0/0; direct sweep 116,178 / 0 crashes.**
Targeted generated C# compiled and ran; the entire recovered game is not
compile-ready and was not executed.

Completed in this release:
- [x] Replay nonempty natural-loop headers inside each iteration instead of
  freezing their statements before `while` or dropping a second in-loop arm.
- [x] Allow memory-RHS recovery in modeled direct loops while retaining the
  conservative fallback for unresolved/potential indirect dispatch.
- [x] Collapse the exact phi/SEH-free shared-entry gate into a short-circuit loop
  exit; ReceiveLoop no longer needs an inward goto.
- [x] Duplicate consumed straight-line tails only after proving the complete
  acyclic single-successor path to the current join; failure emits nothing.
- [x] Native-review ReadSpan, DrawCurved, ReceiveLoop, Touchscreen.OnStateEvent,
  and ViscosityVorticityJob.Execute; pin the corrected loop behavior with unit,
  fixture, snapshot, and compiled-runtime checks.
- [x] Restore and test the core source BOM/CRLF contract.
- [x] Rebuild, parse, directly sweep, compare, promote, checksum, and package the
  complete output. Into-block gotos fall 13,641 → 8,067 and affected methods
  2,996 → 2,047; the 83 method-level increases remain explicitly reported.

### Priorities at Review 80 (historical; use the current list above)

1. **Packed low-lane math and native sqrt ABI.** `sub_1804ce6d8` is a
   sqrt/domain helper, not IsNaN. Prove CVTPS2PD/SQRTPD lane semantics, XMM
   arguments/results, high-lane observability, and normal/error paths. The
   existing scalar SQRTSS cast is not this fix.
2. **Remaining shared-call ABIs.** Generic/unknown sret sizes, mixed signatures,
   non-address return buffers, indirect/virtual calls, and broader stack-argument
   cases remain. Keep exact ABI/type proof; do not broaden matching by name.
3. **Cyclic array allocation and alias recovery.** Header execution is now
   correct, but cycles and unresolved indirect dispatch still need placement,
   dominance, per-iteration identity, and alias-lifetime proof before allocation
   materialization can be widened.
4. **Mixed-field packed initialization and scalar/struct tracking.** Review 78's
   all-Boolean byte proof is not general struct/float initialization. Packed
   components, loop-carried types, and unresolved values remain visible.
5. **Finish legal structured control flow.** **8,067 into-block gotos across
   2,047 methods remain.** Generalize shared-entry/consumed-region handling only
   with exact CFG, edge-phi, loop, switch, and SEH proof; avoid uncontrolled code
   duplication. The 83 methods whose metric increased in Review 80 are listed in
   `validation_reports/review80/structural_delta_summary.json`.
6. **Full C# compilation readiness.** Resolve definite assignment,
   references/project dependencies, constructor/SEH issues, identifier/type
   artifacts, and other compiler diagnostics. Syntax-clean parsing and the
   focused compiled smoke are not a complete-project build.
7. **ARM64 semantics and independent fixtures.** Existing scaffolding is not
   validated semantic recovery. Do not infer equivalence from the x64 fixture.

The unchanged DLL/metadata were included in that private replacement.
Historical b42/b76/partial-tree and Review 77–80 notes below do not describe the
current `final_out/`.

Split 2026-08-22: the batch writeups, current numbers, promotion
record, known artifacts, completed backlog items, the working-loop
rules, and gotchas moved to `new.md` (its §0b-§0v, §1-§8; every
cross-reference like "§0p" below resolves against new.md). Durable
architecture lives in CLAUDE.md, native-construct mapping in
README.md. READ new.md §4 (working loop) and §7 (gotchas) before
any nontrivial change.

> 2026-09-08 consolidation: the old parent folder was folded into this
> repo — sibling `../work/` merged into `work/`, the game folder moved to
> `testgame/` (gitignored), five loose scripts moved to `tools/`, backup
> zips kept in the parent folder. History below still refers to
> `../work/`, sibling `bXX_out1` trees, and `Shift At Midnight` at the old
> root; read those as `work/`, reaped batch trees, and `testgame/`.

Historical baseline: `final_out/` = **b42_out1, PROMOTED 2026-08-22**
(byte-verified copy; the batch trees one level up, b37_out1 through
b42_out1, were reaped at promotion per the §6 rule — no A/B tree is
kept below `final_out/`). Batch 42 (§0v) shipped the LCA hoist
extension (51), the tail-goto guard (51a, a live b41 hole), the late
second run (51b), and the funnel (51c-g, v4 spine model) applied to
classic hoists too — fixing two disasm-proven b41 wrong-hoist
families. THE HONEST COST: lines +75,477 and into_block
17,718/4,079 -> 32,094/9,434 — the ~14.4k un-done hoists are mostly
the guard-chain pyramid whose default arm RETURNS past the merge;
neither form compiles (definite assignment), the kept goto is
greppable. Gate at promotion: bad-file set the documented TMP pair
(2/4,864/4), brace 0, census at fixpoint (26 residual sound sites,
census_b42_v4.py).

**HISTORICAL PROMOTED CANDIDATE: `b76_out1` (batch trees reaped; source state frozen
at the gated build, tree backups in the parent-folder zips) is the current verified
gated candidate, batches 43 through 76 (new.md §0w through §0at; lead 9
/ batch 57 / §0ak remains open and reverted, source unaffected).
Gate 0/0/0, build 115,658 bodies / 0 failed, sweep 0 crashes /
into_block 13,518/2,979. Closed-generic-CLASS statics resolve (9 tokens
cleared, 0 new); goldens 50/50 unmoved.**

Review 77 (2026-09-08, REVIEW.md) advanced the SOURCE past the b76
candidate: resolved-direct-tail args (`Lifter._tail_method_args`, Win64
positional XMM selection, 1,186 sites / 1,145 methods), unknown-pointer
renderer ordering (quote/select-aware scan before `_unsafify`), CLI
discovery/filter repair (`--metadata`/`--binary`, `--types` honored,
`--strict`), fallback/emission failure instrumentation, and the portable
kit (`tools/validate_corpus.py`, `tests/` 136 = 72 unit + 64
MethodDef-keyed snapshots, CRLF `.gitattributes`). Validation table:
11,107 files / 115,658 bodies / 0 failed, gate 0/0/0, sweep 116,178 /
0 crashes, into_block 13,642 (2,997 methods) under the NEW validator vs
13,518/2,979 under `sweep_1a_audit.py` -- different tool, not a
regression; 637 files differ from the uploaded baseline, 10,470
byte-identical, strict-mode full emission exits 0. Promotion over
`final_out/` is still a human call.

2026-09-08 evening: full rebuild into `final_out/` ABORTED mid-run (the
Assembly-CSharp results were already in hand). The tree on disk is
PARTIAL -- 6 assemblies (Assembly-CSharp 391 files, mscorlib, System,
System.Xml, Unity.InputSystem, UnityEngine.UIElementsModule), Review-77
source. NOT a candidate: do not gate, promote, or regenerate goldens
off it. InventoryManager.cs (12,435 lines / 803 KB; was 6,359 at b38 --
growth is phi materialization + tail duplication, not game code) read
end to end; findings + sized leads in new.md §0au. New leads from that
read (detail in §0au, ordered by size): (1) argument-type shared-body
disambiguation -- `RaycastHit.get_point` (9 cands) + `LayerMask.
op_Implicit` (11 cands) provable from argument Expr types, clears the
Shoot distance `unknown` + layer-mask naming; (2) unregistered NaN
predicate `sub_1804ce6d8` (7 `0f > unknown` guard sites); (3)
string-Concat array store twins (18 here, fix-72c gap); (4) `int <-
int[]` mistype poisoning ReloadSMG ammo math (`30 - unknown`); (5)
constant-`true` bool stores rendering as `unknown` (5 sites, smallest
probe). Still open as before: Update()'s ~50-line `.locals init`
zero header + 264 gotos / 628 `objN` (loop-carried copies need real
loop liveness, lead 4a).

Batch 75 (§0as, CLOSED) took the batch-16 cached-delegate backer (below):
fix 75 moves the join-edge phi copies before the fork (48,520 sites /
2,198 methods in Assembly-CSharp alone; sweep +13/+1, +71,345 lines;
goldens 42/50, all phi renumbering), fix 75b folds the triple to
`T objA = CACHE ?? (CACHE = new T(a1, a2));` with the cctor artifact,
the shared-ctor call and the phi copies gone (SetActiveCamera
verified live; no-phi variant, guards and no-fold shapes pinned in
`work/b75fold_test.py`, 20/20 green -- see §0as).

Batch 74 (§0ar) closed todo lead 11's genericinst half (11(a)) -- but
not the way the lead sketched it. The lead's premise ("accept
valuetype-underlying genericinst rows; fty[0] may already be the
generic td") was wrong twice over, both caught by probing before any
edit (work/probe_b74_genericinst.py): a types row with enum 0x15
carries a runtime Il2CppGenericClass POINTER in t[0] (the td decodes
through it -- Il2Cpp.td_of_ty already had that walk), and the open
generic td it resolves to has NO runtime layout at all -- its
field_offsets row is all zeros and type_sizes[td] is None (160/161
open value types probed) -- so merely opening the 0x11/0x12 guard
resolves nothing (probe A: every residue disp still None; the open
def's instance chain collapses to one bogus 0x0 entry under the
dedup). The instantiation's layout had to be RECONSTRUCTED. Fix 74
restructures static_off_path/_sf_chain_path into _sf_field_path/
_sf_chain_walk plus the inflated-layout helpers: a static field whose
type is a valuetype-underlying GENERICINST gets its layout from the
open td's field list walked in declaration order with the gc class
arguments substituted for VAR fields, IL2CPP sequential rules,
natural alignment capped 8 (_sf_infl_chain, cached per (td, args);
alignment participates ONLY in layout building -- the span check
stays alignment-free on type_sizes exactly as fix 72/73 had it).
Ground truth: TMP_Text..cctor copies the constructed
TMP_TextProcessingStack<MaterialReference> into blob+0x10 as
5x16B + 8B = 0x58 bytes (probe_b74_disasm.py) and the declaration-
order reconstruction gives itemStack@0x10, index@0x18,
m_DefaultItem@0x20 (MaterialReference's exact closed layout, 0x38),
m_Capacity@0x58, m_RolloverSize@0x5c, m_Count@0x60 -- exact. The
TextMeshPro corpus sites give a SECOND independent confirmation:
`__static_1708` resolves to m_EllipsisInsertionCandidateStack.m_Count
with the reconstructed TMP_TextProcessingStack<TMP_WordInfo> size
0x3d8 proven by the next static's own offset (k_ParseTextMarker@0x1710
= 0x1338+0x3d8). static_off_path's second element is the Il2CppType
TUPLE now (a substituted field has no field-table index; the one
lifter consumer updated, b72/b73 contract pins updated with it).
**Yield: genericinst-vt tokens 25 -> 0, plus 13 deeper sites the
census's covering-static-only classification had filed under
vt/class** (Touch/InputActionState/EnhancedTouchSupport/Awaitable
generics sitting INSIDE plain-vt statics) -- honest tree-wide tokens
62 -> 24 (-61%), files 21 -> 13 (fixed-regex census; the old
census_b73_static.py regex ALSO matched `__static_fields` itself as
`__static_f` -- both sides of every historical __static_N number
carry that artifact; tool fixed, old-regex pair 273 -> 222 / 66 ->
61 files). TMP_Text's SaveWordWrappingState renders the five blob
reads under one typed base with real component reads
(`int num1 = obj13.m_Count;`); LayoutDefaults' fixed buffers name
their elements (`EdgeValuesUnit.__2` -- __0..__8 are the metadata's
own generated field names). **The first build FAILED 3 bodies** (0
failed is the standing bar since batch 53) -- TextMeshPro.
GenerateTextMesh, TextMeshProUGUI.GenerateTextMesh and one
InputActionState method, all one porting slip: _sf_infl_chain
returned (chain, size) while _sf_ty_size_align's nested-genericinst
branch read lay[2] -- the probe carried alignment as a third element,
the production port dropped the element without dropping the read;
no unit pin covered a NESTED genericinst-vt (the 25 validated sites
are all depth-1). Fixed, rebuild clean (11,107 files / 115,658
bodies / 0 failed, 790.9s), and the lesson stands: port a validated
sim element-for-element or re-diff it. Gate 0/0/0, brace 0/11,107,
sweep crashes 0/116,178 and into_block 13,505/2,978 byte-identical
to b73 (naming-only change; sweep lines 1,990,095 -> 1,990,093);
goldens 50/50 unmoved; 10 of 11,107 files differ, every diff read
line by line and confirmed a win. b74_test 38/38 pins the
reconstruction, the residue disps, the honest misses and both
renders. The residue is re-split below (lead 11).

Batch 73 (§0aq) closed todo lead 11's 11(a) half -- the UIElements
`*Property` family -- by answering the lead's own question ("the offset
table's meaning needs its own understanding"): there IS no new meaning.
BindingId is 0x98 bytes (a nested PropertyPath value type at chain 0x10
+ the string m_Path at 0xa0), the 0x98 strides are correct layout, and
the failing disps land INSIDE the nested PropertyPath. Fix 73
generalizes fix 72's static_off_path inner walk into a recursive
`_sf_chain_path` (largest chain entry < key whose own value type SPANS
the key descends; type_sizes span check; depth-capped, cycle-guarded --
seeded EMPTY: self-typed statics like Vector3.zeroVector are legitimate
first hops). **`__static_N` tokens 1,906 -> 273 (-85.7%), files 121 ->
66; UIElementsModule 1,419 -> 31.** Downstream: typed reads unblocked
dead-spill folds (math.cs, ScriptableRenderer.cs) and a real
`Finger[]`-typed array render replaced raw pointer indexing in
EnhancedTouchSupport.TearDownState (its `unsafe` wrapper dropped).
Gate 0/0/0, brace 0/11,107, sweep crashes 0 and into_block
13,505/2,978 byte-identical to b72; 64 files differ, tree lines -5;
b73_test 32/32; goldens regenerated 50/50 (7 diffs read, none new).
The residue is a different class (genericinst value types, named-field
deref-then-index, honest pointer-as-value/address-of forms) -- lead 11
rewritten below.

Batch 72 (§0ap) closed todo lead 11's 11(a) half (the inner-component
reads) plus the decompiler-side defects the probe exposed on the way:
fix 72 adds `Il2Cpp.static_off_path` (a blob read at
[field_base + inner] resolves through the owning static field's own
value type -- unboxed blob storage; zeroVector.z, upVector.y,
identityMatrix elements, the inner field's own type riding on the
Expr); fix 72b shares it in `_fold_static_addrs`, stops the field@0
compounding (a `.` after the blob = the lifter's miss suffix), and
fixes the intermediate-hop guard that never fired on rendered text;
fix 72c kills the byte-cast blob store twin (1,403 sites -- the
delegate-cache second render; the star-deref spelling at dedupe time,
`<>`-prefixed closure members, two-phase, a second call after
_member_fold); fix 72d makes typeof(...).member chains pure-load
candidates (dead `objN = typeof(X).__static_fields;` spills, 1,003
sites); fix 72e is `_switch_synth` (lead 2's switch half, +40 real
switches across 29 files, census-guarded). **`__static_N` tokens
5,564 -> 1,906 (-66%), files 969 -> 139; zeroVector-prefix compounding
1,412 -> 0; twins 1,403 -> 194; dead spills 1,003 -> 39.** Gate 0/0/0,
brace 0/11,107, sweep crashes 0 and into_block 13,505/2,978 (the -1
A/B-located per method, work/ab_b72_into_block.py); tree lines -19,450;
2,472 files differ. b72_test 65/65; goldens 43/50 with SEVEN new
mismatches, all fix-72d dead static-read drops read line by line
(regenerate goldens at/before the next promotion). The residue is a NEW
mechanism (the UIElements Property family -- see lead 11).

Batch 71 (§0ao) closed the batch-16 "named static-address residues"
item's `__static_fields` half -- which was NOT actually 0 at b38 as
the old note claimed: the live tree held 5,342 `__static_fields`
lines and 11,369 `__static_N` fallback tokens, including LIVE WRONG
NAMES (DateTime.cs rendered the const `TicksPerMillisecond` as a
pointer base for the real `s_daysToMonth365` array load). Fix 71a
filters `static_off_names` to real static storage (literals have no
slot and shadowed offset 0x0 first-wins); fix 71c stamps the owner
TypeDef onto typeof/klass Exprs at usage-slot decode time (`_td`,
the fix-66 `_mi` pattern) because the BSS runtime-cache cells
(typeof(string), typeof(__c)) arrive with ty=None -- ty_of_td has no
CLASS row for System.String at all. **`__static_N` 11,369 -> 8,586
(-2,783), files 1,158 -> 969; DateTime wrong names 4 -> 0; composed
`(byte*)` array reads became real `X.s_daysToMonth365[i]` indexers.**
Gate 0/0/0, brace 0/11,107, sweep A/B crashes 0 and into_block
13,506/2,978 byte-identical both sides (§0an's 13,650/3,000 does not
reproduce under sweep_1a_audit.py -- bookkeeping correction in
§0ao). 987/11,107 files differ, tree lines -514. staticfield_test
20/20. The residue (inner-component reads off static value-type
fields, stamp-loss on phi/spill bases, getClass()-rooted chains) is
new lead 11 below. `b71_out1`.

Batch 60 (§0an) closed todo lead 3's delegate `invoke_impl` bucket.
The inherited runtime thunk now carries its delegate receiver into `_call`,
resolves that TypeDef's declared `Invoke`, substitutes concrete generic
class arguments (required for `Func<T>` return typing and the hidden-sret
ABI), and then uses the ordinary resolved-call path for arity, byref,
return, and receiver rendering. **Delegate residues 626 -> 3 (-99.5%)**;
the three survivors do not carry a concrete delegate type (two are runtime
casts left as `System.Delegate`, one is an untyped ref/out local) and remain
honest. Full sweep 0/116,178 crashes and 0 structural defects except the
existing into-block class (13,650/3,000); build 115,658/0, gate 0/0/0,
brace 0/11,107, lightweight tests 36/36, goldens 30/50 with the same 20
documented mismatches. 229 files differ, every one containing at least one
of the 623 converted sites; tree lines -598. `b70_out1`.

Batch 59 (§0am) closed todo lead 5c (the resolved-call arity trim didn't
count the hidden sret buffer slot). Sized first the way the lead itself
demanded (a temporary lifter probe, `work/patch_probe_b69_sretarity.py`
+ `work/census_b69_sretarity.py`): 659 of 116,178 methods reach the trim
with a sret return the struct-return fold didn't already peel off, 376
of which actually drop the true last argument. Fix 69 mirrors
`_hint_arg_types`/`_positional_args`'s own unconditional `+= 1` for this
exact slot. A direct diff against `b68b_out1` then caught fix 69's OWN
regression (fix 69b): `rest = args[1:]` -- feeding the property/indexer
accessor folds -- hardcoded "args[0] is the receiver", wrong when sret
also shifts the receiver to args[1]; `Transform.get_position()` briefly
printed with a bogus argument before the fix. Read all 34 changed files
in full: every hunk recovers one real, previously-dropped trailing
argument (dozens of SIMD intrinsics in `X86.cs`, `math.mul`,
`Quaternion.Inverse`, `ContactFilter2D.CreateLegacyFilter`, ...), no
corruption anywhere. Gate held at 0/0/0, brace 0/11,107, crash sweep
0/116,178, into_block byte-identical to b68b_out1 (13,506/2,978 -- no
CFG-shape change), goldens 30/50 unchanged. `b69b_out1`.

Batch 58 (§0al) closed todo lead 8 (the `& 0xFF/*z*/` movzx-mask residue
`_BZEXT_RX`'s character-class regex structurally could not reach).
Replaced it with `Decompiler._bzext_strip`, a literal-aware
balanced-paren walk (fix 68), then a mandatory-delimiter check a plain
unit test caught missing before any build ran -- `while`/`switch`/a
bare `if`/a single-argument call's own required parens are NOT the
mask's droppable wrapper (fix 68b). A direct per-file diff against
`b66_out1` then caught fix 68's OWN regression: `_is_sugar`'s
`_HIER_RX` (the il2cpp inline IsInst hierarchy-check fold) assumed the
mask's wrapper parens would always survive and lost its anchor once
they didn't, live in 589 of 11,107 files (fix 68c, `\(?...\)?`).
**Masks 14,365 -> 0 (-100%)**, gate held at 0/0/0, brace 0/11,107,
crash sweep 0/116,178, into_block byte-identical to b66_out1 (13,506/
2,978 -- no CFG-shape change, every fix lives in `_bool_sugar`/
`_is_sugar`), goldens 30/50 unchanged (the sample contains no mask
shape). 2,079/11,107 files differ from b66_out1: 2,078 mask-bearing
ones plus one legitimate bonus fold (`XmlSchemaType.cs`, same native
idiom, never masked, blocked for an unrelated pre-existing reason).
`b68b_out1`.

Batch 56 (§0aj) took todo lead #3 -- but re-censused it first, because
its residue list was a batch-38 vintage, and the LARGEST bucket was not
in the lead at all. `work/census_b65_indirect.py` buckets every
`/*indirect*/` line by the shape of its callee: of 13,808 at b65_out1,
**6,259 (45%) have an ALREADY-RESOLVED `Type.Method` callee** -- 4,955
of them Unity `*_Injected` icall bindings -- printed as if they were
unknown function pointers, in front of an untrimmed argument list
(`object obj17 = Event.set_Internal_keyCode_Injected() /*indirect*/
(this.m_Ptr, value, obj7, obj8, obj10, obj12, obj14, obj16);`).
`Il2Cpp.scan_icall_cache` had mapped all 2,285 cache cells to their
signature strings since it was written and `_icall_annotation` already
resolved 99.3% of them to a real MethodDef -- **it returned the
rendered text and dropped the index**, so `_read_mem` handed `_call` a
plain `obj`, `mi` stayed None, and nothing downstream could fire.
**Fix 66** carries the index through `_icall_annotation` ->
`decode_slot` -> `_read_mem` (new `Expr._mi`, `fptr` kind) into
`_call`, seated the way the VIRT_CALL block seats a resolved vtable
slot -- which puts the site on the ordinary resolved-call path: arity
trim, `_hint_arg_types`, `_positional_args`, fix 54's byref/`ref`
render, the sret and property folds. No guess is added: the cell's
contents are proven by the signature string that fills it, and an
unresolved signature keeps the honest marker. **Fix 66b**:
`declaringTypeIndex` is a TYPE index, so nested signatures
(`ParticleSystem/MainModule::get_duration`) matched nothing; cells
resolving 2,268 -> **2,285 of 2,285**. **Fixes 66c/66d were forced by
66 and reach wider than icalls**: `jmp reg` carries `('stop',)` from
CFG build and `'stop'` emits NOTHING, so an indirect TAIL call whose
result is the method's return value was dropped outright as soon as
`_call` knew the return type and bound the result instead of emitting
a statement; 66c makes it `return <call>;` (also closing the same
silent drop for resolved vtable/interface tail calls), and 66d fixes
reading that value from RAX when Win64 returns R4/R8 in XMM0, plus a
dry-pass `b.ret`/terminator leak the same shape exposed. **Gate held
at 0/0/0**, brace 0/11,107, sweep crashes 0, into_block
13,505/2,978 -> 13,506/2,978. 946 of 11,107 files differ (66c reshapes
arms far beyond the icall sites). **`/*indirect*/` 13,808 -> 7,538
(-45.4%)**, the largest move that marker has ever had; **read-before-def
118,917 -> 111,050 (-6.6%)**; tree lines -1,372. Goldens 19 -> 20, the
new one this batch's own and read against the disassembly. New unit
mirror `work/icall_test.py` 10/10.

Batch 55 (§0ai) CLOSED lead #10 by reading its 20 residual sites as
disassembly (`work/probe_b65_tables.py`, `work/probe_b65_decode.py`)
instead of as bucket names -- and the lead's own residue text was wrong
about half of them. **`no_lea 8` was not a real bucket**: all eight
sites have a reachable table-base `lea` (11 to 123 instructions back)
that fix 64 finds; `census_b63_tables.py`'s `classify()` mirror kept a
6-instruction lookback that fix 64 had made stale. **No image-base
fallback was written -- nothing needs one**; the mirror is corrected
instead. The real residue was three things. **Fix 65a**: the
`cmp idx,N; ja` bound scan took the FIRST hit in its window, so an
unrelated earlier guard capped the table (CookieParser.Get 0x1824E70E0,
`cmp eax,1; jne` ten insns before the real `cmp eax,0Ch; ja`: 13 entries
capped at 2, then killed by the `< 3` floor); it now scans backward and
follows the index through register copies. **Fix 65b**: the sparse
form's byte GROUP TABLE is the switch's case map, not just a bound.
Expanding the jump table through it gives one entry per OPERAND value,
which both recovers the twelve `short` dispatches (the exact length is
max(group)+1, unreachable by the address walk because MSVC lays the
group table right after the jump table) and fixes a wrong-output bug
live on EVERY sparse dispatch already structuring: `_emit_switch`
numbers cases by list position, and that position was a jump-table SLOT
-- HID.DetermineLayout 0x18268AB70 printed Hatswitch (operand 9, per
Unity's own InputSystem source) as `case 1`. The `< 3` floor did not
have to be relaxed at all. **Fix 65c**: `_prune_nonreturning` FILTERED
a switch's target list when dropping a throw-stub edge, renumbering
every case after it; blanked in place now. **Gate held at `0/0/0`**,
brace 0/11,107, sweep crashes 0, into_block 13,815/2,960 ->
13,505/2,978. 89 of 11,107 files differ. **Switch statements 721 -> 758,
case labels 9,052 -> 10,295, raw table loads 52 -> 25**; tree lines +381
and read-before-def -21 (flat). Recognizer buckets **`ok` 111 /
`short` 1** (that one is JsonParser.Equals, a virtual tail-dispatch, not
a table). Goldens 19, the same 19 by name; new mirror
`work/jumptable_test.py` 9/9.

Batch 54 (§0ah) took lead #10's SECOND cause, found by building the
tool the lead should have had: `work/census_b63_tables.py` buckets every
`jmp reg` by `_jump_table`'s own rejection reason in ~17s, and read
**`no_lea` 77 / `ok` 22 / `short` 12** at b63_out1. `no_lea` = the index
load is found and the table-base register identified, but no
rip-relative `lea` for it exists in the 5-instruction lookback --
because **MSVC emits ONE `lea rB,[rip+image_base]` per function and
reuses rB for every jump table in it**, so a second dispatch reached
from inside the first table's case bodies has no lea anywhere near it
(CurrentDayManager.PlayNextOccurence 0x1806A6000: one `lea rdx` at
0x1806A6924 serving tables 45 instructions apart). Fix 64 walks back to
the nearest earlier `lea tabreg,[rip+X]`. It is sound without dominance
analysis because it stops at the NEAREST match -- so it cannot regress a
table that works today, the longer range being reached only where the
old code returned nothing -- and because a wrong base fails `va2off` or
yields <3 targets inside the method's own extent. An intervening-write
guard was considered and REJECTED: it would reject the ground-truth
case, whose whole point is that the clobbers sit on unreachable paths.
Buckets after: **`ok` 92 / `short` 12 / `no_lea` 8**. **Gate held at
`0/0/0`**, brace 0/11,107, sweep crashes 0, into_block 12,950/2,928 ->
13,815/2,960. 66 of 11,107 files differ -- parsers, tokenizers and state
machines. **Switch statements 559 -> 721, case labels 6,528 -> 9,052,
`/*indirect*/` 13,941 -> 13,845**; tree lines +16,358 and
read-before-def +7 (flat, so the recovered code is well typed). Goldens
19, the same 19 by name.

Batch 53 (§0ag) took todo lead #10 (jump-table dispatch is not
recovered) and found the recogniser was never the problem -- the DECODE
WINDOW was. `_decode`'s flat `end = min(nxt or (va+0x10000),
va+0x10000)` cut every method at 64KB; `InventoryManager.Update` is
**0x110A0 bytes**, so its 60-entry image-relative table at 0x1806FAC50
had entry[0] (0x1806FA9AE) past the cut, `_jump_table`'s `lo <= tgt <
hi` broke on the first entry, and the dispatch degraded to an indirect
call on the raw table load -- **all 60 case bodies silently gone**, 156
rendered lines for a 70KB method. Fix 63a decodes the 0x10000 window
first (byte-identical for 88,924 of 88,976 distinct entry points) and
re-decodes ONCE up to `next_method_start` (capped 0x40000) **only when
the reachability trace actually followed a target into [window_end,
bound)**; the trace moved into `_trace_reachable` so it can report that,
and `_jump_table` is called with the true bound so an out-of-window entry
is SEEN rather than truncating the table silently. Fix 63b raises the CFG
block cap 1500 -> 3000, without which 63a makes that method WORSE (it
would newly fall to the linear flat lift). **Exactly three methods
corpus-wide sit between the two caps** -- and two of them are
`TextMeshPro`/`TextMeshProUGUI.GenerateTextMesh`, i.e. the sweep's only
two crashes and the parse gate's only two bad files for ~35 batches.
Their badness was never a decompiler defect: the cap threw them at the
linear lifter, whose output bypasses `_final_text`. **Gate 2/2,206/4 ->
`0 bad / 0 ERROR / 0 MISSING` -- the first fully clean parse this corpus
has ever had** (trajectory 708/2,261/487 pre-b17 -> 16/15/2 -> 2/7,919/2
-> 2/2,206/4 -> 0/0/0). Sweep **crashes 2 -> 0**, brace 0/11,107,
into_block 12,502/2,926 -> 12,950/2,928 (the +448 all inside the three
methods). **Exactly 3 of 11,107 files differ from b62_out1,
byte-identical otherwise.** read-before-def 118,609 -> 118,931, and the
same +322 measures over just those three files, so nothing else moved --
honest cost of 12,333 newly-recovered body lines. Goldens 19, the same 19
by name. **Retires new.md §6's "exclude the TMP pair from any census"
workaround.**

Batch 52 (§0af) came off READING InventoryManager.cs end to end at
b59_out1 rather than off this list, and found three families no lead
tracked and no metric counted. **(A) The `unknown` conditions** -- batch
28's honest placeholder for the six flag-specific jumps CMP_OPS never
mapped -- were 8,290 conditions + 1,048 ternaries. A census that
instruments the miss (`work/census_b52_unknown.py`) found **no
unrecoverable bucket at all**: JS/JNS after TEST 44%, JP after an SSE
compare 46%, JS/JNS after SUB/ADD 8%. Fix 60 makes `Lifter.flags` a
property that stamps WHICH instruction wrote it, and derives `x < 0` /
`x >= 0` / the unordered-NaN check from that; `cmp a,b` is deliberately
NOT derived (SF is sign(a-b), not `a < b`, under overflow). Fix 60b is
the soundness half: any instruction iced says writes or undefines SF/PF
clears the recorded SETTER -- never the pair -- so an unmodelled flag
writer degrades to `unknown` instead of naming an older `test`, and no
existing mapped-operator branch changes at all. 60b also models memory
read-modify-write, which wrote no flags before and is the exact site
that started the family: `this.currentInventoryIndex -= 1; if
(!(unknown))` is now `if (this.currentInventoryIndex < 0)`, and
Update() went from 1 `unknown` to 0. **Conditions 8,290 -> 4,022
(-51.5%)**, ternaries -44.9%. **(B) The `& 0xFF/*z*/` movzx artifact**
(18,035 lines) was a precedence BUG: `_mk` left `_prec` None so
`_bin_txt` STRIPPED the mask's own parens, and `x & 0xFF + i*8` groups
in C# as `x & (0xFF + i*8)` -- different expression, still parses,
invisible to the gate, and it also hid the sites from `_bool_sugar`'s
existing identity strip. 1,702 sat inside address expressions. Fix 61a
gives the Expr its real precedence; 61c makes the mask match the SOURCE
width (`movzx eax,cx` is 16-bit and rendered an 8-bit mask,
disasm-proven at 0x1806c65a0). Masks 18,035 -> 14,229. **(C) A
switch-subject paren bug the GATE caught**: `b61_out1` read 3 bad files
against 2 while total ERROR FELL -- §4's per-file rule exactly.
`_SUBK_RX`'s two optional parens are independent, so
`(num1 & 0xFF) - 97` captured `num1 & 0xFF)` and emitted
`switch (num1 & 0xFF))`. Pre-existing, exposed by 61a. Fix 62 gives
`strip_outer` the peeling job and leaves the regex the subtraction.
Final gate **2/2,206/4** (bad-file SET the documented TMP pair, ERROR
-5), brace 0/11,107, bare `objN;` 0, sweep crashes 2/2 pre-existing,
into_block 12,497/2,924 -> 12,502/2,926, tree lines +3,632.
read-before-def 118,445 -> 118,609 (+164) and that is honest, not a
regression: a condition that printed the single token `unknown` now
prints its operands, so an undefined operand gets counted for the first
time. New unit mirror `work/flagcond_test.py` (26 cases, ten of them
pinning what must STAY `unknown`). Two first cuts were reverted before
shipping and §0af says why -- a NEG special-case that would have
changed ordinary je/jne output, and an early type-based mask drop that
would have re-created batch 50's per-text collapse hazard.

The candidate before it, `b59_out1`, was batch 51 (§0ae), which closed
lead 5b AND the caller-side twin the lead did not
know it had, by reading a table nothing had ever read:
`Il2CppMetadataRegistration.typeDefinitionsSizes` (assigned into
`type_sizes_count`/`type_sizes_ptr` since the registration loader was
written, then never consumed) gives every value type's EXACT size --
16,916/16,916 entries readable, 22/22 hand-checked types exact,
`work/probe_b51_typesizes.py`. Win64/MSVC returns a struct of size
1/2/4/8 by value and everything else through a hidden buffer in the FIRST
argument slot; both halves are disasm-proven at
`work/probe_b51_sretabi.py` (`Panel.get_IMGUIEventInterests` 0x182ef7bc0
is 3 bytes and takes a buffer -- `mov [rcx],ax` with `this` in RDX and
`mov rax,rcx`; `TimeZoneInfo.get_BaseUtcOffset` 0x18063aab0 is 8 bytes
and is `mov rax,[rcx+30h]; ret`). Of 17,723 valuetype returns, **11,046
are genuinely sret (7,633 with parameters -- `_setup_entry` seated every
one of them a register too far LEFT) and 6,677 come back in RAX (3,499
with parameters -- `_hint_arg_types`/`_positional_args` walked every CALL
of those a register too far RIGHT)**. Fixes 59/59b/59c/59d route all four
decision sites through one `Il2Cpp.returns_sret`, and delete the b35c
`any(field offset >= 0x18)` guess it supersedes.
`TimeZoneInfo.GetDaylightTime` went from
`year.GetPreviousAdjustmentRule(ruleIndex, ...)` -- a method call on an
int -- to `this.GetPreviousAdjustmentRule(rule, ...)`. Gate
**2/2,211/4**, bad-file SET unchanged (the documented TMP pair; ts_gate
lists every bad file so that 2-row report IS the per-file diff), the
+114 ERROR all inside them and all cascade churn (row-text buckets and
their top-12 distribution unchanged, 495 -> 499 distinct texts), brace
0/11,107, bare `objN;` 0, sweep crashes 2/2 pre-existing and into_block
12,484/2,923 -> 12,497/2,924. **read-before-def 124,715 -> 118,445
(-5.0%)**, methods 34,065 -> 30,962 (-9.1%); tree lines +4,643.

The candidate before it, `b50_out3`, covered batches 43 through 50 and
supersedes `1a_dup5b_out1` (left on disk, not reaped) — strict
superset, same source tree plus batch 50's fixes 57/58/58b/58c/58d
(Correctness backlog #2, read-before-def). Its own gate was **2/2,097/4** —
bad-file set unchanged (the documented TMP pair), and ERROR inside
those two files fell 5,020 -> 2,097; brace 0/11,107; sweep into_block
12,484/2,923 UNCHANGED (no fix touches CFG shape), crashes 2/2
pre-existing; tree lines 2,695,492 -> 2,694,051.
**read-before-def 214,287 -> 124,715 (-41.8%)**, the largest movement
that metric has ever had. Two unguarded intermediate builds hit real
regressions (819 newly-bad files, then 112), both caught by the gate
and root-caused the same session into fixes 58b/58c/58d — those trees
were deleted after their diffs were captured, never candidates. The
gate summary line alone would have MISSED the first one: total ERROR
FELL while 817 files went bad (§4's per-file-diff rule).** Batch 48 (§0ab) took todo lead #4's "slot liveness is ONE
upstream feature blocking three items" framing and **tested the premise
first — two of the three did not survive it, and no escape analysis was
needed or written.** Re-censused with a blocking-position test rather
than the b37 coexistence test, address-taken sources block **234 of
104,263 pure copies (0.2%)**, not 43.3%; out/ref detection is not
blocked on a stack-frame model at all but decidable from the callee's
declared parameter type; and the "phantom first store" is the IL
`.locals init` zero-fill of a byref parameter's buffer (disasm-proven,
0x180671845), blocked on a ParamAttributes field v31 metadata does not
have. Shipped fixes 54/54b/54c (render a `&X` call argument by what the
callee DECLARES — `ref X` for byref, bare `X` for a by-value struct
passed by hidden pointer, untouched raw `&` for anything else) and
55/55b (`_drop_dead_lastdef`, worth an honest 405 lines). `ref <local>`
renders 28,267 -> 7,244, of which 8,238 ungrammatical
`((byte*)ref obj12 + 0x0)[0]` / `(ref this.m_InertialFrame).frame` sites
-> 531 genuinely-correct ones; tree lines -4,189. Gate **2/4,863/4**,
bad-file set unchanged (the documented TMP pair, the -1 ERROR entirely
inside TextMeshPro.cs), brace 0/11,107, sweep crashes 2/2 pre-existing,
into_block 15,418/3,957 -> 15,416/3,956. Batch 47
(§0aa) closed lead #7: `_hint_arg_types` had the same ordinal-per-class
register-walk bug fix 42b corrected in `_positional_args` (two
independent float/int counters instead of one shared Win64 positional
counter), so interleaved float/int signatures (2,288 methods
corpus-wide) got hinted from the wrong register slot. Fixed to mirror
`_positional_args`' walk exactly. Gate byte-identical to the documented
baseline (2/4,864/4), 0 new crashes, brace 0; full-corpus sweep
into_block unchanged at 15,418/3,957 (hint-only, no CFG-shape change),
lines -7. Batch 46 (§0z) closed the standing Correctness-backlog
`_collapse_arm` dead-code finding: the emptiness check tested the
pre-drop arm (always non-blank, the label line lives there) so the
collapse never fired; fixed to test the post-drop set, which surfaced
and fixed a second, previously-dormant dangling-goto bug in the same
function (caught live by `work/hoist_test.py`). Gate byte-identical to
the documented baseline (2/4,864/4), 0 new crashes, brace 0;
full-corpus sweep into_block 15,419/3,958 -> 15,418/3,957, lines -8.
Batch 45 (§0y)
shipped interface-dispatch naming (lead #3, the interfaceOffsets-search
shape): `/*indirect*/` lines 14,179 -> 13,009 (-8.3%), gate
byte-identical to the documented baseline (2/4,864/4), 0 new crashes
(2/2 pre-existing TMP caps), brace 0.
Batch 43's tail-DUPLICATION fallback (duplicate a
funnel-blocked shared tail into each goto site instead of hoisting it
once — sound because nothing else jumps into a goto's own position, so
it needs none of the funnel's non-participant-leak reasoning) recovers
over half the batch-42 residue: sweep into_block 32,094/9,434 ->
15,419/3,958 (-52% sites). Capped at 24 raw tail lines after a
`_singleton_cse` interaction ballooned one method 108->324 lines
(InventoryManager.AssignTemplates). Batch 44's else-if/switch
flattener (`_elseif_flatten`, a pure boolean-identity rewrite, no CFG
reasoning needed at all unlike batch 43 on the same source shape) then
turns PickupNewObj's 6-level `index != 5/3/2/11/58/4` pyramid — and
13,224 similarly-shaped sites corpus-wide (0 existed before this
session) — into flat `else if` chains. Gate byte-identical to
b42_out1/b43_out1 (2/4,864/4, 0 newly bad), brace 0/11,107, crashes
2/2 pre-existing, tree lines 2,663,122 (b42_out1) -> 2,630,342 (net
-32,780 despite batch 43's own +75,477 duplication cost). Full
writeups, the exact gate logic (including two reverted fix attempts
for a real live-caught bug), and the residual-lead breakdown in
§0w/§0x. Promotion over `final_out/` is a human call per the standing
rule (§0/§6).

The golden suite (`PYTHONHASHSEED=0 pytest work/test_goldens.py`) is
part of the inner loop — but it samples 50 bodies; for structural
pass changes the full-corpus sweep sizes what it only shapes (§7's
batch-42 caveat). **`goldens.json` was regenerated 2026-09-05 at the
gated `b71_out1` build (batch 71, §0ao)**: the old-vs-new diff moved
EXACTLY the 20 documented mismatch names — batch 71 itself moved 0 of
the 50 sampled bodies (the sample holds no static-field shapes; its
real sites are pinned by `work/staticfield_test.py` 20/20 and the
sweep) — and the suite is 50/50 since (`work/goldens_b70.json.bak`
kept). Before that it had been STALE as of batch 48: last regenerated
2026-08-22 19:32, predating batches 44+45's own source changes
(il2csharp.py last touched 22:27); 7/50 cases mismatch
(AudiencePath, CurrentDayManager, GameManager.CheckAllReady,
InputManager, InventoryManager.AssignTemplates, LegsAnimator,
SendMouseEvents) but every one is confirmed pre-existing drift, not a
live regression (checked four times now, batches 45, 46, 47 and 48, all
via a byte-identical patch-revert A/B). **Batch 48 adds 4 more
mismatches (11/50 total) that are INTENDED and were read line by line**
— ActorCOMTransform.Update, AddRandomVelocity.Update, LobbyMenu.Update
and BurstSolverImpl.ApplyFrame, all the fix-54 `&`/`ref` render family
(§0ab). Batch 49 added InventoryManager.AssignTemplates and
RenderGraphPass.SetColorBufferRaw (12/50). **Batch 51 adds ONE more (19/50),
`int3x3.op_BitwiseOr@1827257d0`, read against the disassembly at
0x1827257d0 (`mov rdi,rcx` parks the sret buffer, `movsd xmm0,[rdx]`
reads `lhs`, `mov ebx,r8d` reads `rhs`) and confirmed correct --
`num1 = ((byte*)rhs + 0x0)[0] ... | num5` with `num5` defined nowhere
became `num1 = lhs.c0 ... | rhs`.** **Batch 50 adds 6 more
(18/50), every one read individually and confirmed CORRECT AGAINST
DISASSEMBLY** — `<>c.<DescribeFields>b__0_7` and
DateTimeParse.ParseFractionExact (fix 57's entry positional walk),
DeviceEnumeratorBase.set_OnReady, EnumBuilder.IsArrayImpl,
Expression.GetUserDefinedUnaryOperatorOrThrow and
Speaker.StopPlayback (fix 58's argument trim); see §0ad.
Batches 52, 53, 54 and 55 each moved NONE of
the 50 — the same 19 by name throughout. **Batch 56 adds ONE (20/50),
its own and intended: `VFXEventAttribute.HasInt@182f7c410`,
`object obj17 = ...HasInt_Injected() /*indirect*/(this.m_Ptr, nameID,
obj7, obj8, obj10, obj12, obj14, obj16);` -> `return UnityEngine.VFX.
VFXEventAttribute.HasInt_Injected(this.m_Ptr, nameID);`.**
**Batch 72d's dead static-read drops moved 7 more (regenerated at the
gated `b73_out1` build, backup `work/goldens_b72.json.bak`, 50/50
since -- every diff read line by line). Batch 74 moved none (the
sample holds no genericinst-static shapes; pinned by `work/b74_test.py`
38/38 instead). Batch 75 moves 8 (fix 75's phi placement; the fold
moves 0 -- the sample holds no delegate-cache triple): AudiencePath.
DrawCurved, CurrentDayManager.Rpc_RakeIntro, DateTimeParse.
ParseFractionExact, GameManager.CheckAllReady, InputManager.
UpdateState, LegsAnimator.Finder_AutoDefineOppositeLegs,
RenderGraphPass.SetColorBufferRaw, SendMouseEvents.SendEvents
(`work/goldens_b75_raw.txt`; all phi renumbering, read).**
Regenerate at/before the next
promotion (`PYTHONHASHSEED=0 python work/make_goldens.py`, then read
the diff before trusting it per the standing rule). **Batch 50 is also
the sharpest demonstration yet of the suite's limits: fixes 58b, 58c
and 58d each fixed an unparseable-output bug and moved ZERO of the 50
goldens — all three were caught only by the real build's gate**
(§7's sample-size caveat). `work/
hoist_test.py` (20), `work/elseif_test.py`
(13), `work/cse_test.py` (30), `work/flag_test.py` (22),
`work/cp_test.py` (20), `work/re_test.py`, `work/selfcopy_test.py`
(5), `work/forhead_test.py` (10), `work/itfdispatch_test.py` (14),
`work/refarg_test.py` (24), `work/lastdef_test.py` (22),
`work/callparen_test.py` (7), `work/flagcond_test.py` (26, new in
batch 52 -- ten cases pin what must STAY `unknown`) cover the statement
passes; `work/callname_test.py` (21) needs `PYTHONPATH=.`.
`work/jumptable_test.py` (9, new in batch 55) pins `_jump_table`'s
recognizer on eight real dispatches plus a case map checked against
Unity's published source; unlike the others it loads the binary
(~7s), because a jump table only exists there.
`work/icall_test.py` (10, new in batch 56) does the same for the icall
thunk-cell path — four resolution cases (one pinning that an
unresolvable signature must NOT claim an identity, which is what keeps
the honest `/*indirect*/`) and six full-body renders read against
disassembly; it also loads the binary (~6s), since a cache cell only
exists there. `work/b72_test.py` (65) / `work/b73_test.py` (32) /
`work/b74_test.py` (38) pin the static-field family and its contract;
`work/b75_test.py` (fix-75 phi placement) 7/7 and `work/b75fold_test.py`
20/20 (fix-75b `??` fold, synthetic + SetActiveCamera) pin the shipped
shapes (§0as); `work/b76_test.py` 16/16 pins the closed-generic-CLASS
static route, synthetic + live (§0at).
`final_out/` holds the promoted b42_out1; `work/sweep_1a_audit.py`
(standalone re-creation) is the current into_block sweep tool since
the historical `sweep_audit.py`/`classify_into2.py` were reaped at the
b42_out1 promotion.

## Next-session leads (ordered by expected payoff; sizes at final_out
= b42_out1 unless a lead carries its own census vintage)

**Methodology note, earned in batch 52 (§0af):** that batch came from
READING one decompiled file end to end, not from this list, and it
found three defect families -- ~9,300 `unknown` conditions/ternaries,
18,035 mis-parenthesised movzx masks, and an unbalanced `switch`
subject -- that **every existing metric was structurally blind to**.
read-before-def counts undefined TEMPS, so a bare `unknown` token is
invisible to it; the parse gate sees only what fails to parse, so
`x & 0xFF + i*8` (which parses, and means something else) is invisible
to it; the brace audit counts braces, not parens. Periodically read a
whole file with fresh eyes. The leads below are what the metrics can
see; they are not the whole of what is wrong.

Clean-code assessment 2026-08-22 (read InventoryManager.cs at b38_out1
end to end; 6,359 lines / 144 methods / rbd 247, down from 722): the
list below is what remains after batches 39-41 shipped the top seven
leads (stack probe + flagN inlining, §0s; singleton CSE + member-load
CSE + bool args + flag tail, §0t; self-copies + for-head dup calls,
§0u).

1. [x] **Shared-tail goto triples — SHIPPED batch 42 (fixes 51-51g,
   new.md §0v), with a different yield than §0u predicted.** The LCA
   extension exists and the classify mirror ran first (SOUND had
   drifted to 47: later passes MINT hoistable shapes after the pass
   runs — hence 51b's late second run). But the strict funnel the
   soundness proof forced (every non-participant arm at the carrying
   LINK must not fall) REJECTS the flagship pyramids: their default
   arms RETURN past the merge (disasm-proven twice, §0v). The batch's
   real yield = the funnel on classic hoists (two b41 wrong-hoist
   families fixed) + 51a's live hole + the LCA/late-run unlocks. Do
   NOT reopen the pyramid family without per-path definite-assignment
   analysis (see the new lead 1a).
1a. **The funnel-blocked residue — MOSTLY SHIPPED batch 43 (new.md
   §0w), with a cheaper mechanism than either path this lead
   originally named.** Neither per-path definite-assignment analysis
   nor lead 2's switch recovery turned out to be necessary: a
   funnel-blocked shared tail can be DUPLICATED into each goto site
   instead of hoisted once, and that needs no reasoning about
   non-participant paths at all (nothing else jumps into a goto's own
   position, so replacing the goto with a copy of what it points to is
   always sound there). Sweep into_block 32,094/9,434 -> 15,419/3,958
   (-52% sites / -58% methods); gate/brace/crashes all clean (§0w).
   **Residue (a) — SHIPPED batch 49 (fix 56, new.md §0ac), cap
   removed entirely.** Root cause: every duplicate copy is the same
   text, so a tail-local decl re-declares the identical token in each
   copy — legal C# (separate block scopes) but it starved
   `_singleton_cse`/`_value_cse`'s flat, non-block-scoped
   single-assignment check, dropping the token from folding ENTIRELY.
   Fixed by minting each copy its own fresh token numbers for
   tail-local declarations (a token the tail only reads from outside
   stays shared, so `_singleton_cse` still hoists ONE fetch for the
   whole method). Hardened same session after the real gate caught a
   live regression: a tail containing its own `try`/`finally`
   (a Monitor.Enter guard) must not be duplicated — a second guard
   region elsewhere corrupted an unrelated dead-arm-collapse pass's
   handling of a first, untouched one; that interaction is NOT
   root-caused, so such tails stay an honest goto. Full-corpus sweep
   -19.0%/-26.1% (sites/methods) off the b48_out1 baseline, gate
   byte-clean on the bad-file SET (still just the documented TMP
   pair), brace 0/11,107, 0 new crashes. `1a_dup5b_out1`.
   **(b) still open:** whatever still fails
   `_falls_to`/`_lca_hoist_plan`'s structural checks entirely (stray
   code between nested closes, SEH-crossing, nested labels,
   forward-disjoint gotos) — these were never in scope for hoist OR
   duplicate and still need per-path definite-assignment analysis (the
   slot-liveness upstream feature, backlog #2/out-ref); lead 2's own
   switch recovery (SHIPPED batch 44 as an else-if flattener only, see
   below) does NOT cover this residue — it never attempted the actual
   `switch`-statement synthesis that would. Cosmetic side effect of
   duplication itself: see the new "foreach degrades to indexed for"
   readability item below.

2. [x] **The nested not-equal pyramid — SHIPPED batch 44 (new.md
   §0x), the else-if HALF only.** `_elseif_flatten` turns PickupNewObj's
   `index != 5/3/2/11/58/4` 6-level nesting (and 13,224 similarly-
   shaped sites corpus-wide) into a flat `else if` chain — a pure
   boolean identity, no CFG reasoning needed. **Still open, deliberately
   NOT attempted this batch: the actual C# `switch` statement
   synthesis** the lead's own text originally pointed at ("the
   flattened chain is the cleanest switch-recovery input") — turning
   `if (x==C1) {...} else if (x==C2) {...} else {...}` into a real
   `switch (x) { case C1: ...; break; ... default: ...; }` needs
   recognizing the SAME token compared to constants across the whole
   chain, C#'s `break`/fallthrough semantics, and a `default:` arm —
   real, separate work, not a trivial extension of the flattener. Until
   it exists, lead 1a's "(b) lead 2's switch recovery" recovery path
   for the funnel-blocked residue is NOT actually available — only
   path (a), per-path definite-assignment analysis, remains open there.
   **SIZED batch 50 and it is SMALL — do not pick this up expecting the
   13,224 number to carry over.** `work/census_b50_switch.py` over
   `1a_dup5b_out1` finds only **712 same-subject `==`-constant chains
   tree-wide, 308 of them clean, and 228 of those are 2-arm** (better
   left as `if`/`else`); at 3+ arms it is **80 chains**. The 15,559
   `else if` lines are dominated by `X == K` / `X != K` against
   DIFFERENT subjects (1,850 / 1,791) and by `((byte*)…)[…] != X`
   deref forms, none of which a `switch` can take. Rejections, for
   whoever does try: nonconst 163, non-pure subject 144, `goto` in an
   arm 105, label in an arm 97, duplicate case value 85, a `break;`
   in an arm that would newly bind to the synthesized switch 27.
   **SHIPPED batch 72 (fix 72e, new.md §0ap)**: `_switch_synth` runs
   right after `_elseif_flatten` on the flat chains, census-guarded;
   **switch statements 758 -> 798 (+40 across 29 files)**. The rest of
   the census's clean chains reject on chain heads that are not bare
   `if (` lines and on the hazard list; a deeper harvest would anchor
   mid-chain heads. Unit-pinned in `work/b72_test.py`.
3. [x] **Indirect-dispatch NAMING — SHIPPED batch 45 (new.md §0y),
   the interfaceOffsets-search shape only.** `Il2Cpp.
   interface_method_by_offset` + `Decompiler._name_interface_dispatch`
   resolve the `typeof(IFace)` + interfaceOffsets-linear-scan pattern
   (GameManager.CheckAllReady VA 0x1806DF770 ground truth) straight
   from metadata — interface typedefs carry no runtime vtable of their
   own (`vtable_start` is -1), but their own `method_start`/
   `method_count` gives the true method-block order, verified NOT to
   be BCL declaration order (`IEnumerator.method[0]` is `MoveNext`,
   not `get_Current`). `/*indirect*/` lines 14,179 -> 13,009 (-8.3%),
   generalizes across the whole corpus (Fusion.Sockets, JSONAccess,
   UIElements, Photon's EnetPeer, System.Xml's Compiler all got real
   `.MoveNext()`/`.GetEnumerator()` renders, not just the ground-truth
   method).
   **The resolved-name half is CLOSED, batch 56 (fixes 66/66b/66c/66d,
   new.md §0aj): `/*indirect*/` 13,808 -> 7,538 (-45.4%).** It was the
   largest bucket in the residue and it was NOT in this lead's own
   list — that list was a batch-38 vintage, eighteen batches stale.
   **Do not size this lead from bucket names again: re-run
   `work/census_b65_indirect.py <tree>` first** (buckets every
   `/*indirect*/` line by the shape of its callee, ~1 min).
   **Residue at `b66_out1`, in size order — each needs its own
   mechanism, not an extension of an existing one:**
   - **klass-slot vtable dispatch, 3,901** (`((byte*)((byte*)X + 0x0)[0]
     + 0xNNN)[0]()`, displacement 0x138 + 16*slot). The slot is already
     decoded (`Lifter.ind_slot`, batch 38b) and used for the arity
     bound; what is missing is the RECEIVER's static type, so
     `Il2Cpp.vtable_method` has nothing to look up. Displacements are
     spread thin (top: 0x1c8 265, 0x188 255, 0x168 252) — no hot slot
     to special-case. This is a type-recovery problem upstream of the
     call, not a naming problem at it.
   - **bare temp, 2,175** (`objN() /*indirect*/(...)`) — a genuinely
     unknown function pointer, concentrated in native interop
     (Steamworks, Photon's SocketNativeSource). Likely unrecoverable.
   - [x] **delegate `invoke_impl`, 626 — SHIPPED batch 60 (fix 70,
     new.md §0an).** `predicate.invoke_impl(predicate.
     method_code, <real args>, predicate.method, predicate.invoke_impl)`
     IS `Delegate.Invoke`, and the shape is completely regular: callee
     `<d>.invoke_impl`, arg0 `<d>.method_code`, compiler plumbing
     (`.method`, `.invoke_impl`) trailing the real arguments. Folding
     it to `<d>.Invoke(<real args>)` is a rewrite, not an inference;
     the only real question is where the argument list ends, and the
     delegate's own instantiation (`Predicate<T>`) declares that. The
     implementation resolves the open TypeDef's `Invoke` and substitutes
     the receiver's concrete generic arguments before deciding return ABI
     or parameter types. **626 -> 3**; the three residual receivers have no
     concrete delegate type and deliberately keep the honest marker.
   - **obj-vtable-0 deref, 494** (`((byte*)objN + 0x0)[0]()`), **other
     constant deref, 315**, **Burst `FunctionPointer<T>.Pointer`, 26**
     (a real runtime pointer field — correctly left honest),
     **`data_*`, 1**.
4. [x] **Copy-prop's remaining ~100k pure copy lines — the
   "slot liveness is ONE upstream feature" framing is RETIRED, batch 48
   (new.md §0ab).** The b37 split quoted here (address-taken 43.3%)
   bucketed a copy as address-taken whenever `&lhs`/`&rhs` appeared
   ANYWHERE in the method — coexistence, not causation.
   `work/census_b48_copyres.py` re-asks the question the pass actually
   asks (is an escape of the SOURCE between the copy and the next read
   of the DEST?) and reads, at b47_out1: in_loop 68.3% / no_read 18.4%
   / escape_coexist-in_loop 12.5% / escape_coexist-no_read 0.6% /
   **escape_blocks 0.2% (234 of 104,263)**. Escape analysis was never
   the blocker here. The out/ref half shipped by a different mechanism
   entirely (fixes 54/54b/54c, metadata not liveness) and the phantom
   first store is blocked on absent metadata, not on analysis — so the
   three items never shared a blocker. **Do NOT reopen this item for
   address-taken sources.**
4a. **The copy residue that is genuinely still open: loop-carried and
   back-edge-reachable copies** (b48_out1: in_loop 73.4%, no_read
   18.6%). Fix 55 (`_drop_dead_lastdef`) took the actionable slice and
   is worth an honest 405 lines; its rejection census over 1,500
   methods is `later-occurrence` 1,246 / `in-loop` 911 / `back-goto`
   509 / DROPPED 5, and relaxing its right-hand-side rule to
   `_drop_dead_locals`' own purity test changes DROPPED from 5 to 5.
   The ceiling under sound guards is reached; what remains needs real
   loop liveness on the flattened statement list (a back edge can
   re-read a value no text-later read shows), not a looser filter.
   Size that before attempting it.
5. [x] **read-before-def re-bucket — DONE batch 50** (new.md §0ad):
   `work/census_b50_rbdprov.py` buckets by MINT SITE, not by the shape
   of the reading line, which is what this item actually wanted. The
   result and the retired premise sit on backlog #2 above; the open
   residue is lead 5a there. Still open and untouched from this item's
   original text: **re-bucket dup_impure before trusting it** — its
   count includes same-text renders of DISTINCT instructions (fix 40's
   identical-text renders; §0r has the EqualInstruction evidence), and
   batch 50 proved that hazard is live in PRODUCTION code, not only in
   the census: fix 58b found `_bind`'s in-block window collapsing five
   separate `new List<int>()` allocations into one temp because it
   matched per-text. A per-instruction-render-count census is the
   honest metric.
5b. [x] **`_setup_entry` does not model the hidden sret buffer** --
   SHIPPED batch 51 (fixes 59/59b/59c/59d, new.md §0ae), together with a
   caller-side half this lead did not know existed. The boundary the
   lead asked for is disasm-proven (`work/probe_b51_sretabi.py`): a
   hidden buffer appears exactly when the returned value type's size is
   NOT in {1,2,4,8}. The exact size comes from
   `Il2CppMetadataRegistration.typeDefinitionsSizes`, which the
   registration loader had been reading into `type_sizes_count`/
   `type_sizes_ptr` and never consuming (`work/probe_b51_typesizes.py`:
   16,916/16,916 readable, 22/22 hand-checked types exact, and it
   disagrees with the old `field offset >= 0x18` guess on 776 of 5,756
   value types). The "upper bound 11,132" is now the exact pair
   **11,046 sret / 6,677 RAX-returned** (7,633 and 3,499 of them take
   parameters). One authority, `Il2Cpp.returns_sret`, feeds all four
   decision sites. read-before-def -5.0%, gate bad-file SET unchanged,
   `b59_out1`.
5c. [x] **The arity trim does not count the sret slot — CLOSED batch 59
   (new.md §0am).** Sized with a temporary lifter probe (`work/
   patch_probe_b69_sretarity.py`, the pattern this item itself
   prescribed): 659 of 116,178 methods reach the trim with a sret return
   the struct-return fold above it did not already peel off, **376 of
   which actually drop the true last argument**. Fix 69 mirrors
   `_hint_arg_types`/`_positional_args`'s own unconditional
   `if returns_sret(rty): +1`. Fix 69b closed a self-inflicted follow-on:
   `rest = args[1:]` (feeding the property/indexer accessor folds)
   hardcoded "args[0] is the receiver", wrong once sret also shifts the
   receiver to args[1] -- caught by a direct diff against b68b_out1, the
   same way lead 8's fix 68c was. All 34 changed files read in full and
   confirmed correct (SIMD intrinsics, math, physics, rendering, input).
   `b69b_out1`. Do not reopen without a fresh shape.
6. The SEH multi-span lead is unchanged.
8. [x] **The `& 0xFF/*z*/` residue `_BZEXT_RX` structurally cannot
   reach — CLOSED batch 58 (new.md §0al).** Replaced with
   `Decompiler._bzext_strip`, a literal-aware balanced-paren walk (fix
   68) plus a mandatory-delimiter check (fix 68b, caught by a unit test:
   `while`/`switch`/a bare `if`/a single-arg call's own required parens
   are not the mask's droppable wrapper) plus a fix for the regression
   the walk caused in `_is_sugar`'s `_HIER_RX`, which had assumed the
   mask's wrapper parens would always survive (fix 68c, caught by a
   direct per-file diff against b66_out1 -- neither the crash sweep,
   goldens, nor the tree-sitter gate saw it). **Masks 14,365 -> 0
   (-100%)** tree-wide. `b68b_out1`. Do not reopen without a fresh
   shape (a new mask-marked residue would be a new bug, not this lead).
10. [x] **Jump-table dispatch is not recovered — CLOSED, SHIPPED
   batches 53, 54 and 55 (new.md §0ag/§0ah/§0ai). The lead's own guess
   ("an unrecognised ADDRESSING form reaching the prewire's
   recogniser") was wrong all THREE times: the recogniser was fine, it
   just never saw the table (53, 54), and where it did see one it
   mislabelled the cases (55).**
   Two distinct causes, each found by instrumenting the recogniser
   rather than by reading output text:
   - **the decode window** (fix 63a, batch 53). `_decode` cut every
     method at 64KB; `InventoryManager.Update` is 0x110A0 bytes, so its
     60-entry table's entry[0] sat past the cut and `lo <= tgt < hi`
     broke on it. Fixed by a proof-driven second decode pass. Needed
     fix 63b (CFG block cap 1500 -> 3000) not to make that method
     worse — which incidentally cleared the legacy-TMP pair and took
     the parse gate to 0/0/0.
   - **one `lea` per function, reused by every table in it** (fix 64,
     batch 54). The table-base lookback was 5 instructions. MSVC emits
     a single `lea rB,[rip+image_base]` and reuses rB for every
     dispatch in the function, so a second table reached from inside
     the first one's case bodies has no `lea` anywhere near it —
     CurrentDayManager.PlayNextOccurence 0x1806A6000 (`lea rdx` at
     0x1806A6924 serving tables at 0x1806A7348 AND 0x1806A737C, 45
     instructions apart), DateTimeFormat.ExpandPredefinedFormat
     (three tables off one `lea r12`), DateTimeParse, RuntimeType,
     JsonTextReader. Fixed by walking back to the nearest earlier
     `lea tabreg,[rip+X]`; sound without dominance analysis because
     the walk stops at the nearest match (so it cannot regress a table
     that works today) and every downstream check validates the guess.
   **Sizing tool, and use it instead of the text census: `work/
   census_b63_tables.py`** buckets every `jmp reg` in the methods that
   still render a raw table load, by `_jump_table`'s own rejection
   reason, in ~17s. (The first cut walked all 88,976 methods and was
   killed at 35 minutes — it is driven from the built tree for a
   reason; widen the input set deliberately if you must.) At b63_out1,
   before fix 64: `no_lea` 77 / `ok` 22 / `short` 12 / `window` 0
   (63a's bucket empty, as designed). After fix 64: **`ok` 92 /
   `short` 12 / `no_lea` 8**.
   - **the residue — CLOSED batch 55 (fixes 65a/65b/65c, new.md §0ai),
     and this lead's own residue text was half wrong.** `no_lea 8` was
     never a real bucket: all eight sites have a reachable table-base
     `lea` (11 to 123 instructions back) that fix 64 already finds, and
     `census_b63_tables.py`'s `classify()` mirror was simply stale (its
     own lookback stayed at 6 instructions). **The image-base fallback
     this lead prescribed was never written — nothing needs it.** The
     real causes: the `cmp idx,N` bound scan took the FIRST hit in its
     window rather than the nearest (65a), and the sparse form's group
     table was read only for the operand register when it is actually
     the switch's CASE MAP (65b) — expanding through it both gives the
     exact entry count and fixes wrong case labels on every sparse
     dispatch that was already structuring. 65c stopped
     `_prune_nonreturning` renumbering cases after a dropped throw-stub
     edge. Buckets **`ok` 111 / `short` 1**, the one being
     JsonParser.Equals 0x1825B3200 (`jmp rax` off `mov rax,[r8+138h]`,
     a virtual tail-dispatch — correctly not a table). Pinned by
     `work/jumptable_test.py`. **Nothing is open here; a new
     unrecovered dispatch would be a new bug.**
   Note the
   text metric is a poor proxy here: `data_180000000` also appears as
   ARGUMENT spray (`sub_1805c4ee0(0, data_180000000, ...)`, the
   image-base register read as a call argument), which is a different
   defect — the batch-16 "named static-address residues" bullet below.

9. **The surviving `unknown` flag-specific conditions** (batch 52,
   §0af) are the sound half by construction, not a backlog: block-entry
   flags rebuilt from carried TEXT with no recorded setter (decompiler.py
   ~1139 nulls the stamp deliberately), plus fix 60b's guard firing on
   an instruction that writes SF/PF without a modelled handler.
   **SIZED batch 57 (§0ak) with a proper tool
   (`work/census_b67_unknown_split.py`, new -- hooks BOTH real
   `flag_cond` call sites, including decompiler.py's own separately-
   bound one the old census never reached): 44 hits/5,809-method sample,
   split 45.5% "no setter recorded" / 27.3% "sign setter present,
   unmodelled pair" / 27.3% "parity setter present, unmodelled pair".**
   **The "no setter" fix was ATTEMPTED and REVERTED in batch 57 --
   read §0ak in full before retrying.** Root cause was real and is now
   understood (every `!flags` end-state Expr has always been built with
   `ty=None`, so fix 60's own documented cross-block reconstruction has
   been dead code since it was written, in both lift passes; pass 2 --
   the one that emits final text -- additionally never reset `L.flags`
   between blocks at all), but two implementation attempts both failed:
   the first (storing the carried pair in `Expr.ty`) crashed 223 methods
   corpus-wide (`.ty` is read elsewhere as an il2cpp type tuple and bit-
   shifted); the second (a side-channel dict instead, unanimous-
   agreement gated on setter+lhs+rhs together) passed the crash sweep,
   goldens, and a real build's tree-sitter gate clean, but a direct
   file-diff against the known-good baseline caught a live regression --
   `Computer.cs`'s ordinary (non-flag-specific) `if (this.tabs.Length ==
   1)` rendered as `if (unknown == unknown)`. Not root-caused before the
   revert. **Whoever retries this needs a way to verify the
   reconstruction is actually firing correctly, not just that nothing
   crashes** (§0ak's own lesson: the crash sweep and goldens that batch
   ran were, in retrospect, testing an accidentally-inert intermediate
   state and would have looked clean either way). The unmodelled-pair
   residue (54.5% combined) is untouched by any of this and still needs
   its own work: deriving sign from `cmp` (currently declined for
   overflow-safety) or parity from ordinary integer ops (currently only
   SSE compares are modelled).
7. [x] `_hint_arg_types` ordinal-per-class register walk bug — SHIPPED
   batch 47 (fix 53, new.md §0aa). Mirrored `_positional_args`' shared
   `pos = base + pi` positional walk; 2,288 interleaved-signature
   methods corpus-wide were affected (`work/probe_b47_hintpos.py`).
   Gate byte-identical (2/4,864/4), brace 0, full-corpus sweep
   into_block unchanged (15,418/3,957, hint-only), lines -7. `b47_out1`.

11. **Static-field naming residue after batch 76 -- 12 real
     tokens across 6 files** (fixed-regex census
     `work/census_b73_static.py <tree>`; the mechanism-tied census is
     `work/probe_b74_census.py <tree>`).
     Lead 11(a)'s genericinst families are BOTH CLOSED (fix 74, §0ar:
     valuetype-underlying GENERICINST statics through the reconstructed
     inflated layout; fix 76, §0at: closed-generic-CLASS statics through
     the reconstructed closed static map -- 9 tokens cleared, 0 new:
     EventBase<T>.EventCategory x5, BaseField<string>.mixedValueString
     x2, BaseCompositeField twoLinesVariantUssClassName x4).
     What remains, in size order:
     (a) **generic-CLASS instantiation statics -- CLOSED batch 76
         (fix 76, §0at).** `typeof(EventBase<GeometryChangedEvent>).
         __static_fields.__static_10` (UIRLayoutUpdater, VisualElement,
         VisualTreeStyleUpdaterTraversal), `typeof(BaseField<string>).
         __static_fields.__static_208` (BaseListView) -- plus two the
         lead had not counted: BaseCompositeField multi-arg
         instantiations (`__static_40` → twoLinesVariantUssClassName)
         and two obj-temp-based EnumField sites whose temps kept their
         genericinst types (`__static_208` → mixedValueString,
         `__static_1f0` → mixedValueLabelUssClassName). The static
         blob of a CLOSED generic class is reconstructed from the open
         td's static field list (declaration order, natural alignment
         capped 8) with class args substituted -- the CLASS-side twin
         of fix 74, keyed by the instantiation. Needs no extension
         unless a site reads past 0x210 in a reconstructed map (packed
         vs natural alignment diverge there; no such site exists).
    (b) **deref-through-named-static** -- InputActionState's
        `(obj.__static_fields + 40)[num8]` (blob+0x28 IS
        s_GlobalState, a held REF; the render indexes THROUGH the
        slot instead of naming the field and reading the pointee's
        member at the index offset; one 0x58 copy survives fix 74 as
        an honest span miss), InputEventTrace's
        `(obj180.__static_fields + 16).IsGeneratedLayout(...)`
        (14 mentions), InputUser (11). Needs a
        load-named-field-then-deref mechanism, not static_off_path.
    (c) **bare blob pointers as values (honest)** -- dictionary
        keys / TryGetValue args / null tests (DataBindingManager 9,
        CallbackDispatcher's `obj11 = obj6.__static_fields;` family,
        13 mentions): the pointer IS the value; do not prettify.
    (d) **address-of forms** -- SqlDecimal's 21 byte-offset statics
        (`obj5.__static_fields + 2`): the ADDRESS is the value
        passed on; the decompiler-side textual fold requires a
        `typeof(X)` base, an obj-temp klass base stays raw. Naming
        these needs an `&X.field` render, a different mechanism.
    (e) **sub-pointer reads inside string/int statics (~7 tokens)**
        -- byte-granular slices of a string's or int static's
        storage (the other-enum 0xe/0x8 buckets in the probe
        census): honest pointer arithmetic, must stay unnamed.
    (f) the old getClass()-rooted chains -- unchanged; the old
        (c) no-td obj-temp bases stay disproven (probe_b72_static.py).

## Standing backlogs — open items only

### Correctness

- [x] `_collapse_arm` dead code — SHIPPED batch 46 (fixes 52/52b,
      new.md §0z). Fixed the check (`k in drop`, per the batch-42
      finding); doing so surfaced and required fixing a second,
      previously-dormant dangling-goto bug in `_collapse_arm` itself
      (the copied-out else-body wasn't filtered by the same `drop`
      set). Gated fully: unit suites 17/17 (+ all other pass mirrors
      unchanged), full-corpus sweep into_block 15,419/3,958 ->
      15,418/3,957 (lines -8, 0 new crashes, brace clean both sides),
      real build gate byte-identical to baseline (2/4,864/4), brace
      0/11,107. `b46_out1`.
- [x] 26 census-residual sound sites at b42_out1 — RE-CHECKED and
      CLOSED 2026-08-23 (census_b42_v4.py) after batches 43-48's
      structural changes: re-ran against b48_out1, count was already
      down to 1 before any fix. Root-caused that one: it's
      `decompiler.py`'s own documented LAST pipeline pass (~487-501,
      after `_hoist_shared_tails`) appending `' ;'` to a label
      immediately before `}` (C# needs a statement there) — earlier
      label consumers, including the real hoist pass, correctly match
      only the un-suffixed `L_x:` spelling and see this as a nested
      label in the tail (refusing to hoist, correctly). The census
      script's own `LAB` regex required an exact `L_x:$` match, so it
      missed the `;`-suffixed form in the final tree and misclassified
      the site as hoistable — pure classifier drift, not a decompiler
      bug. Fixed `LAB` in `../work/census_b42_v4.py` to accept the
      optional `;` suffix; re-ran and residual count is now **0** at
      b48_out1 (confirms the hoist pass is fully sound under the v4
      model on the current tree). No production code changed.
- [x] #2 read-before-def — the item's PREMISE is RETIRED, batch 50
      (new.md §0ad). The standing instruction ("bucket by which lifter
      path emitted the phi") was finally carried out, by instrumenting
      the lifter rather than the output text
      (`work/census_b50_rbdprov.py`). **Phis are 3.0% of the mass**, not
      the dominant cause the item asserted; 79% is one thing — a
      register holding an unknown, being read (fresh-unknown 40.8% /
      entry-seed 38.5%), and the biggest single cell is entry-seeded
      ARG_XMM slots sprayed into `/*indirect*/` argument lists (15.4%).
      Fixes 57 (`_setup_entry`'s positional walk, the third copy of the
      42b/53 ordinal-per-class bug, 3,345 methods) and 58 + 58b/58c/58d
      took **214,287 -> 124,715 (-41.8%)**, the largest movement this
      metric has ever had. Gate 2/2,097/4 (bad-file set unchanged),
      brace 0, into_block unchanged, `b50_out3`.
      **Do NOT reopen this item as a phi problem.** The residue that is
      genuinely open is lead 5a below.
5a.   **read-before-def residue after batch 50** — **118,609 at
      `b62_out1`** (was 124,715 at b50_out3; batch 51's sret model took
      it to 118,445 and batch 52 put back 164 for an honest reason —
      §0af: a condition that printed the single token `unknown` now
      prints its operands, so an undefined operand is counted for the
      first time). The provenance census below was run at b50_out3 and
      its SHARES are still the guide, but re-run it before trusting the
      absolute numbers — two batches of lifter fixes have landed since.
      Re-censused on the FIXED source
      (`work/rbdprov_b50_after.txt`; §0ad has the before/after table).
      The argument-spray family is substantially closed (new/ctor -96%,
      bare `sub_` -67%, `/*indirect*/` -55%); what remains is three
      mechanisms fix 58 structurally cannot reach, in size order:
      **`copy rhs` 29.3%** (`objA = objB;` with objB unknown — not an
      argument slot at all, now the largest single family);
      **stores 18.2%** (`raw store lhs/rhs` 12.6% + `store rhs` 5.6%,
      an unknown written into a real field or through a raw pointer —
      §3 #2's old note rightly calls this class a correctness bug, not
      clutter); and **`stack-slot` 12.9%** (a slot read before any
      tracked write, `Lifter.slot_var`, a different mechanism).
      The 442 surviving `/*indirect*/` argument sites are the
      deliberate carve-out — an unknown in a MIDDLE GPR slot with a
      real slot after it, left visible because the later real slot
      proves the arity. **Find which instruction the lifter failed to
      model there; do NOT widen the trim.** Choose from the provenance
      census, not from `rbd_subclassify.py`/`rbd_misc_split.py` — those
      bucket by the reading line and answer a different question.
- [x] #5 instance methods rendered static — SHIPPED batch 38 (fixes
      40-40e; `GameObject.SetActive(obj22[num2], 0)` -> `obj22[num2].
      SetActive(0)`, static SetActive renders 63 -> 0 in AC). Closed;
      a NEW unshaped-receiver residue would be a new bug.
- [x] #6 golden snapshot tests — SHIPPED batch 38: `work/
      make_goldens.py` + `work/test_goldens.py` + `work/goldens.json`,
      50 bodies (16 ground-truth VAs + deterministic spread), ~13s,
      50/50 green. Regenerate ONLY after a gated build, and read the
      diff before accepting it (§0r records why: the first generation
      froze a then-live regression; batch 40's 47c catch is the
      suite earning its keep).

### Readability

- [x] self-copy drop — SHIPPED batch 41 (fix 49/49b, new.md §0u):
  `num4 = num4;` AC 103 -> 0. The copies are MINTED by `_copy_prop`'s
  substitution (backedge phi copy whose source resolves to the same
  local), so `_selfcopy_drop` runs immediately after it — the first
  cut's early slot fired zero times (`work/probe_b41_stages.py`).
  Unit mirror `work/selfcopy_test.py`.
- [x] for-head duplicate call — SHIPPED batch 41 (fix 50/50b, §0u):
  `num6 < FindGameObjectsWithTag("Flashlight").Length` ->
  `num6 < obj31.Length`, AC 28 -> 3 (residue = beyond-window and
  guard-blocked). Honesty proven by disassembly (`work/
  probe_b41_forhead.py`: 6 calls for 6 tags, all before their loops,
  none inside a back-edge span). Unit mirror `work/forhead_test.py`.
- [x] flagN ternary consumer — SIZED AND DECLINED batch 41: 7 sites
  in AC (`work/census_b41.py`). The flagN residue after 44/45/45b is
  multi-use flags, loop heads (kept by design), and non-adjacent
  consumers — all correct keeps. Do not reopen without a fresh shape.
- [x] "phantom first store" — DECLINED batch 41 with data, and
  ROOT-CAUSED batch 48 (new.md §0ab): it is the IL `.locals init`
  zero-fill of a byref parameter's stack buffer, not a phantom and not
  an escape-analysis problem. Disassembly at 0x180671845 (the same
  method whose `&obj4` motivated the item) is a 44-byte zero-fill —
  `xorps xmm0,xmm0` + two `movups` + two zero stores, exactly
  sizeof(RaycastHit) — of the buffer that becomes R8, the
  `out RaycastHit hitInfo` argument. Dropping it needs `out` vs `ref`,
  and **v31 `Il2CppParameterDefinition` is
  `{nameIndex, token, typeIndex}` (12 bytes, il2csharp.py ~322): there
  is no ParamAttributes field**, so out-ness is not recoverable at all.
  Fix 54 changes its status for free — the call now renders
  `Physics.Raycast(real5, real1, ref obj4, ...)` and C# definite
  assignment REQUIRES a store before a `ref` argument, so the store is
  load-bearing in the rendered form. CLOSED; do not reopen without new
  metadata. Update's flag5-9 twins stay per §0q's live-bool trade (the
  stores are those calls' last render, 23c invariant).
- [x] singleton CSE / member-load CSE — SHIPPED batch 40 (fixes 46/
      47, new.md §0t): method-scope singleton fetch with hoisted
      canon + inline-spelling rewrite; `_value_cse` for identical
      pure-load decls (depth model, identifier kills). Unit mirror
      `work/cse_test.py`. The accepted-trade record (calls between
      fetches) is in §0t.
- [x] bool call-arg literals — SHIPPED batch 40 (fix 48):
      `.SetActive(0)` -> `.SetActive(false)`, 815 sites in AC; the
      140-set residue is shared-body calls, honest by design.
- [x] null coalescing — SHIPPED batch 41 (`_redundant_else`, see
      new.md §0r): the if-null-return-else shape (1,054 sites) folds;
      `? null :` and `?? default` were already 0. Closed.
- [x] single-value phi propagation — PROBED and DECLINED batch 38
      with data (`work/probe_svphi.py`): same-value copies are 0.6%
      of AC's 235,126 copy lines and 76% of those exist only because
      a pred's value was skipped (unsound to collapse); the merge-time
      same-text collapse at `_analyze` already handles the real case.
      Do not reopen without a fresh shape.
- [x] out/ref parameter detection — SHIPPED batch 48 (fixes 54/54b/54c,
      new.md §0ab). **It was never blocked on the stack-frame model or
      on slot liveness**: the callee's declared parameter type decides
      it. Win64 passes anything not 1/2/4/8 bytes by hidden pointer, so
      a by-value struct argument and a genuine `ref`/`out` argument
      arrive through the identical `lea` (disasm-proven at
      DEMO_LegsAnim_KeepOnGround.FixedUpdate 0x180671800 @0x180671a30:
      Vector3 origin and direction BY VALUE, `out RaycastHit` — three
      identical leas) and only the byref bit separates them. `&X` now
      renders `ref X` at a byref param, bare `X` at a non-byref value
      type, and stays an untouched raw `&` for everything else (a lea
      at a string/int/float param means the slot mapping is wrong for
      that call — 5.4% of the corpus census — and is left honest).
      This also removed the arg-0-only `_ADDR_LOCAL_RX` rewrite whose
      `(?<=[\(,])` lookbehind had made all 21,955 b47 `ref` renders
      "argument 0" by comma position, 8,238 of them ungrammatical
      (`((byte*)ref obj12 + 0x0)[0]`). Residue, deliberately left: the
      tail-jmp `_call` path never calls `_hint_arg_types` (71 lines
      tree-wide), and 54c is render-only so the sret path still skips
      `&s_N` TYPE HINTING (size that separately). `out` is not
      separable from `ref` — v31 metadata carries no ParamAttributes.
- [x] **foreach degrades to indexed for after tail-duplication** —
      RE-CHECKED batch 47, STALE / does not reproduce. The documented
      example (`CurrentDayManager.Rpc_RakeIntro`, batch 43/§0w) now
      renders BOTH duplicated copies as `foreach (GameObject obj8 in
      obj7)` in the current tree (`b47_out1/Assembly-CSharp/
      CurrentDayManager.cs:867` and `:901`), not the degraded indexed
      `for` the batch-43 note described. Root cause it would have been
      (confirmed by reading `_structure`'s pass order, decompiler.py
      ~1801-1854): `_foreach_sugar` runs once, sandwiched between the
      first `_hoist_shared_tails` call and the LATE second one (fix
      51b, batch 42) — a tail duplicated only by the late run would
      indeed never get a foreach pass over it. But live output shows
      this pyramid's duplication already lands before the first
      `_foreach_sugar` call, so it isn't hitting that gap. Since the
      one concrete example that motivated this item no longer
      reproduces, and a corpus-wide census would need per-method pass
      instrumentation to distinguish real degradation from the (likely
      larger) set of loops that are legitimately never foreach-eligible
      (write access, multi-use index, etc.), this is closed without
      further chase. If a fresh concrete example turns up, the
      structural fix is a second `_foreach_sugar` call after the late
      `_hoist_shared_tails` (line ~1846) — it's idempotent by
      construction (already-folded `foreach` loops don't match
      `_FORHDR_RX` again) — but don't add it speculatively without a
      live case proving the gap is actually hit.

### Batch-16 leftovers / long-term

- [ ] three hot unknowns, deliberately left honest (exact semantics
      unproven from the head): 0x180002380 / 0x180002210
      (byte-identical dictionary-lookup helper), 0x18043dc60
      (assignability/interface-check family), 0x1804346b0
      (init-family; by-value copy/box helper smell).
- [x] named static-address residues: `__static_fields + N` is **0**
      tree-wide at b38 (collapsed by the b35b static-fields filter —
      this half is done). The `<>c`/`<x>9__` cached-delegate backer
      (3,478 shape hits) still needs the metadata field table — keep
      as the residue, scoped to that.
      **RE-CENSUSED batch 71 (§0ao): the first half's claim was
      WRONG** — the `__static_fields` family was live (5,342 lines /
      11,369 fallback tokens, including real wrong names); fixed as
      71a/71c, residue moved to lead 11. The cached-delegate backer
      half's stated blocker is also dead: the metadata field table has
      been parsed and field declarations render since batch 35 (the
      pattern spells `__c.__9__N_M` after `<>`-sanitization — 3,555
      `__9__` sites across 326 files at b70_out1, with named field
      decls like `public static Func<AudioListener, bool> __9__15_0;
      // static @0x8`). What remains open is the FOLD itself
      (null-check / init / use triple -> the delegate construction),
      not any metadata prerequisite.
       **CLOSED batch 75 (§0as): fix 75 places the phi copies
       before the fork, fix 75b (`Decompiler._delegate_cache_fold`,
       end of `_structure`) folds to
       `T objA = CACHE ?? (CACHE = new T(a1, a2));` -- 737 folds across
       181 files at `b75_out1` (gate 0/0/0), SetActiveCamera and OnEnable
       verified live. The pinned no-folds (self-copy tail, else, live
       arm statement, reassigned lhs, mismatched ctor/store, live spill,
       resolved ctor) remain the residue.**
- [ ] coroutine / state-machine MoveNext recovery (long-term).
- [ ] SEH round four: multi-span trys + the one surviving artifact
      (§6).

## Android Phase 1 (2026-09-07): pre-Unity-6 ARM64 registration -- DONE
Target: Chiki's Chase (`com.dvdfu.chicken2`, Unity 2022.3.41f1,
metadata v31, ARM64 `libil2cpp.so` + `global-metadata.dat` in
Downloads/). `--probe` + `--decls-only` now work on it; bodies still
x64-only (Lifter is `Decoder(64)` throughout).
What shipped (`work/patch_android_phase1{,b,c,d}.py`, backup
`work/il2csharp_pre_android.bak`):
- `ELF.apply_relocations()`: `.rela.dyn` R_AARCH64_RELATIVE (type
  1027) application at load — this dump ships zero addends (295,661
  slots), so every data pointer reads 0 without it. Skips exec
  sections; no-op for PE/relocation-free ELF (classic path untouched).
- `find_registrations_android()` (version-routed: non-6000 ELF only):
  mscorlib-anchored module search over all non-exec sections,
  module-list backtrack with strict 17-qword CodeRegistration check
  (X-128, v31.1 layout) + implied-index check (array must parse with
  mscorlib.dll at the entry's slot -- uniqueness does NOT hold here:
  extra RO tables reference modules and the array). Metareg keeps the
  classic pair order; q2/q3 goes unconsumed (open shape, see below).
- Ground truth: Cpp2IL dev-branch build+run on the same dump
  (codereg 0x2A98DE0, metareg 0x2B79C08, 73/73 module counts match
  exactly). Checkout + outputs under Temp\opencode (NOT in repo).
Gates: probe ok (59,026/65,884 addrs, 59,026/59,026 in exec);
decls-only full tree 6,852 files / 0 failed; output shape matches PC
decls-only control (base classes, field offsets, real types, enum
values all render); goldens 50/50 (no Windows regression).
Open gaps (bodies phase): (1) q2/q3 pair identity (4,893 pointers
into the shared pool, not `{argc,argv}`; `generic_insts` zeroed,
`generic_method_name` degrades gracefully); (2) GameCenter/AppleCore
method tables live in BSS (not file-backed, tolerated as empty);
(3) ARM64 lifter backend (Capstone + AArch64 semantics + AAPCS64 +
unwinding) -- the big one; `MiniArm64Decompiler.cs` ADRP technique
banked for reference recovery.

## Android bodies scaffold (2026-09-07) -- DONE, gated 0/0/0
`Arm64Lifter` (capstone decode -> `AInsn`, linear asm-comment
`lift()` fallback) + `Arm64Decompiler.lift_method` (real CFG via the
shared `_trace_reachable`/`_make_blocks`, asm-comment statements with
exact cbz/cbnz/tbz/tbnz conds, `x0` returns, shared
`_structure`/`_final_text`). Emitter dispatches by arch
(`is_arm64_binary`); x64 path behavior-identical (goldens 50/50).
Provenance: `work/patch_arm64_scaffold{,2,3}.py`,
`work/arm64_hist.py`; backups `*_pre_arm64scaffold.bak`.
Gates on Assembly-CSharp (494 files, 4,255 bodies, 0 failed):
tree-sitter 0/0/0 after two scaffold fixes (`#`-immediates are not
lexable C# -- strip in cond text; label-above-only-comments needs
`;` like the trailing-label rule -- shared `_final_text` tweak,
x64-gated). Histogram (6.8M insns): top 15 mnemonics ~93%, top ~30
~98% -- semantics order: mov/ldr/bl/adrp/ldp/add/stp/str first.
Next: AAPCS64 entry binding, `_insn` by frequency, ADRP xref
recovery, noreturn-throw set, ARM64 golden set.
