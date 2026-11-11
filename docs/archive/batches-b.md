## 0h. Batch 26 (2026-08-21, backlog #2 investigation + label-tail MISSING fix, CLOSED)

Picked up backlog #2 (read-before-def audit, flagged top item) and §2's
stale MISSING-family claim (last measured at batch 18/19: 193 sites,
mostly bare trailing labels).

**Read-before-def re-measured and bucketed one level deeper** (see the
full writeup now living directly on backlog item #2 in §3, not
duplicated here): 273,700 temps at `b25_out1` (down from the 307,013 last
recorded at batch 23c, unmeasured since -- some from batch 24's CFG fix,
some from batch 25's dead-cycle removal, not split out). New tool
`work/rbd_subclassify.py` splits the dominant "other" shape bucket
(132,622 / 48.5%) into byte*-deref-base (13,392), mem[]-store-value
(10,375), plain-store-value (4,938 -- a REAL field/array element getting
an undefined value, e.g. `this.anim.speed = obj5;`, a correctness bug not
just clutter), and a still-mixed other-misc (103,917, ~45% call/`new`
arguments, ~43% no recognizable call shape, no dominant single cause).
Root-caused byte*-deref-base specifically (live re-lift,
`AddRandomVelocity.Update`, VA 0x180513900): a hidden-struct-return call
whose sret buffer is `[rsp+0x20]` via `lea rcx,[rsp+20h]` doesn't get
recognized as a tracked stack slot, so the existing `Foo(&s_N,...) ->
s_N = Foo(...)` sret-fold (il2csharp.py ~4681) never fires for it -- the
call's RAX return binds to a dead fresh temp instead, while the real
consumer reads RAX again later under a second, never-defined temp name.
**Deliberately NOT fixed this batch** -- it's the same stack-frame/
slot-tracking gap already flagged elsewhere in this backlog as blocked
("out/ref parameter detection... needs slot liveness"), genuinely harder
than a session-sized fix, not guessed at. Full detail on backlog item #2.

**§2's MISSING-family claim confirmed stale and mostly already resolved**
by earlier batches (undocumented at the time): re-measured at 6 total
(not 193) at `b25_out1`, and all six individually enumerable (small
enough for a real per-node tree-sitter walk, not just aggregate counts).
Triage: 2 are the already-documented TextMeshPro/TextMeshProUGUI
legacy-lift-path artifact (out of scope by explicit project policy, see
§6's "known artifacts"); 2 are `SequenceNode.cs`'s pre-existing residual
(untouched, not investigated this batch); the remaining 2
(`AchievementsManager.cs`, `LeaderboardManager.cs`) turned out to be a
LIVE instance of exactly the batch-18/19 bare-trailing-label family, just
down to two survivors instead of 169 -- **fixed**. Root cause: `_render`'s
two `typeof(X)` static-member-store elision substitutions
(`_TYPEOF_STORE_0_RX`, `_TYPEOF_KSTORE_RX`, decompiler.py ~4236) replace
a real statement (including its trailing `;`) with a bare `/* ... */`
comment -- ordinarily harmless, but when that elided store is the ONLY
tail after a label (confirmed live: an async `MoveNext`'s `else { L_x:
<elided store> }` funnel arm, `AchievementsManager`'s
`_Initialise_d__9.MoveNext`, VA 0x181A7F5D0), the label is left with
nothing but a comment after it -- a genuine MISSING-node parse error (a
label must be followed by a statement; a comment is not one). Fix: both
replacements now end in `;`, making them valid empty statements
unconditionally (harmless in the non-label case too, and composes fine
with `_hoist_shared_tails`/`_resolve_labels`, which both already ran
earlier in the pipeline and can't see this since the elision happens
last, in `_render`). Verified in isolation with a standalone tree-sitter
parse (0 bad nodes) before trusting it live.

**Validation**: live re-lift of `AchievementsManager._Initialise_d__9.
MoveNext` confirms the fix (`L_181a7f6a6: /* ... */;`, valid). Full-corpus
crash sweep: 116,178 methods, 600.5s, 2 crashes -- byte-identical to
baseline. Full rebuild `b26_out1`: 11,107 files, 115,658 bodies, 0 failed
(664.9s). Gate (`ts_gate.py`): **13 bad / 8,148 ERROR / 4 MISSING** (was
`b25_out1`'s 15/8,150/6) -- `AchievementsManager.cs` and
`LeaderboardManager.cs` both cleared, 0 newly bad, both listings fully
enumerated and compared row-by-row (small enough not to need
`gate_diff.py`). Brace audit: 0 unbalanced, 11,107 files. `b26_out1` is a
verified, gate-clean, crash-clean candidate to promote over `b25_out1`;
promotion is left for a human call (§0/§6) per the standing convention.

Next-session leads, ordered by expected payoff:
1. Backlog #2's byte*-deref-base root cause (hidden-struct-return via an
   untracked `lea rcx,[rsp+N]` sret buffer) is real but needs the
   stack-frame/slot-liveness work this backlog already defers elsewhere
   -- worth scoping as its own project before attempting, not a
   drive-by fix. Start by splitting the 13,392 byte*-deref-base count
   into "sret-return shape" versus other raw-pointer patterns (out/ref
   params, raw offset field access) to size which sub-shape actually
   dominates.
2. `SequenceNode.cs`'s 2 remaining MISSING (and its 10 ERROR) are
   untouched -- last flagged back at batch-2x's "worst files" gate
   listings, never individually root-caused.
3. The `other-misc` read-before-def sub-bucket (103,917, still the
   single biggest undifferentiated slice) needs its own proper
   classifier the way byte*-deref-base/mem[]/plain-store got one this
   batch, rather than the ad hoc call-shape/no-call-shape split used to
   size it this session.
4. Items 1-3 from batch 25's own leads (§0g) are all still open --
   this batch didn't touch `scan_dead_cycles.py`'s residual 986,
   `dup_impure_scan.py`, or the `ComputedStyle` dispatch lead.

## 0i. Batch 27 (2026-08-21, CMOV modeling attempted+reverted, three kept fixes, CLOSED)

Picked up batch 26's own lead #2: `SequenceNode.cs`'s 2 residual MISSING,
"never individually root-caused." This time they were -- and the root
cause is a real, previously undiscovered Lifter gap, not a text-pipeline
one.

**Root cause (confirmed live):** `Il2Cpp.Lifter._insn`'s CMOV handling
(il2csharp.py ~3773) was a bare `return` -- every CMOV variant silently
dropped. A CMOV is a real data-dependent conditional the compiler
collapsed into straight-line code; dropping it leaves the destination
register confidently holding whatever it held BEFORE the conditional,
which is actively WRONG whenever the condition would have updated it,
not just imprecise. Ground-truthed against `SequenceNode.
SequenceConstructPosContext`'s ctor (VA 0x18239D8B0): `xor ecx,ecx; cmp
[rbx],rdx; cmove rcx,rbx; mov [rcx+38h],rax` -- ecx's stale pre-cmov
value 0 survived, rendering a bare-integer lvalue (`56 = ...;`, `0x38` =
56 decimal) instead of the real conditionally-selected pointer.

**Attempted fix:** model CMOV as the ternary it is (`cond ? new : old`),
mirroring SETcc's existing flags-derived-condition shape immediately
above it in the same dispatch. This surfaced FIVE separate bugs across
three rounds of live-trace-fix-rebuild, four fixed, one still unlocated:

1. (own bug) Unbounded text growth: a data-dependency chain of 2+ cmovs
   (one's result feeding arithmetic that feeds a second cmov's condition
   or operand) re-embeds a whole prior ternary's text verbatim each
   time. Fixed the same way ADD/SUB's own register accumulator already
   guards identical growth just above in the same dispatch: past a
   length budget, materialize to a temp instead of re-embedding text.
2. (own bug) The six flag-specific CMOV variants (CMOVS/NS/O/NO/P/NP --
   never mapped, same as CMP_OPS/SETcc's dicts) spliced a bare `'?'` in
   as if it were a comparison operator: `(A ? B ? C : D)` parses as `A ?
   (B ? C : D)`, silently missing the OUTER ternary's `:` -- invalid,
   and the missing else swallows whatever text follows, cascading into
   unrelated LATER statements too (`NavmeshBase.cs`, a two-cmov chain
   ~15 bytes apart, no loop involved -- the "8-deep nesting" first
   suspected was two independent instances of this bug sitting next to
   each other, not iteration). Fixed: render the whole condition as
   `unknown` (this codebase's existing syntax-safe undecodable-value
   placeholder, `decompiler.py`'s `_rewrite_unknowns`) instead of
   splicing a second `?` in.
3. (PRE-EXISTING, newly exposed) The conditional-BRANCH handler (not
   CMOV -- a few lines above it) has the IDENTICAL `op, '?'` splice bug
   for its own six unmapped jump variants (JS/JNS/JO/JNO/JP/JNP) --
   never triggered before because nothing produced a ternary-shaped
   `self.flags` operand reaching a rare jump until CMOV started doing
   so. Fixed the same way (whole condition -> `unknown`).
4. (PRE-EXISTING, newly exposed) `strip_outer()` strips ANY redundant
   outer paren layer, including one protecting a top-level ternary --
   safe at its five genuinely statement-level call sites (`var v =
   EXPR;` / `return EXPR;`), unsound at the SIXTH (the conditional-
   branch builder, which embeds the stripped text as an OPERAND of a
   new comparison: `(cond ? a : b) <= null` un-parenthesizes to `cond ?
   a : (b <= null)` once stripped -- `?:` binds looser than everything).
   Fixed generally (protects all six call sites, not just the risky
   one): refuse to strip when doing so would expose a top-level `?`/`:`.
5. (PRE-EXISTING, newly exposed) `decompiler.py`'s `_unsafify()` (the
   `*(E)` -> `((byte*)E)[0]` raw-pointer-syntax converter) has a guard
   against converting an `inner` that "looks like an assignment" --
   `re.search(r'[=;]', inner)` -- but that also matches the `=` INSIDE
   `==`/`!=`/`<=`/`>=`, so any dereference target containing a plain
   comparison (a CMOV-derived ternary's condition) silently skipped
   conversion, leaving the raw `*(...)` form, which is a genuine parse
   error whenever the bracket-matched inner isn't a bare identifier
   (`XmlWriterSettings.cs`, bisected down to the minimal failing case,
   `*(obj6 + 0x0);` alone). Fixed: only a real assignment operator or a
   statement-terminating `;` should block conversion, not any bare `=`.
6. **UNLOCATED.** A sixth shape, `while (v178 - 0x1 ? 0);` /
   `if (!((num1 >= obj12 ? obj12 : num1) ? 0))`
   (`DebugLogManager.cs`, `BaseListViewController.cs`,
   `TransactionManager.cs`), matches fix #2/#3's signature exactly (a
   bare `?` spliced as an operator) but is NOT coming from either fixed
   site: live-hooked every `CONDITIONAL_BRANCH`+`NEAR_BRANCH64`
   instruction in the affected method and found zero with an unmapped
   op, and the raw pre-`_structure` Lifter output for that method
   contains no `?` character anywhere at all -- yet the shape is ALREADY
   present by the very first `_structure` pass (`_resolve_labels`).
   Something in the CFG-to-statement / loop-condition synthesis path
   (`decompiler.py`, not `il2csharp.py`) independently builds a similar
   condition text and has the same class of bug, not yet found. All
   three examples cleared with zero new bad nodes once CMOV modeling was
   reverted (confirmed live, all 5 affected methods re-checked) --
   whatever triggers it only manifests via a ternary-shaped register
   value, so it's real but dormant without CMOV.

**Decision: reverted the CMOV modeling itself** (back to the original
bare `return`, `CMOV_OPS` dict removed). Justification, not just
caution: three rounds of live-trace-fix-full-corpus-rebuild each found a
NEW distinct bug rather than converging, culminating in a sixth,
unlocated one in an entirely different file (`decompiler.py`'s condition
synthesis) that a fourth round would be needed just to FIND, let alone
fix and validate. That's a different shape of problem than every prior
batch in this file -- not "one root cause, prove it, ship it" but "a
previously-unexercised code path (ternary-valued registers) turns out to
interact with an unknown number of assumptions across two files" -- and
per this project's own standing practice (the struct-return/sret gap,
the `ComputedStyle` reaching-definition gap), that shape gets scoped and
deferred with a real design pass, not forced through on an ad hoc
whack-a-mole basis against a 116k-method corpus's worth of edge cases.

**Kept: the three independently-verified fixes (#3/#4/#5 above), since
none of them depend on CMOV being enabled** -- each is a real bug in
shared, widely-used code (the conditional-branch handler, `strip_outer`,
`_unsafify`) whose trigger condition (a ternary-shaped value reaching
that code) is not itself CMOV-specific, and each was individually
verified via an isolated tree-sitter parse before being kept. With CMOV
reverted, re-checked all five methods that had regressed -- zero bad
nodes in all five (`SequenceNode.cs` correctly returns to its ORIGINAL
2-MISSING state, not a new one).

**Validation** (full bar, both for the reverted attempt at each stage
and the final kept state):
- Live re-lifts at every stage: the original bug (confirmed, VA
  0x18239D8B0), each of the 3 kept fixes in isolation (tree-sitter parse
  of the minimal failing shape, 0 bad nodes each), and all 5
  regression-then-reverted methods re-checked clean with CMOV off.
- Full-corpus crash sweep run 4 times across the investigation (once per
  major code state): 116,178 methods, 2 crashes every time, byte-
  identical to the documented baseline throughout.
- Full rebuilds: `b27_out1` (CMOV attempt, first cut) gated **110 bad /
  37,471 ERROR / 76 MISSING** -- caught immediately, not shipped, not a
  scoped spot check that would have missed it; reaped, not kept (a
  known-broken intermediate, not a valid A/B reference). `b27b_out1` (final,
  CMOV reverted + 3 kept fixes): 11,107 files, 115,658 bodies, 0 failed
  (747.6s). Gate: **13 bad / 8,148 ERROR / 4 MISSING** -- byte-identical
  bad-file list and MISSING count to `b26_out1`'s 13/8,150/4 (the
  TextMeshPro.cs ERROR count wobbles by 1, an already-excluded legacy-
  lift-path artifact file, same class of noise seen between other
  batches' rebuilds of that file, not a regression). Brace audit: 0
  unbalanced, 11,107 files. `b27b_out1` is a verified, gate-neutral,
  crash-clean candidate to promote over `b26_out1`; promotion is left
  for a human call (§0/§6) per the standing convention.

Next-session leads, ordered by expected payoff:
1. **Resume CMOV modeling as its own dedicated project**, not a drive-by
   fix. Suggested shape: (a) first FIND bug #6 above (instrument
   decompiler.py's loop/condition-synthesis code the same way `_insn`
   was live-hooked here) so the full defect set is known before
   re-attempting; (b) build a small hand-written unit-test harness for
   "a ternary-shaped Expr flows through arbitrary later text
   processing" the way `test_dead_locals.py`/`test_dead_copies.py` did
   for batch 25's liveness closure, since this class of bug (ternary
   text reaching code that assumes a simple atom) is clearly not fully
   enumerable by live-tracing one corpus's worth of examples; (c) only
   then re-apply the CMOV `_insn` change (already written and reverted
   here, in this session's history) and re-run the full validation bar.
2. The read-before-def `byte*-deref-base` root cause from batch 26 is
   STILL the CMOV gap above -- e.g. `AddRandomVelocity.Update`'s
   hidden-struct-return case may or may not be a cmov-adjacent pattern,
   not reconfirmed this batch. Worth a fresh look once CMOV modeling is
   real.
3. Batch 26's other leads (`SequenceNode.cs` is now root-caused but NOT
   fixed -- don't re-open item 2 from §0h as "unknown", it's item 1
   above now) and batch 25's leads (§0g) remain untouched, EXCEPT: §0g's
   lead #1 (the 986 residual `scan_dead_cycles.py` hits) is now [x]
   CLOSED (see §0g itself, updated post-batch-27 session) -- 100%
   scanner false positives, `work/scan_dead_cycles2.py` confirms 0
   genuine mutual cycles tree-wide, batch 25's fix is fully effective.
   Also [x] **CLOSED, no longer reproduces:** the `_hoist_shared_tails`
   funnel-rule gap (batch 23's lead, §0g/§0e -- `ControllerLayoutMenu`'s
   "~30-level pyramid", CLAUDE.md's "no code between... every sibling
   `else` arm ends in flow-break" predicate suspected of missing an
   implicit-empty-else shape). Checked both originally-named example
   files directly: `ControllerLayoutMenu.SetupKeysFromCurrentLanguage`
   is now fully flat (no nesting, no `if (x == null) goto SHARED;`
   funnel at all -- every `GetMiscText` call is a plain top-level
   statement); `NuisanceCustomer.cs` has exactly one `== null` check
   tree-wide, no funnel pattern either. A corpus-wide scan for the
   pattern (`raise_NullReferenceException` density, the funnel's shared
   target) found max nesting depth ~10 at the worst files
   (`System.Data`'s `*Storage.cs` family), not the ~30 originally
   described. Neither named example reproduces; not investigated further
   -- don't re-open without a fresh concrete repro, this was likely
   resolved as a side effect of an unrelated later fix (batch 24's CFG
   work is the most likely candidate given its timing, not confirmed).
   `ComputedStyle.cs` remains `dup_impure_scan.py`'s worst file (572,
   was 556 at batch 23c) but that's a SEPARATE, already-documented
   false positive (batch 24: legitimate switch-case fan-out, each case
   correctly calling `.Read()`/`.Write()` once -- not the funnel-rule
   shape, don't conflate the two). Also re-measured (same session,
   read-only, no code change): `dup_impure_scan.py` against `b27b_out1`
   -- **34,300 redundant calls** (was 34,513 at batch 23, -0.6%,
   expected: nothing since batch 23c has touched this mechanism).

## 0j. Batch 28 (2026-08-21, decompiler.py's real CONDITIONAL_BRANCH handler had the SAME unmapped-mnemonic gap batch 27 thought it had closed, CLOSED)

Picked up batch 27's own lead #1 ("resume CMOV modeling... first FIND bug
#6"). Before re-enabling CMOV, re-read the fix-#3 description
("conditional-BRANCH handler... fixed the same way, whole condition ->
unknown") skeptically, since this codebase's own history (21c/21d, 21f/
21g) repeatedly shows a fix landing in one of two duplicate code paths and
missing its twin. Grepped both: `il2csharp.py`'s dead `_insn` copy (the
legacy flat-lift fallback only the two TextMeshPro cfg-too-large-cap
methods use) DOES have the fix (`op = self.CMP_OPS.get(mn); if op is
None: emit('if (unknown) goto ...')`, ~3211). `decompiler.py`'s
`exec_block` CONDITIONAL_BRANCH handler -- the REAL path every other
method in the corpus goes through -- does NOT: `op = L.CMP_OPS.get(mn,
'?')` with no check, spliced straight into `'%s %s %s' % (lt, op, rt)`.
Batch 27's fix #3 never touched this copy at all; the writeup's claim
that it did was wrong (an easy mistake to make: CMOV -- fix #2's target --
IS in decompiler.py, right next to this handler, so it's easy to
conflate "fixed CMOV's copy of this bug" with "fixed the branch handler's
copy," which are two different handlers in two different files).

**This is NOT a CMOV-dependent bug** -- it fires for any of the six
flag-specific jump mnemonics CMP_OPS never maps (JS/JNS/JO/JNO/JP/JNP)
regardless of whether CMOV modeling is on. It also doesn't reliably trip
the parse gate the way fix #2/#3's CMOV-adjacent cases did: a downstream
`: default` false-arm synthesis pass silently completes the incomplete
`lt ? rt` into syntactically-VALID-but-confidently-WRONG C#. Confirmed
live (`work/probe_store.py`, fix temporarily reverted for the A/B):
`AudiencePath.SpawnPeople` (VA 0x1804fedf0, a `jp`/parity-flag branch)
rendered `if (!(((byte*)obj33 + 0x18)[0] - 0x1 ? 0 : default))` before the
fix -- a complete, parseable ternary whose "condition" is actually an
unrelated pointer-deref expression and whose branches (`0`/`default`) are
synthesized filler, not the real branch semantics at all.

Fix: mirrored the already-correct dead-copy pattern -- `op =
L.CMP_OPS.get(mn)` (no default), and on `op is None` set `b.cond =
'unknown'` directly (skipping the boolean-test/null-handling logic below,
which assumes `op` is a real comparison operator) instead of falling
through to the splice.

**Scope**, measured with a new standalone scanner
(`work/scan_unmapped_condbr.py`, monkey-patches `Lifter.CMP_OPS` with a
dict subclass that logs every `.get()` miss without touching source --
same non-invasive-probe pattern as `probe_nullcond.py` in §0c): 510
hits / 170 methods in Assembly-CSharp scope; **11,980 hits full-corpus**
(5,446 JP + 4,604 JS + 1,906 JNS + 24 JO -- concentrated in mscorlib's
string/XML/collation algorithms, `SmallXmlParser`/`SimpleCollator`/
`MSCompatUnicodeTable` etc., which lean on parity/sign flag checks for
their byte-comparison inner loops).

**Validation** (full bar):
- Live re-lifts: `AudiencePath.SpawnPeople` and `WFX_Demo.OnGUI` (VA
  0x18052aa60, a JS/JNS-heavy method) both went from the malformed
  synthesized-ternary shape to `if (!(unknown))` / `num3 = unknown ? ... :
  ...` -- honest, always-parses, matches the dead copy's already-proven
  pattern exactly.
- Full-corpus crash sweep (`work/sweep_crash.py`): 116,178 methods,
  674.9s, **2 crashes, byte-identical to the documented baseline** (the
  two pre-existing TextMeshPro/TextMeshProUGUI cfg-too-large caps).
- Full rebuild (`work/run_build_b28.py` into `b28_out1`): 11,107 files,
  115,658 bodies, 0 failed, 530.7s.
- Gate (`work/treesitter_gate.py`): **13 bad / 8,148 ERROR / 4 MISSING
  (`b27b_out1`) -> 13 bad / 14 ERROR / 0 MISSING (`b28_out1`)** -- same 13
  filenames both times (confirmed by hand; `work/gate_diff.py` misparsed
  the older report's different column format as "0 files," a tooling
  quirk not a real discrepancy -- don't trust its "A files 0" output
  without checking the raw reports match up first). Every remaining
  error/file is an ALREADY-DOCUMENTED, unrelated pre-existing family,
  confirmed by reading each row directly: `RenderGraphPass.cs` (2, the
  `_mem_lvalue` base/index-swap family, todo.md's own §0e/§2 #9), seven
  files' `return *N == ...;` (the deref-base-folded-to-a-constant family,
  flagged since batch 20), `TextMeshPro(UGUI).cs` + `SequenceNode.cs` (the
  L1-header whole-file-span artifact row), `NodeLink2.cs`'s `56 = "..."`
  (the register-name-leak row, flagged since batch 20b). TextMeshPro.cs
  dropped from ERROR=4389/MISSING=1 and TextMeshProUGUI.cs from
  ERROR=3735/MISSING=1 to a single L1-header row each -- both are the
  "one unparseable line cascades over a whole file" effect CLAUDE.md
  warns about (their giant `GenerateTextMesh` methods are JS/JP-heavy;
  one bad splice was corrupting parse recovery for the entire rest of the
  file). **`SequenceNode.cs` also dropped its 2 MISSING to 0** -- checked
  directly whether this meant batch 27's still-open CMOV lead had
  incidentally been fixed: it has NOT. `SequenceConstructPosContext`'s
  ctor in `b28_out1` still renders `this = node; obj5.firstpos =
  firstpos; obj5.this_ = lastpos; obj5.firstpos = 0; obj5.lastpos = 0;`
  -- syntactically valid (so no more MISSING node) but semantically wrong
  in exactly the way batch 27 root-caused (CMOV silently dropped, stale
  values survive). **Don't re-close batch 27's lead #1 based on this gate
  number moving** -- the underlying bug is unchanged, only its gate
  visibility is.
- Brace audit (`work/tree_brace_audit.py`): 0 unbalanced, 11,107 files.

`b28_out1` is a verified, gate-clean (only pre-existing/documented
residue), crash-clean candidate to promote over `b27b_out1`; promotion is
left for a human call (§0/§6) per the standing convention.

Next-session leads, ordered by expected payoff:
1. **CMOV modeling is still the right next big swing** (batch 27's lead
   #1, unchanged) -- this batch fixed a DIFFERENT bug found while
   re-checking batch 27's own claims, not bug #6 itself. Bug #6 (the
   still-unlocated `decompiler.py` condition-synthesis-side `?`-splice,
   §0i) has NOT been searched for yet this session; do that first if
   resuming CMOV, per §0i's (a)/(b)/(c) plan -- and given THIS session's
   finding, explicitly re-verify any "fixed both copies" claim by
   grepping both files directly rather than trusting the writeup, before
   moving on.
2. **Audit for other instances of the same "fix landed in the dead
   `il2csharp.py` copy, not the live `decompiler.py` copy" mistake.**
   This is now the SECOND time it's happened for this exact handler
   pairing (batch 27's fix #3 for the branch handler, now confirmed
   incomplete) and the general pattern (21c/21d, 21f/21g) has recurred
   at least four times total across the project's history. Worth a
   dedicated grep pass: every `CMP_OPS`/`SETcc`-style dict or idiom-
   specific helper referenced from `il2csharp.py` should have its
   `decompiler.py` counterpart checked side-by-side, not assumed.
3. Batch 27's leads #2/#3 (read-before-def's `byte*`-deref-base root
   cause, and the fully-closed/no-longer-reproducing items) are otherwise
   unchanged -- see §0i.

## 0k. Batch 29 attempt (2026-08-21, CMOV resume test -- STRONG PROGRESS, NOT SHIPPED, one repro left to trace)

Same session as batch 28, picked up its own lead #1 immediately: tested
whether batch 28's decompiler.py fix also closes batch 27's unlocated
"bug #6" before committing to the full CMOV resume plan's (a)/(b)/(c)
steps. It's a strong yes, with one new loose end found late.

**Reconstructed batch 27's CMOV-as-ternary patch** (`dst = cond ? src :
dst`, a new `CMOV_OPS` class dict mirroring `CMP_OPS`/SETcc's op set, the
six flag-specific variants -> `unknown`, and a length-budget growth guard
mirroring ADD/SUB's -- not necessarily byte-identical to whatever batch 27
actually tested, since that patch was never saved to a work/patch_*.py
file, but built independently from the same design description in §0i).
Applied it to `il2csharp.py`'s `_insn` (the single shared dispatch both
the dead flat-lift path and decompiler.py's real `exec_block` route
through for CMOV specifically -- unlike CONDITIONAL_BRANCH, CMOV itself
was never duplicated).

**Validation, in order:**
1. `work/probe_cmov6.py` (new): re-lifts every method in the three files
   batch 27's bug #6 was tied to (DebugLogManager.cs,
   BaseListViewController.cs, TransactionManager.cs) and scans for the
   unmatched-`?` signature. 108 methods, 0 crashes, **0 hits** -- and
   spot-checking confirmed CMOV is genuinely firing in these files
   (`BaseListViewController.Move`: `(index <= newIndex ? newIndex :
   index)`, a min/max-style CMOV ternary embedded in a comparison,
   structurally identical to batch 27's own bug-6 quote), not just
   silently inert.
2. Full-corpus crash sweep with the patch active: 116,178 methods, 689.0s,
   **2 crashes, byte-identical to baseline** (the two pre-existing
   TextMeshPro cfg-too-large caps).
3. `work/scan_cmov_full.py` (new): full-corpus re-lift scanning every
   line for the same unmatched-`?` signature (string/char-literal-aware,
   after an early literal-unaware pass produced ~196 false positives, all
   literal `?` characters in path-prefix/CSS-shaped string content) AND
   for any line over 500 chars (a growth-guard proxy). Clean result: **2
   raw hits, both a pre-existing unrelated comment string
   (`/* store into untracked ?addr elided */`) containing a literal `?`,
   not a real malformed shape; 3 long-line hits, all independently
   confirmed via direct disassembly to contain ZERO CMOV instructions**
   (pre-existing shapes -- one is a 4-call `FindConversionOperator(...) !=
   null ? ... : ...` fallback chain, unrelated to CMOV's own growth guard).
4. **The original motivating case**, `SequenceNode.ConstructPos` (VA
   0x18239d8b0, NOT the ctor at 0x18239d840 one byte before it -- got this
   wrong on the first pass, the ctor's own separate bug, still present, is
   unrelated to CMOV; see below) -- re-lifted clean: `(((byte*)obj26 +
   0x0)[0] == obj27 ? obj26 : 0)` where batch 27 found a bare-integer
   lvalue (`56 = ...;`) before.
5. **Full rebuild** (`work/run_build_b29.py` into `b29_out1`): 11,107
   files, 115,658 bodies, 0 failed, 612.9s.
6. **Gate: 13 bad/14 ERROR/0 MISSING (`b28_out1`) -> 5 bad/6 ERROR/0
   MISSING (`b29_out1`)** -- BETTER than the already-clean batch-28
   baseline. Two families flagged unsolved since batch 20 both fully
   cleared: the `return *N == ((byte*)this + 0xM)[0];` deref-base-folded-
   to-a-constant family (7 files: MemberHolder.cs, EnumDataUtility.cs,
   RefreshPropertiesAttribute.cs, BaseProcessor.cs,
   DataRelationPropertyDescriptor.cs, DataColumnPropertyDescriptor.cs,
   BindingRestrictions.cs) and `NodeLink2.cs`'s `56 = "PointGraph..."`
   register-name-leak row -- both were this same stale-CMOV-value bug all
   along, not the separate mechanisms the backlog guessed at.

**But: gating `b29_out1` also found ONE NEW bad row**, not present in
`b28_out1`: `Obi/ASDF.cs`'s `<_Build_d__3>.MoveNext` (VA 0x181f25690)
renders `((unknown >= unknown &obj37 : &obj35))[(num2 < 4 ? num2 : (num2 -
0x4))] = obj49;` -- a nested ternary that lost its own `?` somewhere
downstream of the CMOV dispatch (NOT batch 27's fixes #2/#3, both
independently reconfirmed unaffected by this repro). Not traced this
session -- ran out of time as the session was winding down, and per this
project's own standing rule (batch 27 itself, the struct-return/sret gap,
`ComputedStyle`), a live-untraced regression does not ship no matter how
good everything else looks.

**Decision: reverted the CMOV modeling again**, back to the bare `return`
(kept the new `CMOV_OPS` class dict, unused but harmless, so the next
session doesn't have to re-derive it). `b28_out1` remains the gated
baseline; `b29_out1` is kept on disk as the reference build for the one
open repro (do not reap it, do not promote it). Re-verified post-revert
that batch 28's own fix is intact (`AudiencePath.SpawnPeople` still
renders `if (!(unknown))`).

**This is a MUCH better position than batch 27 left CMOV in**: one
sharply scoped repro (VA 0x181f25690, exact malformed text known) instead
of an open-ended "somewhere in decompiler.py's condition synthesis, not
yet located" search. Next session should very likely be able to ship CMOV
modeling outright rather than re-run the full resume plan (a)/(b)/(c) from
scratch.

Next-session leads, ordered by expected payoff:
1. **Trace VA 0x181f25690 live** (`Obi.ASDF+<_Build_d__3>.MoveNext`,
   `work/probe_store.py 0x181f25690` with the CMOV patch reapplied --
   the exact reconstruction is inline in `il2csharp.py`'s CMOV TODO
   comment/this section, not saved to a separate patch file). The shape
   (`unknown >= unknown &obj37 : &obj35` -- condition renders, then jumps
   straight past what should be `?` into the true/false arms) smells like
   a downstream text pass (a `_fix_select`-family colon/select-mark
   handler, given the `: default` synthesis machinery already documented
   as operating in this exact neighborhood) mishandling a nested ternary
   whose OWN condition is itself `unknown`-valued -- but that's a
   hypothesis, not yet confirmed; trace it before assuming.
2. Once #1 is fixed and re-verified (full bar: this repro clean, the
   other 4 verification steps above re-run, a fresh full rebuild+gate),
   ship it as its own batch. Don't skip the full-corpus rescan even though
   most of it already passed once -- a fix for #1 could itself have
   side effects elsewhere.
3. The `SequenceConstructPosContext..ctor` bug noticed in passing (VA
   0x18239d840, one byte before `ConstructPos`) is UNRELATED to CMOV --
   confirmed zero CMOV instructions in its disassembly. It renders `this =
   node; obj5.this_ = lastpos;` (wrong field mapping, an invalid `this =`
   reassignment) from what disassembles as a receiver store plus four
   write-barrier-wrapped field stores (`lea rcx,[rsi+N]; mov [rsi+N],rbx;
   mov rdx,rbx; call write_barrier`) -- looks like a field-offset/receiver
   mismap in the write-barrier path, possibly related to the struct-vs-
   class receiver distinction (`this` reassignment suggests the emitter
   treated a value-type `this` parameter like a reference receiver). Not
   investigated further; a new, separate, real bug, worth a session of its
   own.

## 0l. Batches 29+30 (2026-08-21, CMOV SHIPPED + value-type field offsets, CLOSED)

**Batch 29 -- the §0k CMOV resume, shipped.** Re-applied the ternary
modeling (`dst = cond ? src : dst`, `CMOV_OPS`, flag-specific variants
-> `unknown`, `_mk`'s cap as the growth guard) via
`work/patch_b29_cmov.py`, reconstructed from the §0k design notes with
ONE deliberate difference: **the condition is always parenthesized**
(`((cond) ? a : b)`). Root-causing the b29 blocker first: the
`Obi/ASDF.cs` row (`((unknown >= unknown &obj37 : &obj35))[...]`) does
NOT reproduce with the parenthesized form -- the failed build's bare
`unknown >= unknown ? a : b` spelling lost its select-mark `?` to a
downstream unknowns pass (classified as an unknown operand next to the
placeholder word, then collapsed; the parenthesized head reads as a
value and survives every `_render` stage -- verified by feeding both
spellings and the bare-`unknown`-condition variant through `_render`
directly). Validation: `probe_cmov6.py` 108 methods / 0 hits;
`scan_cmov_full.py` (116,178 methods, 483.8s) 0 crashes beyond the two
TMP caps, 0 genuine malformed shapes (the 2 hits are the known
`/* store into untracked ?addr elided */` comment string; the 3
long-line outliers are the same trio §0k already verified contain zero
CMOV instructions); SequenceNode.ConstructPos (0x18239d8b0) renders
real CMOV ternaries (`((((byte*)obj21 + 0x0)[0] == obj22) ? obj21 : 0)`);
batch 28's own fix intact. Full rebuild `b30_out1` (555.1s): gate
**4 bad / 8,132 / 2 under ts_gate.py -- one better than b29_out1's
5/8,133/2 (the ASDF row itself cleared), everything else identical**.
vs `b28_out1` (13/8,148/4): the `*N ==` deref-base family (7 files),
NodeLink2, and SequenceNode all cleared. `b30_out1` is kept as the
CMOV-only A/B reference.

**Batch 30 -- value-type field offsets (found tracing §0k's lead #3,
the SequenceConstructPosContext..ctor mismap at VA 0x18239d840).**
Ground truth: the struct's 5 field stores at raw [rsi+0..+0x20] were
misnamed one slot off (`obj5.this_ = lastpos; obj5.firstpos = 0;` for
`lastpos`/`lastposLeft`), plus a stray `this = node;`. Root cause, two
ordered bugs in `Lifter._field_expr`: (1) IL2CPP metadata FieldOffsets
for a value type carry the 0x10 boxed-object header, but code accesses
an UNBOXED struct pointer at raw offsets -- the chain's direct-hit
branch ran before the existing valuetype `disp + 0x10` fallback, so
every struct field at raw disp >= 0x10 resolved to the PREVIOUS field's
name; (2) the `kind=='obj' && disp==0` klass-load branch intercepted
`[this+0]` on a struct receiver (an unboxed struct has no header),
dropping the first store -- its write-barrier twin then leaked the
bare `this = node;`. Fixes (`work/patch_b30_vtfields.py`): a
`_recv_is_vt()` helper; for valuetype receivers the chain is probed
ONLY at `disp + 0x10`, and the klass-load branch skips them. Plus
`work/patch_b30_wbvt.py`: `_wb_operands` folds a bare value-typed
address register through `_field_expr(..., 0, ...)` so the barrier's
lvalue matches the plain store and the `_wb_finish` twin dedup fires
(note: `_BARE_TOKEN_RX` only matches temp-shaped tokens, not `this` --
use a plain identifier regex there). Ctor now renders perfectly:
`this.this_ = node; this.firstpos = firstpos; this.lastpos = lastpos;
this.lastposLeft = 0; this.firstposRight = 0;`

Corpus impact of batch 30: 2,428 files changed; `getClass()` reads
**49,442 -> 29,296 (-40.7%)** -- thousands of bogus header-loads on
struct receivers now resolve to the real first field; wrong-name
stores become right-name stores or honest raw derefs (sub-field stores
inside a struct field, e.g. `Vector3.z` within `position`, still render
`((byte*)this + 0x18)[0]` -- naming those needs field-of-field
resolution, honestly raw is correct behavior); raw `((byte*)this + N)`
deref count +1,455 (that honest-raw conversion, sample-verified:
b30's `obj5._obj = Position.getClass();` b31's `this._obj = Obj;`).

Validation of batch 30 (full bar): fresh `scan_cmov_full.py` with the
vt patches (476.0s) byte-identical to baseline (2 TMP crashes only,
same 2 comment-string hits, same 3 long lines); full rebuild `b31_out1`
(554.4s, 115,658 bodies, 0 failed); gate **5 bad / 8,133 / 2**
(b30's 4/8,132/2 + ONE new row: `InputDeviceBuilder.cs:1904`
`num3 * obj9 * obj9[this.m_Device.m_ControlTreeNodes + 4] = ...` --
live-traced via `probe_store.py 0x1825AA5B0`: this is the documented
`_mem_lvalue` base/index-swap family (§0e/RenderGraphPass, "left
as-is; do not attempt a text-level patch"), newly EXPOSED because the
vt fix resolved `m_ControlTreeNodes` (16 sites in that file, 0 before)
into a composite the old wrong-name render kept parseable; the same
method's malformation existed in b30 as a differently-spelled line).
Brace audit 0 unbalanced (11,107 files).

`b31_out1` is the verified gated candidate (CMOV + vt fields);
promotion is a human call per the standing rule. `b30_out1` = CMOV-only
A/B; `b29_out1` = the failed-spelling reference, now only of
historical interest (safe to reap on the next cleanup pass); `b28_out1`
remains the pre-CMOV baseline.

Dual-copy audit (batch 28 lead #2, done this session): both
CONDITIONAL_BRANCH handlers (`il2csharp.py` `_insn` ~3232 and
`decompiler.py` `exec_block` ~702) verified to carry the `op is None ->
unknown` fix; CMOV and SETcc are single-copy (only `_insn`, which both
pipelines share). No further live/dead divergence found in this
handler family.

Tooling note: `work/ts_gate.py` vs the older `treesitter_gate.py`
count different things (nodes vs rows) -- §0k's "5/6/0" and §0j's
"13/14/0" are treesitter_gate numbers; all numbers in THIS section are
ts_gate numbers. Don't mix the two without naming the tool.

## 0m. Batches 31-33 (2026-08-21, 3-operand IMUL + obj_Equality fold + vtable-slot recovery, CLOSED)

**Batch 31 -- the `_mem_lvalue` base/index-swap family, root-caused and
CLOSED (§0c's standing lead, §0l's new gate row).** Live-tracing
`InputDeviceBuilder.AddControlToNode` (VA 0x1825AA5B0) against raw
disasm: the family was never a `_mem_lvalue` role bug at all. The ROOT
CAUSE is that **3-operand `imul dst, src, imm` (MSVC's standard
scaled-index idiom) was lifted as 2-operand** -- no code anywhere
handled operand 2 (`grep A(2)|op2_kind` over both files: zero hits).
The handler used the destination's STALE old value as the left operand
and dropped the immediate: `imul rdx,rcx,7` with rdx previously holding
an array rendered `arr * counter` WITH kind 'arr', and every later
`[rdx + arr + disp]` access mangled (`num3 * obj9 * obj9[...] = ...`,
the exact RenderGraphPass/XmlTextWriter/InputDeviceBuilder rows).
Fixes (`work/patch_b31_imul3.py`): (a) a 3-operand IMUL branch
(`a = reg(op1)`, multiplier from op2, result kind int); (b) a
defensive role swap in `_read_mem`/`_mem_lvalue`'s indexed branches
(base expr int-kind + index expr arr-kind -> swap before the element
fold); (c) `add int-reg, arr-reg` keeps the composite ARRAY-typed so a
later `[r + D]` deref folds to `(arr + idx*S)[k]` element syntax
instead of raw byte-pointer arithmetic (needed `_recv_fold`-style
parens, which `_field_expr`'s arr branch already applies). Verified
live: AddControlToNode renders real array indexing
(`m_ControlTreeNodes[obj10 * 7 + 4]`); RenderGraphPass.SetColorBufferRaw's
malformed store gone. Gate: the InputDeviceBuilder, XmlTextWriter AND
RenderGraphPass rows all cleared.

**Batch 32 -- §3 #5's cosmetic half, closed: `Object.op_Equality/
op_Inequality(A, B)` -> `(A == B)` / `(A != B)`, bare `0` args ->
`null`** (`work/patch_b31_objop.py`, a `_final_text` transform in
decompiler.py; string-literal-aware via `_in_string`, balanced-paren
arg splitting via the new `_split_args`, args containing a `?` outside
a literal get wrapped to protect ternary precedence). Unit-tested
against 10 shapes including `"a,b"` and `a ?? b` args before trusting.
7,254 -> 15 sites tree-wide; all 15 survivors are in the two legacy
flat-lift TMP files that don't run `_final_text` (documented artifact).

**Batch 33 -- the read-before-def 48,409-site VIRT_CALL/indirect lead
(§3 #2's newest finding), sized, designed and shipped in two cuts:**
1. `Il2Cpp.slot_max_arity(slot)` (lazy one-time scan of every typedef's
   vtable): the largest declared arity of any method occupying that
   slot across ALL types -- batch 21j's max-arity proof applied to
   slot-indexed candidates. An unresolved VIRT_CALL's args trim to it
   (`work/patch_b32_slotarity.py`). Measured effect alone: almost nil
   (read-before-def -5) -- the bound is sound but rarely binding,
   because the high-arg population is 98% `vtable slot None`.
2. **The real win: recovering the slot for the `None` cases.** The
   standard IL2CPP dispatch shape `mov rax,[klass+0x138+16N]; ...
   call rax` loads the vtable entry into a REGISTER first; the
   direct-memory call path set `vt_recv_slot` but the register path
   never did -- even though the vtmethod Expr's own text already
   carries the slot (`X.vtable[N]`, kind 'vtmethod'). Fix
   (`work/patch_b33_vtslotreg.py`): regex the slot out of the expr
   text at `call reg`, restore `vt_recv` from `e.recv`. This doesn't
   just re-enable the arity trim -- it lets the EXISTING
   `vtable_method(recv_td, slot)` naming block fire, resolving the
   call to a real named method outright (live repro,
   ControllerLayoutMenu.Apply VA 0x18069F160: `/*vtable slot None*/
   this.sensitivitySlider(this.sensitivitySlider, ...6 bogus args...)`
   -> `this.sensitivitySlider.value * 10.0f` + real named calls).

**Validation (full bar, per cut and final):** full-corpus
`scan_cmov_full.py` after each Lifter-side change -- 116,178 methods,
2 crashes (the TMP caps) every time, 0 genuine malformed shapes (the
long-line proxy grew by one legit nested-ternary dispatch chain,
LightCompiler.CompileArithmetic -- parses fine). Full rebuilds:
`b32_out1` (imul3+swap+addfold+objop, 533.6s) gate **2/8,125/2**;
`b33_out1` (+slot-arity, 524.2s) gate 2/8,125/2, rbd 273,016 -> 273,011;
`b34_out1` (+slot recovery, 636.8s) gate **2/8,125/2**, brace 0,
rbd **242,822 (-11.1% vs b32)**, `vtable slot None` 4,454 -> 51,
vtable-slot lines 17,156 -> 1,409 (the rest now named calls),
`getClass()` 29,296 -> 15,710.

`b34_out1` is the verified gated candidate; promotion is a human call.
Tooling note for A/B: `b32_out1` = pre-slot-arity, `b33_out1` =
slot-arity-only; reap `b29_out1`/`b30_out1`/`b31_out1` on the next
cleanup pass if disk is tight (b28_out1 stays as the pre-CMOV
baseline).

## 0n. Batch 35 (2026-08-21, sret RAX echo binding + field-map statics filter, CLOSED)

Picked up §0's own #1 lead (read-before-def's remaining 242,822, byte*-
deref-base split). Three fixes shipped, all in `il2csharp.py`
(`work/patch_b35_sretreg.py`, `patch_b35b_staticfields.py`,
`patch_b35c_sretsize.py`), plus the classification work that sized the
next lead.

**35a -- the sret RAX echo, root-caused and closed.** Re-classified
b34's 110,355 "other" bucket one level deeper (`work/rbd_misc_split.py`,
`rbd_shape_split.py`, new): indirect-call-arg 23,668 / sub_-call-arg
19,604 / no-call-shape 17,029 / shared-body 11,873 / new-arg 7,034 /
vtable 1,442; and byte*-deref-base (13,956) by deref offset: 11,738 at
+0x0 alone. Live-traced three methods against raw disasm
(`work/probe_rawlift.py`, new -- tees the per-block `_Sink` to dump
the Lifter's pre-structure statements with raw t/v/s names):
ActorCOMTransform.Update (VA 0x1805135E0, the `TransformPoint` case),
AddRandomVelocity.Update (0x180513900, §3 #2's own ground truth --
where the note claimed the sret fold "never fires", it demonstrably
DOES fire today: `s_20 = Random.get_onUnitSphere();`), and
AudiencePath (0x1804FDEC0, the property-getter variant
`obj41 = obj40.transform.position; real1 = obj41.x;`). The fold was
never the gap. The REAL bug: `_call`'s struct-return fold emits
`s_N = Foo(...)` and `return`s without rebinding RAX -- but the Win64
sret ABI echoes the hidden buffer pointer back in RAX and MSVC callers
read the result through it (`movsd xmm1,[rax]`). `_fresh_unknowns` at
the call had already minted a `vN` for the popped RAX, so every member
read rendered `*(v80 + 0x0)` lifter-side, `((byte*)obj11 + 0x0)[0]`
tree-side -- the undefined-temp family. Fix: bind
`self.regs['RAX'] = Expr('&%s' % buf, rty, 'ptr')` in the fold, and
teach `_field_expr` to normalize a `&s_N` base onto the existing
kind-'local' slot path (member resolution via `slot_types` +
`field_offset_map` with the 0x10 boxed header) when the slot's type is
a value type. Loads AND stores both route through `_field_expr`, so
one normalization covers both.

**35b -- statics polluting the instance field maps.** First live
re-lift rendered `[rax+8]` as `s_40.upVector` -- wrong. Root cause:
`Il2Cpp.field_offset_map` / `instance_field_chain` enumerate ALL
fields including STATICS, keyed by their `__static_fields`-blob
offsets, which collide with instance offsets; `field_offset_map` is
last-wins so Vector3's instance `z@0x18` was silently overwritten by
static `upVector@0x18` (the chain is first-wins, same hazard when a
static precedes an instance field in metadata order). Filter
FA_STATIC/FA_LITERAL rows in both builders (`field_attrs`, the batch-
21a accessor); all three consumers (local-slot members ~3139,
instance chains ~3164, valuetype array elements ~4047) want instance
fields only. Vector3's maps now read exactly {0x10:x, 0x14:y, 0x18:z}.

**35c -- size guard, found by the rebuild's own artifact check.**
b35_out1 (35a+35b only) introduced 7 `if (&s_890 != 256)` renders
inside the two legacy-TMP flat-lift files (b34: 0 sites -- checked
before assuming pre-existing, per this file's own rules). MSVC x64
returns structs of size <= 8 IN RAX by value, no hidden buffer --
binding those to `&s_N` invents a pointer. Guard: bind only when the
valuetype's instance field chain has a field at boxed offset >= 0x18
(spans past 8 bytes = sret). Vector3 binds; Vector2/single-field/
empty structs keep the pre-35a fresh-unknown render. b35_out2 = the
guarded build; the 7 invented pointers are gone (0 sites).

**Validation (full bar):** full-corpus `scan_cmov_full.py` after
35a+35b AND after 35c: 116,178 methods, 452.7s / 495.5s, **2 crashes
both times = the pre-existing TMP cfg-too-large caps** (the 2
"bad-shape" hits are `?` inside a `/* store into untracked ?addr
elided */` COMMENT -- the detector strips literals but not comments;
both lines exist verbatim in b34). Rebuilds: `b35_out1` 679.5s,
`b35_out2` 492.6s, both 11,107 files / 115,658 bodies / 0 failed.
Gate b34 2/8,125/2 -> b35_out2 **2/7,924/2** (same two TMP files,
ERROR -201 confined to them, 0 newly bad / 0 cleared -- the gate's
bad-file set is exactly those two files, so no other file gained or
lost a parse error). Brace audit 0 unbalanced. Census:
read-before-def 242,822 -> 234,460 (-3.4%), byte*-deref-base 13,956
-> 6,368 (-54%, the +0x0 slice 11,738 -> ~4,900), copy-rhs -373,
`.upVector` leak 1 -> 0, `if (&s_` 0 -> 0, and **854 fewer methods
carry an `unsafe` wrapper** (39,454 -> 38,600) because their raw
byte-pointer arithmetic became member reads. Residual deref-base
(~6.4k) is other raw-pointer patterns: untyped interface-call results,
native pointers, `+ num*8 + 0x20` array-element addressing.

**Also sized this session (not fixed): the indirect/interface-dispatch
family.** 14,227 `/*indirect*/` call lines in b34. The GameManager
ground truth (VA 0x1806DF770): `obj32 = (((byte*)obj31 + i*8 + 0x8)[0]
<< 4) + 0x138 + ((byte*)obj5 + 0x0)[0]; obj33 = ((byte*)obj32 +
0x0)[0]() /*indirect*/(obj5, ((byte*)obj32 + 0x8)[0], obj34, obj35);`
-- that is IEnumerator.MoveNext() through il2cpp's interface-offset
table walk (the `typeof(IEnumerator)` comparison loop renders right
above it; `[obj32+8]` is the VirtualInvokeData method arg; obj34/obj35
the stale spray). 5,570 lines are the simpler direct shape (constant
klass+0x138+16*slot -- slot recoverable from text, batch-33 style);
2,145 lines in 555 files are the interface-offset shape. Recorded as
§0 lead #1.

`b35_out2` is the verified gated candidate; promotion is a human
call. b35_out1 kept for A/B (the unguarded binding).

## 0o. Output-quality census (2026-08-21, post-batch-35 assessment)

Read b35_out2 end-to-end at a user's request ("read the current output
and see how we can improve") -- one qualitative pass over real game
code (BabyDoll.cs end-to-end, GameManager, InventoryManager samples)
plus fresh tree-wide counts (`work/`-style ad-hoc greps; ugrep on this
box mangles `\s`-anchored patterns, count with Python). Everything
below is AT b35_out2.

**What reads well now:** gate/brace clean, declarations + usings +
field offsets correct (batch 21a), calls named with true arity
(batches 21j/33), property sugar, sret member reads (batch 35). The
old §2/§6 honesty debts mostly evaporated without anyone noticing
WHEN: `: default` 4,929 -> **9**, `?addr` ~1.9k -> **10**,
`&s_` call-arg lines ~450 -> 495 (stable), `sub_`/*shared body*/
markers remain honest by design (17,592 / 51,741 total `sub_` refs).

**Fresh counts, the improvement surface:**
- `((byte*)` raw-pointer lines: **201,710 in 4,872 files** (272,233
  occurrences) -- overwhelmingly const-offset member access
  `((byte*)X + 0xN)[0]`, ~9.7k indexed-element, rest other. Worst
  assemblies: Unity.Mathematics 27,153 / UIElementsModule 18,406 /
  mscorlib 14,928 / InputSystem 13,032 / System.Xml 11,940 /
  Assembly-CSharp 9,680 / Obi 8,633 / Fusion.Runtime 8,528.
- Pure `objN = objM;` copy lines: **171,199 (3,717 files)**;
  `objN = this;` 2,143 (611 files). (The read-before-def copy-rhs
  bucket, 70,612, is the undefined-temps subset of this population.)
- Duplicate impure renders (`dup_impure_scan.py`): **32,754 redundant
  calls** / 22,116 distinct exprs / 11,789 methods / 2,886 files --
  was 34,513 at b23c, i.e. backlog #4 has barely moved since 23c.
  Worst: SDK.cs 724, ComputedStyle.cs 577, ProbeReferenceVolume.cs
  373, XsdBuilder.cs 313, FastTouchscreen.cs 302.
- Pointer-typed locals (`T* objN = ...` declarations): 1,599 (410
  files). Generic-T leaks (`Enumerator<T> obj12`): 531 (219 files).
- `getClass()` reads 15,737 (stable since b34).

**Qualitative ground truths (BabyDoll.cs, Assembly-CSharp):**
- `Rpc_ChangeHittableHealth` (RVA 0x60A690 VA 0x18060A690): the
  pointer-member root cause of lead #1 -- `obj10 =
  SimulationMessage.Allocate(...)` (return type KNOWN, the local even
  declares `SimulationMessage* obj10`), then `((byte*)obj10 + 0x24)
  [0] = real1;` and `((byte*)obj10 + 0xc)[0] = 96;` stay raw because
  `_td_of` can't unwrap PTR/BYREF tuples. Same method carries TWO
  backlog-#4 duplicate calls (Allocate, HasAnyActiveConnections) and
  a dead `flag1` binding.
- `Start()` (VA 0x18060C2B0): the
  try/finally phi-copy shape end-to-end (`finally { obj13.Dispose();
  obj15 = obj18; obj16 = obj19; }` -- all dead), `obj15 = this;`
  call-through-copy chains, `Enumerator<T>` leak, and the foreach
  still mangled into `while (obj9.MoveNext())` with `obj13 = &obj9`
  aliasing (the enumerator-alias bug is its own deep shape -- the
  byref'd enumerator and its user print under different names).
- Polish instances: `this.InvokeRpc = 0;` (bool), `this._runner.Stage
  != 4` (enum) -- backlog #5's cosmetic half, live in the same file.

**Payoff order** = §0's leads list (pointer members -> copy-prop ->
impure dedup -> indirect dispatch -> polish). The pointer-member fix
is the recommended next batch: biggest line count, the mechanism
shipped in batch 35, and a located static root cause. Size the
typed-base slice first (§0 lead #1's SIZE FIRST note).

**EPILOGUE 2026-08-21 (batch 36, §0p): all five of this census's
leads were addressed same day.** The typed-base slice measured 2,199
recoverable of ~1.06M sites (the 202k premise was wrong -- it was
overwhelmingly genuinely-untyped bases); pointer members shipped
anyway (`->` renders). Copy-prop shipped (-53.5% of the copy lines).
Impure dedup's root cause shipped (`_bind` render sites; -10.8%).
The indirect trim shipped and measured marginal. The bool/enum polish
shipped. Fresh counts at b36_out2: copy lines 98,928, redundant
calls 29,220, `((byte*)` lines 196,223, read-before-def 212,018.

## 0p. Batch 36 (2026-08-21, five fixes: pointer members, copy-prop, bind sites, indirect trim, bool/enum folds — CLOSED)

Picked up ALL FIVE §0 leads in one session. Every fix was validated
against a live ground truth first, then scoped (Assembly-CSharp ±
Fusion, `scan_cmov_full.py --only`, 0 crashes every time), then the
full bar at the end. Full-build chain: `b36_out1` (all fixes through
38b with the trim's first, loose guard), then `b36_out2` (38c guard
tightening) as the final gated candidate.

**36a — pointer-typed-base member resolution (§0 lead #1, backlog
#10).** The SIZE FIRST census (`work/size_ptrbase.py`, full corpus,
monkeypatched `_field_expr`) DISPROVED the lead's premise: of ~1.06M
raw-deref fallthrough sites, only **2,199 sit on a PTR/BYREF-typed
base whose pointee resolves to a typedef AND whose offset hits a real
field** (the "recoverable" slice); 1,569 are past-struct payload
writes (correctly raw — `SimulationMessage.Allocate` allocates
capacity + sizeof(T), ground truth BabyDoll.Rpc_ChangeHittableHealth
0x18060A690: `[rdi+0x1c]`/`[rdi+0x24]` write the variable-length
payload, `[rdi+0xc]` is the `Offset` field), and 3,409 have
unresolvable pointees (PTR-to-PTR/primitive/generic-param). The ~202k
`((byte*)`-line ceiling is overwhelmingly genuinely-untyped bases.
Shipped anyway (correct, cheap, grounded): `_field_expr`'s
member-resolution site unwraps PTR/BYREF pointees (NOT `_td_of`
itself — it feeds receiver folding/vtable dispatch), valuetype
pointees use the unboxed `disp+0x10` convention, class pointees raw
`disp`, render `base->Field`; past-struct offsets keep the honest raw
deref. 36b: the three consumers gating on `'.' in fe.text`
(`_mem_lvalue`, the LEA byref path, `_wb_operands`) now accept `->`
— the ground truth's `obj10->Offset = 96;` was resolved by 36a and
then DISCARDED by `_mem_lvalue`'s gate until this. 36c: `_has_arrow`
(decompiler.py) adds string-literal-aware `->` detection to
`needs_unsafe`. Tree effect: 2,104 `->` lines (was 127), `((byte*)`
lines -5,487, unsafe-wrapped methods 38,807 -> 38,754.

**37 — `_copy_prop` (§0 lead #2, backlog #3): the biggest statement
win.** New decompiler pass after `_singleton_cse`, before
`_drop_dead_locals`: forward substitution of pure local-to-local
copies (`lhs = rhs;` where rhs is a bare local or `this`), then a
backward last-def-dead sweep. Substitutions die at redefinitions of
either side (incl. `++`/`--`/compound/for-headers), `ref`/`out`/`&`
of either side (slot semantics — never substituted into, always
killed), labels/catch/finally joins, flow-break lines, and the `}`
of the recording brace level; the sweep drops a PURE assignment whose
lhs has no literal/comment-stripped text-later read and no text-later
`goto`, never inside a loop-keyword frame (back-edge re-read). The
sweep also kills the per-ASSIGNMENT blind spot `_drop_dead_locals`
has by design (it tracks locals, not assignments): BabyDoll.Start's
`finally { obj15 = obj18; obj16 = obj19; }` dead RE-definitions of
otherwise-live locals. Unit suite `work/cp_test.py`, 20 cases,
built BEFORE trusting live — three pass bugs found by the suite
itself (label detection used the provisional `@@` prefix instead of
resolved `L_` labels — substitutions leaked past jumps; a phantom
read-decrement inverted the backward accounting; string literals
counted as reads). BabyDoll.Start: 7 copy lines → 0. Tree: **pure
copy lines 212,836 → 98,928 (-53.5%)**; the surviving half is
cross-arm phi copies (def doesn't dominate uses), loop-carried
copies, address-taken sources — §0 lead #3.

**38 — `_bind` render-site rewrite (§0 lead #3, backlog #4's ROOT
CAUSE).** Live-traced with `work/probe_bind.py`: the BabyDoll
`Allocate` duplicate was ONE native call rendered twice because at
bind time the +0x1c statement sat in a DIFFERENT block than the
defpos block — `_bind`'s rewrite window only covered the
declaration's own block ("per-block binding", backlog #4's own
words). Fix: `_note_use` records each counted rendering's landing
site (`Expr._sites`), and `_bind` rewrites those sites across blocks
— per EXPRESSION OBJECT (a real second identical call is a different
object and never touched), only in blocks REACHABLE from the
declaration's (BFS over block succs; a path around the declaration
keeps the full text), def-block sites past the 64-line window
included, and cond/ret/switch renders land at `len(stmts)` which no
later stmt occupies (terminal), so they can only match via the
explicit cond/ret/switch rewrite. Decompiler passes `L._blocks` in
`_analyze`. BabyDoll.Rpc_ChangeHittableHealth: the inline `Allocate`
duplicate collapsed to `obj10`. AC-scoped: redundant calls 3,324 →
2,603 (-21.7%). Tree: **32,754 → 29,220 (-10.8%)**, read-before-def
-22,116 (partly this, partly 37 deleting copy statements).
NOT fixed (root-caused, deferred — §0 lead #1 next session): the
flags-cond twin (`if (Call()) ... flag1 = Call();`) — flags state
rematerializes per block entry as concatenated TEXT in a fresh Expr
(`_analyze`'s `'%s%s' % ft`), so the call object never reaches use
#2. That needs the flags-state redesign, not a bind tweak.

**38b/38c — indirect vtable-dispatch arity trim (§0 lead #4's
"at minimum" half).** The dominant `/*indirect*/` family (14,000 of
14,227 lines at b35_out2) is constant-slot vtable dispatch through
an opaque klass chain: `*(*(X + 0x0) + 0xNNN)` where NNN =
0x138 + 16*slot. When the callee text ends in that shape, `_call`
trims the register-spray arg list to `slot_max_arity(slot)` — the
same max-arity-across-all-types bound batches 21j/33 proved sound.
38b's first matcher keyed on the RENDERED `)[0]` form and never
fired at all (the lifter-side text is `*(...)`; found by the b36_out1
census showing avg args unchanged), 38c tightened the structural
guard to the true klass-walk signature (base ends `+ 0x0)` — the
[object+0] klass read — or a folded `getClass()`; native callback
tables like `bounds.m_Center + 0x338` end an identifier and are
rejected). MEASURED MARGINAL: AC avg args 5.21 → 5.10, because
slot_max_arity bounds are loose tree-wide (mx=13 at slot 9 vs
typical 4-9 args). Kept (sound, occasionally fires); the real payoff
is NAMING, which needs the receiver's static type from the adjacent
interface search loop — §0 lead #2.

**39 — bool/enum literal folds (§0 lead #5).** `Il2Cpp.enum_members`
builds value→name maps from the already-parsed `fieldDefaultValues`
table + its data blob (detection: the `value__` instance slot; every
width 1/2/4/8 read so I1/I2/I8-backed enums match). `_fimm`: a 0/1
immediate into a Boolean-typed location renders `true`/`false`
(`this.InvokeRpc = 0;` → `= false;`), an int into an enum-typed
location renders `Type.Member`. The CONDITIONAL_BRANCH render folds
`==`/`!=` against an int literal when the lhs type resolves to an
enum (`this._runner.Stage != 4` → `!= SimulationStages.Forward`) —
39b relaxed both guards to go through `_td_of` (generic-instantiated
enums arrive as GENERICINST 0x15, not 0x12). The 531 generic-T leaks
and 1,599 `T* objN` declarations were left alone deliberately
(§0c: enclosing-method unresolvable-T shapes; pointer decls are
correct C#).

**Validation (full bar):** syntax-check before every run; scoped
`scan_cmov_full.py --only Assembly-CSharp,Fusion` after every fix
(0 crashes / 0 bad shapes each time); unit suite for 37 (20/20);
full-corpus crash sweep AFTER all fixes: 116,178 methods, 578.6s,
**2 crashes = the pre-existing TMP cfg-too-large caps, 2 bad-shape
hits = the documented `?`-in-comment false positives, byte-identical
to baseline**. Builds: b36_out1 636.2s, b36_out2 682.1s, both 11,107
files / 115,658 bodies / 0 failed. Gate (ts_gate.py, b35_out2 re-run
for a clean A/B): b35_out2 2/7,924/2 -> b36_out1 2/7,919/2 ->
b36_out2 2/7,919/2, `gate_diff` all-zero both steps. Brace audit:
**0 unbalanced (11,107 files)**. Censuses (b35_out2 -> b36_out2):
read-before-def 234,460 -> 212,018 (-9.6%), pure copy lines 212,836
-> 98,928 (-53.5%), duplicate impure renders 32,754 -> 29,220
(-10.8%) / 22,116 -> 19,257 distinct, `((byte*)` lines 201,710 ->
196,223 (in 5,084 -> 5,074 files), `->` lines 127 -> 2,104,
unsafe-wrapped methods 38,807 -> 38,754, `: default` 9 and `?addr`
10 both unchanged, `/*indirect*/` line count unchanged at 14,179
(the trim shortens arg lists, it does not remove lines).

**Method / new tooling under work/:** `size_ptrbase.py` (lead-#1
SIZE FIRST census, monkeypatched `_field_expr`, full corpus),
`probe_ptrbase.py` / `probe_fe_trace.py` (type-layout + `_field_expr`
I/O traces), `probe_bind.py` (bind-time defpos/sink trace -- found
the cross-block gap in one run), `probe_flag.py` (flags-cond duplicate
trace, kept for the §0 lead #1 resume), `cp_test.py` (`_copy_prop`
unit suite), `census_b36.py` (the before/after tree census), the
applied patches `patch_b36_ptrbase.py` / `patch_b36b_arrowgates.py` /
`patch_b37_copyprop.py` / `patch_b37b_cpfix.py` / `patch_b38_sites.py`
/ `patch_b38b_indirect.py` / `fix_b38b_form.py` / `fix_b38c_guard.py`
/ `patch_b39_polish.py` / `fix_b39_guards.py` kept as the record,
and `run_build_b36.py`. Trap re-confirmed: Git-Bash heredocs MANGLE
literal `\r\n` escapes in patch scripts (a `\`+literal-`r`+LF landed
in the file) — write patch scripts as files, never heredocs.

`b36_out2` is the verified gated candidate; promotion is a human
call per the standing rule. `b36_out1` kept for A/B (the 38b loose-
guard trim — behaviorally identical except rarer/more-loose trims).

## 0q. Batch 37 (2026-08-22, the flags-cond duplicate-call fix — use-count accounting, NOT a flags redesign — CLOSED)

Picked up §0 lead #1. The lead's own prescription — "carry (lhs_expr,
rhs_expr) objects through end_state instead of text, a flags-state
redesign" — was built on a misread of probe_flag.py's trace ("the je's
note_use consumed a rematerialized lhs"). Re-tracing with a NEW tool
(`work/probe_flag2.py`, which dumps blocks/conds/end_states/phi_copies
past `_analyze`) showed the je consumed the ORIGINAL object: the
`test al,al; je` pair lives in ONE basic block (x64 basic blocks end at
the jcc; the setter and its consumer are adjacent by construction), so
no rematerialization is involved in the dominant shape at all. What the
trace actually showed — uses stuck at 1 across THREE note_use calls at
the SAME ip — was the same-ip guard eating the je's count because
`_cur_ip` never advances for the instructions exec_block handles
itself.

**The real mechanism, three compounding defects:**

1. `decompiler.py::exec_block` handles RETURN / CONDITIONAL_BRANCH /
   JMP itself (only everything else falls through to `L._insn`, which
   is what sets `L._cur_ip`). So every je's `_note_use` ran under the
   PREVIOUS instruction's ip — the flag-setter's — and
   `_note_use`'s same-ip guard (`e._use_ip == self._cur_ip: return`,
   which exists so `test r,r` / `add r,r` double-reads count once)
   silently ate it: no count, no render-site recorded.
2. The counting was split-brained: cmp/test/comiss OPERAND reads
   counted a use at the setter (a non-rendering read — the reg-file
   `__getitem__` counts on every read), while for ARITHMETIC-set flags
   (add/sub/inc/dec, `flags = (result_expr, '0')`) the result expr was
   counted at its consumer (the je). Each side accidentally totaled 1
   for a single render — cmp-set flags counted at the cmp (je
   suppressed by the stale ip), arith-set flags at the je. Fixing
   defect 1 alone would have double-counted every cmp+je pair in the
   corpus and bound a spurious temp for every long comparison operand
   (`if (this.someLongChain == null)` everywhere) — the explosion the
   lead's authors presumably brushed against and misattributed to the
   flags design.
3. `_build_phi_copies` renders each pred's end_state value as BARE
   TEXT (`pb.end_state.get(k).text` — plain dicts, no counting, no
   render sites). The duplicate line `flag1 = obj7.HasAnyActiveConnections();`
   is a phi copy for RAX at the merge block (the call's result survives
   the test/je block in RAX; the RPC-send path leaves a different value
   there; texts differ -> phi -> per-edge copies) — rendered from text,
   it re-called the method in the output although native code calls it
   ONCE (BearTrap.Rpc_Trap VA 0x18060E3D0: call at 0x18060e497, test/je
   at 0x18060e49c/e49e, the merge at 0x18060e513 with `test sil,7`).

**The fix (three hunks, `work/patch_b37_flagcount.py`):**

- **A** — `exec_block` sets `L._cur_ip = ins.ip` at the top of the
  per-instruction loop. Pure bookkeeping correctness; also makes the
  RETURN handler's RAX read and the JMP tail-call argument reads count
  at their true ips.
- **B** — the cmp/test and comiss handlers bracket their operand reads
  with `self._copying = True/False` (the same flag reg-reg moves use;
  it only gates `_note_use`). The setter's reads no longer count; the
  CONSUMER (je in exec_block, setcc/cmov in the lifter) counts the
  comparison text's single rendering. Arithmetic flag results are
  untouched — their operand reads still count (they render into the
  result expression), and their result still counts at the consumer.
- **C** — `_build_phi_copies` runs `_note_use` on each pred's end_state
  Expr before taking its text (sink neutralized to `[]` so the site
  recorded is a dud — the copy text below then reads the temp name
  directly; `L._cur_ip = -1` so the same-ip guard can't eat it). When
  the count hits 2 the bind fires AFTER pass 2: the declaration lands
  at the value's `_defpos` (in-calls it stamped at set_reg time), and
  earlier renders are rewritten through the batch-38 site machinery —
  in particular the declaration block's `b.cond` rewrite (the je's
  terminal render site) turns `!t1000.HasAnyActiveConnections()` into
  `!t1042`.

The accounting invariant after the batch: a value's counted uses equal
its output renderings — flag-setter reads don't count, consumers count
the comparison render, phi copies count one each. Soundness note for
hunk C: a phi-copy source object reached the pred's end_state either by
its own def in that pred or by all-preds agreement at an earlier merge
(both mean the def dominates the copy edge); FLAGS phis are excluded
from copies as before, and end_state values long enough to bind were
necessarily `_stamp`ed in pass 2, so the bind's declaration always has
a real defpos.

**Validation:** two live ground truths first (BearTrap.Rpc_Trap — the
duplicate collapsed to `bool flag2 = obj7.HasAnyActiveConnections();
if (flag2) { ...send rpc... }`, byte-faithful to the disassembly;
BabyDoll.Rpc_ChangeHittableHealth 0x18060A690 — same collapse, and all
8 HasAnyActiveConnections duplicate sites in BabyDoll.cs cleared), a
setcc-path ground truth (ControllerLayoutMenu.OnEnable 0x18069F6D0 —
the OLD cmp+setcc double-count had bound spurious `numN` temps for
single-render `PlayerPrefs.GetInt` comparisons; they're gone, the call
renders inline in `(GetInt(...) == 1 ? 1 : 0)`), then the scoped
AC±Fusion scan (12,972 methods, 0 crashes / 0 bad shapes / 0 long
lines), then the full bar: crash sweep 116,178 methods / 618.5s / 2
crashes = the documented TMP caps byte-identical; build `b37_out1`
1010.8s, 11,107 files, 115,658 bodies, 0 failed, PYTHONHASHSEED=0;
gate (ts_gate.py, fresh same-tool run on `final_out` as the A/B since
b36_out2 was deleted): baseline re-confirmed 2/7,919/2 -> b37_out1
**2/7,298/0** — the same two TMP filenames, MISSING cleared in both,
ERROR -621 (TextMeshPro.cs 4,282->3,652, TextMeshProUGUI.cs
3,637->3,646) — per CLAUDE.md the unchanged bad-file set IS the
per-file diff, and both files are the documented flat-lift pair that
bypasses `_final_text` (their counts wobble with any lifter-side text
change; this batch's (B) moves the flat-lift path's counting too).
Brace audit 0 unbalanced (11,107 files). Censuses (b36_out2 ->
b37_out1): **duplicate impure renders 29,220 -> 19,418 redundant calls
(-33.5%) / 19,257 -> 10,405 distinct (-46%)** — the biggest
duplicate-call win since 23c; read-before-def 212,018 -> 211,643
(flat); pure copy lines 98,928 -> 101,658 (+2.8% — the traded
`flagN = tN;` live-bool shape, 23 `flag = flag` lines in all of AC);
`((byte*)` 196,223 -> 196,052, `->` 2,104 -> 2,076, unsafe-wrapped
38,754 -> 38,765 (all flat). NEW side effect, measured not guessed:
double-rendered member chains now bind — `bool flagN = this.X;` decls
in AC went 70 -> 430 (+360; spot-checked BearTrap/CameraManager —
property read once into a flag, faithful to the native single read).

**Residual (known, accepted):** a value whose renderings are ALL phi
copies on two-plus edges, with no counted consumer anywhere else, still
re-renders per copy — hunk C's `-1` sentinel suppresses the count for
objects never counted before (`_use_ip` defaults to -1). Such objects'
copies are dead-value copies in practice (a live consumer would have
counted them), and `_copy_prop` drops the dead twins, so nothing
observable is left; noted as §0 lead #5 rather than chased.

**Tooling under work/:** `probe_flag2.py` (the _analyze intermediate
dumper — blocks/conds/end_states/phi_copies, the tool that disproved
the rematerialization theory), `probe_full.py` (full-body re-lift by
VA, no needle filter — the before/after eyeball tool), the applied
`patch_b37_flagcount.py`, `run_build_b37.py` + `build_b37.log`, and
the gate report `ts_gate_b37_out1.txt` (plus a fresh stdout capture of
the final_out baseline re-run in the session log).

`b37_out1` is the verified gated candidate; promotion over
`final_out/` (= b36_out2) is a human call per the standing rule (§0/§6).

