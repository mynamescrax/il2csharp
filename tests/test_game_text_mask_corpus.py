"""Masker differential over the promoted tree (read-only `final_out/`).

Every line of every Nth file goes through the old character loop and the
shared regex masker, in both entry states and with block-comment state
threaded down the file the way a method body threads it. The full tree
(11,183 files, 3,056,380 lines) was proven identical when the masker
landed; this samples it so the check stays cheap.
"""
import os

import pytest

from il2cpp.text import mask_literals
from test_text_mask import _oracle_mask

pytestmark = pytest.mark.game

ROOT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'final_out')
STRIDE = 25


def _files():
    paths = []
    for dp, _dn, fn in os.walk(ROOT):
        paths.extend(os.path.join(dp, f) for f in fn if f.endswith('.cs'))
    paths.sort()
    return paths[::STRIDE]


def test_sampled_final_out_lines_mask_identically():
    if not os.path.isdir(ROOT):
        pytest.skip('final_out/ not present')
    paths = _files()
    assert paths, 'final_out has no .cs files'
    lines = spans = 0
    for p in paths:
        with open(p, 'r', encoding='utf-8', errors='replace', newline='') as f:
            text = f.read()
        want_bc = got_bc = False
        for line in text.split('\n'):
            lines += 1
            for bc in (False, True):
                assert mask_literals(line, bc) == _oracle_mask(line, bc), (p, line[:120], bc)
            want, want_bc = _oracle_mask(line, want_bc)
            got, got_bc = mask_literals(line, got_bc)
            assert (got, got_bc) == (want, want_bc), (p, line[:120])
            if NUL_IN(got):
                spans += 1
    assert lines > 50000 and spans > 1000


def NUL_IN(s):
    return '\x00' in s
