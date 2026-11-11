# Review 80 validation evidence

Current release: `../../docs/reviews/REVIEW80.md` and `../../docs/reviews/REPLACEMENT.md`.
All native/game inputs were read statically, never executed.

## Full gates

- `summary.json`: release counts, source/fixture hashes, environment, limits,
  and release-copy verification.
- `tests_portable.log`, `tests_native_focused.log`, `tests_final.log`, and
  `tests_release_copy.log`: portable, focused native, complete, and extracted-ZIP
  results (265 total in the final release).
- `tests_loop_units.log`: the focused loop/control-flow/source-format unit gate.
- `baseline_sweep.json`, `baseline_sweep.methods.jsonl.gz`: all 116,178 methods
  directly lifted by the unchanged uploaded source, with no emitter fallback.
- `final_sweep.json`, `final_sweep.methods.jsonl.gz`: the same direct sweep using
  the frozen Review 80 core source.
- `comparison.json`: complete per-method hash and structural-audit changes.
- `structural_delta_summary.json`: exact into-block-goto decreases and increases;
  increases remain visible rather than being netted out of the release record.
- `structural_increase_largest_*` and `structural_increase_negative_lines_*`:
  full native/body captures and diffs for the largest five increases and every
  increased-metric method whose total line count fell.
- `baseline_parse.json`, `final_parse.json`, `parse_comparison.json`: complete
  before/after syntax gates, including recovery nodes and newly bad files.
- `final_build.log`: completed strict full rebuild (decompiler output generation,
  not C# compilation).
- `output_comparison.json`, `output_changes.diff.gz`: complete generated-file
  inventory/hashes, selected metrics, and normalized changed-output excerpts.
- `promotion_verification.json`: all 3,466 changed candidate hashes still match
  after promotion into `final_out/`.
- `release_verification.json`, `manifest_release_copy.log`,
  `tests_release_copy.log`, and `csharp_smoke_release_copy.log`: separately
  extracted ZIP root/checksum/test/compiler verification.

## Native, source, and compiler evidence

- `focused_before.json`, `focused_after.json`: exact native instructions and fresh
  bodies for MIs 11974, 23566, 28576, 32833, and 80548.
- `focused_changes.diff`, `focused_summary.json`: reviewed body diffs and compact
  line/hash/unknown/goto measurements for those five methods.
- `snapshot_extra_before.json`, `snapshot_extra_after.json`,
  `snapshot_extra_changes.diff`, `snapshot_extra_eh.json`, and
  `snapshot_extra_review.json`: the additional Reset protected-range and
  AddToTable proved-tail snapshot evidence.
- `source_changes.diff`, `source_hashes.json`: readable LF-normalized core-source
  diff and exact before/after hashes. Shipped core sources themselves retain CRLF,
  and `il2csharp.py` retains its UTF-8 BOM.
- `snapshot_changes.diff`, `snapshot_review.json`: the five changed snapshots,
  reviewed and accepted only after complete build/parse/sweep gates. Review 77
  and Review 79 snapshot files remain unchanged.
- `csharp_smoke/Program.cs`, `Smoke.csproj`, `UnsafeSmoke/`, `run.log`, and
  `report.json`: actual loop-emitter plus allocation/sret/scalar-root runtime
  checks and an emitter-generated unsafe project's compiler result.
- `csharp_smoke.log`, `py_compile.log`: top-level compiled-smoke and Python source
  checks.

Manifests are relative to this report directory. Paths in logs record where
validation ran; they are provenance, not installation paths. Elapsed times were
measured under concurrent workloads and are not performance comparisons.

```text
python tools/validate_corpus.py compare validation_reports/review80/baseline_sweep.json validation_reports/review80/final_sweep.json --report work/recheck80.json
python tools/validate_corpus.py compare validation_reports/review80/baseline_parse.json validation_reports/review80/final_parse.json --report work/recheck80_parse.json
python tools/csharp_smoke.py --out work/csharp-smoke --dotnet dotnet
python tools/verify_release.py
```

No full-project C# build, game execution, semantic-equivalence guarantee,
performance benchmark, or ARM64 validation is implied. The remaining 8,067
into-block gotos and other guarded/open cases are listed in `../../docs/todo.md`.
