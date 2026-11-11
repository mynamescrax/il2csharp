"""Fix 110: unanimous == / != shared calls fold to operators.

An address whose every candidate is a static 2-parameter bool
`op_Equality` (`Equals` twins allowed) or unanimously `op_Inequality`
runs the same machine code whichever owner is true, so the operator
spelling is behavior-exact with no attribution. Operands must prove
the exact same type for some candidate; positions must prove bool.
"""

from types import SimpleNamespace as NS

from il2cpp import Decompiler
from il2cpp.csharp import FA_LITERAL, FA_STATIC

VA_EQ = 0x9000
VA_NE = 0x9100
VA_MIX = 0x9200
VA_FLOAT = 0x9300
VA_INT = 0x9400
VA_SINGLE = 0x9500
VA_GEN = 0x9600
VA_NEMIX = 0x9700

I_BOOL, I_STR, I_INT, I_FLOAT, I_OBJ, I_SINT, I_LIT = range(7)
T_BOOL = (0, 0x02 << 16)
T_STR = (5, 0x0E << 16)
T_INT = (0, 0x08 << 16)
T_FLOAT = (0, 0x0C << 16)
T_OBJ = (0, 0x1C << 16)
T_SINT = (0, (0x08 << 16) | FA_STATIC)
T_LIT = (0, (0x08 << 16) | FA_LITERAL)
TD_HOLDER, TD_PI, TD_SUB = 10, 20, 21
CLS = 0x12 << 16

SPELL = {
    T_BOOL: "bool", T_STR: "string", T_INT: "int", T_FLOAT: "float",
    T_OBJ: "object", T_SINT: "int", T_LIT: "int",
    (TD_HOLDER, CLS): "Holder", (TD_PI, CLS): "PlayerInput",
    (TD_SUB, CLS): "Sub", (5, CLS): "string",
}


def P(ti):
    return NS(type=ti)


METHODS = [
    NS(idx=0, name="Equals", is_static=True, return_type=I_BOOL,
       declaring=TD_HOLDER),                                  # (str,str)
    NS(idx=1, name="op_Equality", is_static=True, return_type=I_BOOL,
       declaring=TD_HOLDER),                                  # (str,str)
    NS(idx=2, name="CompareTo", is_static=False, return_type=I_INT,
       declaring=TD_HOLDER),
    NS(idx=3, name="op_Equality", is_static=True, return_type=I_BOOL,
       declaring=TD_HOLDER),                                  # (float,float)
    NS(idx=4, name="op_Equality", is_static=True, return_type=I_BOOL,
       declaring=TD_HOLDER),                                  # (float,float)
    NS(idx=5, name="Equals", is_static=True, return_type=I_BOOL,
       declaring=TD_HOLDER),                                  # (int,int)
    NS(idx=6, name="op_Equality", is_static=True, return_type=I_BOOL,
       declaring=TD_HOLDER),                                  # (int,int)
    NS(idx=7, name="op_Inequality", is_static=True, return_type=I_BOOL,
       declaring=TD_HOLDER),                                  # (int,int)
    NS(idx=8, name="op_Inequality", is_static=True, return_type=I_BOOL,
       declaring=TD_HOLDER),                                  # (int,int)
    NS(idx=9, name="Equals", is_static=True, return_type=I_BOOL,
       declaring=TD_HOLDER),                                  # (int,int)
]
PARAMS = {
    0: [P(I_STR), P(I_STR)], 1: [P(I_STR), P(I_STR)],
    2: [P(I_STR)], 3: [P(I_FLOAT), P(I_FLOAT)],
    4: [P(I_FLOAT), P(I_FLOAT)], 5: [P(I_INT), P(I_INT)],
    6: [P(I_INT), P(I_INT)], 7: [P(I_INT), P(I_INT)],
    8: [P(I_INT), P(I_INT)], 9: [P(I_INT), P(I_INT)],
}
CANDS = {
    VA_EQ: [("method", 0), ("method", 1)],
    VA_MIX: [("method", 0), ("method", 1), ("method", 2)],
    VA_FLOAT: [("method", 3), ("method", 4)],
    VA_INT: [("method", 5), ("method", 6)],
    VA_SINGLE: [("method", 0)],
    VA_GEN: [("method", 0), ("generic", 3)],
    VA_NE: [("method", 7), ("method", 8)],
    VA_NEMIX: [("method", 7), ("method", 8), ("method", 9)],
}

TYPES = [T_BOOL, T_STR, T_INT, T_FLOAT, T_OBJ, T_SINT, T_LIT]

FIELDS = [
    NS(name="playerInput", type=I_STR, token=1),   # TD_PI, instance
    NS(name="s_pi", type=I_SINT, token=2),         # TD_PI, static
    NS(name="s_count", type=I_SINT, token=3),      # TD_SUB, static
    NS(name="kind", type=I_LIT, token=4),          # TD_SUB, literal
]
TDS = ([NS(index=i, name="T%d" % i, namespace="", field_start=0,
            field_count=0, parent=-1) for i in range(22)])
TDS[TD_HOLDER] = NS(index=TD_HOLDER, name="Holder", namespace="",
                    field_start=0, field_count=0, parent=-1)
TDS[TD_PI] = NS(index=TD_PI, name="PlayerInput", namespace="",
                field_start=0, field_count=2, parent=-1)
TDS[TD_SUB] = NS(index=TD_SUB, name="Sub", namespace="",
                 field_start=2, field_count=2, parent=-1)


def make_lift():
    d = Decompiler.__new__(Decompiler)
    il = NS(addr_candidates=CANDS, types=TYPES,
            type_name=lambda t: SPELL.get(
                (t[0], t[1]) if isinstance(t, tuple) else t, "object"),
            base_chain_tds=lambda td: {21: (21, 20)}.get(td, (td,)))
    meta = NS(methods=METHODS, typedefs=TDS, fields=FIELDS,
              method_params=lambda m: PARAMS.get(
                  getattr(m, "idx", -1), []))
    d.L = NS(il=il, meta=meta)
    d._var_types = {}
    return d


def m_bool():
    return NS(return_type=I_BOOL, name="M", declaring=TD_PI,
              is_static=True)


def m_inst():
    return NS(return_type=I_BOOL, name="M", declaring=TD_PI,
              is_static=False)


def m_void():
    return NS(return_type=I_OBJ, name="M", declaring=TD_PI,
              is_static=True)


def run(d, m, lines):
    return d._shared_equality_ops(lines, m)


def sub(va, args):
    return "sub_%x/*shared body, 2 candidates*/(%s)" % (va, args)


# --- unanimity ---------------------------------------------------------------


def test_eq_rewrites():
    d = make_lift()
    out = run(d, m_bool(), ["string text1 = GetScheme();",
                            "if (%s)" % sub(VA_EQ, 'text1, "Gamepad"')])
    assert out[1] == 'if (text1 == "Gamepad")'


def test_ne_rewrites():
    d = make_lift()
    out = run(d, m_bool(), ["int num1 = GetN();",
                            "if (%s)" % sub(VA_NE, "num1, 3")])
    assert out == ["int num1 = GetN();", "if (num1 != 3)"]


def test_mixed_names_stay():
    d = make_lift()
    line = "if (%s)" % sub(VA_MIX, 'text1, "Gamepad"')
    out = run(d, m_bool(), ["string text1 = GetScheme();", line])
    assert out[1] == line


def test_single_and_generic_stay():
    d = make_lift()
    for va in (VA_SINGLE, VA_GEN):
        line = "if (%s)" % sub(va, 'text1, "Gamepad"')
        out = run(d, m_bool(), ["string text1 = GetScheme();", line])
        assert out[1] == line


def test_nemix_stays():
    d = make_lift()
    line = "if (%s)" % sub(VA_NEMIX, "num1, 3")
    out = run(d, m_bool(), ["int num1 = GetN();", line])
    assert out[1] == line


def test_float_operands_stay():
    d = make_lift()
    line = "if (%s)" % sub(VA_FLOAT, "real1, real2")
    out = run(d, m_bool(),
              ["float real1 = GetF();", "float real2 = GetF();", line])
    assert out[2] == line


def test_int_literals():
    t = Decompiler._eq_int_literal
    assert t("3") == "int"
    assert t("-3") == "int"
    assert t("+3") == "int"
    assert t("0x10") == "int"
    assert t("3u") == "uint"
    assert t("3l") == "long"
    assert t("3ul") == "ulong"
    assert t("9999999999") == "long"
    assert t("99999999999999999999") is None
    assert t("3.0") is None
    assert t("1f") is None
    assert t("abc") is None
    assert t("") is None
    assert t(None) is None


# --- operand typing ----------------------------------------------------------


def test_temp_and_literal_operands():
    d = make_lift()
    out = run(d, m_bool(), ["string text1 = GetScheme();",
                            "string text2 = GetOther();",
                            "bool flag1 = %s;" % sub(VA_EQ, "text1, text2")])
    assert out[2] == "bool flag1 = text1 == text2;"


def test_unknown_and_object_temps_stay():
    d = make_lift()
    line = "if (%s)" % sub(VA_EQ, "obj1, obj2")
    out = run(d, m_bool(), [line])
    assert out[0] == line
    line = "if (%s)" % sub(VA_EQ, 'obj1, "Gamepad"')
    out = run(d, m_bool(), ["object obj1 = GetO();", line])
    assert out[1] == line


def test_multi_decl_temp_stays():
    d = make_lift()
    line = "if (%s)" % sub(VA_EQ, 'text1, "x"')
    out = run(d, m_bool(), ["string text1 = A();", "int text1 = B();",
                            line])
    assert out[2] == line


def test_member_path_operands():
    d = make_lift()
    out = run(d, m_inst(), ["if (%s)" % sub(
        VA_EQ, "this.playerInput, this.playerInput")])
    assert out[0] == "if (this.playerInput == this.playerInput)"


def test_static_via_this_stays():
    d = make_lift()
    line = "if (%s)" % sub(VA_INT, "this.s_pi, 3")
    out = run(d, m_inst(), [line])
    assert out[0] == line


def test_typeof_root_path():
    d = make_lift()
    out = run(d, m_bool(), ["int num1 = GetN();",
                            "if (%s)" % sub(
                                VA_INT, "typeof(Sub).s_count, num1")])
    assert out[1] == "if (typeof(Sub).s_count == num1)"


def test_literal_field_path():
    d = make_lift()
    out = run(d, m_bool(), ["int num1 = GetN();",
                            "if (%s)" % sub(
                                VA_INT, "typeof(Sub).kind, num1")])
    assert out[1] == "if (typeof(Sub).kind == num1)"


def test_call_indexer_addr_operands_stay():
    d = make_lift()
    for args in ("GetA(), b", "a[0], b", "&a, b", "a + b, c",
                 "null, b", "a, b, Foo()"):
        line = "if (%s)" % sub(VA_EQ, args)
        out = run(d, m_bool(), ["string a = A();", "string b = B();",
                                "string c = C();", line])
        assert out[-1] == line, args


# --- positions ---------------------------------------------------------------


def test_positions():
    d = make_lift()
    body = ["string text1 = GetScheme();",
            "while (%s)" % sub(VA_EQ, 'text1, "x"'),
            "return %s;" % sub(VA_EQ, 'text1, "y"'),
            "bool flag1 = %s;" % sub(VA_EQ, 'text1, "z"')]
    out = run(d, m_bool(), body)
    assert out[1] == 'while (text1 == "x")'
    assert out[2] == 'return text1 == "y";'
    assert out[3] == 'bool flag1 = text1 == "z";'


def test_return_void_and_object_decl_stay():
    d = make_lift()
    out = run(d, m_void(), ["return %s;" % sub(VA_EQ, 'text1, "y"')])
    assert out[0].startswith("return sub_")
    d = make_lift()
    out = run(d, m_bool(), ["object obj1 = GetO();",
                            "object obj2 = %s;" % sub(VA_EQ, 'text1, "y"')])
    assert out[1].startswith("object obj2 = sub_")


def test_bang_and_paren_shapes():
    d = make_lift()
    out = run(d, m_bool(), ["string text1 = GetScheme();",
                            "if (!(sub_9000(text1, \"x\")))"])
    assert out[1] == 'if (!(text1 == "x"))'


def test_and_operand():
    d = make_lift()
    out = run(d, m_bool(), ["string text1 = GetScheme();",
                            "bool ok = true;",
                            "if (ok && sub_9000(text1, \"x\"))"])
    assert out[2] == 'if (ok && text1 == "x")'


def test_multi_site_line():
    d = make_lift()
    out = run(d, m_bool(), ["string text1 = A();", "string text2 = B();",
                            "if (sub_9000(text1, \"x\") && "
                            "sub_9000(text2, \"y\"))"])
    assert out[2] == 'if (text1 == "x" && text2 == "y")'


def test_bare_and_nested_stay():
    d = make_lift()
    line = "%s;" % sub(VA_EQ, 'text1, "x"')
    out = run(d, m_bool(), ["string text1 = GetScheme();", line])
    assert out[1] == line
    line = "Foo(%s);" % sub(VA_EQ, 'text1, "x"')
    out = run(d, m_bool(), ["string text1 = GetScheme();", line])
    assert out[1] == line


def test_extra_args():
    d = make_lift()
    out = run(d, m_bool(), ["string text1 = GetScheme();",
                            "if (%s)" % sub(VA_EQ, 'text1, "x", 0')])
    assert out[1] == 'if (text1 == "x")'


def test_parenize():
    p = Decompiler._eq_parenize
    assert p("text1", "text1") == "text1"
    assert p("a.b", "a.b") == "a.b"
    assert p('"x"', '"   "') == '"x"'
    assert p("F()", "F()") == "F()"
    assert p("a + b", "a + b") == "(a + b)"
    assert p(None, None) is None
