"""Win64 stack arguments and stack parameters keep their real positions."""
from types import SimpleNamespace as NS

from iced_x86 import Decoder

from il2cpp import Expr, Lifter, MethodDef, ParamDef
from test_native_values import execute

VOID = (0, 0x01 << 16)
INT = (0, 0x08 << 16)
FLOAT = (0, 0x0C << 16)
REF_FLOAT = (0, (0x0C << 16) | (1 << 29))


def make_call_lifter(params, regs, *, returns=VOID, static=True, name="Target"):
    target = 0x2000
    m = MethodDef(0, name, 0, 0, 0, -1, 1, 0x10 if static else 0, 0, 0, len(params))
    types = [returns] + params
    meta = NS(
        methods=[m],
        typedefs=[NS(name="Example", namespace="", is_valuetype=False)],
        method_params=lambda method: [ParamDef(f"p{i}", i, i + 1) for i in range(len(params))],
    )
    il = NS(
        meta=meta,
        types=types,
        addr_candidates={target: [("method", 0)]},
        addr_to_method={target: ("method", 0)},
        function_extent=lambda va: (va, va + 16),
        returns_sret=lambda ty: False,
        _type_enum=lambda ty: ((ty[1] >> 16) & 0xFF) if ty else None,
        type_from_ptr=lambda ptr: None,
    )
    lift = Lifter.__new__(Lifter)
    lift.il, lift.meta = il, meta
    lift.bin = NS(is_exec_va=lambda va: va == target, qword=lambda addr: None)
    lift.regs = {r: (e if isinstance(e, Expr) else Expr(e, None, "float" if r.startswith("XMM") else "int"))
                 for r, e in regs.items()}
    lift.out = []
    lift.cur_va = 0x1000
    lift._type_hints, lift._var_types = {}, {}
    lift.slot_types, lift.stack_map, lift.stack_values, lift.addr_of = {}, {}, {}, {}
    lift.rsp_delta = lift.var_n = 0
    lift._call_class_args = None
    lift._xmm_pending = []
    lift.rt_init_meta = None
    lift.rethrow_va = None
    lift.raise_va = None
    lift.rt_value_box = None
    lift.rt_alloc = None
    lift.rt_arrnew = set()
    lift.rt_wbarrier = set()
    lift.rt_names = {}
    lift.vt_recv_slot = None
    lift.vt_recv = None
    lift.dry = lift.asm_comments = lift._copying = False
    lift._cur_ip = 0
    lift.flags = None
    ins = Decoder(64, b"\xe8\xfb\x0f\x00\x00", ip=0x1000).decode()  # call 0x2000
    return lift, ins


def test_resolved_call_recovers_the_fifth_stack_argument_without_xmm_tail_noise():
    lift, ins = make_call_lifter(
        [INT, INT, INT, INT, INT],
        {"RCX": "a", "RDX": "b", "R8": "c", "R9": "d", "XMM0": Expr("stale", FLOAT, "float")},
        returns=INT,
    )
    lift.stack_map[0x20] = "s_20"
    lift.stack_values["s_20"] = Expr("e", INT, "int")
    lift._insn(ins, [ins], 0, None, ins.next_ip)
    assert lift.regs["RAX"].text == "Example.Target(a, b, c, d, e)"
    assert "stale" not in lift.regs["RAX"].text


def test_entry_stack_parameter_survives_fixed_frame_allocation():
    m = MethodDef(0, "StackArgUser", 0, 0, 0, -1, 1, 0x10, 0, 0, 5)
    meta = NS(
        methods=[m],
        typedefs=[NS(index=0, is_valuetype=False)],
        method_params=lambda method: [ParamDef(f"p{i}", i, i) for i in range(5)],
    )
    il = NS(types=[INT] * 5,
            returns_sret=lambda ty: False,
            _type_enum=lambda ty: (ty[1] >> 16) & 0xFF if ty else None,
            type_from_ptr=lambda ptr: None,
            instance_field_chain=lambda td: {})
    lift = Lifter.__new__(Lifter)
    lift.il, lift.meta = il, meta
    lift.bin = NS()
    lift.regs = {"RCX": Expr("this", None, "obj")}
    lift.out, lift._type_hints, lift._var_types = [], {}, {}
    lift.slot_types, lift.stack_map, lift.stack_values, lift.addr_of = {}, {}, {}, {}
    lift.rsp_delta = lift.var_n = 0
    lift.dry = lift.asm_comments = lift._copying = False
    lift._cur_ip = 0
    lift.flags = None
    lift._setup_entry(m, meta.typedefs[0])
    out = execute(lift, "4883ec20448b442448")  # sub rsp,20h ; mov r8d,[rsp+48h]
    assert lift.regs["R8"].text == "p4"
    assert lift.stack_map[0x28] == "p4"
    assert out == []


def test_resolved_scalar_float_result_uses_xmm0():
    lift, ins = make_call_lifter([], {"RAX": "staleInt", "XMM0": "staleFloat"}, returns=FLOAT)
    lift._insn(ins, [ins], 0, None, ins.next_ip)
    assert lift.regs["XMM0"].text == "Example.Target()"
    assert lift.regs["RAX"]._unk


def test_resolved_byref_float_result_uses_rax():
    lift, ins = make_call_lifter([], {"RAX": "staleInt", "XMM0": "staleFloat"}, returns=REF_FLOAT)
    lift._insn(ins, [ins], 0, None, ins.next_ip)
    assert lift.regs["RAX"].text == "Example.Target()"
    assert lift.regs.get("XMM0") is None or lift.regs["XMM0"]._unk
