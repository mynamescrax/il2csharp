"""Dec F5 residuals R1-R4: comment/string-blind substitutions stay out.

R1 `_fix_select`, R2 `_strip_dangling_default` and R3 `_rewrite_unknowns`
rewrote `?`/`: default`/`?`-operand marks inside comments because they
matched raw line text (quote-only `_in_string` + comment-blind paren
walks). R4 `_len_sugar` matched `*(a + 0x18)` with no masking at all,
including inside string literals. Guards mirror the landed Dec F5 fix:
match on the NUL mask, splice into the original. Each family pins
byte-identity over {plain string, verbatim string, line comment, block
comment} plus a code-fire control asserting today's fold still fires.
Instantiation follows tests/test_decF5_literal_blind.py
(Decompiler.__new__ doubles, no fixture).
"""
from il2cpp import Decompiler


def fix_select(ln):
    return Decompiler.__new__(Decompiler)._fix_select(ln)


def render1(ln):
    return Decompiler.__new__(Decompiler)._render([ln])


def len_sugar(cond):
    d = Decompiler.__new__(Decompiler)
    d._var_types = {}
    return d._len_sugar(cond)


def test_r1_line_comment_untouched():
    assert fix_select('x = 1; // (c ? d)') == 'x = 1; // (c ? d)'


def test_r1_block_comment_untouched():
    assert fix_select('x = 1; /* (c ? d) */') == 'x = 1; /* (c ? d) */'


def test_r1_string_untouched():
    assert fix_select('s = "(c ? d)";') == 's = "(c ? d)";'


def test_r1_verbatim_untouched():
    assert fix_select('s = @"(c ? d)";') == 's = @"(c ? d)";'


def test_r1_code_still_fires():
    assert fix_select('x = (c ? y);') == 'x = (c ? y : default);'


def test_r2_line_comment_untouched():
    assert render1('x = 1; // y : default') == ['x = 1; // y : default']


def test_r2_block_comment_untouched():
    assert render1('x = 1; /* y : default */') == ['x = 1; /* y : default */']


def test_r2_string_untouched():
    assert render1('s = "a : default";') == ['s = "a : default";']


def test_r2_code_still_fires():
    assert render1('return x : default;') == ['return x ;']


def test_r3_line_comment_untouched():
    assert render1('x = 1; // (? + b)') == ['x = 1; // (? + b)']


def test_r3_equals_comment_untouched():
    assert render1('x = 1; // = ?;') == ['x = 1; // = ?;']


def test_r3_call_comment_untouched():
    assert render1('y = f(a); // (? - c)') == ['y = f(a); // (? - c)']


def test_r3_block_comment_untouched():
    assert render1('x = 1; /* (? + b) */') == ['x = 1; /* (? + b) */']


def test_r3_string_untouched():
    assert render1('s = "a ? b";') == ['s = "a ? b";']


def test_r3_code_still_fires():
    assert render1('x = ? + y;') == ['x = unknown + y;']


def test_r4_string_untouched():
    assert len_sugar('s == "i < *(a + 0x18)"') == 's == "i < *(a + 0x18)"'


def test_r4_verbatim_untouched():
    assert len_sugar('s = @"i < *(a + 0x18)";') == 's = @"i < *(a + 0x18)";'


def test_r4_line_comment_untouched():
    assert len_sugar('i < *(a + 0x18)) // n < *(b + 0x18)') == \
        'i < a.Length) // n < *(b + 0x18)'


def test_r4_block_comment_untouched():
    assert len_sugar('/* n */ i < *(a + 0x18)') == '/* n */ i < a.Length'


def test_r4_code_still_fires():
    assert len_sugar('i < *(a + 0x18)') == 'i < a.Length'
