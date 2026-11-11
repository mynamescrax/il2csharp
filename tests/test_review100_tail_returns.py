"""Fix 100: resolve ambiguous shared tails by the caller's return type.

A `return <call>` tail delivers the callee's value as the caller's own,
so the true callee's closed, spec-inflated return must equal the
caller's exact metadata return. The filter keeps nothing on
speculation (open/unreadable rows decline the whole resolution),
drops closed mismatches, and resolves only when every survivor renders
identically -- duplicate MethodDefs, or generic instantiations proven
by the return itself (e.g. `Unsafe.As<T>` with `T` := caller return).
Void callers decline (fix 95 owns them: a value filter there is both
vacuous and unsound), as do open/unknown callers, empty or split
survivors, and open generic definitions (receiver instantiation is a
separate, unattempted proof).
"""

import struct
from types import SimpleNamespace as NS

from iced_x86 import Decoder

from il2cpp import Expr, Lifter, MethodDef, ParamDef

VOID = (0, 0x01 << 16)
INT = (0, 0x08 << 16)
BOOL = (0, 0x02 << 16)
OPEN = (0, 0x1E << 16)

TAIL_T = 0x4000


def tail_meta_il(methods, typedefs, params_fn, specs=(), gnames=None,
                 inst_args=None, genparams=()):
    meta = NS(
        methods=list(methods),
        typedefs=list(typedefs),
        method_params=params_fn,
        generic_parameters=list(genparams),
    )
    il = NS(
        meta=meta,
        types=[VOID, INT, BOOL, OPEN],
        method_specs=list(specs),
        _closed_type_key=lambda ty: None if ty is None or ty == OPEN else ty,
        _method_spec_type_args=lambda inst: (inst_args or {}).get(inst),
        generic_method_name=lambda si: (gnames or {}).get(si, "G.M<%d>" % si),
        _type_enum=lambda ty: ((ty[1] >> 16) & 0xFF) if ty else None,
        returns_sret=lambda ty: False,
        addr_candidates={},
        addr_to_method={},
        bin=NS(exports={}),
        function_extent=lambda va: (va, va + 16),
    )
    return meta, il


def twin_methods():
    td = NS(name="Twins", namespace="", generic_container=-1)
    m0 = MethodDef(0, "Combine", 0, 1, 0, -1, 0, 0x10, 0, 0, 2)
    m1 = MethodDef(1, "Combine", 0, 1, 0, -1, 0, 0x10, 0, 0, 2)
    params = lambda m: [ParamDef("a", 0, 1), ParamDef("b", 1, 1)]
    return [m0, m1], [td], params


def make_lift(caller_rt=1, cands=None, methods=None, typedefs=None,
              params_fn=None, specs=(), gnames=None, inst_args=None,
              genparams=(), regs=None):
    if methods is None:
        methods, typedefs, params_fn = twin_methods()
    meta, il = tail_meta_il(methods, typedefs, params_fn, specs, gnames,
                            inst_args, genparams)
    il.addr_candidates = {TAIL_T: list(cands or [("method", 0), ("method", 1)])}
    lift = Lifter.__new__(Lifter)
    lift.il, lift.meta = il, meta
    lift.bin = NS(is_exec_va=lambda va: True,
                  read=lambda va, n: b"\xcc" * n,
                  exports={})
    lift.regs = dict(regs or {
        "RCX": Expr("t8", None, "obj"),
        "RDX": Expr("t9", None, "int"),
    })
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
    lift._current_method = NS(return_type=caller_rt, name="M", is_static=True)
    lift._type_hints = {}
    lift.slot_types = {}
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


def target(lift, cands):
    return lift._shared_tail_return_target(list(cands))


def test_dup_twins_resolve_end_to_end():
    lift = make_lift()
    lift._insn(jmp_insn(), [jmp_insn()], 0, None, 0x1010)
    assert lift.out == [(0x1000, "return Twins.Combine(t8, t9); /* tail */", None)]


def test_dup_twins_resolve():
    lift = make_lift()
    assert target(lift, [("method", 0), ("method", 1)]) == ("method", 0)


def test_return_mismatch_drops_decoy():
    methods, typedefs, params = twin_methods()
    methods.append(MethodDef(2, "IsSet", 0, 2, 0, -1, 0, 0x10, 0, 0, 1))
    lift = make_lift(methods=methods, typedefs=typedefs,
                     params_fn=lambda m: params(m) if m.index < 2 else [ParamDef("a", 0, 1)])
    assert target(lift, [("method", 0), ("method", 2)]) == ("method", 0)


def test_split_spellings_decline():
    methods, typedefs, params = twin_methods()
    methods[1] = MethodDef(1, "Other", 0, 1, 0, -1, 0, 0x10, 0, 0, 2)
    lift = make_lift(methods=methods, typedefs=typedefs, params_fn=params)
    assert target(lift, [("method", 0), ("method", 1)]) is None


def test_empty_survivors_decline():
    methods, typedefs, params = twin_methods()
    methods[0] = MethodDef(0, "A", 0, 2, 0, -1, 0, 0x10, 0, 0, 1)
    methods[1] = MethodDef(1, "B", 0, 2, 0, -1, 0, 0x10, 0, 0, 1)
    lift = make_lift(methods=methods, typedefs=typedefs,
                     params_fn=lambda m: [ParamDef("a", 0, 1)])
    assert target(lift, [("method", 0), ("method", 1)]) is None


def test_void_caller_declines():
    lift = make_lift(caller_rt=0)
    assert target(lift, [("method", 0), ("method", 1)]) is None


def test_open_caller_declines():
    lift = make_lift(caller_rt=3)
    assert target(lift, [("method", 0), ("method", 1)]) is None


def test_no_method_declines():
    lift = make_lift()
    lift._current_method = None
    assert target(lift, [("method", 0), ("method", 1)]) is None


def test_unknown_kind_declines():
    lift = make_lift()
    assert target(lift, [("method", 0), ("thunk", 9)]) is None


def test_malformed_candidate_declines():
    lift = make_lift()
    assert target(lift, [("method", 0), ("method",)]) is None


def test_generic_inflation_resolves():
    td = NS(name="G", namespace="", generic_container=-1)
    md = MethodDef(0, "Get", 0, 3, 0, 0, 0, 0x10, 0, 0, 0)
    lift = make_lift(caller_rt=1, cands=[("generic", 0)],
                     methods=[md], typedefs=[td],
                     params_fn=lambda m: [],
                     specs=[(0, -1, 0)], gnames={0: "G.Get<int>"},
                     inst_args={0: (INT,)},
                     genparams=[("o", "T", 0, 0, 0, 0)])
    assert target(lift, [("generic", 0)]) == ("generic", "G.Get<int>", 0)
    call, m2 = lift._tail_generic_call("G.Get<int>", 0, [], [])
    assert call == "G.Get<int>()"
    assert m2 is md


def test_generic_unreadable_inst_declines():
    td = NS(name="G", namespace="", generic_container=-1)
    md = MethodDef(0, "Get", 0, 3, 0, 0, 0, 0x10, 0, 0, 0)
    lift = make_lift(caller_rt=1, cands=[("generic", 0)],
                     methods=[md], typedefs=[td],
                     params_fn=lambda m: [],
                     specs=[(0, -1, 0)], gnames={0: "G.Get<int>"},
                     inst_args={},
                     genparams=[("o", "T", 0, 0, 0, 0)])
    assert target(lift, [("generic", 0)]) is None


def test_generic_split_instantiations_decline():
    td = NS(name="D", namespace="", generic_container=7)
    md = MethodDef(0, "Get", 0, 2, 0, 0, 0, 0x10, 0, 0, 0)
    specs = [(0, 0, -1), (0, 1, -1)]
    gnames = {0: "D<int>.Get", 1: "D<string>.Get"}
    lift = make_lift(caller_rt=2, cands=[("generic", 0), ("generic", 1)],
                     methods=[md], typedefs=[td],
                     params_fn=lambda m: [],
                     specs=specs, gnames=gnames,
                     inst_args={0: (INT,), 1: (INT,)})
    # md returns closed BOOL(2) and the caller returns BOOL: both survive
    # the filter, but the proven spellings differ, so no resolution.
    assert target(lift, [("generic", 0), ("generic", 1)]) is None


def test_generic_dup_specs_resolve():
    td = NS(name="G", namespace="", generic_container=-1)
    md = MethodDef(0, "Get", 0, 3, 0, 0, 0, 0x10, 0, 0, 0)
    specs = [(0, -1, 0), (0, -1, 1)]
    gnames = {0: "G.Get<int>", 1: "G.Get<int>"}
    lift = make_lift(caller_rt=1,
                     cands=[("generic", 0), ("generic", 1)],
                     methods=[md], typedefs=[td],
                     params_fn=lambda m: [],
                     specs=specs, gnames=gnames,
                     inst_args={0: (INT,), 1: (INT,)},
                     genparams=[("o", "T", 0, 0, 0, 0)])
    got = target(lift, [("generic", 0), ("generic", 1)])
    assert got == ("generic", "G.Get<int>", 0)


def test_open_owner_declines():
    td = NS(name="List", namespace="S", generic_container=3)
    m0 = MethodDef(0, "GetCount", 0, 1, 0, -1, 0, 0x10, 0, 0, 0)
    lift = make_lift(methods=[m0], typedefs=[td],
                     params_fn=lambda m: [])
    assert target(lift, [("method", 0)]) is None


def test_open_method_declines():
    td = NS(name="G", namespace="", generic_container=-1)
    m0 = MethodDef(0, "M", 0, 1, 0, 4, 0, 0x10, 0, 0, 0)
    lift = make_lift(methods=[m0], typedefs=[td],
                     params_fn=lambda m: [])
    assert target(lift, [("method", 0)]) is None


def test_subst_preserves_byref():
    lift = make_lift(genparams=[("o", "T", 0, 0, 0, 0)])
    byref_var = (0, (0x1E << 16) | (1 << 29))
    got = lift._tail_subst_closed(byref_var, (9, -1, 0))
    assert got is None
    lift.il._method_spec_type_args = lambda inst: {0: (INT,)}.get(inst)
    got = lift._tail_subst_closed(byref_var, (9, -1, 0))
    assert got == (INT[0], (INT[1] & ~(1 << 29)) | (1 << 29))
