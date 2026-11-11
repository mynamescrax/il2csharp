## 2. Next up — remaining gate families, in attack order

**UPDATE 2026-08-21 (`archive/batches-b.md` §0o census, b35_out2): this section is a batch-19
snapshot and most of it is DONE or collapsed.** The tree-sitter gate
now reads 2 bad files / 7,924 ERROR / 2 MISSING and BOTH files are the
documented legacy-TMP pair -- there is no gate attack list left; the
improvement surface moved to honesty/readability, ordered in `archive/batches-a.md` §0's
leads and sized in `archive/batches-b.md` §0o. In particular the `: default` honesty debt
below is 4,929 -> 9 sites and `?addr` ~1.9k -> 10; neither is worth a
batch. Kept below for archaeology.

The three families that led this list at batch 18 (`inf.0d`, the
`? -` select-mark residue, the partial-deref store) are all 0. What is
left, bucketed from `work/ts_gate_b19_out2.txt`:

1. **MISSING is now the bigger half** (193 vs 118 ERROR) and barely
   moved this batch (210 -> 193) — and it is ONE family: **169 of the
   187 listed MISSING rows (90%) are bare label lines**, `L_181d8d2e5:`
   with nothing after them. tree-sitter reports a MISSING node because
   a label must be followed by a statement, and these sit at the end of
   a block. Emitting a `;` (empty statement) after a trailing label, or
   dropping labels with no remaining successor, should take MISSING
   from 193 to roughly 25 in one change — the cheapest big win on the
   board. The remaining 18 are one-offs (`AsyncTaskMethodBuilder.Start
   <<_Run_b__0>d>` generic-argument shapes x4, `typeof(X)` elision
   comments x2, a few ctor signature lines).
2. **Whole-file L1 artifacts** (`// Decompiled by il2csharp` header,
   `internal sealed partial class`) — measurement noise that overstates
   ERROR-node damage. Discount, don't chase.
3. Small/honest residues, each 1-3 sites: `Type..ctor` x2 (the last two
   of 296 — a FOURTH name path the batch-19 lstrip missed, find it via
   `RemoteVoice..cctor()` / `Scale..ctor(a, &obj1)`);
   `((byte*)((...)[0] + 0x278)[0]() /*indirect*/` x1 (honest);
   `sub_...`/`obj128 /*indirect*/` x2-4 (honest markers).
4. **Not a parse-gate item, but the honesty debt behind it**: 4,929
   `: default` sites tree-wide are `_fix_select`'s synthesized false
   arms for the lifter's no-false-arm select form `(c ? Y)`. They
   parse; they are not right. Recovering the real false arm is a
   Lifter-side job, not a text job.

## 4. Working loop (keep mirrored)

- **Every `il2cpp/` module and the `il2csharp.py` launcher are CRLF.** A
  read-text/write-text Python edit rewrites the whole file to LF (a
  phantom diff over the module). Package modules carry no BOM; only the
  launcher keeps its UTF-8 BOM. Patch them with binary read/write — `work/patches/patch_*.py`
  are the pattern — and verify `d.count(b'\r\n')` vs `d.count(b'\n')`
  afterwards. The `.md` files are LF; don't cross the two.
- `_final_text` transforms are line-local, and ORDER MATTERS:
  `_rewrite_unknowns` (?-classifier), then `_strip_dangling_default`,
  then `_fix_select` — fix_select re-synthesizes `: default` only when
  a REAL select mark survives the strip; with the string-guard in,
  in-string `?` can't trigger it.
- Mirror every `_final_text` change into `work/lib/sim_rewrite.py` (~2-min
  tree re-gate) and into unit mirrors `strip_test.py` / `uk_test.py` /
  `fixsel_test.py` (reaped with the batch trees — not in the current tree;
  the sim re-gate is the surviving fast loop). Lifter-side changes (`il2cpp/lifter/`) need a real
  build — the sim can't see them. `_structure`-pass changes get their
  own unit mirror instead (batch 36's `_copy_prop` -> `work/experiments/cp_test.py`,
  20 cases; three pass bugs were caught by that suite before any live
  run — build the suite first for any new statement pass).
- **A sim tree may only be diffed against ANOTHER sim tree.** The sim
  does not mirror `_fix_select`, so it strips `: default` the real
  pipeline re-synthesizes; a sim-vs-`b19_out2` diff invents ~80
  regressions that do not exist. `work/lib/make_sim_base.py` regenerates
  the old-rules control (`work/lib/sim_rewrite_base.py`) to diff against.
- **Measure a rule's hazards against what ENTERS the pass, not the
  tree it produced.** A built tree has the old rule's output baked in,
  so a shape the old rule collapsed reads as "0 sites" right up until
  the new rule stops collapsing it. This is exactly how batch 19's
  `? ?` regression shipped.
- **Always run `work/lib/gate_diff.py OLD.txt NEW.txt`**, not just the gate
  summary line. Batch 19's first build looked like a clean -44% ERROR;
  the per-file diff showed 14 newly-bad files and one carrying 81 ERROR
  nodes.
- Gate via `work/lib/ts_gate.py`, which prints to stdout — redirect to a
  file (saved reports live in `work/artifacts/ts_gate_*.txt`) if you want
  a report to diff. (`work/lib/treesitter_gate.py`, the older writer with
  its own report file, still carries a dead hardcoded output path.)
- `_rewrite_unknowns` rules (load-bearing, unit-tested in the
  `uk_test.py` mirror, since reaped — see `work/experiments/cp_test.py` for the
  surviving mirror pattern): the head test looks PAST whitespace for a value
  (`0 ? &obj5`, `real1 ? -inff` are selects), with three carve-outs —
  `>` counts only ADJACENT (generic close `Foo<T>?`; spaced, it is the
  comparison operator, so `? > ?` still rewrites), `_OPENS_EXPR`
  keywords (`return ? - x;`) are not values, and `?` is deliberately
  NOT a value so `? ?` chains rewrite BOTH marks and the
  `unknown unknown` collapse folds them to one. Only because the head
  test is whitespace-aware may the tail set carry bare `-`, `&` and
  `:`. `:` must sit in the whitespace-prefixed class, not the adjacent
  one (`cond ? num28 - ? : num63`).
- `_in_string(s, i)` (`il2cpp/cfg.py`, module-level) is the
  backslash-aware quote tracker — reuse it for any other pass that
  scans `?`/`:` and must not see literals.

## 5. Batch 19 writeup (2026-08-19, parse-gate batch — kept for its
method notes; later batches live in `archive/batches-a.md`–`archive/batches-e.md`)

Gate **302/427/210 -> 183/118/193**; 119 files fully cleared, 10
improved, **0 newly bad, 0 worse**. Sweep and body counts unchanged
(115,658/0 failed; into_block 21,326/4,538; crashes 2 = the TMP caps).
Two builds: `b19_out1` (first pass, carried the `? ?` regression) and
`b19_out2` (final). Both `PYTHONHASHSEED=0`.

### Shipped

1. **inf/nan literals** (`il2csharp.py` `repr_f32`/`repr_f64`).
   `repr()` of a non-finite float gives `inf`/`nan` and the suffix step
   glued a type suffix on: `inf.0d`, `nan.0d`, `inff`, `nanf` — none of
   which lex. New `_repr_special_float()` emits `float.NaN` /
   `double.PositiveInfinity` / `float.NegativeInfinity` etc. All four
   are `const` fields in .NET, so they are legal in the
   `const double INFINITY_DBL = ...;` initializer where two gate rows
   sat. 1,285 sites now render as constants; 25 gate rows -> 0.
   Superseded and REMOVED `decompiler.py::_INFNF_RX`, which patched the
   old broken text and did it WRONG (mapped both signs to
   NegativeInfinity, and always to `double` even for an `f` suffix).
2. **`_rewrite_unknowns` head test made whitespace-aware** + tail set
   relaxed to bare `-`, `&`, `:` (see §4 for the exact rule and its
   carve-outs). The old head test read only `s[i-1]`, so every select
   mark with a space in front of it looked like an unknown operand;
   the digit guards in the tail existed only to paper over that. 127
   gate rows -> 0.
3. **Write-barrier lvalue: partial-paren address composite**
   (`il2csharp.py` `_call`). The normalization prepended a bare `*` to
   any dst that merely STARTED with `(`, so `(v95 + 2 << 4) + t1002`
   rendered `*(v95 + 2 << 4) + t1002 = 0;` — a deref of the FIRST TERM
   ONLY, not an lvalue and not parseable. Both that test and the
   already-a-deref test now use balanced-paren spans
   (`_paren_spans_all` / `_deref_spans_all`); the old
   `^(\*\([^)]*\))(\[[^\]]*\])?$` regex also mis-fired on any nested
   paren, double-wrapping a correct deref. 83 gate rows -> 0, the
   largest single family, and it cascaded whole-file (VisualTreeAsset
   listed 11 rows off 2 real defects).
4. **Name sanitizing, two holes batch 17 missed**: `csharp_type_name`
   never stripped `@`, so a codegen type name reached call targets
   verbatim (`ReaderWriter@Fusion_NetworkString`) — `@` is a
   verbatim-identifier PREFIX in C# and illegal mid-token, so only a
   segment-leading one survives (`@class` still renders `@class`).
   And `Il2Cpp.method_simple_name` plus the two usage-slot renderings
   spelled `m.name` raw, printing `.ctor` as `Type..ctor`: **296 sites
   -> 2** (a fourth path still emits them, see §2.3).

### The regression, and why it shipped

`b19_out1` gated 203/238/194 — a clean-looking -44% ERROR — but
`gate_diff.py` showed **14 newly-bad files, one with 81 ERROR nodes**
(Timer.cs), all one root cause: `if (unknown ? ? : default)` where
batch 18 rendered `if (unknown)`.

I had added `?` to the head's back-value set to guard `? ? -1 : 0`
against the relaxed `-` tail, and justified it by measuring ZERO `? ?`
sites — **on the output tree, where the old rules had already collapsed
every such chain into one `unknown`.** It is an input shape, not an
output one. Keeping `?` protected the second mark, the chain stopped
collapsing, and one unparseable condition cascaded over whole files.

Measured properly on `b19_out1` (which preserves the chains precisely
because of the bug): all 29 `? ?` sites are `? ? : default` — not one
has a `-`-leading arm, so the hazard the guard existed for has zero
sites on this corpus. `?` removed from the back set; three cases pinned
in   `uk_test.py` (now reaped; see `work/experiments/cp_test.py` for the
  surviving pattern).

### Method / new tooling under work/

Unit mirrors first (`uk_test.py`, +20 pinning cases; the 44
pre-existing cases are unchanged bar one synthetic with 0 real sites),
then a sim A/B (control `sim_rewrite_base.py` 389/597/203 -> new
331/439/203, 0 newly bad, 0 worse), then the full-corpus sweep, then
the real build + gate + `gate_diff`. New scripts: `uk_census.py`
(buckets surviving `?` by head/tail char), `gate_diff.py` (per-file
diff of two gate reports), `probe_store.py` (re-lift one method by VA,
dumping RAW pre-`_render` text), `probe_lval.py` (`_mem_lvalue` I/O
trace), `probe_emit.py` (stack-trace whichever emitter produced a given
statement text — this is what found the write-barrier path in one
run), `verify_clears_b19.py`, `make_sim_base.py`, `run_build_b19b.py`,
and the applied source patches `patch_*.py` kept as the record.

## 6. Baselines, promotion, known artifacts

Live authority has moved on: current baseline, gates, and file census
are `docs/todo.md` (Current work), `validation_reports/promotion_r10.json`
and `promotion_r9.json` (frozen evidence). The former root `TODONOW.md`
(now an appendix of `docs/todo.md`) and the `promotion_r4*` files are
history. What
follows is a batch-19 snapshot, kept for its "known artifacts"
list below — all promotion status here is historical, not Review 79 authority.
The batch-19-era baseline chain it originally described
(`b19_out2`, `b18_out12`, `b18_noreind`, `b19_out1`/`b19_sim`/
`b19_simbase`) is long gone; the following is the older promotion chronology:
- **`final_out/` was promoted to `b42_out1` on 2026-08-22** (batch 42,
  `archive/batches-e.md` §0v; gate 2/4,864/4 — the TMP pair only; byte-verified copy of the
  b42_out1 build, 11,107 files / 115,658 bodies). The gated candidate
  is now **`b74_out1`** (batches 43-74, gate 0/0/0, `archive/batches-c.md` §0ar); batch 75 is
  source-only with no build (`archive/batches-c.md` §0as). The same promotion
  pass reaped the batch trees one level up (`b37_out1` through
  `b42_out1`) and the work-dir archaeology tied to reaped trees (old
  build logs, gate reports, site dumps, one-shot build scripts, the
  frozen batch-21 source snapshots, caches) — provenance records
  (`patch_*.py`, `fix_*.py`, probes, censuses, tests) were kept.
  Previous promotion: b36_out2 on 2026-08-21, which had deleted the
  `b18_noreind`-through-`b36_out1` chain; the "replace `final_out/`
  outright" rule was followed again. No A/B tree is kept below
  `final_out/`.
- Known artifacts (stable anchor):
  - CustomAttributeTypedArgument.ToString: switch-reached +3-open SEH
    region, byte-identical across prev12/prev13/prev14/prev15; the
    `try { } else { }` class itself is 0 tree-wide. Read CLAUDE.md's
    SEH section before touching region open/close logic.
   - **Re-measured at b35_out2 (`archive/batches-b.md` §0o, 2026-08-21): `?addr` ~10 sites
    (was ~1.9k at the batch-19 snapshot below); `&s_` 495 call-arg
    lines (stack-frame model); `: default` 9 (was 4,929).** The
    snapshot numbers follow: `?addr` ~1.9k sites (untracked base
    registers, all call args); `&s_N` ~450 call-arg lines;
    `sub_.../*shared body, N candidates*/` markers = honest by design
    (17,592 marker lines / 51,741 total `sub_` refs at b35_out2).
  - ~~The two TextMeshPro cfg-too-large caps
    (`TextMeshPro`/`TextMeshProUGUI.GenerateTextMesh`) fall back to the
    legacy flat lift, which does NOT run `_final_text` — so raw `?`,
    `*(...)` and `t`/`v` temp names survive in those two files only.
    Any `?`-family census over the tree must exclude them or it will
    chase ghosts.~~ **RETIRED batch 53 (`archive/batches-d.md` §0ag).** Both methods are 1831
    and 1842 blocks; the cap was 1500 and is now 3000, so both get a
    real structured lift and neither file is bad any more. The whole
    "exclude the TMP pair from any census" workaround is dead — at
    `b63_out1` the parse gate is 0/0/0 and the sweep crashes 0. A census
    that still filters them out is now filtering out ordinary output.

## 7. Gotchas

- Gate messages truncate ~100 chars — bucket by row text, discount
  whole-file spans (the L1 artifact overstates ERROR-node damage), and
  remember ONE bad line can cascade to dozens of ERROR nodes in the
  same file.
- Sweep gates are structural truth for CFG changes; the parse gate is
  syntax-only — neither sees wrong-but-parseable output (`obj4 is
  obj5` already parses; `v95 + 0x2*8` parses and is wrong; the is-fold
  was a QUALITY fix).
- **`sed -i` on any `il2cpp/` module rewrites the whole file
  to LF** (batch 50 hit this). CLAUDE.md names the Python
  read-text/write-text hazard; `sed -i` is the same hazard through a
  different tool, and so is any editor/tool that rewrites the file
  wholesale. Use the binary `work/patches/patch_*.py` pattern for these
  files, even for a one-word comment change, and check
  `d.count(b'\r\n')` against `d.count(b'\n')` after ANY touch.
- `PYTHONHASHSEED`: fix it before comparing builds.
- Syntax-check package modules (`python -m compileall il2cpp`) before any
  rebuild — instant, catches typos before a multi-minute build.
- Builds: 18.1 min serial idle (1,085 s, 114,458 bodies, all 91 images
  at r9); r10 measured 24.4 min (1,465,953 ms) with an unrelated build
  competing for CPU. `--workers 8` measured 262.9 s (2026-09-26, r9) and
  275.0 s (2026-09-28, box ~30% external load), tree byte-identical on
  both; a 6-worker instrumented run is 0.93 worker-efficient (tail costs
  <=8%), so the residual wall is total work and box load, not tail order.
  Gate ~2 min; validator sweep ~23 min; sim re-gate ~2 min. The old
  `~7-9 min` and `1,359 s` figures are pre-r9 and stale.
- Census by the RENDERED NAME, not by scanning method heads for CALL
  instructions (the class-init twin is tail-jmp-reached — a call
  census never sees it).
- **The golden suite samples 50 bodies — for a STRUCTURAL pass
  change, run the full-corpus sweep before trusting it.** Batch 42:
  the first funnel draft over-rejected ~16k hoists (~6k methods, 5% of
  the corpus) and moved only 5/50 goldens — the sample under-represents
  exactly the shapes a statement-pass soundness change touches. The
  sweep's into_block count was what forced the redesign (17,718 ->
  34,144 under the bad draft; 32,094 final, the honest cost).
- **A path that falls past a construct in the lifted tree natively
  flows to the NEXT EMITTED block** — the lifter emits a goto whenever
  a successor is non-adjacent, so a falling sibling arm never ran the
  moved tail natively. This invariant is the whole basis of the
   hoist-pass funnel (`archive/batches-e.md` §0v; disasm-proven twice), and it generalizes:
  any future pass that moves code across a brace must ask which fall
  paths newly reach it.
- Raw pass input (pre-`_render`) packs multiple statements per line
  (`call(); return;`) — any line-local predicate on the pass-side
  statement list must read the TRAILING statement, not the line head
  (`_FLOWTAIL_RX` in `il2cpp/cfg.py`; `_final_text`-style transforms
  only ever see the split lines).

