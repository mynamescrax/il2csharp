"""Fix 138: for-head counters that outlive the loop are declared.

Ground truth (disasm):
- ConstrictedInteractable.CheckForCurItem 0x18069DF80: the search index
  is live after the loop (passed to the next call), so `_for_sugar` keeps
  it out of the head's declaration; it is now declared `int num2;` on the
  line before the head instead of being read undeclared (CS0103 x4).
- Microsoft.Win32.RegistryKey.FixupPath (mscorlib, mi 516): the inner
  backslash loop's index is read after the loop (`num6 = num10;`); fix
  137 made its condition pure (`path[num10] == 92`) so the loop resugared
  while->for, exposing the same undeclared head.
"""
import re

import pytest

from test_game_goldens import game_decompiler

pytestmark = pytest.mark.game


def _lift(il, dec, mi, name):
    m = il.meta.methods[mi]
    assert m.name == name
    return dec.lift_method(m, il.meta.typedefs[m.declaring])


def _declared_before_head(lines, head_rx):
    for i, ln in enumerate(lines):
        m = re.match(head_rx, ln.strip())
        if m:
            nm = m.group(1)
            return lines[i - 1].strip() == 'int %s;' % nm
    raise AssertionError('head not found')


def test_search_index_declared_before_head(game_decompiler):
    il, dec = game_decompiler
    lines = _lift(il, dec, 24664, 'CheckForCurItem')
    assert _declared_before_head(lines, r'^for \((num\d+) = 0; \1 < num\d+; \1\+\+\)$')


def test_fixup_path_inner_index_declared(game_decompiler):
    il, dec = game_decompiler
    lines = _lift(il, dec, 516, 'FixupPath')
    assert _declared_before_head(lines, r'^for \((num\d+) = num\d+ \+ 1; path\[\1\] == 92; \1\+\+\)$')
