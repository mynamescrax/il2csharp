"""Fix 129: vtable rows are encoded metadata usages.

Usage 6 (MethodRef) rows index the methodSpec table; decoding them as
MethodDef rows named unrelated methods (fixture: TaskNode slot 13 read
`DebugLogResizeListener..ctor` instead of `Task`1.InnerInvoke`; only 64 of
8,846 such rows agreed with their slot). Empty rows are abstract slots: the
unique instance method of the type or an ancestor carrying that metadata
`slot` owns them (fixture: 1,523 rows, 0 ambiguous).
"""
from types import SimpleNamespace as NS

from il2cpp import Il2Cpp

USAGE_DEF = 3 << 29
USAGE_REF = 6 << 29


def _m(slot=0xFFFF, static=False, params=0):
    return NS(slot=slot, is_static=static, param_count=params)


def _il(typedefs, entries, methods, specs=(), types=()):
    il = Il2Cpp.__new__(Il2Cpp)
    il.meta = NS(vtable_methods=list(entries), methods=methods, typedefs=typedefs)
    il.method_specs = list(specs)
    il.types = list(types)
    return il


def _td(vt_start, vt_count, m_start=0, m_count=0, parent=-1):
    return NS(vtable_start=vt_start, vtable_count=vt_count, method_start=m_start,
              method_count=m_count, parent=parent)


def test_method_ref_row_decodes_through_method_specs():
    methods = [_m(static=True)] + [_m(slot=s) for s in range(1, 6)]
    # row says spec 2 -> MethodDef 5; the bare decode would name row 2
    il = _il([_td(0, 1)], [USAGE_REF | (2 << 1) | 1], methods,
             specs=[(1, -1, -1), (3, -1, -1), (5, 7, -1)])
    assert il.vtable_method(0, 0) == 5


def test_method_ref_row_out_of_range_declines():
    il = _il([_td(0, 1)], [USAGE_REF | (9 << 1) | 1], [_m(static=True), _m()],
             specs=[(1, -1, -1)])
    assert il.vtable_method(0, 0) is None


def test_method_def_row_unchanged():
    il = _il([_td(0, 1)], [USAGE_DEF | (1 << 1) | 1], [_m(static=True), _m(slot=0)])
    assert il.vtable_method(0, 0) == 1


def test_empty_row_names_own_abstract_method():
    # type 0 owns methods 1..2; method 2 declares slot 4 (abstract)
    methods = [_m(static=True), _m(slot=3), _m(slot=4)]
    tds = [_td(0, 5, m_start=1, m_count=2)]
    il = _il(tds, [USAGE_DEF | 3, 0, 0, USAGE_DEF | (1 << 1) | 1, 1], methods)
    assert il.vtable_method(0, 4) == 2


def test_empty_row_walks_to_ancestor_and_declines_ambiguity():
    methods = [_m(static=True), _m(slot=4), _m(slot=4), _m(slot=4)]
    # td1 (child, no methods) -> parent type 0 -> td0 declares slot 4 once
    tds = [_td(0, 5, m_start=1, m_count=1), _td(5, 5, m_start=0, m_count=0, parent=0)]
    il = _il(tds, [0] * 10, methods, types=[(0, 0x12 << 16)])
    assert il.vtable_method(1, 4) == 1
    tds2 = [_td(0, 5, m_start=2, m_count=2)]
    assert _il(tds2, [0] * 5, methods).vtable_method(0, 4) is None


def test_slot_max_arity_uses_spec_decode():
    methods = [_m(static=True), _m(params=9), _m(params=1)]
    il = _il([_td(0, 1)], [USAGE_REF | (0 << 1) | 1], methods, specs=[(2, -1, -1)])
    assert il.slot_max_arity(0) == 2
