"""Exact shared identity leaves copy their input without naming an owner."""
import pytest

from test_game_goldens import game_decompiler

pytestmark = pytest.mark.game


def body(game_decompiler, mi, name, va):
    il, dec = game_decompiler
    method = il.meta.methods[mi]
    assert method.name == name
    assert hex(method.addr) == va
    return '\n'.join(dec.lift_method(method, il.meta.typedefs[method.declaring]))


def test_pure_first_argument_copies_and_effectful_second_site_declines(game_decompiler):
    text = body(game_decompiler, 104303, '<FindGraphWhichInheritsFrom>b__0',
                '0x180722590')
    assert 'System.Type type1 = this.type;' in text
    assert text.count('sub_18063ac90/*shared body, 1806 candidates*/') == 1
    assert 'graph.GetType()' in text


def test_event_pointer_copy_keeps_its_pointee_type(game_decompiler):
    text = body(game_decompiler, 32833, 'OnStateEvent', '0x18264a0d0')
    assert 'InputEvent* inputEventPtr2 = eventPtr.m_EventPtr;' in text
    assert 'sub_18063ac90/*shared body' not in text
