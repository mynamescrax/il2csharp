"""String/char literals and comments survive the text passes.

Two silent-corruption paths (dec audit 2026-09-28):
- `_render` replaced `$` with `_` over the whole line: JSON.NET's wire
  names became `_type`/`_id`/`_values`, the UTF7 direct-character set lost
  its `$`, and a money template became `MONEY: _`.
- `_rename_locals` collected and substituted vN/tN/s_XX tokens over whole
  lines: the ADO.NET diffgram namespace rendered `...-obj83`, and a
  literal-only token shifted the numbering.
"""
from types import SimpleNamespace as NS

from il2cpp import Decompiler


def _renderer():
    return Decompiler.__new__(Decompiler)


def _renamer():
    dec = Decompiler.__new__(Decompiler)
    dec.L = NS(slot_types={}, _var_types={}, _type_hints={})
    dec._var_types = {}
    return dec


def test_render_keeps_dollar_inside_literals_and_comments():
    lines = ['f("$5");', 's = "urn:x-$id";', "c = '$';", '// $keep']
    assert _renderer()._render(lines) == lines


def test_render_sanitizes_dollar_in_code():
    assert _renderer()._render(['x = $BurstManaged;']) == ['x = _BurstManaged;']


def test_render_keeps_interpolation_prefixes():
    d = _renderer()
    assert d._sanitize_dollar('y = $"a{b}";') == 'y = $"a{b}";'
    assert d._sanitize_dollar('y = $@"a""b";') == 'y = $@"a""b";'


def test_rename_locals_keeps_literal_tokens():
    dec = _renamer()
    assert dec._rename_locals(['v1 = "$type v1";', 'Use(v1);']) == \
        ['object obj1 = "$type v1";', 'Use(obj1);']


def test_rename_locals_keeps_comments_and_skips_literal_only_tokens():
    dec = _renamer()
    assert dec._rename_locals(['F("v1");', 'v2 = G();', '// v1 comment']) == \
        ['F("v1");', 'object obj1 = G();', '// v1 comment']
