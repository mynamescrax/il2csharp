"""Fix 109: single-level `typeof(X).Member` fence args are droppable.

A static access with no dereference, no calls, no indexers: strictly
fewer load effects than the already-accepted `obj.f` chains (which can
NRE). Checked on masked text so quoted text can never shape-match.
"""

from test_review107_fence_calls import lift_pass, run

from il2cpp.dec.highlevel import _HighLevelMixin as H

MB = "System.Threading.Thread.MemoryBarrier();"


def test_bare_typeof_whole_string():
    ok = H._fence_bare_typeof
    assert ok("typeof(Foo)")
    assert ok("typeof (Foo)")
    assert ok("typeof(D<K, V>)")
    assert not ok("typeof(Foo).Get()")
    assert not ok("typeof(Foo).Bar")
    assert not ok("xtypeof(Foo)")
    assert not ok("typeof(Foo")
    assert not ok("")
    assert not ok(None)
    # legacy hole: the old prefix/suffix spelling took calls as bare.
    assert H._fence_trivial_arg("typeof(Foo)", None)
    assert not H._fence_trivial_arg("typeof(Foo).Get()", "typeof(Foo).Get()")


def test_typeof_member_shapes():
    ok = H._fence_typeof_member
    assert ok("typeof(Foo).Bar")
    assert ok("typeof (Foo).Bar")
    assert ok("typeof(Foo<T>).Bar")
    assert ok("typeof(A.B.C).D")
    assert ok("typeof(D<K, V>).X")
    assert not ok("typeof(Foo)")
    assert not ok("typeof(Foo).Bar.Baz")
    assert not ok("typeof(Foo).Bar()")
    assert not ok("typeof(Foo).Bar[0]")
    assert not ok("typeof(Foo).bar + 1")
    assert not ok("mytypeof(Foo).Bar")
    assert not ok("typeof(Foo.Bar")
    assert not ok("typeof(Foo).")
    assert not ok("typeof().")
    assert not ok("")
    assert not ok(None)


def test_trivial_arg_wires_masked():
    assert H._fence_trivial_arg("typeof(Foo).Bar", "typeof(Foo).Bar")
    assert not H._fence_trivial_arg("typeof(Foo).Bar.Baz",
                                    "typeof(Foo).Bar.Baz")
    # raw shape right but masked shows a string: not a member access.
    assert not H._fence_trivial_arg("typeof(Foo).Bar", '"typeof(Foo).Bar"')
    # legacy single-arg behavior unchanged without masked text.
    assert not H._fence_trivial_arg("typeof(Foo).Bar")


def test_end_to_end_rewrite():
    d, m = lift_pass()
    out = run(d, m, ["object obj1 = sub_5000(typeof(InternalLogStreams).LogDebug);",
                     "return 1;"])
    assert out == [MB, "return 1;"]
    d, m = lift_pass()
    out = run(d, m, ["object obj1 = sub_5000(typeof(DateTimeFormatInfo).s_invariantInfo, obj42);",
                     "return 1;"])
    assert out == [MB, "return 1;"]


def test_live_temp_still_stays():
    d, m = lift_pass()
    out = run(d, m, ["object obj1 = sub_5000(typeof(Foo).Bar);",
                     "return obj1;"])
    assert out[0] == "object obj1 = sub_5000(typeof(Foo).Bar);"


def test_multilevel_and_calls_stay():
    d, m = lift_pass()
    out = run(d, m, ["object obj1 = sub_5000(typeof(Foo).Bar.Baz);",
                     "return 1;"])
    assert out[0] == "object obj1 = sub_5000(typeof(Foo).Bar.Baz);"
    d, m = lift_pass()
    out = run(d, m, ["object obj1 = sub_5000(typeof(Foo).Get(), obj2);",
                     "return 1;"])
    assert out[0] == "object obj1 = sub_5000(typeof(Foo).Get(), obj2);"
