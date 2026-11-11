"""Boehm card-mark residue (`drop_gc_cardmarks`, dec/build.py).

The write barrier's card-table update is modelled as ordinary code in some
builds. Three exact shapes are dropped, each only while nothing reads it;
anything else stays. `8589930496` is 0x1FFFFF000 (the card-table address
mask); `8589934592` is 0x200000000, a real System.Uri flag that this pass
must never touch.
"""
from il2cpp.dec.build import drop_gc_cardmarks

IND = '        '


def _lines(*ls):
    return [IND + x if x not in ('{', '}') else IND + x for x in ls]


def test_empty_while_over_the_card_index_is_dropped():
    src = _lines('int a = 1;',
                 'while (((byte*)obj1 + 0x8)[0] >> 12 & 63)', '{', '}',
                 'return a;')
    assert drop_gc_cardmarks(src) == [src[0], src[4]]


def test_empty_while_with_explicit_compare_is_dropped():
    src = _lines('while ((((long)obj1 + 0x8) >> 12 & 63) != 0)', '{', '}', 'return;')
    assert drop_gc_cardmarks(src) == [src[3]]


def test_while_with_a_body_stays():
    src = _lines('while (((byte*)obj1 + 0x8)[0] >> 12 & 63)', '{', 'num1 = 1;', '}')
    assert drop_gc_cardmarks(src) == src


def test_while_with_a_call_in_the_condition_stays():
    src = _lines('while (Foo.Next() >> 12 & 63)', '{', '}')
    assert drop_gc_cardmarks(src) == src


def test_while_with_an_assignment_in_the_condition_stays():
    for cond in ('(num1 = Load()) >> 12 & 63', 'num1++ >> 12 & 63',
                 '(num1 += 4) >> 12 & 63', '(num1 >>= 1) >> 12 & 63'):
        src = _lines('while (%s)' % cond, '{', '}')
        assert drop_gc_cardmarks(src) == src, cond


def test_other_shifts_and_masks_stay():
    for cond in ('x >> 11 & 63', 'x >> 12 & 31', 'x >> 13 & 63', 'x << 12 & 63'):
        src = _lines('while (%s)' % cond, '{', '}')
        assert drop_gc_cardmarks(src) == src, cond


def test_empty_data_flag_if_is_dropped():
    for head in ('if (data_183e72c16 != 0)', 'if (data_183E72C16 == 0)',
                 'if (!(data_183e72c16 != 0))'):
        src = _lines('this.x = 1;', head, '{', '}', 'return;')
        assert drop_gc_cardmarks(src) == [src[0], src[4]], head


def test_data_flag_if_with_a_body_or_an_else_stays():
    body = _lines('if (data_183e72c16 != 0)', '{', 'this.x = 1;', '}')
    assert drop_gc_cardmarks(body) == body
    els = _lines('if (data_183e72c16 != 0)', '{', '}', 'else', '{', 'this.x = 1;', '}')
    assert drop_gc_cardmarks(els) == els


def test_other_conditions_on_empty_blocks_stay():
    for head in ('if (data_183e72c16 != 1)', 'if (this.ready != 0)',
                 'if (data_183e72c16 != 0 && a)', 'if (data_ != 0)'):
        src = _lines(head, '{', '}')
        assert drop_gc_cardmarks(src) == src, head


def test_unread_card_index_is_dropped_typed_and_bare():
    typed = _lines('long num5 = (((long)obj1 + 0x8) & 8589930496) >> 12 & 63;', 'return;')
    assert drop_gc_cardmarks(typed) == [typed[1]]
    bare = _lines('num5 = (((long)obj1 + 0x8) & 8589930496) >> 12 & 63;', 'return;')
    assert drop_gc_cardmarks(bare) == [bare[1]]


def test_read_card_index_stays():
    src = _lines('long num5 = (((long)obj1 + 0x8) & 8589930496) >> 12 & 63;',
                 'return num5;')
    assert drop_gc_cardmarks(src) == src


def test_member_named_like_the_index_is_not_a_read():
    src = _lines('long num5 = (((long)obj1 + 0x8) & 8589930496) >> 12 & 63;',
                 'this.num5 = 0;')
    assert drop_gc_cardmarks(src) == [src[1]]


def test_card_index_with_a_call_or_other_mask_stays():
    call = _lines('long num5 = (Foo.Bar() & 8589930496) >> 12 & 63;')
    assert drop_gc_cardmarks(call) == call
    uri = _lines('long num5 = (flags.value__ & 8589934592) >> 12 & 63;')      # 0x200000000
    assert drop_gc_cardmarks(uri) == uri


def test_utf8_encoding_shift_is_not_touched():
    src = _lines('((byte*)pDst + 0x1)[0] = num1 >> 12 & 63 | 128;',
                 'Unicode.Rune rune2 = rune >> 12 & 63 | 128;')
    assert drop_gc_cardmarks(src) == src


def test_unrelated_text_round_trips():
    src = _lines('if (a)', '{', 'b();', '}', 'else', '{', '}')
    assert drop_gc_cardmarks(src) == src
    assert drop_gc_cardmarks([]) == []
