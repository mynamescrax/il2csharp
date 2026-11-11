"""Array receivers resolve Clone; exact string twins use their shared semantics.

Ground truth: `sub_181c07770` folds 9 instance Clone() bodies. A byte[]
field home (275/326) or Delegate[] home (4047) can only dispatch to
System.Array.Clone -- arrays have no subclasses. The 2-candidate
string twins (144, Equals/op_Equality over one typedef) cannot be
identified individually, but their shared equality behavior is exact.
"""
import pytest

from test_game_goldens import game_decompiler

pytestmark = pytest.mark.game


def lift_text(game_decompiler, mi, name, va):
    il, dec = game_decompiler
    m = il.meta.methods[mi]
    assert m.name == name
    assert hex(m.addr) == va
    return '\n'.join(dec.lift_method(m, il.meta.typedefs[m.declaring]))


def test_byte_array_field_clones_through_array(game_decompiler):
    text = lift_text(game_decompiler, 275, 'get_Value', '0x181ad0920')
    assert 'object obj4 = this.m_aValue.Clone();' in text
    assert 'shared body' not in text


def test_second_byte_array_owner_clones_through_array(game_decompiler):
    text = lift_text(game_decompiler, 326, 'HashFinal', '0x181ad61f0')
    assert 'object obj8 = this.state.Clone();' in text
    assert 'shared body' not in text


def test_delegate_array_clones_through_array(game_decompiler):
    text = lift_text(game_decompiler, 4047, 'GetInvocationList',
                     '0x181cff280')
    assert 'System.Delegate[] delegateArray1 = this.delegates.Clone();' \
        in text
    assert 'shared body' not in text


def test_same_typedef_string_twins_render_exact_equality(game_decompiler):
    text = lift_text(game_decompiler, 144, 'ReadReference', '0x181ae3120')
    assert text.count('this.ReadName() == ') == 5
    assert 'sub_181af7520/*shared body' not in text


def test_unrelated_receiver_proves_object_memberwise_clone(game_decompiler):
    text = lift_text(game_decompiler, 28861, 'Copy', '0x1806257b0')
    assert 'this.MemberwiseClone()' in text
    assert 'sub_181cf6c90/*shared body' not in text


def test_second_unrelated_receiver_proves_object_memberwise_clone(game_decompiler):
    text = lift_text(game_decompiler, 37793, 'Clone', '0x1823366b0')
    assert 'this.MemberwiseClone()' in text


def test_stack_value_receiver_proves_shared_getter(game_decompiler):
    text = lift_text(game_decompiler, 23106, 'IsVarFunction', '0x182e4ad70')
    assert 'styleValueHandle1.valueType' in text
    assert 'sub_1808615a0/*shared body' not in text


def test_untyped_pointer_keeps_shared_getter_marker(game_decompiler):
    text = lift_text(game_decompiler, 23105, 'ReadAsString', '0x182e4ada0')
    assert 'sub_1808615a0/*shared body, 45 candidates*/' in text


def test_resolved_getter_keeps_enum_constructor_cast(game_decompiler):
    text = lift_text(game_decompiler, 18054,
                     'UnityEngine.UIElements.IStyle.get_unitySliceType',
                     '0x182f22d60')
    assert 'styleEnum11.ctor((UnityEngine.UIElements.SliceType)(styleInt1.value),' in text
    assert 'sub_1811d8370/*shared body' not in text
    assert 'sub_1809463c0/*shared body' not in text
