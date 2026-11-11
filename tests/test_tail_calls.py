"""Exercise the real x64 JMP handler, not a reimplementation of the fix."""
from types import SimpleNamespace as NS

import pytest
from iced_x86 import Decoder

from il2cpp import Expr, Lifter, MethodDef, ParamDef

VOID = (0, 0x01 << 16)
BOOL = (0, 0x02 << 16)
INT = (0, 0x08 << 16)
FLOAT = (0, 0x0C << 16)
DOUBLE = (0, 0x0D << 16)
REF_INT = (0, (0x08 << 16) | (1 << 29))
REF_FLOAT = (0, (0x0C << 16) | (1 << 29))
POINTER = (0x1234, 0x0F << 16)
STRUCT = (0, 0x11 << 16)
GENERIC = (0, 0x15 << 16)


def make_lifter(params, regs, *, returns=VOID, static=True, name="Target", sret=False):
    target = 0x2000
    m = MethodDef(0, name, 0, 0, 0, -1, 1, 0x10 if static else 0, 0, 0, len(params))
    types = [returns] + params
    meta = NS(
        methods=[m],
        typedefs=[NS(name="Example", namespace="")],
        method_params=lambda method: [ParamDef(f"p{i}", i, i + 1) for i in range(len(params))],
    )
    il = NS(
        meta=meta,
        types=types,
        addr_candidates={target: [("method", 0)]},
        addr_to_method={target: ("method", 0)},
        function_extent=lambda va: (va, va + 16),
        returns_sret=lambda ty: sret,
        _type_enum=lambda ty: ((ty[1] >> 16) & 0xFF) if ty else None,
        type_from_ptr=lambda ptr: INT if ptr == POINTER[0] else None,
    )
    lift = Lifter.__new__(Lifter)
    lift.il, lift.meta = il, meta
    lift.bin = NS(is_exec_va=lambda va: va == target)
    lift.regs = {
        r: (e if isinstance(e, Expr) else Expr(e, None, "ptr" if e.startswith("&") else "int"))
        for r, e in regs.items()
    }
    lift.out = []
    lift.cur_va = 0x1000
    lift._type_hints, lift.slot_types = {}, {}
    lift._call_class_args = None
    lift._xmm_pending = []
    # jmp 0x2000 from 0x1000, as a real iced-x86 instruction.
    ins = Decoder(64, b"\xe9\xfb\x0f\x00\x00", ip=0x1000).decode()
    return lift, ins


def run_tail(params, regs, **kwargs):
    lift, ins = make_lifter(params, regs, **kwargs)
    lift._insn(ins, [ins], 0, None, ins.next_ip)
    return lift, " ".join(code for _, code, _ in lift.out)


def test_float_tail_uses_xmm_instead_of_stale_meaningful_gpr():
    _, text = run_tail(
        [DOUBLE, INT, INT],
        {"RCX": "typeof(Math)", "RDX": "digits", "R8": "0", "XMM0": "value"},
        returns=DOUBLE,
    )
    assert text == "return Example.Target(value, digits, 0); /* tail */"


def test_instance_mixed_signature_uses_parameter_position():
    _, text = run_tail(
        [FLOAT, INT, DOUBLE],
        {"RCX": "this", "RDX": "stale", "R8": "count", "R9": "unrelated",
         "XMM0": "wrong", "XMM1": "amount", "XMM3": "scale"},
        static=False,
    )
    assert text == "this.Target(amount, count, scale); return;"


@pytest.mark.parametrize("value,expected", [("0", "false"), ("1", "true")])
def test_boolean_tail_arguments(value, expected):
    _, text = run_tail([BOOL], {"RCX": value})
    assert text == f"Example.Target({expected}); return;"


def test_byref_integer_and_float_still_use_gprs():
    lift, text = run_tail(
        [REF_INT, REF_FLOAT],
        {"RCX": "&s_20", "RDX": "&t7", "XMM0": "wrong", "XMM1": "alsoWrong"},
    )
    assert text == "Example.Target(ref s_20, ref t7); return;"
    assert lift.slot_types["s_20"] == INT
    assert lift._type_hints["t7"] == FLOAT


def test_field_address_byref_is_rendered_as_ref():
    _, text = run_tail([REF_INT], {"RCX": "&this.position"})
    assert text == "Example.Target(ref this.position); return;"


def test_pointer_parameter_keeps_its_address():
    _, text = run_tail([POINTER], {"RCX": "&s_20"})
    assert text == "Example.Target(&s_20); return;"


def test_by_value_struct_is_not_rendered_as_ref():
    _, text = run_tail([STRUCT], {"RCX": "&s_20"})
    assert text == "Example.Target(s_20); return;"


def test_float_at_fifth_position_is_not_filled_by_xmm_tail():
    _, text = run_tail(
        [INT, INT, INT, INT, FLOAT],
        {"RCX": "a", "RDX": "b", "R8": "c", "R9": "d", "XMM0": "stale"},
    )
    assert text == "Example.Target(a, b, c, d); return;"


def test_unknown_float_register_does_not_reuse_gpr_or_old_pending():
    missing = Expr("v91", None, "?")
    missing._unk = True
    lift, ins = make_lifter([FLOAT], {"RCX": "stale", "XMM0": missing})
    lift._xmm_pending = [(0, Expr("previous_call_value", FLOAT, "float"))]
    lift._insn(ins, [ins], 0, None, ins.next_ip)
    text = " ".join(code for _, code, _ in lift.out)
    assert "stale" not in text
    assert "previous_call_value" not in text
    assert "v91" in text or "_" in text


def test_zero_arg_method_does_not_receive_xmm_residue():
    _, text = run_tail([], {"RCX": "junk", "XMM0": "junkFloat"})
    assert text == "Example.Target(); return;"


def test_sret_abi_is_left_unchanged_by_this_scoped_fix():
    _, text = run_tail([INT], {"RCX": "buffer", "RDX": "argument"}, returns=STRUCT, sret=True)
    assert text == "return Example.Target(buffer); /* tail */"


def test_generic_return_abi_is_not_guessed():
    _, text = run_tail([FLOAT], {"RCX": "legacy", "XMM0": "value"}, returns=GENERIC)
    assert text == "return Example.Target(legacy); /* tail */"


def test_nonfloat_tail_output_is_unchanged():
    _, text = run_tail([INT, INT], {"RCX": "first", "RDX": "second", "XMM2": "irrelevant"})
    assert text == "Example.Target(first, second); return;"

def test_proved_sqrt_helper_tail_uses_xmm0_without_gpr_spray():
    lift, ins = make_lifter(
        [], {"RAX": "stale", "RCX": "junk",
             "XMM0": Expr("value", DOUBLE, "float")}, returns=DOUBLE
    )
    lift.rt_sqrt = 0x2000
    lift._insn(ins, [ins], 0, None, ins.next_ip)
    text = " ".join(code for _, code, _ in lift.out)
    assert text == "return Math.Sqrt(value); /* tail */"
    assert "junk" not in text and "sub_" not in text
