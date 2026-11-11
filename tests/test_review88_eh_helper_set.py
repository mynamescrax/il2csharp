"""Regression tests for fix 91: the program-wide proven throw-helper set.

Fix 90 established that helper naming must be per-method evidence. That was
correct but narrow: a method with no EH pad of its own can never name a
helper, so throw renderings collapsed and bare `sub_...` calls took their
place. Fix 91 proves the helpers once, from the whole binary.

The first draft of fix 91 trusted witness counts alone and published six
targets. Four of them were wrong, and my own probe caught it:

  * 0x180435420 is a `jmp` thunk onto il2cpp_codegen_initialize_runtime_metadata.
    181 methods taught it as "the rethrow helper", so every
    `il2cpp_codegen_initialize_runtime_metadata(typeof(...))` line in them was
    replaced by a bare `throw;`, which also cascaded into the following
    allocation and renumbered the locals.
  * 0x1804356a0 and 0x1804356b0 are raise_IndexOutOfRangeException and
    raise_NullReferenceException. Both really are throw helpers, but each
    raises one specific new exception and already carries a name derived from
    a string reference in its own wrapper chain, so flattening them to a bare
    `throw;` loses which exception is thrown.
  * 0x180002650 was taught by 45 pad-bearing methods, yet its body is
    `movsxd rdx,[rcx+10h]; ...; ret`. A throw helper never returns; the pad
    scan only reached it because the real helper ahead of it was skipped.

So the gate now also rejects plumbing the lifter can already name (directly
or through a thunk chain) and any routine with a reachable `ret`, and the set
keeps a target only where many independent methods agree on it by a decisive
role margin. Both new filters are properties of the callee alone, so they
screen the per-method evidence and the program-wide set alike.
"""
import types

import pytest

from il2cpp import Decompiler

# sub rsp,28h; add rsp,28h; ret; int3 padding -- ordinary code, it returns
RETURNING_CODE = b"\x48\x83\xec\x28\x48\x83\xc4\x28\xc3" + b"\xcc" * 8
# sub rsp,28h; call rel32; int3 padding -- the shape of a noreturn throw stub
NORETURN_CODE = b"\x48\x83\xec\x28\xe8\x00\x00\x00\x00" + b"\xcc" * 8


def _dec(code=None, exec_ok=True, reads=None, exports=None, **lifter):
    """A Decompiler over a stub lifter, optionally backed by crafted bytes."""
    def read(va, n):
        if reads is not None:
            reads.append(va)
        return (code or b"")[:n]

    il = types.SimpleNamespace(
        addr_to_method={},
        addr_candidates={},
        bin=types.SimpleNamespace(
            exports=exports or {},
            is_exec_va=lambda va: exec_ok,
            read=read,
        ),
    )
    return Decompiler(types.SimpleNamespace(il=il, **lifter))


def test_named_runtime_plumbing_is_rejected():
    dec = _dec(rt_names={0x180435660: "il2cpp_object_new"})
    assert dec._eh_helper_ok(0x180435660) is False


def test_discovered_runtime_helper_slots_are_rejected():
    dec = _dec(
        rt_init_meta=0x180435400,
        rt_alloc=0x180435660,
        rt_value_box=0x180434650,
        rt_sqrt=0x1804CE6D8,
        rt_arrnew={0x1804346F0},
        rt_wbarrier={0x180434670, 0x180435700},
    )
    for va in (0x180435400, 0x180435660, 0x180434650, 0x1804CE6D8,
               0x1804346F0, 0x180434670, 0x180435700):
        assert dec._eh_helper_ok(va) is False, hex(va)


def test_thunk_resolved_plumbing_is_rejected():
    # the census called 0x180435420 "clean" because the name map holds only
    # the inner address it jumps to, so membership must be tested after
    # resolving the chain
    dec = _dec(
        rt_names={0x180490FB0: "il2cpp_codegen_initialize_runtime_metadata"},
        _thunk_final=lambda va: 0x180490FB0 if va == 0x180435420 else va,
    )
    assert dec._eh_helper_ok(0x180435420) is False


def test_resolving_through_a_thunk_is_not_itself_disqualifying():
    # _thunk_final also walks `sub rsp,N; call T` noreturn forwarders, and
    # genuine throw helpers are shaped exactly like that, so the mere fact
    # that a candidate resolves somewhere must not reject it
    dec = _dec(
        code=NORETURN_CODE,
        rt_names={0x180490FB0: "il2cpp_codegen_initialize_runtime_metadata"},
        _thunk_final=lambda va: 0x18044FD00,
    )
    assert dec._eh_helper_ok(0x180435740) is True


def test_returning_routine_is_rejected():
    dec = _dec(code=RETURNING_CODE)
    assert dec._eh_helper_returns(0x180002650) is True
    assert dec._eh_helper_ok(0x180002650) is False


def test_noreturn_stub_is_accepted():
    dec = _dec(code=NORETURN_CODE)
    assert dec._eh_helper_returns(0x180435740) is False
    assert dec._eh_helper_ok(0x180435740) is True


def test_returns_probe_is_memoised():
    # the pre-pass asks about the same handful of targets thousands of
    # times, so each VA must be decoded once
    reads = []
    dec = _dec(code=RETURNING_CODE, reads=reads)
    assert dec._eh_helper_returns(0x180002650) is True
    assert dec._eh_helper_returns(0x180002650) is True
    assert reads == [0x180002650]


def test_unreadable_target_keeps_the_previous_behaviour():
    # only positive evidence of a `ret` rejects a candidate
    dec = _dec(code=b"", exec_ok=False)
    assert dec._eh_helper_returns(0x180435740) is False
    assert dec._eh_helper_ok(0x180435740) is True


def test_a_prebuilt_set_is_never_rebuilt():
    # an empty dict means "already proven", which is also how the verify
    # probe reproduces fix-90-only behaviour without editing the source
    dec = _dec()
    dec.L.eh_helper_set = {}
    dec._ensure_eh_helper_set()
    assert dec.L.eh_helper_set == {}


def test_missing_metadata_publishes_an_empty_set():
    dec = _dec()
    dec._ensure_eh_helper_set()
    assert dec.L.eh_helper_set == {}


def test_acceptance_rule_stays_decisive():
    # measured post-filter distribution over all 4,526 pad-bearing methods:
    # 3403, 183, then 13, 13, 8, 6, 3. The first draft's threshold of 10 sat
    # inside that low cluster, where 0x1804346b0 split 12 rethrow / 13 raise
    # -- a coin flip that decides `throw;` against `throw x;`.
    assert Decompiler._EH_HELPER_MIN_WITNESSES >= 25
    assert Decompiler._EH_HELPER_MIN_DOMINANCE >= 4


# --- native fixtures: the real binary -----------------------------------

import il2cpp as I  # noqa: E402
from test_game_goldens import game_decompiler  # noqa: E402,F401

RETHROW_HELPER = 0x180435740          # 3403 rethrow witnesses vs 126 raise
RAISE_HELPER = 0x180435670            # 183 raise witnesses vs 25 rethrow
METADATA_INIT_THUNK = 0x180435420     # jmp -> il2cpp_codegen_initialize_...
RAISE_IOOR = 0x1804356A0              # raise_IndexOutOfRangeException
RAISE_NRE = 0x1804356B0               # raise_NullReferenceException
RETURNING_HIGH_WITNESS = 0x180002650  # 45 methods taught it; it returns
TRACE_EVENT_TYPE = 77946              # GetTraceEventType, no EH pads


def _fresh(il):
    return Decompiler(I.Lifter(il))


def _body(dec, il, mi):
    m = il.meta.methods[mi]
    return dec.lift_method(m, il.meta.typedefs[m.declaring])


@pytest.mark.game
def test_proven_set_is_the_decisively_witnessed_pair(game_decompiler):
    il, _ = game_decompiler
    dec = _fresh(il)
    _body(dec, il, TRACE_EVENT_TYPE)   # any lift builds the set once
    assert dec.L.eh_helper_set == {
        RETHROW_HELPER: "rethrow_va",
        RAISE_HELPER: "raise_va",
    }


@pytest.mark.game
def test_runtime_plumbing_is_rejected_on_the_real_binary(game_decompiler):
    _, dec = game_decompiler
    for va in (METADATA_INIT_THUNK, RAISE_IOOR, RAISE_NRE,
               RETURNING_HIGH_WITNESS):
        assert dec._eh_helper_ok(va) is False, hex(va)
    for va in (RETHROW_HELPER, RAISE_HELPER):
        assert dec._eh_helper_ok(va) is True, hex(va)


@pytest.mark.game
def test_returning_target_is_detected_from_its_own_bytes(game_decompiler):
    _, dec = game_decompiler
    assert dec._eh_helper_returns(RETURNING_HIGH_WITNESS) is True
    assert dec._eh_helper_returns(RETHROW_HELPER) is False


@pytest.mark.game
def test_named_raisers_keep_their_evidence_derived_names(game_decompiler):
    _, dec = game_decompiler
    names = dec.L.rt_names
    assert (names.get(RAISE_IOOR) or "").startswith("raise_")
    assert (names.get(RAISE_NRE) or "").startswith("raise_")


@pytest.mark.game
def test_metadata_init_is_not_flattened_to_a_throw(game_decompiler):
    # This method has no EH pads, so only the program-wide set can render a
    # throw in it at all. The first draft printed three bare `throw;` here,
    # each one eating an il2cpp_codegen_initialize_runtime_metadata call,
    # while the one genuine win is the raise helper at the end.
    il, _ = game_decompiler
    dec = _fresh(il)
    body = _body(dec, il, TRACE_EVENT_TYPE)
    # fix 125/126 re-pin (reviewed): the init statement itself is no longer
    # emitted, so the guard is now that nothing became a bare `throw;` and the
    # one genuine throw keeps its concrete exception.
    assert [ln for ln in body if ln.strip() == "throw;"] == []
    assert any(ln.strip().startswith("throw ") for ln in body)
    assert any("new System.ArgumentOutOfRangeException(\"level\")" in ln for ln in body)
