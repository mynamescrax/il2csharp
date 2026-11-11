"""Fix 139: the inlined interface-table scan is pruned to the resolve arm.

Ground truth: FusionNetworkManager.Update 0x1805611c7..0x18056127f (the
bytes below, verbatim from the fixture binary). `mov r10,[rbx]` loads the
klass; `movzx r9d,word [r10+12Eh]` / `cmp cx,r9w; jae MISS` is the entry
test; the loop compares `[r8+rax*8]` against typeof(INetworkTRSPTeleport);
the hit arm folds `shl 4; add 138h; add r10` and jumps to the join; the
miss arm calls the resolve helper 0x18043DC60 and falls into the join,
which `call [rax]`s the entry. Forcing the test onto the miss arm leaves
one definition of the entry at the join.
"""
import pytest

from il2cpp.prelude import HAVE_ICED

pytestmark = pytest.mark.skipif(not HAVE_ICED, reason='iced_x86 required')

BASE = 0x1805611c7
CODE = bytes.fromhex(
    '4c8b1333c90f1075b78b75c70f287dd7450fb78a2e010000488b15c2db6c0366413bc9'
    '731c4d8b82b00000000fb7c14803c0493914c0746166ffc166413bc972eb4533c0488b'
    'cbe84dcaedff4c8b48084c8d45e7488d55a70f2975e7488bcb8975f7660f7f7da7ff10'
    '0f28bc24b00000000f28b424c0000000488b450f4885c00f84defeffff4c8b4028488b'
    'd7488b4840ff5018e9cbfeffff0fb7c94803c9496344c80848c1e0044805380100004903'
    'c2eb99e83144edffcc')
HELPER = 0x18043DC60
NAMES = {HELPER: 'il2cpp_interface_get_method'}


def _blocks(code):
    from iced_x86 import Decoder, DecoderOptions
    from il2cpp import Decompiler
    dec = Decoder(64, code, DecoderOptions.NONE)
    dec.ip = BASE
    insns = list(dec)

    class _D:
        eh = None
    d = _D()
    d.entry_ip = insns[0].ip
    d.last_ip = insns[-1].next_ip
    blocks, bmap = Decompiler._make_blocks(d, insns, set())
    return blocks, bmap


def _patched(old_hex, new_hex):
    code = CODE.hex()
    assert code.count(old_hex) == 1
    return bytes.fromhex(code.replace(old_hex, new_hex))


def test_entry_test_forced_onto_resolve_arm():
    from il2cpp.dec.ifaceprune import iface_fast_path_prune
    blocks, bmap = _blocks(CODE)
    entry, miss = bmap[BASE], bmap[0x180561208]
    loop, hit = bmap[0x1805611f3], bmap[0x180561260]
    join = bmap[0x180561213]
    skip = set()
    assert iface_fast_path_prune(blocks, NAMES, skip=skip) == 1
    assert blocks[entry].term == ('jmp', miss)
    assert blocks[entry].succs == [miss]
    assert blocks[loop].term == ('abort',) and not blocks[loop].succs
    assert blocks[hit].term == ('abort',) and not blocks[hit].succs
    assert blocks[join].preds == [miss]
    assert blocks[miss].preds == [entry]
    # the forced test's interface-count load and compare are dead
    assert skip == {0x1805611d7, 0x1805611e6}


def test_other_helper_declines():
    from il2cpp.dec.ifaceprune import iface_fast_path_prune
    blocks, bmap = _blocks(CODE)
    assert iface_fast_path_prune(blocks, {}) == 0
    assert blocks[bmap[BASE]].term[0] == 'jcc'


def test_store_in_scan_declines():
    from il2cpp.dec.ifaceprune import iface_fast_path_prune
    # `cmp [r8+rax*8],rdx` -> `mov [r8+rax*8],rdx`: the scan is no longer pure
    blocks, bmap = _blocks(_patched('493914c0', '498914c0'))
    assert iface_fast_path_prune(blocks, NAMES) == 0
    assert blocks[bmap[BASE]].term[0] == 'jcc'


def test_live_callee_saved_write_declines():
    from il2cpp.dec.ifaceprune import iface_fast_path_prune
    # `inc cx` -> `inc bx`: the scan writes RBX, which the join reads
    # (`mov rcx,rbx`) -- the two arms no longer agree on it
    blocks, bmap = _blocks(_patched('66ffc1', '66ffc3'))
    assert iface_fast_path_prune(blocks, NAMES) == 0
    assert blocks[bmap[BASE]].term[0] == 'jcc'


def test_count_read_on_miss_arm_keeps_test():
    from il2cpp.dec.ifaceprune import iface_fast_path_prune
    # `xor r8d,r8d` -> `mov r8,r9`: the miss arm reads the count register,
    # so its load must still lift (the prune itself stays sound)
    blocks, bmap = _blocks(_patched('4533c0488bcbe8', '4d8bc1488bcbe8'))
    skip = set()
    assert iface_fast_path_prune(blocks, NAMES, skip=skip) == 1
    assert skip == set()
