"""Literal-parsing regressions for Review 86 (fixes 87, 88, 89).

fix 87 -- `_int_lit` treated `d`/`f` as float suffixes and stripped them
          from hex literals too, so `0x3d` parsed as 3 and `0xf` did not
          parse at all.
fix 88 -- `lea r,[reg+N]` with a literal base is how the compiler
          materialises a small constant. Unfolded it reached every
          literal consumer as the composite text `(0 + 0x3)`, which none
          of them could parse -- that is why `FileMode.Open` printed as a
          bare `3`.
fix 89 -- signed immediates arrive as unsigned bit patterns at every
          width, not only Int16, so `-2` printed as `4294967294`.
"""
import pytest

from il2cpp import Lifter, _int_lit

from test_native_values import INT, execute, lifter

SBYTE = (0, 0x04 << 16)
SHORT = (0, 0x06 << 16)
LONG = (0, 0x0A << 16)
UINT = (0, 0x09 << 16)


@pytest.mark.parametrize('text,expected', [
    # `d` and `f` are hex digits, not float suffixes -- fix 87
    ('0x3d', 61),
    ('0xf', 15),
    ('0xF', 15),
    ('0x7f', 127),
    ('0xdd', 221),
    ('0x2d', 45),
    ('-0x10', -16),
    # decimal text may still carry a float suffix, and `_fold_bin`'s
    # identity rules depend on `0f`/`0d` staying parseable
    ('0f', 0),
    ('0d', 0),
    ('1f', 1),
    ('1d', 1),
    # genuinely non-integer text stays unparseable
    ('1.5f', None),
    ('', None),
    ('obj1', None),
    ('this.value', None),
    # plain decimals are untouched
    ('0', 0),
    ('255', 255),
])
def test_int_lit_parses_hex_digits_that_look_like_float_suffixes(text, expected):
    assert _int_lit(text) == expected


@pytest.mark.parametrize('src,ty,expected', [
    ('4294967294', INT, '-2'),
    ('4294967295', INT, '-1'),
    ('2147483648', INT, '-2147483648'),
    ('254', SBYTE, '-2'),
    ('65534', SHORT, '-2'),
    ('18446744073709551614', LONG, '-2'),
    # values already in range round trip unchanged, so only a genuine
    # wrap is ever rewritten
    ('5', INT, '5'),
    ('-2', INT, '-2'),
    ('0', INT, '0'),
    # an unsigned declaration keeps the unsigned reading
    ('4294967294', UINT, '4294967294'),
    # no declared type means no proof of signedness
    ('4294967294', None, '4294967294'),
])
def test_signed_immediates_are_read_at_their_declared_width(src, ty, expected):
    assert Lifter.__new__(Lifter)._fimm(src, ty) == expected


def test_lea_with_a_literal_base_folds_to_the_constant_it_materialises():
    """`xor eax,eax; lea r8d,[rax+3]` materialises the constant 3."""
    lift = lifter(fields={0x10: ('value', 0)}, field_types=[INT])
    # xor eax,eax / lea r8d,[rax+3] / mov [rcx+0x10],r8d
    assert execute(lift, '31c0' + '448d4003' + '44894110') == ['this.value = 3;']
