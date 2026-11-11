# CLAUDE.md

## Current source and validation authority — r11 promoted tree

**r11 (2026-10-01):** `final_out/` was rebuilt from `main` `1cafd3f` (twin
relax + box-only hetero guard): strict build 11,183 files / 114,458 bodies,
0 failures; brace 0; parse 0/0/0; 2,838 files changed vs r10; 11,276 files,
aggregate `735f2e9a…1707f`, 0 mismatches (`promotion_r11.json`). The r10 notes
below are history.

The working source contains fixes 114 (method dispatch flags, generic
constructor names), 115 (unsafe on pointer-signature methods/ctors), 116
(unsafe on pointer-typed fields/properties; CS0214 fully zero), 117
(generic `_N` reference spellings matching declarations, incl. explicit
interface qualifiers; CS0115 fully zero), 118 (tuple-based explicit
qualifiers + structure-aware qualifier sanitize; CS9334 fully zero), 119
(namespace-qualified spellings feeding `using` generation), 120 (nested
owner paths via `nested_types`), 121 (mirror-nested own-suffix +
owner-first distribution), 122 (receiver-proven stub temps take the
unique owner's type with a caller-proven cast), and 123
(collision-aware using-strip with full-depth generic arguments; CS0246
fully zero), and 124 (wide raw stores byte-address their displacement —
`((T*)((byte*)E + N))[0]`, where the pre-fix spelling scaled N by
sizeof(T)), plus three unnumbered follow-ups: shortest round-trip float32
literals with fixed-point tie-break, entry stack-parameter names/types
surviving the pass wipe with slot reloads restoring the recorded kind, and
exact runtime type on klass-equality cmov select — and, since, the
recovery rounds: RSP-copy frame homes (RBP quarantine), array receivers
via System.Array, rename barrier + param exclusion, interface dispatch
naming, boxed-bool null fold, SIMD consumer-side recovery (tails and
direct calls), each decline-by-default with portable + game pins; plus
documented disproofs (hinted receivers, ?addr tightening,
receiver-driven generics). 1465 tests (1223 portable + 242 game): 1463
pass, and the two failures are this sandbox's named-pipe denial for
`tests/test_game_parallel_build.py` (`ProcessPoolExecutor` cannot create
its pipe; proven by a three-line repro, see
`validation_reports/review124_environment.json`), not fix 124. Rebuilt
and gated twice after fix 123 — r4a then r4c,
both 114,458 bodies / 0 failed / 0 fallbacks, brace 0, parse 0/0/0 —
and promoted 2026-09-23: `final_out/` holds r4c (11,183 `.cs` files /
11,276 paths, aggregate `c0ee1b78…1236`). Promotions since (r4d, r5, r7, r8
Assembly-CSharp) were superseded by **r9, 2026-09-26** (aggregate
`73f4426d…c8821`), and r9 by **r10, 2026-09-28**: the audit-batch-3 tree
built strict (11,183 type files / 114,458 bodies / 0 failed / 0
structured fallbacks / 0 type-emission failures in 1,465,953 ms under
external CPU contention), brace 0 unbalanced, parse 0/0/0/0, paired
sweep 0 crashes with `into_block` 8,075/2,046 unchanged, promoted by
in-place move with a per-file sha256 proof (11,276 files, aggregate
`b0c87509…b9fe`, 0 mismatches / 0 stale; `promotion_r10.json`).
`final_out/` now holds r10 everywhere, so r9 and earlier are history; see
`docs/todo.md` Current work and `validation_reports/promotion_r*.json`. The `bckups/` copies of prior
promoted trees were deleted 2026-09-19 per user call — GitHub is now the
history authority; any prior tree rebuilds from git history. See `docs/todo.md` for exact evidence and the
remaining compiler backlog.

Read `docs/reviews/REVIEW84.md`–`REVIEW87.md`, `docs/todo.md`'s Current work section, and
`docs/archive/reviews-log.md` section 0bf first. `final_out/` is the complete strict-built
tree (r10, all 91 images, 2026-09-28; every earlier aggregate below is history),
not the Review 84 file set alone, b42/b76, or a partial candidate. Historical paragraphs below retain
the reasoning behind older changes; their old "current" labels are not release authority.
`validation_reports/review84/summary.json` (baseline) plus `validation_reports/followups_sweep.json`,
`followups_parse.json`, `followups_promotion_verification.json` (fix-123 era, frozen)
and `validation_reports/promotion_r4a.json` + `promotion_r4c.json`
+ `promotion_r4d.json` + `promotion_r5.json` + `promotion_r7.json` +
`promotion_r8.json` (r8 scoped to Assembly-CSharp)
are authoritative for the promoted tree. Fix-114 evidence lives in
`validation_reports/review114_*`; fix-115 gates, probe, and promotion record
in `validation_reports/review115_*`; fix-116 in `validation_reports/review116_*`;
fix-117 in `validation_reports/review117_*`;
fix-118 in `validation_reports/review118_*`;
fix-119 in `validation_reports/review119_*`;
fix-120 in `validation_reports/review120_*`;
fix-121 in `validation_reports/review121_*`;
fix-122 in `validation_reports/review122_*`;
fix-123 in `validation_reports/review123_*`.

**Current invariants:**
- `base_chain_tds` maps IL2CPP_TYPE_OBJECT only through one unique
  `System.Object` TypeDef and stops cycles without repeating a TypeDef. The
  broad shared-receiver heuristic must use `_legacy_shared_receiver_chain` so a
  newly visible Object tail cannot steal unrelated derived-receiver calls.
- `_chain_cache` and `_bases_cache` are per `Il2Cpp` instance. TypeDef indices
  are binary-local; never restore class-level cache sharing across loaded
  fixtures or workspaces. The same rule covers every `td.index`-keyed map:
  `Decompiler._tdname_cache` (was the class attribute `_TDNAME_CACHE`),
  `Emitter._us_cache`, `Emitter._delegate_cache`, and
  `Emitter._delegate_viable_cache` are per instance, created lazily through
  `self.__dict__.setdefault` because ~80 tests build a `Lifter`/`Decompiler`/
  `Emitter` with `__new__` and never run `__init__`. A shared map does not
  crash — it hands a second binary the first binary's index, and
  `_static_field_name` then emits another type's field name. Never split one
  dict's key spaces either: the two delegate answers are separate dicts
  precisely because an `int` key can only fail to collide with a
  `('viable', int)` key by accident.
- The same rule covers the five runtime maps missed by audit batch 1:
  `_tn_cache`, `_slot_cache`, `_fo_cache`, `_sf_infl_cache`, and
  `_mod_ptr_cache` are per instance, created lazily through
  `self.__dict__.setdefault` (TypeDef/field indices and slot VAs are
  binary-local; a second fixture got the first binary's type names,
  field owners, slot annotations and pointer arrays with no marker).
  `cli.py` and `tools/corpus_common.py` free the module-pointer arrays
  through `getattr(il, '_mod_ptr_cache', {})`, never a bare attribute.
- `_shared_parameterless_ctor_target` is an exact constructor proof, not normal
  shared-call resolution. Require typed current-constructor `this` or exact
  fresh `_alloc` provenance, a reference-type inheritance match, zero declared
  parameters, instance/void ABI, and exactly one concrete closed MethodDef.
  Generic candidates, multiple eligible ancestors, unknown/byref/value-type
  receivers, and malformed candidates must decline.
- `_constructor_initializer_kind` may emit the internal `this..ctor` /
  `base..ctor` pseudo form only while lifting the matching nonstatic `.ctor`.
  Same-type targets mean `this`; ancestor targets mean `base`. The emitter owns
  promotion to the C# initializer and no raw pseudo call may remain in output.
- `_alloc` belongs to the exact `il2cpp_object_new` expression and must survive
  copies/binding until one constructor consumes it. Complete an unbound
  allocation directly or patch exactly one matching declaration. Never fold by
  type-name similarity, globally deduplicate `new`, or emit a second discarded
  `new T(args)` statement.
- Preserve the 15 conservative constructor-sweep leftovers (12 ambiguous
  `sub_180506120` sites and three complex legacy `this.ctor` sites) until new
  receiver/generic proof exists; do not force them for cosmetic cleanliness.
- `shared_return_type` is an all-candidate proof for an address with more than
  one metadata owner. Every candidate must be readable, fully closed,
  structurally identical, and supported by `_return_abi_is_known`; one failure
  declines the address. Never use a majority, the first candidate, or printed
  type-name equality.
- Root MethodSpec `VAR`/`MVAR` returns may inflate from exact class/method
  instantiations. An open generic at any nested depth declines. Preserve byref
  from the return signature, not the type argument.
- Return consensus does not resolve method identity. Keep the honest
  `sub_<va>/*shared body, N candidates*/` rendering and do not apply
  method-name/receiver/property transformations that require one owner.
- One shared body has one argument list. `_shared_arity_cap` (largest
  declared arity among an address's candidates, receiver included, plus the
  hidden sret buffer when the return is the all-candidates consensus) bounds
  both `_call` and, through `_shared_tail_keep`, an unresolved shared tail --
  one VA must not print `(x)` when called and `(x, 0)` when tail-jumped. Only
  a trailing run of literal `0` is droppable, and only below that cap: it is
  the register a shared forwarder zeroed for the callee (`xor edx,edx` /
  `mov r8d,0` ahead of the jmp), never something the source wrote. A
  non-zero extra argument, a single candidate, an unreadable candidate, or a
  cap that does not sit below the list keeps today's spelling, so a
  registry-missed sharer that really reads the register (probed:
  `List<T>.CopyTo`'s R8 at `0x180df9c30`) is untouched. Never trim a
  *resolved* tail: an identified callee owns its own signature.
- A shared body's printed argument list follows the all-candidates slot
  classes when every candidate is a readable non-generic MethodDef that
  agrees on the class sequence (`_shared_slot_classes`; receiver and the
  consensus sret buffer count as GPR, R4/R8 by-value params as XMM).
  `_shared_positional_args` then rebuilds the list by ABI position: the
  raw GPR-first spray, truncated to the arity cap, printed the stale RCX
  value where a float parameter lives and dropped the real XMM argument
  (mi 20081 `Angle.op_Implicit` at 0x182da54f0; the `mulss xmm0,xmm0`
  square leaf 0x1826e1660). A generic spec, an unreadable row,
  disagreement, a class beyond the four argument registers, or a class
  set without an XMM slot keeps today's truncation.
- `_icall_annotation` picks a same-named overload by the runtime
  signature's own parameter list: unique declared arity, else unique
  normalized parameter-type match (CLI primitives, `/`->`.`, backtick
  arity, byref markers; `_icall_type_key`). The old first-row scan seated
  `_call`'s arity trim on the wrong overload and dropped real arguments
  (`Object.FindObjectsOfType(Type,bool)` rendered `(type)`; the
  AndroidJNI `To*Array(ptr,int)` family, `UnsafeUtility.IsBlittable`).
  Ambiguity returns the text-only annotation, never a guess.
- An interface-offset dispatcher (the fixture's `0x180002210` /
  `0x180002380`) is recognized by structure, never by address: exactly one
  `movzx ..., word [k+0x12E]` interface count, one `mov ..., [k+0xB0]`
  table, one `add ..., 0x138` and one `shl ..., 4`, an indirect tail jmp,
  and a miss-path call (`_iface_dispatch_arity`, filled into `rt_iface`
  by `_init_runtime_ids` from the hot-target set it already collects).
  Only a member that never reads R9 -- the register after the
  (slot, iface, receiver) triple -- is a nullary dispatcher; a reading
  variant forwards one managed argument through the parameterized twin
  below. The resolved return closes
  through `_generic_class_args(iface.ty)` + `_subst_closed`; an
  unclosable open return (`IEnumerator_1<T>` with no T in scope)
  declines to `sub_`. Results are materialized at the call instruction
  (getters excepted): left lazy, the enumerator stack home and the phi
  copy's `_bind` both materialize the call, duplicating `GetEnumerator()`
  with the second instance as the iterated one.
- A forwarded R9 argument is live on entry or it does not exist:
  `_r9_touch` decides by FIRST touch (source/memory/CMP/TEST/JMP/CALL/
  PUSH/XCHG reads prove it; a MOV/ZERO/LEA/POP destination manufactures
  it, self-xor included). The eager `cnt`/`stats` sample is
  Assembly-CSharp-only, so non-AC members are proved on demand through
  the memoized `_iface_arity` choke (per instance; VAs are
  binary-local), never by address. The parameterized twin resolves
  single-parameter targets with GPR-class R9 (floats/`?`/placeholders
  decline), drops R9 spray for zero-parameter targets, and declines
  multi-parameter targets, byref first parameters, and single-field
  struct returns (the F2 first-field guard would project whole-struct
  reloads without consumer proof; enums flow cleanly).
- A unanimous conversion family (every candidate the same static
  one-parameter op_Implicit/op_Explicit with distinct returns)
  resolves only at a caller-proven `(T)` cast naming exactly one
  return, with a float-taking single argument (bare-object temps,
  doubles, and multi-arg keep the marker).
- A bounds-checked element-address helper is a 34/35-byte skeleton
  with the jae landing exactly on the fail call; the stride is
  extracted, never assumed. Naming (`il2cpp_array_addr`, arity 2)
  reaches non-AC images through the same lazy `_call_name` seam as
  the class-init twin.
- An element-class IsInst folds `sub_x(obj, [arrklass+0x40])` to `obj
  as E` only with newarr-exactness: a same-method newarr fixes the
  runtime klass to exactly E[], while array covariance lets a
  param/field/static/`as`-refined E[] hold a D[] at runtime, so only
  an allocation proves (`_newarr`, preserved across value-preserving
  copies, kills, binds and merges). Merges compose per-path proofs
  for one array type; dry unanimous merges record a `_dry_proof`
  invisible to dry execution because pass 2 reads dry end_states at
  loop back-edges structurally. The element must be a closed
  nameable reference type, never System.Object (an `as object` fold
  is noise) or a value type (`as` is illegal); the fold fires on the
  load path only, so stores, LEA and CMP keep today's raw spelling.
- A consensus value type folds sret only when the individual call's first
  argument is an observed address. Require a known exact nonzero value-type
  size; generic value types, source-level ref returns, and unsupported opaque
  ABI classes remain unknown.
- `type_sizes[i]` is `instance_size - 0x10` or `None`, never a negative
  number: the loader subtracts the 0x10 object header, so any
  `0 < instance_size < 0x10` (an open generic DEFINITION, a `<Module>` row)
  is an unknown size, not `-15`. Test `v >= 0x10`, not `v`. A negative size is
  the plausible-wrong-value that flips a hidden-sret decision and shifts every
  argument register.
- The Android registration loader is a *different struct shape*, so it is
  reachable only for an ELF (`cli.py` gates the fallback on
  `isinstance(bin_, ELF)`). Probed on the x64 PE it does not fail: it lands on
  a `code_reg_va` 0x10 below the classic answer with the same module count and
  the same resolved method coverage, so running it on a PE trades a clean
  error for a silently wrong registration. The whole registration phase is
  wrapped and reports `error:` rather than tracebacking.
- Ambiguous arity trimming happens before sret folding and uses the inflated
  consensus type for the hidden-buffer slot. A typed shared call binds at its
  call instruction so type evidence cannot reorder it across visible effects.
- A partitioned sweep can expose pre-existing state/order-sensitive render
  hashes. Use fixed-order isolated old/new source parity before attributing hash
  changes: Review 83 proves 4,322 genuine changed bodies and classifies 2,029
  initial comparison deltas as partition-state-only.
- `_semantic_local_names` is a final-render-boundary readability pass. Never move
  it before copy/dead-local/control-flow/interface-dispatch processing: those
  passes intentionally consume the num/flag/real/obj vocabulary.
- A type-derived local name is allowed only when the emitted declaration type is
  already concrete. `object objN` is the honesty marker for unresolved native
  values and must remain `objN`; prettier names are not type evidence.
- Semantic names are method-wide unique, collision-checked against every body
  identifier and every metadata parameter name (even unused parameters), and
  replaced outside string/character literals and line/block comments only.
- The same literal/comment barrier covers `_render`'s `$` -> `_` sanitize
  (`_sanitize_dollar`; `$"`/`$@"` prefixes included) and
  `_rename_locals`' vN/tN/s_XX pass (`_mask_literals` NUL-blanks the
  spans for both the token scan and the substitution, keeping spans
  aligned with the original line). A blanket replace corrupted JSON.NET's
  wire names (`$type`/`$id`/`$values`), the UTF7 direct-character set,
  and the ADO.NET diffgram namespace (`...-v1` -> `...-obj83`); renaming
  comment tokens also kept a dead pure cluster of mi 80548 alive, which
  the post-render DCE now drops.
- `_refine_explicit_object_locals` may strengthen `object` only for a
  single-definition array creation, string literal, or exact `typeof` RHS with
  no later write or ref/out/in/address escape. Do not add `new T()` without
  proving reference type and boxing identity. Array rank counts top-level
  dimension commas only; uncertain generic/comparison dimensions stay object.
- Declaration matching requires an assignment distinct from `==` and excludes
  control heads. Keep the `return obj1 == 36` regression: it must not block
  `char character1`.
- A first-use bare assignment declares its temp from the same tracked-type
  lookup as `var` lines, with scope-aware re-declaration in sibling blocks.
  A zero-literal RHS becomes `= default` only for zero-valued numerics under
  a type it cannot spell; nonzero literals keep their faithful value.
- `_strip_dangling_default` keeps any `: default` governed by a live `?`
  mark at an open paren depth. A call's parens or commas inside the true
  arm (`c ? Foo(a, b) : default`) are not region boundaries; `??`/`?.`/
  nullable `?` never open an arm. Do not restore the flat reset: it
  orphaned 26 false arms into unparseable `? call() ;` (fix 97e).
- The unregistered native sqrt/domain wrapper is accepted only as one unique
  structurally matching unknown target: bounded executable extent, XMM0 double
  spill/reload, `SQRTSD`, RIP-relative `"sqrt"`, and `RET`. Never hardcode its
  address or infer it from a managed method name.
- Packed conversion/root/narrowing instructions scalarize only at IPs recorded
  by `_sqrt_low_lane_sites` after the exact `UCOMISD; JA helper; SQRTPD` diamond
  is proved. The helper arm's scalar XMM0 ABI is the high-lane-dead proof;
  unpaired packed SIMD remains conservative.
- `_return_value_register` is the shared Win64 return rule: by-value R4/R8 use
  XMM0; integer/object/pointer/generic and byref R4/R8 use RAX. Keep structured
  RET, flat fallback, direct-call results, and indirect tails consistent.
- A natural-loop header with statements, or with both successors inside the
  loop, is executed through `_seq` inside `while (true)`. Never move its reads,
  calls, copies, or branch before the loop: the header runs on entry and every
  back edge. `_enter_stop`, `_active_loop_header`, and suppressed-start-label
  controls are narrow internal mechanisms for exactly that one header visit.
- `_memory_rhs_needs_loop_guard` guards unresolved/potential indirect control
  flow, not modeled direct back edges. Do not reintroduce the frozen ReadSpan
  fallback. Cyclic array allocation remains separately guarded until dominance,
  per-iteration identity, and alias lifetime are proved.
- `_loop_shared_entry_gate` may fold only the exact single-predecessor,
  statement-free gate with one shared in-loop target, one exit, no edge phi
  copies, and no pad/SEH boundary. Otherwise retain conservative CFG output.
- `_replay_consumed_linear_to_stop` proves the entire consumed acyclic,
  single-successor path to the current exact stop before emitting any duplicate.
  Do not turn this into speculative region cloning or allow entry/pad/SEH
  crossings; failure must remain atomic.
- The corpus still has 8,071 into-block gotos in 2,048 methods. Net reductions
  do not erase the 83 method-level increases recorded in
  `validation_reports/review80/structural_delta_summary.json`.
- `_shared_sret_receiver_target` proves a common two-pointer Win64 ABI across
  every candidate and matches RDX's exact pointee. RCX is the output buffer,
  never receiver evidence. Unknown sizes/generics/mixed layouts stay unresolved.
- `_array_allocation` creates one typed identity per instruction only when the
  CFG proves the required acyclic lifetime. String-array LEAs retain their
  element address so local plain-store/GC-barrier twins collapse; never replace
  this with global textual deduplication.
- SQRTSS narrows Math.Sqrt to float; SQRTSD remains double. The proved packed
  low-lane/helper family follows the stricter Review 81 rules above; general
  packed SIMD/vector tracking remains open. Generated projects allow unsafe.
- Resolved direct calls/tails rebuild Win64 positions, ignore stale GPR/XMM
  noise, recover contiguous stack args, and preserve fixed-frame `rsp` slot
  identity. Broader shared/virtual/indirect ABI recovery remains open.
- Preserve Review 78's Boolean-byte stores, old-value aliases, array type hints,
  and exact all-candidate static-conversion gate.
- `_decl_type_of` may close an open-generic tracked hint (structural VAR/MVAR
  proof) over the same line's closed `new` RHS only for the same generic
  definition (same short base, same arity) with argument-position openness
  agreement — qualified names like `TMPro.X` are closed, never params.
- `_drop_dead_locals` re-runs on post-`_render` lines (fix 99): `_render`
  drops empty pure-cond `if`s and orphans their pure loads, so the second run
  is load-bearing. Never remove it as "redundant" with the pre-render run.
- A `mov r64,rsp` frame copy carries the frame offset (`_stack_offset` on a
  `?`-text ptr) instead of dropping to `None`, so `[copy+N]` keys slots by
  absolute address and aliases `[rsp+M]` of the same home; arithmetic, indexed,
  and 32-bit uses decline to the unknown-base shapes. RBP never takes a copy
  offset (`mov rbp,rsp` keeps the unreadable frame idiom): the frame path owns
  its disp keys, and absolute tracking there splits homes (stash-proven on
  80548) — RBP behavior is byte-identical with or without copies live.
- `_rbp_is_frame()` consults `_rbp_frame`, a tracked FACT, never the register
  value. `mov rbp,rsp` sets it; any other write to RBP clears it in `set_reg`;
  the pass-2 phi merge cannot clear it, because the merge installs values
  with `L.regs[k] = ...` and so bypasses `set_reg`. Deriving the answer from
  the value is what broke it: the merge rewrites a never-written `RBP = None`
  into `Expr('?')`, which `_bind` then rewrites into a temp name, so a text
  or `_unk` test catches at most half the sites and every `[rbp+N]` in a
  merged region fabricates pointer arithmetic on the seed
  (`((byte*)obj9 - 0x30)[0] = vector31`, where `obj9` is not a pointer —
  named, so it parses, so the parse gate sees nothing). Do not reach for
  `_defpos` as the discriminator either: `_copy_expr` drops it, so "no
  definition site" cannot tell an unwritten register from a copy of a
  written one.
- `slot_var` sign-extends with `sdisp` before keying, so one native home has
  one key whatever the caller passed. iced-x86 reports `[rbp-0x30]` as
  `0xffffffffffffffd0`, and the callers disagree: the RSP-copy path hands in
  an already-extended `_stack_address`, while the RSP/RBP direct paths and the
  LEA path hand in `ins.memory_displacement` raw. Two coordinate systems for
  one home split a `[copy+N]` write from an `[rsp+M]` read into two C# locals
  and name slots `s_ffffffffffffffd0`. `sdisp` is idempotent on an
  already-negative value, so normalizing at this single choke point leaves
  every correct caller's name byte-identical. Both the key and the name must
  come from that one normalized `off`. The name still uses `abs(off)`, which
  is pre-existing and deliberately unchanged: it means a `+0x30` and a `-0x30`
  slot would share the name `s_30` at different keys. Normalizing the name
  derivation too would rename every correct caller's slot, so fix that latent
  collision only inside a deliberate rename pass, never as a drive-by.
- Same-typedef shared-body twins (e.g. Transform get_parent triple) keep the
  honest marker: no receiver proof can split one declaring typedef, and
  consensus typing never resolves identity. An exact all-candidate semantic
  operation may render without selecting an owner: the System.String
  Equals/op_Equality pair shares one body and one `(string,string)->bool`
   signature, so typed string operands can render `==`. Unknown operand
   types and effectful extra registers still decline.
- A shared `call; int3/ud2` forwarder renders `return Target(args)` only
  when the caller body is multi-owner, the target is exactly one readable
  MethodDef, the call text is marker-free, and the caller's exact return
  tuple equals the target's (both non-void). MSVC's own abort is the
  noreturn evidence; anything else keeps the honest `/* nothing */` drop.
- Array-typed receivers resolve through the System.Array typedef
  (`_system_array_td`, unique-or-decline like `_system_object_td`):
  arrays have no subclasses and Array owns their instance dispatch, so
  rank/element openness cannot change Clone/CopyTo identity. Byref
  markers and missing/ambiguous Array rows decline; the sret-clear,
  ctor, generic, and `len(hits)==1` gates run unchanged at all three
  chain-filter twins.
- `_rename_locals` never mints an obj/num/flag/real name already used in
  the lines or declared as a metadata parameter (124140: s_8/v4 became
  obj1/obj2, shadowing the params, and `_copy_prop` merged the dropped
  argument). Reserve-then-bump, mirroring `_semantic_local_names`.
- `_rename_locals` never renames a token matching a metadata parameter
  name (113041: body params v0/v1 became unbound obj5/obj6 while the
  emitter kept v0/v1). Parameters already declare their names; a lifter
  temp sharing the spelling keeps its honest lift-stage name.
- Textual interface dispatch names a call only when the slot-address
  assignment, a span-referenced `typeof()` decl, an exact single
  in-range metadata method, and a shaped receiver all agree
  (25368: GetEnumerator/MoveNext/Current). `_N` display arity falls
  back to `` `N `` metadata names only after the exact key misses.
- A boxed bool from a proved-bool dispatch folds its null test
  (`object X = call; if (X == null)` to `bool X; if (!X)`), recorded
  at naming time and folded post-semantic-names with all-uses-bool,
  single-decl, and standalone-head gates; anything else keeps the
  boxed shape.
- Scalar const-pool loads carry their bytes for float-lane readers;
  GPR `?` tail and resolved-direct args materialize composites at closed
  all-float vector slots (house `(float2)(l0,l1)`; 80548's part-less
  integer carries decline by construction).

All package sources under `il2cpp/` are CRLF with no BOM; the root
`il2csharp.py` launcher is CRLF and retains its UTF-8 BOM. A regression test
(`tests/test_source_format.py`) enforces this contract. **1253 tests pass** (1027 portable + 226 game;
64 golden snapshots, all green).
`tests/goldens_review84.json` is **hash-only**: each of the 64 snapshots
keeps its MethodDef row, VA, owner and name plus `body_sha256` /
`body_lines`; `tests/test_game_goldens.py` compares hashes when bodies are
absent and bodies when present. The older `goldens_review77/79/80/82/83`
archives and every full-body snapshot were removed from history in the
2026-09-28 public scrub (see `docs/public_release.md`); regenerate a local
full-body file with `tools/make_goldens.py --full` (never commit it).

Use `tools/csharp_smoke.py` for the .NET 8 compiled-pattern checks, including the
actual loop emitter. They passed for Review 80 but were not rerun for Reviews
81–97 (or the package split, which `work/split/rebuild_verify.py` proves byte-identical)
because this environment has no .NET SDK; they are never a build of the
complete recovered game. The supplied game fixtures live in the local,
git-ignored `testgame/` only (licensed game data; never track or distribute
them — the 2026-09-28 scrub removed them from history; see
`docs/public_release.md`).

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

`il2csharp` is a from-scratch IL2CPP → C# decompiler: `global-metadata.dat` +
`GameAssembly.dll`/`libil2cpp.so` in, a real source tree out, with every
method body lifted from native x64 code (not just signatures). The code lives
in the `il2cpp/` package (split out of the former `il2csharp.py` +
`decompiler.py` monoliths on 2026-09-12, with byte-identical output):

- `il2cpp/metadata.py`, `binary.py` — `global-metadata.dat` and PE/ELF frontends
- `il2cpp/runtime/` — the `Il2Cpp` registration/usage-slot/EH4 decoder,
  composed from `registration`, `types`, `fields`, `eh` mixins (`core.py`
  holds the class; `meta.py` holds import-free leaf helpers)
- `il2cpp/lifter/` — the `Lifter` (symbolic x64 execution over `iced-x86`),
  composed from `state`, `values`, `insn`, `calls`, `render` mixins
- `il2cpp/dec/` — CFG construction and the structured `Decompiler`:
  control-flow recovery, the SEH region stack, and the ~20-stage statement
  post-processing pipeline, composed from ten mixins (`build`, `analyze`,
  `structure`, `sugar`, `seh`, `flow`, `dataflow`, `highlevel`, `textpass`,
  `emit`)
- `il2cpp/emitter.py`, `headers.py`, `cli.py` — output assembly and the CLI;
  `arm64.py`/`arm64_dec.py` hold the ARM64 scaffold

Every public name is re-exported from `il2cpp/__init__.py`, so
`from il2cpp import Lifter, Decompiler, Il2Cpp` works.
`docs/construct-mapping.md` documents, in detail, what native constructs
recover as what C# — read it before assuming a construct is unhandled
(the root `README.md` is the quick start).

## Repo layout (2026-09-08 consolidation)

Project root is `il2csharp/` itself. The old parent folder held a sibling
`work/` (20 files, now merged into `work/`), five loose scripts (now in
`tools/`: `compare_content.py`, `compare_outputs.py`, `count_diffs.py`,
`test_import.py`, `test_import2.py`), and the game folder (now the local,
git-ignored `testgame/`; never tracked). Pre-consolidation history in `docs/archive/`
still refers to `../work/`, `il2csharp/final_out/`, sibling `bXX_out1`
trees, and `Shift At Midnight` at the old root — read those as `work/`,
`final_out/`, reaped batch trees, and `testgame/`. Backup zips live in the
parent folder, not in this repo.

## Commands

There is no build step — the decompiler itself is the `il2cpp/` package plus
scratch/validation scripts (`il2csharp.py` is a thin launcher), run directly. There IS a test suite now:
`tests/` (portable unit tests plus optional game-backed goldens, see
`docs/reviews/REVIEW84.md` and `docs/todo.md`), run with `PYTHONHASHSEED=0 python -m pytest -m "not game"`
(portable only) or `PYTHONHASHSEED=0 python -m pytest` with
`IL2CSHARP_METADATA`/`IL2CSHARP_BINARY` pointing at `testgame/`.
Dependencies are pinned in `requirements.txt` / `requirements-dev.txt`
(`requirements-arm64.txt` for the ARM64 scaffold).

```
python il2csharp.py <game-dir-or-metadata> -o <outdir> [options]   # or: python -m il2cpp
  --only NAMES     comma-separated assembly filters (substring), e.g. Assembly-CSharp
  --workers N      emit assemblies in N processes (0 = half the cores, max 8);
                   the tree is byte-identical, only the schedule changes
  --decls-only     signatures only, skip body lifting
  --max-methods N  cap lifted bodies (debug)
  --probe          diagnostics: registrations + modules, no output files
  --publicize      compile-gate mode (fix 127): every member public, fields
                   lose `readonly`; default output unchanged
  --raw-addr       compile-gate mode (fix 128): `(byte*)E` bases route through
                   a declared `__addr(E)` helper (`__RawAddr.cs` per assembly)
```

The two compile-gate flags are opt-in and never part of the promoted tree;
they exist so the Roslyn gate (`work/cgate/`) measures lifting errors
instead of accessibility/raw-pointer noise (see `docs/todo.md` top).

Requires `iced-x86` (`pip install iced-x86`). Syntax-check a change with
`python -c "import compileall,sys; sys.exit(0 if compileall.compile_dir('il2cpp', quiet=1) else 1)"`
before running anything — it's instant and catches typos before a
multi-minute rebuild does. `python -c "import il2cpp"` additionally catches
import cycles, which the package layout can reintroduce.

**All source files under `il2cpp/` are CRLF with no BOM; the root `il2csharp.py` launcher is CRLF+BOM.**
A read-text/write-text edit in Python silently rewrites the whole file to LF — a ~6,000-line phantom diff that
buries the real change. **`sed -i` does exactly the same thing** (batch
50), as will any tool that rewrites the file wholesale. Edit them with
binary read/write (`work/patches/patch_*.py` are the pattern) and check
`d.count(b'\r\n')` against `d.count(b'\n')` afterwards — after *any*
touch, including a one-word comment change. The `.md` files here are LF;
don't cross the two.
**Rewrite scripts must never open the target for writing until every
assertion has passed on the fully-built content** — `open(p, 'wb')
.write(f())` evaluates `open` first, so a raising `f()` leaves a
zero-byte file behind (batch 72's A/B lost decompiler.py exactly this
way; see `docs/archive/batches-c.md` §0ap's incident record). Build in memory, assert,
then write once; make backups once and never re-derive them from the
live file.

**The real target for validation** is a licensed Windows build of *Shift At
Midnight* (Kwalee), metadata v31, x64, kept in the local, git-ignored
`testgame/` (never tracked, never redistributed; the 2026-09-28 history
scrub removed every earlier trace — see `docs/public_release.md`). A Unity 2022 sample
(`Simple_2022_3_35`) under `temptools/Cpp2IL/TestFiles/` is a second,
smaller data point when that external checkout is present (it is not
bundled with this repo). There's no synthetic/bundled test fixture — every claim
about output correctness in this codebase's own commit history was checked
against one of these two real binaries, not asserted from reading code.

### Validating a change

1. A **direct re-lift** of one method is the fast loop — see
   `work/` (now grouped into `lib/`, `runners/`, etc.; routing table in `work/README.md`;
   the old sibling `../work/` was merged into this repo on 2026-09-08) for the pattern: load
   `Metadata`/`Il2Cpp`/`Lifter`/`Decompiler`, find a method by VA in
   `meta.methods`, call `dec.lift_method(m, td)`, print. No file I/O.
1b. **Golden snapshot tests:** `PYTHONHASHSEED=0 python -m pytest -q
   tests/test_game_goldens.py` re-lifts the 64 frozen bodies in the
   tracked, hash-only `tests/goldens_review84.json` (MethodDef row `mi`,
   owner, name, `body_sha256`/`body_lines`) and sees wrong-but-parseable
   output the gates can't. `tools/make_goldens.py` regenerates it ONLY
   after a gated build; read the diff before accepting it — the goldens
   pin whatever the current source produces, bugs included. `--full`
   writes bodies for local review only; never commit it. Do NOT
   regenerate off unbuilt source.
   SAMPLE-SIZE CAVEAT (batch 42): the suite is 64 bodies — a
   structural pass change touching ~6k methods (5% of the corpus) moved
   only 5 of the then-50 bodies. For statement-pass soundness changes,
   the golden suite finds the SHAPE of a wrong transformation, the
   full-corpus sweep (item 3) sizes it — run both before a build.
2. A **tree-sitter parse gate** (`work/lib/ts_gate.py` in this repo, pip:
   `tree-sitter tree-sitter-c-sharp`) is the gate that sees what brace
   counting can't (bare `do {}`, NUL/`...` in statements, missing call
   parens, illegal identifiers, unlexable literals). Historical corpus:
   `b74_out1` — **0 bad files / 0 ERROR / 0 MISSING** (held since batch
   53, `docs/archive/batches-d.md` §0ag; batch 75 has no build yet, so there is nothing
   newer to gate). The legacy-TMP pair that had been the ONLY two bad
   files for ~35 batches was never a decompiler defect: both methods
   exceeded the 1500-block CFG cap and fell to the linear flat lift,
   which bypasses `_final_text`. Raising the cap to 3000 (batch 53's
   fix 63b — exactly three methods corpus-wide sit between the two)
   cleared both. Historical trajectory: 2/2,206/4 at batch 52,
   2/4,864/4 at batch 42, 2/7,919/2 at batch 36, 2/7,924/2 at batch
   35, 2/8,125/2 at batches 32-34, 13/8,148/4 at batch 28, 16/15/2 at
   batch 22, 183/118/193 at batch 19, 302/427/210 at batch 18,
   708/2,261/487 pre-batch-17.
   A clean gate raises the stakes on the OTHER checks rather than
   lowering them: a parse gate at zero can only tell you a change made
   something unparseable, never that it made something wrong. The
   goldens, the sweep and reading real output carry the rest.
   NOTE: `ts_gate.py` prints to stdout — redirect to a file (the
   repo's `work/` keeps the saved `ts_gate_*.txt` reports) if you want
   a report to diff. Parse-gate numbers live in `docs/reviews/REVIEW80.md` and
   validation_reports/review80/; current compile-gate (roslyn error)
   numbers live at the top of `docs/todo.md` (fix 140: gate b19 =
   454,955); older numbers here are history. Always bucket by row text — whole file-span rows (L1
   headers, `internal sealed partial class`) inflate counts, and ONE
   unparseable line can cascade over a whole file (batch 19 hit 81
   ERROR nodes in Timer.cs off a single bad condition), so a big
   per-file count usually means one defect, not many. When the bad-file
   set is unchanged between two gates, every ERROR delta is confined to
   those files — that IS the per-file diff (used this way at batch 35).
   `work/lib/gate_diff.py A.txt B.txt` diffs two saved
   reports per file (newly-bad / cleared / worse / better) — always run
   it when you have saved reports, the summary line alone hides a
   regression under a bigger win.
   Note: `_final_text`'s line-local transforms are mirrored in
   `work/lib/sim_rewrite.py` — a built tree + ~2 min sim re-gate is the
   fast full-corpus loop for `?`/`unknown`/`default`/select-family
   changes, but a REAL rebuild (18.1 min measured at r9, a `work/runners/run_build_*.py` into
   `<out>`) is the only truth for Lifter-side changes. Two traps in
   that loop, both paid for in batch 19:
   - **A sim tree may only be compared against another sim tree.**
     `sim_rewrite.py` does not mirror `_fix_select`, so it strips
     `: default` that the real pipeline re-synthesizes; a sim-vs-built
     diff shows ~80 phantom regressions. `work/lib/make_sim_base.py`
     generates the old-rules control to diff against.
   - **Measure a rule's hazards against what ENTERS the pass, not the
     tree it already produced.** A built tree has the old rule's output
     baked in, so a shape the old rule collapsed reads as "0 sites"
     right up until the new rule stops collapsing it.
3. A **full-corpus in-memory sweep** (iterate every method with native
   code, wrap `lift_method` in try/except, no file writes) catches
   crashes/regressions across all ~116k bodies in a couple of minutes —
   much faster than a file-writing rebuild, and it's how the two most
   subtle bugs found in this codebase's history were actually caught
   (a silently-crashing regex, and a brace-balance regression neither the
   crash count nor the per-file audit below could see on its own).
   `work/lib/sweep_audit.py <tag>` is the driver: per-method literal-aware
   counts of `brace`, `dangling` (goto with no label), `into_block`
   (goto into a nested block), `empty_arg` (`f(a, , b)`), `follower`, and
   crashes — batch 15's gates. Known baseline at b74_out1: 0 / 0 /
   13,505 / 0 / 0 / 0 (sites/methods for into_block: 13,505/2,978;
   driver now `work/lib/sweep_1a_audit.py`). into_block history: 21,326 (batch 20) ->
   21,464 (batch 21, explained uptick) -> 17,718 (the shared-tail
   hoist pass, batches 12-15 era baseline through b41) -> 32,094
   (batch 42: the funnel applied to classic hoists un-did ~14.4k
   hoists proven unsound by disassembly — the deliberate, documented
   honesty cost, `docs/archive/batches-e.md` §0v; recovery paths sized as todo leads 1a/2)
   -> 15,419 (batch 43's tail duplication) -> 12,950 at b63_out1
   -> 13,815/2,960 (batch 54's second-table recovery) -> 13,505/2,978
   (batch 55's bound/group-table fixes, held through b74) ->
   13,518/2,979 (batch 75, `work/sweep_b75b.log` with the fold
   active: +13/+1 off b74, +63,252 lines net of phi materialization
   and fold collapse).
   **Crashes are 0 as of batch 53** (`docs/archive/batches-d.md` §0ag): the two
   long-standing cfg-too-large caps in
   TextMeshPro/TextMeshProUGUI.GenerateTextMesh cleared when fix 63b
   raised the block cap 1500 -> 3000, so ANY crash in a sweep from now
   on is one you introduced.
4. A **full rebuild + brace audit** (`python il2csharp.py <target> -o
   <outdir>`, then `python work/lib/tree_brace_audit.py <outdir>`) is the
   final gate before promoting a build to the baseline. `--workers N`
   emits the 91 images across a process pool, heaviest image (by native
   method count) submitted first, and is the same tree byte-for-byte: the
   full 8-worker r10 tree is 11,276/11,276 files identical to `final_out`
   (275.0 s vs 1,085 s serial on 2026-09-28; 262.9 s on 2026-09-26), so
   the determinism cross-check costs ~4.5 min instead of 18. `--workers 0`
   is half the cores, max 8 -- a wide build takes the machine; and
   `--max-methods` and `--bodies` force 1. Note its blind
   spot: it sums `{`/`}` counts per **file**, so a `try { } else { }`
   (individually balanced brace pairs, invalid C#) or two compensating
   errors in the same file both read as 0. Prefer the full-corpus
   sweep's **per-method** count when chasing structural bugs
   specifically — and that count MUST be literal-aware:
   `work/lib/sweep_trybrace.py`'s `brace_delta()` skips braces inside
   string/char literals and `/* */` comments, because a naive
   `l.count('{') - l.count('}')` counts `"BitVector32{"`-style literals
   as imbalance (all 24 "imbalanced" methods in batch 13 were that false
   positive; literal-aware count is 0). The `try { } else { }`
   malformation class itself is now 0 sites tree-wide (was 389 pre-batch
   12); the one surviving try-structure artifact is a switch-reached
   +3-open region in CustomAttributeTypedArgument.ToString,
   byte-identical across prev12/prev13 — see `docs/reference.md` §6 (Known
   artifacts).
5. **Baselines.** The current release baseline is Review 84 `final_out/`,
   documented in `docs/archive/reviews-log.md` §0bb and `docs/todo.md`'s head. The following promotion
   chronology is historical, not an instruction to use the older trees. `final_out/` **was
   promoted to `b42_out1` on 2026-08-22** (batch 42, gated 2/4,864/4 —
   the documented TMP pair only; byte-verified copy); the gated
    candidate is now **`b76_out1` (batches 43-76, gate 0/0/0)**;
    `b74_out1`/`b75_out1` are superseded (`b75_out1` gate 0/0/0 --
    do not regenerate goldens off unbuilt source). Review 77 (`docs/reviews/REVIEW.md`,
    2026-09-08) advanced the SOURCE past b76 (tail-arg recovery,
    renderer ordering, CLI + instrumentation, portable validator kit;
    validation table 11,107 / 115,658 / 0 failed, gate 0/0/0) WITHOUT
    promoting -- b76_out1 is still the gated candidate, promotion is a
    human call. The 2026-09-08 `final_out/` disk tree is a PARTIAL
    aborted rebuild (6 assemblies, Review-77 source -- `docs/archive/batches-c.md` §0au),
    not a candidate and not a baseline.
   The promotion
   pass reaped the batch trees one level up (`b37_out1`-`b42_out1`)
   and the work-dir archaeology tied to reaped trees (old build logs,
   gate reports, site dumps, one-shot `run_build_*` scripts, the
   frozen batch-21 source snapshots, `__pycache__`/`.pytest_cache`);
   the provenance records (`patch_*.py`, `fix_*.py`, probes,
   censuses, tests, the current build log and gate report) were kept.
   The previous promotion (b36_out2, 2026-08-21) had already deleted
   the `b18_noreind`-through-`b36_out1` chain and the
   `final_out_prev18/` archive — nothing is kept for A/B below
   `final_out/`. To isolate one change's *own* effect,
   re-run the build against a copy of the source with just that change
   reverted, then diff.
6. `PYTHONHASHSEED` nondeterminism is a known, historical class of bug in
   this codebase (dict/set iteration ordering leaking into generated temp
   names) — if a diff looks unrelated to your change, check whether it
   reproduces with a fixed hash seed before assuming you caused it.

Read `docs/todo.md` (open work only) before starting nontrivial work, and
`docs/` for the state record — `docs/todo.md` holds current work, `docs/reference.md`
the working-loop rules (§4), baselines/promotion/known artifacts (§6) and
gotchas (§7), and `docs/archive/` the review log, batch writeups (§0b–§0r),
archived numbers (§1), backlog trail (§3) and compressed history (§8); every
`§NN` cross-reference in the repo resolves against those files (map in
`docs/README.md`). They record what was just tried, including reverted attempts and *why*
they were reverted, which matters as much as what shipped.

## Architecture

**Pipeline**: `Metadata` (parses `global-metadata.dat` tables) +
`load_binary` (PE/ELF, locates `Il2CppCodeRegistration`/
`Il2CppMetadataRegistration` by structural validation, not a version
lookup) → `Il2Cpp` (joins them: method addressing, usage-slot decoding,
vtables, EH tables, generic instantiation) → `Lifter` (per-method: decode
the real instruction extent — not a linear byte prefix — build a CFG,
symbolically execute twice: a dry pass to discover phi-merge locations,
then a real pass that emits statements with types carried through). Method
values are `Expr` (text + il2cpp type tuple + a coarse kind like `obj`/
`int`/`ptr`); the register file is a dict subclass that counts *renderings*
per expression object so a value used twice gets bound to a named temp at
its definition instead of re-printing its whole expression text at each use
(`_bind`), and a store invalidates the text of every live expression that
reads the stored location (`_kill_stale`) so re-rendered text can't
silently pick up a post-store value.

**`Decompiler`** (in `il2cpp/dec/`, mixin `dec/structure.py` + `flow.py` + `dataflow.py` + …) takes the Lifter's per-block output
and structures it: dominator/postdominator analysis, natural-loop
detection, `_seq` — a recursive-descent walk that emits `if`/`else`/`while`/
`switch`/`goto` directly rather than building an intermediate AST — followed
by roughly twenty-five statement-list passes (`_structure`) that fold sugar:
`for`, `foreach`, ternary, null-conditional, `lock`, `using`, string
interpolation, compound assignment, dead-code elimination, local renaming,
plus `_switch_synth` (flat `==`-chains -> `switch`), `_drop_dead_lastdef`
and, last, `_delegate_cache_fold` (`CACHE ?? (CACHE = new ...)`).
Passes run in a fixed order and several depend on an earlier one having
already run (e.g. dead-phi-copy removal has to precede `&&`/`||` folding;
the delegate-cache fold runs after `_drop_dead_lastdef` so no later pass
eats its `??`);
check the call sequence at the end of `_structure` before reordering
anything. `_seq`'s jcc handler emits a join-edge phi copy at the END OF
THE TEST BLOCK before the `if` head when that edge IS the join and its
arm reaches the join (fix 75 `pre_edge`); otherwise it keeps the old
after-fork emission. One pass — `_hoist_shared_tails` (after the second
`_resolve_labels`) — eliminates `goto`-into-nested-block sites: it moves a
label's tail out past its construct when every into-goto provably falls
through to the hoist point (no code between, no loop/switch/SEH level
crossed) and every sibling `else` arm ends in flow-break (the funnel
rule). Its soundness predicates are replicated by `work/lib/classify_into2.py`
(per-label census; SOUND = 0 tree-wide after batch 15); treat the
`_falls_to` switch-level rejection and the nested-label guard as load-
bearing — both were root-caused against real wrong output, not taste.

**SEH (`__CxxFrameHandler4`)** is its own subsystem, decoded from ground
truth: `ehdata4_export.h` is a real Microsoft header (not public, but
shipped with any MSVC install — `VC/Tools/MSVC/*/include/`), and this
codebase's EH4 parsing was rewritten against it rather than reverse-engineered
from disassembly. `Il2Cpp._eh4_parse`/`_eh4_ipstates`/`_eh4_try_ranges`/
`_eh4_regions` decode the compressed try/catch/finally tables, including
exact per-try IP ranges where they resolve to one contiguous span (most do;
switch/goto-reached trys with several disjoint spans don't, and use a
structural fallback instead — bridging disjoint spans was tried and
reverted, it can misattribute a sibling try's code). `Decompiler` tracks
**multiple** independent try regions per method as
`self._seh_regions` (a list, outer-to-inner ordered) rather than one — every
consumption point in `_seq` opens/closes *all* matching regions, not one.
This area's one surviving artifact is a switch-reached +3-open region in
CustomAttributeTypedArgument.ToString (byte-identical across
prev12/prev13; the `try { } else { }` class itself is 0 sites tree-wide
now) — see `docs/reference.md` §6 (Known artifacts) before touching region open/close
logic.

**Shared-body call resolution**: MSVC folds byte-identical method bodies
and IL2CPP shares one compiled body across generic instantiations, so a
call's target address can have dozens to thousands of true owners.
`Il2Cpp.addr_candidates` keeps all of them (`addr_to_method` keeps only the
first, for callers that don't care which). Disambiguation walks the
receiver's declaring type up its **base chain** (`Il2Cpp.base_chain_tds`) —
important because a `: base()` constructor's receiver is always the
*derived* type, never the base that actually declares the shared
constructor — or matches a shared generic call's hidden instantiation
argument against a decoded metadata usage slot. When neither settles it,
the honest `sub_x/*shared body, N candidates*/` marker prints instead of a
guess; don't try to make that case "prettier" without a way to actually
prove the target — the alternative is a confidently wrong name (this was
a real, shipped bug before batch 11: `Guid.cs` calling `ReadOnlySpan<Obi.
BurstCollisionMaterial>`). Even the genuinely-ambiguous case isn't fully
unrecoverable, though: every candidate names a call into the literal same
compiled machine code, so they consume the same argument registers no
matter which metadata identity is true (batch 21, fix 21j) — the argument
list is trimmed to the largest declared arity among all candidates
(sound, not a guess at which one is right) instead of keeping every GPR
slot plus whatever stale float-register value survived from earlier in
the method as a bogus extra "argument". Untrimmed, this was read-before-
def's single biggest contributor tree-wide (-6.8% of the whole corpus's
temp count from this one fix) — the `Update()`-is-300-lines-of-`objN`
complaints trace substantially back to it.

**Reference checkouts under `temptools/`** (Cpp2IL, ReforgeIL — external,
not bundled) are *not*
dependencies — nothing here imports from them. They're read for ground
truth on version-gated metadata formats and design patterns (ReforgeIL's
`docs/` in particular documents its own deliberately-unsolved problems,
e.g. RGCTX resolution — useful for knowing what's genuinely hard versus
what's just unattempted before spending time on it).
