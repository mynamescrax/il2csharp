"""Renamed locals must not capture metadata parameter names.

Ground truth: StreamBuffer.WriteBytes overloads (mi 113041-113044)
take byte params named v0..v7. The renamer rewrote body uses to
obj5/obj6 (emitter keeps v0/v1), disconnecting every argument and
leaving spine temps unbound. Parameters are excluded from rename
targets now; temp-vs-param spelling collisions keep the honest lift
name instead of a silent capture.
"""
import pytest
import re

from test_game_goldens import game_decompiler

pytestmark = pytest.mark.game

CASES = [
    (113041, 'WriteBytes', '0x181fc5e20',
     ['this.buf[num2] = v0;', 'this.buf[num4] = v1;']),
    (113042, 'WriteBytes', '0x181fc5bf0',
     ['this.buf[num2] = v0;', 'this.buf[num4] = v1;',
      'this.buf[num6] = v2;']),
    (113043, 'WriteBytes', '0x181fc5eb0',
     ['this.buf[num2] = v0;', 'this.buf[num6] = v2;']),
    (113044, 'WriteBytes', '0x181fc5ca0',
     ['this.buf[num2] = v0;', 'this.buf[num8] = v3;',
      'this.buf[num16] = v7;']),
    (1935, 'Initialize', '0x181c9fee0',
     ['((uint*)((byte*)v1 + 0x0))[0] = System.HashCode.s_seed + 606290984;']),
    (79519, 'ValuesEquals', '0x181e1c5e0',
     ['if (v1 != v2)',
      'return Newtonsoft.Json.Linq.JValue.Compare(v1._valueType, v1._value, v2._value) == 0;']),
]


@pytest.mark.parametrize('mi,name,va,lines', CASES,
                         ids=[str(c[0]) for c in CASES])
def test_params_keep_spellings(game_decompiler, mi, name, va, lines):
    il, dec = game_decompiler
    m = il.meta.methods[mi]
    assert m.name == name
    assert hex(m.addr) == va
    text = '\n'.join(dec.lift_method(m, il.meta.typedefs[m.declaring]))
    for ln in lines:
        if ln.startswith('this.buf[num'):
            # The integer temp may renumber as earlier prologue copies
            # acquire their proved scalar types. Pin the actual parameter
            # at the store, which is this regression's invariant.
            value = ln.split('] = ', 1)[1]
            assert re.search(r'this\.buf\[num\d+\] = ' + re.escape(value), text)
        else:
            assert ln in text
    assert 'obj5' not in text and 'obj6' not in text
