"""Fix 104: object stubs for unresolved sub_ targets + caller-proven casts.

83% of shared-body references sit in `TYPE name = sub_X(...)` position,
where the declaration TYPE is the callee's proven need. Whole
conditions prove `bool`, `return` proves the method's return, plain
assignments prove the mapped decl type; everything else keeps the
object spelling. The emitter collects referenced VAs per assembly and
writes one `__SharedBodyStubs` class plus a `using static` per
referencing file.
"""

import re
from types import SimpleNamespace as NS

from il2cpp import Decompiler
from il2cpp.emitter import Emitter

INT = (0, 0x08 << 16)
VOID = (0, 0x01 << 16)


def dec():
    return Decompiler.__new__(Decompiler)


def cast(line, amap=None, rty="int", is_void=False, real=None):
    return dec()._stub_cast_line(
        line, amap or {}, rty, is_void,
        frozenset() if real is None else real)


# --- mask ------------------------------------------------------------------


def test_mask_hides_strings_comments_keep_offsets():
    d = dec()
    line = 'int x = sub_1a("a(b", c); // sub_2('
    masked = d._stub_mask_line(line)
    assert len(masked) == len(line)
    assert masked.startswith("int x = sub_1a")
    assert "a(b" not in masked and "sub_2" not in masked


def test_mask_verbatim_and_char():
    d = dec()
    line = 'string t = @"a""b sub_1a"; char c = sub_2'
    masked = d._stub_mask_line(line)
    assert "sub_1a" not in masked
    assert masked.endswith("char c = sub_2")


def test_mask_marks_comments_distinctly():
    d = dec()
    masked = d._stub_mask_line("int x = sub_1a(a); // note")
    assert "" in masked
    assert masked.index("") == len("int x = sub_1a(a); ")
    assert "" not in d._stub_mask_line('string t = "a//b";')


# --- call boundaries + spans -------------------------------------------------


def test_call_boundaries():
    d = dec()
    assert d._stub_call_at("sub_1a2b(", 0) == "1a2b"
    assert d._stub_call_at("my_sub_1a2b(", 3) is None
    assert d._stub_call_at("obj.sub_1a2b(", 4) is None
    assert d._stub_call_at("sub_1a2bx(", 0) is None
    assert d._stub_call_at("sub_1A2B(", 0) is None
    assert d._stub_call_at("vsub_s8(", 1) is None


def test_call_span():
    d = dec()
    assert d._stub_call_span("sub_1a2b(a, Foo(1))", 8) == (8, 18)
    assert d._stub_call_span("sub_1a2b (a)", 8) == (9, 11)
    assert d._stub_call_span("sub_1a2b       (a)", 8) == (15, 17)
    assert d._stub_call_span("sub_1a2b(a, b", 8) is None
    assert d._stub_call_span("sub_1a2b", 8) is None


# --- decl-assign ---------------------------------------------------------------


def test_decl_cast():
    assert cast("int num1 = sub_180002210(0, typeof(X), obj6);") == \
        "int num1 = (int)sub_180002210(0, typeof(X), obj6);"


def test_decl_skips():
    assert cast("object obj1 = sub_1a2b(x);") is None
    assert cast("System.Object obj1 = sub_1a2b(x);") is None
    assert cast("byte* ptr1 = sub_1a2b(x);") is None
    assert cast("const int x = sub_1a2b();") is None
    assert cast("ref int x = sub_1a2b();") is None
    assert cast("x.y = sub_1a2b();") is None
    assert cast("arr[i] = sub_1a2b();") is None
    assert cast("a = b = sub_1a2b(x);") is None
    assert cast("int x = a == b;") is None
    assert cast("bool b = sub_1a2b() is Foo;") is None
    assert cast("object o = sub_1a2b() as Foo;") is None
    assert cast("string t = $\"{sub_1a2b()}\";") is None
    assert cast("int x = Foo(sub_1a2b());") is None
    assert cast("int x = num1 + sub_1a2b();") is None
    assert cast("int x = sub_1a2b(a, b;") is None
    assert cast("int x = 5;") is None


def test_decl_ternary_and_nested():
    assert cast("int x = c ? sub_1a() : sub_1b();") == \
        "int x = c ? (int)sub_1a() : (int)sub_1b();"
    # fix 105: a call in the ternary condition proves bool there; the
    # arms keep the line's type.
    assert cast("int x = sub_c() ? sub_1a() : sub_1b();") == \
        "int x = (bool)sub_c() ? (int)sub_1a() : (int)sub_1b();"
    assert cast("string t = sub_c() ? A() : B();") == \
        "string t = (bool)sub_c() ? A() : B();"
    # arms without calls pass through; unparseable arms decline all.
    assert cast("int x = c ? sub_1a() : other;") == \
        "int x = c ? (int)sub_1a() : other;"
    assert cast("int x = c ? sub_1a() : y + sub_1b();") is None
    assert cast("int x = sub_c() ? sub_1a() : sub_1b();", real={"c"}) is None
    assert cast("int x = (sub_1a());") == "int x = ((int)sub_1a());"
    assert cast("int x = sub_1a(sub_1b());") == \
        "int x = (int)sub_1a(sub_1b());"


def test_decl_comment_tail_kept():
    assert cast("int x = sub_1a(a); // note") == \
        "int x = (int)sub_1a(a); // note"


def test_real_names_never_cast():
    assert cast("int x = sub_abc1(a);", real={"abc1"}) is None


# --- return / conditions / plain assign ------------------------------------------


def test_return_cast_and_split():
    assert cast("return sub_1a2b(x);") == "return (int)sub_1a2b(x);"
    assert cast("return sub_1a2b(x);", rty=None) is None
    assert cast("return sub_1a2b(x);", is_void=True) == \
        ["sub_1a2b(x);", "return;"]
    assert cast("return c ? sub_1a() : sub_1b();", is_void=True) is None


def test_return_object_unchanged():
    # object methods need no cast: the line must come back identical
    d = dec()
    assert d._stub_cast_line("return sub_1a2b(x);", {}, "object",
                             False, frozenset()) is None


def test_condition_bool():
    assert cast("if (sub_1a2b(a, b))") == "if ((bool)sub_1a2b(a, b))"
    assert cast("while (!(sub_1a()))") == "while (!((bool)sub_1a()))"
    assert cast("else if (sub_1a())") == "else if ((bool)sub_1a())"
    assert cast("} while (sub_1a());") == "} while ((bool)sub_1a());"
    assert cast("if (c ? sub_1a() : sub_1b())") == \
        "if (c ? (bool)sub_1a() : (bool)sub_1b())"
    assert cast("if (sub_1a() == null)") is None
    assert cast("if (x && sub_1a())") is None
    assert cast("if (c ? sub_1a() : sub_1b())", real={"1a"}) is None


def test_plain_assign_map():
    assert cast("num1 = sub_1a();", amap={"num1": "int"}) == \
        "num1 = (int)sub_1a();"
    assert cast("num1 = sub_1a();", amap={}) is None
    assert cast("num1 = sub_1a();", amap={"num1": "object"}) is None
    assert cast("o.m = sub_1a();", amap={"o.m": "int"}) is None


# --- map + return-type helpers -----------------------------------------------------


def test_assign_types_unique():
    d = dec()
    d.L = NS(meta=NS(method_params=lambda m: []),
             il=NS(types=[], type_name=lambda t: "object"))
    amap = d._stub_assign_types(
        ["int x = 1;", "int a = 0;", "string x = s;", "int y = 2;",
         "foreach (Foo f in g) {", "catch (Exception e) {",
         "a = b = sub_1a();"], None)
    assert amap.get("y") == "int"
    assert "x" not in amap  # two types: skip
    assert amap.get("f") == "Foo"
    assert amap.get("e") == "Exception"
    # `a = b = ...` is a chained assign, never a decl shape: b stays out
    assert "b" not in amap


def test_assign_types_params():
    d = dec()
    d.L = NS(meta=NS(method_params=lambda m: [NS(name="v", type=1)]),
             il=NS(types=[None, INT], type_name=lambda t: "int"))
    amap = d._stub_assign_types([], None)
    assert amap == {"v": "int"}


def test_return_type():
    d = dec()
    d.L = NS(il=NS(types=[VOID, INT], type_name=lambda t: "void" if t == VOID else "int"))
    assert d._stub_return_type(NS(return_type=1)) == ("int", False)
    assert d._stub_return_type(NS(return_type=0)) == (None, True)
    assert d._stub_return_type(NS(return_type=9)) == (None, False)


def test_type_ok():
    d = dec()
    assert d._stub_type_ok("int")
    assert d._stub_type_ok("List<int>")
    assert d._stub_type_ok("int?")
    assert d._stub_type_ok("T")
    assert not d._stub_type_ok("object")
    assert not d._stub_type_ok("System.Object")
    assert not d._stub_type_ok("byte*")
    assert not d._stub_type_ok("ref int")
    assert not d._stub_type_ok("(int, string)")
    assert not d._stub_type_ok("const int")
    assert not d._stub_type_ok("")
    assert not d._stub_type_ok(None)


def test_real_names():
    d = dec()
    d.L = NS(meta=NS(methods=[NS(name="sub_abc1"), NS(name="Foo"),
                              NS(name=None), NS(name="sub_XY")]))
    assert d._stub_real_names() == frozenset({"abc1"})


# --- emitter -----------------------------------------------------------------


def test_stub_collect_boundaries():
    e = Emitter.__new__(Emitter)
    assert e._stub_collect("x = sub_1a2b(a);") == {"1a2b"}
    assert e._stub_collect("x = my_sub_1a2b(a);") == set()
    assert e._stub_collect("x = obj.sub_1a2b(a);") == set()
    assert e._stub_collect("x = sub_1a2bx(a);") == set()
    assert e._stub_collect("// sub_1a2b(a);") == {"1a2b"}
    assert e._stub_collect("") == set()


def test_stub_file_text():
    e = Emitter.__new__(Emitter)
    e.il = NS(addr_candidates={
        0x1a2b: [],
        0x1a2c: [("method", 7), ("thunk", 1)],
    }, generic_method_name=lambda si: "G.M<int>")
    e.meta = NS(methods=[None] * 8,
                typedefs=[None] * 8)
    e.meta.methods[7] = NS(name="Equals", declaring=3)
    e.meta.typedefs[3] = NS(name="String", namespace="System")
    text = e._stub_file_text({"1a2b", "1a2c"})
    assert "internal static class __SharedBodyStubs" in text
    assert "internal static object sub_1a2b(params object[] args)" in text
    assert "0x1a2b: unregistered native target" in text
    assert "String.Equals" in text
    assert "NotImplementedException" in text


def test_stub_owners_guarded():
    e = Emitter.__new__(Emitter)
    e.il = NS(addr_candidates=None)
    e.meta = NS(methods=[], typedefs=[])
    assert e._stub_owners("1a2b") == "unresolved target"
