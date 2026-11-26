"""A struct receiver and a class receiver use different native field origins."""
from types import SimpleNamespace as NS

import pytest

from il2cpp import Expr
from test_native_values import execute, lifter


@pytest.mark.parametrize('struct,expected', [(True, 'this.label'), (False, 'this.inner.reference')])
def test_direct_field_and_nested_reference_at_header_distance(struct, expected):
    inner = (1, 0x11 << 16)
    string = (0, 0x0e << 16)
    reference = (2, 0x12 << 16)
    lift = lifter({'RBX': Expr('this', (0, 0x12 << 16), 'obj')}, field_types=[inner, string, reference])
    lift.meta.typedefs = [NS(is_valuetype=struct), NS(is_valuetype=True), NS(is_valuetype=False)]
    lift.il.instance_field_chain = lambda td: [
        {0x18: ('inner', 0), 0x40: ('label', 1)}, {0x28: ('reference', 2)}, {}][td]
    lift.il._sf_field_size = lambda ty, depth: 0x20 if ty == inner else 8
    lift._current_method = NS(declaring=0, is_static=False)
    execute(lift, '488b7330')  # mov rsi,[rbx+30h]
    assert lift.regs['RSI'].text == expected
    assert lift.regs['RSI'].ty == (string if struct else reference)
