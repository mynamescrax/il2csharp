"""Fix 116: pointer-typed fields and properties carry unsafe.

Method/ctor signatures were covered by fix 115; the remaining CS0214
residue is declaration-level only (465 fields, 52 properties, 0 body
lines tree-wide): `private readonly void* m_value;` needs its own
unsafe context, as does a pointer-typed property.
"""
from types import SimpleNamespace as NS

from test_review113_type_decls import make_emitter, td_base, P, TYPES, SPELL

T_PF_PRIV_RO = (90, (0x0F << 16) | 0x21)  # private | initonly -> void*
T_PF_PUB = (91, (0x0F << 16) | 0x06)  # public -> byte*
T_PF_PRIV_STATIC = (92, (0x0F << 16) | 0x11)  # private | static -> int*
T_PF_PLAIN = (93, (0x08 << 16) | 0x06)  # public int control
for _t, _s in ((T_PF_PRIV_RO, "void*"), (T_PF_PUB, "byte*"),
               (T_PF_PRIV_STATIC, "int*"), (T_PF_PLAIN, "int")):
    if _t not in TYPES:
        TYPES.append(_t)
    SPELL[_t] = _s
I_PF_RO, I_PF_PUB, I_PF_ST, I_PLAIN = (len(TYPES) - 4 + k for k in range(4))


def _field(tt, name="m_value"):
    return NS(type=tt, name=name)


def _emit_fields(fields):
    e = make_emitter(fields=fields)
    e.il.field_offsets = [None] * 11
    td = td_base(name="C", flags=0)
    td.fis = list(range(len(fields)))
    out = []
    assert e.emit_type(td, out) is True
    return [l for l in out if l.strip().endswith(";")]


def test_pointer_instance_field_is_unsafe():
    (line,) = _emit_fields([_field(I_PF_RO)])
    assert line.strip() == "private readonly unsafe void* m_value;"


def test_pointer_public_field_is_unsafe():
    (line,) = _emit_fields([_field(I_PF_PUB, "eventBuffer")])
    assert line.strip() == "public unsafe byte* eventBuffer;"


def test_pointer_static_field_is_unsafe():
    (line,) = _emit_fields([_field(I_PF_ST, "s_ptr")])
    assert line.strip() == "private static unsafe int* s_ptr;"


def test_plain_field_stays_safe():
    (line,) = _emit_fields([_field(I_PLAIN, "count")])
    assert line.strip() == "public int count;"
    assert "unsafe" not in line


def _prop_emitter(getter):
    e = make_emitter(methods=[getter])
    e._lift_body = lambda *a: None
    return e


def test_pointer_auto_property_is_unsafe():
    get = NS(name="get_Pointer", is_static=False, return_type=I_PF_PUB)
    e = _prop_emitter(get)
    out = []
    e.emit_property(td_base(name="C", flags=0), out, "    ", ("Pointer", 0, -1, 0, 0), None)
    assert out[0].strip().startswith("public unsafe byte* P { get;")


def test_pointer_bodied_property_is_unsafe():
    get = NS(name="get_Data", is_static=False, return_type=I_PF_PUB)
    e = _prop_emitter(get)
    e._lift_body = lambda *a: ["return null;"]
    out = []
    e.emit_property(td_base(name="C", flags=0), out, "    ", ("Data", 0, -1, 0, 0), None)
    assert out[0].strip() == "public unsafe byte* P"
    assert any("return null;" in l for l in out)


def test_plain_property_stays_safe():
    get = NS(name="get_N", is_static=False, return_type=I_PLAIN)
    e = _prop_emitter(get)
    out = []
    e.emit_property(td_base(name="C", flags=0), out, "    ", ("N", 0, -1, 0, 0), None)
    assert "unsafe" not in out[0]
