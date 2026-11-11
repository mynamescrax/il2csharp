# Review 85 - enum member identity, integer literals, and signed immediates

**Completed:** 2026-09-10  
**Scope:** enum member decoding, enum-valued arguments, integer literal parsing, address composition, and immediate signedness  
**Authority:** `validation_reports/review85/`

Review 84 closed object construction. What remained were smaller defects that
are worse than they look, because each one prints a confident, plausible,
*wrong* fact. An enum argument printed a named member the metadata never
assigned to that value; a hex literal printed a number the machine code never
contained; a negative immediate printed as a large positive one.

Before:

```csharp
new FileStream(text2, 3);
obj13 = System.DateTime.SpecifyKind(dateTime1, 0);
if (dateTime1.Kind == DateTimeKind.Utc)   // the native code compares against 2
this.__1__state = 4294967294;
this.value = (0 + 0x3);
```

After:

```csharp
new FileStream(text2, FileMode.Open);
obj13 = System.DateTime.SpecifyKind(dateTime1, DateTimeKind.Unspecified);
if (dateTime1.Kind == DateTimeKind.Local)
this.__1__state = -2;
this.value = 3;
```

Review 85 fixes the decoding underneath each of those lines, and it ends with
a finding that matters more than any of them: part of the corpus delta this
release is **not** caused by the fixes at all. Section 7 documents that
honestly rather than claiming it as an improvement.

## Outcome

- Enum member tables now decode the compressed (zigzag) default-value blob
  through the enum's underlying element type. The previous reader took the
  blob raw at four fixed widths, which **doubled every member value** and
  invented junk entries. **Eight member names are confirmed wrong before and
  correct after.**
- Enum-valued call arguments fold to `Type.Member` instead of a bare integer,
  so `new FileStream(text2, 3)` becomes `new FileStream(text2, FileMode.Open)`.
- `_int_lit` no longer treats the hex digits `d` and `f` as float suffixes.
  It had been reading `0x3d` as **3**, `0x7f` as **7**, and `0xf` as
  unparseable. **17 parser cases are now pinned by tests.**
- Literal-base address composition folds instead of printing its own
  scaffolding: `(0 + 0x3)` becomes `3`.
- Immediates are reinterpreted at their declared width, so a 32-bit `-2`
  stops printing as `4294967294`. **188 immediates were rewritten in the
  first 4,000 methods**, across `sbyte`, `short`, `int`, and `long`.
- Corpus effect: **10,758 method bodies changed, 0 structural changes, 0 new
  crashes, 0 added or removed methods**, net **-526 lines**.
- Tests **358 -> 399** (289 portable + 64 snapshots + 46 native).
- A validation-tool bug that made moved sweep reports unreadable on Windows
  is fixed.
- **New defect diagnosed and quantified, not fixed:** EH helper naming is
  order dependent (section 7).

## 1. Enum member tables were doubled (fix 86)

`enum_members` read each literal field's default value straight out of the
metadata blob at a width guessed from the field type. IL2CPP stores those
values **zigzag compressed**, so every decoded number was the zigzag encoding
rather than the value: 37 for 74, 39 for 78, 59 for 118. The reader also
accepted trailing junk as extra members.

The fix resolves the enum's underlying element type through `td.element` and
`_type_enum`, then decodes with the compressed-integer reader that the rest of
the metadata layer already uses.

The corrected names, each cross-checked against the enum declaration emitted
by the independent `parse_default` path:

| Printed before | Value | Actually is | Value | Method |
| --- | --- | --- | --- | --- |
| `Token.XdrDatatype` | 37 | `Token.XsdSchema` | 74 | mi 42414 |
| `Token.XdrExtends` | 39 | `Token.XsdElement` | 78 | mi 42414 |
| `Token.SchemaRef` | 59 | `Token.XsdRedefine` | 118 | mi 42414 |
| `SimulationStages.Forward` | 2 | `SimulationStages.Resimulate` | 4 | mi 26747 |
| `ParsingFunction.Eof` | 11 | `ParsingFunction.InReadAttributeValue` | 22 | mi 37191 |
| `ParsingFunction.ReaderClosed` | 12 | `ParsingFunction.InReadContentAsBinary` | 24 | mi 37191 |
| `DateTimeKind.Utc` | 1 | `DateTimeKind.Local` | 2 | mi 86310 (twice) |
| `PhotonSocketState.Connecting` | 1 | `PhotonSocketState.Connected` | 2 | mi 28576 |

The doubling is visible directly in the table: 74 = 2 x 37, 78 = 2 x 39,
118 = 2 x 59.

## 2. Enum-valued arguments (fix 85)

`_hint_arg_types` already knew a call argument's declared parameter type. It
folded booleans but not enums, so correct enum metadata still reached the page
as a bare integer. Enum arguments now render `Type.Member` when the value has
exactly one member, and stay numeric otherwise.

Verified end to end at all three `SaveSystem` call sites: `FileMode.Open`
(mi 27274), `FileMode.Create` (mi 27277), `FileMode.Open` (mi 27280).

## 3. Hex literals were silently truncated (fix 87)

`_int_lit` stripped a trailing `f`/`d` float suffix before parsing. Those are
also hex digits, so `0x3d` parsed as 3, `0x7f` as 127 became 7, and `0xf`
failed to parse at all. Only decimal-looking text can carry a float suffix, so
the strip is now conditional on the text not being hex.

This defect was found by a probe that used `_int_lit` as its own ground truth
and crashed on `None`. The probe was the bug report.

## 4. Literal-base address composition (fix 88)

A `LEA` with a literal base emitted the composition text verbatim, producing
`(0 + 0x3)` where the instruction materialises the constant 3. The LEA path
now folds when the base parses as an integer, and marks the result `int` so
nothing downstream re-renders it as a misleading pointer expression.

This fix depends on fix 87 and was applied in the same edit: with the old
`_int_lit`, folding `(0 + 0x2d)` would have produced 2 instead of 45. The
deliberately untouched sibling is `_field_expr`'s dereference form, which
keeps `((byte*)num4 + 0x0)[0]` byte-identical and stays pinned by the Review
80 regression.

## 5. Signed immediates at every width (fix 89)

`_fimm` reinterpreted only 16-bit immediates as signed, so a 32-bit `-1`
printed as `4294967295` and `-2` as `4294967294`. It now reinterprets at each
signed width (`sbyte`, `short`, `int`, `long`) and deliberately leaves the
unsigned and native-int type codes alone.

Measured on the first 4,000 methods: **188 immediates rewritten**, all `Int32`
in that sample, for example `4294967295 -> -1`. The async state machine field
that motivated it now reads `this.__1__state = -2;`.

One related line is deliberately left alone: `((byte*)obj15 + 0x0)[0] =
4294967294;` stores through an untyped `byte*` lvalue, so there is no declared
width to justify a sign flip. That is recorded as open work, not fixed by
guess.

## 6. Moved sweep reports could not be read (validation tooling)

`tools/validate_corpus.py` resolved a manifest path recorded on another
machine by testing `Path("/old/machine/x.gz").is_absolute()`, which is `False`
on Windows. It then fabricated `C:\old\machine\...` and failed. Manifests are
now relocated relative to the report that names them, which is what made this
release's report directory rename safe.

## 7. What the corpus delta does and does not prove

Of the 10,758 changed method bodies, **1,913 are `Neon` ARM intrinsic stubs**
whose last statement changed from a raw helper call to `throw obj2;`. That
change is real and correct, but it is **not** caused by fixes 85-89. Four
independent checks establish this:

1. Review 84's baseline sweep records the exact source hashes of the
   pre-session backups, so the comparison is genuinely before/after.
2. Reverting `_int_lit`, `_fimm`, and `_hint_arg_types` to their baseline
   definitions at runtime leaves the rendering **and** the helper discovery
   completely unchanged.
3. Lifting the same method in a fresh process renders the old raw call, with
   `raise_va` unset.
4. Review 84 swept in two partitions (63,300 + 52,878) and merged the
   manifests. Partition 1 contains mi 100, which teaches the lifter the raise
   helper VA; partition 2 contains the `Neon` methods but not mi 100. The
   merged baseline therefore recorded partition 2's uninformed rendering,
   while this release swept in a single process.

The root cause is a real defect: `_seh_helpers` discovers the raise and
rethrow helper VAs opportunistically from whichever method happens to be
lifted first, writes them onto the shared lifter, and never resets them. A
method's output therefore depends on what was lifted before it -- on process
partitioning, and in principle on test ordering.

It is not only a cross-run problem. **A single build is internally
inconsistent**: `work/review86_out` contains 460 raw `sub_180435670(...)`
calls across 142 files and 28 `sub_180435740(...)` calls across 19 files,
alongside 3,113 rendered `throw` statements. The 64 golden snapshots contain
no method that calls either helper, which is why the snapshot review did not
surface this.

**Correction (fixes 90 and 91).** Calling those 3,113 statements "correctly
rendered", as this section first did, was wrong. A census of all 4,526
pad-bearing methods found 99 distinct rethrow targets and 9 raise targets,
and 51 of the rethrow targets were ordinary registered methods --
`AsyncTaskMethodBuilder.SetException`, `Debug.LogException`,
`Marshal.FreeHGlobal`, even `DateTime.AddYears`. Every caller of one of those
printed `throw;` in place of a real call, so a large share of the 3,113 were
leaked values that had each eaten a call, not correct output. The defect was
worse than order dependence, and the remedy was not simply to make the
discovery deterministic. See `REVIEW86.md` for fixes 90 and 91.

The reproduction probes are `work/review86_scan_raiseva.py` (finds the
teaching method: rethrow at mi 64, raise at mi 100) and
`work/review86_partition_check.py` (proves the merged baseline).

## 8. Validation

All gates ran on the frozen sources `il2csharp.py` `e1f0bc02...` and
`decompiler.py` `79cd0d79...` against the unmodified fixtures.

| Gate | Result |
| --- | --- |
| Portable tests | 289 passed, 110 deselected |
| Full suite with native fixtures | **399 passed, 0 failed** |
| Golden snapshots | 64 frozen; 9 changed, +37 / -37 lines, every changed line an enum-member fold |
| Direct structured-lift sweep | 116,178 methods, **0 crashes**, 2,192,368 lines, 578.9 s |
| Sweep comparison vs Review 84 | 10,758 changed methods, **0 structural changes**, **0 new crashes**, 0 added/removed |
| Structural metrics | into-block gotos 8,067 across 2,047 methods (unchanged); brace and dangling-goto totals 0 |
| Strict emission build | 11,107 type files, 115,658 bodies, **0 failed**, 0 structured fallbacks, 620,988 ms |
| tree-sitter C# parse gate | 11,107 files, 0 bad files, 0 errors, 0 missing, 0 recovery nodes, 10.9 s |

The build inventory is identical to Review 84 (11,107 files / 115,658
bodies). The parse gate ran against the freshly emitted tree rather than the
stale `final_out`, so it validates the fixed code.

A .NET SDK remains unavailable, so the generated tree was not compiled.

## Limits and next work

- **EH helper naming was order dependent** (section 7). **Resolved by fixes 90
  and 91**; see `REVIEW86.md`. The target stated here originally -- "488 raw
  helper call sites should become `throw` / `throw;`" -- is retracted. It
  assumed the existing `throw` renderings were right and only the raw calls
  were wrong, when in fact most helper targets were misidentified registered
  methods. Naming is now per-method evidence plus a program-wide proven pair,
  `0x180435740` rethrow and `0x180435670` raise, each required to be
  unregistered native code that the lifter cannot already name and that has
  no reachable `ret`.
- `((byte*)objN + 0x0)[0] = 4294967294;` still prints unsigned. The store has
  no declared width; recover the lvalue type instead of sign-flipping.
- `Object.Instantiate<Font>` is emitted with the wrong generic argument.
- `final_out` **has** been re-promoted (2026-09-11), but to the tree gated
  after fixes 90, 91, 91b, and 91c rather than the tree described here; see
  `REVIEW86.md` and `validation_reports/review85/promotion_verification.json`.
  `work/review86_out` was never promoted. The previous Review 84 tree is kept
  at `bckups/final_out_r84`.
- All Review 84 limits still stand: 112,423 `object objN` declarations,
  13,254 empty allocations, 160 `sub_180506120` sites, and the open ABI,
  control-flow, and ARM64 work.

## Reproduce

With dependencies installed:

```text
PYTHONHASHSEED=0 python -m pytest -q
```

The complete offline gates use `tools/validate_corpus.py`:

```text
PYTHONHASHSEED=0 python tools/validate_corpus.py sweep \
  --metadata "$IL2CSHARP_METADATA" --binary "$IL2CSHARP_BINARY" \
  --report validation_reports/review85/recheck_sweep.json

python tools/validate_corpus.py compare \
  validation_reports/review84/final_sweep.json \
  validation_reports/review85/recheck_sweep.json \
  --report validation_reports/review85/recheck_comparison.json

python tools/validate_corpus.py parse work/review86_out \
  --report validation_reports/review85/recheck_parse.json
```

The order-dependence finding reproduces with:

```text
PYTHONHASHSEED=0 python work/review86_scan_raiseva.py
python work/review86_partition_check.py
```

Use `--strict` and a fresh output directory for emission. Do not execute the
supplied binary; all release validation is static.
