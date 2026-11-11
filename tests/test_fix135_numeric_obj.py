"""fix 135 (CS0019 slice): integer-only `object objN` temps become int/long."""
from il2cpp.dec.highlevel import _HighLevelMixin as H


def run(*lines):
    h = H.__new__(H)
    return h._numeric_obj_retype(list(lines))


def test_literal_and_self_arith_become_int():
    assert run('object obj1 = 0;', 'obj1 = obj1 + 1;', 'return obj1 * 2;') == [
        'int num1 = 0;', 'num1 = num1 + 1;', 'return num1 * 2;']


def test_wide_literal_becomes_long():
    assert run('object obj2 = 0x100000000;', 'if (obj2 >> 3 > 5)') == [
        'long num1 = 0x100000000;', 'if (num1 >> 3 > 5)']


def test_chain_through_int_local_and_fresh_num_index():
    assert run('int num4 = 1;', 'object obj13 = num4 << 2;', 'obj13 += 7;') == [
        'int num4 = 1;', 'int num5 = num4 << 2;', 'num5 += 7;']


def test_reference_uses_keep_object():
    for src in (
        ('object obj4 = 1;', 'obj4.ToString();'),
        ('object obj5 = 1;', 'if (obj5 != null)'),
        ('object obj7 = 3;', 'Bar(&obj7);'),
        ('object obj8 = 3;', 'var x = __addr(obj8 + 0x10);'),
        ('object obj9 = 3;', 'var y = (Foo)obj9;'),
    ):
        assert run(*src) == list(src)


def test_unproven_defs_keep_object():
    for src in (
        ('object obj6 = Foo();', 'return obj6 + 1;'),
        ('object obj10 = obj11;', 'object obj11 = obj10;'),
        ('object obj12 = "7";', 'return obj12 + 1;'),
    ):
        assert run(*src) == list(src)


def test_float_lanes_become_real():
    # fix 136: float literals / float locals type the temp float/double
    assert run('object obj1 = 0.5f;', 'if (obj1 > 0.6f)', 'obj1 = obj1 * 2;') == [
        'float real1 = 0.5f;', 'if (real1 > 0.6f)', 'real1 = real1 * 2;']
    assert run('float real3 = 1f;', 'object obj2 = real3 + 1;') == [
        'float real3 = 1f;', 'float real4 = real3 + 1;']
    assert run('object obj4 = 1.5;', 'return obj4 / 2;') == [
        'double real1 = 1.5;', 'return real1 / 2;']


def test_float_temp_used_bitwise_keeps_object():
    src = ('object obj5 = 1.5f;', 'x = obj5 & 3;')
    assert run(*src) == list(src)
