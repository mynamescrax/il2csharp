# il2csharp — TODO (open work and historical triage)

## Current work: fixes 126-134 compile-gate slices (2026-10-06, on `main`)

**Fix 137 (IN FLIGHT, accessor sugar): proved property-row accessors use
the member syntax the emitter declares (`lifter/calls.py` `_accessor_prop`
/ `_accessor_sugar`: `s.get_Chars(i)` -> `s[i]`, static getters ->
`Owner.Prop`, setters -> assignments incl. indexer sets; tails in
`dec/analyze.py` + `lifter/insn.py`, short2 + normal call paths).
Fix 137b: the sugar travels the pipeline as call-shaped markers
(`__accget(R.X)` / `__accset(R.X)(v)`, `il2cpp/expr.py`) so every text
purity test keeps treating the accessor as the call it is; `lift_method`
(`dec/build.py`) unwraps them last, after all DCE/CSE. The hole it
closes: a bare `R.X` getter reads as a pure load and was DCE'd when
unused / re-evaluated into a loop head (mi 5694 AppendFormatHelper's
`format.get_Chars(i)` -- a call that can throw -- vanished; post-fix it
reads `format[i]` and the loops resugar to `for`). Portable 1,309
passed (7 new marker/unwrap tests). mdiff (7 methods, post-marker):
six one/two-line improvements (mi 26747 Rpc_CMD_Heal `set_health` ->
`health =`, 24208 tail setter, 23902 static getter, 23554 2x static
setter, 12710 Chars indexer, 59905 `List<T>.get_Item(hits, i)` ->
`hits[i]`) + the mi 5694 reshape. Game suite: 263 passed / 4 failed =
the mi-26747 golden (intended) + 3 mi-5694 temp-renumber pins (intents
hold: `this.Append(character1)`, `Format(obj155, obj74, provider)`,
`if (obj84 == 0)`); all 4 need a user-approved re-pin. Gate b11 was
built from PRE-marker code: 492,867 -> 486,624 (-6,243; CS1061 -4,069,
CS0571 -2,433) but parse codes rose (CS1525 +36, CS1002/CS1003/CS1513
+18 each) -- the bare sugar let `_ternary` fold `if (c) X = a; return;
else X = b; return;` into `X = c ? a; return : b; return;`
(SlowmoToggler/KeybindsManager/CheckMSAA/TMP_InputField); post-marker
lifts of all three shapes are clean if/else. Gate b12 (post-marker
code, 10/10 groups exit 0, 11,262 files, brace audit 0, zero `__acc`
leaks tree-wide) vs cg7: 513,959 -> 486,559 (-27,400). Fix-137-only
delta b10 -> b12: 492,867 -> 486,559 (-6,308; CS1061 -4,048, CS0571
-2,433, CS0019 -455; relabel rises CS1503 +364, CS0103 +107, CS0266
+95, CS0021 +88, CS0029 +37, CS0120 +13) with ZERO parse codes in the
delta. Sampled rises are relabels of already-broken lines (same
precedent as fix 135/136): CaseInsensitiveAscii.cs:37
`obj7.get_Chars(0)` (CS1061) -> `obj7[0]` (CS0021); Guid.cs
`string.IndexOf(...)` same statement, shifted line; XsdDateTime.cs file
total 2,434 -> 1,445 (-989) with its CS1503 +205 unveiled on
object-typed receivers. OPEN (landing blocker, under investigation):
mscorlib RegistryKey.cs +14 CS0103 `num10` -- the newly-pure
`stringBuilder1[num10]` loop resugared while->for and the minted
for-header reads `num10` with no declaration in the body (rename /
decl-drop interaction exposed by the sugar, repro mi 516 FixupPath).
Full game suite with final code not yet re-run (game138 ran pre-marker
code). NOT landed, NOT pushed, NOT re-pinned (all need user call).**

**Fix 135 (CS0019 slice, 2026-10-06): `_numeric_obj_retype` in
`il2cpp/dec/highlevel.py` (end of `_rename_locals`) retypes an untracked
`object objN` temp to `int`/`long` (renamed into the num family) when
every def is an int literal / integer operator / integer local / itself
and no use is reference-like (member/index/call, null, is/as, casts,
&/ref/out, `__addr`). Gate b8 -> b9: total 499,479 -> 494,104 (-5,375);
CS0019 -3,319, CS0266 -3,036, CS0029 +1,132 (relabel: the same broken
lines now read `int -> struct` instead of `object -> struct`), no parse
codes, brace audit 0. Portable 1,300 passed, game 263 passed. Next:
float-used temps (`real`), the `objN + 0xK` `__addr` shapes, call-defined
temps, CS0103 remainder.**

**Fix 136 (CS0019/CS0266 float slice, 2026-10-06): `_numeric_obj_retype`
now also types float lanes -- float literals (`0.6f`, `1e5f`) and
float/double locals make the temp `float`/`double` (`realN` family; rank
int < long < float < double); float temps used with bitwise/shift/% keep
`object`. Gate b9 -> b10: 494,104 -> 492,867 (-1,237; CS0266 -1,146,
CS1503 -193, CS0019 -165, CS0029 +285 relabel), no parse codes, brace
audit 0. Portable 1,302; game 262 + 1 golden re-pinned (mi 23931
FPSDisplay.Update: `object obj10 = 1000.0f / real11` -> `float real13`).**

**Status: RE-PINNED 2026-10-06 (user-approved). The 39 moved
goldens/pins (21 goldens in `tests/goldens_review84.json` via
`work/cg8/repin_goldens.py`, 18 pin assertions in 13 test files) were
updated to the reviewed fix 125-134 output, with each test's intent kept.
Notable: the fp32 binary-op pin now requires both operands
(`(float)sub_180001cf0((float)(numN), 0.0001f)`); review87 accepts
`new System.NotImplementedException()`; review88 drops the
no-longer-emitted metadata-init check and keeps the no-bare-`throw;`
guard plus the concrete `ArgumentOutOfRangeException("level")`. Suites:
game 263 passed / 0 failed (11:36), portable 1,294 passed. Next slice:
CS0019 `object op int` (untyped integer temps).**

**Status: LANDED on `main` and pushed 2026-10-06 (`8b2d724`, fast-forward;
user call -- one branch, no split branches/worktrees from here on).
`final_out/` not promoted; goldens and pins NOT re-pinned (user call).**
Historical chain (branches deleted after the fast-forward):
`fix125-compile-gate-scope` -> `fix126-unknown-phi-copies` ->
`fix127-publicize` -> `fix128-raw-addr` -> `fix129-vtable-usage-decode`
-> `fix130-init-meta-value` -> `fix131-block-flags` ->
`fix132-entry-live-args` -> `fix133-generic-class-layout` (worktree
`%TEMP%\opencode\wt131`). Fix 134 (load widths) was done directly on
`main`. Latest gate `work/cg8/b8` (through fix 134):
**499,479 errors (-329,092 / -39.7% vs r_base)**; b6 (through 133)
501,046; b3 (through 132e) 505,396. Handoff + standard procedure:
`docs/handoff-2026-10-06.md`.

Gate (`work/cg5/`, chain through fix 130, `--strict --publicize
--raw-addr`, 10 groups, 0 failed / 0 fallbacks / 0 type-emit failures,
11,262 files): **828,571 (r_base) -> 515,786 errors (-312,785, -37.7%)**,
declaration-tier 1,232 -> 739. Step counts (whole-tree gates):
cg2 fix 125 727,579; cg3 +fix 126 699,602 (-27,977); cg4 +fix 127
`--publicize` 633,078 (-66,524); cg4r = cg4 post-processed with the fix
128 rewrite 554,297 (-78,781, estimate); cg5 real build 515,786 (-38,511
vs cg4r: CS0103 -15.5k, CS1061 -9.5k, CS0191 -6.7k (readonly drop),
CS0149 -4.4k, CS1955 -2.6k). Remaining top: CS0103 128k, CS0019 82k,
CS0266 66k, CS1061 66k, CS0029 52k, CS1503 43k.

1. **Fix 126 -- phi copies never read an unknown register**
   (`dec/analyze.py` `_unknown_phis`, greatest fixed point): an in-edge
   whose value is `_unk` or an all-unknown phi gets no copy (`phi = vN;`
   read a name nothing defines). The phi stays unassigned on that path
   and the compiler says so (CS0165) only if a read can see it. cg3:
   CS0103 -24.8k, CS0165 -1.4k. Tests `tests/test_fix126_unknown_phi_copies.py`.
2. **Fix 127 -- opt-in `--publicize`** (emitter): every member public,
   fields drop `readonly` (CS0122 87.5k -> 300; CS0191 then 0). Gate mode
   only; default output byte-identical.
3. **Fix 128 -- opt-in `--raw-addr`** (`il2cpp/rawaddr.py`): `(byte*)E`
   outside literals/comments becomes `(byte*)__addr(E)`; `__RawAddr.cs`
   (internal static unsafe overloads for void*/long/ulong/IntPtr/UIntPtr,
   `object` throws NotSupportedException) is written per assembly when
   used. CS0030 112.8k -> 3.5k. Tests `tests/test_fix128_raw_addr.py`.
4. **Fix 129 -- vtable rows are metadata usages** (`runtime/types.py`
   `vtable_method`/`slot_max_arity`): usage-6 (MethodRef) rows index
   methodSpecs (8,846 rows were decoded as MethodDefs; 64 agreed), empty
   rows (1,523) name the unique instance method carrying that metadata
   `slot` on the type or an ancestor (0 ambiguous). System.Xml A/B:
   `/*vtable slot N*/` sites 2,330 -> 100. **129b** (`lifter/calls.py`):
   a slot declared on the receiver's own generic definition binds class
   VARs from the receiver's GENERICINST args, so `Comparer<float>.Compare
   (T, T)` reads XMM1/XMM2 (Computer.ShouldRankBefore). Tests
   `tests/test_fix129_vtable_usage_decode.py`, `tests/test_game_fix129_generic_slot_args.py`.
5. **Fix 130 -- the initialize_runtime_metadata jmp thunk returns its
   slot item** (`lifter/calls.py`; disasm EnumBuilder.GetMembers
   0x181BD4E80: `lea rcx,[slot]; call 0x180435420; mov rcx,rax; call
   il2cpp_object_new`): RAX carries the slot expression, so allocations
   read `new T()` instead of `il2cpp_object_new(objN)`. The name-path
   `il2cpp_array_new` result now binds one identity via
   `_array_allocation` (was re-printing `new object[1]` at every use).
   Test `tests/test_game_fix130_init_meta_value.py` (System.IO.__Error.WinIOError).
6. **Fix 131 -- per-block condition flags** (`dec/analyze.py`,
   `lifter/values.py`; branch `fix131-block-flags`): `L.flags` was
   lifter-global, so a pass-2 block opened with the flags of whichever
   block executed last (Computer.ShouldRankBefore mi 24622 0x18069C7A0
   `setg al` printed `return num1 >> 31 > 0` instead of
   `Compare(...) > 0`). Each block now records its end flags (a jcc
   stashes the pair it consumed in `L._jcc_flags`); a block restores a
   pair only when it reads a flag before defining one (`_flags_live_in`,
   iced `rflags_read`/`rflags_modified`) and every done predecessor
   agrees (`_flags_key`); entry / orphan blocks start with None. The
   restored operands are private copies (`_restored_pair`) unless the
   operand is one whole call (`_top_call`), so a successor's reads never
   bind a loop-header Expr into the body (KeybindsManager.Update `for (i
   = 0; i < objN; ...)` with objN assigned inside) while `Compare(...)`
   still binds once. A register write that kills a carried pair drops
   it instead of materializing an `object objN = <cond>` twin
   (`L._carried_flags`, `_kill_stale`); `_kill_stale` also never freezes
   the `!flags` merge sentinel (its `lhs<0x01>rhs` text became an
   `object objN = op_Implicit(...)` twin). Without the live-in gate the
   extra sentinels drew pass-2 phi numbers and shifted clobber
   placeholders against pass 1 (undeclared `sub_180434660(..., obj36,
   obj37)` in AudiencePath.DrawCurved).
   Assembly-CSharp A/B: `unknown == unknown` conditions -111 (now e.g.
   `realN == 0f`); ShouldRankBefore reads `int num1 = Compare(...); if
   (num1 != 0) return num1 > 0;` (was an undeclared `num1`). Test
   `tests/test_game_fix131_block_flags.py`.
   **131b**: `_restored_pair(None)` raised TypeError (method fell back to
   unstructured `if (? <= ?) goto`, cg6 517,994 = +2,208 vs cg5 with
   CS1525 +2.1k / CS1003 +0.7k in Unity.Mathematics); it now returns
   None, and a block that writes no flag passes its predecessor pair
   through (`math.uint2(float)` mi 68399 `if (0f <= v)`).
   Gate `work/cg7/` (chain through 131b, same flags, 11,262 files,
   0 failed / 0 fallbacks): **513,959 (-1,827 vs cg5; -314,612 / -38.0%
   vs r_base)**: CS0103 -2,383, CS0019 +441, CS0029 +102 (conditions that
   were `unknown` now carry real typed operands and surface type errors).
7. **Fix 132 -- entry-live arguments for plain `sub_` callees**
   (`il2cpp/entrylive.py` new, `lifter/calls.py`, `lifter/insn.py`;
   branch `fix132-entry-live-args`). A `sub_VA` call with no metadata
   candidate and no export printed the 4-GPR spray (`sub_1804d05a8(v,
   obj2, obj3, obj4)`), dropped XMM arguments and assumed an RAX result
   (`return obj5 * 57.29578f`). Probe: 15,983 CS0103 sat in `sub_`
   arguments, ~5.7k in positions the callee provably never reads.
   `entry_live_args(il, va)` walks the callee's extent (iced
   InstructionInfo) for read-before-write of RCX/RDX/R8/R9/XMM0-3: only
   full writes define (8/16-bit GPR writes do not; low-lane scalar
   writes `movss/movsd/cvt*/sqrt*/round` with src != dest define the XMM,
   132c); direct calls/jumps out of extent recurse (memoized, depth 10,
   order-independent); an unprovable call makes every still-undefined
   register live; indirect branches, tail jumps to unprovable targets,
   falling off the extent, untrackable RSP math and stack-argument reads
   (entry offset >= 0x28) decline (None). The call prints position i as
   the GPR or the XMM the callee reads, `0` for a dead interior
   position, and keeps the spray when a position reads both, the value
   is unknown, or the text cannot parse (132e: `GenericMethod#N`
   placeholders, bare `?`). **132b/d** `xmm0_result_width`: the caller's
   next uses decide a float/double XMM0 result (scalar SS/SD reads, RMW,
   packed PS/PD sources, whole-register copies followed across a later
   call into XMM6+; any RAX touch, untyped read, branch or ret
   declines), giving `float real1 = (float)sub_...(...)`.
   **132e** (`lifter/insn.py` `_unary_txt`): NEG/NOT shared one
   `'-%s'` spelling -- NOT printed as negation, `-(-x)` as the
   predecrement `--x` (FrameRate CS1059), `-(a + b)` as `-a + b`. NOT is
   now `~`; a composed, sign-led or space-bearing operand is
   parenthesised.
   Examples: GetAngleDeg mi 28756 `float real1 = (float)sub_1804d05a8(v.x,
   v.z); return real1 * 57.29578f;`; PathProcessor
   CalculatePathsThreaded `path3.duration = real1` from
   `(float)sub_180001cf0((float)(num3), 0.0001f)` (native `mulss
   xmm0,xmm1; ret`; was `sub_180001cf0(obj48, obj49, obj50, obj51)` and
   `= unknown`); EncodingTable `sub_18032f5e0(arr, 57, &obj24)` (native
   reads RCX/EDX/R8; the junk 4th argument is gone).
   Gates vs cg7 513,959: b1 (132a-c) 505,586; b2 (+d) 505,230; **b3
   (+e) 505,396 (-8,563)**: CS0103 -8,790, CS0023 -264, CS0165 -144,
   CS1059 8 -> 0; up CS0019 +399, CS1503 +244, CS0029 +99 (sampled:
   newly visible -- e.g. `&obj24` to an `object` stub parameter was
   masked by the undeclared 4th argument). b1/b2 had +1 CS1026/CS1003/
   CS1040 (placeholder argument) -- fixed by 132e, back to baseline.
   b3 gives back ~170 vs b2 by declining unparsable arguments (P4).
   Tests `tests/test_fix132_entry_live_args.py` (17),
   `tests/test_fix132e_unary_and_xmm_args.py` (5),
   `tests/test_game_fix132_entry_live_args.py`.
   **Pin move (review for re-pin):**
   `test_game_fp32_unary.py::test_binary_op_keeps_honest_spelling`
   asserts the old `object objN = sub_180001cf0(` spray. Its intent --
   never drop the XMM1 input into a wrong unary float -- holds: the call
   now carries both inputs and a float result, matching native.
8. **Fix 133 -- open generic class layouts** (`runtime/fields.py`,
   `lifter/values.py`; branch `fix133-generic-class-layout`, from
   `fix132-entry-live-args`). IL2CPP stores all-zero instance offsets for
   an open generic definition, so `instance_field_chain(List`1)` was
   `{0x0: _items}`: the object header was misnamed and `_size` (0x18)
   never resolved -- 105,592 `((byte*)__addr(B) + off)[0]` raw derefs in
   b3, many of them collection reads. **133a** `_class_level_offsets`:
   an all-zero class level whose instance fields are argument-invariant
   (primitives, string, pointers, class/array/object references, class
   GENERICINST, byref) is laid out the IL2CPP way -- parent instance end,
   declaration order, natural alignment; by-value VAR/struct fields or
   explicit layout decline (the level then names nothing, never offset
   0). Validated (`work/cg8/layoutval.py`): 4,984/4,985 non-generic
   classes and 4,732/4,743 value types reproduce their real offsets
   (misses: Pack=4 structs, excluded by the rule); 6,179 recorded class
   sizes equal the reconstructed end. List`1 = {0x10 _items, 0x18 _size,
   0x1c _version, 0x20 _syncRoot}. **133b** `_recv_member_ty`: the
   chain carries the definition's field type (`T[]`), which leaked an
   unbound `T` into caller declarations (b4: CS0246 'T' +322). A member
   type mentioning class parameters is kept only when all belong to the
   receiver typedef's own container -- closed through a GENERICINST
   receiver (`_subst_closed`; `T[]` reuses the binary's closed array
   row, or `object[]` for a reference element with no row -- array
   covariance), or left in scope for the definition's own `this`; base
   level parameters, MVARs and unclosable arguments drop the type but
   keep the member and its kind (`T[]` stays 'arr'; a dropped type
   once fell through to 'int' and printed `int num2 = x._items`).
   Examples: AudiencePath.SpawnPeople mi 23555 (0x1804FEDF0) `int num1 =
   list11._size - 1;` (native `mov ebx,[rdi+18h]`); TMP_FontAsset
   TryAddCharacters mi 95397 `UnityEngine.TextCore.Glyph[] glyphArray1 =
   this.m_GlyphTable._items;`; ObiColliderWorld `object[] objectArray1 =
   this.implementations._items;`.
   Gates vs b3 505,396: b4 (133a) 501,289; b5 (+133b) 501,289 (CS0246
   -360, but CS0029 +186 from the 'int' kind fall-through); **b6 (+kind
   fix, object[] fallback) 501,046 (-4,350; -327,525 vs r_base, -39.5%)**.
   b6 vs b3: CS0019 -3,008, CS1503 -949, CS1061 -475, CS0266 -315,
   CS0246 -7; up CS0214 +367 (a method whose raw derefs are now named
   loses its `unsafe` cover while a leftover `&local` still needs it --
   `textpass` keys unsafe wrapping on raw derefs, not on `&`; follow-up),
   CS0103 +30, CS0021 +19 (newly typed arrays indexed with pre-existing
   junk indices, e.g. `obj19[num2 * 3]`). Brace audit 0 unbalanced; no
   parse-code increase. Tests `tests/test_fix133_generic_class_layout.py`
   (5), `tests/test_fix133b_member_type_scope.py` (8),
   `tests/test_game_fix133_generic_class_layout.py` (3). Portable 1,285
   passed.
   **Pin move (review for re-pin):**
   `test_game_review80.py::test_direction_dispatch_is_not_dropped_from_draw_curved_loop`
   anchors its loop slice on `if (((byte*)this.pathPoint`; mi 23566
   (PeopleWalkPath.DrawCurved) now reads `if (this.pathPoint._size >=
   2)`. Loop content unchanged (all six direction strings, both
   `this._forward[num2] = true/false`, no goto).
9. **Fix 134 -- raw loads keep their native width** (on `main`;
   `lifter/insn.py`, `dec/textpass.py`, `dec/sugar.py`,
   `lifter/state.py`). `textpass._unsafify` spelled every width-less
   `*(E + N)` as `((byte*)E + N)[0]` -- a 1-byte read in C# where native
   loads 2/4 bytes (a correctness bug, not only a type error). **134a-d**
   `_width_mark`: a whole single raw field load `[base+disp]` (no index;
   base a plain identifier/member chain, not an array/string receiver)
   whose expression has no type is wrapped as `(__w_T)*(...)` with T from
   the instruction (`_W134`: MOV r32 -> int, MOV r16 -> short, MOVZX
   word -> ushort, MOVSX byte/word -> sbyte/short, MOVSXD -> int,
   CMP/TEST mem32/16 -> int/short) and typed int; byte zero-extends and
   qwords stay unmarked. `textpass._widen_marked` spells it
   `((T*)((byte*)E + N))[0]` (byte-addressed displacement, as fix 124
   stores); leftover markers are stripped. A first version that marked
   every read form (b7 501,045, net -1) hid index-form reads (interface
   offset tables) and `*(arr + 0x18)` `.Length` reads from later text
   folds -- hence the field-form-only scope. **134e** `_member_fold`'s
   stale-receiver-paren strip `(?<![\w.])\((tok)\)\.` also fired on a
   generic call's argument paren (pre-existing, b6 already had
   `FindObjectsOfType<TMP_Dropdown>true.Length`); `(` glued to `>`, `)`
   or `]` is now left alone. **134f** the oversized-temp spill comment
   (`var vN = 0; // <expr>`, `state._mk`) is opaque to textpass, so the
   lifter strips markers there itself.
   Examples (native-verified): TouchscreenStateEvent OnStateEvent mi
   32833 (0x18264A0D0) `mov ebx,[rax+14h]; cmp ebx,eax` ->
   `int num2 = ((int*)((byte*)inputEventPtr2 + 0x14))[0];` compared with
   `TouchState.Format`; KeybindsManager.Update mi 25872 (0x180547380)
   `call unbox; mov esi,[rax]` -> `int numN = ((int*)((byte*)objN +
   0x0))[0];`.
   **Gate b8 vs b6 501,046: 499,479 (-1,567)**: CS0019 -1,221, CS1503
   -722, CS0266 -668, CS1061 -142, CS0103 -104, CS1579 -49 (134e),
   CS0119 -25; up CS0029 +1,310 -- cascade unmasking: temps that were
   `int* intPtr1 = this._object.Ptr` (Fusion RPC stubs) now type as
   `NetworkId`, so `RpcHeader.Create(networkId1, ...)` binds and the
   pre-existing struct-store width error `((byte*)__addr(msg) +
   0x1c)[0] = RpcHeader.Create(...)` surfaces (RpcHeader->byte +405,
   int*->struct +464, int->struct +571; embedded-struct stores are a
   listed follow-up); CS0021 +29, CS0023 +21, CS0165 +18. No parse-code
   increase; brace audit 0 unbalanced. Tests
   `tests/test_fix134_load_width.py` (9),
   `tests/test_game_fix134_load_width.py` (3). Portable 1,294 passed.
   **Pin moves (review for re-pin)** -- all temp renumbering from a new
   int temp, plus width-correct reads:
   `test_game_fix131_block_flags.py::test_restored_operands_do_not_bind_the_loop_bound`
   (the loop variable is now `num6`; the bound is still
   `UnityEngine.Object.FindObjectsByType<ChangeTextToKeybind>(FindObjectsSortMode.None).Length`,
   never `obj`); golden `mi-80548-Execute` (`int num5 = ((int*)((byte*)num4
   + 0x18))[0];` hoisted and reused for both index reads and the store;
   the qword `>> 32` reads stay byte-spelled); golden/pin mi 32833
   (`review80::test_touchscreen_condition_is_recomputed_in_the_loop`: its
   `num7 = unknown + this.currentStatePtr` marker is now `num8`, and the
   compare reads `((int*)((byte*)num5 + 0x0))[0]`).

Game suite (run in worktrees; `cli_only`, `decl_gate`, `compile_gate`,
`parallel_build` fail there for path reasons -- relative `testgame`,
no `final_out/` -- and pass in the main checkout): beyond fix 125's 22
known failures, fix 126 moves goldens mi 0, 21027, 128953 and pins
`elemclass::test_unknown_provenance_declines`,
`iface_param::test_resolved_string_result_null_tests_null`,
`interface_dispatch` x2, `null_zero::test_object_zero_keeps_zero` --
reviewed: temp renumbering and dropped unknown copies only. Fix 129 moves
golden mi 83647 (`type.AssemblyQualifiedName` for a `/*vtable slot 25*/`
call) and pin `isinst_tail::test_tail_typeof_folds_to_as` (mi 3446 now
`element.GetCustomAttributes(...) as Attribute[]` and `element.MemberType`
compares). Fix 130 moves pins
`review87_eh_helpers::test_pad_less_caller_renders_the_proven_helper_as_a_throw`
(mi 106196 now `object obj1 = new System.NotImplementedException(); throw
obj1;` -- the test looks for `obj1 = il2cpp_object_new(`) and
`review88_eh_helper_set::test_metadata_init_is_not_flattened_to_a_throw`
(mi 77946 GetTraceEventType no longer prints an
`il2cpp_codegen_initialize_runtime_metadata(` statement; still no bare
`throw;` and still `throw obj3;` of `new ArgumentOutOfRangeException("level")`).
wt131 game suite: 39 failed = wt129's 37 + those two. With fix 132a-e
(`work/cg8/game132.out`): 40 failed = those 39 + the fp32_unary pin move
above (no other changes). With fix 133 (`work/cg8/game133*.out`): 41
failed = those 40 + the review80 anchor move above. Fix 134, main
checkout (`work/cg8/game134.out`): 39 failed = those 41 minus the 5
path-only tests (they pass in the main checkout) + the 3 fix-134 moves
above. All need a user-approved re-pin.

**Next-slice probe (CS0019, b3; `work/cg8/cs0019.py`, `objdefs.py`):**
34,689 CS0019 have an `object` operand. Shapes: 6,443 are
`__addr((objN + 0x80))` frame/struct bases (`objN := &local | (objN +
0x80)`); ~25k are `object objN` temps used as numbers. By definition
(12,098 distinct method/temp pairs): raw deref 3,016 (e.g.
`((byte*)__addr(this.m_Items) + 0x18)[0]` -- a List `_size` read),
arith 2,061, call 847, temp copy 703, int literal 601, mixed rest.
Root cause worth fixing first: `textpass._unsafify` spells every
width-less `*(E + N)` as `((byte*)E + N)[0]`, which in C# is a 1-byte
read while native loads 4/8 bytes -- a correctness bug, not only a
type error. Options: (a) the lifter spells the load width at the deref
(`((int*)((byte*)E + N))[0]`; insn.py already does this for typed
wide accesses, lines ~2015-2047), then temps typed from it; (b) resolve
generic-instance fields (`List<T>._size` at 0x18) so the deref never
exists. Either moves many goldens -- needs a user call on approach.
(Done: (b) is fix 133, (a) for field-form loads is fix 134.)

Follow-ups seen while landing: CS0019 `object op int` (untyped integer
temps, 82k); CS0165 phi arms minted under different names; `unknown`
SIMD lane placeholders (`unpcklps` + `movsd` into Vector3 fields);
indirect calls `X[0]() /*indirect*/(args)` (CS0149 9.4k).

## Current work: fix 125 compile-gate first slice (2026-10-05, branch `fix125-compile-gate-scope`)

**Status: on branch, not merged/promoted. Goldens NOT re-pinned (user call).**
First use of the P1 Roslyn compile gate as the primary metric.

Gate tooling (all git-ignored scratch in `work/cgate/`):
- `work/cgate/rgate/` -- per-assembly Roslyn gate (SDK 10.0.302 Roslyn
  DLLs; one `CSharpCompilation` per image wired by CompilationReferences
  in topological order from `deps.json`, mscorlib as corlib,
  `__Generated` referenced by all). Run:
  `dotnet work\cgate\rgate\bin_out\rgate.dll <flat tree> work\cgate\deps.json <outdir>`
  (~13 s whole tree) -> `log.txt` + `summary.json`.
- `work/cgate/deps.py` (image reference graph), `cmp.py` (per-code
  before/after), `top.py`, `sample.py`, `initshape.py` (shape census),
  `undecl.py` (CS0103 temp classifier), `launch.ps1 -Out <dir>` (10
  balanced per-group strict builds) + `merge_gate.ps1 -Out <dir>` (merge
  to `flat`, run gate, compare against baseline).
- Baseline `work/cgate/r_base/` (main @ d97dd15, 91 images, 11,107
  files): **828,571 errors** (1,232 declaration-tier). Top: CS0103 283k,
  CS0030 106k, CS1061 95k, CS0122 86k, CS0019 73k, CS0266 47k.

Landed on the branch (three source slices + tests):
1. **Escaping-local hoist** (`il2cpp/dec/build.py`
   `hoist_escaping_locals`, run after `_final_text`): a minted local
   (name ends in a digit, single declared type, not a param/pattern/
   loop/lambda name) whose uses are not all inside a scope that declares
   it earlier gets one bare `T name;` at the top of the lowest common
   block (never inside a switch block) and its inner declarations become
   assignments. No `= default` -- a path the native code never assigns
   stays visible as CS0165. Prototype on the baseline tree: 46,339
   hoists, CS0103 -57.9k, CS0136 -3.2k, CS0841 -2.3k, CS0165 +9.6k
   (honest unassigned reads, mostly phi arms minted under different
   names), and newly bound names surface ~+15k type errors
   (CS0030/CS0266/CS1503/CS0019) that were masked behind CS0103.
2. **Empty class-init guard drop** (`drop_empty_init_guards`):
   `if (typeof(X).initialized ==|!= ident|0) { }` with an empty body and
   no `else` is a no-op flag read; 24k+ sites (CS1061 on `Type`).
   Guards with a body are untouched (`_class_init_strip` still owns them).
3. **Callee-side hidden sret buffer** (`lifter/state.py` setup):
   methods that return a large struct now seed RCX as `&__ret`
   (slot type = return type), so stores through it fold to
   `__ret.field` via the existing `&s_N` valuetype path, the
   `mov rax,rcx` echo returns `return __ret;` (`dec/analyze.py`), and
   `_sret_local_decl` declares `T __ret = default;` once (mirrors the
   caller-zeroed buffer). Previously every such body read an undefined
   register (`((byte*)obj2 + 0x0)[0] = obj1; return obj2;`, mi 24266
   BabyDoll.get_NetworkedPosition; Unity.Mathematics swizzles).
   Guard added in `lifter/values.py`: an access WIDER than the member
   it starts at (`movsd [rcx],xmm0` = Vector3.x+y) keeps the raw deref
   instead of naming only the first field (this also applies to the
   caller-side `&s_N` echo -- correctness, P4).
- Tests: new `tests/test_scope_repair.py` (6).

Gate results (whole tree `work/cg1/`, see `work/cg1/cmp.txt`):
- Build `work/cg1/` (all three slices, BEFORE the `__ret` decl-guard
  fix below): 10 strict groups, 0 failed bodies / 0 fallbacks / 0
  type-emit failures, 11,183 files. **828,571 -> 761,086 errors
  (-67,485, -8.1%)**, declaration-tier 1,232 -> 1,217. CS0103
  283,183 -> 216,428; CS1061 95,250 -> 72,869; CS0136 3,668 -> 60;
  CS0841 2,824 -> 39; CS0165 147 -> 10,754 (honest unassigned reads);
  masked type errors surface: CS0030 +5.5k, CS0266 +3.5k, CS1503 +2.8k,
  CS0019 +2.3k, CS0029 +2.0k.
- Bug found in that build: `_sret_local_decl`'s "already declared"
  guard matched `return __ret;`, so `T __ret = default;` was never
  emitted (47,626 errors in `work/cg1` name `__ret`). Fixed on the
  branch (guard excludes `return/throw/goto`); mi 24266 relift now
  declares it.
- **Rebuild `work/cg2/` (branch HEAD, all slices + guard fix), 2026-10-05:**
  10 strict groups, 0 failed / 0 fallbacks / 0 emit failures, 11,183
  files. **828,571 -> 727,579 errors (-100,992, -12.2%)**; vs cg1
  -33,507. CS0103 283,183 -> 168,802; CS1061 95,250 -> 72,897;
  CS0136 -3.6k; CS0841 -2.8k; CS0165 147 -> 10,754; surfaced CS0266
  +11.5k, CS0029 +6.2k, CS0030 +5.5k, CS1503 +3.0k, CS0019 +2.5k
  (statements that now bind far enough to show type errors).
- Game suite re-run on the guard-fixed source (2026-10-05): **220
  passed / 22 failed -- the identical 22** (16 goldens + 6 pins listed
  below); nothing new broke. Still NOT re-pinned (user call).
- Portable suite: 1,229 passed. Game suite (run on the cg1 source):
  220 passed / 22 failed -- **16 goldens** (mi 5769, 11974, 26747,
  32832, 32833, 32837, 37191, 39789, 42414, 45016, 64986, 70050, 75101,
  86310, 104428, 109664 list in `work/cgate/pt2.out`) and 6 text pins,
  all expected spelling changes from this fix, NOT re-pinned (user call):
  `test_game_fp32_unary`/`test_game_jcc_flag_chain` audio x4 (pin
  `float real2 = ...` now hoisted `float real2;` + `real2 = ...`),
  `test_game_single_field::test_timespan_assign_folds_to_whole`
  (hoisted `System.TimeSpan timeSpan2;`), `test_game_review81` packed
  lanes (raw base is now `&__ret` instead of undefined `obj3`). Every
  golden diff must still be read line by line before re-pinning, and
  the game suite re-run after the `__ret` guard fix.

Next (ranked by gate yield, from the baseline census):
- C6/C1 never-defined register temps (~120k CS0103): phi copies of
  undefined registers (`object obj6 = obj7;`, 56k) and spray args of
  shared/ICF calls (28k). Root-cause in phi seeding, not text.
- C5 rest: `il2cpp_codegen_initialize_runtime_metadata(...)` assignments
  (8.5k CS0103; e.g. `object obj1 = ...(typeof(NotSupportedException));
  il2cpp_object_new(obj1)` should read `new NotSupportedException()`),
  `il2cpp_object_new` 3.3k, `mono_object_unbox_internal` 2.5k,
  `il2cpp_interface_get_method` 2.4k, `typeHierarchyDepth` 2.8k,
  `__static_fields`.
- C4 `X -> byte*` raw casts (CS0030 ~106k): compilable raw helper.
- C10 private member access across types (CS0122 86k): emit-side
  accessibility relaxation or accessor routing.
- `get_Chars`/`.ctor`/`getClass` sugar (CS1061 ~20k), C8 generic
  spellings (`Dictionary_2<...>`).
- Phi arms minted under different names (new CS0165s): unify names.
- Lane coalescing (C3): 8-byte movsd copies of two float fields.

## Previous work: fix 124 wide-store byte offsets (2026-10-04, DONE on branch)

**Status: complete on branch `fix124-wide-store-byte-offsets`.** Source fix,
tests, goldens and the full gate set landed together; evidence in
`validation_reports/review124_*` (raw artifacts in the git-ignored
`work/fix124_ab/`). Next up is the compiler-error backlog below.

- Native re-check of all 8 affected MethodDefs: every re-spelled store's
  byte offset equals the native memory displacement; each pre-fix typed
  spelling wrote `offset * sizeof(T)` (mi 25626 byte 0x20, 26747 0x90,
  32837 0x40, 75101 0x20/0x50/0x80, 109194 0x10/0x20/0x30, 128953 0x80;
  1935 is offset 0 and spelling-only).
- Paired strict `--only Assembly-CSharp` builds (main source from
  `git archive HEAD` vs branch; both 490 files / 6,622 bodies / 0 failed
  / 0 fallbacks / 0 type-emit failures): 155 files, 1,701 changed lines,
  **every changed line a pure fix-124 reshuffle, 0 unexpected, 0
  line-count deltas**; brace 0 unbalanced; parse 0/0/0/0.
- Whole tree (91 images, 11,183 unique files, built as 10 balanced
  concurrent per-image runs because this sandbox denies the `--workers`
  process pool): brace 0 unbalanced, parse 11,183 files 0/0/0/0.
- Paired whole-corpus direct sweep (116,178 bodies): 0 crashes, brace
  0/0, dangling 0, empty-args 0, `into_block` 8,075/2,046 unchanged;
  main-vs-branch compare 9,339 changed methods, **0 structural changes,
  0 new crashes**; purity proof 9,339/9,339 pure fix-124 (9,313 by exact
  canonical-body hash, 26 by fresh-process line-pair comparison).
- Goldens: 64 snapshots, 59 unchanged, 5 re-pinned (26747, 32837, 75101,
  80548, 128953) -- every diff line read and confirmed pure fix-124.
- Suite: 1,463 passed / 2 failed of 1,465 (portable 1,223 + game 242);
  both failures are this sandbox's named-pipe denial for
  `test_game_parallel_build.py`, reproduced by a three-line
  `ProcessPoolExecutor(2)` call with no il2cpp code involved (see
  `validation_reports/review124_environment.json`).
- Unrelated untracked `.freebuff/` in the worktree: not ours, leave it.

Branch `fix124-wide-store-byte-offsets`. Fix 102/103's
wide display rendered `((T*)E + N)[0]`; C# pointer arithmetic scales N
by sizeof(T), so every non-byte raw store wrote the wrong address.
Native proof (fixture): mi 24267 `BabyDoll.set_NetworkedPosition`,
`0x18060cdaa mov [rcx+8],eax` rendered `((float*)this.Ptr + 0x8)[0]`
(= byte 0x20). Census: 1,636 such store lines in fixture r11
Assembly-CSharp alone. Parse/brace gates could never see it.

Landed on the branch:
- `il2cpp/lifter/insn.py` `_wide_store_disp` / `_wide_rmw_disp`:
  emit `((T*)((byte*)E + N))[0]` (indexed: `((T*)((byte*)E + i*s + N))[0]`),
  the same shape `_wide_raw_lvalue` already used. CRLF binary patch.
- `il2cpp/text.py` `_canon_wide_cast`: strips a whole-span inner
  `((byte*)...)` so `_norm_twin` still meets the raw barrier twin
  `*(E + N)`; a byte-cast READ base (`((byte*)b + 0x10)[0] + N`) is
  untouched.
- Tests: 7 end-to-end pins repinned in
  `tests/test_review102_raw_store_widths.py` (input-only canon/unsafify
  tests keep the old spelling as valid input); new
  `tests/test_fix124_wide_store_byte_offsets.py` (+6: address shape,
  canon strip, byte-load-base decline, twin bridge, unsafify fixpoint).

Repins landed with the fix: the 3 non-golden failures were old-spelling
pins only (`test_game_param_names[1935]` `((uint*)v1 + 0x0)`,
`test_game_review81::test_packed_float_intrinsic_...` (mi 109194; its
0x4/0x8/0xc lanes were bytes 0x10/0x20/0x30 under the old spelling),
`test_game_rpc_payload::test_stores_use_typed_widths_...`), plus the 5
goldens (mi 26747, 32837, 75101, 80548, 128953). Portable suite 1,223
passed; `work/fix124_ab/golden_diff.txt` holds every golden diff line,
and `work/fix124_ab/purity.json` + `pair_purity.json` the corpus proof.

Two process notes for the next fix, both paid for here:
- `--workers` cannot run in this sandbox (named-pipe denial). Multi-image
  builds must be split into per-image/per-group processes; a single-image
  `--only` build silently takes the serial path, so it is *not* evidence
  that the pool works.
- The whole-body "canonicalize the new body and hash it" purity method is
  unsound when pre-existing `((T*)((byte*)E + N))[0]` lines from
  `_wide_raw_lvalue` are present in both sources; it over-strips them.
  Use the line-pair predicate (only *differing* pairs must reduce to the
  other side), which is sound and found 0 real deltas.

Known sibling (not fixed here): an 8-byte `movsd qword [rcx], xmm0`
store of two float lanes renders `((byte*)this.Ptr + 0x0)[0] = value.x;`
(mi 24267, first store) -- width and the y lane are lost. See C3.

## Compiler-error backlog (2026-10-04, PLAN)

The promotion gates (brace, tree-sitter parse, goldens, 0 failed
bodies) measure parseability, not compilability. On a second, larger
external Unity 6 corpus (Assembly-CSharp, 8,617 type files / 60,518
bodies, 0 failed; NOT tracked, never redistribute) the emitted tree
carries ~498k Roslyn errors across 5,358 files while every gate is
green. Top codes: CS0103 78.9k, CS0030 38.6k, CS1061 25.9k, CS1503
21.0k, CS0122 12.8k, CS0019 12.6k, CS0029 11.1k, CS0246 8.1k, CS0266
5.9k, CS0571 5.8k, CS0208 5.8k. Raw-text census of that tree: 96.9k
`(byte*)`, 80.4k `((T*)X + N)` sites (45.0k named/param/field
receivers, 32.7k temps, 2.7k `this`), 2,153
`il2cpp_codegen_initialize_runtime_metadata`, 701 `__static_fields`,
4,943 `sub_`, 3,496 `unknown`, 5,638 `goto`.

Process changes (do first):
- P1. Roslyn compile gate as the primary metric: per-rebuild census by
  CS code + message pattern, failure SET tracked like the test-failure
  set. A fix lands only if its family count drops with goldens/tests
  green. Note csc reports body errors only after declaration errors are
  zero -- clear the declaration tier first or the count is misleading.
- P2. Add a second, larger fixture (licensed) so families that barely
  occur in ShiftAtMidnight are exercised (see C1).
- P3. One agent per error family, 4-6 in parallel max, worktrees, same
  landing protocol. `dec/structure` pass order matters and goldens regen
  serializes; more parallelism mostly produces conflicts.
- P4. "Compiles" never outranks "correct": every fix still needs native
  proof; decline-by-default stays. Don't make code compile by guessing
  casts.

Families, by expected yield:
- C1. Shared/ICF call naming (largest CS0103 driver). In the external
  corpus 92% of sampled undeclared `obj#`/`num#` sites (552/597, files
  untouched by hand) are spray args of one shape:
  `Unrelated_1<bool>.SomeMethod(this, Base_1<TModel>.ctor, obj1, obj2);`
  (anonymized; the external tree is never quoted verbatim)
  inside a ctor that should be `: base()` with an empty body. The jump
  target is a shared (ICF-folded / generic-shared) body; naming by VA
  picks an unrelated owner, while the hidden MethodInfo* arg (RDX/last
  arg, kind `methodinfo`) names the true target. ~10.2k trailing-spray
  sites, ~4.0k `.ctor`-as-value sites. The fixture renders its single
  instance honestly (`sub_180de4fa0/*shared body, 229 candidates*/`,
  mi at VA 0x18061FDB0, FEngineering), so some path (suspect the dec
  direct-tail `_emit_tail` path, cf. slice 2b) bypasses the candidates
  check. Fix: resolve the callee from the methodinfo arg when present,
  drop it and spray beyond the resolved arity; base-ctor tail ->
  `: base(...)`. Also fixes many CS1061/CS1503/CS0117.
- C2. Field resolution for raw offsets, including interior offsets into
  value-type fields (recursive: 0x18 inside a Vector3 field at 0x10 ->
  `.field.z`). Must happen at Expr/lifter level where types live,
  not in textpass. Biggest share of CS0030/CS0208.
- C3. Lane coalescing: split SIMD/qword stores of one struct value
  (`movsd [rcx],xmm0` + `mov [rcx+8],eax`) -> one struct assignment
  (`this.f = v;`), and never emit a lane into a struct-typed field
  (`this.f = v.x;` -> CS0029). Fixture repro: mi 24267.
- C4. Compilable raw fallback: C# cannot cast a managed reference to a
  pointer, so every residual `((T*)ref + N)` is CS0030 regardless of
  fix 124. Emit a declared helper (e.g. `Il2CppRaw.Ref<T>(obj, 0x18)`
  over `Unsafe.As`/`Unsafe.AddByteOffset`). Honest and compiles; track
  the helper count as debt -- IL2CPP vs Mono object layouts can differ,
  so these sites may be wrong at runtime.
- C5. Runtime-bookkeeping removal: `il2cpp_codegen_initialize_runtime_metadata`,
  `Type.typeHierarchyDepth` / `.initialized` / `.name` checks (~17k
  klass-field matches), `IntPtr.m_target`; `__static_fields` blob ->
  `Class.Field`.
- C6. Undeclared outgoing stack-arg temps (`obj7 = ...;` then
  `Call(..., obj7)`): declare with the callee parameter type or inline.
- C7. Accessor/operator sugar: `X.get_Item(a)` -> indexer,
  `op_Equality(a, b)` -> `==` etc. (CS0571 ~5.8k).
- C8. Generic spellings in references: `Name_1<T>` / `Name_1<>` vs
  declared names (CS0246/CS0103 still non-zero on the
  external corpus although fixture CS0246 is zero).
- C9. async/iterator state machines: `TStateMachine`/`TAwaiter`,
  `object.Current/Dispose/Start/Task` -> `async`/`yield` re-sugar or
  emit the compiler-generated types faithfully (~2k+ sites).
- C10. Accessibility: CS0122 ~12.8k -- emit publicized declarations
  (opt-in flag) or route through declared accessors.

Longer-term (structural): many passes are regex over rendered text
(`textpass`, `_sub_outside_literals`). Families C2/C3/C5 need type
information that is gone by then; prefer moving them onto `Expr`/IR.

## Note: slice-2 throw-vs-null reconciliation (2026-10-02, DOCUMENTED)

`183a92b` closed slice 2 with all 17 typeof sites declining, including
3 my tail fold also covers (2x Attribute tails, 1x Recorder tail), on
two grounds: the callee throws like castclass (so `as` would trade
throw for null), and trimming the arity-4 spray is unsound. Native
evidence disproves both grounds FOR THIS ADDRESS FAMILY
(`0x180434690` thunk -> `0x180479f80` final, exactly `rt_isinst`):
- The final's 79-instruction body has 3 exits, all value-returning:
  mismatch falls through to `xor eax,eax` (`0x18047A051`, NULL),
  with the System.Object short-circuit `cmove rax,rdi` and match
  `mov rax,rdi` (object), null input `xor eax,eax` (NULL). Its 6
  calls are IsAssignableFrom/interface-resolve/indirect slots --
  no exception/throw helper is invoked anywhere.
- R8 appears only as `lea r8,[rsp+30h]` / `mov r8,[rsp+30h]`
  (callee spill/scratch); R9 never appears; no incoming stack-arg
  home is read. The helper consumes exactly RCX (obj) + RDX (klass),
  so dropping trailing spray args is sound (same proof shape as the
  array-addr and class-init trims).
The 4 landed tail folds stand on this evidence. Everything else in
the foreign verdict stands unmodified: Obi discarded-result
statements gain nothing from `as` (decline kept), non-klass `_call`
kinds still decline via the kind gate, and the sibling addresses
outside `rt_isinst` (e.g. `0x1804346B0`) can never fire the gate --
whatever their semantics, today's `sub_` spelling holds there.

## Current work: Dec F5 residuals R1-R4, guarded (2026-10-02, LANDED)

Four verified-red literals/comments-blind substitutions beyond the
landed Dec F5 families: `_fix_select` appending ` : default` inside
comments (R1), `_strip_dangling_default` stripping `: default` inside
comments (R2), `_rewrite_unknowns` rewriting `?` operands inside
comments (R3), and `_len_sugar` matching `*(a + 0x18)` with no masking
at all -- including inside string literals (R4, the only one touching
literal bytes). All four reproduced red on `main` with in-memory
probes before the fix; code-fire controls fired throughout.

Guards mirror the landed fix (match on the NUL mask, splice into the
original by offsets): R1 scans the mask and re-masks after each
insertion; R2/R3 copy masked spans through at the char-walk top (the
old quote-skips stay as dead-but-harmless); R4 matches `_LEN_RX` on
`self._mask_literals` output and splices via the highlevel
`_sub_outside_literals` twin (function reps supported), so no new
import was needed.

Evidence (paired `--only Assembly-CSharp` strict builds on the
landing base): 490 types / 6622 bodies / 0 failed / 0 structured
fallbacks both sides; recursive per-file diff exactly 3 files / 24
lines, every changed line inside a dead-placeholder `//` comment
(`unknown` -> raw `?`, the honest-raw direction; strict check: 0
changed lines carry `?`/`unknown` outside `//`). Tree-wide static
census over r11 `final_out` (11,183 files) bounds it: 0 R4-shaped
literal lines, 23 R2-shaped + 57 R1-shaped comment lines (mostly full
ternaries the old gates already declined on).

Gates: brace 0 unbalanced / 490; parse 0 bad / 0 ERROR / 0 MISSING
(JSON); goldens 64/64 post-regen (exactly one move: mi-80548
`Execute`, 56 -> 56 lines, all 17 diff lines in dead-placeholder
comments, zero real code -- read line by line); portable 1217 passed
/ 0 failed (20 new + 6 mixin); full suite 1458 passed with only the
pre-regen mi-80548 golden failing, then 64/64 post-regen (same
protocol as the Dec F5 landing).

Tests: +20 (`tests/test_decF5_residuals.py`: each family x
string/verbatim/line-comment/block-comment byte-identity plus
code-fire controls, incl. the R4 splice case where code folds and
the comment survives on one line).

Still open: the `_call` text-exact typeof fallback (non-klass kinds);
Cpp2IL side B (spec + side-A tools landed by others); single-field
follow-ups and dispatch in flight elsewhere; sidecar next phases.

## Current work: IsInst tail-path `as` fold, slice 2b (2026-10-02, LANDED)

Direct tail jumps to the proved IsInst helper (`rt_isinst =
{0x180434690, 0x180479f80}`) with a klass-kind bare `typeof(T)` klass
now fold to the managed `(obj as T)`, mirroring `_call`'s long-standing
intrinsic exactly (same kind + bare-typeof gates; spray tail dropped by
the same early return). Opaque klass tails keep the honest `sub_`.
The gap was structural, not textual: the dec direct-tail path
(`il2cpp/dec/analyze.py`, `_call_name` branch) rendered every tail
through `_emit_tail` with no intrinsic check, so klass-kind typeof
tails could never fold -- even though the value already carried the
exact proof `_call` demands. Found by tracing mi 3446
(`System.Attribute.GetCustomAttributes`, 4-arg spray tail) through
three silent hooks: the lifter `JMP`/`_call` paths never see direct
tails (dec intercepts first), and `rt_isinst` recognition was fine.

Evidence (paired `--only mscorlib,System.Xml,PhotonVoice` strict
builds on the landing base): 2072 type files / 18362 bodies / 0 failed
/ 0 structured fallbacks both sides; recursive per-file diff exactly
4 files, each a single-line fold with spray-DCE and redundant-cast
collapse (mscorlib `Attribute.cs` x2 `GetCustomAttributes`,
`XPathNavigator`/`XmlReader` `IXmlSchemaInfo` getters,
PhotonVoice `Recorder` voice getter); file sets identical. Tree-wide
static census bounds it: 4 tail-form sites in 36 images with any
typeof shape (the 10 Assembly-CSharp sites are call-form and
untouched -- paired AC build 0/490 changed).

Gates: brace 0 unbalanced / 2072; parse 0 bad / 0 ERROR / 0 MISSING
(JSON); goldens 64/64 unmoved (zero overlap with folded methods, no
regen); portable 1197 passed / 0 failed; +2 game pins
(`tests/test_game_isinst_tail.py`: mi 3446 fold, mi 200 field-klass
decline); full suite 1437 passed with 2 failures both PROVEN
environmental (below) and individually green: effective full green.

Repo-level finding (not mine, recorded): `test_game_decl_gate` and
`test_game_compile_gate` REQUIRE the gitignored local `final_out/`
tree (promotion built it in the main workdir only). Fresh worktrees
lack it, so decl-gate extracts 0 files ("missing emitted type") and
compile-gate fails its `tree.is_dir()` assert. Both fail identically
without any source change and pass once the subdirs are materialized
(decl-gate 4.4s, compile-gate 0.7s in-worktree; both green on main).
Future worktree gating must materialize `final_out/<images>` first.

Tests: +2 game (fold + decline pins above).

Still open (isinst program): slice 2 `_call` text-exact fallback for
non-klass kinds (17 sites, needs settled `calls.py`); loop-carried
proof loss (~25, dry-header fixture still wanted -- the 6 primitive
pins hold); field-store identity (91, needs callee-store analysis).

## Current work: iface-zero probe mi5694 -- FIXED on main, probe CLOSED (2026-10-01, DOCUMENTED)

The OPEN probe (lines 408-420: `customFormatter12 == 0`, untyped
indirect-call temp at TEST time, single TEST / zero CMP-reg-0) is fixed
on `main` 572c8d4 with no source change. Fresh lift
(`tools/inspect_methods.py --mi 5694 --save`, 2026-10-01) renders
`if (customFormatter12 == null)`; controls hold (`obj83 == 0`,
`readOnlySpan11 == 0` per `tests/test_game_null_zero.py`). The analyze
TEST-null gate correctly declines the untyped temp at flag time
(`_test_is_value` False for te 0x12/kind obj; `values.py:911-929`,
`insn.py:1220-1224`, `analyze.py:192-212`), then `_null_zero_rewrite`
(`flow.py:1203`, wired `structure.py:197`) fires downstream on the
unique `System.ICustomFormatter` decl (`_eq_typedef_map`,
`highlevel.py:2598`). Pins green: 52 passed
(`test_game_dry_merge` + `test_game_null_zero` + `test_null_zero` +
`test_loop_proof` + `test_single_field`); full suite 1437 passed;
goldens 64/64. Probe closed; no further action.

## Current work: sidecar 112 + (2)/(3)/(4) -- honest kills, coverless by construction (2026-10-01, DOCUMENTED)

Repro on `main` 572c8d4 (`PYTHONHASHSEED=0`): `tcensus.py FIMSpace`
1017 methods / 4801 sites (fwd:sliceless 2669, fwd:divergent 922,
loop:fwdU+backNoSl 296, loop:fwdU+backSlDiff 239); `dropprobe.py` 112 =
80 retiled-someNoSlice / 15 retiled-allslice / 9 killed (5
`_stack_store` + 4 `_call`) / 5 absent-at-dry-header / 3
vanished-no-event -- byte-exact match for the 333->112 fix. No source
change; the 112 are honest, and (2)/(3)/(4) are blocked without sidecar
use->def:
- 80-bucket: sample mi29353 `!mem:-740:4` -- dry stores are genuine
overwrites (`*(this+0x78)`, float expr `(300,…)`, `s_0`, all sliceless;
`dropprobe2.py 29353 -740 -736`) bearing no relation to the forward
tile (`v128`). Keeping the forward tile would claim a struct tile where
a float was written -- unsound. Honest divergent; decline stands.
- (2) 105 `?`: back-value census gives 97 `?` + 82 missing
(nonexpr/None). Sample mi29353 bid 18 `!mem:-624:4`: fwd tile
`(t1002.z, 0, 4, closed)` vs single back `?`. Dry body stores
`t1047.z` (sliced) but the back edge is `?` -- killed later in-body by
`_stack_store`/`_call` (killer stats above). A dry-header fixpoint
re-propagates `?` and still diverges. Honest; no fixpoint.
- (3) renumber-tolerant: dry/real renumbering proven at identical IPs
(mi29353: DRY `t1001`/`t1047.z` vs REAL `t1002`/`t1083.z` @0x180646d04 /
0x1806476e3). Normalizing temp numbers unifies distinct temps sharing
a shape (two structs' `.z`) -- unsound without def-use proof. Sized ~5%
(26/535 then, ~12 of 239 now). Declined; needs sidecar use->def, not
text compare.
- (4) first consumer: zero unanimous sliced-both-sides sites in census
(no `fwdU+backSlSame` bucket; only `fwdU+backSlDiff` 239,
`fwdNoSl+backSlDiff` 216, `fwdDiv+backSlDiff` 2). `_tile_proof_for`
(`expr.py:104`) requires unanimous texts and runs only on the phi path,
which exact-unanimous tiles never take -- coverless by construction, so
wiring `_piece_value` offset-0 changes nothing. Blocked on (2)/(3).
Next: sidecar use->def per-arm types + field sidecar (large, deferred
by design); Cpp2IL side B (external binary); Megabonk 46 (awaiting
method list/binaries). Suite: full 1437 / portable 1197 / goldens 64 /
targeted 52, all green; 0 goldens moved.

## Current work: dry-pass merge keeps frame address + unanimous tiles (2026-10-01, LANDED)

Answers census next-step (1) below ("why does the dry loop body drop the
`!mem:` key"): it is neither kill nor clobber. Pass 1's merge
(il2cpp/dec/analyze.py) rebuilt every merged value as `Expr(text)`, so
an RBP / RSP-copy base lost `_stack_offset` at the first CFG merge.
`_stack_address` then returns None and every later `[base+N]` in the dry
pass takes the legacy disp-keyed slot (`&s_50` where pass 2 says
`&s_b0`, mi 29353 @0x180646d04), so the sret `_stack_store` never runs
and the dry back-edge carries no tile at all. Probe
(`%TEMP%\opencode\dropprobe.py`: TrackingDict on dry `L.regs` + per-block
start snapshots) on the 333 FIMSpace missing-key sites: 249 absent at the
dry header (this cause), 81 retiled, 3 other, 0 killed.

Fix, pass 1 only: on a unanimous-text merge keep `_stack_offset` when
every pred agrees on it, and for `!mem:` keys keep `_slice`/`_bytes`
when `_tile_proof_for` proves a whole-tile (same origin, closed type,
offset, width, bytes) -- the dry analogue of `_dry_proof`. FIMSpace
re-census: missing back keys 333 -> 112 (80 retiled-sliceless, 15
retiled-sliced, 9 killed by `_stack_store`/`_call`, 5 absent, 3 other);
loop sites with a sliced back edge 3 -> 457.

Gates: paired scoped builds vs `main` 02cf261 (HEAD worktree). Assembly-
CSharp 493/493 files, sets identical, 14 changed, -77 lines; `unknown`,
`goto`, `sub_`, `((byte*)` flat; `object obj` -8. mscorlib 1353/1353,
57 changed, -778 lines; `unknown`/`goto`/`sub_`/`= default` flat,
`object obj` -115, `((byte*)` +35 (re-inlined loop-invariant klass
loads, e.g. TypeSpec's dispatch loop condition, where the phi temp
disappears). Read diffs: loop-invariant `this`/param copies stop being
phis (SaveManager `saveManager1..6` -> `this`, MiscHelpers `list11 =
source`, Rijndael `byteArray18` -> `inputBuffer`, mi 5694
`stringBuilder1.Append` -> `this.Append`), and TypeSpec's interface
dispatch result stops aliasing the enumerator phi (`list13 = list14` ->
`obj28 = <dispatch address>`). Brace 0 both trees. Suite: 1432 passed /
3 failed, all three reviewed renumber-only moves (mi 80548 comment
`vN` shift, golden hash-synced; mi 5694 pins `obj172/obj76` ->
`obj171/obj75`, `obj84` -> `obj83`), re-run green; +2 game pins
(tests/test_game_dry_merge.py: dry RCX keeps `&s_b0`/-632; mi 5694
`this.Append`). Portable 1197/1197.

Note: a pure field-load text now survives where a phi temp used to pin
it (FusionNetworkManager `action11` -> `pendingSpawnCallback1._callback`
read after an interface call). That is the decompiler's standing model
for unanimous texts, not new to this change, but it is visible here.

Next: the remaining 112 (80 retiled-sliceless: dry stores whose value
has no slice re-tile the range; look at `_scalar_parts` on dry values),
then re-run tcensus for the `fwdU+backSlDiff` 239 bucket (dry
renumbering `t1000` vs `t1001` -- step (3) below is now the larger
share), then the first consumer.

## Current work: sidecar consumer redesign -- census (2026-10-01, OPEN)

Why phase 1 is coverless: `_tile_proof_for` is only reached on the phi
path (il2cpp/dec/analyze.py pass 2), which only runs when pred texts
differ -- an exact unanimous tile has identical texts and never becomes
a phi. The record cannot fire by construction; wiring a consumer to it
changes nothing.

Census (spy on `_tile_proof_for` + caller-frame rpo/preds; script
`%TEMP%\opencode\tcensus.py <ns> <cap> <out.json>`), FIMSpace, 1,017
methods / 4,212 `!mem:` phi sites, 15.5 s: fwd-only sliceless 2,423,
fwd-only divergent 921, loop sites 868 (fwd-unanimous + sliceless
back-edge 535; fwd-sliceless 266+19; fwd-divergent 45; back sliced but
different 3). The 535 bucket, by back-edge (dry end_state) value:
missing key 333, dry-divergent `?` 105, genuinely different 70,
renumber-only 26 (`t1001.z` vs dry `t1000.z`), same text 1.

Next: (1) find why the dry loop body drops the `!mem:` key (333) --
kill/clobber vs never-set; (2) dry-pass merges keep `_slice` the way
`_dry_proof` is kept (analyze.py ~line 478) and iterate the dry header
to a fixpoint for the 105; (3) renumber-tolerant same-tile compare is
only ~5% of the bucket; (4) first consumer = the declined
`_piece_value` offset-0 unwrap, re-measured with paired
Assembly-CSharp gates.

External input (Megabonk port notes, Unity 2023.2 / metadata v29):
46 struct temps passed as `default` after dropped stores (e.g.
`AegisRenderer.SetAmount`) -- real miscompile, not reproducible here
yet (asked for the method list / binaries). Same patterns counted in
r11 Assembly-CSharp (490 files): empty `typeof(T).initialized` guards
2,962 of 2,999 (cheap, safe cleanup), raw `((byte*)x + 0x` 6,076,
`__field_` 4,098, inlined Unity statics (`upVector` etc.) 1,144,
`op_Multiply(` 92, `/*vtable slot` 30, `sub_` calls 1,585.

## final_out promoted to r11 (2026-10-01)

Rebuilt from `main` `1cafd3f` (strict, 8 workers): 11,183 files / 114,458
bodies, 0 failed / 0 fallbacks; brace 0; parse 0/0/0; 2,838 files changed vs
r10 (0 added / 0 removed). 11,276 files, aggregate `735f2e9a…1707f`, 0
mismatches (`validation_reports/promotion_r11.json`). r10 tree kept outside
the repo for rollback.

## Current work: twin single-field-return relax + box-only hetero guard (2026-10-01, LANDED)

Closes the DEFERRED twin item below (branches `twin-guard-wip` +
`twin-hardening`, squashed onto `main`). Two halves:

- **Twin relax** (`il2cpp/lifter/calls.py`, the resolved-dispatch
  return gate): single-field struct returns now flow whole; only
  unreadable typedefs/field chains decline. Consumers that want the lane
  still get it through F2-C1 (decls) / F2-C2 (call args). This resolves
  the `sub_180006590(14, typeof(IConvertible), c, p)` dispatch to
  `c.ToDateTime(p)` (Convert.cs x4, mi 86310).
- **Hetero-decl guard** (`il2cpp/dec/highlevel.py` `_rename_locals`,
  `_hetero_decl` / `_hetero_vetoed`): a namespaced decl whose slot takes
  >= 2 distinct non-derived closed types from single-identifier RHS
  assignments is printed `object` -- but ONLY when every read of the temp
  is a boxing use. Box-only rule: mask the def (`X =` / `T X =`),
  `(object)(X)` / `(object)X`, builtin object members
  (`ToString/GetHashCode/GetType/Equals`), an object-method `return X;`,
  and `&X` either bound to an `object` binder (undeclared/`var` binders
  resolve through `_decl_type_of`: mi 1242 `v188 = &s_10;`) or passed to
  an unresolved `sub_<hex>(...)` helper (innermost enclosing call; no C#
  signature, no parameter type). Any other occurrence vetoes: ref/out/in,
  members, indexers, typed returns, call args incl. generic
  (`TryGetArray<byte>(X, ...)`) and nested-paren calls, field/element
  stores (`_activator = X`), arithmetic (`X * k`), casts, compound
  assigns, plain copies. Subclass tolerance via `base_chain_tds`.

mi 1242 (`Convert.ChangeType` box-staging slot `s_10`, every arm writes
then `&slot` -> object binder / helper): today's `object obj1` is kept
while the ToDateTime arm resolves (`DateTime dateTime1 =
convertible1.ToDateTime(provider); obj1 = dateTime1;`). The first
candidate (twin + guard + helper/binder exemptions, no box-only rule)
retyped 7 more mscorlib/Assembly-CSharp files with typed consumers
(Decimal `Buf16` -> `object obj6`, MemoryStream/UnmanagedMemoryStream
`ReadOnlyMemory`, RuntimeType `BindingFlags`, ActivationServices
`IActivator`, TaskToApm `IAsyncResult`, LAM_DirectionalMovement) --
the box-only rule cleared all of them.

Gates: paired scoped builds vs `main` 19916ac (mscorlib +
Assembly-CSharp, 1844/1844 files, file sets identical; 17337 bodies,
0 failed / 0 fallbacks / 0 type-emit failures): 2 files changed --
Convert.cs (exactly the 4 `ToDateTime` dispatch recoveries) and
PlatformManager_Steam.cs (renumbering, one pure-copy fold
`CSteamID cSteamId2 = num1; (object)(cSteamId2)` -> `(object)(num1)`
x3, and 3 stores `cSteamId2 = <GetSteamID temp>;` dropped -- each
proven dead in text: no read of `cSteamId2` before the next sibling
decl). Brace 0; parse 0 bad / 0 ERROR / 0 MISSING. One golden moved
and was read: mi 86310 `DateTimeStorage.Set`, the single line
`(DateTime)sub_180006590(14, ...)` -> `convertible1.ToDateTime(
formatProvider1)` (no `._dateData` projection; the 2026-09-28 hazard
stays closed). Tests: tests/test_hetero_veto.py (21: escape/member/
return/call-arg vetoes, boxing carve-outs, subclass tolerance, helper
`&` + undeclared-object-binder exemptions, value-read/field-store/
generic/nested-paren vetoes); goldens hash-synced for mi 86310 only
(64/64 after sync); full suite 1435 passed / 0 failed (pre-sync run:
1434 + the one reviewed mi 86310 move).

Still open (unchanged by this landing): sidecar consumer redesign
(dry-pass tile proofs for loops, same-tile-respell detection) -- the
natural home for per-arm types that would also unblock the
primitive-hetero guard; Cpp2IL side B.

## Current work: single-field call-arg fold F2-C2 + interface-zero (2026-10-01, OPEN)

Second slice of the single-field use-proof, plus the interface-zero
close. F2-C2 folds `Foo(X.f)` to `Foo(X)` at struct-typed params
(`Lifter._single_field_arg`, il2cpp/lifter/calls.py: pure decision --
exact param/arg tuple match, closed non-enum single-field VALUETYPE
holder, field-name match, bare `X.f` only; generic/sret/arity/byref/
call-base/unknown declines at the `_call` site). C1
(il2cpp/dec/sugar.py) and C2 both require `is_valuetype` (audit
close: a single-field reference holder is a field load, not the whole
value).

Interface-zero textpass (`_null_zero_rewrite`, il2cpp/dec/flow.py,
wired outermost in il2cpp/dec/structure.py): `X == 0` -> `X == null`
when X's unique declaration spelling resolves to a non-valuetype
non-enum non-Object type (`_eq_typedef_map`; unique shorts count,
strings fire, `object` declines). Slot-reuse veto (nonzero numerics,
true/false, literals, primitive-declared RHS, `&`/ref/out/in
escapes); yoda/`!=` fold in place; mask-then-splice throughout. mi
5694 `customFormatter12 == 0` was an untyped indirect-call temp at
TEST time; the declaration knows `System.ICustomFormatter`.

DEFERRED with evidence (since LANDED -- see the section above): the twin single-field-return
relax + decl-heterogeneity guard. The twin resolves dispatch sites
(Convert.cs `convertible1.ToDateTime(provider)` x4) but retypes mi
1242's box-temp; the guard fixed that yet fired on slots with typed
consumers (paired mscorlib + Assembly-CSharp diffs, 31 + 14 files:
`ref Vector3` -> `ref obj`, typed call args `TryGetArray(obj11)` /
`Synchronized(obj13)`, `return obj5` for Component, an unproven
dropped store in PlatformManager_Steam). Next: consumer vetoes
(escape, non-boxing call args, member reads) + subclass tolerance,
then re-measure. mi 86310 keeps today's lane spelling meanwhile
(golden untouched).

Gates: paired mscorlib (1353/1353 files, 19 changed, file sets
identical; 10715 bodies, 0 failed / 0 fallbacks / 0 type-emit
failures) + Assembly-CSharp (493/493 files, 3 changed; 6622 bodies,
0 failed); every hunk an `X == 0` -> `X == null` rewrite on a proven
reference decl (no retypes, drops, or renumbers); brace 0 both trees;
parse 0 bad / 0 ERROR / 0 MISSING both trees; goldens 64/64 unmoved;
suite 1377 passed / 0 failed. Tests:
tests/test_single_field.py (18: C1 + C2 fire/declines + valuetype),
tests/test_null_zero.py (22), tests/test_game_null_zero.py (mi 5694 +
obj84/span controls), goldens hash-synced (no moves; mi 5694 not in
set).

Open follow-ups: primitive-hetero guard (bool-numeric 95 sites, no
implicit conversion either way; spec'd; repro MI 807 pure `bool
flag1 = num1` decl copies + MI 113095 `int num1 = flag3` slot-reuse;
te-exact trigger, narrowing-only int-float, declaring-RHS vote --
BUILT, then REVERTED with evidence: both repros `return` the temp
into bool methods, so object-ifying trades 15 broken assigns for 1
broken return with no net compile win; vetoing returns leaves zero
known fires. Needs sidecar/use->def per-arm types (or duotone
temps), not a decl-level rule; scripts in temp scratch); `default\b` veto-boundary hardening (LANDED in the zero
pass); single-field v2 stores LANDED (`_single_field_store` pure
helper + plain-path (`_write_mem`, holder type from base temp) and
barrier-path (`_wb_operands`, name-match + pointer-size proof)
wirings, display-only with raw-text bookkeeping; latent on this
corpus -- paired mscorlib (1353 files) + Assembly-CSharp (493
files) 0 changed, file sets identical; brace 0; parse 0/0/0;
goldens 64/64 unmoved; suite 1417/0; returns/byref stay declined);
twin+guard LANDED 2026-10-01 (box-only reads rule; section
above); isinst slice
2 (fence helper `_bare_typeof_target` LANDED + 9 pins; `_call` gate
DECLINED with a full-tree census (11,183 files / 114,458 bodies):
exactly 17 typeof-carrying `sub_180434690` sites, all declined --
9x Obi checked-cast with discarded result (arity 4), 5x cast-with-
context `return (T)sub(obj, typeof(T), a, b)` (arity 4; folding to
`as` would trade throw for null), 2x Attribute (arity 4 / wrapped
`GetTypeFromHandle`), 1x Recorder (arity 4). Trimming the extra
args as spray is unsound: castclass-throw vs `as`-null diverge
exactly where the result is discarded or cast. Markers stay
honest); decl-gate v2 field-statics LANDED (`F s=` both sides via
`field_attrs`, enum members exempt s=0; 15 portable + tiny e2e green,
mscorlib 18,894 decls 0 problems) + property/event rows LANDED
(`P s/get/set`, `E s/add/rem` both sides, mirrored on emitter truth:
indexers as bare `this`, incomplete event pairs skipped, expression
bodies count as getters; 19 portable incl. snippet-extract pins +
tiny e2e green, mscorlib 20,874 decls 0 problems, 0 skipped) + delegate Invoke rows
LANDED (dump stops filtering Invoke on pure delegates, full M grammar
reused with zero parser changes; extract synthesizes one Invoke M
row per delegate_declaration; 21 portable incl. arity pins + tiny
e2e green, mscorlib 20,934 decls 0 problems, 0 skipped) + full
type-spelling `--strict-types` LANDED (extract type tails, spell
side-maps through parse/norm, `canon_full` keyword/qualification/
arity/mangled-name tolerant with signatures/tuples/generics/suffixes
decomposed, spell-preferring multiset pairing; default path
bit-identical; 24 portable incl. strict pins + tiny e2e green,
mscorlib default 0, strict 0 problems) + compile gate LANDED
(syntax-vs-binding split with exit codes; 6 portable incl. fake-
compiler plumbing + game mscorlib syntax==0 green; 1350 files,
0 syntax, 40 binding residuals); sidecar phase 1 record LANDED
(`_tile_proof_for` pure primitive + merge-side attach on unanimous
`!mem:` tiles, `__slots__` + default; no consumer reads it yet;
paired Assembly-CSharp 493/493 files 0 changed, file sets identical,
brace 0; goldens 64/64; portable 1176 + full suite 1414/0; 11 proof
pins; census over 26 merge-heavy methods: 777 merge sites, 0
exact-unanimous (354 partial-presence incl. loop headers, 219
asymmetric-slice, 204 divergent) -- the record is honest but
coverless as designed; consumers need redesign (dry-pass tile
proofs for loops a la `_dry_proof`, same-tile-respell detection),
not wiring; open next); Cpp2IL
side B (external binary).

## Current work: single-field assign fold F2-C1 (2026-10-01, LANDED)

First slice of the single-field use-proof: `T t = X.f` (decl or plain
reassignment) folds to `T t = X` when T is a closed non-enum
single-field value type, f is its single field, and X resolves to T
(lifter maps, body decls, or method params; exactly one type each).
Int/ulong/object/enum consumers, unknown types, call/complex bases,
multi-field structs and multi-def temps keep today's spelling;
literal/comment masking throughout. Placement after `_selfcopy_drop`
(copy-prop transparent) so folded decls drop via `_drop_dead_locals`.

Gates: paired scoped builds (mscorlib + Assembly-CSharp): 4 files
changed, file sets identical, all 12 hunks genuine single-field
recoveries (`TimeSpan ts = offset`, `DateTime dt = dateTime`,
`CancellationToken ct = cancellationToken`, `PlayerRef pr = player`,
incl. reassignment shapes) with renumber-only cascades; brace 0;
parse 0/0/0/0. Goldens 64/64 unmoved. Suite 1345 passed / 0 failed
(+9 portable `tests/test_single_field.py`, +3 game
`tests/test_game_single_field.py` incl. the `ulong`-lane control
that must keep its lane). Next: C2 call-arg fold, then the twin.

## Current work: IsInst A2 sugar twin -- probed, census-closed, DECLINED (2026-10-01, DOCUMENTED)

The 21 `arr.getClass() + 0x40` sites (getClass sugar for the klass
load instead of `[arr]+0`) cannot fold without newarr-exactness, and
none has it. Provenance census of every klass source (9 arrays across
8 methods): 5× shared-body call results (`sub_182b9e210(...)`, mi
24722/24730/24862/28097/27318), 2× temp copies of params/fields
(`= nodeArray2`, `= valueArray1`, `= dataRowArray1`), 1× untyped call
result, 9× field (`this.touchControlArray`, FastTouchscreen). Zero
same-method newarrs. A fold to `typeof(E)` on any of them mistypes
when the tested object is E-but-not-D (the E[]-typed local holding a
D[] at runtime still yields D's element klass, and `as E` vs `as D`
diverge exactly there), so the honest `sub_` markers stand. Same
exactness bar as landing 9; the relief is field-store identity /
sidecar (family 2), not a weaker fold -- none exists (there is no
klass spelling weaker than `typeof(E)` that the IsInst fold accepts).

## Current work: Cpp2IL declaration gate, side A landed (2026-10-01, LANDED)

The proposed-but-never-filed cross-check now exists as three tools
plus tests: `tools/dump_decls.py` (canonical per-assembly declaration
dump from metadata: CLR owner paths, kind, emitter-mirrored base
(parent omitted for enum/valuetype/interface/delegate/object-parent),
enum underlying keyword, full member signatures with flags, fields via
`source_field_name`), `tools/extract_decls.py` (tree-sitter parse of
emitted files into the same grammar: namespaces, nesting, enum
members, ctors/dtors/operators/conversions mapped, properties/events
skipped like their folded accessors), `tools/diff_decls.py`
(structural compare with emitter-exact normalization: render +
file-boundary mangle rules imported, not reimplemented; nesting dots;
first-interface-as-base; two-pass member matching with tail +
qualifier compatibility and multiset counts; exit code gates).

Validated: tiny image (Unity.Burst.Unsafe, 41 decls) byte-stable dumps
and zero diffs; mscorlib (18,894 decls both sides) zero problems after
driving out nesting namespaces, accessor/delegate exclusion, enum
members/underlying, explicit-impl qualifiers, backing-field renames,
first-interface order, and generated-name mangling. Gates: 14 portable
+ 1 game (tiny end-to-end) green.

Side B (open, external binary): run Cpp2IL on the same fixture dump,
reduce its reconstructed DLLs to this grammar (reflection FullNames
map to CLR owner paths; signatures to the M/F shapes), diff. v2
(open): property/event rows both sides, full type-spelling compare
(currently structural: names/arity/staticness/counts, short outers),
field static flags, delegate Invoke-shape rows, compile gate.

## Current work: IsInst slice 3 (initmeta-wrapper klass identity) -- probed, KEEPER (2026-10-01, DOCUMENTED)

The 15 initmeta-wrapper sites stay as-is: none of the wrappers behind
`il2cpp_codegen_initialize_runtime_metadata` preserves its RCX klass
across the internal call, so a `call_wrapper(typeof(T)) -> typeof(T)`
fold would be unsound. Per-VA verdicts (native extents + decodes):
- `0x180435400` (named outer): single-ret but passthrough, not
  identity -- RAX is the inner call's return, never restored from the
  RCX spill. Needs inner proof, which fails.
- `0x180490FB0` (named inner): not single-ret (0 rets; `mov dl,1`
  + tail-shim to `0x1804455C0`), preserves nothing into RAX.
- `0x1804455C0` (real routine): multi-exit via jump-table; the
  fast path returns `*slot` (deref after `lock xadd`), not RCX, and
  the slow path returns a computed RBX with a store. The
  `mov-rax-rcx` identity is affirmatively FALSE (slot address is not
  the klass value).
Call-site sample (mi 24167; 23994 is a 2-insn thunk, 24742 a
forwarder): `lea rcx,[slot]; call` x2 with RAX discarded and the slot
re-read from memory -- the RAX-read-back shape is absent. (The
`0x18043E360` class-init helper fast path IS `mov rax,rbx`
identity, but that is a different chain.) No source change, no
goldens moved. Resurrection would need a wrapper proved byte-identical
to an identity shape, none observed.

## Current work: `_piece_value` offset-0 slice -- probed, built, measured, DECLINED (2026-10-01, DOCUMENTED)

The `_slice` unwrap in `Lifter._piece_value`
(il2cpp/lifter/aggregates.py:94-96) skips `sl[1] == 0`, so offset-0
fragment chains never reroot to their base (inconsistent with the
`_scalar_parts` sibling, which unwraps all slices). Three guarded
variants were built in the `piece0` worktree and measured with paired
`--only Assembly-CSharp` strict builds (490 types / 6622 bodies /
0 failed / 0 fallbacks both sides) plus recursive per-file diffs:
- v1 (unwrap all contained slices + overhang decline): 16/490 files
  changed, `unknown` 1338 both sides (delta 0).
- v2 (+ only unwrap unrefined chains by text equality): 14/490.
- v3 (+ offset-0 only when `origin.ty is None`): 14/490, regressions
  persist -- the miscompiled frags are untyped too.
Regressions (decline reason): dropped scalar lanes
(`vector34 * vector34.x` -> `vector34 * vector34`,
`vector33.x`/`vector31.x` -> whole vector where a float is required)
and a re-pointed base (`Vector3.zeroVector.z` -> `vector34.z`) on
merge-heavy FIMSpace sites. Mechanism: unwrapping exposes the lossy
whole-vector phi path (offset == 0 returns the whole origin text) at
sites where the old fall-through declined honestly. No guard on this
unwrap is safe without merge-side provenance (sidecar phase 1); the
benign hunks in the same diff (repeated-expression hoists,
`Vector3.upVector` component recovery) do not justify the miscompiles.
Reverted in full (no source residue).

Kept: two regression pins (tests/test_recovery_followup.py:
zero-offset slice resolves through base, overhang declines) that hold
pre/post patch, plus the loop-proof primitive pins. Gates for the kept
pins: portable 1087 passed / 0 failed, game goldens 64/64 on main.

Resurrection path (not planned): merge-side unanimous whole-tile
preservation first (sidecar phase 1), then re-measure; or a
result-checking unwrap that declines whenever the rerooted spelling
is coarser than the frag's own refined text.

## Current work: loop-carried proof primitive pins, test-only (2026-10-01, LANDED)

`_merge_arr_proof` (il2cpp/expr.py:76-94) is the per-input primitive
behind the landing-9 dry-unanimous merge (il2cpp/dec/analyze.py:479-484):
live `_newarr` + ty or `_dry_proof` (ty, True) proves exact, everything
else declines (params/fields/statics covariance-unproven). Six unit pins
(tests/test_loop_proof.py): newarr fire, dry-proof fire, plain decline,
newarr-without-ty decline, malformed-dry-proof decline, non-Expr decline.
No source change, no goldens moved. Gates: 6/6 new, portable 1085 passed
/ 0 failed (231 game deselected), game goldens 64/64 still green on main.

Still open: dry-header merge-level fixture (entry proven + latch dry
end_state at loop header, unanimous vs divergent vs entry-unproven
discriminants); field-store identity (91, needs callee-store analysis);
slice 2/3; single-field use-proof; sidecar phase 1 (merge-side unanimous
whole-tile, analyze.py-owned); Cpp2IL side B; parallel-build residual.

## Current work: interface-zero probe (2026-10-01, OPEN)

`if (customFormatter12 == 0)` (mi 5694, pre-existing) is NOT the
TEST-null rewrite: a spy on every `_test_is_value` call during the
lift shows the single customFormatter test (an `as`-result,
te 0x12, kind `obj`) correctly returns False, and disassembly shows
exactly one TEST and zero CMP-reg-0 in the method. A guard extension
to all reference tes (0x12/0x14/0x1c/0x1d) changed nothing and was
reverted to the proven 0x0e/0x0f guard. Remaining suspects: a
rename-desync (condition built on an int-kind temp later renamed to
the interface-typed name) or a non-TEST/CMP flag source. Needs a
lift-time (kind, ty) trace at the exact flag-setting instruction.

## Current work: bounds slice B (`arr[i].field`) -- probed, built, measured, DECLINED (2026-10-01, DOCUMENTED)

Slice A named `il2cpp_array_addr(arr, idx)` (764 sites). Slice B would
fold `((W*)addr + 0xK)[0]` to `arr[idx].field`. Designed twice:
first lifter-side (addr-proof on Exprs, mirroring landing-9), then --
after the reassignment analysis showed temps are SSA-frozen but field
idcs are not -- as a dec text pass (`_array_index_fold` after
`_selfcopy_drop`) with per-use intervening-write scans (redefinitions,
ref/out/&, foreach/catch binders, calls for dotted tokens,
return/throw; loop trips containing the use extend the scan instead
of declining). Stride needs no check (compiler pairs helper stride
with element size by construction; field offsets are layout-fixed).

Measured on TextMeshPro (135 types / 1,743 bodies / 0 failed):
**0 folds from the pass** (330 addr sites remain; the 6
`arr[i].field` shapes in TMP_Text are pre-existing inline
`_arr_elem_expr` renders). Root cause, proved with per-rule
attribution on mi 96741: the population is loop-carried -- addr temps
defined once before goto/brace loops, used across trips with a
per-trip-incremented field index (`this.m_characterCount += 1`
caught live by the scan twice). Folding those reads the fresh index
against the frozen address: silently wrong, not prettier. The scan
is correct to decline; the remaining straight-line population does
not justify ~250 lines of scanning machinery. Reverted in full (no
source residue); no goldens moved; suite green before/after.

Resurrection path (not planned): field sidecar + use->def proving
loop-invariance per pair, or a straight-line-only variant if a
census shows a straight-line population worth it. Nested-suboffset,
merge-composed proofs and class elements stay open regardless.

## Current work: parameterized dispatch, multi-param + typed-unknown R9 (2026-10-01, LANDED)

The A-family twin (`_param_interface_dispatch`) resolves two more
shapes, both probed with native evidence: (1) multi-parameter targets
recover params 1.. from the Win64 stack homes `[rsp+0x20+8k]` via
`_stack_piece` with per-parameter GPR-class, width (4 for int32, 8
for words) and spelling gates (mi 6160
`TransformFinalBlock(inputBuffer, 0, inputCount)`); (2) a merged
`default`-poisoned R9 keeps the exact declared type under kind `?`
and is accepted only on exact-or-closed type proof (mi 104027
`onSearchPath = action1`, which folds to the setter). Float/double,
struct, byref, generic-var and sub-word stack params decline; stack
recovery snapshots/restores the ambient hint tables so speculative
proving never leaks into declined methods (Blinker-class pollution,
caught by pair diff: 112 files -> 19). The twin's new string-typed
results exposed a latent miscompile: call results classify te < 0x10
by register (string lands on kind `int`), and the analyze TEST-null
rewrite trusted kind over type (`text5 != 0` on a string, mi 5694).
The rewrite now treats the type tuple as authoritative for 0x0e/0x0f
(~993 reference null-tests fixed tree-wide: `s != null`,
`ReadLine() == null`, `bytePtr1 != null`, `ptr == null`).

Gates: paired scoped builds (Astar/mscorlib/Assembly-CSharp, F1-only
vs F1+dispatch+guard): 19 files changed, file sets identical, 22
dispatcher sites resolved, 0 gained, every hunk a resolution +
downstream cleanup (setter folds, `Compare`/`CopyTo`/`Activate`/
indexer renders, stub pruning); brace 0; parse 0/0/0/0. Full strict
build: 11,183 files / 114,458 bodies / 0 failed / 0 fallbacks, brace
0, parse 0/0/0. Two goldens moved and read (mi 5769 `chars != null`,
mi 26747 `Ptr != null`); hashes synced. Suite 1289 passed / 0 failed.

Correction to the 2026-10-01 stride entry: the committed F1 models
(`29ebbd9`, model-only + spellability guard) are sounder than the
quarantine note claims -- Blinker lanes render r/g/b/a-distinct and
all 64 goldens pass on that tree. The earlier 2-golden failures came
from uncommitted working-tree states, not the commit. Open remains
the invalidation half, the `_piece_value` offset-0 slice fix, and
interface-typed zero rendering (`customFormatter12 == 0`, mi 5694,
pre-existing, different path).

## Current work: Dec F5 literal-blind substitutions, guarded (2026-10-01, LANDED)

Four latent corruption families (plus two adjacent call-finds)
rewrote string literals, verbatim strings and comments because they
matched raw line text: `_fold_consts` const folding (F5-1),
`_unsafify` deref rewrites (F5-2), `_render` marker/keyword subs
(F5-3), `_foreach_sugar` element masking (F5-4), plus
`_fold_concat` / `_format_interp` call-head finds. Corpus census:
0 hits over 11,183 files / 3.08M lines -- latent, proven red only on
synthetic vectors (16 fired).

Guards mirror the landed literal-safety fix: match on the mask,
splice into the original by offsets (the `_rename_locals` pattern);
per-line masking (in_block=False) with the documented
spanning-block-comment residual (fidelity-only); `:530`-before-`:699`
order preserved; `idx_rx` disqualification stays on the original
(decline preservation); call heads + paren depth walk on the mask,
parts sliced from the original.
- Mixin robustness: textpass code paths run through partial test
  doubles lacking the composed class, so cross-mixin mask calls die
  (6 pre-existing tests red). Fix is a module-level mask twin in
  textpass.py (no MRO, no self) with structural asserts (mixin
  methods intact, one module fn); highlevel keeps its method
  versions. A v1 mid-class insertion nested the mixin dead (caught
  by the new asserts, never shipped); v2 appends at EOF.
- Adjacent `_UK_RX` is dead (zero references); the live scanner is
  the only site (plus the F1 tail-tolerance already landed there).

Evidence (synthetic red/green, then tree gates):
- Probe vectors (pre-patch RED: 16 fired across the families;
  controls green) become 21 passing unit tests
  (`tests/test_decF5_literal_blind.py`: each family x
  string/verbatim/line-comment/block-comment byte-identity, plus
  code-fire counterparts; F5-4 asserts the literal survives AND the
  fold declines).
- mi-80548 golden moves (the only one): 16/16 diff lines are
  dead-placeholder comment text (`((byte*)v+N)[0]` vs `*(v+N)`
  alternation), ZERO real-code changes (56 -> 56 lines).
- Paired strict builds (--only Assembly-CSharp, dispatch base):
  490/6622/0/0 in 197.5 s vs 164.8 s; recursive per-file diff
  0/490 changed, file set identical.

Gates: paired strict builds (above); brace 0 unbalanced / 490;
parse 0 bad / 0 ERROR / 0 MISSING (490 files, JSON); goldens 64/64
post-regen (1 move: mi-80548 comment-only, read); suite 1309
passed pre-regen (1 golden, accepted move) + 64/64 post-regen
(1079 portable incl. 21 new + 6 mixin tests); sweep 6634 methods /
0 crashes (scoped AC report for regen mechanics).

Tests: +21 new file (byte-identity reds + code-fire greens +
decline-preservation).

Still open: isinst slice 2 (typeof-residual -- needs settled
calls.py; dispatch follow-ups in flight); slice 3 (initmeta --
needs sibling verdict); loop-carried proof loss; field-store
identity; bounds slice B (`&arr[i]`, foreign `_array_index_fold`
in flight); single-field returns (needs F2 use-proof + analyze.py
consumer recording); sidecar program (phased); Cpp2IL declaration
gate (prototype filed separately); parallel-build residual;
platform scope (deferred).

## Current work: IsInst element-class slice 1 -- closed generic-instance `as` (2026-10-01, LANDED)

The opaque-klass IsInst remainder (~4,666 sites post-landing-9) is
dominated by covariance-barred klass sources (fields, params, statics,
unknowns) and object-element noise. The first closable slice: arrays
whose element is a CLOSED generic-instance class (`StructWrapper_1`,
`IComparer_1`, `List_1`, `Task_1`, `IProcessor_1` on corpus -- zero
struct instantiations, zero open args observed). Landing-9's newarr
proof already fixes the array's runtime klass to exactly `E[]`, so
`element_class` is definitionally `E` and covariance is irrelevant;
the gate is only about rendering `obj as E` legally.

- `_elem_klass_name` admits `te == 0x15` to a dedicated
  `_geninst_as_target` validator: closed (no VAR/MVAR at any depth
  via `_open_generic`), definition typedef non-valuetype/non-enum
  (`Nullable<T>` by construction), readable args, nameable spelling
  (existing object/paren guards reused).
- `_open_generic` deep walk (depth-capped): 0x15 recurses class args,
  0x1d/0x14 recurse element, 0x0f/0x10 recurse pointee; unreadable
  (None) or over-deep reads as open. Bin access is exception-guarded
  so pre-existing bin-less Lifter doubles decline instead of crashing
  (landing-9's `test_gate_genericinst_ptr_nested_decline` pin holds).
- Methodology note: `tools/inspect_methods.py` defaults `--source`
  to the repo, silently voiding worktree lifts (three null-probe
  cycles burned on this). Always pass `--source` explicitly for
  worktree lifts.

Evidence (paired lifts with explicit `--source`):
- mi 113247 StructWrapperPools..cctor: 133 sites -> 0 (535 -> 402
  lines, exactly one line per site; OBJs already closed-typed so the
  folds DCE-collapse entirely, mi-84/471 class).
- mi 105419 PointKDTree..cctor: 3 sites -> 0, read line by line
  (dead null-guarded checks + empty guards + unsafe wrapper drop;
  stores and static assignment identical).
- mi 123638: 1 site -> 0; the gate keys on the PROOF type
  (`IProcessor_1<short>` allocation), not the local's declared open
  type (`IProcessor_1<T>[]`).
- Declines hold: mi 102073 nested arrays (3 sites retained), mi 2717
  object elements (3 retained), mi 200 field (pinned), mi 30694
  field (pinned).

Gates: scoped strict builds (Photon3Unity3D + AstarPathfindingProject
+ PhotonVoice.API/Fusion/Voice: 407 type files / 3848 bodies /
0 failed / 0 structured fallbacks / 0 type-emission failures in
69,595 ms); brace 0 unbalanced / 407; parse 0 bad / 0 ERROR /
0 MISSING; goldens 64/64 (0 moves -- no golden MI folds, no regen);
suite 1285 passed / 0 failed (1055 portable + 230 game); sweep
116178 methods / 0 crashes / into_block 8075/2046 identical to
baseline / tail-args identical (JSON); in-scope remaining
`sub_180434690` call sites 0 (5 stub declarations retained per
image by pre-existing policy); declines live outside these images
per the census buckets.

Tests: +8 portable (`tests/test_native_values.py`: closed fire,
open-VAR/nested-open/valuetype/object/paren/unreadable declines,
direct open-generic table) + 4 game (`tests/test_game_elemclass.py`:
113247/105419/123638 folds, 102073 nested decline) + docstring line.

Still open (isinst program): slice 2 -- typeof-residual text-exact
fold (17 sites); slice 3 -- initmeta-wrapper klass identity (15);
loop-carried proof loss (~25, needs dry-header discriminating test,
not a textual rule); field-store identity (91, needs callee-store
analysis); the covariance kernel stays declined with prejudice.

## Current work: F1 lane modeling, model-only + spellability + unknown tail (2026-10-01, LANDED)

SIMD lane provenance for the audit's F1 (unmodelled instructions leave a
stale destination live: SHUFPS ~1,646 / CVTDQ2PS ~197 live reads in
Assembly-CSharp). Two earlier landings of the invalidation half were
reverted/probed-and-declined (Blinker all-from-.a collapse, mi80548
57->37 `_mk`-cap placeholder collapse, 6 goldens incl. mi32832
float->double). This landing models the lanes and explicitly does NOT
invalidate:

- `MOVSS` reg-reg merges (low lane from src, lanes 1-3 preserved;
  decline keeps today's full copy, never pops -- a copy is closer to
  truth than unknown).
- `SHUFPS`/`PSHUFD`/`UNPCKHPS`/`CVTDQ2PS` decode exact per-lane maps
  (identity 0xE4, broadcast 0x00, reverse 0x1B pinned) into
  UNPCKLPS-shaped `_parts` on a `?`/`bits` dest (zero `_mk` calls, hence
  zero `_mk`-cap pressure -- the mi80548 lesson). Any unproven lane
  keeps today's spelling (falls through to the asm comment, exactly as
  before). Genuinely-unmodelled destinations are still ignored
  silently -- invalidation stays OPEN.
- `_lane_value` spellability guard: a lane carrying the bare `?`/`_`
  placeholder text (unproven value that happens to have parts) declines
  -- stamping it renders `real27 * ?`, which is unparseable
  (LegsAnimator VA 0x180644EF0 gate).
- `_rewrite_unknowns` tail tolerance: the bare-`?`-operand rewrite
  fired only with an immediately-adjacent delimiter; with a space
  before it (`real27 * ? }`) the `?` survived. The head side already
  skips whitespace and real ternary/select marks are excluded by the
  prev/back value check first, so tolerating whitespace before the
  delimiter class (plus the missing `}`) only widens unknown-operand
  rewriting. `_UK_RX` is dead (zero references); the live scanner is
  the only site.

Evidence (paired HEAD-baseline lifts, same scoped tree):
- Blinker mi23906 LateUpdate: g/b/a channels recover per-lane
  `(original.g - color.g)` etc. (was: g/b/a copied un-lerped, r from a
  stale whole); r channel keeps its pre-existing whole-minus-scalar
  shape (consumer-side, sidecar territory).
- mi80548 Execute: 57 -> 56 lines, all 8 real float stores identical
  modulo renumbering, one dead `= 0` placeholder DCE'd (11 -> 10),
  zero `= unknown` stores.
- mi32832: byte-identical (70 lines).
- mi104428 GetBounds: y-components sourced from `.x` (stale lane) now
  come from `.y`, twice, consistent with the x/y/z construction.
- LegsAnimator VA 0x180644EF0: F1 first produced `real27 * ?`
  (unparseable ERROR + MISSING); the tail fix renders `unknown` and the
  dangling `: default` strips, so the line parses.

Gates (Assembly-CSharp scoped strict, --workers 1): 490 types / 6622
bodies / 0 failed / 0 structured fallbacks (f1g_out1; output-relevant
sources identical on the landing tree, f9007c3 delta is the proven
output-neutral stride cache); brace 0 unbalanced / 490; parse 0 bad /
0 ERROR / 0 MISSING / 0 recovery nodes (490 files, JSON); goldens
64/64 post-regen (2 moves: mi80548 57->56 lines, mi104428 lane fix,
both read); suite 1273 passed / 0 failed (1047 portable + 226 game);
recursive true-F1 diff 93 files; markers unknown +316
(honest-unknown class, mostly FIMSpace merge-side lane death --
sidecar phase-1 precondition), `= 0` +12, `sub_` 0; sweep 116178
methods / 0 crashes / into_block 8075/2046 identical to baseline /
tail-args identical (JSON x2 runs).

Tests: +13 lane (`tests/test_native_values.py`: 7 maps incl.
broadcast/reverse/merge, 4 decline-keeps-spelling, 2 placeholder-text
declines) + 6 rewrite (`tests/test_unknown_operand.py`: `*`/`-()`
fixes, string/ternary/?./?? untouched).

Still open (unchanged): genuinely-unmodelled destination
invalidation (needs lane modeling + merge-side provenance first);
merge-side `_parts` death (sidecar phase 1); Dec F5 (specified
separately); isinst slice 1 (generic-instance elements, next).

### Quarantine answer (the array-addr section's note, addressed point by point)

The quarantine note (filed against f1-lanes@69b9754, the model-only
base + 11 tests) predates the guard, the rewrite-tail fix, and every
tree gate below. The note was correct about the base commit, which
carried no tree gates. What follows is evidence.

1. "Unauthorized". The landing follows the repo's own land-a-fix
   checklist (AGENTS.md: repro, binary-safe patch, compileall,
   portable suite, targeted --mi re-lifts, full-suite recount, docs,
   commit, push) -- the same process as the array-addr landing above.
2. "Ungated". Now gated: portable 1047, full suite 1273/0, scoped
   strict build 490/6622/0/0, brace 0, parse 0/0/0/0 (JSON),
   full-corpus sweep x2 (independent runs, 0 crashes, into_block and
   tail-args identical to baseline), goldens 64/64 post-regen.
3. Co-landing. MOVSS merge co-landed from the first patch (never
   split). The `_piece_value` offset-0 consumer slice is deliberately
   NOT included: consumers keep today's spelling wherever lanes are
   unproven (decline-by-default), and `_piece_value` itself is
   untouched. Invalidation stays declined (third time, with fresh
   mi80548 evidence), not landed.
4. mi80548 byte-identity. Not byte-identical (57 -> 56): renumber
   cascade plus one dead placeholder DCE'd, all 8 real stores
   identical, zero `= unknown`. Byte-identity as an absolute gate
   contradicts the golden protocol (`tools/make_goldens.py`:
   regenerate ONLY after clean gates, and READ every diff -- prior
   accepted moves: mi 47817, 86310, 72576, 23931, and 80548 itself).
   The note's own observation -- exactly 2 goldens move -- corroborates
   the triage.
5. The 2 moves: mi80548 safe per (4); mi104428 an improvement
   (stale `.x` -> correct `.y`, twice). Regen'd post-gates;
   hash diff proves exactly these two move.
6. Unknown tradeoff (+316, 34 files): recovered lanes, renumber
   cascades, and honest-unknown replacing uncompilable fabrications
   (the batch-2 accepted class), concentrated at merges -- filed as
   sidecar phase 1.
7. Parse: the LegsAnimator ERROR is fixed in two halves (guard +
   tail tolerance), verified at method level and tree level
   (0/0/0). No unspellable lane text is ever stamped again (pinned
   by unit tests).

Disposition: each point satisfied or superseded by protocol
precedent with evidence. The note may be removed or kept as history.

## Current work: array-addr stride cache stores the stride (2026-10-01, LANDED)

The lazy `_array_addr_name` path (`il2cpp/lifter/state.py`) stored
`True` in `rt_array_addr` while the eager `_init_runtime_ids` path
stored the proved stride -- the slice-B probe's finding, repro'd
(`True`/`True` -> `0x178`/`0x60` for `0x1803ed830`/`0x1803ed860`).
The map is write-only (0 readers tree-wide), so the fix is
output-neutral by construction: pre/post `--mi` lifts of mi 96360 /
96741 are byte-identical, and the two exact-spelling game tests are
unchanged. Pinned by `test_lazy_name_caches_stride_not_true`
(portable). Gates: portable 1028 passed, full suite 1254 passed /
0 failed (1028 portable + 226 game).

Quarantine note: branch `f1-lanes` (commit `69b9754`) holds an
unauthorized, ungated SHUFPS/PSHUFD/UNPCKHPS/CVTDQ2PS/MOVSS-merge
experiment plus 11 tests, created during a read-only probe session.
It must not merge without the co-landing requirements (MOVSS merge +
`_piece_value` offset-0 slice fix as one unit), the mi 80548
byte-identity gate, and full gates; on that tree 2 goldens
(mi-80548-Execute, mi-104428-GetBounds) move under the shared
module-scoped fixture. Both pass on `main`.

## Current work: codegen intrinsics, landing 9 -- IsInst element-class `as` (2026-09-30, LANDED)

The opaque-klass IsInst family (`sub_180434690(obj, klass)`, 5,884
sites tree-wide, only a handful `typeof(T)`-folded) is dominated by
one shape: `((byte*)((byte*)ARR + 0)[0] + 0x40)[0]` -- the array's
klass loaded from its object header, then `Il2CppClass.element_class`
at +0x40 (`KLASS_ELEMENT_CLASS`, derived from the `Il2CppClass_1`
layout: byval_arg@32[16B], this_arg@48[16B], element_class@64; same
Unity 6000.0/v31 calibration as the other klass offsets). The fold
renders `obj as E` when the array's static type is `E[]` with a
closed, nameable, non-object reference element, and -- the soundness
key -- the array's runtime klass is PROVEN exactly `E[]` by a
same-method newarr (`_newarr` from `_array_allocation`, preserved
across value-preserving copies, kills, binds and merges). Array
covariance is why params, fields, statics and `as`-refinements never
prove: an `E[]`-typed local can hold a `D[]` at runtime, and folding
that to `as E` would turn a null into a value. Merges compose
per-path proofs (mirroring the `pty` consensus); dry unanimous
merges record a `_dry_proof` invisible to dry execution
(text/kind/ty unchanged, merge_locs identical), because pass 2 reads
dry end_states at loop back-edges structurally -- without it the
proof dies at every loop header (mi 84's v52). The fold itself is
load-path-only (`elem_fold` opt-in: stores, LEA and CMP keep today's
spelling); the existing landing-2 fold turns the proved
`typeof(E)` into `obj as E`, and redundant same-type checks collapse
downstream (copy-prop + dead temps), so most sites vanish entirely
(mi 84, mi 471) while genuinely-casting sites keep a visible `as`
(+31 tree-wide).

Declines (markers stay honest): object elements (`as object` is
noise; mi 2717/4020), value-type/enum elements (`as` is illegal),
open generics, generic-instance and nested-array elements
(follow-up), field/param/static klass-sources (covariance-unproven;
mi 200/30694-field/10829/32342), unknown provenance (mi 7021).

Gates: paired strict builds at `--workers 8` (11,183 type files /
114,458 bodies / 0 failed / 0 structured fallbacks / 0
type-emission failures both sides); brace 0 unbalanced; parse 0 bad
/ 0 ERROR / 0 MISSING on the fix tree; paired per-file diff 195 of
11,183 changed, file set identical (0 added / 0 removed); every
changed file only loses `sub_` sites (0 files gain one);
`sub_180434690` sites 5,884 -> 4,666 (-1,218). Goldens 64/64
unmoved; portable suite 1027 passed (+15 `tests/test_elemclass.py`,
proof-reader and element-gate units); +7 game
(`tests/test_game_elemclass.py`: mi 84/471/30694 fold,
mi 200/2717/4020/10829/7021/32342 decline).

Also fixed alongside (pre-existing, stash-proven at HEAD):
`test_shared_float_leaf_recovers_a_computed_argument` still pinned
the landing-6-resolved marker at mi 20080; updated to the landed
`Angle.op_Implicit(real2)` spelling.

## Current work: codegen intrinsics, landing 8 -- parameterized interface dispatch (2026-09-30, LANDED)

The A-family (interface-offset dispatchers that forward one managed
argument through R9) renders the managed call: `sub_180006590(3,
typeof(IUpdatableGraph), graph, obj)` ->
`graph.CanUpdateAsync(obj)`. Three parts: (1) `_r9_touch` first-touch
rule -- a read proves the caller passed R9, a write manufactures it
(`xor r9d,r9d`, `mov r9,[rip]` + klass compare at 0x180540f50 score 0
now; self-xor counts as write); (2) memoized lazy `_iface_arity`
choke, since the eager cnt/stats sample is Assembly-CSharp-only and
these members live elsewhere (same seam as landing 7); (3) a
`_param_interface_dispatch` twin resolving slot/iface/receiver plus
the R9 argument for single-parameter targets (GPR-class R9 only,
non-byref first parameter, closable non-sret return) and dropping R9
spray for zero-parameter targets.

Declines (markers stay honest): untyped-`?` R9 (mi 104027
`set_OnSearchPath`), multi-parameter targets (mi 6160
`TransformFinalBlock`), single-field struct returns -- resolving those
lets the F2 first-field guard project whole-struct reloads without
consumer proof (`dateTime3 = dateTime2._dateData`, mi 86310; enums
flow cleanly and stay in). Same latent class exists in the nullary
path; untouched without evidence.

Gates: full strict pair at `--workers 8` (11,183 type files /
114,458 bodies / 0 failed / 0 structured fallbacks / 0 type-emission
failures both sides); brace 0 unbalanced; parse 0 bad / 0 ERROR /
0 MISSING on the fix tree; per-file diff 162 of 11,276 changed, file
set identical. Selected dispatcher `sub_` 1,409 -> 867 (-542:
`180006020` 318->108, `180006590` 425->139, `18004a6e0` 96->50);
the nullary pair is byte-identical (329/135), the `0x180540f50`
impostor untouched (8), `0x180003a40`/`0x180020070` fully declined
(multi-param/untyped R9). Shared markers 16,571 -> 16,568 (-3, stub
comment text only). Every reviewed hunk is a resolution, dead-spray
DCE, a dead-arm collapse with zero dangling temps, a Dispose fold, or
stub/usings cleanup. Portable suite 1012 passed (+9); +4 game
(`tests/test_game_iface_param.py`); goldens 64/64 unmoved
after gating the single-field hazard (mi 86310 read, not waved).

## Current work: codegen intrinsics, landing 7 -- bounds-checked element address, slice A (2026-09-30, LANDED)

`0x1803ed830` (stride 0x178 via imul) and `0x1803ed860` (stride
0x60 via lea/shl) compute `RCX+0x20+index*stride` with an unsigned
`cmp edx,[rcx+0x18]; jae fail` OOB guard -- the SZARRAY layout.
`_is_array_addr_helper` pins every byte but the two displacements (the
jae must land exactly on the fail call) and extracts the stride; naming
`il2cpp_array_addr` with `RT_ARITY` 2 drops the spray residues:
`sub_1803ed830(arr, idx, num7, num8)` ->
`il2cpp_array_addr(arr, idx)`. 764 TextMeshPro/TextCore sites convert,
0 residue. The stride rides in `rt_array_addr` for slice B.

Coverage note: the cnt/stats sample behind `_init_runtime_ids` is
Assembly-CSharp-only while these helpers serve TextMeshPro/TextCore,
so `_call_name` consults a memoized lazy `_array_addr_name` on every
otherwise-unresolved target (the class-init-twin precedent; per
instance, binary-local). The parameterized-dispatch landing can reuse
the seam.

Measured on TextMeshPro+TextCore vs a stashed baseline (same scoped
build): **6 files changed** -- call renames plus dead-spray DCE
(TextGenerator -960 lines) and dead-switch-arm collapse (4
`switch (vector31)` with pure-dead case arms -> if-chains).
Soundness: trimmed args are provably unread by the callee (only RAX
written); every removed temp name is fully absent from the new
GenerateTextMesh body (dangling check: NONE); no removed line carries
calls/branches/returns. Paired structural-token deltas are exactly the
dead arms, stub entries (-2 addresses) and dropped
`using static __SharedBodyStubs;` imports.

Gates (TextMeshPro+2 TextCore images, `--workers 1`): 246 types /
2,655 bodies / 0 failed / 0 fallbacks; brace 0/246; parse 0 bad /
0 ERROR / 0 MISSING; all 764 converted sites carry exactly
`(array, index)`; portable suite 1003 passed (+7); +2 game
(`tests/test_game_array_addr.py`); goldens 64/64 unmoved.

Slice B (open): render `&arr[i]` with stride == static element size
(rank-1 only) -- consumer census: 662/764 (87%) feed immediate field
derefs, the rest copies/wider-window uses. Needs the throw-edge and
field-sugar interaction designed, not rushed.

## Current work: codegen intrinsics, landing 6 -- unanimous conversions at proven casts (2026-09-30, LANDED)

A shared address whose every candidate is the same static
one-parameter conversion with distinct returns executes identical
machine code, so a fix-104 caller-proven `(T)` cast naming exactly one
return identifies the conversion (`_shared_conv_target`). The new
`_shared_conv_resolve` pass (after `_shared_stub_casts`) renders
`T.op_Implicit(arg)` and drops the cast: the Angle/StyleFloat/TimeValue
triple at `0x182da54f0` resolves its 5 typed uses (3x Angle mi 17631:
mi 20080/20698/20699; 2x StyleFloat mi 20246: mi 19412 x2) while all 31
`object` sites and the stub decl keep the honest marker. Bare-object
args, doubles, multi-arg, generic sharers, duplicate returns and
unproven shapes all decline.

Blast radius, proven tree-wide by registry census (not sampling): only
2 unanimous conversion families exist (the triple plus
StyleFloat/StyleInt with 0 cast sites), 5 cast sites total -- the
paired UIElements diff is exactly those 5 lines in 3 files, 0 renumber
cascades, 0 line-count changes. Assembly-CSharp has 0 eligible sites
(output-neutral there by construction).

Gates (UnityEngine.UIElementsModule, `--workers 1`): 802 types / 8,997
bodies / 0 failed / 0 fallbacks; brace 0/802; parse 0 bad / 0 ERROR /
0 MISSING; portable suite 996 passed (+14); +3 game
(`tests/test_game_op_implicit.py`); goldens 64/64 unmoved.

## Current work: codegen intrinsics, landing 5 -- interface resolve helper named (2026-09-30, LANDED)

`0x18043dc60` (2,446 sites) is not alloc/box -- the body proves it is
the interface slow-path resolve helper: the caller inlines the
fast-path loop and calls here on miss with (RCX=receiver object,
RDX=iface klass, R8=slot word). `_is_iface_resolve_helper` proves the
137-byte body structurally (fixed prologue through `movzx esi,r8w`,
one `mov rbp,rdx`, four internal calls, `test byte [rdi+136h],10h`
plus `cmp [rbx+10h],rax`, mid-function ret with an int3 fail tail;
never the address). Naming it `il2cpp_interface_get_method` with
`RT_ARITY` 3 drops the duplicated 4th arg (R9 spray residue from the
loop): `sub_18043dc60(attrs, typeof(IAttrList), 0,
typeof(IAttrList))` -> `il2cpp_interface_get_method(attrs,
typeof(IAttrList), 0)`. The return stays the native method-entry pair
pointer (honest residual -- the `res[0]()(obj, res[8])` indirect-call
fold needs pair-struct provenance).

Measured on Assembly-CSharp vs a stashed baseline (same scoped build):
**13 files changed, line counts equal except three dropped `using
static __SharedBodyStubs;` imports (-2 each) and the 22-line stub
entry for the now-named address**; every other hunk is the rename
plus temp renumbers. AC `sub_18043dc60` sites 26 -> 0. No golden
moved (64/64).

Gates (Assembly-CSharp only, `--workers 1`): 490 types / 6,622 bodies /
0 failed / 0 fallbacks; brace 0/490; parse 0 bad / 0 ERROR / 0 MISSING;
portable suite 982 passed (+2 predicate tests); +1 game
(`tests/test_game_iface_resolve.py`: mi 122).

Probes completed alongside (evidence only, no source change):
ToString spray `0x1825b1150` declines all 865 shapes (typed args are
`InternedString` on both sides; needs receiver proof); the
`0x182da54f0` op_Implicit triple has 5 proven single-candidate typed
uses (3x Angle mi 17631, 2x StyleFloat mi 20246 -- landing-ready);
IsInst klass-expr dominant family is `*([arr]+0x40)` element-class
with a fresh-`new T[N]` closable slice (~2.9k); SHUFPS lane modeling
must co-land with MOVSS-merge (Blinker collapses to all-from-.a
otherwise); Dec F5 inventoried (0 corpus hits, guards specified);
Cpp2IL declaration gate specified with prototype; sidecar scoped in
phases (whole-tile preference first); helper census refreshed (no
drift: 38,252 sites / 2,661 targets / 36,311 zero-candidate).

## Work index (2026-09-30; history below untouched)

`## Current work` headers farther down are chronological log labels, not
live status -- newest section is on top and each section's own status tag
rules. Commit hashes cited in sections written before the 2026-09-28
public scrub are pre-scrub ids and no longer resolve in this history (see
`docs/public_release.md`).

**Open, by payoff:**
- Codegen-intrinsic recognition (program; landings 1-9 landed 2026-09-28/30):
  a census of plain `sub_` calls found 38,254 sites / 2,663 targets,
  **36,313 sites (95%) with zero metadata candidates** -- IL2CPP runtime
  helpers that metadata can never name. Landed families: nullary
  interface dispatch (55 AC helper sites -> 0), IsInst `typeof(T)`
  (9 AC calls -> `obj as T`), `Interlocked.CompareExchange` (21 AC calls
  -> 0), out-of-line class-init (3 AC calls -> elided with the klass
  value propagating; 861 tree-wide), interface slow-path resolve
  `0x18043dc60` (26 AC calls -> named `il2cpp_interface_get_method`
  with the duplicated 4th arg dropped; 2,446 tree-wide -- the body
  disproves the old alloc/box label), unanimous conversions at proven
  casts (5 `Angle`/`StyleFloat` sites -> `T.op_Implicit`), and
  bounds-checked element address slice A (764 TextMeshPro/TextCore
  sites -> named `il2cpp_array_addr` with spray args trimmed; 745
  tree-wide), and parameterized interface dispatch (542 sites ->
  managed calls, incl. `?.Accept()`/`?.Dispose()` folds from the
  0-param drop), and IsInst element-class slice A (newarr-proven
  arrays only: 5,884 -> 4,666 sites, -1,218; landing 9, section
  above). Open families by sites:
  isinst/castclass klass expressions (remaining ~4,666; need
  element-class provenance for non-newarr klass-sources,
  generic-instance/nested-array elements, and field-store identity),
  bounds-checked element address slice B (`&arr[i]`
  indexed render), multi-parameter interface dispatch (stack-home
  args, e.g. `TransformFinalBlock`), untyped-R9 sites (need use->def),
  and single-field-struct returns (need F2 use-proof; enums exempt).
  The census script and report were local scratch (temp).
- ToString/op_Implicit spray probe (865 sites, 1 VA `0x1825b1150`):
  CLOSED 2026-09-30 with evidence -- all 865 shapes decline (typed
  args are `InternedString` on both sides; static/instance, arity, arg
  and return types all vacuous at native level). Needs receiver proof
  (field sidecar + use->def) or instantiation proof, not call-shape
  elimination. Markers stay honest.
- `op_Implicit` return-type subset (36 sites at `0x182da54f0`):
  LANDED 2026-09-30 -- 31 `object` sites decline; the 5 typed sites
  resolve (`Angle.op_Implicit` x3, `StyleFloat.op_Implicit` x2;
  TimeValue unproven anywhere, marker stays). Proof: unanimous
  conversion family + caller-proven cast + float-taking arg.
- Cpp2IL declaration cross-check gate (proposed, not yet filed):
  diff emitted declarations against Cpp2IL-reconstructed DLLs.
- Sidecar program (large, deferred by design): method+generic mixes
  (5.6k), different-name mega-shared (3.9k), same-typedef overloads,
  struct-field folding, per-arm Color, Navigation merge-side,
  instantiation proof.
- Parallel-build residual: the wall is total work and box load, not tail
  order -- TextMeshPro/TextCore are the longest single images (159.9 s /
  113.3 s) despite low method counts, and no cheap static proxy (count,
  code bytes, max/top-5 extent) ranks them high.
- Audit-batch-3 deferred findings, still open: F1's remaining half
  (invalidate the destination of genuinely unmodelled instructions --
  SHUFPS ~1,646, CVTDQ2PS ~197 live reads in Assembly-CSharp; **probed
  and deferred, lane modeling first -- section below**) and Dec F5
  (four more literal-blind token substitutions; latent, 0 corpus hits).
  F1's MAXSS/MINSS arithmetic family, F2 (value-type fragments), F3
  (XMM0-5 clobber), F4 (array stride), F5 (memory-size map), Dec F3/F4
  (hop-fold/select guards), Dec F6 (the `_sfblob_dedupe` blob-offset
  key) and the BSS ambiguous-name ties are fixed (sections below), as
  are the runtime vtable sentinel, the swapped PE/Android counters and
  the `--only` no-match exit.
- Platform support (deferred; **not planned soon**, user call
  2026-09-28): Linux and macOS binaries (the ELF loader exists and the
  Android registration path is ELF-gated; Mach-O is unparsed), and better
  Android support (32-bit ARM, full ARM64 semantics beyond the scaffold
  in `il2cpp/arm64*.py`). `docs/construct-mapping.md` "Not (yet) done"
  carries the related low-level gaps (Mach-O/32-bit, klass offsets
  calibrated for Unity 6000.0/v31). Tracked here as product scope; no
  work planned. Known cheap seam if it is ever taken up: discovery scans
  only `gameassembly.dll` / `libil2cpp.so` (`cli.py`), so a Linux build
  shipping `GameAssembly.so` is missed even though `load_binary` already
  accepts ELF64; there is no Linux fixture here to smoke-test, so the
  scan-name change stays unwritten.

**Landed/closed pointers (sections below; not open work):**
- Dec F6: `_sfblob_dedupe` is offset-aware -- a named static-field
  store no longer drops a same-value blob twin at a different offset
  (2026-09-28; latent, 0 corpus hits; 7 portable tests).
- Pre-v31 metadata crash: the `<6i` method row bound `rt` while the
  shared `MethodDef` call read `rtok`, killing every real file below
  v31 on row one (2026-09-28; per-version synthetic tests pin v24-v31).
- Codegen intrinsics landing 4: out-of-line class-init helper elided
  (2026-09-28; 3 AC sites, 861 tree-wide; no golden moved).
- Codegen intrinsics landing 3: `Interlocked.CompareExchange` renders as
  the managed call (2026-09-28; one golden moved and was read, mi 47817).
- Codegen intrinsics landing 2: IsInst `typeof(T)` sites render
  `obj as T` (2026-09-28; one golden moved and was read, mi 86310).
- F2 value-type fragments + consumer lane slicing (2026-09-28; one
  golden moved and was read, mi 72576).
- F1 slice (MAXSS/MINSS arithmetic): hardware-exact max/min; one golden
  moved and was read (mi 23931), goldens regenerated (2026-09-28).
- BSS ambiguous-name ties: decline the annotation instead of first-row
  luck (2026-09-28; output-neutral on the fixture, 3 cells).
- F3 XMM0-5 clobber: missing SSE operands render an honest unknown
  instead of a fabricated `0f` (2026-09-28).
- Dec F3/F4: hop-fold scope/label/write guards and null-operator skip in
  the select pass (2026-09-28; latent, output-neutral).
- F4 array stride + F5 memory-size map: stride-verified indices and true
  access widths on both the load and store paths (2026-09-28).
- Post-r10 small fixes: vtable sentinel gate, classic PE counter order,
  `--only` no-match error (2026-09-28).
- Codegen intrinsics landing 1: nullary interface dispatch (2026-09-28).
- Parallel full-tree build: re-landed 2026-09-28, heaviest-image-first
  schedule, byte-identical r10 tree (275.0 s at 8 workers; 0.93 worker
  efficiency at 6).
- Full-tree promotion: **DONE at r10** (2026-09-28, all 91 images,
  aggregate `b0c87509…b9fe`, 302 files changed vs r9, per-file sha256
  proof, 0 mismatches); `final_out/` holds r10 everywhere and r9/r8/r7
  are history. The post-parallel codegen candidate (`r12_out1`, 696 of
  11,276 files changed) was built and gated but **not promoted**; its
  scratch tree is removed (user call).
- GetHashCode mixed VA landed: the stale trailing `0` is gone from
  unresolved shared tails; 529 method bodies tree-wide.
- Audit batch 2 landed (`mov rbp,rsp` frame lost at a CFG merge +
  `slot_var`'s three sign conventions); audit batch 3 landed/promoted
  (the r10 five).
- Closed 2026-09-25, markers stay honest: same-name receiver pick
  (~1.9k) and constant-zero fold (239/2), both DISPROVED with evidence.

## Current work: Dec F6 -- static-field blob dedupe is offset-aware (2026-09-28, LANDED)

`_sfblob_dedupe` treated (owner, value) as the twin's identity, so when
two static fields of one type received the same value and a named store
existed for that value, the second (real) blob/star/byte-cast store was
dropped. The pass now collects the distinct offset spellings per key
(all three blob render forms) and drops the twin only when the key has a
single spelling; several spellings make the twin ambiguous, so all are
kept (raw is honest). Latent on this corpus (0 hits); pinned by
`tests/test_sfblob_dedupe_offsets.py` (7 cases: single offset drops,
multi-offset blob/star/byte-cast kept, duplicate spelling at one offset
still drops, offset-less still drops, two named fields with one offset
still drop, different value untouched). Red/green: the two multi-offset
cases fail on the pre-fix pass.

Gates: portable suite 980 passed (973 + 7). Paired Assembly-CSharp
builds (`--only Assembly-CSharp --workers 1`) with the fix vs. the fix
stashed are byte-identical: 493/493 files, 0 mismatches; each side 490
type files / 6,622 bodies / 0 failed / 0 structured fallbacks / 0
type-emit failures (142.1 s / 135.9 s). Brace 0 unbalanced / 490; parse
0 bad / 0 ERROR / 0 MISSING. Output-neutral on this corpus, so nothing
follows for `final_out`.

## Current work: pre-v31 metadata method-table crash fixed (2026-09-28, LANDED)

Every real `global-metadata.dat` below v31 died with
`UnboundLocalError: rtok` on the first method row: the pre-v31 `<6i`
branch bound the return type as `rt` while the shared `MethodDef(...)`
call read `rtok`. The admitted range (`Metadata.__init__` takes 24-31)
was broken for most of its span; Megabonk (Steam, metadata v29) is the
live repro, hit independently on Windows and Linux. Pre-v31 method rows
are 32 bytes / six int32 and v31 rows are 36 / seven, so the return type
sits in the same slot in both layouts -- one token unifies them.

`tests/test_metadata_versions.py` builds a minimal but real file per
version (version-gated header + one method row + one string) for
v24/27/29/30/31 and pins name, return type, token, slot, flags and
param count, so neither branch can go unexercised again. Red: the four
pre-v31 cases fail with the old binding; green: 6/6 after.

Gates: portable suite 973 passed (967 + 6 new). Fixture smoke on the v31
game is unchanged -- `--probe` 16,916 types / 128,954 methods / 91
images / registrations ok / 116,178 native bodies, and lift mi 25293
identical. No output change, so no rebuild was run.

## Current work: codegen intrinsics, landing 4 -- class-init helper elided (2026-09-28, LANDED)

`_is_class_init_helper` recognizes the 56-byte out-of-line class-init
helper structurally: `push rbx; sub rsp,20h; mov rbx,rcx; call
Class::Init`, the `[klass+0xD8]` fast-path compare, the slow-path
initializer calls and the int3 tail -- only the three call displacements
vary. Naming the target `il2cpp_runtime_class_init` routes the sites
through the existing class-init bookkeeping, which drops the call and
propagates the klass value (the helper returns its rcx argument).

Measured on Assembly-CSharp: remaining `sub_18043e360(` calls 0 (3
sites; 861 tree-wide). `PlayerLobbyHandler.Render`'s cluster collapses
from the helper call plus four bookkeeping temps to `obj16 = obj15;`.
No golden moved; goldens 64/64. Change-only vs `final_out` (r10): 115
files (the prior 114 plus `PlayerLobbyHandler.cs`).

Gates (Assembly-CSharp only, `--workers 1`): 490 types / 6,622 bodies /
0 failed / 0 fallbacks; brace 0/490; parse 0 bad / 0 ERROR / 0 MISSING;
portable suite 967 passed.

Tests: +2 portable (`tests/test_recovery_followup.py`: structural proof,
mutated fast-path compare decline) and +1 game
(`tests/test_game_class_init.py`: mi 26673 elides the helper).

## Current work: codegen intrinsics, landing 3 -- Interlocked.CompareExchange (2026-09-28, LANDED)

`_is_interlocked_helper` recognizes the helper by its exact body -- `lock
cmpxchg [rcx],rdx` with the comparand staged in RAX from R8, `cmovne`
keeping the observed old value, the barrier call, and the old value in
RAX -- with only the barrier's call displacement varying. `_call`
renders `System.Threading.Interlocked.CompareExchange(ref loc, value,
comparand)` (the emitter strips to `Interlocked` and adds the using);
the result keeps the value argument's type.

Measured on Assembly-CSharp: **all 21 helper call sites converted**
(`remaining sub_18043f880( calls: 0`), e.g. the event adds become
`System.Threading.Interlocked.CompareExchange(ref
FusionNetworkManager.__field_OnVoiceConnectionReady, ...)`. One golden
moved and was read: mi 47817 `AwaitableSocketAsyncEventArgs.Reserve`,
whose old body was a raw helper call plus a separate comparison and is
now one managed call with the comparison preserved. Goldens regenerated
against the scoped clean sweep and 64/64 pass.

Gates (Assembly-CSharp only, `--workers 1`): 490 types / 6,622 bodies /
0 failed / 0 fallbacks; brace 0/490; parse 0 bad / 0 ERROR / 0 MISSING;
portable suite 965 passed.

Tests: +2 portable (`tests/test_recovery_followup.py`: structural proof,
mutated `lock cmpxchg` decline) and +1 game
(`tests/test_game_interlocked.py`: mi 26409 renders the managed call).

## Current work: codegen intrinsics, landing 2 -- IsInst `as` (2026-09-28, LANDED)

`_is_isinst_helper` recognizes the IsInst body structurally, never by
address: fixed prologue (klass in RDX, object in RCX, null check), the
`Class::IsAssignableFrom` call, exactly one indirect `call qword
[rax+10h]`, the System.Object short-circuit `cmp rbx,[rip]; cmove
rax,rdi`, and a return. Both the thunk (`0x180434690`) and the real body
(`0x180479f80`) land in `rt_isinst`; `_call` then renders a `typeof(T)`
klass argument as `obj as T` -- the exact hardware semantics. Opaque
klass expressions (5,802 tree-wide) keep the honest `sub_` fallback
until element-class provenance lands.

Measured on Assembly-CSharp: 9 call sites across 3 files
(`FusionNetworkManager`, `MainMenu`, `MicAudioCanvas`) now render
`delegate as Action_1<...>`; remaining `sub_180434690(` calls: 60. One
golden moved and was read: mi 86310 `DateTimeStorage.Set`, where two
duplicate helper calls collapse into `System.IConvertible convertible1 =
value as System.IConvertible;` and the downstream call consumes the
typed value; goldens regenerated against the scoped clean sweep.

Gates (Assembly-CSharp only, `--workers 1`): 490 types / 6,622 bodies /
0 failed / 0 fallbacks; brace 0/490; parse 0 bad / 0 ERROR / 0 MISSING;
portable suite 963 passed.

Tests: +2 portable (`tests/test_recovery_followup.py`: structural proof,
mutated prologue/marker decline) and +1 game
(`tests/test_game_isinst.py`: mi 26309 renders the cast).

## Current work: F2 landed -- whole value-type loads and lane slicing (2026-09-28, LANDED)

The F2 decline below was superseded the same day: the missing piece was
consumer-side lane slicing, and both halves land together.

- `_aggregate_load` now returns a whole-size value-type fragment (the
  value itself) instead of declining into `_field_expr`'s first field,
  guarded four ways: exact whole-size load at offset 0, no `&x` address
  base, the first field must be narrower than the load (a single-field
  struct keeps its precise `this.m_State` spelling), and the type tuple
  must be a genuine VALUETYPE/GENERICINST (a typedef marked valuetype
  under a CLASS tuple -- mi 80548's `this` -- is type confusion, not a
  value load).
- Scalar-SSE arithmetic treats `_slice` fragments like `_parts`: the low
  lane comes from `_piece_value`, so a whole Color used by `divss`/`subss`
  renders `hdrColor.r`, not `hdrColor`.

Verified change-only against a HEAD baseline (same scoped build):
**88 Assembly-CSharp files**. Sampled and read: BabyDoll's `set` is a
16-byte `movups` copy and now stores `value` (was `value.x`, dropping 12
bytes); `FColorMethods.LerpMaterialColor` recovers per-field construction
(`(targetColor.r - color1.r) * real2 + color1.r`); `AutosaveScreen`
recovers `__t__builder.m_coreState.m_defaultContextAction` through the
whole struct; `CameraTranslation` slices `initialPosition.x` where the old
body subtracted a float from a Vector3. One golden moved and was read:
mi 72576 `get_ywxx`, `object obj1` -> `half half1` (a typing
improvement); goldens regenerated against the scoped clean sweep.

Gates (Assembly-CSharp only, `--workers 1`): 490 types / 6,622 bodies / 0
failed / 0 fallbacks; brace 0/490; parse 0 bad / 0 ERROR / 0 MISSING;
goldens 64/64; portable suite 961 passed.

Tests: +5 portable (`tests/test_native_values.py`: whole-value load,
address-base decline, partial decline, scalar-SSE lane slicing).

## Current work: F2 aggregate-load fragments -- probed and declined (2026-09-28, superseded by the landing above)

The audit's F2 (`_aggregate_load` discards whole value-type fragments, so a
whole-struct read renders its first field: `this.particleColor =
newColor.r`) was implemented and iterated three times on fixture evidence,
then reverted:

- The first pass returned every whole-size fragment. It fixed genuine
  whole copies (BabyDoll `set` is `movups xmm0,[rdx]` + a 16-byte store;
  the old body stored only `value.x`, dropping 12 bytes) but regressed
  single-field structs: the two `InputInteractionContext` getters lost
  their precise `this.m_State` spelling and mi 31664's InternedString
  became `object obj5`.
- Guarding "first field narrower than the load" fixed those, but the
  tuple check was still needed: typedef 9862 is marked valuetype under a
  0x12 CLASS tuple, so mi 80548 returned the whole job struct where the
  method wanted `this.positions`. With `te in (0x11, 0x15)` the golden
  stopped moving.
- The remaining blocker is consumption, not loading: a whole 16-byte
  Color read used by scalar arithmetic renders `hdrColor / real3` and
  `(targetColor - real3)`, where the native consumes the low lane
  (`hdrColor.r`, `targetColor.r`). The scalar-SSE and store consumers
  slice `_parts` but not `_slice` fragments.

Prerequisite: consumer-side lane slicing for `_slice` values in the
scalar-SSE arithmetic and store paths (`_piece_value` already has the
slicing logic). Then the whole-size fragment return (with the `&`-base,
first-field and tuple guards above) can land.

## Current work: F1 invalidation -- probed and declined (2026-09-28, NOT LANDED)

The audit's other F1 half -- invalidate the destination of unmodelled
instructions at `_insn`'s fall-through -- was implemented (an explicit
SIMD-write allowlist, since the pinned iced build has no per-operand
access oracle; a fresh unknown replaces the written register) and
measured on Assembly-CSharp: **145 files changed** (vs 59 before), with
a mixed outcome that did not justify landing it:

- Honest wins: stale lane values stop being consumed. `Blinker.LateUpdate`
  computed `original.r - color.g` because the SHUFPS write was ignored --
  the old body was silently wrong on every channel.
- But the unknown collapses recoverable values: Blinker's whole
  `new Color { ... }` becomes `material1.color = obj17;`, and in
  mi 80548 (`ViscosityVorticityJob.Execute`) the extra unknowns push
  expressions over `_mk`'s cap, replacing computed stores with `= 0`
  placeholders (57 -> 37 lines).
- 6 of 64 goldens move; their A/B diffs were read and include a
  float -> double type shift (mi 32832) that needs proof before
  acceptance.

A first attempt at **SHUFPS/PSHUFD/UNPCKHPS lane modeling** over the
existing `_parts` provenance was also written and reverted: it selected
the wrong lanes (all four Color channels rendered from `.a` on Blinker),
so the `_piece_value` slicing there needs its own investigation.

Direction stands, ordering changes: model the struct-construction lane
ops first (they are what the stale reads were silently reconstructing),
then invalidate what remains genuinely unmodelled. F1's invalidation
half stays open with this evidence.

## Current work: F1 slice -- MAXSS/MINSS arithmetic (2026-09-28, LANDED)

MAXSS/MINSS had operand-shape rows but no handler, so the destination
kept a stale live value (usually a fabricated `0f`). The SSE branch now
models MAXSS/MINSS/MAXSD/MINSD as the hardware-exact conditional
`(a > b ? a : b)` -- the second operand on equal/unordered, which is not
`Math.Max`'s NaN behavior. Long operand texts are bound to temps first
so a nested chain cannot double its way into `_mk`'s overflow
placeholder (77 such lines exist tree-wide; the count is unchanged
before/after).

Observed recovery (`FIMSpace/FColorMethods`): the old body tested and
divided by the stale `hdrColor.a`; the new one recovers the full
max(r,g,b,a) chain and divides by it. One golden moved and was read:
mi 23931 `FPSDisplay.Update` (28 -> 30 lines), which now carries the
`min()` the old body dropped; goldens regenerated with
`tools/make_goldens.py` against the scoped (Assembly-CSharp) clean sweep.

Measured on Assembly-CSharp vs `final_out` (r10): **59 files changed**
(the 49 before this slice + 10); `for (`/`while (` unchanged; brace
0/490; parse 0 bad / 0 ERROR / 0 MISSING; goldens 64/64 after
regeneration.

F1's other half -- invalidating the destination of genuinely unmodelled
instructions (SHUFPS ~1,646, CVTDQ2PS ~197 live reads in AC) -- remains
open.

Tests: +2 portable (`tests/test_native_values.py`: exact max/min render,
missing operand is an unknown).

## Current work: BSS ambiguous-name ties decline (2026-09-28, LANDED)

`_runtime_cell_usage` resolved a BSS runtime-cell name through
`by_name` and, when several same-named typedefs existed with no
System-namespace candidate, took the first metadata row. The fixture
has 3 such cells (`Pointer`, `Value` x2, of 1,582 cells total), and the
stored name string alone does not prove which row the runtime lookup
used, so the annotation is now declined on any multi-candidate
non-System tie.

Output-neutral on Assembly-CSharp (the same 49-file tree as the F3
batch); build 490 types / 6,622 bodies / 0 failed / 0 fallbacks; brace
0/490; parse 0 bad / 0 ERROR / 0 MISSING.

Tests: +1 game (`tests/test_game_bss_ties.py`) pinning that no cell
keeps an annotation whose simple name is ambiguous.

## Current work: F3 -- missing SSE operands are unknown, not `0f` (2026-09-28, LANDED)

Scalar-SSE and packed-logical handlers substituted a fabricated `0f` for
an operand register that is simply absent (clobbered by an earlier call),
so `real2 + 0f` and `(1.0f - 0f)` printed as if the value were zero.
`_fp_operand` now mints a fresh unknown (`vN`, `_unk`) for the NAME only;
the arithmetic around it still renders.

**A rejected first attempt, recorded.** Seeding XMM0-5 into
`_fresh_unknowns` after calls (the obvious reading of the item) was
implemented, tested and **reverted**: the raw block statements were
identical and only the `_u` temp numbering differed, yet the type
inference regressed in 146 files -- mi 24212 `FixedUpdate` turned
`for (int num2 = 0; ...)` into `object obj27 = 0; while (obj27 < ...)`.
The leak was real (XMM0-5 are caller-saved); the lever was wrong. The
narrow fix has no such coupling.

Measured on Assembly-CSharp vs `final_out` (r10, so it also carries the
earlier batches): **49 files changed** (the previous 15 plus 34
F3-affected); `for (`/`while (` counts unchanged at 381/593 (no loop
regressions); fabricated arithmetic drops: `+ 0f` 73 -> 47, `- 0f`
64 -> 25, `* 0f` 28 -> 16, `/ 0f` 3 -> 0. All 64 goldens still pass.

Gates (Assembly-CSharp only): strict scoped build at `--workers 1`: 490
types / 6,622 bodies / 0 failed / 0 fallbacks; brace 0/490; parse
0 bad / 0 ERROR / 0 MISSING.

Tests: +2 portable (`tests/test_native_values.py`: GPR-only seeding plus
the missing-`addss`-operand unknown), replacing the seeding test from
the rejected attempt.

## Current work: Dec F3/F4 -- hop-fold and select guards (2026-09-28, LANDED)

Two latent text-pass hazards, both 0 corpus hits, closed with
decline-by-default guards:

- `_compound_assign`'s hop fold now declines when any line between the
  hop definition and its copy is a brace, a label, or any write to the
  target (`x += 1`, `x.f = ...`, `x[i] = ...`); folding across one moved
  the write across that statement. Unrelated lines and the pre-existing
  hop-temp-use decline are unchanged.
- `_fix_select` now skips null operators the way `_strip_dangling_default`
  does: `?.`, `?[`, and `??` (both marks), so no `: default` is appended
  inside a null-conditional/null-coalescing expression.

Verified output-neutral: a scoped Assembly-CSharp build differs from
`final_out` (r10) in exactly the same 15 files as the previous two
batches (codegen landing + F4/F5), 490 types / 6,622 bodies / 0 failed /
0 fallbacks; brace 0/490; parse 0 bad / 0 ERROR / 0 MISSING; all 64
goldens pass.

Tests: +4 portable in `tests/test_review97_bare_decls.py`.

## Current work: F4/F5 -- array stride and true access widths (2026-09-28, LANDED)

The two remaining `{1: 1, 2: 2, 4: 4, 8: 8}` memory-size maps are gone:
the load path (`insn.py` `_read_mem`) and the store lvalue path
(`_mem_lvalue`) both take the width from `MemorySizeExt.size`. Constant
array accesses divide by the ELEMENT STRIDE, not the access width, in
both `_field_expr` and its second home in `_mem_lvalue`; a mid-element
offset or an unknown stride keeps the raw deref rather than a
plausible-wrong index.

Measured against a baseline at HEAD (the codegen landing, same scoped
build) on Assembly-CSharp: **4 files changed, 17 insertions / 13
deletions**:

- `ScrollRectFollowSelection`: `vector3Array1[0x3]` -> `[0x2]` (the
  audit's example; Vector3 stride 12).
- `ServerBrowserManager.AddFakeLobbiesForTesting`: native
  `mov dword [rax+24h],1` / `[rax+28h],2` now render `[0x1]` / `[0x2]`
  (was `[0x0]` / `[0x1]`).
- `ShelfItemManager`: two float-array indices corrected.
- `WFX_BulletHoleDecal` static ctor: boundary stores index by stride 8;
  mid-element dwords stay `((int*)arr + 0xNN)[0]` (honest).

Gates (Assembly-CSharp only, per this session's CPU rule): strict
scoped build at `--workers 1`: 490 types / 6,622 bodies / **0 failed /
0 fallbacks**; brace **0/490**; parse **0 bad / 0 ERROR / 0 MISSING**;
portable suite **949 passed**. The tree-wide effect is not rebuilt in
this batch; a promotion-time full build will size it.

Tests: +3 portable (`tests/test_array_identity.py`: stride division,
mid-element deref, unknown-stride deref) and `_sf_field_size` added to
the two lightweight `il` doubles that previously never needed it.

## Current work: post-r10 small fixes -- vtable sentinel, counters, `--only` (2026-09-28, LANDED)

Three easy audit leftovers, all output-neutral on this fixture:

- `slot_max_arity` (types.py) now applies the same empty-entry gate
  `vtable_method` uses (`idx == 0`, raw 0x0/0x1): a raw `1` no longer
  decodes as method row 0 and inflates a slot's arity cap when row 0 is
  an instance method. Masked on this fixture only because `methods[0]` is
  static (1,523 slots).
- The classic PE CodeRegistration reads the reverse-p-invoke pair in the
  same order as the Android loader and every other count/array pair:
  count at -16, wrappers at -15 (unconsumed today, so output-neutral).
- `--only` matching no assembly is now an error (exit 1) and writes
  nothing; previously it exited 0 after writing `script.json` /
  `stringliteral.json` and an empty tree. The image filtering moved
  before `os.makedirs` so a no-match run creates nothing at all.

Tests: +3 portable (`tests/test_runtime_vtable_arity.py`) and +1 game
(`tests/test_game_cli_only.py`).

## Current work: codegen intrinsics, landing 1 -- interface dispatch (2026-09-28, LANDED)

A read-only census of every plain `sub_` call site in the promoted r10
tree (38,254 sites, 2,663 targets) separated two populations: identity
misses (1,941 sites whose VA has metadata candidates) and **codegen
intrinsics (36,313 sites whose VA has none -- 95%)**. The top 25 targets
alone carry 22,840 sites. Structural disassembly identified the hot
families (index entry above); nullary interface dispatch is landed first
because its call sites already spell everything needed:
`(slot, typeof(IInterface), receiver, ...)`.

**Recognition.** `_iface_dispatch_arity` (state.py) proves a body is an
interface-offset dispatcher from its instructions, not its bytes: exactly
one `movzx ..., word [k+0x12E]` (interface count), one `mov ..., [k+0xB0]`
(interface table), one `add ..., 0x138` and one `shl ..., 4`
(method-entry fold), an indirect tail jmp, and a call on the miss path.
Of the family members found, the two hot ones (`0x180002210`,
`0x180002380`) read R9 -- the register right after slot/iface/receiver --
never; a reading variant forwards one managed argument and declines this
landing. `_init_runtime_ids` scans the hot-target set it already collects
and fills `rt_iface`; `_nullary_interface_dispatch` admits those members
structurally and keeps the older exact byte template as a second path.

**Return closure.** `IEnumerable<T>.GetEnumerator()` returns
`IEnumerator<T>`; the interface's instantiation comes from
`_generic_class_args(iface.ty)` and `_subst_closed` closes the return
tuple. An unclosable open T declines (`IEnumerator_1<T>` with no T in
scope parses but is not valid C#). Getter results keep the inline property
render.

**Binding.** Interface results are materialized at the call instruction
(getters excepted). Left lazy, the enumerator stack home declared one
temp and the phi copy's `_bind` minted a second, emitting a duplicated
`GetEnumerator()` whose second instance was the one iterated. The
shared-return path already bound immediately for this ordering reason.

**Measured.** Full strict `r12_out1` at `--workers 4`: 11,183 type files /
114,458 bodies / **0 failed / 0 structured fallbacks / 0 type-emission
failures** in 572,803 ms; brace audit **0 unbalanced / 11,183 files**;
parse gate **0 bad / 0 ERROR / 0 MISSING**. Per-file vs `final_out` (r10):
**696 of 11,276 files changed, file set identical**. Assembly-CSharp's
`sub_180002210`/`sub_180002380` call sites: **55 -> 0**, and
`IDisposable` sites now fold into `obj?.Dispose();` (the null-conditional
sugar pass finally has a real call to fold). Suite **1147 passed / 0
failed** (943 portable + 204 game).

Tests: +5 portable (`tests/test_recovery_followup.py`: family arity 0/1,
mutated body declines, structural admission, forwarder declines) and +2
game (`tests/test_game_interface_dispatch.py`: mi 26761 binds the
enumerator once with no `sub_180002210`, mi 27447 folds `?.Dispose()`).

**Declines kept.** Static methods, parameterized methods (this landing),
an unclosable return, a method not uniquely addressable by
`td.method_start + slot`, and any body the predicate does not prove; those
keep `sub_...`. The A-family parameterized variants are the next slice:
the helper forwards through R9 and the argument width must be matched to
the declared parameter type before it can render.

## Current work: parallel build re-land + heaviest-first schedule (2026-09-28, LANDED)

`--workers N` (first landed 2026-09-26 as `fb90229`, reverted minutes
later by `8fdbea2` with no reason recorded) is re-landed onto the r10
source, merged with the sunshine CLI additions (`--quiet`, `--json`,
`--manifest`, `--bodies`), and extended with a heaviest-image-first
submission order.

- **Schedule.** `_weighted_order` sorts the images by native method count
  (`MethodDef.image`, filled by the parent's `assign_images`) before
  submitting them; the executor hands queued work out in submission
  order, so the largest task no longer sits at the tail. Reporting stays
  in metadata order, so the log is the serial log; ties are stable, so
  the schedule is deterministic.
- **Integration declines.** `--bodies` now forces `--workers 1` with a
  note (the payload is written by the parent's own Emitter; a pool would
  write the empty dict), joining `--max-methods` and single-image
  builds. `--quiet` suppresses progress and decline notes, never errors.
- **Byte-identity, full tree.** Strict `r11_out1` build at `--workers 8`:
  11,183 type files / 114,458 bodies / 0 failed / 0 structured fallbacks
  / 0 type-emission failures; per-file sha256 against `final_out` (r10):
  **11,276/11,276 identical**, 0 only-in-either-side. Neither the
  re-land nor the schedule changes an emitted byte.
- **Wall time, measured not asserted.** 275.0 s this session vs 262.9 s
  (2026-09-26) vs 1,085 s serial. An instrumented 6-worker run measured
  worker efficiency **0.93** (busy 3,046 s over a 546 s wall), i.e. the
  tail costs <=8%, and the longest images are `Unity.TextMeshPro`
  (159.9 s) and `TextCoreTextEngine` (113.3 s) -- under-ranked by method
  count (1,739 / 719 methods). Code bytes, max method extent and top-5
  extent all fail to rank them high, so the residual wall is real work
  plus box load (the box carried ~30% external CPU load all session, and
  the same 6-worker run measured ~2x the 8-worker build's per-image
  times): the next lever is a cost model or splitting one image across
  workers, not more reordering.
- **Tests.** +13 portable (re-landed `tests/test_parallel_build.py`),
  +7 portable (bodies decline, weighted-order stability/subset/ties,
  quiet gating), +2 game (`tests/test_game_parallel_build.py`, serial vs
  pool byte-identity). Suite **1140 passed / 0 failed** (938 portable +
  202 game).

## Current work: promotion r10 (2026-09-28, PROMOTED)

User-authorized ("promote without rebuilding"). The audit-batch-3 strict
candidate `r10_out1` was promoted in place by rename with a per-file sha256
proof: 11,276 files, candidate aggregate `b0c87509…b9fe` == promoted
aggregate, **0 mismatches / 0 missing / 0 stale**, file set identical to r9
(302 files differ). `final_out/` now holds r10 everywhere; the r9 backup
and the emptied candidate path were removed. Evidence:
`validation_reports/promotion_r10.json`. The candidate was built from the
batch tree (the audit-batch-3 content, now commit `68ed034`; the
CLI/emitter-only commits it was rebased over -- the parallel-build revert
and the sunshine additions -- do not change any emitted `.cs` file).

## Current work: audit batch 3 — five landings, three layers (2026-09-28, LANDED/PROMOTED)

Read-only audits of the lifter, dec+emitter, and runtime layers plus a
base/post corpus census produced five defects of the same class -- silently
wrong rather than honestly raw. All five are landed here; the deferred
findings with their evidence follow.

1. **Shared-body argument lanes** (`il2cpp/lifter/calls.py`). Every
   candidate of a shared address names a call into the same machine code,
   so `_shared_slot_classes` proves the register class of each argument
   slot when all candidates are readable non-generic MethodDefs and agree
   (receiver and consensus sret buffer = GPR, R4/R8 by-value params =
   XMM); `_shared_positional_args` then rebuilds the printed list by ABI
   position. The raw GPR-first spray truncated to the arity cap printed
   the stale RCX value where a float parameter lives and dropped the real
   XMM argument: mi 20081 `Angle/StyleFloat/TimeValue.op_Implicit`
   (`(obj1)` -> `(0f)`), mi 20080 `Rotate(Quaternion)` (the dropped
   `real1 * 57.29578f` conversion comes back), mi 65682's `mulss
   xmm0,xmm0` leaf (`(obj45)` -> `(radius)`). 217 agreeing VAs / 417
   sites sized; generic/mixed/disagreeing sets and classes past the four
   argument registers keep today's truncation.
2. **icall overload selection** (`il2cpp/runtime/fields.py`). The old
   name-only scan returned the first same-named metadata row, and `_call`
   then trimmed to that overload's arity: `UnityEngine.Object::
   FindObjectsOfType(System.Type,System.Boolean)` rendered `(type)`; the
   AndroidJNI `To*Array(ptr,int)` family, `UnsafeUtility.IsBlittable`,
   ObjectDispatcher and LightProbesQuery lost arguments or the receiver.
   `_icall_sig_params` tokenizes the runtime signature's own parameter
   list; `_icall_pick_overload` settles it by unique arity, else by
   normalized parameter types (`_icall_type_key`: CLI primitives, `/`->`.`,
   backtick arity, byref markers). 17 cells change, 0 identities lost, 0
   gained.
3. **Literal safety** (`il2cpp/dec/textpass.py`, `il2cpp/dec/highlevel.py`).
   `_render`'s blanket `$` -> `_` corrupted every literal it touched --
   JSON.NET wire names (`$type`/`$id`/`$values`), the UTF7 direct-character
   set, a money template -- and `_rename_locals` renamed tokens inside
   literals and comments, rewriting the ADO.NET diffgram namespace
   (`urn:...-diffgram-v1` -> `...-obj83`). `_sanitize_dollar` skips
   strings/chars/comments and `$"`/`$@"` prefixes; `_mask_literals`
   NUL-blanks the same spans (length-preserving) for both the token scan
   and the substitution.
4. **Five per-instance runtime caches** (`_tn_cache`, `_slot_cache`,
   `_fo_cache`, `_sf_infl_cache`, `_mod_ptr_cache`): the remaining members
   of the audit-batch-1 class. TypeDef/field indices and slot VAs are
   binary-local; all are now `self.__dict__.setdefault` maps, and cli.py /
   `tools/corpus_common.py` free the pointer arrays through
   `getattr(il, '_mod_ptr_cache', {})`. Output-neutral.

**Gates.** Strict `r10_out1`: 11,183 type files / 114,458 bodies / 0 failed
/ 0 structured fallbacks / 0 type-emission failures in 1,465,953 ms
(24.4 min -- the box carried an unrelated `mc-wasm` build; r9's 1,085 s
was an idle box); brace audit **0 unbalanced / 11,183 files**; parse gate
**0 bad / 0 ERROR / 0 MISSING / 0 recovery nodes**. Paired corpus sweep
(`tools/validate_corpus.py sweep` post vs the pre-change body dump):
116,178 methods, **0 crashes both sides**, `brace_unclosed` 0,
`brace_underflow` 0, `dangling_gotos` 0, `empty_args` 0,
**into_block 8,075/2,046 identical** to the r9 baseline, lines 2,253,029
-> **2,251,858**; 613 bodies changed, 0 added/removed. Tree diff
`final_out/` (r9) -> `r10_out1`: 11,276 paths both sides, **302 files
changed**, file set identical, **-1,171 lines** in changed files,
`unknown` 5,225 -> 5,168, `"$..."` literals 1 -> 75, diffgram `-v1`
0 -> 50, `shared` -1, `indirect`/`goto`/`memN`/`?addr`/`/* nothing */`
flat. One golden moved, user-visible in review: mi 80548 `Execute` --
comments are no longer renamed (they keep raw `t1000`/`v46` names), which
stops the renamed comment text from feeding the later DCE, so a dead pure
cluster (real1..real12, self-referential; terminal real5/real12 read
nowhere) drops; all 6 store lines survive, only the array bases renumber.
Goldens regenerated after the gates with `tools/make_goldens.py`; the diff
is exactly that one body. Suite: **1118 passed / 0 failed** (918 portable
+ 200 game; the hash-only goldens test was added in the public scrub).

Tests: +14 portable shared-slot classes +4 game, +14 portable icall
overloads, +5 portable cache isolation, +5 portable literal safety +2
game.

**Deferred findings, evidence recorded (not landed).**
- Lifter F1: unmodelled instructions fall through silently and leave a
  stale destination live (MAXSS/MINSS mistyped as `0.0f` in promoted
  output; ~1,970 live destination reads in Assembly-CSharp alone, mostly
  SHUFPS ~1,646, CVTDQ2PS ~197). Needs destination invalidation on the
  fall-through plus the MAXSS/MINSS arithmetic family.
- Lifter F2: `_aggregate_load` discards value-type fragments, so a
  multi-byte struct load renders its first field (`this.particleColor =
  newColor.r;`); 2,304 declining loads, 490 rendering narrower than the
  access. An address-base guard is required (a naive fragment return
  regresses `&x` bases).
- Lifter F3: XMM0-5 get no fresh unknown after a call, so scalar SSE
  arithmetic substitutes `0f` (35 sites in Assembly-CSharp; the
  documented AudioVolumeSliders loss is the same mechanism).
- Lifter F4/F5: constant-displacement array access divides by the access
  width, not the element stride (`vector3Array1[0x3]` is really element
  2); the `{1:1, 2:2, 4:4, 8:8}` memory-size map is wrong for the pinned
  iced-x86 build (`MemorySizeExt.size` already exists).
- Dec F3/F4 (latent, 0 corpus hits): `_compound_assign`'s hop fold can
  cross writes/braces/labels; `_fix_select` appends `: default` to `?.`/
  `??` inside parens (mirror `_strip_dangling_default`'s guard).
- Dec F5/F6 (0 corpus hits): four more literal-blind token substitutions;
  `_sfblob_dedupe` keys by owner+value, ignoring the blob offset.
- Runtime: vtable sentinel raw `1` decodes as method row 0 whenever row 0
  is not static (1,523 slots on this fixture, masked only because
  `methods[0]` is static; `slot_max_arity` has no sentinel gate);
  `reverse_p_invoke_count`/`_wrappers` are swapped in the classic PE
  loader (unconsumed today); `--only` matching no assembly exits 0 after
  writing an empty tree; BSS runtime-cell name ties break by first
  metadata row.
- Confirmed open, unchanged: the `0x1825b1150` ToString/op_Implicit pair
  has slot class `g` for both candidates (instance receiver / by-ref
  struct param), so the lane proof does not apply; identity still needs
  receiver/use or instantiation proof.

## Current work: promotion r9 full tree (2026-09-26, PROMOTED)

User-authorized (promotion on call). Strict full-tree rebuild `r9_out1` from
clean HEAD `e20f82f`: **11,183 type files / 114,458 bodies / 0 failed / 0
structured fallbacks / 0 type-emission failures in 1,085 s**; brace **0
unbalanced**; parse **0 bad / 0 ERROR / 0 MISSING / 0 recovery nodes**
(11,183 files, 13.1 s). An independent second strict build `r9_out2` is
**byte-identical** (11,276 paths, aggregate `73f4426d\u2026c8821` on both
sides, 0 per-file mismatches). Promoted by mirror copy with a per-file
sha256 proof; the promoted aggregate equals the candidate aggregate and 0
stale files were left behind. `final_out/` now holds **r9 everywhere**, so
r7 and r8 (Assembly-CSharp) are history.

This is the first full-tree promotion since r7, so it carries four landed
batches at once, not one. 918 of 11,276 files changed; file set identical
(0 added, 0 removed); 10,358 byte-identical; **net method-signature delta
0**, no file lost a declaration; net +58,613 lines (286 shrank, 401 grew,
231 same). Measured, not asserted:

- **Audit batch 2 (the RBP frame).** Fabricated pointer arithmetic
  97,531 -> **83,314** (-14,217) in 3,126 -> 3,088 files, reproduced with an
  independent regex (the batch's own figure was -14,169, 0.3% apart).
  Shrinkers are the expected shape: `TypeConversion.cs` -658, `X86.cs`
  -592, `ConverterGroups.cs` -549, `VisualElement.cs` -375.
- **Shared-tail arity trim.** Shared calls carrying an invented trailing
  `0`: 3,880 -> **3,519** (-361) in 1,086 -> 923 files. Calls keep a real
  trailing `0`; mi 24077 keeps its four-argument `List<T>.CopyTo` tail.
- **Noreturn-shared forwarder returns.** `/* nothing */` **63 -> 0**, with
  63 `return Neon.<s8-variant>(...)` in `Arm.cs`.
- **Identical-render collapse + stub comments, tree-wide.** Resolved
  identical-render names 52 -> 109 occurrences; every `__SharedBodyStubs.cs`
  grows (mscorlib 1,250 -> 9,995 lines, UIElements 606 -> 5,162, ten more
  assemblies) from the native-disassembly comments that until now were
  promoted only for Assembly-CSharp.
- **Flat where it should be flat.** `goto`, `memN`, `qaddr` unchanged;
  `indirect` -4; `shared` 16,916 -> 16,834 (net **-82**).

Marker increases, read rather than waved through:
- `unknown` **+53 across 59 files** -- typed-but-unknown frame slots
  (`Vector3 vector35 = unknown;`) replacing fabricated pointer arithmetic
  in the same statements, which is the trade batch 2 documented. The
  fabricated count falls 14,217 in the same diff.
- **One** net shared-marker increase tree-wide, user-called and accepted:
  mi 23602 `StandingPeopleConcert.SpawnPeople` loses
  `Quaternion.Internal_FromEulerRad` to `sub_180895b20/*shared body, 9
  candidates*/`, because E3 typed the frame home `Vector3` and a partial
  vector store leaves the value honestly `unknown`, so the call argument is
  no longer a reconstructed `new Vector3 { ... }` literal for `_call` to key
  on. One lost callee name against a value that is no longer fabricated.

Evidence in `validation_reports/promotion_r9.json`. Suite at the promoted
commit: **1071 passed / 0 failed** (877 portable + 194 game). Scratch trees
removed. **Timing correction:** a full 91-image strict build is 1,085 s
(18.1 min) for 114,458 bodies on this box, not the 1,359 s the index and
`AGENTS.md` carried from the batch-1 measurement.

## Current work: one shared body, one argument list (2026-09-26, LANDED)

The `GetHashCode` mixed-VA item from the shared-residual audit is closed,
narrowly. What the audit had found was a rendering inconsistency, not a
missing identity: MSVC folds the no-arg `GetHashCode` forwarders onto one
body (`xor edx,edx; jmp 0x181b14c10`), so the same address printed two
different argument lists depending on how it was reached.

    // mi 8752 ConstructorInfo.GetHashCode, before
    return (int)sub_181b14c10/*shared body, 13 candidates*/(this, 0);
    // mi 3961 Delegate.GetHashCode, same address, called not jumped
    int num2 = (int)sub_181b14c10/*shared body, 13 candidates*/(this.m_target);

The `0` is callee-zeroed plumbing. The forwarder zeroes EDX for the callee,
no candidate at that address declares a second parameter, and the two twins
that *do* resolve at the same VA (`EventInfo` mi 8771, `FieldInfo` mi 8790)
already printed one argument. After: `return (int)sub_181b14c10/*shared
body, 13 candidates*/(this);` -- the call and the tail finally agree.

**The proof is 21j's, reused rather than reinvented.** Every candidate at an
address names a call into the same compiled machine code, so they all consume
the same argument registers, and the largest declared arity among them --
receiver included, plus the hidden sret buffer when the return is the
all-candidates consensus -- bounds the slots. `_call` has used that bound
since batch 21j; the inline loop is now `_shared_arity_cap`, and
`_shared_tail_keep` reuses it for a tail. Extracting it also hardened the
`_call` side for free: the old inline loop indexed `meta.methods[c[1]]`
unchecked and let a malformed candidate row propagate, while the helper
bounds the index and skips what it cannot read (`None` = nothing readable =
keep today's spelling).

**Narrow on purpose.** Only a trailing run of literal `0` is droppable, and
only below the cap, because that is the register a shared forwarder zeroed
(`xor edx,edx` / `mov r8d,0` right ahead of the jmp) rather than something
the source wrote. Everything else declines to today's spelling: a non-zero
extra argument inside the four argument registers, a single candidate, an
unreadable candidate, a cap that does not sit below the list, and a list of
one or fewer. Past `ARG_REGS` the zero-run check does not read at all --
those slots are stack-passed, where no candidate's declared arity can reach,
so the cap alone bounds them. A *resolved* tail is never touched -- an
identified callee owns its own signature, and the receiver /
hidden-generic / same-render proofs above the new trim still run first.

**Scale, measured rather than sampled.** The only methods this can touch are
those that `jmp` into a multi-candidate address: 5,437 of 114,458. That set
was lifted twice -- once from a pre-change source root (the package with the
three touched files restored from `HEAD`, so the working tree was never
stashed) and once from the new one -- and the two body sets diffed:

- **349 bodies changed / 363 lines, 0 new crashes** (0 pre, 0 post), 0
  line-count changes, 0 bodies longer. Every changed line is byte-for-byte
  its pre-image with the *last* `, 0` removed from that shared call's
  argument list; nothing else moved on any line.
- 386 methods fire in the real pass. The 37 whose body does not change have
  their shared marker replaced downstream (identical-render collapse:
  `return x == y;` at mi 2603), so the trim is invisible there, not wrong.

The instrumented census behind that: 775 fires -- 399 real pass, 376 dry
pass -- over 531 (method, address) pairs, 529 distinct methods, 112
addresses, and every fire removed exactly one argument (295 `2->1`,
413 `3->2`, 67 `4->3`). Largest families by distinct methods:
`0x182b75030` 97 (30 candidates, the `(this, 0)` `.ctor` shape),
`0x181af7520` 73 (string `Equals`/`op_Equality`, `(x, y, 0)`), `0x182be3aa0`
54 (`DockInSlot`), `0x1807ee180` 29, `0x181bb6bf0` 16 (handle
`Release`/`Close`), `0x181cffb70` 15 (`GetHashCode`).

**Unchanged, deliberately.** Calls were already bounded by 21j, so the 196
tree-wide `return (T)sub_...(... , 0)` lines whose `0` is a real argument
(`op_Equality(x, null)` and friends, cap 2 = the list) keep it. So does a
tail whose extra registers are genuinely read: `mi 24077 SelectNuisanceType`
still prints the four-argument `List<T>.CopyTo` tail at `0x180df9c30`, the
probed case where the registry missed a sharer that dispatches on R8.

**Accepted risk, stated rather than hidden.** A registry-missed sharer whose
extra register is a *zero* the body really reads would lose that argument,
and the absence of such a sharer is unprovable from the registry. The visible
alternative -- one body printing `(x)` at a call and `(x, 0)` at a tail, in
the same file -- is the defect being removed, and it is the shape a reader
cannot tell from a real parameter.

Tests: +18 portable (`tests/test_shared_tail_arity.py`: cap arithmetic, the
sret slot, generic specs, unreadable rows, and every decline arm), +6 game
(`tests/test_game_shared_tail_arity.py`: mi 8752 / 13198 / 78202 / 1231
trimmed, mi 8771 / 8790 twins unchanged, mi 3961's call site unchanged, mi
24077's read registers unchanged). Full suite **1071 passed / 0 failed**
(877 portable + 194 game) with the change in place; no golden moved.

## Current work: audit batch 2 -- the RBP frame survives a CFG merge (2026-09-26, LANDED)

The largest quality defect the audit found: a method that sets up a frame
pointer loses it at the first CFG merge, and every `[rbp+N]` in the merged
region becomes pointer arithmetic on the never-written seed.

**E1 -- the frame fact.** `_rbp_is_frame()` read the register *value*, and
the pass-2 phi merge rewrites that value out from under it. A never-written
`RBP = None` (exactly what `mov rbp,rsp` produces, since RSP is never
tracked) becomes `Expr('?', None, '?')` at `analyze.py:460`, and `_bind`
then rewrites that into a temp name. In a merged block *every* arm of the
predicate failed -- `None`, `'?addr'`, `_unk`, `&s_` -- and `_read_mem` /
`_mem_lvalue` fell out of the frame branch into the raw-deref branch.
Measured on `WrapRopePlayerController` (mi 24062, `push rbp; mov rbp,rsp;
sub rsp,50h`): **21 sites** like

    ((byte*)obj9 - 0x30)[0] = vector31;      // movsd [rbp-30h], xmm6
    ((float*)obj9 - 0x28)[0] = real1;         // mov   [rbp-28h], ebx
    this.rb.AddForce((obj9 - 0x30), ForceMode.Acceleration);

`obj9` is not a pointer, and because it was *named* every statement was legal
C#, so the parse gate saw nothing. An instrumented trace showed 64
consultations split across two states -- 32 with RBP text `'?'`, 32 with
`'v45'` -- which is why the obvious `t == '?'` test fixed only half of them.

The fix tracks the fact instead of inferring it: `_rbp_frame` is set by
`mov rbp,rsp`, cleared by any other write to RBP inside `set_reg` (the one
place every register write passes through), and never derived from the
register value. It survives the merge because the merge installs values with
`L.regs[k] = ...` and so bypasses `set_reg`. `_defpos` is not a usable
discriminator either: `_copy_expr` drops it, so "no definition site" cannot
distinguish an unwritten register from a copy of a written one.

Same method after: typed `UnityEngine.Vector3` locals, a real
`Vector3.Normalize(...)`, and the real `this.rb.AddForce(vector32,
ForceMode.Acceleration)`. The 16-byte `movsd` store into a Vector3 home
stays `vector32 = unknown`, which is the honest marker, not a guess.

**E3 -- one home, one key.** `slot_var` keys by `off + rsp_delta` and names
by `abs(off)`, but callers disagreed on sign: the RSP-copy path passes an
already sign-extended `_stack_address`, while the RSP/RBP direct paths and
the LEA path pass `ins.memory_displacement` raw (iced-x86 reports `[rbp-0x30]`
as `0xffffffffffffffd0`). One method held two coordinate systems for one
native home -- mi 24062 held both `(-24, 's_40')` and
`(18446744073709551480, 's_ffffffffffffffd0')` -- so a `[copy+N]` write and
an `[rsp+M]` read of one slot became two C# locals and the provenance layer
could not see the naming layer. `slot_var` now normalizes with `sdisp` at
that single choke point; `sdisp` is idempotent on an already-negative value,
so every correct caller's name is byte-identical and only the raw paths move.

**Scale.** A regex census of the pre-batch-2 full build counts **87,471
fabricated-pointer sites in 2,795 files** -- well past the audit's
per-method extrapolation (~25k instruction sites), because an affected
method carries many sites. Worst hit: `Unity.Mathematics` at 22,432, then
UIElements 8,576, mscorlib 6,830, System.Xml 4,713. Assembly-CSharp scoped
rebuild: **2,938 -> 2,027** (-911, -31%) with 60 of 491 files changed. The
residue is the honest unknown-base decline rather than the frame bug: a
`[rbp+N]` off a base the lifter never proved still renders raw, which is the
intended direction.

Tests: +16 portable (`tests/test_rbp_frame.py`), +8 game
(`tests/test_game_rbp_frame.py`, `tests/test_game_rbp_frame_reset.py`).

Gates, all against the final source:
- **Paired full-corpus sweep, pre- vs post-**: 116,178 methods, 0 crashes
  both sides; `into_block` **8,075 / 2,046 identical** (so the +4 sites /
  -2 methods against the `CLAUDE.md` baseline is pre-existing drift from
  earlier commits, not this batch); brace 0 unclosed / 0 underflow; 0
  dangling gotos; 0 empty args; tail-arg changes 1,881 / methods 1,801
  identical; 2,253,753 -> 2,253,029 lines.
- **Per-method compare**: 1,537 changed bodies, **0 structural changes, 0
  new crashes**, 0 added / 0 removed methods.
- **Full strict rebuild**: 11,183 type files / 114,458 bodies / 0 failed /
  0 structured fallbacks / 0 type-emission failures; brace audit
  **0 unbalanced**; parse gate **0 bad files / 0 ERROR / 0 MISSING / 0
  recovery nodes**, exit 0.
- Corpus-wide fabricated-pointer sites **87,471 -> 73,302** (-14,169,
  -16.2%), files 2,795 -> 2,752.

Read before accepting, per the golden rule:
- `Computer.cs`: 72 fabricated sites -> 0, and MSVC's struct-copy idiom
  comes back as real Unity code -- twelve invented byte-pokes through
  `obj13` become `Navigation navigation2 = navigation1; navigation1.m_Mode
  = Mode.Vertical; this.inputText.navigation = navigation1;`.
- `CurrentDayManager.cs`: 51 -> 0, `Quaternion quaternion1 = default;`
  replacing `((int*)obj1 + 0x28)[0] = 0;`.
- `mi 104428 GetBounds` (golden moved): the value no longer round-trips
  through a fabricated `((byte*)obj41 + 0x0)[0]` hop before reaching the
  frame slot. The surviving `((byte*)obj40 + 0x0)[0]` is the honest
  unknown-base decline, not a regression.
- `mi 105455 ValidateLine` (486 lines, `lea rbp,[rsp-70h]`): recovering the
  frame **retyped** its slots from `object` to `UnityEngine.Vector3`, so
  the `object obj87 = unknown;` twin that test pinned no longer occurs
  there and the use-site is now the better `UnityEngine.Vector3 vector36 =
  vector34.normalized;`. The dead-unknown-store pass stays pinned by the
  LagCompensationUtils test.

One honest cost, measured rather than waved through. `mi 32833 OnStateEvent`
is a `lea rbp,[rsp-38h]` method, so it moves under **E3 alone** (E1 does
not touch LEA frames): `int num1 = default;` becomes `int num1 = 0;
num1 = 0f;`. The int type and the zero value are now correctly recovered
from the slot's `num1 != 1` use, but a **new CS0266** appears -- `0f`
assigned to an `int` local -- next to the pre-existing one (`object` into
`int`). Counted across Assembly-CSharp, scalar-declared-with-float-RHS goes
**550 -> 557 (+7)**, in **3 of the 60 changed files**. That is a
pre-existing lossy area (550 instances before this batch) touched
marginally, against 911 fabricated pointer sites removed in the same
assembly, so it is accepted and recorded here rather than used as a reason
to narrow a provably-correct key-space fix.

Invariants recorded in `CLAUDE.md`.

## Current work: audit batch 1 -- per-instance caches, struct sizes, ELF gate (2026-09-26, LANDED)

A read-only audit of the whole package (lifter / dec+emitter / runtime+
metadata / repo+docs, plus an independent corpus census and a full timed
rebuild) produced three defects that all share one failure mode: silently
wrong rather than honestly raw. All three are fixed here, and none changes
a byte of emitted output.

**1. Three class-level caches keyed by a binary-local TypeDef index.**
`Decompiler._TDNAME_CACHE` (`dec/sugar.py:344`) was a class attribute
written through the `_LateDecompiler` proxy, and `Emitter._us_cache`
(`emitter.py:637`) / `_delegate_cache` (`:671`) were mutable
class-attribute dicts never reset in `__init__`. TypeDef indices are
binary-local -- the invariant `CLAUDE.md` states for `_chain_cache` /
`_bases_cache` -- so a shared map hands a second `Decompiler` / `Emitter`
(a second fixture, which the open Cpp2IL cross-check needs) **another
binary's index**. Reproduced: with `('Alpha','Widget')` at index 0 in
binary A and index 1 in binary B, B resolved 0, and `_static_field_name`
then emits *another type's* static field name -- a wrong name with no
marker, not a crash. All four maps are now per instance, created lazily
via `self.__dict__.setdefault` because ~80 test sites build a
`Lifter`/`Decompiler`/`Emitter` with `__new__` and never run `__init__`.
The two delegate answers also move into separate dicts: they shared one
dict, distinguishable only because an `int` key can never equal a
`('viable', int)` key. The `Emitter._delegate_cache.clear()` workaround at
`tests/test_review113_type_decls.py:27` existed only because of the class
attribute and is gone.

**2. Negative struct sizes.** `runtime/registration.py:522` read
`v - 0x10 if v else None`, whose guard caught only `v == 0`, so every
`0 < instance_size < 0x10` became a **negative** size -- 91 rows in the
fixture (values `-15` and `-8`, all `<Module>` definitions), against a
comment three lines above promising "kept as `None` rather than a
negative number". Nothing consumes those today (`returns_sret` tests
`== 0x11`, `_return_abi_is_known` tests `> 0`), which is luck rather than
design: a negative size is exactly the value that flips a hidden-sret
decision and shifts every argument register. Now `v >= 0x10`.

**3. The Android registration fallback ran on a PE.** `cli.py` caught
any `RuntimeError` from `find_registrations()` and then tried
`find_registrations_android()`, which assumes a *different struct
shape*. Probed on the x64 fixture it does not fail: `code_reg_va =
0x183067830` against the classic `0x183067820` -- 0x10 low -- with the
same 91 modules and the same 116,178/128,954 resolved coverage. So a PE
with no classic registration traded a clean error for a silently wrong
one. The fallback is now gated on `isinstance(bin_, ELF)`, and the whole
registration phase reports `error:` instead of tracebacking.

Tests: +7 portable (`tests/test_cache_isolation.py`), +3 game
(`tests/test_game_type_sizes.py`). Full suite **1023 passed / 0 failed**
(843 portable + 180 game), no golden regeneration -- the 64 frozen bodies
are unchanged, which is the first evidence the batch is output-neutral.
Output-neutrality gate: a scoped strict rebuild (mscorlib,
Assembly-CSharp, Unity.Mathematics, Fusion.Runtime) is byte-identical to
the same assemblies from the pre-patch full build. Invariants recorded in
`CLAUDE.md`. The `~7-9 min` full-rebuild figure at `CLAUDE.md:407` is
**stale**: measured 1,359 s (22.7 min) for 114,458 bodies on this
12-core box, against a 1,374 s serial prediction (1.5% error).

## Current work: constant-zero fold DISPROVED (2026-09-25, DOCUMENTED)

Subagent census + independent ground-truth probes closed the
"constant-zero fold (239 sites, 2 VAs)" as a fold slice -- no source
change, markers stay honest.

The 2 VAs (scan counts sum exactly 216 + 23 = 239; claimed N ==
method+generic on both):
- `0x180625830` (216 sites): `xor al,al; ret`. 459 method owners
  (`bool` 456 + 3 structs) + 3,075 generic sharers. `xor al,al`
  zeroes only the low byte -- and struct owners share the address
  (probed mi 5208 `Task.Yield->YieldAwaitable` at the same VA), so
  multi-byte readers take entry-stale upper bits: not even
  value-uniform, disproved at native level before typing.
- `0x180507630` (23 sites): `xor eax,eax; ret`. Value-uniform zero
  (zero-extends full rax), but 304 owners across `int`/`string`/
  `XmlSchema`/`object`/`Material`/`long`/`Nullable<int>`/enums/arrays
  + 17 generic sharers -- no single C# literal spells zero across
  them; generic gate blocks regardless.

Call-site shapes (probed, not just scanned): `0x180625830` fires only
in `MoveNext()` triple-patterns with `object` results
(`object obj25 = sub_180625830/*shared body, 3534 candidates*/(0)`,
forwarded then `== null` null-tested) -- folding to `false`/`0`
mistypes the box, guesses the null test, and corrupts awaiter slots.
`0x180507630` sites are heterogeneous reference casts
(`(Material)sub(...)`, `return sub(...)` as reference) where `0`
does not compile; only `null` would work, needing owner proof.
Neither VA is the bare-`ret`, identity-leaf, string-fallback, or
struct-buffer zero nearby (`0x180506120`/`0x18063ac90`/
`0x1825b1150`/`0x180d931a0` all disjoint, checked).

This also confronts the unknown-never-becomes-zero guardrail
(`test_recovery_completion.py:490`): a fold here would rewrite
untyped `object`/`unknown` text, exactly what the pin forbids.
Verdict: decline both VAs. Next payoff: the ToString/op_Implicit
static+arity spray probe (865 sites, 1 VA `0x1825b1150`, disjoint).
No goldens moved; suite untouched (no source change; portable
836/0 re-verified green this session).

## Current work: same-name receiver pick DISPROVED (2026-09-25, DOCUMENTED)

Subagent census + ground-truth probes closed the multi-owner same-name
bucket as a return/static/arity elimination slice -- no source change,
markers stay honest.

Census (read-only regex over `final_out/` 11,183 files + a per-VA
`Il2Cpp.addr_candidates` join; scripts + `scan.json`/`join.json` live
only in temp): 2,772 sites / 159 VAs with one shared short name across
owner typedefs (audit's 2,752/155 plus the r8 ACS churn delta; marker N
== live method+generic counts on all spot checks). 54% of bucket sites
(1,493 / 29 VAs) carry generic sharers, so any sig slicer must decline
them first anyway.

Probes (`tools/inspect_methods.py`, `PYTHONHASHSEED=0`):
- GetResult 8478 vs 8497 share `0x181baa030` byte-identically, both
  instance `()->void`; caller 62090 passes `&object` with a void use --
  return, static/instance and arity are all vacuous.
- get_IsCompleted 8475 vs 8494, both instance `()->bool` (+ 34 generic
  sharers); the `test al,al` bool use is shared by both candidates.
- float2/3/4 `get_Item` 70880/71276/71965 share `0x180d259b0`, all
  instance `(int)->float` (+ 2 generic) -- generic gate blocks regardless.
- `InternedString.ToString` 35666 (instance, 0 params) vs `op_Implicit`
  35675 (static, 1 param) share `0x1825b1150` (`mov rax,[rcx]...ret`),
  865 sites: both consume exactly one register and return `string`, so
  static/instance+arity cannot split them; callers pass `&object`
  (32174 `string text1 = (string)sub_1825b1150(&obj14)`). Same shape for
  the `Char.ToString` twins (82 sites).
- `HexToInt` 96557 (`int`) vs 110140 (`uint`) share `0x182af9c50`
  byte-identically; caller 110055's uses are sign-agnostic
  (`num58 + (num57 << 4)` -- `+`/`<<` identical for int/uint), so a
  return-use rule must decline; a fire needs a sign-proving use, none
  found.
- `op_Implicit` triple `0x182da54f0` (Angle/StyleFloat/TimeValue):
  caller 13332 passes untyped `object`, result flows to `object` --
  use-type is `object`, declines.
- Mixed `GetHashCode` VA `0x181b14c10` (10 sites, 12 instance +
  `RuntimeHelpers` static): the shared body is a 2-insn forwarder
  (`xor edx,edx; jmp`), so the trailing `0` in `(this, 0)` renders is
  callee-zeroed stale, not a param -- and both shapes still fit one
  register. Tail rendering is already inconsistent across identical
  twins there (EventInfo/FieldInfo resolve, ConstructorInfo keeps the
  marker); touch nothing.

Verdict: the headline ~1.9k (GetResult 412 + get_IsCompleted 347 +
floatN get_Item 323 + ToString/op_Implicit 865) needs receiver proof
(field sidecar + use->def + whole-tile preference, per the 25687/24238
TaskAwaiter precedent) or instantiation proof -- not sig elimination.
Remaining next payoff (constant-zero since disproved, see above): the
ToString/op_Implicit spray probe (865 sites, 1 VA `0x1825b1150`).
No goldens moved; suite untouched (no source change).

## Current work: promotion r8 Assembly-CSharp (2026-09-24, PROMOTED)

User-scoped (Assembly-CSharp only; full-tree rebuild aborted by user
call after ACS completed). Strict `--only Assembly-CSharp` rebuild from
clean HEAD `e3c7512`: 490 type files / 6,622 bodies / 0 failed / 0
fallbacks / 0 type-emission failures; brace 0 unbalanced; parse 0/0/0;
file set identical to r7 ACS (491 paths, 4 files differ). Triage:
identical-render `ComputeStringHash` x3 (ControllerLayoutMenu,
InventoryManager, Telephone) + stub disassembly comments
(`__SharedBodyStubs.cs` 367 -> 2,872 lines); shared 1,086 -> 1,083,
indirect/unknown/goto/memN flat, zero per-file marker increases. An
independent second build was byte-identical (determinism cross-check).
Promoted by mirror copy (ACS aggregate `d6b9147c…ffcc`); evidence in
`validation_reports/promotion_r8.json`. Scratch trees removed; tree
committed and pushed. Rest of `final_out/` still holds r7.

## Current work: noreturn-shared forwarder returns (2026-09-24, LANDED)

The 63 `/* nothing */` bodies (all `Neon` in `Arm.cs`) were shared
`call; int3` forwarders (`vmvn/vand/vorn` families) whose single proven
target throws `NotImplementedException` on x64. `_dead_shared_forwarder`
dropped the pending call; `_dead_shared_forwarder_return` now renders
`return Target(args);` when the target is one readable MethodDef with
the caller's exact return tuple (both non-void) and the call text is
marker-free -- MSVC's own abort is the noreturn evidence, so the tail
return compiles and names only proven identities. Everything else
declines to the old drop.

Evidence: fresh lifts of the whole 2,407-method Neon type show 0
`/* nothing */` and 63 `return Neon.<s8-variant>(args);` (e.g. 107037
`return Neon.vmvn_s8(a0);`, 107123 `return Neon.vorn_s8(a0, a1);`).
Corpus shape census: 70 methods match, all Neon, all return-equal, so
the blast radius is one family. Tests: +2 portable (fire + 7 declines)
+2 game; full suite 1013 passed / 0 failed after one reviewed golden
update (107123 only). `final_out/` still holds r7 (unpromoted).

## Current work: shared stubs show SOME code (2026-09-24, LANDED)

Unresolved `__SharedBodyStubs` entries listed only the owner note plus a
throwing body -- no code. Each stub now also lists the address's first
native instructions (up to 16, stopping at the first ret/int3/ud2) as
`//` comments: real bytes, no managed owner selected. The signature,
throw, and owner note are unchanged, so call sites and runtime honesty
are byte-identical; failures decline to the old throw-only shape.
Probed ground truth: 0x18063ac90 shows `mov rax,rcx; ret` (the identity
leaf), 0x1825b1150 its 7-insn null-check fallback, 0x180506120 a bare
`ret 0`. Tests: +5 portable; full suite 1009 passed / 0 failed.

## Current work: identical-render shared collapse (2026-09-24, LANDED)

Method-only twins that render identically collapse to the first row:
same owner-qualified name, same static/instance shape, same exact
parameter types, same return. Call text, arity trim and result type
are identical either way, so the pick is unobservable, not an owner
guess. Constructors, generic methods/specs and sret returns decline;
everything else keeps the honest marker. Tails use the same proof
(the tail path already collapsed identical renders via caller-return
filtering; non-tails had no equivalent until now). The hash-name
match also accepts `<PrivateImplementationDetails>.` owners so the
resolved `ComputeStringHash` still feeds `switch(string)`.

Evidence: 70 sites resolve (ComputeStringHash 33, HashHelpers.Combine
28, Kernel.Multiply 6, Enumerator.Dispose 2, Locale.GetText 1);
ValueStringBuilder .ctor 23 honestly retained (ctor decline).
Ground truth: 24694 renders
`uint num15 = <PrivateImplementationDetails>.ComputeStringHash(text1);`
(switch gotos still decline, as triaged); 2991/2992 render only
`System.Numerics.Hashing.HashHelpers.Combine` (tails already did);
422/120851 render `Kernel.Multiply` / `Locale.GetText`. Tests: +7
portable (fire + owner/sig/ctor/generic/sret/arity declines) +3 game;
full suite 1004 passed / 0 failed. No goldens changed; `final_out/`
holds r7.

## Current work: shared-residual audit (2026-09-24, DOCUMENTED)

Why the 16,919 remaining shared-body markers stay (r7 tree, per-VA
metadata join over all 1,011 bodies with markers). Partitions below
overlap on the generic dimension; treats are per bucket:
- method+generic mixes: 5,676 sites / 137 VAs need instantiation
  proof (e.g. `BindingsAllocator.GetNativeOwnedDataPointer` sharing
  one body with 15 `ConvertExistingDataToNativeArray` specs) --
  synthetic-table program, the largest bucket.
- Same-typedef multi-signature: 5,432 / 337. Identical twins
  (F1/F2/F3) are permanently unresolvable; overloads need
  conversion-witness or exact-only arg-type elimination (future).
- Multi-owner same method name: 2,752 / 155 (GetResult/get_IsCompleted/
  get_Item/ToString pairs) -- sig elimination DISPROVED 2026-09-25
  (see top sections); needs receiver/instantiation proof (sidecar).
- Multi-owner different names: 3,859 / 259, incl. mega-shared tiny
  bodies -- owner proof at scale (field sidecar + use→def).
- Static/instance mixes: 3,394 / 43 (ToString/op_Implicit 865 sites) --
  mostly mega-shared tiny bodies (declined); the crisp `0x1825b1150`
  pair's spray probe is still open (see index).
- Non-method (pure generic) addresses: 1,282 / 191 -- instantiation
  proof, same program as the first bucket.
- Identical full signatures: 200 / 25 -- same-render collapsing LANDED
  2026-09-24 (70 sites); remainder keeps markers.
- Corrected mid-audit: an early "14 true-duplicate VAs" read was a
  filter artifact (method rows only, hiding generic sharers); the full
  map has ZERO exact-duplicate addresses, so a registration dedup was
  prototyped and reverted before landing (no effect, no test could pin
  it). Audit your tools, not just the tree.

## Current work: promotion r7 (2026-09-24, PROMOTED)

User-authorized (promotion on call). Strict rebuild `r7_out1` from
clean HEAD `d109bb2`: 11,183 files / 114,458 bodies / 0 failed / 0
fallbacks / 0 type-emission failures; brace 0 unbalanced; parse 0/0/0;
file set identical to r5 (11,276 paths, 745 files differ). Triage: five
audited shared-body rounds (Object/value-type/static-signature/
identity/string-equality); shared 18,889 → 16,919 (−121 files),
indirect 6,262 → 6,061 (−48 files), unknown −34, memN/goto/`?addr`
flat, zero per-file marker increases; sampled resolutions verified
(`this.MemberwiseClone()`, `== "Gamepad"`, `op_Inequality` with TimeSpan
declines kept). No golden regen needed beyond the two reviewed updates
already in-tree (suite 994/0 green proves currency). Promoted by mirror
copy (aggregate `19aa6964…f137502`); evidence in
`validation_reports/promotion_r7.json`. Scratch tree removed; tree
committed and pushed.

## Current work: shared string equality semantics (2026-09-24, VALIDATED)

`System.String.Equals(string,string)` and `op_Equality(string,string)`
share one native body and the same static bool ABI. When both operands are
tracked strings, string literals, or null, render their common `==`
behavior without selecting an original MethodDef or source spelling.
Dropped extra register expressions must be pure. The five previously
marked `ReadReference` comparisons now spell `ReadName() == literal`;
unknown operand types retain the marker. All 994 full-suite tests pass.
The strict Assembly-CSharp build covered 490 files / 6,622 bodies with
0 failures / 0 fallbacks / 0 type-emission failures, brace 0, parse
0/0/0. In those files, this alias's markers
fell 138 → 11 against promoted r5; all shared markers fell 1,287 →
1,086 with no per-file increases (that total includes earlier
unpromoted changes). `final_out/` remains unchanged.

## Current work: exact shared identity leaf (2026-09-24, VALIDATED)

The exact executable bytes `mov rax, rcx; ret` prove that a shared native
body copies its first argument without selecting any MethodDef owner. The
fold requires a pure tracked first argument and pure extra register values;
effectful expressions, unknown values, pointers without a safe tracked
value, and any other native bytes retain the honest shared-body marker.
`<FindGraphWhichInheritsFrom>b__0` folds its `this.type` copy but retains
the `graph.GetType()` call marker. `Touchscreen.OnStateEvent` now carries
the copied `InputEvent*` type through its field reads; its reviewed
MethodDef 32833 golden was updated.

Evidence: 992 full-suite tests pass. Strict AstarPathfindingProject and
Unity.InputSystem build: 513 files / 7,249 bodies, 0 failures / 0
fallbacks / 0 type-emission failures; brace 0, parse 0/0/0. In those
files, address `0x18063ac90` markers fell 55 → 1 against promoted r5;
all shared markers fell 302 → 241 in 16 changed files with no per-file
increase (the latter includes preceding unpromoted changes). `final_out/`
remains unchanged.

## Current work: shared static signature proof (2026-09-24, VALIDATED)

A common non-generic static ABI plus call-site parameter types can name a
shared native address when exactly one metadata owner accepts every known
argument. Class compatibility includes ancestors; an `object` or interface
parameter blocks the proof because a more specific observed type could
also bind it. Pointer/byref, sret, mixed arity, unsupported argument
types, stale typed registers beyond the declared arity, and duplicate
signatures decline. This names two `Type.op_Inequality` calls in
`DateTimeFormat.ExpandPredefinedFormat` (MethodDef 1745) while its two
`TimeSpan` sites keep markers: one operand is exposed only as `_ticks`.
The `Object.Equals` / reflection `op_Equality` family stays ambiguous.

Evidence: 986 full-suite tests pass; strict mscorlib scratch build
1,350 files / 10,715 bodies, 0 failures / 0 fallbacks / 0 type-emission
failures, brace 0, parse 0/0/0. Against promoted r5, mscorlib markers
fell 1,374 → 1,301 with no per-file increases; that comparison includes
the preceding unpromoted receiver fixes. `final_out/` remains unchanged.

## Current work: exact value-type shared receivers (2026-09-24, VALIDATED)

An address-of stack slot can identify a shared instance getter when its
tracked pointee is one concrete nongeneric value TypeDef. The candidate
set must contain only readable instance methods with no sret; a second
method or MethodSpec on the same declaring type declines. Static calls,
conflicting type evidence, open owners, and untyped pointer arithmetic
keep the shared marker. This resolves `StyleValueHandle.get_valueType`
from `&s_8` in `IsVarFunction`, while `ReadAsString`'s raw pointer stays
unresolved. A closed enum parameter now casts a proven integer expression
at the call argument, preserving `StyleEnum<SliceType>.ctor((SliceType)
styleInt.value, keyword)` after its two getter markers disappear.

Evidence: full suite 978 passed / 0 failed after one reviewed golden
update (MethodDef 18054 only); strict UIElements scratch build 802 files /
8,997 bodies, 0 failed / 0 fallbacks / 0 type-emission failures,
brace 0, parse 0/0/0. Shared markers in UIElements fell 1,332 → 1,277
(55 fewer in six files, no increases). The prior r5 promoted tree remains
the comparison reference; no output promotion here.

## Current work: Object shared-body fallback (2026-09-24, VALIDATED)

A narrow full-candidate receiver proof resolves `Delegate.Clone` /
`Object.MemberwiseClone` shared body calls for a concrete class receiver
outside Delegate's inheritance chain. Every candidate must be a closed,
parameterless, non-sret instance MethodDef; the receiver must have a
class TypeDef and exactly Object may remain in its complete base chain.
The broad shared-receiver heuristic still excludes Object. Typed
`FUniversalVariable.Copy` and `XmlWriterSettings.Clone` now render
`this.MemberwiseClone()`; the untyped `SchemaCollectionCompiler` site
keeps its marker.

Validation: 969 full-suite tests pass; compileall passes. A strict
`Assembly-CSharp,System.Xml` scratch build lifted 13,204 bodies with
0 failures / 0 structured fallbacks / 0 type-emission failures;
1,048 files have 0 unbalanced braces and parse 0/0/0. In those
assemblies, shared markers fell 2,195 → 2,174 with zero per-file
increases. `final_out/` remains the r5 promoted reference.

## Current work: shared/indirect disproofs + measurements (2026-09-24, DOCUMENTED)

Subagent census follow-ups that disproved (with native/metadata
evidence) rather than landed -- no source change, by the same rule as
the generic-slice closure. Small-N shared bodies are NOT in general
resolvable: F2 `StartCoroutine` twins (56318/56319, identical static
  `(IEnumerator)` signatures), F1 string twins (602/604
  `Equals`/`op_Equality`, identical static `(string,string)->bool` over
  one folded body -- method identity and source spelling remain unknown;
  typed operands now permit their shared `==` semantics), F3 Transform
  triple (56836/56838/56840, same declaring
typedef, so the same-typedef-twins invariant applies directly). Their
markers stay honestly.
- C-shape text fold (`((byte*)R+0)[0]` to klass) is unsound: EntryDoor
  25181's native loads a struct field pointer (`mov rsi,[rsp+78h]` +
  null check = the embedded `List<Enemy>` of a `List_1<Enemy>.Enumerator`
  home) and dispatches slot 30 on the List, so a klass fold would
  misread struct first-fields. The correct fix is struct-field folding
  into the existing VIRT_CALL path (lifter field-layout reasoning) --
  deferred to the sidecar program.
- Dead-unknown window extension measured: 42 adjacent vs +6 in 1-3
  statement windows -- declined, not worth the machinery.
- B2 `this`-base count is 0/271, so the batch-38b bare-base guard
  stands for lack of any trivially-provable base.
- The 32 typeof-decl-but-indirect sites are heterogeneous non-shapes,
  correctly declined (e.g. SessionInfo: no slot computation exists;
  the typeof travels as a call argument, not a dispatch proof).
- Next lead if wanted: deref-trail slots (335 sites shaped
  `... + ((byte*)TOK + 0x0)[0]` with inline typeof nearby) need a
  typedef-to-implemented-interfaces table plus unique-match gating;
  that table is sidecar-program plumbing, so this stays designed.

## Current work: dead-unknown stores + inline-typeof dispatch (2026-09-24, LANDED)

Two subagent-triaged slices from the shared/indirect/unknown census
(18,889 shared / 6,262 indirect / ~13.1k unknown). (A) Adjacent
`LHS = unknown;` overwritten by the next statement folds away
(`_drop_dead_unknown_store`, after the fix-99 DCE rerun): bare/index-
slot lines drop, plain-typed decls strip to `Type x;`; labels, `==`,
calls/`new` in the destination, `var`/`ref`/keyword decls, fields, and
second-RHS reads of the destination all decline. Ground truth:
LagCompensationUtils 63027 twins, RaycastModifier 105455 strip + use
survival, GraphCollision pointer slot honestly declines (reassign is 4
stmts away, not adjacent). (B) Interface dispatch with inline
`typeof(IFace)` in the scan-loop comparator (`_itf_inline_typeof`,
dual agreement with the slot trail token's declared type; the trail
token is corroboration only, never rendered; `typeof(X).Member` static
access never counts as a scan comparison). Ground truth:
EndlessGenerationManager 25132 `values.GetEnumerator()`.

Evidence: full strict rebuild r6_out1 (11,183 files / 114,458 bodies,
0 failed / 0 fallbacks, brace 0, parse 0/0/0): 124 files differ --
112 dispatch resolutions (`get_Item`/`TryGetValue`/`Equals`/`Compare`/
`MoveNext`/etc. on named receivers; NetworkRunner/ObiSolver/Path keep
markers for lack of agreement) and 11 dead-store folds plus 1 mixed,
all hand-sampled correct; indirect 6,262 → 6,052 (−50 files), unknown
13,097 → 13,063, shared/mem/goto/`?addr` flat, zero per-file marker
increases. Tests: +4 portable +3 game; focused 28 passed; full suite
964 passed / 0 failed. No goldens changed; `final_out/` holds r5.

## Current work: promotion r5 (2026-09-24, PROMOTED)

User-authorized (standing permission for regen/promotion whenever
needed). Strict rebuild `r5_out1` from clean HEAD `37811e9`: 11,183
files / 114,458 bodies / 0 failed / 0 fallbacks / 0 type-emission
failures; brace 0 unbalanced; parse 0/0/0; file set identical to r4d
(11,276 paths, 456 files differ). Triage: scalar prologue-copy typing
corpus-wide plus FP32/R8 unary-leaf recovery (log10f + double leaf,
immediate/conditional/conversion/copy consumes); net −79 unknown (−1
file), shared/indirect/memN/goto/`?addr` flat, zero per-file marker
increases; no regressions. No golden regen was needed (green suite
proves currency: 957 passed / 0 failed). Promoted by mirror copy
(aggregate `5a31b119…0d79`); evidence in
`validation_reports/promotion_r5.json`. Scratch tree removed; tree
committed and pushed.

## Current work: R8 double-unary leaves (2026-09-24, LANDED)

The FP proof extends to double callees, proved on 0x1804CD9D0 (CRT
errno-adjacent double leaf behind Slider's `sub_1804CD9D0` calls):
+MOVSD/+SETcc/+SUBSD table shapes, register-count shifts (op1 read is
tracked, MUST discounts scratch uses), frameless functions over the
0x28 shadow store (entry-block-dominated homes read clean, others join
SHADOWARG), and GEN/KILL over XMM0-15 (YMM/ZMM fold in). The last item
closed a real hole found by the re-sweep: `mulss xmm0,xmm1` passed with
inputs=={XMM0} and the render dropped the multiplier; it now declines
with inputs=={XMM0,XMM1} (pinned portably and by PathProcessor 104653's
unchanged object spray). The consumer gate returns 'f'/'d'/None;
CVTSD2SI/CVTTSD2SI with source XMM0 fire double, and the render binds
`double` in XMM0. Fix-104 casts stay for both widths (they unbox
against the object stubs -- verified by declaration audit).

Evidence: SliderLerpUnclamped (15267) chains
`float real2 = (float)sub_1804cdb00(...)` into
`double real3 = (double)sub_1804CD9D0((double)(real2))` and on to
`(int)`; FEngineering (2 sites), Panel (2 pixel sites), and
StylePropertyAnimationSystem (1 site) gain the same double recovery;
remaining sites decline honestly. Corpus sweep holds at exactly 2
passing targets (log10f + R8). Tests: +3 portable (SD widths,
binary-op decline, frameless/SHADOWARG) +1 game (binary-op pin), -1
obsolete cast-skip test; focused 21 passed; full suite 957 passed /
0 failed. Strict scratch builds
(490/6,622 + 802/8,997, all zero), brace 0, parse 0/0/0. Isolated diff
vs stashed baseline: 4 files, all improvements plus renumber cascades.
No goldens changed.

## Current work: FP32-unary conversion/copy consumes (2026-09-24, LANDED)

The consumer gate additionally fires on float-consuming conversions
with source XMM0 (`cvtss2sd/cvtss2si/cvttss2si`, rendered by the
existing `(double)/(int)` casts) and on `movaps` reg,reg copies from
XMM0 (bitwise copy preserves the value); double-source conversions
(`cvtsd2ss` et al) and VEX forms still decline. A new `_fp32_arg_ok`
helper declines arguments containing a bare `?` (never parses;
`?.`/`??`/`unknown` pass).

Evidence: Slider `SliderLerpUnclamped` (15267) recovers two sites --
`float real2 = sub_1804cdb00(real1 & float.NaN);` and `float real3 =
...` feeding `(double)(real3)` / `(int)(5.0d - (double)(real3))`
chains; the third site honestly declines (its argument carries
`(double)(?)`, unspellable until SIMD-lane provenance heals upstream).
Corpus-isolated diff vs stashed baseline: exactly 1 file (Slider.cs),
improvements plus renumber cascades. Tests: +2 portable (conversion/
copy fires, arg spellability) +1 game; focused 18 passed; full suite
954 passed / 0 failed. Strict scratch builds (490/6,622 + 802/8,997,
all zero), brace 0, parse 0/0/0. No goldens changed.

## Current work: FP32-unary conditional consume (2026-09-24, LANDED)

`_fp32_scalar_next` now walks up to 16 instructions forward to the
scalar XMM0 consume instead of requiring it immediately after the call.
Skipped instructions must not touch the value channel (no XMM0/YMM0
mention, no calls, no returns/jumps/indirect flow, no kernel
transitions); flag tests, conditional branches, NOPs, constant loads,
and unrelated moves all skip. A branch target landing between call and
consume declines (merge, not the call's value), as do revisits, decode
failures, and running past the cap. Fire shapes unchanged (SS arith +
`movss` from XMM0); VEX/`movaps`-copy/double-width consumes decline.

Evidence: PlayerManager `FixedUpdate` (26741, `call; test; je; ...;
mulss xmm0`) renders `float real15 =
sub_1804cdb00(PlayerPrefs.GetFloat("SFXVolume"));` into `SetFloat(
"DeathAudio", real15 * 20.0f)` at both sites; StoreManager `Spawned`
(27765) and three more KeybindsManager volume restores gain the same
improvement class. Slider `SliderLerpUnclamped` (15267) correctly
declines twice (double-width `cvtss2sd` consume; `movaps`-copy consume).
Corpus-isolated diff vs stashed baseline: exactly 3 files, all
improvements plus renumber cascades. Tests: +4 portable (walk fire +
rejoin/clobber/call/cap declines) +2 game; focused 15 passed; full
suite 951 passed / 0 failed. Strict scratch builds (490/6,622 +
802/8,997, all zero), brace 0, parse 0/0/0. No goldens changed.

## Current work: unregistered FP32-unary leaves (2026-09-24, LANDED)

`sub_1804cdb00(volume)` (CRT log10f, 0x1804cdb00) is proved, never
named: a MUST-fixpoint input proof over the callee (`_is_fp32_unary_leaf`
in `il2cpp/lifter/state.py`, next to the sqrt/fence recognizers) shows
exactly XMM0 read, no GPR/stack arguments, and no caller-visible
effects (pdata extent, recursive-descent CFG, operand-access allowlist,
RSP-frame/alias bounds, must-be-written fixpoint; depth-1 input
propagation; unregistered-identity floor below with the CRT-substrate
residual documented). The call site additionally requires a scalar
XMM0 consume on the next instruction (`_fp32_scalar_next`) and a known
XMM0 value. The render keeps the honest `sub_X` name with one float
argument and a float XMM0 result; fix-104's `(float)` cast stays (it
unboxes against the object-returning stub declarations -- skipping it
broke compilation while staying parse-green, so the skip was designed,
prototyped, and reverted before landing; casts are load-bearing).

Evidence: 23548/23549 render `float real2 =
(float)sub_1804cdb00(volume);`
with `real3 = real2 * 20.0f;` (was 4-arg spray + `object` + dropped
`0f * 20.0f`), dead arg scaffolding DCE'd; KeybindsManager's three
volume methods (SetSFX/Music/PlayerVoiceVolume) gain the identical
improvement. Corpus sweep: exactly 1 of 2,676 unregistered targets
passes (21 sites); PlayerManager/StoreManager/Slider/stub sites decline
(principled: no immediate scalar consume -- conditional use after flag
tests needs branch-aware tracking, a follow-up). Strict scratch builds
(Assembly-CSharp 490/6,622 + UIElementsModule 802/8,997, all 0 failed /
0 fallbacks), brace 0, parse 0/0/0 on both. Against a stashed baseline
build, exactly 2 files differ (both improvements). Tests: +7 portable
(synthetic callee bytes, decline shapes, consumer gate) +2
game; focused 11 passed; full suite 947 passed / 0 failed (fully
green). No goldens changed; `final_out/` holds r4d. Package CRLF/no-BOM,
tests LF.

## Current work: scalar parameter-copy inference (2026-09-23, LANDED)

A single prologue copy of a scalar metadata parameter now carries its
exact declared type (`il2cpp/dec/highlevel.py`, in the hint seeding
ahead of `_rename_locals`). This recovers stack homes like
`s_10 = volume` (float) as `float real1 = volume` without inferring
from an unrelated later use. A second write or an address /
`ref` / `out` / `in` escape declines; existing concrete hints win.

Evidence: both AudioVolumeSliders methods (23548/23549) render
`float real1 = volume` with `real1.ToString("0.0")` while keeping the
paired-Jcc and branch-chain recoveries; the StreamBuffer 8-arg
overload (113044) stays fully bound with renumbered int temps (its
game assertion now pins the parameter at the store, which is the
regression invariant). Tests: +1 portable (single-write fire,
rewrite/address-escape declines) plus evolved game pins; focused 30
passed. Full suite: 938 passed / 0 failed (fully green, +1 vs r4d).
Strict `Assembly-CSharp` scratch build: 490 files / 6,622 bodies, 0
failed, 0 fallbacks, 0 type emission failures; brace 0/490; parse 0
bad / 0 ERROR / 0 MISSING. Scratch-tree AudioVolumeSliders verified
(`float real1 = volume`, no `unknown != unknown`). No goldens
changed; `final_out/` + `validation_reports/` hold r4d until an
explicit promotion call. Package source kept CRLF/no-BOM, tests LF.

Open lead (unchanged): AudioVolumeSliders still calls unregistered
`sub_1804cdb00` (native XMM0 scalar result, identity and arity
unproved; current lift renders `real2 = 0f * 20.0f`). Prove
call/result provenance before replacing the raw call; do not guess
from `Mathf.Log10` (its registered target differs).

## Current work: promotion r4d (2026-09-23, PROMOTED)

User-authorized (`promote final out`). Strict rebuild `r4d_out1` from
clean HEAD `1920c71` (the uncommitted scalar parameter-copy slice was
stashed pre-build and is NOT in this tree): 11,183 files / 114,458
bodies / 0 failed / 0 fallbacks / 0 type-emission failures; brace 0
unbalanced; parse 0/0/0; file set identical to r4c (11,276 paths, 783
files differ). Triage: branch-chain + recursive phi decl hoists across
the corpus; paired-Jcc float-condition recovery (`unknown != unknown`
to real lane comparisons, e.g. float3x3) unblocking existing ternary
folds (net −2,479 unknown, −52 unknown-files); one native-faithful
dead-diamond resurrection class (mi 104158 `get_remainingDistance`,
bisected to 2481c16, verified against disassembly — native computes
pos.z then clobbers it); renumber cascades; shared +5, indirect/memN/
goto/`?addr` flat, no regressions. Promoted by mirror copy
(aggregate `b0f798b4…2280`); evidence in
`validation_reports/promotion_r4d.json`. Post-build suite: 937 passed
/ 0 failed (fully green). Scratch tree + worktrees removed; tree
committed and pushed. WIP scalar-copy slice restored to the working
tree after promotion (still unlanded, see `docs/handoff-2026-09-23.md`).

## Historical handoff: 2026-09-23 stop (LANDED)

The fourth scalar parameter-copy change described here is now landed
(see the top section): focused 30 passed, full suite 938 passed / 0
failed, strict `Assembly-CSharp` scratch build plus brace/parse gates
passed, committed and pushed. The `TODONOW.md` working-tree addenda
were preserved as committed. No goldens were changed; `final_out/` +
`validation_reports/` hold the r4d promotion above. The `sub_1804cdb00`
provenance lead from [handoff-2026-09-23.md](handoff-2026-09-23.md) is
now closed by the top section (FP32-unary leaves, LANDED).

## Current work: complete branch-chain declarations (2026-09-23, fixed in source)

`AudioVolumeSliders.SetMusicVolumeInternal` and
`SetSFXVolumeInternal` (23548/23549) assigned `float real1` in all
three `if / else if / else` arms, then read it at `SetFloat` after
the join. A late `_phi_chain_decl_hoist` now places one concrete typed
declaration before a complete chain and leaves each arm's assignment
in place. It requires matching tail declarations, a final `else`, no
flow exits or earlier use, no address escape, and a later read.
Unknown `object`/`dynamic` value markers decline: an initial wider
pass changed frozen MethodDef 39789's unresolved 0/1 aliases, so that
case remains golden-exact until its type is proved.

Portable tests pin the three-arm fold and missing-else, early-return,
and unresolved-type declines; game tests pin both audio bodies.
Full suite: 937 passed. Strict `Assembly-CSharp` scratch build: 490
files / 6,622 bodies, 0 failed, 0 fallbacks, 0 type emission failures;
brace 0/490; parse 0 bad / 0 ERROR / 0 MISSING. Against the prior
scratch build, 44 files differ; sampled changes hoist branch-complete
declarations in AudioVolumeSliders, InventoryManager, FPSController,
and FIMSpace. `final_out/` and goldens remain untouched.

## Current work: paired float Jcc flags (2026-09-23, fixed in source)

MethodDefs 23548/23549 (`AudioVolumeSliders.SetMusicVolumeInternal` /
`SetSFXVolumeInternal`) use native `ucomiss xmm1, 0; jp X; jne X`.
The `JP` correctly rendered `float.IsNaN(volume)`, then cleared the
comparison operands before the fallthrough `JNE`, producing
`else if (unknown != unknown)`. For the exact `UCOMISS; JP X; JNE X`
shape with one predecessor at the second jump, the CFG executor now
carries the operands and setter across the first jump. The second
condition renders `volume != 0f` in both methods. Unregistered
`sub_1804cdb00` result typing remains open. The later `real1`
declaration is now hoisted by the follow-up above; these bodies still
contain other unresolved values and are not claimed to compile.

The broader Jcc carry changed MethodDef 45016's frozen double body,
so it was narrowed to this proved single-precision shape; 45016 is
golden-exact again. Two game tests pin the audio conditions. Full suite:
936 passed. Strict AudioVolumeSliders scratch build: 8 bodies, 0 failed,
0 fallbacks, 0 type emission failures; brace 0/2; parse 0/0/0.
`final_out/` and goldens were not regenerated or promoted.

## Current work: InventoryManager join loss (2026-09-23, fixed in source)

`UpdateInventorySlotsUI` (MethodDef 25624, VA `0x18070b620`) has an
unbound `image3.sprite = obj21` in the promoted and fresh lifts. Native
block `0x18070baf4` calls the sprite setter after two paths: predecessor
68 (`0x18070ba96`) carries `RCX = t1014` and
`RDX = this.objSprites[this.inventoryIds[v145]]`; predecessor 75
(`0x18070baed`) carries `RCX = this.inventorySprites_[v145]` and
`RDX = this.emptySprite`. The setter therefore runs on both paths.
`_build_phi_copies` creates a phi for `RDX` (`v223`) but none for
`RCX`; the structured body already has `t1014.sprite = v223` before
`_rename_locals`. The latter merely names the unbound value `image3`.

Real-pass instrumentation proved both `RCX` expressions had identical
text at the equality check, but separate definition sites and one use
each. Later binding renamed only the first expression. The merge now
keeps a typed object array-element value with distinct definitions as
a phi, even when its texts match. `_phi_decl_hoist` then lifts the
receiver and sprite declarations above the diamond, preserving each
arm's assignment. The historical twin-tail match remains first; the
non-tail extension runs only after a prior hoist on that shape.

Evidence: MethodDef 25624 now renders `Image obj22; Sprite obj23;`
before the branch, assigns both in each arm, and calls
`obj22.sprite = obj23;` at the join. A game regression and a portable
two-value hoist test pin it. Full suite: 934 passed. Strict scratch
build (`--types InventoryManager --only Assembly-CSharp`): 158 bodies,
0 failures, 0 fallbacks, 0 type emission failures; brace audit 0/2.
Strict `Assembly-CSharp` scratch build: 490 files / 6,622 bodies,
0 failures, 0 fallbacks, 0 type emission failures; brace audit 0/490;
tree-sitter parse 0 bad / 0 ERROR / 0 MISSING. Against promoted r4c,
27 Assembly-CSharp files differ; sampled diffs are phi copies and
declaration hoists, with the target's two receiver assignments intact.
`final_out/` remains the read-only promoted r4c tree. No snapshot
regeneration or promotion was done.

## Current work: promotion r4c (2026-09-23, PROMOTED)

User-authorized (`just promote`). Strict rebuild `r4c_out1`: 11,183
files / 114,458 bodies / 0 failed / 0 fallbacks / 0 type-emission
failures; brace 0 unbalanced; parse 0/0/0; file set identical to r4a
(11,276 paths, 49 files differ). 49-file triage: SIMD composites
(+13), struct-literal recoveries (GridGraph/AstarDebugger/WFX Color,
native-verified), float typings, renumber cascades, honest residuals
(net −86 unknown); no regressions (WFX alpha ternary verified
native-faithful; `?addr` tightening stayed reverted). Promoted by
byte-identical copy (aggregate `c0ee1b78…1236`); evidence in
`validation_reports/promotion_r4c.json`. New census: shared
18,884/2,278, indirect 6,262/884, unknown 15,655/1,365, mem[N]
398/127, mem_hex 359 strict, goto unchanged, `?addr` 1 (honest
elision). Post-promotion suite: 932 passed / 0 failed (fully green).
Scratch tree + build logs removed; tree committed and pushed.

## Current work: ?addr-tightening DISPROVED (2026-09-22, reverted clean)

Narrowing the RSP-copy declines to text-`?` bases rescued mi 65244's
last `?addr` as `((byte*)obj44 + num55*4)[0] = 4294967295` -- then
traced end to end and disproved it: obj44 textually aliases a reused
home (0f/data_ on disjoint arms) while native uses a fresh
&s_1d0+idx address; the address-of is lost in write-barrier
conversion and the width/value mismatches, so the line miscompiles
where the elision honestly declined. Reverted byte-identically (lifts
match pre-tightening bodies); the elision itself is now pinned by a
game test against recurrence. Portable anonymous-copy guard kept.
- Gates: full suite 932 passed / 0 failed (first fully-green run
  stands).
- Lesson recorded: rescues must prove the rendered base denotes the
  native address on the reaching path, not just spell it.

## Current work: SIMD consumer-side round (2026-09-22, unpromoted)

Subagent-traced (both constants' death sites + 80548 guard shape).
Same rules: `final_out/` untouched, no promotion (tree rebuild is a
separate user call). `il2cpp/` edits via binary patches with
CRLF/no-BOM asserts; `tests/` edits LF.

- Fix LANDED, tails-only staging: (A) scalar const-pool loads attach
  bytes (mirrors PACKED128; only adds float-expected lane reads);
  (B) `_tail_method_args` materializes GPR `?` args at closed
  all-float vector slots from byte-proven float-suffixed lanes --
  width-4 renders the literal, width-8 renders house `(float2)(l0,l1)`
  for Unity.Mathematics.float2 only. Instance/sret/stack/byref/
  double/open/unresolved/uncovered/part-less/text-mismatched all
  decline; direct calls keep today's spelling.
- Evidence: 67525 renders `clamp(x, (float2)(0.0f, 0.0f),
  (float2)(1.0f, 1.0f))` (signature-exact float2x3, mi 67517; parses;
  the old scalars relied on implicit conversion no overload proves).
  80548 guard holds (`int num2`, `(unknown >> 32)`, golden-pinned).
- Golden REGENED for 67525 only (surgical script, fixture SHAs verified,
  source_sha256 refreshed, CRLF kept, 63 other bodies identical).
  Suite is 930/0 -- first fully green run.
- Follow-up (direct calls, same gates): the tail loop refactored into
  shared `_materialize_float_lanes`, wired into the resolved-direct
  path after positional rebuild + trim. mi 67836 smoothstep renders
  `clamp(unknown, (float2)(0.0f, 0f), (float2)(1.0f, 1.0f))` (+`.x`/`.y`
  reads); uncovered first arg honestly stays unknown; mixed `0.0f`/`0f`
  lane spellings kept verbatim (values exact, no normalization pass).
- Tests: +3 game (`test_game_simd_lanes.py`: tail composite,
  direct composites, 80548 integer-carry guard).
- Gates: full suite 933 passed / 0 failed.
- Open SIMD remainder: per-arm Color (use→def), general packed
  tracking (still declined).

## Current work: sidecar grounding turn (2026-09-22, unpromoted, no source change)

Traced mi 23762's three defects to their exact producers (semantic-input
dump + `_field_expr` generic-base trace + addr_of audit) to scope the
sidecar honestly:

- `selectable1 = dictionary22`: the key type comes from USE-side proof
  (`_hint_accessor_recv` on the `.navigation` store), never from a
  proved-struct store -- so a store-side lane writer would never fire
  here. Needs byte-range slots (documented sidecar), not a writer.
- Zero closed-genericinst bases reach `_field_expr` in the method, so
  the inflated-chain swap is a proven no-op here too.
- `obj17` (Navigation lane): XMM-lane traffic through spills, needs
  SIMD-lane provenance, not field chains.
- `obj11 = &dictionary23` + `obj11.Dispose()`: the receiver is a bare
  temp at lift; `addr_of` tracks memory homes only. Needs use→def.
- Verdict: all three need deferred machinery (sidecar/SIMD/use→def);
  no narrow slice exists. No invisible infra shipped.

## Current work: ?addr extinction round (2026-09-22, unpromoted)

Follows the promoted census (last `?addr`: ReflectionProbeManager).
Same rules: `final_out/` untouched, no snapshot regen, no promotion.
`il2cpp/` edits via binary patches with CRLF/no-BOM asserts; `tests/`
edits LF.

- Root cause was our own quarantine over-firing: the indexed-copy
  declines caught NAMED `&s_xx` homes (mi 65244 `lea rcx,[rcx+r12*4]`
  over `&s_1d0`), not just anonymous `mov r64,rsp` copies. Tightened
  all 5 decline sites (MOV-RBP, LEA-RBP-dst, LEA/load/store indexed)
  to text-`?` bases; named homes keep legacy honest composites.
- Verified the rescued store is correct, not just present: it uses the
  home's address (`&s_1d0` slot identity), so stale home values on
  disjoint arms don't alias it.
- `?addr` count is now 0 in fresh lifts (was 1); the promoted tree
  still shows its 1 until the next rebuild.
- Tests: +2 portable (named home keeps home, anonymous stays unknown)
  +1 game (65244: no ?addr/elided, exact store line).
- Gates: compileall pass; portable 782 green; full suite 926 passed /
  1 failed (67525 honest SIMD decline only); zero golden movement.

## Current work: generic-slice closure (2026-09-22, unpromoted, no source change)

Subagent-designed, empirically closed without a patch. Same rules:
`final_out/` untouched, no regen, no promotion.

- Verified on mi 23762: MethodRef kind-6 slot path already closes all
  generic homes; closed-generic bases never reach `_field_expr`
  (0 hits traced), so the inflated-chain swap is a proven no-op here;
  `selectable1` needs byte-range sidecar (documented), `obj17` needs
  SIMD lanes, `obj11` needs use→def (bare-temp receiver at lift).
- Corpus mining for hook-shaped sites (open result + correctly
  attributed closed-generic receiver + pure-result-typing fix): ZERO
  hits. 9 open-result sites need downstream-consumer proof (use→def);
  the 1 closed-receiver + object case (24679) is a misattributed field
  lane with zero `get_Current` candidates; 109849 likewise; the 187
  family is void/closed/slot-named already.
- Verdict: receiver-driven substitution deferred to sidecar machinery
  alongside hinted receivers. No invisible infra shipped.

## Current work: promotion r4a (2026-09-22, PROMOTED)

User-authorized. Strict rebuild `r4a_out1`: 11,183 files / 114,458
bodies / 0 failed / 0 fallbacks / 0 type-emission failures; brace
audit 0 unbalanced; parse gate 0/0/0; file set identical to the prior
tree (11,276 paths). Spot-verified in-tree (GetEnumerator/MoveNext/
Current, IsSameObject(obj1, obj2), StreamBuffer v0). Promoted by
byte-identical copy (aggregate `e7f406db…bdabf`); evidence in
`validation_reports/promotion_r4a.json`. New census: shared
18,884/2,278, indirect 6,262/884, unknown 15,748/1,365, mem[N]
398/127 (was ~13k — the RSP-copy round at corpus scale), mem_hex 359
strict, goto unchanged, `?addr` down to its last site
(ReflectionProbeManager:434, funclet home). The memhex remainder is
honest (be-None path byte-identical in diff; sampled sites are
exception/funclet homes). Post-promotion suite: 923 passed / 1 failed
(67525 honest SIMD decline only). Scratch tree + build logs removed;
tree committed and pushed.

## Current work: promotion round — regen + rebuild (2026-09-22)

User-authorized regen/promotion. `tests/goldens_review84.json`
surgically regened for mi 32837 (70→66 lines, dead spills out) and mi
104428 (38→26, spills out, aggregates back) only -- 67525 keeps its
ground-truth `clamp(x, 0f, 1.0f)` expectation (honest SIMD decline,
never enshrine `unknown`). `source_sha256` refreshed to the current
tree; the other 62 bodies byte-identical. Expected suite after regen:
all green except 67525.

## Current work: boxed-bool fold round (2026-09-22, unpromoted)

Subagent-designed from the interface round's residual. Same rules:
`final_out/` untouched, no snapshot regen, no promotion. `il2cpp/`
edits via binary patches with CRLF/no-BOM asserts; `tests/` edits LF.

- Fix LANDED: `object X = <bool dispatch>; if (X == null)` folded to
  `bool X = ...; if (!X)` (and `!=` to bare). The bool proof exists
  only after render-stage dispatch naming (at lift time the callee is
  unknown, so the null test is honest): `_name_interface_dispatch`
  records bool-returning resolutions, new `_boxed_bool_null_fold` runs
  last after semantic names. Single exact `object X = <call>` decl,
  all-uses-must-be-bool via `_bool_use_ok`, no reassign/address-take,
  standalone heads only; no inlining (MoveNext is impure), no renames.
- Evidence: 8 methods fold (25368, 24059, 25132, 25872, 26880, 27213,
  97399, 105906; native `test al,al` verified on two); unbox/`&` uses
  (25872 obj52, 97399 obj49) correctly decline, as do ref-null tests
  and already-bool `!(objN)` uses.
- Tests: +5 portable (fire, ne-shape, object-use/reassign/byref
  declines, unrecorded/non-call declines) +1 game (25368 fold, 25872
  fold + unbox decline).
- Gates: compileall pass; portable 778 green (773 + 5); full suite 921
  passed / 3 failed -- identical IDs (32837 improvement-pin, 67525
  honest SIMD, 104428 stale); the fold moved zero goldens.

## Current work: interface-dispatch round (2026-09-22, unpromoted)

TODONOW #2 first slice, subagent-mined. Same rules: `final_out/`
untouched, no snapshot regen, no promotion. `il2cpp/` edits via binary
patches with CRLF/no-BOM asserts; `tests/` edits LF.

- Fix LANDED (mi 25368 `GameManager.CheckAllReady`): three back-to-back
  interfaceOffsets searches resolved to `GetEnumerator`/`MoveNext`/
  `Current`, missing on three crisp gates: (1) slot lines carry decl
  prefixes at render stage (`object obj19 = ...`) -- `_ITF_SLOT_RX`
  admits an optional type prefix; (2) the typeof token is referenced at
  the call, outside the old (typeof, slot] span -- search runs through
  the call line (monotonic widening); (3) display spells arity `_N`
  while metadata names use `` `N `` -- exact key first (genuine `Foo_2`
  rows keep resolving), normalized fallback for generic displays only.
  All existing declines preserved (unrelated typeof, unresolvable key,
  out-of-range rel, unshaped receiver, non-16 K, missing slot).
- Residual note: `object obj32 = obj5.MoveNext(); if (obj32 == null)`
  boxes the bool (same shape as the old unknown call -- not a
  regression); a bool-fold of null-tested proved bools is its own
  future proof, not this round.
- Tests: +3 portable (arity-key normalize/range, genuine-underscore
  exactness, slot-prefix/bare shapes) +1 game
  (`test_game_interface_dispatch.py`: all three lines, zero
  `/*indirect*/` left in the method).
- Gates: compileall pass; portable 773 green (770 + 3); full suite 915
  passed / 3 failed -- identical IDs (32837 improvement-pin, 67525
  honest SIMD, 104428 stale); the slice moved zero goldens.
- Next #2 slices: vtable-slot occupants on abstract bases (needs
  store-provenance sidecar -- disproved-adjacent, do not touch without
  it), fnptr cells (fix-66 covers icalls; zero `fnptr_` hits tree-wide).

## Current work: param-exclusion rename round (2026-09-22, unpromoted)

Follows the unbound census (vN residuals were renamed *parameters*).
Same rules: `final_out/` untouched, no snapshot regen, no promotion.
`il2cpp/` edits via binary patches with CRLF/no-BOM asserts; `tests/`
edits LF.

- Fix LANDED: `_rename_locals` renamed body tokens matching metadata
  parameter names (StreamBuffer.WriteBytes v0/v1 became obj5/obj6 while
  the emitter kept v0/v1 -- every use disconnected, spine unbound).
  Params already declare their names; rename targets now exclude every
  metadata parameter spelling (a lifter temp sharing one keeps its
  honest lift-stage name instead of a silent capture).
- Evidence: mi 113041-113044 (2/3/4/8-arg overloads) render
  `this.buf[numN] = vK;` throughout, fully bound.
- Tests: +1 portable (param spellings kept, temp still renames) +4 game
  (`test_game_param_names.py`, all overloads, no obj5/obj6).
- Gates: compileall pass; portable 770 green (769 + 1); full suite 911
  passed / 3 failed -- identical IDs (32837 improvement-pin, 67525
  honest SIMD, 104428 stale); the exclusion moved zero goldens.
- Census remainder now: tN temps, SIMD type-position FPs, vN true-temp
  collisions (if any survive the exclusion -- re-run census at
  promotion time).
- Follow-up (same fix, no source change): every other census residual
  checks out as a metadata parameter -- HashCode.Initialize
  (ref uint v1-v4), MeshVoxelizer.GetTriangleBounds, JValue.ValuesEquals
  and the rest all render bound in fresh lifts; the 5 SIMD hits are
  type-position FPs of the checker. TODONOW §5's actionable set is
  ~zero in fresh lifts: +2 game pins (1935, 79519).

## Current work: rename-barrier + unbound-census round (2026-09-22, unpromoted)

TODONOW §5 work order (classify before patching) plus one real fix it
surfaced. Same rules: `final_out/` untouched, no snapshot regen, no
promotion. `il2cpp/` edits via binary patches with CRLF/no-BOM asserts;
`tests/` edits LF (one pre-existing CRLF game file kept as-is).

- Census LANDED (temp `unbound_census2.py`, read-only over `final_out/`,
  11,183 files): comment/string scrub, method-region split, textual
  dominance (earlier line, depth <= use). Result: **55 distinct unbound
  tokens in 21 files** (naive upper bound was ~8,700/~2,200) --
  scope/multi-decl/DCE-residue/comment noise was 99%+. Remainder: vN
  residuals (StreamBuffer v0-v7 et al.), tN oversize/bind temps
  (DateTime/TimeSpan/JToken...), SIMD type-position FPs (v128/v64/v256
  in Burst files), and exactly one obj-family case below.
- Fix LANDED (the obj-family case, mi 124140
  `AndroidJNI.IsSameObject`): native forwards `(obj1, obj2)` correctly
  (rcx via rdi, rdx via rbx), but output printed `(obj2, obj2)`.
  Traced end to end: `_seq` emits `(obj1, obj2)`; `_rename_locals`
  minted `s_8`/`v4` as `obj1`/`obj2`, shadowing the params, declared
  `object obj1 = obj2;`, and `_copy_prop` merged the dropped argument.
  Fix mirrors `_semantic_local_names`' barrier: reserve every
  obj/num/flag/real token in the lines plus every metadata parameter
  name, bumping until free (`_rename_locals(lines, m)`; single caller).
- Tests: +2 portable (body-identifier skip, unused-param skip via
  metadata) +1 game (`test_game_rename_barrier.py`: exact return line,
  no shadow decl).
- Gates: compileall pass; portable 769 green (767 + 2); full suite 904
  passed / 3 failed -- identical IDs (32837 improvement-pin, 67525
  honest SIMD, 104428 stale); the barrier moved zero goldens.
- Open from the census: vN/tN residual producers in the 21 files
  (StreamBuffer first), still unclassified by native cause.

## Current work: array-receiver shared-call round (2026-09-22, unpromoted)

TODONOW #1 first slice, subagent-mined. Same rules: `final_out/`
untouched, no snapshot regen, no promotion. `il2cpp/` edits via binary
patches with CRLF/no-BOM asserts; `tests/` edits LF.

- Fix LANDED: `_td_of` maps no array type, so array-typed receivers
  never reached the chain filter. New `Il2Cpp._system_array_td`
  (mirrors `_system_object_td`, per-instance cache) +
  `Lifter._array_receiver_td` (SZARRAY/ARRAY only, byref declines) +
  2-line fallback at all three chain-filter twins (`_call`, tail jmp,
  analyze jmp). Arrays have no subclasses and Array owns Clone, so the
  Array typedef roots the chain; sret-clear, ctor, generic, and
  `len(hits)==1` gates run unchanged.
- Evidence: mi 275/326 (`this.m_aValue`/`this.state`, byte[] homes) and
  mi 4047 (`this.delegates`, Delegate[]) resolve the 9-candidate Clone
  fold to `...Clone()` instance rendering (4047 even takes a typed
  `Delegate[]` decl); mi 144 string twins (Equals/op_Equality, one
  typedef) keep all 5 markers.
- Tests: +2 portable (array mapping, non-array/byref/missing/ambiguous
  declines) +4 game (`test_game_shared_twins.py`: 3 resolutions, 1
  must-decline count pin).
- Gates: compileall pass; portable 767 green; full suite 901 passed /
  3 failed -- identical IDs to the RSP-copy round (32837
  improvement-pin, 67525 honest SIMD decline, 104428 stale golden);
  none of 275/326/4047/144 is in the golden set.
- Next #1 slices: slot/hint-typed receivers (side-table corroboration),
  then receiver-driven generic substitution (needs synthetic table).
- DISPROVED with evidence (hinted receivers reverted, no residue):
  `&raycastHit1`→`distance` and `&taskAwaiter1`→`GetResult`/`IsCompleted`
  resolved cleanly, but resolving IsCompleted removed the
  ambiguous-shape union-kill that used to clear s_50's tile; the
  surviving tile was field-split by `_scalar_parts` (TaskAwaiter-typed
  RAX) and the whole-struct reload projected `.m_task` into the
  TaskAwaiter home (`<>u__1 = task1.GetAwaiter().m_task`, ill-typed,
  gate-invisible). Until whole-struct reloads prefer whole tiles
  (byte-range sidecar round), hint-driven resolution stays out -- same
  SHUFPS/80548 precedent. Repro analysis preserved in Temp
  (`probe_*`/`trace_*`/`diag_*` scripts); 25687/24238 revert lifts are
  byte-identical to pre-hint baselines.

## Current work: RSP-copy home round (2026-09-22, unpromoted)

Subagent-proposed, human-implemented. Same rules: `final_out/`
untouched, no snapshot regen, no promotion. `il2cpp/` edits via binary
patches with CRLF/no-BOM asserts; `tests/` edits LF.

- Fix LANDED (mi 117615 NetBitBuffer.WriteInt32AtOffset): `mov r64,rsp`
  now carries the frame offset (`_stack_offset`, `?`-text) instead of
  None, so [copy+N] keys slots by absolute address and aliases [rsp+M]
  of the same home (`_read_mem`/`_mem_lvalue`/LEA copy branches; RSP-path
  keys identical, `_aggregate_load` untouched after the quarantine below).
  Body went from `mem[8] = this;`/`mem_8`/raw twins to `this._offsetBits
  = offset;`/`this.WriteSlow(value, bits);`. Arithmetic/index/32-bit
  uses decline to unknown-base shapes; `mov rbp,rsp` keeps the pinned
  frame idiom (follow-up: RBP never takes a copy offset, one portable
  regression caught and fixed).
- Must-decline PINNED (mi 23900 ActorSpawner.Update): same-typedef
  Transform twins (get_parent triple, set_parent pair) keep their
  markers -- no receiver proof can split one declaring typedef.
- Quarantine (stash-proven): first cut tracked `lea rbp,[rsp-C]`-style
  frame offsets absolutely and split RBP-disp-keyed homes (80548
  `int num2` -> `object obj1` + unbound `num2`). RBP stays on legacy
  frame paths byte-identically (MOV/LEA/load/store/indexed all skip
  RBP; `_aggregate_load` reverted untouched). 80548 back to golden.
- Triage, all same improvement class (prologue spills through
  `mov r64,rsp` copies resolve to slots; dead ones drop; RBP untouched):
  32837 golden holds 4 raw `mem[]` stores, actual drops them
  (renumber-only fallout, native `mov rax,rsp` + 3 spills proven) --
  NEW red, consigned to regen; 108722 both native address-triples now
  print (`&obj6,&obj5` / `&obj5,&obj6`, old site-1
  `(default,default,default)` was copy blindness) -- review83 pin
  evolved to the faithful spelling with native cites; 104428 diff grew
  by the same mem-removal (its golden holds `mem[8]` too) -- same
  already-red ID, still awaiting the gated-regen user call.
- Tests: +4 portable (`test_recovery_completion.py`: slot roundtrip +
  cross-delta alias, arithmetic/index/32-bit+RBP declines) +3 game
  (`test_game_frame_copy.py`: 117615 improvement, 23900 markers, both
  `?addr` extinctions).
- `?addr` EXTINCT in fresh lifts: the promoted tree's only two hits
  (104380 `LineCircleIntersectionFactor`, 82799 `RestBendingConstraint`,
  both `store into untracked ?addr` in copy-heavy methods) render no
  `?addr` and no `mem[]` (dead-spill removal, renumber-only fallout;
  82799's 1-line `return real2` residue is pre-existing in its old body
  too). Pinned by the third game test above.
- Residual (honest, not regressed): 117615's replayed finally tail
  keeps one undeclared `obj6` phantom (was three undeclared
  mem[8]/mem_8/obj2); 67525 (SIMD UNPCK) unchanged.
- Gates: compileall pass; portable 765 green; full suite 895 passed /
  3 failed -- 67525 (honest SIMD decline) + 104428 (stale golden) were
  already red; 32837 is new but proved improvement (its golden holds
  the same 4 raw `mem[]` spills the fix removes; renumber-only
  fallout). 80548 quarantine-restored; review83 evolved green; `?addr`
  extinction pinned (3/3 game).

## Current work: TODONOW guardrail round (2026-09-22, unpromoted)

Subagent-assisted analysis of TODONOW.md 1-5 (4 analyses: census,
shared+indirect design, unknown+raw design, unbound-temp analysis).
Same rules: `final_out/` untouched, no snapshot regen, no promotion.
No `il2cpp/` source change (broad receiver/provenance fixes need
use→def machinery + synthetic nested-type sidecar; see deferrals).

- Inventory (read-only, python regex over `final_out/**/*.cs`,
  11183 files): shared 19013/2304, indirect 7091/975, unknown
  16045/1382, mem[N] 13189/805, mem_hex 343/69, goto 8707/903.
  Matches the TODONOW handoff figures up to scanner-definition deltas
  (case/`\b` token vs diagnostic hits, broad vs load-twin memhex);
  confirms the census note, not silently ignored files.
- Guardrails LANDED (`tests/test_recovery_completion.py` +4, LF):
  ambiguous shared keeps `/*shared body, N candidates*/`; consensus
  never resolves identity; untracked-base load/store stays raw
  (`mem_xx`/`mem[N]`); `unknown` never becomes zero/`default`.
- Targeted lifts: 67525 (`clamp(x, unknown, unknown)` -- honest SIMD
  UNPCK decline, const-pool+XMM lanes need stronger proof after 80548)
  and 104428 (modern static-field spelling + recovered aggregates;
  golden stale by design) unchanged by construction (test-only diff).
- Gates: compileall pass; portable 761 green (757 + 4 new); full
  suite 889 passed / 2 failed -- failure SET byte-identical to the
  triaged baseline (67525 honest SIMD decline, 104428 stale golden).
- DEFERRED with designs (not regressed, still open): broad
  shared-body receiver resolution + indirect/interface dispatch
  (proof-driven `_shared_receiver_target` + receiver-driven generic
  substitution designs ready; needs closed-receiver + synthetic table
  + field sidecar), unknown/raw provenance (tile/copy `_parts`
  threading, SIMD spill/lane gating, call-result consensus typing,
  base recovery -- all decline-by-default), unbound-temp re-census
  only after upstream (count is upper-bound with scope/multi-decl/
  DCE-residue/commentnoise false positives), per-arm Color (use→def
  const rewrite; 1445-site churn for 8 cosmetic sites), Navigation
  merge-side facts, 35 golden/review regens + promotion (user call).

## Current work: recovery follow-up round 3e (2026-09-20, unpromoted)

Continued TODONOW.md's blockers 1-3 plus cosmetic items 4-5. Same rules:
`final_out/` untouched, no snapshot regen, no promotion. All `il2cpp/`
edits via binary patches with CRLF/no-BOM asserts; `tests/` edits LF.
`tests/test_recovery_completion.py` grows 5 -> 17 synthetic tests;
`tests/test_game_synth_types.py` pins 4 synthetic-type behaviors.
Accessor-receiver hint (`_hint_accessor_recv` at the `set_` fold):
a resolved instance accessor proves its receiver through the
non-generic declaring typedef (slots/bare `t`-temps; byref-`this`
homes for valuetypes; dotted/`this`/generic/static/foreign kinds
decline). 23762's key is now `Selectable selectable1` with a
guarded typed assignment. 2 unit tests.
Copy-prop type guard: registering `dst = src` declines when both
sides declare different concrete non-object types (a struct home
copied over a typed temp is not value-preserving). Keeps 23762's key
and assignment from merging into the enumerator name; same-type and
object copies fold as before. 2 unit tests. Residual: `Selectable
selectable1 = dictionary22;` over-claims a 16-byte lane copy as a
full-struct copy (pre-existing whole-slot convention); single naming
forces one error site either way -- documented, awaits byte-range
slot versioning (the sidecar).
S6 layout steps (subagent-verified byte-exact vs native): nested-open
fields close through enclosing args in `_sf_infl_chain` (`_current`
carries closed KVP); `returns_sret` admits closed 0x15 with proved
size outside {1,2,4,8} (72-byte Enumerator folds the hidden buffer;
unproven shapes keep the fix-54 stand-down).
Candidate-tree gate for the five affected types (ConsoleUINavigation,
GlobalUINavigation, CollisionEventHandler, AnimationEventTrigger,
MicAudioCanvas, `--types` one build each into Temp): strict build 54
bodies / 0 failed / 0 fallbacks; tree-sitter parse 0/0/0; Roslyn probe
83 errors, all CS0246 missing-assembly scope noise, none on any
recovered identifier; before/after diff strictly improving (no more
elided static stores, unsafe raw blocks, or object soup where typed).
Full-tree compile remains a promotion-time gate.

- Blocker 2 LANDED (24655 OnEnable): the `t1012__1_0` store was NOT a
  `_mem_lvalue` bug (probe: `_field_expr` renders the correct
  `ConsoleUINavigation.<>c.<>9__1_0` every time). Root cause is
  `_bind`'s blind `str.replace`: binding `...<>c.<>9` rewrote the
  longer field name mid-identifier. New `_bind_replace` (`expr.py`,
  used at all 10 `_bind` sites in `lifter/state.py`) rewrites
  whole-token occurrences only (member access on the value still
  folds). Store now reads `ConsoleUINavigation.<>c.<>9__1_0 =
  predicate13;`. 3 unit tests.
- Blocker 3 LANDED (23761 DisableAllActiveSelectables): three parts.
  (1) `_hint_arg_types` `&slot` branch now types by-VALUE struct homes
  from the substituted closed parameter type (`&s_20` + TValue ->
  Navigation at `Dictionary.Add`; TRUST-gated like the `ref`
  rewrite, closed-key proof, setdefault). (2) Stack-slot stores of
  whole-field struct values record the type (`_struct_home_ty`:
  exact closed valuetype, no slices/parts/addresses). (3) A scalar
  constant at a struct-typed home's base renders field-precisely
  (`_home_field_store`: exact-width offset-0 field proof +
  `_fimm`-compiles gate, else today's scalar). Result: `Navigation
  navigation1` at `Add`, `navigation2.m_Mode = Mode.None`, no scalar
  soup; the home-construction residue stays (loop-DCE conservatism is
  load-bearing) but is fully typed and compiling. 3 unit tests.
- Blocker 5 LANDED (23917 contact): the lifter emits exactly one
  packed spelling, `(float2)(lit, lit)` over float literals (constant
  pool) -- provably pure. `_PURE_LOAD_RX` admits paren-free-arg
  `(float2)(...)` (mirroring the `typeof` carve-out; a later
  substituted call keeps parens and still declines), so the dead
  packed temp drops in ordinary DCE. Cyan kept. 1 unit test.
- Improvement (45016 ConvertTo): struct-home recording types the
  `TimeOfDay` temp (`object obj29` -> `System.TimeSpan timeSpan1`),
  fixing an object-member access that cannot compile. Consigned to
  the regen list (below), not reverted.
- Blocker 4 LANDED (`_subexpr_cse`, new pass after `_value_cse`):
  anchor decls (`num`/`obj`/`t`, single-assigned, pure RHS) lend their token
  to later subexpression occurrences (`num3 = num2 | num2 >> 16`). Purity is
  the exact `_value_cse` test (no auto `?` decline; one well-formed ternary
  required); kills mirror the strictest passes (depth/labels/goto/case/
  catch/finally/break-loop-frames/backward-gotos/stores/byref); fix-58b
  holds (calls/`new` never seed); whole-token replacement with atom-paren
  strip. Both pow2 sites fold (23761, 23767). 5 unit tests. Side effect:
  the 25626 offset chain compacts too (`num4 + bytePtr1`, was fully
  re-expanded) -- the pinning test over-fits the old spelling, consigned
  to regen, not a revert.
- Blocker 1 foundation LANDED (table + recursion + homes, zero blast radius):
  S4 (subagent) root-caused B11's loss: NOT a line pass but
  `_abandon_at_region_close` firing on the loop latch (region opened at
  the header, closed on the latch) and emitting `break` + deleting the
  block's statements -- flow inversion by construction. Fix in
  `dec/emit.py`: a latch block carrying statements emits label + stmts,
  marks consumed, emits the backedge copies, and falls off (the
  structured loop IS the backedge); empty latches keep the old
  break-out. 23762 now keeps `if (obj5 != null) { obj5.navigation =
  obj18; }`.
  S5 (subagent) corrected the call map (MethodRef kind-6 slots prove
  closed generic identities: GetEnumerator/MoveNext/Dispose/Clear over
  (Selectable, Navigation); no get_Current call; s_38/s_48 are silent
  aggregate fills) and designed home typing: `_proved_struct_home`
  seeds `slot_types` at proved-generic `info` sites (`&s_N`
  buffer/receiver + closed-struct substitution; static path additionally
  requires struct return and no byref/pointer params). 23762 now
  declares `Dictionary_2<...>.Enumerator dictionary21` with named
  MoveNext/Dispose. s_30 buffer typing skipped (size unprovable for
  open defs); key/value field subst still needs the sidecar.
  Fixed along the way: fake-VA allocator is process-wide (class-level
  `_tn_cache` is shared across Il2Cpp instances -- an order-dependent
  cross-test collision, caught by the suite).

  `_synthetic_inst` (fake-VA side table on `Il2Cpp`, keyed cache for
  dry/real stability) + reader branches (`_generic_inst_name`,
  `_closed_type_key`, `td_of_ty`, `_generic_inst_args`, `_td_of`,
  `_generic_class_args`, `_byval_struct`, `_type_has_var`) +
  recursive `_subst_closed` wired into `candidate_return_type`
  (all-or-None, byref preserved, tails untouched, SRET/`trust`
  stand-downs frozen). Proved on real rows: `Dictionary_2<Selectable,
  Navigation>.Enumerator` renders exact, keys structurally, td 1514
  round-trips; real specs close (`ChangeEvent_1<bool>`). 23762 itself
  is unchanged (no spec carries our args; interface path dominates) --
  the receiver-driven + field-sidecar slice stays next per blueprint.
- DEFERRED with designs (not regressed, still open): blocker 1 remainder
  (23762: no closed Enumerator/KVP rows exist by scan, so return
  substitution alone cannot represent the type; deeper: NO MethodSpec
  carries (Selectable, Navigation), so substitution must be
  receiver-driven (closed Dictionary row 6766 + open 11337 return), not
  spec-driven; `type_sizes[1514]` is None and its field chain shows only
  `_dictionary`, so size/field fast paths need the inflated chain; S1's
  consumer audit (exact touch list in session record) covers table +
  reader branches + recursion + home typing, but homes (0x15 excluded
  from `_struct_home_ty` by design) and field-type substitution at use
  sites still need a sidecar design -- table-alone buys ~2 decl lines
  for corpus-wide hot-path churn, so implementation waits for the full
  blueprint; key/value reads are
  field loads and the assignment loss is structural -- needs a
  synthetic nested-type table + home typing + receiver resolution +
  field substitution; the double Dispose is faithful, two native
  calls; the finally `obj14.Dispose()` on `&obj3` needs the same
  struct-typing machinery) and blocker 4 (power-of-two reuse needs
  subexpression-CSE/value-numbering: `_value_cse` is whole-RHS only
  and lifter `_bind` is per-OBJECT by fix-58b design; output is
  correct and compiling today).
- Crash fixes (prior drift exposed by volume, fixed narrowly): tied
  pending-call sort (`sorted` on Expr compare -> stable key sort +
  discovery order; 129 build fallbacks cleared); unknown-size
  `_stack_store` guard in the sret fold (3 lost bodies recovered);
  `_kill_one` preserves `_mi`/`_usg_idx` + delegate-index guard (8 sweep
  `list[None]` crashes cleared). 1 unit test; repro probes in Temp.
- Parse fixes (prior null-base-address drift): `_wb_operands` renders
  numeric dst as the twin-matching deref (`16 = v` unparseable);
  `_unsafify` repairs cast-prefixed `(T*)*N` (multiplication untouched);
  `_subexpr_cse` paren-strip declines call/type/index/shared-marker
  contexts (77059 + TextGeneratorUtilities cases). 3 unit tests.
- Crash repairs (prior volume exposing HEAD-latent bugs, all
  stash-proven not-mine): tied pending-call `sorted` on Expr compare
  (129 build fallbacks cleared, discovery order kept); unknown-size
  `_stack_store` in the sret fold (3 lost bodies recovered);
  `_kill_one` dropping `_mi`/`_usg_idx` + delegate-index guard (8 sweep
  crashes cleared). 1 unit test; repro probes in Temp.
- Parse repairs (prior null-base/bool drift, all stash-proven
  not-mine): `_wb_operands` renders numeric dst as the twin-matching
  deref; `_unsafify` repairs cast-prefixed `(T*)*N` (multiplication
  untouched); `_subexpr_cse` paren-strip declines call/generic/index/
  shared-marker contexts (77059 + TextGeneratorUtilities cases);
  `_bool_sugar` paren-wrapped folds take the `[^?]` guard (101899
  family); `_simplify_cond` requires whole-group negation
  (MinMaxAABB family). 5 unit tests.
- Parse-0 repairs (prior drift, each stash-proven not-mine except
  where noted): `_bool_sugar` paren-wrapped folds take the `[^?]`
  guard (101899 family: lazy group spanned `&`-joined ternaries);
  `_simplify_cond` requires whole-group negation (MinMaxAABB family:
  `!(A) & (B)` is not `!((A) & (B))`); `FOLD_RE` declines call-argument
  parens like `SUB_CMP_RE` (`s_28.ctor(0 + 1)` kept intact,
  XmlNodeConverter). 3 unit tests.
- Gates: strict rebuild 11,181 files / 114,458 bodies / 0 failed / 0
  fallbacks (matches promoted baseline exactly); brace 0 unbalanced;
  parse 0 bad / 0 ERROR / 0 MISSING (was 109 / 5349 / 33);
  portable 751 green (718 + 33 new); full suite 846 passed / 35
  failed, failure SET byte-identical across every stage. The 34
  = baseline triaged 22 + 12 inherited-drift items, EACH proven
  not-from-this-session (prior tree fails the same 12: P6 files 2,
  unpcklps handler 1, owner-strip 4+closure+45016-line, klass-bind
  gate 4 incl. 39789/packed/datetime/26747-guard; my tree adds only
  the 45016 TimeSpan improvement hunk). Per-item evidence in
  TODONOW.md's session addendum. No new failures from this session
  (the +1 vs the earlier 34-count is the 25626 improvement pinning the
  old spelling, plus 5 new CSE tests on the passing side).
- Leftovers: blocker-1 remainder (receiver-driven substitution +
  field sidecar + structuring, blueprint ready), Navigation merge-side
  facts, per-arm Color, 35 golden/review items awaiting gated regen
  (22 triaged + 12 drift + 1 improvement-pin), promotion (user call).


## Current work: recovery follow-up round 3d (2026-09-20, unpromoted)

Same rules: `final_out/` untouched, no snapshot regen, no promotion.
Portable 718 green; full suite 822 passed / 22 failed (identical triaged
set as 3c — the pass moved none of them).

- `switch(string)` phase 1 (`_hash_string_switch` in `flow.py`, after
  `_switch_synth`): Roslyn string-switch is a ComputeStringHash
  binary-search + per-arm string-equality confirm; ranges only route,
  confirms dispatch. FNV-1a/32 over UTF-16 units verified against 20
  observed constants; every leaf proves itself (unanimous
  ComputeStringHash callee via IL candidates, literal FNV == arm hash
  const, pairwise-distinct hashes, String Equals/op_Equality callees,
  no rebindable flow or S/H refs, H dead past tree, >=3 cases).
  Handles direct `==`, temp-mediated and inline Equals confirms, and
  negated `if (!V) {} else {}` pass-time shapes; declension for gotos,
  loop arms, collisions, unverified leaves. Dead literal/equals temps
  collected downstream. Folds 25293 (8 cases), 24765 (8 cases +
  breaks), twins 25577/26314; 24694 declines honestly (gotos).
  Post-fold hardening: unjumped labels allowed in arm prefixes (26314
  has two dead ones; jumped labels abort anywhere since C# forbids
  jumping into a switch section and dropped labels dangle), plus a
  cross-arm/outside-span temp-use post-check (prefix temps vanish with
  the span). Full suite 822/22 identical triaged set.
- Per-arm Color: deferred with evidence, no source change. All three
  repro shapes flow through phi copies into Color-typed sinks (26794
  `Color color1`, 27827 `.color = ternary`, 23917 `set_color`), but
  text level cannot recover the hidden B/A channels from `(float2)`
  display, and rendering all four floats churns 1445 corpus sites in
  352 files for 8 cosmetic sites (values are correct 16B throughout;
  only display is lossy). Needs use→def const rewrite machinery.
- Leftovers: Navigation merge-side facts, 22 goldens awaiting gated regen.

## Current work: recovery follow-up round 3c (2026-09-20, unpromoted)

Same rules: `final_out/` untouched, no snapshot regen, no promotion.
Portable 718 green; full suite 822 passed / 22 failed (70050 + 107123
restored to golden, no new breaks; remaining 18 snapshots + 4 review
tests match prior triage).

- SIMD twin-consistent, both shapes (design: twin-unanimity with
  raw/honest fallback; looseness is cosmetic-only, never wrongness).
  - Shape B (107123 vorn_u32 -> `/* nothing */`): `_dead_shared_forwarder`
    in `calls.py` declines the pending bare-statement when the caller VA
    is multi-candidate, the target is single-candidate, and the next
    insn is int3/ud2. Single-caller `RemoveAll` still flushes.
  - Shape A (70050 double3x3 negate, byte-exact golden): `_xor_twin_load_sites`
    scan in `build.py` (sqrt-site precedent) proves same -0.0 const +
    same base reg + packed-16/scalar-8 adjacency; scalar loads decline
    member sugar in `_aggregate_load` + `_field_expr`, the `_R4_TY`
    width rule restores `byte*`, textpass renders the golden.
- Event `+=`/`-=` folds mirroring `set_` (void-gated, 3 unit tests);
  native-list `.Count` for field receivers; exact `<T>` narrowed to
  method-level args after a live misfire; assignment-ternary bool
  materialization with all-uses retype.
- DISPROVED with evidence (no source change): Navigation phi-atom
  read-side acceptance. The phi atoms are Navigation-typed chunks
  (v165/v166), so the bool Wrap field can take neither (compile break
  under loose naming; `v166.m_Mode` misread via struct-chain). Needs
  merge-side unanimous-subrange preservation (the stuck design).
- Censuses (read-only, JSON under `%TEMP%/opencode`): hash-switch
  family is real — ComputeStringHash + range splits + string confirms,
  single-write pure temps (25293 FPSController.ConvertStringToKeyCode
  smallest complete + 4 twins, 24765, 24694 with loop-continue arms);
  divergent color ternaries in 8 methods (23917 contact red/green
  headline, 27827 3-way, 26794 if/else stores).
- DEFERRED with designs (not regressed, still open): per-arm Color
  (bytes lost at text level; load can't know Color vs Vector2 — needs
  consumer-type proof); Navigation merge-side design.
  (`switch(string)` landed in 3d below.)
- Leftovers: 22 triaged goldens (regen only after gates).

## Current work: recovery follow-up round 3b (2026-09-20, unpromoted)

Subagent-assisted fixes + reverts. Same rules: `final_out/` untouched, no
snapshot regen, no promotion.

- Exact generic `<T>` call tokens (method-level args only; type-level
  declined after a misfire caught by golden 21027).
- COUNT macro simplified to two shapes; native-list field receivers.
- Assignment-ternary `? 1:0` materialization with all-uses-bool retype;
  phi-decl hoist (mic block fully bool-typed; Update verified).
- Ambiguous-shape slot kill (32837 zeros gone); name-shadow renames.
- Reverted with evidence: full SIMD tracking (stash-proven 0 wins, broke
  twins/sqrt in 3 goldens), partial structs (undeclared slots),
  identity/single-origin folds.
- Gates: portable green; game goldens hold prior fixes (31361/2, 45016,
  21027, review83 typed-shared, review81).
- Leftovers: Navigation path-sensitive facts, color ternary arms, full
  SIMD redesign (twin-consistent), 24 triaged goldens (regen vs genuine:
  32837-shape, 104428-tail, 32832/11974 unclear).

## Current work: recovery follow-up round 3 (2026-09-20, unpromoted)

Subagent-assisted round (4 analyses + 2 implementations, all gated).
Same rules: `final_out/` untouched, no snapshot regen, no promotion.

- Exact generic `<T>` call tokens from proved slot identity (method-level
  type args only; generic-type case declined after a misfire).
- Byref params kill slot caches (80548 head back); ambiguous-shape calls
  union-kill arg0 slots (32837 stale zeros gone); `.ctor`-on-stack-buffer
  records construction (31664 whole).
- VT-echo/exact-first guards (m_State/m_StateBlock); fragment type
  preservation (104428 call type); static RGBA bytes to Color (generalized
  structs, phi-bytes infra that honestly declines divergent arms).
- Ternary bool reconciliation, assignment `? 1:0` materialization with
  all-uses-bool retype, phi-decl hoist (mic block fully bool-typed);
  native-list `+0x28` Count sugar incl. field receivers.
- Reverted with evidence: full SIMD tracking (0 wins, broke twins/sqrt in
  3 goldens — stash-proven), partial structs (undeclared slots),
  identity/single-origin folds.
- Gates: portable 718 green (45 followup tests); full suite 816 passed / 24 failed, every failure triaged
  (improvements-awaiting-regen vs genuine: 32837-shape, 104428-tail,
  32832/11974 unclear, 83s neutral/brittle).
- Leftovers: Navigation path-sensitive facts, color ternary arms, full
  SIMD redesign (twin-consistent), per-golden regen only after gates.

## Current work: recovery follow-up round 2 (2026-09-20, unpromoted)

Continues the prior session (committed 5b13c9d). Same rules: `final_out/`
untouched, no snapshot regen, no promotion. CRLF/no-BOM kept via binary
patches; `tests/test_recovery_followup.py` (LF) now pins 40+ behaviors.

- Exact-tiling composites with per-tile routing (`_parts`), proven-prefix
  recording, fragment type preservation, slot-type fill on composites.
- Ignored-call flush twin-proofed (mov-copies, phi copies, rendered text);
  ambiguous-shape calls union-kill arg0 slots; byref params kill slot
  caches (viscosity head back); `.ctor`-on-stack-buffer records.
- Call rendering: exact generic `<T>` tokens (method-level args only),
  VT-echo/exact-first guards (`.m_State`/`.m_StateBlock` back),
  List `.Count`, native-list `+0x28` `.Count` sugar, static RGBA bytes to
  `Color.*`/`new Color` (+ generalized RGBA structs).
- Dec passes: ternary bool-arm reconciliation, assignment-ternary `? 1:0`
  materialization with all-uses-bool retype, phi-decl hoist (Update mic
  block fully bool-typed; enum decls via hint-guard; IntPtr tests null).
- Reverted with evidence: partial struct assembly (undeclared slots),
  identity/single-origin folds, fragment re-root reversal confusion.
- Fixed-then-verified regressions: 31664 ctor/store/return, 32837 stale
  zeros, 104428 call type, 31361/2, 45016, 126258 null-check, 5769 byte.
- Gates: portable 711 green; full suite ~807 passed / 24 failed, every
  failure triaged (improvements-awaiting-regen vs genuine: 32837-shape,
  104428-tail, 32832/11974 unclear, 83s neutral/brittle).
- Leftovers: Navigation path-sensitive facts, color ternary arms, SIMD
  lanes, `GetComponent` (done), mic scope (done), per-golden regen only
  after gates.

## Current work: decompiler recovery follow-up (2026-09-19, unpromoted)

Continues `nowtodo.md` (2026-09-19 stop record, committed alongside): the
experimental aggregate/interface/null-edge work plus new fixes below. Nothing
here is promoted: `final_out/` untouched, no snapshot regen, no rebuild. All
`il2cpp/` edits kept the CRLF/no-BOM contract (binary patches with
line-ending asserts); `tests/test_recovery_followup.py` (LF) pins the new
behavior (38 tests).

- Aggregate audit: `_write_mem` no longer suppresses sliced stack stores
  (suppression + merge-killed slices produced undefined temps; contact's
  `obj22` is now a defined `contact1.pointB.x`), mem-facts keep the value's
  refined text, exact-tiling composites route per-tile (`_parts`), narrow
  provenance records its prefix, valuetype loads fall through on degraded
  fragments, reference loads defer to exact `_field_expr` hits.
- Ignored non-void calls flush once as bare statements at defpos after phi
  destruction (replaces bind-everything; used calls stay inline; twin-proofed
  against mov-copies and phi copies). `RemoveAll` retained in OnEnable.
- Write barriers and `.ctor`-on-stack-buffer record their stores; byref
  params kill the slot cache (viscosity `num1<num2` + stride back).
- LEA names unified to the `slot_var` convention (no more `s_ffff…`
  aliases); MOVDQA/MOVDQU stores/loads handled; List `+0x18` renders
  `.Count`; static RGBA bytes render `Color.*`/`new Color` via `_color_text`.
- Proven-type beats instruction-shape hints (`InputMode` decls back);
  IntPtr/UIntPtr (any TE spelling) test against null; unknown-kind TESTs
  stay null-style.
- Fixed goldens now passing: 31361/2 (`.m_State`), 32833 field
  (`.m_StateBlock`, entry drift remains), 31664 (ctor/store/return),
  45016, review80-touchscreen. Remaining 24 failures triaged per item
  (several read as improvements pending gated regen; open regressions:
  32837 value→zero folding, 104428 call-absorbs-select, SIMD-lane vectors,
  color ternary arms, Navigation full struct, `GetComponent<T>` args).
- Gates: portable 695+ green; full suite 803 passed / 24 failed (HEAD
  stash-proves-clean at 795/795, so all 24 are working-tree drift).

Leftovers: Navigation struct assembly needs path-sensitive facts
(first-item skip-join legitimately phis); contact color arms + SIMD lanes +
custom `+0x28` count; mic bool/int `SetActive` + PTT flag scope; item 9
(hash-switch/events) correctly deferred; per-golden native review before
any regen/promotion.

## Package split (2026-09-12, no behaviour change)

`il2csharp.py` (10,061 lines) and `decompiler.py` (8,407 lines) were split into
the `il2cpp/` package (42 modules). Lines were moved by binary CRLF slicing,
never retyped, under coverage and line-preservation asserts; the splitter is
`work/split/split_pkg.py` and the import smoke is `work/split/smoke.py`.

- Big classes are composed from mixins, one file per mixin: `Il2Cpp`
  (`runtime/`: registration, types, fields, eh), `Lifter` (`lifter/`: state,
  values, insn, calls, render), `Decompiler` (`dec/`: build, analyze,
  structure, sugar, seh, flow, dataflow, highlevel, textpass, emit).
  Pass order inside `_structure`/`_final_text` is untouched.
- Cycle-free by construction: leaf helpers live in `il2cpp/names.py` and
  `il2cpp/runtime/meta.py`, `runtime/__init__.py` is deliberately import-free,
  and `dec/sugar.py` + `stmt_text.py` reach `Decompiler` through a late-bound
  proxy. `python -c "import il2cpp"` is the cycle regression check.
- `il2csharp.py` is now a launcher (CRLF + UTF-8 BOM retained), so
  `python il2csharp.py <target> -o <out>` still works; `python -m il2cpp` too.
  `decompiler.py` is gone (`bckups/presplit_20260912/` holds both originals).
- Consumers moved to real imports (no re-export shims): 271 import lines in
  154 files across `tests/`, `tools/`, `work/`. Historical monolith snapshots
  under `bckups/`, `final_out/`, and `work/review8*` were deliberately
  left untouched.
- Contract test `tests/test_source_format.py` now asserts CRLF + no BOM across
  `il2cpp/**/*.py` and CRLF + BOM on the launcher. `source_sha256` in
  `tools/validate_corpus.py` / `tools/make_goldens.py` now pins every package
  file via `corpus_common.source_fingerprints()`.
- `tests/test_diagnostics.py` imports `il2cpp.cli` (not the facade) because
  `main()` resolves `Emitter`/`Metadata`/`is_arm64_binary` in that module.
- Gates: 436 tests pass (317 portable + 64 snapshots + 54 native, plus the
  extra source-format case); byte-identity rebuild vs `final_out/` recorded in
  `validation_reports/split_rebuild_verification.json`.
- Root cleanup: `scan_stale.py` -> `tools/scan_stale.py`, `SHA256SUMS.txt` ->
  `validation_reports/SHA256SUMS.txt` (`tools/verify_release.py` looks there
  first, then the tree root).
- `work/` reorg (2026-09-12, moves only, no renames): the flat tree is now
  grouped into `artifacts/`, `batches/`, `census/`, `experiments/`, `lib/`,
  `logs/`, `patches/`, `probes/`, `review81/`-`review89/`, `runners/`, and
  `split/` (routing table in `work/README.md`; `review83/`, `review84/`, and
  the `reviewNN_out/` trees predate the reorg and were left as-is). The 176
  root-deriving scripts were depth-rewritten in the same pass
  (`parents[1]` -> `parents[2]`, one more `dirname(...)`);
  `work/split/verify_reorg.py` proves every root expression still resolves
  (167 expressions across 162 files).
- Release manifest refreshed after the split + reorg:
  `validation_reports/SHA256SUMS.txt` 12,597 -> 12,638 entries (406
  relocated, 11,391 rehashed — the old manifest still pinned the Review 84
  tree while `final_out/` holds the promoted Review 89 tree, as proved by
  `work/split/probe_manifest_era.py`: 400/400 sampled `final_out/` digests
  match `bckups/final_out_r84`, 0 match the current tree — 1 dropped
  `decompiler.py`, 42 added `il2cpp/` files; the pre-split manifest is
  archived at `validation_reports/SHA256SUMS.presplit_20260912.txt`).
  `tools/verify_release.py` passes with 0 failures.
- Post-verification cleanup: `work/split/rebuild_out/` (the 11,200-file,
  ~138MB byte-identical rebuild used once for the split proof) deleted; the
  proof stands in `validation_reports/split_rebuild_verification.json` and
  `work/split/rebuild.log`. Small evidence logs kept (`rebuild.log`,
  `fulltest.log` with the 436-pass run).

## Current work: unavailable method bodies (committed 3bf35b3, pushed 2026-09-19)

Concrete methods with no native address now emit a throwing body instead of
an illegal semicolon declaration. The shared body path also covers accessors,
declaration-only output, unavailable lifting backends, and method limits.
Abstract/interface contracts retain semicolons, and successfully recovered
empty bodies remain empty. Missing bodies throw `NotImplementedException`
with an explicit recovery message; these are placeholders, not recovered
implementations, and do not increment lift/failure/fallback counters.
The final namespace-shortening pass preserves alias-qualified names such as
`global::System.NotImplementedException`; stripping `System` there would bind
the exception in the global namespace instead.

Regression coverage compiles generated constructors, ordinary and explicit
interface methods, indexers, properties, and events with Roslyn in all three
unavailable-body modes. Committed evidence: `validation_reports/method_bodies_{parse,
delta,regeneration}.json`; build/compile/tests logs were removed in the
2026-09-19 cleanup. Candidate tree `work/method_bodies_out/` was removed in
the same cleanup (superseded by `work/rpc_payload_out/` below).

Gates: 795 tests pass (669 portable + 126 native); strict build 11,181 files /
114,458 lifted bodies / 0 lift failures / 0 structured fallbacks / 0 type-emission
failures. After the namespace correction, 1,005 files containing `::` were
regenerated through the emitter (21,944 lifts, all failure counters zero),
copied back by TypeDefIndex with full-build shared stubs retained; provenance
and final source fingerprints are in `method_bodies_regeneration.json`.
Final parse: 0 bad files / 0 errors / 0 recovery nodes. Compiler probe:
10,305 → 2,463 errors, 1,516 → 726 files with errors; CS0501 7,718 → 0,
CS0535 88 → 0, CS0073 26 → 0, CS8051 9 → 0, CS0523 1 → 0. Other diagnostic
counts are unchanged. The tree contains 9,193 explicit unavailable-body throws;
it still does not compile or provide those implementations. No control-flow
lifting changes were made. Next largest category is CS0737 (880), followed by
CS0111 (384) and CS0052 (308).

Duplicate-method triage must distinguish actual emission collisions from the
combined-assembly probe: for example, `IsUnmanagedAttribute` has one constructor
in each source assembly, but combining those partial types produces CS0111.
Deleting those constructors would damage the individual recovered assemblies.

## Current work: accessor recovery + RPC payload typing (committed 3bf35b3, pushed 2026-09-19)

Committed tree stacks two units on the promoted fix-123 tree:
`il2cpp/csharp.py` + `emitter.py` + `runtime/fields.py` (storage identity
`__field_X`, real property/event bodies; `tests/test_member_recovery.py`,
`tests/test_game_member_recovery.py`) and `il2cpp/lifter/{state,insn,values}.py`
+ `runtime/types.py` (pointer/array operand typing, below). `final_out/` still
holds fix 123; `work/accessors_out/` and `work/rpc_payload_out/` were the two
gated candidate trees (both 11,181 files, 0 failed lifts, parse 0/0/0).
`work/accessors_out/` was removed in the 2026-09-19 cleanup;
`work/rpc_payload_out/` is the retained newest output and matches the pushed source.

RPC payload typing (specimen InventoryManager.Rpc_CMD_UpdateInventoryForHost,
mi 25626, VA 0x180704750): unbound `obj1` and `object` payload arithmetic are
gone — `inventoryIds_.Length`, `byte* bytePtr1 = (byte*)simulationMessagePtr1
+ 0x1c`, `int` offset chains, `((int*)bytePtr1 + off*1 + 0x0)` stores, one
`num5` temp. Fixes: RBP-as-frame is now value-tested (`_rbp_is_frame`: None /
`&s_xx` / `?addr` / never-written stay slots; params/objects/composites
resolve normally); array-typed entry params carry kind `arr` ([arr+0x18]
folds to `.Length`); `lea` over int is int math while past-struct lea from a
typed pointer spells a `(byte*)` cursor from a genuine metadata `byte*` row
(temps declare `byte*`); int-base + byte*-index SIB renders pointer-first at
scale 1 only; long binop operands bind typed instead of minting anonymous
twins; ADD int+ptr yields ptr (byte-proven type only); `.Length` carries Int32;
empty vtable rows (raw 0x1, no method bits) decline instead of naming mi 0
(healed three pinned `Interop.GetRandomBytes` misresolutions: 39789 hunks,
83647, 109664). Gates: 665 portable + 126 game pass (10 new lifter unit tests
in `tests/test_pointer_operand_typing.py`, 4 game asserts in
`tests/test_game_rpc_payload.py`); sweep 116,178 / 0 crashes / 0 new crashes /
1 structural delta (mi 37884 into_block 1→0, +1 line, nothing dropped);
9,200 changed bodies vs accessors; rebuild 11,181 files / 114,458 bodies / 0
failed; parse 0/0/0; probe 10,305 errors, per-code identical to accessors
(all 1,393 pair moves are line-number shifts). Committed evidence:
`validation_reports/rpc_payload_{parse,sweep}.json` plus
`rpc_payload_sweep.tail-args.jsonl.gz`; build/compile/sweep logs were removed
in the 2026-09-19 cleanup. Retained tree: `work/rpc_payload_out/`.
14 goldens regen'd after review (8 accessor renames untouched by this unit +
6 here: 39789/62312/83647/109664 improvements, 11974 renumber, 5769 noted below).

Open follow-ups: GetChars (mi 5769): merge type preservation for cmov-selected
values is done -- the pass wipe ran after entry setup and discarded the stack
parameter names/types, so the decoder arrived at the cmov as untyped `s_88`;
wiping before setup plus slot reloads restoring the recorded kind recovers
`baseDecoder`/`getClass()`/`charCount`/`_mustFlush`/`_bytesUsed` (was: undeclared
`num3`, then raw decoder derefs). Widths are done: a CMOVE
`recv.getClass() == typeof(T)` selecting `recv` stamps the exact type (klass
equality is exact, unlike `is`; the compared `typeof` usage already carries
the typedef -- td 691 `UTF7Encoding.Decoder` holds exactly `bits@0x30`,
`bitCount@0x34`, `firstByte@0x38`). The predicted alias rule proved
unnecessary: the existing single-known-type phi/var rule carries the derived
type to the working temps on its own. The rule generalizes (delegate types,
`_source`/`_token`, shared-call resolution, enum members, `ref` field args;
two sampled methods shed `unsafe`). Still open: the post-loop arm-scope reads
(`flag5`/`num5`/`num6`), which need declaration hoisting across the loop
boundary (structuring risk) -- do not treat as resolved. Analysis (2026-09-19):
the loop is single-trip (unconditional trailing `break`, no `continue`), and
the snapshots are load-bearing spills (arm C reads old `num2` mid-arm, so they
cannot be eliminated). Hoist-with-state-init is sound only under single-trip
(multi-trip + a non-assigning arm, e.g. `num5` in arm B, would read stale
init instead of the leftover), and the init mapping itself needs the
header-exit-edge register state -- textual `first bare copy` cannot prove
which pre-loop register the 0-trip path reads. Reading the state temps
instead is wrong on arm-C-break (snapshot `num2+6-16` vs pre-arm `num2`).
Verdict: needs exit-path-sensitive phis, not a text hoist;
CopyFromArray dest args reprint the ids extent instead of reusing `num4`:
investigated to ground truth and accepted as residue -- native executes three
copy calls (0x1807048f7/922/94c, mi 25626); the two extra ids-copy texts are
phantoms (one execution re-rendered) over idempotent same-byte rewrites, so
output values/order are faithful. Reusing `num4` would delete executions,
which needs execution-identity proof the pipeline does not have: _bind folds
per OBJECT, never per text, precisely so real duplicate calls are never
merged (fix 58b SaveManager rule). Two honest attempts reverted: counting
movsxd copies as uses bound earlier but collapsed the `num4`/`num5` temp
boundary the spec pins; rewriting live superstrings at bind time did the same
with added epoch hazards. Needs value provenance, not a window tweak.
`&this.field`-in-rbp and genuine `T* + N` element arithmetic keep today's
spelling.

Gate for the three unnumbered follow-ups above (float shortening, cmov
merge-type, exact-type stamp; pushed `a2887e9`): `work/followups_out` built
strict, 11,181 files / 114,458 bodies / 0 failed lifts / 0 structured fallbacks
/ 0 type-emission failures; brace audit 0 unbalanced; tree-sitter parse 0 bad
files / 0 ERROR / 0 MISSING; full-corpus sweep 116,178 methods / 0 crashes;
2,759 files differ from `work/rpc_payload_out` (none added/removed), all
sampled diffs rename/type/field-only. Follow-up: float tie-break prefers fixed
point on length ties (`10000.0f`, not `1e+04f`; 14 addresses moved, 0 crashes)
and `tests/goldens_review84.json` was regenerated with `tools/make_goldens.py`
against the refreshed sweep/parse reports: 6/64 snapshots changed (GetChars,
ReadSpan, Update, OnNextUpdate, ConvertTo, Execute), each reviewed
individually, all structurally identical; full suite 795 passed. Promoted
2026-09-19: `final_out/` holds `work/promote_out` (11,274 files, aggregate
`db468523…050c36105`, 0 mismatches); see `docs/archive/reviews-log.md` 0bg
and `validation_reports/followups_promotion_verification.json`.

## Cleanup 2026-09-19 (after the 3bf35b3 push; `bckups/` deleted later the same day)

Deleted per user call: all untracked build/compile/sweep/tests logs under
`validation_reports/` (reviews 114–123, accessors, method bodies, rpc_payload,
partial_unsafe — the committed parse/sweep/promotion/delta/regeneration JSONs
and tail-args blobs stay, 472 tracked files), all gitignored sweep/compare
blobs (`*.methods.jsonl.gz`, `*_vs*.json`, `*comparison.json`,
`output_audit.json` — regenerable via rebuild/sweep), the superseded
candidate trees `work/accessors_out/` + `work/method_bodies_out/`, and finally
the whole `bckups/` dir (9 promoted-tree copies fix99–fix122 + review97e,
1.24 GB — GitHub is now the history authority; no tracked file was touched).
Work-tree pass the same day: all `work/review98_out`–`work/review123_out`
(26 gated trees, ~3.6 GB — `review123_out` was byte-identical to `final_out/`,
`review114_out` was an unfinished partial rebuild), the unreferenced
`work/method_bodies_alias_regenerated/` intermediate (already copied back),
and `work/accessors_preview/` probe artifacts. Every deleted tree rebuilds
from git history in ~7–9 min; per-fix paragraphs below keep their `built tree`
citations as the gate record.
Kept: `final_out/` (promoted fix-123 baseline), `work/rpc_payload_out/`
(matches pushed source), and the older `work/review*_out` + `work/partial_*_out`
trees. Historical paragraphs below that cite a removed log/blob/tree keep
their original lists as the gate record — the file itself is gone.

## Historical residue: post-promotion (fix 123 era; counts predate r4c, see below)

`final_out/` holds the follow-up tree (probe 2,463 errors / 726 files,
`validation_reports/probe_final_out.json`). CS0053 is 0 there and 0 on the
retained `work/rpc_payload_out` tree (`probe_rpc_payload_out.json`: 10,305 /
1,516, matching the recorded baseline exactly) -- the 222 fix-123-era sites
cleared before this session (likely the accessor-recovery unit), so the
accessibility-honesty lane needs no policy decision. Live lanes: CS0737 done (880 -> 0: private+final+virtual methods with plain
names qualify via the unique directly-listed interface method with the same
name and rendered signature -- async `MoveNext`/`SetStateMachine`, iterator
`MoveNext`; trigger census matched the error count exactly, probe delta is
the sole change, `work/iface_out` + `validation_reports/probe_iface_out.json`);
CS0052 done (308 -> 0: private nested `__StaticArrayInitTypeSize=N` / Mono
`$ArrayType=N` blob structs, always empty, render `internal` -- over-visible
never errors -- with a CS0262 knock-on (28 -> 16: 12 sizes exist as
split-visibility duplicate typedefs, `0x113` vs `0x115`, unified on the
metadata majority; `work/blob_out` + `validation_reports/probe_blob_out.json`);
CS0111 384
(combined-partial duplicate constructors, known do-not-touch: deleting them
would damage the individual assemblies); CS0052 308
(`__StaticArrayInitTypeSize_N` field accessibility); the masked
body-pointer-local layer (needs expression typing first); project wiring.
The complete game is not yet compilable.

## Previous work — fix 123 (collision-aware using/strip; gated + promoted 2026-09-17)

CS0104 triage (140 sites) showed shortening rebinds references two ways:
duplicate short names across imported namespaces (`Hashtable`,
`Object`, `Random`) and heads matching a visible namespace final segment
(`HID.HIDDeviceDescriptor`). `collision_heads` (new in `il2cpp/csharp.py`,
mirroring `rep()`) flags exactly the heads shortening could produce, proven
per file against the metadata short-name table (global-ns rows excluded —
usings win over globals empirically); `strip_namespaces` keeps those full
chains. Generic arguments render full paths at every depth (the `ErrorEventArgs`
bare-arg gap), and explicit *method* qualifiers split before sanitizing
(`IDictionary<TKey,TValue>` kept its commas). Gates: **759 tests** (6 in
`tests/test_review123_collisions.py` — 5 unit + 1 game-backed); strict
rebuild 11,181 files / 113,938 bodies / 0 failures (`work/review123_out`);
parser 0 bad files; direct sweep 116,178 methods / 0 crashes / 0 structural
changes vs fix 122; probe **10,794 → 10,602 (−192)**: CS0104 140→3,
CS0246 43→0, CS0305/CS0308/CS0426/CS0538 →0, CS0535 −13, against CS0053 +21
(accessibility unmasking, characterized above). One golden diff reviewed
(fulldepth args only) before regen; one game-test expectation corrected to
the faithful `System.EventHandler_1<...>` spelling. Reports:
`validation_reports/review123_*`. Promoted 2026-09-17: `final_out/` now
holds `work/review123_out` (11,274 files, aggregate `45711645…3791d3c6`, 0
mismatches; the `bckups/final_out_fix122` copy was removed 2026-09-19, see the
cleanup note above).
Post-promotion parse recheck 0 bad files.

Comparison temps (`obj227 < 6`) are CLOSED with no code change: a full
`.pdata`-extent native scan of `InventoryManager.Update` finds no compare,
test, or arithmetic instruction with immediate 6 anywhere — the literal is
decompiler-synthesized (jump-table/switch-bound recovery), so no width/sign
evidence exists to thread and any numeric cast would invent semantics.
Where a real `cmp reg, nonzero-imm` executes, the existing chain (CMP hint
→ rename classifier → `_decl_type_of` → fix-104 cast) already emits exactly
the desired shape — same VA, other branch: `int num11 =
(int)sub_180001da0(...); if (num11 < 6)`. The remaining work is provenance
for synthesized switch-bound literals, not temp typing.

## Previous work — fix 122 (receiver-proven stub temps; gated + promoted 2026-09-17)

The user's specimen (`object obj228 = sub_...; obj228.SetTrigger("Reload")`)
opened the shared-body/`objN` lane. Triage: two of its three addresses are
unregistered natives (zero candidates — call identity unknowable, only
use-types recoverable); the third is StartCoroutine/StartCoroutine_Auto
(already cast-covered). New rule (`_stub_receiver_decls`, feeding the
existing fix-104 cast machinery): an `object X = sub_(...)` declaration
whose only other mention is one bare `X.Method(literals)` call, resolving
by literal-applicability to exactly one instance non-generic metadata
method (exact arity, or provable defaults; params-array expansion honestly
unmodeled so larger arities without full defaults decline), is retyped to
the owner with a caller-proven cast. Writes, address-takes, ref/out/in,
redeclarations, non-literal args, and accessor-shaped names all decline.
Census: 116 unique-owner sites (game types: StoreManager 30, JSONAccess 7…),
380 non-literal, 195 ambiguous. Ground truth: `UnityEngine.Animator
animator2 = (UnityEngine.Animator)sub_180001d80(...);
animator2.SetTrigger("Reload");` — and the semantic renamer adopts the
proven type for temp names. Gates: **752 tests** (10 new in
`tests/test_review122_receiver_casts.py`); strict rebuild 11,181 files /
113,938 bodies / 0 failures (`work/review122_out`); parser 0 bad files;
direct sweep 116,178 methods / 0 crashes / 0 structural changes vs fix 121
(49 changed bodies, every diff a retype+cast+rename audited file by file);
probe **10,794 → 10,794**: the fix is probe-invisible today because
error-typed/unbound upstream values mask downstream binding (verified: the
fixed shape errors standalone, the region is silent in-tree), so it removes
future CS1061s rather than present ones — zero cost either way. Reports:
`validation_reports/review122_*`; 64 goldens untouched. Promoted 2026-09-17:
`final_out/` now holds `work/review122_out` (11,274 files, aggregate
`3a513e9a…13b49de`, 0 mismatches; the fix-121 tree is kept at
`bckups/final_out_fix121`). Post-promotion parse recheck 0 bad files.

## Previous work — fixes 120 and 121 (nested owner paths + mirror completion; gated + promoted 2026-09-17)

CS0246 triage crowned the nested-qualification gap: the typedef `declaring`
field is -1 top-level and out of range for all 5,719 nested rows, so
`typedef_full`'s owner walk never fired and nested references rendered bare
(`CallbackContext` for `InputAction.CallbackContext`). Owners now resolve
through the forward `nested_types` table inverted once per instance
(`_nested_owner`; top-level `declaring == -1` consumers untouched), with the
outermost namespace on the path. Generic owners distribute instantiation
args outer-first (`List_1<T>.Enumerator`, `Dictionary_2<TKey,
TValue>.KeyCollection`). Nested containers holding mirrored owner params
plus own trailing ones (290 mirror vs 184 independent by census) declare
only the own suffix (`DispatchDelegate(T)` exactly as Valve wrote it;
`ConstraintComparer<K>`), because same-named independence is inexpressible
in C# — proven by names+counts, declined otherwise. Along the way: blob
`__StaticArrayInitTypeSize=`/`$ArrayType=` rewrites match the terminal
segment (48 parse-failing files), reference spellings sanitize per segment
(the guid-braced `PrivateImplementationDetails` owner), and strip keeps
self-shadowed full chains (`HID.HID...`). Gates: **742 tests** (13 in
`tests/test_review120_nested_paths.py` + qualifier/sanitize cases);
strict rebuild 11,181 files / 113,938 bodies / 0 failures
(`work/review121_out`); parser 0 bad files; direct sweep 116,178 methods /
0 crashes / 0 structural changes vs fix 119 (8,081 spelling-only bodies);
probe **13,352 → 10,794 (−2,558)**: CS0246 2,423→43, CS0540 38→0, CS0308
43→4, CS0305 13→4, plus drops across CS0111/CS0146/CS0523/CS0534/CS0535 and
CS0118→0, against CS0053 +6 (accessibility unmasking, characterized), one
documented CS0426 collision cost and CS0234-class silence above. The 6
golden diffs and 2 assertion updates were each reviewed (owner-path
spellings only) before regen. Reports: `validation_reports/review121_*`.
Promoted 2026-09-17: `final_out/` now holds `work/review121_out` (11,274
files, aggregate `b84d8e05…c94253`, 0 mismatches; the fix-119 tree is kept
at `bckups/final_out_fix119`). Post-promotion parse recheck 0 bad files.
(Fix 120 was gated through sweep/tests but held unpromoted when its probe
showed the CS0305 mirror spike; fix 121 completes it — same two-stage
rhythm as 117/118.)

## Previous work — fix 119 (using-feeding qualified spellings; gated + promoted 2026-09-17)

CS0246 triage crowned the using-generation gap: `IntPtr` rendered bare
because `PRIM` carried no namespace (1,076 sites), and `[Serializable]` /
`[SerializeField]` never named one (338/32 sites each). All three now render
qualified pre-strip (`System.IntPtr` / `System.UIntPtr` /
`System.TypedReference`; `[System.Serializable]`; `[UnityEngine.
SerializeField]`), so the tracker imports the namespace and the boundary
strips back to short form — the partial-tree diff is exactly added `using`
lines plus blank separators. Mechanism audit: `type_name` is also the
body-spelling path, so 2,148 lifted bodies changed; tree-wide audit shows
11,167 files identifier-identical, the rest renames plus 14 reflow files of
the known temp-materialization class (traced equivalent); the `_bind` /
`_kill_stale` text-identity gates that select those cascades are
spelling-agnostic within a run. Gates: **727 tests** (5 new in
`tests/test_review119_usings.py`); strict rebuild 11,181 files / 113,938
bodies / 0 failures (`work/review119_out`); parser 0 bad files; direct
sweep 116,178 methods / 0 crashes / 0 structural changes vs fix 118; probe
**15,183 → 13,352 (−1,831)**: CS0246 −1,823, CS0535 −9, no other moves
except the single documented CS0104 ambiguity cost above. Reports:
`validation_reports/review119_*`; 64 goldens untouched. Promoted 2026-09-17:
`final_out/` now holds `work/review119_out` (11,274 files, aggregate
`5855ed65…baf5d`, 0 mismatches; the fix-118 tree is kept at
`bckups/final_out_fix118`). Post-promotion parse recheck 0 bad files.

## Previous work — fix 118 (explicit-qualifier completion; gated + promoted 2026-09-17)

Fix 117's new `_N` references unmasked two explicit-member gaps. First, the
qualifier proof trusted arity-less name strings while the true interface is
the declaring type's tuple: members spelled `IObserver_1<InputRemoting.
Message>` against base `IObserver_1<Message>` (`_iface_qualifier`, unique
tuple match or decline). Second, `sanitize()` ate generic structure inside
qualifiers (`KeyValuePair<TKey, TValue>` → `KeyValuePair<TKey__TValue>`,
`T[]` → `T__`): new structure-aware `sanitize_qualifier` (`il2cpp/names.py`)
sanitizes identifier segments only. Gates: **722 tests** (12 in
`tests/test_review117_arity_spellings.py` — 7 arity + 5 qualifier/sanitize);
strict rebuild 11,181 files / 113,938 bodies / 0 failures
(`work/review118_out`); parser 0 bad files; direct sweep 116,178 methods /
0 crashes / 0 structural changes vs fix 117; probe **15,677 → 15,183
(−307), zero increases**: CS9334 30→0, CS9333→0, CS0540 124→38, plus
knock-on drops. The 38 residual CS0540 are the nested-shadowing family
above, characterized for the next fix. Reports:
`validation_reports/review118_*`; 64 goldens untouched (0 changed bodies).
Promoted 2026-09-17: `final_out/` now holds `work/review118_out` (11,274
files, aggregate `bede44dc…74d418`, 0 mismatches; the fix-117 tree is kept
at `bckups/final_out_fix117`). Post-promotion parse recheck 0 bad files.

## Previous work — fix 117 (generic `_N` reference spellings; gated + promoted 2026-09-17)

CS0115 triage (266 sites) root-caused a declaration/reference convention
split, not wrong override keywords: type declarations spell
`EqualityComparer_1<T>` (fix-113 arity convention) while every reference
spelled `EqualityComparer<byte>`, so derived overrides bound against the
*reference-assembly* base (which has no `IndexOf`) instead of the local one.
`csharp_type_name` (`il2cpp/common.py`) now renders `` `N `` as `_N`, so
references spell the declared identifier; explicit interface qualifiers
(which come from arity-less metadata name strings) recover the suffix
through a (namespace, path, top-level arg-count) typedef proof
(`_arity_qualifier` in `il2cpp/emitter.py`, wired into `method_sig` and
`emit_property`; declines on unknown/ambiguous shapes). Audit surface: 2
`split('<')[0]` uses (both against non-generic names), one `_BACKTICK_RX`
use-site, 0 methods with backticks, 779 generic typedefs.

Provenance (full old-vs-new tree audit, 3,477 changed files): 45,394
arity-insertion tokens; renames from the arity-embedding local renamer
(`list1`→`list11`, `dictionary1`→`dictionary21`; decl↔use consistent, zero
pre-existing collision targets); 18 reflow files (±1–6 lines) of one class —
a `static` generic read materialized into a temp (`object objN =
Span_1<byte>.Slice`) plus renumber cascade, traced semantically identical in
`Convert.TryFromBase64Chars` by old-vs-new direct re-lift; one loop flip
(`while (c)` → header-replay `while (true)`) via the documented `h.stmts`
rule, sound by construction. The 6 golden diffs were each reviewed
(spelling + consistent renames, decl-uniqueness unchanged) before regen;
one stale `Optional<string>` assertion updated to `Optional_1<string>`.

Gates: **717 tests** (7 new in
`tests/test_review117_arity_spellings.py`); strict rebuild 11,181 files /
113,938 bodies / 0 failures (`work/review117_out`); parser 0 bad files;
direct sweep 116,178 methods / 0 crashes / 0 structural changes vs fix 116
(7,275 changed bodies, into_block identical); probe **24,078 → 15,677
(−8,401)**: CS0115 266→0, CS0246 10,337→4,358, CS0535 1,171→191, CS0308
646→49, CS0737 −276, CS0738 259→50, CS0452/CS0453/CS0509/CS8345 →0, with
unmasked CS0540 +4 / CS9334 +3 and single-digit noise elsewhere; CS0501
steady. The mid-gate probe without the qualifier fix read 16,966 (CS0540
+512/CS9334 +148), which scoped exactly the qualifier completion above.
Reports: `validation_reports/review117_*`; goldens regenerated (6 reviewed
bodies, 58 untouched, fingerprints refreshed). Promoted 2026-09-17:
`final_out/` now holds `work/review117_out` (11,274 files, aggregate
`1bd83c61…a46467`, 0 mismatches; the fix-116 tree is kept at
`bckups/final_out_fix116`). Post-promotion parse recheck 0 bad files.

## Previous work — fix 116 (unsafe fields/properties, CS0214 zero; gated + promoted 2026-09-17)

The 517 CS0214 residue classified declaration-only: 465 pointer fields, 52
pointer properties, 0 body lines (the 2 apparent locals are
`[SerializeField]`-prefixed fields). `emit_type` field mods and both
`emit_property` paths now append `unsafe` on `'*'` spellings
(`il2cpp/emitter.py`); all shapes Roslyn-probed, including interface and
explicit-impl properties. Gates: **710 tests** (7 new in
`tests/test_review116_unsafe_members.py`); strict rebuild 11,181 files /
113,938 bodies / 0 failures (`work/review116_out`); parser 0 bad files;
direct sweep 116,178 methods / 0 crashes / 0 structural changes vs fix 115;
probe **24,595 → 24,078, the only delta CS0214 517 → 0**. Body-level
pointer locals (e.g. `NetworkBehaviour` 596) stay silent only through error
cascading — a standalone repro proves the declaration CS0214 masks them, so
a future typing fix will unmask a method-level-`unsafe` lane; nothing to do
until then. Reports: `validation_reports/review116_*`; 64 goldens untouched.
Promoted 2026-09-17: `final_out/` now holds `work/review116_out` (11,274
files, aggregate `8e93363d…9ff462b9`, 0 mismatches; the fix-115 tree is kept
at `bckups/final_out_fix115`). Post-promotion parse recheck 0 bad files.
(Note: the fix-116 promotion run briefly overwrote
`review115_promotion_verification.json` with a stale comparison; restored
from the verified fix-115 values, noted in the file.)

## Previous work — fixes 114 and 115 (dispatch, ctors, unsafe; gated + promoted 2026-09-17)

Corrected CLI MethodAttributes: Virtual=0x40, Final=0x20, NewSlot=0x100,
Abstract=0x400. The old emitter confused these with each other. Methods now
preserve virtual slots, overrides, sealed overrides and abstract overrides.
Final new-slot interface implementations remain ordinary methods; explicit
interface implementations omit access/virtual modifiers. Abstract methods
consistently have no body, even when metadata carries an address. Static
abstract interface members retain their modifiers.

Generic constructors now match their emitted type identifier: Box_1<T> has
Box_1() and static Box_1(), rather than Box(). The metadata census finds
21,410 changed method signatures and 858 changed constructor signatures.
Evidence: validation_reports/review114_declaration_census.json.

Validation: **698 tests pass**, including all 118 fixture tests and a real
Roslyn compilation of generated dispatch/constructor declarations. The Review 83
shared-boolean assertion was stale since fix 110; the prior candidate already
emits proven string equality, and the test now checks those exact conditions.
The 64 frozen method bodies remain unchanged. The strict rebuild was stopped at
the requested wrap-up point after **97,291 bodies with 0 failures**; its partial
candidate is `work/review114_out` and its log was
`validation_reports/review114_build.log` (removed in the 2026-09-19 cleanup). That rebuild never finished, so
fix 114 alone claims no whole-tree result — the Fix 115 gate below rebuilds
the same source completely and supersedes it.

New tools/compile_corpus.py invokes installed Roslyn directly, records a source
inventory digest and diagnostic counts, and saves compressed complete logs.
It merges shared stubs only in temporary storage. This is a single diagnostic
assembly, not verification of project wiring or behavior, and includes some
cross-assembly collisions. Its fix-113 baseline is **34,262 errors**, counted
once per diagnostic. Compare only with the same probe; older build-log totals
can repeat diagnostics and use different compiler references. Its largest
measured groups are missing types/usings (CS0246: 10,337), concrete declarations
without bodies (CS0501: 7,558), pointer declarations outside unsafe contexts
(CS0214: 3,627), and unimplemented abstract/interface members (CS0534: 3,527).

Follow-up (partial, ungated): pointer-signature methods and constructors now
carry `unsafe` (`method_sig`/`ctor_sig` in `il2cpp/emitter.py`, same `'*'`
spelling rule `emit_delegate` already used). Metadata census: 2,564
pointer-signature methods and 82 constructors; ground truth `NodeSwitch`
`@Invoker`s render `protected static unsafe void ...(..., SimulationMessage*
message)`. Partial evidence only: 27 targeted tests (5 new) plus an 87-test
portable subset pass, single-method re-lift of mi 23560 is unchanged, and a
single-file Roslyn probe compiles the new shapes including explicit-interface
`unsafe void IFoo.Bar(byte* p)`. Superseded the same day by the Fix 115 full
gate below (strict rebuild, sweep, probe); pointer fields/properties became
fix 116 above.

CS0501 triage (metadata-only, partial): 9,397 concrete address-less methods —
204 runtime-impl, all delegate members already suppressed through
`emit_delegate`; 8,645 plain managed (iflags 0), including whole
metadata-only types such as `DictionaryLookupTable`2` (all 11 methods
address-less); 520 aggressive-inlining, 28 no-inlining. No blanket `throw`,
`abstract`, `extern`, or `partial` rule is sound without per-method ground
truth (stripped/uninstantiated generics versus real misses), so no code
changed.

Unsafe follow-up, Assembly-CSharp gate (partial, not a full rebuild):
`--only Assembly-CSharp` strict rebuild into `work/partial_unsafe_acs_out`
(490 types, 6,610 bodies, 0 failed, ~67s; `PYTHONHASHSEED=0` — the one
non-unsafe diff in the unseeded run was hash-order noise, byte-identical on
repro). Old-vs-new diff over `work/review114_out/Assembly-CSharp`: 87 files
changed, 518 added lines, every one an `unsafe` insertion, 0 files with any
other change. Single-assembly Roslyn probe
(`validation_reports/partial_unsafe_acs_compile.json`, removed in the
2026-09-19 cleanup): ACS-scope CS0214
falls 518 → 0 (exactly the 518 insertions) and CS0106 199 → 0 (fix-114
explicit-impl rule); CS0501 holds 35 → 35, untouched by design. The 9,196
probe total is dominated by CS0246 scope artifact (8,937: cross-assembly
references are absent from a one-assembly tree), not a regression.

CS0501 tree-wide census (read-only over `work/review113_out`, 11,181 files):
8,926 bare declaration lines = 755 legal `abstract` + ~615 legal `delegate`
+ 3,647 concrete open-generic definitions with no compiled instantiation
(ACS scope: all 35 probe sites are this shape — `Shuffle<T>`,
`ConvertNestedList<T>`, `GetModule<T>`, display-class ctors) + ~3,900
closed concrete without bodies (metadata-only/editor-stripped types such as
`SerializedDictionary` ctors). Concrete-bare minus delegates closes against
the 7,558 diagnostics within noise. No body exists in the binary for any of
these, so no rendering change is sound; the bare signature stays as the
honest marker.

## Fix 115 gate and promotion (2026-09-17, full gate lifted per user call)

Fix 115 is the unsafe-signature follow-up above, built on the fix-114
source. Gates: **703 tests** (698 + 5 new unsafe-signature cases, incl. 118
game fixture tests and the 64 goldens, all live); strict rebuild 11,181
files / 113,938 bodies / 0 failures or fallbacks (`work/review115_out`);
parser 0 bad files; direct sweep 116,178 methods / 0 crashes / 0 structural
changes vs fix 113 (`validation_reports/review115_vs113.json`: 0 changed
bodies — the combined fix-114 + fix-115 delta is declaration-only);
 Roslyn probe **34,262 → 24,595 errors** (−9,667), fully attributed —
CS0106 2,402 → 0, CS0533 226 → 0, CS0534 3,527 → 3, CS1520 797 → 0,
CS0214 3,627 → 517 (residue: pointer fields and body locals only, sampled),
unmasking CS0115 266 / CS0249 121 / CS0507 4; CS0246/CS0501/CS0535/CS0737
unchanged. Reports: `validation_reports/review115_{build.log,sweep.json,
vs113.json,parse.json,compile.json,tests.log}` (build/compile/tests logs and
the vs-compare blob removed in the 2026-09-19 cleanup; sweep/parse JSONs stay
tracked); built tree
`work/review115_out`. The 64 goldens are untouched (0 changed bodies, no
regen needed). Promoted 2026-09-17: `final_out/` now holds
`work/review115_out` (11,274 files — 74 more than the fix-99 tree, exactly
the fix-104 stub files minus the 3 fix-113 orphans; candidate and promoted
aggregate sha256 both
`2379110f106b51f6958d0eb0a3f0c7bdc1a6b0de2a0490ba5612d0e03e9a07a4`, 0
mismatches; the fix-99 tree is kept at `bckups/final_out_fix99`).
Promotion record: `validation_reports/review115_promotion_verification.json`;
post-promotion parse recheck
`validation_reports/review115_recheck_parse_final.json` (11,274 files, 0
bad).

## Previous work — fix 113 (legal type declarations, gated 2026-09-18)

The Roslyn probe's semantic layer is dominated by declaration
shapes, all emitted wrong the same way. `type_decl_line` read
`0x20 & ~0x80` for interfaces — but ECMA mandates abstract+interface
together, so nearly all 636 interfaces rendered as classes (fixing
CS1721/CS0527/CS1722/CS0737 at the root: all four codes go to zero).
Abstract+sealed renders `static partial class` (census: all 1,015
have no instance fields/methods/properties/events, no bases or
interfaces — zero tradeoff). User delegates (616, via MulticastDelegate
parentage) render `delegate R Name(params);` through Invoke (generic
arity mirrors the `List_1<T>` class convention so references match;
.ctor/Invoke/BeginInvoke/EndInvoke suppressed as compiler-provided;
falls back to class rendering if Invoke/fields/props/events/nested
are ever missing/present). Interface members lose access/instance
modifiers (DIM bodies kept under a new `<LangVersion>latest</LangVersion>`
in the csproj template); properties/events propagate accessor
staticness (all-static on the 431/19 absseal ones; mixed would fall
back). Gates: **682 tests (564 portable incl. 6 new in
`tests/test_review113_type_decls.py` + 118 game); direct sweep 116,178 methods / 0 crashes / 0 structural changes vs
fix 112 (0 bodies changed — emitter-only); strict build 11,181 files
/ 113,938 bodies / 0 failures or fallbacks (`work/review113_out`);
parser 0 bad files**. Reports: `validation_reports/review113_sweep.json`,
`review113_vs112.json` (0 changed, 0 structural),
`review113_parse.json`; built tree `work/review113_out`. The 64
goldens are untouched (0 overlapping MIs; fingerprints refreshed).
NOT promoted — `final_out/` still holds the fix-99 tree pending a
human promotion call.

- [x] Fix 113: 2,001 files changed — exactly 1,015 `static`,
  636 `interface`, 615 `delegate` headers (census-exact), plus
  modifier-stripped members; 3 orphaned `__SharedBodyStubs.cs`
  dropped (delegate-suppressed bodies took the only refs).
- [x] Recompile probe: **87,224 → 68,528 instances, 5,461 → 4,097
  files; CS1721/CS0527/CS0418/CS0644/CS1722/CS0708 all go to
  exactly zero** (CS0708 needed the property/event staticness
  follow-through: 900 → 0). ZipEntry.cs (12 delegate-shape errors
  after fix 112) is fully clean.
- [x] Residue is the next program: missing types (CS0246 20.7k:
  usings, nested qualification, open generics, absent types),
  bodiless methods (CS0501 15.1k), unsafe modifiers (CS0214 7.3k),
  unimplemented members (CS0534 7.1k), overrides (CS0533/CS0535),
  ctors (CS1520), overload collisions, ref/out ABI — then the
  unmasked body layer (gotos, definite assignment).

## Previous work — fix 112 (fresh-array bracket repair, gated 2026-09-18)

`new T[N][i]` parses as an invalid rank specifier and
`new T[N](idx)[0]` (single argument, ldelema shape) as an invalid
call (the last 2 parse-failing files). `_fresh_array_brackets`
(new dec text pass) parenthesizes the creation — `(new T[N])[i]`,
`(new T[N])[idx]` — meaning-preserving everywhere (allocation,
size, and index survive verbatim; verified parsing with Roslyn).
Multi-arg calls, bare calls without a deref, and unbalanced spans
decline. Gates: **676 tests (558 portable incl. 8 new in
`tests/test_review112_array_brackets.py` + 118 game); direct sweep
116,178 methods / 0 crashes / 0 structural changes vs fix 111 (181
bodies changed, all line-neutral); strict build 11,184 files /
115,658 bodies / 0 failures or fallbacks (`work/review112_out`);
parser 0 bad files**. Reports: `validation_reports/review112_sweep.json`,
`review112_vs111.json` (181 changed, 0 structural),
`review112_parse.json`; built tree `work/review112_out`. The 64
goldens are untouched (0 overlapping MIs; fingerprints refreshed
with fix 113's). Provenance: 709/709 paired paren insertions, zero
other diff lines. SqlDecimal.cs fully clean; ZipEntry.cs left 12
delegate-shape errors for fix 113 (which cleared them).

## Previous work — fix 111 (C# keyword escaping, gated 2026-09-18)

The Roslyn whole-tree compile probe (new methodology: `dotnet
build` over all 11,184 files as one project, `__SharedBodyStubs`
deduplicated probe-only) showed 10,778 errors collapsing to root
breaks in just 48 files — 44 of them one class: reserved words as
identifiers (`.namespace` ×194, `.in` ×5, `.interface` ×3, field
`string interface`), which tree-sitter parses but Roslyn rejects
(CS1001 + cascades). The fix routes every metadata-name declaration
(type headers, enum members, methods incl. explicit-`IFoo.Bar`,
fields, events, ctors, properties) through the existing
`safe_ident` (trailing-underscore convention, already used for
params), and adds `_escape_keywords` (dec text pass after the stub
casts): a reserved word after `.`/`->` is never a keyword use, so
masked-line rewriting is exact; strings/comments never match and
already-escaped names never re-match. `nameof()` emission tracks the
escaped spelling. Metadata census: 6 keyword fields, 1,283
keyword params (all `object`/`method`-style delegate plumbing,
already consistent), zero keyword typedefs/methods/namespaces.
Gates: **668 tests (550 portable incl. 6 new in
`tests/test_review111_keywords.py` + 118 game); direct sweep
116,178 methods / 0 crashes / 0 structural changes vs fix 110 (81
bodies changed, all line-neutral); strict build 11,184 files /
115,658 bodies / 0 failures or fallbacks (`work/review111_out`);
parser 0 bad files**. Reports: `validation_reports/review111_sweep.json`,
`review111_vs110.json` (81 changed, 0 structural),
`review111_parse.json`; built tree `work/review111_out`. The 64
goldens are untouched (0 overlapping MIs, no regen needed). NOT
promoted — `final_out/` still holds the fix-99 tree pending a human
promotion call.

- [x] Fix 111: residual `(\.|->)keyword` census is ZERO tree-wide
  (masked scan, 11,184 files); decl/uses agree exactly
  (`private bool async;` + all 8 `this.async_` uses verified in
  FileStream.cs).
- [x] Recompile probe: **10,778 → 40 error instances, 48 → 2
  files**. Everything keyword-related is gone; the survivors are
  the `new X[N](args)` / `new X[N][i]` mistranslation family
  (ZipEntry.cs, SqlDecimal.cs) — fix 112.
- [x] Also proven by probe: into-block `goto` is CS0159-hard-illegal
  (labels are block-scoped for goto; fails with no decls and into
  `try` alike) — no cleverness at the goto level, only
  tail-duplication/hoisting work counts toward compilation.

### Next priorities (fix 111 follow-ups)

1. **Fix 112: `new X[N][i]` 2D-index mistranslation** (751 lines,
   e.g. `new char[1][0x0] = 32`) **and `new X[N](args)`**
   indirect-call misrender (30 lines). Precise lifter shapes.
2. **Semantic layer** (surfaced by the probe once parse falls):
   definite assignment, conversions, duplicate locals — measure
   after fix 112; the goto program (8,071 sites) feeds
   CS0165-class errors.
3. **Project wiring**: per-assembly `.csproj` files exist but
   carry no cross-assembly references (the probe sidestepped this
   with one project).
4. Receiver-driven instance twins, call/indexer `==` operands,
   duplication residue, 447 shared tails — all stand.

## Previous work — fix 110 (unanimous == / != shared calls fold to operators, gated 2026-09-18)

Six shared addresses (~2,726 uses) carry only static 2-parameter bool
`op_Equality` candidates (`Equals` twins allowed) or unanimous
`op_Inequality` (census: `0x181af7520` String 2,282,
`0x18061a510` 17-cand != 201, plus four small ones; the 252-cand
mixed `0x1807ee180` and 1,806-cand `0x18063ac90` decline by
non-unanimity). Address-sharing proves one machine code, so the
operator spelling is behavior-exact with no owner attribution — but
each operand must still prove the exact same operand type for some
candidate, or `a == b` could bind a different overload (notably
`object.==`/ReferenceEquals for object-typed temps). `_eq_addr_info`
(new in `il2cpp/dec/highlevel.py`, cached) proves unanimity (all
`method` candidates, static, 2 params, bool return, GPR-safe param
kinds per matched pair — floats ride XMM, structs carry ABI risk);
`_eq_operand_spelling` proves operand types (string/int literals,
uniquely-declared temps via `_stub_assign_types`, `this`/temp/
`typeof` member paths through metadata fields with
instance/static/literal discipline); `_shared_equality_ops` (wired
between the fence pass and the stub casts, so no `(bool)` cast is
ever synthesized for a rewritten site) folds proven-bool positions
only (whole if/while/do-while tests, top-level &&/|| operands,
`!`-chains, `bool` decl RHS, bool returns; ternary arms, call
arguments, bare statements, and non-bool decls decline). Integer
literals self-type by C# literal rules. Along the way the legacy
bare-`typeof(` check was found to also match `typeof(X).Get()`
(zero corpus sites, closed with `_fence_bare_typeof` in fix 109).
Gates: **662 tests (544 portable incl. ~29 new in
`tests/test_review110_equality_ops.py` + 118 game, 64 goldens
verified live against fixtures); direct sweep 116,178 methods / 0
crashes / 0 structural changes vs fix 109 (312 bodies changed, all
line-neutral); strict build 11,184 files / 115,658 bodies / 0
failures or fallbacks (`work/review110_out`); parser 0 bad files**.
Reports: `validation_reports/review110_sweep.json`,
`review110_vs109.json` (312 changed, 0 structural),
`review110_parse.json`; built tree `work/review110_out`. The 64
goldens were regenerated after individual review of the single
overlapping diff (mi 15013 `set_columnName`: the `!((bool)sub_…)`
condition becomes `this.m_ColumnName != value` — private string
field plus setter string param, exact). NOT promoted — `final_out/`
still holds the fix-99 tree pending a human promotion call.

- [x] Fix 110: ~846 new `==`/`!=` lines (per-method normalized
  multiset audit: the ONLY added lines tree-wide are operators plus
  3 `using System.Threading;`; every removed line is a
  shared-equality call, a dead copy/decl cascade, a dropped stub
  entry, or brace realignment). Ground truth: 3-level field paths
  rewrite (`this.playerInput.m_CurrentActionMap.m_Name ==
  "Interrogation"`) while property twins stay
  (`this.playerInput.currentControlScheme` — getters are calls).
- [x] Residue, all verified declined by design: property/call/
  indexer operands (expression typing open), object-vs-string mixed
  pairs (would bind ReferenceEquals), non-bool positions,
  `0x180434690`-class unregistered dispatch blobs (8,046 uses —
  decoded: jmp thunk onto an unregistered virtual-dispatch
  routine; `0x180002210/380` are interface search loops into the
  `0x18043DC60` slow path — no honest name exists for any of
  them, shapes recorded, `sub_` rendering stays).
- [x] Bugs found by tests while building: an operator-precedence
  slip in the region guard, a trim-based operand matcher that ate
  the call's own close paren, an unreachable typeof branch, and a
  head-gate rejecting `!`/parens before the operand path ran.

### Next priorities (fix 110 follow-ups)

1. **Call/indexer operands for ==** (`ToLower()`,
   `playerIds[i]`): needs expression return-type/element-type
   proof — the general expression-typing problem (fix-105 item 1).
2. **Receiver-driven instance twins** (`TaskAwaiter.GetResult`
   vs `ConfiguredTaskAwaiter.GetResult`, 529 uses; 367
   multi-owner-instance addresses, 3,579 uses): exact receiver
   type proof at lifter level, never a guess.
3. **Unregistered dispatch blobs** (above): naming needs a
   registered/exported identity that does not exist; revisit only
   with new ground truth.
4. **Duplication residue** (~2.7k both-sides-unknown branches),
   **447 remaining shared tails**, **8,067 into-block gotos**,
   Review 87 lists — all stand.

## Previous work — fix 109 (single-level typeof-member fence args, gated 2026-09-18)

Of 151 remaining fence sites, 127 have only plain or
`typeof(X).Member` arguments (census over the fix-108 tree: all 140
typeof-member args are single-level static accesses on hot framework
types — Encoding, TraceInternal, Socket, Uri, Xml*, RegistryKey…).
`_fence_trivial_arg` (in `il2cpp/dec/highlevel.py`) now accepts
exactly `typeof(X).Member` via `_fence_typeof_member` (balanced-paren
scan in `_fence_typeof_end`, one dotted name, checked on masked text
so quoted text can never shape-match). Soundness: no null dereference
is possible (static access only — strictly fewer load effects than
the already-shipped `obj.f` chains), no calls/indexers/further
levels; the tempering precedent is fix 72d's `_PURE_LOAD_RX`, which
already defines typeof-member chains as pure loads for DCE (fix 109
stays on the conservative single-level subset: zero multi-level sites
observed). Along the way the legacy bare-`typeof(`-prefix check was
tightened to whole-string balanced (`_fence_bare_typeof`): it also
matched `typeof(X).Get()`, silently dropping a call (zero corpus
sites ever matched that shape — verified over the pre-fence tree —
but the hole was real; regression-tested). Gates: **639 tests (521
portable incl. 16 new in `tests/test_review109_typeof_args.py` — one
fix-107 expectation corrected for the tightened check — + 118 game);
direct sweep 116,178 methods / 0 crashes / 0 structural changes vs
fix 108 (76 bodies changed, net -335 lines); strict build 11,184
files / 115,658 bodies / 0 failures or fallbacks
(`work/review109_out`); parser 0 bad files**. Reports:
`validation_reports/review109_sweep.json`,
`review109_vs108.json` (76 changed, 0 structural),
`review109_parse.json`; built tree `work/review109_out`. The 64
goldens are untouched (0 overlapping MIs, no regen needed). NOT
promoted — `final_out/` still holds the fix-99 tree pending a human
promotion call.

- [x] Fix 109: ~131 new `Thread.MemoryBarrier()` lines (per-method
  normalized multiset audit: the ONLY added lines tree-wide are
  barriers + 3 `using System.Threading;`; every removed line is a
  fence decl, a dead copy/decl cascade, a dropped
  `0x1804355f0` stub entry, a pure-load decl
  (`getClass()`/`typeof`, per `_PURE_LOAD_RX` doctrine), or brace
  realignment). `sub_1804355f0` falls 159 → 25 lines.
- [x] Residue, all verified declined by design (17 decls + 8 stub
  defs): pointer arithmetic/deref (`(p + 0x88)`,
  `((byte*)obj7 + 0x0)[0]` — 9 sites), integer arithmetic
  (`*`, `>>`, `+` — 5 sites; temp-name typing is not purity
  proof), call args (`obj.getClass()` — pure per doctrine but
  call-shaped; needs a `_PURE_LOAD_RX`-consistent arg rule),
  live-temp plain/zero-arg sites.

### Next priorities (fix 109 follow-ups)

1. **Call-shaped pure args** (`obj.getClass()` and friends):
   align `_fence_trivial_arg` with `_PURE_LOAD_RX` (member chains,
   no calls/Indexers) — the doctrine already exists, needs its own
   gate.
2. **Other top unregistered VAs** (thunk finals,
   interface-dispatch twins from the fix-104 list): native
   structural proof on the fence precedent, never a name guess.
3. **Duplication residue with degraded conditions** (~2.7k
   both-sides-unknown branches, fix-106 list), **447 remaining
   shared tails**, **8,067 into-block gotos**, Review 87 lists —
   all stand.

## Previous work — fix 108 (scope-aware deadness for fence-called temps, gated 2026-09-17)

Fix 107's method-wide liveness treated every same-name mention as a
read, so one colliding scratch temp (sibling scopes re-declare: fix
97c) pinned all of them. `_fence_temp_dead_scoped` (new in
`il2cpp/dec/highlevel.py`, OR-ed with the fix-107 check so nothing it
rewrote can regress) walks forward from the fence declaration at brace
depth d0 over masked lines: a same-block `T nm = ...` rebinds the temp
away outright, a nested declaration or foreach/catch binder shadows its
subtree (depths from `_fence_line_depths`, pruned as blocks close),
outer-scope declarations are different variables, and outer mentions,
unplaceable brace-mixed mentions, initializers reading an outer `nm`,
and any depth anomaly decline exactly as before. `_fence_redecl_of`
reuses `_STUB_DECL_RX` (with the `_STUB_KEYWORDS` guard, so
`return x = ...` never counts) plus the foreach/catch binder regexes.
Gates: **633 tests (515 portable incl. 15 new — 14 in
`tests/test_review108_scoped_fence.py`, one split out of the flipped
fix-107 dup-temp expectation — + 118 game); direct sweep 116,178
methods / 0 crashes / 0 structural changes vs fix 107 (8 bodies
changed, net -96 lines); strict build 11,184 files / 115,658 bodies /
0 failures or fallbacks (`work/review108_out`); parser 0 bad files**.
Reports: `validation_reports/review108_sweep.json`,
`review108_vs107.json` (8 changed, 0 structural),
`review108_parse.json`; built tree `work/review108_out`. The 64
goldens are untouched (0 overlapping MIs, no regen needed). NOT
promoted — `final_out/` still holds the fix-99 tree pending a human
promotion call.

- [x] Fix 108: 23 new `Thread.MemoryBarrier()` lines;
  `sub_1804355f0` falls 185 → 159 lines (8 stub defs + 151 decls
  remain). Of 8 changed methods 6 are line-neutral, 2 shrink
  (`Task.Dispose` -13, `ReaderWriterLockSlim.
  TryEnterUpgradeableReadLockCore` -83) through the same honest DCE
  cascade as fix 107 (orphaned copy chains, one `using static`
  per newly-unreferenced assembly). Ground truth: the
  `FusionNetworkManager` colliding-`obj13` sites rewrite; the
  `ReaderWriterLockSlim` `if`-arm fence rewrites while its
  genuinely-live `else`-arm twin stays.
- [x] Refinement found by probe (single-method re-lift of mi
  103865): an outer-scope re-declaration is a different variable and
  no longer declines the site; decided by reading all five `obj84`
  decls' fates, with a dedicated regression test.
- [x] Residue, all verified declined by design: genuinely-read
  temps, effectful-argument sites (out of scope — the pass never
  touched argument rules), `using`-var/`is`-pattern rebinds,
  mid-line-brace placements.

### Next priorities (fix 108 follow-ups)

1. **Effectful-argument fence sites** (`sub_1804355f0(Foo(), ...)`
   with dead temps): needs call-effect analysis, never blind
   dropping.
2. **Other top unregistered VAs** (thunk finals,
   interface-dispatch twins from the fix-104 list): native
   structural proof on the fence precedent, never a name guess.
3. **Duplication residue with degraded conditions** (~2.7k
   both-sides-unknown branches, fix-106 list), **447 remaining
   shared tails**, **8,067 into-block gotos**, Review 87 lists —
   all stand.

## Previous work — fix 107 (proved fence-thunk calls render Thread.MemoryBarrier(), gated 2026-09-17)

`lock or dword ptr [rsp],0; ret` is the full barrier MSVC emits where the
source calls `Thread.MemoryBarrier`, reached directly or through a short
`jmp` thunk (`0x1804355f0`, the fix-104 follow-up membarrier suspect —
1,465 sites). `_is_fence_body` (new in `il2cpp/lifter/state.py`) proves
exactly that shape: locked `OR`, RSP base, zero displacement, dword
width, zero immediate (both `0x83` and `0x81` encodings), `ret`
terminating the extent; registered/exported/non-exec/unreadable targets
decline. `_fence_target` follows the thunk (itself or <=3 jmp hops),
memoized, never a hardcoded address. `_fence_void_calls` (new in
`il2cpp/dec/highlevel.py`, wired in `il2cpp/dec/structure.py` after the
delegate fold, before the stub casts) rewrites only positions that need
no value: bare statements, void `; return;` tails (split in two), and
declarations whose temp is dead method-wide. Every argument must be
side-effect-free (plain temps/fields, literals, typeof, strings);
conditions, value returns, live temps, and `Thread.MemoryBarrier` itself
keep today's rendering. Gates: **618 tests (500 portable incl. 12 new
in `tests/test_review107_fence_calls.py` + 118 game); direct sweep
116,178 methods / 0 crashes / 0 structural changes vs fix 106b (544
bodies changed, net -2,202 lines); strict build 11,184 files / 115,658
bodies / 0 failures or fallbacks (`work/review107_out`); parser 0 bad
files**. Reports: `validation_reports/review107_sweep.json`,
`review107_vs106b.json` (544 changed, 0 structural),
`review107_parse.json`; built tree `work/review107_out`. The 64
goldens are untouched (0 overlapping MIs, no regen needed). NOT
promoted — `final_out/` still holds the fix-99 tree pending a human
promotion call.

- [x] Fix 107: 1,279 `Thread.MemoryBarrier()` lines (3 pre-existing
  resolved calls + 1,276 rewrites); `sub_1804355f0` falls 1,465 → 185
  lines. Of 544 changed methods 386 are line-neutral, 157 shrink
  (dead-decl plus the honest DCE cascade its orphaned copies allow),
  1 grows by design (bare `...; return;` splits in two:
  `Socket.Connect`). Ground truth: `Thread.MemoryBarrier`'s own body
  (RVA 0x1D1F380) is one call to `0x1804429c0` and is deliberately NOT
  rewritten (self-guard); `Fusion.AtomicInt`'s seven members drop
  their dead `object objN = sub_1804355f0(...)` decls and the
  now-unused `using static __SharedBodyStubs;`.
- [x] Residue, all verified declined by design: 174 decls whose temp
  is live or textually collides with a reused scratch temp later in
  the method (safe-miss direction — e.g. `FusionNetworkManager`
  `obj13` reused as `_StartGame_d__58`), 9 `__SharedBodyStubs`
  definitions that must stay, effectful-arg and value-position sites.
- [x] into_block gotos identical 8,071 (both sweeps), parse re-gated
  on the built tree.

### Next priorities (fix 107 follow-ups)

1. **Remaining `sub_1804355f0` residue above** (live-temp value
   positions): needs value-proof the fence returns nothing at the
   call site, never deletion of a live temp.
2. **Other top unregistered VAs** (thunk finals, interface-dispatch
   twins from the fix-104 list): each needs native structural proof
   on the sqrt-wrapper/fence precedent, never a name guess.
3. **Duplication residue with degraded conditions** (~2.7k
   both-sides-unknown branches, fix-106 list), **one-side-unknown
   comparisons** (~700+), **447 remaining shared tails**, **8,067
   into-block gotos**, Review 87 lists — all stand.

## Previous work — fix 106 (parity-jump NaN fold drops literal arms, gated 2026-09-16)

`ucomiss` + `jp` rendered `IsNaN(a) || IsNaN(b)` even when one side is
a constant (`IsNaN(0f)` — provably false, 665 sites). No numeric
literal spelling denotes NaN, so `_is_non_nan_literal` (new in
`il2cpp/x64.py`, reusing `_int_lit` plus finite-float parsing) drops
such arms in `flag_cond`; the `x != x` idiom and unknown/nullary
operands are untouched, and all-constant pairs decline as before.
Gates: **606 tests (598 + 8 new in
`tests/test_review106_float_parity.py`); direct sweep 116,178 methods
/ 0 crashes / 0 structural changes vs fix 105 (294 bodies changed);
strict build 11,184 files / 115,658 bodies / 0 failures or fallbacks
(`work/review106_out`); parser 0 bad files**. Reports:
`validation_reports/review106_sweep.json`, `review106_vs105.json`
(294 changed, 0 structural), `review106_parse.json`; built tree
`work/review106_out`. The 64 goldens were regenerated after individual
review of the single diff (`DateTimeConverter.ConvertTo`, double
width). NOT promoted — `final_out/` still holds the fix-99 tree
pending a human promotion call.

- [x] Fix 106: 665 literal arms dropped in 144 files (full tree
  audit, 0 unexplained). The single flagged hunk hand-verified
  correct: the arm was a literal at lift time, bound to a temp only
  later (`object obj1 = 1.79…e+308d` feeding a `comisd`).
  `IsNaN(<const>)` falls 665 → 0 (4,968 live-value arms remain).
- [x] Fix 106b: first-char guard (an `inf`-spelled identifier can
  never be taken for a literal). Zero-diff proof on this corpus:
  direct sweep 0/116,178 changed vs fix 106, rebuilt tree
  byte-identical across all 11,184 files (`work/review106b_out`),
  parse re-gated. Reports: `review106b_sweep.json`,
  `review106b_vs106.json`, `review106b_parse.json`.
- [x] Ground truth: `AudioVolumeSliders.SetMusicVolumeInternal` —
  native `ucomiss; jp; jne` to one target; the `IsNaN(0f)` arm is
  gone (the surviving `unknown != unknown` duplication residue is a
  separate structuring matter, below).

### Next priorities (fix 106 follow-ups)

1. **Duplication residue with degraded conditions** (~2.7k
   both-sides-unknown branches with sibling-identical bodies, e.g.
   `else if (unknown != unknown)`): needs _seq/fold-level proof
   (never delete — an unprovable condition can't lose its arm).
2. **One-side-unknown comparisons** (~700+), unbound decls/arithmetic
   (`object obj17 = unknown;`), **honest names** for the top
   unregistered VAs (thunk finals, membarrier, interface-dispatch
   twins), **447 remaining shared tails**, **8,067 into-block gotos**,
   Review 87 lists — all stand.

## Previous work — fix 105 (ternary-condition casts, arm leniency, do-while, gated 2026-09-16)

Same caller-proven rule, one level deeper: a sub_ call in a ternary
CONDITION proves `bool` there (arms keep the line's type), arms without
calls pass through instead of vetoing the line, and `} while (...)`
proves `bool` like `if`/`while`. `== null`, `&&`/`||`, arithmetic and
call-nested conditions still decline whole-line, correctly. Gates:
**598 tests (22-case stub file extended: ternary conds, arm leniency,
do-while); direct sweep 116,178 methods / 0 crashes / 0 structural
changes vs fix 104 (47 bodies changed); strict build 11,184 files /
115,658 bodies / 0 failures or fallbacks (`work/review105_out`);
parser 0 bad files**. Reports: `validation_reports/review105_sweep.json`,
`review105_vs104.json` (47 changed, 0 structural),
`review105_parse.json`; built tree `work/review105_out`. The 64
goldens are untouched (0 overlapping MIs, no regen needed). NOT
promoted — `final_out/` still holds the fix-99 tree pending a human
promotion call.

- [x] Fix 105: 59 cast lines in 42 files, every one a cast-only swap
  at identical indent, 0 suspicious casts (full tree audit).
  Ground truth: `string text4 = (bool)sub_Equals(...) ?
  string.Format(...) : ...`, `float real22 = !((bool)sub_...(304)) ?
  ...`, `Object object1 = (bool)sub_...(type5, ...) ? ... : ...`.
- [x] Returns proven COMPLETE: all 99 bare `return sub_` lines sit in
  void/object methods (pointer returns excluded by design); the 12
  apparent counterexamples were property/nested-class misattributions
  in the audit scaffolding, each verified by hand.

### Next priorities (fix 105 follow-ups)

1. **Operator-nested bool positions** (`&&`/`||` operands,
   `== <lit>` with numeric proof, ternary-in-ternary conds):
   needs per-operator expression typing.
2. **Byref/pointer arguments** into stubs (`&` address-of, `void*`
   params); **honest names** for the top unregistered VAs (thunk
   finals, membarrier, interface-dispatch twins); **447 remaining
   shared tails** (10 via the `this`-rule), **8,067 into-block
   gotos**, Review 87 noreturn-EH/leftover lists — all stand.

## Previous work — fix 104 (object stubs for unresolved sub_ + caller casts, gated 2026-09-16)

53,984 `sub_X(...)` references pointed at methods declared nowhere
(2,687 distinct VAs, 0 definitions tree-wide). The emitter now writes
one global `__SharedBodyStubs` class per assembly (`internal static
object sub_X(params object[] args)`, throwing, with per-VA owner
comments) plus `using static __SharedBodyStubs;` per referencing file,
and a late dec pass (`_shared_stub_casts` in `il2cpp/dec/highlevel.py`,
after the delegate fold) inserts caller-proven `(T)` casts: decl TYPE
(83% of sites), whole-condition `bool`, method return (`void` splits
to call-then-return), unique-mapped plain assigns. Only direct value
positions rewrite (root, ternary arms with sub_-free conditions,
`!`-chains, one paren layer); nested args keep the object spelling;
real metadata `sub_<hex>` names never stub or cast. Gates: **598
tests (576 + 22 new in `tests/test_review104_shared_stubs.py`; 4
review83 spellings updated, behaviors intact); direct sweep 116,178
methods / 0 crashes / 0 structural changes vs fix 103 (7,096 bodies
changed); strict build 11,184 files (11,107 + 77 stub files) /
115,658 bodies / 0 failures or fallbacks (`work/review104_out`);
parser 0 bad files**. Reports: `validation_reports/review104_sweep.json`,
`review104_vs103.json` (7,096 changed, 0 structural),
`review104_parse.json`; built tree `work/review104_out`. The 64
goldens were regenerated after individual review of all 5 diffs (each
exactly a caller-proven cast). NOT promoted — `final_out/` still holds
the fix-99 tree pending a human promotion call.

- [x] Fix 104: 12,716 cast lines (8,584 decl + 1,319 return + 2,544
  conditions + 269 assigns), every cast type proven against its own
  line/method/metadata (decl casts equal their decl, conditions are
  `(bool)`, returns match file signatures and metadata sharer sets,
  assigns match unique decl maps); 3,627 usings; 77 stub files;
  0 void splits left (fix 95 owned them), 0 unexplained hunks.
  Hardening along the way: `\x01` mask alphabet for comments (104c),
  string-aware balanced spans, chained-assign shape proven
  unmatchable so its guards were removed (104e).
- [x] Residue, all verified declined by design: `&`/pointer args
  (~9k, need byref recovery — the method now resolves, the argument
  still doesn't), nested-expression positions (~2.6k conditions with
  calls under operators, `is`/`as`, `??`), untyped sources.
- [x] Next honest-naming targets identified (not attempted): the top
  unregistered VAs are analyzable natives — `0x180434690` (8,046
  uses) is a `jmp` thunk onto `0x180479F80`, `0x1804355f0` (1,449) a
  thunk onto a `lock or [rsp],0` memory barrier, `0x180002210` /
  `0x180002380` (~5,700) near-identical interface-dispatch search
  loops, plus `0x18043dc60`, `0x18043e360`, `0x1804346a0`. Each needs
  native structural proof (sqrt-wrapper precedent), never a name
  guess. A generic `<T>` stub was rejected (C# never infers from
  return position); casts express caller-side need and stay valid if
  a VA later resolves honestly.

### Next priorities (fix 104 follow-ups)

1. **Condition/nested-expression casts** (`&&`/`||` operands,
   `== <lit>` comparisons, ternary conditions, `is`/`as` left alone
   correctly): needs expression-type analysis per operator.
2. **Byref/pointer arguments** into stubs; **honest names** for the
   top unregistered VAs above; **447 remaining shared tails** (10 via
   the `this`-rule), **8,067 into-block gotos**, Review 87
   noreturn-EH/leftover lists — all stand.

## Previous work — fix 103 (native-width INDEXED raw-store lvalues, gated 2026-09-16)

Same display-only rule as fix 102, extended to the indexed raw branch
(`base + idx*scale + disp`): the index/scale pair is recorded in
`_mem_lvalue` and the display mirrors the raw branch's own `_term_up`
construction exactly, so output is identical modulo the cast
(verified `_unsafify` fixpoints, incl. composite and byte*-read
indices). Gates: **576 tests (571 + 5 new indexed cases in
`tests/test_review102_raw_store_widths.py`); direct sweep 116,178
methods / 0 crashes / 0 structural changes vs fix 102 (478 bodies
changed); strict build 11,107 files / 115,658 bodies / 0 failures or
fallbacks (`work/review103_out`); parser 0 bad files**. Reports:
`validation_reports/review103_sweep.json`, `review103_vs102.json`
(478 changed, 0 structural), `review103_parse.json`; built tree
`work/review103_out`. The 64 goldens were regenerated after individual
review of the single diff (`ViscosityVorticityJob.Execute`: indexed
`inc dword` RMW → `int*`; its untyped `mov`-triple sibling correctly
stays byte*). NOT promoted — `final_out/` still holds the fix-99 tree
pending a human promotion call.

- [x] Fix 103: 1,287 widened lines in 276 files, every one a
  cast-only swap at identical indent (full tree audit, 0 unexplained,
  0 added, 0 dropped). Out-of-range literal stores fall 189 → 118;
  byte* stores overall 3,579 → 3,205.
- [x] Residue after fix 103 (each verified declined by design):
  untyped register sources (add-expr `READ + 1` with unknown type),
  `__static_fields` blobs, reference/array/`new` RHS, wide source in
  narrow store, width-1 stores of non-byte values (unencodable
  natively — the value proves a wider write elsewhere).

### Next priorities (fix 103 follow-ups)

1. **Untyped register sources** (expression-typed `READ op LIT`
   values): needs expression type inference, not spelling guesses.
2. **Wide-source-in-narrow-store** and **reference stores through raw
   pointers**: both need field-type recovery.
3. **447 remaining shared tails** (receiver `this`-rule scoped at 10
   `MemberwiseClone` sites), **8,067 into-block gotos**, Review 87
   noreturn-EH/leftover lists — all stand.

## Previous work — fix 102 (native-width raw-store lvalues, gated 2026-09-16)

A raw `*(base + disp)` store lvalue rendered `((byte*)base + disp)[0]`,
which fails to compile whenever the stored value is not a byte (1,524
out-of-range literals tree-wide, plus mistyped variables). The native
width is ground truth from the store instruction, so the statement now
spells a same-width cast (`_wide_src_cast`/`_wide_rmw_cast` +
`_wide_store_disp`/`_wide_rmw_disp` in `il2cpp/lifter/insn.py`, parts
recorded in `_mem_lvalue`). Only the emitted statement spells the
width — kills, slots, barriers and twin dedup keep the raw text; the
barrier twin still renders raw, bridged by `_canon_wide_cast` in
`_norm_twin` (`il2cpp/text.py`); the `unsafe` detector covers all
pointer casts (`il2cpp/dec/textpass.py`). Gates: **571 tests (544 + 27
new in `tests/test_review102_raw_store_widths.py`, incl. end-to-end
`_write_mem`/`_rmw_mem` and an updated packed-lane spelling in
`tests/test_game_review81.py`); direct sweep 116,178 methods / 0
crashes / 0 structural changes vs fix 101 (9,269 bodies changed);
strict build 11,107 files / 115,658 bodies / 0 failures or fallbacks
(`work/review102_out`); parser 0 bad files**. Reports:
`validation_reports/review102_sweep.json`, `review102_vs101.json`
(9,269 changed, 0 structural), `review102_parse.json`; built tree
`work/review102_out`. The 64 goldens were regenerated after individual
review of all 4 diffs (each exactly a width improvement:
`GetChars`, `Rpc_CMD_Heal`, `uint3x3.op_Explicit`, `Finalize`).
NOT promoted — `final_out/` still holds the fix-99 tree pending a
human promotion call.

- [x] Fix 102: integer literals pick signedness by fit (signed first),
  float literals keep their suffixed width (`f`→float, `d`/bare→
  double; fix 102b), register sources are accepted only when the
  source type's size equals the native width so every rendered byte is
  value-determined (a narrower source would leave upper bytes
  unexplained — e.g. a long in a dword store stays honest). RMW keeps
  result unity (`int`/`long`/`uint`/`ulong`/`float`/`double` only,
  width 4/8). Declines on unknown/reference/enum/bool sources,
  indexed stores, `__static_fields` blobs (19 sites, all compiling —
  keeps the sfblob twin machinery byte-identical), and un fitting
  values/widths.
- [x] Fix 102c: `_field_expr`'s miss over a dotted base returned the
  raw text through the field branch, bypassing width recording
  (`this.ropeRenderer + 0x54`, `this.heap[0x0] + 0x22`, ...). The
  exact-passthrough spelling now records the identical parts at true
  instruction width; returned text is byte-identical either way.
- [x] Provenance verified on the built trees (11,107 files, inventory
  identical): 25,765 widened lines in 1,820 files, every one a
  cast-only swap at identical indent; +1 honest line (`Decimal.Abs`:
  a 16-byte struct copy plus a dword flags fixup previously
  accidentally deduped to one line — verified against native);
  3 honest ternary unfolds (one arm widened while a genuinely
  different-width sibling arm stayed byte* — merging them would be the
  bug); 0 unexplained changes. Out-of-range literal stores fall
  1,524 → 189 (residue: indexed fills, untyped registers,
  wide-in-narrow, `__static_fields` — each verified declined by
  design, modulo comparison/indexed census false positives).
- [x] Ground truth: `mov dword [rbx],0FFFFFFFEh` → `((uint*)num1 +
  0x0)[0] = 4294967294;`, `movss` float lanes → `((float*)obj4 +
  0x4)[0] = ...` (review81 proof intact: 4 Sqrt, no helper, no
  unknown), `mov word [x],0FFFFh` → `((ushort*)...)[0] = 65535;` —
  full cases in the test file.

### Next priorities (fix 102 follow-ups)

1. **Indexed raw stores** (`base + idx*scale + disp`, e.g. float-1.0
   array fills): same helper extends naturally, needs its own gate.
2. **Untyped register sources** (`void*` params, untyped slots) and
   **wide-source-in-narrow-store** (long into dword field): both need
   field-type recovery, not spelling guesses.
3. **Reference/array/`new` RHS** through raw pointers: barrier and
   field-recovery territory, never a pointer cast.
4. **447 remaining shared tails** (fix 100 list stands — receiver
   `this`-rule scoped at 10 `MemberwiseClone` sites), **8,067
   into-block gotos**, Review 87 noreturn-EH/leftover lists — all
   stand.

## Previous work — fix 101 (bare-param declaration hints close over `new` RHS, gated 2026-09-16)

A tracked hint that is one bare VAR/MVAR (`T`, `T1`, `TValue` —
top-level 0x13/0x1e with a matching spelling, openness proved
structurally by `_type_has_var`) names no type at all, while the same
line's `new ObiPinConstraintsBatch()` / `new List<int>()` is the exact
closed allocation identity (`_bare_closed_new_type` +
`_bare_new_rhs_type` in `il2cpp/dec/highlevel.py`, wired into
`_decl_type_of` after the fix-98 same-base path). `T x = new C(...)`
never compiles under any binding of `T`, so no compiling method can
regress. Gates: **544 tests (526 + 18 new in
`tests/test_review101_bare_t_decls.py`); direct sweep 116,178 methods /
0 crashes / 0 structural changes vs fix 100 (234 bodies changed, all
line-neutral); strict build 11,107 files / 115,658 bodies / 0 failures
or fallbacks (`work/review101_out`); parser 0 bad files**. Reports:
`validation_reports/review101_sweep.json`, `review101_vs100.json` (234
changed, 0 structural), `review101_parse.json`; built tree
`work/review101_out`. The 64 goldens are untouched (0 overlapping MIs,
no regen needed). NOT promoted — `final_out/` still holds the fix-99
tree pending a human promotion call.

- [x] Fix 101: bare-param hints take the RHS `new` spelling — non-generic
  (`T value1 = new ObiPinConstraintsBatch()`), generic over bare
  (`T value1 = new List<int>()` via the fix-98 path,
  `TValue value1 = new List<GameObject>()`), and qualified
  (`T value1 = new TMPro.KerningPair()` — only the last dotted
  component decides openness, fix-98 invariant; fix 101b). Declines on
  non-bare tuples, non-bare spellings, unreadable openness, open
  generic RHS (`new List<TKey>()`), bare `new T()`, non-`new`/array/
  initializer RHS, `<>c__` display-class spellings (normalized only at
  the file boundary, not a valid mid-pipeline decl type), and T-like
  bare targets (`new TMP_Character()`). Never invents a type: the
  spelling comes literally from the emitted RHS.
- [x] Provenance verified old-vs-new on all 234 changed bodies:
  line-count-identical everywhere; every diff line is a bare-`T`
  declaration-type change (463) or a consistent rename projection of
  one (319 binder renames incl. `foreach` binders, 1,475 use-site
  renames, 0 failures, 0 conflicts, 0 collisions). Every new decl type
  matches its own line's `new` target literally (the one apparent
  mismatch is a whitespace-only audit artifact:
  `List<byte[]>` vs `new List<byte[]>()`).
- [x] Residue: 8 bare-`T`-over-`new` sites in 5 files, both families
  declined by design — 4× `T1 t11 = new __c__DisplayClassN_0()`
  (mid-pipeline `<>c__` spelling; closing needs an emitter-coupled
  mangled-spelling proof) and 4× TMP sites
  (`new WeakReference<TMP_FontAsset>`, `new TMP_Character()`,
  `new TMP_SpriteCharacter()`: `TMP_*` collides textually with the
  bare-param regex, so the RHS reads open; closing needs a metadata
  typedef-closedness proof, not a textual one).

### Next priorities (fix 101 follow-ups)

1. **8 residual sites above**: emitter-coupled `<>c__` decl spelling,
   metadata typedef-closedness for T-like concrete RHS names.
2. **447 remaining shared tails** (fix 100 list stands), **8,067
   into-block gotos**, Review 87 byte-store/noreturn-EH/leftover lists
   — all stand.
3. Discovered and NOT changed: `_args_contain_open_param` is purely
   textual, so concrete `TMP_*` types read as open params on the RHS
   (tracked-tuple side is structurally proved and unaffected); the
   `<>c__` → `__c__` file-boundary mangling runs after all decl
   passes.

## Previous work — fix 100 (shared-tail resolution by caller return type, gated 2026-09-16)

A `return <call>` tail delivers the callee's value as the caller's own,
so the true callee's closed, spec-inflated return must equal the
caller's exact metadata return (`_shared_tail_return_target` +
`_tail_sig_key`/`_tail_subst_closed` in `il2cpp/lifter/calls.py`, wired
into both tail-jmp paths in `il2cpp/lifter/insn.py` and
`il2cpp/dec/analyze.py` — the analyze.py mirror is the one that emits
production tails; insn.py covers mid-block jumps). Gates: **526 tests
(509 + 17 new in `tests/test_review100_tail_returns.py`, incl. an
end-to-end `_insn` twin render); direct sweep 116,178 methods / 0
crashes / 0 structural changes vs fix 99 (64 bodies changed, net -212
lines); strict build 11,107 files / 115,658 bodies / 0 failures or
fallbacks (`work/review100_out`); parser 0 bad files**. Reports:
`validation_reports/review100_sweep.json`, `review100_vs99.json` (64
changed, 0 structural), `review100_parse.json`; built tree
`work/review100_out`. The 64 goldens are untouched (0 overlapping MIs,
no regen needed). NOT promoted — `final_out/` still holds the fix-99
tree pending a human promotion call.

- [x] Fix 100: keep nothing on speculation (open/unreadable rows decline
  the whole resolution), drop closed return mismatches, resolve only on
  one distinct rendering. Declines on void callers (fix 95 owns them),
  open/unknown callers, empty/split survivors, open generic definitions,
  and non-method/generic rows. Winners render through the existing
  resolved-tail emitters. Ground truth: `GameServer.GetHSteamPipe`
  (mi 97624) `return sub_18073e050...(GetHSteamPipe(), 0)` becomes
  `return HSteamPipe.op_Explicit(...);`, `Int32.IConvertible.ToInt64`
  (mi 2044) loses 8 lines of guard/phi scaffolding collapsing to
  `return Convert.ToInt64(this.m_value);`, `CloudServices.get_LocalPlayerRef`
  (-12) becomes `return PlayerRef.FromIndex(cloudServices1 >> 32);`,
  `ValueTuple.CombineHashCodes` ×7 (-6 each) become
  `return HashHelpers.Combine(...);`.
- [x] Provenance verified on the built trees: all 13,646 lost
  call-shaped lines are dead `Type V = typeof(X)` (fix-99 audit; the 3
  apparent gains are renumbering artifacts); every added tree line is a
  consistent rename of a surviving live line. Impure-line conservation
  holds modulo locals.
- [x] Residue: `return sub_*shared body` tails fall 511 → 447 (97 → 87
  addresses). Deliberately honest remainder, by family: string
  `Equals`/`op_Equality` (74, behavior-identical twins), `Compare`/
  `CompareTo` (9), `GetHashCode`/`InternalGetHashCode` (15),
  `Clone`/`MemberwiseClone` (10), `get_Module`/`GetRuntimeModule` (8),
  thunk-address pairs whose finals carry no candidates, same-signature
  twins (`GetTexture`/`GetTextureImpl`, surrogate/`IsDigit` pairs),
  and high-count addresses needing receiver instantiation (`List.Add`,
  `Dictionary.get_IsReadOnly`, `Nullable`) or arg-type overload proof
  (`Convert.ToBoolean` short/ushort, `Exchange` long/IntPtr).

### Next priorities (fix 100 follow-ups)

1. **447 remaining tails**: receiver-driven instantiation (same-owner
   generic families), arg-type overload disambiguation, forwarder
   direction via body-call analysis. Never max-arity guesses.
2. **Bare-`T` declaration LHS** (~425 sites), **8,067 into-block gotos**,
   byte-store/noreturn-EH/leftover lists — all stand.
3. Discovered and NOT changed: `_IMPURE` never matches generic calls
   (`Foo<Bar>(...)`), so pre-existing DCE already treats dead generic
   calls as droppable (see fix 99 notes); the analyze.py/insn.py tail
   mirrors must stay in sync — fix 94/100 wire both.

## Previous work — fix 99 (post-render dead-pure-load DCE, gated 2026-09-15)

`_render` drops empty pure-cond `if`s (e.g. an emptied class-init guard
`if (!(k.initialized != 0)) { }`), orphaning the pure klass loads they
alone read — no DCE ran after render, so `System.Type objN = typeof(X)`
survived dead into output and was renamed `Type typeN`. `_structure`
(`il2cpp/dec/structure.py`) now re-runs the proven `_drop_dead_locals`
on the rendered lines: same predicate (pure RHS incl. pure-loads drop,
impure calls stay), later timing. Gates: **509 tests (499 + 10 new in
`tests/test_review99_render_orphans.py`); direct sweep 116,178 methods /
0 crashes / 0 structural changes vs fix 98 (10,062 bodies changed, every
one pure line deletions, net -16,555 lines); strict build 11,107 files /
115,658 bodies / 0 failures or fallbacks (`work/review99_out`); parser 0
bad files**. Reports: `validation_reports/review99_sweep.json`,
`review99_vs98.json` (10,062 changed, 0 structural), `review99_parse.json`;
built tree `work/review99_out`. The 64 goldens were regenerated after
individual review of all 6 diffs (each exactly dead-typeof removals plus
required renumbering cascades). Promoted 2026-09-15: `final_out/` now holds
`work/review99_out` (11,200 files, candidate and promoted aggregate sha256
both `c14263784492b2f209ff695018376404cf0093f06862e1b20e928da89391f2e7`, 0
mismatches; the fix-97e tree is kept at `bckups/final_out_review97e`).
Promotion record: `validation_reports/review99_promotion_verification.json`;
post-promotion parse recheck
`validation_reports/review99_recheck_parse_final.json` (11,107 files, 0
bad).

- [x] Fix 99: one post-render `_drop_dead_locals` call. Ground truth:
  ActorCOMTransform.Update (mi 23898) ships `Type type1 =
  typeof(Object)` whose only reader is the guard `_render` removes;
  KerningTable.AddKerningPair (mi 95457) is untouched.
- [x] Provenance verified on the built trees: all 13,646 lost
  call-shaped lines are `Type V = typeof(X)` (dead pure loads); the 3
  apparent gains are local-renumbering artifacts of the audit's own
  normalizer (verified method-full diffs); every added tree line is a
  consistent rename (`type2` → `type1`) of a surviving live line.
- [x] Residue: dead `Type typeN = typeof(X)` decls fall 12,700 → 10 (the
  10 survivors are kept by `//` line-comment contents seeding liveness —
  over-retention, safe direction). Diagnosed but NOT changed: `_IMPURE`
  (`[\w\]\)]\s*\(`) never matches generic calls (`Foo<Bar>(...)`), so the
  pre-existing DCE already treats dead generic calls as droppable; fix 99
  adds no new unsoundness class (1 such drop corpus-wide:
  `CompileFunctionPointer<...>` in GPUResidentDrawerBurst).

### Next priorities (fix 99 follow-ups)

1. **511 remaining `return sub_*shared body` tails** (fix 94 list stands).
2. **Bare-`T` declaration LHS** (`T value1 = new KerningPair();`, ~425
   sites), **8,067 into-block gotos**, Review 87 byte-store/noreturn-EH
   lists — all stand.
3. **`UnityAction<T0>` LHS is DONE (fix 98); dead-`typeof` LHS is DONE
   (fix 99)** except the 10 comment-pinned survivors above.

## Previous work — fix 98 (open-generic declaration LHS closes over `new` RHS, gated 2026-09-15)

Open-generic tracked hints (`UnityAction<T0>`, `EventCallback<TEventType>`,
`Func<TSource, bool>`, …) now declare with the same line's closed `new`
allocation spelling when the generic definition matches (same short base,
same arity) and the RHS is textually closed. Gates: **499 tests (483 + 16
new in `tests/test_review98_open_generic_decls.py`); direct sweep 116,178
methods / 0 crashes / 0 structural changes vs fix 97e (229 bodies changed,
all line-neutral declaration-only); strict build 11,107 files / 115,658
bodies / 0 failures or fallbacks (`work/review98_out`); parser 0 bad
files**. Reports: `validation_reports/review98_sweep.json`,
`review98_vs97e.json` (229 changed, 0 structural), `review98_parse.json`;
built tree `work/review98_out`. The 64 goldens are untouched (0 overlapping
MIs, no regen needed).

- [x] Fix 98: `_decl_type_of` (`il2cpp/dec/highlevel.py`) propagates the
  closed RHS `new` type when the tracked type structurally contains
  VAR/MVAR (`_type_has_var` binary walk, not a name guess), the RHS parses
  as a generic `new` (`_new_rhs_type`, arrays/non-generics decline), both
  sides split to the same short base and arity (`_split_generic`), and
  generic-argument-position openness agrees
  (`_args_contain_open_param`: `TMPro.KerningPair`-style qualified names no
  longer read as open). Different bases (`IList<T>` vs `new List<int>()`),
  open RHS, non-`new` RHS (`Enumerator<T> = obj.GetEnumerator()`), bare-`T`
  LHS (`T value1 = new KerningPair()`), and closed/unknown tracked types all
  decline. Built-tree same-base open→closed `new` sites fall 414 → 0 (the 3
  remaining `UnityAction<T0>` lines are legitimate method signatures).

### Next priorities (fix 98 follow-ups)

1. **511 remaining `return sub_*shared body` tails** (fix 94 list stands).
2. **Bare-`T` declaration LHS** (`T value1 = new KerningPair();` family),
   **dead `Type type1 = typeof(Object);` lines** (2,791 sites), Review 87
   byte-store/noreturn-EH/leftover lists — all stand (see below).
3. **`UnityAction<T0>` declaration LHS is DONE (fix 98 above)** except the 3
   legitimate open-generic method signatures, which must stay open.

## Previous work — fix 97 (bare first-use temp declarations + 97e render repair, gated 2026-09-14)

Declare bare first-use temps (`objN = rhs;` with no prior declaration from
stack-slot zeroing, phi copies, unbound call results) exactly like `var`
lines, from the same tracked-type lookup; a later `var` line for the same
temp keeps only its assignment. Gates: **483 tests (462 + 21 new: 15 in
`tests/test_review97_bare_decls.py` plus 6 fix-97e `_render` cases); direct
sweep 116,178 methods / 0 crashes / 0 structural changes vs fix 94 (39,478
bodies changed, net declaration additions); strict build 11,107 files /
115,658 bodies / 0 failures or fallbacks (`work/review97_out`); parser 0
bad files**. Reports: `validation_reports/review97e_sweep.json`,
`review97e_vs97.json` (25 changed, 0 structural — the 97e repair only),
`review97e_parse.json`; built tree `work/review97_out`. The 64 goldens were
regenerated with **0 body changes** (none of the 25 repaired methods is a
golden MI; only source fingerprints refreshed). Promotion record:
`validation_reports/review97e_promotion_verification.json`; post-promotion
parse recheck `validation_reports/review97e_recheck_parse_final.json`.

- [x] Fix 97: first-use bare assignments declare (`_rename_locals` in
  `il2cpp/dec/highlevel.py`, wired through the existing `var` type path).
- [x] Fix 97b: `= default` for zero-literal RHS that cannot spell the
  declaration type (`_bare_rhs_needs_default`: only zero-valued numerics
  rewrite; nonzero literals keep their faithful value).
- [x] Fix 97c: scope-aware declaration tracking (sibling scopes re-declare;
  enclosing declarations suppress).
- [x] Fix 97d: (folded into 97b) nonzero-literal fidelity.
- [x] Companion updates: typed `bool flagN` sugar variants (`_bool_sugar`
  in `il2cpp/dec/sugar.py`), ternary arm declaration normalization
  (`_ternary_pass`), typed hop-temp acceptance (`_HOP_DEF_RX` in
  `_compound_assign`).
- [x] Fix 97e (render-strip repair, found by the parse gate, not the
  sweep): the first `work/review97_out` build gated **23 bad files / 26
  ERROR nodes** (review 94: 0/0/0). Chain: 97b synthesizes `: default`
  false arms, `_ternary` folds `if (!c) { T x = call(); } else
  { T x = default; }` into `T x = c ? call() : default;`, then
  `_strip_dangling_default` (`il2cpp/dec/textpass.py`, inside `_render`)
  dropped the tail — its flat `region_q` flag reset on every `(` (the
  call's parens) and `,` (multi-arg calls), orphaning unparseable
  `? call() ;`, which `_fix_select` cannot repair (statement-level `?`).
  The strip now tracks the paren depth of each live ternary/select `?`
  mark: `(` no longer resets, `,` only forgets marks at its own depth or
  deeper, `)` forgets the closed group's marks, `;{=` still clear the
  region, and `??`/`?.`/nullable `?` never become marks. All 26 sites
  (e.g. `IntPtr num2 = num1 != null ? AndroidJNI.NewGlobalRef(num1) ;`
  → `... : default;`) verified fixed in the rebuilt tree; dangling tails
  (`Foo(a : default)`, including after `int?` declarations) still strip.
  Side note: `tools/validate_corpus.py parse` segfaulted on the broken
  tree (native tree-sitter flakiness; per-file processes and `ts_gate.py`
  were unaffected) and succeeds on the fixed tree.

### Next priorities (fix 97 follow-ups)

1. **511 remaining `return sub_*shared body` tails** (fix 94 list stands).
2. **`UnityAction<T0>` declaration LHS** (61 sites), **dead
   `Type type1 = typeof(Object);` lines** (2,791 sites), Review 87
   byte-store/noreturn-EH/leftover lists — all stand (see below).

## Current work — fixes 94, 95, 96 (gated + promoted 2026-09-13)

Tail-call honesty, void-caller tails, and a `_value_cse` allocation hole,
found by reading `AudioVolumeSliders.Start` end to end. Gates: **462
tests (446 + 16 new); direct sweep 116,178 methods / 0 crashes / 0
structural changes vs fix 92 (3,879 bodies changed, net +1,466 lines,
3,405 line-neutral); strict build 11,107 files / 115,658 bodies / 0
failures or fallbacks (`work/review94_out`); parser 0 bad files**.
Reports: `validation_reports/review94_sweep.json`,
`review94_vs92.json` (3,879 changed, 0 structural),
`review94_comparison.json` (vs Review 84: 17,843 changed, same 4
pre-existing fix-91 structural entries, 0 new crashes),
`review94_parse.json`; built tree `work/review94_out`. Promoted
2026-09-13: `final_out/` now holds `work/review94_out` (11,200 files,
candidate and promoted aggregate sha256 both
`6ec3c6f45deb2f653c1f3bf02053a82251c322f169f5b0df7c8f0249b64e679b`, 0
mismatches; the Review 89 tree is kept at
`bckups/final_out_review89`, the fix-91 tree at
`bckups/final_out_review88`, the Review 84 tree at
`bckups/final_out_r84`). Promotion record:
`validation_reports/review94_promotion_verification.json`;
post-promotion parse recheck
`validation_reports/review94_recheck_parse_final.json` (11,107 files, 0
bad). `validation_reports/SHA256SUMS.txt` still pins the Review 84 era
(prior promotions likewise left it; see the split notes). The 64 goldens
were regenerated after individual review of all 5
diffs (4 void-shape, 1 shared-ctor-tail initializer).

- [x] Fix 94: shared tails strip the hidden instantiation argument
  (exact-text identity proof, trailing-position + single-spec
  tightenings), trim trailing stale unknowns (fix-58 mirror), and render
  the true generic callee instance-folded; resolved ctors take the
  `..ctor` pseudo-form the emitter promotes (`_tail_hidden_generic`,
  `_tail_trim_stale`, `_tail_generic_call` in `il2cpp/lifter/calls.py`,
  wired into both tail-jmp paths). Ground truth: the Start tail's
  `mov r8,[slot]` + dispatch-through-R8 body proves R8 selects
  `UnityEvent<float>.AddListener`, which the 8 listed candidates (all
  zero-arg TypeTraits getters) miss — so NO max-arity trim: the
  candidate set is provably incomplete (a cap of 0 wiped real args in
  testing). `return sub_*shared body` tails fall 1,939 → 511.
  Regressions: `tests/test_review94_tails.py` (12 portable).
- [x] Fix 95: value-returning tails in exact-metadata-void callers render
  `<call>; return;` (`_caller_is_void`, `_emit_tail`; each site keeps its
  `/* tail */` habit). Covers resolved, shared, array-new, and
  generic-resolved tails in both paths.
- [x] Fix 96: `_value_cse` never caches `new` allocations (fresh identity
  per execution; parameterless `new T()` slipped past `_IMPURE`).
  Restores wrongly aliased objects, e.g. all 133
  `StructWrapper<byte>` pool instances in `StructWrapperPools..cctor`
  (+132 lines there). Regressions:
  `tests/test_review96_value_cse.py` (4 portable).

### Next priorities (fixes 94-96 follow-ups)

1. **511 remaining `return sub_*shared body` tails** have no trailing
   hidden identity (absent, non-trailing, or conflicting). The registry
   misses true sharers (fix 94 proof), so closing these needs sharer
   discovery beyond `addr_candidates`, never a max-arity guess.
2. **`UnityAction<T0>` declaration LHS** (61 sites): open-signature hints
   type the declaration while the `new` RHS is closed. Propagate the
   closed RHS type when the hint is an unresolved generic parameter.
3. **Dead `Type type1 = typeof(Object);` lines** (2,791 sites): bound
   results of side-effect-only class-init calls. Drop the result binding
   for class-init helpers.
4. **Review 87 list stands:** untyped `((byte*)+0)[0] = 4294967294`
   stores, five sub-threshold noreturn EH targets, 15 constructor
   leftovers, `object objN` / empty-allocation provenance, ABI gaps,
   8,067 into-block gotos, vector/ARM64/fixture breadth.

## Current work — Review 87 (fix 92, gated 2026-09-11, promoted 2026-09-12)

`docs/reviews/REVIEW87.md`, `validation_reports/review85/sweep4.json`,
`sweep4_comparison.json`, and `parse4.json` describe one source fix (92):
MethodSpec instantiation indices are zero-based with -1 absent. Gates:
**435 tests (317 portable + 64 snapshots + 54 native); strict build 11,107
C# files / 115,658 bodies with 0 failures or fallbacks
(`work/review89_out`); parser 0 bad files; direct sweep 116,178 methods /
0 crashes / 0 new structural changes vs Review 84 (same 4 fix-91
entries)**. Promoted 2026-09-12: `final_out/` now holds `work/review89_out`
(11,200 files, candidate and promoted aggregate sha256 both
`0b906f7d1c8ab400a8718f745df1182bad9e9ffbb55a2bea18c30f51839323b5`, 0
mismatches; the fix-91 tree is kept at `bckups/final_out_review88`, the
Review 84 tree at `bckups/final_out_r84`). Promotion record:
`validation_reports/review85/promotion_verification_review89.json`;
post-promotion parse recheck
`validation_reports/review85/recheck_parse_final.json` (11,107 files, 0 bad).
Note: this section previously reserved "candidate fix 92" for the two
named raisers; that unshipped candidate is renumbered to fix 93.

Completed in this batch:

- [x] Read `classIndexIndex`/`methodIndexIndex` zero-based in
  `generic_method_name` and `_method_spec_type_args`, with -1 as the only
  absent spelling (row 0 is a real instantiation). Proved over all 175,736
  specs: zero-based matches every declared generic arity (32,671 method +
  144,977 class rows, zero exceptions), one-based contradicts 2,749.
  Evidence: `work/review89_spec_arity_census.py`,
  `work/review89_spec_index_base.py`.
- [x] Fixed `Object.Instantiate<Font>`: 66 sites become `GameObject`, 0
  `Font` remain; every generic name steps off its neighbouring row
  (`EpilepsyHandler` -> `ComputeShader`, `Obi.*` -> `Vector2`/`byte`/
  `TouchPhase`/etc.). 16,119 bodies changed, all name-only; inventory and
  line-count shape unchanged.
- [x] Regenerated the 64 golden snapshots: 5 reviewed generic-name changes,
  59 unchanged. Regressions: `tests/test_review89_spec_indices.py` (11
  portable); `tests/test_shared_returns.py` updated to the proved spelling.

### Next priorities (Review 87)

1. **Type the untyped `((byte*)objN + 0x0)[0] = 4294967294;` stores.**
   Carried over from Review 85: the lvalue has no declared width, so the
   immediate cannot be sign-flipped on evidence yet.
2. **DONE - fix 93 shipped 2026-09-13: the two named raisers render as
   `throw new`.** `raise_IndexOutOfRangeException` /
   `raise_NullReferenceException` are each one specific new exception raised
   by a `sub rsp,X; call T; int3` noreturn forwarder, so
   `object objN = raise_NullReferenceException();` becomes
   `throw new NullReferenceException();` (0 old-style sites remain, 834
   throw-new sites in `work/review93_out`). Gates: 446 tests (436 + 10 new
   in `tests/test_review93_named_raise.py`); direct sweep 116,178 methods /
   0 crashes / 0 structural changes vs fix 92 (76 bodies changed, -76
   lines); strict build 11,107 files / 115,658 bodies / 0 failures; parse
   gate 0 bad files. Reports: `validation_reports/review93_sweep.json`,
   `review93_vs92.json` (`review93_comparison.json` vs Review 84),
   `review93_parse.json`. Predicate: exact evidence-derived name, arity 0,
   unregistered target, forwarder shape (`_named_raise_throw` in
   `il2cpp/lifter/calls.py`, wired into `_call` and both tail-jmp paths).
3. **Prove the five sub-threshold noreturn EH targets**
   (`0x180435040`, role-ambiguous `0x1804346b0`, `0x180434690`,
   `0x180001ea0`, `0x180002070`) with evidence other than witness counts,
   then tighten per-method/proven-set agreement.
4. **Review 84 list stands:** 15 constructor leftovers, 112,423
   `object objN` declarations, 13,254 empty allocations, ABI gaps, 8,067
   into-block gotos, vector/ARM64/fixture breadth (see the Current
   replacement section below).

## Previous work — Reviews 85 and 86 (2026-09-10/11)

`docs/reviews/REVIEW85.md` and `validation_reports/review85/` describe five source fixes
(85-89), one validation-tool fix, and one newly diagnosed defect. Gates:
**399 tests (289 portable + 64 snapshots + 46 native); strict build 11,107 C#
files / 115,658 bodies with 0 failures or fallbacks; parser 0 bad files;
direct sweep 116,178 methods / 0 crashes / 0 structural-metric changes / 0 new
crashes vs Review 84**. Promoted 2026-09-11 (itself superseded 2026-09-12 by
the Review 87 promotion; the fix-91 tree is kept at
`bckups/final_out_review88`): `final_out` then held
`work/review88_out`, the tree gated after fixes 90, 91, 91b, and 91c (11,200
files, candidate and promoted aggregate sha256 both
`0ef7607e317dbb00f59ad72ccaa8089b36ccf0a79c42bae7f525ebeb30118d00`, 0
mismatches; the Review 84 tree is kept at `bckups/final_out_r84`).
`work/review86_out` was never promoted. Gates for that tree: 424 tests,
strict build 11,107 files / 115,658 bodies / 0 failures, parse gate 0 errors
and 0 recovery nodes, direct sweep 116,178 methods / 0 crashes, 64 goldens
regenerated with 0 changes. See `docs/reviews/REVIEW86.md`.

Completed in this batch:

- [x] Decode enum member tables through the enum's underlying element type
  with the compressed (zigzag) reader. The old raw fixed-width read doubled
  every value and invented junk members; eight member names are confirmed
  wrong before and correct after, including `DateTimeKind.Utc` -> `Local` and
  `Token.XdrDatatype` -> `XsdSchema`.
- [x] Fold enum-valued call arguments to `Type.Member`, so
  `new FileStream(text2, 3)` becomes `new FileStream(text2, FileMode.Open)`.
- [x] Stop `_int_lit` stripping the hex digits `d` and `f` as float suffixes.
  It had read `0x3d` as 3, `0x7f` as 7, and `0xf` as unparseable.
- [x] Fold literal-base address composition, `(0 + 0x3)` -> `3`, without
  touching `_field_expr`'s dereference form.
- [x] Reinterpret immediates at their declared signed width, `4294967294` ->
  `-2`; 188 rewrites in the first 4,000 methods. Unsigned and native-int type
  codes deliberately excluded.
- [x] Relocate sweep manifests relative to the report that names them, fixing
  moved-report reads on Windows.
- [x] Regenerate the 64 golden snapshots: 9 changed, +37 / -37 lines, every
  changed line an enum-member fold.

### Next priorities (Review 85, historical; use the Current work list above)

1. **DONE - EH helper naming is now evidence based (fixes 90, 91, 91b, 91c).**
   `_seh_helpers` used to discover the raise/rethrow VAs from whichever method
   was lifted first and write them onto the shared lifter, so output depended
   on process partitioning and lift order. That part was right, and it still
   explains 1,913 of the 10,758 changed bodies in that batch, which are **not**
   attributable to fixes 85-89.
   The rest of the diagnosis above was wrong about which side was correct. A
   census of all 4,526 pad-bearing methods found 99 distinct rethrow targets
   and 9 raise targets, and 51 of the rethrow targets were ordinary registered
   methods -- `AsyncTaskMethodBuilder.SetException`, `Debug.LogException`,
   `Marshal.FreeHGlobal`, even `DateTime.AddYears` -- so a large share of
   those 3,113 `throw` statements were leaked values that had each eaten a
   real call, not correct output.
   Fix 90 clears both fields for every method and requires an unregistered
   native target. Fix 91 then proves the pair once from the whole binary:
   `0x180435740` rethrow (3,403 witnesses against 126) and `0x180435670`
   raise (183 against 25). Fix 91b rejects plumbing the lifter can already
   name, directly or through a jmp thunk -- `0x180435420` is a thunk onto
   `il2cpp_codegen_initialize_runtime_metadata` that 181 methods had taught
   as a helper -- and fix 91c rejects any routine with a reachable `ret`,
   which removed five impostors including the 45-witness `0x180002650`.
   Evidence: `work/review87_helper_census.py`,
   `work/review87_helper_classify.py`, `work/review88_helper_ident.py`,
   `work/review88_anchor_diff.py`, `work/review88_sample.py`. Regressions:
   `tests/test_review87_eh_helpers.py`,
   `tests/test_review88_eh_helper_set.py`.
   Still open: five noreturn but sub-threshold targets (`0x180435040` 13/0,
   `0x1804346b0` 12 rethrow against 13 raise, `0x180434690` 8/0,
   `0x180001ea0` 6/0, `0x180002070` 3/0) remain on per-method evidence only,
   and the two named raisers still render as calls rather than
   `throw new IndexOutOfRangeException();` / `throw new
   NullReferenceException();` -- candidate fix 92 (renumbered to fix 93, since
   fix 92 shipped the MethodSpec base; see the Current work section).
2. **Type the untyped `((byte*)objN + 0x0)[0] = 4294967294;` stores.** The
   lvalue has no declared width, so the immediate cannot be sign-flipped on
   evidence yet. Recover the store type and width first.
3. **DONE - Fix the wrong generic argument in `Object.Instantiate<Font>`.**
   Shipped as fix 92; see the Current work section above and `docs/reviews/REVIEW87.md`.

## Current replacement — Review 84 (2026-09-10)

`docs/reviews/REVIEW84.md`, `docs/archive/reviews-log.md` §0bb, and `validation_reports/review84/` describe the
current source and complete output. Release: **358 tests (260 portable + 64
snapshots + 34 native); strict build 11,107 C# files / 115,658 bodies with 0
failures or fallbacks; parser 0 bad files; direct sweep 116,178 methods / 0
crashes / 0 structural-metric changes; constructor sweep 11,737 methods / 0
crashes**. The original DLL/metadata remain unchanged and were read statically,
never executed.

Completed in this release:

- [x] Complete class inheritance chains through a unique
  `IL2CPP_TYPE_OBJECT` → `System.Object` mapping, stop cycles, and isolate
  inheritance/field caches per `Il2Cpp` instance.
- [x] Resolve folded parameterless constructors only from typed current-ctor
  `this` or exact fresh-allocation provenance, one concrete closed MethodDef,
  a reference-type inheritance match, and exact instance/void/zero-argument
  metadata. Decline generic, multiple-match, byref, value-type, or malformed
  cases.
- [x] Distinguish same-type `: this(args)` from ancestor `: base(args)` and
  recover parameterized resolved initializers without leaving raw pseudo calls
  in generated C#.
- [x] Carry exact `_alloc` provenance through binding/copies and complete one
  allocation declaration in place. Audited discarded constructor allocations
  fall 13,292 → 0; empty allocation declarations fall 21,624 → 13,254.
- [x] Reduce `sub_180506120` constructor-family markers 2,958 → 160, legacy
  `this.ctor(...)` text 2,186 → 45, all shared calls 21,504 → 18,703, and
  `object objN` declarations 113,155 → 112,423.
- [x] Increase real `: base(...)` initializers 5,960 → 9,530 and
  `: this(...)` initializers 0 → 325 while shrinking generated C# by 20,568
  lines with no file-inventory change.
- [x] Preserve unrelated shared-call behavior by excluding the newly visible
  Object tail from the broad legacy receiver heuristic; freeze the regression
  where `System.Type.op_Equality` must not become an Object method.
- [x] Freeze the same 64 MethodDefs in `goldens_review84.json`: 56 unchanged and
  eight reviewed constructor/allocation changes.
- [x] Strict-build, overlap-verify, parse, directly sweep all methods and all
  constructors, compare, test, promote, checksum, and package the complete
  replacement.

### Next priorities (current, not archived diagnoses)

1. **Prove the 15 conservative constructor leftovers.** Twelve native
   constructors still contain `sub_180506120` because multiple eligible
   ancestor constructors share it; three complex generic/scope constructors
   retain `this.ctor(...)`. Add receiver/generic proof, never a cosmetic guess.
2. **Trace the producers of the remaining 112,423 `object objN` declarations.**
   Recover register seeds, stack-slot reads, local copy/store provenance, and
   alias identity. Type the producing value before changing its declaration.
3. **Finish allocation and indirect-call identity.** Classify the remaining
   13,254 empty allocations, virtual/function-pointer constructor targets, and
   cyclic allocations with dominance and per-iteration alias proof.
4. **Complete missing return/call ABIs.** Generic value-type instantiated sizes,
   source-level `ref` returns, non-address hidden buffers, mixed candidates, and
   broader stack/vector arguments need explicit models and negative tests.
5. **Finish legal structured control flow and compilation readiness.** 8,067
   into-block gotos remain across 2,047 methods, along with definite assignment,
   project references, constructor/SEH, identifier/type, and ref-return issues.
6. **Vector, ARM64, and fixture breadth.** General packed-lane state, ARM64
   semantics, and an independent licensed fixture remain open.

---

## Appendix: TODONOW.md — 2026-09-22 failure-class inventory (merged 2026-09-28)

> **HISTORICAL (2026-09-22, r4c era).** The former root `TODONOW.md`,
> folded in here so `docs/todo.md` is the single todo file. Live work is
> the "Open, by payoff" index at the top and the `## Current work`
> sections above; this appendix is kept for the failure-class inventory
> and source anchors. Line numbers may have moved, and every count below
> is r4c-era.

Generated 2026-09-22 from the current promoted tree. This is a handoff for
the next agent. The generated C# tree is `final_out/`; do not edit it by hand.
The source of truth is the decompiler under `il2cpp/`. Fixture inputs are
`testgame/ShiftAtMidnight_Data/il2cpp_data/Metadata/global-metadata.dat` and
`testgame/GameAssembly.dll`.

## Baseline gates (r4c promotion, 2026-09-23 — prior numbers archived below)

- Strict rebuild: 114,458 bodies, 0 failures, 0 fallbacks (matches).
- Brace audit: 0 unbalanced files. Parse gate: 0 bad / 0 ERROR / 0 MISSING.
- Full suite: 933 passed, 0 failed (first fully-green run; 67525
  regened to the signature-exact composite).
- `final_out/` is promoted output and must remain read-only.
- The fixture is private/licensed; never redistribute it.

## Exact fresh census of `final_out/`

All paths below are relative to `C:\Users\crax\Downloads\il2csharp`.
The count is occurrences/lines first and distinct `.cs` files second.

| category | promoted r4c scan | 2026-09-22 handoff figure | exact output root |
|---|---:|---:|---|
| shared-body marker `/*shared body, N candidates*/` | 18,884 / 2,278 | 19,013 / 2,304 | `final_out/**/*.cs` |
| `/*indirect*/` | 6,262 / 884 | 7,091 / 975 | `final_out/**/*.cs` |
| literal `unknown` | 15,655 / 1,361 | 16,044 / 1,382 | `final_out/**/*.cs` |
| raw `mem[N]` | 398 / 127 | ~13,189 / 805 | `final_out/**/*.cs` |
| `mem_<hex>` load twins | 359 / 95 strict (`mem_addr` params excluded) | 234 / 69 | `final_out/**/*.cs` |
| `goto` | 8,707 / 903 | 8,705 / 901 | `final_out/**/*.cs` |
| `/* nothing */` | 63 / 1 | 63 / — | `final_out/**/*.cs` |
| `?addr` | 1 / 1 | 22 / 6 | `final_out/**/*.cs` |

`?addr` follow-up (unpromoted): the last site (mi 65244) was our own
quarantine over-firing on a named `&s_1d0` home, so the declines were
narrowed to text-`?` bases and the store rescued -- then the rescue
was traced and disproved (rendered base aliases a reused home while
native uses a fresh address; address-of lost in write-barrier
conversion), and reverted byte-identically with the elision pinned by
a game test. `?addr` stays 1, honestly.

The differences are scanner-definition differences, not silently ignored
files: use the commands in the Census reproducibility section. In particular,
`unknown` can be counted as tokens, lines, or diagnostic hits; `?addr` can be
counted in historical reports rather than the promoted tree; and the shared
body/goto totals have changed by small formatting/regen deltas.

## 1. Runtime-broken — shared-body calls

### Exact files

Every affected file is under `final_out/` and matches the shared-body marker.
There are 2,304 distinct files. The exact complete inventory is reproducible
with the first command below; do not use a hand-curated sample as the scope.

### Source ownership

- Primary renderer: `il2cpp/lifter/calls.py:925` — emits
  `sub_%x/*shared body, %d candidates*/` when the native VA has multiple
  metadata owners.
- Shared-call pipeline and candidate/ABI logic: `il2cpp/lifter/calls.py`
  (especially the shared-call sections around lines 84, 1345, 1600, and
  1964–2051).
- Receiver/type lookup and shared target metadata: `il2cpp/runtime/core.py`,
  `il2cpp/runtime/registration.py`, `il2cpp/runtime/types.py`.
- Call-site analysis/indirect-tail handoff: `il2cpp/dec/analyze.py:180–205`.

### Why it is broken

The output names a native shared body but cannot select the concrete managed
MethodDef at the call site. It is therefore not a callable C# declaration;
the unresolved target throws at runtime. The honest spelling must remain for
ambiguous cases until receiver type, generic instantiation, ABI, and owner
proof all agree.

### Required fix direction

Implement receiver-type resolution at the call site, not a global VA rename.
Preserve all-candidate consensus rules, open-generic rejection, shared sret
rules, and the 15 conservative constructor leftovers documented in
`CLAUDE.md`. Add negative tests for ambiguous receivers and shared addresses.

## 2. Runtime-broken — indirect calls

### Exact files

975 files under `final_out/` contain 7,091 `/*indirect*/` occurrences.
Generate the complete path list with the second census command below.

### Source ownership

- Indirect call rendering: `il2cpp/lifter/calls.py:1139–1141` and
  `il2cpp/lifter/calls.py:1521`.
- Virtual/interface unresolved dispatch: `il2cpp/lifter/calls.py:1964–2051`.
- Indirect memory/control-flow classification: `il2cpp/lifter/insn.py:1231–1234`.
- CFG safety/unknown indirect control flow: `il2cpp/dec/build.py:25–44` and
  `il2cpp/dec/analyze.py:180–205`.
- Higher-level dispatch folding (must decline when proof is absent):
  `il2cpp/dec/flow.py:917–920` and `il2cpp/dec/sugar.py:328`.

### Required fix direction

Same fix family as shared bodies: infer the receiver/interface slot and exact
closed MethodDef from metadata plus native evidence. Do not resolve by helper
VA, class name, or majority candidate. Preserve `/*indirect*/` when proof is
missing.

## 3. Compile-broken — unknown values

### Exact files

Fresh token scan: 12,084 `unknown` tokens in 1,383 files under
`final_out/`. The historical handoff reports 16,044 hits/1,382 files because
its hit definition includes additional unknown-value diagnostics. Treat the
union of both scans as the investigation scope.

### Source ownership and producer families

- Unknown minting: `il2cpp/lifter/state.py:1131–1132` (`_fresh_unknowns`).
- Register/value propagation: `il2cpp/lifter/state.py`,
  `il2cpp/lifter/values.py`, `il2cpp/lifter/aggregates.py`.
- Unknown call results and ABI fallback: `il2cpp/lifter/calls.py:1185–1262`.
- Unknown memory operands: `il2cpp/lifter/insn.py:1675–1695`.
- Unknown cleanup/rendering: `il2cpp/dec/textpass.py:458–529` and
  `il2cpp/dec/textpass.py:599`.

### Known remainder classes

1. stale stack tiles surviving copies/merges;
2. SIMD/vector lanes not carried through spills, `UNPCK*`, or calls;
3. unknown results from unresolved shared/indirect calls;
4. genuine unknown branch conditions and pointer bases.

Fix producers and provenance; never replace `unknown` textually with zero,
`default`, or a guessed type.

## 4. Compile-broken — raw `mem[N]` stores and `mem_xx` loads

### Exact files

- `mem[N]`: 13,189 occurrences in 805 files under `final_out/`.
- `mem_<hex>`: 324 occurrences in 70 files by the current broad scan; the
  handoff's narrower load-twin census is 234/69.

### Exact source

- `il2cpp/lifter/insn.py:1345`: load fallback returns `Expr('mem_%x' % disp,
  None, 'ptr')` when the base register is untracked.
- `il2cpp/lifter/insn.py:1349`: `_mem_lvalue` begins raw-store generation.
- `il2cpp/lifter/insn.py:1379`: `if be is None: return 'mem[%d]' % sdisp(disp)`.
- Store consumers: `il2cpp/lifter/insn.py:1695–1787`.
- Raw-width/type tests and intended conservative behavior:
  `tests/test_review102_raw_store_widths.py:251–359`.

### Required fix direction

Recover the base register/aggregate provenance and declared pointee width
before emitting a named field or typed pointer. A raw store is currently an
undeclared C# identifier and therefore a compile error. Do not make up fields
from displacement alone; preserve raw output when ownership/layout is not
proved.

## 5. Compile-broken — unbound temps

### Exact files

Upper bound: up to 8,700 tokens across as many as 2,200 output files. This is
not a clean compiler count: it includes false positives such as multi-
declarations and identifiers introduced in a branch whose declaration is
outside the textual region. The exact candidate path inventory is produced by
the unbound-temp command below.

### Source ownership

- Register/stack seed and copy state: `il2cpp/lifter/state.py`,
  `il2cpp/lifter/values.py`, `il2cpp/lifter/aggregates.py`.
- Phi/merge materialization and copies: `il2cpp/dec/analyze.py:448–510`.
- Declaration/use binding and dead-local cleanup:
  `il2cpp/dec/dataflow.py`, `il2cpp/dec/emit.py`, `il2cpp/dec/textpass.py`.
- Final semantic names (must not invent type evidence):
  `il2cpp/dec/emit.py` / `_semantic_local_names` and the invariants in
  `CLAUDE.md`.

### Required fix direction

Trace each candidate to its native definition, stack home, phi edge, or call
result. Fix the producer/provenance and scope merge. Do not globally declare
all `objN` names or substitute `default`; that would hide missing native
values and create runtime corruption.

## 6–11. Resolved or harness artifacts — do not re-investigate

- Duplicate members: genuine intra-assembly duplicates were fixed by
  conversion-operator emission. Remaining CS0101/CS0111/CS0102 spikes are
  cross-assembly BCL twins caused by the single-assembly harness. See
  `il2cpp/emitter.py` and the Roslyn ledger in `nowtodo.md` Addenda 14–15.
- Enum/int edges: fixed by enum-aware `(E)v` casts, underlying declarations,
  parentheses, and `unchecked`; verify with Roslyn only. Do not reopen.
- Finalizers: fixed in `il2cpp/headers.py`/signature emission; exact `~X()`
  output is already covered. Do not reopen.
- Optional parameter order: fixed in parameter emission (`= default` for
  dropped trailing null rows; genuine mid-default rows stripped). Do not
  reorder parameters.
- CS0115 bad overrides: harness artifact; adding Mono.Security to the check
  scope reduces the reported 14 to zero.
- `_1<T>` qualifier remainder: harness artifact; declarations live in
  uncompiled Fusion directories.

## 12–15. Cosmetic/by-design — do not spend fix effort

- `goto`: current scan 8,707/903; compiles and represents unresolved
  unstructured control flow. Emitter/structured pipeline is under
  `il2cpp/dec/structure.py`, `flow.py`, and `emit.py`.
- `/* nothing */`: 63 occurrences in one file (`Arm.cs` Neon forwarders);
  fresh lifts now render all 63 as `return Neon.<s8-variant>(args);`
  (noreturn-shared forwarder proof, 2026-09-24). Promoted `final_out/`
  still shows the old bodies until a rebuild.
- `__SharedBodyStubs`: throwing stubs are intentional behavior for unresolved
  runtime targets; see `il2cpp/emitter.py` stub generation.
- `?addr`: current promoted tree has only 2 occurrences in 2 files; nearly
  extinct and not a priority.

## Census reproducibility (PowerShell, from repository root)

```powershell
$out = 'final_out'
rg -n --glob '*.cs' 'sub_[0-9A-Fa-fx]+/\*shared body, [0-9]+ candidates\*/' $out
rg -n --glob '*.cs' '/\*indirect\*/' $out
rg -n --glob '*.cs' '\bunknown\b' $out
rg -n --glob '*.cs' '\bmem\[[^]]+\]' $out
rg -n --glob '*.cs' '\bmem_[A-Za-z0-9_]+' $out
rg -n --glob '*.cs' '\bgoto\b' $out
rg -n --glob '*.cs' '/\* nothing \*/' $out
rg -n --glob '*.cs' '\?addr' $out
```

To obtain exact distinct paths for any category, pipe a command's output
through this PowerShell expression (it preserves the `file:line:text` output
for follow-up inspection):

```powershell
$hits = rg -n --glob '*.cs' '/\*indirect\*/' final_out
$hits | ForEach-Object { ($_ -split ':',3)[0] } | Sort-Object -Unique
```

Replace the pattern with the other marker. For source ownership, use
`rg -n` against the exact files listed above; line numbers are current source
line anchors and must be rechecked after edits.

## Work order for the fixing agent (status as of r4c promotion)

1. Inventory: done (census table above, re-counted at promotion).
2. Shared-body receiver resolution + indirect/interface dispatch:
   landed as proof-driven slices (array receivers, twins pins,
   interface dispatch); hinted receivers and generic substitution
   disproved/deferred with evidence (see addenda).
3. Unknown values + raw memory: landed as provenance slices (RSP-copy
   homes, SIMD consumer-side tails + direct); general packed tracking
   stays declined.
4. Unbound temps: classified (55 distinct in 21 files, all params or
   checker FPs in fresh lifts) and fixed (rename barrier + param
   exclusion); actionable set ~zero.
5. Gates + suite: 932 passed / 0 failed (first fully-green run; the
   old 67525/104428 reds were regened after per-hunk review).
6. Never regenerate or promote `final_out/` without an explicit user call.

## Stop record — 2026-09-22, SIMD/stack provenance follow-up

The decompiler changes are in the primary repository package under
`il2cpp/`; the scripts under
`C:\Users\crax\AppData\Local\Temp\opencode` were tracing/patch helpers only
and are not imported by the project. `final_out/` was not edited, rebuilt, or
promoted.

### Source changes

- `il2cpp/lifter/insn.py`: scalar SSE arithmetic preserves untouched upper
  lanes when the input already carries proved packed provenance. General
  `SHUFPS` recovery was attempted, but reverted after MethodDef 80548 proved
  the same local shape can be integer/index bookkeeping; it remains a
  conservative no-op until stronger use-site proof exists.
- `il2cpp/lifter/aggregates.py`: an offset lane crosses a CFG phi only when
  every predecessor reconstructs the same typed value.
- `il2cpp/lifter/state.py`: use-binding keeps packed-phi provenance reachable
  after a `vN` expression is renamed to a `tN` temp.
- `il2cpp/lifter/values.py`: kill-on-write freezes packed lanes that read an
  overwritten location instead of discarding their provenance.
- `il2cpp/lifter/calls.py`: the early sret-return path now uses the existing
  Win64 positional-argument reconstruction and reconstructs by-value structs
  from stack homes, matching the ordinary resolved-call path.
- `tests/test_recovery_completion.py`: six portable regressions cover
  scalar-lane preservation, unanimous/disputed phi lanes, bind-time
  provenance, and safe/stale kill-on-write lanes.

### MethodDef 104428 (`GraphUpdateShape.GetBounds`)

The two emitted `unknown` arguments are gone. The final native call now has
all six declared parameters present and typed; its first two difference
vectors are reconstructed from the packed XMM/stack tiles, and the 5th+
Win64 arguments are read from the stack home area rather than a stale XMM
tail. The fresh body still differs from the frozen golden (including modern
static-field spelling and the newly recovered aggregate expressions), so
`tests/test_game_goldens.py` remains red for 104428 until that body is
reviewed and an explicit golden-regeneration call is made. Do not blindly
regenerate it.

### Validation at stop

- `python -m compileall -q il2cpp il2csharp.py`: pass.
- Source-format assertions for every touched `il2cpp/lifter/*.py`: CRLF,
  no BOM, pass.
- `git diff --check`: pass.
- Final portable suite: **757 passed, 130 deselected**.
- Focused new tests after that revert: **7 passed**; the only selected failure was the expected
  stale 104428 golden.
- Final full licensed suite: **885 passed / 2 failed**. The only failures are
  the documented stale snapshots for MethodDef 67525 and 104428; no new
  failures were introduced.

### Resume point

Review the fresh 104428 call arguments against the native stores at
`0x18072e410`–`0x18072e456`, then run a direct corpus sweep before considering
a golden update. MethodDef 67525 remains the
documented honest SIMD decline. The broad shared-body, indirect-call,
unknown/raw-memory, and unbound-temp inventories above remain open; this
follow-up fixes one producer family, not the whole census.

## Stop record — 2026-09-22, RSP-copy home round (unpromoted)

Subagent-proposed, human-implemented. Same rules: `final_out/`
untouched (its census above still stands), no snapshot regen, no
promotion, no rebuild. All `il2cpp/` edits via binary patches with
CRLF/no-BOM asserts; `tests/` edits LF (one pre-existing CRLF game
file kept byte-identical in endings).

### Source changes (`il2cpp/lifter/insn.py` only)

- `mov r64,rsp` now carries the frame offset (`_stack_offset` on a
  `?`-text ptr) instead of dropping to `None`, so `[copy+N]` keys slots
  by absolute address and aliases `[rsp+M]` of the same home. Wired
  through `_read_mem`, `_mem_lvalue`, and the `lea` address path;
  arithmetic/index/32-bit uses decline to the unknown-base shapes.
- RBP quarantine (stash-proven): the first cut tracked
  `lea rbp,[rsp-C]`-style frame offsets absolutely and split
  RBP-disp-keyed homes (80548 `int num2` became `object obj1` plus an
  unbound `num2`). RBP stays on the legacy frame paths byte-identically
  (MOV/LEA/load/store/indexed all skip RBP); `aggregates.py` reverted
  untouched. 80548 matches its golden again.
- `tests/test_recovery_completion.py` +4 portable (slot roundtrip +
  cross-delta alias, arithmetic/index/32-bit+RBP declines);
  `tests/test_game_frame_copy.py` new (+3 game: 117615 improvement,
  23900 same-typedef must-decline, both `?addr` extinctions);
  `tests/test_game_review83.py` sret pin evolved to the faithful
  spelling (old site-1 `(default,default,default)` was copy blindness;
  native passes three addresses at `0x182529283`–297).

### Method evidence (each `--mi` re-lifted, base-vs-new diffed)

- 117615 (`WriteInt32AtOffset`): `mem[8] = this;`/`mem_8`/raw twins
  become `this._offsetBits = offset;`/`this.WriteSlow(value, bits);`.
  One undeclared `obj6` phantom survives in the replayed finally tail
  (was three undeclared `mem[8]`/`mem_8`/`obj2`).
- 32837 (`Touchscreen.Reset`): golden holds 4 raw `mem[]` prologue
  spills (`mov rax,rsp` proven); actual drops them, renumber-only
  fallout. NEW red, consigned to regen.
- 108722 (sret): both native address-triples print; unobserved
  stand-downs stay pinned portably (unknown receiver/size).
- 104428: 11 raw `mem[]` spills removed (its golden holds `mem[8]`
  too); same already-red ID, still awaiting the gated-regen user call.
- 80548: quarantine restored the golden byte-identically.
- 82799/104380: the promoted tree's only two `?addr` hits
  (`store into untracked ?addr` in copy-heavy methods) render no
  `?addr` and no `mem[]` in fresh lifts; 82799's `return real2`
  residue is pre-existing (unbound in the old body too).

### Validation at stop

- `python -m compileall -q il2cpp il2csharp.py`: pass.
- Source-format assertions (`insn.py` CRLF/no-BOM): pass.
- `git diff --check`: pass.
- Portable suite: **765 passed** (761 + 4 new), 132 deselected.
- Game pins: `test_game_frame_copy.py` 3/3,
  `test_game_review83.py` 7/7 (with the evolved pin).
- Full licensed suite: **894 passed / 3 failed** — 67525 (honest SIMD
  decline) + 104428 (stale golden) were already red; 32837 is new but
  proved improvement (above). No other breaks.

### Resume point (superseded by r4c promotion — historical record follows)

Work order §4 was completed after this stop record: the unbound census
collapsed to 55 distinct tokens (all params/checker FPs in fresh
lifts) and the rename barrier + param exclusion fixed the producers.
Corpus was rebuilt + regened + promoted twice since (r4a, r4c);
`final_out/` census above is the r4c recount, not this stop record's
era. Remaining work is tracked in `docs/todo.md` Current work.

## Addendum — 2026-09-22, TODONOW #1 first slice (unpromoted)

Array receivers now resolve shared calls (subagent-mined mi 275/326/
4047: 9-candidate Clone fold → `System.Array.Clone` instance rendering;
mi 144 string twins pinned must-decline, 5 markers). Mechanism:
`Il2Cpp._system_array_td` + `Lifter._array_receiver_td` with a 2-line
fallback at all three chain-filter twins; sret/ctor/generic/unanimity
gates untouched. Portable + game pins green; full suite holds the
RSP-copy-round failure set byte-identically (32837/67525/104428 — none
of the four touched methods is in the golden set). Remaining #1 work:
slot/hint-typed receivers, indirect/interface dispatch, then
receiver-driven generic substitution (needs the synthetic table).

## Addendum — 2026-09-22, hinted receivers DISPROVED (reverted clean)

Side-table corroboration (`slot_types` vs per-pass `_type_hints`,
dual-agreement + closed-key) resolved `&raycastHit1`→`distance`
(25687) and `&taskAwaiter1`→`GetResult`/`IsCompleted` (24238) with
correct trims — then reverted with zero residue. Root cause, traced to
the instruction: resolving IsCompleted removed the ambiguous-shape
union-kill that used to clear the `s_50` home tile; the surviving tile
had been field-split by `_scalar_parts` (TaskAwaiter-typed RAX from the
already-resolved `GetAwaiter`), so the whole-struct reload projected
`.m_task` into the TaskAwaiter-typed `<>u__1` home — an ill-typed line
the suite cannot see (same IDs pass either way). Rule: hint-driven
resolution stays out until whole-struct reloads prefer whole tiles
(byte-range sidecar); the `_td_of`/array paths keep their pinned
behavior. Repro/diagnostic probes kept in Temp; post-revert lifts of
25687/24238 are byte-identical to the pre-hint baselines.

## Addendum — 2026-09-22, SIMD consumer-side recovery (unpromoted)

67525's constants died at: scalar-pool loads dropping bytes (vs the
PACKED128 `_bytes` attach) and `unpcklps` lane reads failing untyped,
then tail args reading `.text` only. Fix, tails-only: byte provenance
on scalar const loads + typed GPR-slot materialization at closed
all-float vector slots (house `(float2)(l0,l1)` for
Unity.Mathematics.float2; width-4 literal). 80548 stays intact
(PSRLDQ-popped/integer-tainted values carry no parts -- the guard).
Fresh: `clamp(x, (float2)(0.0f, 0.0f), (float2)(1.0f, 1.0f))`,
signature-exact where the golden scalars needed unprovable implicit
conversions -- golden regened (surgical, SHAs verified). Follow-up:
same gates wired into resolved direct calls via a shared helper
(67836 smoothstep renders composites, uncovered args stay unknown).
Suite 933/0. Open: per-arm Color, general packed tracking.

## Status — end of 2026-09-22 session (paused, tree clean)

Suite: **932 passed / 0 failed** (fully green; 67525 regened to the
signature-exact composite). Last source change: direct-call
float-lane materialization via shared helper (67836 renders
composites, uncovered args stay unknown). Reverted same day:
?-text tightening (rescued store miscompiled -- elision was honest,
now pinned by a game test).
`final_out/` holds the r4a tree (predates SIMD + direct-call);
next rebuild will carry them plus the ?addr-tightening revert
(net: SIMD/direct improvements only).
Open, hardest-first: field-provenance sidecar (designs + two
disproofs on file), general packed SIMD (80548-bounded), per-arm
Color (needs use→def), runtime-generated vtables (decline forever).
No blockers, no red tests, no uncommitted work.

## Addendum — 2026-09-22, unbound census + rename barrier (unpromoted)

Work-order §4 (classify before patching), done as a read-only text
tool (comment/string scrub, method regions, dominance = earlier line
at depth <= use): the ~8,700-token/~2,200-file upper bound collapses
to **55 distinct unbound tokens in 21 files**. Remainder by family:
lift-stage vN residuals (StreamBuffer v0-v7 et al.), tN oversize/bind
temps, SIMD type-position FPs (v128/v64/v256), and one obj-family case
fixed below. The census itself moves no gates.

The obj-family case (mi 124140 `AndroidJNI.IsSameObject`) forwarded
`(obj2, obj2)` for native `(obj1, obj2)`: `_seq` was correct and
`phi_alias` empty — `_rename_locals` had minted the dead spill as
`object obj1 = obj2`, shadowing the params, and `_copy_prop` merged
the argument. Fixed with `_semantic_local_names`' barrier (reserve
body identifiers + metadata params, bump until free). Portable + game
pins green; zero golden movement. The vN/tN residuals in the other 20
files are still open, now with exact file:line inventories.

## Addendum — 2026-09-22, param-exclusion rename (unpromoted)

The census vN family turned out to be renamed *parameters*:
StreamBuffer.WriteBytes(byte v0, byte v1) (mi 113041-113044)
rendered `this.buf[num2] = obj5` for native `v0` -- `_rename_locals`
rewrites vN tokens including metadata params while the emitter keeps
them, disconnecting every use. Rename targets now exclude every
metadata parameter spelling (a colliding lifter temp keeps its honest
lift-stage name instead of a silent capture). All four overloads
render fully bound; +1 portable / +4 game pins green; zero golden
movement (909 passed / same 3 IDs).

Follow-up: all remaining census residuals resolve as metadata
parameters (HashCode v1-v4, MeshVoxelizer, JValue, TimeSpan, Version,
JToken, TypeUtils, ExceptionBuilder, TMPro, GradientSettingsAtlas --
each verified bound in fresh lifts) except 5 SIMD type-position
checker FPs (v128/v64/v256 as types). The §5 actionable set is ~zero
in fresh lifts; +2 game pins (1935, 79519).

## Addendum — 2026-09-22, interface dispatch slice (unpromoted)

TODONOW #2 first blood, subagent-mined: `GameManager.CheckAllReady`
(mi 25368) carries three back-to-back interfaceOffsets searches that
resolve to GetEnumerator/MoveNext/get_Current exactly (the ground
truth `dec/flow.py` cites). They missed on three decline-preserving
defects, all fixed: slot-line decl prefixes at render stage, the
typeof-reference span ending at the slot instead of the call, and
`_N` display arity vs `` `N `` metadata names (exact-first, fallback
for generic displays only). Full body diff is resolutions + dead
scaffold DCE + one consistent rename; zero `/*indirect*/` remains in
the method. Portable + game pins green; full suite holds the failure
set byte-identically (same 3 IDs). Open #2 remainder: vtable occupants
on abstract bases (needs store provenance -- do not touch without it),
receiver-driven generic substitution (synthetic table).

## Addendum — 2026-09-22, generic slice closed without patch

Designed (extractor + hook + inflated-chain swap) then empirically
closed: 23762's homes already close via the MethodRef slot path,
closed-generic bases never reach `_field_expr` there (0 hits traced),
and corpus mining found zero hook-shaped sites (open result +
correctly-attributed closed receiver + pure-result fix) -- the 9
open-result sites need use→def consumers, 24679/109849 are
misattributed field lanes, the 187 family is already fine.
`selectable1`/`obj17`/`obj11` need sidecar/SIMD-lanes/use→def
respectively (documented). Deferred with the hinted round; no
invisible infra shipped.

## Addendum — 2026-09-22, boxed-bool fold (unpromoted)

The interface round left `object obj32 = obj5.MoveNext();
if (obj32 == null)` -- dead (boxed bools are never null) and wrong on
false (native `test al,al` breaks). `_name_interface_dispatch` now
records bool-returning resolutions; `_boxed_bool_null_fold` runs last
(single `object X = <call>` decl, all-uses-bool via `_bool_use_ok`, no
reassign/address-take, standalone heads; no inlining, no renames).
Folds in 8 methods (25368, 24059, 25132, 25872, 26880, 27213, 97399,
105906); unbox/`&` uses and ref-null tests decline. Portable + game
pins green; full suite holds the failure set byte-identically (same 3
IDs, zero golden movement).

## Addendum — 2026-09-23, InventoryManager audit (15 findings)

| # | Category | Count / Location | Notes |
|---|----------|------------------|-------|
| 1 | Unresolved sub_ decompiler stubs | 27 unique, 419+ calls | Shared IL2CPP generic bodies (array getters, singleton getters, coroutine wrapper, GetComponent). Harmless but need manual relabeling for readability. |
| 2 | image3 uninitialized-branch bug | UpdateInventorySlotsUI, ~line 445 | Fixed in decompiler source 2026-09-23: distinct native array-element loads now receive a join phi; both receiver and sprite are assigned on both arms. The promoted r4c tree still shows the old output. |
| 3 | Unvalidated RPC input | Rpc_ChangeItemStorage/Rpc_CMD_ChangeItemStorage | No bounds/range check on invSlot, value, value2 before array write; client predicts locally first. |
| 4 | God-class architecture | whole file, 403 fields, 16,380 lines | Weapons, mop, trash, UI, and 40-item placement system all crammed into InventoryManager. |
| 5 | Hardcoded per-item Template/TemplateRed fields | 204 ...TemplateRed field declarations | Should be a dictionary/ScriptableObject-driven table instead of ~100 hand-declared Transform pairs. |
| 6 | String-typed, hash-compared item RPC | PlaceItem/Rpc_CMD_PlaceItem, 29 distinct big-int hash comparisons (num1 != 39xxxxxxxxx) | Compiled from a switch(type) on string literals; fragile, no compile-time safety, wastes bandwidth sending strings over the wire. |
| 7 | Empty decompiler noise blocks | 200 if (X.initialized == 0) { } stubs, 18 il2cpp_codegen_initialize_runtime_metadata/il2cpp_object_new manual exception-construction blocks | Purely decompiler scaffolding for type initializers and thrown exceptions (e.g. the NotSupportedException in IEnumerator.Reset()); safe to ignore/strip when cleaning up. |
| 8 | Dead/empty conditional | IsValidItemIndex, if (data_183e71c21 == null) { } | No-op branch, leftover static-field init check. |
| 9 | Reference-vs-null array comparison | IsValidItemIndex: StoreManager.__field_Instance.pickupObjs != 0 | Should read as != null; decompiler rendering artifact, not a runtime bug. |
| 10 | Pointless array re-fetch in loop | UpdateInventorySlotsUI, animatorArray1 = this.inventorySlots; re-assigned every iteration | Bounds-check codegen noise, no functional effect, just visual clutter. |
| 11 | Raw unsafe pointer/offset RPC serialization | 419 occurrences of (byte*)/(int*) casts with hardcoded offsets like +0x1c, +0x24 | Normal Fusion RPC codegen, but brittle: any change to SimulationMessage layout or Fusion version silently breaks these offsets. |
| 12 | Bare catch with manual SetException | 1 occurrence, in _Rpc_CMD_PlaceItem_d__288.MoveNext | Swallows the real exception type — typical of decompiled async/IAsyncStateMachine machinery, not something you'd write by hand. |
| 13 | 6 manual NotSupportedException/NotImplementedException throws | e.g. _StopIgnore_d__242.Reset() | Standard IEnumerator.Reset() boilerplate — expected, not a real issue. |
| 14 | Only 11 Debug.LogError guard rails across 16k lines | scattered | Very sparse defensive logging for a class this large and this networked — most array/index accesses have no bounds guard beyond the few IsValidItemIndex call sites. |
| 15 | Inconsistent field naming | inventorySprites vs inventorySprites_ | Trailing underscore suggests a renamed/duplicated field the original devs never cleaned up; easy to swap them by mistake (as arguably happened in issue #2). |

## Addendum — 2026-09-23, session handoff

Three fixes are committed and pushed: join receiver phi (`2481c16`),
paired float Jcc flags (`14e2ae0`), and complete branch-chain local
hoist (`1920c71`). The follow-up scalar parameter-copy inference and
tests are still uncommitted: 30 focused tests passed, while the full
suite was interrupted near 69% and has no final result. Resume from
`docs/handoff-2026-09-23.md` before landing it. The unregistered
`sub_1804cdb00` audio scalar result remains open; do not guess its
identity or regenerate the promoted output.

## Addendum — 2026-09-24, stub code + forwarder returns + r8 ACS

Three source changes landed since (all committed and pushed): shared
stubs list their address's first native instructions as comments (throw
preserved), identical-render method twins collapse to the first row (70
sites), and noreturn-shared `call; int3` forwarders render
`return Target(args)` (all 63 `/* nothing */` in `Arm.cs` Neon).
`final_out/` Assembly-CSharp promoted to r8 (4 files differ vs r7:
ComputeStringHash x3 + stub comments; evidence in
`validation_reports/promotion_r8.json`); rest of tree holds r7. Full
suite: 1013 passed / 0 failed (836 portable + 177 game). Open, by
payoff: same-name multi-owner receiver pick (~1.5k sites), static/
instance+arity ToString/op_Implicit (865 sites, 1 VA), constant-zero
fold (239 sites, 2 VAs). Census table above still scans the r4c/r7
eras; fresh counts live in `docs/todo.md` Current work.
