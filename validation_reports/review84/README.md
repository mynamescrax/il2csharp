# Review 84 validation evidence

Current release: `../../docs/reviews/REVIEW84.md` and `../../docs/reviews/REPLACEMENT.md`.
The unchanged native/game inputs were read statically and never executed.

## Authoritative summary and full gates

- `summary.json`: release counts, hashes, environment, proof boundaries,
  promotion, and extracted-copy verification.
- `tests_baseline.log`: complete 318-test Review 83 baseline before edits.
- `tests_portable_all.log`, `tests_shared_ctors.log`,
  `tests_native_semantic.log`, `tests_snapshots_final.log`, and
  `tests_complete.log`: incremental and final Review 84 suites; final result is
  358 passed.
- `build_part1.log`, `build_part2.log`, `build_merge.json`, and
  `build_merge.log`: partitioned strict all-assembly emission and exact
  inventory/overlap verification.
- `final_parse.json` / `.log`: tree-sitter syntax gate over all 11,107 C# files.
- `final_sweep.json`, `final_sweep.methods.jsonl.gz`, and
  `final_sweep.tail-args.jsonl.gz`: merged direct lift of all 116,178 native
  MethodDefs.
- `sweep_comparison.json`: complete Review 83 → Review 84 manifest comparison;
  structural metrics do not change.
- `constructor_sweep.json` / `.log`: direct lift of all 11,737 native
  constructors and the exact 15 conservative leftovers.
- `promotion_verification.json`: candidate and promoted `final_out/` inventory
  and aggregate hashes.
- `release_verification.json` and `tests_staging_preflight.log`: isolated-copy
  output-hash and complete 358-test preflight. The final archive is extracted
  and checksum/test verified externally after packaging.

## Constructor and allocation proof

- `output_audit.json` / `.log`: full generated-tree inventory, constructor,
  allocation, shared-address, unresolved-object, and initializer metrics.
- `output_changes.diff.gz`: complete generated C# diff.
- `constructor_output_invariants.json` / `.log`: zero raw pseudo calls,
  leading-comma constructor calls, and standalone constructor allocations.
- `snapshot_comparison.json` / `.log` and `snapshot_changes.diff`: the same 64
  MethodDefs, 56 unchanged and eight reviewed changes.
- `tests_snapshots_preupdate.log`: exactly the eight intended Review 83 snapshot
  deltas before the gated Review 84 freeze.
- `source_changes.diff`, `source_hashes.json`, and `source_format.json`: exact
  core diff, SHA-256 values, UTF-8 BOM, and CRLF checks.

## Important interpretation

The build and sweep were each split into two assembly partitions. Build overlap
was limited to `Unity.InputSystem.dll`, accidentally selected by both the
`Unity.InputSystem.dll` and `System.dll` substrings; all 345 overlapping files
were byte-identical. The unique merged inventory exactly matches Review 83.

The raw sweep comparison contains 14,688 changed render hashes across fresh
partitions. It is retained as broad regression scope, not claimed as an exact
source-attribution count. The authoritative output audit compares complete
strict-built trees; the constructor-only sweep defines the native-constructor
residue directly.

No .NET SDK was available, so there was no current compiled-pattern smoke or
complete generated-project C# build. Syntax cleanliness, exact allocation
provenance, and metadata constructor proof are not claims that the complete
recovered game is semantically equivalent or runnable.
