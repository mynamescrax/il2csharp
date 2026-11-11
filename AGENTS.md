# AGENTS.md — new-session tutorial

`il2csharp` is an IL2CPP → C# decompiler: `global-metadata.dat` +
`GameAssembly.dll` in, a C# tree out, every body lifted from native x64.
This file orients a new session. Normative rules live in `CLAUDE.md`;
start there, then `docs/todo.md` (Current work section).

## First reads (in order)

1. `CLAUDE.md` — architecture, mandatory guardrails, validation gates.
2. `docs/todo.md` — current work (top section is live), what's done,
   what's deferred with evidence.
3. `docs/handoff-2026-09-23.md` — 2026-09-23 stop record (historical);
   the 2026-09-22 failure-class inventory (the former root `TODONOW.md`)
   is now an appendix of `docs/todo.md`. Live work is `docs/todo.md`;
   the pre-reorg `nowtodo.md` no longer exists.
4. `docs/README.md` — map of every doc and `§NN` cross-reference.
5. `docs/construct-mapping.md` — what native constructs recover as what
   C#, plus the detailed internals/validation notes.

## Code map

- `il2csharp.py` — thin CLI launcher (CRLF **with** BOM).
- `il2cpp/` — the package (all CRLF, no BOM). Public names re-exported
  from `il2cpp/__init__.py`:
  - `metadata.py`, `binary.py` — `global-metadata.dat`, PE/ELF frontends.
  - `runtime/` — `Il2Cpp`: registrations, usage slots, EH4 (`core.py`
    holds the class; `registration`/`types`/`fields`/`eh` mixins).
  - `lifter/` — symbolic x64 over iced-x86 (`state`, `values`, `insn`,
    `calls`, `render` mixins; `aggregates.py` = stack-tile/struct
    provenance).
  - `expr.py` — `Expr` values (text + il2cpp type tuple + kind).
  - `dec/` — CFG + structured decompiler: `build` (blocks, site scans),
    `analyze` (dry/real exec, merges, phi copies), `structure`
    (the ~25-stage statement pipeline — pass order matters, read it
    before reordering), `flow`/`highlevel` (sugar passes incl.
    `_switch_synth`, `_hash_string_switch`), `textpass` (final
    `*(E+N)` → `((byte*)E+N)[0]` rendering), `emit`, others.
  - `emitter.py`, `headers.py`, `cli.py`, `arm64.py` scaffold.
- `tests/` — portable unit tests (LF) + game goldens
  (`test_game_goldens.py`, `tests/goldens_review84.json` — frozen).
- `tools/` — `inspect_methods.py` (`--mi` exact MethodDef rows),
  `corpus_common.py` (fixture loader). Add `tools/` to `PYTHONPATH`.
- `work/` — scratch runners (`work/lib/`: `sweep_audit.py`,
  `tree_brace_audit.py`, `ts_gate.py`; routing in `work/README.md`).
- `testgame/` — local, git-ignored licensed fixture (never tracked or
  redistributed; see `docs/public_release.md`).
- `final_out/` — last promoted tree (r11, 2026-10-01). Read-only reference.
  Never edit, never rebuild into.
- `validation_reports/` — frozen gate evidence. Don't touch.
- Temp scratch: `C:\Users\crax\AppData\Local\Temp\opencode` (outside repo).

## Session setup (PowerShell)

```powershell
$env:PYTHONHASHSEED = '0'
$env:IL2CSHARP_METADATA = (Resolve-Path 'testgame/ShiftAtMidnight_Data/il2cpp_data/Metadata/global-metadata.dat').Path
$env:IL2CSHARP_BINARY = (Resolve-Path 'testgame/GameAssembly.dll').Path
$env:PYTHONPATH = '<repo>;tools'
```

## Common tasks

**Lift one method** (the fast loop — no file I/O):
`tools/inspect_methods.py --metadata ... --binary ... --mi 25293`.
Goldens key on MethodDef row (`mi`), never VA (shared bodies alias).

**Portable tests:** `python -m pytest -q -m "not game" --disable-warnings`
(1027 pass). **Full suite:** `python -m pytest -q` (~7 min, needs fixture
env above; suite is fully green — any failure is yours).

**Rebuild a tree:** `python il2csharp.py testgame -o <name_out1> [--only
Assembly-CSharp] [--workers N]`. `--workers 0` = half the cores (max 8);
the tree is byte-identical, only the schedule changes; `--max-methods`
forces 1. Name output `*_out1/` (git-ignored). Gate with
`python work/lib/tree_brace_audit.py <dir>` (must print 0 unbalanced).

**Land a source fix:** repro first (probe script in temp dir, never in
repo), binary-safe patch (below), compileall, portable suite, targeted
`--mi` re-lifts, full-suite recount (failure SET must be byte-identical
to the triaged list), docs, commit, push. Decline-by-default: every
unproven shape keeps today's spelling; raw is always honest.

## Iron contracts (violations cause phantom diffs / flaky output)

- `il2cpp/*.py` are CRLF no-BOM: edit via binary read/write scripts,
  assert `d.count(b'\r\n') == d.count(b'\n')` after every touch.
  Read-text/write-text, `sed -i`, and heredocs silently rewrite to LF.
  `tests/*.py` and `*.md` are LF.
- Never open the target for writing until assertions pass (build in
  memory, assert, write once); never re-derive backups from live files.
- PowerShell 5.1: no `head`/`tail`/`grep`/`rm`/`||`/`&&`; no `>` redirect
  (writes UTF-16); quote paths with spaces. `PYTHONHASHSEED=0` always —
  set iteration order leaks into temp names otherwise.
- GitHub is the history authority for the post-scrub history. The
  2026-09-28 scrub removed the licensed fixture and every full-body /
  disassembly artifact from all of it and pruned LFS, so every pre-scrub
  commit hash changed; the intended local backup bundle is no longer
  present (see `docs/public_release.md`), so hashes in older docs no
  longer resolve anywhere. Never track or publish game data or
  decompiled output (`testgame/`, `final_out/`, `work/` are all ignored),
  never commit secrets, and never regen snapshots or promote output
  without an explicit user call. Stash-prove-clean before attributing a
  break to your change.

## In flight (2026-10-27)

- **Fix 146 (2026-11-04): metadata v39 frontend** (`il2cpp/metadata.py`,
  Unity 6.3/6.4): 12-byte section descriptors and variable-width indices.
  Validated on *No, I'm not a Human* (18,598 types / 136,688 methods,
  5,934 bodies lifted, 0 failed); portable 1,471 passed. Committed and
  pushed on `main`.

- **Batch on `main` (2026-10-25 .. 2026-10-27, pushed): fixes 142-145
  plus three non-fix source commits. The batch ended at `b507823`, and
  fix 146 is the only commit on `origin/main` after it. Gated together at
  `work/cg8/b21`, the
  first tree since `b20` (fix 141): gate **428,845 (-10,733 vs b20)**,
  zero parse-level code moves; portable 1,470 passed; game 271 passed /
  13 failed = exactly the triaged pin/golden list, so nothing here moved
  a golden of its own. The push happened (`b507823`); re-pin is still a
  user call, batch state in `docs/handoff-2026-10-27.md`. Details below;
  full entries in
  `docs/todo.md` top.**
- Fix 145 (2026-10-27, P/Invoke declarations from the marshalling stub;
  `il2cpp/pinvoke.py`): `mov rax,[cell]; test; jne` + a fully populated
  `PInvokeArguments` at the `il2cpp_codegen_resolve_pinvoke` call is the
  original `[DllImport(...)] static extern ...;`, so the row stops
  printing lifted plumbing. Structural frame tracking, gated on the
  `PInvokeImpl` flag (0x2000); anything unproven keeps today's body.
  Fixture: 1,951 flagged, 1,944 decode (7 declines = on-the-fly resolve,
  bare forwarder, `alloca` frame). `PInvokeArguments` carries no
  `SetLastError`, so that attribute argument is unrecoverable -- recorded
  as a known gap. Tests: 21 portable + 5 game.
- Fix 144 (2026-10-25): `dec/build.py` `drop_gc_cardmarks` drops three
  exact side-effect-free Boehm card-mark shapes (`>> 12 & 63` retry,
  empty `if (data_X)`, dead `& 8589930496` temp). No v31 hits.
- Fix 143 (2026-10-25): `_eh_helper_returns` decides by the first
  terminator (ret/int3/ud2/invalid, 512-insn cap), not a 64-instruction
  window; one real flip corpus-wide.
- Fix 142 (2026-10-25): `il2cpp/initguard.py` -- one metadata-init guard
  scan with an exact EFLAGS gap rule (GAP_MAX 16), the body bounded by
  the jne target, SIMD register-operand moves allowed, `lock or` counted
  only after the init call. 8,094 methods change.
- Also unpushed: `dde2ace` (one precompiled literal/comment masker),
  `e68ba9f` (emitter cosmetics: state-machine note, COMPILE-GATE header),
  `1166180` (per-type parallel emission: Emitter plan/one-file/tail +
  chunked process pool).
- Fix 141 (2026-10-23, all-unknown join phis): a merge phi whose every
  incoming value is missing/`_unk` is marked `_unk` (`dec/analyze.py`
  `_phi_all_unknown`; 141b requires all preds emitted this pass, so a
  loop latch's stale dry `end_state` cannot falsely unknown a carried
  value). Call args already drop unknown slots (fix 58/126), so guard-join
  `objN` spray is gone: gate b20 = 439,578 (-15,377 vs b19; CS0103
  -15,619; CS1503 +225 / CS0029 +18 / CS0165 +12 newly visible; -46.95%
  vs r_base, zero parse codes, brace 0). Portable 1,325 passed; game
  recount deferred on the user's push call (full run interrupted at the
  first game tests; only expected pin/golden F marks seen). 3 new golden
  moves (mi 0 GetRandomBytes, mi 26747
  Rpc_CMD_Heal, mi 128953 Finalize) on top of fix 140's ReadSpan /
  GetBounds; re-pin of the moved set awaits approval. Interior unknown
  args keep the honest `_` hole (CS0103 728 -> 827); a compilable
  `default` spelling is a separate user-call slice.
- Fix 140 (2026-10-12, unresolved vtable-slot receivers): VIRT_CALL slot
  resolution falls back to the klass-load object (`vt_recv`), arg1 behind
  an sret buffer, or a type proven by an inlined castclass/isinst
  hierarchy check (`_note_cast_narrow`, rendered `((T)x).M()`); the sret
  struct-return fold also folds parameter/local/`arr[i]` receivers.
  Gate b19 = 454,955 (-2,542 vs b15; unresolved vtable sites 1,193 ->
  381; CS1955 250 -> 23; -45.1% vs r_base). Commit 72e3590. Portable
  1,322 passed; game 261 passed / 10 failed = 8 fix 137/139 pin moves + 2
  golden improvements (ReadSpan, GetBounds) -- re-pin awaiting approval.
  Gotcha: `self.regs.get` / `self.regs[...]` COUNT a use (and may bind a
  temp); side probes must read uncounted via `dict.get(self.regs, r)`.
- Fix 139 (2026-10-11, inline interface dispatch): `il2cpp/dec/ifaceprune.py`
  forces the inlined interface-table scan onto the resolve-helper arm
  (structural + liveness gates); the helper result carries the slot's
  MethodDef (`Expr._ifm`) so `call [entry]` renders `recv.I_Method(args)`.
  2,163/2,262 sites pruned. Gate b15 = 457,497 (-16,598 vs b13, zero
  parse codes; -44.8% vs r_base). Portable 1,318 passed; game 8 pin
  moves (4 fix 137 + 4 fix 139) awaiting re-pin approval. Follow-up
  (CS1955 `IEnumerator.Current` vtable-slot callee text) done by fix 140.
- Fix 137 (accessor sugar, call-shaped markers) + fix 138 (2026-10-11,
  undeclared for-head counters get a bare `int numN;` before the head,
  `_rename_locals`): gate b13 = 474,095 (-12,464 vs b12, CS0103
  -19,091, zero parse codes; -42.8% vs r_base). Portable 1,313 passed;
  game suite has exactly the 4 fix-137 pin moves (mi 26747 golden + 3
  mi 5694 temp-renumber pins) awaiting a user re-pin call. Next slice
  candidate: interface-offset-table scans read as 1-byte raw loads
  (2,320 CS0019 on for heads). See `docs/todo.md` top.
- Fix 135 (CS0019 slice): integer-only `object objN` temps are declared
  `int`/`long` (`_numeric_obj_retype`, highlevel.py). Gate -5,375
  (CS0019 -3,319, CS0266 -3,036); suites green. Pushed (`22a5186`).
- Fix 136: the same pass types float lanes as `float`/`double` (`realN`).
  Gate -1,237 (b10 = 492,867). One golden re-pinned (mi 23931).
- Compile-gate slices 125-133 are fast-forwarded onto `main` and pushed
  (2026-10-06, `8b2d724`, user call: one branch, no split branches or
  worktrees -- work each slice directly on `main` in the main checkout,
  one slice at a time). `final_out/` NOT promoted, goldens/pins NOT
  re-pinned. Fix 134 (raw loads keep native width) landed directly on
  `main`. Real Roslyn gate (`--strict --publicize --raw-addr`, through fix
  134, `work/cg8/b8`): 828,571 -> 499,479 errors (-39.7%). The 39 moved
  goldens/pins were re-pinned (user-approved, 2026-10-06): game suite
  263 passed / 0 failed, portable 1,294 passed. Next slice: CS0019
  `object op int`. Current state, the standard
  per-slice procedure (probe -> patchlib patch -> tests -> 10-group
  build -> gate -> delta review -> suites -> docs/commit) and e-MCP
  session mechanics: `docs/handoff-2026-10-06.md`.

- Fix 124 (wide raw stores byte-address their displacement) is complete
  on branch `fix124-wide-store-byte-offsets`, not merged or promoted:
  paired Assembly-CSharp + whole 91-image tree gates clean, 9,339 changed
  bodies proven pure fix-124, 5 goldens re-pinned, suite 1,463/1,465.
  The 2 failures are this sandbox's named-pipe denial in
  `tests/test_game_parallel_build.py` (a bare `ProcessPoolExecutor(2)`
  reproduces it), so `--workers` builds are unavailable here — split
  multi-image work into per-image processes instead. Evidence:
  `validation_reports/review124_*`.
- Compiler-error backlog (process P1-P4, families C1-C10): the gates
  prove parseability, not compilability. Roslyn error count is the
  new primary metric. Both live at the top of `docs/todo.md`.

## Current state (2026-10-01, `main` clean; `final_out/` = r11)

Promoted 2026-10-01 on user call after a full rebuild from `main` `1cafd3f`
(twin single-field-return relax + box-only hetero-decl guard):
`python il2csharp.py testgame -o r11_out1 --strict --workers 8` gave 11,183
files / 114,458 bodies / 0 failed / 0 fallbacks / 0 type-emit failures.
Brace audit 0 unbalanced; tree-sitter parse gate bad=0 ERROR=0 MISSING=0.
Versus r10: 0 added, 0 removed, 2,838 files changed (top: mscorlib 368,
UIElementsModule 226, Assembly-CSharp 210). Per-file sha256 proof: 11,276
files, aggregate `735f2e9a…1707f`, 0 mismatches / 0 missing / 0 stale
(`validation_reports/promotion_r11.json`). Suite at landing: 1435 passed
(1197 portable + 238 game), goldens 64/64.

## Previous state (2026-09-28, `final_out/` was r10)

Promoted 2026-09-28 on user call without rebuilding (per-file sha256 proof:
11,276 files, aggregate `b0c87509…b9fe`, 0 mismatches / 0 stale; 302 files
changed vs r9; `validation_reports/promotion_r10.json`). The candidate came
from audit batch 3, five fixes across three layers: shared-body argument
lanes (the all-candidates slot classes rebuild the printed list, so a
float-parameter body no longer prints the stale RCX value and drops the real
XMM argument), icall overload selection from the runtime signature's own
parameter list (17 cells), literal-safe `$` sanitize + `_rename_locals`
masking (JSON.NET wire names and diffgram URIs survive), and five
per-instance runtime caches (the audit-batch-1 class). Strict rebuild:
11,183 files / 114,458 bodies / 0 failed / 0 fallbacks / 0 type-emission
failures in 1,465,953 ms (contended box); brace 0; parse 0/0/0/0; paired
sweep 0 crashes both sides, into_block 8,075/2,046 unchanged, unknown -57;
one golden moved (mi 80548) and reviewed. Later the same day the
2026-09-26 `--workers N` build was re-landed (it had been reverted bare)
with a heaviest-image-first submission order: a full 8-worker build is
byte-identical to `final_out` (11,276/11,276 files) and the instrumented
6-worker run measures 0.93 worker efficiency, so the remaining wall is
total work and box load, not tail order. Suite 1147 passed / 0 failed
(943 portable + 204 game). Deferred audit findings (stale destinations on
unmodelled instructions, value-type fragment discard, XMM0 clobber, array
stride) are filed in `docs/todo.md` with evidence.

Also on 2026-09-28 the repository history was scrubbed for public release:
`git filter-repo` removed the licensed fixture and every full-body /
disassembly artifact (golden archives, focused/structural dumps, raw
logs and diffs, `*.tail-args.jsonl.gz`), LFS objects were pruned, and the
history was force-pushed. Every pre-scrub commit hash changed; the old
history lives only in `il2csharp_prepurge_backup.bundle` (parent folder).
`testgame/` is local + git-ignored, and the tracked golden is hash-only
(`tools/make_goldens.py` defaults to hash-only; `--full` is local-only).
Checklist: `docs/public_release.md`.

## Previous state (2026-09-26, `main` clean; `final_out/` = r9)

Promoted 2026-09-26 (**r9**, full tree, all 91 images, from `e20f82f`):
strict rebuild 11,183 type files / 114,458 bodies / 0 failed / 0 structured
fallbacks / 0 type-emission failures in **1,085 s (18.1 min)**; brace **0
unbalanced**; parse **0 bad / 0 ERROR / 0 MISSING / 0 recovery nodes**; an
independent second build byte-identical (aggregate `73f4426d…c8821` both
sides); mirror-copied over `final_out` with a per-file sha256 proof, 0 stale
files. 918 of 11,276 files changed, file set identical, **net method
signature delta 0**. Census: fabricated pointer sites 97,531 → 83,314
(-14,217), shared 16,916 → 16,834 (net -82), `/* nothing */` 63 → 0 with
63 `return Neon.<variant>(...)`, shared calls with an invented trailing `0`
3,880 → 3,519, `indirect` -4, `goto`/`memN`/`qaddr` flat, `unknown` +53 in
59 files (typed-but-unknown frame slots replacing fabricated arithmetic).
One accepted regression, user-called and recorded: mi 23602
`StandingPeopleConcert.SpawnPeople` loses `Quaternion.Internal_FromEulerRad`
to a 9-candidate marker. Evidence in
`validation_reports/promotion_r9.json`. r7 and r8 are history.

Landed 2026-09-26 (one shared body, one argument list): an unresolved
shared-body **tail** is now bounded by the same largest-declared-arity proof
`_call` has used since 21j (`_shared_arity_cap` / `_shared_tail_keep`), so
one VA no longer prints `(x)` when called and `(x, 0)` when tail-jumped --
the `GetHashCode` forwarder family at `0x181b14c10` was the visible case.
Only a trailing run of literal `0` goes (callee-zeroed plumbing), so a
registry-missed sharer whose extra register is really read (`List<T>.CopyTo`'
s R8 at `0x180df9c30`) is untouched. Paired pre/post sweep over all 5,437
methods that `jmp` into a multi-candidate address (pre root = `HEAD`
versions of the three files, no stash): **349 bodies / 363 lines changed, 0
new crashes**, every changed line its pre-image minus the last `, 0`; 775
fires over 112 addresses, every one dropping exactly one argument. Calls and
resolved tails untouched. +18 portable / +6 game.

Landed 2026-09-26 (audit batch 2): the `mov rbp,rsp` frame is now a
tracked fact (`_rbp_frame`) instead of an inference from the register
value, so it survives the pass-2 phi merge -- 1,537 method bodies change,
**0 structural changes, 0 new crashes**, and fabricated `(T*)x - 0xNN`
pointer arithmetic falls 87,471 -> 73,302 tree-wide. `slot_var` now
sign-extends with `sdisp`, so one native home has one key. Accepted,
documented cost: +7 scalar-declared-with-float-RHS lines (550 -> 557 in
Assembly-CSharp, 3 of 60 changed files), a pre-existing lossy area.
Also landed (batch 1, output-neutral): three class-level `td.index` caches
made per-instance, `type_sizes` no longer negative (91 rows), Android
registration fallback gated on ELF.
A full-tree rebuild measures **1,085 s (18.1 min)** serial for 114,458
bodies (r9, two builds at 1,085/1,086 s); `--workers 8` measured 262.9 s
(2026-09-26) and 275.0 s (2026-09-28, box ~30% external load) with the
tree byte-identical.
Landed before that: identical-render shared collapse (70 sites),
shared-stub native disassembly comments, noreturn-shared forwarder
returns (63 Neon `/* nothing */` -> `return Target(args)`), r8
Assembly-CSharp promotion (ComputeStringHash x3 + stub comments; rest
of tree at r7). That full-tree promotion is now *sized*: 101 of 11,276
files differ from a fresh HEAD build, 95 comment-only or 1:1 renames, 6
to read.
Documented (no source change, markers stay honest): same-name
receiver-pick disproof (~1.9k sites need sidecar, not sig
elimination), constant-zero fold disproof (239 sites, 2 VAs).
Full suite: 1147 passed / 0 failed (943 portable + 204 game), verified
against the fixture this session. The parallel build is re-landed and
scheduled: `--workers N` in `cli.py` (default 1), merged with the
sunshine `--quiet`/`--json`/`--manifest`/`--bodies` flags, with heaviest
images submitted first (`_weighted_order`, native-method count);
`--workers 0` is half the cores (max 8); `--max-methods` and `--bodies`
force 1. A full 8-worker build is byte-identical to `final_out` r10
(11,276/11,276 files) and the instrumented 6-worker run measures 0.93
worker efficiency, so the remaining wall is total work and box load, not
tail order (TextMeshPro/TextCore are the longest images despite low
method counts). A `sub_` census then found the biggest output
population: 36,313 of 38,254 plain `sub_` sites (95%) point at IL2CPP
runtime helpers with no metadata candidate at all. Landing 1 of that
program recognizes nullary interface dispatch structurally
(`_iface_dispatch_arity` + `rt_iface`; 0x180002210/0x180002380), closes
the return from the interface instantiation, and binds the result at the
call; full strict build `r12_out1` is 696/11,276 files changed with 0
failed / 0 fallbacks, brace 0, parse 0/0/0, and Assembly-CSharp's helper
sites are 55 -> 0 with `?.Dispose()` folds. Landing 2 recognizes IsInst
structurally: the `typeof(T)` subset renders `obj as T` (9 AC calls),
opaque klass expressions keep `sub_`. Landing 3 recognizes the
Interlocked helper's `lock cmpxchg` body and renders the managed
`Interlocked.CompareExchange` (21 AC calls -> 0). Landing 4 recognizes
the out-of-line class-init helper and elides it, propagating the klass
value (3 AC calls, 861 tree-wide). Landing 5 names the interface
slow-path resolve helper `0x18043dc60` (`il2cpp_interface_get_method`,
2,446 sites -- the body disproves the old alloc/box label). Landing 6
resolves unanimous conversion families at caller-proven casts (5
`Angle`/`StyleFloat` sites -> `T.op_Implicit`; the 865-site
ToString spray is closed-declined, all shapes vacuous). Landing 7
names the bounds-checked element-address helpers
(`il2cpp_array_addr`, 764 sites). Landing 8 renders parameterized
interface dispatch (542 sites -> managed calls; the R9 first-touch
liveness guard, lazy arity choke for non-AC images, and a
single-field-struct return decline with enums exempt). Open, by
payoff: the rest of the codegen families (isinst klass-expr 5,802
sites, bounds slice B `&arr[i]`, multi-parameter dispatch,
untyped-R9 sites, single-field returns), unmodelled-instruction
invalidation (`insn.py`'s silent fall-through leaves a stale destination
live; probed, needs lane modeling first -- SHUFPS must co-land with
the MOVSS merge), Dec F5 literal-blind guards (inventoried, 0 corpus
hits), ToString/op_Implicit spray probe (865 sites, 1 VA
`0x1825b1150`, closed-declined), Cpp2IL
declaration cross-check (specified with prototype, not yet
implemented); then the sidecar program (phased, whole-tile
preference first) and a
full-tree promotion (user call). Suite is 1231 passed / 0 failed
(1012 portable + 219 game). Platform support (Linux/macOS binaries,
better Android) is recorded in `docs/todo.md` as deferred and not
planned soon.
