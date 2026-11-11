# Construct mapping and internals

Reference material moved out of the root README: what native constructs
recover as what C#, the implementation notes behind them, and the detailed
validation and limitation records. Start at [`../README.md`](../README.md).

## What gets recovered

What gets resolved inside bodies:

| Native construct                  | Recovered as                                    |
|-----------------------------------|-------------------------------------------------|
| direct/indirect calls             | `Type.Method(args)` — real names from metadata, args trimmed to the real signature, instance-style `recv.Method(...)` |
| generic shared methods            | `List<StructMultiKey<object,object>>.Add(...)` via method specs + generic instances |
| ambiguous shared-body returns     | retains the honest `sub_<va>/*shared body, N candidates*/` callee while using a return type only when every owner proves the same closed type and supported ABI; restores `void` effects, direct `bool` conditions, XMM0 scalar results, and observed sret-buffer assignments |
| instance/static field access      | `this.health`, `this._forward` — offsets mapped through the *whole inheritance chain* |
| field declarations                | visibility, `static`, `readonly` and `const` come from the field's own CLI `FieldAttributes` (the low 16 bits of its `Il2CppType` word), not an offset-threshold/name-shape guess — 7,085 fields tree-wide were misclassified under the old heuristic (real statics printed as instance fields exactly at the `< 0x10` threshold, instance fields on generic type definitions — which have no per-definition offset table — printed `static`, 14 unparsed RVA-data blobs printed `const`); the same fix applies to type declarations (`TypeAttributes` visibility is a *different* bit table than member visibility, and nested `NestedPublic`/`NestedPrivate` types were reading the wrong one entirely) |
| metadata usage slots (v27.1+)     | `typeof(X)`, string **literals** (`"save.data"`), static-field refs, method refs |
| klass-structure derefs            | the *indirect* static pattern resolves through the class layout: `[typeof(X)+0xb8]` → `typeof(X).__static_fields` → `[blob+off]` → `typeof(X).staticName` (`typeof(<>c).<>9__15_0`, `typeof(AstarPath).active`); static-blob *addresses* do too: `typeof(X).__static_fields + 0x2c` folds to `typeof(X).field` through the decoded field-offset map; init-guard flags render `typeof(X).initialized`; vtable slot reads render `typeof(X).vtable[n]` |
| object/array allocation helpers   | `new Player()`, `new bool[16]`                   |
| GC write barriers                 | `this.field = value;`; a barrier whose target is an address composite rather than a field re-reads as the WHOLE write (`(v + 2 << 4) + t` → `*((v + 2 << 4) + t) = 0;`, never a deref of the first term only) — including when the barrier is the very last thing a void method does, compiled as a tail `jmp` straight into the barrier helper rather than a `call`+`ret` pair (5,797 sites tree-wide rendered the raw `il2cpp_codegen_write_barrier(...)` call unconverted before this was handled) |
| `.ctor` chains                    | `new T(args)` folding, `base..ctor()`            |
| constructor rendering             | `.ctor`/`.cctor` emit as `public ClassName()` / `static ClassName()` with `: base(...)` / `: this(...)` initializers promoted out of the body (implicit for object/valuetype parents) |
| C# type names                     | `System.Int32` → `int`, `System.String` → `string`, … (exact full-name match, so game types like `System.Int32Enum` survive), applied inside generic arguments and array suffixes; reflection-style nested names `Outer+Inner`/`Outer/Inner` render `Outer.Inner` |
| using directives                  | each file opens with the sorted, de-duplicated namespaces it actually references (fields, signatures, bases, bodies), validated against the metadata's real namespace set |
| explicit local declarations       | no `var`: every local declares its tracked type (`int num1 = 0;`, `List<object> list1 = …;` with arity markers stripped), `object` when untracked |
| memory stores                     | `this.num = value;`, `arr[i] = value;`, and read-modify-write forms (`add [this+0x20],11` → `this.num = this.num + 11;`) |
| indexed addressing                | `lea r,[b+i*s+d]` composes real text instead of a placeholder: the compiler's multiply idiom `lea rcx,[rax+rax*2]` renders `i * 3` (typed int, folded like `imul`), array-element addressing folds the header back into the index (`[points + (i*3)*4 + 0x2c]` → `points[i * 3 + 3]`, the same bias fold jump tables use) or resolves a valuetype-element member, and an arr-base LEA yields `&arr[i]` |
| kill-on-write expression binding  | a store to `this.timeJumping` first binds every live expression that reads it: `var num1 = (deltaTime + this.timeJumping); this.timeJumping = num1; if (num1 <= …)` — without it the re-rendered text silently reads the *post*-store value |
| use-count expression binding | an expression rendered a second time is materialized to a temp at its definition: `var num1 = Random.Range(0, arr.Length); if (num1 != this.cur) …; this.curTrackIndex = num1;` — without it the call text prints at every use, reading like three separate calls |
| local type inference              | call arguments carry their parameter's metadata type (Win64 slots reconstructed exactly, sret/byref-aware), as do `return` statements and stores into typed fields; **instruction classes type what calls never mention**: GPR arithmetic/logic ⇒ int (SSE ⇒ float, `setcc` ⇒ bool), so counters, masks and sums rename `objN` → `num/flag/real`; a byref parameter types the local or stack slot whose address it receives, and a loop phi inherits its back-edge type over unknown entry edges; a hinted local renames `objN` → `num/flag/real` and a deref through it resolves to a member; a shared-generic-body call (`GetComponent<T>()` and friends) compiles down to its own unsubstituted signature, so its declared return type is the literal `T` — recovered instead from the concretely-typed field/local the result is immediately stored into (2,511 → 451 raw `T objN = …` sites tree-wide), and the call itself is re-annotated with the same recovered type (`this.GetComponent<Camera>()`) when it lost its own `<T>`; a static field read (`typeof(X).Instance` and any other static field) carries its real declared type the same way an instance field does, so a further deref off the result folds to a real member name (`Instance.someField`) instead of raw pointer arithmetic |
| virtual/interface dispatch        | vtable-slot resolution through metadata (`call [klass+0x138+16*slot]`), with the same arg trimming and accessor folding as direct calls — `this.text.text = this.num.ToString("N0")` |
| jump tables                       | `switch (x) { case 0: { … break; } }` with **inlined case bodies** — MSVC rel32 and abs64 table styles, shared targets folded into one section, the table's index bias folded back into the case labels |
| property accessors                | `get_X()` → `this.X`, `set_X(v)` → `this.X = v;`, statics → `Type.X` — and through *any* receiver expression (untyped `*(x + 0x40)` pointees, `&local` byrefs, explicit-interface dotted names): the accessor's metadata alone declares the receiver an instance of the declaring type; indexer accessors fold the same way (`recv.get_Item(k)` → `recv[k]`). Auto-property backing fields fold the same way: `<Y>k__BackingField` renders as `.Y` in reads, writes and splice arguments once the declaring type's matching backing-field declaration is in scope (`typeof(X).<Instance>k__BackingField` → `typeof(X).Instance`) — the residue (3,526 sites) is string-literal occurrences (reflection / `RuntimeHelpers.InitializeArray` data strings), raw type-header declarations, and generic/`<>c` path shapes |
| boolean tests                     | `if (!flag)`, `if (Input.GetMouseButton(0))` via return/field types |
| string concatenation              | `String.Concat(a, "/", b)` → `(a + "/" + b)`, or **interpolation** when literals mix with expressions: `String.Concat("Score: ", x.ToString("N0"))` → `$"Score: {x:N0}"` (braces doubled, `ToString(fmt)` folded into a format hole; shapes with nested quotes stay `+`-joined); `String.Format("{0} x {1}", a, b)` → `$"{a} x {b}"` with format/alignment suffixes kept and `ToString(fmt)` args folded |
| locals                            | phi-merged variables retain visible definitions; numeric/Boolean locals use `numN`/`realN`/`flagN`, concrete object-family locals use type-derived names (`gameObject1`, `list1`, `byteArray1`), and only genuinely untracked values keep `objN` |
| final object-local cleanup         | runs only after all semantic/structural passes; uses already emitted concrete types, checks body and metadata-parameter collisions, skips literals/comments, and refines `object` only for single-definition array/string/exact-`typeof` right-hand sides without ref/out/in/address escape |
| lazy class-init / metadata-init guards | swallowed (recognized structurally) — including the *inline cold twin* `cmp dword [klass+0xE4],0; je il2cpp_runtime_class_init; ret` (tail-jmp-reached, so invisible to any call census; named per-destination by `_is_class_init_twin`), pointer-form and reversed-operand guards, and the cold-call assignment `objN = il2cpp_runtime_class_init(X);` folding straight to `objN = X;` |
| noreturn throw raisers           | IL2CPP's exception raisers are named from the exception-class string their builder `lea`s (RIP-relative data): `raise_IndexOutOfRangeException()`, `raise_NullReferenceException()` — arity 0, replacing bare `sub_1804356a0`/`sub_1804356b0` (~7,151 sites); `_thunk_final` also follows `sub rsp,X; call T; int3` noreturn forwarders (the trailing `int3`/`ud2` is the load-bearing gate) |
| null-check throw stubs            | pruned — IL2CPP guards every member access with a branch to a throw helper; those paths are compiler scaffolding |
| counting loops                    | `for (int num1 = 0; num1 < arr.Length; num1++)` recovered from the header test + the back-edge counter copy |
| branch structure                  | `if`/`else` joined at the immediate postdominator, `while`/`do-while`, `break`; nonempty native loop headers replay inside every iteration, and proved shared-entry gates / consumed linear tails avoid inward jumps; unresolved CFG shapes retain explicit `goto` |
| proved scalar sqrt                | `SQRTSS`/`SQRTSD` and only structurally proved low-lane `SQRTPD` diamonds render `Math.Sqrt`; the unregistered domain helper is identified by its XMM0 double spill/reload, scalar root, and `"sqrt"` literal, including direct calls and tail jumps; unpaired packed SIMD remains conservative |
| scalar return ABI                | managed by-value `float`/`double` returns and resolved call results use XMM0; integer/object/pointer/generic and `ref float`/`ref double` forms use RAX; structured returns, flat fallback, and indirect tails share the same metadata/byref-bit rule |
| float/int constants               | literal values from the constant pool; **constant folding + normalisation** — negative immediates flip the operator (`x + -1` → `x - 1`), literal pairs evaluate, identities against 0/1 drop, and displacements sign-extend (`0xfffffffffffffff8` renders as `- 0x8`) |
| constant-pool types               | `movss` → `0.5f`, `movsd` → `1.25d`, packed 128-bit → `(float2)(0.5f, 0.6f)`, GPR int loads → decimal/hex literals. Float32 literals render shortest round-trip (`0.07f`, not `0.07000000029802322f`). **Non-finite floats have no literal form in C#** and render as the framework constants (`float.NaN`, `double.PositiveInfinity`, `float.NegativeInfinity` — all four are `const` fields, so they are legal in a `const double X = …;` initializer) |
| float-vector call args            | scalar const-pool loads carry their bytes for lane readers, so a GPR-carried `?` argument at a closed all-float vector slot materialises from proved lanes (`clamp(x, (float2)(0.0f, 0.0f), …)` for tails and resolved direct calls; integer-carried lanes such as index unpacking decline by construction since they carry no parts) |
| runtime class caches              | the il2cpp startup caches well-known `Il2CppClass*` pointers (Type, Int32, String, Object, …) in BSS cells filled by name; a byte-scan over the code sections recovers the fill sites, so reads render `typeof(System.Type)` and their init guards get swallowed |
| icall thunk caches                | BSS cells caching native function pointers resolved from signature strings (`"UnityEngine.Camera::get_main_Injected()"`) map to the managed method — the lazy-fill guard (`mov rax,[cell]; test; jne; lea,[sig]; call; mov [cell],rax`) is swallowed (full path, incl. resolved-call rendering, in the `icall thunk caches` row below) |
| native string constants           | `lea reg,[rel wstr]` (Steamworks/GDK interface names) renders `&"steam_api64"` |
| expression simplification         | precedence-aware parentheses: `(a + (b * c))` → `a + b * c`, grouping kept exactly where precedence requires it (`a - (b + c)` stays) |
| dead code                         | assignments to locals nothing reads are dropped (SSA-destruction copies, instruction observations); impure right sides (calls) stay because they execute for effect |
| ternary / small switches          | `if (c) { x = a; } else { x = b; }` → `x = c ? a : b;` (else-if chains fold to nested conditionals); a switch with ≤ 2 case labels renders as if/else-if |
| null-conditional                  | `if (x != null) { x.M(); }` → `x?.M();`, and a ternary with a `null` else-arm over `x != null` renders `x = x?.member;` |
| lock statements                   | the compiled `Monitor.Enter(obj, &taken)` + duplicated `if (taken != 0) Monitor.Exit(obj)` finally guards fold to `lock (obj) { … }` — each Enter owns the guards up to the next Enter, duplicated guards vanish, the last closes the block |
| using statements                  | a straight-line `T obj = new X(); … if (obj != null) { obj.Dispose(); }` (guard last, single assignment, no goto into the span) folds to `using (obj) { … }` |
| foreach                           | `for (int i = 0; i < arr.Length; i++)` whose counter only feeds element reads (`arr[i]`, `*(arr + i*size + hdr)`) renders `foreach (T e in arr)` with the element type from the array's tracked type |
| property/event bodies             | `get_X`/`set_X` accessor bodies move inside the property declaration (`public T X { get { … } }`); add_/remove_ accessors are represented by the event, not duplicated as methods |
| serialisation attributes          | `[Serializable]` from the type's metadata flag; `[SerializeField]` on non-public instance fields (real `FieldAttributes` visibility, not a name-casing guess) of MonoBehaviour/ScriptableObject descendants — whether Unity would actually serialize this *particular* field isn't knowable without the custom-attribute blob, so it stays a well-scoped guess, just a better-scoped one than name casing |
| try/catch/finally (SEH)           | the PE's `.pdata`/UNWIND_INFO is parsed and the **compressed `__CxxFrameHandler4` ehdata** decoded, including `dispIPtoStateMap` (read against the real `ehdata4_export.h` layout, not guessed): every try block's catch/finally funclets (pads) are recovered **exactly** as delta-chained RVAs, and a try whose protected range decodes to one contiguous IP span gets its **exact** open/close block from that span rather than a heuristic; a try with several disjoint spans (reached from more than one switch/goto entry point) falls back to the structural scan (wrapper-slot zeroing, `mov qword [rsp+K],0`, pad tail `mov rcx,[rsp+K]; test; jne rethrow`) — bridging its disjoint spans into one open/close pair was tried and reverted, since it can swallow a *sibling* try's span. **Multiple independent try regions in one method now render as independent clauses** (`self._seh_regions`, outer-to-inner ordered) instead of only the first; pads are seeded into the CFG (entered by the exception dispatcher, never by flow), lifted, and rendered as `try { … } finally { … }` / `catch { … }` — the compiled finally's normal-path duplicate is dropped by normalised statement match, the rethrow helper renders `throw;` and the raise helper `throw obj;`. Typed catches render `catch (Exception)`: the managed filter is the inlined IsInst fast path in the pad head (depth +0x130 / hierarchy +0xC8 against a usage-slot klass, both mismatch branches sharing the rethrow target) — no call may sit inside the filter window, which keeps the using/foreach dispose guards out. **Known gap (nearly closed):** a region's close point can land at a block that's also an `if`/`else` merge point, and the interaction renders `try { … } else { … }` (invalid C#, missing `catch`/`finally`) — the `try { } else { }` shape is now 0 sites tree-wide; one switch-reached +3-open artifact survives in CustomAttributeTypedArgument.ToString (see `docs/reference.md` §6, Known artifacts) — found by a per-*method* brace check rather than the per-file one below, which can mask it (a `try{}`/`else{}` pair's own brace counts are individually balanced, so a file-level total can still read 0) |
| shared-body call resolution       | MSVC folds byte-identical method bodies (6.3% of direct-method addresses tree-wide) and IL2CPP shares one body across generic instantiations (18% of generic addresses); printing whichever candidate registered first at that address is how a `Guid.cs` method ended up calling `ReadOnlySpan<Obi.BurstCollisionMaterial>`. A collision is resolved when the receiver's declaring type — walked up its **base chain**, not just matched exactly, since `this` in a `: base()` constructor is always the *derived* type — identifies exactly one candidate, or when a shared generic call's hidden instantiation argument (a decoded metadata usage slot, kind 6/MethodRef) matches one candidate's rendered name exactly. Otherwise the honest `sub_x/*shared body, N candidates*/` marker prints instead of a guess (16,916 sites tree-wide) — but even then, **every candidate names a call into the literal same compiled machine code**, so they consume the same argument registers no matter which metadata identity is the true one: the argument list is trimmed to the largest declared arity among all candidates, a provable bound rather than a guess, instead of keeping every GPR slot plus whatever stale float-register value happened to survive from earlier in the method as a bogus extra "argument" (a major source of undefined-temp spam — read-before-def dropped 6.8% tree-wide, in one fix, from this alone). Method-only twins that render identically collapse to the first row (same owner-qualified name, static/instance shape, exact parameter types, same return — unobservable pick, not an owner guess; constructors, generics and sret decline) |
| is-pattern                        | the inlined il2cpp IsInst fast path — `objType.typeHierarchyDepth < typeof(T).typeHierarchyDepth` and `objType.typeHierarchy[T.depth - 1] != typeof(T)` (klass members at **+0x130**/**+0xc8** in the v31 layout, named from the compiled check) — folds to `!(recv is T)` through the `klass = recv.getClass()` link |
| icall thunk caches                | BSS cells caching `resolve_icall` results are recovered **by fill-site scan** (`lea rcx,[rel sig]; call resolve; mov [rel CELL],rax`): every cell maps to its managed method (2,285/2,285, nested `A/B::m` signatures included), cell reads carry the MethodDef into `_call` so the site renders on the ordinary resolved-call path (arity trim, arg typing, `ref`, sret) instead of `f(...) /*indirect*/(...)`; the lazy-fill guard is swallowed, stray `resolve_icall` calls render the resolved method, and indirect tail calls whose value is the return render `return <call>;` |
| P/Invoke declarations (DllImport) | a `[DllImport]` method has no managed body: IL2CPP compiles it to a stub that caches the resolved function pointer in a RIP-relative cell (`mov rax,[cell]; test rax,rax; jne`) and passes a fully populated `PInvokeArguments` (module name + character length as UTF-16, entry point + length, calling convention, charset, parameter size, `isNoMangle`) to `il2cpp_codegen_resolve_pinvoke`, so the row prints the original `[System.Runtime.InteropServices.DllImport(...)] static extern ...;` instead of the marshalling plumbing (fixture: 1,944 of 1,951 flagged rows; `EntryPoint`/`CallingConvention`/`CharSet`/`ExactSpelling` print only when the binary recorded a value C# can spell, and `SetLastError` is not a struct field at all, so it is unrecoverable) |
| static inner-component reads      | static value-type storage in the blob is unboxed, so `[blob + fieldBase + inner]` resolves through the owning field's own value type (`typeof(Vector3).zeroVector.z`, `simpleVert.normal.y`); nested layouts recurse (UIElements `BindingId` = nested `PropertyPath` + `m_Path`, 0x98 bytes: `__static_N` 1,906 -> 273), and valuetype-underlying GENERICINST statics reconstruct their inflated layout from the open def + class args (`TMP_TextProcessingStack<MaterialReference>` = 0x58, proven by the cctor copy and the next static's offset: genericinst-vt 25 -> 0, honest tokens 62 -> 24) |
| delegate calls                    | `d.invoke_impl(d.method_code, <args>, d.method, d.invoke_impl)` folds to `d.Invoke(<args>)` with the receiver's concrete generic args substituted (626 -> 3, the residue genuinely untyped); cached-delegate backers fold to `T objA = CACHE ?? (CACHE = new T(a1, a2));` once the join-edge phi copies sit before the fork (fix 75/75b, in flight -- see `docs/archive/batches-c.md` §0as) |
| struct returns (sret)             | Win64/MSVC returns structs of size 1/2/4/8 by value and everything else through a hidden first-argument buffer (sizes from `typeDefinitionsSizes`, 16,916/16,916 exact); entry setup, arg hinting/positioning and the resolved-call arity trim all count that slot, so `get_position()`-style getters stop printing a bogus argument |
| jump tables                       | decode-window proof pass (70KB methods keep their tables) + one-`lea`-per-function reuse walk + sparse group-table case maps + no case renumbering on throw-stub pruning: switches 559 -> 758, `no_lea` never a real bucket; small (<=2-label) switches render as if/else, flat `==`-chains of 3+ arms synthesize `switch` (+40) |
| flag conditions / movzx masks     | `flags` stamps its writing instruction: JS/JNS after TEST and JP after SSE compares render `x < 0` / NaN checks (`unknown` conditions -51.5%), unmodelled writers degrade to `unknown` instead of naming stale text; `& 0xFF/*z*/` masks strip via a literal-aware paren walk with mandatory-delimiter checks (14,365 -> 0) |
| arrays/strings                    | `.Length`, element indexing                      |
| unresolved shared bodies          | 53,984 `sub_X(...)` references with no definition anywhere get one throwing `__SharedBodyStubs` class per assembly plus caller-proven `(T)` casts (declaration type, whole-condition `bool`, method return, unique-mapped assigns — 12,716 cast lines); nested-argument and value positions keep the honest object spelling. Where the stub address decodes, its first native instructions are listed as comments, so every unresolved target shows what the shared body does without naming an owner |
| shared forwarder bodies           | a shared `call; int3/ud2` body with exactly one proven target and caller==target return tuples renders `return Target(args)` (MSVC's own abort is the noreturn evidence; 63 Neon `/* nothing */` bodies); anything else keeps the honest drop |
| shared-tail returns               | `return <call>` resolves the callee when its closed return must equal the caller's exact metadata return (`HSteamPipe.op_Explicit(...)`, `Convert.ToInt64(this.m_value)`); value tails in exact-`void` callers split to call-then-return; 511 → 447 remaining honest tails |
| bare-`T` declarations             | a tracked hint that is one bare `VAR`/`MVAR` takes the same line's closed `new` spelling (`T x = new List<int>()`); `T x = new C(...)` never compiles under any binding, so no compiling method regresses |
| native-width raw stores           | `*(base + disp)` store lvalues spell the instruction's native width (`((uint*)p + 0x0)[0] = 4294967294;`, float lanes, indexed forms) instead of always-`byte*`; out-of-range literal stores 1,524 → 118 |
| ternary-condition casts           | a `sub_` call in a ternary condition proves `bool` there (arms keep the line's type); armless lines pass through, `} while (...)` proves `bool` like `if`/`while` |
| parity-jump NaN arms              | `ucomiss` + `jp` renders `IsNaN(a) \|\| IsNaN(b)` minus provably-false literal arms (`IsNaN(0f)` — no literal spelling denotes NaN; 665 dropped, `x != x` untouched) |
| full memory barriers              | the unregistered `lock or [rsp],0; ret` helper (reached directly or through ≤3 jmp hops, never a hardcoded address) renders `Thread.MemoryBarrier()` in value-free positions with side-effect-free args; scope-aware deadness rescues colliding scratch temps (1,279 sites); single-level `typeof(X).Member` static args join the trivial set |
| unanimous == / !=                 | an address whose every candidate is a static 2-parameter bool `op_Equality` (`Equals` twins allowed) or unanimously `op_Inequality` executes identical machine code, so `a == b` / `a != b` is behavior-exact with no owner attribution — each operand still proves the exact same operand type (literals, uniquely-declared temps, metadata member paths), so object-typed temps keep the stub instead of misbinding to `ReferenceEquals` |
| C# keyword escaping               | reserved words as identifiers escape with trailing underscore (`.namespace` → `.namespace_`, `string interface;` → `string interface_;`) via the existing `safe_ident`, declarations and uses agreeing exactly; the Roslyn probe's parse layer went 10,778 → 40 → 0 on this plus array brackets |
| fresh-array brackets              | `new T[N][i]` parses as an invalid rank specifier and `new T[N](idx)[0]` (single-argument ldelema shape) as an invalid call; wrapping the creation (`(new T[N])[i]`, `(new T[N])[idx]`) preserves allocation/size/index verbatim (709 sites) |
| legal type declarations           | interfaces misread as classes (ECMA mandates abstract+interface together) render `partial interface` with modifier-free members (DIM bodies kept); abstract+sealed utility classes (all member-static, census-proven) render `static partial class`; user delegates render `delegate R Name(params);` via Invoke; static-ness propagates to properties/events |
| nullary interface dispatch        | the interface-offset dispatcher is proved structurally, never by address (one `movzx` interface-count at +0x12E, one interface-table load at +0xB0, one `add 0x138` + one `shl 4` method-entry fold, an indirect tail jmp, a miss-path call); members that never read R9 render the managed call (`graph.CanUpdateAsync(obj)`), with the return closed through the interface instantiation and results materialized at the call instruction so `IDisposable` sites fold into `obj?.Dispose()` (55 Assembly-CSharp helper sites -> 0); R9-reading (parameterized) members decline here |
| parameterized interface dispatch  | the R9-forwarding twin renders one-argument managed calls under a first-touch rule (a read proves the caller passed R9, a write manufactures it) with lazy per-member arity proof: single GPR-class parameters resolve, zero-parameter targets drop the spray (more `?.Dispose()` folds), and multi-parameter targets, untyped R9, byref first parameters and single-field-struct returns keep the marker (542 sites -> managed calls) |
| IsInst `as` (typeof klass)        | the IsInst helper is proved structurally, never by address (klass-in-RDX/object-in-RCX prologue with null check, `Class::IsAssignableFrom` call, exactly one indirect `call [rax+10h]`, the System.Object short-circuit, return; thunk and body both land); a literal `typeof(T)` klass argument renders `obj as T` with the exact hardware semantics (9 Assembly-CSharp calls); opaque klass expressions keep the marker |
| IsInst `as` (element klass)       | `[arrklass+0x40]` is `Il2CppClass.element_class`, so `sub_x(obj, elemclass(arr))` renders `obj as E` when the array is statically `E[]` with a closed nameable reference element AND a same-method newarr proves the runtime klass is exactly `E[]` (array covariance lets params/fields/statics/`as`-refinements hold a `D[]`, so only allocations prove); merges compose per-path proofs and dry unanimous merges carry the proof through loop back-edges (5,884 -> 4,666 sites, -1,218; the rest, plus generic-instance/nested-array elements, keep the marker) |
| Interlocked.CompareExchange       | the `lock cmpxchg [rcx],rdx` helper (comparand staged in RAX from R8, `cmovne` keeping the observed value, the barrier call) renders `System.Threading.Interlocked.CompareExchange(ref loc, value, comparand)` with the value argument's type (21 Assembly-CSharp sites -> 0) |
| out-of-line class-init            | the 56-byte class-init helper (`Class::Init` call, `[klass+0xD8]` fast-path compare, int3 tail) is named `il2cpp_runtime_class_init`, routing sites through the existing bookkeeping which drops the call and propagates the klass value (3 Assembly-CSharp sites, 861 tree-wide) |
| interface resolve helper          | the 137-byte interface slow-path resolve body (callers inline the fast loop and land here on miss) is named `il2cpp_interface_get_method(obj, iface, slot)` with arity 3, dropping the sprayed 4th argument; the return stays the native method-entry pair pointer (26 Assembly-CSharp calls, 2,446 tree-wide) |
| unanimous conversions             | a shared address whose every candidate is the same static one-parameter `op_Implicit`/`op_Explicit` with distinct returns executes identical machine code, so a caller-proven `(T)` cast naming exactly one return resolves it: `T.op_Implicit(float-arg)` (5 Angle/StyleFloat sites; bare-object/double/multi-arg/generic shapes keep the marker) |
| bounds-checked element address    | the `cmp edx,[rcx+0x18]; jae fail` helpers over the SZARRAY layout (`RCX+0x20+index*stride`, stride extracted not assumed) are named `il2cpp_array_addr(arr, idx)` with arity 2, trimming spray residues (764 TextMeshPro/TextCore sites; the stride rides along for the `&arr[i]` follow-up) |

## How it works (original implementation)

1. **Metadata frontend** — parses all tables of `global-metadata.dat`
   (types, methods, fields, params, properties, generics, default values,
   string literals…).
2. **Binary frontend** — parses PE/ELF, locates `Il2CppCodeRegistration` /
   `Il2CppMetadataRegistration` by structural validation (codegen-module
   anchor + field-offset table cross-checks), parses per-assembly
   `Il2CppCodeGenModule`s, generic method tables, field offsets and vtables.
3. **Method addressing** — every method token → native address
   (`module.methodPointers[rid-1]`, plus adjustor thunks and shared-generic
   instantiations).
4. **Usage-slot decoding** — v27.1+ lazy metadata handles
   (`(kind << 29) | (index << 1) | 1`) are decoded directly from the binary’s
   data slots, recovering typeof/string/method/field references statically.
5. **Decompiler** — recursive-descent decode (the method's real extent, not a
   linear prefix), CFG construction, jump-table pre-wiring, non-returning-path
   pruning, dominator/postdominator analysis, natural-loop detection, two-pass
   symbolic execution with phi-merges (types carried through merges), SSA
   destruction with phi coalescing, structural if/else/while/do-while/switch
   recovery, `for` sugaring, switch-to-if, constant folding, ternary
   detection, dead-local elimination, property-accessor and boolean
   rendering, typed local renaming — on top of the iced-x86 instruction
   semantics with typed expression propagation, il2cpp idiom recognition and
   pattern-calibrated runtime-helper identification. Methods whose CFGs are
   too large fall back to linear lifting automatically.

Method bodies are produced by a built-in **structured decompiler**: the native
code is disassembled into a control-flow graph, executed symbolically per basic
block with phi-style state merging at joins, then structured into real
`if`/`else`, `for`, `while`, `do-while`, `switch` and `break` control flow:

```csharp
private void FixedUpdate()
{
    num1 = this.ambientTracks;
    for (int num2 = 0; num2 < num1.Length; num2++)
    {
        if (num2 == this.curTrackIndex)
        {
            num3 = num4;
        }
        else
        {
            num3 = num5;
        }
        this.ambientTracks[num2].volume = num3;
        num1 = this.ambientTracks;
    }
}
```

Not every construct survives structuring perfectly: locals whose type never
propagates stay `objN`, occasional `*(ptr + 0x18)` accesses remain, and a
single store into a genuinely unrenderable indexed home keeps the honest
`?addr` elision; goto into a nested block
— the merge-block-inlined-into-one-arm shape — is eliminated where the
hoist is provably sound (batch 15: 56,657 → 21,322 sites); the residue is
state machines, switch-section arms, and other shapes whose fall-through
paths would change behavior (see `work/lib/classify_into2.py`, SOUND = 0),
rendered as `goto L_<va>` with a label, plus a few methods that fall back
to linear lifting. Every method keeps its `// RVA/VA` address so you can
cross-check in a debugger or Ghidra.

### Things worth knowing about the internals

* **`Il2CppClass` offsets are per-Unity-generation constants** (`KLASS_STATIC_FIELDS`,
  `KLASS_INITIALIZED`, `KLASS_VTABLE` in `il2cpp/runtime/types.py` + `il2cpp/x64.py`). The vtable is
  the trailing `VirtualInvokeData[]` at **0x138** on Unity 6000.0 / v31 — a
  different field from `static_fields` at 0xB8. Conflating them silently shifts
  every virtual call by 8 slots, which resolves to a real but wrong method name.
* **Memory destinations must be dispatched before the register-move handlers.**
  Those key off `op0_register`, which is `NONE` for a memory destination, so they
  will swallow the store and write a bogus register instead (`il2cpp/lifter/insn.py`).

* **`ins.memory_size` is iced's MemorySize *enum*, not bytes.** UINT32=3,
  UINT64=5, FLOAT32=29, FLOAT64=30, PACKED128_FLOAT32=74 — comparing it
  against byte counts (`in (4, 8)`) matches nothing. The constant-pool
  render sat dead behind exactly that comparison for an unknown stretch of
  time, and every pool constant rendered `data_NNN` (`il2cpp/lifter/insn.py`).
* **BSS metadata caches are recovered from their fill sites, not their
  bytes** — the cells live in the virtual tail of .data (no file image), so
  `il2cpp/runtime/registration.py:scan_runtime_class_cache` byte-scans the code sections for
  `mov [rip+CELL], rax` stores and reads the name from the nearest
  preceding `lea` whose target resolves to a typedef; the shared
  names-table lea (`"System\0Void\0…"`) fails resolution and is skipped
  naturally. `decode_slot` serves the map only when the slot qword is
  unreadable, so readable usage slots are untouched.
* **The class-init cold twin is invisible to any call census.** MSVC emits
  `cmp dword [rcx+0E4h],0; je <warm export>; ret` (Unity 6000.0 / v31 klass
  offset) that is reached almost exclusively by **tail jumps**, never by a
  `call` — the call-site census counts 175 rendered uses, the tail-jump
  census 2,539. `_is_class_init_twin` (`il2cpp/lifter/calls.py`) therefore names it lazily inside
  `_call_name` (per destination, memoized), and the recognition must use
  iced's real immediate kind: `cmp dword [mem],0` disassembles with
  `IMMEDIATE8TO32` (=12), not `IMMEDIATE8`, so an `IMMEDIATE8` pattern match
  silently misses every one of them. Class-attr constants referenced inside
  `_is_class_init_twin` also need an explicit `self.` — inside a method
  body a bare name hits module globals and `NameError`s instead.
* **The backing-field / static-address folds are text-level and
  quote-aware.** `_member_fold` (`il2cpp/dec/textpass.py`) folds `<Y>k__BackingField` tokens to `.Y`
  (matching the declaring type's own declaration, base-chain aware) and
  `typeof(X).__static_fields + N` addresses to `typeof(X).field` (via the
  decoded `static_off_names` offset map) in every non-string chunk of a
  statement — line text is split on string/char literals first, so
  reflection strings like `"<Instance>k__BackingField"` stay honest data
  (that's why ~3.5k sites survive, not a fold gap).
* **There is exactly one live `[base+disp]` folder: `_field_expr` (`il2cpp/lifter/insn.py`).** A second
  klass-aware folder (`mem_expr`) sat next to it with **zero callers** for an
  unknown stretch of time — every deref went through `_field_expr`, which
  lacked the klass-layout branches, so the *indirect* static pattern
  (`[typeof(X)+0xb8]` → blob → `[blob+off]`) rendered 49k raw `*(typeof(X) +
  0xNN)` derefs tree-wide while its resolution code existed but never ran.
  Its branches (klass layout, static-fields blob, vtable reads, typed stack
  slots) now live at the top of `_field_expr`; the dead copy is deleted. A
  second hazard that removal fixed: klass bases used to fall through to the
  instance-field chain, where an unrelated static's *blob* offset could
  coincide with the klass-struct offset being read — `[klass+0x130]` rendered
  as a wrongly-named field. Klass-kind bases now never consult the field
  chain; unmapped klass offsets stay honest raw derefs.
* **An indexed LEA must compose text, never surrender to a placeholder.**
  `lea rcx,[rax+rax*2]` (base register == index register) is the compiler's
  multiply-by-3 idiom — pure integer math that must render exactly as
  `imul` would (`i * 3`, typed int, eligible for folding and type hints);
  rendering it as an opaque pointer token poisons every consumer, and one
  such token re-renders at each of its uses (`il2cpp/lifter/insn.py`). A distinct base+index composes
  `(base + i*s [+ disp])` as ptr-kind (or int-kind when the base is
  integer-flavoured). `?addr` survives only for a genuinely untracked base.
* **Array-element addressing folds the header back into the index (`il2cpp/lifter/insn.py`).**
  `[arr + idx*S + D]` with `(D-0x20) % S == 0` renders `arr[idx + (D-0x20)/S]`
  — correct because multidim indexing multiplies the row stride into the
  index *first*, so the displacement lands on an element boundary (the same
  bias fold jump tables use). Ambiguity at a zero remainder is settled by
  access size: a load narrower than the stride (`movss` into a 12-byte
  element) is a *member* access, resolved through the element type's field
  chain — whose offsets carry the 0x10 object header, so the element-relative
  offset `k` looks up `k + 0x10`.
* **Postdominators decide where branches join (`il2cpp/dec/build.py`).** `_ipdom` must return the
   *nearest* join; returning a farther one makes the then-branch swallow the
   shared tail, which then only reappears as a `goto`.
* **A merge block inlined into one arm is hoisted back out — the shared-tail
   hoist.** When `_seq` inlines a diamond's merge block into one arm, the
   other arm is left jumping into it: `if (!flag1) { L: obj14 = obj1; } else
   { Exit; goto L; }` — a `goto` into a nested block, which is invalid C#.
   `_hoist_shared_tails` (`il2cpp/dec/flow.py`, in `_structure` after the second
   `_resolve_labels`) moves the label's tail out past the whole construct
   and deletes the goto (`if (flag1) { Exit; } obj14 = obj1;`). It fires
   only when **every** into-goto falls through to the hoist point with
   nothing executing in between — no non-blank statement after the goto at
   any crossed level, no loop/switch/SEH level crossed — and when the
   sibling-arm funnel rule holds: every `else` arm must end in flow-break
   (return/goto/break/continue/throw) or its fall-through paths would
   execute a hoisted tail they never executed before (MainMenu.GetErrorKey's
   trailing-switch arm is the canonical UNSOUND shape — it stays an honest
   illegal goto; the blanket switch-level rejection in `_falls_to` is what
   keeps it that way). A nested label inside the tail also blocks the hoist
   (the state-machine class). One hoist per fixpoint round, capped at 200;
   the label arm, when emptied, collapses into the sibling arm
   (`_collapse_arm`). After batch 15: `into_block` sites 56,657 → 21,322,
   and the remaining ones decompose into provably-blocked classes (the
   `work/lib/classify_into2.py` census, per-label, counts SOUND = 0).
* **GPR arithmetic writes the flags it must (`il2cpp/lifter/insn.py`).** Only CMP/TEST (and SSE
  compares) used to set `L.flags`; a `jcc` after `sub rsi,1` (loop
  counter) therefore read the *stale* flags of an earlier `test`/`cmp`
  and the loop condition rendered against the wrong variable
  (BitVector32's `while (num1 != null)` testing the data word instead of
  the counter — batch 13). ADD/SUB/AND/OR/XOR/SHL/SHR/SAR/INC/DEC — and
  the `xor/sub/and/or reg,reg` self-folds — now set
  `flags = (result, 0)`; IMUL is deliberately excluded (its ZF/SF are
  undefined). The `0 == 0` renders that survive are faithful: the branch
  really does sit right after an xor-zeroing.
* **A self-looping header IS a loop body (`il2cpp/dec/flow.py`).** `_emit_loop`: when a loop's
  header block is also its own body (back-edge straight to itself —
  MSVC's count-down loops), `start` resolves to None and the body walk
  is skipped; the loop's real work then lives only in the `(hdr, hdr)`
  phi copies (`v62 = v62 - 1;`), which must be emitted via
  `self._edge(hdr, hdr, out)` or the loop renders empty (`while (c) { }`
  with the body's statements gone).
* **Non-returning paths must be pruned before analysis (`il2cpp/dec/build.py`).** A loop whose exit
  branch leads to a throw stub has no path to a `ret`, so its postdominator set
  never converges and the loop cannot be structured.
* **A store invalidates the text of every expression that reads the stored
  location (kill-on-write, `il2cpp/lifter/state.py` + `il2cpp/dec/dataflow.py`).** Registers — and the captured comparison operands
  in `flags` — hold *text* that re-renders at each use; once `this.x = …` lands,
  that text would read the new value. `_kill_stale` materializes such
  expressions to a temp before the store (all store paths: `_write_mem`,
  `_rmw_mem`, write barrier, struct-return, property setter), and the
  decompiler does the same at merges for phi-copy writes (`phi_pre` lines on
  the in-edges). Two documented gaps remain, both pointer-aliasing rather than
  text problems: a **call** can mutate a field without any store being visible
  (killing every field-reading expression at every call would flood the output
  with temps), and two registers can hold the **same pointer under different
  phi names** (equal only on some paths), so a store through one leaves text
  written through the other stale. `tools/scan_stale.py` counts residual sites of
  the textual shape.
* **A second rendering binds an expression to a temp at its definition
  (use-count binding, `il2cpp/lifter/state.py`).** The register file is a dict subclass whose reads
  count renderings per *expression object* (two calls with identical text are
  two values; each binds on its own uses) and whose writes stamp the
  definition slot. On use #2 of a call/typeof/arithmetic text ≥ 16 chars (or
  a member chain ≥ 24), `_bind` declares `var tN = <text>;` at the definition,
  rewrites earlier renderings in that block **by content** (positional anchors
  go stale the moment a declaration shifts lines — and a mark at the
  definition slot otherwise rewrites the declaration itself into `var t =
  t;`), and renames the expression so every later rendering reads the temp.
  Renderings in blocks that precede the declaration keep the full text:
  rewriting them would use the temp before it exists. Register-register moves
  don't count (`mov rbx, rax` re-homes a value, it doesn't render it), and
  neither does the dry first pass — which therefore runs on a plain dict,
  because the counting dispatch on every read is a measurable share of total
  runtime.
* **Per-method state that names temps must be reset per method (`il2cpp/lifter/state.py` + `il2cpp/dec/` mixin `reset`)** — tokens
  (`v7`, `t5`) repeat in every method and differ between the two analysis
  passes, so `_var_types`/`_type_hints` leftovers type the next method's
  locals at random. (This was a live bug: the decompiler's `_var_types` was
  never reset, which silently mislabeled locals across the whole tree.)
* **Type hints are only as sound as the argument-slot mapping (`il2cpp/lifter/calls.py` + `il2cpp/dec/dataflow.py`).** The Win64
  assignment is reconstructed from the signature (integers/receiver fill
  RCX–R9, floats XMM0–3, in order; a valuetype return means RCX is a hidden
  sret buffer — including when that buffer is a register-held local rather
  than `&s_N`; a byref is pointer-class even when its pointee is float), and
  hinting skips stack params, unset slots and address-of expressions —
  though a byref's *pointee* types the local/slot whose `&` it receives.
  Hints flow *forward* only: a deref resolves to a member only when the
  typing call/store precedes it in execution order. Round two adds
  instruction-class evidence: GPR arithmetic/logic types its bare-token
  operands and unknown-typed results as int (pointer-flavoured operands
  excepted — their arithmetic is address math), SSE arithmetic as R4/R8 by
  mnemonic, `setcc` results as bool, and a GPR compare against a non-zero
  literal as int (zero may be a null test). Loop phis take the single type
  their preds agree on even when some preds are unknown. Two-pass hint
  seeding was rejected as unsound: v-names differ between the two analysis
  passes, so a pass-1 hint can key a different value's name.
* **Anything that names temps must iterate in a fixed order.** `vN`/`tN`
  numbering flows into output text, so iterating a `set` of strings (merge
  keys, `VOLATILE`) makes output differ between runs — the merge loops sort
  their keys and `VOLATILE` is a tuple for this reason.
* **The decompiler path never runs `Lifter.lift()`**, so per-method Lifter
  state (`vt_recv*`, `cur_va`, `flags`) is reset in `il2cpp/dec/build.py:fresh_regs()` instead —
  `_call` (`il2cpp/lifter/calls.py`) reads `vt_recv_slot` unconditionally and would crash otherwise
  (masked in production by the legacy-lift fallback, which hides the crash but
  silently emits a flat body).
* **Any exception in `Decompiler.lift_method` silently downgrades to the
  legacy linear lift** — and that still counts as `lifted`, never `failed`,
  in every stats line the tool prints. This is not hypothetical: a regex
  with 5 capturing groups being unpacked into 6 values
  (`_NULLTERN_RX`/`_null_ternary_sugar`) crashed silently on some null-ternary
  shapes and was live for an unknown stretch of time — measured impact
  ~0.51% of methods (extrapolates to ~590 tree-wide), each rendering with
  raw `s_N` slots, visible labels and no type inference instead of a real
  structured body, with zero visibility in the "0 failed" count. Fixed by
  making the decl-type prefix group capturing; a full-corpus sweep with the
  fix found only 2 remaining fallbacks, both an intentional `cfg too large`
  cap on one pathological method, not bugs. Worth re-running that sweep
  after any change to the post-processing pipeline: iterate every method,
  wrap `lift_method` in try/except, count — no file writes needed, so it's
   fast (`work/lib/sweep_audit.py` has the pattern).

## Validation

Gates at the r10 tree (historical; current suite and compile-gate
numbers are at the top of `docs/todo.md`): **1253 tests (1027 portable + 226 game)**;
a strict 11,183-file/114,458-body build with no failures or fallbacks; a
0-error syntax parse of every C# file; and a paired 116,178-method direct
sweep with 0 crashes and structural metrics unchanged (into_block
8,075/2,046, identical to r9). Exact reports: `validation_reports/
promotion_r10.json` (promotion proof, aggregate `b0c87509…b9fe`, 0
mismatches), `validation_reports/audit_batch3.json` (landing evidence),
and the older `review84`/`review123` sets plus `promotion_r9.json` for
history. At Review 84 the same strict build held with **358 tests**.

Two independent corpus gates, run against the built tree:

- **tree-sitter parse gate** (`work/lib/ts_gate.py`; the portable
  equivalent is `tools/validate_corpus.py parse`): parses every
  emitted `.cs` with the tree-sitter C# grammar and counts ERROR /
  MISSING nodes per line. Historical numbers (Review-77 source, Shift At
  Midnight): **0 bad files / 0 ERROR / 0 MISSING across 11,107
  files** -- the first fully clean parse landed at batch 53
  (`b63_out1`), when the CFG block cap 1500 -> 3000 let the two
  long-standing TextMeshPro cfg-too-large fallbacks lift structurally;
  held through batches 74 (and still 0/0/0 at `b76_out1`, `work/artifacts/ts_gate_b76_out1.txt`).
  Trajectory: 708/2,261/487 when the gate first ran, 302/427/210 at batch 18, 183/118/193 at batch 19, 16/15/2
  at batch 22, 2/2,206/4 at batch 52, 0/0/0 since batch 53 (see
  `docs/archive/batches-a.md`–`batches-e.md` for the batch-by-batch numbers). This is the gate that sees what brace
  counting can't: bare `do { }` without a `while` closer,
  `try { } else { }`, NUL bytes and `...` inside statements, missing
  call parens, `|`/`@`/`.` in identifiers, and unlexable literals
  (`inf.0d`, `nanf`). A clean gate only proves nothing is
  unparseable, never that nothing is wrong -- the golden snapshots,
  the sweep and reading real output carry the rest.
- **per-method structural sweep** (`work/lib/sweep_1a_audit.py`; the portable
  equivalent is `tools/validate_corpus.py sweep`): literal-aware
  brace balance, dangling gotos, goto-into-block, empty args, follower,
  crashes. Review-77 source: **crashes 0/116,178, brace 0,
  into_block 13,642 (2,997 methods)** under the new validator
  (13,518/2,979 under `sweep_1a_audit.py` -- different tool, not a
  regression; the funnel-blocked residue kept honest; batch 43's tail
  duplication recovered half of batch 42's un-hoists).
  Batch 75 source-only sweep (`work/sweep_b75.log`, fix 75 only):
  13,518/2,979, lines +71,345; internal detail is in `docs/archive/`.
  Golden snapshots (`work/lib/test_goldens.py`, 50 bodies): 50/50 at the
  gated `b73_out1` build (regenerated; fix-75's 8 phi-placement
  renumberings read, `docs/archive/batches-c.md` §0as); `tests/` holds the portable 64-snapshot
   suite (MethodDef-keyed) added in Review 77 (now 64 in `tests/goldens_review84.json`, 56 unchanged from Review 83
   at the Review 84 promotion; Reviews 85–89 regenerated with only name-only deltas;
   fix 97 regenerated with declaration-only deltas (24 snapshots, all bare→typed
   declarations); fix 97e regenerated with 0 body changes).

Both run offline over the output tree; no game binary, no rebuild.

A third, newer gate compiles the whole tree with Roslyn (`dotnet
build`, .NET 10 SDK, all assemblies as one project with the
per-assembly `__SharedBodyStubs` classes deduplicated probe-only):
it sees what the parse gate cannot — undeclared names, bad
conversions, illegal declarations. Method: count root breaks, not
error instances (one bad line cascades hundreds of follow-ons);
first-error-per-file histogram ranks the defect classes. Trajectory
on the parse layer: **10,778 error instances / 48 files → 40 / 2
(fix 111) → 0 (fix 112)**; full tree 87,224 / 5,461 → 68,528 /
4,097 (fix 113). What remains is ranked in `docs/todo.md` (missing
types, bodiless methods, `unsafe` modifiers, unimplemented members,
then the body layer). Two caveats this probe taught us: declaration
errors suppress method-body binding, so goto/definite-assignment
errors stay masked until declarations are fixed (an isolated
into-block `goto` is CS0159-hard-illegal — labels are block-scoped
for `goto`); and per-assembly `.csproj` files exist but carry no
cross-assembly references yet, so the probe sidesteps them with one
project.

## Not (yet) done

Ordered by how much they cost readability:

1. **The remaining `data_` population (~17k token-lines).** The
   icall-cell band is gone (`resolve_icall` sites render managed
   methods) and the image-base composites fold to one named table
   (`*(data_<va> + i*4)` — the il2cpp-section invoker/thunk tables).
   What's left: .text function-pointer leas (`&data_1800xxxx` —
   native/icall thunks), BSS init-guard cells whose fills match no
   known idiom, and readable .rdata tables.
2. **SEH, round four.** try/catch/finally lands (see the table), the
   compressed IP2State stream is decoded for exactly-one-span trys
   (most of them), and independent try regions in one method render as
   independent clauses instead of only the first. Still open: a
   region's close point occasionally lands on an `if`/`else` merge
   point and renders invalid `try { } else { }` (the `try { } else { }`
   shape is now 0 sites tree-wide; one switch-reached +3-open artifact
   survives in CustomAttributeTypedArgument.ToString — see `docs/reference.md` §6,
   Known artifacts); multi-span trys (reached from
   more than one switch/goto entry point) still use the structural
   open/close scan rather than exact data — recovering them needs the
   pad's own continuation address, not a heuristic; the catch variable
   is unnamed (the clause header types it; the body's uses render raw).
3. **Enumerator-based foreach** (needs state machines); the array-index
   shape and the `is`-pattern landed.
4. **Stack-frame model.** Spill slots render as `s_N` and get passed by address;
   proven homes render named (`&dictionary23`, never raw `&s_N`) and
   typed-slot member derefs already resolve (ported with the klass
   branches). A `mov r64,rsp`
   frame copy keeps the frame offset, so `[copy+N]` traffic names the same
   slot as `[rsp+M]` (RBP frames keep their own disp keys, byte-identically).
5. **Type inference, round three.** Stack params (5th+ integer) the Win64
   reconstruction skips; the `?addr` family (untracked *base* registers —
   the index is known, the pointer it scales isn't) is down to 2 elided
   stores in the promoted tree and renders none in fresh lifts, which also
   cleared the copy-idiom `mem[]` spills around them.
6. Attribute data blobs (`[Header]`, `[Tooltip]`, … — `[Serializable]` comes
   from the type flag and `[SerializeField]` from the field's real
   visibility, but the blob contents themselves — and so which specific
   non-public field Unity would actually serialize — are unparsed).
7. Klass offsets are calibrated for Unity 6000.0 / v31 only; other generations
   need their own constants.
8. Mach-O / 32-bit binaries.
9. **Runtime-helper residue.** Nine intrinsic families now render managed
   calls (nullary + parameterized interface dispatch, IsInst `as` for
   `typeof` and newarr-proven element klasses, `Interlocked`,
   class-init elision, interface resolve, unanimous conversions,
   bounds-checked element address). Open slices: bounds `&arr[i]`
   render, multi-parameter dispatch, untyped-R9 sites,
   single-field-struct returns, non-newarr klass provenance,
   generic-instance/nested-array elements, field-store identity. Live
   status and counts in `docs/todo.md`.

Deliberately not done: **LINQ inversion** (`for` → `arr.Sum()`), **nameof**
reconstruction, **tuple deconstruction** — each guesses at source that may
never have existed (a literal matching a symbol name is usually a tag, not a
nameof; a manual sum loop may never have been LINQ). A decompiler that
invents plausible source is worse than one that's honestly imperative. The
Cpp2IL-style x64→CIL→ILSpy round-trip stays a documented alternative, not a
next step: on optimized MSVC x64 the state machines and method boundaries
those patterns depend on are already destroyed, and the stack-exact CIL
intermediate it requires is where silent wrongness would live.

## Review 80 compiler smoke

`python tools/csharp_smoke.py --out work/csharp-smoke --dotnet dotnet` generates
small C# fragments from the real lifter, compiles and runs them, and builds an
actual emitter-generated unsafe project. Requires a .NET SDK, not the game.
It is deliberately separate from the tree-sitter gate and is not a build of
`final_out/`. The runtime smoke includes the real CFG loop emitter. It last ran
for Review 80; it was not rerun for Reviews 81–113 (a .NET 10 SDK is present
in this environment as of fix 111, but the smoke's compiled-pattern checks
cover different ground than the whole-tree Roslyn probe above, which is the
current compilation gate). See `docs/reviews/REVIEW84.md`, `docs/reviews/REVIEW87.md`,
and `docs/todo.md` for current validation and compilation blockers.
