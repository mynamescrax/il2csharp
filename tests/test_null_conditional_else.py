"""A null-conditional call cannot stand in for an if that owns an else."""
import pytest

from il2cpp import Decompiler


@pytest.mark.parametrize('tail', [[], [''], ['// retain the fallback']])
@pytest.mark.parametrize('alternative', ['else', 'else if (fallback)'])
def test_keep_null_guard_with_alternate(tail, alternative):
    dec = Decompiler.__new__(Decompiler)
    lines = ['if (x != null)', '{', '    x.Write();', '}', *tail, alternative,
             '{', '    WriteNull();', '}']
    assert dec._null_conditional(lines) == lines


def test_null_conditional_at_end_of_block():
    dec = Decompiler.__new__(Decompiler)
    assert dec._null_conditional(['if (x != null)', '{', '    x.Write();', '}']) == ['x?.Write();']
    assert dec._null_conditional(['if (x == null)', '{', '}', 'else', '{', '    x.Write();', '}']) == ['x?.Write();']
