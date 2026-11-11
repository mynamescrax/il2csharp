## 0aa. Batch 47 (2026-08-23, todo lead #7: `_hint_arg_types` ordinal-
per-class bug -- SHIPPED, CLOSED)

Picked up lead #7 (`_hint_arg_types` has the same ordinal-per-class
register-walk bug fix 42b corrected in `_positional_args`). Confirmed
by reading both functions side by side: `_positional_args` walks
`pos = base + pi` (one shared Win64 positional counter over
`enumerate(method_params)`), but `_hint_arg_types` still tracked `xi`
(advanced only on float params) and `ri` (advanced only on non-float
params) as two INDEPENDENT ordinal counters. Win64 assigns the
register index by PARAMETER POSITION, not per-class ordinal, so any
signature with a "class switch" after position 0 (float then int, or
vice versa) reads the wrong GPR/XMM slot for every param past the
switch. `work/probe_b47_hintpos.py` found 2,288 such interleaved-
signature methods corpus-wide. Fix 53: replaced the two independent
counters with the same `pos = base + pi` walk `_positional_args` uses,
routing through XMM lookup or `arg_exprs[pos]` by class exactly as
before -- only the slot arithmetic changed. Hint-only function (only
ever populates `_type_hints`, never rewrites a printed arg itself), so
this was flagged low-risk in the lead's own text ("cheap to align if
touching that code anyway").

Golden suite: 7/50 mismatches both before and after (confirmed via a
clean revert/reapply A/B under `PYTHONHASHSEED=0` -- byte-identical
failure set both times), matching the already-documented batch-44/45
drift (goldens.json is stale as of batch 46, unrelated to this fix).

Full-corpus sweep A/B (`work/sweep_1a_audit.py`, source reverted/
reapplied for a clean comparison):
```
before (pre-batch-47): lines=1,911,725 crashes=2 (TMP caps, pre-existing)
                        brace_unbalanced=0 into_block=15,418/3,957
after  (batch-47):      lines=1,911,718 crashes=2 (same)
                        brace_unbalanced=0 into_block=15,418/3,957
```
Small and clean: -7 lines (better type hints unlock a downstream fold
at a handful of interleaved-signature call sites), 0 new crashes, 0
into_block/brace change (expected -- a hint fix, not a CFG-shape
change).

Full rebuild `b47_out1`: 11,107 files / 115,658 bodies / 0 failed,
631.2s. Gate: **2/4,864/4, byte-identical to the b42_out1 through
b46_out1 baseline** (the same two legacy-TMP files). Brace audit:
0/11,107 unbalanced. Real-build tree line count 2,630,333 (b46_out1)
-> 2,630,326 (b47_out1), delta -7, matching the in-memory sweep
exactly. Patches: `work/patch_b47_hintposfix.py` (fix 53), binary CRLF
per CLAUDE.md; build `work/run_build_b47.py` + `work/build_b47.log`;
gate report `work/ts_gate_b47_out1.txt`; sweep `work/sweep_1a_audit.py`
(existing tool, re-run); sizing probe `work/probe_b47_hintpos.py`.

`b47_out1` is a verified, gate-clean, crash-clean, brace-clean
candidate (supersedes b46_out1 -- strict superset, same source tree
plus fix 53); promotion over `final_out/` (= b42_out1) is a human call
per the standing rule (§0/§6). `b46_out1`/`b45_out1` were left on disk
rather than reaped, per the same standing rule.

## 0z. Batch 46 (2026-08-22, Correctness backlog: the dead
_collapse_arm check -- SHIPPED, CLOSED)

Picked up the standing Correctness backlog item (batch-42 finding,
todo.md): `_collapse_arm`'s emptiness check tested `range(arm + 1,
ac)` against the PRE-drop `lines` -- the label line `li` always lives
in that span and is never blank (`"L_xxx:"`), so `all(not
lines[k].strip() ...)` was false at essentially every call site and
the collapse never fired. `_hoist_shared_tails` left an emptied label
arm as a valid-but-ugly `if (cond) {} else { body }` shape instead of
folding it to `if (!cond) { body }`.

**Fix 52**: test `k in drop or not lines[k].strip()` instead -- `drop`
(already computed two lines above: the label line + its hoisted tail +
every into-goto) is exactly the set this round is about to remove from
the arm, so the check now asks the right question (is what's LEFT
BEHIND blank?). Unblocking the call surfaced a second, previously
dormant bug in `_collapse_arm` itself, caught live by `work/
hoist_test.py`'s `classic-sibling` case (16/17, not 17/17, on the first
cut): the sibling else-arm's content, copied out verbatim to become the
new collapsed if-body (`ebody`), was read off the same pre-drop `lines`
with no idea that one of ITS OWN lines could be an into-goto this same
round is also deleting -- the goto's target label (`li`) is already
gone by the time `ebody` lands in the output, so the naive copy left a
dangling goto behind (illegal C#, a different failure mode than the
into-block goto the whole pass exists to remove, not merely the same
bug recurring).

**Fix 52b**: thread the caller's `drop` set into `_collapse_arm`
(default `()` so the other, unrelated call sites -- there are none
today, but the signature stays defensible -- don't need updating) and
filter `ebody` by it (`t not in drop`). If filtering empties `ebody`
entirely (the else-arm's only content was the goto being removed), the
existing `if ebody:` branch already falls through correctly to the
bare-condition/drop-entirely case.

Validation (full CLAUDE.md bar): `work/hoist_test.py` 17/17 after
updating the one pinned case whose "want" had documented the OLD
buggy shape verbatim (its own comment said so: "no collapse: the
collapse branch tests the pre-drop arm and never fires") --
`classic-sibling` now expects the collapsed `if (flag1) { Monitor.
Exit(obj7); } obj14 = obj1; return;`, goto gone, no dangling reference.
The other 16 hoist cases and all other statement-pass unit mirrors
(elseif_test 13/13, cse_test 30/30, flag_test 22/22, cp_test 20/20,
selfcopy_test 5/5, forhead_test 10/10, itfdispatch_test 14/14)
unchanged. Golden suite: 7/50 mismatches (AudiencePath,
CurrentDayManager, GameManager.CheckAllReady, InputManager,
InventoryManager.AssignTemplates, LegsAnimator, SendMouseEvents) --
confirmed via direct A/B relift (`work/probe_b46_relift7.py`, run
against the patched source and again against a byte-identical
pre-patch revert) to be byte-IDENTICAL with and without this batch's
patch, i.e. pre-existing drift already present against `goldens.json`
(which predates batches 44/45 -- last regenerated 19:32, il2csharp.py
last touched 22:27) and not this batch's concern; flagged again for
the next golden regen, which should happen before/at the next
promotion regardless of who ships it.

Full-corpus sweep A/B (`work/sweep_1a_audit.py`, PYTHONHASHSEED=0,
same source tree reverted/reapplied for a clean comparison):
```
before (pre-batch-46): lines=1,911,733 crashes=2 (TMP caps, pre-existing)
                        brace_unbalanced=0 into_block=15,419/3,958
after  (batch-46):      lines=1,911,725 crashes=2 (same)
                        brace_unbalanced=0 into_block=15,418/3,957
```
Small and clean: -8 lines, -1 into_block site/method (a downstream
unblock from the simplified shape, not this arm's own goto -- that
goto was already being dropped via the `drop` set regardless of
whether the collapse fired, so the pre-fix baseline was already SOUND
here, just uglier), 0 new crashes, brace balance unaffected either
side.

Full rebuild `b46_out1`: 11,107 files / 115,658 bodies / 0 failed,
589.8s. Gate: **2/4,864/4, byte-identical to the b42_out1 through
b45_out1 baseline** (the same two legacy-TMP files, same per-file
ERROR/MISSING counts -- confirmed file-for-file since only 2 bad files
exist tree-wide, no separate gate_diff needed). Brace audit: 0/11,107
unbalanced. Real-build tree line count 2,630,341 (b45_out1) ->
2,630,333 (b46_out1), delta -8, matching the in-memory sweep exactly.
Patches: `work/patch_b46_collapsearm.py` (fix 52), `work/
patch_b46b_collapsearm_drop.py` (fix 52b), both binary CRLF per
CLAUDE.md; build `work/run_build_b46.py` + `work/build_b46.log`; gate
report `work/ts_gate_b46_out1.txt`; sweep `work/sweep_1a_audit.py`
(existing tool, re-run); relift A/B probe `work/probe_b46_relift7.py`.

`b46_out1` is a verified, gate-clean, crash-clean, brace-clean
candidate (supersedes b45_out1 -- strict superset, same source tree
plus fixes 52/52b); promotion over `final_out/` (= b42_out1) is a
human call per the standing rule (§0/§6). `b45_out1` was left on disk
rather than reaped -- deleting a build tree is the kind of call this
session left for whoever promotes next, per the same standing rule.

## 0y. Batch 45 (2026-08-22, todo lead #3: interface-dispatch
naming -- SHIPPED, partial)

Picked up lead #3 (§0n's sizing, unchanged in kind since batch 36:
14,179 `/*indirect*/` lines) against its own recorded ground truth,
GameManager.CheckAllReady VA 0x1806DF770 (work/probe_gamemanager.py).
Read the raw lifted shape directly rather than guessing from the
census buckets: ahead of each interface call, il2cpp emits `typeof
(IFace)` + a linear scan of `klass->interfaceOffsets[]` for a matching
`interfaceType`, landing on `offset` -- an ABSOLUTE slot in the
receiver's class vtable where that interface's OWN method block
begins (`(pair.offset << 4) + 0x138 + klass`) -- and the call itself
adds one more small constant to reach a specific method within that
block.

The naming insight: **interface typedefs carry no runtime vtable of
their own** (`vtable_start` is -1 in metadata -- interfaces are never
instantiated), so `il.vtable_method` (the mechanism batch 33 built for
ordinary VIRT_CALL resolution) cannot apply here. But metadata's
`method_start`/`method_count` on the INTERFACE typedef itself gives
the true method-block order, and it is NOT BCL declaration order --
verified empirically against the real metadata (not assumed):
`System.Collections.IEnumerator`'s method[0] is `MoveNext`, not
`get_Current` (probed directly: `[0] MoveNext, [1] get_Current, [2]
Reset`). Dividing the call's own extra displacement by 16 (KLASS_
VTABLE's stride) gives the relative index into that interface's own
method table directly -- no runtime value tracking needed, since the
Lifter's symbolic execution can't know which interfaceOffsets[i] the
real search loop would land on (it's a genuine data-dependent loop),
but the STATIC relationship between (interface type text, call's own
relative displacement) and (resolved method) holds regardless of which
runtime index the search would find.

Two pieces, following the CFG-job framing exactly as §0n described it:
`Il2Cpp.interface_method_by_offset` (il2csharp.py) resolves `(interface
type text, relative slot)` -> a global method index, parsing a closed-
generic display string (`IEnumerator<Fusion.PlayerRef>` -> base name +
depth-aware top-level-comma arity count -> `` `1 `` metadata suffix) and
indexing straight into `method_start`. `Decompiler.
_name_interface_dispatch` (decompiler.py, new LAST `_structure` pass,
after `_render` -- the `((byte*)...)` unsafe-cast text this pass
matches on doesn't exist until `_render`'s `_unsafify` produces it, a
real bug caught by the ground-truth probe going quiet on the first
wiring attempt) is purely textual: given a `/*indirect*/` call site,
walk backward for the nearest same-token slot-address assignment (the
`<< 4) + 0x138 +` shape), then further back for the nearest typeof()
decl actually REFERENCED somewhere in that span (so an unrelated
typeof several statements earlier can't be picked up by accident).
Declines silently -- keeping the honest marker -- whenever the
displacement isn't a multiple of 16, the interface type text doesn't
resolve, the relative slot is out of the interface's own method-table
range, or the receiver arg doesn't fold cleanly (`_recv_shaped`); a
wrong name is worse than an honest unknown (CLAUDE.md's `sub_x/*shared
body*/` precedent, applied here rather than restated). Reuses the
existing `_recv_fold`/`_split_args`/get_-prefix-property convention
verbatim, so a resolved call reads exactly like every other named
instance call in the corpus -- `recv.MoveNext()`, `recv.Current` (no
parens, the property path) -- rather than a new, differently-shaped
special case.

Validation (full CLAUDE.md bar): new unit suite `work/
itfdispatch_test.py`, 14/14 (6 cases against `interface_method_by_
offset` directly -- including the exact ground-truth order fact
`IEnumerator.method[0] is MoveNext` as a hardcoded regression fixture,
not a BCL-order assumption -- plus 8 against the full text pass: the
three ground-truth shapes, a 2-param arg-trim case, and four reject/
decline cases). Ground truth re-lifted matches exactly: `obj21.
GetEnumerator();`, `obj5.MoveNext();`, `obj5.Current` (was three
`/*indirect*/` blobs). Golden snapshot suite: only GameManager.
CheckAllReady changed, and it changed correctly (the intended fix,
regen deferred to the next promotion per the standing golden-regen
rule); the other 6 golden mismatches at this source tree (AudiencePath,
CurrentDayManager, InputManager, InventoryManager.AssignTemplates,
LegsAnimator, SendMouseEvents) were confirmed PRE-EXISTING and
unrelated by reverting this batch's two files to a byte-identical
pre-patch state and re-running -- identical 6 failures, so goldens.json
is stale against source drift from batches 43/44's own work, not
something this batch introduced (not chased further -- out of scope,
flagged for the next golden regen). Full-corpus in-memory sweep (work/
sweep_itfdispatch.py, new): 116,178 methods, 546.3s, crashes still 2/2
(the pre-existing TextMeshPro/TextMeshProUGUI cfg-too-large caps,
unchanged), `/*indirect*/` lines **14,179 -> 13,009 (-8.3%)** --
generalizes far beyond the one ground-truth method (spot-checked
resolved `.MoveNext()`/`.GetEnumerator()` sites across Fusion.Sockets,
JSONAccess, UIElements, Photon's EnetPeer, System.Xml's Compiler --
different modules entirely, all reading correctly). Full rebuild
`b45_out1`: 11,107 files / 115,658 bodies / 0 failed, 811.5s. Gate:
**2/4,864/4, byte-identical to the b42_out1/b43_out1/b44_out1
baseline** (same two legacy-TMP files, 0 newly bad). Brace audit:
0/11,107 unbalanced. Real-build `/*indirect*/` count 13,006 (matches
the in-memory sweep within file-write-time dedup noise). Patches:
`work/patch_3_itfdispatch.py` (binary CRLF patch, both files);
build `run_build_b45.py` + `build_b45.log`; gate report
`ts_gate_b45_out1.txt`; sweep `sweep_itfdispatch.py`; ground-truth
probe `probe_gamemanager.py` (scratchpad, not checked into work/).

**Partial, honestly**: this ships the interfaceOffsets-search shape
specifically (the "2,145 interface-offset dispatch lines" half §0n
originally split out) plus whatever of the broader 14,179-line count
happened to share that exact shape -- 1,170 lines corpus-wide, well
beyond §0n's original 2,145 estimate for that bucket alone, since the
same search-block pattern recurs per-call rather than being cached
(three separate searches in the one ground-truth method alone). The
OTHER named sub-buckets from the batch-38 re-census (2,206 bare-temp
`objN() /*indirect*/`, 1,570 `((byte*)objN + 0x0)[0]()` obj-vtable-0,
~2,400 constant-slot klass-walk, 585 `invoke_impl()`, 181 `data_*`) are
untouched -- none of those shapes carry a `typeof()` anchor this pass
can resolve against; naming them needs a genuinely different mechanism
per bucket, not an extension of this one. 13,009 `/*indirect*/` lines
remain open residue.

`b45_out1` is a verified, gate-clean, crash-clean, brace-clean
candidate (supersedes b44_out1, reaped); promotion over `final_out/`
(= b42_out1) is a human call per the standing rule (§0/§6).

## 0x. Batch 44 (2026-08-22, todo lead 2: the else-if/switch
flattener -- CLOSED)

Picked up lead 2 straight off lead 1a's own residue: PickupNewObj (VA
0x1807018d0, batch 43's own ground-truth method) had its gotos cleared
by the tail-duplication fix, but its `index != 5/3/2/11/58/4` compare
cascade was still 6 levels of raw brace nesting -- exactly the "needs
an else-if/switch flattener" lead. Unlike lead 1a, this needed no
CFG/data-flow reasoning at all: flattening a right-nested if/else
chain is a PURE boolean identity. `if (C) {X} else {Y}` and `if (!C)
{Y} else {X}` render identical C# for ANY X, Y (nothing moves across a
CFG region, so none of lead 1a's reachability/funnel machinery
applies), and `else {if(c){...}else{...}}` with NOTHING ELSE in the
else-block is identical C# to `else if (c) {...} else {...}` (an else
holding a single if statement literally IS an else-if). Two cases in
`_elseif_flatten` (decompiler.py, new `_structure` pass, wired in
LAST, right before `_render`, so it never has to be taught about
anything the rest of the pipeline might still produce): the chain
already sits in the else arm (direct reparent, no negation) or the
chain sits in the true arm -- PickupNewObj's actual shape -- (negate
the condition, swap which content renders first). `!=`/`==` swap to a
clean opposite for a single, uncompounded comparison; anything else
conservatively wraps in `!(...)`, the same fallback `_collapse_arm`
already uses elsewhere in this file.

Three real bugs, each caught before it shipped -- this pass looked
simple and was not:

- **The pass couldn't see past the level it had just flattened.**
  First draft merged 'else'+'if (cond)' into one text line
  immediately. `_construct_arms` (which this pass's own re-scan
  depends on to find a DEEPER pyramid level next round) requires a
  standalone 'else' line followed by '{' to recognize a chain -- and
  a merged line no longer even starts with 'if (', so the pass's own
  top-level scanner skipped straight past it on the next round.
  Caught unit-testing a 3-level synthetic pyramid (only the outermost
  level flattened, `hoist_test.py`-style hand-tracing hadn't caught it
  because the first live probe target only needed one level to look
  right). Fixed by keeping 'else' and 'if (cond)' as two SEPARATE
  lines through every round (an independent 'if (...)' line is picked
  up by the scanner regardless of what precedes it) and merging each
  adjacent else/if pair into one line as a single cosmetic pass once
  the structural rounds are done.
- **A dangling `else if` with no matching `if` -- a real syntax
  error.** Caught live-tracing a NEW golden regression
  (ActorSpawner.Update, VA 0x180513740) the first clean build
  surfaced. Root cause: `_render`'s own PRE-EXISTING "drop empty
  if/else blocks" collapse (batch 44b, long before this session) knows
  how to invert `if (X) { }` into `if (!(X)) {...}` when a bare 'else'
  follows -- checked by exact text match, `cleaned[j].strip() ==
  'else'`. Every site that logic had ever seen before today put a bare
  'else' on its own line (confirmed empirically: zero 'else if' sites
  existed anywhere in the corpus before this session); this pass's
  merged 'else if (cond)' line doesn't match, so the check fell
  through to ITS sibling branch (unconditional drop when the guard is
  pure) and silently ate the entire `if (X) { }` -- condition included
  -- leaving its `else if` orphaned. First fix attempt broadened
  `_render`'s lookahead to also recognize 'else if' -- this cleared
  the syntax error but a SECOND bug surfaced immediately: the
  broadened invert path skipped past the whole 'else if (cond)' line
  to reach its body, discarding the chained condition entirely (`if
  (X) {} else if (Y) {...} else {BODY}` collapsed to `if (!X)
  {BODY}`, silently dropping the Y test) -- syntactically valid,
  semantically wrong, exactly the class the golden suite exists to
  catch and the parse gate cannot. Properly generalizing _render's
  cascading collapse to preserve a chained condition on invert would
  be a much bigger, riskier change to already-delicate, previously-
  correct code for a narrow gain. Reverted that path entirely.
- **The actual fix: never hand `_render`'s untouched logic a shape it
  wasn't built for.** `_elseif_flatten` now declines outright whenever
  either arm it would place next to the merge point is wholly empty
  (`wholly_empty()`, checked precisely for just the two arms that
  matter -- not a broad "any empty block anywhere in the span" scan,
  which a first cut tried and which declined the REAL target pyramid
  outright: PickupNewObj's own for-loop bodies each carry an unrelated
  no-op `if (!(num4 != 0)) { }` leftover, one per case, structurally
  nowhere near where this pass would ever merge an else-if). Those
  sites are left for `_render`'s existing, unmodified, already-correct
  mechanism to collapse exactly as it always has.

Validation (full CLAUDE.md bar): new unit suite `work/elseif_test.py`,
13 cases (both sound cases, the ambiguous/reject shapes, and both live
bugs above pinned as their own regression cases). All standing suites
green (hoist 17, cse 30, flag 22, cp 20, re 0 failures, selfcopy 5,
forhead 10). Golden snapshot suite: 6/50 bodies changed on top of
lead 1a's own already-reviewed 5 (AudiencePath, CurrentDayManager,
InputManager, LegsAnimator, SendMouseEvents changed FURTHER;
AssignTemplates changed independently of its lead-1a size-cap decline)
-- every diff read by hand, several genuine additional `else if`
flattenings beyond the original PickupNewObj target (e.g. InputManager
`obj29 >= unknown >> 3`, LegsAnimator `unknown == unknown`,
CurrentDayManager `!flag1`), one (AssignTemplates) verified sound by
direct case-by-case truth-table check rather than just pattern-
matching the shape. Full-corpus crash sweep: 116,178 methods, 672.3s,
crashes 2/2 (the pre-existing TextMeshPro/TextMeshProUGUI cfg-too-
large caps, unchanged). Scoped Assembly-CSharp rebuild (6,622 bodies,
49s) gated **perfectly clean: 0 bad / 0 ERROR / 0 MISSING**, 888 real
`else if` sites all parsing correctly, brace 0/489. Full rebuild
`b44_out1`: 11,107 files / 115,658 bodies / 0 failed, 741.6s. Gate:
**2/4,864/4, byte-identical to the b42_out1/b43_out1 baseline** (same
two legacy-TMP files, 0 newly bad). Brace audit: 0/11,107 unbalanced.
Corpus-wide: **13,224 `else if` sites** (0 existed anywhere before this
session), tree lines 2,663,122 (b42_out1) -> 2,630,342 (net -32,780
despite lead 1a's own +75,477 duplication cost landing in the same
window -- flattening removes more brace-nesting overhead than
duplication adds). Patches: `work/patch_2_elseif.py` (first draft,
superseded), `patch_2_elseif2.py` (the two-line-until-final-merge
fix), `patch_2_elseif3.py` (the `_render` lookahead broadening,
REVERTED), `patch_2_elseif4.py` (the broad any-empty-block guard,
REVERTED -- over-declined the real target), `patch_2_elseif5.py` (the
precise per-arm `wholly_empty` guard, shipped); build
`run_build_b44.py` + `build_b44.log`; gate report
`ts_gate_b44_out1.txt`.

`b44_out1` is a verified, gate-clean, crash-clean, brace-clean
candidate (supersedes b43_out1, reaped); promotion over `final_out/`
(= b42_out1) is a human call per the standing rule (§0/§6).

## 0w. Batch 43 (2026-08-22, todo lead 1a: the tail-DUPLICATION
fallback for funnel-blocked shared-tail gotos -- CLOSED)

Batch 42's own §0v left lead 1a as "declined with data": the funnel
correctly blocks HOISTING a shared tail when some non-participant arm
(usually a genuine default case) can leak into the shared insertion
point without ever executing the tail. §0v's own framing named the
honest recovery as either per-path definite-assignment analysis (the
blocked slot-liveness upstream feature) or lead 2's switch recovery.
This batch found a third, much cheaper path that needed neither:
**duplication instead of hoisting.** Ground-truthed against
InventoryManager.PickupNewObj (VA 0x1807018d0, the same method §0v's
own funnel work used) via `work/probe_b42_hoist.py`: every one of its
5 into-gotos to the shared tail re-establishes the exact same
phi-merge names (`v514`..`v525`) right before the jump that the tail
reads. Replacing `goto L;` with an inlined COPY of L's body at the
goto's own position is therefore always behaviorally identical to what
the goto already does -- nothing else jumps INTO a goto's own spot, so
this needs no reasoning about other, non-participant paths at all. The
funnel's whole soundness proof (does some OTHER path leak into a MOVED
tail?) is a hoisting-specific question that duplication sidesteps
entirely.

**The gate.** Reused rather than reinvented: `_falls_to` (classic path)
and a new `until_funnel=True` early-return on `_lca_hoist_plan` (LCA
path) already prove everything duplication needs -- that the specific
goto's own unwind to H is clean (no stray statement, no loop/switch/SEH
crossed) -- before either ever reaches its own `funnel_ok` call. A
funnel_ok-only rejection (as opposed to a falls_to/structural failure)
is therefore safe to duplicate from; `dup_ok` tracks exactly that
distinction. The duplicated span is always `li+1..ac` (the label's own
immediate arm, same as what hoisting would have moved) -- NOT
`li+1..H`, which would wrongly include unrelated code between nested
block closes and H (a real bug in an early draft, caught by
hand-tracing hoist_test.py's own "reject-label-side-code" case before
it shipped: H is proven reachable by falling through pure brace/`else`
punctuation only, never real statements, so extending the duplicated
slice to H is neither necessary nor safe in general). Two more guards,
both found live: (1) the tail itself must contain no `goto` to a label
outside `[li, ac)` -- otherwise duplicating it mints a fresh
into-block goto from a brand-new lexical position (mirrors fix 51a's
protection for the hoist path, hoist_test.py's
"reject-tail-goto-targets-inner-label"); (2) a size cap at 24 raw
statement lines -- InventoryManager.AssignTemplates (VA 0x1806faf40, a
63-line singleton-heavy tail) duplicated correctly but ballooned
108->324 lines because `_singleton_cse`'s "one Instance fetch, N
reads" collapse didn't re-fire within either copy, an interaction not
yet root-caused. Above the cap, sites are left exactly as before
(illegal-but-honest goto) rather than risk that interaction; every
other funnel-blocked shape found in the golden sample (small tails, at
most a short loop) duplicated cleanly.

**Validation** (full CLAUDE.md bar; three live-caught bugs in draft
code along the way, all fixed before any build): new unit suite
`work/hoist_test.py` extended to 17 cases (the existing 15 plus new
dup-accept/dup-reject cases, including three cases that were
"reject"-only for HOISTING under batch 42 but are proven-by-hand sound
for duplication and now flip to accept: `dup-if-without-else`,
`dup-sibling-arm-falls`, `dup-classic-guard-bypass`,
`dup-cascade-stores-arm` -- the funnel's non-participant-leak concern
is provably irrelevant to a transform that never creates a shared
insertion point). All standing suites green (cse 30, flag 22, cp 20,
re 0 failures, selfcopy 5, forhead 10). Golden snapshot suite: 5/50
bodies changed, every diff read by hand -- SendMouseEvents.SendEvents,
InputManager.UpdateState, AudiencePath.DrawCurved,
LegsAnimator.Finder_AutoDefineOppositeLegs, and
CurrentDayManager.Rpc_RakeIntro (the exact method §0v's own writeup
named as a disasm-proven b41 wrong-hoist) all show a clean
goto-to-duplicate conversion, several with downstream passes
(copy-prop, `_redundant_else`) cleaning the duplicated arm up further
than a hoist's single shared copy ever could (a previously-flat,
ambiguous "if(b){...goto...} <dangling code>" shape now renders as a
proper `if/else`). InventoryManager.AssignTemplates and
RenderGraphPass.SetColorBufferRaw (the size-cap and CSE-interaction
cases above) correctly stay unchanged post-cap. New full-corpus
structural sweep `work/sweep_1a_audit.py` (standalone re-creation, the
original `sweep_audit.py`/`classify_into2.py` were reaped at the
b42_out1 promotion -- numbers below are this tool's own into_block
mirror, not guaranteed bit-identical methodology to the historical
tool, though the same shape): 116,178 methods / 676.8s, crashes 2/2
(the pre-existing TextMeshPro/TextMeshProUGUI cfg-too-large caps,
unchanged), brace 0/116,178, **into_block 32,094/9,434 (b42_out1
baseline) -> 15,419/3,958 (-52% sites / -58% methods)** -- over half of
the entire batch-42 funnel-blocked residue recovered as sound
duplicated code. Full rebuild `b43_out1`: 11,107 files / 115,658
bodies / 0 failed, 679.5s. Gate (`ts_gate.py`): **2 bad / 4,864 ERROR /
4 MISSING, byte-identical to b42_out1** (same two legacy-TMP files, 0
newly bad, ERROR/MISSING counts unchanged). Brace audit: 0/11,107
unbalanced. Patches: `work/patch_1a_dup.py` (first draft, superseded),
`patch_1a_dup2.py` (the `until_funnel` gate correction after
hand-tracing found the first draft's li+1:ac-unconditional bug),
`patch_1a_dup3.py` (fix 51a's tail-internal-goto guard, mirrored),
`patch_1a_dup4.py` (the 24-line size cap); build `run_build_b43.py` +
`build_b43.log`; gate report `ts_gate_b43_out1.txt`.

`b43_out1` is a verified, gate-clean, crash-clean, brace-clean
candidate; promotion over `final_out/` (= b42_out1) is a human call
per the standing rule (§0/§6).

**Next-session leads on this same family:** the residual 15,419
into_block sites are the cases duplication's own gates correctly
declined -- the 24-line size cap (needs the `_singleton_cse`
interaction root-caused, or a size-aware alternative: hoist the
singleton fetch out of the tail BEFORE duplicating the rest), plus
whatever still fails `_falls_to`/`_lca_hoist_plan`'s structural checks
entirely (stray code between nested closes, SEH-crossing, nested
labels, forward-disjoint gotos) -- these were never in scope for
either the hoist or the duplicate path and still need lead 1a(a)'s
per-path definite-assignment analysis or lead 2's switch recovery.
Also noted, not investigated: CurrentDayManager.Rpc_RakeIntro's golden
diff shows a `foreach` degrading to an indexed `for` loop once its body
is duplicated to a second call site -- likely the foreach-sugar pass
requiring a single-use pattern that duplication breaks; cosmetic, not
chased this batch.

## 0v. Batch 42 (2026-08-22, todo lead #1: the LCA hoist extension +
the funnel that had to exist first -- two disasm-proven b41 wrong-hoist
families fixed -- CLOSED)

The lead said "hoist to the LCA"; the batch's real work was proving
WHICH LCA hoists are sound, and that proof turned on the classic path
too. Seven fixes, each earned by a caught failure:

- **51 -- `_lca_hoist_plan`.** When the classic point (from the
  label's own arm) is unreachable from some into-goto, H = end of the
  smallest construct containing the label and every into-goto.
  Guards: label-side unwind clean (no code between inner construct
  ends and parent arm closes -- reordering), no loop/switch/SEH on
  the label's ancestor chain, falls_to per goto, the funnel (below),
  and 51a.
- **51a -- tail-goto guard (SHARED, fixes a live b41 hole).** A goto
  inside the tail must not target a label that stays inside the
  hoisted-over region: b41 hoisted `tail1; goto L_aa;` past the
  construct while `L_aa:` stayed inside it, minting a backward
  into-block goto (hoist_test case 12 reproduces b41's behavior).
- **51b -- late second run**, after `_drop_dead_locals`: later passes
  MINT shapes the early run (before `_drop_dead_temps`) can never see
  -- dead-store drops empty the arms around gotos, `_redundant_else`
  restructures siblings (HuntManager.SpawnEnemies's into-goto was
  SEH-blocked at the early position, sibling-clean at the final one).
  classify_into2's SOUND=47 at b41_out1 was exactly this residue.
- **51c-51g -- the funnel, v4 (the spine model), applied to CLASSIC
  hoists too.** The golden suite caught a wrong cascade
  (InventoryManager.AssignTemplates: a sound 51-hoist unblocked a
  LEAKY classic hoist of the loop-head label -- the classic path
  shipped without classify_into2's arm_fallthrough, so b41 moved the
  whole loop body above the assigned-path stores). v4: inside each
  participant arm only the carrying LINK construct (the last
  statement -- that is what _falls_to guarantees) is checked; its
  non-participant arms must not fall; a no-else/loop/switch/SEH link
  holding a participant is rejected (the false path bypasses it);
  pre-link constructs funnel into the link; tail-internal constructs
  move with it. Two drafts died on caught cases (v2 flat enumeration
  over-rejected tail-internal init guards; v3 chain-only missed
  sibling sub-arms) -- the pre-build sweep was the decisive tool
  (into_block 17,718 -> 34,144 under v3 forced the spine redesign).
  Raw input packs `stmt; return;` on one line: _FLOWTAIL_RX reads the
  trailing statement (`_can_fall`).
- **51f -- end-of-method single-return equivalence:** a tail of
  exactly `return;` hoisted to the end of the statement list is sound
  for every path (executing it == falling off the end).
- **Two b41 wrong-hoist families PROVEN by disasm, now fixed:**
  CurrentDayManager.Rpc_RakeIntro (the Notify/mask==4/num1==7 paths
  jmp the shared epilogue -- b41 made them run the foreach tail with
  SetActive calls) and SimpleCollator.IndexOf (the `start >=` default
  arm jumps straight to `mov esi,-1; ret` at 0x181ade5db -- b41 made
  it execute the merge stores). Model behind both: a path that falls
  past a construct in the lifted tree natively flows to the NEXT
  EMITTED block (the lifter emits a goto whenever the successor is
  non-adjacent), so falling non-participant arms never ran the tail
  natively.
- **Declined with data:** the pure-dead-tail relaxation (re-qualify
  the blocked hoists when the tail is pure stores and H is
  return-only): the leak paths read tail RHS temps that may be
  UNASSIGNED on those paths -- b41's hoisted forms were
  definite-assignment-broken anyway; a kept goto is greppable, a
  silently wrong hoist is not (the pass docstring's own rule). The
  honest recovery is per-path def-assign/dominance analysis (the
  slot-liveness upstream feature, backlog #2's family) or lead 2's
  switch recovery (the blocked pyramids ARE switch shapes).

Validation (full CLAUDE.md bar): unit mirror `work/hoist_test.py` NEW
(15 cases: every rule + the 51a/51b live repros + the cascade), plus
the standing suites all green (selfcopy 5, forhead 10, cse 30, flag
22, cp 20, re 0). Goldens read as evidence twice: the 5 changed bodies
were each judged pre-build (1 disasm-proven, 4 by the lifter-structure
invariant) and the post-build regen froze exactly those 5 (50/50).
Pre-build crash sweep (same source the build ran): 116,176 methods,
crashes 2 (the TMP caps), brace 0, dangling 0, empty_arg 0, follower
0, into_block 32,094/9,434 (see below). Full rebuild b42_out1:
11,107 files / 115,658 bodies / 0 failed (566s). Gate: bad-file set
UNCHANGED (the TMP pair); ERROR 4,863 -> 4,864 (+1 node inside
TextMeshProUGUI's 1,703-node cap -- the flat lift runs _structure, so
the hoist shift moved one node; MISSING 4/4); reports
`work/ts_gate_b42_out1.txt`. Brace audit 0/11,107. Census
`work/census_b42_v4.py` (NEW, mirrors the shipped predicates): the
tree is at fixpoint -- 26 residual CLASSIC+LCA-sound sites (0.1%),
blocked families funnel 4,330 / goto falls_to 8,181 / nested-label
4,477 / label-side 2,090 / loop-switch-seh 369.

THE HONEST COST: tree lines 2,587,645 -> 2,663,122 (**+75,477**) and
into_block 17,718/4,079 -> 32,094/9,434. The ~14.4k newly-kept gotos
are the un-done b41 hoists the funnel proved unsound -- most are the
guard-chain compare pyramid (SimpleCollator/MSCompatUnicode family)
whose default arm RETURNS past the merge; they do not compile either
way (the hoisted form breaks definite assignment on the leak paths),
and the kept form is greppable. New tools: `work/hoist_test.py`,
`work/census_b42_v4.py`, `work/probe_b42_hoist.py`; patches
`patch_b51_lca.py` / `b51c_funnel2.py` / `b51d_notail.py` /
`b51e_funnel3.py` / `b51f_endret.py` / `b51g_funnel4.py`; build
`run_build_b42.py` + `build_b42.log`. Also found, not fixed:
`_collapse_arm` is dead code (its emptiness check tests the pre-drop
arm, which always contains the label line) -- fix or reap next
session.

`b42_out1` was the verified gated candidate; promotion over `final_out/`
(= b36_out2) was a human call per the standing rule (§0/§6) -- the
+75k-line/+14.4k-into_block honesty cost against two disasm-proven
correctness fixes. **The call was made: promoted to `final_out/` on
2026-08-22** (byte-verified copy; batch trees b37_out1-b42_out1 and
their work-dir archaeology reaped per the §6 rule).

## 0r. Batch 38 (2026-08-22, todo.md sweep: two shipped fix families, one
shipped probe suite, four sizings/declines — CLOSED)

Drove EVERY open todo.md item to a close or a measured decline in one
session. Three fix families shipped (fixes 40-40e, 41-41b, 42-42b), the
golden snapshot suite landed (backlog #6), and the four survey/probe
leads were sized with concrete numbers (two declined with data, two
re-scoped for the next session).

- **40/40b/40c/40d+40e — receiver folding extended from accessors to
  CALLS (backlog #5's last open half).** Ground truth
  CurrentDayManager.Rpc_RakeIntro (VA 0x1806aa110): arg0 read
  `v137[v133]` at `_call` time, so neither fold guard (bare token /
  dotted / this / &-of-those) accepted it and the call rendered
  `GameObject.SetActive(obj13, 1)`. A resolved instance method's arg0
  IS the receiver by IL2CPP convention -- the exact argument the
  accessor branch already folds through ANY receiver on -- so `_recv_
  shaped` (new module helper: any text that is not a placeholder,
  literal, class token, or byref composite) now folds it (40), plus the
  same rule on both tail-jmp handlers (40c, the il2csharp.py/decompiler
  .py split 21c/21d already documented), `_recv_fold`'s no-paren set
  grown to postfix-`[]` texts (40b, `obj22[num2].SetActive(0)`), and a
  stale-paren collapse in `_member_fold` (40d). **40d REGRESSED and was
  fixed same-session by 40e**: its `\(([\w.]+)\)\.` -> `\1.` also ate
  `typeof(X).member`'s parens (the paren belongs to the typeof keyword,
  not grouping) -- `typeofSystem.Linq...EqualInstruction.s_X`,
  31,908 sites tree-wide, GATE-INVISIBLE (`typeofFoo` lexes as an
  identifier) and it also broke the `/* typeof(X) static-member store
  elided */` elision matcher. Caught by the full-tree grep census after
  the first b38 build, NOT by the scoped gates (it's semantically wrong,
  syntactically valid -- exactly the class the golden suite exists
  for). 40e adds the `(?<![\w.])` lookbehind. Tree: static SetActive
  renders 63 -> 0 in AC; 213 AC files changed.
- **41/41b — `_redundant_else`, new `_structure` pass (the readability
  null-coalescing item's remaining shape).** Survey first: `? null :`
  and `?? default` are already 0 tree-wide; the surviving shape is the
  explicit `if (x == null) { ...return/throw...; } else { work }` --
  1,054 sites in 544 files at b37. When the if-arm provably ends in an
  unconditional flow-break (return/throw/goto/break/continue), the else
  arm is plain fall-through: the pass drops the keyword and splices the
  arm's braces (cannot reassociate any inner else -- token sequence
  unchanged; brace matching counts only exact-brace lines so string
  literals can't skew depth). Unit mirror `work/re_test.py` FIRST per
  §4's rule -- and it caught a real bug before any live run (41b: the
  backward brace matcher checked depth before decrementing; every fold
  case failed, every no-fold case passed, zero live impact). AC:
  bare-`else` lines 4,471 -> 3,185 (-29%); scoped gate 0/0/0.
- **42/42b — positional float-parameter recovery (backlog #2's
  plain-store-value sub-bucket, root-caused live).** Ground truth
  CamouflagedMonsterRun.OnEnable (VA 0x18060F5A0): `movss xmm1,[rel
  182FC7D40h]` (the 4.0f const pool) then the set_speed thunk rendered
  `this.anim.speed = obj5;` with obj5 undefined. Root cause: Win64
  assigns register index by PARAMETER POSITION (param 2 -> XMM1 when
  param 1 is the integer receiver; the `xor r8d` is the trailing
  hidden MethodInfo* slot) -- but `_call` assembles args GPR-first and
  trims to the declared arity, so the stale `_`/unknown GPR text
  printed at the float position and the real value sat past the trim.
  `_positional_args` (new) mirrors `_hint_arg_types`' positional walk
  (42b corrected it: slot == parameter position, NOT float-ordinal --
  the first cut looked in XMM0 for a position-1 float and never fired;
  NOTE `_hint_arg_types` itself has the same ordinal-per-class advance,
  so its hints miss on interleaved signatures -- pre-existing,
  hint-only impact, deliberately left) and rewrites placeholder/
  unknown entries only; meaningful entries are never clobbered. AC
  read-before-def 8,846 -> 7,514 (-15%); full tree 211,643 -> 208,043
  (-1.7%; the float family sits mostly in the call-arg bucket, not
  plain-store).
- **Backlog #6 SHIPPED — golden snapshot tests.** `work/make_goldens.
  py` freezes ~50 lifted bodies (all 16 batch-writeup ground-truth VAs
  + a deterministic index-stride spread; `work/goldens.json`), and
  `work/test_goldens.py` re-lifts and diffs them under pytest -- 50/50
  green in ~13s including the 4.5s metadata load. Run both with
  `PYTHONHASHSEED=0` (the test skips with instructions otherwise).
  Construction caught a real harness ambiguity immediately: shared-
  body VAs fold many methods onto one address (String.get_Length and
  7+ other trivial getters share 0x1805410f0), so goldens pin the
  MethodDef ROW (`mi`), never the VA. Regenerate only after a gated
  build and READ THE DIFF -- the first generation of this suite froze
  the 40d typeof damage because it was generated from the then-current
  source (regenerated clean after 40e).
- **Probes/sizings that CLOSED leads with data** (details moved into
  todo.md's leads): single-value phi propagation DECLINED (same-value
  copies are 0.6% of AC's 235,126 copy lines, and 76% of those exist
  only because a pred's value was skipped -- unsound to collapse; the
  merge-time same-text collapse at `_analyze` already handles the real
  case); the dead-value-copy residual (§0q lead #5) is 660 sites in AC
  (638 impure-shaped -- kept BY DESIGN per 23c's never-drop-the-last-
  render invariant; 22 pure with paren-carrying RHS the `_IMPURE`
  regex over-matches -- negligible); copy-prop's remaining pure copies
  split addr-taken 43% / in-loop 19% / cross-arm 34% / unsubstituted
  1.3% (AC) -- the biggest shape is address-taken sources, which is
  escape-analysis/slot-liveness territory, confirming the todo's
  separate-mechanism framing; indirect dispatch re-censused at 14,179
  lines (2,206 bare-temp / 1,570 obj-vtable-0 / ~2,400 klass-walk-NNN
  / 585 invoke_impl / 181 data_) -- naming still needs the interface-
  type recovery CFG job (GameManager 0x1806DF770 ground truth).
- **Also**: `__static_fields + N` residues are now **0** tree-wide
  (was the batch-16 "named static-address residues" item; collapsed by
  the b35b static-fields work -- that half is done). The `<>c`
  cached-delegate backer's blocker was never the field table (parsed
  since batch 35; decls render `__9__15_0`): it is the FOLD itself,
  now fix 75b in flight (§0as).

Validation (full CLAUDE.md bar): 11,107 files / 115,658 bodies / 0
failed; gate **2/7,312/0** (both bad files the documented legacy-TMP
pair; gate_diff vs b37 all-zero -- 0 newly bad, 0 cleared, 0 worse, 0
better; the +14 ERROR over b37's 7,298 is inside the TMP pair, the
documented acceptable wobble, batch 25 saw -25 the same way); brace 0
unbalanced; full-corpus crash sweep 116,178 methods / 426.4s / 2 crashes
byte-identical to baseline (the TMP caps). Readability deltas:
read-before-def 211,643 -> 208,043, pure copy lines 101,658 -> 97,952,
AC bare-else 4,471 -> 3,185, static SetActive 63 -> 0. **dup_impure
reads 19,418 -> 20,950 (+7.9%) — a MEASUREMENT artifact, not a
regression**: fix 40's receiver fold makes distinct same-shape call
instructions render IDENTICAL text (`InterpretedFrame.Pop(frame)` ->
  `frame.Pop()`, previously materialized as distinct objN temps), so the
scanner's same-text match now sees pairs the distinct temps hid;
per-instruction render count is unchanged (verified line-level on
EqualInstruction.cs: each `frame.Pop()` is a distinct `call` in the
disassembly, rendered once). Patches: `work/patch_b40_recvfold.py`,
`patch_b40b_recvfold2.py`, `patch_b40c_tailrecv.py`,
`patch_b40d_staleparen.py`, `patch_b40e_lookbehind.py`,
`patch_b41_redelse.py`, `patch_b41b_redelse_fix.py`,
`patch_b42_posfloat.py`, `patch_b42b_posargsfix.py`; unit mirror
`work/re_test.py` (14 cases); tools `work/probe_svphi.py` (single-value
phi probe), `work/make_goldens.py` + `work/test_goldens.py` +
`goldens.json`; build `run_build_b38.py` + `build_b38.log`; gate report
`ts_gate_b38_out1.txt`.

`b38_out1` is the verified gated candidate; promotion over `final_out/`
(= b36_out2) is a human call per the standing rule (§0/§6).

