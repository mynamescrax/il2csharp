"""Fix 102: raw native-width stores render width-preserving casts.

A raw `*(base + disp)` lvalue renders `((byte*)base + disp)[0]`, which
fails to compile whenever the stored value is not a byte. The native
width is ground truth from the store instruction, so a same-width cast
(`uint`/`int`/`float`/...) preserves address, value and width. Only the
emitted statement spells the width: kills, slots, barriers and twin
dedup keep the raw text (the barrier twin still renders raw, bridged
by `_canon_wide_cast` in `_norm_twin`).
"""

import struct
from types import SimpleNamespace as NS

from iced_x86 import Decoder, Mnemonic

from il2cpp import Expr, Lifter
from il2cpp.text import _canon_wide_cast, _norm_twin

INT = (0, 0x08 << 16)
UINT = (0, 0x09 << 16)
LONG = (0, 0x0A << 16)
ULONG = (0, 0x0B << 16)
FLOAT = (0, 0x0C << 16)
DOUBLE = (0, 0x0D << 16)
BYTE = (0, 0x05 << 16)
SBYTE = (0, 0x04 << 16)
SHORT = (0, 0x06 << 16)
USHORT = (0, 0x07 << 16)
CHAR = (0, 0x03 << 16)
BOOL = (0, 0x02 << 16)
OBJECT = (0, 0x1C << 16)
BYREF_INT = (0, (0x08 << 16) | (1 << 29))


def make_lift():
    lift = Lifter.__new__(Lifter)
    lift.regs = {}
    lift.out = []
    lift.dry = False
    lift.asm_comments = False
    lift.flags = None
    lift.slot_types = {}
    lift._type_hints = {}
    lift.stack_map = {}
    lift.stack_values = {}
    lift.il = NS()
    lift.meta = NS(typedefs=[])
    lift._td_of = lambda ty: None
    lift._last_stmt = None
    return lift


def lift_of(regs):
    lift = make_lift()
    lift.regs.update(regs)
    return lift


# --- integer literal fit -------------------------------------------------


def test_dword_negative_takes_signed():
    lift = make_lift()
    assert lift._wide_int_cast(4, -2) == "int"
    assert lift._wide_int_cast(4, -2147483648) == "int"


def test_dword_wrapped_takes_unsigned():
    lift = make_lift()
    assert lift._wide_int_cast(4, 4294967294) == "uint"
    assert lift._wide_int_cast(4, 1084227584) == "int"
    assert lift._wide_int_cast(4, 0) == "int"


def test_dword_overflow_declines():
    lift = make_lift()
    assert lift._wide_int_cast(4, 1 << 32) is None
    assert lift._wide_int_cast(4, -(1 << 31) - 1) is None


def test_word_fit():
    lift = make_lift()
    assert lift._wide_int_cast(2, 1000) == "short"
    assert lift._wide_int_cast(2, 257) == "short"
    assert lift._wide_int_cast(2, -1) == "short"
    assert lift._wide_int_cast(2, 70000) is None
    assert lift._wide_int_cast(2, 40000) == "ushort"


def test_qword_and_bad_widths():
    lift = make_lift()
    assert lift._wide_int_cast(8, 1609587929392839161) == "long"
    assert lift._wide_int_cast(8, (1 << 64) - 1) == "ulong"
    assert lift._wide_int_cast(1, 5) is None
    assert lift._wide_int_cast(16, 5) is None


# --- store cast selection --------------------------------------------------


def test_store_literals():
    lift = make_lift()
    assert lift._wide_src_cast(4, "4294967294", None) == "uint"
    assert lift._wide_src_cast(4, "-1", None) == "int"
    assert lift._wide_src_cast(4, "-0x10", None) == "int"
    assert lift._wide_src_cast(2, "1000", None) == "short"
    assert lift._wide_src_cast(4, "1000", None) == "int"
    assert lift._wide_src_cast(4, "0f", None) == "int"
    assert lift._wide_src_cast(4, "5u", None) == "int"
    assert lift._wide_src_cast(4, "0xFF", None) == "int"
    assert lift._wide_src_cast(4, "?", None) is None
    assert lift._wide_src_cast(4, "num1", None) is None
    assert lift._wide_src_cast(4, "", None) is None
    assert lift._wide_src_cast(4, None, None) is None
    assert lift._wide_src_cast(4, "1e5", None) is None  # not an int spelling


def test_store_float_literals():
    lift = make_lift()
    assert lift._wide_src_cast(4, "1.0f", None) == "float"
    assert lift._wide_src_cast(8, "1.0d", None) == "double"
    assert lift._wide_src_cast(8, "1.0", None) == "double"
    # the suffix is the width proof: crossing it would change the value
    assert lift._wide_src_cast(8, "1.0f", None) is None
    assert lift._wide_src_cast(4, "1.0d", None) is None
    assert lift._wide_src_cast(4, "1.0", None) is None
    assert lift._wide_src_cast(2, "1.0f", None) is None
    assert lift._wide_src_cast(1, "1.0f", None) is None


def test_store_reg_types():
    lift = make_lift()
    assert lift._wide_src_cast(4, "num1", INT) == "int"
    assert lift._wide_src_cast(4, "num1", UINT) == "uint"
    assert lift._wide_src_cast(2, "num1", SHORT) == "short"
    assert lift._wide_src_cast(2, "num1", USHORT) == "ushort"
    assert lift._wide_src_cast(2, "num1", CHAR) == "ushort"
    assert lift._wide_src_cast(8, "num1", LONG) == "long"
    assert lift._wide_src_cast(8, "num1", ULONG) == "ulong"
    assert lift._wide_src_cast(4, "real1", FLOAT) == "float"
    assert lift._wide_src_cast(8, "real1", DOUBLE) == "double"
    # exact-size only: a narrower source leaves upper bytes unexplained,
    # so every rendered byte would not be value-determined.
    assert lift._wide_src_cast(8, "num1", INT) is None
    assert lift._wide_src_cast(2, "num1", INT) is None
    assert lift._wide_src_cast(4, "num1", BYTE) is None
    assert lift._wide_src_cast(2, "num1", BYTE) is None
    assert lift._wide_src_cast(4, "num1", SBYTE) is None
    assert lift._wide_src_cast(8, "num1", SBYTE) is None
    assert lift._wide_src_cast(4, "num1", SHORT) is None
    assert lift._wide_src_cast(8, "real1", FLOAT) is None
    assert lift._wide_src_cast(4, "real1", DOUBLE) is None
    assert lift._wide_src_cast(4, "num1", CHAR) is None
    assert lift._wide_src_cast(4, "flag1", BOOL) is None
    assert lift._wide_src_cast(8, "obj1", OBJECT) is None
    assert lift._wide_src_cast(4, "num1", BYREF_INT) is None
    assert lift._wide_src_cast(3, "num1", INT) is None


# --- RMW cast selection ------------------------------------------------------


def test_rmw_int_sources():
    lift = make_lift()
    assert lift._wide_rmw_cast(4, Mnemonic.ADD, "11", None) == "int"
    assert lift._wide_rmw_cast(8, Mnemonic.ADD, "11", None) == "long"
    assert lift._wide_rmw_cast(4, Mnemonic.XOR, "num1", UINT) == "uint"
    assert lift._wide_rmw_cast(4, Mnemonic.ADD, "num1", INT) == "int"
    assert lift._wide_rmw_cast(8, Mnemonic.ADD, "num1", LONG) == "long"


def test_rmw_declines():
    lift = make_lift()
    assert lift._wide_rmw_cast(2, Mnemonic.ADD, "11", None) is None
    assert lift._wide_rmw_cast(4, Mnemonic.ADD, "4294967295", None) is None
    assert lift._wide_rmw_cast(4, Mnemonic.ADD, "num1", LONG) is None
    assert lift._wide_rmw_cast(4, Mnemonic.ADD, "flag1", BOOL) is None
    assert lift._wide_rmw_cast(4, Mnemonic.ADD, "1.5f", None) is None
    assert lift._wide_rmw_cast(4, Mnemonic.ADDSS, "11", None) is None


def test_rmw_float_sources():
    lift = make_lift()
    assert lift._wide_rmw_cast(4, Mnemonic.ADDSS, "1.5f", None) == "float"
    assert lift._wide_rmw_cast(8, Mnemonic.ADDSD, "real1", DOUBLE) == "double"
    assert lift._wide_rmw_cast(4, Mnemonic.MULSS, "real1", FLOAT) == "float"
    assert lift._wide_rmw_cast(4, Mnemonic.ADDSS, "real1", INT) is None


# --- twin canonicalization -----------------------------------------------------


def test_norm_twin_bridges_wide_and_raw():
    assert _norm_twin("((uint*)v + i*8 + 0x20)[0] = x;") == \
        _norm_twin("*(v + i * 8 + 32) = x;")
    assert _norm_twin("((int*)obj8 + 0x0)[0] = 5;") == \
        _norm_twin("*(obj8 + 0x0) = 5;")


def test_norm_twin_keeps_distinct_apart():
    assert _norm_twin("((uint*)v + 0x20)[0] = x;") != \
        _norm_twin("((uint*)v + 0x24)[0] = x;")
    assert _norm_twin("((uint*)v + 0x20)[0] = x;") != \
        _norm_twin("((uint*)v + 0x20)[0] = y;")


def test_norm_twin_plain_behavior_unchanged():
    assert _norm_twin("*(v + 32) = x;") == _norm_twin("*(v+0x20)=x;")
    assert _norm_twin("x = (a + b) * c;") == _norm_twin("x=(a+b)*c;")


def test_canon_nested_and_passthrough():
    assert _canon_wide_cast("((uint*)((byte*)obj34 + 0xb0)[0] + 0x1a0)[0]") == \
        "*(*(obj34 + 0xb0) + 0x1a0)"
    assert _canon_wide_cast("x = (a + b) * c;") == "x = (a + b) * c;"
    assert _canon_wide_cast("x = ((int)y) + 1;") == "x = ((int)y) + 1;"
    assert _canon_wide_cast("((uint*)x)[0]") == "*(x)"


# --- unsafe detector + render fixpoints ------------------------------------------


def test_needs_unsafe_block():
    from il2cpp.dec.textpass import _needs_unsafe_block
    assert _needs_unsafe_block(["((uint*)x + 0x10)[0] = 5;"])
    assert _needs_unsafe_block(["((byte*)x)[0];"])
    assert _needs_unsafe_block(["y = *(x + 4);"])
    assert not _needs_unsafe_block(["int x = 5;"])
    assert not _needs_unsafe_block(["x = (int)y;"])
    assert not _needs_unsafe_block(["x = (a + b) * c;"])


def test_unsafify_keeps_wide_shapes():
    from il2cpp.dec.textpass import _TextPassMixin
    t = _TextPassMixin.__new__(_TextPassMixin)
    for s in ("((uint*)obj8 + 0x0)[0] = 4294967294;",
              "((int*)obj8 + 0x0)[0] = -1;",
              "((float*)obj8 + 0x10)[0] = 1.0f;",
              "((uint*)obj8 + 0x0)[0] = ((uint*)obj8 + 0x0)[0] + 11;"):
        assert t._unsafify(s) == s


# --- end-to-end through _write_mem / _rmw_mem --------------------------------------


def decode(code, ip=0x1000):
    return Decoder(64, code, ip=ip).decode()


def test_write_mem_dword_imm_widens():
    lift = lift_of({"RBX": Expr("num1", None, "int")})
    lift._write_mem(decode(bytes((0xC7, 0x03, 0xFE, 0xFF, 0xFF, 0xFF))), None)
    assert lift.out == [(0x1000, "((uint*)((byte*)num1 + 0x0))[0] = 4294967294;", None)]
    # the side-channel records the raw parts; kills/slots keep raw text
    assert lift._lv_width == 4
    assert lift._lv_raw_parts == ("num1", "+ 0x0")


def test_write_mem_reg_src_widens_by_type():
    lift = lift_of({"RBX": Expr("num1", None, "int"),
                    "RAX": Expr("num2", INT, "int")})
    lift._write_mem(decode(bytes((0x89, 0x03))), None)
    assert lift.out == [(0x1000, "((int*)((byte*)num1 + 0x0))[0] = num2;", None)]


def test_write_mem_byte_store_untouched():
    lift = lift_of({"RBX": Expr("num1", None, "int")})
    lift._write_mem(decode(bytes((0xC6, 0x03, 0x05))), None)
    assert lift.out == [(0x1000, "*(num1 + 0x0) = 5;", None)]


def test_write_mem_unknown_src_stays_raw():
    lift = lift_of({"RBX": Expr("num1", None, "int"),
                    "RAX": Expr("obj1", None, "obj")})
    lift._write_mem(decode(bytes((0x89, 0x03))), None)
    assert lift.out == [(0x1000, "*(num1 + 0x0) = obj1;", None)]


def test_write_mem_wide_reg_mismatch_stays_raw():
    # int value in a qword store: the upper bytes are unexplained,
    # so no cast renders them value-determined.
    lift = lift_of({"RBX": Expr("num1", None, "int"),
                    "RAX": Expr("num2", INT, "int")})
    lift._write_mem(decode(bytes((0x48, 0x89, 0x03))), None)
    assert lift.out == [(0x1000, "*(num1 + 0x0) = num2;", None)]


def test_rmw_dword_widens():
    lift = lift_of({"RBX": Expr("num1", None, "int")})
    lift._rmw_mem(decode(bytes((0x83, 0x03, 0x0B))), None, "+")
    assert lift.out == [(0x1000, "((int*)((byte*)num1 + 0x0))[0] = ((int*)((byte*)num1 + 0x0))[0] + 11;", None)]


def test_rmw_word_stays_raw():
    lift = lift_of({"RBX": Expr("num1", None, "int")})
    lift._rmw_mem(decode(bytes((0x66, 0x83, 0x03, 0x0B))), None, "+")
    assert lift.out == [(0x1000, "*(num1 + 0x0) = *(num1 + 0x0) + 11;", None)]


def test_mem_lvalue_dotted_raw_records_parts():
    # fix 102c: _field_expr's miss over a dotted base returns the raw
    # text through the field branch; the parts must still be recorded.
    lift = lift_of({"RBX": Expr("this.ropeRenderer", None, "obj")})
    ins = decode(bytes((0xC7, 0x43, 0x54, 0x00, 0x00, 0x80, 0x40)))
    lv = lift._mem_lvalue(ins)
    assert lv == "*(this.ropeRenderer + 0x54)"
    assert lift._lv_width == 4
    assert lift._lv_raw_parts == ("this.ropeRenderer", "+ 0x54")


def test_write_mem_dotted_base_widens():
    lift = lift_of({"RBX": Expr("this.ropeRenderer", None, "obj")})
    lift._write_mem(decode(bytes((0xC7, 0x43, 0x54, 0x00, 0x00, 0x80, 0x40))), None)
    assert lift.out == [(0x1000, "((int*)((byte*)this.ropeRenderer + 0x54))[0] = 1082130432;", None)]


def test_unsafify_keeps_dotted_wide_shapes():
    from il2cpp.dec.textpass import _TextPassMixin
    t = _TextPassMixin.__new__(_TextPassMixin)
    s = "((uint*)this.ropeRenderer + 0x54)[0] = 1082130432;"
    assert t._unsafify(s) == s


def test_unsafify_keeps_indexed_wide_shapes():
    # fix 103: the indexed display mirrors the raw branch's own
    # `_term_up` construction, so these are fixpoints like the byte*
    # twins (including a composite index and a byte* index read).
    from il2cpp.dec.textpass import _TextPassMixin
    t = _TextPassMixin.__new__(_TextPassMixin)
    for s in ("((uint*)outChars + num5*2 + 0x0)[0] = 655373;",
              "((float*)obj93 + obj94*8 + 0x24)[0] = 1065353216;",
              "((uint*)num4 + (((byte*)voidPtr1 + 0x8)[0])*1 + 0x30)[0] = 65535;",
              "((uint*)tree + (max_code * 2 + 3)*2 + 0x20)[0] = 32767;"):
        assert t._unsafify(s) == s


def test_write_mem_indexed_imm_widens():
    # mov dword [rbx+rsi*4+0x20], 0xFFFFFFFF
    lift = lift_of({"RBX": Expr("obj41", None, "int"),
                    "RSI": Expr("obj40", None, "int")})
    lift._write_mem(decode(bytes((0xC7, 0x44, 0xB3, 0x20, 0xFF, 0xFF, 0xFF, 0xFF))), None)
    assert lift.out == [(0x1000, "((uint*)((byte*)obj41 + obj40*4 + 0x20))[0] = 4294967295;", None)]


def test_write_mem_indexed_reg_src_widens():
    # mov [rbx+rsi*4+0x20], eax with int-typed eax
    lift = lift_of({"RBX": Expr("obj41", None, "int"),
                    "RSI": Expr("obj40", None, "int"),
                    "RAX": Expr("num1", INT, "int")})
    lift._write_mem(decode(bytes((0x89, 0x44, 0xB3, 0x20))), None)
    assert lift.out == [(0x1000, "((int*)((byte*)obj41 + obj40*4 + 0x20))[0] = num1;", None)]


def test_write_mem_indexed_unknown_src_stays_raw():
    lift = lift_of({"RBX": Expr("obj41", None, "int"),
                    "RSI": Expr("obj40", None, "int"),
                    "RAX": Expr("obj1", None, "obj")})
    lift._write_mem(decode(bytes((0x89, 0x44, 0xB3, 0x20))), None)
    assert lift.out == [(0x1000, "*(obj41 + obj40*4 + 0x20) = obj1;", None)]


def test_rmw_indexed_widens():
    # add dword [rbx+rsi*4+0x20], 11
    lift = lift_of({"RBX": Expr("obj41", None, "int"),
                    "RSI": Expr("obj40", None, "int")})
    lift._rmw_mem(decode(bytes((0x83, 0x44, 0xB3, 0x20, 0x0B))), None, "+")
    assert lift.out == [(0x1000, "((int*)((byte*)obj41 + obj40*4 + 0x20))[0] = ((int*)((byte*)obj41 + obj40*4 + 0x20))[0] + 11;", None)]
