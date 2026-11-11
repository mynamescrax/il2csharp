# Docs index

Project notes live here since the 2026-09-12 reorg (previously loose
`*.md` files at the repo root; the pre-reorg set was backed up at
`bckups/docs_reorg_2026-09-12.zip` until the whole `bckups/` directory was
deleted on 2026-09-19, so this history is the record). The two Python
sources are untouched by the move. All repo paths below are root-relative.

## Start here (live)

- `docs/todo.md` — current work (codegen-intrinsic landing 1, r10
  promoted tree), validation status, next priorities, replacement
  records.
- 2026-09-22 failure-class inventory (formerly root `TODONOW.md`) —
  appendix of `docs/todo.md` (historical, r4c era).
- `docs/handoff-2026-09-23.md` — 2026-09-23 stop record (historical).
- `docs/handoff-2026-10-05.md` — fix 125 compile-gate first slice stop
  record (historical).
- `docs/handoff-2026-10-06.md` — live handoff: compile-gate chain
  125-132 state, gate numbers, standard per-slice procedure, e-MCP
  session mechanics.
- `docs/reference.md` — working-loop rules (§4), baselines / promotion /
  known artifacts (§6), gotchas (§7), next-up families (§2), Batch 19
  gate methodology (§5). Read §4 and §7 before any nontrivial change.
- `docs/construct-mapping.md` — what native constructs recover as what C#,
  implementation notes, the detailed validation gates and limitations.
- `docs/public_release.md` — what must never be published (licensed
  fixture, decompiled trees) and the scrubbed-export checklist.
- `docs/reviews/` — per-release notes: `REVIEW.md` (Review 77) and
  `REVIEW78.md`–`REVIEW87.md`, plus `REPLACEMENT.md` (release handoff).
  These are historical records: the 2026-09-28 public scrub removed the
  older golden archives, raw logs and body dumps they reference (see
  `docs/public_release.md`).
- `../README.md` (repo root) — quick start: install, usage, output shape,
  supported targets, testing, limitations.
- `../CLAUDE.md` (repo root) — architecture and mandatory
  correctness/validation guardrails.

## Archive (read-only history, bodies unchanged by the move)

- `docs/archive/todo-archive.md` — superseded replacement records,
  promotion archaeology, session leads, standing backlogs.
- `docs/archive/reviews-log.md` — short state records, Reviews 78–87
  plus fix 97 (§§0av–0bf).
- `docs/archive/batches-a.md` — §0 index plus Batches 20–25 (§§0, 0b–0g).
- `docs/archive/batches-b.md` — Batches 26–37 (§§0h–0q).
- `docs/archive/batches-c.md` — Batches 39–41, 57–60, 71–77
  (§§0s–0ak in file order).
- `docs/archive/batches-d.md` — Batches 48–56 (§§0aj–0ab in file order).
- `docs/archive/batches-e.md` — Batches 38, 42–47 (§§0aa–0r in file
  order).
- `docs/archive/numbers-backlogs.md` — archived numbers (§1), backlog
  trail (§3), compressed history (§8).

## Section map (`§NN` cross-references)

Every `§NN` reference in the repo resolves against these files:

| Section | File |
|---|---|
| §§0av–0be (review records) | `docs/archive/reviews-log.md` |
| §0, §§0b–0g | `docs/archive/batches-a.md` |
| §§0h–0q | `docs/archive/batches-b.md` |
| §§0s–0ak (file order) | `docs/archive/batches-c.md` |
| §§0aj–0ab (file order) | `docs/archive/batches-d.md` |
| §§0aa–0r (file order) | `docs/archive/batches-e.md` |
| §§1, 3, 8 | `docs/archive/numbers-backlogs.md` |
| §§2, 4, 5, 6, 7 | `docs/reference.md` |

Notes:

- Batch sections after §0u are filed out of chronological order (newest
  first: 58, 59, 77, 76, …); the table above follows file order, which
  is what the `§NN` references assume.
- References of the form `REVIEWnn.md`, `todo.md`, or `new.md §NN`
  inside archive files predate the move: `REVIEWnn.md` now lives in
  `docs/reviews/`, live `todo.md` is `docs/todo.md`, and `new.md §NN`
  resolves via the table above.
- `validation_reports/*/README.md` files point at `docs/reviews/`;
  the frozen `summary.json` records inside `validation_reports/` keep
  their original root-relative `../../REVIEWnn.md` strings as evidence
  and were deliberately not rewritten.
- Two code comments still cite pre-move paths and were deliberately
  left byte-identical when the monoliths were split into `il2cpp/`:
  `il2cpp/dec/flow.py` ("new.md section 4" = `docs/reference.md` §4) and
  `il2cpp/lifter/insn.py` ("todo.md 0l" = `docs/archive/batches-a.md` §0l).
  They were formerly in `decompiler.py` and `il2csharp.py` respectively.
