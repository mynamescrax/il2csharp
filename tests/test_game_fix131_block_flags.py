"""Fix 131: a block opens with its predecessors' flags, not the flags of
whichever block the walk executed last.

Ground truth (disasm, Computer.ShouldRankBefore 0x18069C700):
`call rdx (Comparer<float>.Compare); test eax,eax; jne 7A0` and
`7A0: setg al; ret`.  The successor's `setg` reads that `test`, so the
body returns `Compare(a, b) > 0`.  `L.flags` is lifter-global and the jcc
consumed it, so 7A0 read the sibling return block's `shr eax,1Fh`
(`return num1 >> 31 > 0;` over an unassigned `num1`).
"""
import pytest

from test_game_goldens import game_decompiler

pytestmark = pytest.mark.game


def test_setg_after_jne_reads_the_compare_result(game_decompiler):
    il, dec = game_decompiler
    m = il.meta.methods[24622]
    assert m.name == 'ShouldRankBefore'
    text = '\n'.join(dec.lift_method(m, il.meta.typedefs[m.declaring]))
    assert 'int num1 = comparer11.Compare(candidate.score, existing.score);' in text
    assert 'return num1 > 0;' in text
    assert '>> 31 > 0' not in text
    # the call renders once: the successor's read binds the same temp
    assert text.count('.Compare(') == 1


def _lift(il, dec, mi, name):
    m = il.meta.methods[mi]
    assert m.name == name
    return '\n'.join(dec.lift_method(m, il.meta.typedefs[m.declaring]))


def test_store_does_not_freeze_the_flags_sentinel(game_decompiler):
    # `if (this.voiceConnection == null) { ...; this.voiceConnection = x; }`:
    # the then-block inherits the jcc's pair; the store must not freeze the
    # `!flags` merge sentinel into an `object objN = <operand>` twin.
    il, dec = game_decompiler
    text = _lift(il, dec, 24944, 'Awake')
    assert 'if (this.voiceConnection == null)' in text
    assert '= (this.voiceConnection == null);' not in text
    assert text.count('UnityEngine.Object.op_Implicit(this.dropdown)') == 2


def test_flags_phi_keeps_pass_numbering(game_decompiler):
    # restoring flags into blocks that never read them added pass-2 flags
    # phis; each drew a `v` number and shifted later clobber placeholders
    # against pass 1's back-edge names: spurious R8/R9 phis became
    # undeclared extra args of the multi-dim array ctor
    il, dec = game_decompiler
    text = _lift(il, dec, 23554, 'DrawCurved')
    assert '(object[,])sub_180434660(typeof(object[,]), &vector31);' in text


def test_flagless_arms_pass_the_pair_through(game_decompiler):
    # math.uint2(float) 0x182701340: `comiss xmm1,xmm0; jbe A` -> both arms
    # (`cvttss2si; jmp J` / `cvttss2si`) write no flags -> `J: ...; jbe`
    # re-reads the comiss. All predecessors agreeing on "no pair" used to
    # crash the restore (TypeError -> unstructured `if (? <= ?) goto`).
    il, dec = game_decompiler
    text = _lift(il, dec, 68399, 'uint2')
    assert 'if (0f <= v)' in text
    assert '?' not in text and 'unknown' not in text


def test_restored_operands_do_not_bind_the_loop_bound(game_decompiler):
    # 0x18054786C `cmp ebx,[rsi+18h]; jge exit` then `movsxd; jae throw`
    # (the bounds check reuses the loop test). The body's read of the
    # restored pair must not bind the header's `.Length` load into the body
    il, dec = game_decompiler
    text = _lift(il, dec, 25872, 'Update')
    assert 'for (int num6 = 0; num6 < obj' not in text  # fix 125/126: num5 -> num6
    assert 'for (int num6 = 0; num6 < UnityEngine.Object.FindObjectsByType' in text
