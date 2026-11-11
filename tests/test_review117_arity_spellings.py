"""Fix 117: generic references spell the declaration's _N identifier.
Declarations say `EqualityComparer_1<T>` while references said
`EqualityComparer<byte>`, so overrides bound against the reference
assembly's base (CS0115) and locals against framework types (CS0246).
`csharp_type_name` now keeps the arity suffix everywhere, and explicit
interface qualifiers (which come from arity-less metadata name strings)
recover it through a (namespace, path, arg-count) typedef proof.
"""
from types import SimpleNamespace as NS

import pytest

from il2cpp.common import csharp_type_name
from test_review113_type_decls import make_emitter, td_base, TYPES, SPELL


def test_reference_spelling_keeps_arity():
    assert csharp_type_name("System.Collections.Generic.List`1") == \
        "System.Collections.Generic.List_1"
    assert csharp_type_name("System.Collections.Generic.Dictionary`2") == \
        "System.Collections.Generic.Dictionary_2"
    assert csharp_type_name("Outer+Inner`2") == "Outer.Inner_2"


def test_non_generic_spellings_unchanged():
    assert csharp_type_name("System.Int32") == "int"
    assert csharp_type_name("System.String") == "string"
    assert csharp_type_name("Foo.Bar") == "Foo.Bar"


def _td(index, name, ns="System.Collections.Generic"):
    return NS(index=index, name=name, namespace=ns, declaring=-1)


def _emitter_with_ifaces():
    e = make_emitter(typedefs=[None] * 5)
    e.meta.typedefs[1] = _td(1, "IEnumerator`1")
    e.meta.typedefs[2] = _td(2, "IEnumerable`1")
    e.meta.typedefs[3] = _td(3, "IEnumerator", ns="System.Collections")
    e.meta.typedefs[4] = _td(4, "IDictionary`2")
    return e


def test_qualifier_gains_suffix_on_exact_proof():
    e = _emitter_with_ifaces()
    assert e._arity_qualifier(
        "System.Collections.Generic.IEnumerator<object>") == \
        "System.Collections.Generic.IEnumerator_1<object>"


def test_qualifier_declines_without_args():
    e = _emitter_with_ifaces()
    assert e._arity_qualifier("System.Collections.IEnumerator") == \
        "System.Collections.IEnumerator"


def test_qualifier_declines_on_unknown_name():
    e = _emitter_with_ifaces()
    assert e._arity_qualifier("Nope.NoSuch<object>") == "Nope.NoSuch<object>"


def test_qualifier_declines_on_arity_mismatch():
    e = _emitter_with_ifaces()
    # only arity-1 IEnumerable exists; two args prove nothing here
    assert e._arity_qualifier(
        "System.Collections.Generic.IEnumerable<object, object>") == \
        "System.Collections.Generic.IEnumerable<object, object>"


def test_explicit_method_sig_suffixes_qualifier():
    from test_review114_method_flags import method
    e = _emitter_with_ifaces()
    m = method(1 | 0x40 | 0x20 | 0x100,
               "System.Collections.Generic.IEnumerator<System.Object>.get_Current")
    assert e.method_sig(m, td_base()).endswith(
        "System.Collections.Generic.IEnumerator_1<object>.get_Current()")


def test_explicit_method_keeps_multi_arg_commas():
    from test_review114_method_flags import method
    e = _emitter_with_ifaces()
    m = method(1 | 0x40 | 0x20 | 0x100,
               "System.Collections.Generic.IDictionary<TKey,TValue>.Add")
    assert e.method_sig(m, td_base()).endswith(
        "System.Collections.Generic.IDictionary_2<TKey, TValue>.Add()")


def _emitter_with_tuple_ifaces():
    # class implements IEnumerable_1<IProperty_1<T>> (tuple truth) plus a
    # non-generic interface that must not abort the match loop
    from test_review113_type_decls import TYPES as _TYPES
    _dummies = [(94, 0x12 << 16), (95, 0x12 << 16)]
    _idx = []
    for _t in _dummies:
        if _t not in _TYPES:
            _TYPES.append(_t)
        SPELL[_t] = "object"
        _idx.append(_TYPES.index(_t))
    e = make_emitter(typedefs=[None] * 4)
    e.meta.typedefs[1] = _td(1, "IEnumerable`1")
    e.meta.typedefs[3] = _td(3, "IEnumerable", ns="System.Collections")
    t10, t11 = (_TYPES[i] for i in _idx)
    e.il.type_name = lambda t: {
        t10: "System.Collections.Generic.IEnumerable_1<Unity.Properties.IProperty_1<TContainer>>",
        t11: "System.Collections.IEnumerable",
    }[t]
    e.meta.interfaces = _idx
    return e


def _iface_td():
    return NS(index=7, name="PropertyCollection`1", namespace="Unity.Properties",
              declaring=-1, interfaces_count=2, interfaces_start=0)


def test_iface_qualifier_prefers_tuple_spelling():
    e = _emitter_with_tuple_ifaces()
    assert e._iface_qualifier(
        "System.Collections.Generic.IEnumerable<IProperty<TContainer>>",
        _iface_td()) == \
        "System.Collections.Generic.IEnumerable_1<Unity.Properties.IProperty_1<TContainer>>"


def test_iface_qualifier_skips_non_generic_tuples():
    e = _emitter_with_tuple_ifaces()
    assert e._iface_qualifier("System.Collections.IEnumerable", _iface_td()) is None


def test_iface_qualifier_none_without_td():
    e = _emitter_with_tuple_ifaces()
    assert e._iface_qualifier(
        "System.Collections.Generic.IEnumerable<IProperty<TContainer>>") is None


def test_sanitize_qualifier_keeps_generic_structure():
    from il2cpp.names import sanitize_qualifier
    assert sanitize_qualifier(
        "System.Collections.Generic.ICollection_1<KeyValuePair_2<TKey, TValue>>") == \
        "System.Collections.Generic.ICollection_1<KeyValuePair_2<TKey, TValue>>"
    assert sanitize_qualifier(
        "System.Collections.Generic.IEnumerator_1<T[]>") == \
        "System.Collections.Generic.IEnumerator_1<T[]>"
    assert sanitize_qualifier("System.Collections.IEnumerable") == \
        "System.Collections.IEnumerable"


def test_sanitize_qualifier_still_sanitizes_segments():
    from il2cpp.names import sanitize_qualifier
    assert sanitize_qualifier("A.B.C-D") == "A.B.C_D"
    assert sanitize_qualifier("ReaderWriter@Fusion_NetworkString.X") == \
        "ReaderWriter_Fusion_NetworkString.X"
    # guid-braced nested owner: braces/dashes go, angles stay for the
    # file-boundary display-class pass (matching declaration spellings)
    assert sanitize_qualifier(
        "<PrivateImplementationDetails>{99f15b47-93f0}.X") == \
        "<PrivateImplementationDetails>_99f15b47_93f0_.X"
