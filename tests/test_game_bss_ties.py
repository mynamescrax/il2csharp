"""BSS runtime-cell annotations decline ambiguous non-System names.

Several same-named typedefs with no System-namespace candidate give no
proof of which row the runtime lookup filled; the old first-row pick is a
plausible-wrong `typeof(...)`. No cell may keep such an annotation.
"""
import re

import pytest

from test_game_goldens import game_decompiler

pytestmark = pytest.mark.game


def test_no_bss_cell_keeps_an_ambiguous_annotation(game_decompiler):
    il, _ = game_decompiler
    by = {}
    for i, td in enumerate(il.meta.typedefs):
        by.setdefault(td.name, []).append(i)
    amb = {n for n, v in by.items()
           if len(v) > 1
           and not any(il.meta.typedefs[i].namespace == 'System' for i in v)}
    offenders = []
    for cell, usg in (getattr(il, 'bss_usage_map', None) or {}).items():
        m = re.search(r'typeof\(([^)]+)\)', usg.get('text') or '')
        if m and m.group(1).rsplit('.', 1)[-1] in amb:
            offenders.append((hex(cell), usg.get('text')))
    assert not offenders, offenders
