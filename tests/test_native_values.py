"""Small real-x64 instruction regressions for Review 78's TODO fixes."""
import struct
from types import SimpleNamespace as NS

import pytest
from iced_x86 import Decoder

from il2cpp import Expr, Lifter

BOOL = (0, 0x02 << 16)
SHORT = (0, 0x06 << 16)
INT = (0, 0x08 << 16)
FLOAT = (0, 0x0C << 16)
ARRAY = (0x9000, 0x1D << 16)
OBJECT = (0, 0x12 << 16)


def lifter(regs=None, fields=None, field_types=None):
    types = field_types or [BOOL, BOOL]
    chain = fields if fields is not None else {0x10: ('first', 0), 0x11: ('second', 1)}
    il = NS(types=types, _type_enum=lambda t: (t[1] >> 16) & 0xFF if t else 0,
            instance_field_chain=lambda td: chain,
            type_from_ptr=lambda ptr: INT if ptr == ARRAY[0] else None,
            # array element stride: references are 8 bytes
            _sf_field_size=lambda fty, depth: 8 if fty is not None else None)
    meta = NS(typedefs=[NS(is_valuetype=False)])
    lift = Lifter.__new__(Lifter)
    lift.il, lift.meta = il, meta
    lift.bin = NS()
    lift.regs = dict(regs or {'RCX': Expr('this', OBJECT, 'obj')})
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
    return [text for _, text, _ in lift.out]


@pytest.mark.parametrize('value,expected', [
    ('0101', ['this.first = true;', 'this.second = true;']),
    ('0100', ['this.first = true;', 'this.second = false;']),
    ('0001', ['this.first = false;', 'this.second = true;']),
    ('0000', ['this.first = false;', 'this.second = false;']),
])
def test_packed_boolean_word_store_preserves_both_fields(value, expected):
    assert execute(lifter(), '66c74110' + value) == expected


def test_packed_boolean_dword_store_preserves_all_four_bytes():
    lift = lifter(fields={0x10+i: (f'b{i}', i) for i in range(4)}, field_types=[BOOL]*4)
    assert execute(lift, 'c7411001000100') == [
        'this.b0 = true;', 'this.b1 = false;', 'this.b2 = true;', 'this.b3 = false;']


def test_single_byte_boolean_store_is_unchanged():
    assert execute(lifter(), 'c6411001') == ['this.first = true;']


def test_word_integer_immediate_is_not_an_unknown():
    lift = lifter(fields={0x10: ('value', 0)}, field_types=[SHORT])
    assert execute(lift, '66c741103412') == ['this.value = 4660;']


def test_signed_short_immediate_is_interpreted_at_field_width():
    lift = lifter(fields={0x10: ('value', 0)}, field_types=[SHORT])
    assert execute(lift, '66c74110ffff') == ['this.value = -1;']


@pytest.mark.parametrize('opcode,operator', [('03','+'), ('2b','-'), ('23','&'), ('0b','|'), ('33','^')])
def test_register_arithmetic_reads_its_memory_source(opcode, operator):
    lift = lifter({'RCX': Expr('30', INT, 'int'), 'R8': Expr('ammo', ARRAY, 'arr'),
                   'RAX': Expr('slot', INT, 'int')})
    execute(lift, '41' + opcode + '4c8020')  # op ecx,[r8+rax*4+20h]
    assert lift.regs['RCX'].text == f'30 {operator} ammo[slot]'
    assert '?' not in lift.regs['RCX'].text


def test_unresolved_memory_source_stays_visible_not_a_zero_default():
    lift = lifter({'RCX': Expr('30', INT, 'int'), 'RAX': Expr('slot', INT, 'int')})
    execute(lift, '412b4c8020')
    assert '?' in lift.regs['RCX'].text or 'mem_' in lift.regs['RCX'].text
    assert lift.regs['RCX'].text != '30'


def test_integer_address_math_does_not_hint_an_array_as_int():
    lift = lifter({'R8': Expr('t0', ARRAY, 'arr')})
    execute(lift, '4983c020')  # add r8,20h (skip array header)
    assert lift._type_hints.get('t0') != INT
    assert lift.regs['R8'].ty == ARRAY
    assert lift.regs['R8'].kind == 'arr'


def test_unknown_scalar_arithmetic_still_receives_integer_hint():
    lift = lifter({'R8': Expr('t0', None, '?')})
    execute(lift, '4983c002')
    assert lift._type_hints['t0'] == INT


def test_three_operand_imul_reads_its_memory_source():
    lift = lifter({'R8': Expr('ammo', ARRAY, 'arr'), 'RAX': Expr('slot', INT, 'int')})
    execute(lift, '416b4c802003')
    assert lift.regs['RCX'].text == 'ammo[slot] * 3'


@pytest.mark.parametrize('fields,types,value', [
    ({0x10: ('first', 0)}, [BOOL], '0101'),                 # unknown second byte
    ({0x10: ('first', 0), 0x12: ('second', 1)}, [BOOL]*2, '0101'),  # padding
    ({0x10: ('first', 0), 0x11: ('second', 1)}, [BOOL,INT], '0101'),
    ({0x10: ('first', 0), 0x11: ('first', 1)}, [BOOL]*2, '0101'),  # duplicate identity
    ({0x10: ('first', 0), 0x11: ('second', 1)}, [BOOL]*2, '0102'),  # noncanonical bool
])
def test_unproven_wide_boolean_store_is_not_split_or_narrowed(fields, types, value):
    lift = lifter(fields=fields, field_types=types)
    output = execute(lift, '66c74110' + value)
    assert len(output) == 1
    assert 'ushort*' in output[0] and '.first =' not in output[0]
    assert str(int.from_bytes(bytes.fromhex(value), 'little')) in output[0]
    from il2cpp import Decompiler
    from tree_sitter import Language, Parser
    import tree_sitter_c_sharp
    rendered = '\n'.join(Decompiler.__new__(Decompiler)._render(output))
    parser = Parser(Language(tree_sitter_c_sharp.language()))
    assert not parser.parse(('class C { void M() {' + rendered + '} }').encode()).root_node.has_error


def test_explicit_layout_is_not_assumed_nonoverlapping():
    lift = lifter()
    lift.meta.typedefs[0].flags = 0x10
    output = execute(lift, '66c741100101')
    assert len(output) == 1 and 'ushort*' in output[0]


def test_packed_store_materializes_old_field_values_before_both_writes():
    lift = lifter({'RCX': Expr('this', OBJECT, 'obj'),
                   'R8': Expr('this.first', BOOL, 'int'),
                   'R9': Expr('this.second', BOOL, 'int')})
    output = execute(lift, '66c741100101')
    assert output[:2] == ['var t0 = this.first;', 'var t1 = this.second;']
    assert output[2:] == ['this.first = true;', 'this.second = true;']
    assert lift.regs['R8'].text == 't0' and lift.regs['R9'].text == 't1'


def test_register_memory_arithmetic_does_not_invent_a_second_store():
    lift = lifter({'RCX': Expr('capacity', INT, 'int'), 'R8': Expr('ammo', ARRAY, 'arr'),
                   'RAX': Expr('slot', INT, 'int')})
    assert execute(lift, '412b4c8020') == []
    assert lift.regs['RCX'].text == 'capacity - ammo[slot]'


def test_unsplit_wide_store_preserves_known_first_field_old_value():
    lift = lifter({'RCX': Expr('this', OBJECT, 'obj'),
                   'R8': Expr('this.first', BOOL, 'int')},
                  fields={0x10: ('first', 0)}, field_types=[BOOL])
    output = execute(lift, '66c741100101')
    assert output[0] == 'var t0 = this.first;'
    assert 'ushort*' in output[1]
    assert lift.regs['R8'].text == 't0'


@pytest.mark.parametrize('encoding,guarded', [
    ('b801000000c3', False),  # straight-line
    ('750190c3', False),     # forward-only branch
    ('9075fd', False),       # direct loop: structured header replay is safe
    ('75fe', False),         # direct self-loop
    ('ffe0', True),          # unresolved/table/indirect dispatch
    ('e9fbefffff', False),   # tail to code outside the current extent
])
def test_memory_rhs_guard_is_reserved_for_unmodelled_control_flow(encoding, guarded):
    from il2cpp import Decompiler
    insns = list(Decoder(64, bytes.fromhex(encoding), ip=0x1000))
    assert Decompiler._memory_rhs_needs_loop_guard(insns) is guarded


@pytest.mark.parametrize('encoding', ['412b4c8020', '416b4c802003'])
def test_forced_indirect_dispatch_guard_keeps_memory_operand_honest(encoding):
    lift = lifter({'RCX': Expr('30', INT, 'int'), 'R8': Expr('ammo', ARRAY, 'arr'),
                   'RAX': Expr('slot', INT, 'int')})
    lift._memory_rhs_loop_guard = True
    execute(lift, encoding)
    assert 'ammo[slot]' not in lift.regs['RCX'].text
    assert '?' in lift.regs['RCX'].text


def test_direct_loop_can_recover_memory_operand_after_header_replay():
    from il2cpp import Decompiler

    loop = list(Decoder(64, bytes.fromhex('412b4c802075fa'), ip=0x1000))
    assert Decompiler._memory_rhs_needs_loop_guard(loop) is False

    lift = lifter({'RCX': Expr('30', INT, 'int'), 'R8': Expr('ammo', ARRAY, 'arr'),
                   'RAX': Expr('slot', INT, 'int')})
    lift._memory_rhs_loop_guard = False
    execute(lift, '412b4c8020')
    assert lift.regs['RCX'].text == '30 - ammo[slot]'


def test_fresh_unknowns_seed_volatile_gprs_only():
    lift = lifter()
    lift._fresh_unknowns()
    assert lift.regs['RAX']._unk
    # XMM registers are not seeded here: the SSE handlers substitute an
    # unknown at the missing operand instead (temp numbering stays stable).
    assert 'XMM0' not in lift.regs


def test_missing_sse_operand_is_an_unknown_not_zero():
    lift = lifter({'XMM1': Expr('real5', FLOAT, 'float')})
    execute(lift, 'f30f58c1')       # addss xmm0, xmm1
    e = lift.regs['XMM0']
    assert 'real5' in e.text and '0f' not in e.text
    assert e.text.startswith('v')   # unknown left operand, honest vN


def test_maxss_minss_render_hardware_semantics():
    lift = lifter({'XMM0': Expr('real1', FLOAT, 'float'),
                   'XMM1': Expr('real2', FLOAT, 'float')})
    execute(lift, 'f30f5fc1')       # maxss xmm0, xmm1
    assert lift.regs['XMM0'].text == '(real1 > real2 ? real1 : real2)'
    lift = lifter({'XMM0': Expr('real1', FLOAT, 'float'),
                   'XMM1': Expr('real2', FLOAT, 'float')})
    execute(lift, 'f30f5dc1')       # minss xmm0, xmm1
    assert lift.regs['XMM0'].text == '(real1 < real2 ? real1 : real2)'


def test_maxss_missing_operand_is_unknown_not_zero():
    lift = lifter({'XMM1': Expr('real2', FLOAT, 'float')})
    execute(lift, 'f30f5fc1')       # maxss xmm0, xmm1 with xmm0 absent
    t = lift.regs['XMM0'].text
    assert '0f' not in t and 'real2' in t and t.startswith('(v')


VEC8 = (0, 0x11 << 16)


def whole_value_lifter(fields=None, field_types=None):
    lift = lifter(fields=fields if fields is not None else {},
                  field_types=field_types)
    lift.meta.typedefs[0].is_valuetype = True
    lift.il._sf_field_size = lambda ty, depth: 8 if ty == VEC8 else 4
    lift.il._closed_type_key = lambda t: t
    return lift


def test_whole_valuetype_load_is_the_value_not_its_first_field():
    lift = whole_value_lifter()
    lift.regs = {'RBX': Expr('particleColor', VEC8, 'obj')}
    execute(lift, '488b03')         # mov rax, [rbx] -- the whole 8-byte value
    assert lift.regs['RAX'].text == 'particleColor'


def test_whole_valuetype_load_from_an_address_base_declines():
    lift = whole_value_lifter()
    lift.regs = {'RBX': Expr('&s_8', VEC8, 'ptr')}
    ins = Decoder(64, bytes.fromhex('488b03'), ip=0x1000).decode()
    assert lift._aggregate_load(ins) is None


def test_partial_valuetype_load_still_declines():
    lift = whole_value_lifter()
    lift.regs = {'RBX': Expr('particleColor', VEC8, 'obj')}
    execute(lift, '8b03')           # mov eax, [rbx] -- 4 of 8 bytes
    assert lift.regs['RAX'].text != 'particleColor'


def test_scalar_sse_slices_a_whole_value_fragment():
    # A whole-value fragment consumed by a scalar op must render its low
    # lane (`particleColor.x`), not the whole struct.
    lift = whole_value_lifter(fields={0x10: ('x', 0)},
                              field_types=[FLOAT, FLOAT])
    lift.regs = {'RBX': Expr('particleColor', VEC8, 'obj'),
                 'XMM1': Expr('real2', FLOAT, 'float')}
    execute(lift, '488b03')         # rax = particleColor (whole fragment)
    lift.regs['XMM0'] = lift.regs['RAX']
    execute(lift, 'f30f58c1')       # addss xmm0, xmm1
    assert lift.regs['XMM0'].text == 'particleColor.x + real2'


# --- F1 lane modeling (SHUFPS/PSHUFD/UNPCKHPS/CVTDQ2PS/MOVSS-merge) ---
#
# Each handler fires only when every consumed lane is proven through
# `_piece_value`; any unproven lane keeps today's spelling (the
# destination is left untouched and execution falls through to the asm
# comment, exactly as before). Invalidation of genuinely-unmodelled
# destinations stays open (mi80548 gate).

def lanes_lifter(regs=None):
    il = NS(types=[INT, FLOAT],
            _type_enum=lambda t: (t[1] >> 16) & 0xFF if t else 0,
            instance_field_chain=lambda td: {},
            type_from_ptr=lambda ptr: None,
            _closed_type_key=lambda t: t,
            _sf_field_size=lambda fty, depth: 4 if fty == FLOAT else None)
    meta = NS(typedefs=[NS(is_valuetype=False)])
    lift = Lifter.__new__(Lifter)
    lift.il, lift.meta = il, meta
    lift.bin = NS()
    lift.regs = dict(regs or {})
    lift.out, lift._type_hints, lift._var_types = [], {}, {}
    lift.slot_types, lift.stack_map, lift.stack_values, lift.addr_of = {}, {}, {}, {}
    lift.rsp_delta = lift.var_n = 0
    lift.dry = lift.asm_comments = lift._copying = False
    lift._cur_ip = 0
    lift.flags = None
    return lift


def _packed(*names):
    p = Expr(names[0], FLOAT, 'bits')
    p._parts = [(i * 4, Expr(n, FLOAT, 'float'), 0, 4) for i, n in enumerate(names)]
    return p


def _lane_texts(lift, reg):
    e = lift.regs.get(reg)
    out = []
    for off in (0, 4, 8, 12):
        v = lift._piece_value(e, off, 4, FLOAT)
        out.append(v.text if v is not None else '<None>')
    return out


@pytest.mark.parametrize('hx,want', [
    ('0fc6c1e4', ['a', 'b', 'g', 'h']),    # shufps identity
    ('0fc6c100', ['a', 'a', 'e', 'e']),    # shufps broadcast
    ('0fc6c11b', ['d', 'c', 'f', 'e']),    # shufps reverse-ish
    ('660f70c1e4', ['e', 'f', 'g', 'h']),  # pshufd identity
    ('660f70c11b', ['h', 'g', 'f', 'e']),  # pshufd reverse
    ('0f15c1', ['c', 'g', 'd', 'h']),      # unpckhps upper interleave
    ('f30f10c1', ['e', 'b', 'c', 'd']),    # movss low-lane merge
])
def test_simd_lane_models(hx, want):
    lift = lanes_lifter({'XMM0': _packed('a', 'b', 'c', 'd'),
                         'XMM1': _packed('e', 'f', 'g', 'h')})
    execute(lift, hx)
    assert _lane_texts(lift, 'XMM0') == want


def test_shufps_with_unproven_lanes_keeps_todays_spelling():
    dst = _packed('a', 'b', 'c', 'd')
    lift = lanes_lifter({'XMM0': dst,
                         'XMM1': Expr('stale', FLOAT, 'float')})
    execute(lift, '0fc6c1e4')
    assert lift.regs['XMM0'] is dst


def test_movss_with_unproven_dst_lane_keeps_full_copy():
    lift = lanes_lifter({'XMM0': Expr('stale', FLOAT, 'float'),
                         'XMM1': _packed('e', 'f', 'g', 'h')})
    execute(lift, 'f30f10c1')
    assert _lane_texts(lift, 'XMM0') == ['e', 'f', 'g', 'h']


def test_cvtdq2ps_models_int_lanes():
    src = Expr('src', None, 'bits')
    src._bytes = struct.pack('<4i', 1, -2, 3, 4)
    lift = lanes_lifter({'XMM0': _packed('a', 'b', 'c', 'd'), 'XMM1': src})
    execute(lift, '0f5bc1')
    assert _lane_texts(lift, 'XMM0') == [
        '(float)(1)', '(float)(-2)', '(float)(3)', '(float)(4)']


def test_cvtdq2ps_with_float_lanes_keeps_todays_spelling():
    dst = _packed('a', 'b', 'c', 'd')
    lift = lanes_lifter({'XMM0': dst, 'XMM1': _packed('e', 'f', 'g', 'h')})
    execute(lift, '0f5bc1')
    assert lift.regs['XMM0'] is dst


# --- IsInst slice 1: closed generic-instance class elements ---
#
# `_elem_klass_name` accepts a 0x15 (GENERICINST) element only when the
# instantiation is closed, its definition is a non-valuetype non-enum
# typedef, and the existing nameability guards pass. Open VAR/MVAR at
# any depth, unreadable args, nested-definition bases, valuetype
# definitions and unnameable spellings keep the honest marker.

_GCPTR = 0x18001000
_GENINST = (_GCPTR, 0x15 << 16)
_CLOSED_INT = (0, 0x08 << 16)
_BASEPTR = 0x18002000


def geninst_lifter(synth=None, typedefs=None, names=None, va2off=None,
                   blob=None, ptrs=None):
    il = NS(types=[INT, FLOAT],
            _type_enum=lambda t: (t[1] >> 16) & 0xFF if t else 0,
            _synthetic_lookup=lambda v: (synth or {}).get(v),
            type_from_ptr=lambda p: (ptrs or {}).get(p),
            type_name=lambda t: (names or {}).get(t, 'object'),
            _closed_type_key=lambda t: t)
    meta = NS(typedefs=typedefs if typedefs is not None
              else [NS(is_valuetype=False, is_enum=False)])
    lift = Lifter.__new__(Lifter)
    lift.il, lift.meta = il, meta
    lift.bin = NS(va2off=va2off or (lambda v: None),
                  d=blob if blob is not None else b'')
    lift.regs = {}
    lift.out, lift._type_hints, lift._var_types = [], {}, {}
    lift.slot_types, lift.stack_map, lift.stack_values, lift.addr_of = {}, {}, {}, {}
    lift.rsp_delta = lift.var_n = 0
    lift.dry = lift.asm_comments = lift._copying = False
    lift._cur_ip = 0
    lift.flags = None
    return lift


def _closed_fire_lifter():
    base = (0, 0x12 << 16)
    return geninst_lifter(
        synth={_GCPTR: (base, [_CLOSED_INT])},
        typedefs=[NS(is_valuetype=False, is_enum=False)],
        names={_GENINST: 'List<int>'},
        va2off=lambda v: {_GCPTR: 0}.get(v),
        blob=struct.pack('<Q', _BASEPTR),
        ptrs={_BASEPTR: base})


def test_closed_generic_instance_class_folds():
    lift = _closed_fire_lifter()
    assert lift._geninst_as_target(_GENINST) == ('List<int>', _GENINST)


def test_open_var_argument_declines():
    lift = geninst_lifter(
        synth={_GCPTR: ((0, 0x12 << 16), [(7, 0x13 << 16)])})
    assert lift._geninst_as_target(_GENINST) is None


def test_nested_open_argument_declines():
    inner = (_GCPTR + 8, 0x15 << 16)
    lift = geninst_lifter(
        synth={_GCPTR: ((0, 0x12 << 16), [inner]),
               _GCPTR + 8: ((0, 0x12 << 16), [(3, 0x1e << 16)])})
    assert lift._geninst_as_target(_GENINST) is None


def test_valuetype_definition_declines():
    base = (0, 0x12 << 16)
    lift = geninst_lifter(
        synth={_GCPTR: (base, [_CLOSED_INT])},
        typedefs=[NS(is_valuetype=True, is_enum=False)],
        names={_GENINST: 'Nullable<int>'},
        va2off=lambda v: {_GCPTR: 0}.get(v),
        blob=struct.pack('<Q', _BASEPTR),
        ptrs={_BASEPTR: base})
    assert lift._geninst_as_target(_GENINST) is None


def test_object_spelling_declines():
    lift = _closed_fire_lifter()
    lift.il.type_name = lambda t: 'object'
    assert lift._geninst_as_target(_GENINST) is None


def test_paren_spelling_declines():
    lift = _closed_fire_lifter()
    lift.il.type_name = lambda t: 'A<B>(c)'
    assert lift._geninst_as_target(_GENINST) is None


def test_unreadable_args_decline():
    lift = geninst_lifter()
    assert lift._geninst_as_target(_GENINST) is None


def test_open_generic_direct():
    lift = geninst_lifter()
    assert lift._open_generic((7, 0x13 << 16)) is True
    assert lift._open_generic(None) is True
    assert lift._open_generic(_CLOSED_INT) is False
    assert lift._open_generic(_GENINST) is True
    # A lane carrying the bare `?` placeholder is proven-looking but
    # unspellable (`real27 * ?` is unparseable -- LegsAnimator gate).
    dst = _packed('a', 'b', 'c', 'd')
    lift = lanes_lifter({'XMM0': dst, 'XMM1': _packed('e', '?', 'g', 'h')})
    execute(lift, '0fc6c11b')
    assert lift.regs['XMM0'] is dst


def test_movss_with_placeholder_src_lane_keeps_full_copy():
    lift = lanes_lifter({'XMM0': _packed('a', 'b', 'c', 'd'),
                         'XMM1': _packed('?', 'f', 'g', 'h')})
    execute(lift, 'f30f10c1')
    assert _lane_texts(lift, 'XMM0') == ['?', 'f', 'g', 'h']


def test_shufps_with_placeholder_lane_text_keeps_todays_spelling():
    # A lane carrying the bare `?` placeholder is proven-looking but
    # unspellable (`real27 * ?` is unparseable -- LegsAnimator gate).
    dst = _packed('a', 'b', 'c', 'd')
    lift = lanes_lifter({'XMM0': dst, 'XMM1': _packed('e', '?', 'g', 'h')})
    execute(lift, '0fc6c11b')
    assert lift.regs['XMM0'] is dst
