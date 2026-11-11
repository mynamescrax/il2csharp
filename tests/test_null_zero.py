"""Interface-zero rewrite pins (F-zero), no fixture needed."""
from types import SimpleNamespace as NS

from il2cpp import Decompiler

TDS = [
    NS(namespace="System", name="Object", is_valuetype=False,
       is_enum=False, index=0),
    NS(namespace="System", name="String", is_valuetype=False,
       is_enum=False, index=1),
    NS(namespace="System", name="ICustomFormatter", is_valuetype=False,
       is_enum=False, index=2),
    NS(namespace="System", name="DateTime", is_valuetype=True,
       is_enum=False, index=3),
    NS(namespace="System", name="DayOfWeek", is_valuetype=True,
       is_enum=True, index=4),
    NS(namespace="System", name="Int32", is_valuetype=True,
       is_enum=False, index=5),
]

NAMES = {0: "object", 1: "string",
         2: "System.ICustomFormatter", 3: "System.DateTime",
         4: "System.DayOfWeek", 5: "System.Int32"}


def dec():
    il = NS(_type_enum=lambda t: (t[1] >> 16) & 0xFF if t else 0,
            types=[],
            type_name=lambda t: NAMES[t[0]])
    meta = NS(typedefs=TDS, methods=[],
              method_params=lambda mm: [])
    lift = NS(il=il, meta=meta)
    d = Decompiler.__new__(Decompiler)
    d.L = lift
    return d


def test_fires_iface_eq():
    d = dec()
    lines = ["System.ICustomFormatter customFormatter12 = customFormatter13;",
             "if (customFormatter12 == 0)"]
    assert d._null_zero_rewrite(lines) == [
        "System.ICustomFormatter customFormatter12 = customFormatter13;",
        "if (customFormatter12 == null)"]


def test_fires_ne_and_yoda():
    d = dec()
    lines = ["System.ICustomFormatter customFormatter12 = customFormatter13;",
             "if (customFormatter12 != 0)",
             "if (0 == customFormatter12)",
             "if (0 != customFormatter12)"]
    assert d._null_zero_rewrite(lines) == [
        "System.ICustomFormatter customFormatter12 = customFormatter13;",
        "if (customFormatter12 != null)",
        "if (null == customFormatter12)",
        "if (null != customFormatter12)"]


def test_fires_short_name():
    d = dec()
    lines = ["ICustomFormatter customFormatter12 = customFormatter13;",
             "if (customFormatter12 == 0)"]
    assert d._null_zero_rewrite(lines) == [
        "ICustomFormatter customFormatter12 = customFormatter13;",
        "if (customFormatter12 == null)"]


def test_fires_string():
    d = dec()
    lines = ["string text5 = text4;",
             "if (text5 != 0)"]
    assert d._null_zero_rewrite(lines) == [
        "string text5 = text4;",
        "if (text5 != null)"]


def test_ok_zero_store_no_veto():
    d = dec()
    lines = ["System.ICustomFormatter customFormatter12 = customFormatter13;",
             "customFormatter12 = 0;",
             "if (customFormatter12 == 0)"]
    assert d._null_zero_rewrite(lines) == [
        "System.ICustomFormatter customFormatter12 = customFormatter13;",
        "customFormatter12 = 0;",
        "if (customFormatter12 == null)"]


def test_decline_prim():
    d = dec()
    lines = ["int num1 = num2;",
             "if (num1 == 0)"]
    assert d._null_zero_rewrite(lines) == lines


def test_decline_object():
    d = dec()
    lines = ["object obj50 = obj51;",
             "if (obj50 == 0)"]
    assert d._null_zero_rewrite(lines) == lines


def test_decline_struct():
    d = dec()
    lines = ["System.DateTime dateTime1 = dateTime2;",
             "if (dateTime1 == 0)"]
    assert d._null_zero_rewrite(lines) == lines


def test_decline_enum():
    d = dec()
    lines = ["System.DayOfWeek dayOfWeek1 = dayOfWeek2;",
             "if (dayOfWeek1 == 0)"]
    assert d._null_zero_rewrite(lines) == lines


def test_decline_undeclared():
    d = dec()
    lines = ["if (mystery == 0)"]
    assert d._null_zero_rewrite(lines) == lines


def test_decline_multi_spelling():
    d = dec()
    lines = ["System.ICustomFormatter x1 = x2;",
             "System.String x1 = x3;",
             "if (x1 == 0)"]
    assert d._null_zero_rewrite(lines) == lines


def test_decline_nonzero_store():
    d = dec()
    lines = ["System.ICustomFormatter customFormatter12 = customFormatter13;",
             "customFormatter12 = 5;",
             "if (customFormatter12 == 0)"]
    assert d._null_zero_rewrite(lines) == lines


def test_decline_prim_ident_store():
    d = dec()
    lines = ["System.ICustomFormatter customFormatter12 = customFormatter13;",
             "int num1 = 5;",
             "customFormatter12 = num1;",
             "if (customFormatter12 == 0)"]
    assert d._null_zero_rewrite(lines) == lines


def test_decline_escape():
    d = dec()
    lines = ["System.ICustomFormatter customFormatter12 = customFormatter13;",
             "Foo(ref customFormatter12);",
             "if (customFormatter12 == 0)"]
    assert d._null_zero_rewrite(lines) == lines


def test_literal_survives_and_code_fires():
    d = dec()
    lines = ["System.ICustomFormatter customFormatter12 = customFormatter13;",
             'string t = "customFormatter12 == 0";',
             "if (customFormatter12 == 0)"]
    assert d._null_zero_rewrite(lines) == [
        "System.ICustomFormatter customFormatter12 = customFormatter13;",
        'string t = "customFormatter12 == 0";',
        "if (customFormatter12 == null)"]


def test_decline_member_shapes():
    d = dec()
    lines = ["System.ICustomFormatter customFormatter12 = customFormatter13;",
             "if (a.customFormatter12 == 0)",
             "if (customFormatter12.y == 0)"]
    assert d._null_zero_rewrite(lines) == lines


def test_decline_numeric_suffixes():
    d = dec()
    lines = ["System.ICustomFormatter customFormatter12 = customFormatter13;",
             "if (customFormatter12 == 0x0)",
             "if (customFormatter12 == 0L)",
             "if (customFormatter12 == 10)",
             "if (customFormatter12 == 0.0)",
             "if (customFormatter12 == 0f)"]
    assert d._null_zero_rewrite(lines) == lines


def test_decline_char():
    d = dec()
    lines = ["char c1 = c2;",
             "if (c1 == 0)"]
    assert d._null_zero_rewrite(lines) == lines


def test_fire_nospace_yoda():
    d = dec()
    lines = ["System.ICustomFormatter customFormatter12 = customFormatter13;",
             "if(0==customFormatter12)"]
    assert d._null_zero_rewrite(lines) == [
        "System.ICustomFormatter customFormatter12 = customFormatter13;",
        "if(null==customFormatter12)"]


def test_decline_paren_zero():
    d = dec()
    lines = ["System.ICustomFormatter customFormatter12 = customFormatter13;",
             "if ((0) == customFormatter12)"]
    assert d._null_zero_rewrite(lines) == lines


def test_return_comparison_fires_no_bogus_decl():
    d = dec()
    lines = ["System.ICustomFormatter x1 = x2;",
             "return x1 == 0;"]
    assert d._null_zero_rewrite(lines) == [
        "System.ICustomFormatter x1 = x2;",
        "return x1 == null;"]
