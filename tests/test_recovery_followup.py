"""Synthetic regressions for the 2026-09-19 recovery follow-up (nowtodo.md).

Each test executes real x64 bytes (or the exact changed helper) through the
real Lifter with minimal doubles. Native fixture coverage lives in the game
goldens; null-edge narrowing is covered by MicAudioCanvas.Start
(mi 26312) since it needs full CFG blocks.
"""
from types import SimpleNamespace as NS
import struct

import pytest
from iced_x86 import Decoder

from il2cpp import Decompiler, Expr, Lifter

INT = (0, 0x08 << 16)
F32 = (0, 0x0C << 16)
STRING = (0, 0x0E << 16)
CLASS = (0, 0x12 << 16)
V3 = (0, 0x11 << 16)


def lifter(regs=None, il=None):
    lift = Lifter.__new__(Lifter)
    lift.il = il or NS(
        types=[INT],
        _type_enum=lambda t: (t[1] >> 16) & 0xFF if t else 0,
        instance_field_chain=lambda td: {},
        type_from_ptr=lambda ptr: None,
    )
    lift.meta = NS(typedefs=[NS(is_valuetype=False)])
    lift.bin = NS()
    lift.regs = dict(regs or {})
    lift.out, lift._type_hints, lift._var_types = [], {}, {}
    lift.slot_types, lift.stack_map, lift.stack_values, lift.addr_of = {}, {}, {}, {}
    lift.rsp_delta = lift.var_n = 0
    lift.dry = lift.asm_comments = lift._copying = False
    lift._cur_ip = 0
    lift.flags = None
    return lift


def execute(lift, hex_bytes):
    insns = list(Decoder(64, bytes.fromhex(hex_bytes), ip=0x1000))
    for index, ins in enumerate(insns):
        lift._insn(ins, insns, index, None, insns[-1].next_ip)


def test_native_count_sugar_fires_for_field_receiver():
    from types import SimpleNamespace as NS
    from il2cpp import Decompiler
    OBI = (9, 0)
    dec = Decompiler.__new__(Decompiler)
    dec._var_types = {}
    dec.L = NS(il=NS(type_name=lambda ty: 'Obi.ObiNativeContactList',
                     instance_field_chain=lambda td: {0x40: ('frame', 5)},
                     types=[None] * 5 + [OBI]),
               _current_td=NS(index=7))
    assert dec._native_count_sugar('n < ((byte*)this.frame + 0x28)[0]') == \
        'n < this.frame.Count'


def test_native_count_sugar_fires_for_native_list():
    from types import SimpleNamespace as NS
    from il2cpp import Decompiler
    dec = Decompiler.__new__(Decompiler)
    dec._var_types = {'list1': (0, 0)}
    dec.L = NS(il=NS(type_name=lambda ty: 'Obi.ObiNativeContactList'))
    assert dec._native_count_sugar('num1 < ((byte*)list1 + 0x28)[0]') == \
        'num1 < list1.Count'
    assert dec._native_count_sugar('num1 < *(list1 + 0x28)') == \
        'num1 < list1.Count'


def test_native_count_sugar_declines_others():
    from types import SimpleNamespace as NS
    from il2cpp import Decompiler
    dec = Decompiler.__new__(Decompiler)
    dec._var_types = {}
    dec.L = NS(il=NS(type_name=lambda ty: 'Obi.ObiNativeContactList'))
    s = 'num1 < ((byte*)list1 + 0x28)[0]'
    assert dec._native_count_sugar(s) == s
    dec._var_types = {'a': (0, 0)}
    dec.L = NS(il=NS(type_name=lambda ty: 'int[]'))
    assert dec._native_count_sugar(s.replace('list1', 'a')) == s.replace('list1', 'a')


def test_bool_materialization_retypes_all_bool_use_temp():
    from il2cpp import Decompiler
    dec = Decompiler.__new__(Decompiler)
    dec._var_types = {}
    lines = [
        "int num1 = 0;",
        "num1 = (levelMeter1.CurrentAvgAmp * this.sensitivity > this.speakingAmpThreshold ? 1 : 0);",
        "this.activationMic.SetActive(flag9 & num1);",
    ]
    dec._var_types = {'flag9': (0, 0x02 << 16)}
    assert dec._bool_materialization_pass(list(lines)) == [
        "bool num1 = false;",
        "num1 = levelMeter1.CurrentAvgAmp * this.sensitivity > this.speakingAmpThreshold;",
        "this.activationMic.SetActive(flag9 & num1);",
    ]


def test_bool_materialization_declines_int_use():
    from il2cpp import Decompiler
    dec = Decompiler.__new__(Decompiler)
    dec._var_types = {}
    lines = [
        "int num1 = 0;",
        "num1 = (a > b ? 1 : 0);",
        "num1 += 1;",
    ]
    assert dec._bool_materialization_pass(list(lines)) == lines


def _boxfold(lines, tmps):
    from il2cpp import Decompiler
    dec = Decompiler.__new__(Decompiler)
    dec._boxed_bool_tmps = set(tmps)
    return dec._boxed_bool_null_fold(list(lines))


def test_boxed_bool_null_fold_fires():
    assert _boxfold(['object obj32 = obj5.MoveNext();',
                     'if (obj32 == null)',
                     '{',
                     'break;',
                     '}'], ['obj32']) == \
        ['bool obj32 = obj5.MoveNext();', 'if (!obj32)', '{', 'break;',
         '}']


def test_boxed_bool_null_fold_ne_shape():
    assert _boxfold(['object obj49 = obj5.MoveNext();',
                     'if (obj49 != null)'], ['obj49']) == \
        ['bool obj49 = obj5.MoveNext();', 'if (obj49)']


def test_boxed_bool_declines_object_use():
    lines = ['object obj52 = enumerator8.MoveNext();',
             'object obj54 = unbox(obj52);']
    assert _boxfold(lines, ['obj52']) == lines


def test_boxed_bool_declines_reassign_and_byref():
    assert _boxfold(['object o1 = e.MoveNext();', 'o1 = other;',
                     'if (o1 == null)'], ['o1']) == \
        ['object o1 = e.MoveNext();', 'o1 = other;', 'if (o1 == null)']
    assert _boxfold(['object o2 = e.MoveNext();', 'f(&o2);',
                     'if (o2 == null)'], ['o2']) == \
        ['object o2 = e.MoveNext();', 'f(&o2);', 'if (o2 == null)']


def test_boxed_bool_declines_unrecorded_and_noncall():
    lines = ['object obj32 = obj5.MoveNext();', 'if (obj32 == null)']
    assert _boxfold(lines, ['nope']) == lines
    assert _boxfold(['object o3 = unknown;', 'if (o3 == null)'],
                    ['o3']) == ['object o3 = unknown;',
                                'if (o3 == null)']


def _packed_lit(*names):
    packed = Expr(names[0], F32, 'bits')
    packed._parts = [(i * 4, Expr(name, F32, 'float'), 0, 4)
                     for i, name in enumerate(names)]
    return packed


def test_unpcklps_recovers_byte_proven_lanes():
    # Part A: a scalar const-pool load carries its bytes, so the
    # unpcklps lane reader recovers '1.0f' lanes; without bytes the
    # same shape stays honestly empty.
    lift = struct_lifter()
    proven = Expr('1.0f', None, 'float')
    proven._bytes = bytes(struct.pack('<f', 1.0))
    assert lift._piece_value(proven, 0, 4, F32).text == '1.0f'
    assert lift._piece_value(proven, 4, 4, F32) is None
    assert lift._piece_value(Expr('1.0f', None, 'float'), 0, 4,
                             F32) is None
    lift.regs.update(XMM0=proven, XMM1=proven)
    execute(lift, '0f14c1')  # unpcklps xmm0,xmm1
    parts = lift.regs['XMM0']._parts
    assert [p[0] for p in parts] == [0, 4]
    assert all(p[1].text == '1.0f' for p in parts)
    bare = struct_lifter()
    raw = Expr('1.0f', None, 'float')
    bare.regs.update(XMM0=raw, XMM1=raw)
    execute(bare, '0f14c1')  # unpcklps xmm0,xmm1
    assert not getattr(bare.regs['XMM0'], '_parts', None)


def test_float_lane_texts_decline_without_parts():
    lift = struct_lifter()
    assert lift._float_lane_texts(_packed_lit('1.0f', '1.0f'), 8) == \
        ['1.0f', '1.0f']
    assert lift._float_lane_texts(Expr('?', None, '?'), 8) is None
    assert lift._float_lane_texts(None, 8) is None
    assert lift._float_lane_texts(_packed_lit('x', 'y'), 8) is None
    assert lift._float_lane_texts(_packed_lit('1.0f', '1.0f'), 16) is None


def test_integer_carry_has_no_lanes():
    # 80548 shape: PSRLDQ pops the dest, so the movq GPR has no parts
    # and no float-slot materialization may fire on it.
    lift = struct_lifter()
    lift.regs.update(XMM0=_packed_lit('x', 'y'))
    execute(lift, '660f73d008')  # psrldq xmm0,8
    execute(lift, 'f3490f7ec0')  # movq r8,xmm0
    assert lift.regs.get('R8') is None
    assert lift._float_lane_texts(lift.regs.get('R8'), 8) is None


def test_sfblob_base_defers_to_static_path():
    lift = struct_lifter()
    base = Expr('typeof(V3).__static_fields', V3, 'sfblob')
    lift.regs['RAX'] = base
    ins = next(iter(Decoder(64, bytes.fromhex('f30f1000'), ip=0x1000)))
    assert lift._aggregate_load(ins) is None
    base2 = Expr('o', V3, 'obj')
    lift.regs['RAX'] = base2
    assert lift._aggregate_load(ins) is not None


def test_add_accessor_folds_to_plus_equals():
    from test_stack_args import make_call_lifter
    lift, ins = make_call_lifter([INT], {'RCX': 'obj', 'RDX': 'h'},
                                 returns=(0, 0x01 << 16), static=False,
                                 name='add_Click')
    lift._insn(ins, [ins], 0, None, ins.next_ip)
    assert lift.out and lift.out[-1][1] == 'obj.Click += h;'


def test_remove_accessor_folds_to_minus_equals():
    from test_stack_args import make_call_lifter
    lift, ins = make_call_lifter([INT], {'RCX': 'obj', 'RDX': 'h'},
                                 returns=(0, 0x01 << 16), static=False,
                                 name='remove_Click')
    lift._insn(ins, [ins], 0, None, ins.next_ip)
    assert lift.out and lift.out[-1][1] == 'obj.Click -= h;'


def test_nonvoid_add_keeps_call_form():
    from test_stack_args import make_call_lifter
    lift, ins = make_call_lifter([INT], {'RCX': 'obj', 'RDX': 'h'},
                                 returns=INT, static=False, name='add_Click')
    lift._insn(ins, [ins], 0, None, ins.next_ip)
    assert not lift.out or '+= ' not in lift.out[-1][1]


def test_value_test_compares_against_zero():
    lift = lifter({'RAX': Expr('n', INT, 'int')})
    execute(lift, '85c0')  # test eax,eax
    assert lift.flags[1].text == '0'


def test_null_test_compares_against_null():
    lift = lifter({'RAX': Expr('o', CLASS, 'obj')})
    execute(lift, '85c0')  # test eax,eax
    assert lift.flags[1].text == 'null'


def test_zero_stored_to_reference_renders_null():
    lift = lifter()
    assert lift._fimm('0', STRING) == 'null'
    assert lift._fimm('0', CLASS) == 'null'


def test_zero_stored_to_byref_stays_zero_and_bool_unaffected():
    lift = lifter(il=NS(
        types=[INT],
        _type_enum=lambda t: (t[1] >> 16) & 0xFF if t else 0,
        instance_field_chain=lambda td: {},
        type_from_ptr=lambda ptr: None,
        enum_members=lambda etd: None,
    ))
    assert lift._fimm('0', (0, (0x12 << 16) | (1 << 29))) == '0'
    assert lift._fimm('0', (0, 0x02 << 16)) == 'false'
    assert lift._fimm('1', (0, 0x02 << 16)) == 'true'


def struct_lifter():
    chain = {0x10: ('x', 1), 0x14: ('y', 1), 0x18: ('z', 1)}
    il = NS(
        types=[INT, F32, V3],
        _type_enum=lambda t: (t[1] >> 16) & 0xFF if t else 0,
        _sf_field_size=lambda ty, _: {F32: 4, V3: 12}.get(ty),
        _closed_type_key=lambda t: t,
        instance_field_chain=lambda td: chain,
        type_from_ptr=lambda ptr: None,
        type_name=lambda ty: 'UnityEngine.Vector3',
    )
    lift = lifter(il=il)
    lift.meta = NS(typedefs=[NS(is_valuetype=True, name='Vector3')])
    return lift


def test_full_struct_reconstructs_initializer():
    lift = struct_lifter()
    lift._stack_store(0x20, 4, Expr('1.0f', F32, 'float'))
    lift._stack_store(0x24, 4, Expr('2.0f', F32, 'float'))
    lift._stack_store(0x28, 4, Expr('3.0f', F32, 'float'))
    assert lift._stack_struct(0x20, V3) == \
        'new UnityEngine.Vector3 { x = 1.0f, y = 2.0f, z = 3.0f }'


def test_partial_struct_returns_no_guessed_fields():
    lift = struct_lifter()
    lift._stack_store(0x20, 4, Expr('1.0f', F32, 'float'))
    lift._stack_store(0x28, 4, Expr('3.0f', F32, 'float'))
    assert lift._stack_struct(0x20, V3) is None


def test_overlapping_store_splits_surviving_ranges():
    lift = struct_lifter()
    lift._stack_store(0x20, 8, Expr('wide', None, 'bits'))
    lift._stack_store(0x24, 4, Expr('1.0f', F32, 'float'))
    tiled = lift._stack_piece(0x20, 8)
    assert tiled is not None and len(tiled._parts) == 2  # exact tiling, no gap
    assert lift._stack_piece(0x24, 4).text == '1.0f'


def test_gapped_request_returns_proven_prefix():
    lift = struct_lifter()
    lift._stack_store(0x20, 4, Expr('a', F32, 'float'))
    lift._stack_store(0x28, 4, Expr('b', F32, 'float'))
    tiled = lift._stack_piece(0x20, 12)
    assert tiled is not None and len(tiled._parts) == 1
    assert lift._piece_value(tiled, 0, 4, F32).text == 'a'
    assert lift._piece_value(tiled, 4, 4, F32) is None


def test_narrow_provenance_records_prefix_not_nothing():
    lift = struct_lifter()
    v = Expr('w', INT, 'int')
    v._slice = (Expr('o', None, 'obj'), 0, 4)
    lift._stack_store(0x20, 8, v)
    assert '!mem:32:4' in lift.regs
    assert '!mem:32:8' not in lift.regs


def test_tiled_composite_routes_per_tile():
    lift = struct_lifter()
    lift._stack_store(0x20, 4, Expr('4', None, 'int'))
    lift._stack_store(0x24, 4, Expr('2.0f', F32, 'float'))
    tiled = lift._stack_piece(0x20, 8)
    assert lift._piece_value(tiled, 4, 4, F32).text == '2.0f'
    assert lift._piece_value(tiled, 0, 4, F32) is not None


def test_sliced_stack_store_still_emits_the_statement():
    lift = struct_lifter()
    frag = Expr('o.field', F32, 'float')
    frag._slice = (Expr('o', None, 'obj'), 0, 4)
    lift.regs['RAX'] = frag
    execute(lift, '89442410')  # mov [rsp+10h],eax
    assert any('s_10' in s[1] and 'o.field' in s[1] for s in lift.out)
    assert lift._stack_piece(0x10, 4).text == 'o.field'


def test_stack_store_load_roundtrip():
    lift = struct_lifter()
    lift.regs['RAX'] = Expr('n', INT, 'int')
    execute(lift, '4889442410')  # mov [rsp+10h],rax
    execute(lift, '8b442410')  # mov eax,[rsp+10h]
    assert lift.regs['RAX'].text == 'n'


PREFIX = bytes.fromhex(
    '48895c2408574883ec20498b184533c9498bf8440fb7932e010000'
    '66453bca73264c8b9bb00000000f1f840000000000410fb7c14803c0'
    '493914c3742d6641ffc166453bca72e9440fb7c1488bcfe8')
SUFFIX = bytes.fromhex(
    '4c8b00488bcf488b5008488b5c24304883c4205f49ffe0410fb7d1'
    '4803d20fb7c9418b44d30803c1489848c1e0044805380100004803c3ebc7')


def iface_lifter(code):
    target = 0x5000
    il = NS(
        types=[INT],
        _type_enum=lambda t: (t[1] >> 16) & 0xFF if t else 0,
        _return_abi_is_known=lambda rt: True,
        returns_sret=lambda rt: False,
        method_simple_name=lambda mi: 'IFoo.Bar',
    )
    lift = lifter(il=il)
    lift.meta = NS(
        typedefs=[NS(flags=0x20, method_count=4, method_start=0)],
        methods=[NS(return_type=0, is_static=False, param_count=0,
                    name='IFoo.Bar')],
    )
    lift.bin = NS(read=lambda va, n: code if va == target and n == len(code) else None)
    return lift, target


def dispatch_args():
    return [Expr('0', INT, 'int'), Expr('typeof(IFoo)', (0, 0x12 << 16), 'klass'),
            Expr('rec', CLASS, 'obj')]


def test_nullary_interface_dispatch_recognized():
    lift, target = iface_lifter(PREFIX + b'\x00\x00\x00\x00' + SUFFIX)
    assert lift._nullary_interface_dispatch(target, dispatch_args()) is not None


def test_nullary_interface_dispatch_rejects_mutated_bytes():
    bad = bytearray(PREFIX + b'\x00\x00\x00\x00' + SUFFIX)
    bad[10] ^= 0xFF
    lift, target = iface_lifter(bytes(bad))
    assert lift._nullary_interface_dispatch(target, dispatch_args()) is None


def test_nullary_interface_dispatch_rejects_non_interface():
    lift, target = iface_lifter(PREFIX + b'\x00\x00\x00\x00' + SUFFIX)
    lift.meta.typedefs[0].flags = 0x00
    assert lift._nullary_interface_dispatch(target, dispatch_args()) is None


def test_nullary_interface_dispatch_rejects_out_of_range_slot():
    lift, target = iface_lifter(PREFIX + b'\x09\x00\x00\x00' + SUFFIX)
    args = [Expr('9', INT, 'int'), dispatch_args()[1], dispatch_args()[2]]
    assert lift._nullary_interface_dispatch(target, args) is None


# The fixture's hot dispatcher family carries different prologues from the
# PREFIX/SUFFIX template above but the same interface-offset arithmetic.
# These are the real bodies (0x180002210 nullary, 0x180006020 forwarding
# one managed argument through R9) with the varying call displacement zeroed.
B_DISPATCH = bytes.fromhex(
    '40534883ec20498bd833c0440fb7c14c8b1b450fb78b2e01000066413bc17325'
    '4d8b93b0000000660f1f8400000000000fb7c84803c9493914ca742366ffc0'
    '66413bc172eb488bcbe800000000488bcb4c8b00488b50084883c4205b49ffe0'
    '0fb7d0488bcb4803d2418b44d2084103c0489848c1e0044805380100004903c3'
    '4c8b00488b50084883c4205b49ffe0')
A_DISPATCH = bytes.fromhex(
    '48895c24084889742410574883ec20498bf833c0498bf1440fb7c1488b1f440fb7'
    '932e01000066413bc2731c4c8b9bb00000000fb7c84803c9493914cb742d66ffc0'
    '66413bc272eb488bcfe8000000004c8b4008488bd6488bcf488b5c2430488b742438'
    '4883c4205f48ff200fb7d04803d2418b44d3084103c0489848c1e004480538010000'
    '4803c3ebc5')


def dispatch_helper_lifter(body):
    target = 0x5000
    il = NS(
        types=[INT],
        _type_enum=lambda t: (t[1] >> 16) & 0xFF if t else 0,
        _return_abi_is_known=lambda rt: True,
        returns_sret=lambda rt: False,
        function_extent=lambda va: (target, target + len(body)),
        addr_candidates={},
    )
    lift = lifter(il=il)
    lift.meta = NS(
        typedefs=[NS(flags=0x20, method_count=4, method_start=0)],
        methods=[NS(return_type=0, is_static=False, param_count=0,
                    name='IFoo.Bar')],
    )
    lift.bin = NS(
        read=lambda va, n: body if va == target and n == len(body) else None,
        is_exec_va=lambda va: va == target,
        exports={},
    )
    return lift, target


def test_iface_dispatch_arity_proves_the_nullary_family():
    lift, target = dispatch_helper_lifter(B_DISPATCH)
    assert lift._iface_dispatch_arity(target) == 0


def test_iface_dispatch_arity_counts_a_forwarded_argument():
    lift, target = dispatch_helper_lifter(A_DISPATCH)
    assert lift._iface_dispatch_arity(target) == 1


def test_iface_dispatch_arity_rejects_a_mutated_body():
    bad = bytearray(B_DISPATCH)
    bad[0x16] ^= 0x01          # low byte of the word [k+0x12E] displacement
    lift, target = dispatch_helper_lifter(bytes(bad))
    assert lift._iface_dispatch_arity(target) is None


def test_nullary_interface_dispatch_admits_the_structural_family():
    lift, target = dispatch_helper_lifter(B_DISPATCH)
    lift.rt_iface = {target: 0}
    assert lift._nullary_interface_dispatch(target, dispatch_args()) is not None


def test_nullary_interface_dispatch_declines_an_argument_forwarder():
    lift, target = dispatch_helper_lifter(A_DISPATCH)
    lift.rt_iface = {target: 1}
    assert lift._nullary_interface_dispatch(target, dispatch_args()) is None


def test_iface_dispatch_arity_declines_a_writes_first_body():
    # the A-family's only R9 touch (`mov rsi,r9` at 0x14) rewritten as a
    # write (`mov r9,rsi`): the caller's R9 is dead on arrival, so no
    # managed argument may be forwarded (0x180540f50's shape).
    bad = bytearray(A_DISPATCH)
    assert bytes(bad[0x14:0x17]) == bytes.fromhex('498bf1')
    bad[0x14:0x17] = bytes.fromhex('4c8bce')
    lift, target = dispatch_helper_lifter(bytes(bad))
    assert lift._iface_dispatch_arity(target) == 0


def test_r9_touch_classifies_positions():
    from iced_x86 import Decoder

    def touch(hex_bytes):
        ins = next(iter(Decoder(64, bytes.fromhex(hex_bytes), ip=0x5000)))
        return Lifter._r9_touch(ins)

    assert touch('498bf1') == 'read'    # mov rsi,r9 (forward)
    assert touch('4c8bce') == 'write'   # mov r9,rsi (manufacture)
    assert touch('4d31c9') == 'write'   # xor r9,r9 (template zeroing)
    assert touch('4c8b0d00000000') == 'write'  # mov r9,[rip] (load)
    assert touch('493bc1') == 'read'    # cmp rax,r9 (source)
    assert touch('4d3bc8') == 'read'    # cmp r9,r8 (CMP reads op0)


def test_r9_touch_reads_memory_bases():
    from iced_x86 import Decoder

    def touch(hex_bytes):
        ins = next(iter(Decoder(64, bytes.fromhex(hex_bytes), ip=0x5000)))
        return Lifter._r9_touch(ins)

    assert touch('488b01') is None      # mov rax,[rcx]: no r9 anywhere
    assert touch('4d8b0121') == 'read'    # mov r8,[r9]: base is read
    assert touch('4d890121') == 'read'    # mov [r9],r8: base is still read
    assert touch('4a8b0c4d00000000') == 'read'  # mov rcx,[r9*2]: index read


def test_iface_arity_memoizes_structural_proof():
    lift, target = dispatch_helper_lifter(A_DISPATCH)
    lift.rt_iface = {}
    assert lift._iface_arity(target) == 1
    assert lift.rt_iface[target] == 1
    assert lift._iface_arity(0x9999) is None


def _param_dispatcher_lifter(body, n_params=1, r9_kind='obj', r9_text='arg1', r9_ty=None):
    target = 0x5000
    RET = (9, 0x12 << 16)
    il = NS(
        types=[INT, RET],
        _type_enum=lambda t: (t[1] >> 16) & 0xFF if t else 0,
        _return_abi_is_known=lambda rt: True,
        _closed_type_key=lambda t: t,
        _sf_field_size=lambda fty, depth: 4 if fty == INT else None,
        returns_sret=lambda rt: False,
        type_name=lambda t: 'IFoo' if t == RET else 'int',
        function_extent=lambda va: (target, target + len(body)),
        addr_candidates={},
    )
    lift = lifter(il=il)
    lift.meta = NS(
        typedefs=[NS(namespace='', name='IFoo', flags=0x20,
                      method_count=4, method_start=0)],
        methods=[NS(return_type=1, is_static=False, param_count=n_params,
                    name='Take', generic_container=-1, declaring=0)
                 for _ in range(4)],
        method_params=lambda m: [NS(type=0)] * n_params,
    )
    lift.bin = NS(
        read=lambda va, n: body if va == target and n == len(body) else None,
        is_exec_va=lambda va: va == target,
        exports={},
    )
    lift.rt_iface = {target: 1}
    args = [Expr('3', INT, 'int'), Expr('typeof(IFoo)', (0, 0x12 << 16), 'klass'),
            Expr('rec', CLASS, 'obj'), Expr(r9_text, r9_ty or INT, r9_kind)]
    return lift, target, args


def test_param_dispatch_resolves_a_typed_argument():
    lift, target, args = _param_dispatcher_lifter(A_DISPATCH)
    got = lift._param_interface_dispatch(target, args)
    assert got is not None and got[0] == 3 and got[1].text == 'rec'


def test_param_dispatch_drops_to_zero_params():
    lift, target, args = _param_dispatcher_lifter(A_DISPATCH, n_params=0)
    got = lift._param_interface_dispatch(target, args)
    assert got is not None and len(got) == 3 and got[0] == 3


def test_param_dispatch_declines_multi_param():
    lift, target, args = _param_dispatcher_lifter(A_DISPATCH, n_params=3)
    assert lift._param_interface_dispatch(target, args) is None


def test_param_dispatch_declines_untyped_r9():
    for kind, text, ty in (('float', 'real1', None), ('obj', '?', None),
                           ('obj', '_', None), ('obj', '', None),
                           ('?', 'v1', CLASS)):
        lift, target, args = _param_dispatcher_lifter(
            A_DISPATCH, r9_kind=kind, r9_text=text, r9_ty=ty)
        assert lift._param_interface_dispatch(target, args) is None, (kind, text)


def test_param_dispatch_resolves_typed_unknown_r9():
    lift, target, args = _param_dispatcher_lifter(
        A_DISPATCH, r9_kind='?', r9_text='v1')
    got = lift._param_interface_dispatch(target, args)
    assert got is not None and len(got) == 4 and got[3].text == 'v1'


def test_param_dispatch_resolves_stack_args():
    lift, target, args = _param_dispatcher_lifter(A_DISPATCH, n_params=3)
    lift._stack_store(32, 4, Expr('0', INT, 'int'))
    lift._stack_store(40, 4, Expr('count1', INT, 'int'))
    got = lift._param_interface_dispatch(target, args)
    assert got is not None and len(got) == 6 and got[0] == 3
    assert got[4].text == '0' and got[5].text == 'count1'


def test_param_dispatch_declines_missing_stack_tile():
    lift, target, args = _param_dispatcher_lifter(A_DISPATCH, n_params=3)
    lift._stack_store(32, 4, Expr('0', INT, 'int'))
    assert lift._param_interface_dispatch(target, args) is None


def test_param_dispatch_declines_writes_first_body():
    bad = bytearray(A_DISPATCH)
    bad[0x14:0x17] = bytes.fromhex('4c8bce')
    lift, target, args = _param_dispatcher_lifter(bytes(bad))
    lift.rt_iface = {}                # no cached verdict: prove it live
    assert lift._param_interface_dispatch(target, args) is None
    assert lift.rt_iface[target] == 0  # ...and the decline is memoized


def test_return_value_register_abi():
    assert Lifter._return_value_register(F32) == 'XMM0'
    assert Lifter._return_value_register((0, 0x0D << 16)) == 'XMM0'
    assert Lifter._return_value_register((0, (0x0C << 16) | (1 << 29))) == 'RAX'
    assert Lifter._return_value_register(INT) == 'RAX'
    assert Lifter._return_value_register(None) == 'RAX'


def test_get_item_sret_folds_to_indexer():
    from test_stack_args import make_call_lifter
    lift, ins = make_call_lifter(
        [INT], {'RCX': '&s_20', 'RDX': 'this', 'R8': '0'},
        returns=V3, static=False, name='get_Item')
    lift.il = NS(
        meta=lift.meta, types=[V3, INT, INT],
        addr_candidates=lift.il.addr_candidates,
        addr_to_method=lift.il.addr_to_method,
        function_extent=lift.il.function_extent,
        returns_sret=lambda ty: True,
        _type_enum=lift.il._type_enum,
        type_from_ptr=lambda ptr: None,
    )
    lift._insn(ins, [ins], 0, None, ins.next_ip)
    assert lift.out and lift.out[-1][1] == 's_20 = this[0];'


def test_lea_names_negative_frame_slot_by_abs_convention():
    lift = lifter()
    lift.rsp_delta = -0x88
    execute(lift, '488d542450')  # lea rdx,[rsp+50h]
    e = lift.regs['RDX']
    assert e.text == '&s_50'
    assert 'ffff' not in e.text
    assert e._stack_offset == -0x38


def test_write_barrier_records_the_pointer_store():
    from test_stack_args import make_call_lifter
    from il2cpp import Expr as _Expr
    rcx = _Expr('&s_28', None, 'ptr')
    rcx._stack_offset = -56
    lift, ins = make_call_lifter([], {'RCX': rcx, 'RDX': 'prev1'}, returns=(0, 0x01 << 16))
    lift.rt_wbarrier = {0x2000}
    lift.il._sf_field_size = lambda ty, _: 8
    lift._insn(ins, [ins], 0, None, ins.next_ip)
    assert '!mem:-56:8' in lift.regs
    assert any('s_28' in s[1] and 'prev1' in s[1] for s in lift.out)


def test_nonzero_slice_reroots_to_base():
    from il2cpp import Expr as _Expr
    lift = struct_lifter()
    base = _Expr('m', V3, 'obj')
    frag = lift._fragment(base, 4, 8)
    assert lift._piece_value(frag, 0, 4, F32).text == 'm.y'
    assert lift._piece_value(frag, 4, 4, F32).text == 'm.z'


def test_zero_offset_slice_resolves_through_base():
    lift = struct_lifter()
    lift._stack_store(0x20, 4, Expr('a', F32, 'float'))
    lift._stack_store(0x24, 4, Expr('b', F32, 'float'))
    tiled = lift._stack_piece(0x20, 8)
    frag = lift._fragment(tiled, 0, 4)
    assert lift._piece_value(frag, 0, 4, F32).text == 'a'


def test_slice_overhang_declines():
    from il2cpp import Expr as _Expr
    lift = struct_lifter()
    base = _Expr('m', V3, 'obj')
    frag = lift._fragment(base, 0, 4)
    assert lift._piece_value(frag, 0, 8, F32) is None


def test_straddling_fragment_keeps_origin_type():
    lift = struct_lifter()
    origin = Expr('v', V3, 'obj')
    frag = lift._fragment(origin, 0, 8)
    assert frag.ty == V3
    assert frag.kind == 'bits'
    assert lift._piece_value(frag, 0, 4, F32).text == 'v.x'


def test_hint_never_downgrades_a_typed_operand():
    lift = lifter()
    lift._hint_tok(Expr('t1', INT, 'int'), F32)
    assert 't1' not in lift._type_hints
    lift._hint_tok(Expr('t9', None, 'int'), F32)
    assert lift._type_hints['t9'] == F32


def test_intptr_tests_against_null():
    il = NS(
        types=[INT],
        _type_enum=lambda t: (t[1] >> 16) & 0xFF if t else 0,
        type_name=lambda t: 'System.IntPtr' if t == (0, 0x18 << 16) else 'System.Guid',
        instance_field_chain=lambda td: {},
        type_from_ptr=lambda ptr: None,
    )
    lift = lifter(il=il)
    lift.meta = NS(typedefs=[
        NS(name='IntPtr', namespace='System', is_valuetype=True),
        NS(name='Guid', namespace='System', is_valuetype=True),
    ])
    assert lift._test_is_value(Expr('p', (0, 0x18 << 16), 'obj')) is False
    assert lift._test_is_value(Expr('g', (1, 0x11 << 16), 'obj')) is True


def test_byref_param_kills_the_slot_cache():
    from test_stack_args import make_call_lifter
    from il2cpp import Expr as _Expr
    REF_INT = (0, (0x08 << 16) | (1 << 29))
    rcx = _Expr('&s_10', None, 'ptr')
    rcx._stack_offset = 0x10
    lift, ins = make_call_lifter([REF_INT], {'RCX': rcx},
                                 returns=(0, 0x01 << 16))
    lift.il._sf_field_size = lambda ty, _: 4
    lift.stack_map[0x10] = 's_10'
    stale = _Expr('stale', (0, 0x08 << 16), 'int')
    lift.stack_values['s_10'] = stale
    lift._stack_store(0x10, 4, stale)
    assert '!mem:16:4' in lift.regs
    lift._insn(ins, [ins], 0, None, ins.next_ip)
    assert 's_10' not in lift.stack_values
    assert '!mem:16:4' not in lift.regs


def test_ctor_on_stack_buffer_records_construction():
    from test_stack_args import make_call_lifter
    from il2cpp import Expr as _Expr
    rcx = _Expr('&s_20', None, 'ptr')
    rcx._stack_offset = 0x30
    lift, ins = make_call_lifter([], {'RCX': rcx}, returns=(0, 0x01 << 16),
                                 static=False, name='.ctor')
    lift.meta.typedefs[0] = NS(name='T', namespace='', is_valuetype=True)
    lift.il._sf_field_size = lambda ty, _: 16
    lift.stack_map[0x30] = 's_20'
    lift._insn(ins, [ins], 0, None, ins.next_ip)
    assert '!mem:48:16' in lift.regs
    assert any('.ctor(' in s[1] for s in lift.out)


def test_non_ctor_call_records_no_buffer():
    from test_stack_args import make_call_lifter
    from il2cpp import Expr as _Expr
    rcx = _Expr('&s_20', None, 'ptr')
    rcx._stack_offset = 0x30
    lift, ins = make_call_lifter([], {'RCX': rcx}, returns=(0, 0x01 << 16),
                                 static=False, name='Reset')
    lift.meta.typedefs[0] = NS(name='T', namespace='', is_valuetype=True)
    lift.il._sf_field_size = lambda ty, _: 16
    lift._insn(ins, [ins], 0, None, ins.next_ip)
    assert not [k for k in lift.regs if k.startswith('!mem:')]


def test_movdqa_mem_store_emits_and_records():
    lift = struct_lifter()
    lift.regs['XMM0'] = Expr('c', F32, 'float')
    execute(lift, '660f7f442410')  # movdqa [rsp+10h],xmm0
    assert any('s_10' in s[1] and 'c' in s[1] for s in lift.out)
    assert lift._stack_piece(0x10, 4).text == 'c'


def test_ignored_call_result_flushes_as_bare_statement():
    from test_stack_args import make_call_lifter
    from il2cpp.expr import _RegState
    lift, ins = make_call_lifter([], {'RCX': 'a'}, returns=INT)
    lift.regs = _RegState(lift, lift.regs)
    lift._insn(ins, [ins], 0, None, ins.next_ip)
    lift._flush_pending_calls()
    assert lift.out == [(0x1000, 'Example.Target();', None)]


def test_used_call_result_renders_inline_without_flush():
    from test_stack_args import make_call_lifter
    from il2cpp.expr import _RegState
    lift, ins = make_call_lifter(
        [INT], {'RCX': 'a'},
        returns=INT,
    )
    lift.regs = _RegState(lift, lift.regs)
    lift._insn(ins, [ins], 0, None, ins.next_ip)
    execute(lift, '4889442410')  # mov [rsp+10h],rax reads the result
    lift._flush_pending_calls()
    assert len(lift.out) == 1
    assert lift.out[0][1] == 's_10 = Example.Target(a);'


def test_generic_return_inflates_to_closed_type():
    from test_stack_args import make_call_lifter
    lift, ins = make_call_lifter([INT], {'RCX': 'a'}, returns=(0, 0x13 << 16))
    lift.il = NS(
        meta=lift.meta, types=[(0, 0x13 << 16), INT],
        addr_candidates={0x2000: [('generic', 0)]},
        addr_to_method={0x2000: ('generic', 0)},
        function_extent=lift.il.function_extent,
        returns_sret=lambda ty: False,
        _type_enum=lift.il._type_enum,
        type_from_ptr=lambda ptr: None,
        method_specs=[(0, 1)],
        candidate_return_type=lambda info: INT,
        generic_method_name=lambda i: 'Example.Target',
        _method_spec_type_args=lambda i: [],
    )
    lift._insn(ins, [ins], 0, None, ins.next_ip)
    assert lift.regs['RAX'].ty == INT


def color_lifter():
    lift = struct_lifter()
    lift.il.type_name = lambda ty: 'UnityEngine.Color'
    return lift


def test_color_red_bytes_render_named():
    lift = color_lifter()
    origin = Expr('(float4)(1, 0, 0, 1)', None, 'float')
    origin._bytes = struct.pack('<4f', 1.0, 0.0, 0.0, 1.0)
    got = lift._piece_value(origin, 0, 16, V3)
    assert got is not None and got.text == 'UnityEngine.Color.red'


def test_color_arbitrary_bytes_render_constructor():
    lift = color_lifter()
    origin = Expr('c', None, 'float')
    origin._bytes = struct.pack('<4f', 0.5, 0.25, 0.125, 1.0)
    got = lift._piece_value(origin, 0, 16, V3)
    assert got is not None
    assert got.text.startswith('new UnityEngine.Color(')
    assert got.text.endswith(')')
    assert got.text.count(',') == 3


def test_color_partial_bytes_decline():
    lift = color_lifter()
    origin = Expr('c', None, 'float')
    origin._bytes = struct.pack('<4f', 1.0, 0.0, 0.0, 1.0)
    assert lift._piece_value(origin, 0, 8, V3) is None


def rgba_lifter():
    chain = {0x10: ('r', 1), 0x14: ('g', 1), 0x18: ('b', 1), 0x1C: ('a', 1)}
    il = NS(
        types=[INT, F32, V3],
        _type_enum=lambda t: (t[1] >> 16) & 0xFF if t else 0,
        _sf_field_size=lambda ty, _: {F32: 4, V3: 16}.get(ty),
        _closed_type_key=lambda t: t,
        instance_field_chain=lambda td: chain,
        type_from_ptr=lambda ptr: None,
        type_name=lambda ty: 'MyGame.Tint',
    )
    lift = lifter(il=il)
    lift.meta = NS(typedefs=[NS(is_valuetype=True, name='Tint')])
    return lift


def test_rgba_struct_bytes_render_own_constructor():
    lift = rgba_lifter()
    origin = Expr('c', None, 'float')
    origin._bytes = struct.pack('<4f', 1.0, 0.0, 0.0, 1.0)
    got = lift._piece_value(origin, 0, 16, V3)
    assert got is not None
    assert got.text == 'new MyGame.Tint(1.0f, 0.0f, 0.0f, 1.0f)'
    assert 'UnityEngine.Color' not in got.text


def test_three_float_struct_declines_color_assembly():
    lift = struct_lifter()
    origin = Expr('c', None, 'float')
    origin._bytes = struct.pack('<4f', 1.0, 0.0, 0.0, 1.0)
    assert lift._piece_value(origin, 0, 16, V3) is None


def ternary_dec():
    dec = Decompiler.__new__(Decompiler)
    dec._var_types = {}
    return dec


def test_ternary_bool_arm_reconciliation():
    # MicAudioCanvas.Update: the false-arm `0` is a phi copy that never
    # passes the lifter `_fimm`, so the fold keeps `int num2`. The true
    # arm's identical text is bool-declared elsewhere (itself `_var_types`
    # bool tracking), proving the ternary bool: the literal becomes
    # `false` and the shared temp takes the `bool` declaration.
    dec = ternary_dec()
    lines = [
        "bool flag9 = this._recorder.IsCurrentlyTransmitting;",
        "if (obj12 == InputMode.OpenMic)",
        "{",
        "int num2 = this._recorder.IsCurrentlyTransmitting;",
        "}",
        "else",
        "{",
        "int num2 = 0;",
        "}",
        "this.openMic.SetActive(num2);",
    ]
    assert dec._ternary_pass(list(lines)) == [
        "bool flag9 = this._recorder.IsCurrentlyTransmitting;",
        "bool num2 = obj12 == InputMode.OpenMic"
        " ? this._recorder.IsCurrentlyTransmitting : false;",
        "this.openMic.SetActive(num2);",
    ]
    # no bool proof anywhere: the int decl and the `0` arm survive.
    dec2 = ternary_dec()
    lines2 = [
        "if (cond1)",
        "{",
        "int num2 = obj3;",
        "}",
        "else",
        "{",
        "int num2 = 0;",
        "}",
    ]
    assert dec2._ternary_pass(list(lines2)) == [
        "int num2 = cond1 ? obj3 : 0;",
    ]
    # the literal must be exactly `0`/`1` (`00` declines).
    dec3 = ternary_dec()
    lines3 = [
        "bool flag9 = this._recorder.IsCurrentlyTransmitting;",
        "if (cond1)",
        "{",
        "int num2 = this._recorder.IsCurrentlyTransmitting;",
        "}",
        "else",
        "{",
        "int num2 = 00;",
        "}",
    ]
    assert dec3._ternary_pass(list(lines3)) == [
        "bool flag9 = this._recorder.IsCurrentlyTransmitting;",
        "int num2 = cond1 ? this._recorder.IsCurrentlyTransmitting : 00;",
    ]


def test_phi_decl_hoist_across_if_else():
    # MicAudioCanvas.Update PTT shape: `bool flag6` is declared in both
    # gamepad arms but read after the join. The hoist strips both tails
    # to bare assignments and declares once above the `if`.
    dec = Decompiler.__new__(Decompiler)
    lines = [
        "if (flag5)",
        "{",
        "UnityEngine.InputSystem.InputActionAsset obj15 = this.playerInput.actions;",
        "bool flag6 = obj15[\"PushToTalk\"].IsPressed();",
        "}",
        "else",
        "{",
        "bool flag7 = Foo();",
        "bool flag6 = flag7;",
        "}",
        "bool flag8 = flag6;",
    ]
    assert dec._phi_decl_hoist(list(lines)) == [
        "bool flag6;",
        "if (flag5)",
        "{",
        "UnityEngine.InputSystem.InputActionAsset obj15 = this.playerInput.actions;",
        "flag6 = obj15[\"PushToTalk\"].IsPressed();",
        "}",
        "else",
        "{",
        "bool flag7 = Foo();",
        "flag6 = flag7;",
        "}",
        "bool flag8 = flag6;",
    ]
    # an earlier assignment of the same temp declines (scope unproven).
    lines2 = ["flag6 = Foo();"] + lines
    assert dec._phi_decl_hoist(list(lines2)) == lines2


def test_phi_decl_hoist_two_values_with_non_tail_declarations():
    dec = Decompiler.__new__(Decompiler)
    lines = [
        "if (empty)", "{", "Image image1 = left;", "Sprite sprite1 = a;",
        "}", "else", "{", "Image image1 = right;", "Sprite sprite1 = b;",
        "}", "image1.sprite = sprite1;",
    ]
    assert dec._phi_decl_hoist(lines) == [
        "Sprite sprite1;", "Image image1;",
        "if (empty)", "{", "image1 = left;", "sprite1 = a;",
        "}", "else", "{", "image1 = right;", "sprite1 = b;",
        "}", "image1.sprite = sprite1;",
    ]


def test_phi_chain_hoists_only_complete_three_arm_assignments():
    dec = Decompiler.__new__(Decompiler)
    lines = [
        "if (nan)", "{", "Call();", "float real1 = a;", "}",
        "else if (nonzero)", "{", "Call();", "float real1 = b;", "}",
        "else", "{", "float real1 = c;", "}",
        "Use(real1);",
    ]
    assert dec._phi_chain_decl_hoist(lines) == [
        "float real1;", "if (nan)", "{", "Call();", "real1 = a;", "}",
        "else if (nonzero)", "{", "Call();", "real1 = b;", "}",
        "else", "{", "real1 = c;", "}", "Use(real1);",
    ]
    no_else = lines[:10] + ["Use(real1);"]
    assert dec._phi_chain_decl_hoist(no_else) == no_else
    with_exit = lines.copy()
    with_exit.insert(8, "return;")
    assert dec._phi_chain_decl_hoist(with_exit) == with_exit
    unresolved = [line.replace("float real1", "object obj1")
                  .replace("real1", "obj1") for line in lines]
    assert dec._phi_chain_decl_hoist(unresolved) == unresolved

def phi_color_lifter():
    chain = {0x10: ('r', 1), 0x14: ('g', 1), 0x18: ('b', 1), 0x1C: ('a', 1)}
    il = NS(
        types=[INT, F32, V3],
        _type_enum=lambda t: (t[1] >> 16) & 0xFF if t else 0,
        _sf_field_size=lambda ty, _: {F32: 4, V3: 16}.get(ty),
        _closed_type_key=lambda t: t,
        instance_field_chain=lambda td: chain,
        type_from_ptr=lambda ptr: None,
        type_name=lambda ty: 'UnityEngine.Color',
    )
    lift = lifter(il=il)
    lift.meta = NS(typedefs=[NS(is_valuetype=True, name='Color')])
    lift._phi_bytes = {}
    return lift


def test_phi_unanimous_bytes_assemble_color():
    lift = phi_color_lifter()
    raw = struct.pack('<4f', 1.0, 0.0, 0.0, 1.0)
    lift._stack_store(0x20, 16, Expr('v999', None, 'float'))
    lift._phi_bytes = {(7, 'v999'): {3: raw, 5: raw}}
    assert lift._stack_struct(0x20, V3) == 'UnityEngine.Color.red'


def test_phi_disagreeing_bytes_decline():
    lift = phi_color_lifter()
    red = struct.pack('<4f', 1.0, 0.0, 0.0, 1.0)
    green = struct.pack('<4f', 0.0, 1.0, 0.0, 1.0)
    lift._stack_store(0x20, 16, Expr('v999', None, 'float'))
    lift._phi_bytes = {(7, 'v999'): {3: red, 5: green}}
    assert lift._stack_struct(0x20, V3) is None


# The fixture's IsInst helper (thunk 0x180434690 -> 0x180479f80), copied
# byte for byte. The recognizer must prove the body, never the address.
ISINST_BODY = bytes.fromhex(
    '48895c24104889742418574883ec20488bda488bf94885c90f84e3000000'
    '488b31488bcb488bd6e81470010084c00f85ba000000f6863601000010'
    '0f84c0000000f6831801000020750c807b2a137406807b2a1e757b4883'
    '7b70007474488b4370488b70284885f67467488bd6488bcfe89b52fdff'
    '48894424304885c0756f488b47104c8d442430488b4f10488b10488b02'
    '488bd6ffd085c078364c8b442430488bd6488bcfe80514fdff84c07518'
    '488b4c2430488b01ff5010488bd6488bcfe84b52fdffeb05488b442430'
    '4885c0751d33c0483b1dc6eca003480f44c7488b5c2438488b74244048'
    '83c4205fc3488bc7488b5c2438488b7424404883c4205fc3488b5c2438'
    '33c0488b7424404883c4205fc3')


def isinst_helper_lifter(body):
    target = 0x5000
    il = NS(
        types=[INT],
        _type_enum=lambda t: (t[1] >> 16) & 0xFF if t else 0,
        function_extent=lambda va: (target, target + len(body)),
        addr_candidates={},
    )
    lift = lifter(il=il)
    lift.bin = NS(
        read=lambda va, n: body if va == target and n == len(body) else None,
        is_exec_va=lambda va: va == target,
        exports={},
    )
    return lift, target


def test_isinst_helper_recognized_structurally():
    lift, target = isinst_helper_lifter(ISINST_BODY)
    assert lift._is_isinst_helper(target)


def test_isinst_helper_rejects_a_mutated_body():
    bad = bytearray(ISINST_BODY)
    bad[0] ^= 0xFF                      # the prologue is the proof
    lift, target = isinst_helper_lifter(bytes(bad))
    assert not lift._is_isinst_helper(target)
    bad2 = bytearray(ISINST_BODY)
    bad2[ISINST_BODY.find(bytes.fromhex('480f44c7'))] ^= 0xFF   # cmove
    lift2, target2 = isinst_helper_lifter(bytes(bad2))
    assert not lift2._is_isinst_helper(target2)


# The Interlocked.CompareExchange helper body (lock cmpxchg core).
INTERLOCKED_BODY = bytes.fromhex(
    '40534883ec20498bd8498bc0f0480fb111480f45d8e846580300488bc34883c4205bc3')


def test_interlocked_helper_recognized_structurally():
    lift, target = isinst_helper_lifter(INTERLOCKED_BODY)
    assert lift._is_interlocked_helper(target)


def test_interlocked_helper_rejects_a_mutated_body():
    bad = bytearray(INTERLOCKED_BODY)
    bad[12] ^= 0xFF                     # the lock cmpxchg opcode
    lift, target = isinst_helper_lifter(bytes(bad))
    assert not lift._is_interlocked_helper(target)


# The out-of-line class-init helper body (56 bytes, three call displacements).
CLASS_INIT_BODY = bytes.fromhex(
    '40534883ec20488bd9e8e21d05004883bbd8000000007509488bc34883c4205bc3488b8b'
    'd8000000e873620300488bc833d2e8d90f0100cc')


def test_class_init_helper_recognized_structurally():
    lift, target = isinst_helper_lifter(CLASS_INIT_BODY)
    assert lift._is_class_init_helper(target)


def test_class_init_helper_rejects_a_mutated_body():
    bad = bytearray(CLASS_INIT_BODY)
    bad[0x10] ^= 0xFF                   # the [klass+0xD8] fast-path compare
    lift, target = isinst_helper_lifter(bytes(bad))
    assert not lift._is_class_init_helper(target)


# The interface slow-path resolve helper (0x18043dc60, 137 bytes, four
# internal calls, fail-path int3). (obj, iface, slot) in RCX/RDX/R8.
IFACE_RESOLVE_BODY = bytes.fromhex(
    '48895c240848896c24104889742418574883ec20488b39488bd9488bcf410fb7f0'
    '488beae8670000004885c07536f6873601000010744248394310743c440fb7c6'
    '488bd5488bcbe814f30000488bd84885c07425488b4808488b4920e88f240500'
    '488bc3488b5c2430488b6c2438488b7424404883c4205fc3440fb7c6488bd548'
    '8bcfe8180d0000cc')


def test_iface_resolve_helper_recognized_structurally():
    lift, target = isinst_helper_lifter(IFACE_RESOLVE_BODY)
    assert lift._is_iface_resolve_helper(target)


def test_iface_resolve_helper_rejects_a_mutated_body():
    bad = bytearray(IFACE_RESOLVE_BODY)
    bad[0] ^= 0xFF                        # the prologue is the proof
    lift, target = isinst_helper_lifter(bytes(bad))
    assert not lift._is_iface_resolve_helper(target)
    bad2 = bytearray(IFACE_RESOLVE_BODY)
    bad2[IFACE_RESOLVE_BODY.find(bytes.fromhex('f6873601000010'))] ^= 0xFF
    lift2, target2 = isinst_helper_lifter(bytes(bad2))
    assert not lift2._is_iface_resolve_helper(target2)
