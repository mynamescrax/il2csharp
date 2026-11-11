"""Real SQRTSS/SQRTSD instructions must retain result width and unknowns."""
import pytest

from il2cpp import Expr
from test_native_values import lifter, execute

FLOAT = (0, 0x0C << 16)
DOUBLE = (0, 0x0D << 16)


@pytest.mark.parametrize("encoding,ty,expected", [
    ("f30f51c1", FLOAT, "(float)Math.Sqrt(value)"),
    ("f20f51c1", DOUBLE, "Math.Sqrt(value)"),
])
def test_register_source_retains_actual_result_type(encoding, ty, expected):
    lift = lifter({"XMM0": Expr("stale", None, "float"),
                   "XMM1": Expr("value", ty, "float")})
    execute(lift, encoding)
    assert lift.regs["XMM0"].text == expected
    assert lift.regs["XMM0"].ty == ty


@pytest.mark.parametrize("encoding", ["f30f51c1", "f20f51c1"])
def test_missing_source_is_not_fabricated_zero(encoding):
    lift = lifter({"XMM0": Expr("stale", None, "float")})
    execute(lift, encoding)
    assert "Math.Sqrt(?)" in lift.regs["XMM0"].text
    assert "stale" not in lift.regs["XMM0"].text


def test_float_memory_source_gets_an_explicit_float_result():
    lift = lifter(fields={0x10: ("value", 0)}, field_types=[FLOAT])
    execute(lift, "f30f514110")  # sqrtss xmm0,[rcx+10h]
    assert lift.regs["XMM0"].text == "(float)Math.Sqrt(this.value)"
    assert lift.regs["XMM0"].ty == FLOAT

@pytest.mark.parametrize("rty,expected", [
    (FLOAT, "XMM0"),
    (DOUBLE, "XMM0"),
    ((0, (0x0C << 16) | (1 << 29)), "RAX"),
    ((0, (0x0D << 16) | (1 << 29)), "RAX"),
    ((0, 0x08 << 16), "RAX"),
])
def test_win64_return_register_respects_byref(rty, expected):
    from il2cpp import Lifter
    assert Lifter._return_value_register(rty) == expected


@pytest.mark.parametrize("selected,expected", [
    ("XMM0", "return realValue;"),
    ("RAX", "return integerValue;"),
])
def test_flat_ret_uses_method_metadata_register(selected, expected):
    lift = lifter({
        "RAX": Expr("integerValue", (0, 0x08 << 16), "int"),
        "XMM0": Expr("realValue", FLOAT, "float"),
    })
    lift._return_reg = selected
    assert execute(lift, "c3") == [expected]
