"""A per-method frame fact must not survive into the next method.

`Lifter` is one instance for the whole build, so anything a method records
about itself must be cleared by EVERY per-method entry point. `lift()` (the
flat / oversized-CFG fallback path) has its own reset block, separate from
`_setup_entry` (the structured path), so a reset in only one of them leaks a
stale `_rbp_frame` into every method that follows -- which would render
`[rbp+N]` as a frame slot in a method that never established a frame.
"""
import pytest

from test_game_goldens import game_decompiler

pytestmark = pytest.mark.game

FRAME_MI = 24062          # WrapRopePlayerController.Update: push rbp; mov rbp,rsp


def _disasm(il, m):
    from il2cpp import Decompiler, Lifter
    insns, _ = Decompiler(Lifter(il))._decode(m)
    return "\n".join(str(i) for i in insns)


def _control_method(il, skip_mi):
    """A method with native code that never sets up a frame pointer."""
    for m in il.meta.methods:
        if not m.addr or m.index == skip_mi:
            continue
        try:
            asm = _disasm(il, m)
        except Exception:
            continue
        if "rbp,rsp" not in asm:
            return m
    pytest.skip("no frame-less control method found")


def test_frame_method_arms_the_fact(game_decompiler):
    il, dec = game_decompiler
    m = il.meta.methods[FRAME_MI]
    assert "rbp,rsp" in _disasm(il, m)
    dec.lift_method(m, il.meta.typedefs[m.declaring])
    assert getattr(dec.L, "_rbp_frame", False) is True


def test_structured_path_clears_the_fact_between_methods(game_decompiler):
    il, dec = game_decompiler
    m_frame = il.meta.methods[FRAME_MI]
    dec.lift_method(m_frame, il.meta.typedefs[m_frame.declaring])
    assert getattr(dec.L, "_rbp_frame", False) is True

    m_plain = _control_method(il, FRAME_MI)
    dec.lift_method(m_plain, il.meta.typedefs[m_plain.declaring])
    assert getattr(dec.L, "_rbp_frame", False) is False, \
        "frame fact leaked from mi %d into mi %d" % (FRAME_MI, m_plain.index)


def test_flat_lift_path_also_clears_the_fact(game_decompiler):
    """`lift()` resets its own per-method state and must clear the fact too."""
    il, dec = game_decompiler
    lift = dec.L

    m_frame = il.meta.methods[FRAME_MI]
    lift.lift(m_frame, il.meta.typedefs[m_frame.declaring])
    assert getattr(lift, "_rbp_frame", False) is True

    m_plain = _control_method(il, FRAME_MI)
    lift.lift(m_plain, il.meta.typedefs[m_plain.declaring])
    assert getattr(lift, "_rbp_frame", False) is False, \
        "the flat lift path leaked the frame fact"
