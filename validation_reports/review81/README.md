# Review 81 validation evidence

Current release: `../../docs/reviews/REVIEW81.md` and `../../docs/reviews/REPLACEMENT.md`.
All native/game inputs were read statically and never executed.

## Full gates

- `summary.json`: release counts, source/fixture/output hashes, environment,
  explicit limits, and release-copy verification.
- `tests_baseline.log`, `tests_portable.log`, and `tests_final.log`: pre-edit,
  portable-only, and complete fixture-backed Python suites.
- `final_build.log`: fresh strict full-tree emission.
- `final_parse.json` and `final_parse.log`: complete generated-C# syntax gate.
- `final_sweep.json`, `final_sweep.methods.jsonl.gz`, and
  `final_sweep.tail-args.jsonl.gz`: direct structured lift of every native
  MethodDef without an emitter fallback.
- `comparison.json`: complete per-method Review 80 → Review 81 hash and
  structural-audit comparison.
- `output_comparison.json` and `output_changes.diff.gz`: full generated-file
  inventory/hash/metric comparison and compressed normalized diffs.
- `promotion_verification.json`: candidate hashes checked again after clean
  promotion into `final_out/`.
- `release_verification.json`, `manifest_release_copy.log`, and
  `tests_release_copy.log`: checksum and test verification from a separately
  extracted replacement ZIP.

## Native, source, and focused evidence

- `source_changes.diff` and `source_hashes.json`: LF-normalized readable core
  diff and exact source hashes. Shipped `il2csharp.py` retains UTF-8 BOM/CRLF;
  `decompiler.py` retains CRLF.
- `sqrt_census_summary.json`: compact distinct-body instruction/pattern counts.
- `sqrt_output_audit.json`: all 205 MethodDefs containing helper/SQRTPD sites,
  with 0 lift exceptions and 0 raw helper calls.
- `helper_disasm.txt` and `tail_helper_native.txt`: structural evidence for the
  unregistered XMM0 double wrapper and a direct domain-arm tail jump.
- `focused_before.txt`, `focused_after.txt`, and `focused_changes.diff`: six
  representative recovered-body comparisons, including a direct helper tail.
- `scalar_abi_before.txt`, `scalar_abi_after.txt`,
  `scalar_abi_changes.diff`, and `scalar_abi_native.txt`: five non-sqrt
  return-register body/native spot checks.
- `byref_returns_before.txt` and `byref_returns_after.txt`: all eight ref-float/
  ref-double method bodies remain byte-identical.
- `byref_callers_before.txt`, `byref_callers_after.txt`, and
  `byref_callers.diff`: the only two changes outside direct scalar-return/sqrt
  bodies; both now retain the `layoutConfig.PointScaleFactor` ref-return target.

The 64-case `tests/goldens_review80.json` snapshot file remains unchanged and all
cases pass. No .NET SDK was available in this environment, so Review 80's focused
compiler smoke remains historical evidence and was not re-run for Review 81.
There was no full-project C# build, game execution, semantic-equivalence claim,
performance benchmark, or ARM64 validation.

```text
python tools/validate_corpus.py compare \
  validation_reports/review80/final_sweep.json \
  validation_reports/review81/final_sweep.json \
  --report validation_reports/review81/comparison.json
python tools/validate_corpus.py parse final_out --report work/recheck81_parse.json
python tools/verify_release.py
```
