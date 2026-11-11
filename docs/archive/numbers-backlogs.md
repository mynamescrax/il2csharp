## 1. Archived numbers (current release is §0aw; corpus: Shift At Midnight; SOURCE at Review 77
-- gated candidate still `b76_out1`, batch 76; `final_out/` on disk is
the 2026-09-08 evening PARTIAL rebuild (6 assemblies, Review-77 source,
NOT a candidate -- §0au); promotion is a human call)

Batch 76 (§0at, CLOSED -- `b76_out1` the candidate): gate **0/0/0**,
brace 0/11,107, build 115,658 bodies / **0 failed** (784.5s). Sweep
116,178 methods / **0 crashes** / brace 0 / into_block **13,518/2,979
byte-identical to b75** (naming-only change). Tree lines 2,762,359 ->
**2,762,356 (-3)**; **7/11,107 files differ**, every diff read.
**Static naming residue 9 tokens cleared, 0 new** (closed-generic-CLASS
statics: EventBase<T>.EventCategory x5, BaseField<string>.
mixedValueString x2, BaseCompositeField twoLinesVariantUssClassName
x4 -- line-level census diff). Goldens 50/50 unmoved. Tests: b76
16/16; b72 67/67, b73 32/32, b74 38/38, staticfield 20/20, b75fold
20/20, b75 7/7.

Batch 75 (§0as, CLOSED -- `b75_out1` the candidate): gate **0/0/0**,
brace 0/11,107, build 115,658 bodies / **0 failed** (839.6s). Sweep
116,178 methods / **0 crashes** / brace 0 / into_block **13,518/2,979**
(work/sweep_b75b.log). Tree lines 2,699,104 -> **2,762,359 (+63,255)**;
**2,888/11,107 files differ**. **`??` delegate folds 0 -> 737 (181
files)**; cache stores 1,179 -> 442. Goldens regenerated at the gated
build, 50/50 (the same 8 phi-placement renumberings, read).
Tests: b75fold 20/20, b75 7/7, b72 67/67, b74 38/38, b73 32/32,
staticfield 20/20.

Batch 74 (§0ar): gate **0/0/0**, held. Brace 0/11,107. Sweep crashes
0/116,178, brace 0, into_block **13,505/2,978 byte-identical** to b73
(naming-only change; no CFG shape moved), sweep lines 1,990,095 ->
**1,990,093 (-2)**. Build 115,658 bodies / **0 failed** (the FIRST
b74 build failed 3 bodies -- the lay[2] porting slip, §0ar's incident
record -- fixed before the candidate existed). Tree lines
2,699,834 -> **2,699,832 (-2)**; **10/11,107 files differ**, every
diff read and confirmed. **`__static_N` tokens 273 -> 222** by the
old census regex (both sides carrying its `__static_fields`-as-
`__static_f` artifact; the tool is fixed now) -- **62 -> 24 (-61%),
files 21 -> 13** by the fixed regex; the mechanism-tied buckets:
genericinst-vt 25 -> **0**, and 13 of the 20 'vt/class' sites (deeper
generics inside plain-vt statics: Touch/InputActionState/
EnhancedTouchSupport/Awaitable) resolved with them. `work/b74_test.py`
38/38; b72_test 65/65, b73_test 32/32 (contract pin updated),
staticfield_test 20/20; goldens 50/50 unmoved (the sample holds no
fix-74 shapes). `b74_out1`.

Batch 73 (§0aq): gate **0/0/0**, held. Brace 0/11,107. Sweep crashes
0/116,178, brace 0, into_block **13,505/2,978 byte-identical** to b72,
sweep lines 1,990,099 -> **1,990,095 (-4)**. Build 115,658 bodies /
0 failed. Tree lines 2,699,839 -> **2,699,834 (-5, cs+csproj)**; **64/11,107 files
differ**. **`__static_N` tokens 1,906 -> 273 (-85.7%), files 121 ->
66**; UIElementsModule 1,419 -> **31**. `work/b73_test.py` 32/32;
goldens regenerated at the gated build, 50/50, the 7 diffs all read
(the fix-72d dead-drop family + two fix-73-resolved bodies).
`b73_out1`.

Batch 72 (§0ap): gate **0/0/0**, held. Brace 0/11,107. Sweep crashes
0/116,178, brace 0, into_block 13,506/2,978 -> **13,505/2,978** (the
-1 A/B-located), sweep lines 2,009,536 -> **1,990,099 (-19,437)**. Build
115,658 bodies / 0 failed. Tree lines 2,719,289 -> **2,699,839
(-19,450)**; 2,472/11,107 files differ. **`__static_N` tokens 5,564 ->
1,906 (-66%), files 969 -> 139**; the field@0 compounding shape
1,412 -> **0**; byte-cast blob twins 1,403 -> **194**; dead blob spills
1,003 -> **39**; **switch statements 758 -> 798 (+40 synthesized)**.
`work/b72_test.py` 65/65; goldens 43/50, the 7 mismatches all fix-72d
dead static-read drops, read line by line. `b72_out1`.

Batch 71 (§0ao): gate **0/0/0**, held. Brace 0/11,107. Sweep A/B
(work/ab_b71_into_block.py): crashes 0/116,178, into_block
13,506/2,978 identical on the patched and reverted-only-71 sides,
sweep lines 2,010,027 -> 2,009,536 (-491). Build 115,658 bodies /
0 failed. Tree lines 2,719,075 -> **2,718,561 (-514)**; 987/11,107
files differ. **`__static_N` tokens 11,369 -> 8,586 (-2,783), files
1,158 -> 969**; DateTime wrong-name witnesses 4 -> 0 and the composed
`(byte*)` array reads became real indexers. `work/staticfield_test.py`
20/20; goldens 30/50 pre-regen (the same 20 documented mismatches),
regenerated at the gated build -- old-vs-new diff exactly those 20
names, suite 50/50 since. `b71_out1`.

Batch 60 (§0an): gate **0/0/0**, held. Brace 0/11,107. Sweep crashes
0/116,178; brace/dangling/empty-arg/follower 0; into_block
13,506/2,978 -> **13,650/3,000**. Build 115,658 bodies / 0 failed.
Tree lines 2,684,731 -> **2,684,133 (-598)**; 229/11,107 files
differ, every one containing a converted delegate site. Delegate
`invoke_impl` **626 -> 3 (-99.5%)** and total `/*indirect*/` 7,538 ->
**6,909**. Lightweight tests 36/36; goldens 30/50, the same 20
documented mismatches. `b70_out1`.

Batch 56 (§0aj): gate **0/0/0**, HELD. Brace 0/11,107. Sweep crashes 0,
brace 0, into_block 13,505/2,978 -> **13,506/2,978**, sweep lines
2,012,814 -> 2,010,848. Tree lines 2,721,268 -> **2,719,896 (-1,372)**.
**946 of 11,107 files differ.** **`/*indirect*/` 13,808 -> 7,538
(-45.4%)** -- the largest move that marker has ever had; the resolved-
name buckets that fix 66 targets go `icall _Injected` 4,955 -> **0** and
`named Type.Method` 1,304 -> **26** (the 26 are Burst
`FunctionPointer<T>.Pointer`, correctly honest), while the untouched
buckets barely move (klass-slot 3,904 -> 3,901, bare-temp 2,209 ->
2,175, invoke_impl 626, obj-vtable-0 494). **read-before-def 118,917 ->
111,050 (-6.6%)**, across 31,012 -> 29,942 methods and 4,828 -> 4,776
files. icall cells resolving to a MethodDef 2,268 -> **2,285 of 2,285**
(fix 66b). Switch statements 758, case labels 10,295, raw table loads
25 -- all unchanged. Goldens 19 -> **20**, the new one
(VFXEventAttribute.HasInt) read and confirmed correct. New unit mirror
`work/icall_test.py` 10/10. `b66_out1`.

Batch 55 (§0ai): gate **0/0/0**, HELD. Brace 0/11,107. Sweep crashes 0,
brace 0, into_block 13,815/2,960 -> **13,505/2,978** (-310 sites), sweep
lines 2,012,429 -> 2,012,814. Tree lines 2,720,887 -> **2,721,268**
(+381). **89 of 11,107 files differ** -- parsers, tokenizers and state
machines. **Switch statements 721 -> 758 (+37), case labels 9,052 ->
10,295 (+1,243)** (the label jump is fix 65b printing one label per
OPERAND value instead of per jump-table slot; the statement count is
what tracks recovered dispatches). Surviving raw table loads **52 -> 25
(-52%)**, `/*indirect*/` 13,845 -> 13,808. read-before-def 118,938 ->
**118,917 (-21)**, flat. Longest consecutive case-label run 57 -> 64 (no
pathological expansion anywhere). Jump-table recognizer buckets `ok` 92
/ `short` 12 / `no_lea` 8 -> **`ok` 111 / `short` 1**, and that one is
JsonParser.Equals, a virtual tail-dispatch that is not a table.
**`no_lea` was never a real bucket** -- the census mirror's lea lookback
was stale (§0ai). Goldens 19, the same 19 by name. New unit mirror
`work/jumptable_test.py` 9/9. `b65_out1`.

Batch 54 (§0ah): gate **0/0/0**, held (batch 53 emptied the bad-file
set, so there was no legacy noise left to hide a regression in). Brace
0/11,107. Sweep crashes 0, brace 0, into_block 12,950/2,928 ->
**13,815/2,960**, sweep lines 1,996,071 -> 2,012,429. Tree lines
2,704,529 -> **2,720,887** (+16,358). **66 of 11,107 files differ** --
parsers, tokenizers and state machines with several switches per method.
**Switch statements 559 -> 721 (+162), case labels 6,528 -> 9,052
(+2,524), `/*indirect*/` 13,941 -> 13,845 (-96).** read-before-def
118,931 -> **118,938 (+7)**, essentially flat under +16,358 recovered
lines. Jump-table recognizer buckets `no_lea` 77 / `ok` 22 / `short` 12
-> **`ok` 92 / `short` 12 / `no_lea` 8**. Goldens 19, the same 19 by
name. `b64_out1`.

Batch 53 (§0ag): gate **0/0/0** -- the bad-file set is EMPTY for the
first time in this corpus's history (was the documented legacy-TMP pair
at 2/2,206/4). Brace 0/11,107. **Full-corpus sweep crashes 2 -> 0** (the
two cfg-too-large TMP caps are gone), into_block 12,502/2,926 ->
**12,950/2,928**, sweep lines 1,983,738 -> 1,996,071. Tree lines
2,702,326 -> **2,704,529**. Exactly **3 of 11,107 files differ** from
b62_out1, byte-identical otherwise. read-before-def 118,609 ->
**118,931** (+322, and the same +322 is measured over just those three
files, so nothing else moved -- it is the cost of 12,333 newly-recovered
body lines). Jump-table text residue barely moved: table-load sites 176
-> 174, files 109 -> 111. Goldens 19, the same 19 by name -- the batch
moved none of the 50. `b63_out1`.

Batch 52 (§0af): gate **2/2,206/4** -- bad-file SET the documented
legacy-TMP pair. The intermediate `b61_out1` gated 3 bad files while
total ERROR FELL, which is how fix 62 was found; that report is kept as
`work/ts_gate_b61_out1.txt`. Brace 0/11,107, bare `objN;` 0. Sweep
crashes 2/2 pre-existing, into_block 12,497/2,924 -> **12,502/2,926**,
sweep lines 1,980,111 -> 1,983,738, tree lines 2,698,694 ->
**2,702,326**. **`unknown` conditions 8,290 -> 4,022 (-51.5%)**,
ternaries 1,048 -> 578, all-`unknown` occurrences 23,409 -> 18,476;
`& 0xFF/*z*/` masks 18,035 -> 14,229 (-21.1%). read-before-def 118,445
-> 118,609 (+164): honest, a condition that printed one token now
prints its operands. Goldens 19, the same 19 by name -- the batch moved
none of the 50. `b62_out1`.

Batch 51 (§0ae): gate **2/2,211/4** -- bad-file SET unchanged (the
documented legacy-TMP pair; ts_gate lists every bad file, so that
2-row report IS the per-file diff). ERROR 2,097 -> 2,211, entirely
inside those two files and entirely cascade churn -- bucketed by row
text the families and their top-12 distribution are unchanged (495 ->
499 distinct texts in TextMeshProUGUI.cs), no new malformation family.
Brace 0/11,107, bare `objN;` 0. Full-corpus sweep crashes 2/2
pre-existing, into_block 12,484/2,923 -> **12,497/2,924** (no CFG-shape
change in this batch), sweep lines 1,975,457 -> 1,980,111, tree lines
2,694,051 -> **2,698,694** (+4,643). **read-before-def 124,715 ->
118,445 (-5.0%)**, across 34,065 -> 30,962 methods (-9.1%) and 4,882 ->
4,824 files; Unity.Mathematics' math.cs 4,020 -> 3,021 (-25%). Goldens
18 -> 19, the new one (int3x3.op_BitwiseOr) read against disassembly
and confirmed correct. `b59_out1`.

Batch 50 (§0ad): gate **2/2,097/4** -- bad-file SET unchanged (the
documented legacy-TMP pair), ERROR inside those two files 5,020 ->
2,097 (-58%), MISSING unchanged. Brace 0/11,107. Full-corpus sweep
crashes 2/2 pre-existing, **into_block 12,484/2,923 UNCHANGED** (no
fix touches CFG shape), sweep lines 1,976,884 -> **1,975,457**, tree
lines 2,695,492 -> **2,694,051** (-1,441). Bare `objN;` statements 0
(2,306 in the deleted first build -- see §0ad's regression trail).
**read-before-def 214,287 -> 124,715 (-41.8%)**, across 45,396 ->
34,065 methods and 5,616 -> 4,882 files: the largest movement this
metric has ever had (previous best batch 33's -11.1%). Provenance of
what remains, and the retired "unresolved phi inputs" premise, in
§0ad; residue lead is todo.md 5a.

Batch 49 (§0ac): gate **2/5,020/4** (bad-file set unchanged), brace
0/11,107, sweep into_block 15,416/3,956 -> **12,484/2,923** (-19.0%
sites / -26.1% methods), tree lines 2,626,137 -> **2,695,492**
(+69,355, the honest tail-duplication cost). `1a_dup5b_out1`.

Batch 48 (§0ab): gate **2/4,863/4** (the same two legacy-TMP files, 0
newly bad; the -1 ERROR sits entirely inside TextMeshPro.cs), brace
0/11,107, full-corpus sweep crashes 2/2 pre-existing, into_block
15,418/3,957 -> **15,416/3,956**, sweep lines 1,911,718 -> **1,907,528**,
tree lines 2,630,326 -> **2,626,137** (-4,189). `ref <local>` renders
28,267 -> **7,244** (the removed ones were arg-0-by-comma-position
artifacts, 8,238 of them ungrammatical); `&<local>` 23,930 -> 29,003
(the intended honesty cost -- see §0ab); pure copy lines 104,263 ->
**100,914**.

Batch 44 (§0x): gate **2/4,864/4, byte-identical to b42_out1/b43_out1**
(same two legacy-TMP files, 0 newly bad), brace 0/11,107, full-corpus
crash sweep 2/2 pre-existing. **13,224 `else if` sites corpus-wide (0
existed anywhere before this session)** -- the else-if/switch
flattener (`_elseif_flatten`, a pure boolean-identity rewrite of a
right-nested if/else compare chain, no CFG reasoning needed unlike
lead 1a on the same source shape) turns PickupNewObj's 6-level nested
`index != 5/3/2/11/58/4` pyramid, and every similarly-shaped
right-nested chain in the corpus, into a flat `else if` cascade.
Declines outright whenever an arm it would place next to the merge
point is wholly empty (a real, live-caught interaction with
`_render`'s own pre-existing empty-if collapse -- see §0x, two reverted
fix attempts before the safe one). Scoped Assembly-CSharp rebuild
(6,622 bodies) gated **0 bad / 0 ERROR / 0 MISSING**, 888 `else if`
sites. Goldens: 6/50 changed on top of lead 1a's own 5 (§0x), every
diff read, several genuine additional flattenings beyond the original
target. Full rebuild `b44_out1`: 11,107 files / 115,658 bodies / 0
failed, 741.6s. Tree lines 2,663,122 (b42_out1) -> 2,630,342 (net
-32,780 despite lead 1a's own +75,477 duplication cost landing in the
same window). `b43_out1` (lead 1a alone) is superseded and reaped.

Batch 43 (§0w): gate **2/4,864/4, byte-identical to b42_out1** (same
two legacy-TMP files, 0 newly bad), brace 0/11,107, full-corpus sweep
crashes 2/2 pre-existing, brace 0/116,178, **into_block (this batch's
own sweep_1a_audit.py mirror) 32,094/9,434 -> 15,419/3,958 (-52%
sites / -58% methods)** -- the tail-duplication fallback (funnel-
blocked shared-tail gotos duplicated into each goto site instead of
hoisted, gated on the same falls_to/lca_hoist_plan proofs the hoist
path already trusts, capped at 24 raw tail lines after a
`_singleton_cse` interaction was found) recovers over half of batch
42's own funnel-blocked residue as sound, honest code. Goldens: 5/50
changed, every diff read (§0w) -- clean goto-to-duplicate conversions,
some cleaned up further by downstream passes than a hoist ever could.
Full rebuild `b43_out1`: 11,107 files / 115,658 bodies / 0 failed,
679.5s. Residue (15,419 into_block sites) is the declined-by-gate
cases: the size cap, and whatever still fails the structural checks
entirely -- sized as the next leads in §0w/todo.md.

Batch 42 (§0v): bad-file set unchanged (the TMP pair; ERROR 4,863 ->
4,864 — +1 node inside TextMeshProUGUI's cap, the flat lift runs
`_structure` so the hoist shift moved one node; MISSING 4/4), brace
0, crashes 2/2 pre-existing, census at fixpoint (26 residual
CLASSIC+LCA-sound sites, `work/census_b42_v4.py` — blocked families:
funnel 4,330 / goto falls_to 8,181 / nested-label-in-tail 4,477 /
label-side 2,090 / loop-switch-seh 369). **THE HONEST COST: tree lines
2,587,645 -> 2,663,122 (+75,477) and sweep into_block 17,718/4,079 ->
32,094/9,434** — the ~14.4k un-done b41 hoists the funnel proved
unsound (two families disasm-proven, §0v); neither form compiles (the
hoisted form breaks definite assignment on the leak paths), the kept
goto is greppable. AC five-shape census stable where untouched
(census_b41.py): self-copies 0, forhead-dup 2 (1 adjacent), phantom
stores 0, flag ternary-consumer 7; AC goto fan-in>=2 634 -> 763 (the
un-hoisting). Goldens regen: 5 bodies, every diff read and judged
pre-build. The readability residue is sized as leads 1a/2 (todo.md).
**POSTSCRIPT: b42_out1 was PROMOTED to `final_out/` on 2026-08-22**
(byte-verified; the b37_out1-b42_out1 batch trees reaped at promotion
per the §6 rule, work-dir archaeology for reaped trees with them).

Batch 41 (§0u): bad-file set unchanged (the TMP pair) — same-tool gate
counts byte-identical across b40_out2/b41_out1 (2/4,863/4 by
`work/ts_gate.py`, which counts nested cascade nodes; §0t's "2/2/0"
was the parent-dir `treesitter_gate.py`'s top-level count on the same
trees — all-zero delta either way), brace 0, crashes 2/2 pre-existing,
sweep into_block 17,718/4,079 baseline-identical. Readability: **AC
self-copies 103 -> 0** (fix 49/49b, `_selfcopy_drop` after
`_copy_prop` — the copies are minted by copy-prop's substitution),
**for-head duplicate calls 28 -> 3** (fix 50/50b `_forhead_call_fold`,
honesty proven by disassembly: the native loops call once, before the
loop), tree lines 2,588,867 -> 2,587,645 (-1,222). Goldens regen: 1
body, the intended fold. Lead #2's ternary consumer sized at 7 AC
sites — declined; the goto triple (634 fan-in>=2 gotos) diagnosed
(§0u) and left as the top sized lead. `final_out/` still holds the
promoted b36_out2; b41_out1 (one level up) is the gated candidate.

Batch 40 (§0t): gate 2/4,868/4 -> **2/2/0** (same two TMP files,
gate_diff all-zero across both b40 builds; the ERROR/MISSING mass
inside the TMP pair collapsed to the L1-header artifact — documented
wobble, good direction), brace 0, crashes 2/2 pre-existing, sweep
into_block 17,718/4,079 unchanged. Readability: **singleton fetch
decls 1,370 -> 931 / inline spellings 299 -> 133** (fix 46, method-
scope), **`playerInput.actions`-class member-load walls fold** (fix
47 `_value_cse`; Update's 14-decl wall -> 1), **SetActive(0/1) 955 ->
140, 815 now false/true** (fix 48), **flagN decls 9,165 -> 5,629
tree-wide / 1,436 -> 386 in AC, still-inlinable adjacent pairs AC
193 -> 1** (fixes 45/45b: tail re-run + the double-negation head),
tree lines 2,605,297 -> 2,588,867 (-16,430). Goldens regenerated
post-gate: 11 bodies changed, every diff read (§0t). `final_out/`
still holds the promoted b36_out2; b40_out2 (one level up) is the
gated candidate.

Batch 39 (§0s): gate 2/7,312/0 -> **2/4,868/4** (same two TMP files,
gate_diff all-zero; the ERROR/MISSING moves are inside the TMP pair —
documented wobble, see §0s), brace 0, crashes 2/2 pre-existing.
Readability: **probe (`sub_1804c67b0`) renders 70 -> 0** (fix 43, the
__chkstk model; 392 extents / 1,094 sites covered, receiver `this`
recovered with ~50 named fields in Update alone), **flagN decls
20,502 -> 9,165 tree-wide / 3,357 -> 1,641 in AC** (`_flag_inline`,
fix 44; while-heads and multi-use flags kept by design), read-before-
def 208,043 -> 207,852, `((byte*)` 196,482 -> 195,842, `if ((` heads
19,082 -> 18,563 (`_cond_dewrap`, 44c), tree lines 2,622,156 ->
2,605,297 (-16,859). Goldens regenerated: 6 bodies, diffs read (§0s).
`final_out/` still holds the promoted b36_out2; b39_out1 (one level
up) is the gated candidate.

Batch 38 (§0r): gate 2/7,298/0 -> **2/7,312/0** (same two TMP files,
gate_diff all-zero, +14 ERROR inside them — documented wobble), brace
0, crashes 2/2 pre-existing. Readability: **read-before-def 211,643 ->
208,043 (-1.7% tree-wide; AC alone 8,846 -> 7,514, -15%)**, pure copy
lines 101,658 -> 97,952, AC bare-`else` 4,471 -> 3,185, static
`GameObject.SetActive(objN, ...)` 63 -> 0 in AC (receiver folding for
calls, fixes 40-40e), the if-null-return-else shape 1,054 -> 0
(`_redundant_else`, 41), the float-arg family recovered positionally
(42: `this.anim.speed = obj5;` -> `= 4.0f;`). dup_impure 19,418 ->
20,950 (+7.9% — MEASUREMENT artifact of fix 40's identical-text
renders, NOT duplicated calls; see §0r). Golden snapshot suite:
`PYTHONHASHSEED=0 pytest work/test_goldens.py` — 50 bodies, ~13s,
50/50. `final_out/` still holds the promoted b36_out2; b38_out1 (one
level up) is the gated candidate.

Batch 37 (§0q): gate 2/7,919/2 -> **2/7,298/0** (same two TMP files,
MISSING cleared, ERROR -621 inside them), brace 0, crashes 2/2
pre-existing. Readability: **duplicate impure calls 29,220 -> 19,418
(-33.5%) / distinct 19,257 -> 10,405 (-46%)**, read-before-def
212,018 -> 211,643 (flat), pure copy lines 98,928 -> 101,658 (+2.8%,
the traded live-bool `flagN = tN;` shape), `((byte*)` 196,223 ->
196,052, `->` 2,076, unsafe-wrapped 38,765, `bool flagN = this.X;`
property-hoist decls in AC 70 -> 430. `final_out/` still holds the
promoted b36_out2; b37_out1 (one level up) is the gated candidate.

Batch 36 (§0p): gate 2/7,924/2 -> **2/7,919/2** (same two TMP files,
gate_diff all-zero), brace 0, crashes 2/2 pre-existing. Readability:
**read-before-def 234,460 -> 212,018 (-9.6%)**, **pure copy lines
212,836 -> 98,928 (-53.5%)**, **duplicate impure calls 32,754 ->
29,220 (-10.8%)**, `((byte*)` lines 201,710 -> 196,223, `->` member
lines 127 -> 2,104, unsafe-wrapped methods 38,807 -> 38,754, `:
default` 9 / `?addr` 10 unchanged. The pointer-base census DISPROVED
the "202k recoverable" premise: 2,199 recoverable / 1,569 past-struct
/ 3,409 unresolvable-pointee of ~1.06M raw-deref sites.

Batch 35 (§0n): read-before-def 242,822 -> 234,460 (-3.4%),
byte*-deref-base 13,956 -> 6,368 (-54%), gate 2/8,125/2 -> **2/7,924/2**
(same two TMP files, 0 newly bad), brace 0, crashes 2/2 pre-existing,
854 fewer `unsafe`-wrapped methods, `.upVector`-style map pollution 0.
The sret RAX echo was closed WITHOUT the full stack-frame model -- one
binding plus a member-resolution normalization; what remains of
deref-base is non-sret raw-pointer patterns. Post-batch output-quality
census (readability surface, not gates): §0o -- 202k `((byte*)` lines,
171k pure copy lines, 32.7k duplicate impure calls, and the §0
payoff-ordered leads built off it.

Batches 31-33 (§0m): root-caused the `_mem_lvalue` family to 3-operand
IMUL mishandling (all three gate rows cleared), folded
op_Equality/op_Inequality to operators (7,254 -> 15 sites), and
recovered vtable slots for register-dispatch calls (4,454 `slot None`
-> 51; most resolved to named calls). Gate: b31 5/8,133/2 -> b32/33/34
**2/8,125/2** (only the two legacy-TMP files). read-before-def
273,016 -> 242,822 (-11.1%). getClass() 29,296 -> 15,710 (batch 30
took it from 49,442). Brace 0, crashes 2/2 pre-existing throughout.


Batch 29+30 (§0l) shipped CMOV ternary modeling (the §0k resume,
condition always parenthesized) and the value-type field-offset fix
(`getClass()` reads -40.7% tree-wide). Gate (ts_gate.py): b28_out1
13/8,148/4 -> b30_out1 (CMOV only) 4/8,132/2 -> b31_out1 (+vt fields)
5/8,133/2 (the +1 row is the documented `_mem_lvalue` base/index-swap
family newly exposed by name resolution, live-traced). Full-corpus
crash scan 2/2 pre-existing TMP caps both times; brace audit 0.

Batch 28 (§0j) fixed `decompiler.py`'s real CONDITIONAL_BRANCH handler --
the six flag-specific jump mnemonics (JS/JNS/JO/JNO/JP/JNP) it never maps
were spliced as a bare `?`, batch 27's fix #3 only reached the dead
`il2csharp.py` copy of this handler, not this one. Not CMOV-dependent
(11,980 raw sites full-corpus); a downstream `: default` synthesizer had
been silently completing the malformed shape into syntactically-valid-
but-wrong C#, so it barely showed in the gate despite the volume -- gate
still moved hugely once the two TextMeshPro parse-cascade files cleared:
13/8,148/4 -> **13/14/0** (same 13 filenames, every remaining row an
already-documented unrelated family -- see §0j). Full-corpus crash sweep
2/2 unchanged, brace audit 0 unbalanced. `b28_out1` is the new gated
candidate.
Batch 27 (§0i) root-caused `SequenceNode.cs`'s residual MISSING to a real
Lifter gap (CMOV silently dropped) and attempted a fix, but reverted the
CMOV modeling itself after it surfaced a chain of pre-existing landmines
faster than they could be closed out (full writeup + a detailed resume
plan in §0i); kept three independently-verified, CMOV-independent
robustness fixes found along the way. Gate 13/8,148/4 (was `b26_out1`'s
13/8,150/4, 0 newly bad, 0 cleared, ERROR wobble -2 in an already-
excluded artifact file), full-corpus crash sweep 2/2 unchanged, brace
audit 0 unbalanced -- gate-neutral by design, this batch's value is the
characterization + 3 kept fixes, not a gate delta.
Batch 26 (§0h) fixed a label-orphaning bug in `_render`'s typeof(X)
static-member-store elision (2 MISSING sites cleared) and re-measured/
bucketed read-before-def one level deeper (still open, see backlog #2 in
§3): gate 13/8,148/4 (was `b25_out1`'s 15/8,150/6, 0 newly bad, 2
cleared), full-corpus crash sweep 2/2 unchanged, brace audit 0 unbalanced.
Batch 25 (§0g) fixed a liveness-closure blind spot in
`_drop_dead_locals`/`_drop_dead_copies`: gate 15/8,150/6 (was
`b24_out1`'s 15/8,175/6, 0 newly bad, 0 cleared, ERROR -25), full-corpus
crash sweep 2/2 unchanged, brace audit 0 unbalanced. The rest of this
section (below) is the last full recount, taken at `b21_out5` (batch 21)
and only lightly superseded since -- see §0d-§0p for what each later
batch actually moved; none of batches 22-36 redid this full breakdown.

`b23c_out1` (batch 23, all of 23a-23c, see §0e) was that era's gated
build: 11,107 files, 115,658 bodies, 0 failed, gate 16 bad files /
15 ERROR / 2 MISSING, sweep byte-identical to `b22_out1` (brace 0,
dangling 0, empty_arg 0, follower 0, into_block 21,464/4,559,
crashes 2), read-before-def 307,013 (was 309,117 at `b21_out5`/
`b22_out1`), `dup_impure_scan.py` duplicate-call-render count 34,513
(was 47,341 pre-batch-23, -27.1% -- 23c alone, see §0e). The rest
of this section is the last full recount, taken at `b21_out5` (batch 21)
and not superseded by batch 22 (a parse-gate-only cheap-wins pass, see
§0d), batch 23 (three targeted semantic fixes, see §0e), or batch 24 (one
CFG-construction fix, see §0f) -- all three landed real but comparatively
small-to-moderate deltas on top of these numbers rather than moving them
wholesale (23c's -27.1% on `dup_impure_scan.py` is the exception, but
that metric isn't tracked in the breakdown below at all -- it's new this
batch); treat the breakdown below as directionally current, not
batch-24-exact. Batch 24's own gate delta (§0f): 16/8,146/6 (`b23c_out1`)
-> **15/8,175/6** (`b24_out1`), one file cleared (`TextContainer.cs`), 0
newly bad; full-corpus crash sweep 2/2 unchanged (both pre-existing TMP
caps).

`b21_out5` is the FINAL batch-21 build (all fixes 21a-21j). Intermediate
builds `b21_out1`-`b21_out4` are superseded and safe to reap.

- Tree-sitter gate: **19 bad files / 18 ERROR / 2 MISSING** (11,107
  files) -- unchanged from `b20_out1`; `gate_diff` shows 0 newly bad,
  0 cleared, 0 worse, 0 better. Batch 21 did not move this number
  because none of its fixes touched a site the gate can see (every
  fixed shape was already syntactically valid, just semantically
  wrong) -- see §0/§0c for the batch's real yardsticks. The 20
  remaining gate rows are unchanged from batch 20 (enumerated at the
  end of §0b). (One transient exception mid-batch: 21g's write-barrier
  dedup exposed a latent regex gap that put 3 files newly bad for one
  build; 21i fixed it same-session -- §0c.)
- Sweep gates (final full-corpus `sweep_audit.py` run, post 21a-j):
  brace 0, dangling 0, empty_arg 0, follower 0, crashes 2 (the two
  pre-existing TMP caps ONLY, unchanged). into_block **21,464 / 4,559**
  (was 21,326 / 4,538 in batch 20) -- a small (+138 sites / +21 methods,
  +0.6%) uptick, plausible fallout of 21c/21d changing instruction-
  elision boundaries next to branches in ~21 methods (unchanged across
  21a-e, 21a-i, and 21a-j -- 21f-21j did not move this further); not
  re-verified against `classify_into2.py`'s SOUND invariant this session
  (batch 20 and earlier all measured SOUND = 0 tree-wide) -- do that
  first if touching `_hoist_shared_tails` or the into_block family next.
- Batch-21 semantic census (not gate-visible, full corpus, see §0 for
  the complete list): **read-before-def 339,938 -> 309,117 temps (-9.1%
  total: -2.4% from 21a-21i, then -6.8% from 21j alone -- the single
  biggest fix of the batch)**; `Object.op_Equality`/`op_Inequality
  (typeof(Object), objN)` 2,417 -> 25 sites; raw `T objN = ...` 2,511 ->
  451 (82% cleared); unconverted `il2cpp_codegen_write_barrier(` calls
  5,797 -> 0 (100% cleared); invalid `?.member = v;` assignments 0 -> 0
  net (3 introduced by 21g, fixed by 21i within the same session);
  7,085 field declarations corrected (visibility/static/const, measured
  directly against the field table, batch 20's `b20_out1` had none of
  this fixed).
- Builds: 11,107 files, 115,658/115,658 bodies, **0 failed** in every
  batch-21 build (`b21_out1` 683.8s testing 21a/21b alone; `b21_out2`
  521.8s with 21a-e; `b21_out3` 498.5s with 21a-g (pre-21i, has the
  transient null-conditional regression); `b21_out4` 533.9s with 21a-i;
  `b21_out5` 558.0s with all 21a-j, the final gated build -- the perf
  fix in 21e shows up as a slightly faster full build across most of
  these, though that was incidental, not the point).

## 3. Standing backlogs — full trail (open items live in todo.md)

Open items #2 (condensed), #5 (open half), #6, the readability
[ ] items, and the batch-16 leftovers were extracted into
todo.md on 2026-08-22; their full historical trails and every
[x] item remain below.

### Correctness (external review 2026-08-19) — above all polish

- [x] #1 REAL PARSER GATE — shipped in batch 17. Driving the remaining
      families down is §2; batches 18-19 took ERROR 2,261 -> 118.
- [ ] #2 read-before-def audit: `work/read_before_def.py`
      (scan_stale.py shape). InventoryManager.cs alone: 722 temps read
      but never defined across 144 methods (`obj8 = obj9;` — obj9 never
      assigned anywhere). Phi inputs on entry edges the lifter never
      resolved; the largest single honesty leak. Bucket by which lifter
      path emitted the phi — expect 2-3 root causes covering most of it.
      **This is the top item now that the parse gate is under control.**
      **Re-measured full-corpus at `b25_out1` (2026-08-21, post-batch-25):
      273,700 temps (down from the 307,013 recorded at batch 23c --
      unmeasured since, so some of that drop is batch 24's CFG fix, some
      is batch 25's dead-cycle removal deleting statements that
      themselves read an undefined temp; not split out). Shape breakdown
      by first read: other 132,622 (48.5%), copy-rhs 80,651 (29.5%),
      call-arg 53,745 (19.6%), cond 5,126, member 1,439, index 117. The
      "bucket by lifter path" instruction above is now done one level
      deeper for the dominant "other" bucket (`work/rbd_subclassify.py`,
      new): byte*-deref-base 13,392 (`objA = ((byte*)objB + 0xN)[0];` --
      objB is the base pointer) / mem[]-store-value 10,375 (`mem[N] =
      objM;`) / plain-store-value 4,938 (a real field/array element
      assigned straight from an undefined temp, e.g. `this.anim.speed =
      obj5;` -- READS AS A CORRECTNESS BUG, not just clutter, since a
      real observable field genuinely gets garbage) / other-misc 103,917.
      **UPDATE 2026-08-21 (batch 35, §0n): the byte*-deref-base sret
      story is CLOSED, and it did NOT need the stack-frame model.**
      Re-split at b34: 13,956 sites, 11,738 at +0x0 alone; live raw-
      lift traces (ActorCOMTransform 0x1805135E0, AddRandomVelocity
      0x180513900 -- where the note below wrongly claimed the fold
      never fires -- and AudiencePath 0x1804FDEC0) showed the fold
      firing fine; the gap was that it never rebound RAX to the
      echoed sret pointer. One size-guarded binding + an &s_N member
      normalization in _field_expr took deref-base to 6,368 (-54%),
      read-before-def to 234,460. The ORIGINAL note's shape analysis
      ("fold never triggers because the lea isn't a tracked slot")
      was wrong for the current code -- keep for archaeology only:
      [the old root-cause narrative, superseded: a hidden-struct-return
      call (`Random.get_onUnitSphere(&buf)`, MSVC ABI also echoes the
      sret pointer back in RAX) -- the EXISTING sret-fold path
      (il2csharp.py ~4681, "`Foo(&s_N, ...)` -> `s_N = Foo(...)`") only
      fires when the call's first argument syntactically already reads
      as `&s_N` (a tracked stack slot)...]
      **NEW, bigger lead found 2026-08-21 (post-batch-27 session, still
      unfixed): 48,409 sites -- 36.5% of the ENTIRE "other" bucket,
      ~17.7% of the corpus-wide 273,700 total -- are indirect/virtual
      call arguments, not `other-misc` at all** (re-classifying: adding
      an `/*indirect*/`-or-`vtable slot`-in-line check to the existing
      other/other-misc split immediately absorbs most of what looked
      like a diffuse 43%-"no call shape" residue -- it WAS a call shape,
      just one the `.method(`/`sub_x`/`new` regex didn't recognize).
      Root cause (il2csharp.py `_call` ~4497): the arg list for EVERY
      call builds from all 4 `ARG_REGS` (RCX/RDX/R8/R9) PLUS all 4
      `ARG_XMM` (XMM0-3) that currently hold a live value, no matter
      what the call target is. For a NAMED method with real metadata,
      later code trims this to the declared arity (or, for an ambiguous
      shared body, to the max arity among candidates -- batch 21j, this
      file's own biggest historical read-before-def fix). For a bare
      `sub_XXXX` address with no name resolution, there's a narrower
      existing cap (`elif re.fullmatch(r'sub_[0-9a-f]+', name) and
      len(args) > 4: args = args[:4]`, il2csharp.py ~4897). **But
      `VIRT_CALL` (an unresolved vtable-slot call, receiver type
      unknown -- renders as `/*vtable slot N*/ recv(args)`) and a truly
      indirect register call (`ptr() /*indirect*/(args)`) get NEITHER
      treatment** -- the full, untrimmed 4+4 list ships as-is, so any
      XMM register still holding a value from an EARLIER, UNRELATED
      float computation earlier in the method rides along as a bogus
      extra "argument" (confirmed via random sampling across dozens of
      files/methods -- overwhelmingly consistent shape:
      `object obj2 = obj1() /*indirect*/(_unity_self, obj3, obj4, obj5,
      obj6, obj7, obj8, obj9);` with most of obj3-obj9 undefined).
      **Why this ISN'T a safe quick fix (unlike the `sub_X` cap):** a
      bare `sub_XXXX` is (per this codebase's own established reading)
      always an internal IL2CPP helper, safely <=4 GPR args by
      convention -- but `VIRT_CALL`/indirect calls dispatch to arbitrary
      MANAGED methods, which legitimately CAN take real float arguments
      via XMM0-3 (e.g. `SetPosition(float,float,float)`). Blindly
      capping to 4 the way `sub_X` does would sometimes truncate a REAL
      argument, trading an honest-but-noisy read-before-def site for a
      confidently wrong dropped argument -- exactly the class of mistake
      this project's own standing rule (`sub_x/*shared body*/`'s "don't
      guess" precedent, CLAUDE.md) exists to prevent. A sound fix needs
      real design: e.g., can an unresolved vtable slot's arity be
      recovered by scanning ALL known types' vtables for whatever method
      occupies that slot number and taking the max declared arity across
      them (extending batch 21j's exact trick to slot-indexed candidates
      instead of shared-body candidates)? Not yet investigated whether
      that index is buildable from existing metadata structures. Sizing
      this properly (is it worth the design work) before attempting is
      the next step, not a fix itself.
      **UPDATE 2026-08-21 (batch 33, §0m): shipped -- twice over.
      `Il2Cpp.slot_max_arity(slot)` builds the max-arity bound, and the
      bigger half was recovering the slot ITSELF for `call reg`
      dispatch (the vtmethod Expr's text already carried it), which
      resolves most such calls to named methods outright:
      vtable-slot lines 17,156 -> 1,409, `slot None` 4,454 -> 51,
      read-before-def 273,016 -> 242,822 (-11.1%) from batch 33 alone.**
      **UPDATE 2026-08-21 (batch 35, §0n): the truly-indirect family is
      now SIZED and split (14,227 `/*indirect*/` lines at b34): 5,570
      direct vtable-through-raw-arith (slot = (NNN-0x138)/16 recoverable
      from the callee text -- batch-33's trick applies, at minimum for
      a slot_max_arity trim) and 2,145 interface-offset dispatch lines
      (`(itfOffsets[i] << 4) + 0x138 + klass`, 555 files; naming needs
      the interface type from the adjacent search loop -- a CFG job;
      GameManager VA 0x1806DF770 IEnumerator.MoveNext is the ground
      truth). The sret half is CLOSED above.**
      **UPDATE 2026-08-21 (batch 36, §0p): 234,460 -> 212,018 (-9.6%)
      from three shipped pieces -- `_copy_prop` deleting dead copy
      statements (the copy-rhs bucket), `_bind`'s cross-block render-
      site rewrite collapsing duplicate impure calls, and 36a's
      pointer-member resolution (`obj10->Offset` renders). The
      indirect/virtual-call-arg half of the old 48,409-site note got
      its trim (38b/38c, `slot_max_arity` on constant-slot klass-walk
      dispatch) but measured MARGINAL -- slot max-arity bounds are
      loose tree-wide (mx=13 at slot 9), so naming the calls (which
      deletes the arg-spray question entirely) is the real item, §0
      lead #2.**
      **UPDATE 2026-08-22 (batch 38, §0r): 211,643 -> 208,043 tree-wide
      (-1.7%; AC alone -15%) from fix 42 — the plain-store-value
      sub-bucket's ROOT CAUSE was the positional-float-arg mechanism
      (`this.anim.speed = obj5;` with obj5 a stale GPR unknown; the real
      4.0f sat in XMM1 past the arity trim; Win64 assigns register
      index by PARAMETER POSITION). The float family mostly lives in
      the call-arg bucket, which is why the tree-wide delta is smaller
      than AC's. Remaining buckets at b38: other-misc 100,627 /
      mem[]-store 10,393 / byte*-deref-base 6,784 / plain-store 5,395.
      dup_impure's +7.9% read at b38 is a scanner-visibility artifact
      (identical-text renders of DISTINCT instructions), not new
      duplicates — re-bucket before attacking (§0r).**
- [x] #3 transitive dead-copy elimination: `obj14 = obj15; ... obj8 =
      obj14;` chains where every link is read but the chain is dead.
      Copy-prop `a = b` forward when `b` isn't reassigned in the live
      range, re-run liveness to fixpoint, then dead-store. Deletes most
      of the objN spam the type-inference items blame on phis.
      **UPDATE 2026-08-21 (§0o, b35_out2): sized -- 171,199 pure
      `objN = objM;` lines (3,717 files) + 2,143 `objN = this;` (611
      files); the try/finally phi-copy variant is ground-truthed in
      BabyDoll.Start (VA 0x18060C2B0). §0 lead #2.**
      **UPDATE 2026-08-21 (batch 36, §0p): SHIPPED as decompiler
      `_copy_prop` (forward substitution + backward last-def-dead
      sweep, 20-case unit suite `work/cp_test.py`). Tree: pure copy
      lines 212,836 -> 98,928 (-53.5%). The remaining ~99k are
      cross-arm phi copies (def does not dominate uses), loop-carried
      copies, and address-taken sources -- different mechanisms,
      §0 lead #3. Dominance-aware substitution or upstream phi
      coalescing would be the next angle; size first. STATUS: the
      mechanism THIS item prescribed is fixed; the remaining copies
      are new shapes -- do not reopen THIS item for them.**
- [x] #4 whole-method impure-expression dedup: `_bind` use-count
      binding is per-block; one call crossing arms renders 2-3 times.
      A duplicate impure text is ALWAYS wrong, never taste. Scan first
      (`dup_impure_scan.py`, scan_stale.py shape) for a number to drive
      against; extend the census to whole-method scope for
      call-containing expression objects.
      **UPDATE 2026-08-21 (§0o, b35_out2): 34,513 (b23c) -> 32,754
      redundant calls / 22,116 distinct exprs / 11,789 methods / 2,886
      files -- barely moved since 23c's -27%. Two instances in one
      small method (BabyDoll.Rpc_ChangeHittableHealth: Allocate x2,
      HasAnyActiveConnections x2 + dead flag1). §0 lead #3.**
      **UPDATE 2026-08-21 (batch 36, §0p): the Allocate-shaped half
      ROOT-CAUSED AND FIXED -- `_bind` rewrote only the declaration's
      own block, so a use of the same Expr object that rendered in a
      later block kept the full text. `_note_use` now records render
      sites (`Expr._sites`) and `_bind` rewrites them cross-block,
      per object, only in blocks reachable from the declaration.
      Tree: 32,754 -> 29,220 (-10.8%). The SURVIVING shape is the
      flags-cond twin (`if (Call()) ... flag1 = Call();`): flags state
      rematerializes per block entry as concatenated text in a fresh
      Expr (`_analyze`'s `'%s%s' % ft`), so the call object never
      reaches use #2 -- fix = carry expr objects through end_state,
      §0 lead #1 (~2,017 call-bearing cond lines in AC alone).
      STATUS: the mechanism THIS item diagnosed (`_bind` per-block
      use-count binding) is fixed; the remaining duplicates are the
      separately-diagnosed flags-state mechanism, tracked as §0
      lead #1 -- do not reopen THIS item for that; it is a new shape.
      **UPDATE 2026-08-22 (batch 37, §0q): the flags-cond twin is
      FIXED, and the diagnosis quoted above was WRONG -- no
      rematerialization is involved; the `'%s%s' % ft` text-carry is
      vestigial and never fed a jcc. The real mechanism was three
      counting defects (exec_block never advancing `_cur_ip` past the
      flag-setter, cmp/test operand reads counting at the setter while
      consumers counted the render, and `_build_phi_copies` rendering
      end_state values as uncounted text). Tree: 29,220 -> 19,418
      redundant calls (-33.5%) / 19,257 -> 10,405 distinct (-46%) --
      the single biggest duplicate-call move since 23c. What remains
      (19,418) is OTHER shapes; re-bucket with dup_impure_scan before
      attacking (the old sub-classification is two batches stale).**
- [x] #5 cheap wins with real metadata behind them: bool params
      `SetBool("On", 0)` -> `false` (126 sites in one file; the
      System.Boolean is already in the signature model); enum params ->
      member names; instance methods rendered static
      (`GameObject.SetActive(obj22[num2], 0)` — receiver folding
      machinery exists for accessors, extend it).
      `Object.op_Equality(typeof(Object), obj8)` -> `obj8 == null`: root-
      caused and mostly fixed by batch 21 (21c/21d, §0c) — it was NOT a
      usage-slot misresolve as guessed here, it was a class-init-guard
      elision peephole swallowing real code past its own branch target;
      2,417 -> 25 raw sites. The literal-argument-should-render-`null`
      and `op_Equality`/`op_Inequality`-should-fold-to-`==`/`!=` cosmetic
      half of this item is still open (now genuinely cheap: the calls'
      arguments are correct now, just need the literal/operator fold) —
      keep this item for that half, scoped down from the original guess.
      **UPDATE 2026-08-21: that cosmetic half is DONE (batch 32, §0m):
      `_objop_fold` in `_final_text`, 7,254 -> 15 sites (the 15 are in
      the two legacy-TMP files that bypass `_final_text`). The bool/
      enum-literal and instance-method-rendered-static halves above
      remain open.**
      **UPDATE 2026-08-21 (§0o, b35_out2): live ground truth for the
      remaining halves, all in BabyDoll.cs: `this.InvokeRpc = 0;`
      (bool-as-int), `this._runner.Stage != 4` (enum-as-int), plus
      531 generic-T leaks (`Enumerator<T> obj12`) tree-wide. §0
      lead #5.**
      **UPDATE 2026-08-21 (batch 36, §0p): bool/enum halves SHIPPED --
      `Il2Cpp.enum_members` reads the already-parsed fieldDefaultValues
      blob (value__ detection, all widths), `_fimm` renders
      true/false + Type.Member for typed stores, the branch render
      folds ==/!= against enum members (`Stage != 4` -> `!=
      SimulationStages.Forward`). Generic-T leaks and `T* objN`
      declarations deliberately left (unresolvable-T shapes, §0c).**
      **UPDATE 2026-08-22 (batch 38, §0r): the LAST open half —
      instance methods rendered static — SHIPPED as fixes 40-40e
      (`_recv_shaped` any-receiver folding on `_call` + both tail-jmp
      handlers + postfix-`[]` no-paren set). Item CLOSED.**

*(open item #6, the readability [ ] items, and the batch-16
leftovers were moved to todo.md verbatim.)*

- [x] #7 **backing-field DECLARATIONS still emitted next to the property
      they back** — was fixed sometime between batch 18 and batch 20
      (undocumented at the time; `emit_type`'s `bk`/`_BKF`/`bk_offs`
      skip-and-carry-offset mechanism was already in place when batch 21
      started reading this code). Reconfirmed 2026-08-20: 0 backing-field
      declaration lines in `b20_out1`'s `Assembly-CSharp` (`grep -rn
      "_k__BackingField;" | grep -v '// static\|// 0x'`). Do not reopen;
      if a similar-looking line resurfaces it is a new bug, not this one.
- [x] #8 **field-offset ordering in type headers** — was a static/
      instance MISCLASSIFICATION, not a sort-order bug (the "check
      before assuming which" call was right to hedge; instance/leak was
      the wrong guess). `CurrentDayManager.OneSecondWait` at offset 0x10
      is a genuine instance field sitting exactly at the `offset < 0x10`
      heuristic's threshold; the emitter never read the real
      FieldAttributes.Static bit. Fixed by batch 21's 21a (see §0c);
      4,793 static-as-instance and 2,292 instance-as-static
      misclassifications corrected tree-wide, confirmed against the
      field table directly (`work/probe_fattrs2.py`), not just this one
      case.
- [x] #9 **missing parentheses when an expression text is substituted
      into an address template** — was fixed sometime between batch 19
      and batch 20 (undocumented at the time; `_term_up()` and its two
      `_mem_lvalue`/`_mk` call sites, plus a third at the tail-call
      instance-address render, were already in place when batch 21
      started reading this code — `work/patch_round20.py` and
      `patch_round20e.py` in the sibling scratch dir confirm it landed
      in batch 20). Reconfirmed 2026-08-20 by reading the current
      source and unit mirror (`work/termup_test.py`). Do not reopen for
      THIS shape; a different unparenthesized-substitution site would be
      a new instance of the audit this item asked for, not a reopening.
- [x] #10 **pointer-typed-base member resolution** (NEW 2026-08-21,
      §0o; §0 lead #1; CLOSED same day by batch 36, §0p): `_td_of`
      (il2csharp.py ~3224) unwraps class/valuetype (0x11/0x12) and
      generic (0x15) type tuples but NOT PTR (0x0f) / BYREF (0x10), so
      a base whose type IS known -- `SimulationMessage* obj10` from
      `SimulationMessage.Allocate(...)`'s typed return, ground-truthed
      in BabyDoll.Rpc_ChangeHittableHealth -- still rendered
      `((byte*)obj10 + 0x24)[0] = real1;` instead of a field store.
      The SIZE FIRST census (work/size_ptrbase.py) measured the
      recoverable slice at only 2,199 of ~1.06M raw-deref sites
      (1,569 past-struct payload writes stay raw correctly, 3,409
      unresolvable pointees, the rest untyped) -- the ~202k-line
      ceiling was never mostly typed bases. Fix landed at
      `_field_expr`'s member-resolution site as prescribed (pointee
      unwrap, unboxed disp+0x10 for valuetype pointees, `->` render,
      plus `->`-aware gates in the three `'.' in fe.text` consumers
      and `_has_arrow` for the unsafe wrapper). `obj10->Offset = 96;`
      is the ground-truth render; past-struct payload writes
      (`+0x1c`/`+0x24` into the message data) keep the honest raw
      deref. Do not reopen; a NEW untyped-base shape would be a
      different bug.

### Readability (2026-08-18 review, triaged — [x] items are NOT bugs, do not reopen)

- [x] using directives; property accessors as methods (`=> expr;`
      remainder is low value); `var` (deliberate — README documents
      tracked-type locals); backing fields (batch 16 `_member_fold`);
      re-indent by brace depth (batch 18 `reindent()`).
## 8. History (compressed — durable details live in CLAUDE.md/README.md)

- Batch 36 (2026-08-21, CLOSED): five fixes, all five §0 leads of the
  batch-35 handoff -- full writeup §0p. 36a-c: pointer-typed-base
  member resolution at `_field_expr` (pointee unwrap, `->` render,
  past-struct payload writes honestly raw; the SIZE FIRST census
  measured the recoverable slice at only 2,199 sites -- the 202k
  premise was wrong, shipped anyway); 37: `_copy_prop` (forward
  substitution + backward last-def-dead sweep, 3 pass-bugs caught by
  its own 20-case unit suite; pure copy lines -53.5% tree-wide); 38:
  `_bind` render-site cross-block rewrite (backlog #4's "per-block
  binding" root cause; duplicate impure calls -10.8%; the flags-cond
  twin root-caused to flags STATE rematerialization -- deferred with
  a live trace); 38b/38c: indirect vtable-dispatch arity trim
  (measured marginal -- slot_max_arity bounds are loose; naming is
  the real fix); 39: bool/enum literal folds off the parsed
  fieldDefaultValues blob. Validated at the full bar (scoped scans
  after every fix, full crash sweep 2/2 baseline, two full rebuilds,
  gate 2/7,919/2 with gate_diff all-zero, brace 0). b36_out2 is the
  gated candidate; promotion is a human call.

- Batch 35 (2026-08-21, CLOSED): three fixes, one root cause + two
  found in its slipstream -- full writeup §0n. 35a: `_call`'s sret
  fold emitted `s_N = Foo(...)` and returned WITHOUT rebinding RAX,
  though the Win64 sret ABI echoes the buffer pointer in RAX and MSVC
  callers read the result through it -- every post-call member read
  (`movsd xmm1,[rax]`) dereferenced a fresh vN unknown (the
  `((byte*)objN + 0x0)[0]` read-before-def family, §3 #2's
  "blocked"-flagged item; it was never actually blocked). Fixed with
  an `&s_N` RAX binding plus an `&s_N`-base member normalization in
  `_field_expr` (loads and stores both route through it). 35b:
  `field_offset_map`/`instance_field_chain` included STATIC fields
  whose blob offsets collide with instance offsets (Vector3.z@0x18
  silently overwritten by static upVector@0x18); filtered via
  `field_attrs`. 35c (found by the b35_out1 rebuild's own artifact
  census): structs <= 8 bytes return IN RAX by value -- size-guard the
  binding (field at boxed offset >= 0x18), else it invents pointers
  (7 `if (&s_890 != 256)` sites, caught and killed same session).
  Validated at the full bar (live disasm traces on 3 methods incl. 2
  documented VAs, crash sweeps before AND after the guard, two full
  rebuilds). b35_out2: gate 2/7,924/2 (0 newly bad), brace 0, rbd
  242,822 -> 234,460, deref-base 13,956 -> 6,368, 854 fewer unsafe
  wrappers. Also sized the next lead: 14,227 `/*indirect*/` lines =
  5,570 raw-arith vtable (slot recoverable from text) + 2,145
  interface-offset dispatch (GameManager 0x1806DF770 ground truth).

- Batch 24 (2026-08-21, CLOSED): one fix, a major CFG-construction
  correctness bug in MSVC jump-table `switch` reconstruction, found
  live-tracing `ComputedStyle.ApplyFromComputedStyle` off this file's own
  #1 lead -- full writeup §0f. Three compounding bugs in `decompiler.py`:
  (1) `_jump_table`'s entries loop had no real bound beyond the method's
  own address range, so a second, unrelated switch's table laid out right
  after the first in `.rdata` got silently swallowed into the first
  table's entries (76 decoded for a table whose real, `cmp idxreg,N`-
  enforced bound was 16); fixed by finding that native bounds check and
  capping there. (2) jump-table targets were never block leaders --
  `_make_blocks` only learns leaders from direct Jcc/JMP targets, jump
  tables are decoded LATER in `_prewire_switches` after blocks already
  exist, so an independently-unreached target was silently dropped and
  its case's code glued onto a neighboring block (THIS is what made a
  16-case switch render as one `case 2:` block running all 16 cases'
  logic unconditionally); fixed with a new `_scan_jump_table_leaders`
  pre-pass before `_make_blocks`. (3) once (2) made block splitting
  finer, `_jump_table`'s own backward scans for the table-base
  `lea`/index `mov`/(1)'s `cmp` went block-local and blind (a real block
  was found with only 5 trailing instructions, too few to find anything);
  fixed by redirecting the whole function onto the method's flat,
  unsplit instruction stream when available. A fourth, independent bug in
  `_prune_nonreturning` (an external tail-jmp -- same shape as batch
  21g's write-barrier idiom -- wasn't in the "reaches a return" seed set,
  so it silently deleted an entire switch case) was found chasing a
  still-missing case after fixes 1-3 and fixed the same session. Verified
  live against raw disassembly (all 16 cases of both dispatches now match
  field-for-field); full-corpus crash sweep 116,178 methods/460.1s/2
  crashes (byte-identical baseline, the two pre-existing TMP caps); full
  rebuild `b24_out1` gate **15/8,175/6** vs `b23c_out1`'s 16/8,146/6 (one
  file cleared -- `TextContainer.cs`'s own "malformed switch-to-if
  reconstruction" row from batch 22 -- 0 newly bad); brace audit 0
  unbalanced. One dead end recorded (not fixed, not a regression): a
  THIRD/FOURTH cascading dispatch in the same method needs a real CFG-
  predecessor-aware register reaching-definition trace, not a flat scan
  -- genuinely harder, left as a next-session lead.
- Batch 23 (2026-08-20/21, same day as batches 20-22; CLOSED): three
  fixes found live-tracing real output at explicit prompts, not off a
  gate row -- full writeup §0e. 23a: `Lifter._insn` (il2csharp.py) never
  handled `MOVQ`/`PSRLDQ` for a register destination, so a stale
  class-init-guard value survived past the point real code (a
  `movups+psrldq+movq` struct-field extraction, e.g. enumerating a
  `Dictionary`) should have overwritten it -- this, not a second
  guard-elision variant as batch 21's own notes guessed, was the real
  cause of the 25 residual `Object.op_Equality/op_Inequality(typeof(
  Object), ...)` gate rows; fixed with an opaque reg-copy for `MOVQ`/
  `MOVD` and an honest register-invalidation for `PSRLDQ` (25 -> 0
  sites). 23b: new `_singleton_cse` pass (decompiler.py) collapses
  redundant same-method re-fetches of the pure static read
  `typeof(X).Instance` -- found reading `InventoryManager.cs` at a user's
  request; corpus census 1,312 redundant sites -> 1,136 (the "flat
  catalog" shape, e.g. `InventoryManager.AssignTemplates`, collapses
  fully: 63 -> 1 in one method). 23c -- this batch's biggest win:
  `_drop_dead_copies` blanket-refused to ever drop a phi copy with an
  impure (call-shaped) RHS, even unread, on the theory it might be the
  only record of a real side effect. Chasing WHY `_singleton_cse`
  couldn't touch `ControllerLayoutMenu.cs`/`NuisanceCustomer.cs` (flagged
  as a "branchier shape, maybe a CFG/phi bug" when 23b landed) led to
  `probe_cfg.py` (new, dumps block/phi structure) proving the phi merges
  themselves were already CORRECT per-edge -- the real bug was that ~25
  individually-correct-but-unread phi copies, all feeding one shared
  `raise_NullReferenceException()` block that reads none of them, could
  never be dropped because their RHS looked like a call. Fixed with the
  same exact-text-twin proof `_wb_finish`/`_sfblob_dedupe` already use:
  an unread impure copy drops once its text is proven to survive as a
  real statement elsewhere (which it always does for a phi copy, by
  construction -- its value was always already computed by an earlier
  statement, never freshly invoked). `dup_impure_scan.py` (backlog §3
  #4's own scanner, previously never moved by any batch): duplicate
  impure call renders 47,341 -> 34,513 (-27.1%). Gate unchanged (16/15/2,
  0/0/0/0 vs `b22_out1` AND vs the 23a+23b-only intermediate build --
  none of the three fixes are gate-visible); sweep byte-identical to
  `b22_out1` on every axis, checked after each fix landed; read-before-def
  309,117 -> 307,013 (-0.68%, modest -- none of the three fixes targeted
  undefined-temp reads). `probe_store.py`/`probe_disasm.py` (reaped after
  batch 21/22) recreated this session; new `probe_cse.py`, `probe_cfg.py`.
- Batch 22 (2026-08-20, cheap-wins pass over the `b21_out5` gate rows;
  CLOSED): three small `decompiler.py` fixes picked off the smallest/
  cheapest remaining gate rows rather than a new backlog item -- full
  writeup §0d. cheapwin1: `_null_ternary_sugar` dropped a dangling `)`
  when the whole ternary (not just the condition) was parenthesized, and
  didn't guard against folding a literal that can never be null.
  cheapwin2/3: `_fix_select`'s two `:` checks were byte-substring tests,
  not string-literal-aware, so a `:` inside a string-literal argument
  blocked the real select-mark fold on the same line (two independent
  instances of this file's own §4 rule to reuse `_in_string`); a bonus
  fourth site cleared as the same bug. Gate 19/18/2 -> 16/15/2 (4
  cleared, 0 newly bad, 0 worse); sweep byte-identical to `b21_out5`.
  `final_out/` (stale since batch 18) promoted to `b22_out1` this
  session -- the batch-18 tree archived at `final_out_prev18/`.
- Batch 21 (2026-08-20, same day as batch 20; CLOSED): semantic-
  correctness batch, not a parse-gate batch (final gate unchanged
  19/18/2, 0/0/0/0 vs b20_out1). 21a/21b: field declarations read real
  CLI FieldAttributes/TypeAttributes instead of offset/name-shape
  heuristics (7,085 fields corrected: static/instance, const, redundant
  [SerializeField], and a wrong shared visibility table for nested
  types). 21c/21d: root-caused and fixed the `Object.op_Equality/
  op_Inequality(typeof(Object), objN)` family (2,417 -> 25 sites) to a
  class-init-guard-elision peephole bounded by a fixed instruction count
  instead of its own branch target, duplicated in both `il2csharp.py`
  and `decompiler.py` (the latter is the real pipeline). 21e: fixed an
  O(n)-per-candidate lookup the 21c/21d fix introduced. 21f/21g (from a
  user bug report, not the gate): shared-generic-body calls
  (`GetComponent<T>()` and friends) lose their type argument at the call
  site and the DECLARATION locked onto the resulting useless bare `T`
  via a `setdefault` race a later, better hint (from the store target)
  could never win -- fixed for both the ordinary write-barrier store
  path and its independently-duplicated tail-jmp sibling, THE THIRD TIME
  this batch found the same "duplicated per-instruction dispatch between
  il2csharp.py's dead Lifter.lift() and decompiler.py's real pipeline"
  shape (raw `T objN =` 2,511 -> 451, unconverted
  `il2cpp_codegen_write_barrier(` 5,797 -> 0, full corpus). 21h: static
  field reads (`typeof(X).Instance` and every other static field) always
  carried `.ty = None`, so a further deref off the result could never
  fold to a real member name -- found from a user question about
  `StoreManager.Instance.someField`-shaped output; fixed by giving
  `static_off_names` the field-type half `instance_field_chain` already
  had, with one missed caller (`decompiler.py`'s independent text-level
  `_fold_static_addrs`/`_static_field_name`) caught immediately by the
  next scoped gate. 21i: fixed a latent `_null_conditional` LHS-guard
  regex gap (missing `<>` in its character class, so a still-mangled
  `<Name>k__BackingField` assignment target wasn't recognized as an
  assignment) that 21g's write-barrier dedup exposed by shrinking a
  2-statement if-block to 1 -- 0 sites pre-session, 3 introduced by 21g,
  0 after 21i, all within this session (caught by always running
  `gate_diff`, never just the summary line, per this file's own §4 rule).
  **21j (from a second user report, picking the top backlog item): the
  batch's biggest single win.** Calls to a genuinely ambiguous shared
  body (`sub_x/*shared body, N candidates*/`) never got their argument
  list trimmed -- trimming requires a resolved `mi`, which by definition
  doesn't exist for the honestly-ambiguous case -- so the render kept
  all 4 GPR argument slots PLUS whatever stale XMM0-3 values survived
  from earlier in the method as bogus extra "arguments", each fed by a
  `_bind`/phi copy that was never really an argument and often never
  really defined (exactly the `obj1 = obj2; obj3 = obj4; ...` copy-chain
  spam behind "Update() is still a mess"). Fixed by trimming to the
  LARGEST declared arity among all N candidates -- sound because every
  candidate names a call into the literal same compiled machine code,
  so they consume the same argument registers regardless of which
  identity is true; a provable bound, same category as 21c/21d's fix,
  not a guess. read-before-def 331,824 -> 309,117 (-6.8% of the batch's
  ENTIRE original baseline, from this one fix alone) -- more than
  double the combined effect of 21a-21i. Batch total: read-before-def
  339,938 -> 309,117 (-9.1%, still one mechanism among several -- the
  copy-rhs bucket remains the top backlog item, just smaller now).
  Full writeup with live-trace methodology: §0c. Two dead-end
  investigations recorded there too (RenderGraphPass base/index swap,
  ActorSpawner single-candidate shared-body misresolve) so they aren't
  re-walked without new tooling. One near-miss recorded in §0: a
  backup-restore mistake briefly lost 21f/21g entirely; recovered from
  conversation context, full-file snapshots kept as the safety net going
  forward. Also established this session: `--only <assembly>` +
  `sweep_ac_only.py` (new) as the validated fast iteration loop, used
  for all but five of this ten-fix batch's full rebuilds.
- Batch 18 (2026-08-19): tree-sitter parse-gate batch, gate
  377/635/439 -> 302/427/210. Shipped batch 17's NUL/control escaping,
  `_mk` cap, `?`-classifier + `_strip_dangling_default`, name
  sanitizing (`@`/`|`/leading-dot), `is objN` fold, `_fix_select`
  string-awareness; then batch 18's call-target sanitize for
  `kind == 'generic'`, MANGLED_IDENT_RX trailing `(?:\|[\w`]+)*`,
  dropped-call-paren fix in `_fold_static_addrs`, `::` sanitize in
  `_icall_annotation`, and NEW `reindent()` + `_brace_scan()` in the
  file writer. Two real bugs found by the rebuild: the
  `_norm_twin`/`hexlit` crash (`int(x, 0)` raises on leading-zero
  decimals — silently downgraded 4 methods to the legacy flat lift, 2
  of which shipped `/* lift failed */` bodies) and the `? & 0xFF`
  classifier gap. Reindent A/B over `b18_noreind`: 4,022 identical,
  7,155 indent-only, 23 content-diff (all the classifier lines).
- Batch 16 (2026-08-18): rt_names wired into `_call_name`; thunk
  noreturn-forwarder following; `raise_<Exception>` naming (~7,151
  sites, arity 0); class-init inline twin named lazily; class-init
  guard widening + `_CLSINIT_ASSIGN_RX`; `_member_fold` (backing
  fields 3,526 sites; named static addresses). Rebuild 11,107 files /
  115,658 bodies / 0 failed.
- Batches 12-15: into_block 56,657 -> 21,322 (`_hoist_shared_tails`,
  classify_into2.py SOUND = 0); `try { } else { }` 389 -> 0 sites;
  literal-aware brace counting (the 24 "imbalanced" methods were
  literal false positives); the silent `_NULLTERN_RX` crash class
  (~0.51% of methods) found by the fallback sweep — re-run that sweep
  after any post-processing change.
