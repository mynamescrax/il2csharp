> **Historical document — Review 78 evidence.** Retained as provenance, not current
> release instructions. Review 79 is current; see `../../docs/reviews/REVIEW79.md`, the live
> `docs/todo.md`, and `validation_reports/review79/`. Past counts and unresolved
> statuses below describe their original release, not today's replacement.

# Review 78 validation evidence

See `../../docs/reviews/REVIEW78.md` and `../../docs/reviews/REPLACEMENT.md` first. This directory is the
current release evidence; files one directory above belong to Review 77.

- `summary.json`: source/fixture hashes, actual upload inventory, environment,
  test stages, full build and final gate results.
- `uploaded_source_tests.log`: 56 failed / 80 passed on the actual uploaded code.
- `restored_review77_tests.log`: 136 passed after restoring the missing source fixes.
- `tests_pre_gate.log`, `tests_release.log`: complete 193-test suite.
- `uploaded_source_sweep.json`, `uploaded_source.methods.jsonl.gz`: repeated,
  full direct sweep of the actual uploaded source, never the partial C# tree.
- `final_sweep.json`, `final_sweep.methods.jsonl.gz`: all 116,178 MethodDefs
  directly lifted by the released source, with hashes and structural metrics.
- `comparison.json`: full per-method baseline/final comparison.
- `baseline_repeatability.json`: compare the repeated uploaded-source sweep to
  the matching original Review 77 baseline report.
- `final_build.log`, `final_parse.json`: completed strict build and complete
  generated-tree syntax gate. The tree is included at `../../final_out/`.
- `focused_native_before.json`, `focused_native_after.json`: MethodDef-keyed
  native disassembly and actual before/after body evidence.
- `sqrt-domain-helper.asm.txt`: disassembly correcting the old NaN-predicate lead.
- `rejected_unguarded_snapshot_diffs.txt`: **rejected experiment**, not current
  output. It exposed an unsafe loop-header hoist. The loop guard keeps all 64
  original snapshots unchanged; none was regenerated.
- `assembly_csharp_comparison.json`, `assembly_csharp_changes.diff.gz`: actual
  uploaded/rebuilt gameplay-file comparison; distinguish normalized content
  changes from CRLF/LF-only byte differences.
- `source_changes.diff`: human-readable source diff with normalized LF. The
  shipped source itself preserves CRLF/BOM; use the full replacement files.

Manifest paths are relative to their reports. Tree/source paths in run logs
record where validation actually ran; they are provenance, not install paths.
To recompare from the project root:

```text
python tools/validate_corpus.py compare validation_reports/review78/uploaded_source_sweep.json validation_reports/review78/final_sweep.json --report work/recheck78.json
```

No game binary execution, .NET compilation, semantic-equivalence guarantee,
performance benchmark or ARM64 validation is implied by these reports.
