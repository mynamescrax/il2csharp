"""Fix 141: no stale-register spray on indirect calls (ground truth).

EncryptorNative.egconstructEncryptor2 0x18061CDD0:
    mov rax,[183E72558h]        ; cached function pointer
    test rax,rax
    jne  0x18061CE53
    ... resolve_icall ...
    mov [183E72558h],rax
0x18061CE53: ... call rax        ; rcx/rdx/r8/r9 are the four real args

The resolver call clobbers the volatile XMM registers; one arm of the guard
leaves them missing, the other carries explicit `_unk` seeds. The join used
to mint untyped phis (v54..v57) that the argument builder printed as
trailing `obj18..obj21`. They are unknown and must not be arguments.
"""
import re

import pytest

from test_game_goldens import game_decompiler

pytestmark = pytest.mark.game


def _lift(il, dec, mi, name):
    m = il.meta.methods[mi]
    assert m.name == name
    return [ln.strip() for ln in dec.lift_method(m, il.meta.typedefs[m.declaring])]


def _top_level_args(call):
    """Split the argument list of a one-line call into top-level items."""
    marker = call.index('/*indirect*/') + len('/*indirect*/')
    start = call.index('(', marker) + 1
    depth = 0
    args, cur = [], []
    for ch in call[start:]:
        if ch == '(':
            depth += 1
        elif ch == ')':
            if depth == 0:
                break
            depth -= 1
        if ch == ',' and depth == 0:
            args.append(''.join(cur).strip())
            cur = []
        else:
            cur.append(ch)
    if ''.join(cur).strip():
        args.append(''.join(cur).strip())
    return args


def test_guard_join_does_not_spray_xmm_unknowns(game_decompiler):
    il, dec = game_decompiler
    lines = _lift(il, dec, 28594, 'egconstructEncryptor2')
    calls = [ln for ln in lines if '/*indirect*/' in ln]
    assert len(calls) == 1
    args = _top_level_args(calls[0])
    assert len(args) == 4, calls[0]
    assert args[-1] == 'mtu'
    assert not any('obj18' in a or 'obj19' in a or 'obj20' in a or 'obj21' in a
                   for a in args)


def test_delegate_invoke_drops_the_unknown_tail(game_decompiler):
    # FusionNetworkManager.Update 0x180560FF0: the cached delegate invoke
    # takes method_code, _obj and method only; the old spelling added a
    # fourth stale `objN` from the guard join.
    il, dec = game_decompiler
    lines = _lift(il, dec, 26440, 'Update')
    calls = [ln for ln in lines
             if 'pendingSpawnCallback1._callback + 0x18' in ln]
    assert len(calls) == 1, calls
    assert calls[0].endswith('_callback.method);')
    assert re.search(r', obj\d+\);$', calls[0]) is None
