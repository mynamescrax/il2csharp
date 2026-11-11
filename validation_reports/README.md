# Validation evidence

**Fix 124 (wide raw stores byte-address their displacement, 2026-10-04,
branch `fix124-wide-store-byte-offsets`, not promoted).** Start with
`review124_summary.json` (native table, gate matrix, environment caveat),
then `review124_ab_ac.json` (paired Assembly-CSharp tree diff),
`review124_sweep.json` + `review124_sweep_compare.json` (whole-corpus
direct sweep and main-vs-branch compare: 9,339 changed methods, 0
structural changes, 0 crashes), `review124_purity.json` (9,339/9,339 pure
fix-124), `review124_parse.json` (whole 91-image tree, 0/0/0/0),
`review124_golden_repin.json` (5 of 64 snapshots re-pinned) and
`review124_environment.json` (the sandbox's multiprocessing-pipe denial,
which fails 2 parallel-build tests and blocks `--workers` builds).

**Current live tree: r11 (2026-10-01, rebuilt from `main` `1cafd3f`).**
Start with `promotion_r11.json` (11,276 files, aggregate `735f2e9a…1707f`, 0
mismatches; strict build 0 failures, brace + parse gates clean).

**Previous tree: r10 (2026-09-28, audit batch 3).** Start with
`promotion_r10.json` (11,276 files, aggregate `b0c87509…b9fe`, 0
mismatches) and `audit_batch3.json` (landing evidence: strict build,
brace + parse gates, paired sweep, golden review), then `../docs/todo.md`
(Current work). `promotion_r9.json` is the previous promoted tree;
everything older is history.

The 2026-09-28 public scrub removed the licensed fixture plus every raw
log, `.diff`, focused/structural body dump, `*.tail-args.jsonl.gz` and
the old golden archives from git history (see `../docs/public_release.md`);
the summaries and JSON reports below remain.

The promoted tree lives at `../final_out/` (git-ignored and derived from
the licensed fixture — never publish it). The `.zip` release artifact
(`docs/reviews/REPLACEMENT.md`) describes the Review 84 handoff ZIP; for
the live tree see `../README.md`, `validation_reports/SHA256SUMS.txt`
and `tools/verify_release.py`. The `../bckups/` archival copies were
deleted 2026-09-19 — GitHub is the history authority.

Earlier releases — Review 84 (`review84/`), Review 80 (`review80/`), Reviews 79/78
(`review79/`, `review78/`) — are preserved below. Their old bundling/"current"
descriptions are not the state of this replacement.

Historical note: **Review 80 was the last release whose validation ZIP was
regenerated for the archive.** Later promotions (Reviews 84–89, fixes 93–97, r4–r10)
keep their evidence in `review84/`, `review85/`, `split_rebuild_verification.json`,
`review93_*`/`review94_*`, `review97*/review97e_*`, and the `promotion_r*.json`
report files; the `review80/` record below remains the last fully-bundled
per-file evidence set.

# Review 77 validation evidence

Start with `../docs/reviews/REVIEW.md` for changes, results, caveats and reproduction commands.
`summary.json` records the exact source/fixture hashes and tested environment.
The game was statically read only; its binaries and the full emitted C# trees
are **not** included.

## Included reports

- `baseline_parse.json`, `final_parse.json`, `parse_diff.json`: per-file C#
  syntax gates, including otherwise-hidden parser recovery nodes.
- `baseline_sweep.json`, `final_sweep.json`: direct-lift sweep summaries from
  the **same final validator**. The baseline is the complete audited rerun;
  discarded early/partial audit results are not bundled.
- `baseline.methods.jsonl.gz`, `final.methods.jsonl.gz`: all 116,178 native-backed
  MethodDef rows with output hashes and audit metrics, not full method bodies.
- `final.tail-args.jsonl.gz`: observed before/after argument preparation at the
  tail helper. The baseline file is empty because that helper did not exist.
- `sweep_diff.json`: every changed method hash and structural-metric comparison.
- `baseline_repeatability.json`: all body hashes matched the repeated baseline.
- `output_diff.json`, `output_changes.diff.gz`: full per-file hash comparisons
  and changed-output excerpts, not a replacement for the complete output tree.
- `*_build.log`, `tests_final_all.log`: original successful build/test runs.
- `tests_release_copy.log`: all 136 tests passed again from the portable release
   copy. Both report comparisons reproduced exactly, all Python files compiled,
   and `../changes.patch` (ships with the portable release copy, not this
   checkout) applied cleanly to the uploaded baseline and reproduced
   the released files.
- `cli_filter.log`, `cli_filter_parse.json`: actual direct-binary filter smoke.
- `tails_before.json`, `tails_after.json`, `byref_after.json`,
  `pointer_methods_after.json`, `gameplay_after.json`, `native_constant.json`:
  selected native instructions/re-lifts and the independently read float constant.

## Recheck portable comparisons

From the project root, with the development requirements installed:

```bash
python tools/validate_corpus.py compare validation_reports/review80/baseline_parse.json validation_reports/review80/final_parse.json --report work/rechecked_parse_diff.json
python tools/validate_corpus.py compare validation_reports/review80/baseline_sweep.json validation_reports/review80/final_sweep.json --report work/rechecked_sweep_diff.json
# For the live tree, compare validation_reports/review84/summary.json + review85/sweep4.json + split_rebuild_verification.json
```

Manifest paths in these copies are relative to their report directory. Generated
tree paths are descriptive labels because those trees are not bundled. Original
fixture directory paths in logs are redacted. Elapsed times are observational;
concurrent jobs make them unsuitable for performance comparisons.
