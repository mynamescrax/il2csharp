## 0aj. Batch 56 (2026-08-24, todo lead #3's largest residue bucket: an
icall thunk-cell call is a call to a KNOWN method, and the identity had
been in hand -- and thrown away -- since the cache scanner was written)

**`b66_out1` is the gated candidate.** Gate **0/0/0**, held.

**How the lead was picked, and why the bucket names in it were not
trusted.** todo lead #3's residue list was a batch-38 census
(bare-temp 2,206 / obj-vtable-0 1,570 / constant-slot klass-walk ~2,400
/ invoke_impl 585 / data_* 181), eighteen batches stale. Re-censusing
first (`work/census_b65_indirect.py`, buckets every `/*indirect*/` line
by the SHAPE of the callee expression) read, at b65_out1 over 13,808
lines:

    6,259  the callee is an already-resolved `Type.Method` path
             4,955 Unity `*_Injected` icall bindings
             1,304 other resolved names
    3,904  klass-slot vtable dispatch  (`... + 0x138 + 16N)[0]()`)
    2,209  bare temp -- a genuinely unknown function pointer
      626  delegate `X.invoke_impl(X.method_code, ...)`
      494  obj-vtable-0 deref
      315  other constant deref

The largest bucket -- 45% of the whole residue -- **was not in the lead
at all**, and it is not "indirect" in any sense: the name was already
fully resolved and printed, as if it were an unknown pointer, in front
of an untrimmed argument list:

    object obj17 = Event.set_Internal_keyCode_Injected() /*indirect*/(
        this.m_Ptr, value, obj7, obj8, obj10, obj12, obj14, obj16);

Ground truth, `UnityEngine.Event.set_Internal_keyCode` @0x182C48660 --
the whole method is the icall thunk:

    182c48682  mov  rax,[183E859F0h]      <- the icall cache cell
    182c48689  test rax,rax
    182c4868c  jne  short 182C486A1h
    182c4868e  lea  rcx,[1830F72E0h]      <- "UnityEngine.Event::
    182c48695  call 180435710h                set_Internal_keyCode_Injected
    182c4869a  mov  [183E859F0h],rax          (System.IntPtr,UnityEngine.KeyCode)"
    182c486a1  mov  edx,edi               <- 2 real argument registers
    182c486a3  mov  rcx,rbx
    182c486b0  jmp  rax

`Il2Cpp.scan_icall_cache` has mapped CELL -> signature string since it
was written (2,285 cells), and `_icall_annotation` already resolved
2,268 of them (99.3%) to a real MethodDef -- **it just returned the
rendered text and dropped the index.** `_read_mem` therefore handed
`_call` a plain `obj`, `mi` stayed None, and every downstream
consequence followed from that one missing field.

**Fix 66** (`work/patch_b66_icallname.py`) carries the resolved
MethodDef through `_icall_annotation` -> `decode_slot` -> `_read_mem`
(as an `fptr` Expr with a new `Expr._mi` slot) into `_call`, where it
seats `mi`/`name`/`rty` exactly the way the VIRT_CALL block seats a
resolved vtable slot. That single assignment puts the site on the
ordinary resolved-call path -- the arity trim, `_hint_arg_types`,
`_positional_args`, fix 54's byref/`ref` render, the sret fold and the
property-accessor fold, none of which a callee with `mi is None` can
reach. It adds no guess: the cell's contents are proven by the
signature string that fills it, the same evidence the printed text
already rested on. Deliberately gated on `method` being present, so a
signature that does not resolve keeps the honest
`Type.Method() /*indirect*/(...)`.

**Fix 66b**: `Il2CppTypeDefinition.declaringTypeIndex` is a TYPE index,
not a typedef index, so a nested signature
(`UnityEngine.ParticleSystem/MainModule::get_duration`) matched
nothing. `types[32550]` is `(16560, 0x120000)` and `typedefs[16560]` is
`UnityEngine.ParticleSystem`; resolve through that. Cells resolving
**2,268 -> 2,285 of 2,285**. Noted and NOT fixed here: `typedef_full`
itself has the same bug (its `while 0 <= d < len(typedefs)` walk tests
a type index against the typedef count, so EVERY nested type comes back
as a bare `MainModule`), but it also feeds type-NAME rendering at
il2csharp.py ~1032 and ~1079 -- qualifying it is a tree-wide output
change and belongs in its own batch, not smuggled in behind an icall
fix.

**Fixes 66c/66d were forced by 66, and are the wider-reaching half.**
`jmp reg` carries `('stop',)` from CFG build (a real jump table
overwrites it in `_prewire_switches`) and **`'stop'` emits NOTHING**.
The exec-side handler at decompiler.py ~1053 does set `b.ret` from
RAX/XMM0, but only `b.term[0] == 'ret'` ever reaches the `return %s;`
line, so it was never printed. That was survivable only because such a
call always left a statement behind: with `mi` unknown, `_call`'s
unresolved-return path BINDS the result and the text at least appeared.
Resolve the callee and `rty` is known, `_call` takes
`self.regs[dstreg] = Expr(call, ...)` instead -- and the entire call
vanished from the output. `Event.get_Internal_keyCode` went from a
bound `object obj20 = ...` to nothing at all before 66c, and to
`return UnityEngine.Event.get_Internal_keyCode_Injected(this.m_Ptr);`
after it. A tail jmp leaves for good, so the callee's value IS this
method's value.

**Fix 66d** is two bugs found on the next case tried,
`ParticleSystem/MainModule.get_duration` @0x182C80520, which 66 + 66c
rendered as `return obj1;` with obj1 defined nowhere:
  * `rv = L.regs.get('RAX') or L.regs.get('XMM0')` takes RAX
    unconditionally, and `_call`'s `_fresh_unknowns` re-mints RAX on
    every call -- so a float-returning tail call read a fresh `vN`
    (correctly declined by the `^v\d+$` filter) while its real value
    sat in XMM0 where Win64 puts it. Choose the register from the
    method's own return type.
  * `_analyze` lifts the SAME `Block` objects twice (dry pass, then
    real). The dry pass had stored a materialized `t1000` -- which the
    `^v\d+$` filter does NOT match -- so declining in the real pass left
    both the stale `b.ret` and the `('ret',)` 66c had set, and that
    stale text is what printed. Decide the terminator in the same pass
    that decides the value.
With both halves the method reads `return this.duration;`, which is the
original C#.

**Numbers.** Gate **0 bad / 0 ERROR / 0 MISSING**, held (the corpus has
had an empty bad-file set since batch 53, so there is no legacy noise
left to hide a regression in). Brace 0/11,107. Full-corpus sweep
crashes **0**, brace 0, into_block 13,505/2,978 -> **13,506/2,978**
(+1 site; 66c changes a terminator, so it is not strictly CFG-neutral,
but nothing structural moved), sweep lines 2,012,814 -> 2,010,848. Tree
lines 2,721,268 -> **2,719,896 (-1,372)**. **946 of 11,107 files
differ.** Switch statements 758, case labels 10,295, surviving raw
table loads 25 -- all unchanged, as expected.

**`/*indirect*/` 13,808 -> 7,538 (-45.4%)**, the largest single move
that marker has ever had (batch 45's interface naming was -8.3%).
Re-censused after: `icall _Injected` 4,955 -> **0**, `named
Type.Method` 1,304 -> **26**, and those 26 are `FunctionPointer<T>.
Pointer` (Burst) -- a real runtime function pointer field with nothing
in metadata to resolve, correctly left honest. The untouched buckets
are unchanged by construction: klass-slot 3,904 -> 3,901, bare-temp
2,209 -> 2,175, invoke_impl 626, obj-vtable-0 494.

**read-before-def 118,917 -> 111,050 (-6.6%)**, across 31,012 -> 29,942
methods and 4,828 -> 4,776 files. That is the metric this batch really
moved: the trimmed junk arguments were undefined temps by construction.
`Event.cs` (1,549) and `CommandBuffer.cs` (1,218) left the worst-files
list entirely.

**Reading the diff.** 946 files is wide because 66c reaches every
resolved indirect TAIL call, vtable and interface dispatches included,
not only icalls -- and a method that used to end with no return at all
now ends with one, which the structurer then re-shapes. Three read
end to end:
  * `TriangleMeshNode.GetVertexArrayIndex` gained
    `return obj19;` after an interface tail-dispatch whose value had
    been dropped on the floor.
  * `AILerp.shouldRecalculatePath` went from
    `if (!(this.canSearchAgain)) { return 0; }` with a silently-empty
    other arm, to `if (this.canSearchAgain) { return this.autoRepath.
    ShouldRecalculatePath(this); } return 0;` -- the condition inverted
    because the non-empty arm now comes first. The real source is
    `canSearchAgain && autoRepath.ShouldRecalculatePath(...)`.
  * `CompareInfo.GetCompareInfo(string)` gained
    `return obj1.CompareInfo;`.
A line-class census over all 946 files reads REM `/*indirect*/` 6,365 /
ADD 95, and every one of those 95 is a MOVE (an unresolved klass-slot
call re-indented into a newly-shaped arm), which the -6,270 net
confirms.

**Goldens 19 -> 20**, and the one new mismatch is this batch's own:
`VFXEventAttribute.HasInt@182f7c410`, `object obj17 = ...
HasInt_Injected() /*indirect*/(this.m_Ptr, nameID, obj7, obj8, obj10,
obj12, obj14, obj16);` -> `return UnityEngine.VFX.VFXEventAttribute.
HasInt_Injected(this.m_Ptr, nameID);`. The other 19 are the documented
pre-existing drift. **New unit mirror `work/icall_test.py` (10 cases:
four on resolution -- including one pinning that an unresolvable
signature must NOT claim an identity, which is what keeps the honest
marker -- and six full-body renders read against disassembly).** All
other mirrors unchanged: hoist 20, elseif 13, cse 30, flag 22, cp 20,
selfcopy 5, forhead 10, itfdispatch 14, refarg 24, lastdef 22,
callparen 7, flagcond 26, callname 21, re 14, jumptable 9.

## 0ai. Batch 55 (2026-08-24, todo lead #10's residue -- and the
wrong-output bug hiding underneath it: the sparse form's byte GROUP
TABLE is the switch's case map, and nothing had ever read it as one)

**CLOSES todo lead #10 entirely.** `b65_out1` is the gated candidate.

**First, a correction to the lead's own residue text: the `no_lea 8`
bucket does not exist.** All eight of those sites have a reachable
rip-relative `lea` for the table base -- 11, 25, 27, 30, 31, 58 and 123
instructions back -- and fix 64 finds every one of them.
`work/census_b63_tables.py`'s `classify()` mirrors the recognizer with
its OWN lookback, which was still 6 instructions; fix 64 (batch 54)
widened the real walk to unbounded and made the mirror stale, so it
reported `no_lea` for sites that were really `short`. The lead's
prescribed fix for that bucket ("recognise that `add rJ,base` implies
base == the image base... the honest general fix, which would subsume
fix 64") was therefore aimed at a phantom, and **no image-base fallback
was written: nothing needs one.** The mirror is corrected to the
unbounded walk, with a comment saying not to re-narrow it. This is the
second time in three batches that lead #10's own guess about the
mechanism was wrong and instrumenting the recognizer is what found the
truth (§0ag, §0ah); the transferable lesson is §0af's -- a mirror that
duplicates production logic is a metric that can rot silently.

The one genuine reject left corpus-wide is JsonParser.Equals
0x1825B3200, whose `jmp rax` comes off `mov rax,[r8+138h]` -- a virtual
tail-dispatch, not a table. It must keep being rejected.

**Fix 65a -- the bounds check must be the NEAREST one, not the first in
the window.** `_jump_table`'s `cmp idxreg,N; ja default` scan walked its
window FORWARD and took the first hit. MSVC emits a chain of range
guards before a dispatch, so the first `cmp` on the index register is
routinely an unrelated earlier test: CookieParser.Get 0x1824E70E0 has
`cmp eax,1; jne` ten instructions before its real `cmp eax,0Ch; ja`, so
a 13-entry table was capped at 2 and then killed by the `< 3` floor.
Same shape at LoadBalancingClient.CheckIfOpAllowedOnServer (0x180831AA0,
0x181FE59E0 -- 15 entries each) and HID.DetermineLayout 0x18268AB70.
Scanning the same span BACKWARD takes the guard that actually dominates
the table computation. The scan now also follows the index through
register copies: ScanReserved 0x18214D990 does `movsxd rax,ecx` between
the bound and the table, so `cmp ecx,39h` was invisible to a scan
looking only for `cmp rax,N` and no bound was found at all.

**Fix 65b -- expand the jump table THROUGH the group table.** A sparse
switch is `movzx idx,byte [base+op+G]; mov rJ,[base+idx*4+T]; add
rJ,base; jmp rJ`: the group table maps each OPERAND value to a
jump-table slot. The old code read it only to recover the operand
register for the `switch (...)` subject, then emitted `case 0:`, `case
1:` ... off the jump table's own slot index -- so **the case labels were
slot numbers, not operand values, on every sparse dispatch in the tree,
including the ones that were already structuring fine.** Ground truth
HID.DetermineLayout 0x18268AB70, group table `00*9 01 02 02 02 03 03 02
00*6` over `usage - 0x30`: Unity's published InputSystem source maps
GenericDesktop.HatSwitch (0x39, the tenth operand value) to the Dpad
check, and this printed it as `case 1`. Expanding to one entry per
operand value makes the sparse form identical to the dense one
downstream -- `_emit_switch` already collapses targets shared by several
case values into one section with stacked labels, so it needed no change
-- and the labels now mean what they say.

The same expansion gives the table its EXACT length (max(group)+1), which
the `lo <= tgt < hi` address walk structurally cannot find: MSVC lays the
group table immediately AFTER the jump table, so the walk reads the first
group bytes as the next "entry", lands outside the method and stops.
That is why all twelve `short` sites decoded 1 or 2 entries. Ground truth
Mono.Security Alert.inferAlertLevel 0x181ABBE40: ONE jump-table entry
(0x181ABBE56) and 22 all-zero group bytes -- a legitimate switch whose 22
cases share one target. Expanded it is 22 in-range entries and clears the
`< 3` floor on its own merits, so **the floor did not have to be relaxed
at all** -- it still guards the plain form, which has nothing else
bounding it. The expansion is used only when it validates end to end (a
bound was found, the two tables provably do not overlap, and all
max(group)+1 slots decode inside the method's own extent); anything short
of that falls back to exactly the old read, floor included.

**Fix 65c -- a pruned switch target must not renumber the cases after
it.** Found by reading 65b's output diff, not predicted by anything.
`_prune_nonreturning` drops edges into throw stubs, and for a switch it
FILTERED the target list -- but a case value is that entry's POSITION in
the list, so dropping slot 1 renumbered every case after it down one.
Harmless while the labels were meaningless slot numbers; corrupting the
moment 65b makes them real operand values. The slot is now blanked in
place, which `_emit_switch` already skips (its `ip2bid.get(tip,-1) < 0`
guard). This is live on DENSE tables too and is most of the label churn
in the b64->b65 diff: LightUnitUtils.ConvertIntensityInternal
0x1828E9460 went from cases `0,1,4 / 2,3,5` to `0,2,5 / 3,4,7` because
slots 1 and 6 lead to throw stubs -- and the new grouping is the
semantically coherent one (punctual light types together, area light
types together; the old one had Point and Rectangle in the same arm).

**Gate: `0 bad / 0 ERROR / 0 MISSING`, HELD** -- batch 53 took this
corpus to a fully clean parse and this batch keeps it there, which is
the only acceptable result now that there is no legacy noise to hide in.
Brace audit 0 unbalanced / 11,107. Full-corpus sweep: **crashes 0**,
brace_unbalanced 0, into_block 13,815/2,960 -> **13,505/2,978** (-310
sites), lines 2,012,429 -> 2,012,814. Goldens: 19 failures, **the same 19
by name** as the documented pre-existing drift -- this batch moved NONE
of the 50, same as batches 52, 53 and 54 (the suite holds no switch-heavy
body; that is a known sample-size limit, §7).

Tree numbers, b64_out1 -> b65_out1 (11,107 files both):
* **switch statements 721 -> 758 (+37)**, case labels **9,052 -> 10,295
  (+1,243)**. The label jump is mostly 65b's expansion printing one label
  per operand value (InputExtensions.IsTextInputKey alone is 127) and is
  expected; the switch-statement count is the number that tracks
  recovered dispatches.
* surviving raw table loads **52 -> 25 (-52%)**, `/*indirect*/` 13,845 ->
  13,808.
* tree lines 2,720,887 -> 2,721,268 (+381 only -- the recovered case
  bodies roughly pay for themselves against the garbage they replace).
* read-before-def **118,938 -> 118,917 (-21)**, i.e. flat: the newly
  recovered code is well typed, no new undefined temps.
* **89 of 11,107 files differ** -- parsers, tokenizers and state machines
  (System.Xml, System.Data, Newtonsoft.Json, RegularExpressions,
  InputSystem, UIElements, DateTimeParse/Format), byte-identical
  otherwise.
* longest consecutive case-label run 57 -> 64, so the expansion has no
  pathological blow-up anywhere in the corpus (the code caps a derived
  count at 512 slots regardless).

Recognizer buckets on the same input set (`work/census_b63_tables.py`
over b63_out1, ~17s): b63 `no_lea` 77 / `ok` 22 / `short` 12 -> b64 `ok`
92 / `short` 12 / `no_lea` 8 -> **b65 `ok` 111 / `short` 1**, and that
one is JsonParser.Equals, which is not a table.

New unit mirror: `work/jumptable_test.py` (9 cases, ~7s) pins the decoded
shape of eight real dispatches plus the DetermineLayout case map against
Unity's published source. Unlike the other mirrors in `work/` it needs
the binary loaded (a jump table only exists there), the way
`test_goldens.py` does.

Artifacts: patch `work/patch_b65_grouptable.py` (carries the full OLD/NEW
text, so the revert for an A/B isolation is exact); probes
`work/probe_b65_tables.py` (disassembly window per residual site) and
`work/probe_b65_decode.py` (the same sites at the number level -- base,
table VA, cap, group VA, the entries walked and where the range break
stops); tree diff `work/census_b65_switch.py`; census
`work/census_b65_tables.txt`; unit `work/jumptable_test.py`; build
`work/run_build_b65.py` + `work/build_b65.log`; sweep
`work/sweep_b65.txt`; gate `work/ts_gate_b65_out1.txt`; re-lift helper
`work/relift_b65.py`.

Promotion over `final_out/` is a human call per the standing rule
(§0/§6).

## 0ah. Batch 54 (2026-08-24, todo lead #10's SECOND cause: MSVC emits
one `lea rB,[rip+image_base]` per function and reuses it for every jump
table in it -- the table-base lookback was 5 instructions)

Batch 53 fixed the decode window and left lead #10's text residue almost
untouched (table-load sites 176 -> 174). That was the signal that the
window was one cause among several, so this batch built the tool the
lead should have had from the start.

### The tool, and a mistake worth recording

`work/census_b63_tables.py` buckets every `jmp reg` by
`_jump_table`'s OWN rejection reason -- the text census (`grep -rc
data_180000000`) says how many sites survive but never why.

**The first cut of it walked all 88,976 methods and was killed at 35
minutes.** The rewrite is driven from the BUILT TREE: scan the rendered
`.cs` for the raw-table-load shape, map back to VAs through the
`// RVA: ... VA:` markers, and decode only those ~68 methods. Same
answer in **17 seconds**. The lesson generalises past this script -- a
census whose question is "why did this site fail" only needs the sites
that failed, and the corpus-wide walk is a reflex worth resisting. The
docstring says so, so nobody widens the input set back by accident.

At `b63_out1`, before this batch's fix: **`no_lea` 77 / `ok` 22 /
`short` 12 / `window` 0**. (`window` empty confirms fix 63a emptied its
own bucket.) `no_lea` means the index load was found and the table-base
register identified, but no rip-relative `lea` for it exists in the
5-instruction lookback.

### Why the lea isn't there

CurrentDayManager.PlayNextOccurence, 0x1806A6000:

    1806a6924: lea rdx,[rel 180000000h]     <- the ONLY lea in the method
    1806a692b: mov eax,[rdx+rax*4+6A7348h]  table 1 -- recognized already
    1806a6932: add rax,rdx
    1806a6935: jmp rax
    ...  45 instructions of table 1's case bodies, several of which
    ...  write EDX on their own paths ...
    1806a69c6: movsxd rax,[rbx+0B4h]
    1806a69cd: cmp eax,5
    1806a69d0: ja   1806A6BF0h
    1806a69d6: mov ecx,[rdx+rax*4+6A737Ch]  table 2 -- rejected
    1806a69dd: add rcx,rdx
    1806a69e0: jmp rcx

MSVC loads the image base once and reuses the register for every
dispatch in the function. Table 2's dispatch is reachable ONLY through
table 1, so RDX does still hold the base there -- but that is a
DOMINANCE fact and `_jump_table` runs over a flat instruction list with
no CFG. Same shape at DateTimeFormat.ExpandPredefinedFormat (three
tables off one `lea r12`), DateTimeParse, RuntimeType, JsonTextReader.

### Fix 64

`work/patch_b64_leareuse.py`. When the 5-instruction window has no
`lea`, keep walking back for the nearest earlier `lea tabreg,[rip+X]`.

The soundness argument matters here, because a linear backward walk is
NOT dominance and the intervening case bodies genuinely do clobber the
register on paths that never reach the second dispatch:

* **It cannot regress a table that works today.** The walk stops at the
  NEAREST match, so wherever a lea sat inside the old window it still
  wins and the result is identical; the longer range is only reached
  where the old code already returned `none`.
* **Everything downstream validates the guess.** A wrong base fails
  `va2off` outright or yields fewer than 3 targets inside the method's
  own [lo, hi) extent. Three consecutive dwords decoding to addresses
  inside this very method by accident is not a thing that happens.
* The independent `cmp idxreg,N` bound still caps the entry scan.

An intervening-write guard was considered and **rejected**: it would
reject the ground-truth case above, whose whole point is that the
clobbers sit on paths that do not reach the dispatch.

Second half of the patch: the `cmp idxreg,N` scan spanned
`min(k2, k) - 10 .. k`, which with a far-away lea would sweep the whole
function looking for a bounds check. Floored at `k - 12` -- exactly
behaviour-preserving for the old near-lea case (k2 >= k-5 > k-12, so the
floor never binds) and local for the new one, where the bound test always
sits immediately before the load.

Buckets after: **`ok` 92 / `short` 12 / `no_lea` 8**
(`work/census_b64_tables.txt`).

### Gates

* **Parse gate stays `0 / 0 / 0`** (`work/ts_gate_b64_out1.txt`, 11,107
  files). Batch 53 emptied the bad-file set, so this batch had nowhere
  to hide: any bad file at all would have been its own regression.
* Brace audit 0/11,107. Full-corpus sweep **crashes 0**,
  brace_unbalanced 0; sweep lines 1,996,071 -> 2,012,429; into_block
  12,950/2,928 -> 13,815/2,960 (+865/+32) -- the honest cost of
  structuring dispatches that previously rendered as one expression.
* **66 of 11,107 files differ**, and they are exactly the shape the
  mechanism predicts: parsers, tokenizers and state machines with
  several switches per method (RegexParser/RegexInterpreter/RegexWriter,
  DateTimeParse/DateTimeFormat, XmlTextReaderImpl and eight more
  System.Xml files, JsonTextReader, ExpressionParser, ComputedStyle,
  CurrentDayManager).
* **Switch statements 559 -> 721 (+162); case labels 6,528 -> 9,052
  (+2,524); `/*indirect*/` lines 13,941 -> 13,845 (-96)** -- the -96
  are degraded dispatches that became real switches. Tree lines
  2,704,529 -> 2,720,887 (+16,358). Per-file: ComputedStyle.cs 10 -> 33
  switches (6,340 -> 10,537 lines), DateTimeParse.cs 4 -> 7,
  RegexParser.cs 3 -> 6.
* **read-before-def 118,931 -> 118,938 (+7)** -- essentially flat under
  +16,358 lines of newly recovered body, which says the recovered code
  is well typed rather than a fresh pile of unknowns.
* Goldens 19, the same 19 by name -- moved none of the 50. All 14 pass
  unit mirrors green. Build 751.0s, 115,658 bodies, 0 failed.

### Ground truth read

`CurrentDayManager.PlayNextOccurence` now renders
`switch (this.curDay)` with a nested `switch (this.curOccurrence)`
inside its `case 2:`; `DateTimeFormat.ExpandPredefinedFormat` recovered
all three of its switches off the one `lea r12`. In the built tree,
DateTimeParse's format-character dispatch reads `switch ((obj5 - 0x6f))`
-- 0x6F is `'o'`, and the subject matches its `lea eax,[rcx-6Fh]`
exactly -- with real `"yyyy'-'MM'-'dd'T'HH':'mm':'ss.fffffffK"` string
literals in the arms.

### The residue, read against disassembly rather than guessed

Both surviving buckets are the SPARSE GROUP-TABLE form
(`movzx eax,byte [base+idx+G]` picking a group, then
`mov ecx,[base+eax*4+T]; add rcx,base; jmp rcx`), which `_jump_table`
already claims to handle.

* **`short` 12 is a `len(entries) < 3` FALSE REJECT** -- the floor is
  the bug, not the lea. Mono.Security's Alert 0x181ABBE40: the jump
  table at 0x181ABBE98 holds exactly ONE entry (0x181ABBE56) and the
  22-byte group table at 0x181ABBE9C is all zeros -- a legitimate
  switch whose 22 cases all reach one target. CodeIdentifier
  0x182356A70: two entries and a 30-byte 0/1 group table. When a group
  table is present the case count is bounded by IT and by `cmp idx,N`,
  not by the entry count, so the `< 3` floor rejects correct tables.
  Relax it only under those two conditions; the plain form has nothing
  else bounding it and must keep the floor.
* **`no_lea` 8** -- same shape, but the base register (`r14` at
  CodeIdentifier 0x182356BAC) has no rip-relative lea anywhere in the
  method's decoded extent. A longer walk will not find it. The honest
  general fix, which would subsume fix 64 entirely, is to recognise
  that the `add rJ,base` form implies base == the image base and
  validate against the binary's own image base instead of searching
  for a lea at all.

Artifacts: patch `work/patch_b64_leareuse.py`; census
`work/census_b63_tables.py` + `work/census_b63_tables.txt` (before) and
`work/census_b64_tables.txt` (after); build `work/run_build_b64.py` +
`work/build_b64.log`; sweep `work/sweep_b64.txt`; gate
`work/ts_gate_b64_out1.txt`.

## 0ag. Batch 53 (2026-08-24, todo lead #10: jump-table dispatch. The
recognizer was never the problem -- the DECODE WINDOW was. Gate
2/2,206/4 -> **0/0/0**, the first fully clean parse this corpus has
ever had, and sweep crashes 2 -> 0)

### The lead, and why its own framing was wrong

todo lead #10 said 1,051 lines / 109 files render a jump-table dispatch
as a raw table load plus an indirect call, and guessed: "most likely an
unrecognised ADDRESSING form reaching `_prewire_switches`, not missing
machinery: find why the pattern does not match the prewire's recogniser
before writing anything new." That instruction was right, and the answer
it produced was that the recogniser never SAW the table.

The motivating site, `InventoryManager.Update`'s item-use switch, is
textbook MSVC image-relative form B, exactly what `_jump_table`'s
docstring already claims to handle (disassembly, `work/probe_disasm.py`
+ the flat-window dumper):

    1806ead0f: movsxd rax,[rdi+108h]        ; this.holdingIndex
    1806ead16: cmp    eax,3Bh               ; the 60-entry bound
    1806ead19: ja     1806F9A1Ah            ; default -> epilogue
    1806ead1f: lea    rdx,[rel 180000000h]  ; image base
    1806ead26: mov    ecx,[rdx+rax*4+6FAC50h]
    1806ead2d: add    rcx,rdx
    1806ead30: jmp    rcx

Every clause of the recogniser matches it. `reg_name` already
canonicalizes ECX/RCX to one family name, so the 32-bit load is not the
issue either. What fails is one line further down: `lo <= tgt < hi`.

`Decompiler._decode` read `end = min(nxt or (va + 0x10000), va +
0x10000)` -- a flat 64KB window, hard-capped even when
`next_method_start` says the method is bigger.
`InventoryManager.Update` runs 0x1806E9CA0 -> 0x1806FAD40, **0x110A0
bytes**, so the window cut it at 0x1806F9CA0. Its table lives at
0x1806FAC50 and its 60 targets run 0x1806EAD51 .. 0x1806FA9BB --
entry[0] is 0x1806FA9AE, already past the cut. The entry scan broke on
the FIRST entry, `len(entries) < 3` returned `none`, the `jmp rcx`
degraded to an indirect tail call on the raw table load, and the whole
60-case body vanished:

    object obj224 = ((byte*)(data_180000000) + this.holdingIndex*4
                     + 0x6fac50)[0]
                  + data_180000000() /*indirect*/(...);

156 rendered lines for a 70KB method. This is a wrong-output bug of the
worst kind -- it looks like a rendered method.

### Fix 63a -- widen the decode window, but only on proof

`work/patch_b63_window.py`. `_decode` now decodes the 0x10000 window
first and re-decodes ONCE up to the method's true upper bound
(`next_method_start`, hard-capped at `DECODE_WINDOW_MAX` = 0x40000)
**only when the reachability trace actually followed a branch or a
jump-table entry into [window_end, bound)**. Three details carry the
soundness and the cost:

* the trace loop moved out into `_trace_reachable(raw, va, bound)`,
  which returns `(kept, overflowed)`. `overflowed` is set at each of
  the three places a target is followed (conditional branch,
  unconditional branch, jump-table entry) when `idx` does not have the
  target AND it lies in [win_end, bound). A target below `win_end` that
  is missing from `idx` is mid-instruction misalignment, not overflow,
  and correctly does not trigger a retry.
* `_jump_table` is called from the trace with `bound`, not the window
  end. This is the half that matters: a table whose entries sit past the
  window must be RECOGNIZED to report overflow at all, otherwise entry 0
  breaks the scan and the truncation stays silent. For 88,924 of 88,976
  distinct entry points `bound` IS the old `end` (their
  `next_method_start` is inside the window), so this changes nothing for
  them.
* the retry is skipped when the 20000-instruction raw cap, not the
  window, stopped the decode (`raw[-1].next_ip < end`) -- a wider window
  would decode the identical prefix and burn the work twice. 47 of the
  52 wide-span methods are tiny shared-body getters whose `next_method_start`
  neighbour is megabytes away; they never overflow, so they never pay
  for the second pass at all.

`work/probe_b63_window.py census`: 52 of 88,976 distinct entry points
declare a span over the window. That is the entire population fix 63a
can touch.

### Fix 63b -- the CFG block cap, without which 63a makes things WORSE

Same patch. `lift_method`'s `len(blocks) > 1500` cap raised to 3000.
Sized, not guessed (`work/probe_b63_window.py big`, every method with a
declared span over 0x8000 lifted under the widened window):

    InventoryManager.Update            2704 blocks  4.1s  5,458 lines
    TextMeshPro.GenerateTextMesh       1831 blocks  3.3s  3,519 lines
    TextMeshProUGUI.GenerateTextMesh   1842 blocks  3.3s  3,512 lines

Nothing else in the corpus exceeds 1200 blocks. Without 63b, 63a makes
`InventoryManager.Update` strictly worse -- it would newly exceed the cap
and fall to `_lift_body`'s linear flat fallback.

The other two are the reason this batch's gate result is what it is.
They are the **documented legacy-TMP pair** -- the sweep's only two
crashes and the parse gate's only two bad files for the last ~35
batches. Their badness was never a decompiler defect at all: the
cfg-too-large cap threw them at the linear lifter, whose output bypasses
`_final_text`. Raising the cap gives them a real structured lift.
`TextMeshPro.GenerateTextMesh` went from

    protected void GenerateTextMesh()
    {
            s_33d0 = v30;
    L_182adca14:
            s_f8 = 0;
            s_100 = 0;
            ...

to ordinary structured C# with a recovered
`switch (this.m_overflowMode)`.

### Ground truth read

Table entry[0] = entry[9] = entry[56] = 0x1806FA9AE, which disassembles
to `test bl,bl; jne 1806F956Fh; jmp 1806F9A1Ah` (the epilogue). Rendered:

    case 0:
    case 9:
    case 56:
    {
        if (flag9)
        {
            L_1806f956f:
            this.DropObject();
        }
        break;
    }

and case 59 (`0x1806FA9BB`, the same `test bl,bl; jne 1806F956F` head)
renders `if (flag9) { goto L_1806f956f; }`. Correct, including the
shared-target case-label grouping and the `ja` default falling out.

### Gates

* **Parse gate 2 bad / 2,206 ERROR / 4 MISSING -> `0 / 0 / 0`**
  (`work/ts_gate_b63_out1.txt`, 11,107 files both sides). The bad-file
  SET went empty; per §4 the two-row report IS the per-file diff, and
  there is no row. Trajectory for the record: 708/2,261/487 pre-batch-17
  -> 16/15/2 (b22) -> 2/7,919/2 (b36) -> 2/2,206/4 (b62) -> **0/0/0**.
* **Full-corpus sweep crashes 2 -> 0**, brace_unbalanced 0. into_block
  12,502/2,926 -> 12,950/2,928; sweep lines 1,983,738 -> 1,996,071. The
  +448 sites land in exactly the three methods (the staged sweep counters
  show +222 by method 40,000 and the rest at the TMP pair).
* **Tree diff: exactly 3 of 11,107 files differ, byte-identical
  otherwise** (md5 over both trees). InventoryManager.cs 6,883 ->
  12,185; TextMeshPro.cs 8,203 -> 6,673; TextMeshProUGUI.cs 8,610 ->
  7,041. Tree lines 2,702,326 -> 2,704,529 (+2,203): the structured TMP
  lifts are SHORTER than the flat ones they replace, which nearly pays
  for InventoryManager's +5,302.
* read-before-def 118,609 -> 118,931 (+322), and the A/B over just those
  three files reads 659 -> 981 -- **the entire corpus delta, so nothing
  else moved**. It is the honest cost of 12,333 newly-recovered body
  lines that did not exist to be counted before.
* Goldens 19/50 mismatching, **the same 19 by name** as batches 51/52
  -- this batch moved none of the 50 (none of the three methods is in
  the suite; TMP is explicitly excluded by `make_goldens.py`).
* All 14 pass unit mirrors green (hoist 20, elseif 13, cse 30, flag 22,
  cp 20, re, selfcopy 5, forhead 10, itfdispatch 14, refarg 24, lastdef
  22, callparen 7, flagcond 26, callname 21).
* Build 636.8s, 115,658 bodies, 0 failed.

### What this did NOT fix

The text residue lead #10 quoted barely moved: table-load sites 176 ->
174, files 109 -> 111 (the two TMP files newly contain some, having
previously been flat-lifted). Fix 63 emptied ONE bucket -- the
window-truncated table -- and it happened to be the biggest single
method in the corpus. The other ~174 sites are a different mechanism and
are re-sized by bucket in `work/census_b63_tables.py`; see todo lead #10.

Artifacts: patch `work/patch_b63_window.py` (+ `patch_b63b_comment.py`,
comment-only); probe/sizer `work/probe_b63_window.py`; census
`work/census_b63_tables.py`; build `work/run_build_b63.py` +
`work/build_b63.log`; gate `work/ts_gate_b63_out1.txt`; sweep
`work/sweep_b63.txt`. `b63_out1` is the verified gated candidate.

## 0af. Batch 52 (2026-08-24, three families found by READING
InventoryManager.cs end to end -- none of them on any todo list:
`unknown` conditions -51.5%, a movzx precedence bug, and a switch-subject
paren bug the gate caught)

This batch did not come off the lead list. It came off reading one file's
decompiled output end to end at `b59_out1` -- 6,883 lines, 144 methods,
rbd 94 -- and asking what was actually wrong with it. Three families
surfaced that every existing metric was blind to, because none of them
counts a bare TOKEN or a re-associated expression.

### Family A -- `unknown` conditions (fixes 60, 60b)

    this.currentInventoryIndex -= 1;
    if (!(unknown))                              InventoryManager.cs:2376
        this.currentInventoryIndex = this.maxInventorySlots - 1;

17,772 lines at b59_out1 carried the bare token, **8,290 of them
conditions** and 1,048 ternaries. `unknown` is batch 28's honest
placeholder for a conditional branch whose mnemonic `Lifter.CMP_OPS`
never mapped -- JS/JNS/JO/JNO/JP/JNP and their CMOV twins. Batch 28 chose
it over splicing a bare `?` (which a downstream `: default` synthesiser
silently completed into confidently WRONG C#), and that was right. What
it never did was ask what the branches MEAN.

`work/census_b52_unknown.py` (new) instruments the miss rather than
grepping the tree -- which cannot answer the question, since `unknown` is
the same token whatever produced it. `CMP_OPS` is replaced by a dict that
records failed lookups, `_insn` is hooked to accumulate each block's
decoded instruction array (exec_block hands it ONE BLOCK at a time and
never calls it for the branch itself -- the first cut of this census
scanned only the last block and found 0), and the flag setter is walked
back to. 1,937 methods, 131 sites, **and there is no unrecoverable
bucket at all**:

```
JS/JNS  <- TEST                  53   (44%)   sign of the tested value
JP      <- UCOMISS / UCOMISD     60   (46%)   unordered == a NaN operand
JS/JNS  <- SUB / ADD             11   ( 8%)   sign of the result
CMOVS/CMOVNS <- TEST/NEG/ADD      7   ( 5%)
JO / JNO / JNP                    0
```

All of it follows from the `(lhs, rhs)` pair `self.flags` already
carries, PROVIDED the consumer knows which instruction set it: arithmetic
parks its RESULT in the lhs slot with a 0 rhs, `test a,a` puts the tested
value there, an SSE compare's parity flag means unordered. **`cmp a,b` is
deliberately NOT derived** -- SF is sign(a-b), which is not `a < b` once
the subtraction can overflow, and the census finds no such site in this
corpus, so it stays `unknown` rather than becoming a guess.

**How the setter is known, and cannot desync.** `Lifter.flags` becomes a
property backed by `_flags`, whose setter stamps `_cur_mn` -- the
mnemonic `_insn` is currently executing -- into `_flags_mn`. All 18
existing `self.flags = ...` sites keep working unchanged and none of them
can forget. Two places override explicitly: `_kill_stale` re-renders the
pair without it being a new flag write, so it saves and restores the
stamp; and the decompiler's block-entry reconstruction rebuilds
`L.flags` from the predecessor's carried TEXT (decompiler.py ~1139),
where the setter is genuinely unknown, so it nulls the stamp rather than
inherit some other block's mnemonic.

**Fix 60b is the soundness half, and it is the reason this is shippable.**
An instruction that writes SF/PF on the real machine but models no flag
write here -- `neg`, `bt`, `shld`, `xadd`, `cmpxchg`, `bsf/bsr` -- would
leave `_flags_mn` naming an OLDER `test`, and fix 60 would emit a
confidently wrong condition: exactly what batch 28 avoided. `_insn` now
clears `_flags_mn` whenever iced says the instruction writes or undefines
SF or PF. **Only the stamp, never the pair** -- so a modelled write
re-stamps one line later, an unmodelled one degrades to `unknown`, and
every ordinary mapped-operator branch reads precisely what it read
before this fix existed. (A first cut special-cased NEG by clearing the
whole pair; that was reverted -- it would have changed output for
ordinary je/jne consumers, which was never the point.)

60b also models **memory read-modify-write**, which wrote no flags at
all: `_rmw_mem` renders `sub [this+0x20],1` and the `js` after it read a
stale pair. That is both the last soundness hole and the exact site that
started the whole family -- with it, InventoryManager.Update goes from 1
`unknown` to **0** and reads

    this.currentInventoryIndex -= 1;
    if (this.currentInventoryIndex < 0)
        this.currentInventoryIndex = this.maxInventorySlots - 1;

which is the source. `Double.CompareTo`'s `if (unknown)` likewise becomes
`if (double.IsNaN(this.m_value) || double.IsNaN(value))`, and the
wrap-around ternary becomes `num8 = (num7) >= 0 ? num7 : this.
maxInventorySlots - 1`.

Unit mirror `work/flagcond_test.py`, 26 cases -- **ten of them pin what
must STAY `unknown`** (cmp+JS, JO/JNO, JP after a non-float setter, JS
after a float compare, no recorded setter, unrenderable operands).

### Family B -- the `& 0xFF/*z*/` movzx artifact (fix 61)

18,035 lines, even though `Decompiler._bool_sugar` has always stripped
the shape as an identity. Reading one survivor explains why, and turns up
a second bug behind it.

`movzx r32, r8` renders `(x & 0xFF/*z*/)` via `_mk`, which leaves `_prec`
at None -- so every composition treats it as an ATOM and `_bin_txt` takes
its `elif _outer_parens(a_txt)` branch and **STRIPS the parens it was
handed**:

    ((byte*)obj43 + num1 & 0xFF/*z*/ + num1*8 + 0x0)[0]
        b59_out1/Assembly-CSharp/EndlessGenerationManager.cs:604

C# binds `+` tighter than `&`, so that reads
`((byte*)obj43 + num1) & (0xFF + num1*8 + 0)` -- a different expression
that still parses, so the tree-sitter gate could never see it. 1,702 of
the 18,035 sat inside an address expression like this. It is also exactly
why the mask survived at all: `_BZEXT_RX` only matches a PARENTHESISED
group, and the parens were gone by the time it ran. **Giving the Expr the
precedence it actually has fixes both halves at once** -- the grouping
where the mask stays, and the stripping where it should not.

Disassembling that same line turned up fix **61c**: the mask width
ignored the source register.

```
1806c65a0  movzx eax,cx        <- SIXTEEN-bit source
1806c65a3  add   rax,rax
1806c65a6  cmp   [r8+rax*8],rdx     <GenerateNight>g__ContainsAny|4_0
```

Every `movzx r32, rN` emitted `& 0xFF` regardless of width; every movzx
in that method is 16-bit and every one was masked wrong. The width is
`RegisterExt.size(ins.op1_register)`, and `_BZEXT_RX` learns the 16-bit
spelling so the identity strip keeps working on both. The line now reads
`((byte*)obj43 + (num1 + num1)*8 + 0x0)[0]` -- base + i*16, matching
`add rax,rax` + `[r8+rax*8]`.

**Reverted before shipping:** a first cut also dropped the mask early for
Boolean/Byte-typed sources. `_bool_sugar` already strips the shape
unconditionally and does it later; doing it earlier would only have made
two distinct values share one text further up the pipeline, which is
precisely the per-text collapse hazard batch 50's fix 58b was about. With
the parens restored, the existing pass reaches these sites on its own --
which is what it was written to do.

### Family C -- the switch-subject paren bug (fix 62), caught by the gate

`b61_out1` gated **3 bad files** where b59_out1 had 2, *while total ERROR
FELL* 2,211 -> 2,207. Textbook §4: the summary line hides a regression
under a bigger win, and only the per-file view sees it.

    b61_out1/Photon3Unity3D/ExitGames/Client/Photon/Protocol16.cs:184
        switch (num1 & 0xFF/*z*/))            one `(`, two `)`

`_emit_switch` rewrites `switch (x - k) { case 0: }` into
`switch (x) { case k: }` with `_SUBK_RX = r'^\(?(.+?) - (\d+)\)?$'`,
whose two optional parens are INDEPENDENT: on `(num1 & 0xFF/*z*/) - 97`
the leading `\(?` eats the open paren, `(.+?)` captures
`num1 & 0xFF/*z*/)` -- close paren included -- and the trailing `\)?`
matches nothing. **Pre-existing, exposed rather than caused by 61a**:
before it, the subject reached this regex paren-free and happened to
match harmlessly. The fix separates the two jobs the regex conflated --
`strip_outer` peels a wrapping layer (it only removes BALANCED pairs, and
refuses when a top-level ternary needs them), the regex matches the
subtraction and nothing else. A subject that is itself parenthesised now
keeps its own parens instead of losing half of them. Also widened the
batch-16 typeHierarchyDepth pattern to accept 61c's 16-bit spelling so a
width change can never silently stop it matching.

### Validation (full CLAUDE.md bar)

All 14 standing unit suites green (hoist 20, elseif 13, cse 30, flag 22,
cp 20, re 0 failures, selfcopy 5, forhead 10, itfdispatch 14, refarg 24,
lastdef 22, callparen 7, **flagcond 26 new**, callname 21).

Goldens 19, **the same 19 by name as b59_out1** -- fixes 60/60b/61/62
moved NONE of the 50. The suite does not contain the shapes; the 31
passing bodies did confirm that 61c's mask-width change broke nothing
they cover. Once again the §7 sample-size caveat, and once again the real
build's gate is what caught the only regression (family C).

Full-corpus sweep, b59_out1 source -> b62_out1 source:
```
b59: lines=1,980,111 crashes=2 brace=0 into_block=12,497/2,924
b62: lines=1,983,738 crashes=2 brace=0 into_block=12,502/2,926
```
crashes are the two pre-existing TMP cfg caps, brace clean both sides,
into_block +5 sites / +2 methods (no CFG-shape change in this batch).

Full rebuild `b62_out1`: 11,107 files / 115,658 bodies / 0 failed,
709.4s. Gate **2/2,206/4 -- bad-file SET back to the documented
legacy-TMP pair**, Protocol16.cs cleared, ERROR 2,211 -> 2,206. Brace
audit 0/11,107. Bare `objN;` statements 0.

```
                          b59_out1     b62_out1
`unknown` occurrences       23,409       18,476   -21.1%
  of which CONDITIONS        8,290        4,022   -51.5%
  ternaries                  1,048          578   -44.9%
`& 0xFF/*z*/` masks         18,035       14,229   -21.1%
tree lines               2,698,694    2,702,326   +3,632
read-before-def            118,445      118,609     +164
```

**read-before-def went UP by 164 (+0.14%), and that is honest, not a
regression**: a condition that used to render as the single token
`unknown` now renders its operands, and where an operand is itself an
undefined temp the metric counts it for the first time. The condition was
always reading that value; only the print changed.

Residue, deliberately left: `_BZEXT_RX`'s `[^(),]+?` cannot match a group
containing parens or commas, so `(((byte*)x + 0x0)[0] & 0xFF/*z*/)` still
survives -- most of the remaining 14,229. Widening it needs care (a
comma would let it span two arguments) and is its own item, todo lead 8.
The 4,022 surviving `unknown` conditions are the sound half by
construction: block-entry text carry with no recorded setter, plus fix
60b's guard firing on an unmodelled flag writer.

New tools: `work/census_b52_unknown.py` (the provenance census),
`work/flagcond_test.py` (26-case unit mirror). Patches
`work/patch_b60_flagcond.py`, `work/patch_b60b_flagsound.py`,
`work/patch_b61_movzx.py`, `work/patch_b62_subk.py`; builds
`run_build_b61.py`/`run_build_b62.py` + `build_b61.log`/`build_b62.log`;
gate reports `ts_gate_b61_out1.txt` (the 3-bad-file one, KEPT as the
evidence for family C) and `ts_gate_b62_out1.txt`; sweeps
`sweep_b60.txt`, `sweep_b61.txt`, `sweep_b62.txt`.

`b62_out1` is the verified gated candidate; promotion over `final_out/`
(= b42_out1) is a human call per the standing rule (§0/§6).

## 0ae. Batch 51 (2026-08-24, todo lead 5b + the caller-side twin it
turned out to have: the binary's own struct-size table, unread since the
registration loader was written -- read-before-def -5.0%, 7,633 methods'
parameters un-shifted)

Picked up todo lead 5b, which batch 50 had opened and deliberately
declined: `_setup_entry` does not model the hidden sret buffer, so every
parameter of a valuetype-returning method sits one slot too far left.
Batch 50 left it because the boundary was unknown -- "Win64 returns
1/2/4/8-byte structs in RAX with no hidden buffer at all, so this needs
its own disasm proof of where the boundary sits" -- and because the
upper bound (11,132 methods) was not an exact count.

### The size table nobody had read

`_load_metadata_registration` has assigned `self.type_sizes_count` and
`self.type_sizes_ptr` from `Il2CppMetadataRegistration` slots 12 and 13
since it was written, and nothing in either source file ever touched
them again. They address an array of pointers to

```c
struct Il2CppTypeDefinitionSizes {
    uint32 instance_size;    // INCLUDES the 0x10 object header
    int32  native_size;
    uint32 static_fields_size;
    uint32 thread_static_fields_size;
};
```

so a valuetype's exact sizeof is `instance_size - 0x10`.
`work/probe_b51_typesizes.py`: **16,916/16,916 entries readable, 0
unreadable, and 22/22 hand-checked types exact** (Boolean 1, Char 2,
Vector3 12, Quaternion 16, Bounds 24, Matrix4x4 64, Decimal 16, ...).
The only size reasoning that existed before this was the b35c sret fold
guard's *field-offset guess* -- "a field at boxed offset >= 0x18 means
the struct spans past 8 bytes" -- which disagrees with the exact size on
**776 of 5,756 value types (13.5%)**: it cannot see a struct whose one
field is itself a 64-byte struct (every `e__FixedBuffer`), and it calls
a 3-byte struct RAX-returned.

Open generic DEFINITIONS store `instance_size == 0` and are kept as
`None` rather than a negative number; **0 of the corpus's 17,723
valuetype returns hit that case**, so that fallback is theory, not load
bearing.

### Where the boundary actually sits (disasm, work/probe_b51_sretabi.py)

MSVC returns a trivially copyable struct of size 1, 2, 4 or 8 by value
and everything else through a caller-supplied buffer whose pointer takes
the FIRST argument slot. Both halves ground-truthed:

```
Panel.get_IMGUIEventInterests   0x182ef7bc0  size 3, instance, 0 params
    movzx eax,word [rdx+188h] / mov [rcx],ax / movzx eax,byte [rdx+18Ah]
    / mov [rcx+2],al / mov rax,rcx / ret
    -- RCX is the buffer, `this` is RDX, buffer echoed in RAX. 3 is not
       a by-value size; the field-offset guess says it is.
AdjustmentRule.get_DaylightTransitionStart 0x180935e40  size 24
    movups xmm0,[rdx+28h] / mov rax,rcx / movups [rcx],xmm0
TermInfoDriver.CreateKeyInfoFromInt  0x181d02de0  size 12, 2 params
    uses R8D and R9B -- four slots: buffer, this, p0, p1.
int3x3.op_BitwiseOr             0x1827257d0  size 36, static, 2 params
    mov rdi,rcx (buffer) / movsd xmm0,[rdx] (lhs struct) / mov ebx,r8d (rhs int)

TimeZoneInfo.get_BaseUtcOffset  0x18063aab0  size 8, instance
    mov rax,[rcx+30h] / ret      -- RCX is `this`, NO buffer at all.
SimpleCollator.GetExtenderType  0x181add3a0  size 4, 1 param
    mov r8,rcx / cmp edx,2015h   -- RCX `this`, RDX the parameter.
DateTime.AddDays                0x181c94c40  size 8 (fix 57's own ground
    truth: the double parameter is in XMM1, argument position 1, which
    is only consistent with RCX being `this` and nothing taking a slot).
```

### Sizes (work/probe_b51_sretsize.py, 116,178 methods with code)

```
valuetype return                              17,723
  genuinely sret (size not in {1,2,4,8})      11,046   (7,633 take parameters)
  returned in RAX (size in {1,2,4,8})          6,677   (3,499 take parameters)
  size unknown                                     0
RAX-returned size histogram: 1:120  2:181  4:3293  8:3083
```

So the bug had TWO halves, and lead 5b named only one:

* **CALLEE side** (`_setup_entry`, lead 5b): no buffer modelled, so
  7,633 methods' `this` and every parameter sit one register too far
  LEFT.
* **CALLER side** (`_hint_arg_types`/`_positional_args`): `ri += 1`
  whenever `_type_enum(rty) == 0x11`, with no size test at all -- so
  every call of 3,499 parameter-taking RAX-returning callees (every enum
  getter among them) is walked one register too far RIGHT. This half was
  not in the lead; it fell out of asking the size question.

### Fix 59 (`work/patch_b59_sretsize.py`)

* **59** `Il2Cpp.type_sizes` parsed next to `field_offsets`, plus
  `value_type_size(td)` and `returns_sret(rty)` -- one authority, with
  the disasm above quoted at it. A GENERICINST (0x15) return stays
  non-sret: its size lives in the instantiation, not this table, and
  fix 54's `trust` guard already stands down on that shape.
* **59b** `_setup_entry` seats the buffer: `base = 1 if returns_sret
  else 0`, then `this` at `ARG_REGS[base]` and `base += 1`.
* **59c** both caller-side walks ask `returns_sret(rty)`.
* **59d** the struct-return call fold's gate, and its RAX-echo binding.
  The b35c `any(field offset >= 0x18)` guard is deleted rather than kept
  alongside: the exact size now gates the whole fold one level up, and
  keeping the guess too would re-lose exactly the cases it cannot see.

### What it looks like

`TimeZoneInfo.GetDaylightTime(int year, AdjustmentRule rule,
Nullable<int> ruleIndex)`, size-24 return, three parameters -- before
(b50_out3 source) and after, same method, direct relift
(`work/probe_b59_relift.py`):

```
- if (((byte*)ruleIndex + 0x60)[0] != 0)
-     AdjustmentRule obj7 = year.GetPreviousAdjustmentRule(ruleIndex, obj8);
-     obj10 = year.ConvertToFromUtc(((byte*)ruleIndex + 0x18)[0], ...);
-     System.DateTime obj21 = TimeZoneInfo.TransitionTimeToDateTime(rule, &obj15);
- return this;
+ if (rule._noDaylightTransitions)
+     AdjustmentRule obj7 = this.GetPreviousAdjustmentRule(rule, obj8);
+     obj10 = this.ConvertToFromUtc(rule._dateEnd, rule._daylightDelta, ...);
+     System.DateTime obj20 = TimeZoneInfo.TransitionTimeToDateTime(year, obj12);
+ return obj24;
```

`year.GetPreviousAdjustmentRule(...)` was a method call on an `int`.
Every field access was an untyped `((byte*)x + N)[0]` because the
receiver carried the wrong type. `AdjustmentRule.
get_DaylightTransitionStart` was worse than untyped -- it *wrote* a
field on `this` (`this._dateStart = ...; return this;`) where the
machine reads `[rdx+28h]` and writes the buffer.

The caller-side half shows up inside the legacy-TMP flat lift, where
`Color32.op_Implicit` (4 bytes, RAX) had its `&s_70` argument taken for
a buffer: `s_70 = Color32.op_Implicit(0); this.m_fontColor32 = v522;`
(v522 defined nowhere) becomes `object t7 = Color32.op_Implicit(s_70);
this.m_fontColor32 = t7;`. Likewise `this.GetPreferredValues(obj3,
float.PositiveInfinity)` -> `(float.PositiveInfinity,
float.PositiveInfinity)`.

### Validation (full CLAUDE.md bar)

All 13 standing unit suites green (hoist 20, elseif 13, cse 30, flag 22,
cp 20, re 0 failures, selfcopy 5, forhead 10, itfdispatch 14, refarg 24,
lastdef 22, callparen 7, callname 21).

Goldens 18 -> **19**. The 18 are the documented pre-existing drift; the
ONE new mismatch is `int3x3.op_BitwiseOr@1827257d0` and it was read
against the disassembly above -- `mov rdi,rcx` parks the buffer,
`movsd xmm0,[rdx]` reads `lhs`, `mov ebx,r8d` reads `rhs`, so
`num1 = ((byte*)rhs + 0x0)[0] ... | num5` (with `num5` defined nowhere)
becoming `num1 = lhs.c0 ... | rhs` is the correct render, not a
regression. `goldens.json` deliberately NOT regenerated: the standing
rule is at/before promotion, and freezing 18 never-individually-read
drifting bodies is exactly what that rule exists to prevent.

Full-corpus sweep vs the b50_out3 source:
```
b50: lines=1,975,457 crashes=2 brace=0 into_block=12,484/2,923
b59: lines=1,980,111 crashes=2 brace=0 into_block=12,497/2,924
```
crashes are the two pre-existing TMP cfg caps, brace clean both sides,
into_block +13 sites / +1 method (this batch changes no CFG shape; the
drift is downstream of differently-typed expressions), lines +4,654.

Full rebuild `b59_out1`: 11,107 files / 115,658 bodies / 0 failed,
546.6s. Gate **2/2,211/4 -- bad-file SET unchanged**, the same
documented legacy-TMP pair, and since ts_gate lists every bad file that
2-row report IS the per-file diff (§4). ERROR 2,097 -> 2,211, all of it
inside those two files and all of it cascade churn in an already
unparseable flat lift: bucketed by row text, TextMeshPro.cs is 754 ->
756 with an identical top-12 distribution, TextMeshProUGUI.cs 1,343 ->
1,455 with 495 -> 499 distinct row texts and the same families (`;`
484 -> 567, `goto L_182af4ac5;` 129 both sides). **No new malformation
family, no new bad file.** Brace audit 0/11,107. Bare `objN;`
statements 0 (batch 50's regression shape).

**read-before-def 124,715 -> 118,445 (-5.0%)**, across 34,065 ->
30,962 methods (-9.1%) and 4,882 -> 4,824 files. Unity.Mathematics'
`math.cs` -- wall-to-wall small-struct operators -- goes 4,020 ->
3,021 (-25%). Tree lines 2,694,051 -> **2,698,694** (+4,643): the
honest cost of receivers that now resolve to typed member chains
instead of collapsing into one untyped deref.

New tools: `work/probe_b51_typesizes.py` (table validation + the
heuristic-vs-exact disagreement census), `work/probe_b51_sretabi.py`
(the boundary disassembly, bucketed by exact size),
`work/probe_b51_sretsize.py` (both halves' population),
`work/probe_b59_relift.py` (the ground-truth relift set, A/B safe --
it degrades to `n/a` on a pre-fix source). Patch
`work/patch_b59_sretsize.py`; build `work/run_build_b59.py` +
`build_b59.log`; gate report `work/ts_gate_b59_out1.txt`; sweep
`work/sweep_b59.txt`.

`b59_out1` is the verified gated candidate; promotion over `final_out/`
(= b42_out1) is a human call per the standing rule (§0/§6). Residue
this batch deliberately did NOT take: see todo.md lead 5c (the arity
trim still counts `param_count + receiver` with no slot for the buffer,
which only matters when the fold cannot peel an `&s_N`).

## 0ad. Batch 50 (2026-08-24, Correctness backlog #2 read-before-def:
the item's PREMISE was wrong -- provenance census + four lifter fixes,
read-before-def -41.8% -- CLOSED)

Picked up backlog #2, the largest open item in the tree (214,287
undefined temps at `1a_dup5b_out1`) and the one whose own standing
instruction had never actually been carried out: "bucket by which
lifter path emitted the phi -- expect 2-3 root causes covering most of
it". Every split done since (`rbd_subclassify.py`, `rbd_misc_split.py`,
the b38 buckets) was TEXTUAL -- it buckets by the shape of the line
that READS the undefined name, which says what the name is used for and
nothing about where it came from.

### The census that had never been run

`work/census_b50_rbdprov.py` (new) instruments the lifter instead:
every mint site is wrapped (`Lifter._fresh_unknowns`, `Lifter.new_var`,
`Lifter.slot_var`, `Decompiler._analyze`'s own per-pass entry seed,
`Decompiler._build_phi_copies`), the method is lifted, the identical
read-before-def rule runs in memory on the result, and every undefined
name is reported by its PROVENANCE. Phi names split further by whether
`_build_phi_copies` found a value on ANY in-edge.

2,619 methods (stride-40 spread over the whole corpus), 6,038 sites:

```
fresh-unknown (post-call clobber)   40.8%
entry-seed (unknown reg at entry)   38.5%
stack-slot                           7.6%
UNKNOWN-mint                         7.0%
_bind temp (new_var)                 3.1%
phi (had in-edge values)             2.1%
phi (NO in-edge value)               0.9%
```

**The backlog item's stated premise -- "These are unresolved phi inputs
on entry edges" -- is wrong by more than an order of magnitude. Phis
are 3.0% of the mass.** 79% is one thing: a register holding an
unknown, being read. The provenance x read-context cross names the
biggest cell exactly:

```
entry-seed  x  call-arg: /*indirect*/     929   (15.4%)
```

`object obj21 = obj12() /*indirect*/(0, buffer, length, 2, obj14,
obj16, obj18, obj20);` -- the four ARG_XMM slots, still holding the
unknowns the entry seed put there, appended to every argument list
because the builder's only test is `is not None`.

### Fix 57 -- `_setup_entry`'s positional walk (the THIRD copy of the
### ordinal-per-class bug)

Reading the mint sites for that census turned up a live bug on the way.
`_positional_args` (fix 42b) and `_hint_arg_types` (fix 53) both
reconstruct the CALLER-side Win64 assignment with one shared positional
counter, `slot = base + pi`. `_setup_entry` -- the CALLEE side, the
mapping of the lifted method's OWN parameters onto entry registers --
still walked two independent counters (`ri` bumped only by non-float
params, `xi` only by float ones, il2csharp.py ~2813, with a leftover
unused `pos = 0` right above them).

Win64 assigns argument slots BY POSITION, and `this` is argument 0 of
an instance method, so an instance method taking one float receives it
in XMM1. Disassembly, four independent methods
(`work/probe_b50_entryfloat.py`):

```
DateTime.AddDays     0x181c94c40   movaps xmm6,xmm1
DateTime.AddSeconds  0x181c95060   movaps xmm6,xmm1
Double.CompareTo     0x181c9a300   comisd xmm1,[rcx]
Single.CompareTo     0x181cc14e0   comiss xmm1,[rcx]
```

All four read XMM1; `_setup_entry` seated the parameter in XMM0, so
every read of the true register rendered as an undefined temp and the
parameter name sat in a register nothing reads. `Double.CompareTo`
shipped at `1a_dup5b_out1` as `if (real1 > this.m_value)` with `real1`
assigned nowhere -- the source says `value`. **3,345 of 116,178 methods
with code (2.9%)** are mis-mapped, broader than the interleaved-
signature class fix 53 measured on the caller side (2,288), because a
float parameter of an INSTANCE method is mis-seated even when the
signature has only that one parameter.

Fix 57 uses the same `slot = base + pi` walk, skips `slot > 3` (5th+
argument arrives on the stack), and adopts `_hint_arg_types`' exact
float test so a byref float (`ref double`) is treated as the GPR-borne
address it is -- ground-truthed at DateTimeParse.ParseFractionExact
0x181c90b60, `mov rdi,r8`.

**Deliberately NOT changed: the hidden sret buffer.** `_hint_arg_types`
starts its caller-side walk one slot later when the callee returns a
valuetype; `_setup_entry` has never modelled that and still does not.
Every parameter of such a method is already off by one today under
either counter scheme, so leaving it alone preserves the status quo
rather than half-changing it. Upper bound: 11,132 methods return
`_type_enum == 0x11` AND take parameters (upper, not exact -- Win64
returns 1/2/4/8-byte structs in RAX with no hidden buffer). New todo
lead, not attempted here.

### Fix 58 -- a never-written register carries no argument

`_call` builds its argument list from all four ARG_REGS plus every
ARG_XMM holding a value, `is not None` the only test. Named targets are
then trimmed to declared arity and a bare `sub_X` is capped at 4;
`/*indirect*/`, high-candidate shared bodies and `new` ctors get
neither.

THE ARGUMENT (sound, not a heuristic). An Expr minted by the entry seed
or by `_fresh_unknowns` sits in a register precisely when NO lifted
instruction has written that register since. RCX/RDX/R8/R9 and XMM0-3
are all volatile -- Win64 forbids a caller from relying on any of them
surviving a call -- so argument setup MUST write the register at the
call site. A register still holding its unknown was therefore not set
up for this call and carries no argument. Same shape of reasoning as
batch 21j's arity trim: bound the list by what is provably there, never
guess which value is right.

`Expr` gains an `_unk` slot (defaulted through the existing
`__getattr__`, so creation stays allocation-free), set at exactly three
mint sites. Any instruction that writes the register replaces the Expr
and clears the mark with it; arithmetic over an unknown (`vN + 8`) is a
written register and keeps its slot. Then: ARG_XMM slots holding an
unknown are skipped outright (`_xmm_pending` is keyed on the XMM INDEX,
so `_positional_args`/`_hint_arg_types` are unaffected by the hole);
trailing ARG_REGS slots holding an unknown are popped, extending the
`while args[-1] == '_'` trim already there. A MIDDLE unknown GPR slot is
left exactly as it renders today -- a later real slot proves the call's
arity, so that hole is a genuine lifter gap and stays visible.

### The regression, caught by the gate, and the three fixes it forced

**The first full build (`b50_out1`) gated `bad=819 ERROR=4390
MISSING=4` against a `2/5,020/4` baseline -- 817 newly-bad files while
the total ERROR count FELL.** Textbook §4: "always run the per-file
diff, the summary line hides a regression under a bigger win."

- **fix 58b.** `_bind`'s in-block rewrite window matches per-TEXT, and
  a statement that is exactly `<old>;` is a DISTINCT instruction's own
  side-effecting emission, not a re-render of the bound value.
  SaveManager 0x1805AA260 (`work/probe_b50_bind.py`): five separate
  `new List<int>();` at five IPs 30 bytes apart, all captured by one
  bind and rewritten to `t1026;` -- not a C# expression statement, and
  five allocations collapsed into one identity. Latent only because
  their texts DIFFERED before, each carrying its own phantom trailing
  arguments. `_bind`'s cross-block path already reasons per-object and
  says so in its own comment ("per object, not per text, so a real
  second identical call is never touched"); this window did not.
  0 bare-token statements in `1a_dup5b_out1`, 2,306 in `b50_out1`.
- **fix 58c.** The same shape at one of the bound expression's OWN
  recorded render sites (`e._sites`) means the opposite thing: it is
  this value's own emission, subsumed by the inserted `var v = old;`,
  so it must be DROPPED, not kept (58b) and not rewritten.
  `ResolvedStyleAccessPropertyBag..ctor` is the clean case -- one
  allocation rendered twice, as the bound declaration and as its own
  `new T();` ctor statement. Safe where the two rules disagree: a ctor
  statement only carries the identical text when the ctor takes NO
  arguments, so nothing is ever lost. Statements are blanked to `''`
  (the lifter's established no-op emission) so no index shifts
  mid-loop. `b50_out2` still gated 112 bad / 282 bare tokens before it.
- **fix 58d.** `_fold_static_addrs`' call-paren-vs-grouping-paren test
  ("a call paren attaches directly to the callee identifier") reads the
  character before the `(`. This decompiler also spells callees with a
  trailing annotation -- `Method() /*indirect*/(args)`,
  `sub_X/*shared body, N candidates*/(args)` -- where that character is
  `/`, so the fold swallowed the call's own parens and glued the callee
  to its argument: exactly the `NotifyPropertyChangedtypeof(X).field`
  failure the batch-16 comment above that code already describes,
  reached through a callee spelling it does not cover. Needs a
  SINGLE-argument call (so `after` is `)` not `,`), which fix 58
  created for the first time. One site tree-wide:
  TouchScreenKeyboard.get_isInPlaceEditingAllowed 0x182bf4650. Unit
  mirror `work/callparen_test.py`, 7 cases including the batch-16 ones
  it must not regress.

### Validation (full CLAUDE.md bar)

Goldens 12 -> 18. The 12 are pre-existing drift (one more than
todo.md recorded -- `RenderGraphPass.SetColorBufferRaw` was already
drifting; verified by a byte-identical revert A/B). All **6 new ones
read individually and confirmed CORRECT against disassembly**, not
regressions: `<>c.<DescribeFields>b__0_7` (`movss [rdx+0Ch],xmm2` --
the float param is XMM2, arg position 2, not XMM0),
DateTimeParse.ParseFractionExact (`mov rdi,r8` -- `ref double` is a
GPR address), and four fix-58 argument trims including
EnumBuilder.IsArrayImpl (disasm sets only RCX/RDX before
`call 180435670h`; `sub_180435670(obj2, obj3, obj5, obj6)` -> 2 args)
and Speaker.StopPlayback (R9's last write is before the intervening
call at 0x18202dc50, so it is a clobber unknown at 0x18202dc6c).
Fixes 58b/58c/58d moved NONE of the 50 -- the sample does not contain
the shapes -- which is precisely the §7 caveat about a 50-body sample
under-representing a structural change; the real gate is what caught
all three.

All standing unit suites green (hoist 20, elseif 13, cse 30, flag 22,
cp 20, re 0 failures, selfcopy 5, forhead 10, itfdispatch 14, refarg
24, lastdef 22, callname 21, callparen 7 new).

Full-corpus sweep vs the `1a_dup5b_out1` baseline:
```
baseline: lines=1,976,884 crashes=2 brace=0 into_block=12,484/2,923
b50:      lines=1,975,457 crashes=2 brace=0 into_block=12,484/2,923
```
into_block byte-identical (expected -- none of the four fixes changes
CFG shape), 0 new crashes (the 2 are the pre-existing TMP caps), brace
clean, lines -1,427.

Full rebuild `b50_out3`: 11,107 files / 115,658 bodies / 0 failed,
627.8s. Gate **2/2,097/4 -- bad-file SET unchanged** (the same
documented legacy-TMP pair), and ERROR inside those two files fell
5,020 -> 2,097 (-58%), MISSING unchanged. Brace audit 0/11,107. Bare
`objN;` statements 0. Tree lines 2,695,492 -> **2,694,051** (-1,441).

**read-before-def 214,287 -> 124,715 (-41.8%)**, across 45,396 ->
34,065 methods and 5,616 -> 4,882 files -- the single largest movement
this metric has ever had (previous best: batch 33's -11.1%).

Patches: `work/patch_b57_entrypos.py` (fix 57),
`work/patch_b58_unkargs.py` (58), `work/patch_b58b_bindbare.py` (58b),
`work/patch_b58c_bindown.py` (58c), `work/patch_b58d_callparen.py`
(58d) -- all binary CRLF per CLAUDE.md. Census
`work/census_b50_rbdprov.py`; probes `work/probe_b50_entryfloat.py`,
`work/probe_b50_bind.py`, `work/probe_b50_stages.py`; build
`work/run_build_b50c.py` + `work/build_b50c.log`; gate report
`work/ts_gate_b50_out3.txt`; sweep `work/sweep_b50c.txt`. The two
intermediate trees (`b50_out1` with the 819-bad regression, `b50_out2`
with the 112-bad residue) were deleted after their diffs were captured
above -- never candidates, kept only long enough to record the bugs.

**A `sed -i` on `il2csharp.py` mid-batch converted the whole file to
LF** (CLAUDE.md's named hazard, reached through `sed` rather than
through Python). Caught immediately by a CRLF count, restored by
re-expanding every LF, and the content verified against a pre-`sed`
snapshot by unified diff. Use the binary `patch_*.py` pattern for these
two files -- `sed -i` counts as a text rewrite.

### Residue, named precisely

Same census re-run on the fixed source (`work/rbdprov_b50_after.txt`,
identical 2,619-method sample): 6,038 -> **3,537 sites (-41.4%)**,
which corroborates the tree-side -41.8% independently. What moved, and
what did not:

```
read context            before   after
call-arg: new/ctor         353      15   -96%
call-arg: bare sub_        768     254   -67%
call-arg: /*indirect*/     987     442   -55%
copy rhs                 1,034   1,038    --      untouched by fix 58
raw store lhs/rhs          446     447    --      untouched
stack-slot (provenance)    457     457    --      untouched
```

So the argument-spray family is substantially closed, and the residue
is three mechanisms fix 58 structurally cannot reach:

1. **`copy rhs`, 29.3% and now the largest** -- `objA = objB;` where
   objB is an unknown. Not an argument slot at all.
2. **`raw store lhs/rhs` 12.6% + `store rhs` 5.6%** -- an unknown
   stored into a real field or through a raw pointer. §3 #2's old
   `plain-store-value` note calls this class out as READING AS A
   CORRECTNESS BUG rather than clutter, and that remains true.
3. **`stack-slot` 12.9%** -- a slot read before any tracked write, a
   different mechanism entirely (`Lifter.slot_var`).

The 442 surviving `/*indirect*/` argument sites are the deliberate
carve-out: an unknown in a MIDDLE GPR slot with a real slot after it,
left visible on purpose because the later real slot proves the call's
arity and the hole is therefore a genuine lifter modelling gap worth
seeing. Whoever picks this up should find which instruction the lifter
failed to model, not widen the trim. Sized as todo lead 5a.

`b50_out3` is a verified, gate-clean, crash-clean, brace-clean
candidate (supersedes `1a_dup5b_out1` -- same source tree plus fixes
57/58/58b/58c/58d); promotion over `final_out/` (= b42_out1) is a human
call per the standing rule (§0/§6).

## 0ac. Batch 49 (2026-08-23, todo lead 1a-a: the `_singleton_cse`
duplication-cap interaction -- ROOT-CAUSED AND FIXED, cap removed,
SHIPPED, CLOSED)

Picked up lead 1a's residue item (a): why a large duplicated tail
(batch 43's fallback, `_hoist_shared_tails`) defeated `_singleton_cse`'s
collapse, which forced dup4's speculative 24-raw-line cap
(`patch_1a_dup4.py`) rather than a real fix.

Root cause (`work/probe_b48_relift.py 0x1806FAF40`, InventoryManager.
AssignTemplates -- the exact case dup4's cap was ground-truthed
against; reproduced live by disabling the cap in place and diffing):
every duplicate copy is the literal SAME text, so a tail-local decl
(`StoreManager obj4 = typeof(StoreManager).Instance;`) re-declares the
IDENTICAL token in every copy. Legal C# -- each copy sits in its own
block scope -- but `_singleton_cse`/`_value_cse` key off a flat,
non-block-scoped `assigns[tok]` count; seeing 2+ assignments to `obj4`
across the copies, they drop that token from folding ENTIRELY, not
partially. That's what ballooned AssignTemplates 108->324 lines
uncapped.

Fix 56: at the point of inserting each duplicate copy, mint that copy
its own fresh number for every token whose first declaration is
inside the tail AND that never appears outside the tail in the
current `lines` list; a token the tail only READS that's declared
OUTSIDE the tail (an outer singleton fetch, e.g. AssignTemplates'
`obj3`) names one shared value and stays untouched in every copy --
letting `_singleton_cse` hoist ONE fetch for the WHOLE method, a
better outcome than dup4's own speculative "collapse within each
copy". Verified live: AssignTemplates now renders 202 lines, both
copies sharing a single `obj3 = typeof(StoreManager).Instance;` at the
method head (was 108 lines capped / 325 uncapped-and-broken). The
24-line cap is removed entirely -- root-caused, not resized.

**Live-caught regression, fixed same session (still fix 56):** the
first real gated rebuild (`1a_dup5_out1`) added a THIRD bad file to
the tree-sitter gate -- `System.Xml/XmlDownloadManager.cs`, previously
clean -- a dangling `else if` with no leading `if` inside a `finally`
block (illegal C#). Traced to `XmlDownloadManager`'s async `MoveNext`
(VA 0x18235e500): removing the cap let a separate, unrelated goto
elsewhere in the SAME method duplicate a tail that itself contains a
SECOND `try`/`finally` `Monitor.Enter` guard region. The mere presence
of that second guard region corrupted an unrelated dead-arm-collapse
pass's handling of the FIRST, entirely untouched guard region --
which rendered correctly both before fix 56 and with only ONE
Monitor.Enter region in the method. That collapse-pass interaction is
NOT root-caused; instead of chasing it, fix 56 grew a guard: a tail
that contains its own `try`/`finally`/`catch` is refused for
duplication and stays an honest goto, same as before fix 56 existed --
scoped to exactly the proven hazard, not a blanket size cap. Re-gated
clean after the guard (see below). This is why CLAUDE.md's "a real
rebuild is the only truth for Lifter/structural-pass changes" rule
exists -- the golden suite and both unit mirrors were green through
this whole regression; only the real gate caught it.

Unit mirror `work/hoist_test.py`, 3 new cases (20/20 total):
`dup-rename-local` (fresh token in the new copy, original copy's own
name untouched), `dup-no-rename-outer-token` (a tail-read token
declared outside the tail is never renamed in either copy),
`reject-dup-tail-has-tryfinally` (the hardening guard).
`work/cse_test.py` unaffected, 30/30.

Golden suite: 12/50 mismatches -- the 11 already-documented stale
cases (batches 44/45 drift) plus 2 new ones, both read line-by-line
and confirmed CORRECT, not regressions: InventoryManager.
AssignTemplates (the fix's own target) and RenderGraphPass.
SetColorBufferRaw (a second, independent site where a `goto` is now
soundly replaced by an inlined tail copy -- same mechanism, verified
by comparing the inlined block's fields against the original tail's
own position field-by-field). goldens.json left stale per the
standing batch-44-onward precedent (regenerate at/before the next
promotion, not every batch).

Full-corpus sweep (`work/sweep_1a_audit.py`, guarded):
```
b48_out1 baseline: into_block=15,416/3,956 (todo.md's last recorded number)
after fix 56:       lines=1,976,884 crashes=2 (TMP caps, pre-existing)
                    brace_unbalanced=0 into_block=12,484/2,923
```
-19.0% sites / -26.1% methods, 0 new crashes, 0 brace regressions --
a materially bigger corpus-wide win than the single named case
suggested, since the removed cap unblocks every previously-capped
funnel-blocked large tail, not just AssignTemplates'.

Full rebuild `1a_dup5b_out1`: 11,107 files / 115,658 bodies / 0
failed, 782.9s. Gate: **2/5,020/4** -- bad-file SET unchanged (the
same documented TMP pair only; the XmlDownloadManager regression is
gone), brace 0/11,107. The ERROR count within the two already-bad TMP
files rose 4,863->5,020 (more duplication landing inside those two
huge legacy-bypass files, the same class of pre-existing defect, not
a new one -- confined entirely to the already-bad set per the
standing batch-35 reading rule, §7). Tree line count 2,626,137
(b48_out1) -> 2,695,492 (1a_dup5b_out1), delta +69,355 -- the honest
duplication cost, comparable in magnitude to batch 43's own +75,477
(this fix unblocks materially more sites than batch 43 shipped).
Patches: `work/patch_1a_dup5.py` (fix 56, idempotent, byte-verified
against the live file), binary CRLF per CLAUDE.md; build
`work/run_build_1a_dup5.py` + `work/build_1a_dup5b.log`; gate report
`work/ts_gate_1a_dup5b_out1.txt`; sweep `work/sweep_1a_audit.py`
(existing tool, re-run); ground truth `work/probe_b48_relift.py`.

`1a_dup5b_out1` is a verified, gate-clean, crash-clean, brace-clean
candidate (supersedes b48_out1 -- strict superset, same source tree
plus fix 56); promotion over `final_out/` (= b42_out1) is a human call
per the standing rule (§0/§6). `b48_out1`/`b47_out1`/`b46_out1`/
`b45_out1` were left on disk rather than reaped, per the same standing
rule. The unguarded intermediate tree `1a_dup5_out1` (the one WITH the
XmlDownloadManager regression) was deleted after its diff was captured
above -- never a candidate, kept only long enough to record the bug.

## 0ab. Batch 48 (2026-08-23, todo lead #4's "slot liveness is ONE
upstream feature": TESTED THE PREMISE, it does not hold -- SHIPPED
PARTIAL, two of the three items closed by a different mechanism, one
re-declined with a root cause)

The session was scoped as "design and ship the slot-liveness / escape
analysis feature that lead #4 names as blocking three backlog items at
once" (copy-prop's address-taken residue / out-ref parameter detection /
the phantom first store). The first thing done was re-measuring the
three trails against real data. **Two of the three premises did not
survive the measurement, and the third is blocked by something else
entirely.** What shipped is the mechanism the data actually pointed at;
no escape analysis was written, because nothing needed one.

### The three premises, re-measured

**(1) "43.3% of copy-prop's ~98k residue is address-taken sources."**
The b37 census bucketed a surviving copy as address-taken whenever
`&lhs`/`&rhs` appeared ANYWHERE in the method -- coexistence, not
causation. `work/census_b48_copyres.py` re-asks the question the pass
actually asks (is an escape of the SOURCE between the copy and the next
read of the DEST?), on b47_out1:

```
pure copy lines        104,263      (b37 measured 97,952 -- same population)
  in_loop               71,194  68.3%
  no_read               19,138  18.4%
  escape_coexist/in_loop 13,039  12.5%
  escape_coexist/no_read    658   0.6%
  escape_blocks             234   0.2%   <- escapes that actually block
```

Escape analysis would unblock **234 of 104,263 copies (0.2%)**. The
residue is in-loop (80.8%) and never-read-again (19.0%). This premise
is dead; do not reopen lead #4 for it.

**(2) "out/ref detection is blocked on the stack-frame model."** It is
not: it is decidable from the callee's declared parameter type, and the
render that existed was wrong. Disasm ground truth,
DEMO_LegsAnim_KeepOnGround.FixedUpdate VA 0x180671800, the 6-param
Physics.Raycast overload at 0x180671a30:

```
RCX <- lea rcx,[rsp+50h]   param0 origin    te=0x11 byref=0  Vector3
RDX <- lea rdx,[rsp+40h]   param1 direction te=0x11 byref=0  Vector3
R8  <- lea r8,[rsp+60h]    param2 hitInfo   te=0x11 byref=1  RaycastHit
```

Win64 passes anything not 1/2/4/8 bytes by hidden pointer, so a BY-VALUE
struct argument and a genuine `ref`/`out` argument arrive through the
IDENTICAL instruction -- three identical `lea`s, two by-value copies and
one `out`, and only the byref bit separates them. Confirmed again at
AudiencePath.SpawnPeople 0x1804FEDF0 (@0x1804ff660, the 4-param
overload) and at Rigidbody.MovePosition (@0x180671ab5, param0 a by-value
Vector3 that rendered `ref obj25`). Corpus census
(`work/census_b48_leaargs.py`, 116,178 methods; `lea [rsp/rbp+N]`-fed
GPR argument slots mapping onto a declared parameter of a
single-candidate named direct call):

```
lea-fed declared-param arg slots: 54,297
  past_arity   24,058  44.3%   receiver / sret buffer / MethodInfo*
  byval_vt     15,081  27.8%   by-value struct via hidden pointer
  byref        12,230  22.5%   genuine ref/out
  byval_other   2,928   5.4%   lea at a string/int/float param
```

**And the existing `ref` render was an accident.** `_ADDR_LOCAL_RX`
(decompiler.py) is `(?<=[\(,])&(...)` while args join with `', '` -- so
only the argument immediately after `(` could ever match. All 21,955
`ref X` renders in b47_out1 were "argument 0", chosen by where the comma
fell, with no relation to the signature. Worse, the same regex fired
inside pointer arithmetic (`*(&obj12 + 0x0)` -> `*(ref obj12 + 0x0)`,
which `_unsafify` then turned into `((byte*)ref obj12 + 0x0)[0]`) and
inside member access (`(ref this.m_InertialFrame).frame`) -- **8,238
ungrammatical sites tree-wide**, gate-invisible, exactly the
wrong-but-parseable class the golden suite exists for (it caught this:
BurstSolverImpl.ApplyFrame, 133 diff lines).

**(3) "phantom first store."** Root-caused, and it is neither phantom
nor an escape-analysis problem. Same method, 0x180671845:

```
xorps  xmm0,xmm0
movups [rsp+60h],xmm0      ; rsp+60 is the R8 arg = out RaycastHit
mov    [rsp+80h],rax       ; rax = 0
movups [rsp+70h],xmm0
mov    [rsp+88h],eax       ; 44 bytes zeroed = sizeof(RaycastHit)
```

It is the IL `.locals init` zero-fill of the byref parameter's stack
buffer, which the lifter narrows to the single line `obj4 = 0f;`.
Dropping it needs `out` vs `ref`, and **v31 `Il2CppParameterDefinition`
is `{nameIndex, token, typeIndex}` (12 bytes, il2csharp.py ~322) -- there
is no ParamAttributes field**, so out-ness is not recoverable from
metadata at all. Re-declined, now with a mechanism instead of a shrug.
Note that fix 54 changes its status for free: the call now renders
`Physics.Raycast(real5, real1, ref obj4, ...)`, and C# definite
assignment REQUIRES a store before a `ref` argument -- the store is
load-bearing in the rendered form, not a phantom.

### Shipped

- **54 (il2csharp.py): `_byref_arg_render` + `Lifter._byval_struct` +
  the `at.startswith('&')` branch of `_hint_arg_types`.** Render a `&X`
  call argument by what the callee DECLARES at that position: byref
  (bit 29 / type-enum 0x10) -> `ref X`; non-byref VALUETYPE, including a
  GENERICINST whose open type is a struct (`ReadOnlySpan<char>`) ->
  bare `X`, the `&` being ABI noise; **anything else -> untouched raw
  `&`**. That last row is load-bearing: a `lea` landing on a
  string/int/float parameter (the census's 5.4%) means the
  parameter->register mapping is wrong for that call, and a confident
  `ref` there is the failure mode the shared-body rule exists to
  prevent. `out` is not separable from `ref` (see (3)), and the
  DECLARATION side already spells both `ref ` (il2csharp.py ~6282), so
  the tree stays self-consistent. Guard: the sret test one line up is
  `_type_enum(rty) == 0x11` only, so a GENERICINST struct return would
  consume RCX without `ri` knowing and shift every parameter one slot
  left -- a mis-slotted type HINT is invisible, a mis-slotted `ref` is
  visible wrongness, so the rewrite stands down entirely on that shape
  (`trust`). Unit mirror `work/refarg_test.py` (24 cases), written
  first.
- **54b (decompiler.py `_render`): removed the arg-0-only
  `_ADDR_LOCAL_RX` rewrite** that fix 54 supersedes. The constant is
  left defined (`_unsafify`'s docstring references the behaviour);
  nothing calls it.
- **54c (il2csharp.py, the sret fold at ~5303): the same render on the
  STRUCT-RETURN path.** Caught by reading the built tree, not by any
  gate: after 54+54b, AC still had `Quaternion.op_Multiply(&obj44,
  &obj62)` (both parameters non-byref by-value Quaternions),
  `Vector3.Normalize(&obj64)`, `Transform.TransformPoint(&obj9)` -- and
  tree-wide `&local` had gone UP rather than down. Root cause: the sret
  branch RETURNS from `_call` before the `mi is not None` block that
  calls `_hint_arg_types`, so **every struct-returning call bypassed fix
  54** -- and struct-returning calls are exactly where `&` arguments
  cluster, because Vector3/Quaternion math both takes and returns
  by-value structs. Instrumented on AudiencePath.DrawCurved 0x1804FDEC0:
  `_hint_arg_types` fires 63 times there, for get_transform / get_Item /
  set_color / DrawLine / Math.Pow only -- never once for a
  struct-returning callee. On this path the sret question is SETTLED
  rather than inferred (arg0 was peeled off as the buffer), so `rest` is
  `[receiver?] + params` exactly and no `trust` guard is needed.
  Render-only: this path also skips `_hint_arg_types`' TYPE HINTING of
  `&s_N` arguments, which would shift resolved types tree-wide and needs
  its own sizing -- deliberately left (see the residue below).
- **55 / 55b (decompiler.py): `_drop_dead_lastdef`,** the actionable
  slice of premise (1). `work/census_b48_noread.py` splits the
  19,720-line no-later-read bucket by which guard holds it:
  `prior_read+goto_after` 9,867 (50.0%) / `prior_read` 5,614 (28.5%) /
  `neither` 3,220 (16.3%) / `+goto_after` 1,019 (5.2%).
  `_drop_dead_locals` is occurrence-based and flow-INSENSITIVE, so a
  read only BEFORE the store still marks the token live and protects
  every definition of it (78.5%); `_copy_prop`'s backward sweep refuses
  any drop above a later `goto` (55%); the `neither` 16.3% is minted by
  the LATE `_hoist_shared_tails` (fix 51b) after both sweeps have run.
  Soundness: a store whose destination has no occurrence at any LATER
  line is observable only by reaching an EARLIER line that reads it,
  which needs backward flow -- so the drop is refused inside a loop
  frame, inside the span of a backward `goto` (label at k, goto at
  j>=k protects [k, j]), or when the destination is ever address-taken.
  Right sides stay bare tokens and literals, so no exception-raising
  load is dropped with the store. Runs LAST in `_structure`. 55b is a
  cheap early-out (one match per line, no scrubbing) because the yield
  is small. Unit mirror `work/lastdef_test.py` (22 cases), written
  first.

**HONEST YIELD NOTE on 55:** it is worth 405 lines tree-wide (sweep
1,909,089 -> 1,908,684), not thousands. The rejection census over 1,500
methods reads `rhs-shape` 5,257 / `later-occurrence` 1,246 / `in-loop`
911 / `back-goto` 509 / `escaped` 180 / **DROPPED 5** -- and RELAXING the
right-hand-side rule to `_drop_dead_locals`' own purity test (arbitrary
pure loads, not just bare tokens and literals) changes DROPPED from 5 to
5. The narrow rule costs nothing, so it stays. The ceiling under sound
guards is what it is: **the remaining copy residue is loop-carried and
back-edge-reachable, and needs real loop liveness, not a looser
filter.** Shipped anyway because it is sound, gate-clean and closes the
question with a number; do not expect more from this shape.

### Validation (full CLAUDE.md bar)

Unit mirrors FIRST per §4: `work/refarg_test.py` NEW (24 cases) and
`work/lastdef_test.py` NEW (22 cases), both written before their code
existed. Existing suites unchanged: hoist 17/17, elseif 13/13, cse
30/30, flag 22/22, cp 20/20, re 0, selfcopy 5/5, forhead 10/10,
itfdispatch 14/14, callname 21/21.

Golden suite, clean revert/reapply A/B under `PYTHONHASHSEED=0`:
**7/50 before, 11/50 after** -- the 7 are the documented pre-existing
batch-44/45 drift (AudiencePath, CurrentDayManager, GameManager.
CheckAllReady, InputManager, InventoryManager.AssignTemplates,
LegsAnimator, SendMouseEvents), and the 4 new ones are read and are all
this batch's intended family: ActorCOMTransform.Update
(`TransformPoint(ref obj9)` -> `(&obj9)` -> `(obj9)`,
`this.transform.position = &obj9;` -> `= obj9;`), AddRandomVelocity.
Update (`AddForce(ref obj5, 2)` -> `AddForce(obj7, 2)`, the copy-prop
substitution the dropped `&` unblocks), LobbyMenu.Update, and
BurstSolverImpl.ApplyFrame -- the last being 133 diff lines of the
`((byte*)ref obj12 + 0x0)[0]` / `(ref this.m_InertialFrame).frame`
garbage 54b removes.

Full-corpus sweep (`work/sweep_1a_audit.py`, PYTHONHASHSEED=0):
```
b47_out1 baseline:  lines=1,911,718 crashes=2 (TMP caps) brace=0
                    into_block=15,418/3,957
54+54b:             lines=1,909,089 crashes=2 brace=0 into_block=15,416/3,956
54+54b+55+55b+54c:  lines=1,907,528 crashes=2 brace=0 into_block=15,416/3,956
```
0 new crashes (the 2 are the pre-existing TMP `cfg too large` caps), 0
brace imbalance, into_block -2 sites / -1 method (a dropped `&`
unblocks a copy-prop substitution that changes line adjacency; no CFG
shape change, as expected -- none of these fixes touches control flow).

Full rebuild `b48_out1`: 11,107 files / 115,658 bodies / 0 failed,
936.3s. Gate: **2/4,863/4 -- bad-file set UNCHANGED (the documented
legacy-TMP pair), ERROR 4,864 -> 4,863, the -1 entirely inside
TextMeshPro.cs** (3,161 -> 3,160; TextMeshProUGUI.cs byte-identical at
1,703). Per §4's rule the unchanged bad-file set IS the per-file diff.
Brace audit 0/11,107. Tree lines 2,630,326 -> 2,626,137 (**-4,189**,
matching the in-memory sweep to one line).

Readability deltas (b47_out1 -> b48_out1):
```
ref <local> renders              28,267 -> 7,244   (-21,023)
((byte*)ref / (ref this.          8,238 ->   531   (-7,707)
&<local>                         23,930 -> 29,003   (+5,073)
pure copy lines                 104,263 -> 100,914  (-3,349)
  escape_blocks                      234 ->    178
  escape_coexist/in_loop          13,039 ->  7,382
```
**The `&local` INCREASE is the intended honesty cost and should not be
read as a regression.** b47 spelled `ref` at 22,107 sites by comma
position; 7,244 of those are metadata-justified and stay, and most of
the rest revert to the raw `&` -- including the 7,707 that were
ungrammatical. The 531 surviving `(ref this.` sites are now genuinely
correct (`Interlocked.CompareExchange(ref this.myLock, 1, 0)`,
`ClampCaretPos(ref this.m_CaretSelectPosition)`). The residual `&local`
splits: raw pointer arithmetic on a local's address
(`((byte*)&objN + 0x10)[0]`, the pre-existing byte*-deref family, never
a call argument), `sub_x` unresolved helpers 6,080, indirect/vtable
1,641, address stores 3,929 -- every one a case where no metadata names
the parameter, i.e. honest by design.

### Residue, named precisely

- **Copy-prop residue (lead #4, item 1): the escape premise is CLOSED
  with data; the real residue is loop-carried (73.4%) and
  back-edge-reachable.** That needs real loop liveness on the flattened
  statement list -- a genuine analysis job, sized here but not
  attempted.
- **The tail-jmp `_call` path** (il2csharp.py ~3577) also never calls
  `_hint_arg_types`, so its `&` arguments keep the raw form: **71 lines
  tree-wide**, negligible, deliberately left.
- **The sret path's TYPE HINTING gap** (54c is render-only): that path
  never populates `slot_types`/`_type_hints` from `&s_N` arguments.
  Fixing it would shift resolved types tree-wide -- size it before
  attempting, do not fold it into a render change.
- **`out` vs `ref`** is unrecoverable from v31 metadata (no
  ParamAttributes). Everything byref renders `ref`.

Patches: `work/patch_b48_refargs.py` (54), `patch_b48b_addrlocal.py`
(54b), `patch_b48c_lastdef.py` (55), `patch_b48d_lastdef_fast.py` (55b),
`patch_b48e_sretargs.py` (54c) -- all binary CRLF per CLAUDE.md. New
tools: `work/probe_b48_refargs.py` (per-call declared-param vs
arg-register disasm probe), `work/probe_b48_relift.py`,
`work/census_b48_leaargs.py`, `work/census_b48_copyres.py`,
`work/census_b48_noread.py`. Build `work/run_build_b48.py` +
`work/build_b48.log`; gate report `work/ts_gate_b48_out1.txt`.

`b48_out1` is a verified gate-clean, crash-clean, brace-clean candidate
and supersedes `b47_out1` (strict superset: same source tree plus this
batch). Promotion over `final_out/` (= b42_out1) is a human call per the
standing rule (§0/§6).

