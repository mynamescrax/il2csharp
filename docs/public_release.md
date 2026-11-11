# Public release checklist

Status 2026-09-28: the scrub is **executed** and force-pushed. This file
records what was removed, what remains before flipping visibility, and how
to verify.

## Done (2026-09-28)

- `testgame/` removed from every commit; the local copy is kept and
  git-ignored (`testgame/` rule in `.gitignore`).
- Full scrub via `git filter-repo`: the golden archives and full-body
  snapshots, review78/79/80 focused + structural JSONs, every `.diff`,
  `*.log`, `*.log.gz`, `*.diff.gz`, `*.tail-args.jsonl.gz` artifact, and
  `SHA256SUMS.presplit_20260912.txt`.
- LFS objects pruned locally (`.git/lfs` 0 MB; `git lfs ls-files --all`
  empty); LFS lines removed from `.gitattributes`.
- Tracked `tests/goldens_review84.json` is **hash-only**
  (`tools/goldens_hash_only.py`); `tools/make_goldens.py` now defaults to
  hash-only and takes `--full` for local-only bodies.
- Blob-level verification over every ref: 0 fixture paths, 0 body/asm
  JSONs, 0 disassembly bulk.
- MIT `LICENSE` added (source, tests, tools, docs only — never game data
  or decompiled output).

## Before flipping visibility

1. **Remote LFS storage.** Rewriting local history cannot erase LFS
   objects already uploaded to GitHub. Recreate the GitHub repository
   (delete + create) and push the rewritten history, or ask GitHub support
   to purge its LFS storage; force-pushing alone leaves the old blobs
   there.
2. Optionally re-run `python tools/validate_corpus.py sweep`/`parse` for
   fresh evidence under the rewritten hashes (the frozen evidence is still
   valid for the source; only commit ids changed).
3. `python -m pytest -q -m "not game"` must pass without fixture env vars;
   the game-marked tests skip.
4. Keep the license scope note with any redistribution.

## Pre-scrub history

Every commit hash in docs written before 2026-09-28 refers to the
pre-scrub history, which no longer exists on GitHub. The local backup
bundle `C:\Users\crax\Downloads\il2csharp_prepurge_backup.bundle` (18 MB,
all refs; LFS pointers only -- the fixture bytes are the local `testgame/`
copy) was **not present** when the repo folder and its parent were
checked on 2026-09-28 (bundle search, `Get-ChildItem .. -Filter *.bundle`
-- empty), so the pre-scrub lineage is gone locally too unless that file
is recovered. If it is ever restored, keep it local: never push it.

## Decisions recorded 2026-09-28

- Fixture: purged from history; local + ignored (user call).
- Golden snapshots: hash-only (user call).
- License: MIT for the source (user delegated the choice).
