"""Fix 111: C# keywords as identifiers escape with trailing underscore.

A reserved word after `.`/`->` is never a keyword use; declarations
route through `safe_ident` (same spelling, same set), so both sides
agree and non-keyword lines are byte-identical.
"""

from il2cpp import Decompiler
from il2cpp.names import safe_ident


def dec():
    return Decompiler.__new__(Decompiler)


def esc(lines):
    return dec()._escape_keywords(lines)


def test_convention():
    assert safe_ident("namespace") == "namespace_"
    assert safe_ident("interface") == "interface_"
    assert safe_ident("in") == "in_"
    assert safe_ident("event") == "event_"
    assert safe_ident("value") == "value"
    assert safe_ident("text1") == "text1"
    assert safe_ident("getClass") == "getClass"


def test_member_tails():
    out = esc(["object obj1 = args.getClass().namespace;",
               "if (type2.namespace == null)",
               "x = y.in;",
               "z = w.interface;",
               "p = q->namespace;"])
    assert out[0] == "object obj1 = args.getClass().namespace_;"
    assert out[1] == "if (type2.namespace_ == null)"
    assert out[2] == "x = y.in_;"
    assert out[3] == "z = w.interface_;"
    assert out[4] == "p = q->namespace_;"


def test_already_escaped_untouched():
    out = esc(["object obj1 = args.getClass().namespace_;",
               "x = y.index;",
               "if (a.inB) {}"])
    assert out[0] == "object obj1 = args.getClass().namespace_;"
    assert out[1] == "x = y.index;"
    assert out[2] == "if (a.inB) {}"


def test_keywords_as_keywords_untouched():
    lines = ["if (x == null)", "return;", "while (true)", "break;",
             "lock (obj1) {}", "foreach (var v in list) {}",
             "int @in = 5;", "namespace Foo.Bar {", "float f = 3.14f;",
             "double d = 1.5;", "x = a..b;"]
    assert esc(lines) == lines


def test_strings_and_comments_untouched():
    out = esc(['string text1 = "a.namespace";',
               "object obj1 = sub_1(a); // use .namespace here",
               "x = y; /* .interface */"])
    assert out[0] == 'string text1 = "a.namespace";'
    assert out[1] == "object obj1 = sub_1(a); // use .namespace here"
    assert out[2] == "x = y; /* .interface */"


def test_nullable_and_calls():
    out = esc(["if (a?.namespace == null)",
               "x = Get(i).in;"])
    assert out[0] == "if (a?.namespace_ == null)"
    assert out[1] == "x = Get(i).in_;"
