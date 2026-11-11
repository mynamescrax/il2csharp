"""Fix 107: proved fence-thunk calls render `Thread.MemoryBarrier()`.

The thunk (and the fence body itself) provably reads nothing and
returns nothing: exactly `lock or dword ptr [rsp],0; ret`. Only
positions that need no value rewrite (bare statements, void tails,
dead-temp decls) with side-effect-free arguments. Ground truth:
`Thread.MemoryBarrier`'s own body is one call to the fence helper.
"""

from types import SimpleNamespace as NS

from iced_x86 import Decoder, DecoderOptions

from il2cpp import Decompiler, Expr, Lifter


def state_stub(code_at=None, cands=None, exports=None, exec_ok=True):
    lift = Lifter.__new__(Lifter)
    lift.bin = NS(is_exec_va=lambda va: exec_ok and va in (code_at or {}),
                  read=lambda va, n: (code_at or {}).get(va, b"")[:n],
                  exports=exports or {})
    lift.il = NS(addr_candidates=cands or {})
    return lift

FENCE = 0x6000
THUNK = 0x5000
PLAIN = 0x5100

FENCE_CODE = bytes((0xF0, 0x83, 0x0C, 0x24, 0x00, 0xC3))


def thunk_to_fence():
    # E9 rel32 from THUNK to FENCE
    import struct
    return bytes((0xE9,)) + struct.pack("<i", FENCE - (THUNK + 5))


def make_lift(code_at=None):
    """Lifter stub with a canned binary (VA -> bytes)."""
    lift = Decompiler.__new__(Decompiler)
    lift.L = NS()
    lift.L.bin = NS(
        is_exec_va=lambda va: va in (code_at or {}),
        read=lambda va, n: (code_at or {}).get(va, b"")[:n],
        exports={},
    )
    lift.L.il = NS(addr_candidates={})
    lift.L.meta = NS(methods=[], typedefs=[])
    lift._var_types = {}
    return lift


def dec_with(code_at):
    d = make_lift(code_at)
    return d


THUNK_BIN = {THUNK: thunk_to_fence(), FENCE: FENCE_CODE}
FENCE_BIN = {FENCE: FENCE_CODE}


def fence_target_of(code_at):
    def _ft(va):
        if va == FENCE:
            return FENCE
        if va == THUNK and code_at.get(THUNK) == thunk_to_fence():
            return FENCE
        return None
    return _ft


# --- structural proof ----------------------------------------------------------


def test_fence_body_proved():
    s = state_stub({FENCE: FENCE_CODE})
    assert s._is_fence_body(FENCE) is True
    # memoized second call
    assert s._is_fence_body(FENCE) is True
    # imm32-encoded twin (0x81) proves identically
    s2 = state_stub({FENCE: bytes((0xF0, 0x81, 0x0C, 0x24, 0x00, 0x00, 0x00, 0x00, 0xC3))})
    assert s2._is_fence_body(FENCE) is True


def test_fence_body_declines():
    def mk(code, cands=None, exports=None, exec_ok=True):
        blobs = {FENCE: code}
        return state_stub(blobs, cands, exports, exec_ok)

    # nonzero immediate would corrupt the return-address slot
    assert mk(bytes((0xF0, 0x83, 0x0C, 0x24, 0x01, 0xC3)))._is_fence_body(FENCE) is False
    # wrong base
    assert mk(bytes((0xF0, 0x83, 0x03, 0xC3, 0x90, 0x90)))._is_fence_body(FENCE) is False
    # displacement
    assert mk(bytes((0xF0, 0x83, 0x4C, 0x24, 0x08, 0x00, 0xC3)))._is_fence_body(FENCE) is False
    # no lock prefix
    assert mk(bytes((0x83, 0x0C, 0x24, 0x00, 0xC3, 0x90)))._is_fence_body(FENCE) is False
    # call instead of ret
    assert mk(bytes((0xF0, 0x83, 0x0C, 0x24, 0x00, 0xE8)))._is_fence_body(FENCE) is False
    # qword width
    assert mk(bytes((0xF0, 0x49, 0x83, 0x0C, 0x24, 0x00, 0xC3)))._is_fence_body(FENCE) is False
    # registered / exported / non-exec / unreadable
    assert mk(FENCE_CODE, cands={FENCE: [("method", 1)]})._is_fence_body(FENCE) is False
    assert mk(FENCE_CODE, exports={FENCE: "x"})._is_fence_body(FENCE) is False
    assert mk(FENCE_CODE, exec_ok=False)._is_fence_body(FENCE) is False
    assert mk(b"", exec_ok=True)._is_fence_body(FENCE) is False
    assert mk(FENCE_CODE)._is_fence_body(None) is False


def test_fence_target_follow():
    s = state_stub(dict(THUNK_BIN))
    assert s._fence_target(THUNK) == FENCE
    assert s._fence_target(FENCE) == FENCE
    assert s._fence_target(PLAIN) is None
    assert s._fence_target(None) is None


# --- argument triviality ---------------------------------------------------------


def test_trivial_args():
    d = dec_with({})
    ok = d._fence_trivial_arg
    assert ok("obj34") and ok("this") and ok("this.x") and ok("value")
    assert ok("s_abc") and ok("0") and ok("5") and ok("0f")
    assert ok("1.5f") and ok("0x10") and ok("-3") and ok("5u")
    assert ok("true") and ok("false") and ok("null") and ok("default")
    assert ok("typeof(X)") and ok('"str"') and ok("'c'")
    bad = d._fence_trivial_arg
    assert not bad("&x") and not bad("x + y") and not bad("Foo()")
    assert not bad("new Foo()") and not bad("x++") and not bad("x = y")
    assert not bad("(int)x") and not bad("a ? b : c") and not bad("")
    assert not bad(None) and not bad("((byte*)x)[0]") and not bad("x[0]")


def test_args_clean():
    d = dec_with({})
    assert d._fence_args_clean("sub_1(a, b)", "sub_1(a, b)", 5, 10) is True
    assert d._fence_args_clean("sub_1()", "sub_1()", 5, 6) is True
    assert d._fence_args_clean("sub_1(a, Foo())", "sub_1(a, Foo())", 5, 14) is False
    assert d._fence_args_clean("sub_1(typeof(D<K, V>))",
                               "sub_1(typeof(D<K, V>))", 5, 21) is True


# --- pass shapes -------------------------------------------------------------------


def lift_pass(code_at=None, ret_void=True, name="M", td=("T", "")):
    d = dec_with(code_at or THUNK_BIN)
    d.L._fence_target = fence_target_of(code_at or THUNK_BIN)
    m = NS(return_type=0 if ret_void else 1, name=name, declaring=0,
           is_static=True)
    d.L.meta = NS(
        typedefs=[NS(name=td[0], namespace=td[1])],
        method_params=lambda m: [],
    )
    d.L.il.types = [(0, 0x01 << 16), (0, 0x08 << 16)]
    d.L.il.type_name = lambda t: "void" if t[1] == 0x01 << 16 else "int"
    return d, m


def run(d, m, lines):
    return d._fence_void_calls(lines, m)


def test_decl_dead_names():
    d, m = lift_pass()
    out = run(d, m, ["object obj1 = sub_5000(this);",
                     "return obj2;"])
    assert out == ["System.Threading.Thread.MemoryBarrier();",
                   "return obj2;"]


def test_decl_live_keeps_stub():
    d, m = lift_pass()
    out = run(d, m, ["object obj1 = sub_5000(this);",
                     "return obj1;"])
    assert out[0] == "object obj1 = sub_5000(this);"


def test_decl_effectful_args_keep_stub():
    d, m = lift_pass()
    out = run(d, m, ["object obj1 = sub_5000(this, Foo());",
                     "return 1;"])
    assert out[0] == "object obj1 = sub_5000(this, Foo());"
    out = run(d, m, ["object obj1 = sub_5000(&t1);",
                     "return 1;"])
    assert out[0] == "object obj1 = sub_5000(&t1);"


def test_bare_and_tailret():
    d, m = lift_pass()
    assert run(d, m, ["sub_5000(a, b);"]) == \
        ["System.Threading.Thread.MemoryBarrier();"]
    assert run(d, m, ["sub_5000(a); return;"]) == \
        ["System.Threading.Thread.MemoryBarrier();", "return;"]
    d2, m2 = lift_pass(ret_void=False)
    assert run(d2, m2, ["sub_5000(a); return;"]) == \
        ["sub_5000(a); return;"]


def test_nonvoid_shapes_untouched():
    d, m = lift_pass(ret_void=False)
    assert run(d, m, ["return sub_5000(a);"]) == ["return sub_5000(a);"]
    assert run(d, m, ["if (sub_5000(a))"]) == ["if (sub_5000(a))"]
    assert run(d, m, ["int x = sub_5000(a) + 1;"]) == \
        ["int x = sub_5000(a) + 1;"]
    assert run(d, m, ["object o = sub_5100(a);",
                      "return o;"])[0] == "object o = sub_5100(a);"


def test_self_recursion_guard():
    d, m = lift_pass(name="MemoryBarrier", td=("Thread", "System.Threading"))
    out = run(d, m, ["object obj1 = sub_5000(this);",
                     "return;"])
    assert out[0] == "object obj1 = sub_5000(this);"
    d2, m2 = lift_pass(name="MemoryBarrier", td=("Thread", "Other"))
    out = run(d2, m2, ["object obj1 = sub_5000(this);",
                       "return;"])
    assert out[0] == "System.Threading.Thread.MemoryBarrier();"


def test_comment_tail_kept():
    d, m = lift_pass()
    out = run(d, m, ["object obj1 = sub_5000(a); // note",
                     "return 1;"])
    assert out == ["System.Threading.Thread.MemoryBarrier(); // note",
                   "return 1;"]


def test_same_scope_dup_decls_both_rewrite():
    # fix 108: neither temp is read, so both fence decls rewrite even
    # though the name collides. (True shadowing across sibling scopes
    # is covered in test_review108_scoped_fence.py.)
    d, m = lift_pass()
    out = run(d, m, ["object obj1 = sub_5000(a);",
                     "object obj1 = sub_5000(b);",
                     "return 1;"])
    assert out == ["System.Threading.Thread.MemoryBarrier();",
                   "System.Threading.Thread.MemoryBarrier();",
                   "return 1;"]
