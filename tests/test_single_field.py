"""Single-field assign fold (F2-C1) unit pins, no fixture needed."""
from types import SimpleNamespace as NS

from il2cpp import Decompiler, Lifter

INT = (0, 0x08 << 16)
LONG = (0, 0x0B << 16)
TS = (7, 0x11 << 16)
MULTI = (8, 0x11 << 16)
ENUM = (9, 0x11 << 16)

TDS = [
    NS(namespace="", name="Dummy0", is_valuetype=False,
       is_enum=False),
] * 7 + [
    NS(namespace="System", name="TimeSpan", is_valuetype=True,
       is_enum=False),
    NS(namespace="System", name="Pair", is_valuetype=True,
       is_enum=False),
    NS(namespace="System", name="EEnum", is_valuetype=True,
       is_enum=True),
]

CHAINS = {
    7: {0x10: ("_ticks", 1)},
    8: {0x10: ("a", 1), 0x18: ("b", 1)},
    9: {0x10: ("value__", 0)},
}

TYPES = [INT, LONG] + [None] * 5 + [TS, MULTI, ENUM]


def dec(m=None):
    il = NS(types=TYPES,
            _type_enum=lambda t: (t[1] >> 16) & 0xFF if t else 0,
            instance_field_chain=lambda td: dict(CHAINS.get(td, {})))
    meta = NS(typedefs=TDS, methods=[],
              method_params=lambda mm: getattr(mm, "params", []))
    lift = NS(il=il, meta=meta)
    lift._td_of = lambda ty: ty[0] if isinstance(ty, tuple) else None
    d = Decompiler.__new__(Decompiler)
    d.L = lift
    return d


def test_fire_from_decl():
    d = dec()
    lines = ["System.TimeSpan timeSpan2 = offset._ticks;",
             "System.TimeSpan offset = t0;"]
    assert d._single_field_assign_fold(lines, None) == [
        "System.TimeSpan timeSpan2 = offset;",
        "System.TimeSpan offset = t0;"]


def test_fire_param_type():
    d = dec()
    m = NS(params=[NS(type=1, name="other"), NS(type=7, name="offset")])
    lines = ["System.TimeSpan timeSpan2 = offset._ticks;"]
    assert d._single_field_assign_fold(lines, m) == [
        "System.TimeSpan timeSpan2 = offset;"]


def test_decline_int_lhs():
    d = dec()
    lines = ["ulong num1 = offset._ticks;",
             "System.TimeSpan offset = t0;"]
    assert d._single_field_assign_fold(lines, None) == lines


def test_decline_unknown_base():
    d = dec()
    lines = ["System.TimeSpan timeSpan2 = mystery._ticks;"]
    assert d._single_field_assign_fold(lines, None) == lines


def test_decline_multi_field():
    d = dec()
    lines = ["System.Pair pair1 = pr.a;",
             "System.Pair pr = t0;"]
    assert d._single_field_assign_fold(lines, None) == lines


def test_decline_enum_lhs():
    d = dec()
    lines = ["System.EEnum e1 = e0.value__;",
             "System.EEnum e0 = t0;"]
    assert d._single_field_assign_fold(lines, None) == lines


def test_decline_call_rhs():
    d = dec()
    lines = ["System.TimeSpan timeSpan2 = Foo()._ticks;",
             "System.TimeSpan offset = t0;"]
    assert d._single_field_assign_fold(lines, None) == lines


def test_decline_wrong_field():
    d = dec()
    lines = ["System.TimeSpan timeSpan2 = offset._ticks;",
             "System.TimeSpan offset = t0;".replace("offset", "other")]
    body = ["System.TimeSpan timeSpan2 = offset.dateData;",
            "System.TimeSpan offset = t0;"]
    assert d._single_field_assign_fold(body, None) == body


def test_reassign_fires():
    d = dec()
    lines = ["System.TimeSpan timeSpan2 = t0;",
             "System.TimeSpan offset = t1;",
             "timeSpan2 = offset._ticks;"]
    assert d._single_field_assign_fold(lines, None) == [
        "System.TimeSpan timeSpan2 = t0;",
        "System.TimeSpan offset = t1;",
        "timeSpan2 = offset;"]


TS_T = (7, 0x11 << 16)
INT_T = (0, 0x08 << 16)
CHAIN1 = {0x10: ("_ticks", 1)}
CHAIN2 = {0x10: ("a", 1), 0x18: ("b", 1)}


def test_c2_fires():
    assert Lifter._single_field_arg(
        "obj._ticks", TS_T, False, TS_T, CHAIN1, False) == "obj"


def test_c2_declines_byref():
    assert Lifter._single_field_arg(
        "obj._ticks", TS_T, True, TS_T, CHAIN1, False) is None


def test_c2_declines_type_mismatch():
    assert Lifter._single_field_arg(
        "obj._ticks", TS_T, False, INT_T, CHAIN1, False) is None
    assert Lifter._single_field_arg(
        "obj._ticks", TS_T, False, None, CHAIN1, False) is None


def test_c2_declines_enum():
    assert Lifter._single_field_arg(
        "obj.value__", TS_T, False, TS_T, CHAIN1, True) is None


def test_c2_declines_multi_field():
    assert Lifter._single_field_arg(
        "obj.a", TS_T, False, TS_T, CHAIN2, False) is None


def test_c2_declines_wrong_field():
    assert Lifter._single_field_arg(
        "obj.other", TS_T, False, TS_T, CHAIN1, False) is None


def test_c2_declines_shapes():
    f = Lifter._single_field_arg
    assert f("obj", TS_T, False, TS_T, CHAIN1, False) is None
    assert f("Foo(obj._ticks)", TS_T, False, TS_T, CHAIN1, False) is None
    assert f("", TS_T, False, TS_T, CHAIN1, False) is None
    assert f(None, TS_T, False, TS_T, CHAIN1, False) is None
    assert f("ref obj._ticks", TS_T, False, TS_T, CHAIN1, False) is None


def test_c2_fires_valuetype_flag():
    assert Lifter._single_field_arg(
        "obj._ticks", TS_T, False, TS_T, CHAIN1, False, True) == "obj"


def test_c2_declines_ref_class():
    assert Lifter._single_field_arg(
        "obj._ticks", TS_T, False, TS_T, CHAIN1, False, False) is None


def test_store_fires_whole_size():
    assert Lifter._single_field_store(
        "obj._ticks", TS_T, TS_T, 8, 8, 0x0, CHAIN1, False, True) == "obj"


def test_store_partial_decline():
    f = Lifter._single_field_store
    assert f("obj._ticks", TS_T, TS_T, 4, 8, 0x0, CHAIN1, False, True) is None
    assert f("obj.a", TS_T, TS_T, 8, 8, 0x0, CHAIN2, False, True) is None
    assert f("obj._ticks", TS_T, INT_T, 8, 8, 0x0, CHAIN1, False, True) is None
    assert f("obj._ticks", TS_T, TS_T, 8, 8, 0x8, CHAIN1, False, True) is None


def test_store_lane_decline():
    f = Lifter._single_field_store
    assert f("Foo()._ticks", TS_T, TS_T, 8, 8, 0x0, CHAIN1, False, True) is None
    assert f("obj.value__", TS_T, TS_T, 8, 8, 0x0, CHAIN1, True, True) is None
    assert f("obj._ticks", TS_T, TS_T, 8, 8, 0x0, CHAIN1, False, False) is None
    assert f("obj._ticks", TS_T, None, 8, 8, 0x0, CHAIN1, False, True) is None
    assert f("obj._ticks", TS_T, TS_T, 8, None, 0x0, CHAIN1, False, True) is None
