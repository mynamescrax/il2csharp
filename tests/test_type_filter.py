from types import SimpleNamespace as NS

from il2cpp import Emitter


def emitter(needle):
    root = NS(index=0, name="Outer", namespace="Demo", nested_start=0, nested_count=1)
    child = NS(index=1, name="Inner", namespace="", nested_start=1, nested_count=1)
    leaf = NS(index=2, name="Leaf", namespace="", nested_start=2, nested_count=0)
    unrelated = NS(index=3, name="Other", namespace="Demo", nested_start=2, nested_count=0)
    em = Emitter.__new__(Emitter)
    em.type_filter = needle.casefold() if needle else None
    em.meta = NS(typedefs=[root, child, leaf, unrelated], nested_types=[1, 2])
    return em, root, unrelated


def test_default_keeps_all_types():
    em, root, unrelated = emitter(None)
    assert em._matches_type_filter(root)
    assert em._matches_type_filter(unrelated)


def test_type_filter_is_case_insensitive():
    em, root, unrelated = emitter("dEmO.oUtEr")
    assert em._matches_type_filter(root)
    assert not em._matches_type_filter(unrelated)


def test_nested_full_name_selects_its_owner():
    em, root, unrelated = emitter("Demo.Outer.Inner.Leaf")
    assert em._matches_type_filter(root)
    assert not em._matches_type_filter(unrelated)


def test_namespace_substring_matches():
    em, root, unrelated = emitter("demo.")
    assert em._matches_type_filter(root)
    assert em._matches_type_filter(unrelated)


def test_missing_type_matches_nothing():
    em, root, unrelated = emitter("NoSuchType")
    assert not em._matches_type_filter(root)
    assert not em._matches_type_filter(unrelated)


def test_nested_cycle_cannot_hang_filter():
    em, root, _ = emitter("NoSuchType")
    em.meta.nested_types[1] = 0
    assert not em._matches_type_filter(root)