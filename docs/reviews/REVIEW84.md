# Review 84 — constructor chains and single-identity object allocation

**Completed:** 2026-09-10  
**Scope:** object construction, constructor initializers, and inheritance identity  
**Authority:** `validation_reports/review84/summary.json`

Review 83 recovered return types for ambiguous shared native bodies, but object
construction was still one of the largest readability and correctness gaps.
IL2CPP commonly splits construction into `il2cpp_object_new(typeof(T))` followed
by a `.ctor` call, and MSVC folds thousands of empty constructors into the same
native address. The old lifter often rendered those facts as two different
objects:

```csharp
Widget widget1 = new Widget();
new Widget(name);
```

It also left real constructors as `this.ctor(...)` or as the huge
`sub_180506120/*shared body, 6469 candidates*/` family instead of a C#
`: base(...)` / `: this(...)` initializer.

Review 84 adds conservative allocation provenance and constructor-specific
metadata proof. It joins only the exact allocation and call that belong
together, recovers constructor initializers only in a proved constructor
context, and keeps ambiguous cases honest.

## Outcome

- Audited standalone constructor-allocation statements fell **13,292 → 0**.
  Their arguments now complete the original allocation declaration instead of
  constructing a second discarded object.
- Empty allocation declarations fell **21,624 → 13,254**
  (**-8,370 / -38.707%**).
- The dominant folded-constructor marker `sub_180506120` fell **2,958 → 160**
  (**-2,798 / -94.591%**) across the complete output.
- Legacy `this.ctor(...)` call text fell **2,186 → 45**
  (**-2,141 / -97.941%**).
- Real C# `: base(...)` initializers rose **5,960 → 9,530** and
  `: this(...)` initializers rose **0 → 325**.
- `object objN` declarations fell **113,155 → 112,423** (**-732**) as a
  secondary benefit of keeping typed allocation identity.
- Generated C# shrank by **20,568 lines** while preserving the exact
  **11,200-file** inventory. There are 4,428 changed C# files and no additions
  or removals.
- The strict all-assembly build recovered all **115,658 bodies** with 0 failed
  bodies, 0 structured fallbacks, and 0 type-emission failures.
- All **11,107** generated C# files pass the tree-sitter syntax gate with 0
  ERROR, MISSING, or recovery nodes.
- The direct **116,178-method** sweep has 0 crashes and 0 structural-metric
  changes from Review 83.
- A dedicated sweep lifted all **11,737 native constructors** with 0 crashes.
- **358 tests pass:** 260 portable, 64 frozen native snapshots, and 34 native
  semantic assertions.

The recovered game was not compiled or executed. These are static recovery and
syntax results, not a semantic-equivalence or ready-to-run claim.

## 1. Complete inheritance identity

Unity 6000 encodes the terminal parent edge for many classes as
`IL2CPP_TYPE_OBJECT` (`0x1c`) rather than a normal class TypeDef edge. The old
`base_chain_tds()` stopped before that edge even though its contract said the
chain continued through `System.Object`.

Review 84:

- maps an OBJECT type to the unique `System.Object` TypeDef;
- includes it in the base chain while rejecting missing or duplicate canonical
  Object definitions;
- stops malformed inheritance cycles without repeating a TypeDef;
- keeps `Il2Cpp` inheritance and field-chain caches per instance, so loading a
  second binary cannot reuse TypeDef-index results from the first one.

The broad pre-existing shared-call receiver heuristic deliberately excludes the
new Object tail for derived receivers. Constructor proof uses the complete
chain; unrelated shared-call resolution keeps its old specificity. This
isolation prevents `System.Object` candidates from stealing ordinary calls such
as `System.Type.op_Equality`.

## 2. Constructor proof is narrower than normal call resolution

A shared native address is treated as a parameterless constructor only when all
of the following are true:

1. the receiver is either the typed `this` of the constructor currently being
   lifted or the exact expression created by `il2cpp_object_new`;
2. the receiver is a closed reference type, not unknown, byref, or a value type;
3. the candidate owner is on the allowed inheritance chain;
4. the candidate is an instance `.ctor` with zero declared parameters and a
   `void` return;
5. exactly one concrete closed MethodDef matches;
6. generic candidates, unsupported candidate kinds, mismatched constructor
   ABIs, or multiple eligible constructors make the proof decline.

For `this`, same-type targets become `: this(args)` and ancestor targets become
`: base(args)`. The internal `this..ctor(...)` / `base..ctor(...)` pseudo form is
promoted by the existing emitter; **0 raw pseudo calls remain in final C#**.
Parameterized resolved constructors retain metadata-trimmed source arguments.

The proof is intentionally not “pick the most likely constructor.” Twelve native
constructors still contain the very large shared-address marker because more
than one eligible ancestor constructor maps there. Three complex generic or
scope constructors still contain legacy `this.ctor(...)`. Those 15 bodies are
retained in `constructor_sweep.json` rather than forced into unsupported C#.

## 3. One allocation, one identity

Every runtime object allocation now carries private `_alloc` provenance on its
`Expr`. That provenance survives the normal expression copy/bind path. When the
matching constructor arrives, Review 84 either:

- completes an unbound `new T()` directly as `new T(args)` and binds it once; or
- patches the one exact previously emitted declaration from `new T()` to
  `new T(args)`.

It never searches for a merely similar type name or patches multiple lines. If
there is no unique exact declaration, the fold declines and leaves the call
visible. Provenance is consumed after one successful completion, preventing a
second constructor from reusing it.

This fixes both simple discarded allocations and objects initialized through
aliases before their final store. For example, the recovered Outline feature
now keeps one `SolidMask` identity:

```csharp
SolidMask solidMask1 = new SolidMask();
solidMask1._scale = 50.0f;
solidMask1._velocity = 0;
this._solidMask = solidMask1;
```

A parameterized exception now becomes one expression instead of an empty object
plus a discarded second object:

```csharp
System.Exception exception1 = new System.InvalidOperationException(text1);
```

## 4. Representative constructor recovery

Trivial folded constructors recover the source initializer:

```csharp
public YieldInstruction() : base()
{
}
```

Same-type constructor chaining is distinguished from ancestor construction:

```csharp
public Random() : this(System.Random.GenerateSeed())
{
}
```

Static closure initialization keeps one allocation and one store:

```csharp
<>c obj1 = new <>c();
typeof(<>c).<>9 = obj1;
```

`System.Xml.Schema.BaseProcessor.AddToTable` now combines every
`XmlSchemaException` and `ValidationEventArgs` allocation with its exact
constructor arguments. `XsdBuilder.InitComplexType` removes the discarded
`new XmlSchemaComplexType(0)` because metadata proves that `0` was a hidden
runtime argument to the parameterless constructor, not a source argument.

The 64-case native snapshot set preserves the same MethodDef inventory as
Review 83: 56 bodies are unchanged and eight reviewed constructor/allocation
bodies change. Their complete diff is `snapshot_changes.diff`.

## 5. Validation

| Gate | Result |
|---|---:|
| Portable tests | 260 passed |
| Frozen native snapshots | 64 passed |
| Native semantic tests | 34 passed |
| Complete test suite | **358 passed** |
| Strict all-assembly build | 11,107 C# files; 115,658 bodies; 0 failures/fallbacks |
| Tree-sitter C# syntax | 11,107 files; 0 bad / 0 ERROR / 0 MISSING / 0 recovery |
| Direct structured sweep | 116,178 methods; 0 crashes |
| Sweep structural delta vs Review 83 | 0 |
| Constructor-only direct sweep | 11,737 constructors; 0 crashes |
| Output inventory | 11,200 before / 11,200 after; no add/remove |

The build and direct sweep used the same two assembly partitions as Review 83.
The build overlap is the substring-selected `Unity.InputSystem.dll`; all 345
overlapping files are byte-identical. The merged direct sweep contains every
Review 83 MethodDef exactly once. Its 14,688 changed hashes are a raw
before/after count across fresh partitions; no semantic attribution is inferred
from that number. The structural metrics are unchanged, including 8,067
into-block gotos across 2,047 methods.

A .NET SDK was unavailable, so the historical focused Review 80 compiled smoke
was not rerun and the complete generated tree was not compiled.

## Limits and next work

- 112,423 `object objN` declarations remain. The next high-value work is
  producer/stack-slot/copy/store provenance, not broader type guessing.
- 13,254 empty allocation declarations remain. Some are legitimately
  parameterless; others need virtual/indirect target or alias proof.
- 160 `sub_180506120` call sites remain output-wide, including 12 conservative
  constructor declines with multiple eligible ancestor candidates.
- Three native constructors still contain legacy `this.ctor(...)`; their
  generic/receiver evidence is insufficient for this proof.
- Broader constructor compilation issues remain: undefined arguments, definite
  assignment, exception-region placement, project references, and identifier
  recovery.
- General cyclic allocation identity, packed SIMD/vector tracking, generic
  value-type sizing, source-level ref returns, broader virtual/indirect calls,
  ARM64 semantics, and independent fixtures remain open.

## Reproduce

With dependencies installed:

```text
PYTHONHASHSEED=0 python -m pytest -q
```

The complete offline gates use `tools/validate_corpus.py`:

```text
PYTHONHASHSEED=0 python tools/validate_corpus.py sweep \
  --metadata "$IL2CSHARP_METADATA" --binary "$IL2CSHARP_BINARY" \
  --report validation_reports/review84/recheck_sweep.json

python tools/validate_corpus.py parse final_out \
  --report validation_reports/review84/recheck_parse.json
```

Use `--strict` and a fresh output directory for emission. Do not execute the
supplied binary; all release validation is static.
