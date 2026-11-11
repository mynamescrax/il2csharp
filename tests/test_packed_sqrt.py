"""Portable proof and instruction tests for packed low-lane sqrt recovery."""
from iced_x86 import Decoder

from il2cpp import Decompiler
from il2cpp import Expr
from test_native_values import FLOAT, execute, lifter

DOUBLE = (0, 0x0D << 16)


def decode(hex_bytes):
    return list(Decoder(64, bytes.fromhex(hex_bytes), ip=0x1000))


def test_proof_pairs_only_the_exact_scalar_helper_diamond():
    # xorps zero; cvtps2pd; ucomisd; ja helper-arm; sqrtpd; jmp join;
    # movaps XMM0,input; call scalar helper; cvtsd2ss at the join.
    insns = decode(
        "0f57d2" "0f5ac8" "660f2ed1" "7706" "660f51c1" "eb08"
        "0f28c1" "e8e60f0000" "f20f5ac0"
    )
    sites = Decompiler._sqrt_low_lane_sites(insns, 0x2000)
    assert sites == {
        "convert": {0x1003},
        "root": {0x100C},
        "narrow": set(),
    }

    # The address is evidence: an otherwise identical call to another helper
    # cannot authorize packed scalarization.
    assert Decompiler._sqrt_low_lane_sites(insns, 0x2001) == {
        "convert": set(), "root": set(), "narrow": set()
    }


def test_proof_records_only_normal_arm_packed_narrowing():
    insns = decode(
        "0f57d2" "0f5ac8" "660f2ed1" "770a" "660f51c1"
        "660f5ac0" "eb08" "0f28c1" "e8e20f0000" "90"
    )
    sites = Decompiler._sqrt_low_lane_sites(insns, 0x2000)
    assert sites["convert"] == {0x1003}
    assert sites["root"] == {0x100C}
    assert sites["narrow"] == {0x1010}


def test_proved_packed_pipeline_retains_scalar_widths():
    lift = lifter({"XMM0": Expr("value", FLOAT, "float")})
    lift._sqrt_low_sites = {
        "convert": {0x1000},
        "root": {0x1003},
        "narrow": {0x1007},
    }
    execute(lift, "0f5ac8" "660f51c1" "660f5ac0")

    result = lift.regs["XMM0"]
    assert result.text == "(float)(Math.Sqrt((double)(value)))"
    assert result.ty == FLOAT


def test_unproved_packed_conversion_is_not_generalized():
    lift = lifter({"XMM0": Expr("value", FLOAT, "float"),
                   "XMM1": Expr("stale", DOUBLE, "float")})
    lift._sqrt_low_sites = {"convert": set(), "root": set(), "narrow": set()}
    execute(lift, "0f5ac8")
    assert lift.regs["XMM1"].text == "stale"
