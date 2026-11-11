## 0s. Batch 39 (2026-08-22, the top two todo leads: stack-probe
modeling + flagN inlining — CLOSED)

Drove todo leads #1 (stack-probe prologue) and #2 (flagN temp
inlining) to shipped in one session, plus two same-family enablers the
flag work surfaced (44b/44c).

- **43 — the MSVC stack probe (`__chkstk`) modeled as the
  register-preserving no-op it is.** Ground truth InventoryManager.
  Update VA 0x1806E9CA0: `mov eax,27B8h; call __chkstk; sub rsp,rax`
  then `mov rdi,rcx` — the generic CALL handler popped volatiles, so
  RCX's `this` died before the receiver save and RDI minted an
  unknown (`obj167`), which turned ~50 named fields into
  `((byte*)obj167 + 0xNNN)[0]` raw derefs and rendered the probe
  itself as `int num1 = sub_1804c67b0(this, obj1, obj2, obj3);`. The
  honest census (`work/probe_census.py`, aligned decode, dedup by
  extent — the todo's "28 methods" was the RENDER census) is **392
  distinct extents / 1,094 sites in THREE shapes**: the constant
  big-frame prologue `mov eax,imm` (152), dynamic alloca `mov rax,r8;
  call; sub rsp,r8` (498, IL stackalloc), and aligned `and rax,~0xF`
  (444) — all one callee at 0x1804c67b0. `_is_stack_probe` (new,
  il2csharp.py) identifies the callee by SIGNATURE (a gs-relative TEB
  stack read plus the 1-byte `[r11]` page-touch store, literal in the
  disasm), memoized per VA — not by address, so a different build's
  chkstk matches too; managed callees are excluded by the
  addr_to_method/addr_candidates emptiness test. The model: preserve
  EVERYTHING (real __chkstk preserves all but RAX and returns its
  input unchanged — RAX already holds the frame-size expr from the
  mov/and), emit nothing, and `sub rsp,rX` was already a no-op
  (`set_reg` ignores RSP). Tree: probe renders 70 -> 0;
  InventoryManager.cs byte-deref lines 238 -> 193, Update's receiver
  is `this` again with named fields (bearTrapTemplate, pendingPickup,
  playerMan.paused, ...).
- **44 — `_flag_inline`, new `_structure` pass (todo lead #2).**
  `bool flagN = <cond>; if (flagN)` -> `if (<cond>)`: the branch
  machinery hoists a condition result into a single-use temp right
  before its only consumer. Fires only on exact-shape heads
  (`if (flagN)` / `if (!(flagN))` / `if (!flagN)`), strict adjacency,
  and a literal-aware whole-body token count of exactly decl+if — any
  other mention (reassignment, ternary/later-if read, shadowing
  redecl, arm-body read) keeps the temp, which also guarantees an
  impure cond is never evaluated twice. Loop heads (while/do/for) are
  deliberately NOT inlined: the temp holds a value set once that the
  loop head re-reads each iteration, so inlining would re-evaluate it
  — a semantic change (pinned in the mirror). Unit mirror FIRST per
  §4: `work/flag_test.py`, 20 cases, written before the pass existed.
  Tree: flag decls 20,502 -> 9,165 (-55%); AC 3,357 -> 1,641;
  InventoryManager.cs 162 -> 85; tree line count -16,859.
- **44b — `_render`'s empty-then fold may INVERT for impure conds.**
  The old `not _IMPURE` guard covered both arms of the fold, but only
  the DROP arm (no else) is unsound for an impure cond (dropping
  `if (call()) {}` erases the side effect); the INVERT arm
  (`if (X) {} else { body }` -> `if (!(X)) { body }`) is purely
  structural — the condition evaluates exactly once either way.
  Needed the moment 44 inlines call-shaped conds (b38 inverted bare
  `flagN` but refused `Object.op_Implicit(obj)`, shipping the
  empty-then shape); the invert also unwraps a fully-paren-wrapped
  cond once.
- **44c — `_cond_dewrap`, redundant condition-head parens.** The fold
  family stacks wraps LATE: `_objop_fold` (`Object.op_Equality(A, B)`
  -> `(A == B)`) always paren-wraps and runs in `_final_text` AFTER
  render's `_fix_cond_line`, so 44's inlined heads read
  `if (!((this.bearTrapTemplate == null)))`. New module-level
  `_cond_dewrap` runs in `_final_text` right after `_objop_fold`
  (indentation-aware — `_final_text` sees rendered lines; the first
  cut anchored on `^if` and never fired) and strips fully-wrapping
  pairs from if/while heads, `!((X))` inner nesting included, via the
  same literal-aware `_paren_wraps_whole` 44 added. An outermost wrap
  is always redundant in a condition head, so this is unconditionally
  safe; it also cleared 519 pre-existing `if ((` sites (19,082 ->
  18,563; most of the remainder is non-redundant wraps like
  `if ((a) + (b))`). NOT mirrored into sim_rewrite: the sim models the
  `?`/default/select family only, and `_objop_fold` itself was never
  mirrored — noted here so the next sim user knows the boundary.
- **Process note**: two follow-up edits (44's multi-layer unwrap loop,
  44c) were applied with the text editor after their patch scripts,
  one briefly breaking a line continuation — caught by `py_compile`
  before any build; patch scripts `patch_b43_probe.py`,
  `patch_b44_flaginline.py`, `patch_b44b_emptythen.py` are the record
  of intent, the compiled source is the record of state.

Validation (full CLAUDE.md bar): 11,107 files / 115,658 bodies / 0
failed; gate **2/4,868/4** (both bad files the documented legacy-TMP
pair; gate_diff vs b38 **all-zero** — 0 newly bad, 0 cleared, 0 worse,
0 better; the ERROR -2,444 and MISSING +4 live entirely inside the TMP
pair, whose flat-lift output bypasses `_final_text` — the same
documented wobble class batches 25/38 saw, larger here because the
probe fix touches those files' biggest methods); brace 0; full-corpus
sweep 116,176 methods / crashes 2 (the TMP caps, unchanged), dangling
0, empty_arg 0, follower 0, into_block 17,718/4,079 (last recorded
21,464/4,559 at the b23c-era recount — not re-measured per batch
since; the drop is consistent with 19 batches of statement removal,
16.8k lines of it this batch). Readability: probe renders 70 -> 0,
flag decls 20,502 -> 9,165 (AC 3,357 -> 1,641), read-before-def
208,043 -> 207,852, `((byte*)` lines 196,482 -> 195,842, `if ((`
heads 19,082 -> 18,563, tree lines 2,622,156 -> 2,605,297. Goldens
regenerated post-gate (6 bodies changed, every diff read: flag
inlines, one empty-then invert, dewraps — no lost statements);
`flag_test.py` 20/20. New tools: `work/probe_census.py` (probe shape
census), `work/flag_test.py`; build `run_build_b39.py` +
`build_b39.log`; gate report `ts_gate_b39_out1.txt`; sweep sites
`../work/audit_sites_b39.txt`.

`b39_out1` is the verified gated candidate; promotion over `final_out/`
(= b36_out2) is a human call per the standing rule (§0/§6).

## 0t. Batch 40 (2026-08-22, todo leads 1/2/3 + 5a: singleton CSE to
method scope, member-load CSE, bool call args, flag-tail re-run —
CLOSED)

Four shipped fix families off the renumbered todo list, all sized
against live ground truth in InventoryManager.cs; two same-family
enablers and three unit-caught bugfixes under them.

- **45 — `_flag_inline` re-runs at the tail of `_structure`** (todo
  5a). The first run sits right after `_bool_sugar`; LATER passes
  (`_copy_prop` substituting flag-to-flag copies, `_drop_dead_locals`
  deleting dead flag decls) unblock pairs after that slot. Census at
  b39 (`work/probe_flagpairs.py`, file-level): 193 still-inlinable
  adjacent single-use pairs in AC. Same guards both runs; loop heads
  still never match.
- **45b — the pre-render head is the DOUBLE negation.** The tail run
  alone moved nothing: at the pass's slot the head renders
  `if (!(!flag1))` (the branch machinery's setcc feed) and none of
  the three exact head shapes match — `_render` normalizes it to
  `if (flag1)` only after every statement pass (ActorSpawner.Update
  VA 0x180513740 and AnimationEventTrigger.Start are the ground
  truths; spy-patched the pass to see it). Accept the two double-neg
  forms, fold emits the plain positive cond. This turned out to be
  the bigger half: AC flag decls 1,436 -> 386 (the 886 "multi-use"
  census pairs were file-level overcounts — flag names repeat across
  methods; the pass is method-scoped and was right to wait for the
  head shape).
- **46 — `_singleton_cse` to METHOD SCOPE** (todo lead 1). The
  batch-27 same-block model never folded PickupNewObj's three
  `StoreManager obj24/25/26 = typeof(StoreManager).Instance;` in five
  statements because calls sat between the fetches. New model: ONE
  fetch per type per method — the first fetch decl hoists to the
  method head (a pure static load evaluated early is invisible),
  later fetch decls drop and alias, INLINE spellings rewrite to the
  canon token (`(typeof(T).Instance).member`, bare `objK = typeof(T).
  Instance;` assignment sites, and the `Type objK = typeof(T);
  objK.Instance` temp path), and a type whose only fetches are inline
  spellings gets a minted `var objN = typeof(T).Instance;` head decl
  (max objN + 1). Calls between fetches no longer reset — the
  documented, accepted trade (a called method could in principle
  reassign the static mid-method; these singletons are set once in
  Awake, one temp per method is what the source read). Disqualifiers,
  conservative: any store to the type's statics in the method
  (`*typeof(T).Instance = v` — the setter shape seen in
  StoreManager/EODReportValues/FusionNetworkManager), an unresolved
  `typeof(T).__static_fields` mention, a store to `.Instance` through
  an unprovable receiver (disqualifies every type), and any fetch
  token that is reassigned or taken byref (its value is not the fetch
  everywhere). 46b/46c are the unit-caught bugs: the string-mask kept
  the wrong half of the literal split (assigns/hazard scans saw
  empty text — the mint path was the only one that worked), and the
  typeof-temp regex missed the `Type objK =` prefix plus the mint
  census never saw decl-less types.
- **47 — `_value_cse`, new `_structure` pass** (todo lead 2), after
  `_singleton_cse`, before `_copy_prop`. Identical pure-load decls
  fold to the first: the lifter re-materializes a member read after
  every call, so Update's `InputActionAsset objN =
  this.playerInput.actions;` wall (14 decls at b39) is a register-
  pressure artifact, not source intent — now 1 decl + 13 aliases.
  Guards: RHS must carry a `.`/`[` and no call parens (past the pure
  `typeof(T)` carve-out) and no `?`; bare-token RHS stays copy_prop's.
  47b: the first cut reset at every brace/ctrl head and never saw the
  real shape — at the pass's slot each wall decl sits behind an
  `if (this.playerInput == null)` guard (stripped later inside
  `_render`). Entries now carry brace depth: ctrl heads and nested
  blocks are crossable (same-block textual order is init order, so an
  outer canon dominates nested decls), entries die when their own
  block closes, kills (stores/ref-out-& to identifiers named in a
  cached RHS) apply from ANY depth so a crossed arm's store still
  kills, and join points (labels, case/default, catch/finally, goto)
  still reset. 47c: a decl may only fold when its token is assigned
  exactly once in the body — the golden suite caught the merge
  (BurstSolverImpl.ApplyFrame's duplicated `obj29 = ...` stores;
  SendMouseEvents' `obj7 = obj7;` self-copy) before any build.
- **48 — Boolean call args render 0/1 as false/true** (todo lead 3),
  in `_hint_arg_types`'s existing Boolean walk (next to the `(cond ?
  1 : 0)` setcc fold): `.SetActive(0)` -> `.SetActive(false)`. Fires
  only on resolved calls and exact `0`/`1` text — the 140-set
  residue is shared-body `sub_x` calls (mi unknown) and expression
  args, which stay honest. Works through property setters too
  (`this.enabled = 0` -> `false`, AdaptiveFovByAspect.Awake).

Validation (full CLAUDE.md bar): unit mirrors FIRST per §4 —
`work/cse_test.py` NEW (30 cases: method-scope singleton + value CSE
+ every hazard guard), `flag_test.py` +2 double-neg cases (22);
`cp_test` 20/20, `re_test` 0. Goldens read as evidence twice (7
bodies after 46/47/48, +4 after 45b — every diff an intended fold;
47c's catch is the suite earning its keep). Crash sweeps before AND
after 45b: 116,176 methods / crashes 2 (the TMP caps), brace 0,
dangling 0, empty_arg 0, follower 0, into_block 17,718/4,079 —
baseline-identical. Two full rebuilds (b40_out1, then b40_out2 after
45b): 11,107 files / 115,658 bodies / 0 failed. Gate **2/2/0** (same
two TMP files; ERROR 4,868 -> 2, MISSING 4 -> 0 — all inside the TMP
pair, the documented wobble class, here collapsing to the L1-header
artifact only; gate_diff b40_out1->b40_out2 all-zero). Goldens
regenerated post-gate, 50/50. Readability (b39_out1 -> b40_out2):
singleton fetch decls 1,370 -> 931, inline spellings 299 -> 133,
SetActive(0/1) 955 -> 140 (815 now false/true), flag decls tree
9,165 -> 5,629 (AC 1,436 -> 386), still-inlinable adjacent pairs AC
193 -> 1, tree lines 2,605,297 -> 2,588,867 (**-16,430**). New
tools: `work/cse_test.py`, `work/probe_flagpairs.py`,
`work/census_b40.py`, `work/probe_b40_relift.py`; patches
`patch_b45*`, `patch_b46*`, `patch_b47*`, `patch_b48*`; builds
`run_build_b40*.py` + logs; gate `ts_gate_b40_out2.txt`; sweep
`../work/audit_sites_b40v2.txt`. b40_out1 deleted (superseded
same-session by 45b).

`b40_out2` is the verified gated candidate; promotion over `final_out/`
(= b36_out2) is a human call per the standing rule (§0/§6).

## 0u. Batch 41 (2026-08-22, todo lead #1's small shapes: self-copy
drop + for-head dup-call fold; lead #2 sized to a decline; the goto
triple DIAGNOSED — CLOSED)

Two shipped fix families off todo lead #1, sized against live ground
truth in InventoryManager.PickupNewObj @ 0x1807018d0; three
same-lead items closed with data (declines); the shared-tail goto
triple root-caused to a precise mechanism and left as the next
session's sized lead.

- **49/49b — `_selfcopy_drop` (todo lead #1's last item).** Bare
  `X = X;` statements drop unconditionally: assigning a local its own
  current value is a no-op whatever surrounds it — loop-carried,
  address-taken, in an arm (the slot already holds exactly the value
  being written). The placement is the whole story: the FIRST cut ran
  after `_drop_dead_temps` and fired ZERO times — `work/
  probe_b41_stages.py` (pass-sequence spy) showed the self-copies do
  not exist there; they are MINTED by `_copy_prop`'s forward
  substitution (a loop backedge phi copy `num4 = v9;` whose source
  active-map entry resolves to num4 substitutes into `num4 = num4;`
  — 0->12 on PickupNewObj, 12->12 through every later pass, which is
  also why copy_prop's own in-loop dead sweep never dropped them).
  49b moved the call to immediately after `_copy_prop`. Note the
  TMP pair DOES run `_structure` (only `_final_text` is bypassed):
  the flat-lift bodies lost their self-copies too (4 lines/file).
  Tree: AC self-copies 103 -> 0 (PickupNewObj's tag loops now read
  `num5 += 1;` straight through).
- **50/50b — `_forhead_call_fold` (todo lead #1's for-header item).**
  A for-head cond re-rendering a call a preceding decl holds folds to
  the token: `num6 < GameObject.FindGameObjectsWithTag("Flashlight").
  Length` -> `num6 < obj31.Length`. HONESTY PROVEN BEFORE WRITING IT
  (`work/probe_b41_forhead.py`): PickupNewObj's disassembly has
  exactly 6 calls to FindGameObjectsWithTag (one per tag), each
  BEFORE its loop and inside NO back-edge span (16 backward branches
  mapped) — the native loop compares against the once-computed array,
  and the cond's call text is the lifter re-rendering that VALUE (the
  render-count artifact behind §0r's dup_impure note). Guards: exact
  call-text match against the NEAREST preceding decl in the same
  block within 8 plain statements (labels/control heads/braces/gotos
  end the window), no store/ref/out/& of the holder or of any
  identifier the call reads between decl and for; only the cond
  clause rewrites, after `_foreach_sugar` so the foreach matcher sees
  the input it always did. 50b (unit-caught before any live run): the
  decl-head slice kept the separator space before `=` and the token-
  anchored regex never matched — rstrip. Tree: AC forhead-dup 28 (26
  adjacent) -> 3 (1 adjacent; the honest residue is beyond-window and
  guard-blocked sites).
- **Declined with data, same session** (todo lead #1's other items +
  lead #2): the flagN ternary consumer census (`work/census_b41.py`)
  reads **7 sites in AC** — lead #2's remaining sized follow-up is
  negligible, closed; the "phantom first store" (`obj4 = 0f;`) is NOT
  a dead store — obj4 is address-taken later (`Physics.Raycast(...,
  &obj4, ...)`), it is the `&`-escape/slot-liveness family (census:
  0 never-read stores AC-wide), stays deferred behind lead #4's
  upstream feature; Update's flag5-9 twins are the §0q live-bool
  trade — their RHS calls are the calls' last render (23c invariant),
  kept by design.
- **Goto shared-tail triples DIAGNOSED, not implemented** (the 634
  fan-in>=2 gotos in AC): `_hoist_shared_tails` derives the hoist
  point from the LABEL'S OWN arm (`_hoist_point(lines, ac)` — one
  level up from the label's block), but in the PickupNewObj shape the
  label sits at the END of the innermost arm of a 5-deep compare
  pyramid whose OTHER arms all end `goto L` — those sibling gotos
  converge only at the LCA of their brace chains (after the WHOLE
  pyramid closes), a point control can never reach by falling out of
  the label's arm. `_falls_to`'s `cl + 1 >= H` early-return correctly
  rejects them (falling out of an outer sibling arm lands past H, and
  the next line is a `}` not an `else`). The sound extension: hoist
  to the LCA of all into-goto stacks + the label stack, with the
  funnel rule checked through else-chains whose arms end in the
  (mutually dropped) gotos — a dedicated session with the
  classify_into2 predicates mirrored first.

Validation (full CLAUDE.md bar): unit mirrors FIRST per §4 —
`work/selfcopy_test.py` NEW (5 cases) and `work/forhead_test.py` NEW
(10 cases: the ground truth + every kill guard), both written before
their passes existed; 50b is the mirror earning its keep (the rstrip
bug failed all positive cases pre-run). Existing suites: cse 30/30,
flag 22/22, cp 20/20, re 0. Goldens read as evidence twice (pre-build
49/50 with LegsAnimator's intended 2-line self-copy drop read; post-
build regen: exactly 1 body changed, same diff, 50/50). Crash sweep
(pre-build, same source the build ran): 116,176 methods / crashes 2
(the TMP caps), brace 0, dangling 0, empty_arg 0, follower 0,
into_block 17,718/4,079 — baseline-identical; sites `../work/
audit_sites_b41pre.txt`. Full rebuild b41_out1: 11,107 files /
115,658 bodies / 0 failed (494.7s). Gate: bad-file set UNCHANGED
(the TMP pair); same-tool counts byte-identical across the trees
(2/4,863/4 — NOTE the §0t "2/2/0" was the parent-dir
`treesitter_gate.py` counting top-level errors only; this repo's
`work/ts_gate.py` counts nested cascade nodes and read 4,863 on BOTH
b40_out2 and b41_out1 — the delta is all-zero either way; reports
`work/ts_gate_b41_out1.txt`). Brace audit 0/11,107. Readability
(b40_out2 -> b41_out1): AC self-copies 103 -> 0, forhead-dup 28 -> 3,
tree lines 2,588,867 -> 2,587,645 (**-1,222**). New tools:
`work/census_b41.py` (the five-shape lead census), `work/
probe_b41_forhead.py` (call-site/back-edge honesty probe),
`work/probe_b41_stages.py` (pass-sequence self-copy spy); patches
`patch_b49_selfcopy.py`, `patch_b49b_selfcopy_move.py`,
`patch_b50_forhead.py`, `patch_b50b_forhead_fix.py`; build
`run_build_b41.py` + `build_b41.log`.

`b41_out1` is the verified gated candidate; promotion over `final_out/`
(= b36_out2) is a human call per the standing rule (§0/§6).

## 0al. Batch 58 (2026-08-26, todo lead 8: `_BZEXT_RX` structurally
could not reach most of the `& 0xFF/*z*/` residue -- CLOSED, with a
self-inflicted regression caught and fixed in the same session)

**`b68b_out1` is the gated candidate.** Gate **0/0/0**, held.

Sizing (`work/census_b68_bzext.py`, new this batch): of the 14,365 masks
surviving at `b66_out1`, the old char-class regex's own content
restriction (`[^(),]+?`, no parens or commas) explained only part of the
residue. Bucketed by why each one survives:

    9,403  paren_nested  -- a wrapper whose content has its own parens or
                             a call, e.g. `(typeof(BabyDoll).
                             typeHierarchyDepth & 0xFF/*z*/)`
    4,194  bare          -- no wrapper at all: the renderer's own
                             precedence logic (fix 61a) already knew none
                             was needed, e.g. `x = ok & 0xFF/*z*/;` --
                             the old regex could never match this shape
                             in the first place, comma/parens or not
      765  paren_simple  -- a SIMPLE wrapper the old content class
                             covers, blocked by two upstream bugs (below)
        3  paren_comma   -- a close paren follows the marker but belongs
                             to an enclosing call/group with sibling
                             arguments, not the mask's own wrapper
                             (`Resize(a, b, x & 0xFF/*z*/)`)

The `paren_simple` 765 turned out not to be a sizing artifact but two
real, separate bugs: `_BZEXT_RX`'s own `(?<![A-Za-z] )` lookbehind
rejects every KEYWORD-headed wrapper, because `return (`, `while (`,
`case (` all end in "letter space paren" -- and this codebase never
renders a real call with a space before its arg-list paren (checked:
every apparent "identifier space (" hit in the corpus is inside a
string literal), so the lookbehind's only actual effect was suppressing
753 legitimate strips like `return (flag5 & 0xFF/*z*/);`. Separately,
`_flag_inline` runs immediately after `_bool_sugar` in `_structure`'s
pass order and can SYNTHESIZE a fresh `!(cond)` wrapper around a bare,
not-yet-stripped mask read straight from a `bool flagN = <cond>;` decl
(`_FLAG_DECL_RX` captures the decl's RHS verbatim) -- `_bool_sugar`
never gets a second look at text minted after it already ran, so
`if (!(ok & 0xFF/*z*/))` reaches final output no matter what the
wrapper-based regex can match.

**Fix 68** (`work/patch_b68_bzext.py`) replaces `_BZEXT_RX` with
`Decompiler._bzext_strip`, a literal-aware balanced-paren walk: it finds
the true matching open paren for a close paren that immediately follows
the marker (nesting-aware, so a call/cast/indexer inside the masked
expression is transparent to it) instead of assuming any adjacent close
paren belongs to the mask, string/char literals blanked
length-preserving first (a real line has a literal `(` inside a string
argument that would otherwise miscount the walk -- caught by a
self-check over the accepted-wrapper set, not by inspection). It refuses
the pairing -- falling back to deleting the marker text alone -- when the
span holds a top-level comma or goes negative-depth (paren_comma's
shape: not the mask's own wrapper). No wrapper case, no comma case: this
alone closed `paren_nested`, `bare`, and `paren_comma`.

**Fix 68b** (`work/patch_b68b_bzext_fix.py`), found by a PLAIN UNIT TEST
before any build or sweep ran: `_bzext_strip('while (canceled &
0xFF/*z*/)')` returned `'while canceled'` -- and the same for `switch`
and a bare (non-double-negated) `if`. The comma/negative-depth reject
only catches a MULTI-argument enclosing group; a single-content one
(`while`, `switch`, a plain `if`, or a one-argument call whose own
wrapper the renderer already dropped as redundant) has no comma to trip
on, so the walk mistook the keyword's or call's OWN REQUIRED delimiter
for the mask's droppable one and deleted grammar C# requires. Fix 68b
adds a second, independent check on what PRECEDES the found open paren:
touching an identifier/`)`/`]`/`>` with no space is call/indexer/
generic-close syntax (mandatory); preceded by whitespace and then one of
`if/while/switch/for/foreach/using/lock/catch/fixed` (checked BY NAME)
is a required statement-condition delimiter (mandatory); `return (`/
`throw (` end in a keyword too but stay OPTIONAL -- C# never requires
those parens. Unit mirror `work/bzext_test.py`, 20/20 (includes the 4
cases fix 68 alone got wrong).

**Fix 68c** (`work/patch_b68c_hierrx_fix.py`) -- fix 68/68b's OWN
regression, caught by neither the crash sweep nor the goldens nor the
tree-sitter gate (all three stayed clean), only by the CLAUDE.md #4
direct per-file diff against `b66_out1`: `_is_sugar`'s `_HIER_RX`
recognizes il2cpp's inlined IsInst hierarchy check (one of two native
fast-path tests that both fold to `!(recv is T)`; see `_is_sugar`'s own
docstring) and its comment already anticipated a masked spelling
(`(?: & 0xFF(?:FF)?/\*z\*/)?`) -- but it still required LITERAL wrapping
parens around `Y.typeHierarchyDepth`, true before this batch only
because the old char-class regex could never reach a mask nested this
deep, so `_bool_sugar` always left the mask AND its wrapper intact for
`_is_sugar` to consume. Fix 68 correctly strips this exact shape (no
comma, no mandatory-context keyword before the open paren) and the
wrapper goes with it -- nothing needs it once the mask is gone -- which
silently stopped `_HIER_RX` from matching at all, live in
`Fusion.Runtime/Fusion/NetworkRunner.cs`'s `GetServerSnapshot` (VA
0x1808A9700: two `else if` arms that should both read `!(this.
_simulation is Server)` per the native double-check idiom instead had
their SECOND arm fall back to the raw disassembled hierarchy-walk
expression -- a real readability regression, not a crash or a parse
error, which is exactly why the other three gates missed it).
`work/probe_b68_hiersugar.py` (a direct re-lift with `_is_sugar`
monkeypatched to print its input) proved the exact pre-fold text and
confirmed the shape is corpus-wide, not a one-off: `grep -rl` for it
hits 589 of 11,107 files at `b66_out1`, every one of them relying on
`_HIER_RX` firing every time. Fix: make the wrapping parens optional
(`\(?...\)?`) exactly like the mask already is, verified against the
masked+parenthesized, parenthesized-no-mask, and bare shapes before
shipping. Re-probed after: `GetServerSnapshot`'s second arm reads
`!(this._simulation is Server)` again, byte-identical to `b66_out1`.

**Numbers.** Unit mirror `work/bzext_test.py` 20/20. Full-corpus crash
sweep (`work/sweep_crash.py`) **0/116,178**, run twice (before and after
68c). Goldens **30/50, the same 20 pre-existing documented mismatches as
b66_out1, zero moved** (none of the 50 frozen bodies contain the mask
shape at all -- confirmed by grepping `goldens.json`, so this metric was
never going to see this batch either way). Full rebuild `b68b_out1`:
11,107 files / 115,658 bodies / 0 failed, 828.4s. Gate **0/0/0**, held.
Brace audit 0/11,107. Full-corpus sweep (`work/sweep_1a_audit.py`)
**crashes 0, brace 0, into_block 13,506/2,978 -- byte-identical to
b66_out1** (no CFG-shape change in this batch, as expected: every fix
lives inside `_bool_sugar`/`_is_sugar`, both post-structuring text
passes). Tree lines 2,719,896 -> **2,719,664 (-232)**.

**`& 0xFF(FF)?/*z*/` masks 14,365 -> 0 (-100%)**, the metric this lead
named as the sizing tool (`grep -rhoE '& 0xFF(FF)?/\*z\*/'`) now reads
zero corpus-wide. **A full per-file diff against `b66_out1`: exactly
2,079 of 11,107 files differ** -- 2,078 of them are precisely the files
`grep -rl` finds a mask in at `b66_out1` (checked by set difference, not
assumption), and the one extra file
(`System.Xml/System/Xml/Schema/XmlSchemaType.cs`) is a legitimate bonus:
fix 68c's now-optional parens ALSO match an occurrence of the same
native idiom that never carried a mask to begin with (a positive `==`
polarity check, `IsDerivedFrom` @ 0x1822b7a80) and had been unfolded for
an unrelated, pre-existing reason since long before this batch; folding
it now additionally lets a later pass drop a now-redundant `unsafe {}`
wrapper, reshaping that one method's braces (verified semantically
correct against the raw hierarchy-walk expression by hand, not merely
gate-clean). A coarse whole-corpus verifier
(`work/verify_b68_diff.py`, new this batch: reduces every changed line
on both sides by removing mask markers and all parens/whitespace, then
diffs the residue) flagged 160 of the 11,069 changed lines for manual
read; every one traces to an ALREADY-EXISTING downstream mechanism now
firing on text `_bool_sugar` never used to hand it -- the ternary fold
(`(cond ? 1 : 0) & 0xFF/*z*/` -> `cond`, `_bool_sugar`'s own established
rule, previously blocked by the same paren-content restriction this
batch fixes), copy-prop/self-copy-drop collapsing a newly-bare
`objN = X;` alias into its source (seen in `MicAudioCanvas.cs`,
`IPv6AddressHelper.cs`, and an AES T-box array index in
`AesTransform.cs`), and one local-variable renumbering shift from an
eliminated decl line -- no incorrect fold among them. Every
"LINE COUNT DIFFERS" file in that flag list is one of these cascades
removing a now-fully-redundant statement, not a corruption.

New tools this batch, all reusable: `work/census_b68_bzext.py` (the
paren/comma/mandatory-context sizing census), `work/bzext_test.py`
(the `_bzext_strip` unit mirror, 20 cases), `work/sim_bzext_b68.py`
(fast full-tree text-only simulation -- no metadata/binary needed --
that caught nothing wrong here but is the right first check for any
future line-local rewrite), `work/probe_b68_hiersugar.py` (direct
re-lift + monkeypatch trace, the tool that actually found fix 68c),
`work/verify_b68_diff.py` (the corpus-wide "does every changed line
reduce to a mask removal" residue check).

Promotion over `final_out/` is a human call per the standing rule
(§0/§6); `b68b_out1` supersedes `b66_out1` as the verified gated
candidate (batches 43 through 58, new.md §0w through §0al -- lead 9,
§0ak, remains open and reverted).

## 0am. Batch 59 (2026-08-26, todo lead 5c: the resolved-call arity trim
doesn't count the sret slot -- CLOSED, with a self-inflicted regression
caught and fixed in the same session, same shape as §0al's)

**`b69b_out1` is the gated candidate.** Gate **0/0/0**, held.

The lead was explicitly marked NOT SIZED -- a per-call-site question no
text census can answer. Sized it the way the lead itself prescribed
(`work/patch_probe_b69_sretarity.py`, temporary and reverted immediately
after: appends every site's shape to a module-global list, mirroring
`work/census_b50_rbdprov.py`'s instrument-the-lifter pattern): of
116,178 methods, **659 resolved-call sites** reach the arity trim
(`want = m2.param_count + (0 if m2.is_static else 1)`) with a return
type that needs a hidden sret buffer (`Il2Cpp.returns_sret`) which the
struct-return fold above it did NOT already peel off (that fold needs
`args[0]` to be a literal `&s_N`; a register-held buffer local never
matches it -- called out by name in `_hint_arg_types`'s own docstring as
a case "the sret fold above does not catch"). Of those 659, **376
actually trigger the bug** (`len(args) > want`, so `args[:want]` drops
the true LAST argument and prints everything else shifted one slot
left) -- dominated by shared-body generics (`Format` 238, `Schedule` 56,
`vbslq_s8` 18, `UpdateUI` 13, `get_position` 10, ...).

**Fix 69** (`work/patch_b69_sretarity.py`): `_hint_arg_types` and
`_positional_args` -- both called on the SAME `args` two lines below this
trim -- already add this slot UNCONDITIONALLY (`if
self.il.returns_sret(rty): ri += 1`, no fold check at all, because the
struct-return fold's own `return` means control can never reach either
of them when the fold DID fire), so the fix mirrors them exactly:
`if self.il.returns_sret(rty): want += 1`. No new guess -- reaching this
trim with `returns_sret(rty)` true already proves the buffer is real and
sits in `args[0]`.

**Fix 69b** -- fix 69's OWN regression, caught the same way §0al's fix
68c was: neither the crash sweep, goldens, nor the tree-sitter gate saw
it (all three stayed clean on fix 69 alone, built as `b69_out1` and
superseded/deleted), only a direct per-file diff against `b68b_out1`
did. `StoryScene.cs`'s `_MovePetUpCoroutine_d__39.MoveNext` (VA
0x1805E0830) went from the correct `.position` property-getter fold to
visibly broken `((obj2 - 0x58)).get_position(obj5)` -- a zero-parameter
getter printed WITH an argument, plus a brand-new spurious `Transform
obj5 = ...` temp materializing the receiver a second time. Root cause:
`rest = args[1:] if args else []` (used only where `not m2.is_static`,
feeding the property/indexer accessor folds and the generic
`recv.Method(rest)` fallback) hardcodes "args[0] is the receiver" --
true for an ordinary instance call, but Win64 puts the sret buffer in
RCX and shifts the receiver to RDX when the return needs one, so
args[0] is the buffer and args[1] is the receiver in that case. Nothing
exposed this before fix 69, because the old undercounted `want` had
already trimmed the receiver clean out of `args` for exactly the
zero-real-arg getter/setter/indexer shapes this feeds -- a getter needs
`rest` empty, which the undercount produced BY ACCIDENT. Fix 69b
(`work/patch_b69b_restoff_fix.py`) shifts `rest`'s own offset with the
identical `ri = (0 if static else 1) + (1 if returns_sret else 0)` walk,
so all three sret-offset computations in `_call` now agree. Verified
directly: a re-lift of `MoveNext` after 69b folds `.position` again,
matching `b68b_out1` (modulo direct-relift cosmetics -- full type names,
undecorated `<>` vs `__` compiler-generated identifiers -- that don't
appear in a real tree build).

**Numbers.** Full-corpus crash sweep (`work/sweep_crash.py`) **0/116,178**,
run three times (fix 69 alone, fix 69+69b, and the probe-instrumented
sizing pass). Goldens **30/50, the same 20 pre-existing documented
mismatches as b68b_out1, zero moved** (checked after fix 69 alone and
again after 69b). Full rebuild `b69b_out1`: 11,107 files / 115,658
bodies / 0 failed, 581.7s. Gate **0/0/0**, held. Brace audit 0/11,107.
Full-corpus sweep (`work/sweep_1a_audit.py`) **crashes 0, brace 0,
into_block 13,506/2,978 -- byte-identical to b68b_out1** (no CFG-shape
change: the fix is argument-list bookkeeping inside `_call`, nothing
CFG-adjacent). Tree lines 2,719,664 -> **2,719,673 (+9)** -- almost the
whole cost is argument text growing on existing lines; the handful of
new lines are spots where a previously-invisible argument value had to
be materialized into its own statement (`obj9 = b.rs;`,
`object obj1 = ((byte*)instancesOffset + 0x0)[0];`).

**A full per-file diff against `b68b_out1`: 34 of 11,107 files differ**
(40 with fix 69 alone, before 69b's own fix folded three of them --
`StoryScene.cs`, `FinaleStartCutscene.cs`, `StartCutscene.cs` -- back to
byte-identical with `b68b_out1`). Read all 34 in full, not sampled:
every hunk recovers a real, previously-dropped trailing argument with
no other change to the line -- SIMD intrinsics
(`Unity.Burst/.../X86.cs`, ~90 sites: `Sse2.add_epi8(a, b)` ->
`Sse2.add_epi8(a, b, c)`-shaped, every AVX/SSE wrapper missing its true
operand or immediate), `Unity.Mathematics` (`math.mul`, `math.saturate`,
`math.floor`, `noise.mod289`), Unity/Obi/FIMSpace quaternion and vector
math (`Quaternion.Inverse`, `Quaternion.op_Multiply`,
`Internal_FromEulerRad`, `Vector3.Normalize`, `MultiplyVector`,
`AngularVelocityToSpinQuaternion`), and one-off real bugs elsewhere
(`ContactFilter2D.CreateLegacyFilter` missing its distance argument,
`ScheduleQueryRendererGroupInstancesJob` missing `instancesOffset`,
`GetTextCoreSettingsForElement` missing a bool flag). No accessor-fold
corruption, no malformed call, anywhere in the 34.

New tools this batch: `work/patch_probe_b69_sretarity.py` +
`work/census_b69_sretarity.py` + `work/revert_probe_b69_sretarity.py`
(the lifter-instrumentation sizing pattern for a per-call-site question,
reusable for the next one of these).

Promotion over `final_out/` is a human call per the standing rule
(§0/§6); `b69b_out1` supersedes `b68b_out1` as the verified gated
candidate (batches 43 through 59, new.md §0w through §0am -- lead 9,
§0ak, remains open and reverted).

## 0au. Review 77 + partial rebuild + InventoryManager read (2026-09-08)

Review 77 (REVIEW.md) advanced the SOURCE past the b76 candidate: (1)
resolved-direct-tail args via `Lifter._tail_method_args` (Win64
positional XMM selection; 1,186 sites / 1,145 methods in the direct
sweep); (2) unknown-pointer renderer ordering (quote/select-aware scan
before `_unsafify`); (3) CLI discovery/filter repair
(`--metadata`/`--binary`, `--types` honored, `--strict`); (4)
fallback/emission failure instrumentation; (5) portable kit
(`tools/validate_corpus.py`, `tests/` 136 = 72 unit + 64
MethodDef-keyed snapshots, CRLF `.gitattributes`). Validation table:
11,107 files / 115,658 bodies / 0 failed, gate 0/0/0, sweep 116,178 /
0 crashes, into_block 13,642 (2,997) under the NEW validator vs
13,518/2,979 under `sweep_1a_audit.py` -- different tool, not a
regression; 637 files differ from the uploaded baseline, 10,470
byte-identical, strict-mode exit 0. REVIEW.md's "no `final_out/`
promoted or replaced" was true then; the evening's aborted rebuild
below changed the DISK state, not the candidate. Promotion is still a
human call. Staleness noted, not fixed: `work/run_build_*.py` +
`work/probe_*.py` still carry pre-consolidation absolute TARGET paths
(`C:\...\il2cpptest\Shift At Midnight`) -- use `testgame/` (bit the
evening probe setup; temp scripts were re-pointed, repo files untouched).

Evening: full rebuild into `final_out/` ABORTED mid-run (the
Assembly-CSharp results were already in hand). Disk tree is PARTIAL: 6
assemblies (Assembly-CSharp 391 files, mscorlib, System, System.Xml,
Unity.InputSystem, UnityEngine.UIElementsModule), Review-77 source.
NOT a candidate -- do not gate, promote, or regenerate goldens off it.

InventoryManager.cs read end to end (12,435 lines / 803 KB; 6,359 at
b38 -- growth is phi materialization + tail duplication, not game
code): `unknown` 17, `/*indirect*/` 0, `__static` 0, `goto` 264,
`object objN` 628, `sub_` calls 362 (19 distinct, 209 honest
shared-body markers). All 17 unknowns bucketed; the three
unknown-feeding callees probed to ground truth (`Metadata` + `Il2Cpp.
find_registrations` + `addr_candidates`, disasm via iced-x86):
(a) constant-`true` bool stores (5: `letGoOfInteract` x2 incl.
AutoLetGoOfClick's whole body, `canShoot`, `justStartedGasPump`,
`canAttack`) -- a `mov [rcx+off],1` renders as `unknown`: smallest
probe in the file, constant-bool store path gap.
(b) `sub_1804ce6d8`: 0 metadata candidates, 0 `addr_to_method`, not an
export; prologue is the NaN idiom (`mov rcx,7FF0000000000000h` /
`and rax,rcx` / `cmp rax,rcx` on the xmm0 double) -- an unregistered
NaN predicate (double.IsNaN shape; IL2CPP helper or folded body with no
owner). 7 call sites, each guarded by `if (0f > unknown)` (Update case
15 x2, Shoot x3, CleanSpill-adjacent GetXZDistance) -- name it
`float/double.IsNaN` and the guard conditions become decidable. Next
probe: GetXZDistance's VA + caller disassembly (the file's RVA/VA
comments give it) to read the real jcc and arity.
(c) two shared bodies the argument types already prove: `0x180895b20`
= `RaycastHit.get_point` (9 cands: Bounds.get_center, Ray.get_origin,
ReadVector3, ContactPoint/RaycastHit.get_point...; Shoot does
`sub(&obj22)` then `+0x0/+0x8` Vector3-component reads for the
"Distance" log, and `obj55 = unknown` is `hit.distance`) and
`0x180894a90` = `LayerMask.op_Implicit` (11 cands;
`sub(this.petrolTankLayer)` -> `int num20`). Neither can use the
receiver base-chain walk -- get_point's receiver is address-taken and
op_Implicit is STATIC (no receiver at all). Lead: match candidate
PARAMETER types against argument Expr types (op_Implicit(LayerMask) is
the only candidate whose parameter type fits a LayerMask argument).
(d) string-Concat array stores emit TWINS: `(new string[11])[i] = x;`
plus `((byte*)new string[11] + off)[0] = x;` (18 here, Shoot logging)
-- fix-72c's byte-cast-twin kill doesn't cover string arrays (or runs
before the array-store fold); census tree-wide, then extend the kill.
(e) `int num4 = this.itemStorages;` (ReloadSMG MoveNext: int <-
int[]) then `&num4[num5]` + `if (num1 > 30 - unknown)` -- array-typed
local mistyped as int poisons the consumer loads; array-element type
recovery at the `int[]` field load.
(f) no-change notes: Update() still opens with ~50 `objN = 0/0f`
zero-inits (the `.locals init` phantom, blocked on absent
ParamAttributes); AssignTemplates is clean straight-line code (fix 56
holds -- no pyramid, no goto); `if (this.currentInventoryIndex < 0)`
renders correctly (fix 60/60b holding in live code).

## 0at. Batch 76 (2026-09-06, todo lead 11(a): closed-generic-CLASS
static-field route -- the class-side twin of fix 74 -- CLOSED)

**`b76_out1` is the gated candidate.** Gate **0/0/0**, held. Brace
0/11,107. Sweep crashes 0/116,178, brace 0, into_block **13,518/2,979
-- byte-identical totals to b75** (naming-only change; no CFG shape
moved), sweep lines 2,053,345 -> **2,053,342 (-3)**. Build 11,107
files / 115,658 bodies / **0 failed** (784.5s). Tree lines 2,762,359
-> **2,762,356 (-3)**; **7 of 11,107 files differ**, every diff read
line by line and confirmed a win. Goldens 50/50 unmoved (the sample
holds no genericinst-static shapes; pinned by `work/b76_test.py`
instead). `work/b76_test.py` 16/16; b72 67/67, b73 32/32, b74 38/38,
staticfield 20/20, b75fold 20/20, b75 7/7.

The batch came off probe_b76_classinst.py (todo lead 11(a)'s own
demand: "needs the CLASS-side twin of fix 74"), and the probe hit on
the first try under both alignment rules. The open generic CLASS td
carries no runtime static layout at all -- EventBase`1's field_offsets
row is [0,0,0,0] and its static map collapses to {0: s_TypeId} -- so
every closed-instantiation read past offset 0 missed. The closed
blob is laid out declaration-order / sequential, and the reconstruction
proves itself three independent ways: EventCategory@0x10 (the live
render already names its type); BaseField<string> mixedValueString@520
(0x208 -- an 8-byte object load at blob+0x208, disasm-proven at
OnArraySizeFieldChanged 0x182d5bbc9 taking it as the object arg
beside the TryParse'd string); and valueProperty measuring 0x98 --
batch 73's independently-proven BindingId size -- out of the same
machinery. Packed and natural alignment agree on every live site
(they differ only past 0x210, where no site reads); shipped natural,
the fix-74 rule.

**Fix 76 (work/patch_b76.py, il2csharp.py):** `static_off_path` takes
the base type through (the lifter sfblob branch passes `base.ty`);
when the existing direct-hit/miss logic fails AND the base is a
GENERICINST resolving to the queried td AND the open row is
degenerate (all zeros -- a td WITH a real row stays owned by the old
logic, pinned), the instantiation's statics come from the new
`_sf_closed_static_map` (cached per (td, args), failures too) and are
searched the same way, including the fix-73 miss descent. The
decompiler textual `+ N` path is untouched (a genericinst owner is
unresolvable from `Full<Args>` text -- stays honest).

**Yield: 9 tokens cleared, 0 new** (line-level diff of the fixed-regex
census, work/census_b75_static.txt vs work/census_b76_static.txt):
EventBase<T>.EventCategory x5 (GeometryChanged x2, DetachFromPanel,
AttachToPanel, CustomStyleResolved -- the named read inlines into the
HasSelfEventInterests call and the dead spill drops, temps renumber);
BaseField<string>.mixedValueString (BaseListView.OnArraySizeFieldChanged
-- plus the two obj-temp-based EnumField sites, whose temps kept
their genericinst types: `.mixedValueString` and
`.mixedValueLabelUssClassName@0x1f0`); BaseCompositeField<Rect,
FloatField, float> and <RectInt, IntegerField, int> (multi-arg
instantiations work unmodified:
`.twoLinesVariantUssClassName@0x40` x4). The Traversal/UIR diffs were
checked for value-flow drift under the renumbering: the whole delta
is the inline plus a uniform -1 temp shift, verified pair by pair.
Residue: the lead-11 rewrite below (obj-temp bases that LOST their
type, deref-through-named-static, bare blob pointers, address-of
forms, sub-pointer slices).

## 0as. Batch 75 (2026-09-06, the cached-delegate backer: join-edge
phi-copy placement (fix 75) + the `??` fold (fix 75b) -- CLOSED,
`b75_out1` is the gated candidate)

**Gate 0/0/0, brace 0/11,107. Build 11,107 files / 115,658 bodies /
0 failed (839.6s).** Sweep 116,178 methods / **0 crashes** / brace 0 /
into_block **13,518/2,979** (work/sweep_b75b.log, fold active --
byte-identical totals to the fix-75-only sweep: the fold moves no CFG
shape; sweep lines 2,061,438 -> 2,053,345, the fold's collapse).
**Tree lines 2,699,104 -> 2,762,359 (+63,255)**; **2,888/11,107 files
differ**. Fold yield: **`??` delegate folds 0 -> 737 across 181 files**;
named cache stores 1,179 -> 442 (-737, exactly the fold count -- each
fold consumes its store); shared-ctor obj calls 12,302 -> 11,574.
Goldens regenerated at the gated build (no .bak kept this once --
deviation noted; verified instead by three consistent measurements:
the pre-regen run on identical source failed exactly these 8, the
00:15 raw run with the fold failed the same 8, post-regen 50/50):
the same 8 phi-placement renumberings, every diff read (pre-branch
`X = <load>;` before the fork, renumbered temps after; the fold moves
0 of the 50). Ground-truth reads of the built tree: Console-
UINavigation.OnEnable's 10-line triple is one `??` line (90 -> 80
lines in the file); Il2CppComDelegate's merge now reads the joined
tokens where the old render read arm-only temps. `b75_out1`
supersedes `b74_out1` (batches 43 through 75, §0w through §0as; lead
9 / batch 57 / §0ak remains open and reverted, source unaffected).
Provenance: `work/sweep_b75.log` (fix-75-only sweep, 759.0s),
`work/sweep_b75b.log` (with the fold, 656.2s, same totals),
`work/sweep_b75b_AC.log` (Assembly-CSharp slice, 44.7s),
`work/goldens_b75_raw.txt` + `work/goldens_b75_diffs.txt` (pre-regen
8, read), `work/run_build_b75.py` + `work/build_b75.log` (the build),
`work/ts_gate_b75_out1.txt` (the gate).

Ground truth (`work/probe_b75_delegates.py` disasm;
`work/probe_b75_stages.py` / `probe_b75_phi.py` / `probe_b75_dbg.py`
stage traces): CameraManager.SetActiveCamera (VA 0x180541950) loads
the Roslyn/MCS cache `<>c.__9__15_0` into RDI on the taken path and
the freshly constructed delegate into RDI on the null path; the
`Enumerable.Count` use reads RDI. Pre-fix the use read the
pre-branch cache-load token instead of the merged register.

**Fix 75 (`work/patch_b75_phicopy.py`, decompiler.py `_seq` jcc
handler): the join-edge phi copies move BEFORE the fork.** The old
placement emitted them AFTER the fork's closing brace whenever one
jcc edge IS the ipdom (`f == J` / `t == J`). When the branched arm
also falls through to the join, that copy executes on BOTH paths and
clobbers the arm-edge copy; `_copy_prop` then substitutes the
surviving pre-branch value into the post-join use and its backward
sweep drops the arm copy. The fix computes `pre_edge` (the jcc edge
that IS the join, when that arm reaches the join) and emits
`self._edge(cur, pre_edge, out)` at the END OF THE TEST BLOCK before
the `if` head; the old after-fork emission becomes conditional on
`pre_edge is None`. When the arm does NOT reach the join
(returns/throws/goto elsewhere) the old placement is kept -- there it
executes on the single surviving path and is correct, and the
pre-branch form would add a dead store to the returning arm. Sizing
(`work/census_b75_phiclobber.py`, run on the list entering
`_drop_dead_copies` where phi copies are intact): **48,520 sites /
2,198 methods in Assembly-CSharp alone**. Unit mirror
`work/b75_test.py` pinned the merge shape pre-fold (see below for why
it is now stale).

**Fix 75 sweep:** crashes **0/116,178**, brace 0, into_block
13,505/2,978 -> **13,518/2,979 (+13 sites / +1 method)** -- the honest
cost of the copies now rendering on both paths
instead of one clobbering the other; sweep lines 1,990,093 ->
**2,061,438 (+71,345, the merges materializing)**. **Goldens 42/50**:
AudiencePath.DrawCurved, CurrentDayManager.Rpc_RakeIntro,
DateTimeParse.ParseFractionExact, GameManager.CheckAllReady,
InputManager.UpdateState, LegsAnimator.Finder_AutoDefineOppositeLegs,
RenderGraphPass.SetColorBufferRaw, SendMouseEvents.SendEvents -- every
diff is phi-placement renumbering (`objN = <load>;` before the fork,
renumbered temps after), no wrong shape among them; re-ran with fix
75b in place, same 8 by name (the 50-body sample holds no delegate-
cache triple, so the fold is invisible to it -- §7's sample-size
caveat again).

**Fix 75b (`work/patch_b75b_fold.py` + `patch_b75b_fold2.py`, method
text in `work/b75fold_method.txt`): the backer triple folds to the
`??` spelling.** After fix 75 the merge renders as two phi copies
around the fork, so the whole compiler pattern is recognisable at the
END of `_structure` (after `_drop_dead_lastdef`, before `_render` --
no later pass can eat the `??`, and all dead-spill cleanup has
already run):
`T objA = CACHE; [objB = objA;] if (objA == null) |
if (!(objA != null)) { [empty cctor `if (<X>.initialized ...) { }`]
T objC = new T(); objD = sub_.../*shared body*/(objC, a1, a2);
CACHE = objC; [dead spills] [objB = objC;] }` ->
`T objA = CACHE ?? (CACHE = new T(a1, a2));` with later `objB` uses
rewritten to `objA` (quote-aware via `_in_string`). Guards: arm
carries nothing else; decl cache text and store LHS agree exactly;
`objA` single-assignment and `objB` exactly the two phi copies with
no pre-decl occurrence; `new`/ctor temps local to the arm; ctor
callee unresolved `sub_...` (a resolved `..ctor` keeps the old form);
spills single-occurrence with side-effect-free RHS (`_DC_PURE_RX` --
`_PURE_LOAD_RX` rejects digit-leading `<>9`-style members, which is
exactly the singleton spill's spelling, so the fold carries its own
purity rule); no `else`. Live render verified 2026-09-06:
`System.Func<AudioListener, bool> obj24 =
typeof(<>c).<>9__15_0 ?? (typeof(<>c).<>9__15_0 = new
System.Func<...>(typeof(<>c).<>9, <>c.<SetActiveCamera>b__15_0));`
with `Enumerable.Count<Animation>(obj23, obj24)` reading the `??`
decl token, the shared-ctor call gone.

**Test status (GREEN at promotion to candidate):**
`work/b75fold_test.py` 20/20 -- the FAIL(5) was a stale synthetic, not
a fold bug: it fed the fold pre-normalization spellings (`if (obj13 ==
null)` + single-paren cctor) while the production pass only ever
receives bool-sugar-normalized input (proven by spying the fold input
on SetActiveCamera: `if (!(obj24 != null))` +
`if (!(typeof(<>c).initialized != obj24))`); the synthetic now uses
the normalized forms, and the 6x undefined `base` preamble the nofold
pins referenced is defined. `work/b75_test.py` 7/7 and `work/b72_test.py`
67/67: the superseded pre-fold pins now assert the post-fold render
(the `??` decl, the consumed store, the gone shared-ctor call) while
phi placement itself stays pinned by the clobber census (pins 2-3,
spying the pre-fold stage) and the fold synthetics. Green alongside:
b74 38/38, b73 32/32, staticfield 20/20. Residue after the fold: the
pinned no-folds (self-copy tail, else, live arm statement, reassigned
lhs, mismatched ctor/store, live spill, resolved ctor).

## 0ar. Batch 74 (2026-09-05, todo lead 11(a): the genericinst
static-field route -- the lead's own mechanism was wrong twice; the
instantiation layout is RECONSTRUCTED -- CLOSED)

**`b74_out1` is the gated candidate.** Gate **0/0/0**, held. Brace
0/11,107. Sweep crashes 0/116,178, brace 0, into_block **13,505/2,978
-- byte-identical totals to b73** (fix 74 is a naming change; no CFG
shape moved), sweep lines 1,990,095 -> **1,990,093 (-2)**. Build
11,107 files / 115,658 bodies / **0 failed** (790.9s). Tree lines
2,699,834 -> **2,699,832 (-2)**; **10 of 11,107 files differ**. Goldens
50/50 unmoved (the 50-body sample holds no fix-74 shapes).

The batch came off probing the lead's own sketch before any edit, and
the sketch was wrong twice (work/probe_b74_genericinst.py, probe A):
(1) **a types row with enum 0x15 does NOT carry a td in t[0]** -- it
carries a runtime Il2CppGenericClass POINTER (open-type ptr + class_inst
ptr); the td decodes through it, exactly what `Il2Cpp.td_of_ty` (71c)
already did; (2) **the open generic td has NO runtime layout** -- its
field_offsets row is ALL ZEROS and `type_sizes[td]` is None (probed
160/161 distinct open value types; one outlier has a row) -- and the
open def's `instance_field_chain` collapses to a single bogus 0x0
entry under the offset-dedup. So "accept valuetype-underlying
genericinst rows" alone resolves NOTHING: probe A's simulation over
the live TMP_Text residue disps returned None for every one. The
static blob layout of the instantiation has to be RECONSTRUCTED from
the open td's field list plus the gc class arguments.

**Ground truth (probe_b74_layout.py / probe_b74_disasm.py)**:
TMP_TextProcessingStack`1 declares {T[] itemStack; int index;
T m_DefaultItem; int m_Capacity; int m_RolloverSize; int m_Count;
const int k_DefaultCapacity} and TMP_Text..cctor (0x182ab6040)
constructs the stack value on the stack, then copies it into
blob+0x10 as **5x16B + 8B = 0x58 bytes** (`movups [rcx+10h..50h],xmm1..xmm5;
movsd [rcx+60h],xmm0`) -- so sizeof(TMP_TextProcessingStack<MaterialReference>)
= 0x58 exactly, matching the static map's own stride
(m_materialReferenceStack@0x10, next static s_colorWhite@0x68).
MaterialReference is a CLOSED struct with an exact field_offsets row
(index@0x10, fontAsset@0x18, spriteAsset@0x20, material@0x28,
isDefaultMaterial@0x30, isFallbackMaterial@0x31, fallbackMaterial@0x38,
padding@0x40, referenceCount@0x44; size 0x38, align 8).

**Fix 74 (work/patch_b74.py, bodies in work/_b74_new_methods.txt)**:
`static_off_path`/`_sf_chain_path` restructured into `_sf_field_path`
(the field-type dispatch) + `_sf_chain_walk` (one chain level) plus
the inflated-layout helpers: `_generic_inst_args` (the
Lifter._generic_class_args twin, on Il2Cpp), `_sf_subst` (VAR 0x13
through the enclosing args by generic-parameter ordinal, MVAR fails
honest), `_sf_ty_size_align` / `_sf_vt_align` (layout-BUILDING size
and alignment; alignment = max natural field alignment capped 8),
`_sf_infl_chain` (the declaration-order reconstruction, cached per
(td, args), failures cached too), `_sf_field_size` (the SPAN CHECK's
size -- deliberately alignment-free: fix 72/73's span check read
type_sizes directly, and an alignment recursion failing on an exotic
field type would kill otherwise-valid descents; the first draft of
this probe had exactly that bug and the fix-73 TextElement pins
caught it before any build). A 0x15 field type routes: td_of_ty ->
is_valuetype -> real layout row if the open def carries one (with a
non-zero field_offsets guard) -> else the reconstructed inflated
chain. The returned second element is the **Il2CppType TUPLE now**
(not the field-table index -- a substituted generic field has no
index); the one lifter consumer updated (sfblob branch drops its
types[...] conversion) and the b72/b73 contract pins updated with it.

**Validation before the build**: probe_b74_inflated.py 40/40 -- the
reconstruction equals the cctor ground truth (0x58 + the six member
starts), all five TMP_Text residue disps resolve
(m_DefaultItem / m_DefaultItem.spriteAsset / .isDefaultMaterial /
.padding / m_Count), honesty pins hold (tail padding 0x64/0x67 ->
None), every fix-72/73 pin re-run through the new code byte-
identical, and 25/25 genericinst-vt census sites resolve
(TMP_TextProcessingStack`1 15, ValueTuple`3 4, FixedBuffer9`1 4,
Nullable`1 2). probe_b74_census.py ties every surviving token to its
covering static's mechanism; **it also exposed that
census_b73_static.py's regex matched `__static_fields` itself as
`__static_f`** (the `f` of "fields" is hex) -- every historical
`__static_N` number carried that artifact on both sides; the tool is
fixed and the honest pair is **62 -> 24 tokens (-61%), 21 -> 13
files** (old-regex pair 273 -> 222 / 66 -> 61 for continuity).

**The first build FAILED 3 bodies** -- 0 failed is the standing bar
since batch 53, so this was a live regression, and the tree diff made
it obvious (TextMeshPro.cs -3,634 / TextMeshProUGUI.cs -3,627 /
InputActionState.cs -27: the crashed bodies render as stubs).
Root cause: ONE porting slip -- `_sf_infl_chain` returned
`(chain, size)` in production while `_sf_ty_size_align`'s
nested-genericinst branch read `lay[2]` (the alignment the probe
carried as a third element and the port dropped without dropping the
read). No unit pin covered a NESTED genericinst-vt (the 25 validated
sites are all depth-1); TextMeshPro.GenerateTextMesh's statics
(descending through a genericinst field INSIDE a reconstructed
layout) hit it. Fixed by restoring the 3-tuple
`(chain, size, align)`; b74_test grew the alignment pin; rebuild
clean. **Lesson recorded: port a validated sim element-for-element
or re-diff it -- a shape change in a helper's return is exactly what
a port loses silently.**

**Ground-truth reads of the built tree** (all 10 differing files read
in full, every hunk a win): FusionProfiler's four ValueTuple`3
chunk stores render `typeof(FusionProfiler).PacketIn.Item3 = obj35;`
(+ Out/Lost/Delivered); JsonTypeReflector's bool? statics render
`return obj1._dynamicCodeGeneration.value;` /
`._fullyTrusted.value;`; Awaitable's store resolves DEEP through a
nested genericinst (`typeof(Awaitable).
_nextFrameAndEndOfFrameWiredUpCTRegistration.m_registrationInfo.
_index = 0;` -- the census had filed it under vt/class because it
only classified the COVERING static); Touch/InputActionState/
EnhancedTouchSupport's field-wise copies name through
`s_GlobalState.touchscreens.additionalValues`,
`s_GlobalState.onActionChange.m_Callbacks[m_...]` etc. (these are
the 13 deeper sites); TMP_Text's SaveWordWrappingState renders the
five blob reads under ONE typed base with real component reads
(`int num1 = obj13.m_Count; ((byte*)state + 0x2f8)[0] =
obj13.m_DefaultItem;` -- the CSE/unification win batch 73 saw on
EnhancedTouchSupport); LayoutDefaults' fixed buffers name their
elements (`typeof(LayoutDefaults).EdgeValuesUnit.__2 = obj6;` --
__0..__8 are the metadata's OWN generated field names, verified in
the FixedBuffer9`1 row); and the TextMeshPro/TextMeshProUGUI
`__static_1708` reads render `if (obj1014.
m_EllipsisInsertionCandidateStack.m_Count == 0)` -- whose
reconstructed TMP_TextProcessingStack<TMP_WordInfo> size 0x3d8 is
INDEPENDENTLY confirmed by the next static's own offset
(k_ParseTextMarker@0x1710 = 0x1338 + 0x3d8): the runtime's static
blob layout proves the inflation arithmetic.

**Gate**: 0/0/0, brace 0/11,107, sweep crashes 0/116,178,
into_block 13,505/2,978 byte-identical to b73, sweep lines -2. Full
work/ suite green (b74 38, b72 65, b73 32, staticfield 20, bzext 20,
callname 21 [PYTHONPATH], callparen 7, cp 20, cse 30,
delegate_invoke/icall/jumptable rc0, elseif 13, flag 22, flagcond
26, forhead 10, hoist 20, itfdispatch 14, lastdef 22, re 0 failures,
refarg 24, selfcopy 5); goldens 50/50. b74_out1 supersedes b73_out1
as the verified gated candidate (batches 43 through 74, §0w through
§0ar; lead 9 / batch 57 / §0ak remains open and reverted, source
unaffected). Promotion over `final_out/` is a human call per the
standing rule (§0/§6). The residue is re-split in todo.md lead 11
(generic-CLASS instantiation statics ~5, the class-side twin of this
fix; deref-through-named-static; bare blob pointers; address-of
forms; sub-pointer slices -- all with their own mechanisms).

## 0aq. Batch 73 (2026-09-05, todo lead 11(a): the recursive static-blob
inner walk -- the UIElements *Property family is a NESTED-layout problem,
not a new offset-table meaning -- CLOSED)

**`b73_out1` is the gated candidate.** Gate **0/0/0**, held. Brace
0/11,107. Sweep crashes 0/116,178, brace 0, into_block **13,505/2,978
-- byte-identical totals to b72** (fix 73 is a naming change; no CFG
shape moved), sweep lines 1,990,099 -> **1,990,095 (-4)**. Build 11,107
files / 115,658 bodies / 0 failed (756.4s). Tree lines 2,699,839 ->
**2,699,834 (-5, cs+csproj measure)**; **64 of 11,107 files differ**. **`__static_N`
tokens 1,906 -> 273 (-85.7%), files 121 -> 66** (census regex
`[A-Za-z_]\w*\.__static_[0-9a-f]+`, both sides, one method:
`work/census_b73_static.py`); **UIElementsModule 1,419 -> 31**.

The batch came off probe_b73_uiprop.py (todo lead 11(a)'s own demand:
"the offset table's meaning needs its own understanding before any
resolution is forced"). The answer: **there is no new meaning**. The
`*Property` statics are `BindingId`-typed, and BindingId is **0x98
bytes** -- a `PropertyPath` value type at chain 0x10 (spanning 0x90:
four inline `PropertyPathPart` members + an array + a length) plus the
string `m_Path` at chain 0xa0. The 0x98 strides ARE correct layout;
fix 72's single-level inner walk misses because the disps (0x8, 0x10..
0x80) land INSIDE the nested PropertyPath: the cctor copies an unboxed
BindingId (an sret buffer -- source and dest offsets line up exactly)
field-wise into the static blob. The same shape resolves UIVertex's
`simpleVert.normal.y` (TMP_InputField's m_CursorVerts fills; simpleVert
is UIVertex-typed at blob 0x14) and ScriptableRenderer's
`s_EmptyAttachment.m_LoadStoreTarget.m_BufferPointer` family (nested
RenderTarget structs). probe_b73b_inner.py simulated the recursive walk
against real metadata before any production edit; probe_b73c_sites.py
logged the live sfblob derefs.

**Fix 73 (il2csharp.py)**: `Il2Cpp.static_off_path`'s miss walk
generalizes into a recursive `_sf_chain_path(td, key, depth, seen)` --
exact chain hit wins; otherwise the largest chain entry < key whose own
value type SPANS the key descends one level (type_sizes is the exact
runtime layout, batch 51; the span test `off + sz > key` keeps padding
and past-the-field reads honest), depth-capped 4, cycle-guarded by a
path set. The innermost field's type rides back, so named components
render with real kinds (`m_Index` int, `m_Path`/`m_Name` str,
`m_AdditionalParts` arr). Decompiler-side consumers needed NO change:
`_fold_static_addrs`/`_static_field_name` route through
static_off_path since fix 72b.

**Two pre-build misfires, both caught before any build** (worth the
record): (1) the patch script's original form embedded the method body
in a Python byte-string with escaped triple quotes and failed to parse
-- replaced with the plain-text pattern (`work/_b73_new_method.txt`
read at patch time); (2) the FIRST cycle-guard seed (`frozenset((td_index,))`,
then `(td2,)`) REJECTED every self-typed static -- `Vector3.zeroVector`
is a Vector3 in Vector3's own blob, `UIVertex.simpleVert` likewise --
so the fix-72 pins went None; the path set must seed EMPTY and grow as
the walk descends. `work/b73_test.py` caught both on its first
assertions; it pins 32 cases (fix-72 results byte-identical, the new
nested names, the honest misses: padding, string/array pointer slices).

**Ground-truth reads of the built tree** (all verified in b73_out1):
TextElement..cctor now names every store
(`typeof(TextElement).displayTooltipWhenElidedProperty.m_PropertyPath.
m_Part0.m_Index = ((byte*)obj5 + 0x10)[0];` ... `.m_Path = obj5.m_Path;`,
the byte-cast zero store renders `*...m_Part0.m_Name = 0;`);
`Touch.s_GlobalState.playerState.activeFingers/activeFingerCount/
haveBuiltActiveTouches/lastId`; `Win32NetworkInterface.fixedInfo.
DnsServerList.IpAddress/Context`; `FEngineering.axis2DProjection.
m_Normal.z`; `AffineTransform`: `obj9.identity.rs.c1.y = obj3.identity.
c1.y`. **Downstream wins where the typed reads unblocked other passes**:
math.cs and ScriptableRenderer.cs lost their dead `objN = typeof(X).
__static_fields.__static_M;` spill twins (fix-58-family folds now fire
on the named forms), and EnhancedTouchSupport.TearDownState's raw
`((byte*)obj11.__static_118 + num1*8 + 0x20)[0]` renders became a real
`Finger[] obj12 = ...playerState.fingers;` with array indexing -- the
`unsafe` block wrapper dropped with them (the -4/-5 sweep/tree lines).

**Goldens**: 43/50 pre-regen, the SAME 7 documented fix-72d mismatches,
none new. Regenerated after the gated build (backup
`work/goldens_b72.json.bak`): 50/50. All 7 diffs read line by line --
the documented dead static-read drops (ActorSpawner.Update,
AmbientMusicSystem.Awake, BabyDoll.Start, GameManager.CheckAllReady,
SendMouseEvents.SendEvents) plus two fix-73-resolved bodies
(AudiencePath.DrawCurved, BurstSolverImpl.ApplyFrame) where
`zeroVector.__static_8` misses became named component reads feeding the
same dead-spill drop. AudiencePath's 12-line delta was verified
explicitly: every dropped temp (obj44/obj46/obj52/obj56) has ZERO reads
in the frozen b72 body; the live obj55/obj49 survive renumbered
(obj54/obj48) with their consumer (`obj61 = obj43 + obj55;` ->
`obj59 = obj43 + obj54;`) intact. Full work/ suite green (bzext 20,
callname 21 [needs PYTHONPATH -- pre-existing], callparen 7, cp 20,
cse 30, delegate_invoke/icall/jumptable rc0-silent, elseif 13, flag 22,
flagcond 26, forhead 10, hoist 20, itfdispatch 14, lastdef 22, re 0
failures, refarg 24, selfcopy 5, staticfield 20, b72 65/65).

**Residue** (lead 11 rewritten in todo.md): 273 tokens / 66 files, and
the mass is a DIFFERENT class -- not field-base+inner reads:
(a) **genericinst value types**: TMP_Text's 26 reads at blob 0x20..0x60
    sit inside `m_materialReferenceStack` (a
    `TMP_TextProcessingStack<MaterialReference>` -- enum **0x15
    GENERICINST**, valuetype-underlying, spanning blob 0x10..0x67), which
    `_sf_chain_path`'s `0x11/0x12` guard rejects. Accepting
    valuetype-underlying genericinst rows (decode the td from the
    genericinst payload) is the natural fix 74.
(b) **deref-through-named-static**: InputActionState's 22
    `(obj.__static_fields + 40)[num8]` -- blob+0x28 IS `s_GlobalState`
    (a held REF); the render indexes through the slot instead of naming
    the field and reading the pointee's member. Needs the
    load-named-field-then-deref mechanism, not static_off_path.
(c) **bare blob pointers as values**: dictionary keys / TryGetValue
    args (DataBindingManager 9, CallbackDispatcher's `obj11 =
    obj6.__static_fields;` family) -- honest, the pointer IS the value.
(d) **address-of forms**: `obj5.__static_fields + 2` (SqlDecimal's 21
    byte-offset statics -- the ADDRESS is the value passed on) -- the
    textual fold requires `typeof(X)`; an obj-temp klass base stays raw.

Promotion over `final_out/` is a human call per the standing rule
(§0/§6); `b73_out1` supersedes `b72_out1` as the verified gated
candidate (batches 43 through 73, §0w through §0aq -- lead 9 / batch
57 / §0ak remains open and reverted, source unaffected).

## 0ap. Batch 72 (2026-09-05, the static-field inner-component family +
the byte-cast blob twins + the dead static-read drops + switch synthesis -- CLOSED)

**`b72_out1` is the gated candidate.** Gate **0/0/0**, held; brace
0/11,107; sweep crashes 0/116,178, brace 0, into_block
13,506/2,978 -> **13,505/2,978** (the -1 A/B-located, see below); sweep
lines 2,009,536 -> **1,990,099 (-19,437)**. Build 11,107 files /
115,658 bodies / 0 failed (749.4s). Tree lines 2,719,289 ->
**2,699,839 (-19,450)**; **2,472 of 11,107 files differ**.

The batch came off re-censusing todo lead 11's residue with a probe
(work/probe_b72_static.py) instead of from the lead's own mechanism
list -- and the lead's 11(b) ("phi/spill-carried blob bases losing the
stamp") turned out to be NOT what the mass is: every probed sfblob base
resolved its td fine (both `_td` and `_td_of(base.ty)`, including a
spill-slot base `t1001.__static_fields`). The mass is 11(a), and its
true shape is the INNER COMPONENT read: static VALUE-TYPE storage in
the blob is unboxed, so `[blob + zeroVector_off + 8]` is the Vector3
component `.z` -- `static_off_names` keys at field BASE offsets only,
every such read missed, and the DECOMPILER-side `_fold_static_addrs`
then compounded each miss into a confidently-wrong name
(`typeof(Vector3).zeroVector.__static_8` names the offset-0 field under
a suffix claiming another offset -- the worst class this repo has).

**Fix 72 (il2csharp.py)**: one new authority, `Il2Cpp.static_off_path
(td_index, disp)` -- direct hits pass through; a miss walks the largest
static field base <= disp whose own value type's instance chain
contains (disp - base + 0x10) (chain keys are header-relative; blob
storage is not) and returns the dotted path plus the INNER field's own
type, so `...zeroVector.z` renders kind float. `_field_expr`'s sfblob
branch consumes it. `static_off_names` gains a per-typedef cache (it
rebuilt the dict on every sfblob read). Probe-pinned ground truth:
Vector3 blob 0x8 = zeroVector.z, Vector2 0x14 = upVector.y /
0x1c = downVector.y, Matrix4x4 0x50 = identityMatrix.<m>; every probed
b71 miss resolved through the walk.

**Fix 72b (decompiler.py)**: `_fold_static_addrs` shares the same
authority for the textual `+ N` form (`typeof(X).__static_fields + 0x8`
-> `typeof(X).zeroVector.z`), and STOPS the compounding -- a `.` after
the blob match (the lifter's own `.__static_N` miss suffix) leaves the
text raw. Two latent defects in the same guard fell out of the mirror:
the one-char `after in '+-*/'` check never fired on rendered text
(chains are space-separated, so `blob + 0x8 + 0x4` folded its FIRST hop
and misnamed the address -- the docstring's "intermediate hops stay raw"
was vacuous), and `'' in '+-*/'` is True in Python, silently disabling
the guard at end-of-string. The guard now looks past whitespace with a
tuple membership test; `blob + N + M` chains stay raw.

**Fix 72c (decompiler.py)**: the delegate-cache store renders TWICE --
the named twin (`typeof(__c).__9__1_0 = obj15;`) and a byte-cast twin.
The twin's spelling at `_sfblob_dedupe` time is the STAR-DEREF store
(`*(typeof(<>c).__static_fields + 8) = obj15;`, minted at
_rename_locals; `_render` re-spells it `((byte*)...)[0]` at the very
end) -- neither the original `_SF_BLOB_RX` nor any spelling the old
pass matched. And the named twin was never MARKED SEEN either:
`_SF_NAMED_RX`'s `\.(\w+)` cannot match `<>9__1_0` (closure members
start with `<>`). Fix: a star-form regex (all three share group layout),
`_SF_NAMED_RX` accepts `(?:<>)*\w+`, the pass is two-phase (named twins
collected first, so a twin drops wherever it sits), and it runs a SECOND
time after `_member_fold` -- the named spelling is first MINTED there by
`_fold_static_addrs` (probe: at the original call site neither spelling
exists yet). **Byte-cast twins 1,403 -> 194**; the 194 have no named
twin (unresolved owner) and stay honest. `__c` delegate-cache blocks
read clean now (ConsoleUNavigation.OnEnable ground truth).

**Fix 72d (decompiler.py)**: `_PURE_LOAD_RX` accepted only a BARE
`typeof(...)`, so every dead `objN = typeof(X).__static_fields;` spill
(1,003 sites) survived all three dead-store drops. Member chains
(`typeof(...).member`, no calls/indexers) are pure too. **Dead blob
spills 1,003 -> 39** (the 39 are read -- correct keeps). Soundness note
for the `.Instance` shape: the golden suite caught 7 bodies losing an
`objN = typeof(X).Instance;` line, and the question is whether that is
a getter CALL with side effects (singleton construction). It is not:
the lifter renders the MSVC-INLINED getter as the sfblob backing-field
read (probe_b71's log names `<Instance>k__BackingField`; `_member_fold`'s
_BK_RX renames it) -- a pure field read. A getter MSVC did NOT inline
renders as a real call and is untouched by this rule. All 7 golden
mismatches are this drop, read line by line (ActorSpawner.Update,
AmbientMusicSystem.Awake, AudiencePath.DrawCurved, BabyDoll.Start,
BurstSolverImpl.ApplyFrame, GameManager.CheckAllReady,
SendMouseEvents.SendEvents).

**Fix 72e (decompiler.py)**: `_switch_synth` -- a flat same-subject
==-constant else-if chain with >= 3 arms (the `_elseif_flatten` output
shape, which the pass runs immediately after) becomes a real C#
`switch`, census-guarded (work/census_b50_switch.py's rejection list):
`break;`/goto/label in an arm, duplicate case values, float-suffixed or
non-constant labels, non-dotted-identifier subject (switch evaluates
the subject ONCE; a decompiled property read is a getter CALL, so a
dotted path here is a field read and safe). Arms ending in a flow
transfer take no synthetic break; an EMPTY arm takes one (an empty case
block falls through, the if-chain's empty arm did not). **Switch
statements 758 -> 798 (+40 across 29 files)** of the census's ~90 clean
3+-arm chains; the rest reject on the census hazards plus chain heads
that are not bare `if (` lines. Verified against the disassembly-shape
ground truth in StunMessage.cs (the case bodies are the b71 arm bodies
verbatim, one level deeper, with the same breaks).

**Numbers.** New unit mirror `work/b72_test.py` 65/65 (static_off_path
direct/inner/no-hit cases, four full-body renders, fold/dedupe/
pure-load/switch-synth cases including every rejection hazard). Full
work/ suite green (bzext 20, cp 20, cse 30, delegate_invoke 3, elseif
13, flag 22, flagcond 26, forhead 10, hoist 20, icall 10, itfdispatch
14, jumptable 9, lastdef 22, refarg 24, selfcopy 5, staticfield 20,
callparen 7 -- FakeIl extended with static_off_path). Goldens 43/50,
the 7 mismatches all fix-72d drops (above). **`__static_N` tokens
5,564 -> 1,906 (-66%) across 969 -> 139 files** (census regex
`[A-Za-z_]\w*\.__static_[0-9a-f]+`, both sides); the field@0
compounding shape itself (`zeroVector.__static_N` etc.) **1,412 -> 0**;
star-form blob twins 0; byte-cast twins 194. Ground-truth witnesses:
DEMO_LegsAnim_RedirectVector..ctor renders
`((byte*)this + 0x30)[0] = typeof(Vector3).zeroVector.z;`
(was `...zeroVector.__static_8`); FinalSequenceManager.Awake renders
`obj7.zeroVector.z` for the same shape through an obj-temp klass base;
UpdateInputs names all five component reads (zeroVector.y / upVector.y
/ downVector.y / leftVector.y / rightVector.y).

**The into_block -1**: located by the batch-72 A/B
(work/ab_b72_safe.py -- the reverted source state is built as COPIES in
a temp tree after the incident; the reverted-side sweep reproduces
b71's exact 13,506/2,978, crashes 0). Exactly ONE method moved:
**UnityEngine.UIElements.KeyboardTextEditorEventHandler.HandleEventBubbleUp
(VA 0x182e8a8a0), 8 -> 7 sites** -- fix 72d's dead-line drops changed
what the late `_hoist_shared_tails` sees (the same interaction class
batch 49 documented), in the fixing direction.

**INCIDENT + RECOVERY RECORD (2026-09-05, same session).** During the
into_block A/B, the original A/B driver's revert step zeroed
decompiler.py: `open(DEC, 'wb').write(apply(...))` truncates the file
BEFORE `apply()` raises on a non-matching pair, and the second run then
copied the zero-byte file over its own (valid) backup -- a double
failure that destroyed the batch-72 source. LESSON (now repo policy,
CLAUDE.md): a rewrite script must build the new content IN MEMORY,
verify every assertion, and only then open the target for writing;
backups must be made once and never re-derived from the live file.
`il2csharp.py` survived (its backup was still valid). The unsafe driver
was deleted; its replacement, `work/ab_b72_safe.py`, builds the
reverted state as COPIES in a temp tree and never opens the real
sources for writing. Recovery: the
user supplied an older decompiler.py (batch-58-era vintage, 6,821
lines) and `work/rebuild_decompiler.py` replayed every
decompiler-targeting patch script (work/patch_b62_subk through
patch_b72e_dec; b67* deliberately absent -- batch 57 was reverted
upstream) test-driven over it: pairs whose OLD matched exactly once
applied, already-present pairs skipped, three areas skipped as
SUPERSEDED (the vintage carries later same-batch revisions of 63a's
_decode, 64's k-12 floor, and 66c's ok_ret form -- all final-fix
behavior verified present). The replay reached **exactly 7,142 CRLF
lines**, the lost file's measured count. PROOF OF EXACTNESS: a full
rebuild from the reconstructed source (b72_out2, 11,107 files /
115,658 bodies / 0 failed) is **byte-identical to b72_out1 on all
11,200 files**; goldens reproduce 43/50 with the same 7 documented
mismatches; the full unit suite is green (b72_test 65/65). The proof
tree was deleted after the diff; the restored input is kept at
`work/decompiler_restored_input.bak` and the replay driver at
`work/rebuild_decompiler.py` as the provenance record.

**Residue** (lead 11 rewritten in todo.md): 1,906 tokens / 139 files.
The dominant mechanism is NEW and was only visible after this batch
cleared the noise: the UIElements Property family (TextElement 184 /
VisualElement 176 / BaseListView 112 / Column 104 ...) -- their
`*Property` statics sit at huge strides (0x0, 0x98, 0x130, ...) and the
cctor copies a runtime-constructed Property object's fields into the
static storage at matching offsets, but the field's declared value type
(BindingId, one field at chain 0x10) does NOT span the stride, so
`static_off_path`'s unboxed-inner walk correctly returns None for
disps like 0x10/0x20. The offset table's meaning for these fields needs
its own understanding before any resolution is forced -- the current
renders are honest misses. Remaining `getClass()`-rooted chains and the
no-td obj-temp bases are unchanged (the lead's old (b)/(c), now the
small half).

Promotion over `final_out/` is a human call per the standing rule
(§0/§6); `b72_out1` supersedes `b71_out1` as the verified gated
candidate (batches 43 through 72, §0w through §0ap -- lead 9 / batch
57 / §0ak remains open and reverted, source unaffected).

## 0ao. Batch 71 (2026-09-05, the static-field naming family: the
literal-shadow wrong names + the ty-less typeof cells -- CLOSED)

**`b71_out1` is the gated candidate.** Gate **0/0/0**, held; brace
0/11,107; sweep crashes 0/116,178 with into_block byte-identical to
the reverted-source A/B (13,506/2,978 both sides -- see the §0an
correction below).

The lead came from re-censusing the batch-16 leftovers against
b70_out1, not from the lead list: the backlog claimed
`__static_fields + N` was 0 tree-wide at b38, but the live tree held
5,342 `__static_fields` lines across 929 files, 11,369 `__static_N`
fallback tokens across 1,158 files, `string.Empty` rendered 0 times,
and -- the decisive find -- DateTime.cs rendered
`obj7.TicksPerMillisecond` (a const long) as a POINTER BASE for the
real `s_daysToMonth365` array load: live confidently-wrong names, the
class this repo treats as worst (the batch-11 Guid.cs lesson).

Two root causes, probe-pinned (work/probe_b71_staticnames.py,
probe_b71_sfblob.py, probe_b71_sfblob2.py, probe_b71_sfblob3.py):

**Fix 71a -- `static_off_names` filtered nothing.** Every field row
entered the offset map first-wins via `setdefault`: compile-time
LITERAL consts (FA_LITERAL, no runtime storage, every fo row forced
to 0x0) shadowed the first real static at 0x0 (DateTime's 37 literals
hid s_daysToMonth365; string's hid Empty -- the map's 0x0 owner was
`StackallocIntBufferSizeLimit`), and instance fields' header-relative
offsets collided with blob offsets. Filtered to FA_STATIC and not
FA_LITERAL -- the same collision field_offset_map filters from the
instance side (statics' fo rows ARE blob offsets: DateTime
0x0/0x8/0x10/0x18/0x20 = s_daysToMonth365/366/MinValue/MaxValue/
UnixEpoch, all hand-checked).

**Fix 71c -- the owner TypeDef is stamped at usage-slot decode time.**
`typeof(X)` only resolved statics through `Lifter._td_of(base.ty)`.
The BSS runtime-cache cells (`_runtime_cell_usage` -- where
`typeof(string)` and the closure-class `typeof(__c)` cells live)
carry `'type': ty_of_td.get(td_idx)`, and ty_of_td has NO CLASS/
VALUETYPE row for System.String at all (its rows are STRING/SZARRAY
forms), so those cells arrived with ty=None and every blob read fell
to `__static_N` -- the direct-chain form alone accounted for 1,638
`__static_0` sites (the `string.Empty` mass). Now `decode_slot`
stamps `'td'` (new `Il2Cpp.td_of_ty`, mirroring `Lifter._td_of`),
`_runtime_cell_usage` stamps the td it already had in hand, both
klass-construction sites (`_read_mem` kind 1/2, the LEA usage path)
carry it on the Expr as `_td` (the fix-66 `e._mi` pattern; new
`__slots__` entry, work/patch_b71b_tdslot.py), the sfblob Expr
threads it, and `_field_expr`'s sfblob branch consumes it as the
fallback when `_td_of(base.ty)` fails.

**Tested and DROPPED:** the phi-merge text-rebuild theory
(decompiler.py ~1225, the dry pass's `L.regs[k] = Expr(v)`). A stack
capture at the constructor (probe_b71_sfblob3.py) plus reading pass 2
showed the REAL pass already carries the full Expr when all preds
agree (`merged[k] = vals[0]`, ~1277); the kind-'?' typeof bases in
the probe logs were dry-pass-only and never reach output. No change
made there.

**Numbers.** New unit mirror `work/staticfield_test.py` 20/20 (map
contents, annotation stamps, both full-body renders). Full work/
suite 66 passed, the same 20 documented golden mismatches, none new.
Goldens were regenerated at this gated build (the standing
at/before-promotion rule): the old-vs-new diff moved EXACTLY the 20
documented mismatch names -- batch 71 itself moved 0 of the 50
sampled bodies (the sample holds no static-field shapes; its real
sites are pinned by staticfield_test and the sweep) -- suite 50/50
since (`work/goldens_b70.json.bak` kept).
Sweep A/B (work/ab_b71_into_block.py -- revert-only-71, sweep,
restore byte-identical): crashes 0/116,178 and into_block
13,506/2,978 BOTH sides; sweep lines 2,010,027 -> 2,009,536 (-491).
Build `b71_out1`: 11,107 files / 115,658 bodies / 0 failed (836.5s).
Gate 0/0/0; brace 0/11,107. Per-file diff: 987 of 11,107 files
differ; tree lines 2,719,075 -> 2,718,561 (-514). **`__static_N`
tokens 11,369 -> 8,586 (-2,783) across 1,158 -> 969 files**;
`typeof(string).Empty` renders where `__static_0` chains stood; every
DateTime wrong-name witness gone (4 -> 0), and the composed
`((byte*)X + i*4 + 0x20)[0]` reads are real `X.s_daysToMonth365[i]`
indexers now -- the `unsafe {}` wrappers over them went with the
pointer arithmetic (DaysInMonth: `return obj3.s_daysToMonth365[month]
- unknown;`).

Ground truth: DateToTicks 0x181C955F0 disassembled
(work/probe_b71_dateticks_disasm.py) -- leap arm `add r8,8` off the
static base, non-leap plain, merged, `[r8]` loads the array pointer,
elements at `[r8 + idx*4 + 0x20]` -- the named arms and the element
indexing are right; the post-merge `obj5.s_daysToMonth365` shape is
the PRE-EXISTING phi-offset-loss (identical in b70, which named it
TicksPerMillisecond on both paths).

**§0an correction (bookkeeping, not source):** §0an/§1 document
batch 60's sweep as into_block 13,506/2,978 -> 13,650/3,000. The
saved `work/sweep_b60.txt` is stale batch-52-era output (it still
shows the two pre-63b TMP cfg-cap crashes and 12,502/2,926), and this
batch's same-tool A/B reads 13,506/2,978 on BOTH the reverted (=
b70-equivalent source) and patched sides -- the 13,650/3,000 figure
does not reproduce under sweep_1a_audit.py on b70 source. Current
same-tool truth for both b70 and b71: **13,506/2,978**.

**Residue -- a new lead, three mechanisms, in size order** (8,586
tokens / 969 files remain):
- static VALUE-TYPE field inner-component reads (~2,700): the map is
  keyed at field BASE offsets only, so `[blob + zeroVector_off + 4]`
  (Vector2.y) misses and renders `zeroVector.__static_4` --
  zeroVector 1,412 / zeroMatrix 313 / displayTooltipWhenElidedProperty
  207 / s_NextId 198 ... needs off = field_off + inner_off resolution
  through the field's own value type (unboxed: no 0x10 header).
- phi/spill-carried blob bases losing the stamp (a fresh phi Expr or
  a slot reload has neither ty nor _td).
- getClass()-rooted chains (`obj.getClass().__static_fields...`): the
  klass Expr's td would come from the recv's type -- the same
  upstream type-recovery class as lead 3's klass-slot bucket.

Promotion over `final_out/` is a human call per the standing rule
(§0/§6); `b71_out1` supersedes `b70_out1` as the verified gated
candidate (batches 43 through 71, new.md §0w through §0ao -- lead 9 /
batch 57 / §0ak remains open and reverted).

## 0an. Batch 60 (2026-09-01, todo lead 3: delegate `invoke_impl`
recovery -- CLOSED, including generic return substitution)

**`b70_out1` is the gated candidate.** Gate **0/0/0**, held.

The b66 residue census named 626 delegate thunk calls of the regular
`d.invoke_impl(d.method_code, <real args>, d.method, d.invoke_impl)`
form. The runtime fields are inherited from `System.Delegate`, but the
receiver's actual TypeDef declares `Invoke`; that declaration is enough to
recover the managed call, its arity, and its return type without guessing.

**Fix 70** marks a typed `invoke_impl` field load with its receiver, resolves
that receiver TypeDef's non-static `Invoke` MethodDef, replaces the native
`method_code` argument with the delegate receiver, and sends the site down
the ordinary resolved-call path. That existing path then performs argument
typing and trimming, byref spelling, return-register selection, and
instance rendering, producing `predicate.Invoke(node)` instead of an
unknown function-pointer call plus stale register spray.

The first focused sret probe found the non-obvious required half before a
corpus run: generic delegates declare `Invoke` against open `VAR` types.
For `Func<Vector3>`, treating the declaration's `TResult` literally loses
the hidden struct-return buffer and duplicates the invocation when the
result is read. Fix 70 therefore reads the receiver GENERICINST's concrete
class arguments and substitutes them into `Invoke`'s return and parameter
types before any ABI decision. The pinned `StartEndModifier.Snap` site now
emits exactly one `obj24 = this.adjustStartPoint.Invoke();`; the
`Func<GraphNode,bool>` site folds directly into
`else if (!(this.filter.Invoke(node)))`.

**Numbers.** New integration mirror `work/delegate_invoke_test.py` pins a
generic bool return, a generic hidden-sret return, and a concrete delegate;
the full lightweight suite is **36/36**. Full-corpus sweep:
**116,178 methods / 0 crashes**, brace/dangling/empty-arg/follower all 0;
into-block **13,506/2,978 -> 13,650/3,000**, an honest structuring movement
from newly typed bool-return calls entering downstream condition folding.
Goldens **30/50**, the same 20 documented pre-existing mismatches as
b69b_out1. Full rebuild `b70_out1`: **11,107 files / 115,658 bodies / 0
failed** (539.9s). Tree-sitter gate **0/0/0**; brace audit 0/11,107.

The indirect census moves `invoke_impl` **626 -> 3 (-99.5%)** and total
`/*indirect*/` **7,532 -> 6,909**. The three survivors are deliberately
honest: two conditional runtime casts whose static type is only
`System.Delegate` (`Component` and `MarshalByValueComponent`), and one
ref/out local whose concrete `RpcStaticInvokeDelegate` type did not survive
into the field-load expression (`NetworkRunner`). No type is guessed from
nearby text.

A deterministic full per-file diff against `b69b_out1` changes **229 of
11,107 files**. Every changed file contains at least one converted delegate
site; the hunks remove all 623 recovered raw calls and add managed `Invoke`
renders plus downstream condition/copy/temp simplifications. Tree lines
2,684,731 -> **2,684,133 (-598)**. The two old delegate-bearing files not
in that changed set are exactly the files containing the three honest
residual calls.

Promotion over `final_out/` is a human call per the standing rule (§0/§6);
`b70_out1` supersedes `b69b_out1` as the verified gated candidate (batches
43 through 60, new.md §0w through §0an -- lead 9, §0ak, remains open and
reverted).

## 0ak. Batch 57 (2026-08-25, todo lead 9: the surviving `unknown`
flag-specific conditions) -- ATTEMPTED AND REVERTED, source unchanged
from b66_out1

**No candidate tree. `decompiler.py` is byte-for-byte back to its
b66_out1 state; every file this batch touched only lives under `work/`.**

Sizing (`work/census_b67_unknown_split.py`, new this batch): the first
cut hooked `il2csharp.flag_cond` and found only 16 hits in a 5,809-method
sample -- a >100x undercount, because `decompiler.py`'s OWN call site
(`exec_block`'s CONDITIONAL_BRANCH handler, the one almost every method's
structured output actually goes through) does `from il2csharp import
(..., flag_cond)`, a separate name binding the module-attribute patch
never reached. Patching `decompiler.flag_cond` too found the real
population: 44 hits, split **45.5% "no setter recorded" / 27.3% "sign
setter present, unmodelled pair" / 27.3% "parity setter present,
unmodelled pair"**.

Tracing the "no setter" bucket found fix 60's own documented mechanism
(carry the flags pair, and which instruction set it, across a block
boundary when predecessors agree) was DEAD CODE in both lift passes:
every site that builds a `!flags` end-state Expr passes `ty=None`
(`Expr('%s\x01%s' % ft, None, '?')`, two sites), and the only consumer
needs `isinstance(fprev.ty, tuple)` to be true -- which it never can be.
Separately, and worse: pass 2 (the pass that actually emits the text you
see) never had a per-block reset of `L.flags`/`L._flags_mn` at all --
only pass 1 (dry, discovers phi-merge locations only, its own `b.cond`
output is thrown away every iteration) resets and rebuilds it. Pass 2
let the pair carry over raw from whatever block RPO visited immediately
before the current one, not necessarily its real CFG predecessor.

**Fix 67** (`work/patch_b67_flagsmn.py`) stored the merged (lt, rt) pair
back into `Expr.ty` to make the existing dead check fire, added a
side-channel dict (`flags_mn_by_block`, block id -> setter mnemonic) so
the SETTER could ride along too (gated on every predecessor agreeing on
all of setter+lhs+rhs text, never a guess -- two predecessors can reach
the same (lhs, rhs) TEXT through different setters, e.g. `cmp x,0` and
`sub x,0` both park `(x, 0)`, and `flag_cond`'s derivation differs by
setter), and gave pass 2 the same reset-then-reconstruct-before-
exec_block flow pass 1 already had. **The full-corpus crash sweep
(`work/sweep_crash.py`, new this batch) caught the bug immediately: 223
crashes, all `TypeError: unsupported operand type(s) for >>: 'str' and
'int'`.** `Expr.ty` is read EVERYWHERE ELSE in this codebase as the
il2cpp `(data, bits)` type tuple (`(e.ty[1] >> 16) & 0xFF`-shaped code),
and a `!flags` end-state Expr lives in the same `regs`/`end_state` dict
as ordinary register Exprs, so generic type-tag code reached it and bit-
shifted a string. This is almost certainly WHY fix 60 shipped with
`ty=None` in the first place -- not an oversight so much as an abandoned
attempt at the same idea.

**Fix 67b** (`work/patch_b67b_flagsmn_fix.py`) replaced the `.ty`-based
plumbing with the side-channel dict for BOTH the (lt, rt) pair and the
setter (never touching `Expr.ty`), requiring all three to agree
unanimously across every predecessor. Crash sweep clean (0/116,178),
goldens clean (30/50, the same 20 pre-existing documented mismatches as
b66_out1 -- zero moved), tree-sitter gate clean (0/0/0 over a real full
rebuild, `run_build_b67.py` -> `b67_out1`), brace audit clean
(0/11,107). **None of these caught the actual bug.**

**A direct file diff against b66_out1 did.** 191 of 11,107 files
differed -- more than the census sample's ~44-scaled-up count predicted,
meaning the mechanism WAS firing outside the sampled slice. Reading one:
`Assembly-CSharp/Computer.cs`, `if (this.tabs.Length == 1)` -- an
ORDINARY `CMP_OPS`-mapped `==` condition, not even one of the six flag-
specific mnemonics this fix targets -- rendered as `if (unknown ==
unknown)`. Root cause not isolated (`exec_block`'s branch handler reads
`lhs, rhs = L.flags` for EVERY conditional branch, mapped or not, so any
bug in the reconstruction can corrupt an ordinary comparison too; the
side-channel's unanimous-triple gate is presumably firing where the
predecessor's true carried state doesn't actually match what
`flags_mn_by_block` recorded for it, but this was not chased further).
**Reverted in full** (`work/revert_b67_all.py`, restores the exact
pre-batch bytes of all three touched regions) rather than ship a
plausible-but-unproven theory under time pressure; spot-checked the
specific Computer.cs method directly against the reverted source
(`this.tabs.Length == 1` back) and re-ran the full-corpus crash sweep
(0/116,178) as the final confirmation. `b67_out1` was deleted (built
from the buggy source, not a valid candidate).

**Lesson for whoever picks this back up:** the crash sweep and goldens
in this batch were, in retrospect, run against an ACCIDENTALLY INERT
intermediate state (the manual `ty=ft`->`ty=None` revert step between
fix 67 and 67b left the OLD `.ty`-gated reconstruction permanently dead
again, so nothing new was actually exercised) -- they never tested the
real fix 67b logic at all. **Only the full build + a direct per-file
diff against the known-good baseline caught the regression.** Don't
trust a clean crash-sweep/goldens run on this kind of change without
also confirming the mechanism actually fired during that same run (e.g.
instrument the reconstruction's own hit/miss counts, not just its
absence of crashes). The sizing tool (`work/census_b67_unknown_split.py`)
and the crash sweep (`work/sweep_crash.py`) are both real, valid,
reusable additions to `work/` regardless of the revert.

