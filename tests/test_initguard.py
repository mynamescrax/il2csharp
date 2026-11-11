"""Metadata-init flag guards (`il2cpp/initguard.py`), pinned with synthetic bytes.

The census that set the windows (116,178 methods, 64,017 guards on the
fixture) is in the module docstring; these tests pin each shape the scan
claims, with no fixture. `_old_stage1` is the pre-fix scan from
`Decompiler._guards` (MOV/MOVZX gap within four instructions, 24-instruction
body), kept as the oracle: the new scan must never drop what it skipped.
"""
import random

import pytest

from il2cpp.prelude import HAVE_ICED

pytestmark = pytest.mark.skipif(not HAVE_ICED, reason='iced_x86 required')

from il2cpp.prelude import FlowControl, IReg, Mnemonic, OpKind  # noqa: E402
from il2cpp.initguard import BODY_MAX, GAP_MAX, metadata_init_guards  # noqa: E402
from il2cpp.text import imm_of  # noqa: E402
from synth_x64 import Asm  # noqa: E402

SLOT = 0x183E78BFA
SLOT2 = 0x183E78C00
INIT = 0x180435400
OTHER = 0x180111110
STR = 0x183BFCAE0

MOV = '44 89 cf'                       # mov edi,r9d
MOVAPS_LD = '0f 28 74 24 20'           # movaps xmm6,[rsp+20h]
MOVUPS_LD = '0f 10 4c 24 20'           # movups xmm1,[rsp+20h]
MOVSS_LD = 'f3 0f 10 44 24 20'         # movss xmm0,[rsp+20h]
MOVSD_RR = 'f2 0f 10 c8'               # movsd xmm1,xmm0 (SSE scalar)
MOVSD_STR = 'a5'                       # movsd [rdi],[rsi] (string op, same mnemonic)
MULSS = 'f3 0f 59 c1'                  # mulss xmm0,xmm1 (arithmetic, EFLAGS untouched)
LEA_RDX = '48 8d 54 24 20'             # lea rdx,[rsp+20h]
ADD = '83 c0 01'                       # add eax,1   (writes EFLAGS)
XOR = '31 c0'                          # xor eax,eax (writes EFLAGS)
UCOMISS = '0f 2e c1'                   # ucomiss xmm0,xmm1 (writes EFLAGS)
CMP_RR = '48 39 c8'                    # cmp rax,rcx (writes EFLAGS)
CMOVNE = '0f 45 c1'                    # cmovne eax,ecx (reads EFLAGS)
JE0 = '74 00'                          # je +0 (control flow)
LOCK_OR = 'f0 83 0c 24 00'             # lock or dword [rsp],0
LOCK_OR_REG = 'f0 09 04 24'            # lock or [rsp],eax


def _prog(gap='', pairs=1, before='', after='', store_val=1, store_slot=SLOT,
          cmp_imm=0, tail_nops=0, cmp_dword=False):
    a = Asm()
    if cmp_dword:
        a.cmp_d(SLOT, cmp_imm)
    else:
        a.cmp_b(SLOT, cmp_imm)
    if gap:
        a.raw(gap)
    a.jne('T')
    if before:
        a.raw(before)
    for _ in range(pairs):
        a.lea_rcx(STR).call(INIT)
    if after:
        a.raw(after)
    a.st_b(store_slot, store_val)
    for _ in range(tail_nops):
        a.nop()
    a.label('T').ret()
    return a


def _bookkeeping(insns, slot=SLOT):
    """The ips a recognized guard must skip: cmp, jne, lea rcx, call INIT, flag store."""
    out = set()
    for i in insns:
        if i.mnemonic in (Mnemonic.CMP, Mnemonic.JNE):
            out.add(i.ip)
        elif i.mnemonic == Mnemonic.LEA and i.op0_register == IReg.RCX:
            out.add(i.ip)
        elif i.mnemonic == Mnemonic.CALL and i.near_branch_target == INIT:
            out.add(i.ip)
        elif (i.mnemonic == Mnemonic.MOV and i.op0_kind == OpKind.MEMORY
              and i.memory_base == IReg.RIP and i.ip_rel_memory_address == slot):
            out.add(i.ip)
    return out


def _skip(a):
    return metadata_init_guards(a.insns(), INIT)


def _old_stage1(raw, init_meta):
    skip = set()
    for i, ins in enumerate(raw):
        if ins.mnemonic == Mnemonic.CMP and ins.op0_kind == OpKind.MEMORY \
                and ins.memory_base == IReg.RIP and ins.memory_size == 1 \
                and imm_of(ins, 1) == 0:
            slot = ins.ip_rel_memory_address
            j = None
            for k in range(i + 1, min(i + 5, len(raw))):
                w = raw[k]
                if w.flow_control == FlowControl.CONDITIONAL_BRANCH and w.op0_kind == OpKind.NEAR_BRANCH64:
                    j = k
                    break
                if w.mnemonic not in (Mnemonic.MOV, Mnemonic.MOVZX):
                    break
            if j is None:
                continue
            T = raw[j].near_branch_target
            found = False
            for k in range(j + 1, min(j + 24, len(raw))):
                w = raw[k]
                if w.mnemonic == Mnemonic.MOV and w.op0_kind == OpKind.MEMORY \
                        and w.memory_base == IReg.RIP and w.memory_size == 1 \
                        and w.ip_rel_memory_address == slot and imm_of(w, 1) == 1:
                    if w.next_ip == T or (k + 1 < len(raw) and raw[k + 1].ip == T):
                        found = True
                    break
                if w.mnemonic not in (Mnemonic.LEA, Mnemonic.MOV, Mnemonic.CALL,
                                      Mnemonic.MOVZX, Mnemonic.XOR, Mnemonic.PUSH, Mnemonic.SUB):
                    break
                if w.ip >= T:
                    break
            if not found:
                continue
            skip.add(ins.ip)
            skip.add(raw[j].ip)
            for k in range(j + 1, len(raw)):
                w = raw[k]
                if w.mnemonic == Mnemonic.MOV and w.op0_kind == OpKind.MEMORY \
                        and w.memory_base == IReg.RIP and w.memory_size == 1 \
                        and w.ip_rel_memory_address == slot:
                    skip.add(w.ip)
                    break
                if w.mnemonic == Mnemonic.LEA and w.op0_register == IReg.RCX \
                        and w.memory_base == IReg.RIP:
                    skip.add(w.ip)
                elif w.mnemonic == Mnemonic.CALL and w.op0_kind == OpKind.NEAR_BRANCH64 \
                        and w.near_branch_target == init_meta:
                    skip.add(w.ip)
    return skip


# ---------------------------------------------------------------- shapes

def test_plain_guard_skips_exactly_its_bookkeeping():
    a = _prog()
    insns = a.insns()
    assert len(insns) == 6
    assert metadata_init_guards(insns, INIT) == _bookkeeping(insns)
    assert metadata_init_guards(insns, INIT) == _old_stage1(insns, INIT)


def test_gap_beyond_four_instructions_is_recognized():
    # the jne is the sixth instruction after the cmp: the old window stopped at four
    a = _prog(gap=MOV * 5)
    insns = a.insns()
    assert _old_stage1(insns, INIT) == set()
    assert metadata_init_guards(insns, INIT) == _bookkeeping(insns)


def test_gap_window_edge():
    ok = _prog(gap=MOV * (GAP_MAX - 1))        # jne exactly GAP_MAX instructions after the cmp
    too_far = _prog(gap=MOV * GAP_MAX)
    assert metadata_init_guards(ok.insns(), INIT) == _bookkeeping(ok.insns())
    assert metadata_init_guards(too_far.insns(), INIT) == set()


@pytest.mark.parametrize('gap', [
    MOVAPS_LD, MOVUPS_LD, MOVSS_LD, MOVSD_RR, MULSS, LEA_RDX,
    MOVAPS_LD + MOVUPS_LD + MOVSS_LD + MULSS + LEA_RDX,
])
def test_gap_that_leaves_eflags_alone_is_recognized(gap):
    a = _prog(gap=gap)
    insns = a.insns()
    assert metadata_init_guards(insns, INIT) == _bookkeeping(insns)


@pytest.mark.parametrize('gap', [ADD, XOR, UCOMISS, CMP_RR, MOV + ADD])
def test_gap_that_writes_eflags_declines(gap):
    # the jne would consume the intervening instruction's flags, not the cmp's
    assert _skip(_prog(gap=gap)) == set()


def test_gap_that_reads_eflags_declines():
    assert _skip(_prog(gap=CMOVNE)) == set()


def test_branch_in_gap_declines():
    assert _skip(_prog(gap=JE0)) == set()


def test_body_longer_than_the_old_window_is_recognized():
    # 40 inlined inits put the flag store 81 instructions past the jne
    a = _prog(pairs=40)
    insns = a.insns()
    assert len(insns) > 24 + 3
    assert _old_stage1(insns, INIT) == set()
    got = metadata_init_guards(insns, INIT)
    assert got == _bookkeeping(insns)
    assert sum(1 for i in insns if i.ip in got and i.mnemonic == Mnemonic.CALL) == 40
    assert 2 * 40 + 1 < BODY_MAX


@pytest.mark.parametrize('piece', [MOVAPS_LD, MOVUPS_LD, MOVSS_LD, MOVSD_RR,
                                   '66 48 0f 6e c0', '66 0f 6e c0', '66 0f 6f 44 24 20',
                                   'f3 0f 6f 44 24 20', '48 63 c1', '0f be c1'])
def test_body_data_moves_are_allowed(piece):
    a = _prog(before=piece)
    insns = a.insns()
    got = metadata_init_guards(insns, INIT)
    assert got == _bookkeeping(insns)
    # the data move is real code: it keeps lifting
    moved = [i for i in insns if i.ip not in got and i.ip not in
             {insns[0].ip, insns[-1].ip}]
    assert any(i.ip not in _bookkeeping(insns) for i in moved)


def test_body_control_flow_declines():
    assert _skip(_prog(after=JE0)) == set()
    assert _skip(_prog(before='eb 00')) == set()


def test_string_movsd_is_not_a_data_move():
    assert _skip(_prog(before=MOVSD_STR)) == set()
    assert _skip(_prog(before=MOVSD_RR)) != set()


def test_flag_store_must_land_on_the_branch_target():
    a = _prog(tail_nops=1)           # a nop sits between the store and T
    assert _skip(a) == set()


def test_cmp_must_be_a_byte_compare_against_zero():
    assert _skip(_prog(cmp_dword=True)) == set()
    assert _skip(_prog(cmp_imm=1)) == set()


def test_flag_store_must_set_one():
    assert _skip(_prog(store_val=0)) == set()


def test_store_to_another_cell_is_not_this_guard():
    assert _skip(_prog(store_slot=SLOT2)) == set()


def test_call_to_another_helper_is_not_skipped():
    a = Asm()
    a.cmp_b(SLOT).jne('T').lea_rcx(STR).call(OTHER).st_b(SLOT).label('T').ret()
    insns = a.insns()
    got = metadata_init_guards(insns, INIT)
    calls = [i for i in insns if i.mnemonic == Mnemonic.CALL]
    assert calls and all(c.ip not in got for c in calls)
    assert insns[0].ip in got and insns[1].ip in got


def test_two_guards_in_one_method():
    a = Asm()
    a.cmp_b(SLOT).jne('T1').lea_rcx(STR).call(INIT).st_b(SLOT).label('T1')
    a.raw(MOV)
    a.cmp_b(SLOT2).raw(MOVAPS_LD).jne('T2').lea_rcx(STR).call(INIT).st_b(SLOT2).label('T2').ret()
    insns = a.insns()
    got = metadata_init_guards(insns, INIT)
    assert sum(1 for i in insns if i.ip in got and i.mnemonic == Mnemonic.CMP) == 2
    assert sum(1 for i in insns if i.ip in got and i.mnemonic == Mnemonic.JNE) == 2


# ---------------------------------------------------------------- barrier

def test_barrier_after_the_init_call_is_part_of_the_guard():
    a = _prog(after=LOCK_OR)
    insns = a.insns()
    got = metadata_init_guards(insns, INIT)
    barrier = next(i for i in insns if i.mnemonic == Mnemonic.OR)
    assert barrier.ip in got
    assert got == _bookkeeping(insns) | {barrier.ip}
    assert _old_stage1(insns, INIT) == set()


def test_barrier_before_any_init_call_declines():
    assert _skip(_prog(before=LOCK_OR)) == set()


def test_barrier_needs_an_immediate_zero_source():
    assert _skip(_prog(after=LOCK_OR_REG)) == set()


def test_barrier_outside_a_guard_is_left_alone():
    a = Asm()
    a.raw(LOCK_OR).ret()
    assert _skip(a) == set()


# ---------------------------------------------------------------- oracle

_GAPS = ['', MOV, MOV * 3, MOV * 4, MOVAPS_LD, MULSS, ADD, XOR, CMOVNE, JE0, LEA_RDX]
_BEFORE = ['', MOV, MOVAPS_LD, MOVSD_STR, JE0, LOCK_OR]
_AFTER = ['', MOV, XOR, MOVSS_LD, JE0, LOCK_OR]


def _pick(rng, benign, menu, p=0.8):
    """Mostly the shape the old scan accepts, sometimes anything on the menu."""
    return benign if rng.random() < p else rng.choice(menu)


def test_never_drops_what_the_old_scan_skipped():
    rng = random.Random(0x1A2B3C)
    recognized_by_old = 0
    for _ in range(3000):
        a = _prog(gap=_pick(rng, rng.choice(['', MOV, MOV * 3]), _GAPS),
                  pairs=_pick(rng, rng.choice([1, 2, 5, 11]), [0, 1, 12, 30, 40]),
                  before=_pick(rng, rng.choice(['', MOV]), _BEFORE),
                  after=_pick(rng, rng.choice(['', MOV]), _AFTER),
                  store_val=_pick(rng, 1, [0, 2]), store_slot=_pick(rng, SLOT, [SLOT2]),
                  cmp_imm=_pick(rng, 0, [1]), tail_nops=_pick(rng, 0, [1]),
                  cmp_dword=rng.random() < 0.05)
        insns = a.insns()
        old = _old_stage1(insns, INIT)
        new = metadata_init_guards(insns, INIT)
        assert old <= new, (a.assemble().hex(), sorted(old - new))
        if old:
            recognized_by_old += 1
            # a single guard the old scan already took: same skip set (no barrier in these)
            if LOCK_OR.replace(' ', '') not in a.assemble().hex():
                assert new == old, a.assemble().hex()
    assert recognized_by_old > 200
