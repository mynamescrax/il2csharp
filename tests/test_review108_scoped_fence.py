"""Fix 108: scope-aware deadness for fence-called temps.

The fix-107 method-wide check treats every same-name mention as a
read, so one colliding scratch temp (sibling scopes re-declare: fix
97c) pins all of them. Lexical scoping proves more: a mention reads
the fence temp only while no intervening re-declaration shadows it.
"""

from test_review107_fence_calls import lift_pass, run

MB = "System.Threading.Thread.MemoryBarrier();"


def test_sibling_if_else_redecl():
    d, m = lift_pass()
    out = run(d, m, ["if (c1) {",
                     "object obj1 = sub_5000(a);",
                     "}",
                     "else {",
                     "object obj1 = sub_5000(b);",
                     "}",
                     "return 1;"])
    assert out == ["if (c1) {", MB, "}", "else {", MB, "}", "return 1;"]


def test_nested_shadow_with_inner_use():
    d, m = lift_pass()
    out = run(d, m, ["object obj1 = sub_5000(a);",
                     "if (c1) {",
                     "object obj1 = sub_5000(b);",
                     "use(obj1);",
                     "}",
                     "return 1;"])
    assert out == [MB,
                   "if (c1) {",
                   "object obj1 = sub_5000(b);",
                   "use(obj1);",
                   "}",
                   "return 1;"]


def test_use_between_decl_and_redecl_stays():
    d, m = lift_pass()
    out = run(d, m, ["object obj1 = sub_5000(a);",
                     "use(obj1);",
                     "object obj1 = sub_5000(b);",
                     "return 1;"])
    assert out[0] == "object obj1 = sub_5000(a);"
    assert out[2] == MB


def test_genuine_later_use_stays():
    d, m = lift_pass()
    out = run(d, m, ["object obj1 = sub_5000(a);",
                     "if (c1) {",
                     "use(obj1);",
                     "}",
                     "return 1;"])
    assert out[0] == "object obj1 = sub_5000(a);"


def test_nested_initializer_reading_outer_stays():
    # `= obj1` binds to the fence temp itself: a genuine read.
    d, m = lift_pass()
    out = run(d, m, ["object obj1 = sub_5000(a);",
                     "if (c1) {",
                     "object obj1 = obj1;",
                     "}",
                     "return 1;"])
    assert out[0] == "object obj1 = sub_5000(a);"
    assert out[2] == "object obj1 = obj1;"


def test_foreach_binder_shadows():
    d, m = lift_pass()
    out = run(d, m, ["object obj1 = sub_5000(a);",
                     "foreach (object obj1 in c1) {",
                     "use(obj1);",
                     "}",
                     "return 1;"])
    assert out[0] == MB
    assert out[1] == "foreach (object obj1 in c1) {"


def test_catch_binder_shadows():
    d, m = lift_pass()
    out = run(d, m, ["object obj1 = sub_5000(a);",
                     "try {",
                     "risky();",
                     "}",
                     "catch (Exception obj1) {",
                     "}",
                     "return 1;"])
    assert out[0] == MB


def test_use_after_block_close_stays():
    # Outer-scope mentions decline exactly as in fix 107.
    d, m = lift_pass()
    out = run(d, m, ["if (c1) {",
                     "object obj1 = sub_5000(a);",
                     "}",
                     "use(obj1);",
                     "return 1;"])
    assert out[1] == "object obj1 = sub_5000(a);"


def test_shadow_ends_at_block_close():
    # The nested binding is gone after `}`: this use reads the fence
    # temp, so the site stays.
    d, m = lift_pass()
    out = run(d, m, ["object obj1 = sub_5000(a);",
                     "if (c1) {",
                     "object obj1 = sub_5000(b);",
                     "}",
                     "use(obj1);",
                     "return 1;"])
    assert out[0] == "object obj1 = sub_5000(a);"


def test_keyword_headed_assign_is_no_rebind():
    # `return obj1 = ...` is an assignment, never a declaration.
    d, m = lift_pass()
    out = run(d, m, ["object obj1 = sub_5000(a);",
                     "return obj1;",
                     "return 1;"])
    assert out[0] == "object obj1 = sub_5000(a);"


def test_condition_read_stays():
    d, m = lift_pass()
    out = run(d, m, ["object obj1 = sub_5000(a);",
                     "if (obj1 == null) {",
                     "}",
                     "return 1;"])
    assert out[0] == "object obj1 = sub_5000(a);"


def test_unbalanced_depth_declines():
    d, m = lift_pass()
    out = run(d, m, ["object obj1 = sub_5000(a);",
                     "} // stray",
                     "use(obj1);",
                     "return 1;"])
    assert out[0] == "object obj1 = sub_5000(a);"


def test_outer_scope_redecl_ignored():
    # The later declaration lives outside the fence temp's block: a
    # different variable that neither reads nor rebinds it.
    d, m = lift_pass()
    out = run(d, m, ["if (c1) {",
                     "object obj1 = sub_5000(a);",
                     "}",
                     "object obj1 = sub_5000(b);",
                     "return 1;"])
    assert out == ["if (c1) {", MB, "}", MB, "return 1;"]


def test_depths_balanced():
    d, m = lift_pass()
    masks = [d._stub_mask_line(x) for x in
             ["if (c1) {", "object obj1 = sub_5000(a);", "}",
              "else {", "object obj1 = sub_5000(b);", "}", "return 1;"]]
    assert d._fence_line_depths(masks) == [0, 1, 0, 0, 1, 0, 0]
    assert d._fence_line_depths(["}", "x();"]) is None
