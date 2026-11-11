"""Fix 93: evidence-named noreturn raisers render as `throw new ...();`.

`raise_IndexOutOfRangeException` and `raise_NullReferenceException` each
raise one specific new exception (the name comes from the exception-class
string their wrapper chain lea's), and each wrapper is a `sub rsp,X;
call T; int3` noreturn forwarder. Rendering them as an ordinary named
call invents a result the callee never returns:

    object obj12 = raise_NullReferenceException();

The honest render names the exception at the throw site:

    throw new System.NullReferenceException();

Every gate is a property of the callee: the exact evidence-derived name,
arity 0, unregistered native code, and the noreturn-forwarder shape.
Only positive proof renders; anything else keeps the old named call.
"""
import struct
from types import SimpleNamespace as NS

from iced_x86 import Decoder

from il2cpp import Expr, Lifter

NRE = 0x1804356B0
IOOR = 0x1804356A0
# sub rsp,28h; call rel32; int3 padding -- a noreturn throw stub
NORETURN_CODE = b"\x48\x83\xec\x28\xe8\x00\x00\x00\x00" + b"\xcc" * 8
# sub rsp,28h; add rsp,28h; ret -- ordinary code, it returns
RETURNING_CODE = b"\x48\x83\xec\x28\x48\x83\xc4\x28\xc3" + b"\xcc" * 8


def make_lifter(target, code, *, name=None, registered=False,
                exported=False, arity=None):
    il = NS(
        addr_to_method={target: ("method", 0)} if registered else {},
        addr_candidates={target: [("method", 0)]} if registered else {},
        bin=NS(exports={}),
    )
    lift = Lifter.__new__(Lifter)
    lift.il = il
    lift.meta = NS(methods=[], typedefs=[])
    lift.bin = NS(
        exports={target: "some_export"} if exported else {},
        is_exec_va=lambda va: True,
        read=lambda va, n: code[:n],
    )
    lift.regs = {}
    lift.out = []
    lift.dry = False
    lift.asm_comments = False
    lift.rt_names = {target: name} if name else {}
    if arity is not None:
        lift.RT_ARITY = dict(Lifter.RT_ARITY, **{name: arity})
    lift.rt_init_meta = None
    lift.rethrow_va = None
    lift.raise_va = None
    lift.eh_helper_set = {}
    lift._thunk_cache = {}
    lift.cur_va = 0x180400000
    return lift


def call_insn(target, ip=0x180400000):
    rel = target - (ip + 5)
    return Decoder(64, b"\xe8" + struct.pack("<i", rel), ip=ip).decode()


def test_named_raise_predicate_proves_the_pair():
    lift = make_lifter(NRE, NORETURN_CODE, name="raise_NullReferenceException")
    assert lift._named_raise_throw(NRE, "raise_NullReferenceException") == \
        "System.NullReferenceException"
    lift = make_lifter(IOOR, NORETURN_CODE,
                       name="raise_IndexOutOfRangeException")
    assert lift._named_raise_throw(IOOR, "raise_IndexOutOfRangeException") == \
        "System.IndexOutOfRangeException"


def test_named_raise_call_renders_throw_new_without_a_result():
    lift = make_lifter(NRE, NORETURN_CODE, name="raise_NullReferenceException")
    lift.regs["RAX"] = Expr("stale", None, "int")
    lift._call(call_insn(NRE), None)
    assert lift.out == [(0x180400000, "throw new System.NullReferenceException();", None)]
    assert "RAX" not in lift.regs or getattr(lift.regs["RAX"], "_unk", False)
    assert all("raise_" not in text for _, text, _ in lift.out)


def test_named_raise_call_renders_index_out_of_range():
    lift = make_lifter(IOOR, NORETURN_CODE,
                       name="raise_IndexOutOfRangeException")
    lift._call(call_insn(IOOR), None)
    assert lift.out == [(0x180400000, "throw new System.IndexOutOfRangeException();", None)]


def test_named_raise_tail_jump_renders_throw_new():
    lift = make_lifter(NRE, NORETURN_CODE, name="raise_NullReferenceException")
    lift.il.function_extent = lambda va: (va, va + 16)
    rel = NRE - (0x180400000 + 5)
    ins = Decoder(64, b"\xe9" + struct.pack("<i", rel), ip=0x180400000).decode()
    lift.flags = None
    lift._insn(ins, [ins], 0, None, 0x180400010)
    assert lift.out == [(0x180400000, "throw new System.NullReferenceException();", None)]


def test_registered_target_is_not_flattened():
    lift = make_lifter(NRE, NORETURN_CODE,
                       name="raise_NullReferenceException", registered=True)
    assert lift._named_raise_throw(NRE, "raise_NullReferenceException") is None


def test_exported_target_is_not_flattened():
    lift = make_lifter(NRE, NORETURN_CODE,
                       name="raise_NullReferenceException", exported=True)
    assert lift._named_raise_throw(NRE, "raise_NullReferenceException") is None


def test_returning_routine_is_not_flattened():
    lift = make_lifter(NRE, RETURNING_CODE, name="raise_NullReferenceException")
    assert lift._named_raise_throw(NRE, "raise_NullReferenceException") is None


def test_unreadable_target_keeps_the_old_named_call():
    lift = make_lifter(NRE, b"", name="raise_NullReferenceException")
    lift.bin.is_exec_va = lambda va: False
    assert lift._named_raise_throw(NRE, "raise_NullReferenceException") is None


def test_unknown_name_is_not_flattened():
    lift = make_lifter(0x180400000, NORETURN_CODE, name="sub_180400000")
    assert lift._named_raise_throw(0x180400000, "sub_180400000") is None
    assert lift._named_raise_throw(0x180400000, None) is None


def test_nonzero_arity_is_not_flattened():
    lift = make_lifter(NRE, NORETURN_CODE,
                       name="raise_NullReferenceException", arity=1)
    assert lift._named_raise_throw(NRE, "raise_NullReferenceException") is None
