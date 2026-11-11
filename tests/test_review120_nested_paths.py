"""Fix 120: nested owner paths resolve through nested_types.

The typedef `declaring` field is -1 for top-level rows and out of range
for every nested row, so `typedef_full`'s owner walk never fired and nested
references rendered bare (`CallbackContext` for
`InputAction.CallbackContext`). Owners now resolve via the forward
`nested_types` table inverted once per instance.
"""
from types import SimpleNamespace as NS

from il2cpp.runtime.types import _TypesMixin


def _meta(typedefs, nested):
    return NS(typedefs=list(typedefs), nested_types=list(nested))


def _td(index, name, ns="", nested_start=-1, nested_count=0, generic_container=-1):
    return NS(index=index, name=name, namespace=ns,
              nested_start=nested_start, nested_count=nested_count,
              generic_container=generic_container)


def _mix(meta):
    m = _TypesMixin.__new__(_TypesMixin)
    m.meta = meta
    return m


def test_nested_path_uses_owner():
    owner = _td(0, "InputAction", ns="UnityEngine.InputSystem",
                nested_start=0, nested_count=1)
    inner = _td(1, "CallbackContext", ns="")
    meta = _meta([owner, inner], [1])
    m = _mix(meta)
    assert m.typedef_full(1) == \
        "UnityEngine.InputSystem.InputAction.CallbackContext"
    assert m.typedef_full(0) == "UnityEngine.InputSystem.InputAction"


def test_nested_path_takes_outermost_namespace():
    owner = _td(0, "HID", ns="UnityEngine.InputSystem.HID",
                nested_start=0, nested_count=1)
    inner = _td(1, "HIDDeviceDescriptor", ns="")
    meta = _meta([owner, inner], [1])
    m = _mix(meta)
    assert m.typedef_full(1) == \
        "UnityEngine.InputSystem.HID.HID.HIDDeviceDescriptor"


def test_top_level_unchanged_and_unknown_safe():
    meta = _meta([_td(0, "Foo", ns="A.B")], [])
    m = _mix(meta)
    assert m.typedef_full(0) == "A.B.Foo"
    assert m.typedef_full(99) == "?"
    assert m.typedef_full(-1) == "?"


def test_blob_rewrite_survives_owner_prefix():
    from il2cpp.runtime.types import _TypesMixin
    owner = _td(0, "<PrivateImplementationDetails>", ns="",
                nested_start=0, nested_count=1)
    blob = _td(777001, "__StaticArrayInitTypeSize=18380", ns="")
    typedefs = [owner] + [None] * 777000 + [blob]
    meta = NS(typedefs=typedefs, nested_types=[777001])
    m = _TypesMixin.__new__(_TypesMixin)
    m.meta = meta
    m.PRIM = {}
    # valuetype branch, distinctive tuple to avoid the shared name cache
    nm = m.type_name((777001, 0x11 << 16))
    assert "=" not in nm, nm
    assert nm.endswith("__StaticArrayInitTypeSize_18380"), nm
    assert nm.startswith("<PrivateImplementationDetails>."), nm


def test_cache_is_per_instance():
    m1 = _mix(_meta([_td(0, "A", nested_start=0, nested_count=1),
                     _td(1, "Inner", ns="")], [1]))
    m2 = _mix(_meta([_td(0, "B", nested_start=0, nested_count=1),
                     _td(1, "Inner", ns="")], [1]))
    assert m1.typedef_full(1) == "A.Inner"
    assert m2.typedef_full(1) == "B.Inner"
    assert m1.__dict__["_nested_owner_cache"] is not m2.__dict__["_nested_owner_cache"]


def test_emitter_qualifier_index_uses_owner_map():
    from test_review113_type_decls import make_emitter
    e = make_emitter(typedefs=[None] * 3)
    e.meta.typedefs[0] = _td(0, "Outer", ns="N", nested_start=0, nested_count=1)
    e.meta.typedefs[1] = _td(1, "IFoo`1", ns="N")
    e.meta.typedefs[2] = _td(2, "Inner`1", ns="")
    e.meta.nested_types = [2]
    e.il._nested_owner = lambda ti: {2: 0}.get(ti)
    assert e._arity_qualifier("N.Outer.Inner<object>") == \
        "N.Outer.Inner_1<object>"


class _DistMixin:
    pass


def _dist_mix():
    from il2cpp.runtime.types import _TypesMixin
    m = _TypesMixin.__new__(_TypesMixin)
    owner = _td(0, "List`1", ns="System.Collections.Generic")
    inner = _td(1, "Enumerator", ns="")
    m.meta = NS(typedefs=[owner, inner], nested_types=[])
    m.__dict__["_nested_owner_cache"] = {1: 0}
    return m


def test_distribute_owner_args():
    m = _dist_mix()
    assert m._distribute_nested_args(
        1, "System.Collections.Generic.List_1.Enumerator", ["T"]) == \
        "System.Collections.Generic.List_1<T>.Enumerator"


def test_distribute_both_generic():
    m = _dist_mix()
    owner2 = _td(0, "Outer`1", ns="N")
    inner2 = _td(2, "Inner`1", ns="")
    m.meta = NS(typedefs=[owner2, None, inner2], nested_types=[])
    m.__dict__["_nested_owner_cache"] = {2: 0}
    assert m._distribute_nested_args(2, "N.Outer_1.Inner_1", ["A", "B"]) == \
        "N.Outer_1<A>.Inner_1<B>"


def test_distribute_declines_on_mismatch():
    m = _dist_mix()
    assert m._distribute_nested_args(
        1, "System.Collections.Generic.List_1.Enumerator", ["A", "B"]) is None
    assert m._distribute_nested_args(
        0, "System.Collections.Generic.List_1", ["T"]) is None


def _mirror_meta():
    # Callback<T> with mirror-nested DispatchDelegate (own container copies T)
    owner = NS(index=0, name="Callback`1", namespace="S", declaring=-1,
               nested_start=0, nested_count=1, generic_container=10)
    inner = NS(index=1, name="DispatchDelegate", namespace="",
               declaring=999, nested_start=-1, nested_count=0,
               generic_container=11)
    gc = {10: (0, 1, 0, 100), 11: (1, 1, 0, 101)}
    gp = [None] * 100 + [(10, "T", 0, 0, 0, 0), (11, "T", 0, 0, 0, 0)]
    meta = NS(typedefs=[owner, inner], nested_types=[1],
              generic_containers=gc, generic_parameters=gp)
    return meta


def test_mirror_nested_takes_no_args():
    from il2cpp.runtime.types import _TypesMixin
    m = _TypesMixin.__new__(_TypesMixin)
    m.meta = _mirror_meta()
    assert m._nested_own_params(m.meta.typedefs[1]) == []
    assert m._nested_own_params(m.meta.typedefs[0]) is None
    assert m._typedef_arity(m.meta.typedefs[1]) == 0


def test_independent_nested_keeps_args():
    from il2cpp.runtime.types import _TypesMixin
    m = _TypesMixin.__new__(_TypesMixin)
    m.meta = _mirror_meta()
    owner = m.meta.typedefs[0]
    inner = NS(index=1, name="Other`1", namespace="", declaring=999,
               nested_start=-1, nested_count=0, generic_container=12)
    m.meta.generic_containers[12] = (1, 1, 0, 102)
    m.meta.generic_parameters.extend([None] * (103 - len(m.meta.generic_parameters)))
    m.meta.generic_parameters[102] = (12, "U", 0, 0, 0, 0)
    m.meta.typedefs[1] = inner
    assert m._nested_own_params(inner) == ["U"]
    assert m._typedef_arity(inner) == 1


def test_prefix_mismatch_declines():
    from il2cpp.runtime.types import _TypesMixin
    m = _TypesMixin.__new__(_TypesMixin)
    m.meta = _mirror_meta()
    inner = NS(index=1, name="Sub`1", namespace="", declaring=999,
               nested_start=-1, nested_count=0, generic_container=12)
    m.meta.generic_containers[12] = (1, 2, 0, 102)
    m.meta.generic_parameters.extend([None] * (104 - len(m.meta.generic_parameters)))
    m.meta.generic_parameters[102] = (12, "Q", 0, 0, 0, 0)
    m.meta.generic_parameters[103] = (12, "K", 0, 0, 0, 0)
    m.meta.typedefs[1] = inner
    assert m._nested_own_params(inner) is None


def test_partial_mirror_declares_own_suffix():
    from il2cpp.runtime.types import _TypesMixin
    m = _TypesMixin.__new__(_TypesMixin)
    m.meta = _mirror_meta()
    inner = NS(index=1, name="Sub`1", namespace="", declaring=999,
               nested_start=-1, nested_count=0, generic_container=12)
    m.meta.generic_containers[12] = (1, 2, 0, 102)
    m.meta.generic_parameters.extend([None] * (104 - len(m.meta.generic_parameters)))
    m.meta.generic_parameters[102] = (12, "T", 0, 0, 0, 0)
    m.meta.generic_parameters[103] = (12, "K", 0, 0, 0, 0)
    m.meta.typedefs[1] = inner
    assert m._nested_own_params(inner) == ["K"]
    assert m._typedef_arity(inner) == 1
