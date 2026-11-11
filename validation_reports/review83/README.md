# Review 83 validation evidence

Current release: `../../docs/reviews/REVIEW83.md` and `../../docs/reviews/REPLACEMENT.md`.
The unchanged native/game inputs were read statically and never executed.

## Authoritative summary and full gates

- `summary.json`: release counts, hashes, environment, proof boundaries,
  promotion, and extracted-copy verification.
- `tests_baseline.log`: complete 293-test Review 82 baseline before edits.
- `tests_portable_*.log`, `tests_native_*.log`, and `tests_complete.log`:
  incremental and final Review 83 suites; final result is 318 passed.
- `build_part1.log`, `build_part2.log`, and `build_merge.json`: disjoint strict
  all-assembly emission and exact merge/overlap verification.
- `final_parse.json` / `.log`: tree-sitter syntax gate over all 11,107 C# files.
- `final_sweep.json`, `final_sweep.methods.jsonl.gz`, and
  `final_sweep.tail-args.jsonl.gz`: merged direct lift of all 116,178 native
  MethodDefs.
- `sweep_comparison.json`: complete Review 82 → Review 83 manifest comparison;
  structural metrics do not change.
- `promotion_verification.json`: candidate and promoted `final_out/` inventory
  and aggregate hashes.
- `release_verification.json` and `tests_staging_preflight.log`: isolated-copy
  output-hash and complete 318-test preflight. The final archive is extracted
  and manifest/test verified externally after packaging to avoid a self-hash
  cycle.

## Shared-return proof

- `consensus_census.json`: every ambiguous address/candidate classified as
  exact supported consensus, open/unreadable, disagreement, or unsupported ABI.
- `changed_method_scope.json`: exact fixed-order source-transform proof. Of the
  initial 6,351 sweep hash deltas, 4,322 are genuine source changes and every
  one receives a proven consensus result; 2,029 are partition-state-only.
- `parity_review82.methods.jsonl.gz` and `parity_review83.methods.jsonl.gz`:
  isolated fixed-order manifests behind that proof; adjacent `.json` files hold
  source and fixture fingerprints.
- `rendered_shared_semantics.json`: all 3,543 bare shared calls are consensus
  `void`; all 2,550 direct shared conditions are consensus `bool`; 0 mismatches.
- `output_audit.json`: full generated-tree inventory and before/after metrics.
  `output_changes.diff.gz` is the complete generated-code diff.
- `generated_spot_checks.log`: representative Boolean, XMM0 float, string,
  observed sret, restored side-effect, and guarded unknown-sret output.
- `snapshot_comparison.json` and `snapshot_changes.diff`: same 64 MethodDefs,
  60 unchanged and four reviewed semantic changes.
- `source_changes.diff`, `source_hashes.json`, and `source_format.json`: exact
  core diff, SHA-256 values, UTF-8 BOM, and CRLF checks.

## Important interpretation

The build and sweep were each split into two assembly partitions. Build overlap
was limited to `Unity.InputSystem.dll`, accidentally selected by both the
`Unity.InputSystem.dll` and `System.dll` substrings; all 345 overlapping emitted
files were byte-identical. The unique merged inventory exactly matches Review 82.

The sweep comparison's 6,351 changed hashes are not all attributed to the source
change: a fresh second partition exposes pre-existing state-sensitive renders.
The fixed-order isolated parity manifests are the attribution authority: 4,322
source-changed methods, all exactly in shared-return consensus scope.

No .NET SDK was available, so there was no current compiled-pattern smoke or
complete generated-project C# build. Syntax cleanliness, metadata consensus,
and snapshot agreement are not claims that the complete recovered game is
semantically equivalent or runnable.
