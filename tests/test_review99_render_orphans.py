"""Fix 99: drop render-orphaned dead pure loads.

`_render` drops empty pure-cond `if`s (e.g. an emptied class-init guard
`if (!(k.initialized != 0)) { }`), orphaning the pure klass loads they
alone read. No DCE ran after render, so `System.Type objN = typeof(X)`
survived dead into output (12.7k dead typeof decls tree-wide) and was
renamed `Type typeN`. `_structure` now re-runs the proven
`_drop_dead_locals` on the rendered lines: same predicate, later timing.

Ground truth: ActorCOMTransform.Update (mi 23898) ships
`Type type1 = typeof(Object);` whose only reader is the emptied guard
`_render` removes; KerningTable.AddKerningPair (mi 95457) is unaffected.
"""

from il2cpp import Decompiler


def ddl(lines):
    return Decompiler.__new__(Decompiler)._drop_dead_locals(list(lines))


def test_dead_typeof_load_drops():
    assert ddl([
        "    System.Type obj3 = typeof(UnityEngine.Object);",
        "    UnityEngine.Vector3 obj4 = default;",
        "    Foo(obj4);",
    ]) == [
        "    UnityEngine.Vector3 obj4 = default;",
        "    Foo(obj4);",
    ]


def test_live_typeof_load_survives_guard():
    lines = [
        "    System.Type obj3 = typeof(UnityEngine.Object);",
        "    if (!(obj3.initialized != 0))",
        "    {",
        "    }",
    ]
    assert ddl(lines) == lines


def test_dead_impure_call_stays():
    lines = ["    object obj1 = Foo();"]
    assert ddl(lines) == lines


def test_dead_init_call_binding_stays():
    lines = [
        "    object obj15 = "
        "il2cpp_codegen_initialize_runtime_metadata(typeof(AsyncTaskMethodBuilder));",
    ]
    assert ddl(lines) == lines


def test_live_load_read_later_survives():
    lines = [
        "    System.Type obj3 = typeof(Vector3);",
        "    Foo(obj3);",
    ]
    assert ddl(lines) == lines


def test_dead_getclass_load_drops():
    assert ddl([
        "    System.Type obj3 = obj1.getClass();",
        "    return;",
    ]) == ["    return;"]


def test_dead_typeof_member_chain_drops():
    assert ddl([
        "    object obj5 = typeof(X).__static_fields;",
        "    return;",
    ]) == ["    return;"]


def test_dead_pure_copy_drops():
    assert ddl([
        "    object obj9 = obj4;",
        "    return;",
    ]) == ["    return;"]


def test_dead_const_store_drops():
    assert ddl([
        "    int num1 = 0;",
        "    return;",
    ]) == ["    return;"]


def test_render_orphan_end_to_end():
    # the exact post-`_render` snapshot shape for mi 23898: the guard is
    # gone, the load stands alone and unread.
    assert ddl([
        "System.Type obj3 = typeof(UnityEngine.Object);",
        "UnityEngine.Vector3 obj4 = default;",
        "if (UnityEngine.Object.op_Inequality(this.actor, 0))",
        "{",
        "    Foo(obj4);",
        "}",
        "return;",
    ]) == [
        "UnityEngine.Vector3 obj4 = default;",
        "if (UnityEngine.Object.op_Inequality(this.actor, 0))",
        "{",
        "    Foo(obj4);",
        "}",
        "return;",
    ]
