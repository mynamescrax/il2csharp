"""Fix 122: receiver-proven stub temps take their owner's type.

`object obj228 = sub_...(args); obj228.SetTrigger("Reload")` proves Animator
when exactly one metadata method matches (name, literal applicability):
the declaration is retyped so the existing caller-proven cast machinery
wraps the call. Literal-only args, instance non-generic methods, exact
arity or provable defaults, no address/ref/out writes. Anything else
declines with the object spelling intact.
"""
from types import SimpleNamespace as NS

from il2cpp import Decompiler


def dec_with(meta_methods=None, types=None, typedefs=None, defaults=None):
    from il2cpp import Emitter  # noqa: ensure package import order
    d = Decompiler.__new__(Decompiler)
    spells = {(0, 0): "string", (1, 0): "int", (2, 0): "void",
              (3, 0): "UnityEngine.Animator", (7, 0x12): "UnityEngine.Animator"}

    def type_name(t):
        try:
            return spells.get((t[0], (t[1] >> 16) & 0xFF), "object")
        except Exception:
            return "object"

    il = NS(types=list(types or []), type_name=type_name, meta=None)
    meta = NS(methods=list(meta_methods or []), typedefs=list(typedefs or []),
              method_params=lambda m: getattr(m, "ps", []),
              param_default_values=dict(defaults or {}))
    il.meta = meta
    d.L = NS(il=il, meta=meta)
    return d


I_STR = (0, 0, "string")
I_INT = (1, 0, "int")
I_VOID = (2, 0, "void")
I_ANIM = (3, 0, "UnityEngine.Animator")


def P(ti, name="p"):
    return NS(type=ti, name=name)


def M(name, ret, params, static=False, generic_container=-1, declaring=7):
    m = NS(name=name, return_type=ret, ps=list(params), is_static=static,
           generic_container=generic_container, declaring=declaring,
           flags=0x86, parameter_start=0)
    return m


def base_meta():
    anim = NS(index=7, name="Animator", namespace="UnityEngine",
              is_valuetype=False)
    methods = [
        M("SetTrigger", 2, [P(0, "name")]),          # (string)
        M("SetTrigger", 2, [P(1, "value")]),         # (int)
        M("SetFloat", 2, [P(0, "name"), P(1, "v")]),  # two-param
        M("ToString", 0, []),
    ]
    return methods, [I_STR, I_INT, I_VOID, I_ANIM], [None] * 7 + [anim]


def test_literal_kinds():
    d = Decompiler.__new__(Decompiler)
    k = d._recv_lit_kind
    assert k('"Reload"') == "string"
    assert k("true") == "bool"
    assert k("6") == "int-lit"
    assert k("1.5f") == "float-lit"
    assert k("'a'") == "char-lit"
    assert k("obj1") is None
    assert k("null") is None
    assert k("5u") == "uint-lit"
    assert k("7l") == "long-lit"


def test_unique_string_overload_wins():
    methods, types, typedefs = base_meta()
    d = dec_with(methods, types, typedefs)
    assert d._unique_receiver_owner("SetTrigger", ("string",)) == \
        "UnityEngine.Animator"


def test_int_literal_overload():
    methods, types, typedefs = base_meta()
    d = dec_with(methods, types, typedefs)
    assert d._unique_receiver_owner("SetTrigger", ("int-lit",)) == \
        "UnityEngine.Animator"


def test_unknown_name_declines():
    methods, types, typedefs = base_meta()
    d = dec_with(methods, types, typedefs)
    assert d._unique_receiver_owner("Nope", ("string",)) is None


def test_nonliteral_declines():
    methods, types, typedefs = base_meta()
    d = dec_with(methods, types, typedefs)
    assert d._unique_receiver_owner("SetTrigger", (None,)) is None


def test_single_owner_tostring_proves_owner():
    methods, types, typedefs = base_meta()
    d = dec_with(methods, types, typedefs)
    assert d._unique_receiver_owner("ToString", ()) == "UnityEngine.Animator"


def test_decl_retype_end_to_end():
    methods, types, typedefs = base_meta()
    d = dec_with(methods, types, typedefs)
    lines = [
        "object obj228 = sub_180001d80(this.holdingAnims, this.holdingIndex);",
        'obj228.SetTrigger("Reload");',
    ]
    assert d._stub_receiver_decls(lines) == [
        "UnityEngine.Animator obj228 = sub_180001d80(this.holdingAnims, this.holdingIndex);",
        'obj228.SetTrigger("Reload");',
    ]


def test_multi_use_declines():
    methods, types, typedefs = base_meta()
    d = dec_with(methods, types, typedefs)
    lines = [
        "object obj1 = sub_1234(a);",
        'obj1.SetTrigger("x");',
        'obj1.SetTrigger("y");',
    ]
    assert d._stub_receiver_decls(lines) == lines


def test_write_declines():
    methods, types, typedefs = base_meta()
    d = dec_with(methods, types, typedefs)
    lines = [
        "object obj1 = sub_1234(a);",
        'obj1.SetTrigger("x");',
        "obj1 = other;",
    ]
    assert d._stub_receiver_decls(lines) == lines


def test_nonstub_rhs_declines():
    methods, types, typedefs = base_meta()
    d = dec_with(methods, types, typedefs)
    lines = [
        "object obj1 = other;",
        'obj1.SetTrigger("x");',
    ]
    assert d._stub_receiver_decls(lines) == lines
