"""Direct JMP on this to a base slot differs from a virtual call to this."""
from types import SimpleNamespace as NS

import pytest

from il2cpp import Expr, MethodDef
from test_tail_calls import INT, make_lifter


@pytest.mark.parametrize('case, expected', [
    ('base slot', 'base'), ('unrelated object', 'other'), ('new slot', 'this'),
    ('other parent implementation', 'this'), ('ambiguous target', 'this'),
    ('overloaded parent', 'this'), ('same class', 'this'),
])
def test_direct_tail_receiver(case, expected):
    receiver = 'other' if case == 'unrelated object' else 'this'
    lift, ins = make_lifter([INT], {'RCX': Expr(receiver, (1, 0x12 << 16), 'obj'), 'RDX': 'x'},
                            returns=INT, name='Read', static=False)
    parent_method = lift.meta.methods[0]
    parent_method.flags, parent_method.slot, parent_method.addr = 0x1c5, 7, ins.near_branch_target
    current = MethodDef(1, 'Read', 1, 0, 0, -1, 2, 0xc4, 0, 7, 1)
    parent = NS(index=0, generic_container=-1, name='Parent', namespace='', flags=1)
    owner = NS(index=1, generic_container=-1, name='Child', namespace='', flags=1, parent=2)
    lift.il.types.append((0, 0x12 << 16))
    lift.meta.methods.append(current)
    lift.meta.typedefs = [parent, owner]
    lift.meta.type_methods = lambda td: [0, 1] if case == 'overloaded parent' else [0]
    lift.il.vtable_method = lambda td, slot: td if case != 'other parent implementation' else 1
    lift._current_method, lift._current_td = current, owner
    if case == 'new slot':
        current.flags |= 0x100
    elif case == 'same class':
        parent_method.declaring = 1
    elif case == 'ambiguous target':
        # Even a candidate picked by a separate shared resolver isn't proof
        # of a nonvirtual base dispatch. Exercise the common resolution seam.
        lift.il.addr_candidates[parent_method.addr].append(('method', 1))
        assert not lift._direct_base_tail(parent_method.addr, 0, lift.regs['RCX'])
        return
    lift._insn(ins, [ins], 0, None, ins.next_ip)
    assert lift.out[-1][1] == f'return {expected}.Read(x); /* tail */'
