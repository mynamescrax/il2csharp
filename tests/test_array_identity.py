"""One native array allocation, one reference, one store per GC twin."""
import pytest
from types import SimpleNamespace as NS

from iced_x86 import Decoder

from il2cpp import Decompiler
from il2cpp import Expr
from test_native_values import ARRAY, lifter, execute

STRING = (0, 0x0E << 16)


def string_array_lifter():
    lift = lifter()
    lift.il.type_from_ptr = lambda ptr: STRING if ptr == ARRAY[0] else None
    return lift


def test_short_array_allocation_is_materialized_at_its_instruction():
    lift = string_array_lifter()
    result = lift._array_allocation("new string[2]", ARRAY, 0x1000, None)
    assert result.text == "t0" and result.kind == "arr" and result.ty == ARRAY
    assert lift.out == [(0x1000, "var t0 = new string[2];", None)]
    assert lift._var_types["t0"] == ARRAY


def test_identical_allocations_remain_distinct_objects():
    lift = string_array_lifter()
    first = lift._array_allocation("new string[2]", ARRAY, 0x1000, None)
    second = lift._array_allocation("new string[2]", ARRAY, 0x1020, None)
    assert (first.text, second.text) == ("t0", "t1")
    assert len(lift.out) == 2


def test_dry_pass_has_the_same_identity_without_emitting_statements():
    lift = string_array_lifter()
    lift.dry = True
    result = lift._array_allocation("new string[2]", ARRAY, 0x1000, None)
    assert result.text == "t0" and lift.out == []
    assert lift._var_types == {}


def test_loop_placement_guard_remains_in_force():
    lift = string_array_lifter()
    lift._memory_rhs_loop_guard = True
    result = lift._array_allocation("new string[2]", ARRAY, 0x1000, None)
    assert result.text == "new string[2]" and lift.out == []


def test_cfg_proof_can_accept_acyclic_backward_shared_tails():
    # Native instruction order is 0,1,2 but flow is 0 -> 2 -> 1 -> exit.
    blocks = [NS(succs=s, insns=[], term=("jmp",)) for s in ([2], [], [1])]
    assert Decompiler._allocation_needs_loop_guard(blocks) is False
    lift = string_array_lifter()
    lift._memory_rhs_loop_guard = True
    lift._array_allocation_loop_guard = False
    assert lift._array_allocation("new string[2]", ARRAY, 0x1000, None).text == "t0"


@pytest.mark.parametrize("edges", [
    [[0]], [[1], [0]], [[1, 2], [2], [1]], [[], [1]],  # includes unreachable cycles
])
def test_cfg_cycle_is_not_mistaken_for_a_shared_tail(edges):
    blocks = [NS(succs=s, insns=[], term=("jmp",)) for s in edges]
    assert Decompiler._allocation_needs_loop_guard(blocks) is True


def test_unresolved_indirect_dispatch_is_not_an_acyclicity_proof():
    jump = Decoder(64, bytes.fromhex("ffe0"), ip=0x1000).decode()
    block = NS(succs=[], insns=[jump], term=("stop",))
    assert Decompiler._allocation_needs_loop_guard([block]) is True


def test_fully_prewired_acyclic_switch_is_allowed():
    jump = Decoder(64, bytes.fromhex("ffe0"), ip=0x1000).decode()
    blocks = [NS(succs=[1, 2], insns=[jump], term=("switch",)),
              NS(succs=[], insns=[], term=("ret",)),
              NS(succs=[], insns=[], term=("ret",))]
    assert Decompiler._allocation_needs_loop_guard(blocks) is False


@pytest.mark.parametrize("offset,index", [("20", "0x0"), ("28", "0x1"), ("70", "0xa")])
def test_string_element_address_uses_the_same_lvalue_as_the_store(offset, index):
    lift = string_array_lifter()
    lift.regs = {"RBX": Expr("t0", ARRAY, "arr"), "RDX": Expr('"value"', STRING, "str")}
    execute(lift, "488953" + offset)  # mov [rbx+offset],rdx
    execute(lift, "488d4b" + offset)  # lea rcx,[rbx+offset]
    pointer = lift.regs["RCX"]
    assert pointer.text == f"&t0[{index}]" and pointer.ty == STRING
    dst, src = lift._wb_operands([pointer.text, '"value"'], [pointer, lift.regs["RDX"]])
    lift._wb_finish(0x1010, dst, src, None)
    assert [line for _, line, _ in lift.out] == [f't0[{index}] = "value";']


def test_barrier_to_a_different_element_is_not_dropped():
    lift = string_array_lifter()
    lift.regs = {"RBX": Expr("t0", ARRAY, "arr"), "RDX": Expr('"value"', STRING, "str")}
    execute(lift, "48895320")
    execute(lift, "488d4b28")
    pointer = lift.regs["RCX"]
    dst, src = lift._wb_operands([pointer.text, '"value"'], [pointer, lift.regs["RDX"]])
    lift._wb_finish(0x1010, dst, src, None)
    assert len(lift.out) == 2


def test_allocation_reference_is_reused_across_native_register_copies():
    lift = string_array_lifter()
    array = lift._array_allocation("new string[2]", ARRAY, 0x1000, None)
    lift.regs = {"RAX": array, "RDX": Expr('"value"', STRING, "str")}
    execute(lift, "4889c34889532048895328")  # rbx=rax; two stores
    text = "\n".join(line for _, line, _ in lift.out)
    assert text.count("new string[2]") == 1
    assert 't0[0x0] = "value";' in text
    assert 't0[0x1] = "value";' in text


VECTOR = (0, 0x11 << 16)


def stride_lifter(stride):
    """Array of a 12-byte (or given-stride) element type."""
    lift = string_array_lifter()
    lift.il.type_from_ptr = lambda ptr: VECTOR if ptr == ARRAY[0] else None
    lift.il._sf_field_size = lambda fty, depth: stride if fty == VECTOR else None
    return lift


def test_array_constant_offset_divides_by_element_stride():
    # 12-byte elements: [arr+0x2c] is element 1, regardless of the 8-byte
    # access width the instruction reads it with.
    lift = stride_lifter(12)
    e = lift._field_expr(Expr("t0", ARRAY, "arr"), 0x2C, 8)
    assert e.text == "t0[0x1]"


def test_array_mid_element_offset_keeps_the_raw_deref():
    lift = stride_lifter(12)
    e = lift._field_expr(Expr("t0", ARRAY, "arr"), 0x26, 8)
    assert e.text == "*(t0 + 0x26)"


def test_array_unknown_stride_keeps_the_raw_deref():
    lift = stride_lifter(None)
    e = lift._field_expr(Expr("t0", ARRAY, "arr"), 0x2C, 8)
    assert e.text == "*(t0 + 0x2c)"