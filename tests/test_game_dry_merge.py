"""Dry-pass merge keeps frame addresses and unanimous stack tiles.

Pass 1 rebuilt every merged value from its text alone, so an RBP / RSP-copy
base lost `_stack_offset` at the first CFG merge and every later [base+N]
fell to the legacy disp-keyed slot: the dry back-edge carried no `!mem:`
tile and a different slot name than pass 2 (s_50 vs s_b0).
"""
import pytest

from test_game_goldens import game_decompiler

pytestmark = pytest.mark.game


def _owner(cls, name):
    for c in cls.__mro__:
        if name in c.__dict__:
            return c
    raise AssertionError(name)


def test_dry_sret_buffer_keeps_frame_address(game_decompiler, monkeypatch):
    il, dec = game_decompiler
    m = il.meta.methods[29353]
    owner = _owner(type(dec.L), '_call')
    orig = owner.__dict__['_call']
    seen = []

    def spy(self, ins, asm):
        if ins.ip == 0x180646d04:
            e = self.regs.get('RCX')
            seen.append((bool(self.dry), e.text if e is not None else None,
                         getattr(e, '_stack_offset', None)))
        return orig(self, ins, asm)

    monkeypatch.setattr(owner, '_call', spy)
    dec.lift_method(m, il.meta.typedefs[m.declaring])
    assert (True, '&s_b0', -632) in seen
    assert (False, '&s_b0', -632) in seen


def test_loop_invariant_this_is_not_a_phi(game_decompiler):
    il, dec = game_decompiler
    m = il.meta.methods[5694]
    assert m.name == "AppendFormatHelper"
    text = "\n".join(dec.lift_method(m, il.meta.typedefs[m.declaring]))
    assert "this.Append(character2)" in text
    assert "System.Text.StringBuilder stringBuilder1 = this;" not in text
