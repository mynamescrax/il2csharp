from types import SimpleNamespace as NS

import pytest
from iced_x86 import Decoder

from il2cpp.generic_array import _saved_array_loads


def array_seed(*, back='', entry=None, copy='4c8bf0', pads=()):
    # R14 receives the array call's RAX; at the read there can be an
    # initial path, a loop back edge, and (in the negative case) a bypass.
    segments = [('90', [1] if entry is None else [1,2]), ('e800100000 33c9 '+copy, [2]),
                ('498b5cfe20', [3,4]), (back+' 90',[2]), ('c3',[])]
    blocks=[]; ip=0x1000
    for raw, succs in segments:
        seq=list(Decoder(64,bytes.fromhex(raw),ip=ip)); ip=seq[-1].next_ip
        blocks.append(NS(insns=seq, succs=succs))
    sites=_saved_array_loads(blocks,blocks[1],0,pads)
    return blocks[2].insns[0].ip in sites


def test_unwritten_nonvolatile_keeps_array_on_every_iteration():
    assert array_seed(back='e800200000')  # call preserves R14 under Win64


@pytest.mark.parametrize('changes',[dict(back='41b601'), dict(back='4c8bf1'), dict(entry='bypass'),
                                    dict(copy='448bf0'), dict(copy='488bc1 4c8bf0'), dict(pads=(3,))])
def test_unproven_array_on_any_edge_declines(changes):
    assert not array_seed(**changes)
