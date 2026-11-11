# Review 82 validation evidence

Current release: `../../docs/reviews/REVIEW82.md` and `../../docs/reviews/REPLACEMENT.md`.
The unchanged native/game inputs were read statically and never executed.

## Full gates

- `summary.json`: authoritative release counts, hashes, environment, limits,
  and extracted-copy verification.
- `tests_baseline.log`, `tests_portable.log`, `tests_native.log`, and
  `tests_final.log`: Review 81 baseline, portable, native-behavior, and complete
  Review 82 suites.
- `final_build.log`: fresh strict all-assembly emission.
- `final_parse.json` and `final_parse.log`: all generated C# syntax-checked.
- `final_sweep.json`, `final_sweep.methods.jsonl.gz`, and
  `final_sweep.tail-args.jsonl.gz`: direct lift of every native MethodDef.
- `comparison.json`: complete Review 81 → Review 82 method-hash and structural
  comparison.
- `promotion_verification.json`: all candidate output hashes checked again after
  clean promotion into `final_out/`.
- `release_verification.json`, `manifest_release_copy.log`, and
  `tests_release_copy.log`: separately extracted archive verification.

## Object/readability evidence

- `naming_audit.json`: full-tree `objN`, declaration, semantic-prefix, and
  conservative guard-residue census.
- `output_comparison.json`: complete generated-file inventory, hashes, line and
  stability metrics.
- `output_changes.diff.gz`: compressed full generated-code diff.
- `snapshot_changes.diff`: readable changes for the unchanged 64-MethodDef
  sample.
- `snapshot_transform_proof.json`: all 64 Review 82 snapshots equal exactly the
  final naming/type transform applied to their Review 81 bodies.
- `source_changes.diff`, `source_hashes.json`, and `source_format.json`: core
  implementation diff, exact hashes, BOM, and line-ending checks.
- `assembly_csharp_build.log` and `assembly_csharp_parse.json`: focused preflight
  over the 489-file game assembly.

The pass is deliberately last in the pipeline. It derives names only from
already emitted concrete types, avoids metadata parameter/body identifier
collisions, and skips literals/comments. Object declarations refine only for
single-definition array, string, or exact `typeof` right-hand sides without a
by-reference/address escape. The 21 guarded residues are listed in
`naming_audit.json`.

No .NET SDK was available, so there was no current compiled-pattern smoke or
full-project C# build. The generated game and supplied binary were not executed.
