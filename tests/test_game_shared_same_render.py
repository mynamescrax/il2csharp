"""Same-render shared bodies resolve without selecting an owner."""
import pytest

from test_game_goldens import game_decompiler

pytestmark = pytest.mark.game


def test_computestringhash_marker_resolves(game_decompiler):
    il, dec = game_decompiler
    method = il.meta.methods[24694]
    assert method.name == 'SetControllerLayoutText'
    text = '\n'.join(dec.lift_method(method, il.meta.typedefs[method.declaring]))
    assert 'sub_18068cbc0' not in text
    assert '<PrivateImplementationDetails>.ComputeStringHash(text1)' in text


def test_combine_markers_resolve_to_tail_name(game_decompiler):
    il, dec = game_decompiler
    method = il.meta.methods[2991]
    assert method.name == 'CombineHashCodes'
    text = '\n'.join(dec.lift_method(method, il.meta.typedefs[method.declaring]))
    assert 'sub_181bd5fe0' not in text
    assert text.count('System.Numerics.Hashing.HashHelpers.Combine') >= 2


def test_kernel_multiply_marker_resolves(game_decompiler):
    il, dec = game_decompiler
    method = il.meta.methods[422]
    assert method.name == 'op_Multiply'
    text = '\n'.join(dec.lift_method(method, il.meta.typedefs[method.declaring]))
    assert 'sub_181ac33e0' not in text
    assert 'Kernel.Multiply(' in text
