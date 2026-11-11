"""Fix 124: wide raw stores byte-address their displacement.

Fix 102/103 rendered `((T*)E + N)[0]`. C# pointer arithmetic scales N by
sizeof(T), so `((float*)this.Ptr + 0x8)[0]` wrote byte 0x20, not the
native 0x8 (game repro: mi 24267 `BabyDoll.set_NetworkedPosition`,
`mov [rcx+8],eax`). The display now casts after the byte-addressed sum:
`((T*)((byte*)E + N))[0]`. Twin canonicalization strips the inner byte
cast so the write-barrier twin `*(E + N)` still meets it.
"""

from iced_x86 import Decoder

from il2cpp import Expr, Lifter
from il2cpp.text import _canon_wide_cast, _norm_twin

from test_review102_raw_store_widths import FLOAT, INT, lift_of


def decode(code, ip=0x1000):
    return Decoder(64, code, ip=ip).decode()


def test_float_store_offset_is_byte_addressed():
    # mov [rbx+8], eax  with float-typed eax
    lift = lift_of({"RBX": Expr("this.Ptr", None, "obj"),
                    "RAX": Expr("value.z", FLOAT, "float")})
    lift._write_mem(decode(bytes((0x89, 0x43, 0x08))), None)
    assert len(lift.out) == 1
    stmt = lift.out[0][1]
    assert stmt.startswith("((float*)((byte*)"), stmt
    assert "((float*)this.Ptr +" not in stmt


def test_no_typed_base_plus_offset_spelling():
    lift = lift_of({"RBX": Expr("num1", None, "int"),
                    "RAX": Expr("num2", INT, "int")})
    lift._write_mem(decode(bytes((0x89, 0x43, 0x18))), None)
    assert lift.out == [(0x1000, "((int*)((byte*)num1 + 0x18))[0] = num2;", None)]


def test_canon_strips_inner_byte_cast():
    assert _canon_wide_cast("((float*)((byte*)this.Ptr + 0x8))[0]") == "*(this.Ptr + 0x8)"
    assert _canon_wide_cast("((uint*)((byte*)v + i*8 + 0x20))[0]") == "*(v + i*8 + 0x20)"


def test_canon_keeps_byte_load_base():
    # a byte* READ used as the base is not the fix-124 wrapper
    assert _canon_wide_cast("((uint*)((byte*)obj34 + 0xb0)[0] + 0x1a0)[0]") == \
        "*(*(obj34 + 0xb0) + 0x1a0)"


def test_norm_twin_bridges_new_spelling():
    assert _norm_twin("((float*)((byte*)this.Ptr + 0x8))[0] = v;") == \
        _norm_twin("*(this.Ptr + 0x8) = v;")
    assert _norm_twin("((uint*)((byte*)v + i*8 + 0x20))[0] = x;") == \
        _norm_twin("*(v + i * 8 + 32) = x;")
    assert _norm_twin("((uint*)((byte*)v + 0x20))[0] = x;") != \
        _norm_twin("((uint*)((byte*)v + 0x24))[0] = x;")


def test_unsafify_fixpoint_on_new_spelling():
    from il2cpp.dec.textpass import _TextPassMixin, _needs_unsafe_block
    t = _TextPassMixin.__new__(_TextPassMixin)
    for s in ("((float*)((byte*)this.Ptr + 0x8))[0] = value.z;",
              "((int*)((byte*)num1 + 0x0))[0] = ((int*)((byte*)num1 + 0x0))[0] + 11;",
              "((uint*)((byte*)obj41 + obj40*4 + 0x20))[0] = 4294967295;"):
        assert t._unsafify(s) == s
        assert _needs_unsafe_block([s])
