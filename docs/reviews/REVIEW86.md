# Review 86 - deterministic, evidence-based EH helper naming (fixes 90, 91)

Fixes 90 and 91 replace the way the decompiler decides that a call target is
an il2cpp exception helper. Review 85 section 7 diagnosed this as order
dependence and proposed making the discovery deterministic. That diagnosis
was half right; the correction is recorded in `REVIEW85.md` section 7.

## Outcome

- `_seh_helpers` no longer leaks helper VAs across methods (fix 90).
- The helper pair is proven once from the whole binary, and only for targets
  that survive three independent filters (fixes 91, 91b, 91c).
- The proven set for this binary is exactly two targets: `0x180435740`
  rethrow and `0x180435670` raise.
- Cost: one 1.7 s pre-pass per lifter, memoised.

## 1. What fix 90 removed

`_seh_helpers` wrote `raise_va` / `rethrow_va` onto the shared lifter and
never reset them, so a method's rendering depended on what had been lifted
before it.

A census of all 4,526 pad-bearing methods (`work/review87_helper_census.py`,
`work/review87_helper_classify.py`) produced 108 distinct target/role records:

| role | distinct targets | unregistered | registered managed methods |
| --- | --- | --- | --- |
| rethrow | 99 | 48 | 51 |
| raise | 9 | 4 | 5 |

The helper VA is therefore not a program constant, and more than half of the
rethrow targets were ordinary methods -- `AsyncTaskMethodBuilder.SetException`,
`Debug.LogException`, `Marshal.FreeHGlobal`, `DateTime.AddYears`,
`Console.set_ForegroundColor`. Every caller of one of those printed `throw;`
where a real call belonged.

Fix 90 clears both fields for every method and requires a candidate to be
unregistered native code: absent from `addr_to_method`, from
`addr_candidates`, and from the export table. Verified over 3,000 methods:
2,709 accepted targets (90.3%), zero registered methods accepted
(`work/review87_fix90_verify.py`).

## 2. What fix 90 cost, and two designs that failed

Per-method evidence is honest but narrow: a method with no EH pad of its own
can never name a helper, so those calls render as `sub_...(...)`.

Two cheaper ways to widen it were tried and rejected on measurement:

- **The helper's callee.** The stubs funnel into unnamed native plumbing, and
  one sink, `0x1804455c0`, is shared by five unregistered helpers and 36
  registered managed methods, so keying on it would re-admit
  `AsyncTaskMethodBuilder.SetException` -- the exact defect fix 90 removed
  (`work/review88_helper_chain.py`).
- **A linear byte window at each pad** instead of real block structure. Fast
  at 0.6 s, but it inverted role dominance for `0x1804356b0`, truly 283
  rethrow / 24 raise, approximated as 617 / 1829, which would emit `throw x;`
  where `throw;` belongs (`work/review88_witness.py`).

## 3. Fix 91: prove the pair once

`_ensure_eh_helper_set` runs the real shape detection over every pad-bearing
method, tallies which target each method names and in which role, and keeps
only targets that enough independent methods agree on. It runs once per
lifter, publishes an empty-dict sentinel before scanning so a half-built set
is never observable to a render, and costs 1.7 s for 4,526 pad-bearing
methods (measured first lift 1.64 s, second lift 0.016 s).

## 4. Fix 91b: plumbing the lifter can already name

The first draft trusted the witness tally and published six targets. Three
were runtime plumbing, and `work/review88_anchor_diff.py` caught it. The
worst was `0x180435420`, taught by 181 methods, which is a `jmp` thunk onto
`il2cpp_codegen_initialize_runtime_metadata`. In mi 77946 three
`il2cpp_codegen_initialize_runtime_metadata(typeof(...))` lines became bare
`throw;`, which also dropped an `il2cpp_object_new` argument, renumbered the
locals, and collapsed an `else`.

Rule added: reject any candidate the lifter can already name -- `rt_names`,
the discovered `rt_init_meta` / `rt_alloc` / `rt_value_box` / `rt_sqrt`
slots, the `rt_arrnew` / `rt_wbarrier` sets, class-init twins, and exports.

Two subtleties, both measured rather than assumed:

- Membership must be tested **after** resolving jmp thunks. `0x180435420` is
  absent from every known-VA set; only `0x180490fb0`, the target of its
  `jmp`, is named.
- Resolvability alone must **not** disqualify. `_thunk_final` also walks
  `sub rsp,N; call T` noreturn forwarders, and genuine throw helpers are
  shaped exactly like that (`0x180435740` begins `48 83 ec 28 e8 ...`). So
  only a resolution the lifter can *name* rejects the candidate, and the
  proven rethrow helper survives the rule.

The other two were `0x1804356a0` and `0x1804356b0`, which are genuine throw
helpers but are `raise_IndexOutOfRangeException` and
`raise_NullReferenceException`: each raises one specific exception and
already carries a name derived from a string reference in its own wrapper
chain, so a bare `throw;` would lose which exception is thrown.

## 5. Fix 91c: a throw helper never returns

Witness count is not sufficient evidence, and my own noreturn probe
(`work/review88_helper_ident.py`) proved it. `0x180002650` had the third
highest tally in the scan, 45 methods, yet its body is
`movsxd rdx,[rcx+10h]; lea eax,[rdx-1]; ...; ret`. Four more accepted
targets also return: `0x180002050`, `0x180003110`, `0x18043dc60`,
`0x182252b90`.

An il2cpp throw helper is noreturn by construction, and the compiler follows
the call with `int3` padding. Decoding a candidate to its first `int3`/`ud2`
and finding a reachable `ret` is therefore positive proof that it is not a
helper. Only positive evidence rejects: an unreadable target keeps the
previous behaviour. Results are memoised per VA.

## 6. The measured distribution and the acceptance rule

Full scan of all 4,526 pad-bearing methods with both new filters active and
the threshold lowered to 3 (`RATE=0 python work/review88_sample.py`):

| target | rethrow witnesses | raise witnesses | disposition |
| --- | --- | --- | --- |
| `0x180435740` | 3403 | 126 | proven rethrow |
| `0x180435670` | 25 | 183 | proven raise |
| `0x180435040` | 13 | 0 | noreturn, below threshold |
| `0x1804346b0` | 12 | 13 | role is a coin flip |
| `0x180434690` | 8 | 0 | noreturn, below threshold |
| `0x180001ea0` | 6 | 0 | scan-continuation artifact |
| `0x180002070` | 3 | 0 | scan-continuation artifact |

Real-helper witness counts *rose* once the impostors were filtered out
(rethrow 3347 -> 3403), because the pad scan no longer halts on the first
impostor it reaches.

Two constants follow from this measurement:

- `_EH_HELPER_MIN_WITNESSES = 25`, placed in the 183 -> 13 gap (14x). The
  first draft used 10, whose justification, a 6 -> 11 gap, disappeared once
  the impostors were filtered out; 10 then cut inside the dense 13/13/12/8
  cluster.
- `_EH_HELPER_MIN_DOMINANCE = 4`. `0x1804346b0` split 12 rethrow / 13 raise,
  and the two roles render differently (`throw;` against `throw x;`), so a
  near-tie is refused rather than guessed. `work/review88_sample.py`
  independently flagged this VA as role-ambiguous at K=1500.

Both new filters are properties of the callee alone, so they screen the
per-method evidence and the program-wide set alike. Every address is measured
at run time; only the threshold, the ratio, and the decode caps are constants.

## 7. Coverage restored

Over a fixed 400-method sample, counted with identical needles in both
configurations (`work/review88_fix91_verify.py`):

| configuration | throw renderings | methods with a throw | residual proven-helper calls |
| --- | --- | --- | --- |
| fix 90 only | 11 | 2 | 6 |
| with the proven set | 17 | 8 | 0 |

The four anchors fix 90 rescued keep their real calls: `Task.FromException`
(mi 11899), `AsyncTaskMethodBuilder.SetException` (mi 12041),
`Debug.LogException` (mi 22316), `Marshal.FreeHGlobal` (mi 43179). The
pad-less mi 77946 renders its throw and keeps all three
`il2cpp_codegen_initialize_runtime_metadata` calls, identically from a fresh
lifter, so the result does not depend on lift order.

## 8. Validation

Fix 90 was gated on its own before fix 91 was written:

| gate | result |
| --- | --- |
| direct sweep (`sweep2.json`, 619.9 s) | 116,178 methods, 0 crashes, 0 brace / goto / empty-arg defects |
| compare against `review84/final_sweep.json` | common 116,178, added 0, removed 0, changed 9,778, structural 3, new crashes 0 |
| strict build (`work/review87_out`, 623 s) | 11,107 type files, 115,658 bodies, 0 failures |
| built-tree parse gate (`parse2.json`) | 11,107 files, 0 bad files, 0 errors, 0 missing, 0 recovery nodes |
| test suite | 408 passed |
| goldens regeneration | 0 changed snapshots |

All three structural changes were attributed individually
(`work/review87_structural.py`): mi 32680 `NewDeviceMsg.Process`; mi 39563
`XmlSerializer.Serialize`, whose renderings are identical either way; and
mi 48016 `<WaitForServerToCloseConnectionAsync>d__63.MoveNext`, where a fake
`throw` had swallowed an entire `try` block (455-line diff).

Regressions: `tests/test_review87_eh_helpers.py` (6 portable + 3 native) and
`tests/test_review88_eh_helper_set.py` (11 portable + 5 native), covering the
proven pair, the thunk-resolution rule, the "resolution alone is not
disqualifying" case, the returning-target rejection, memoisation, the
sentinel, the acceptance constants, and the mi 77946 metadata-init
regression.

Fix 91 was then gated the same way, against the same Review 84 baseline:

| gate | result |
| --- | --- |
| direct sweep (`sweep3.json`, 555.7 s) | 116,178 methods, 0 crashes, 0 brace / dangling-goto / empty-arg defects |
| compare against `review84/final_sweep.json` | common 116,178, added 0, removed 0, changed 11,195, structural 4, new crashes 0 |
| strict build (`work/review88_out`, 639.8 s) | 11,107 type files, 115,658 bodies, 0 failed, 0 structured fallbacks |
| built-tree parse gate (`parse3.json`) | 11,107 files, 0 bad, 0 errors, 0 missing, 0 recovery nodes |
| test suite | 424 passed |
| goldens (`tests/goldens_review84.json`) | 64 snapshots regenerated, 0 changed, 64 passed |
| promotion (`promotion_verification.json`) | 11,200 files, candidate aggregate == promoted aggregate, 0 mismatches |

The gated tree was promoted over `final_out` by `work/review88_promote.py`,
which mirrors the Review 84 promotion record: the previous tree is renamed to
`bckups/final_out_r84` rather than deleted, the candidate is copied into
place, and both trees are then hashed file by file and reduced to one
aggregate sha256 each. Candidate and promoted aggregates both came out
`0ef7607e317dbb00f59ad72ccaa8089b36ccf0a79c42bae7f525ebeb30118d00` over
11,200 files with no per-file mismatch. The `source_sha256` recorded in the
promotion report, the regenerated goldens, and `sweep3.json` all agree, so
the shipped tree, the frozen snapshots, and the gate reports describe one
state of the sources.

`changed_method_count` rises from 9,778 to 11,195 because the proven set
reaches pad-less callers that fix 90 could not name. The sweep totals are
notable for what did *not* move: `into_block_gotos` is 8,071 across 2,048
methods, identical to the fix-90 gate, and `tail_argument_changes` is
unchanged at 1,771 across 1,693 methods. Total rendered lines fell by 643
(2,192,702 -> 2,192,059) as helper calls collapsed into `throw` statements.

The four structural entries are a redistribution rather than an accumulation.
`work/review88_anchor_diff.py` attributes each one:

| mi | method | into-block gotos | cause |
| --- | --- | --- | --- |
| 37694 | `XmlWellFormedWriter.ThrowInvalidStateTransition` | 2 -> 3 | fix 91, four proven raise sites |
| 38740 | `ValidateNames.ThrowInvalidName` | 0 -> 3 | fix 91, three proven raise sites |
| 38807 | `XmlConvert.ToString` | 1 -> 0 | fix 91, one proven raise site |
| 48016 | `<WaitForServerToCloseConnectionAsync>d__63.MoveNext` | 0 -> 1 | fixes 85-90; no rendering change under fix 91 |

In each fix-91 case the rendering itself became more correct. In mi 38740,
`object obj11 = sub_180435670(obj8, obj10);` -- a leaked return value standing
in for the throw of the `XmlException` constructed on the preceding lines --
becomes `throw obj8;`. The goto movement is a second-order effect: a `throw`
terminates its block, so successor edges change and the structurer sometimes
emits a label and a goto where it previously emitted `else if`. One method
improved, two regressed on that metric, and the corpus total did not move.

### Corpus residue, counted with identical needles

`work/review86_count_raise.py` over each built tree, one probe and one needle
set per tree:

| tree | `sub_180435670(` | `sub_180435740(` | `throw` |
| --- | --- | --- | --- |
| `work/review86_out` (before fix 90) | 460 | 28 | 3,113 |
| `work/review87_out` (fix 90 only) | 3,366 | 43 | 267 |
| `work/review88_out` (fixes 91, 91b, 91c) | 0 | 0 | 3,550 |

This is the honest cost of fix 90 in isolation. The 3,113 `throw` statements
in the pre-fix-90 tree were not earned by evidence: each came from a helper
VA that had leaked in from a previously lifted method. Some of those leaks
happened to name the real helper and were right by luck; many named a
registered managed method and ate a real call. Fix 90 refused all of them,
which cost 92% of the throw coverage, and fix 91 restores it from proof.

Fix 91c removes the raw helper call sites entirely: both needles score zero in
`work/review88_out`, and `throw` reaches 3,550 occurrences across 560 files.
That is higher than the 3,113 of the pre-fix-90 tree, and this time every one
of them is backed by a program-wide proof rather than by inherited state. The
snapshot set is unaffected either way: all 64 goldens re-render byte for byte,
because none of the focus methods calls either proven helper.

These two figures, 3,113 -> 267 and 460 -> 3,366, were re-measured here with
a single probe and a single needle set after I suspected the first draft had
counted the two trees with different needles (`throw ` against `throw`). The
suspicion was wrong; the pair stands.

## 9. Limits and next work

- Five noreturn but sub-threshold targets stay on per-method evidence only:
  `0x180435040` (13/0), `0x1804346b0` (12/13, role ambiguous), `0x180434690`
  (8/0), `0x180001ea0` (6/0), `0x180002070` (3/0). Some are probably genuine
  helpers on rarer exception paths; proving them needs evidence other than a
  witness count.
- Candidate fix 92: render `raise_IndexOutOfRangeException` and
  `raise_NullReferenceException` as `throw new IndexOutOfRangeException();`
  and `throw new NullReferenceException();`. Both currently render correctly,
  as named calls.
- Per-method evidence is not required to agree with the proven set.
  Tightening that is deferred until the sub-threshold targets are understood.

## Reproduce

```
PYTHONHASHSEED=0 python -m pytest -q
python work/review88_helper_ident.py
python work/review88_anchor_diff.py
python work/review88_fix91_verify.py
RATE=0 python work/review88_sample.py
```
