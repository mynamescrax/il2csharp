"""Fix 113: legal type declarations.

Interfaces were misread as classes whenever the abstract bit was set
(which ECMA mandates for interfaces); abstract+sealed utility classes
render `static`; user delegates render `delegate` via Invoke; interface
members lose access/instance modifiers (DIM bodies kept).
"""

from types import SimpleNamespace as NS

from il2cpp.emitter import Emitter

I_VOID, I_BOOL, I_STR, I_INT = range(4)
T_VOID = (0, 0x01 << 16)
T_BOOL = (0, 0x02 << 16)
T_STR = (5, 0x0E << 16)
T_INT = (0, 0x08 << 16)
TYPES = [T_VOID, T_BOOL, T_STR, T_INT]
SPELL = {T_VOID: "void", T_BOOL: "bool", T_STR: "string", T_INT: "int"}


def P(ti, name="p"):
    return NS(type=ti, name=name)


def make_emitter(methods=(), fields=(), typedefs=(), ifaces=()):
    e = Emitter.__new__(Emitter)
    il = NS(addr_candidates={}, types=TYPES,
            type_name=lambda t: SPELL.get(
                (t[0], t[1]) if isinstance(t, tuple) else t, "object"),
            base_chain_tds=lambda td: (td,))
    meta = NS(methods=list(methods), fields=list(fields),
              typedefs=list(typedefs), interfaces=list(ifaces),
              generic_containers=[], generic_parameters=[],
              param_default_values={},
              getstr=lambda i: "P",
              method_params=lambda m: getattr(m, "ps", []),
              type_methods=lambda td: getattr(td, "mis", []),
              type_fields=lambda td: getattr(td, "fis", []))
    e.il = il
    e.meta = meta
    il.meta = meta
    return e


def td_base(index=10, name="Foo", flags=0, parent=-1, ifaces=(),
            methods=(), fields=(), generic_container=-1):
    return NS(index=index, name=name, namespace="", flags=flags,
              parent=parent, declaring=-1, is_enum=False,
              is_valuetype=False, generic_container=generic_container,
              field_start=0, field_count=0, method_start=0,
              method_count=len(methods), property_count=0, event_count=0,
              nested_count=0, interfaces_count=len(ifaces),
              interfaces_start=0, mis=list(methods), fis=list(fields))


def test_interface_flag_with_abstract():
    e = make_emitter()
    td = td_base(name="IFoo", flags=0x20 | 0x80)
    assert e.type_decl_line(td) == ["internal partial interface IFoo"]


def test_static_class():
    e = make_emitter()
    td = td_base(name="Math", flags=0x80 | 0x100)
    assert e.type_decl_line(td) == ["internal static partial class Math"]
    td = td_base(name="C", flags=0x80)
    assert e.type_decl_line(td) == ["internal abstract partial class C"]
    td = td_base(name="D", flags=0x100)
    assert e.type_decl_line(td) == ["internal sealed partial class D"]
    td = td_base(name="E", flags=0)
    assert e.type_decl_line(td) == ["internal partial class E"]


def test_delegate_emit():
    inv = NS(name="Invoke", is_static=False, return_type=I_BOOL,
             declaring=30, generic_container=-1, parameter_start=0,
             ps=[P(I_STR, "s")])
    td = td_base(index=30, name="Action_1", flags=0x100, parent=-1,
                 methods=[inv])
    td.mis = [7]
    e = make_emitter(methods=[None] * 7 + [inv], typedefs=[None] * 32)
    e.meta.typedefs[30] = td
    e.il.base_chain_tds = lambda td: (30, 31)
    e.meta.typedefs[31] = NS(name="MulticastDelegate")
    assert e._is_delegate_td(td) is True
    out = []
    assert e.emit_delegate(td, out, "    ") is True
    assert out[1] == "    internal delegate bool Action_1(string s);"


def test_delegate_fallback_and_bases():
    e = make_emitter()
    td = td_base(index=30, name="Weird")
    assert e._is_delegate_td(td) is False
    sysdel = NS(index=40, name="MulticastDelegate", namespace="System")
    assert e._is_delegate_td(sysdel) is False


def test_interface_method_sig():
    e = make_emitter()
    td = td_base(name="IFoo", flags=0x20 | 0x80)
    m = NS(name="Bar", is_static=False, return_type=I_BOOL,
           flags=0x400 | 0x10, declaring=10, generic_container=-1,
           parameter_start=0, ps=[P(I_INT, "x")])
    assert e.method_sig(m, td) == "bool Bar(int x)"
    m2 = NS(name="Baz", is_static=True, return_type=I_BOOL,
            flags=0x10, declaring=10, generic_container=-1,
            parameter_start=0, ps=[])
    assert e.method_sig(m2, td) == "static bool Baz()"


def test_property_staticness():
    e = make_emitter()
    e._lift_body = lambda *a: None
    get_s = NS(name="get_P", is_static=True, return_type=I_INT)
    get_i = NS(name="get_Q", is_static=False, return_type=I_INT)
    td = td_base(name="C", flags=0)
    out = []
    e.emit_property(td, out, "    ",
                    ("P", 0, 1, 0, 0), None)
    # no accessors resolvable: instance rendering, no static
    assert out[0].strip().startswith("public object ")
    assert "static" not in out[0]
    e2 = make_emitter()
    e2._lift_body = lambda *a: None
    e2.meta.methods = [get_s]
    td2 = td_base(name="D", flags=0)
    out2 = []
    e2.emit_property(td2, out2, "    ", ("P", 0, -1, 0, 0), None)
    assert "static" in out2[0] and "get;" in out2[0]
