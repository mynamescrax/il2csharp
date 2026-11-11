"""Dec F5 red/green pins: literal/comment-blind substitutions stay out.

Each family x {plain string, verbatim string, line comment,
block comment} asserts byte-identity (RED today), plus code-fire
counterparts asserting today's fold still fires. F5-4 green asserts
the literal survives AND the fold still declines (decline
preservation). Instantiation follows tests/test_literal_safety.py
(Decompiler.__new__ doubles, no fixture).
"""
from il2cpp import Decompiler


def render1(ln):
    return Decompiler.__new__(Decompiler)._render([ln])[0]


def fold_consts(ln):
    return Decompiler._fold_consts(ln)


def test_fold_consts_string_untouched():
    assert fold_consts('Log("(2 + 3)");') == 'Log("(2 + 3)");'


def test_fold_consts_verbatim_string_untouched():
    assert fold_consts('s = @"(2 + 3)";') == 's = @"(2 + 3)";'


def test_fold_consts_line_comment_untouched():
    assert fold_consts('// (4 * 5)') == '// (4 * 5)'


def test_fold_consts_block_comment_untouched():
    assert fold_consts('/* (4 * 5) */') == '/* (4 * 5) */'


def test_fold_consts_code_still_fires():
    assert fold_consts('x = (2 + 3);') == 'x = 5;'


def test_sub_cmp_string_untouched():
    assert fold_consts('s = "num1 - 1 == 2";') == 's = "num1 - 1 == 2";'


def test_sub_cmp_code_still_fires():
    assert fold_consts('x = num1 - 1 == 2;') == 'x = num1 == 3;'


def test_unsafify_dstar_string_untouched():
    d = Decompiler.__new__(Decompiler)
    assert d._unsafify('Log("*obj5");') == 'Log("*obj5");'


def test_unsafify_nconst_string_untouched():
    d = Decompiler.__new__(Decompiler)
    assert d._unsafify('Log("*16");') == 'Log("*16");'


def test_unsafify_cast_nconst_string_untouched():
    d = Decompiler.__new__(Decompiler)
    assert d._unsafify('x = "(uint*)*16";') == 'x = "(uint*)*16";'


def test_unsafify_code_still_fires():
    d = Decompiler.__new__(Decompiler)
    assert d._unsafify('x = *obj5;') == 'x = ((byte*)obj5)[0];'


def test_render_question_addr_string_untouched():
    assert render1('s = "?addr";') == 's = "?addr";'


def test_render_question_addr_comment_untouched():
    assert render1('// ?addr here') == '// ?addr here'


def test_render_unknown_collapse_string_untouched():
    assert render1('s = "unknown unknown";') == 's = "unknown unknown";'


def test_render_default_op_string_untouched():
    assert render1('s = "default > x";') == 's = "default > x";'


def test_render_rconst_string_untouched():
    assert render1('s = "return *16;";') == 's = "return *16;";'


def test_render_question_addr_code_still_elides():
    assert render1('?addr = v;') == '/* store into untracked ?addr elided */'


def test_concat_name_in_string_untouched():
    assert (Decompiler._fold_concat('s = "use System.String.Concat(a, b) ok";')
            == 's = "use System.String.Concat(a, b) ok";')


def test_concat_code_still_fires():
    assert (Decompiler._fold_concat('x = System.String.Concat(a, b);')
            == 'x = (a + b);')


def test_format_name_in_string_untouched():
    d = Decompiler.__new__(Decompiler)
    assert (d._format_interp('s = "use System.String.Format("{0}", x) ok";')
            == 's = "use System.String.Format("{0}", x) ok";')


def test_foreach_string_counter_declines():
    dec = Decompiler.__new__(Decompiler)
    dec.L = __import__('types').SimpleNamespace(
        slot_types={}, _var_types={}, _type_hints={})
    dec._var_types = {}
    loop = ['for (int v0 = 0; v0 < arr.Length; v0++)', '{',
            '    Log("arr[v0]");', '}']
    out = dec._foreach_sugar(list(loop))
    assert out == loop
