"""Pointer/array operand typing for RPC payload-style native code.

Ground truth: InventoryManager.Rpc_CMD_UpdateInventoryForHost (mi 25626,
VA 0x180704750) -- array params kept in callee-saved registers, a
`SimulationMessage* + 0x1c` payload cursor, aligned CopyFromArray offset
chains, and `[offset + cursor]` stores. Every test executes real x64
bytes through the actual Lifter.
"""
from types import SimpleNamespace as NS

from iced_x86 import Decoder

from il2cpp import Expr, Lifter
from il2cpp.expr import _INT_TY

INT = (0, 0x08 << 16)
U1 = (0, 0x05 << 16)
PTR_U1 = (0xA000, 0x0F << 16)      # byte*
PTR_OBJ = (0xB000, 0x0F << 16)     # T* (non-byte pointee)
ARRAY = (0x9000, 0x1D << 16)
OBJECT = (0, 0x12 << 16)


def lifter(regs=None):
    inner = {0xA000: U1, 0xB000: OBJECT, 0x9000: INT}
    il = NS(types=[INT, U1, PTR_U1, PTR_OBJ, ARRAY, OBJECT],
            _type_enum=lambda t: (t[1] >> 16) & 0xFF if t else 0,
            instance_field_chain=lambda td: {},
            type_from_ptr=lambda ptr: inner.get(ptr))
    meta = NS(typedefs=[NS(is_valuetype=False)])
    lift = Lifter.__new__(Lifter)
    lift.il, lift.meta = il, meta
    lift.bin = NS()
    lift.regs = dict(regs or {})
    lift.out, lift._type_hints, lift._var_types = [], {}, {}
    lift.slot_types, lift.stack_map, lift.addr_of = {}, {}, {}
    lift.rsp_delta = lift.var_n = 0
    lift.dry = lift.asm_comments = lift._copying = False
    lift._cur_ip = 0
    lift.flags = None
    return lift


def execute(lift, hex_bytes):
    insns = list(Decoder(64, bytes.fromhex(hex_bytes), ip=0x1000))
    for index, ins in enumerate(insns):
        lift._insn(ins, insns, index, None, insns[-1].next_ip)


def test_array_length_load_folds_not_raw_deref():
    lift = lifter({'RDI': Expr('trash_', ARRAY, 'arr')})
    execute(lift, '8b4718')  # mov eax,[rdi+18h]
    e = lift.regs['RAX']
    assert e.text == 'trash_.Length'
    assert e.kind == 'int'
    assert e.ty == _INT_TY


def test_rbp_scratch_array_reads_length_not_a_slot():
    lift = lifter({'RBP': Expr('inventoryIds_', ARRAY, 'arr')})
    execute(lift, '8b4518')  # mov eax,[rbp+18h]
    e = lift.regs['RAX']
    assert e.text == 'inventoryIds_.Length'
    assert not e.text.startswith('s_')


def test_rbp_frame_address_still_reads_a_slot():
    lift = lifter()
    execute(lift, '4889e5')  # mov rbp,rsp establishes the frame
    assert lift._rbp_is_frame()
    execute(lift, '8b4518')  # mov eax,[rbp+18h]
    assert lift.regs['RAX'].text == 's_18'


def test_lea_over_integer_is_integer_arithmetic():
    lift = lifter({'RAX': Expr('n', INT, 'int')})
    execute(lift, '8d6803')  # lea ebp,[rax+3]
    e = lift.regs['RBP']
    assert e.kind == 'int'
    assert e.ty == INT
    assert e.text == '(n + 0x3)'


def test_lea_past_typed_pointer_uses_a_byte_cursor():
    lift = lifter({'RAX': Expr('simMsg', PTR_OBJ, 'ptr')})
    execute(lift, '4c8d781c')  # lea r15,[rax+1Ch]
    e = lift.regs['R15']
    assert e.kind == 'ptr'
    assert e.ty == PTR_U1
    assert e.text == '(byte*)simMsg + 0x1c'


def test_lea_over_byte_pointer_needs_no_cast():
    lift = lifter({'RAX': Expr('cur', PTR_U1, 'ptr')})
    execute(lift, '4c8d780c')  # lea r15,[rax+0Ch]
    e = lift.regs['R15']
    assert e.kind == 'ptr'
    assert e.ty == PTR_U1
    assert e.text == '(cur + 0xc)'


def test_cursor_as_index_renders_pointer_first():
    lift = lifter({'RDX': Expr('off', INT, 'int'),
                   'RCX': Expr('v', INT, 'int'),
                   'R15': Expr('cur', PTR_U1, 'ptr')})
    insns = list(Decoder(64, bytes.fromhex('42890c3a'), ip=0x1000))  # mov [rdx+r15],ecx
    lv = lift._mem_lvalue(insns[0])
    assert lv == '*(cur + off*1 + 0x0)', lv


def test_integer_offset_plus_cursor_is_an_address():
    lift = lifter({'RCX': Expr('off', INT, 'int'),
                   'R15': Expr('cur', PTR_U1, 'ptr')})
    execute(lift, '4903cf')  # add rcx,r15
    e = lift.regs['RCX']
    assert e.kind == 'ptr'
    assert e.ty == PTR_U1


def test_byte_cursor_binds_with_its_type():
    lift = lifter()
    lift._bind(Expr('(byte*)simMsg + 0x1c', PTR_U1, 'ptr'))
    assert PTR_U1 in lift._var_types.values()
    assert lift.out and lift.out[0][1].startswith('var t')


def test_long_operand_binds_typed_instead_of_minting_a_twin():
    big = 'n' + '0' * 170
    lift = lifter({'RAX': Expr(big, INT, 'int'), 'RBX': Expr('k', INT, 'int')})
    execute(lift, '4801d8')  # add rax,rbx
    assert lift.regs['RAX'].text == 't0 + k'
    assert 't' in lift.regs['RAX'].text
    assert INT in lift._var_types.values()
    assert len(lift.out) == 1
