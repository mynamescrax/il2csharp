"""Only project a packed sign mask where the observed consumer takes lane zero."""
from types import SimpleNamespace as NS

import pytest

from dotnet_case import run_case
from il2cpp import Expr
from test_native_values import FLOAT, INT, execute, lifter


def masked(op, bits, after='f30f59c1', ty=FLOAT, flags=0x40000040, ret=None, math_abs=False):
    lift = lifter({'XMM0': Expr('x', ty, 'float'), 'XMM1': Expr('scale', FLOAT, 'float')})
    lift.bin.sections = [NS(name='.rdata', addr=0x2000, rawsize=16, chars=flags)]
    if ret is not None:
        lift._current_method = NS(return_type=0, name='Abs' if math_abs else 'Read')
        lift._current_td = NS(namespace='System' if math_abs else 'Demo', name='Math')
        lift.il.types = [ret]
    pool = Expr('packedMask', None, 'float')
    # Deliberately different high lanes: they cannot justify a scalar spelling.
    pool._bytes = bits.to_bytes(4, 'little') + bytes(range(12))
    lift._read_mem = lambda ins, asm: pool
    execute(lift, '0f' + op + '05f90f0000' + after)
    return lift.regs['XMM0'].text


@pytest.mark.parametrize('op,bits,tail,ty,flags', [
    ('57', 0x80000000, '', FLOAT, 0x40000040),             # whole register still packed
    ('57', 0x80000000, 'f20f59c1', FLOAT, 0x40000040),   # double consumer
    ('54', 0x7fc00000, 'f30f59c1', FLOAT, 0x40000040),   # also prints NaN, different bits
    ('54', 0x7fffffff, 'f30f59c1', INT, 0x40000040),     # unproved scalar float
    ('57', 0x80000000, 'f30f59c1', FLOAT, 0xc0000040),   # writable data
    ('57', 0x80000000, '0f28d0f30f59c1', FLOAT, 0x40000040),  # intervening packed read
])
def test_sign_mask_declines_other_uses(op, bits, tail, ty, flags):
    assert 'packedMask' in masked(op, bits, tail, ty, flags)


def test_emitted_sign_operations_match_float_bits(tmp_path):
    neg = masked('57', 0x80000000, '4531c0f30f59c1')     # xor r8d,r8d between the ops
    mag = masked('54', 0x7fffffff)
    direct_neg = masked('57', 0x80000000, 'c3', ret=FLOAT)
    intrinsic = masked('54', 0x7fffffff, 'c3', ret=FLOAT, math_abs=True)
    assert neg == '-x * scale'
    assert mag == 'System.Math.Abs(x) * scale'
    assert direct_neg == '-x'
    assert 'Math.Abs' not in intrinsic
    runner = tmp_path / 'runner'
    runner.mkdir()
    (runner / 'Program.cs').write_text('''using System;
static float Neg(float x, float scale) => NEG;
static float Abs(float x, float scale) => MAG;
static float Returned(float x) => RETURNED;
static float Intrinsic(float x) => INTRINSIC;
foreach (uint b in new uint[] {0, 0x80000000, 1, 0xff800000, 0xc0c00000, 0xffc00042}) {
    float x = BitConverter.UInt32BitsToSingle(b);
    if (BitConverter.SingleToUInt32Bits(Neg(x, 1f)) != (b ^ 0x80000000u) ||
        BitConverter.SingleToUInt32Bits(Abs(x, 1f)) != (b & 0x7fffffffu) ||
        BitConverter.SingleToUInt32Bits(Returned(x)) != (b ^ 0x80000000u) ||
        BitConverter.SingleToUInt32Bits(Intrinsic(x)) != (b & 0x7fffffffu))
        throw new Exception(b.ToString("x"));
}
Console.WriteLine("float bits OK");'''.replace('NEG', neg).replace('MAG', mag)
        .replace('RETURNED', direct_neg).replace('INTRINSIC', intrinsic), encoding='utf-8')
    assert 'float bits OK' in run_case(tmp_path, runner)


@pytest.mark.parametrize('ret', [INT, (0, 0x0d << 16), (0, (0x0c << 16) | (1 << 29))])
def test_mask_return_requires_by_value_single(ret):
    assert 'packedMask' in masked('57', 0x80000000, 'c3', ret=ret)
