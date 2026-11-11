"""Fix 138: a for-head counter nothing declares gets a bare declaration.

`_for_sugar` folds the counter's entry copy into the loop head without a
type when the counter outlives the loop (`for (num2 = 0; ...)` followed
by `F(num2)`) or its init is not a literal. When no enclosing scope has
declared the counter, the rename pass now emits `T name;` on the line
before the head (CS0103 at ~11.6k head/body/after-loop reads in gate
b12). A counter some enclosing scope already declares is left alone.
"""
from il2cpp import Decompiler


INT_T = (0, 0x08 << 16)


def rename(lines, var_types=None):
    dec = Decompiler.__new__(Decompiler)
    dec._var_types = dict(var_types or {})
    dec.L = type("L", (), {})()
    dec.L._var_types = {}
    dec.L.slot_types = {}
    dec.L._type_hints = {}
    dec.L.il = type("I", (), {})()
    dec.L.il.type_name = lambda t: {INT_T: "int"}.get(t, "object")
    return dec._rename_locals(list(lines))


def test_undeclared_head_counter_is_declared_before_the_loop():
    out = rename(["for (v3 = 0; v3 < v1; v3++)", "{", "}", "F(v3);"],
                 var_types={"v3": INT_T, "v1": INT_T})
    assert out == ["int num1;", "for (num1 = 0; num1 < num2; num1++)", "{", "}",
                   "F(num1);"]


def test_indent_and_nonliteral_init():
    out = rename(["    for (v3 = v2 + 1; v3 < 9; v3++)"],
                 var_types={"v3": INT_T, "v2": INT_T})
    assert out == ["    int num1;", "    for (num1 = num2 + 1; num1 < 9; num1++)"]


def test_already_declared_counter_is_untouched():
    out = rename(["v3 = 5;", "for (v3 = 0; v3 < 9; v3++)"],
                 var_types={"v3": INT_T})
    assert out == ["int num1 = 5;", "for (num1 = 0; num1 < 9; num1++)"]


def test_typed_head_and_later_bare_assignment():
    # an already-typed head declares itself; a later bare write after a
    # minted declaration stays an assignment
    assert rename(["for (int v3 = 0; v3 < 9; v3++)"], var_types={"v3": INT_T}) == [
        "for (int num1 = 0; num1 < 9; num1++)"]
    out = rename(["for (v3 = 0; v3 < 9; v3++)", "v3 = 7;"], var_types={"v3": INT_T})
    assert out == ["int num1;", "for (num1 = 0; num1 < 9; num1++)", "num1 = 7;"]
