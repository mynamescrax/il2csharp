"""Proof of the address and of the zero must hold together at the store."""
import pytest
from iced_x86 import Decoder

from il2cpp.byref_zero import _scan


def sites(code, *, init=None, pads=()):
    insns = list(Decoder(64, bytes.fromhex(code), ip=0x1000))
    return _scan(insns, {'RDX': ('day', '0'), 'R8': ('money', '0f')}, init, pads)


def test_qword_aliases_across_conditional_init_call():
    # Preserve both byrefs in nonvolatile registers across a forward guard.
    proof = sites('4c8bfa 4d8bf0 7505 e800000000 31ff 41893f 41893e', init=0x100d)
    assert list(proof.values()) == [('day', '0'), ('money', '0f')]
    assert list(sites('41c70000000000').values()) == [('money', '0f')]


@pytest.mark.parametrize('code', [
    '75024c8bfa 31ff 41893f',  # branch lands in the middle of a copy
    '448bfa 31ff 41893f',      # truncated byref copy
    '31ff 897a04',              # interior offset
    '31ff 893c0a',              # indexed destination
    '31ff 66893a',              # half of the pointee
    '31ff 48893a',              # two dwords
    'bf01000000 893a',          # not zero
    '6631ff 893a',              # only the low word is zero
    '31ff 893a ebfa',           # loop re-enters the prefix
    '31ff 893a ffe0',           # possible indirect edge
    'e800000000 31ff 893a',    # volatile byref lost at init call
])
def test_unproven_store_is_left_raw(code):
    assert not sites(code, init=0x1005)


def test_join_requires_both_paths_and_eh_is_not_method_entry():
    assert not sites('7503 4c8bfa 31ff 41893f')  # one path never copied RDX into R15
    assert not sites('7502 31ff 893a')            # one path never zeroed EDI
    assert not sites('31ff 893a', pads=[0x1002])
