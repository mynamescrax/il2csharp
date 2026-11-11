"""`slot_max_arity` must skip empty vtable entries (raw 0x0/0x1).

Decoding a raw `1` as method row 0 inflates a slot's arity cap whenever
row 0 happens to be an instance method -- the fixture only masks it
because methods[0] is static. The gate mirrors `vtable_method`'s.
"""
from types import SimpleNamespace as NS

from il2cpp import Il2Cpp


def _il(entries, methods):
    il = Il2Cpp.__new__(Il2Cpp)
    il.meta = NS(
        vtable_methods=list(entries),
        methods=methods,
        typedefs=[NS(vtable_count=len(entries), vtable_start=0)],
    )
    return il


def test_slot_max_arity_ignores_empty_entries():
    # raw 0x1 carries no method bits; row 0 is an instance method with 3
    # parameters, so decoding it would claim an arity-4 cap.
    il = _il([1], [NS(param_count=3, is_static=False)])
    assert il.slot_max_arity(0) is None


def test_slot_max_arity_reads_real_entries():
    # (3 << 1) | 1 = raw 7 -> method row 3; instance -> receiver included.
    methods = [NS(param_count=0, is_static=False) for _ in range(4)]
    methods[3] = NS(param_count=2, is_static=False)
    il = _il([(3 << 1) | 1], methods)
    assert il.slot_max_arity(0) == 3


def test_slot_max_arity_static_has_no_receiver():
    methods = [NS(param_count=0, is_static=False) for _ in range(2)]
    methods[1] = NS(param_count=4, is_static=True)
    il = _il([(1 << 1) | 1], methods)
    assert il.slot_max_arity(0) == 4
