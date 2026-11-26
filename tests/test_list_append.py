from types import SimpleNamespace as NS

import pytest
from iced_x86 import Decoder

from il2cpp.list_append import _saved_this


@pytest.mark.parametrize('case',['dominating save','bypassed save','replaced this','call before capture'])
def test_terminal_epilogue_rejects_unrelated_receivers_and_bypassed_saves(case):
    # Some predecessors in the real CFG are unreachable metadata-init arms.
    # A reachable bypass is different: restoring RDI there isn't a no-op.
    prefix='53 4883ec20 '+('e800000000 ' if case=='call before capture' else '')+'488bd9'
    parts=[prefix,'48897c2430','488bcb' if case!='replaced this' else '488bd8','90']
    blocks=[];ip=0x1000
    for j,part in enumerate(parts):
        raw=bytes.fromhex(part); blocks.append(NS(bid=j,insns=list(Decoder(64,raw,ip=ip)),succs=[j+1] if j<3 else []));ip+=len(raw)
    if case=='bypassed save':blocks[0].succs.append(2)
    assert _saved_this(blocks,blocks[-1].insns[0].ip)==(case=='dominating save')
