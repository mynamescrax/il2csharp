## 0. Archived batch-closed stack (live leads live in todo.md)

**BATCH 38 CLOSED on 2026-08-22 (§0r), the full todo.md sweep: receiver
folding for calls (40-40e, incl. a same-session gate-invisible typeof
regression caught and fixed), `_redundant_else` (41), positional float
args (42), the golden snapshot suite (backlog #6), and four probe/
sizing closes. `b38_out1` is the gated candidate.**

**BATCH 37 CLOSED on 2026-08-22 (§0q), picking up §0 lead #1 (flags-cond
duplicate calls).** `b37_out1` (11,107 files, 115,658 bodies, 0 failed) is
the new gated candidate: gate **2 bad / 7,298 ERROR / 0 MISSING** (the same
two legacy-TMP files; MISSING cleared in both, ERROR -621 — the bad-file
set is unchanged, which per CLAUDE.md IS the per-file diff), brace 0,
full-corpus crash sweep 2/2 (the pre-existing TMP caps only), and the
biggest single duplicate-call win since 23c: **duplicate impure renders
29,220 -> 19,418 redundant calls (-33.5%), distinct 19,257 -> 10,405
(-46%)**. IMPORTANT for whoever resumes: the old lead #1's prescribed fix
(the flags-state redesign carrying (lhs_expr, rhs_expr) objects through
end_state) was built on a MISREAD of probe_flag.py's trace — the je
consumed the ORIGINAL same-block object, not a rematerialized one. The
real mechanism was three compounding counting defects (stale `_cur_ip`,
double-sided counting, uncounted phi-copy text renders); the fix is a
use-counting correction, NOT a flags redesign — full writeup §0q. The
flags text-carry in end_state (`'%s%s' % ft`) is unchanged and still
vestigial; `L.flags` in pass 2 remains the raw RPO leftover (correct for
the same-block and RPO-adjacent cases, which is all the corpus exercises).

*(The "next-session leads" list that used to follow here was
extracted verbatim into todo.md on 2026-08-22.)*

Old honesty debts that COLLAPSED (§0o re-measured, don't chase):
`: default` 4,929 -> **9** sites; `?addr` ~1.9k -> **10**. (`: default`
may have moved again at b37 — the TMP flat-lift pair changed slightly;
re-measure only if promoting.)

**BATCH 36 CLOSED on 2026-08-21 (§0p), same day as 29-35.** `b36_out2`
(11,107 files, 115,658 bodies, 0 failed) gated 2/7,919/2 (same two
legacy-TMP files, gate_diff all-zero), brace 0, crash sweep 2/2, with
read-before-def 234,460 -> 212,018 (-9.6%), pure copy lines 212,836 ->
98,928 (-53.5%), duplicate impure calls 32,754 -> 29,220 (-10.8%), and
pointer members rendering `obj->field` (127 -> 2,104 `->` lines) off
five fixes (full writeup §0p): pointer-typed-base member resolution
(36a-c), `_copy_prop` (37, 20-case unit suite), `_bind`'s cross-block
render-site rewrite (38 -- backlog #4's root cause), the indirect
vtable-dispatch arity trim (38b/38c, measured marginal), and the
bool/enum literal folds (39). **b36_out2 was promoted to
`il2csharp/final_out/` on 2026-08-21**; the same cleanup pass deleted
every other batch dir one level up (`b18_noreind` through `b36_out1`)
and the old `final_out_prev18/` archive — nothing was kept on disk
below `final_out/` until `b37_out1` (this batch) appeared one level up.

**BATCH 35 CLOSED on 2026-08-21 (§0n), same day as 29-33.** `b35_out2`
(11,107 files, 115,658 bodies, 0 failed) was the gated candidate:
gate **2 bad / 7,924 ERROR / 2 MISSING** under ts_gate.py (the same two
legacy-TMP files as b34, ERROR -201 all inside them, 0 newly bad / 0
cleared), brace 0, and **read-before-def 242,822 -> 234,460** with the
byte*-deref-base bucket **13,956 -> 6,368 (-54%)** and 854 fewer
`unsafe`-wrapped methods -- the sret RAX echo root cause §3 #2 had
flagged as "blocked on the stack-frame model" turned out to be a
one-binding fix (full writeup §0n). Its promotion was left for a human
call per the standing rule (§0/§6). b35_out1 is the intermediate
(35a+35b, without the size guard) kept for A/B; b34_out1 and earlier
superseded but on disk.

BATCHES 31-33 CLOSED on 2026-08-21 (§0m), same session as 29+30:
`b34_out1` was that batch's gated candidate (gate 2/8,125/2, rbd
273,016 -> 242,822, `getClass()` reads 29,296 -> 15,710 on top of
batch 30's -40.7%). The `_mem_lvalue` family is CLOSED (§0m,
3-operand IMUL was the root cause) -- don't reopen without a fresh
shape.

BATCH 29+30 (earlier this session, §0l): CMOV modeling SHIPPED (the
§0k resume, condition always parenthesized) plus the value-type
field-offset fix. `b31_out1` gated 5/8,133/2. **Caveat on gate
numbers: §0k's "5/6/0" was measured with `treesitter_gate.py`;
`ts_gate.py` counts ERROR/MISSING *nodes* -- b28_out1 reads
13/8,148/4, b31 5/8,133/2 under ts_gate. Always name the tool.**



**Batch 28 CLOSED on 2026-08-21** (re-checked batch 27's own claim that
the conditional-branch handler's unmapped-mnemonic splice bug was fixed
"the same way" in both duplicate copies -- it wasn't: only the DEAD
`il2csharp.py` copy got the fix, the REAL `decompiler.py` `exec_block`
copy still spliced a bare `?` for JS/JNS/JO/JNO/JP/JNP, and a downstream
`: default` synthesizer silently completed the malformed shape into
syntactically-valid-but-wrong C#, so it barely showed in the parse gate
despite affecting 11,980 sites full-corpus. Not CMOV-dependent -- a
plain pre-existing gap. Full writeup in §0j. Gate 13/8,148/4 ->
**13/14/0** (same 13 filenames, every remaining row an already-documented
unrelated family), full-corpus crash sweep 2/2 unchanged, brace audit 0
unbalanced. `b28_out1` is the new gated candidate -- **start at §0j's
leads if resuming**: lead #1 is still CMOV modeling itself (batch 27's
own lead #1, unchanged, bug #6 not yet searched for), lead #2 is a
dedicated audit for the same "fix landed in the dead copy only" mistake
elsewhere in the codebase.).

**Batch 27 CLOSED on 2026-08-21** (root-caused `SequenceNode.cs`'s
residual MISSING to a real Lifter gap -- `Il2Cpp.Lifter._insn` silently
drops every CMOV instruction, ground-truthed live -- attempted the fix,
but REVERTED the CMOV modeling itself after three live-trace-fix-rebuild
rounds each found a NEW distinct pre-existing landmine instead of
converging, the last one still unlocated; kept three independently-
verified, CMOV-independent robustness fixes found along the way
[conditional-branch `?`-as-operator collision, `strip_outer` stripping a
load-bearing ternary paren, `_unsafify` mistaking `==` for `=`]. Full
writeup + a concrete resume plan (find the 6th bug, build a real unit
harness, THEN re-apply the CMOV change) in §0i -- **start there if
picking CMOV back up**, don't re-derive from scratch.). Gate
13/8,150/4 -> **13/8,148/4** (gate-neutral by design; this batch's value
is the characterization + 3 kept fixes). `b27b_out1` is the new gated
candidate.

**Batch 26 CLOSED on 2026-08-21** (picked up backlog #2, read-before-def,
this file's own flagged top item -- re-measured and bucketed one level
deeper, root-caused its byte*-deref-base sub-shape but deliberately left
the fix unattempted, it needs the stack-frame/slot-liveness work already
flagged elsewhere as blocked, not a session-sized drive-by; also found
and fixed a live 2-site MISSING-node regression-of-sorts in `_render`'s
typeof(X) elision, the same bare-trailing-label family from batch 18/19
just down to two survivors -- full writeup in §0h, full backlog-#2 detail
in §3). Gate 15/8,150/6 -> **13/8,148/4**, 0 newly bad, 2 cleared.
`b26_out1` is the new gated candidate.

**Batch 25 CLOSED on 2026-08-21** (fixed exactly the bug this file's own
IN-PROGRESS LEAD described, plus its `_drop_dead_copies` twin the lead
flagged as unchecked -- full writeup in §0g). Both
`_drop_dead_locals`/`_drop_dead_copies` (decompiler.py) tested liveness by
a flat reference COUNT, blind to a mutual copy CYCLE (`obj25 = obj5;` /
`obj5 = obj25;` each count as a "use" of the other forever, so neither
ever reaches count<=1 no matter how many peeling passes run).
`InventoryManager.DropEverything` (VA 0x1806FE330) was the ground-truth
case: ten such dead phantom-local pairs collapsed a 79-instruction method
into ~80 rendered lines; re-lifted after the fix it's ~30 lines, matching
raw disassembly exactly (only `num1`/the two `DropObject()` bursts/the
trash-ID guard survive). Fixed with a proper mark-and-sweep liveness
closure in both functions (seed live from unconditionally-kept lines,
propagate backward through copy edges to a fixed point) instead of a flat
count; both changes verified with hand-built unit cases (2-cycle,
3+-cycle, self-reference, live cycle, and -- for `_drop_dead_copies`
specifically -- the batch-23c duplicate-protection invariant and its
propagation-through-a-protected-line edge case) before trusting live.
Corpus census (`work/scan_dead_cycles.py`, a per-file heuristic, sizes
the win not an exact site count): candidate dead mirror-pairs 1,510 (581
files) -> 986 (481 files) in the rebuilt tree. Final gated build is
`b25_out1`: 11,107 files, 115,658 bodies, 0 failed, gate **15 bad files /
8,150 ERROR / 6 MISSING** (bad-file count and file list byte-identical to
`b24_out1`'s 15/8,175/6 under the same `ts_gate.py`; ERROR count down 25,
plausibly just fewer total nodes from the removed dead lines -- no newly
bad file, none cleared). Brace audit: 0 unbalanced (11,107 files).
Full-corpus crash sweep (`work/sweep_crash.py`, run twice -- once after
the `_drop_dead_locals` fix alone, once after both fixes): 116,178
methods, ~430-460s, 2 crashes both times, byte-identical to the
documented baseline (the two pre-existing TextMeshPro/TextMeshProUGUI
cfg-too-large caps). `b25_out1` is a verified, gate-clean, crash-clean
candidate to promote over `b24_out1`; per this file's own standing rule,
promotion is left for a human call (§0/§6).

**Batch 24 CLOSED on 2026-08-21** (one fix, a major CFG correctness bug in
jump-table switch reconstruction -- found chasing this file's OWN #1 lead
below, "trace the worst `dup_impure_scan.py` file live before assuming
23c's mechanism applies twice in a row"; it didn't -- the real bug was
much bigger). Full writeup in §0f. Final gated build is `b24_out1`:
11,107 files, 115,658 bodies, 0 failed, gate **15 bad files / 8,175 ERROR
/ 6 MISSING** -- **one file better than `b23c_out1`'s 16/8,146/6**
(`TextContainer.cs` cleared, 0 newly bad -- its `else if (anchor == 6)`
row was batch 22's own "malformed switch-to-if reconstruction" note,
exactly this bug). Full-corpus crash sweep (new `work/sweep_crash.py`,
recreated per CLAUDE.md's pattern): 116,178 methods, 460.1s, **2 crashes,
byte-identical to the documented baseline** (the two pre-existing
TextMeshPro/TextMeshProUGUI cfg-too-large caps, unchanged). Brace audit:
0 unbalanced (11,107 files). This was a CFG-construction fix (block
leaders, jump-table entry counting, dead-end pruning) -- load-bearing,
high-blast-radius code -- so it earned the full validation bar (live
disasm trace, two scoped rebuilds, a full-corpus crash sweep, AND a full
rebuild + gate + brace audit) before being written up here, not just the
scoped-build spot check most single-fix sessions stop at.

**Batch 23 CLOSED on 2026-08-20/21** (same day as batches 20-22; three
fixes, all found live-tracing real output at a user's request rather
than off a gate row -- full writeup in §0e). Final gated build is
`b23c_out1`: 11,107 files, 115,658 bodies, 0 failed, gate **16 bad
files / 15 ERROR / 2 MISSING** -- byte-for-byte identical to `b22_out1`
AND to the intermediate `b23_out1` (23a+23b only) (`gate_diff` both
ways: 0 newly bad, 0 cleared, 0 worse, 0 better; none of the three
fixes touch a gate-visible shape). Full-corpus `sweep_audit.py`: 0
brace, 0 dangling, 0 empty_arg, 0 follower, crashes 2 (unchanged),
into_block 21,464/4,559 (byte-identical to `b22_out1`) -- run
separately after 23a alone, after 23a+23b, and after all of 23a-23c,
identical every time. **23a** fixed the 25 residual `Object.op_Equality`/
`op_Inequality(typeof(Object), ...)` gate rows §0's own next-session
lead #1 flagged -- root cause turned out to be NOT a second
guard-elision variant as guessed, but two SSE mnemonics (`MOVQ`,
`PSRLDQ`) never handled for a register destination in `Lifter._insn`,
leaking a stale class-init-guard value into real calls; 25 -> 0 raw
sites. **23b** added `_singleton_cse` (new pipeline pass,
decompiler.py): `typeof(X).Instance` is a pure static read, but every
`.field` access off it re-derived it fresh instead of reusing one fetch
-- corpus census 1,312 redundant same-method re-fetches -> 1,136 (the
"flat catalog" shape collapses fully, e.g. `InventoryManager.
AssignTemplates` 63 -> 1 in one method, roughly halving its length).
**23c -- the big one this batch: fixed `_drop_dead_copies` refusing to
ever drop an impure (call-shaped) phi copy, even when unread.** This
IS what was blocking `ControllerLayoutMenu.cs`/`NuisanceCustomer.cs`
from 23b (the "branchy re-fetch shape" flagged as a next-session lead
below at the time) -- but root-causing it against raw disassembly
showed it was never a `_singleton_cse` problem OR a CFG/phi-merge bug
at all: `ControllerLayoutMenu.SetupKeysFromCurrentLanguage`'s ~30
`if (x == null) throw;` guards all really do funnel into one shared
`raise_NullReferenceException()` block that reads NONE of the values
flowing into it on any edge, but `_drop_dead_copies` blanket-protected
every phi copy with an impure RHS regardless of whether anything read
it, on the theory that dropping it could silently erase a real call's
side effect. That theory is only sometimes true for a phi copy
specifically (its RHS, `pb.end_state.get(k)`, is ALWAYS a snapshot of
an already-computed value, never a fresh invocation -- the real call
was already emitted as its own statement elsewhere by the normal
exec_block path), so the fix is the same exact-text-twin proof
`_wb_finish`/`_sfblob_dedupe` already use: an unread impure copy drops
only when its RHS text is proven to survive elsewhere too, keeping the
first occurrence and never dropping the last one standing (verified
against a 6-case unit suite covering exactly that invariant before
trusting it live). Corpus-wide, via `work/dup_impure_scan.py`
(backlog §3 #4's own dedicated scanner): duplicate impure call
renders **47,341 -> 34,513 (-27.1%)**, distinct duplicate expressions
27,080 -> 23,721 (-12.4%), methods affected 13,136 -> 12,200 -- the
single biggest-magnitude win of this batch, on a metric no earlier
batch had moved at all. `ControllerLayoutMenu.SetupKeysFromCurrentLanguage`
itself: 281 -> 164 lines, EVERY `GetMiscText(...)` call now appears
exactly once (was twice: once for real, once as the dead phantom copy);
the `if (x == null) { stale duplicate call } else { real work }`
pyramid is now an honest `if (x != null) { real work }` with no
duplicate-carrying else arm at all. read-before-def barely moved
(307,036 -> 307,013 -- this was never a read-before-def-shaped bug,
the phi vars WERE defined, just redundantly). `b23c_out1` is a
verified, gate-clean candidate to promote over `b22_out1`; per this
file's own standing rule, promotion is left for a human call (§0/§6).

Next-session leads, ordered by expected payoff:
1. **`dup_impure_scan.py`'s remaining 34,513 redundant call renders**
   (backlog §3 #4, now measurably 27% smaller but far from closed) --
   23c fixed exactly ONE mechanism (a call's value surviving only as an
   unread phi copy into a dead-end block). The worst files post-23c
   (`ComputedStyle.cs` 556, `SDK.cs` 504, `ProbeReferenceVolume.cs` 357,
   `FastTouchscreen.cs` 302, `DateTimeParse.cs` 210 -- redundant-call
   counts, `work/dup_impure_scan.py <root> --list N` for the full list)
   are NOT confirmed to share 23c's mechanism -- trace the worst one
   live before assuming the same fix pattern applies twice in a row.
   The DEEP nesting itself (`ControllerLayoutMenu`'s ~30-level pyramid,
   still there after 23c -- only the phantom duplicate calls inside it
   are gone) is a separate, real readability issue: `_hoist_shared_tails`
   SHOULD be funneling ~30 identical `if (x == null) goto SHARED;`
   guards that all reach the same terminal throw into a flat sequence
   instead of leaving them nested N-deep, and isn't -- worth checking
   whether its funnel-rule predicates (CLAUDE.md: "no code between, no
   loop/switch/SEH level crossed... every sibling `else` arm ends in
   flow-break") are failing to recognize this specific shape (an empty
   implicit else, not a written one) before assuming a new mechanism is
   needed.
2. Batch 21's leads (the 451 residual `T objN` sites, the read-before-def
   `copy-rhs` bucket) are unchanged by this batch -- see §0's older
   content below and §0c.

**Batch 21 CLOSED on 2026-08-20** (same day as batch 20 -- both landed in
one session, then extended with a tenth fix from a targeted follow-up
on the read-before-def backlog item). Ten fixes (21a-21j), full writeup
with live-trace methodology in §0c. Final gated build is `b21_out5`:
11,107 files, 115,658 bodies, 0 failed, gate **19 bad files / 18 ERROR /
2 MISSING** -- byte-for-byte identical to `b20_out1` (`gate_diff`: 0
newly bad, 0 cleared, 0 worse, 0 better). Full-corpus `sweep_audit.py`:
0 brace, 0 dangling, 0 empty_arg, 0 follower, crashes 2 (the two
pre-existing TMP caps only, unchanged), into_block 21,464/4,559
(+138/+0.6% over batch 20, explained by 21c/21d, unchanged by 21j --
see §1). This batch's wins mostly don't show up in the parse gate at
all (every fixed shape was already syntactically valid, just wrong) --
judge it by the semantic census:

- **read-before-def (`il2csharp/work/read_before_def.py`), the batch's
  headline number: 339,938 -> 309,117 temps (-9.1%)**, split
  21a-21i -8,114 (-2.4%) then **21j alone -22,707 (-6.8%), by far the
  single largest fix this batch** -- see below.
- `Object.op_Equality`/`op_Inequality(typeof(Object), objN)` (21c/21d,
  the class-init-guard-elision fix): **2,417 -> 25** raw sites (99%
  cleared).
- raw `T objN = ...` declarations (21f, shared-generic-body return type):
  **2,511 -> 451** tree-wide (82% cleared; the residue is enclosing-
  method's-own-unresolvable-`T`, member-access-only uses, and
  collection-element reads -- §0c/leads list below).
- unconverted `il2cpp_codegen_write_barrier(...)` calls (21g, the
  tail-jmp write-barrier idiom, independently duplicated a THIRD time
  from the same split 21c/21d found): **5,797 -> 0** (100% cleared).
- invalid `?.member = value;` assignments (21i, a latent LHS-guard regex
  gap in `_null_conditional` that 21g's dedup exposed by shrinking a
  2-statement if-block to 1): **0 -> 3 -> 0** (introduced then fixed
  within this same session, net zero against the pre-session baseline;
  see §0c for why the regex never had a reason to fire before).
- Field declarations (21a/21b): **7,085** misclassified static/instance/
  const fields and visibility keywords corrected tree-wide (measured
  directly against the field table).
- Static field type resolution (21h): `typeof(X).Instance`-style static
  field reads now carry their real declared type instead of `None`, so
  a FURTHER deref off the result folds to a real member name instead of
  raw pointer arithmetic (`obj4.bearTrapTemplate` instead of
  `((byte*)obj3 + 0x250)[0]`) -- no standalone census taken (it compounds
  with the `T objN` / read-before-def numbers above), qualitatively
  confirmed live on `InventoryManager.AssignTemplates` (many dozens of
  sites in that one method alone).
- **21j -- ambiguous shared-body call argument trimming, the batch's
  biggest single win.** Every call to a genuinely-ambiguous shared body
  (`sub_x/*shared body, N candidates*/`) skipped arg trimming entirely
  (trimming needs a resolved `mi`, which by definition doesn't exist for
  this case), so the argument list kept every one of the four GPR slots
  PLUS whatever stale XMM0-3 values happened to survive from earlier in
  the method, printed as bogus extra "arguments" -- each one a phantom
  `objN` fed by a `_bind`/phi copy of a value that was never really an
  argument to this call and often was never really defined at all
  (exactly the `obj1 = obj2; obj3 = obj4; ...` copy-chain spam the user
  flagged as the dominant symptom of "Update() is still a mess"). Fixed
  by trimming to the LARGEST declared arity among all `N` candidates --
  sound because every candidate names a call into the literal same
  compiled machine code, so they must all consume the same argument
  registers regardless of which metadata identity is the true one; this
  is a provable bound, not a guess at which candidate is right, same
  category of fix as 21c/21d's `T`-bounded guard swallow. Verified live
  on `AmbientMusicSystem.SwitchTracks` (VA 0x1806067D0): `sub_182bd5710
  /*shared body, 2 candidates*/(0, this.ambientTracks.Length, 0, obj1,
  obj3, obj5, obj7, obj9)` plus five preceding `objN = objM;` copy lines
  -> `sub_182bd5710/*shared body, 2 candidates*/(0,
  this.ambientTracks.Length)`, matching the real disassembly's `Random.
  Range`-shaped 2-register call exactly, copy chain gone entirely.
  Assembly-CSharp-scoped: read-before-def 15,921 -> 14,186 (-10.9%),
  gate 0/0/0, `sweep_ac_only.py` 0 crashes/0 brace/0 dangling. Full
  corpus: read-before-def 331,824 -> 309,117 (-6.8% of the WHOLE
  corpus's original 339,938 baseline, from one fix).

`b21_out5` supersedes `b20_out1` as the gated baseline (batch 22's
`b22_out1` supersedes `b21_out5` in turn — see §0d). `b20_out1` is
kept for A/B; `b19_out2` and `b18_out12` remain for deeper archaeology.
`b21_out1`/`b21_out2`/`b21_out3`/`b21_out4` (intermediate batch-21
builds, missing later fixes) and `b21_ac`/`b21_ac2`/`b21_ac3`/`b21_ac4`/
`b21_nj`/`b21j_ac` (Assembly-CSharp/Newtonsoft.Json-scoped iteration
builds) were all scratch and are gone (reaped in an earlier session;
none were present on disk when batch 22 started). **`final_out/`
in-repo was promoted to `b22_out1` on 2026-08-20** (user-approved,
conservative cleanup pass); the prior batch-18 promotion is archived at
`final_out_prev18/` per the standing convention, not deleted.

**Gotcha hit this session, read before touching backups again**: an
attempted A/B comparison (copy current files aside, restore a `.preNN`
snapshot, diff, copy back) silently lost 21f/21g when the "copy aside"
step's path was invalid on this Windows/Git-Bash setup and failed
silently while the shell kept going -- the restore then succeeded
against a NOW-MISSING backup, permanently reverting both files to their
batch-20 state with no error surfaced. Recovered by re-applying every
edit from 21a through 21g in order from conversation context, then
re-verifying against all three live repros. **Full-file snapshots are
kept as `il2csharp/work/il2csharp_batch21_final.py` /
`decompiler_batch21_final.py`, refreshed after every landed fix this
session** -- prefer diffing against a full saved copy over a restore-
and-diff maneuver when checking one change's isolated effect; if a
restore-based A/B is still needed, verify the backup file actually
exists and is non-empty BEFORE overwriting anything, in a separate
command with its own exit check.

**Also confirmed this session**: `--only <AssemblyNameSubstring>`
(~30-45s for Assembly-CSharp, 6,622 bodies) plus
`il2csharp/work/sweep_ac_only.py <substring>` (a matching scoped
`sweep_audit.py`, no 10,000+-file cost) is a validated fast loop for
iterating without paying the ~9 min full-rebuild cost every time --
used for most of this batch's iteration; the full rebuild was only run
five times total across the whole batch (three to close out 21a-21i,
two more for 21j's follow-up), everything else validated at
Assembly-CSharp (or Newtonsoft.Json, for 21i) scope first.

Next-session leads, ordered by expected payoff:
1. **The 25 surviving `op_Equality`/`op_Inequality(typeof(Object), ...)`
   sites** -- almost certainly a second, smaller-volume variant of the
   same guard-elision family (21c/21d's fix bounded ONE guard shape;
   these may involve a cascade of two guards, or a differently-shaped
   receiver read). One live trace (`probe_store.py`) on the first site
   in `VolumeManager.cs:1395` would confirm or rule this out fast.
2. **The 451 residual `T objN = ...` sites** -- §0c's breakdown of
   what's left: `new T()`/`GetComponent<T>()` where `T` is the
   ENCLOSING method's own unresolvable type parameter (correctly
   irresolvable, leave alone), values used only via `.member` access or
   passed inline to another call rather than stored (21f only recovers
   a type from a STORE target; a member-access-based recovery is a
   separate, larger, possibly-ambiguous effort), and collection/array
   element reads. Diminishing returns already reached for THIS fix's
   mechanism -- if pursued, it needs a genuinely different signal, not
   a tuning pass.
3. **read-before-def's dominant `copy-rhs` bucket (still ~35% after
   21j; 309,117 total, down from 339,938)** -- §3 #2's top item, now
   with a real methodology proven out FOUR times this batch (21c/21d's
   guard bound, 21f/21g's write-barrier hint path, 21h's static-field
   type, 21j's ambiguous-arity trim -- 21j alone was -6.8% of the WHOLE
   corpus's original baseline, the single biggest fix of the batch).
   Current worst files on `b21_out5/Assembly-CSharp`:
   `FIMSpace/FProceduralAnimation/LegsAnimator.cs` (1,322),
   `InventoryManager.cs` (630, down from 708 pre-21j),
   `PlayerManager.cs` (393), `StoreManager.cs` (354),
   `FusionNetworkManager.cs` (259, down from 392 pre-21j -- Fusion RPC
   code leans heavily on shared-body calls, so it disproportionately
   benefited from 21j; worth a dedicated look next). Pick a worst-file
   repro, trace it live with `probe_store.py`/raw disassembly, and look
   specifically for OTHER duplicated-idiom-recognition or hint-recording
   code paths that only cover the COMMON case and silently miss a
   sibling shape, OR another `.ty = None` dead-end like 21h found, OR
   another untrimmed-argument-list shape like 21j found (e.g. check
   whether VIRT_CALL/vtable-resolved calls and the confident-single-
   candidate path both trim correctly, or whether either has its own
   untrimmed edge case) -- every one of this batch's big wins was
   exactly one of those patterns.
4. Everything else in §3 unchanged from batch 20 (see there): backing-
   field declarations (already fixed, §3 #7 -- confirmed 0 sites this
   session), field-offset ordering (was §3 #8 -- fixed by 21a, see
   §0c; remove #8 from the backlog when next editing §3), the
   `_mem_lvalue` base/index swap family (RenderGraphPass, traced but not
   fixed -- §0c), the single-candidate shared-body misresolve
   (ActorSpawner, traced and documented as a data-availability limit,
   not a fixable bug -- §0c).

Batch 20 closed on 2026-08-20: four builds, fixes 20h-20u, gate at
19 bad files / 18 ERROR / 2 MISSING (see §0b and §1). The tree
in `b20_out1` is the previous gated baseline, superseded once batch 21
gates clean. `b19_out2` (batch 19) and `b18_out12` (batch 18) are kept
for A/B and regression archaeology.

Next-session backlog (all one-off/small, row text to grep, also
listed at the end of §0b): the `*32 == ((byte*)this + 0x20)[0]`
family (7 rows, MemberHolder.Equals -- dead-base deref renders the
displacement as the pointer; same mechanism as the `Assert.Check(
(((byte*)? + 0x10)...` row; needs a live lifter trace of
0x1B7DD90), `num8 * index * index[obj17 + 20] = obj18;` (2 rows,
RenderGraphPass -- `_mem_lvalue` misclassifies the scale-muls as the
base, emits the displacement part as an index; todo.md §2 #9's
neighbor), `num1 = 1 ?? 0);` (1), the `? 0)`-select residue (3 rows:
`else if (anchor == 6)`, bare `else`, `Index("...") ? 0)`), L1
header rows (3, `// Decompiled by...` line artifacts), `56 =
"PointGraph (used for node links)";` (1), the 2 deliberate MISSING
`/* typeof(X) static-member store elided */` rows.

Two open housekeeping items, both deliberately left for a human call
at the time (both since resolved — see §0d/§0 for current state):

- **`final_out/` is STALE** — RESOLVED 2026-08-20: promoted to
  `b22_out1`; the batch-18 promotion this bullet describes is archived
  at `final_out_prev18/`, not lost.
- **Scratch trees to reap**: `b19_out1` (the batch-19 build BEFORE the
  `? ?` fix-up — keep only while §5's regression story matters),
  `b19_sim` / `b19_simbase` (sim A/B pair, regenerable in ~1 min from
  `work/sim_rewrite.py` + `work/make_sim_base.py`).

If another build is needed: `work/run_build_b19b.py` does not clean —
delete `b19_out2/` + `work/build_b19b.log` first. It fixes
`PYTHONHASHSEED=0` itself (unlike the older `run_build_b18l.py`, which
inherited it from the shell). For reindent A/Bs use
`$env:IL2CSHARP_NO_REINDENT=1`.

## 0b. Batch 20 in flight (2026-08-20, overnight loop)

Nine fixes landed (all in `work/patch_round20*.py`, applied to the
current source; several files are CRLF so the patches use binary
read/write):

- 20h property-comment-on-accessors, 20i attribution row widening
  (previous session).
- 20j MOVZX same-family reg->reg skip (`(op0 & 0x0F) == (op1 & 0x0F)`,
  il2csharp.py ~3301): kills `x = x;`/latch-copy chains. 0 self-copies,
  0 latch copies in PlayerManager.FixedUpdate.
- 20k3 async-name mangler, final form (`MANGLED_IDENT_RX`:
  `(?<![\w`])<?<[\w.`]+(?:`\d+)?>[\w`]*(?:>[\w`]+)?|<>[\w`]*(?:\|[\w`]+)*`
  + flat group-replace; 20k/20k2 span-extension versions superseded).
  `<<Service>b__0>d` -> `__Service_b__0_d`, `Start<<<Service>b__0>d>`
  -> `Start<__Service_b__0_d>`, generics/comparisons/shifts untouched.
- 20l `_BZEXT_RX` comma guard (decompiler.py:1562 `([^(),]+?)`): the
  movzx mask strip could swallow a whole call arg list (`new
  InflateBlockscodec, 0, 1 << w & 31;` family) via `_bool_sugar`.
- 20m mangler tail `(?:>[\w`]+)?`: was `*`, the tail could eat the
  CALLER's generic close when followed by `(` -- `Start<<S>d__6>(a)`
  became `Start<_S_d__6_(a)`. Now requires >=1 word char after `>`.
- 20n `_recv_fold` on the four property-accessor folds (get_/set_/
  get_Item/set_Item): `obj7 + 24.Task` -> `(obj7 + 24).Task`.
- 20o `_recv_fold` on the seven deref/member folds in `_insn`
  (struct member, arr/str Length, arr/str index, both instance-field
  folds): `this + 128.alignContent` -> `(this + 128).alignContent`.
- 20p `_recv_fold` on `getClass()` (3009) and the tail-call instance
  join (3219).
- null-cond LHS guard in `_null_conditional` (decompiler.py ~3094):
  `if (x != null) { x.f = v; }` stays an if, never `x?.f = v;`.

Sweep (decompiled corpus, 116,176 lifted / 2 pre-existing TMP cap
crashes): null-cond-LHS sites 0; `+ N.member` precedence sites 1
(`obj14 + 16.k`, IObserver<Message>.OnNext, one-off). The 581-file
subset build (20m-era, --only Assembly-CSharp,Fusion.Common) shows
TaskManager.cs fully clean: `Start<_SetupStunServers_d__6>(...)`,
`Start<__Run_ReversePing_b__0_d>(...)`, `(obj7 + 24).Task` everywhere,
decl/call names consistent.

Full 11,107-file build (02:53, nine fixes) + gate: 58 bad / 55 ERROR
/ 39 MISSING; gate_diff vs b19: 129 cleared / 4 newly bad
(MeshGizmo 12, PostProcessPass 7, GenericDropdownMenu 2, Image 1).
Follow-up fixes, all landed and verified by direct probe (no rebuild
needed for verification):

- 20q (il2csharp.py ~4650/4673): `mdot = mdot.replace('|','_')`
  sanitize at the instance-call name sinks -- the `|10_0` local-function
  suffixes printed unsanitized (`this._AddWireCube_g__AddEdge|10_0(...)`),
  the `|N` row family (~32 rows / 6 files). First patch attempt had an
  IndentationError; fixed to `.replace` on the same line.
- 20r (decompiler.py, `_FLAG_SENTINEL_RX`, `_final_text` loop): strips
  `\x01[^;\r\n]*;` -- `_resolve_labels` leaks the FLAGS sentinel exprs
  (`lhs\x01rhs`, minted at decompiler.py:808/904) into value statements
  (`object obj15 = this.m_Event.modifiers | typeof(...).s_Modifiers\x010;`).
  Verified: sentinel gone from PanelEventHandler-family re-lifts.
- enum gparams off in `type_decl_line` (il2csharp.py ~5312): generic
  enums exist in metadata but C# forbids them; `internal enum
  VirtualizationChange<T>` etc. no longer emitted (3 sites).
- 20s (il2csharp.py 4814 + sanitize): local-function `|N` can sit
  INSIDE an async machine name (`<<InternalWriteEndAsync>g__AwaitIndent|11_1>d`
  and `Start<<ReadAsync>g__FinishReadAsync|44_0>d>(...)`); the mangler
  tail is now `[\w`]*(?:\|[\w`]+)*(?:>[\w`]+)?` to absorb it.
  Same patch: sanitize() now maps `-` -> `_` (Unity's
  `_PrivateImplementationDetails__99f15b47-...` GUID class).
  probe_mangle10: 7/9 pass; the two "FAILs" are context-real: a
  `<`-after-word site keeps only ONE leading underscore, and that is
  self-consistent per statement (no class decls exist for these nested
  machines, verified by tree grep).
- 20t (il2csharp.py type_name, ~38990): `$ArrayType=N` (Mono's spelling
  of the blob structs; the existing hard-coded rewrite only knew
  `__StaticArrayInitTypeSize=`) -> `_ArrayType_N`, matching the
  sanitized decl side. probe_at: 15/15 typedefs clean.
- 20u (parse_default te==0x03, ~39150): char literals with
  non-printable values emitted raw chr() (an actual NUL byte in
  `lowSurrogate = '\x00'`, unlexable); non-printables now render
  as `'\u%04x'`. probe_to_utf32: `lowSurrogate = '\u0000'`.

Third full build (03:01, all fixes through 20s): 11,107 files / 115,658
bodies / 0 failed; gate 21 bad files / 65 ERROR / 2 MISSING (35 rows);
vs b19: 162 cleared / 0 newly bad / 1 worse (the `$ArrayType`
family = the same 2 details files, 2 -> 46 rows -- fixed by 20t);
1 better (RenderGraphPass 3 -> 2). Sweep unchanged (brace 0, dangling 0,
into_block 21,326, crashes 2). Gate row census at ts_gate_b20_out1.txt.

Fourth build (04:04) + gate: 19 bad files / 18 ERROR / 2 MISSING
(20 rows); vs b19: 164 cleared / 0 newly bad / 0 worse. The
`$ArrayType` family (12 rows) and the ToUTF32 NUL row cleared; the
whole-file gate row census still lives in ts_gate_b20_out1.txt.
BATCH 20 CLOSED at this gate (see §1 for the numbers).

Known remaining families after that (all one-off or small, each with
the row text to grep): `num8 * index * index[obj17 + 20] = obj18;`
(2 rows, RenderGraphPass -- store-LHS `*`-maul, next to todo.md §2
#9 parens in `_mem_lvalue`), `return *32 == ((byte*)this + 0x20)[0];`
+ `*24`/`*112`/`*136`/`*16` variants (7 rows -- deref base folded to a
constant; MemberHolder.Equals family; needs a live lifter trace),
`num1 = 1 ?? 0);` (1), `if (string.IndexOf("...", c) ? 0)` + `else if
(anchor == 6)` + bare `else` (3, select-mark residue), L1 header rows
(3, `// Decompiled by...` -- whole-file artifacts), `Assert.Check(
(((byte*)? + 0x10)[0] == 0 ? 1 : 0)` (1, honest `?` base),
`56 = "PointGraph (used for node links)";` (1, register-name leak),
`/* typeof(X) static-member store elided */` (2 MISSING, deliberate).
Repo backlog unchanged: `(Func<double>, int, int)` ctor shapes,
`obj14 + 16.k`, `public PlayerLobbyHandler() : base()` rows,
read-before-def audit (`work/read_before_def.py`), `: default` false-arm
debt (4,929 sites).

## 0c. Batch 21 (2026-08-20, CLOSED)

Started from the read-before-def census (`il2csharp/work/read_before_def.py`
run against `b20_out1`: 339,938 undefined-temp reads across 53,081
methods; 35.3% are plain phi-copy `objN = objM;` where `objM` is never
defined anywhere in the method) and todo.md's own §3 backlog, both
pointing at the same two areas.

**21a/21b -- real FieldAttributes, not offset/name-shape heuristics
(closes §3 #8, confirms and generalizes the already-shipped #7 fix).**
IL2CPP stores a field's CLI FieldAttributes in the low 16 bits of its
`Il2CppType` word (`attrs:16`, same word `_type_enum` reads bits 16-23
from) -- the emitter never read it, and instead guessed `static` from
`offset < 0x10`, `const` from "has a decodable default value", and
printed every field `public`. Measured on Shift At Midnight (59,522
non-enum fields): 4,793 real statics printed as instance fields (this
IS §3 #8's `CurrentDayManager.OneSecondWait` case -- a real static field
at offset 0x10, exactly at the heuristic's threshold, printed as instance
last in the header; not a sort-order bug as #8 guessed, a
static/instance misclassification), 2,292 instance fields on GENERIC type
definitions printed `public static ... // static @0x0` (generic defs have
no per-definition field-offset table, so the heuristic's offset always
read 0), 3,410 redundant `[SerializeField]` on already-public fields, and
14 RVA-data blobs printed as `const` (a decodable default value is not
the CLI Literal marker; those 14 don't compile as const-eligible types
anyway on read but the modifier itself was simply wrong). Also split
`TYPE_VIS` in two: type visibility (TypeAttributes) and member visibility
(Method/FieldAttributes) are different ECMA-335 bit tables, and every
type header was reading the WRONG one -- nested `NestedPublic` (2) typedefs
rendered `private protected`, `NestedPrivate` (3) rendered `internal`;
verified against BCL ground truth (`Enumerator<T>` nested in `List<T>` is
genuinely `public`, nested in `Dictionary<TKey,TValue>` genuinely
`private`) post-fix. Full-corpus `emit_type` sweep (`work/
sweep_emit_type.py`, all 16,916 typedefs): 0 crashes, 0 malformed
`const` (no initializer), 0 double-modifier lines. Rebuilt as `b21_out1`
(11,107 files, 115,658 bodies, 0 failed, 683.8s); gate 19/18/2, unchanged
from `b20_out1` as expected (field modifiers are not a parse-gate
concern). Patches: `work/patch_round21a.py`, `patch_round21b.py`.

**21c/21d -- class-init-guard swallow bounded by its own branch target,
not a fixed instruction count (this IS §3 #5's "typeof(Object) operand"
hypothesis, traced to ground truth).** `Object.op_Equality`/`op_Inequality
(typeof(Object), objN)` -- 2,417 raw sites on `b20_out1` -- comes from the
`mov rA,[rip slot->TypeInfo] ; cmp dword [rA+E4],0 ; jne T ; call
class_init ; T:` class-init-guard idiom, whose instructions get elided
(`skip_ips`/`skip`) so the class pointer reads as already available. The
swallow loop bounded itself by `min(m3 + 4, len(insns))` -- 4 instructions
past wherever the class-init call was found -- with an early-break if it
happened to find a second `mov rA,[same slot]` (a slot RELOAD) first. When
the guard's own register gets reused directly instead (`mov rcx,rA` where
`rA` already equals `rcx`, so no second slot-load exists), the break never
fires and the loop blindly swallows past `T`, the guard's actual merge
point -- catching whatever REAL code the compiler placed right after it.
Live-traced against `AmbientMusicSystem.Awake` (VA 0x180606330, a
standard Unity singleton guard, `if (Instance != null && Instance !=
this) { Destroy(gameObject); return; }`): the guard immediately precedes
the real `op_Inequality`-shaped call, whose arg setup is `xor r8d,r8d ;
xor edx,edx ; mov rcx,rdi ; call`. All three of those fell inside the old
`m3+4` window and got swallowed, so the call rendered with its 1st arg
holding the guard's STALE class-token value (`typeof(Object)`, not the
`Instance` field it should have read) and its 2nd arg an undefined temp
(`obj3`/`obj4` -- the `xor edx,edx` that should have supplied the literal
`0`/null was never seen). Fix: since the guard's `jne T` fast path jumps
straight to `T` regardless of what the slow path does, NOTHING between
the guard's start and `T` can be real code reachable outside the guard --
bounding the swallow by `T`'s own instruction index (found by scanning
forward for `insns[ti].ip == T`) is a provable bound instead of a guessed
lookahead, and subsumes the old reload-based early-break as a special
case (a reload, if present, is always strictly before `T`). Found live
via `IL2C_DEBUG_GUARD`-gated prints temporarily added to (and removed
from) both copies -- **this idiom is independently duplicated in two
places**: `il2csharp.py`'s `Lifter.lift()` (dead code for the real
pipeline; only reached by the legacy flat-lift fallback the two
TextMeshPro cfg-too-large-cap methods use) and `decompiler.py`'s
`Decompiler._guards()` (the actual path every real build exercises --
21d is the fix that matters; 21c is its flat-lift-fallback twin, fixed
for consistency and because a future `--decls-only`-adjacent code path
could start using it). Patches: `work/patch_round21c.py` (il2csharp.py),
`work/patch_round21d.py` (decompiler.py). Verified live via
`il2csharp/work/probe_store.py 0x180606330`, RAW pre-render text before
vs after:
```
before: if (!UnityEngine.Object.op_Inequality(typeof(UnityEngine.Object), obj3))
after:  if (!UnityEngine.Object.op_Inequality(typeof(AmbientMusicSystem).Instance, 0))
```
matching the real source (`Instance != null`) up to two remaining
cosmetic items, NOT part of this fix and left for a follow-up: the
literal `0` should render `null` against an Object-typed operand, and
`Object.op_Equality`/`op_Inequality` calls generally should fold to `==`/
`!=` (both are cheap, mechanical follow-ups once this family's volume is
confirmed post-rebuild).

**21e -- the T-lookup 21c/21d added was O(n) per candidate (linear scan
over the remaining instruction list), not O(1); real, independent of
whether it explained the symptom below. Fixed by building one
`{ip: index}` map per `_guards`/`lift()` call (`ip_idx` / `_ci_ip_idx`)
and using a dict lookup instead of the forward scan. Caveat on the
motivating symptom: the first `sweep_audit.py` run after 21c/21d landed
was killed at "0% methods=1, no progress for 2+ minutes" on the
assumption it had hung -- but a LATER run (with 21e already applied)
took 132s to reach its first 20% checkpoint too, which turned out to be
normal pacing for this sweep, not a hang. So the O(n)-per-candidate cost
was real and worth fixing regardless, but it was never rigorously
isolated as the cause of the first run looking stuck (the original,
unfixed version was never let run long enough to tell "slow but
progressing" from "actually stuck" apart) -- don't cite this as a
confirmed before/after performance measurement, only as a real
complexity-class fix applied preventively. **Take from this**: an
O(1)-looking `for x in raw: if x.ip == T` inside an outer per-candidate
loop is an easy way to accidentally introduce quadratic behavior in this
codebase -- prefer an index map whenever a peephole needs to locate an
instruction by address instead of by list position; and don't kill a
background sweep on impatience alone -- check its normal pacing (or let
it run once uninterrupted) before concluding it hung.
- `num8 * index * index[obj17 + 20] = obj18;` (RenderGraphPass.
  SetColorBufferRaw, VA 0x1829174F0, 2 gate rows) was traced live
  (`il2csharp/work/probe_store.py 0x1829174F0`): `_mem_lvalue`'s
  base/index roles are genuinely swapped for this store -- the register
  the lifter treats as the array BASE (kind='arr') actually holds a
  scaled-index expression (`num8 * index`), and the register it treats
  as the INDEX holds what looks like a real array-element address
  (`obj17 + 20`). Read-before-def on the SAME method shows `num2`,
  `num3`, `num7`, `num8` all undefined -- this is a phi-resolution
  failure on a merge this method's CFG shape triggers, not a narrow
  render-site bug; needs the same kind of ground-truth trace 21c/21d got,
  not yet done. Left as-is; do not attempt a text-level patch over it.
- Confirmed that even a SINGLE-candidate shared-body call resolution can
  still be a confidently wrong name, and it is not a bug in this
  codebase's disambiguation logic when it happens: `il.addr_candidates`
  for the call target in `ActorSpawner.Update` (VA 0x180513740, one of
  the read-before-def scan's worst files) returns exactly one entry,
  `('generic', 157234)` -> `Unity.Collections.NativeSortExtension.
  IntroSortStruct_R<T, U>` -- but the call's real argument setup (`this.
  template.gameObject` in rcx, a freshly-built `Vector3`/`Quaternion` in
  rdx/r8) is unmistakably `Object.Instantiate(GameObject, Vector3,
  Quaternion)`. IL2CPP's registration tables only recorded ONE
  `Il2CppMethodSpec` for this folded code address; there is no second
  candidate for `addr_candidates` to have missed, so CLAUDE.md's
  documented disambiguation machinery (base-chain walk / usage-slot
  match) never even runs -- the information needed to pick correctly
  does not exist in this data source. Matches CLAUDE.md's own framing of
  this problem class (the pre-batch-11 `Guid.cs` bug); worth a repo-level
  note but not a fixable bug without a new data source (e.g. verifying
  argument SHAPE against the candidate's expected parameter types, a
  much larger feature). Left as-is.

**21f/21g -- type inference for shared-generic-body calls (`T objN =
Foo.Method();` and its "spaghetti" write-barrier-tail-call sibling),
found from a user bug report reading real output, not the gate.**
`Component.GetComponent<T>()` and every other reference-type generic
method IL2CPP compiles as fully shared across instantiations: the
compiled call target is the method's own UNSUBSTITUTED signature, whose
return type is the literal declared generic parameter -- `T`, not
`object`, not the real type. `_bind`/`_materialize`/the phi-substitution
helper (`_kill_one`) each record a new temp's declared type via
`vt.setdefault(v, e.ty)`, and since a raw `T` type tuple passes
`isinstance(e.ty, tuple)` same as any real type, it PERMANENTLY locks
the temp's declaration to the useless placeholder -- `setdefault` means
a later, better hint (already recorded by `_write_mem`'s "storing a bare
temp into a typed location types the temp" when the temp gets stored
into a concretely-typed field, e.g. `this._cam = obj3;`) can never win.
Traced live against `AdaptiveFovByAspect.Awake` (VA 0x180606130):
`T obj3 = this.GetComponent(); this._cam = obj3;` for source that reads
`_cam = GetComponent<Camera>();` -- 609 raw `T objN = ` sites in
Assembly-CSharp alone (batch-20 baseline).

Fix (21f): `_is_unresolved_gp(ty)` (new module-level helper, il2csharp.py)
tests for IL2CPP_TYPE_VAR/MVAR (0x13/0x1e); all three binding sites skip
`vt.setdefault` for such a type and instead record the token in a new
per-method `self._gp_blocked` set, leaving the `setdefault` slot open for
the later, better hint. Got the declaration from `T obj3` to `object
obj3` -- progress, but not `Camera`, because the ACTUAL dominant store
path for a reference-typed field is NOT `_write_mem`'s plain-mov path at
all: IL2CPP inserts a GC write barrier for almost every reference-type
field store, which `_call` recognizes as a SEPARATE idiom
(`target in self.rt_wbarrier`) that builds its assignment statement
directly and never touched `_write_mem`'s hint-recording line. Extracted
the write-barrier statement construction into a shared `_wb_operands`
helper and added the same "type the bare-token value from the typed
address argument" hint there (the address arg's Expr carries its
pointee's type, same convention `_bind` documents for `&`-prefixed
text). That alone fixed the declaration (`Camera obj3 = ...`); a further
addition in `decompiler.py`'s `_rename_locals` (which already does one
retroactive `var` -> real-type declaration-fix pass) re-annotates the
RHS too, IFF the token's type was specifically withheld via
`_gp_blocked` (the load-bearing signal that this call genuinely lost its
own `<T>`) AND the RHS is the exact bare `Foo.Method()` shape (empty
parens, no existing `<...>`) this idiom produces --
`UnityEngine.Camera obj3 = this.GetComponent<UnityEngine.Camera>();`,
matching real source. Deliberately conservative: a call that already
resolved its OWN (possibly wrong, single-candidate-shared-body) generic
argument, e.g. `Object.FindFirstObjectByType<PlayableDirector>()` for a
field truly typed `PlayerInput` (a second, independent instance of the
single-candidate-shared-body limit §0c already documents for
ActorSpawner), is left untouched on the call side -- only the
declaration gets the honest, hint-derived type; 21f/21g does not try to
also silently correct an already-present-but-wrong `<T>`, which would be
guessing without proof, the same restraint CLAUDE.md documents for the
`sub_x/*shared body*/` marker.

Fix (21g), found chasing 21f's OWN validation: the write-barrier idiom
can be the LAST thing a void method does, compiled as a tail `jmp`
straight into the barrier helper rather than a `call`+`ret` pair (MSVC
tail-call optimization -- confirmed live via raw disassembly of
`BackButtonPressed.Awake`, VA 0x18060CE80: `lea rcx,[rbx+48h] ; mov
[rbx+48h],rax ; mov rdx,rax ; add rsp,20h ; pop rbx ; jmp
il2cpp_codegen_write_barrier`). This tail-jmp shape is handled by an
ENTIRELY SEPARATE code path from `_call` -- independently duplicated
TWICE more (`il2csharp.py`'s `Lifter.lift()`, dead for the real
pipeline, and `decompiler.py`'s `_analyze`/`exec_block`, the path that
matters -- the SAME split 21c/21d already found and fixed for the
class-init guard, hit again for a different idiom), and neither knew
about the write-barrier idiom at all: the raw call rendered unconverted,
`return il2cpp_codegen_write_barrier(ref this.field, value);` -- 246
sites in Assembly-CSharp alone (batch-20 baseline), one of the exact
"spaghetti"/"RPCs are incomplete-looking" complaints in the bug report
that started this. Refactored the dedup logic (exact-text twin, radix-
normalized twin, same-lvalue-as-previous-store twin -- three checks
`_call`'s write-barrier block already had, to avoid double-printing the
plain store AND its GC-barrier twin) into a second shared helper,
`_wb_finish(ip, dst, src2, asm, tail=False)`; both tail-jmp sites now
build `arg_exprs` (a parallel Expr list next to the existing text-only
`args`, needed for `_wb_operands`'s type-hint half) and call
`_wb_operands` + `_wb_finish(..., tail=True)` when the jmp target is a
registered write barrier, closing with `return;` for the real,
non-duplicate case (a duplicate, same as the ordinary case, needs no
explicit `return;` at all -- the method's void return type makes falling
off the end of the block, after the plain store two lines above already
rendered the assignment, valid C# on its own).

Verified live (three repros, `probe_store.py`): `AdaptiveFovByAspect.
Awake` (0x180606130, plain write-barrier store) ->
`UnityEngine.Camera obj3 = this.GetComponent<UnityEngine.Camera>();`;
`BackButtonPressed.Awake` (0x18060CE80, two stores, second one
tail-jmp'd) -> both fields correctly typed, no duplicate statement, no
raw helper call; `AmbientMusicSystem.Awake` (0x180606330, the 21c/21d
repro) -> unchanged, confirming 21f/21g did not disturb 21c/21d.
Assembly-CSharp-scoped build+gate (`b21_ac2`): 0 bad files; raw `T objN
= ` sites 609 -> 40 (the residue is `new T()`/generic-method-own-`T`/
member-access-only uses -- §0's leads list); unconverted
`il2cpp_codegen_write_barrier(` calls 246 -> 0. Scoped structural sweep
(NEW `il2csharp/work/sweep_ac_only.py`, an `--only`-filtered
`sweep_audit.py` for exactly this fast-iteration need): 6,634 methods,
0 crashes, 0 brace, 0 dangling, 0 empty_arg (into_block 1858, +12 over
the batch-20-code baseline measured the same way -- consistent with,
not a new regression beyond, 21c/21d's already-explained +0.6% corpus-
wide uptick). Full-corpus numbers (see §1): `T objN =` 2,511 -> 451
(82%), unconverted write_barrier 5,797 -> 0 (100%).

**21h -- static field reads (`typeof(X).Instance` and every other static
field, not just singletons) always carried `.ty = None`, so a FURTHER
deref off the result could never fold to a real member name.** Found
answering a user question about a DIFFERENT-looking but related output
sample (`object obj8 = ((byte*)obj7 + 0x280)[0]; this.explosiveTemplate
= obj8;` for `StoreManager.Instance.explosiveTemplate`). `_field_expr`'s
`base.kind == 'sfblob'` branch (the static-fields-blob offset resolver,
`static_off_names`) returned a bare NAME string and built
`Expr('%s.%s' % (...), None, 'obj')` -- the `None` meant the read's OWN
type was thrown away, so `obj3 = typeof(StoreManager).Instance` (a
correctly-NAMED read) left `obj3` untyped, and the very next
instruction's deref (`*(obj3 + 0x250)`, meant to read a FIELD off the
singleton instance) had no type to resolve `instance_field_chain`
against and fell back to raw `*(base disp)` pointer arithmetic. Fix:
`static_off_names` now returns `{offset: (name, field_type_idx)}`
(mirroring `instance_field_chain`'s existing shape exactly) instead of
`{offset: name}`, and `_field_expr`'s sfblob branch resolves and
attaches the real field type/kind the same way the instance-field
branch already did. **One caller missed on the first pass** --
`decompiler.py`'s `_fold_static_addrs` (a text-level sibling fold over
the `typeof(T).__static_fields + N` blob-address SPELLING, independent
of `_field_expr`'s Expr-level resolution) calls the SAME
`static_off_names` through its own `_static_field_name` helper and
expected the old plain-string shape; the first Assembly-CSharp-scoped
gate after 21h caught it immediately (190 bad files, `typeof(Vector3).
('kEpsilon', 35166)` -- Python's `%s` stringifying the un-unpacked
tuple). Fixed by unpacking in `_static_field_name` instead (it only
ever needed the name half). Verified live
(`InventoryManager.AssignTemplates`, VA 0x1806FAF40): `object obj7 =
typeof(StoreManager).Instance; object obj8 = ((byte*)obj7 +
0x280)[0];` -> `StoreManager obj7 = typeof(StoreManager).Instance;
this.explosiveTemplate = obj7.explosiveTemplate;` (further folded to a
direct member access on some sites since the intermediate temp's use-
count dropped to the point `_bind` doesn't need to materialize it).
Rebuild-verified clean on both Assembly-CSharp (`b21_ac4`: 0/0/0) and
the full corpus (`b21_out4`, see §1).

**21i -- a latent gap in `_null_conditional`'s "this body is an
assignment, don't fold to `?.`" guard, exposed (not introduced as new
risk) by 21g's write-barrier dedup.** The guard's regex,
`[\w.\[\]]+\s*(?:[+\-*/%&|^]|\?\?)?\s*=`, tests the text after the
tested variable's `.` for an assignment shape -- but at the pipeline
stage `_null_conditional` runs (before `_member_fold`, which turns
`<Name>k__BackingField` into plain `.Name`), a backing-field-typed
assignment target still carries its RAW compiler-mangled name,
`token.<Parent>k__BackingField = this;` -- and `<`/`>` are not in the
character class, so the regex fails to match at all, `not re.match(...)`
comes back `True`, and the fold proceeds onto an assignment target:
`token?.Parent = this;`, invalid C# (`?.` cannot be an lvalue). This
was a genuinely pre-existing gap (confirmed 0 sites on `b20_out1`,
before any of this session's changes) that had simply never had a
single-statement `if (x != null) { x.<Backing>k__BackingField = v; }`
shape to trigger on -- until 21g's write-barrier-to-assignment dedup
collapsed a 2-statement body (`token.Parent = this; return
il2cpp_codegen_write_barrier(&token.Parent, this);`, the second
statement previously rendering raw and un-deduped) down to exactly 1,
which is precisely the shape `_null_conditional`'s simple pattern
matches. Found via `gate_diff` on the FIRST full-corpus rebuild
including 21f/21g (`b21_out3`, all in Newtonsoft.Json: 3 newly-bad
files, 1 ERROR node each) -- caught because `gate_diff` is always run,
never just the summary line, per this file's own standing rule (§4).
Root-caused with a NEW spy probe (`il2csharp/work/probe_nullcond.py`,
monkey-patches `Decompiler._null_conditional` to print its input/output
whenever it changes something, without touching the source) rather than
guessing from the final text. Fix: added `<>` to BOTH copies of the
regex's character class (the straight `if(x!=null){...}` shape and its
`if(x==null){}else{...}` inversion share the identical pattern).
Verified: 0 sites tree-wide before this session, 3 after 21g alone, 0
after 21i (`b21_nj`, Newtonsoft.Json-scoped: gate 0/0/0; full corpus
`b21_out4`: `grep -rn '?\.[A-Za-z_]\w* = '` excluding `??` -> 0).

## 0d. Batch 22 (2026-08-20, cheap-wins pass over the `b21_out5` gate rows, CLOSED)

Picked the smallest/cheapest remaining gate rows off `b21_out5`'s 19/18/2
(listed in full at the top of §1) rather than a new backlog item. Three
patches, all in `decompiler.py` (`work/patch_cheapwin1_nullternpar.py`,
`patch_cheapwin2_fixselect_colon.py`, `patch_cheapwin3_fixselect_innercolon.py`):

- **cheapwin1 -- `_null_ternary_sugar` dangling paren.** `_NULLTERN_RX`
  only expected parens wrapping the *condition* (`(t == null)`), never
  the whole ternary (`(t == null ? a : b)`). In the whole-wrap case the
  leading `(` was consumed and discarded while the matching trailing `)`
  got swallowed into the greedy `b` capture, so the synthesized `t ?? b`
  text kept the stray `)` -- `AnimationCurve.cs:571`'s
  `num1 = 1 ?? 0);`. Fixed by capturing the paren presence explicitly and
  stripping the matching trailing `)` back off `b` when only the leading
  paren was seen. Also added a guard skipping the fold entirely when the
  tested-for-null operand `t` is a bare integer literal (a literal can
  never be null; the AnimationCurve.cs site's actual condition was `1 !=
  null`, a stray textual match, not a real nullable check) -- left as the
  honest original text instead of synthesizing `??`/`?.` nonsense over it.
- **cheapwin2/3 -- `_fix_select`'s two `:` checks were byte-substring
  tests, not string-literal-aware (this file's own §4 rule: reuse
  `_in_string` for exactly this).** `UriHelper.cs:1038`'s
  `if (string.IndexOf(";/?:@&=+_,", c) ? 0)` never got its missing
  `: default` arm for two independent, stacked reasons: the whole-line
  fast-reject (`if ':' in ln: return ln`) bailed because the STRING
  LITERAL argument contains a `:`, and even after removing that (cheapwin2),
  the per-group "already a ternary" check (`':' in ln[k:j]`) also fired
  on the same string-literal `:`, since it spans back to the enclosing
  `if (` (cheapwin3). Both are now literal-aware via `_in_string`. Bonus,
  unplanned fourth clear: `NetConnectionMap.cs:408`'s `Assert.Check(
  (((byte*)? + 0x10)[0] == 0 ? 1 : 0), ...)` -- documented in earlier
  batches as an "honest `?` base" -- was actually the SAME bug (the real
  `: default`-eligible select mark sat on a line with an unrelated real
  ternary's `:` later on, blocking cheapwin2's fix alone; cheapwin3
  cleared it): now `(((byte*)? + 0x10 : default)[0] == 0 ? 1 : 0)`,
  consistent with how every other true select-mark site on this corpus
  already renders, not a new kind of guess.
- Investigated but NOT touched (root cause is a different, bigger bug in
  each case, not a cheap fix): `NodeLink2.cs:138`'s `56 = "PointGraph
  (used for node links)";` (a duplicate store of the same value as
  `NodeLink2.cs:120`'s correctly-cast `((byte*)56)[0] = ...`, tangled
  in the same method's broken `isinst`-idiom recovery -- read-before-def
  spam on `obj26`/`obj27`/`obj28` in the same method says this needs a
  live lifter trace, not a text patch); `TextContainer.cs:428`'s
  `else if (anchor == 6)` (a malformed `switch`-to-if reconstruction --
  the whole `GetPivot` method lost most of its cases, not a stray-text
  bug); `XmlTextWriter.cs:1677`'s bare `else` (traced to the SAME
  `_mem_lvalue` base/index-swap family already on file for
  RenderGraphPass, `num8 * index * index[obj17 + 20] = obj18;` --
  `this.stack * this.top[this.stack + 16] = ns;` a few lines above it is
  the tell; a second occurrence of a known, not-yet-root-caused bug, see
  §0 next-session leads). The 7-row `*32 == ((byte*)this + 0x20)[0]`
  family (MemberHolder, EnumDataUtility, RefreshPropertiesAttribute,
  BaseProcessor, DataRelationPropertyDescriptor x2, BindingRestrictions)
  and the 2 TextMeshPro L1 whole-file artifacts were left alone per their
  existing documentation (needs a live lifter trace / known cfg-too-large
  cap, respectively) -- not attempted this pass.

Verified: unit-level (direct `_fix_select`/`_null_ternary_sugar` calls
against the exact repro text and several must-stay-unchanged shapes),
then a full rebuild `b22_out1` (11,107 files, 115,658 bodies, 0 failed,
615.5s) gated **16 bad files / 15 ERROR / 2 MISSING** -- `gate_diff` vs
`b21_out5`: **4 cleared** (AnimationCurve.cs, UriHelper.cs,
NetConnectionMap.cs, plus the file-level count), **0 newly bad, 0
worse**. Full-corpus `sweep_audit.py`: brace 0, dangling 0, empty_arg 0,
follower 0, crashes 2 (the two pre-existing TMP caps, unchanged),
into_block 21,464/4,559 -- byte-identical to `b21_out5`, confirming no
structural regression. `b22_out1` is a verified, gate-clean candidate to
promote over `b21_out5` as the baseline; leaving that call for a human
per this file's own standing promotion rule (§0/§6). Remaining gate rows
after this pass: 15 (the 7-row `*N == ...` family, the 3-row
`switch`/`_mem_lvalue` residues just traced above, 2 TMP L1 artifacts,
1 SequenceNode.cs L1 artifact not yet root-caused, 2 deliberate MISSING
markers).

## 0e. Batch 23 (2026-08-20/21, three live-traced fixes off real output, CLOSED)

Not a gate-row-driven batch: all three fixes came from live-tracing
output a user pointed at directly -- 23a from todo.md's own §0 lead #1,
23b from a "read InventoryManager, it looks bloated" prompt, and 23c
from chasing WHY 23b's own fix couldn't touch two files it should have
helped -- the same read-real-output-not-just-the-gate methodology
21f-21h used. Patches
applied directly to source (no `work/patch_*.py` snapshot this session --
both edits are small and are recorded verbatim below).

**23a -- `MOVQ`/`PSRLDQ` never handled for a register destination in
`Lifter._insn` (il2csharp.py), leaking a stale value into real calls.**
Investigating §0's own lead #1 (the 25 residual `Object.op_Equality`/
`op_Inequality(typeof(Object), ...)` gate rows, guessed there to be "a
second, smaller-volume variant" of 21c/21d's class-init-guard family) --
live-traced `VolumeManager.CheckStack` (VA 0x182878F40, `probe_store.py`
re-created this session, see below) against raw disassembly
(`probe_disasm.py`, new) instead of assuming the guess was right.
It wasn't: the guard-elision bound from 21c/21d is working correctly
here (swallow stops exactly at `T`). The REAL bug is a completely
different, previously-undiscovered gap: IL2CPP compiles "read the second
8-byte field of a 16-byte struct" (a boxed `KeyValuePair`-shaped value,
seen here in a `Dictionary`-style enumeration) as `movups xmm0,[mem] ;
psrldq xmm0,8 ; movq rcx,xmm0` -- and `_insn` had no case at all for a
register-destination `MOVQ`/`MOVD` (`STORE_MNEMONICS` only covers the
memory-destination case) or for `PSRLDQ`, so both fell through to the
function's final "ignore the rest silently" catch-all. Silently ignoring
a MOV is fine for genuinely irrelevant bookkeeping opcodes, but here `rcx`
had JUST been the class-init guard's `mov rcx,[rip+typeinfo]` a few
instructions earlier -- with the real `movq` never updating the tracked
register, that stale `typeof(X)` class-token value kept rendering at
every later read of `rcx`, which is exactly `Object.op_Equality(typeof(
Object), 0)`'s shape. Confirmed the same idiom recurs ~10+ times in ONE
method (`SendMouseEvents.SendEvents`, VA 0x182C7E2B0) via raw
disassembly, so this was never a one-off.

Fix: added an explicit `MOVQ`/`MOVD` case (register source: opaque
same-text copy, matching the existing `MOVSS`/`MOVUPS` reg-copy
convention; memory source: `_read_mem`) and an explicit `PSRLDQ` case
that POPS the destination register rather than leaving it stale --
modeling the actual byte-level shift would need a struct-field model this
Expr shape doesn't have, so the honest move is an invalidated ("`_`"
placeholder) register, not a confidently wrong one, same philosophy
CLAUDE.md documents for the `sub_x/*shared body*/` marker. Verified live
on all 6 files carrying the 25 gate sites (`probe_store.py`, no rebuild
needed for verification) -- `typeof(Object)` residue: 0 in every one.
`SendMouseEvents.SendEvents` went from `Object.op_Inequality(typeof(
Object), 0)` (garbage) to `Object.op_Inequality(hit.getClass(), obj16)`
(a real, correct-looking comparison). Both pipelines share `_insn`
(unlike the guard-elision idiom, which CLAUDE.md notes is independently
duplicated between `il2csharp.py`'s dead `Lifter.lift()` and
`decompiler.py`'s real path) -- confirmed by reading `lift()`'s own
dispatch, which also calls `_insn`, so this is a single edit point, not
a two-copy fix. Full-corpus `sweep_audit.py` (isolated, before 23b
landed): brace 0, dangling 0, empty_arg 0, follower 0, into_block
21,464/4,559, crashes 2 -- byte-identical to the `b22_out1` baseline.

**23b -- redundant same-method re-fetch of a pure `typeof(X).Instance`
static read (new `_singleton_cse` pass, decompiler.py), found reading
`InventoryManager.cs` at a user's request ("it looks bloated").**
`typeof(X).Instance` is a plain static-field load (batch 21h gave it a
real type; still no side effects) -- but each `.field` access off it is
its own instruction at lift time, so a source method that reads several
fields off one cached singleton (`var s = X.Instance; a = s.p; b = s.q;
...`) re-derives `Type objN = typeof(X).Instance;` FRESH on every single
line instead of reusing one. Corpus census against `b22_out1` (own
throwaway script, same-method 2nd+ occurrence count): **1,312 redundant
re-fetches across 351 methods in 129 files**; single worst method in the
WHOLE corpus is `InventoryManager.AssignTemplates` (63 in one ~230-line
method -- literally every line). Fix: a new linear pass, run right after
`_member_fold` (backing-field names must already be folded to `.Instance`
-- an earlier attempt placing it right after `_drop_dead_temps`, before
`_member_fold`, matched nothing at all, because the RHS still read the
raw `.<Instance>k__BackingField` there; found via a monkeypatch spy,
`work/probe_cse.py`, new, mirroring the `probe_nullcond.py` pattern batch
21i used). The pass tracks, per straight run of statements, the first
temp holding `typeof(TYPE).Instance` for each TYPE; a later redundant
declaration of the SAME TYPE is deleted and its uses aliased to the first
temp. Deliberately conservative: resets tracking (and stops merging)
at any brace, label, `goto`/`return`/`break`/`continue`, any
`if`/`while`/`for`/`switch`/`case`/`try`/`catch`/`finally` line, any
statement containing a call (`_IMPURE`, reused from the dead-copy/dead-
temp/dead-local passes), and any store whose LHS starts with `typeof(` --
each of those could plausibly mean the cached read didn't actually
execute on this path, or could invalidate it. Verified live
(`probe_store.py`): `AssignTemplates` 63 -> 1 real fetch (a second,
distinct fetch in the early-return branch is correctly left alone -- it's
in a different scope), method body 230 -> 114 lines. Also verified 5
hand-built edge cases directly against the pass (call/branch/label/store
invalidation all fire correctly; two interleaved types track
independently) before trusting the live result.

**The branchy re-fetch shape, root-caused against raw disassembly and
FIXED same session (23c) -- turned out to be neither a `_singleton_cse`
gap nor a CFG/phi-merge bug, both guessed at earlier in this same
investigation before the real mechanism was found.** The corpus-wide
redundant count only dropped 1,312 -> 1,136 from 23b alone (176
cleared) -- `ControllerLayoutMenu.cs` (44) and `NuisanceCustomer.cs`
(34), the next two worst files, were BYTE-IDENTICAL before and after.
`_singleton_cse` was correctly refusing these (a real branch sits
between every pair of fetches in the DECOMPILED text, its safety rule
working exactly as designed) -- but manually decoding
`ControllerLayoutMenu.SetupKeysFromCurrentLanguage` (VA 0x1806A18F0)
past `il.function_extent`'s bound (which is wrong/too-short for this
method -- a real gotcha for next time; decode a fixed larger window
instead of trusting it for a large method) showed the REAL assembly has
NO such branch structure at all: ~30 independent
`[klass]->static_fields[0] != null` guards, one per UI-text key, ALL
jumping to the exact same shared `raise_NullReferenceException()`
block on failure -- and that block reads NONE of them. The decompiler
was turning that into a ~30-deep nested if/else pyramid where every
"null" arm's body was a phantom, one-iteration-STALE duplicate call
(level N's null-branch called `.GetMiscText` using level (N-1)'s
instance temp and key string, confirmed mechanically across the whole
chain). First hypothesis (a CFG/phi-merge bug -- a shared block
duplicated per-predecessor with the wrong live-register snapshot)
turned out to be a plausible-looking dead end: `probe_cfg.py` (new,
monkeypatches `_structure` to dump `blocks`/`phi_copies` before
structuring runs) showed the shared handler block (bid 74) has 25
predecessors, EACH with its own, individually-CORRECT `phi_copies[(p,
74)]` entry (`v719 = t1001.GetMiscText("UI Text", "Move");` on edge
(5,74), `v719 = t1002.GetMiscText("UI Text", "Jump");` on edge (8,74),
etc. -- exactly the right value for THAT edge, not stale at all). The
real bug: block 74's own body is just `var t1052 =
raise_NullReferenceException();` -- it reads NONE of v711-v724, so
every one of those 25 correctly-computed phi copies is genuinely dead
code, yet `_drop_dead_copies` refused to drop ANY of them because their
RHS (`t1001.GetMiscText(...)`) is call-shaped ("impure"), and the
function's blanket rule was "impure RHS never drops, it might be the
only record of a side effect." Fixed (see 23c above): the exact-text-
twin proof already used elsewhere in this file (`_wb_finish`,
`_sfblob_dedupe`) applied to `_drop_dead_copies` -- an unread impure
phi copy now drops when its RHS text is proven to survive as another,
real statement elsewhere (which it always does for a phi copy, by
construction: `pb.end_state.get(k)` is always a snapshot of a value
some earlier statement already computed, never a fresh invocation).
Verified via a 6-case unit suite (pure dead drops; impure with no twin
stays; impure with a twin drops; two dead impure duplicates with no
third survivor leave exactly one standing, never zero; self-referential
copies still drop; a copy that IS read always stays) before trusting it
live. `SetupKeysFromCurrentLanguage`: 281 -> 164 lines, every
`GetMiscText(...)` call now renders exactly once. The deep ~30-level
nesting itself is UNCHANGED (a separate, real readability issue, not
this bug) -- see §0 lead #1 for that follow-up.

Full rebuild `b23c_out1` (11,107 files, 115,658 bodies, 0 failed,
477.0s; the intermediate `b23_out1`, 23a+23b only, was 526.1s) gated
**16 bad files / 15 ERROR / 2 MISSING** -- `gate_diff` vs `b22_out1`
AND vs `b23_out1`: 0 newly bad, 0 cleared, 0 worse, 0 better on both
(none of the three fixes touch a gate-visible shape). Full-corpus
`sweep_audit.py`, run three times (after 23a alone, after 23a+23b,
after all of 23a-23c): brace 0, dangling 0, empty_arg 0, follower 0,
into_block 21,464/4,559, crashes 2 -- byte-identical to `b22_out1`
every time. read-before-def: 309,117 -> 307,036 (23a+23b) -> 307,013
(all three) -- essentially flat; none of the three fixes targeted
undefined-temp reads (23c's phi vars were always defined, just
redundantly). `dup_impure_scan.py` (backlog §3 #4's own scanner):
duplicate impure call renders 47,341 -> 34,513 (-27.1%) from 23c alone
-- the batch's biggest-magnitude win, on a metric no earlier batch had
moved. `InventoryManager.cs` read-before-def: 630 -> 623 (23b, small
as expected -- the singleton re-fetch was already-correctly-defined
text, just repetitive, not a read-before-def instance).

**Tooling note**: `probe_store.py` and `probe_disasm.py` had been reaped
as scratch at some point after batch 21/22 (not present in `work/` at the
start of this session) and were recreated from CLAUDE.md's own
documented "Validating a change" #1 pattern; `probe_cse.py` and
`probe_cfg.py` are new this session, both built on the same monkeypatch-
spy pattern as the existing `probe_nullcond.py` (`probe_cfg.py` dumps
block/phi structure -- the tool that actually distinguished "CFG/phi
bug" from "dead-code-elimination bug" here; keep it, this class of
question will come up again). All four are in `il2csharp/work/` for the
next session.

## 0f. Batch 24 (2026-08-21, jump-table switch CFG reconstruction bug, CLOSED)

Started from this file's own §0 lead #1 (`dup_impure_scan.py`'s worst
files, `ComputedStyle.cs` 556 redundant calls in `b23c_out1`, the lead's
own instruction being "trace it live before assuming 23c's mechanism
applies twice in a row"). It didn't -- live-tracing
`ComputedStyle.ApplyFromComputedStyle` (UnityEngine.UIElementsModule, VA
0x182F00000, a property-copy dispatcher switching on `StylePropertyId`)
against raw disassembly (`probe_disasm.py`) found the repeated
`StyleDataRef<T>.Read()`/`.Write()` calls were never a CSE opportunity at
all: the method's jump-table `switch` dispatches were being reconstructed
WRONG, not just verbosely. One 16-case switch rendered as a SINGLE `case
2:` block containing all ~32 statements that belonged to 16 different
cases, unconditionally executing every property's copy logic regardless
of which `StylePropertyId` was actually passed -- a real semantic bug,
not clutter. A second dispatch was missing a case (`case 1`) entirely,
its code silently deleted.

**Root cause, three compounding bugs in `decompiler.py`'s MSVC jump-table
recognizer (`_jump_table`) and the CFG builder that consumes it:**

1. **No real bound on the entries-scan.** `_jump_table`'s loop that reads
   consecutive table entries from `.rdata` only stopped when a decoded
   target address fell outside the METHOD's own address range (`lo <= tgt
   < hi`) -- not at the table's own true end. MSVC always guards the
   dispatch with `cmp idxreg,N; ja default` right before computing the
   table address, and THAT compare's operand is the real, hardware-
   enforced entry count (verified live: `cmp eax,0Fh` bounding the 16-case
   table at VA 0x182f00183) -- but the loop never looked for it. When a
   SECOND, unrelated switch's table sits immediately after the first one
   in `.rdata` (both switches' targets are inside the same method, so
   both pass the address-range check), the loop silently walked into the
   second table too: 76 entries decoded for a table whose real bound was
   16, since the following 60 entries (`b.switch_targets[16:]`) were
   actually the SECOND switch's table verbatim. Fixed: scan backward from
   the table-base `lea`/index-load `mov` for that `cmp idxreg,N; jcc`
   pair and cap the entries loop there.
2. **Jump-table targets were never block leaders.** `_make_blocks` only
   learns block leaders from direct `Jcc`/`JMP` near-branch targets;
   jump-table targets are only decoded LATER, in `_prewire_switches`,
   which runs AFTER blocks already exist. A target address not
   INDEPENDENTLY reached some other way (e.g. also a `Jcc` target) was
   therefore never a block leader -- `_prewire_switches`'s `ip2bid.get(tip,
   -1)` silently dropped that case's edge, and its code just glued onto
   whatever block already physically occupied that address range. This
   IS the "one case block containing 16 cases' worth of statements" bug
   above: entries 16-75 of the overrun table (bug #1) were never split
   into their own blocks at all, so `_emit_switch` only ever saw a single
   target block covering the whole run. Fixed: new
   `_scan_jump_table_leaders(insns)` pre-scans every `jmp reg` in the
   method's flat instruction stream for a jump table BEFORE `_make_blocks`
   runs, folding every table's targets into the leader set `_make_blocks`
   already builds from Jcc/JMP targets.
3. **Once (2) made block splitting finer, `_jump_table`'s own backward
   scans (for the table-base `lea`, the index-load `mov`, and (1)'s new
   `cmp` bounds check) went block-local and blind.** `_prewire_switches`
   calls `_jump_table` per-BLOCK; once a block gets split right before a
   dispatch's own preamble (exactly what fix (2) causes for adjacent
   switches), the local backward window can no longer see the `lea`/`mov`
   it needs, let alone the `cmp` further back still -- confirmed live: one
   block ended up with only 5 trailing instructions
   (`cdqe;lea;mov;add;jmp`), too few for the existing 6-8-instruction
   lookback windows to find anything. Fixed: `_jump_table` now redirects
   itself to operate on the method's full flat, unsplit instruction
   stream (`self._flat_insns`/`self._flat_ip_idx`, set once in
   `lift_method`) whenever the jmp's ip is found there, so every backward
   scan sees real preceding context regardless of how finely the CFG cut
   the block. `_decode`'s OWN internal reachability-trace caller (which
   runs before `_flat_insns` exists) still gets the old block-local
   behavior via a getattr-guarded fallback -- it already passes the full
   flat list itself at that point, so behavior there is unchanged.

**A fourth, independent bug** (`_prune_nonreturning`) was found chasing
why a DIFFERENT case (`case 1`) went missing entirely even after fixes
1-3: the block ended in `jmp 0x180434670` -- a near, unconditional tail
jmp to an address OUTSIDE the method (an external helper, same tail-jmp
shape as batch 21g's write-barrier idiom, just a different helper here).
`_make_blocks` classified this as `('jmp', -1)` (target unresolved, no
successor recorded) instead of the existing `('stop',)` bucket `jmp reg`
already uses for "unresolved but still a live exit" -- and
`_prune_nonreturning`'s good-reachable-to-a-return seed set is exactly
`term[0] in ('ret', 'stop')`. A block ending in an external tail-jmp is
semantically equivalent to a `ret` (control never comes back into this
method, same as batch 21g's write-barrier tail-jmp resolves to `return;`
in the final text) -- but wasn't in the seed set, so the ENTIRE case
silently vanished, on reasoning meant only for real throw-stub dead ends.
Fixed by reclassifying an unconditional near-jmp to an out-of-range
target as `('stop',)`, matching an identical "downgrade an unresolved
target to stop" idiom already used elsewhere in the file (SEH block
dedup, ~line 2172) -- not a new pattern invented for this fix.

**Verified live** (`probe_store.py`, `probe_disasm.py`, plus new
throwaway debug harnesses, all against
`ComputedStyle.ApplyFromComputedStyle`): both jump-table dispatches now
render as real `switch` statements with all 16 cases each, every case
doing exactly its own field's copy, matching raw disassembly field-for-
field (SIMD `movups` pairs, scalar `mov [rbx+N],ecx` copies, and offsets
all cross-checked against the decoded jump table's real targets). A
THIRD and FOURTH jump-table dispatch in the SAME method (StylePropertyId
ranges 0x20000/0x30000, chained as this dispatch's own "default"
fallthrough) still render as unresolved indirect-call text -- traced but
NOT fixed this session, and NOT a regression (same behavior before and
after, see the next-session lead below).

**`dup_impure_scan.py` is NOT a good before/after metric for this fix**
-- `ComputedStyle.cs`'s redundant-call count went UP on a scoped rebuild
(556 -> 572), because 16 correctly-separated switch cases each
legitimately calling `.Read()`/`.Write()` once looks like 16x duplication
to a text-level scanner with no concept of switch-case mutual exclusion.
The real signal for this fix is correctness (verified against
disassembly), the parse gate, and the crash sweep, not that scanner.

**Validation** (this was CFG-construction code -- block leaders, jump-
table decoding, dead-end pruning -- so it got the full bar, not just a
scoped spot check):
- Scoped rebuilds (`--only UnityEngine.UIElementsModule`,
  `--only Assembly-CSharp`) + new `work/ts_gate.py` (a minimal
  tree-sitter parse gate; the old `treesitter_gate.py` had been reaped as
  scratch, sanity-checked against `b23c_out1` first: 16 bad files,
  matching this file's own documented baseline exactly, before trusting
  it on the fix). Both scoped builds: 0 bad / 0 ERROR / 0 MISSING, 0
  unbalanced braces.
- `work/read_before_def.py` on the Assembly-CSharp scoped rebuild: 13,891
  (down from batch 21j's documented 14,186 baseline, -2.1% -- a bonus,
  not the target: correctly-split switch cases stop leaking phantom
  cross-case variable reads from the old wrongly-merged block).
- Full-corpus crash sweep, new `work/sweep_crash.py` (the
  `sweep_audit.py`/full-sweep pattern CLAUDE.md documents; also reaped as
  scratch, recreated standalone): 116,178 methods, 460.1s, 2 crashes --
  `TextMeshPro.GenerateTextMesh` (1831 blocks) and
  `TextMeshProUGUI.GenerateTextMesh` (1842 blocks), both `RuntimeError('cfg
  too large')`, byte-identical to the documented pre-existing baseline.
- Full rebuild `b24_out1`: 11,107 files, 115,658 bodies, 0 failed
  (488.6s). Gate (`ts_gate.py`): **15 bad / 8,175 ERROR / 6 MISSING**,
  one file BETTER than `b23c_out1`'s 16/8,146/6 -- `TextContainer.cs`
  cleared (its `else if (anchor == 6)` row was documented in batch 22 as
  "a malformed switch-to-if reconstruction... not a stray-text bug",
  exactly this bug's signature), 0 newly bad. Brace audit
  (`tree_brace_audit.py`): 0 unbalanced, 11,107 files. `b24_out1` is a
  verified, gate-clean, crash-clean, strictly-improved candidate to
  promote over `b23c_out1`; per this file's own standing rule, promotion
  is left for a human call (§0/§6).

Next-session leads, ordered by expected payoff:
1. **The 0x20000/0x30000-range dispatches in `ComputedStyle.
   ApplyFromComputedStyle` itself, still unresolved (indirect-call text,
   same as before this session -- not a regression).** Root cause traced
   live: their table-base register (`rdx`, holding the image base) is
   loaded ONCE near the method's start and reused across all four
   dispatches, but between the earlier dispatches' inline case bodies
   (which repeatedly clobber `rdx` for unrelated `Read()`/`Write()` call
   setup) and this later dispatch there is no NEARBY reload -- the
   register is only valid via the TRUE control-flow predecessor (a
   distant `ja` from an EARLIER dispatch's own bounds check, whose nearby
   `lea rdx,[rip+imagebase]` survives across the jump because the branch
   skips the intervening clobbering code entirely). A flat linear-scan
   backward search (this session's fix) cannot see this -- linear address
   order is not control-flow order once case bodies from different
   switches are interleaved in memory. Fixing this needs a real, CFG-
   predecessor-aware reaching-definition trace for the table-base
   register, genuinely harder than this session's fix (which only needed
   the flat INSTRUCTION stream, not real predecessor edges) -- deliberately
   left alone rather than guessed at. Worth checking how common
   "chained/cascading switch-of-switches on ID-range prefixes" is
   corpus-wide before investing in this (this method alone has two; no
   census taken yet).
2. **`dup_impure_scan.py`'s remaining count, not re-measured full-corpus
   this session** (only spot-checked on scoped rebuilds, where it's a
   poor metric for THIS fix specifically, see above) -- re-run
   `work/dup_impure_scan.py` against `b24_out1` full-corpus and compare
   to the batch-23 baseline (34,513) with a literal eye: some of the drop
   will be real (other jump-table-heavy dispatchers elsewhere in the
   corpus, now correctly split into cases instead of one flattened
   block), some will be the same "16 legitimately-separate cases each
   call `.Read()`" false-positive noise seen on `ComputedStyle.cs` --
   don't trust the raw delta without spot-checking a few worst files
   the way this session did.
3. Batch 21's leads (the 451 residual `T objN` sites, the read-before-def
   `copy-rhs` bucket) are unchanged by this batch -- see §0's older
   content below and §0c.

## 0g. Batch 25 (2026-08-21, dead-copy/dead-local liveness-closure fix, CLOSED)

Started from this file's own top-of-§0 IN-PROGRESS LEAD:
`InventoryManager.DropEverything` (VA 0x1806FE330, `b24_out1` line 472)
rendered a 79-instruction method as ~80 lines, TEN pairs of completely
dead phantom locals (`obj5`/`obj25`, `obj7`/`obj27`, `obj9`/`obj29`,
`obj11`/`obj31`, `flag1`/`flag2`, `obj13`/`obj34`, `obj15`/`obj35`,
`obj17`/`obj36`, `obj19`/`obj37`, `obj21`/`obj38`, `obj23`/`obj39`)
threaded through the loop for no reason. Ground-truthed against raw
disassembly (`probe_disasm.py` pattern, live re-lift via a standalone
script following `work/probe_cfg.py`'s Metadata/Il2Cpp/Lifter/Decompiler
setup): the real loop body only touches `ebx` (-> `num1`), `dropTrash`
(captured once, never actually read downstream), and
`this.inventoryIds[ebx]`; every other var is 100% unread clutter,
including the `flag1`/`flag2` pair the lead's own ground-truth paragraph
had flagged as possibly load-bearing -- it isn't; nothing in the rendered
method ever reads `flag1`, it's part of the same dead cycle as the rest.

**Root cause, confirmed exactly as the lead traced it:**
`_drop_dead_locals` and `_drop_dead_copies` (decompiler.py) both test
liveness with a flat reference COUNT (`counts.get(name, 0) <= 1` /
`uses.get(nm)`) over a fixed number of peeling passes -- sound for a
linear dead chain (each pass drops one link, shrinking the count for the
next), but blind to a mutual CYCLE: `obj25 = obj5;` and `obj5 = obj25;`
each count as a "use" of the other, so neither line's count ever drops to
<=1 no matter how many passes run. Verified `_drop_dead_copies` has the
identical defect pre-rename (synthetic `v5 = v6; v25 = v5; v5 = v25;`
with `v5`/`v25` in `phi_names` survives untouched) -- the lead's own open
question ("check whether independently reachable... not yet checked"),
now checked and confirmed yes.

**Fix, same shape in both functions:** replace the flat count with a
mark-and-sweep liveness closure. Seed `live` from every token a
line this pass could never remove anyway (impure, `goto`-bearing, or not
a renamed-local assignment at all) reads or writes; then repeatedly walk
candidate `dst = rhs;` lines and, whenever `dst` is already live, add
every local token in `rhs` to `live` too; repeat to a fixed point.
Anything never reached -- including every member of a cycle with no
external reader -- is dead. `_drop_dead_copies` additionally has to keep
batch 23c's exact-text-twin duplicate protection for dead impure phi
copies (an unread call-shaped copy drops only when its RHS text
provably survives elsewhere, so the call's side effect is never lost);
that carve-out only applies to candidates already known non-live, so it
composes with the closure without circularity -- and since it always
protects at least one exact-text survivor, an impure candidate's RHS
tokens can be unconditionally seeded as live regardless of whether that
specific line or its twin is the one that survives (they're
textually/token-identical either way). Both changes verified against
hand-built unit suites before trusting them live (`test_dead_locals.py`:
2-cycle with/without external use, 3-node cycle, self-reference, linear
chain; `test_dead_copies.py`: the same set plus the duplicate-protection
case and a protected-line-propagates-liveness-to-its-own-operand case) --
6/6 passing in both.

**Validation** (a correctness fix to two liveness passes used on nearly
every method's final rendering -- full bar, not a scoped spot check):
- Live re-lift of `InventoryManager.DropEverything`: all ten dead pairs
  gone, output now exactly matches the ground-truth read (`num1`, the two
  `DropObject()` bursts, the `this.inventoryIds[num1] != 57` guard,
  nothing else).
- Corpus census, `work/scan_dead_cycles.py` (new; a per-file heuristic --
  sizes the win, doesn't enumerate exact sites): candidate dead
  mirror-pairs in `b24_out1` **1,510 across 581 files**; same scan
  against the rebuilt tree: **986 across 481 files**. (The residual 986
  are expected scanner noise -- coincidental 2-occurrence pairs that
  aren't actually cycles -- not confirmed-surviving instances of this
  bug; the unit suite's cycle cases are the soundness proof, this census
  is only for sizing.)
- Full-corpus crash sweep (`work/sweep_crash.py`), run twice: once right
  after the `_drop_dead_locals` fix alone (116,178 methods, 422.7s, 2
  crashes), once after both fixes (116,178 methods, 432.1s, 2 crashes) --
  both runs byte-identical to the documented baseline (the two
  pre-existing TextMeshPro/TextMeshProUGUI `cfg too large` caps).
- Full rebuild `b25_out1`: 11,107 files, 115,658 bodies, 0 failed
  (475.4s). Gate (`ts_gate.py`, re-run against `b24_out1` first to
  confirm it reproduces the documented 15/8,175/6 exactly, then against
  `b25_out1`): **15 bad / 8,150 ERROR / 6 MISSING** -- same bad-file
  count, same file list (TextMeshPro.cs, TextMeshProUGUI.cs,
  SequenceNode.cs, XmlTextWriter.cs, RenderGraphPass.cs, and the same 8
  single-ERROR/single-MISSING files), 0 newly bad, 0 cleared; ERROR count
  down 25 (8,175 -> 8,150), plausibly incidental (fewer total lines in
  the same already-malformed TextMeshPro methods shrinking descendant
  node counts), not itself the point of this fix. Brace audit
  (`tree_brace_audit.py`): 0 unbalanced, 11,107 files. `b25_out1` is a
  verified, gate-clean, crash-clean candidate to promote over `b24_out1`;
  per this file's own standing rule, promotion is left for a human call
  (§0/§6).

Next-session leads, ordered by expected payoff:
1. [x] **CLOSED 2026-08-21 (post-batch-27 session):** the 986 residual
   `scan_dead_cycles.py` hits were classified -- 100% scanner false
   positives, not surviving bugs. Root cause of the false positives:
   the v1 scanner only checked that both names in ONE candidate copy
   line (`a = b;`) had exactly 2 total file occurrences; it never
   verified the MIRROR line (`b = a;`) actually existed, so any
   ordinary, correct, linear 2-hop copy chain (`a = expr; b = a;` with
   `b` read elsewhere -- confirmed live, `STP.cs`'s `obj207`/`obj208`:
   `obj207 = ((byte*)obj192 + 0x0)[0]; ... obj208 = obj207;` then
   `obj208` used as a real call argument two lines later) coincidentally
   satisfied the count check and got flagged. `work/scan_dead_cycles2.py`
   (new) requires BOTH `a = b;` AND `b = a;` to be present (the actual
   batch-25 mutual-cycle shape) before counting a pair: **0 genuine
   mutual pairs, 0 files, tree-wide.** Batch 25's liveness-closure fix is
   fully effective corpus-wide; nothing further to do here.
2. Batch 21's leads (the 451 residual `T objN` sites, the read-before-def
   `copy-rhs` bucket) remain unchanged by this batch -- see §0c.
3. `dup_impure_scan.py`'s remaining count (34,513 as of batch 23, not
   re-measured since) and the `ComputedStyle.ApplyFromComputedStyle`
   0x20000/0x30000-range dispatch leads from §0f are both still open --
   this batch didn't touch either.

