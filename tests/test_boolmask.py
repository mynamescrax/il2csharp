"""Instruction-level guards for Boolean NEG/SBB masks and conditional bit adds."""
from iced_x86 import Decoder
import pytest

from il2cpp.cfg import Block, _Sink
from il2cpp.expr import Expr
from test_native_values import BOOL, INT, lifter


SEED = '0fb64110 f6d8 19d2 83e202'  # load AL; neg al; sbb edx,edx; and edx,2
SELECT = '448bc2 4183c804 80791100 440f44c2'
LAST = '418bc0 83c810 80791200 410f44c0'    # third bit = 16, not the game's 8


def run_mask(parts, *, types=None, conflicting=False):
    lift = lifter(fields={16:('one',0),17:('two',1),18:('three',2)}, field_types=types or [BOOL]*3)
    lift.regs['RDX'] = Expr('oldDestination', INT, 'int')
    ip = 0x3000
    lift._blocks = []
    for bid, part in enumerate(parts):
        seq = list(Decoder(64, bytes.fromhex(part), ip=ip))
        b = Block(bid, seq)
        if bid:
            b.preds = [0, 2] if conflicting else [0]
        lift._blocks.append(b)
        lift.out = _Sink(b)
        for j, ins in enumerate(seq):
            lift._insn(ins, seq, j, None, seq[-1].next_ip)
        b.end_state = dict(lift.regs)
        ip = seq[-1].next_ip
    return lift.regs


def is_mask(expr):
    return getattr(expr, '_mask_step', (None,))[0] == 'mask'


def test_self_borrow_ignores_old_destination():
    result = run_mask([SEED])['RDX']
    assert result.text == '(this.one ? 2 : 0)' and result.ty == INT


@pytest.mark.parametrize('code', [
    SEED.replace('f6d8', 'f6d9'),        # neg cl after loading al
    SEED.replace('f6d8', 'f6dc'),        # high-byte alias
    SEED.replace('f6d8', 'f7d8'),        # wrong NEG width
    SEED.replace('19d2', '19ca'),        # different SBB inputs (edx -= ecx + CF)
    SEED.replace('19d2', '6619d2'),      # partial destination
    SEED.replace('19d2', '85c0 19d2'),   # intervening TEST cleared CF
    SEED.replace('0fb64110', '0fb74110'), # wider load
    SEED.replace('83e202', '83e102'),    # masking a different register
])
def test_unproved_carry_does_not_produce_a_boolean_mask(code):
    assert not is_mask(run_mask([code])['RDX'])


def test_nonboolean_field_does_not_prove_a_boolean_load():
    assert not is_mask(run_mask([SEED], types=[INT,BOOL,BOOL])['RDX'])


@pytest.mark.parametrize('selector', [SELECT.replace('440f44c2','440f45c2'), # cmovne reverses the choice
                                      SELECT.replace('448bc2','448bc0'),     # d started with another value
                                      SELECT.replace('80791100','80791101')])
def test_unproved_select_is_not_a_conditional_bit_add(selector):
    assert not is_mask(run_mask([SEED + selector])['R8'])


def test_cmov_can_follow_single_null_guard_but_not_conflicting_merge():
    sections = [SEED + SELECT + '4885db 7406', LAST]
    value = run_mask(sections)['RAX']
    assert is_mask(value) and value.text == '(this.one ? 2 : 0) | (this.two ? 4 : 0) | (this.three ? 16 : 0)'
    assert not is_mask(run_mask(sections, conflicting=True)['RAX'])
