from types import SimpleNamespace as NS
import struct

import pytest

from il2cpp.shared_coroutine import _START, _wrapper


def proof(*, forwarding='488bd6', prefix='', signature=_START, offset=0x10):
    # Preserve the enumerator, unwrap the receiver, then tail-call the cached
    # injected function. A read on an error arm also invalidates the proof.
    va, cell = 0x2000, 0x3000
    head = bytes.fromhex(prefix + ' 488bf2 488b4910 ' + forwarding + ' 488b05')
    code = head + struct.pack('<i', cell - (va + len(head) + 4)) + b'\xff\xe0'
    il = NS(next_method_start=lambda _:va+len(code), icall_cells={cell:signature},
            bin=NS(read=lambda p,n:code[p-va:p-va+n]))
    return _wrapper(NS(il=il), va, offset)


def test_forwarder_keeps_receiver_and_original_routine():
    assert proof()


@pytest.mark.parametrize('change', [dict(forwarding='488bd1'), dict(offset=0x18),
                                    dict(signature='Other::Start()'), dict(prefix='4c89c6'),
                                    dict(prefix='4885d275044c89c0cc')])
def test_coroutine_near_misses_decline(change):
    assert not proof(**change)
