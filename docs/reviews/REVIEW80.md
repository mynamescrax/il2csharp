# Review 80 — correct loop-header execution and safer CFG sharing

Date: 2026-09-09. This is a complete private replacement of the supplied
`il2csharp/` folder. The original game DLL and metadata are retained byte-for-byte.
They were read statically, **never executed**. Keep these licensed fixtures private.

## Outcome and limits

- **265 tests passed**: 188 portable tests, the same 64 MethodDef snapshot cases,
  and 13 native-backed assertions across Reviews 78–80.
- Full strict rebuild: **11,107 C# type files, 91 project files, 115,658 lifted
  bodies; 0 failed bodies, 0 structured fallbacks, 0 type-emission failures**.
- Complete syntax gate: **0 bad files / 0 ERROR / 0 MISSING / 0 recovery nodes**.
- Full direct sweep: **116,178 methods / 0 crashes**. 7,797 method bodies changed
  from the verified uploaded source. Into-block gotos fell **13,641 → 8,067**
  (−5,574, 40.9%); affected methods fell **2,996 → 2,047** (−949, 31.7%).
- The instruction-generated C# smoke **compiled and ran successfully** on .NET 8.
  It now executes an actual structured-loop fragment that fails if the native
  header value is frozen. The emitter-generated unsafe project also built with
  0 warnings and 0 errors.

This is a large correctness step toward the requested goal of clean C#, **not a
claim that the recovered game is perfect or buildable yet**. The complete
`final_out/` still contains 8,067 illegal into-block gotos, unresolved values and
calls, definite-assignment problems, missing project references, partial SIMD
semantics, and other reconstruction limits. A clean tree-sitter gate is not C#
compilation or semantic equivalence. No full-game build, gameplay run, ARM64
validation, or performance improvement is claimed.

## Baseline was verified before editing

All **255 supplied tests passed unchanged** against the uploaded source. Its
complete output was syntax-checked again, and the source was directly swept with
the same final validator and `PYTHONHASHSEED=0`: 116,178 native methods, 0 crashes,
13,641 into-block gotos in 2,996 methods. The old complete output remained in
place until a fresh candidate had passed strict rebuild, parse, and comparison.

## 1. Execute native loop headers on every iteration

A natural-loop header executes on first entry and after every back edge. The old
`_emit_loop` printed header statements before `while`, freezing memory reads and
other values after the first iteration. If both conditional successors stayed in
the loop, it could also structure one arm and silently drop the other.

`_emit_loop_replaying_header` now emits these shapes as `while (true)` and sends
the header through the ordinary CFG sequencer *inside* the loop. `_seq` has three
narrow internal controls: enter a stop/header once, suppress its duplicate label,
and avoid recursively rediscovering the active loop. The later back edge reaches
the same stop set and ends that iteration. Statements, branches, edge-phi copies,
SEH bookkeeping, and exits therefore stay in native execution order.

The memory-RHS safety gate now stands down for modeled direct loops. It remains
active for unresolved or potential indirect branches, whose hidden targets can
still conceal an unproved cycle. Cyclic array-allocation materialization remains
separately guarded because correct header placement alone does not prove
allocation dominance, per-iteration identity, or alias lifetime.

Native evidence:

- `System.IO.StreamReader.ReadSpan` (MI 11974) recomputes
  `_charLen - _charPos` inside every iteration and restores the refill
  `ReadBuffer(...)` arm that the old structured output omitted. Its focused body
  goes from one `unknown` token to zero.
- `PeopleWalkPath.DrawCurved` (MI 23566) now retains the full Forward, Backward,
  HugLeft, HugRight, WeaveLeft, and WeaveRight dispatch inside its loop, rather
  than only the first `_forward[...] = true` action. The corrected loop contains
  no goto.
- `UnityEngine.InputSystem.Touchscreen.OnStateEvent` (MI 32833) recomputes its
  state predicate inside the loop instead of testing a value captured before it.
- `ViscosityVorticityJob.Execute` (MI 80548) keeps its pair loads/work inside each
  iteration and recovers `(num1 << 5) + this.pairs` instead of the prior unknown
  base.

No method name, native address, or game-specific value is hardcoded in the fix.

## 2. Fold a proved shared loop-entry gate

A common native shape sends one header edge directly to the loop body and the
other through a second, statement-free exit test before reaching that same body.
Naively structuring the first path consumes the shared body; the second then needs
an illegal goto into its lexical scope.

`_loop_shared_entry_gate` folds only the exact proved shape into one short-circuit
exit condition. It requires a single gate predecessor, one shared in-loop target,
one out-of-loop target, no SEH boundary, and no edge-specific phi copies. Any
ambiguity leaves the ordinary conservative CFG path unchanged.

`ExitGames.Client.Photon.SocketNativeSource.ReceiveLoop` (MI 28576) now renders:

```csharp
if ((this.State != 1) && (this.State != PhotonSocketState.Connecting))
{
    break;
}
```

The shared body follows once and the method contains no goto.

## 3. Replay only proved consumed linear tails

Sibling branches can converge through a short basic-block tail that was already
rendered while structuring the first sibling. A goto from the second sibling into
the first sibling's scope is illegal C# even though the CFG edge is real.

`_replay_consumed_linear_to_stop` duplicates that tail at the current site only
when the complete path is proved in advance: every block is already consumed,
straight-line, single-successor, inside the current loop when applicable, free of
entry/pad/SEH boundaries, acyclic, and ends exactly at the caller's current
stop/join. It emits nothing on failed proof. Conditional paths, cycles, invalid
exits, and phi/SEH ambiguity remain explicit rather than guessed.

This repair is responsible for most of the corpus-wide scope improvement. Of
1,615 methods whose structural audit changed, 1,532 have fewer into-block gotos
and 83 have more. The net is −5,574 sites. The increases are not hidden: 78 of
those 83 methods also recover additional lines, often because the old loop
structurer truncated a path; the largest and all five negative-line-delta cases
were inspected. They still count as open C# blockers, not as solved output.

## 4. Protect source fidelity and release gates

The uploaded follow-up had converted `il2csharp.py` from its documented BOM/CRLF
format to LF. Review 80 restores the UTF-8 BOM and CRLF in `il2csharp.py`, keeps
`decompiler.py` CRLF, and adds a regression test so future whole-file rewrites
fail immediately. The two functional source files compile with Python 3.13.

New tests cover header/refill execution order, both-in-loop header successors,
shared-entry gate acceptance and phi-state rejection, atomic linear-tail replay,
direct-loop memory operands versus indirect dispatch, five real native methods,
and the source-format contract. The compiled smoke covers the real loop emitter,
array identity, GC-store twins, shared sret receiver, scalar roots, and an emitted
unsafe project. It does **not** compile `final_out/`.

## Regression and output review

- The original Review 77 and Review 79 snapshot files remain unchanged. Review 80
  keeps the same 64 MethodDefs; **59 bodies are byte-identical**. MIs 11974,
  32833, 32837, 39789, and 80548 change. MI 32837 now keeps its loop inside the
  native protected span before `finally`; MI 39789 is the reviewed proved-tail
  replay. Native instructions and complete body diffs were reviewed before
  `goldens_review80.json` was created after all full gates.
- The clean rebuild has the same file inventory as the supplied complete output:
  no added or removed generated files. **3,466 C# files** changed;
  selected corrected methods were read again from the rebuilt tree.
- Direct sweep line count rises 2,056,123 → 2,205,134 (+149,011) because loop
  headers now execute inside their loops and proved shared tails are duplicated
  at legal lexical sites. This is output-size data, not a performance claim.
- Structural audits remain clean for brace underflow/unclosed braces, dangling
  gotos, and empty call arguments. The remaining 8,067 into-block gotos in 2,047
  methods are explicitly retained as the next compilation-readiness target.

Evidence: `validation_reports/review80/README.md`, `summary.json`, exact source
and focused-method diffs, complete sweep/parse/output comparisons, per-method
manifests, compiler-smoke sources/logs, and final release-copy verification.
Historical Review 77–79 documents and evidence remain preserved and labeled.

## Reproduce

See `REPLACEMENT.md` for Windows setup and direct-overwrite instructions.

```bash
python -m pip install -r requirements-dev.txt
PYTHONHASHSEED=0 python -m pytest -m "not game"
PYTHONHASHSEED=0 python il2csharp.py testgame --strict -o rebuilt_out
python tools/validate_corpus.py parse rebuilt_out --report work/rebuilt_parse.json
PYTHONHASHSEED=0 python tools/validate_corpus.py sweep --metadata testgame/ShiftAtMidnight_Data/il2cpp_data/Metadata/global-metadata.dat --binary testgame/GameAssembly.dll --report work/rebuilt_sweep.json
python tools/csharp_smoke.py --out work/csharp-smoke --dotnet dotnet
python tools/verify_release.py
```

Set `IL2CSHARP_METADATA` and `IL2CSHARP_BINARY` to the supplied fixture paths,
and `PYTHONHASHSEED=0`, before running all 265 tests. The compiler smoke requires
an installed .NET 8 SDK; the Python tests do not. No game executable is launched.
