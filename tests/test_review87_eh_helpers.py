"""Regression tests for fix 90: EH helper naming is per-method evidence.

`_seh_helpers` used to write `raise_va` / `rethrow_va` onto the shared lifter
with no guard of any kind, so the values survived into every later method: a
body's rendering depended on what had been lifted before it.

A census of 4,526 pad-bearing methods showed the helper VA is not a program
constant (99 distinct rethrow targets, 9 raise targets, two taught as both),
and that 51 of the rethrow targets were ordinary registered methods --
AsyncTaskMethodBuilder.SetException, Debug.LogException, Marshal.FreeHGlobal,
even DateTime.AddYears -- so any caller of one of those printed `throw;` in
place of the call.

Fix 90 clears both fields for every method and requires a candidate to be
unregistered native code.
"""
import types

import pytest

from il2cpp import Decompiler


def _dec(addr_to_method=None, addr_candidates=None, exports=None):
    """A Decompiler over a stub lifter; __init__ only stores what it is given."""
    il = types.SimpleNamespace(
        addr_to_method=addr_to_method or {},
        addr_candidates=addr_candidates or {},
        bin=types.SimpleNamespace(exports=exports or {}),
    )
    return Decompiler(types.SimpleNamespace(il=il))


def test_registered_managed_methods_are_rejected():
    dec = _dec(addr_to_method={0x180435740: ("method", 7)})
    assert dec._eh_helper_ok(0x180435740) is False


def test_generic_and_thunk_owners_are_rejected():
    dec = _dec(addr_to_method={0x1000: ("generic", 3), 0x2000: ("thunk", ("m", 1))})
    assert dec._eh_helper_ok(0x1000) is False
    assert dec._eh_helper_ok(0x2000) is False


def test_candidate_owners_are_rejected_without_a_primary_owner():
    # addr_to_method keeps only the first owner of a VA; addr_candidates keeps
    # every one, so a shared address is still a managed method
    dec = _dec(addr_candidates={0x3000: [("method", 9), ("method", 10)]})
    assert dec._eh_helper_ok(0x3000) is False


def test_exports_are_rejected():
    dec = _dec(exports={0x4000: "il2cpp_init"})
    assert dec._eh_helper_ok(0x4000) is False


def test_unregistered_native_code_is_accepted():
    dec = _dec(addr_to_method={0x1000: ("method", 7)})
    assert dec._eh_helper_ok(0x180435670) is True


def test_missing_targets_are_rejected():
    dec = _dec()
    assert dec._eh_helper_ok(0) is False
    assert dec._eh_helper_ok(None) is False


# --- native fixtures: the real binary -----------------------------------

import il2cpp as I  # noqa: E402
from test_game_goldens import game_decompiler  # noqa: E402,F401

NEON_VADD_S8 = 106196
NEON_VADD_S8_VA = "0x182508610"
RETHROW_TEACHER = 64           # DependencyInjector.get_SystemProvider
RAISE_TEACHER = 100            # RuntimeMarshal.PtrToUtf8String
LOG_EXCEPTION_CALLER = 22316   # MeshGenerationDeferrer.Invoke


def _fresh_body(il, mi):
    """Lift `mi` as the first method a brand-new lifter ever sees."""
    dec = Decompiler(I.Lifter(il))
    m = il.meta.methods[mi]
    return dec.lift_method(m, il.meta.typedefs[m.declaring])


@pytest.mark.game
def test_helper_naming_is_order_independent(game_decompiler):
    il, _ = game_decompiler
    m = il.meta.methods[NEON_VADD_S8]
    assert hex(m.addr) == NEON_VADD_S8_VA
    alone = _fresh_body(il, NEON_VADD_S8)
    dec = Decompiler(I.Lifter(il))
    for teacher in (RETHROW_TEACHER, RAISE_TEACHER):
        t = il.meta.methods[teacher]
        dec.lift_method(t, il.meta.typedefs[t.declaring])
    after = dec.lift_method(m, il.meta.typedefs[m.declaring])
    assert after == alone


@pytest.mark.game
def test_pad_less_caller_renders_the_proven_helper_as_a_throw(game_decompiler):
    # SUPERSEDED EXPECTATION, kept deliberately. Under fix 90 alone this
    # method rendered `sub_180435670(...)`: vadd_s8 has no EH pad of its own,
    # so no local evidence proved the callee was a throw helper and the
    # honest rendering was the call. Fix 91 proves the helper pair once from
    # the whole binary, so a pad-less caller can name it -- that is the point
    # of the fix, and it matches the real source of these stubs, which is
    # `throw new NotImplementedException()`.
    #
    # What must still hold is that the throw is evidence-based rather than a
    # leaked register, and that it does not depend on lift order. The latter
    # is asserted by test_helper_naming_is_order_independent above; this test
    # lifts from a fresh lifter for the same reason.
    il, _ = game_decompiler
    body = _fresh_body(il, NEON_VADD_S8)
    assert not any("sub_180435670(" in ln for ln in body)
    thrown = [ln for ln in body if "throw " in ln]
    assert len(thrown) == 1
    # the thrown value must be the exception this method constructs
    obj = thrown[0].strip()[len("throw ") :].rstrip(";")
    # fix 125/126 re-pin: the allocation now folds to `new E()`.
    assert any(("%s = new System.NotImplementedException()" % obj) in ln for ln in body)
    assert any("NotImplementedException" in ln for ln in body)


@pytest.mark.game
def test_registered_method_is_not_renamed_to_a_throw(game_decompiler):
    il, _ = game_decompiler
    body = _fresh_body(il, LOG_EXCEPTION_CALLER)
    assert any("LogException(" in ln for ln in body)
    assert [ln for ln in body if ln.strip() == "throw;"] == []
