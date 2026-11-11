"""Fix 96: `_value_cse` must never fold `new` allocations.

A `new` mints a fresh object identity on every execution -- it is not a
pure load. But parameterless `new T()` slipped past `_IMPURE`
(`[\w\]\)]\s*\(`: `>` is not in its lead class and `new ` breaks
word-paren adjacency), and `new T[n]` has no parens at all, so two
identical allocations in one block were aliased into one object.
AudioVolumeSliders.Start's two UnityAction<float> listeners folded into
a single shared delegate.
"""
from il2cpp import Decompiler


def cse(lines):
    return Decompiler.__new__(Decompiler)._value_cse(list(lines))


def test_parameterless_new_allocations_never_fold():
    lines = [
        "UnityAction<float> obj1 = new UnityAction<float>();",
        "UnityAction<float> obj2 = new UnityAction<float>();",
        "obj10.AddListener(obj1);",
        "obj12.AddListener(obj2);",
    ]
    assert cse(lines) == lines


def test_new_with_arguments_never_folds():
    lines = [
        "List<int> obj1 = new List<int>(4);",
        "List<int> obj2 = new List<int>(4);",
        "obj1.Add(1);",
        "obj2.Add(2);",
    ]
    assert cse(lines) == lines


def test_new_array_never_folds():
    lines = [
        "string[] obj1 = new string[4];",
        "string[] obj2 = new string[4];",
        "obj1[0] = text1;",
        "obj2[0] = text2;",
    ]
    assert cse(lines) == lines


def test_pure_member_loads_still_fold():
    lines = [
        "InputActionAsset obj1 = this.playerInput.actions;",
        "InputActionAsset obj2 = this.playerInput.actions;",
        "obj2.Do();",
    ]
    assert cse(lines) == [
        "InputActionAsset obj1 = this.playerInput.actions;",
        "obj1.Do();",
    ]
