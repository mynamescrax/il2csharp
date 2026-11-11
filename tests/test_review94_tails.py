"""Fixes 94/95: honest tail-call arguments and void-caller tails.

A tail jump through a shared body kept everything the register spray
held: the hidden instantiation argument (compiler plumbing the ordinary
`_call` path already strips) and trailing stale unknowns (which `_call`
trims per fix 58). And a value-returning tail in a void method printed
`return <call>;`, which has nowhere to put the value:

    return sub_1812f0360(sliderEvent2, unityAction2,
                         UnityEvent<float>.AddListener, obj13);

becomes:

    sliderEvent2.AddListener(unityAction2);
    return;

Every trim reuses the `_call` proof it mirrors (generic identity by
exact text, stale-unknown slots, largest declared arity); only an exact
metadata void changes the return shape.
"""
import struct
from types import SimpleNamespace as NS

from iced_x86 import Decoder

from il2cpp import Expr, Lifter, MethodDef, ParamDef

VOID = (0, 0x01 << 16)
INT = (0, 0x08 << 16)

TAIL_T = 0x3000
ADD = "UnityEvent<float>.AddListener"


def tail_meta_il():
    m_add = MethodDef(0, "AddListener", 0, 0, 0, -1, 1, 0, 0, 0, 1)
    m_other = MethodDef(1, "Handler", 1, 1, 0, -1, 1, 0x10, 0, 0, 2)
    meta = NS(
        methods=[m_add, m_other],
        typedefs=[NS(name="UnityEvent", namespace="", is_valuetype=False)],
        method_params=lambda m: [ParamDef("value", 0, 1)] if m.index == 0
        else [ParamDef("a", 0, 1), ParamDef("b", 1, 1)],
    )
    il = NS(
        meta=meta,
        types=[VOID, INT],
        addr_candidates={TAIL_T: [("generic", 0), ("generic", 1)]},
        addr_to_method={},
        method_specs=[(0, 0, -1), (1, 0, -1)],
        generic_method_name=lambda si: ADD if si == 0 else "Other.Handler",
        returns_sret=lambda ty: False,
        _type_enum=lambda ty: ((ty[1] >> 16) & 0xFF) if ty else None,
        function_extent=lambda va: (va, va + 16),
        bin=NS(exports={}),
    )
    return meta, il


def make_tail_lifter(caller_void=True, hidden=ADD):
    meta, il = tail_meta_il()
    lift = Lifter.__new__(Lifter)
    lift.il, lift.meta = il, meta
    lift.bin = NS(is_exec_va=lambda va: True,
                  read=lambda va, n: b"\xcc" * n,
                  exports={})
    stale = Expr("v99", None, "?")
    stale._unk = True
    lift.regs = {
        "RCX": Expr("t8", None, "obj"),
        "RDX": Expr("t9", None, "int"),
        "R8": Expr(hidden, None, "obj"),
        "R9": stale,
    }
    lift.out = []
    lift.dry = False
    lift.asm_comments = False
    lift.rt_names = {}
    lift.rt_init_meta = None
    lift.rethrow_va = None
    lift.raise_va = None
    lift.eh_helper_set = {}
    lift._thunk_cache = {}
    lift.cur_va = 0x1000
    lift._current_method = NS(return_type=0 if caller_void else 1)
    lift._type_hints = {}
    lift._call_class_args = None
    lift._xmm_pending = []
    lift.vt_recv_slot = None
    lift.vt_recv = None
    lift.flags = None
    lift._cur_ip = 0
    return lift


def jmp_insn(target=TAIL_T, ip=0x1000):
    return Decoder(64, b"\xe9" + struct.pack("<i", target - (ip + 5)),
                   ip=ip).decode()


def test_shared_tail_strips_hidden_arg_and_stale_in_void_caller():
    lift = make_tail_lifter(caller_void=True)
    lift._insn(jmp_insn(), [jmp_insn()], 0, None, 0x1010)
    assert lift.out == [(0x1000, "t8.AddListener(t9); return;", None)]


def test_shared_tail_resolves_but_returns_in_value_caller():
    lift = make_tail_lifter(caller_void=False, hidden="Other.Handler")
    lift._insn(jmp_insn(), [jmp_insn()], 0, None, 0x1010)
    assert lift.out == [(0x1000, "return Other.Handler(t8, t9); /* tail */", None)]


def test_hidden_generic_matches_usage_slot_form():
    lift = make_tail_lifter()
    slot = Expr(ADD, None, "obj")
    slot._usg_idx = 0
    exprs = [Expr("t8", None, "obj"), slot]
    hit = lift._tail_hidden_generic(
        [("generic", 0), ("generic", 1)], ["t8", ADD], exprs)
    assert hit == (ADD, 0, 1)


def test_hidden_generic_declines_without_identity():
    lift = make_tail_lifter()
    exprs = [Expr("t8", None, "obj"), Expr("t9", None, "int")]
    assert lift._tail_hidden_generic(
        [("generic", 0), ("generic", 1)], ["t8", "t9"], exprs) is None


def test_hidden_generic_declines_without_naming_hook():
    lift = make_tail_lifter()
    del lift.il.generic_method_name
    exprs = [Expr("t8", None, "obj"), Expr(ADD, None, "obj")]
    assert lift._tail_hidden_generic(
        [("generic", 0), ("generic", 1)], ["t8", ADD], exprs) is None


def test_trim_stale_drops_placeholders_and_unknowns():
    lift = make_tail_lifter()
    stale = Expr("v1", None, "?")
    stale._unk = True
    args = ["t8", "t9", "_"]
    exprs = [Expr("t8", None, "obj"), Expr("t9", None, "int"), None]
    lift._tail_trim_stale(args, exprs)
    assert args == ["t8", "t9"]
    assert [e.text if e else None for e in exprs] == ["t8", "t9"]
    args = ["t8", "v1"]
    exprs = [Expr("t8", None, "obj"), stale]
    lift._tail_trim_stale(args, exprs)
    assert args == ["t8"]
    assert [e.text if e else None for e in exprs] == ["t8"]
    args = ["t8", "t9"]
    exprs = [Expr("t8", None, "obj"), Expr("t9", None, "int")]
    lift._tail_trim_stale(args, exprs)
    assert args == ["t8", "t9"]


def test_hidden_generic_requires_trailing_position():
    # an identity with a real argument after it is a stale leftover,
    # not this call's callee
    lift = make_tail_lifter()
    exprs = [Expr("t8", None, "obj"), Expr(ADD, None, "obj"),
             Expr("t9", None, "int")]
    assert lift._tail_hidden_generic(
        [("generic", 0), ("generic", 1)], ["t8", ADD, "t9"], exprs) is None


def test_hidden_generic_declines_conflicting_identities():
    lift = make_tail_lifter()
    exprs = [Expr(ADD, None, "obj"), Expr("Other.Handler", None, "obj")]
    assert lift._tail_hidden_generic(
        [("generic", 0), ("generic", 1)],
        [ADD, "Other.Handler"], exprs) is None


def test_hidden_generic_declines_single_owner_tails():
    # with one owner the registry already names the callee; a stray
    # identity-looking argument must not rename it
    lift = make_tail_lifter()
    exprs = [Expr("t8", None, "obj"), Expr(ADD, None, "obj")]
    assert lift._tail_hidden_generic(
        [("method", 0)], ["t8", ADD], exprs) is None


def test_caller_void_gate():
    assert make_tail_lifter(caller_void=True)._caller_is_void() is True
    assert make_tail_lifter(caller_void=False)._caller_is_void() is False
    lift = make_tail_lifter()
    lift._current_method = None
    assert lift._caller_is_void() is False


def test_emit_tail_honors_void_caller_and_marker_habit():
    lift = make_tail_lifter(caller_void=True)
    lift._emit_tail(7, "t8.AddListener(t9)", None)
    assert lift.out == [(7, "t8.AddListener(t9); return;", None)]
    lift = make_tail_lifter(caller_void=False)
    lift._emit_tail(7, "t8.AddListener(t9)", None)
    assert lift.out == [(7, "return t8.AddListener(t9); /* tail */", None)]
    lift = make_tail_lifter(caller_void=False)
    lift._emit_tail(7, "t8.AddListener(t9)", None, marker=False)
    assert lift.out == [(7, "return t8.AddListener(t9);", None)]
    lift = make_tail_lifter(caller_void=False)
    lift._emit_tail(7, "Foo.Bar()", None, void=True)
    assert lift.out == [(7, "Foo.Bar(); return;", None)]


def test_resolved_ctor_tail_uses_initializer_pseudo_form():
    # a constructor resolved through the hidden argument must render the
    # `..ctor` pseudo-form the emitter promotes -- never single-dot
    # `this.ctor`, which no pass owns
    meta, il = tail_meta_il()
    caller = MethodDef(9, ".ctor", 5, 0, 0, -1, 1, 0, 0, 0, 2)
    callee = MethodDef(2, ".ctor", 3, 0, 0, -1, 1, 0, 0, 0, 2)
    meta.methods.append(callee)
    meta.method_params = lambda m: [ParamDef("a", 0, 1), ParamDef("b", 1, 1)] \
        if m.index in (2, 9) else tail_meta_il()[0].method_params(m)
    tds = [NS(name="T%d" % i, namespace="", is_valuetype=False) for i in range(6)]
    meta.typedefs = tds
    il.base_chain_tds = lambda td: [5, 3]
    lift = Lifter.__new__(Lifter)
    lift.il, lift.meta = il, meta
    lift.bin = NS(is_exec_va=lambda va: True, read=lambda va, n: b"",
                  exports={})
    lift.regs = {}
    lift.out = []
    lift.dry = False
    lift.asm_comments = False
    lift.rt_names = {}
    lift._current_method = caller
    lift._current_td = NS(index=5)
    lift._type_hints = {}
    lift._call_class_args = None
    lift._xmm_pending = []
    recv = Expr("this", (5, 0x12 << 16), "obj")
    call, m2 = lift._tail_generic_call(
        "Base.Impl..ctor", 2, ["this", "solver", "Skin"],
        [recv, Expr("solver", None, "obj"), Expr("Skin", None, "int")])
    assert call == "base..ctor(solver, Skin)"
    assert m2 is callee
