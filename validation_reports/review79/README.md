# Review 79 validation evidence

Current release: `../../docs/reviews/REVIEW79.md` and `../../docs/reviews/REPLACEMENT.md`.
All native/game inputs were read statically, never executed.

## Full gates

- `summary.json`: release counts, source/fixture hashes, environment, and limits.
- `baseline_tests.log`: all 193 supplied tests passed before any change.
- `units_final.log`, `tests_final.log`, `tests_release_copy.log`: focused/full
  and ZIP-extracted test results (252 total in the final release).
- `baseline_sweep.json`, `baseline_sweep.methods.jsonl.gz`: full unchanged-source
  direct sweep; `baseline_repeatability.json` compares it with Review 78.
- `final_sweep.json`, `final_sweep.methods.jsonl.gz`: all 116,178 methods directly
  lifted by the frozen final source, not Emitter fallbacks.
- `comparison.json`: complete per-method changes and structural audit deltas.
- `baseline_parse.json`, `final_parse.json`, `parse_comparison.json`: complete
  before/after syntax gates including recovery nodes and newly-bad file checks.
- `final_build.log`: completed strict full rebuild (not C# compilation).
- `output_comparison.json`, `output_changes.diff.gz`: complete output inventory,
  per-file hashes, normalized diff, and selected token/readability measurements.
- `release_verification.json`: ZIP-root/inventory and extracted checksum verification.

## Native and compiler evidence

- `focused_native_before.json`, `focused_native_after.json`: exact MethodDef
  instructions and fresh bodies for the changed/correctness-guarded examples.
- `shared_sret_owners.json`, `sret_call_evidence.json`: all owners and observed
  RCX/RDX slot/pointee evidence for the RaycastHit shared body.
- `scalar_sqrt_native.json`: real SQRTSS instructions and explicitly float output.
- `snapshot_changes.diff`, `snapshot_review.json`: exactly one changed snapshot,
  native-proved and accepted after complete gates; the original 64 remain archived.
- `source_changes.diff`: readable LF-normalized core-source diff. Shipped Python
  sources themselves retain their CRLF (and il2csharp.py's BOM).
- `csharp_smoke/Program.cs`, `Smoke.csproj`, `UnsafeSmoke/`, `run.log`, `report.json`:
  instruction-generated pattern compilation/runtime checks and an actual generated
  unsafe project's successful compiler check. Not a build of the recovered game.
- `compiler_before/`: the original emitter's same unsafe project fails with the
  expected CS0227 diagnostic. This is the baseline counterexample, not a failure
  of the released source.

Manifests are relative to their report directory. Paths in logs record where
validation ran; they are provenance, not installation paths. Elapsed times were
measured under concurrent workloads and are not performance comparisons.

```text
python tools/validate_corpus.py compare validation_reports/review79/baseline_sweep.json validation_reports/review79/final_sweep.json --report work/recheck79.json
python tools/validate_corpus.py compare validation_reports/review79/baseline_parse.json validation_reports/review79/final_parse.json --report work/recheck79_parse.json
python tools/csharp_smoke.py --out work/csharp-smoke --dotnet dotnet
python tools/verify_release.py
```

No full-project C# build, game execution, semantic-equivalence guarantee, native
floating-point-mode equivalence, performance benchmark, or ARM64 validation is
implied. The explicit guarded/open cases are listed in `../../docs/todo.md`.
