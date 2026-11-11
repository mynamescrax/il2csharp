"""Fix 119: namespace-qualified spellings feed using generation.

`IntPtr` rendered bare (PRIM had no `System.` prefix), so no file ever
gained `using System;` from it (1,076 CS0246); `[Serializable]` and
`[SerializeField]` likewise never named a namespace. All three now render
qualified pre-strip (`System.IntPtr`, `[System.Serializable]`,
`[UnityEngine.SerializeField]`) so the using tracker imports the namespace
and the file boundary strips back to the short form.
"""
from types import SimpleNamespace as NS

from il2cpp.csharp import UsingTracker, strip_namespaces
from il2cpp.runtime.registration import _RegistrationMixin
from test_review113_type_decls import make_emitter, td_base


def test_prim_pointer_spellings_are_qualified():
    assert _RegistrationMixin.PRIM[0x18] == "System.IntPtr"
    assert _RegistrationMixin.PRIM[0x19] == "System.UIntPtr"
    assert _RegistrationMixin.PRIM[0x16] == "System.TypedReference"


def test_qualified_intptr_roundtrips_through_usings():
    tr = UsingTracker(None)
    tr.add_text("    private System.IntPtr _freeHead; // 0x18")
    assert tr.render() == ["using System;"]
    assert strip_namespaces(
        ["    private System.IntPtr _freeHead; // 0x18"],
        set(tr.used)) == ["    private IntPtr _freeHead; // 0x18"]


def test_bare_intptr_gains_no_using_without_qualification():
    tr = UsingTracker(None)
    tr.add_text("    private IntPtr _freeHead; // 0x18")
    assert tr.render() == []


def test_self_shadow_prefix_is_not_stripped():
    line = "    public UnityEngine.InputSystem.HID.HID.HIDDeviceDescriptor hid;"
    uses = {"UnityEngine", "UnityEngine.InputSystem",
            "UnityEngine.InputSystem.HID"}
    assert strip_namespaces([line], uses) == [line]


def test_ordinary_prefix_still_strips():
    assert strip_namespaces(["    private System.IntPtr _p;"],
                            {"System"}) == ["    private IntPtr _p;"]


def _emit_type_lines(td, em):
    em.il.field_offsets = [None] * 11
    out = []
    assert em.emit_type(td, out) is True
    return out


def test_serializable_attribute_is_qualified_pre_strip():
    e = make_emitter()
    td = td_base(name="C", flags=0x2000)
    lines = _emit_type_lines(td, e)
    assert any(l.strip() == "[System.Serializable]" for l in lines)


def test_serialize_field_attribute_is_qualified_pre_strip():
    from il2cpp.csharp import FA_STATIC
    e = make_emitter(fields=[NS(type=3, name="x")])
    e._unity_serialized = lambda *a: True
    td = td_base(name="C", flags=0)
    td.fis = [0]
    lines = _emit_type_lines(td, e)
    assert any("[UnityEngine.SerializeField]" in l for l in lines)
