"""Fix 112: fresh-array creations get brackets repaired.

`new T[N][i]` parses as an invalid rank specifier and
`new T[N](idx)[0]` (single argument, ldelema shape) as an invalid
call. Wrapping the creation is meaning-preserving (allocation, size,
and index survive verbatim) while the lines become valid C#.
"""

from il2cpp import Decompiler


def dec():
    return Decompiler.__new__(Decompiler)


def fix(lines):
    return dec()._fresh_array_brackets(lines)


def test_index_forms():
    out = fix(["object obj30 = new int[3][num3];",
               "if ((new Npc[6][((byte*)obj139 + 0x54)[0]] == null))"])
    assert out[0] == "object obj30 = (new int[3])[num3];"
    assert out[1] == ("if (((new Npc[6])[((byte*)obj139 + 0x54)[0]] "
                      "== null))")


def test_index_write_wraps():
    out = fix(["new char[1][0x0] = 32;"])
    assert out == ["(new char[1])[0x0] = 32;"]


def test_call_ldelema_forms():
    out = fix(["object obj10 = ((byte*)(num5 + 0x2) + "
               "new byte[extraFieldLength]((byte*)1)[0] + 0x21)[0];"])
    assert out == ["object obj10 = ((byte*)(num5 + 0x2) + "
                   "(new byte[extraFieldLength])[(byte*)1] + 0x21)[0];"]


def test_plain_allocs_untouched():
    lines = ["object obj1 = new Foo();",
             "object obj2 = new List<int>();",
             "object obj3 = new Dictionary<int, string>();",
             "object obj4 = new byte[num1];",
             "object obj5 = (new int[2]).Length;",
             "bool flag1 = (new byte[num4] == null);"]
    assert fix(lines) == lines


def test_call_nonderef_and_multi_stay():
    lines = ["object obj1 = new Foo(a, b);",
             "object obj2 = new byte[8](x);",
             "object obj3 = new byte[8](x, y)[0];",
             "object obj4 = new byte[8](x)[1];"]
    assert fix(lines) == lines


def test_garbage_and_unbalanced_stay():
    lines = ["object obj1 = new Foo Bar[3];",
             "object obj2 = new [3][i];",
             "object obj3 = new byte[3;",
             "object obj4 = Renewed();"]
    assert fix(lines) == lines


def test_strings_comments_untouched():
    out = fix(['string text1 = "new byte[5][i]";',
               "object obj1 = sub_1(a); // new int[3][0]",
               "x = y; /* new int[3][0] */"])
    assert out[0] == 'string text1 = "new byte[5][i]";'
    assert out[1] == "object obj1 = sub_1(a); // new int[3][0]"
    assert out[2] == "x = y; /* new int[3][0] */"


def test_nested_and_multi_site():
    out = fix(["object obj1 = new A[new B[1][i]];",
               "object obj2 = new T[N][i] + new U[M][j];"])
    assert out[0] == "object obj1 = new A[(new B[1])[i]];"
    assert out[1] == ("object obj2 = (new T[N])[i] + "
                      "(new U[M])[j];")
