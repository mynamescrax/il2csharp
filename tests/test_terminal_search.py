from types import SimpleNamespace as NS

from iced_x86 import Decoder
import pytest

from il2cpp.dec.search_loop import terminal_search
from test_loop_headers import _block, _decompiler


def search():
    blocks = [
        _block(0, term=('jmp', 1), succs=(1,)),
        _block(1, term=('jcc', 5, 2), cond='i >= length', succs=(5, 2), preds=(0, 3)),
        _block(2, term=('jcc', 4, 3), cond='Match(i)', succs=(4, 3), preds=(1,)),
        _block(3, term=('jmp', 1), succs=(1,), preds=(2,)),
        _block(4, stmts=('Act(i);',), term=('ret',), preds=(2,)),
        _block(5, stmts=('Miss();',), term=('jmp', 6), succs=(6,), preds=(1,)),
        _block(6, term=('ret',), preds=(5,)),
    ]
    for n in (4, 6):
        blocks[n].insns = [Decoder(64, b'\xc3', ip=blocks[n].insns[0].ip).decode()]
        blocks[n].ret = ''
    d = _decompiler(blocks, 1, {1, 2, 3}, 3)
    d.L._current_method = NS(return_type=0)
    d.L.il.types = [(0, 1 << 16)]
    d.L.il._closed_type_key = lambda t: (t[1] >> 16, 0)
    d.L.rt_wbarrier = set()
    d.phi_copies = {(1, 2): ['Enter();'], (1, 5): ['Exhausted();'], (2, 4): ['Hit();'],
                    (2, 3): ['Advance();'], (3, 1): ['i++;']}
    return d, blocks


def test_search_places_edge_effects_on_their_own_paths():
    d, bs = search(); out = []
    assert terminal_search(d, bs, 1, set(), set(), out, 0) == 5
    assert out[1:] == ['while (!(i >= length))', '{', 'Enter();', 'if (Match(i))', '{',
                       'Hit();', 'Act(i);', 'return;', '}', 'Advance();', 'i++;', '}', 'Exhausted();']
    assert not bs[5].consumed and not bs[6].consumed and not d._bstack


@pytest.mark.parametrize('invalidate', ['shared hit', 'shared miss', 'shared miss interior', 'consumed miss',
                                        'parent stop at hit', 'parent switch', 'extra preheader', 'unresolved jump',
                                        'bare nonvoid return', 'synthetic ret'])
def test_search_declines_atomically(invalidate):
    d, bs = search(); stop = set(); out = ['before']; stack = list(d._bstack)
    if invalidate.startswith('shared'):
        n = {'shared hit': 4, 'shared miss': 5, 'shared miss interior': 6}[invalidate]
        bs[n].preds.append(0)
    elif invalidate == 'consumed miss': bs[5].consumed = True
    elif invalidate == 'parent stop at hit': stop.add(4)
    elif invalidate == 'parent switch': d._sw_depth = 1
    elif invalidate == 'extra preheader': bs[1].preds.append(7)
    elif invalidate == 'bare nonvoid return': d.L.il.types[0] = (0, 8 << 16)
    else:
        bs[4].insns = [Decoder(64, b'\xff\xe0', ip=0x1040).decode()]
        if invalidate == 'unresolved jump': bs[4].term = ('stop',)
    consumed = [b.consumed for b in bs]
    assert terminal_search(d, bs, 1, stop, set(), out, 0) is None
    assert [b.consumed for b in bs] == consumed and out == ['before'] and d._bstack == stack
