"""Reference-width loads from a returned SZARRAY have the element's type."""
import pytest

from il2cpp import Expr
from test_native_values import ARRAY, INT, OBJECT, execute, lifter


STRING = (0, 0x0e << 16)


def load(code, *, ty=ARRAY, element=STRING):
    lift = lifter({'R8': Expr('words', ty, 'obj'), 'RAX': Expr('index', INT, 'int')})
    lift.il.type_from_ptr = lambda ptr: element if ptr == ARRAY[0] else None
    execute(lift, code)
    return lift.regs['RCX']


def test_split_result_element_is_string():
    e = load('498b4cc020')  # mov rcx,[r8+rax*8+20h]
    assert (e.text, e.ty, e.kind) == ('words[index]', STRING, 'str')


@pytest.mark.parametrize('code,kwargs', [
    ('418b4cc020', {}),                       # dword read
    ('498b4c8020', {}),                       # stride four, not eight
    ('498b4cc018', {}),                       # header, not elements
    ('498b4cc020', {'ty': OBJECT}),           # byte shape alone proves no type
    ('498b4cc020', {'ty': (ARRAY[0], ARRAY[1] | (1 << 29))}),
    ('498b4cc020', {'element': OBJECT}),      # object[] permits non-strings
])
def test_unproven_load_is_not_rendered_as_a_string(code, kwargs):
    assert load(code, **kwargs).kind != 'str'
