"""Shared literal/comment masker: `il2cpp.text.mask_literals`.

One precompiled alternation replaced two copies of a character loop
(`dec/highlevel.py` `_mask_literals`, `dec/textpass.py` `_mask_line_spans`).
`_oracle_mask` below is that old loop, kept as the differential oracle. It
differs from the original in exactly one place: the original skipped two
characters at a trailing backslash inside an unterminated literal and
returned a mask one NUL longer than the line (0 lines of the r11 tree);
the oracle clamps, because "same length" is the contract.
"""
import random

import pytest

from il2cpp.dec import highlevel, textpass
from il2cpp.text import mask_literals

NUL = '\x00'


def _oracle_mask(line, in_block_comment):
    out = []
    i = 0
    n = len(line)
    while i < n:
        if in_block_comment:
            j = line.find('*/', i)
            if j < 0:
                out.append(NUL * (n - i))
                return ''.join(out), True
            out.append(NUL * (j + 2 - i))
            i = j + 2
            in_block_comment = False
            continue
        if line.startswith('//', i):
            out.append(NUL * (n - i))
            break
        if line.startswith('/*', i):
            in_block_comment = True
            out.append(NUL * 2)
            i += 2
            continue
        if line.startswith('@"', i):
            j = i + 2
            while j < n:
                if line.startswith('""', j):
                    j += 2
                    continue
                if line[j] == '"':
                    j += 1
                    break
                j += 1
            out.append(NUL * (j - i))
            i = j
            continue
        c = line[i]
        if c in ('"', "'"):
            j = i + 1
            while j < n:
                if line[j] == '\\':
                    j += 2
                    continue
                if line[j] == c:
                    j += 1
                    break
                j += 1
            j = min(j, n)
            out.append(NUL * (j - i))
            i = j
            continue
        out.append(c)
        i += 1
    return ''.join(out), in_block_comment


def _blank(s):
    return NUL * len(s)


# (prefix, blanked span, suffix, state after the line)
SPAN_CASES = [
    ('s = ', '"ab"', ';', False),
    ('s = ', '"a\\"b"', ' + c;', False),            # escaped quote
    ('s = ', '"a\\\\"', ' + c;', False),            # escaped backslash, then closer
    ('c = ', "'x'", ';', False),
    ('c = ', "'\\''", ';', False),                  # escaped apostrophe
    ('s = ', '@"C:\\dir ""q"" end"', ';', False),   # verbatim: "" escapes
    ('s = ', '@"a\\"', ' + b;', False),             # verbatim: backslash is plain
    ('s = ', '@"abc""', '', False),                 # unterminated, ends on a pair
    ('x = ', '"abc', '', False),                    # unterminated string
    ('x = ', '"abc\\', '', False),                  # trailing backslash: length contract
    ('x = ', "'a", '', False),                      # unterminated char literal
    ('x ', '// c "q" /* z', '', False),             # comment swallows quotes and openers
    ('x = ', '"//not a comment"', '; y', False),
    ('x = ', '"/*not a comment"', '; y', False),
    ('a ', '/* b */', ' c', False),
    ('a ', '/**/', ' b', False),
    ('a ', '/*/ b', '', True),                      # `/*/` is an opener, not a closed comment
    ('a ', '/* b', '', True),
    ('s = ', '$@"{x}""y"', ';', False),             # interpolated verbatim
]


@pytest.mark.parametrize('prefix,span,suffix,state', SPAN_CASES)
def test_span_cases(prefix, span, suffix, state):
    line = prefix + span + suffix
    masked, in_bc = mask_literals(line, False)
    if span.startswith('$@'):
        # the `$` is code; only the verbatim string after it is blanked
        assert masked == prefix + '$' + _blank(span[1:]) + suffix
    else:
        assert masked == prefix + _blank(span) + suffix
    assert in_bc is state
    assert (masked, in_bc) == _oracle_mask(line, False)


def test_plain_code_is_returned_unchanged():
    for line in ('', 'num1 = num2 / num3;', 'a @ b', 'x = y * z; /'):
        assert mask_literals(line, False) == (line, False)


def test_division_is_not_a_comment():
    assert mask_literals('a = b / c / d;', False) == ('a = b / c / d;', False)


def test_open_block_comment_state_is_threaded():
    lines = ['int a; /* start', 'still "in" a comment', 'end */ int b = "x"; /* again', 'tail */ z']
    expect = [
        ('int a; ' + _blank('/* start'), True),
        (_blank(lines[1]), True),
        (_blank('end */') + ' int b = ' + _blank('"x"') + '; ' + _blank('/* again'), True),
        (_blank('tail */') + ' z', False),
    ]
    st = False
    got = []
    for ln in lines:
        masked, st = mask_literals(ln, st)
        got.append((masked, st))
    assert got == expect


def test_open_comment_empty_line_keeps_state():
    assert mask_literals('', True) == ('', True)
    assert mask_literals('', False) == ('', False)


def test_resume_after_close_scans_the_rest_for_literals():
    masked, st = mask_literals('b */ c "d" // e', True)
    assert masked == _blank('b */') + ' c ' + _blank('"d"') + ' ' + _blank('// e')
    assert st is False


def test_newline_inside_a_comment_is_swallowed():
    line = 'a // b\nc "d"'
    masked, st = mask_literals(line, False)
    assert masked == 'a ' + _blank(line[2:])
    assert (masked, st) == _oracle_mask(line, False)


def test_verbatim_with_only_doubled_quotes_runs_to_end_of_line():
    # every quote is half of a `""` pair, so there is no closer: the literal
    # is unterminated, never `@"a"` followed by a second stray literal
    for line in ('@"a""', '@"a"" b""', 'x = @"p"""" q"" r'):
        at = line.index('@')
        masked, st = mask_literals(line, False)
        assert masked == line[:at] + _blank(line[at:]) and st is False
        assert (masked, st) == _oracle_mask(line, False)


def test_verbatim_has_no_backslash_escape():
    # the quote after the backslash is a lone quote: it closes the literal
    line = '@"a"" b\\" + c'
    masked, st = mask_literals(line, False)
    assert masked == _blank('@"a"" b\\"') + ' + c' and st is False


def test_both_passes_share_one_scanner():
    assert highlevel._HighLevelMixin._mask_literals is mask_literals
    assert textpass._mask_line_spans is mask_literals


_ALPHABET = ['@', '"', '"', "'", '\\', '/', '/', '*', '*', 'a', 'b', ' ', '$',
             '\n', '{', '}', '=', '@"', '""', '/*', '*/', '//']


def test_differential_fuzz_against_the_old_loop():
    rng = random.Random(0xC0FFEE)
    for _ in range(40000):
        line = ''.join(rng.choice(_ALPHABET) for _ in range(rng.randint(0, 14)))
        for in_bc in (False, True):
            got = mask_literals(line, in_bc)
            want = _oracle_mask(line, in_bc)
            assert got == want, (line, in_bc, got, want)
            masked = got[0]
            assert len(masked) == len(line), (line, in_bc)
            # every surviving character is the original one, in place
            assert all(m == NUL or m == c for m, c in zip(masked, line)), (line, in_bc)
