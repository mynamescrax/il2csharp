"""fix 137: accessor calls use the member syntax their property rows declare.

The emitter declares every property row as a property and every row with
index parameters as ``this[...]`` whatever its metadata name, so a call that
names a proved accessor row must spell the member: ``s.get_Chars(i)`` (CS1061:
String's indexer row is named Chars) becomes ``s[i]``, ``Gizmos.set_color(c)``
(CS0571) becomes ``Gizmos.color = c``. Methods outside a property row, dotted
(explicit) rows and arity disagreements keep today's call spelling.

fix 137b: the sugar travels the pipeline as call-shaped markers
(``__accget(R.X)`` / ``__accset(R.X)(v)``) so every text purity test keeps
treating the accessor as the call it is (never DCE'd, never re-evaluated);
``lift_method`` unwraps them last.
"""
from types import SimpleNamespace as NS

from il2cpp import Lifter
from il2cpp.expr import acc_get, acc_lhs, acc_set, unwrap_accessor_markers as U


def _lifter():
    names = ['Chars', 'color', 'Length', 'Item', 'System.Collections.IList.Item']
    methods = [
        NS(name='get_Chars', declaring=0, param_count=1, is_static=False),   # 0
        NS(name='get_Length', declaring=0, param_count=0, is_static=False),  # 1
        NS(name='Concat', declaring=0, param_count=2, is_static=True),       # 2
        NS(name='get_color', declaring=1, param_count=0, is_static=True),    # 3
        NS(name='set_color', declaring=1, param_count=1, is_static=True),    # 4
        NS(name='get_Foo', declaring=1, param_count=0, is_static=False),     # 5 (no row)
        NS(name='set_Item', declaring=2, param_count=2, is_static=False),    # 6
        NS(name='System.Collections.IList.get_Item', declaring=2,
           param_count=1, is_static=False),                                  # 7
    ]
    typedefs = [
        NS(method_start=0, property_start=0, property_count=2),
        NS(method_start=3, property_start=2, property_count=1),
        NS(method_start=6, property_start=3, property_count=2),
    ]
    properties = [
        (0, 0, -1, 0, 0),   # String.Chars   get rel 0
        (2, 1, -1, 0, 0),   # String.Length  get rel 1
        (1, 0, 1, 0, 0),    # Gizmos.color   get rel 0 / set rel 1
        (3, -1, 0, 0, 0),   # List.Item      set rel 0
        (4, 1, -1, 0, 0),   # explicit IList.Item get rel 1
    ]
    L = Lifter.__new__(Lifter)
    L.meta = NS(methods=methods, typedefs=typedefs, properties=properties,
                getstr=lambda i: names[i])
    L._current_method = None
    return L


def S(sg):
    return None if sg is None else (sg[0], U(sg[1]))


def test_indexer_row_named_chars_is_an_indexer():
    L = _lifter()
    assert L._accessor_prop(0) == ('get', 'Chars', 1)
    assert L._accessor_sugar(0, 'text6', ['num1']) == ('expr', '__accget(text6[num1])')
    assert S(L._accessor_sugar(0, 'text6', ['num1'])) == ('expr', 'text6[num1]')
    assert S(L._accessor_sugar(0, 'textArray1[num1]', ['0'])) == ('expr', 'textArray1[num1][0]')


def test_plain_getter_and_static_setter():
    L = _lifter()
    assert S(L._accessor_sugar(1, 'this.name', [])) == ('expr', 'this.name.Length')
    assert S(L._accessor_sugar(3, 'UnityEngine.Gizmos', [])) == ('expr', 'UnityEngine.Gizmos.color')
    sg = L._accessor_sugar(4, 'UnityEngine.Gizmos', ['color1'])
    assert sg == ('stmt', '__accset(UnityEngine.Gizmos.color)(color1)')
    assert S(sg) == ('stmt', 'UnityEngine.Gizmos.color = color1')
    assert acc_lhs(sg[1]) == 'UnityEngine.Gizmos.color'
    assert L._static_owner('UnityEngine.Gizmos.set_color', 4) == 'UnityEngine.Gizmos'


def test_indexer_setter_and_composite_receiver():
    L = _lifter()
    assert S(L._accessor_sugar(6, 'list1', ['i', 'v'])) == ('stmt', 'list1[i] = v')
    assert S(L._accessor_sugar(6, 'a + b', ['i', 'v'])) == ('stmt', '(a + b)[i] = v')
    assert acc_lhs(L._accessor_sugar(6, 'list1', ['i', 'v'])[1]) == 'list1[i]'


def test_declines():
    L = _lifter()
    assert L._accessor_prop(2) is None            # not an accessor
    assert L._accessor_prop(5) is None            # get_ name without a row
    assert L._accessor_prop(7) is None            # explicit (dotted) row
    assert L._accessor_sugar(0, 'text6', []) is None          # arity
    assert L._accessor_sugar(0, 'text6', ['?']) is None       # placeholder
    assert L._accessor_sugar(0, '42', ['0']) is None          # literal receiver
    assert L._accessor_sugar(0, '&s_20', ['0']) is None       # byref composite
    assert L._accessor_sugar(0, None, ['0']) is None


def test_tail_accessor_spelling():
    L = _lifter()
    L._info_name = lambda info: 'UnityEngine.Gizmos.set_color'
    assert U(L._tail_accessor(4, ['c'])) == 'UnityEngine.Gizmos.color = c'
    assert U(L._tail_accessor(0, ['&s_10', 'i'])) == 's_10[i]'
    assert L._tail_accessor(2, ['a', 'b']) is None
    # a getter tail in a void caller is not a statement
    L._caller_is_void = lambda: True
    assert L._tail_accessor(0, ['s', 'i']) is None
    assert U(L._tail_accessor(4, ['c'])) == 'UnityEngine.Gizmos.color = c'


def test_markers_read_impure_to_dce():
    from il2cpp.dec import dataflow
    imp = None
    for v in vars(dataflow).values():
        if isinstance(v, type) and hasattr(v, '_impure'):
            imp = v
            break
    assert imp is not None
    obj = imp.__new__(imp)
    assert obj._impure(acc_get('format[num2]'))
    assert obj._impure(acc_get('this.name.Length'))
    assert not obj._impure('format[num2]')   # why the marker exists


def test_unwrap_shapes():
    assert U(acc_set('this.a.X', acc_get('(' + acc_get('b.Y') + ').Z')) + ';') == 'this.a.X = b.Y.Z;'
    assert U('if (' + acc_get('format[n]') + ' == 125)') == 'if (format[n] == 125)'
    assert U('Foo((' + acc_get('a.B') + '))') == 'Foo((a.B))'
    assert U('x = (' + acc_get('a.B') + ').C;') == 'x = a.B.C;'
    assert U('if (' + acc_get('a.B') + ')') == 'if (a.B)'
    assert U('(T)(' + acc_get('a.B') + ').C') == '(T)(a.B).C'
    assert U(acc_set('l[i, ")("]', "')'") + ';') == 'l[i, ")("] = \')\';'
    assert U('x = __accget(a.B;') == 'x = __accget(a.B;'   # unbalanced: untouched
    assert U('plain(x);') == 'plain(x);'
