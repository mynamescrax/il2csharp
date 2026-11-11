"""Dead-`unknown`-store elimination pinned on LagCompensationUtils 63027
(`vector32 = unknown;` + `vector32 = 0;` twins) and RaycastModifier
105455 (`object obj87 = unknown;` + `obj87 = 0;` strip, plus a use-site
that must survive).
"""
import re

import pytest

from test_game_goldens import game_decompiler


pytestmark = pytest.mark.game


def test_lagcomp_twins_drop_first_store(game_decompiler):
    il, dec = game_decompiler
    m = il.meta.methods[63027]
    assert m.name == 'ClosestDistanceBetweenLines'
    body = '\n'.join(dec.lift_method(m, il.meta.typedefs[m.declaring]))
    assert body.count('vector32 = unknown;') == 3
    assert 'vector32 = 0;' in body
    # non-twins keep their honest spelling (different next LHS, use of
    # the value, typed decl without a same-name overwrite)
    assert 'vector31 = unknown;' in body
    assert 'float real8 = unknown;' in body


def test_raycast_use_site_survives_and_is_now_typed(game_decompiler):
    """mi 105455 ValidateLine (`lea rbp,[rsp-70h]`, 486 lines).

    This method used to carry an `object obj87 = unknown;` + `obj87 = 0;`
    twin pair whose declaration the dead-store pass stripped to a bare
    `object obj87;`, with `Vector3 vector35 = obj87.normalized;` surviving as
    the use-site. Recovering the frame retyped those slots: they are
    UnityEngine.Vector3 homes, so the object twin no longer exists and the
    use-site now reads a typed receiver. The dead-unknown-store pass itself
    stays pinned by test_lagcomp_twins_drop_first_store above.
    """
    il, dec = game_decompiler
    m = il.meta.methods[105455]
    assert m.name == 'ValidateLine'
    body = '\n'.join(dec.lift_method(m, il.meta.typedefs[m.declaring]))
    # the honest unmodelled store survives
    assert body.count('vector34 = unknown;') == 2
    assert 'vector32 = unknown;' in body
    # the use-site survives, now through a typed Vector3 receiver
    assert 'UnityEngine.Vector3 vector36 = vector34.normalized;' in body
    # no object-typed unknown twin is left in this method
    assert not re.search(r'\bobject obj87\b', body)
    assert not re.search(r'\bobject \w+ = unknown;', body)
    assert '= unknown;' in body
