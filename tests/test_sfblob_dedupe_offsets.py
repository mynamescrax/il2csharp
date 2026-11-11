"""Dec F6: the static-field blob dedupe keys on the offset, not just
(owner, value).

`_sfblob_dedupe` dropped every blob/star/byte-cast store whose owner and
value matched a named store.  Two static fields of one type can receive
the same value, so a second, real store could be dropped whenever the
named twin existed.  The guard keeps every blob spelling for a key when
they write more than one distinct offset.
"""
from il2cpp.dec.sugar import _SugarMixin


def _dedupe(lines):
    return _SugarMixin()._sfblob_dedupe(list(lines))


def test_single_offset_twin_is_dropped():
    lines = [
        'typeof(V3).zeroVector = v;',
        'typeof(V3).__static_fields + 0x10 = v;',
    ]
    assert _dedupe(lines) == ['typeof(V3).zeroVector = v;']


def test_two_offsets_with_same_value_are_kept():
    lines = [
        'typeof(V3).zeroVector = v;',
        'typeof(V3).__static_fields + 0x10 = v;',
        'typeof(V3).__static_fields + 0x20 = v;',
    ]
    assert _dedupe(lines) == lines


def test_star_and_byte_cast_spellings_count_toward_offsets():
    lines = [
        'typeof(V3).zeroVector = v;',
        '*(typeof(V3).__static_fields + 0x10) = v;',
        '((byte*)typeof(V3).__static_fields + 0x20)[0] = v;',
    ]
    assert _dedupe(lines) == lines


def test_duplicate_spelling_at_one_offset_is_still_deduped():
    lines = [
        'typeof(V3).zeroVector = v;',
        'typeof(V3).__static_fields + 0x10 = v;',
        '*(typeof(V3).__static_fields + 0x10) = v;',
    ]
    assert _dedupe(lines) == ['typeof(V3).zeroVector = v;']


def test_offset_less_spelling_still_dedupes():
    lines = [
        'typeof(V3).zeroVector = v;',
        'typeof(V3).__static_fields = v;',
    ]
    assert _dedupe(lines) == ['typeof(V3).zeroVector = v;']


def test_two_named_fields_one_offset_still_dedupes():
    # Both named stores carry the same value, so whichever field the blob
    # write is, that value is already stored -- the blob twin is redundant.
    lines = [
        'typeof(V3).zeroVector = v;',
        'typeof(V3).oneVector = v;',
        'typeof(V3).__static_fields + 0x10 = v;',
    ]
    assert _dedupe(lines) == [
        'typeof(V3).zeroVector = v;',
        'typeof(V3).oneVector = v;',
    ]


def test_different_value_is_never_touched():
    lines = [
        'typeof(V3).zeroVector = v;',
        'typeof(V3).__static_fields + 0x10 = w;',
    ]
    assert _dedupe(lines) == lines
