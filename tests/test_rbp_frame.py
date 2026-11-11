"""The `mov rbp,rsp` frame must survive a CFG merge, and one stack home must
have one key.

E1: `_rbp_is_frame()` used to read the register VALUE, and the pass-2 phi
merge rewrites that value out from under it -- a never-written RBP = None
becomes Expr('?'), which _bind then rewrites to a temp name. In a merged
block every arm of the predicate failed, so every `[rbp+N]` fell out of the
frame branch and fabricated pointer arithmetic on a non-pointer.

The predicate now consults `_rbp_frame`, a tracked FACT rather than an
inference: set by `mov rbp,rsp`, cleared by any other write to RBP through
`set_reg`, and untouched by the merge (which writes `L.regs` directly).

E3: `slot_var` keys by `off + rsp_delta` and names by `abs(off)`, but its
callers passed three different sign conventions -- iced-x86 reports
`[rbp-0x30]` as 0xffffffffffffffd0. One method held two coordinate systems
for one native home, so a `[copy+N]` write and an `[rsp+M]` read of the same
slot became two C# locals, and names came out as `s_ffffffffffffffd0`.
"""
import pytest

from il2cpp import Lifter
from il2cpp.expr import Expr

RAW_NEG_30 = (1 << 64) - 0x30      # iced-x86's encoding of [rbp-0x30]
RAW_NEG_18 = (1 << 64) - 0x18      # ...and of [rsp-0x18]


def stub(regs=None, rsp_delta=0, stack_map=None):
    lf = Lifter.__new__(Lifter)
    lf.regs = dict(regs or {})
    lf.rsp_delta = rsp_delta
    lf.stack_map = {} if stack_map is None else stack_map
    lf._rbp_frame = False
    return lf


def _unk_expr():
    e = Expr("v1", None, "?")
    e._unk = True
    return e


# ------------------------------------------------------------------ E1
def test_frame_fact_makes_a_merged_rbp_a_frame():
    lf = stub({"RBP": Expr("?", None, "?")})
    lf._rbp_frame = True
    assert lf._rbp_is_frame() is True
    # the same register with no proven frame still declines
    assert stub({"RBP": Expr("?", None, "?")})._rbp_is_frame() is False


def test_frame_fact_survives_a_bound_temp_name():
    """_bind rewrites the merge-minted '?' to a temp name, which is why a
    text test could not cover the second half of the sites."""
    lf = stub({"RBP": Expr("v45", None, "?")})
    assert lf._rbp_is_frame() is False
    lf._rbp_frame = True
    assert lf._rbp_is_frame() is True


@pytest.mark.parametrize("regs", [
    {"RBP": None},                                  # never written
    {"RBP": Expr("?addr", None, "?")},              # untracked rsp-derived base
    {"RBP": _unk_expr()},                           # entry-seed unknown
    {"RBP": Expr("&s_10", None, "ptr")},            # lea rbp frame slot
])
def test_unchanged_predicate_arms(regs):
    lf = stub(regs)
    lf._rbp_frame = True
    assert lf._rbp_is_frame() is True


def test_real_write_to_rbp_clears_the_frame_fact():
    lf = stub({"RBP": None})
    lf._rbp_frame = True
    lf.set_reg("RBP", Expr("this.thing", None, "obj"))
    assert lf._rbp_frame is False
    assert lf._rbp_is_frame() is False


def test_frame_setup_write_does_not_clear_the_fact():
    """`mov rbp,rsp` stores None (RSP is never tracked) and re-arms the
    fact on the next line, so the None write must leave it alone."""
    lf = stub({"RBP": None})
    lf._rbp_frame = True
    lf.set_reg("RBP", None)
    assert lf._rbp_frame is True
    assert lf._rbp_is_frame() is True


def test_the_merge_cannot_clear_the_fact():
    """The pass-2 merge installs register values with L.regs[k] = ..., which
    bypasses set_reg -- that is exactly why the fact survives it."""
    import inspect

    from il2cpp.dec import analyze
    src = inspect.getsource(analyze)
    assert "L.regs[k] = Expr('?', None, '?')" in src
    assert "set_reg" not in src


# ------------------------------------------------------------------ E3
def test_slot_var_normalises_a_raw_displacement():
    lf = stub()
    name = lf.slot_var(RAW_NEG_30)
    assert -0x30 in lf.stack_map
    assert not name.startswith("s_ffff")
    assert name == "s_30"


def test_signed_and_raw_callers_agree():
    raw = stub()
    signed = stub()
    assert raw.slot_var(RAW_NEG_30) == signed.slot_var(-0x30) == "s_30"
    assert set(raw.stack_map) == set(signed.stack_map)


def test_one_home_one_key():
    lf = stub()
    lf.slot_var(RAW_NEG_30)
    lf.slot_var(-0x30)
    assert len(lf.stack_map) == 1


def test_normalisation_is_idempotent_for_correct_callers():
    lf = stub()
    lf.stack_map[-0x30] = "s_preexisting"
    assert lf.slot_var(RAW_NEG_30) == "s_preexisting"
    assert lf.slot_var(RAW_NEG_18) != "s_preexisting"


def test_positive_displacements_unchanged():
    lf = stub()
    assert lf.slot_var(0x28) == "s_28"
    assert lf.slot_var(0) == "s_0"


def test_rsp_delta_still_offsets_the_key():
    lf = stub(rsp_delta=0x28)
    lf.slot_var(RAW_NEG_30)
    assert list(lf.stack_map) == [-0x30 + 0x28]


def test_no_raw_unsigned_key_survives():
    lf = stub()
    for raw in (RAW_NEG_30, RAW_NEG_18, 0xFFFFFFFFFFFFFFF8, 0x28, 0x0):
        lf.slot_var(raw)
    assert all(k <= (1 << 63) for k in lf.stack_map)
