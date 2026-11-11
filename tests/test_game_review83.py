"""Native-backed checks for all-candidate shared return-type consensus."""
import pytest

from test_game_goldens import game_decompiler

pytestmark = pytest.mark.game


def body(game_decompiler, mi):
    il, dec = game_decompiler
    method = il.meta.methods[mi]
    return "\n".join(dec.lift_method(method, il.meta.typedefs[method.declaring]))


def test_representative_shared_addresses_have_exact_consensus(game_decompiler):
    il, _ = game_decompiler
    expected = {
        0x181AF7520: "bool",
        0x1825B1150: "string",
        0x182BAC5E0: "float",
        0x18284DE50: "void",
    }
    assert {va: il.type_name(il.shared_return_type(va))
            for va in expected} == expected
    assert il.shared_return_type(0x180506120) is None


def test_shared_boolean_result_becomes_a_boolean_condition(game_decompiler):
    text = body(game_decompiler, 23560)
    call = 'sub_181af7520/*shared body, 2 candidates*/'
    # Fix 110 proves unanimous string equality for this shared address.
    # Keep checking boolean conditions against the current exact operator.
    assert 'if (this.animName == "walk")' in text
    assert 'else if (!(this.animName == "run"))' in text
    assert f'object obj8 = {call}' not in text


def test_typed_shared_result_stays_after_its_native_predecessor(game_decompiler):
    lines = body(game_decompiler, 31664).splitlines()
    ctor = next(i for i, line in enumerate(lines)
                if line.endswith('.ctor(shortDisplayName);'))
    # fix 104: the string decl carries its caller-proven cast now.
    result = next(i for i, line in enumerate(lines)
                  if 'string text1 = (string)sub_1825b1150/*shared body' in line)
    assert ctor < result


def test_shared_void_result_is_kept_as_a_side_effect(game_decompiler):
    text = body(game_decompiler, 32833)
    call = 'sub_182695690/*shared body, 2 candidates*/(&obj3, 0);'
    assert text.count(call) == 2
    assert f'object obj' not in '\n'.join(
        line for line in text.splitlines() if 'sub_182695690' in line)


def test_shared_float_result_uses_xmm0_and_float_locals(game_decompiler):
    text = body(game_decompiler, 109695)
    call = 'sub_182bac5e0/*shared body, 2 candidates*/'
    assert text.count(f'float real') >= 5
    assert text.count(call) == 5
    assert 'ID_GradientScale, real1);' in text
    assert f'object obj25 = {call}' not in text


def test_shared_struct_return_uses_buffer_and_trims_stale_registers(game_decompiler):
    text = body(game_decompiler, 32174)
    call = 'sub_1825bd360/*shared body, 2 candidates*/'
    # fix 97: the shared results now carry declarations (and the first a
    # semantic name); the buffer-and-trim proof is unchanged.
    # fix 104: both carry caller-proven casts (decl and mapped assign).
    pv = '(UnityEngine.InputSystem.Utilities.PrimitiveValue)'
    assert f'PrimitiveValue primitiveValue1 = {pv}{call}(0);' in text
    assert f'primitiveValue1 = {pv}{call}(1);' in text
    assert f'{call}(0, 0' not in text


def test_frame_copy_homes_observe_sret_buffers(game_decompiler):
    text = body(game_decompiler, 108722)
    call = 'sub_182539ee0/*shared body, 2 candidates*/'
    # RSP-copy round: `mov rax,rsp` homes are observed slots now, so both
    # native address triples render. Native site 1 passes
    # [rax-28h]/[rax-38h]/[rax-48h] (0x182529283-297); the hidden buffer is
    # consumed by the sret proof and the two value homes print. The old
    # `(default, default, default)` spelling was untracked-copy blindness,
    # not an unobserved buffer (the homes hold a/b.Byte0 provably). The
    # unobserved stand-downs stay pinned portably (unknown receiver/size).
    assert 'mem[8' not in text and 'mem_8' not in text
    assert f'Unity.Burst.Intrinsics.v128 v1281 = (Unity.Burst.Intrinsics.v128){call}(&obj6, &obj5);' in text
    assert f'Unity.Burst.Intrinsics.v128 v1282 = (Unity.Burst.Intrinsics.v128){call}(&obj5, &obj6);' in text
