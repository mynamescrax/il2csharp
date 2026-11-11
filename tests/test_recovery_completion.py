"""Regressions for native UI/contact recovery, independent of output snapshots."""
from types import SimpleNamespace as NS

from il2cpp import Decompiler, Expr
from il2cpp.text import _ATOM_PREC, _bin_txt
from test_recovery_followup import lifter, execute, struct_lifter, V3, F32


def test_binary_composition_keeps_conditional_grouping():
    ternary = '((capacity <= 16) ? 16 : capacity)'
    assert _bin_txt(ternary, _ATOM_PREC, '-', '1', _ATOM_PREC) == ternary + ' - 1'
    assert _bin_txt('n', _ATOM_PREC, '|', ternary, _ATOM_PREC) == 'n | ' + ternary


def test_class_metadata_is_not_instance_aggregate_storage():
    from iced_x86 import Decoder
    lift = struct_lifter()
    for kind in ('klass', 'usage', 'sfblob'):
        lift.regs['RAX'] = Expr('typeof(V3)', V3, kind)
        ins = next(iter(Decoder(64, bytes.fromhex('f30f1000'), ip=0x1000)))
        assert lift._aggregate_load(ins) is None


def test_unpack_low_float_lanes_preserves_both_components():
    lift = struct_lifter()
    lift.regs.update(XMM0=Expr('x', F32, 'float'), XMM1=Expr('y', F32, 'float'))
    execute(lift, '0f14c1')  # unpcklps xmm0,xmm1
    packed = lift.regs['XMM0']
    assert lift._piece_value(packed, 0, 4, F32).text == 'x'
    assert lift._piece_value(packed, 4, 4, F32).text == 'y'
    assert lift._piece_value(packed, 8, 4, F32) is None


def _packed_floats(*names):
    packed = Expr(names[0], F32, 'bits')
    packed._parts = [(i * 4, Expr(name, F32, 'float'), 0, 4)
                     for i, name in enumerate(names)]
    return packed


def test_scalar_sse_arithmetic_preserves_high_lanes():
    lift = struct_lifter()
    lift.regs.update(XMM0=_packed_floats('x', 'y'),
                     XMM1=Expr('dx', F32, 'float'))
    execute(lift, 'f30f5cc1')  # subss xmm0,xmm1
    result = lift.regs['XMM0']
    assert lift._piece_value(result, 0, 4, F32).text == 'x - dx'
    assert lift._piece_value(result, 4, 4, F32).text == 'y'


def test_phi_preserves_unanimous_high_lane():
    lift = struct_lifter()
    phi = Expr('v99', F32, 'float')
    lift._aggregate_phi_sources = {
        'v99': [_packed_floats('left', 'same'),
                _packed_floats('right', 'same')],
    }
    lift._aggregate_phi_types = {}
    high = lift._piece_value(phi, 4, 4, F32)
    assert high.text == 'same'


def test_phi_declines_disputed_high_lane():
    lift = struct_lifter()
    phi = Expr('v99', F32, 'float')
    lift._aggregate_phi_sources = {
        'v99': [_packed_floats('left', 'a'),
                _packed_floats('right', 'b')],
    }
    lift._aggregate_phi_types = {}
    assert lift._piece_value(phi, 4, 4, F32) is None


def test_binding_keeps_packed_phi_provenance():
    lift = struct_lifter()
    phi = Expr('v99', F32, 'float')
    sources = [_packed_floats('left', 'same'),
               _packed_floats('right', 'same')]
    lift._aggregate_phi_sources = {'v99': sources}
    lift._aggregate_phi_types = {}
    lift._gp_blocked = set()
    lift._bind(phi)
    assert lift._aggregate_phi_sources[phi.text] is sources
    assert lift._piece_value(phi, 4, 4, F32).text == 'same'


def test_kill_on_write_keeps_safe_high_lane():
    lift = struct_lifter()
    packed = _packed_floats('old - dx', 'safe')
    frozen = lift._kill_one(packed, 'old', {})
    assert lift._piece_value(frozen, 0, 4, F32).text == frozen.text
    assert lift._piece_value(frozen, 4, 4, F32).text == 'safe'


def test_kill_on_write_freezes_stale_high_lane():
    lift = struct_lifter()
    packed = _packed_floats('old - dx', 'old.y')
    frozen = lift._kill_one(packed, 'old', {})
    high = lift._piece_value(frozen, 4, 4, F32)
    assert high.text.startswith('t')
    assert any('= old.y;' in line[1] for line in lift.out)


def test_boolean_xor_one_is_logical_negation():
    lift = lifter({'RAX': Expr('enabled', (0, 0x02 << 16), 'int')})
    execute(lift, '83f001')
    assert lift.regs['RAX'].text == '!(enabled)'


def test_boolean_constant_returns():
    dec = Decompiler.__new__(Decompiler)
    dec.L = NS(il=NS(types=[(0, 0x02 << 16)], _type_enum=lambda t: 2))
    assert dec._bool_sugar(['return 0;', 'return 1;'], NS(return_type=0)) == [
        'return false;', 'return true;']

from il2cpp.expr import _bind_replace


def test_bind_replace_blocks_longer_identifier_prefix():
    # Blocker 2: binding `...<>c.<>9` must not rewrite the static-field
    # store `...<>c.<>9__1_0` into the undeclared `t1012__1_0`.
    lhs = 'ConsoleUINavigation.<>c.<>9__1_0 = predicate13;'
    assert _bind_replace(lhs, 'ConsoleUINavigation.<>c.<>9', 't1012') == lhs


def test_bind_replace_allows_member_access_on_value():
    rhs = 'new P((ConsoleUINavigation.<>c.<>9).<OnEnable>b__1_0);'
    assert _bind_replace(rhs, 'ConsoleUINavigation.<>c.<>9', 't1012') == \
        'new P((t1012).<OnEnable>b__1_0);'


def test_bind_replace_blocks_token_prefix_and_member_suffix():
    assert _bind_replace('obj12 = obj1;', 'obj1', 'v9') == 'obj12 = v9;'
    assert _bind_replace('x.oldname = 1;', 'oldname', 'v9') == 'x.oldname = 1;'
    assert _bind_replace('p->field = q;', 'field', 'v9') == 'p->field = q;'

from il2cpp.expr import Expr as _Expr


def test_struct_home_ty_accepts_whole_field_values():
    from il2cpp.expr import _BOOL_TY
    lift = struct_lifter()
    assert lift._struct_home_ty(_Expr('nav', V3, 'float')) == V3
    assert lift._struct_home_ty(_Expr('nav', V3, 'obj')) == V3
    # slices, addresses, scalars and open generics decline
    sl = _Expr('nav', V3, 'float')
    sl._slice = (sl, 0, 4)
    assert lift._struct_home_ty(sl) is None
    assert lift._struct_home_ty(_Expr('&s_1', V3, 'ptr')) is None
    assert lift._struct_home_ty(_Expr('n', F32, 'float')) is None
    assert lift._struct_home_ty(_Expr('n', _BOOL_TY, 'int')) is None


def test_home_field_store_names_first_field():
    lift = struct_lifter()
    lift.il.value_type_size = lambda td: 12
    lift.slot_types['s_50'] = V3
    assert lift._home_field_store('s_50', 4, '0') == ('s_50.x', '0.0f', F32)
    assert lift._home_field_store('s_51', 4, '0') is None
    assert lift._home_field_store('s_50', 12, '0') is None


def test_byval_struct_home_hint_from_call_param():
    lift = struct_lifter()
    lift.il.returns_sret = lambda r: False
    lift.meta.method_params = lambda m: [NS(type=2)]
    lift.meta.methods = [NS(name='Add', declaring=0, is_static=False, param_count=1)]
    lift._call_class_args = None
    args = ['recv', '&s_20']
    exprs = [None, _Expr('s_20', None, 'local')]
    lift._hint_arg_types(args, exprs, 0, None)
    assert lift.slot_types.get('s_20') == V3
    assert args[1] == 's_20'

def test_packed_constant_load_is_pure():
    from il2cpp.dec.flow import _FlowMixin
    assert _FlowMixin._PURE_LOAD_RX.match('(float2)(0.0f, 1.0f)')
    assert not _FlowMixin._PURE_LOAD_RX.match('(float2)(Foo(), 1.0f)')
    dec = Decompiler.__new__(Decompiler)
    lines = ['object obj34 = (float2)(0.0f, 1.0f);',
             'UnityEngine.Gizmos.set_color(UnityEngine.Color.cyan);']
    assert dec._drop_dead_locals(lines) == lines[1:]

def _sub_lines(lines):
    dec = Decompiler.__new__(Decompiler)
    return dec._subexpr_cse(list(lines))


def test_subexpr_pow2_chain_folds():
    lines = ['int num2 = ((num1 > 16) ? num1 : 16) - 1;',
             'int num3 = num2 | ((num1 > 16) ? num1 : 16) - 1 >> 16;']
    assert _sub_lines(lines) == ['int num2 = ((num1 > 16) ? num1 : 16) - 1;',
                                 'int num3 = num2 | num2 >> 16;']


def test_subexpr_nested_or_chain_folds():
    lines = ['int num1 = ((requiredCapacity <= 16) ? 16 : requiredCapacity) - 1;',
             'int num2 = num1 | ((requiredCapacity <= 16) ? 16 : requiredCapacity) - 1 >> 16;',
             'int num3 = num2 | (num1 | ((requiredCapacity <= 16) ? 16 : requiredCapacity) - 1 >> 16) >> 8;']
    assert _sub_lines(lines)[2] == 'int num3 = num2 | num2 >> 8;'


def test_subexpr_declines_calls_and_new():
    lines = ['int num3 = num2 | Foo(num1) >> 16;',
             'object obj9 = new Vector3 { x = contact1.pointB.x };',
             'object obj10 = new Vector3 { x = contact1.pointB.x };']
    assert _sub_lines(lines) == lines


def test_subexpr_killed_by_store_label_and_loop():
    a = ['int num2 = ((num1 > 16) ? num1 : 16) - 1;',
         'num1 = x;',
         'int num3 = num2 | ((num1 > 16) ? num1 : 16) - 1 >> 16;']
    assert _sub_lines(a) == a
    b = ['int num2 = ((num1 > 16) ? num1 : 16) - 1;',
         'goto L_1;',
         'L_1:',
         'int num3 = num2 | ((num1 > 16) ? num1 : 16) - 1 >> 16;']
    assert _sub_lines(b) == b
    c = ['int num2 = ((num1 > 16) ? num1 : 16) - 1;',
         'while (c)',
         '{',
         'int num3 = num2 | ((num1 > 16) ? num1 : 16) - 1 >> 16;',
         '}']
    assert _sub_lines(c) == c


def test_subexpr_unstable_roots_decline_but_obj_roots_fold():
    # phi/bool/float bit-temps and stack homes are foreign namespaces.
    assert _sub_lines(['int num1 = v7.distance + 1;',
                       'int num2 = v7.distance + 2;']) == [
                       'int num1 = v7.distance + 1;',
                       'int num2 = v7.distance + 2;']
    # obj-rooted member fragment with an anchor decl folds later uses.
    assert _sub_lines(['object obj12 = contact1.distance;',
                       'int num1 = contact1.distance + 1;']) == [
                       'object obj12 = contact1.distance;',
                       'int num1 = obj12 + 1;']

VT11 = (0, 0x11 << 16)


def _home_lifter(static=False, params=(), rty=None):
    from types import SimpleNamespace as NS2
    il = NS2(
        _synthetic_inst=lambda base, args: (0x70000000, 0x15 << 16)
        if base == (0, 0x11 << 16) and tuple(args) == (VT11,) else None,
        _method_spec_type_args=lambda inst: [VT11] if inst == 7 else None,
        method_specs=[(0, 7, -1)],
        types=[(0, (0x11 << 16) | (1 << 29))],
        typedefs=[NS2(is_valuetype=True)],
        methods=[NS2(declaring=0, is_static=static)],
    )
    il.meta = NS2(methods=il.methods, typedefs=il.typedefs,
                  method_params=lambda m: [NS2(type=t) for t in params])
    lift = lifter(il=il)
    lift.meta = il.meta
    lift.slot_types, lift._type_hints = {}, {}
    return lift


def test_proved_struct_home_instance_receiver():
    lift = _home_lifter()
    assert lift._proved_struct_home(('generic', 0), ['&s_80', 'recv'], None) ==         ('s_80', (0x70000000, 0x15 << 16))


def test_proved_struct_home_static_needs_struct_return():
    lift = _home_lifter(static=True)
    assert lift._proved_struct_home(('generic', 0), ['&s_20'], VT11) ==         ('s_20', (0x70000000, 0x15 << 16))
    assert lift._proved_struct_home(('generic', 0), ['&s_20'], None) is None
    assert lift._proved_struct_home(('generic', 0), ['&s_20'], (0, 0x12 << 16)) is None


def test_proved_struct_home_declines_params_and_shapes():
    lift = _home_lifter(static=True)
    assert lift._proved_struct_home(('generic', 0), ['&s_20'], VT11) is not None
    lift2 = _home_lifter(static=True)
    lift2.il.meta.method_params = lambda m: [NS(type=0)]
    assert lift2._proved_struct_home(('generic', 0), ['&s_20'], VT11) is None
    assert lift._proved_struct_home(('method', 0), ['&s_20'], VT11) is None
    assert lift._proved_struct_home(('generic', 0), ['s_20'], VT11) is None
    assert lift._proved_struct_home(('generic', 99), ['&s_20'], VT11) is None

def _acc_lifter(static=False, valuetype=False, generic=False):
    lift = lifter()
    lift.meta = NS(
        typedefs=[NS(is_valuetype=valuetype,
                     generic_container=0 if generic else -1)],
        methods=[NS(declaring=0, is_static=static)],
    )
    return lift


def test_accessor_receiver_hint_types_slots():
    from il2cpp.expr import Expr as _E
    lift = _acc_lifter()
    m = lift.meta.methods[0]
    assert lift._hint_accessor_recv(_E('s_90', None, 'local'), m) ==         ('s_90', (0, 0x12 << 16))
    liftv = _acc_lifter(valuetype=True)
    mv = liftv.meta.methods[0]
    assert liftv._hint_accessor_recv(_E('&s_50', None, 'ptr'), mv) ==         ('s_50', (0, 0x11 << 16))
    assert liftv._hint_accessor_recv(_E('s_50', None, 'local'), mv) ==         ('s_50', (0, 0x11 << 16))


def test_accessor_receiver_hint_declines():
    from il2cpp.expr import Expr as _E
    lift = _acc_lifter()
    m = lift.meta.methods[0]
    assert lift._hint_accessor_recv(_E('s_90', None, 'ptr'), m) is None
    assert lift._hint_accessor_recv(_E('x.y', None, 'obj'), m) is None
    assert lift._hint_accessor_recv(_E('v7', None, '?'), m) is None
    assert lift._hint_accessor_recv(_E('s_90', None, 'local'),
                                    _acc_lifter(static=True).meta.methods[0]) is None
    liftg = _acc_lifter(generic=True)
    assert liftg._hint_accessor_recv(_E('s_90', None, 'local'),
                                     liftg.meta.methods[0]) is None
    assert lift._hint_accessor_recv(None, m) is None
    assert lift._hint_accessor_recv(_E('s_90', None, 'local'), None) is None

def _cp_lines(lines):
    dec = Decompiler.__new__(Decompiler)
    return dec._copy_prop(list(lines))


def test_copy_prop_declines_concrete_mismatch():
    lines = ['System.Collections.Generic.Dictionary_2<A, B>.Enumerator obj4 = obj3.GetEnumerator();',
             'UnityEngine.UI.Selectable obj6 = obj4;',
             'obj6.navigation = obj16;']
    assert _cp_lines(lines) == lines


def test_copy_prop_folds_same_and_object():
    assert _cp_lines(['System.TimeSpan obj14 = obj13;',
                      'use(obj14);']) == ['use(obj13);']
    assert _cp_lines(['object obj7 = obj4;',
                      'use(obj7, obj4);']) == ['use(obj4, obj4);']

def test_flush_pending_calls_with_tied_defpos():
    # 129 build fallbacks: two pending calls sharing one defpos idx
    # crashed `sorted` on Expr-vs-Expr compare. Ties keep insertion
    # order now (stable key sort), deterministically.
    from il2cpp.expr import Expr as _E
    lift = lifter()
    blk = NS(stmts=[])
    e1 = _E('Foo()', None, 'obj')
    e1._defpos = (blk, 0)
    e2 = _E('Bar()', None, 'obj')
    e2._defpos = (blk, 0)
    lift.out = []
    lift._pending_calls = [(e1, 1, None), (e2, 2, None)]
    lift._flush_pending_calls(None)
    assert blk.stmts == ['Foo();', 'Bar();']

def test_kill_one_preserves_method_identity():
    # 8 sweep failures: a killed methodinfo temp lost `_mi` (kind kept),
    # crashing the delegate path that indexes it. The temp freezes the
    # exact value, so identity proofs survive the move.
    from il2cpp.expr import Expr as _E
    lift = lifter()
    e = _E('SomeMethod', None, 'methodinfo')
    e._mi = 42
    e._usg_idx = 7
    t = lift._kill_one(e, 'SomeMethod', {})
    assert t.text != 'SomeMethod'
    assert t.kind == 'methodinfo'
    assert t._mi == 42
    assert t._usg_idx == 7

def test_wb_operands_numeric_dst_renders_deref():
    # A constant-folded null-base address is not a variable: `16 = v`
    # never parses. The deref spelling parses and matches the
    # plain-store twin so the duplicate still drops.
    lift = lifter()
    assert lift._wb_operands(['16', 'num3'], [None, None]) == \
        ('((byte*)16)[0]', 'num3')
    assert lift._wb_operands(['(16)', 'num3'], [None, None]) == \
        ('((byte*)16)[0]', 'num3')
    assert lift._wb_operands(['s_20', 'num3'], [None, None]) == \
        ('s_20', 'num3')

def test_subexpr_call_paren_survives_fold():
    # 77059: folding the argument of a generic call must keep the
    # call's own parens (`ToList<X>(obj)` never becomes `ToList<X>obj`).
    assert _sub_lines(['object obj9 = a.B;',
                       'object obj23 = System.Linq.Enumerable.ToList<X>(a.B);']) == [
                       'object obj9 = a.B;',
                       'object obj23 = System.Linq.Enumerable.ToList<X>(obj9);']
    assert _sub_lines(['object obj9 = a.B;',
                       'object obj23 = sub_1a2b/*shared body, 2 candidates*/(a.B);']) == [
                       'object obj9 = a.B;',
                       'object obj23 = sub_1a2b/*shared body, 2 candidates*/(obj9);']

def test_unsafify_cast_prefixed_const_deref():
    # `(uint*)*16` (folded null-base) is not a multiplication: the
    # paren group is cast-shaped, so the inner deref drops and the
    # honest address form parses. Operand parens never match.
    from il2cpp.dec.textpass import _TextPassMixin
    t = _TextPassMixin()
    assert t._unsafify('((uint*)*16 + 0x3c)[0] = batchLayerMask;') == \
        '((uint*)16 + 0x3c)[0] = batchLayerMask;'
    assert t._unsafify('y = (a + b)*16;') == 'y = (a + b)*16;'
    assert t._unsafify('x = (uint*)p + 4;') == 'x = (uint*)p + 4;'

def _bs_lines(lines):
    dec = Decompiler.__new__(Decompiler)
    return dec._bool_sugar(list(lines))


def test_bool_sugar_keeps_joined_ternary_pair():
    # 101899: `(A ? 1 : 0) & (B ? 1 : 0)` is not a flaggable paren wrap;
    # the lazy group used to span the join and drop parens asymmetrically.
    line = ('bool flag1 = (body == x ? 1 : 0) & '
            '(finally_ == y ? 1 : 0);')
    assert _bs_lines([line]) == [line]


def test_bool_sugar_still_folds_simple_wraps():
    assert _bs_lines(['bool flag1 = (a == b ? 1 : 0);']) == \
        ['bool flag1 = a == b;']
    assert _bs_lines(['flag1 = (a == b ? 1 : 0);']) == ['flag1 = a == b;']

def test_simplify_cond_keeps_partial_negation():
    # MinMaxAABB: `!(A) & (B)` is not a whole negation; simplifying it
    # drops the `!` and strands the `&` arm outside the head.
    from il2cpp import Decompiler
    assert Decompiler._simplify_cond('!(a) & (b)') == '!(a) & (b)'
    assert Decompiler._simplify_cond('!((a) & (b))') == '!((a) & (b))'
    assert Decompiler._simplify_cond('!(a == b)') == 'a != b'
    assert Decompiler._simplify_cond('!(a)') == '!(a)'

def test_fold_consts_keeps_call_arguments():
    # XmlNodeConverter: `s_28.ctor(0 + 1)` is a call, not grouping --
    # folding it deletes the argument list (`s_28.ctor1`).
    from il2cpp.dec.textpass import _TextPassMixin as _T
    assert _T._fold_consts('s_28.ctor(0 + 1);') == 's_28.ctor(0 + 1);'
    assert _T._fold_consts('x = (0 + 1);') == 'x = 1;'
    assert _T._fold_consts('foo((0 + 1));') == 'foo(1);'


def test_todonow_ambiguous_shared_keeps_marker():
    # TODONOW 1: receiver-blind `_call_name` must stay honest when one
    # native VA has several metadata owners; picking one invents identity.
    from types import SimpleNamespace as NS
    from il2cpp import Lifter
    lift = Lifter.__new__(Lifter)
    lift.il = NS(addr_candidates={0x1234: [('method', 0), ('method', 1)]},
                 addr_to_method={}, bin=NS(exports={}))
    lift.rt_names = {}
    lift.rt_init_meta = None
    lift._is_class_init_twin = lambda tgt: False
    lift._thunk_final = lambda tgt: tgt
    lift._info_name = lambda info: 'Should.Not.Resolve'
    assert lift._call_name(0x1234) == \
        'sub_1234/*shared body, 2 candidates*/'


def test_todonow_consensus_does_not_resolve_identity():
    # TODONOW 1 invariant: `shared_return_type` consensus types the call
    # result only; the rendered name stays shared. Consensus agreeing
    # must never become a method-identity proof.
    from types import SimpleNamespace as NS
    from il2cpp import Lifter
    lift = Lifter.__new__(Lifter)
    lift.il = NS(addr_candidates={0x1234: [('method', 0), ('method', 1)]},
                 addr_to_method={}, bin=NS(exports={}))
    lift.rt_names = {}
    lift.rt_init_meta = None
    lift._is_class_init_twin = lambda tgt: False
    lift._thunk_final = lambda tgt: tgt
    lift._info_name = lambda info: 'Should.Not.Resolve'
    assert 'shared body' in lift._call_name(0x1234)


def test_todonow_raw_mem_preserved_without_base():
    # TODONOW 4: an untracked base has no proven owner/layout, so the
    # load/store stays raw (`mem_xx` / `mem[N]`) instead of inventing a
    # field from displacement alone.
    lift = struct_lifter()
    lift.regs = {}
    execute(lift, '488b4110')  # mov rax,[rcx+0x10], RCX untracked
    assert lift.regs['RAX'].text == 'mem_10'
    from il2cpp import Expr
    lift2 = struct_lifter()
    lift2.regs = {}
    lift2.regs['RAX'] = Expr('v', (0, 0x08 << 16), 'int')
    execute(lift2, '48894110')  # mov [rcx+0x10],rax, RCX untracked
    assert lift2.out and lift2.out[0][1] == 'mem[16] = v;'


def test_todonow_unknown_never_becomes_default_or_zero():
    # TODONOW 3/5: `unknown` is the honesty marker for a missing native
    # value; text passes must never substitute zero/`default` for it.
    from il2cpp.dec.textpass import _TextPassMixin as _T
    t = _T()
    assert t._unsafify('x = unknown;') == 'x = unknown;'
    assert 'default' not in t._unsafify('x = unknown;')
    assert t._fold_consts('x = unknown;') == 'x = unknown;'


def test_rsp_copy_homes_share_one_slot():
    # mi 117615: `mov r11,rsp` parks the frame base; [r11+8] and later
    # [rsp+0x50] (after `sub rsp,0x48`) are one home, not mem[8]/mem_8.
    lift = struct_lifter()
    lift.regs = {}
    lift.rsp_delta = 0
    execute(lift, '4c8bdc')  # mov r11,rsp
    assert getattr(lift.regs.get('R11'), '_stack_offset', None) == 0
    from il2cpp import Expr
    lift.regs['RAX'] = Expr('v', (0, 0x08 << 16), 'int')
    execute(lift, '49894308')  # mov [r11+8],rax
    assert lift.out and lift.out[-1][1].startswith('s_') \
        and 'mem[' not in lift.out[-1][1]
    execute(lift, '498b4308')  # mov rax,[r11+8]
    assert lift.regs['RAX'].text == 'v'
    execute(lift, '4883ec48')  # sub rsp,0x48
    execute(lift, '488b442450')  # mov rax,[rsp+0x50]
    assert lift.regs['RAX'].text == 'v'


def test_rsp_copy_arithmetic_stays_raw():
    # `add r11,8` voids the frame offset: later traffic must not invent
    # a slot from the stale base.
    lift = struct_lifter()
    lift.regs = {}
    lift.rsp_delta = 0
    execute(lift, '4c8bdc')  # mov r11,rsp
    execute(lift, '4983c308')  # add r11,8
    from il2cpp import Expr
    lift.regs['RAX'] = Expr('v', (0, 0x08 << 16), 'int')
    execute(lift, '49894308')  # mov [r11+8],rax
    assert lift.out and 's_' not in lift.out[-1][1]


def test_rsp_copy_indexed_stays_raw():
    # [copy+index] is unproved address math: the unknown-base shape,
    # never a slot.
    lift = struct_lifter()
    lift.regs = {}
    lift.rsp_delta = 0
    execute(lift, '4c8bdc')  # mov r11,rsp
    execute(lift, '498b040b')  # mov rax,[r11+rcx]
    text = lift.regs['RAX'].text or ''
    assert 's_' not in text and '?' in text


def test_indexed_lea_through_anonymous_copy_stays_unknown():
    # Indexed LEA over a genuinely untracked base declines: the base
    # is unknown, so no home may be named.
    from il2cpp import Expr
    lift = struct_lifter()
    lift.regs = {}
    lift.rsp_delta = 0
    copy = Expr('?', None, 'ptr')
    copy._stack_offset = 0
    lift.regs['R11'] = copy
    execute(lift, '498d0c0b')  # lea rcx,[r11+rcx]
    text = lift.regs['RCX'].text or ''
    assert '?addr' in text


def test_rsp_copy_32bit_and_rbp_stay_legacy():
    # 32-bit `mov r11d,esp` truncates: no offset. `mov rbp,rsp` is the
    # pinned frame idiom: RBP stays unreadable so _rbp_is_frame() holds.
    lift = struct_lifter()
    lift.regs = {}
    lift.rsp_delta = 0
    execute(lift, '448bdc')  # mov r11d,esp
    assert getattr(lift.regs.get('R11'), '_stack_offset', None) is None
    lift2 = struct_lifter()
    lift2.regs = {}
    lift2.rsp_delta = 0
    execute(lift2, '4889e5')  # mov rbp,rsp
    assert lift2.regs.get('RBP') is None
    assert lift2._rbp_is_frame()


def _array_lifter(typedefs, ty_enum=(0x1d, 0x14)):
    from types import SimpleNamespace as NS
    from il2cpp import Lifter
    il = NS(
        types=[],
        _type_enum=lambda t: (t[1] >> 16) & 0xFF if t else 0,
        meta=NS(typedefs=typedefs),
    )
    arr = next((i for i, td in enumerate(typedefs)
                if td.namespace == 'System' and td.name == 'Array'), None)
    il._system_array_td = lambda arr=arr: arr
    lift = Lifter.__new__(Lifter)
    lift.il = il
    return lift


def _td(ns, name):
    from types import SimpleNamespace as NS
    return NS(namespace=ns, name=name)


def test_array_receiver_maps_to_system_array():
    lift = _array_lifter([_td('System', 'Object'), _td('System', 'Array')])
    assert lift._array_receiver_td((9, 0x1d << 16)) == 1
    assert lift._array_receiver_td((9, 0x14 << 16)) == 1


def test_array_receiver_declines_non_array_byref_and_missing():
    lift = _array_lifter([_td('System', 'Object'), _td('System', 'Array')])
    assert lift._array_receiver_td((0, 0x08 << 16)) is None
    assert lift._array_receiver_td((0, 0x12 << 16)) is None
    assert lift._array_receiver_td(None) is None
    assert lift._array_receiver_td((9, (0x1d << 16) | (1 << 29))) is None
    dup = _array_lifter([_td('System', 'Array'), _td('System', 'Array')])
    dup.il._system_array_td = lambda: None  # ambiguous row declines
    assert dup._array_receiver_td((9, 0x1d << 16)) is None
    from il2cpp import Lifter
    bare = Lifter.__new__(Lifter)
    from types import SimpleNamespace as NS
    bare.il = NS(_type_enum=lambda t: (t[1] >> 16) & 0xFF if t else 0)
    assert bare._array_receiver_td((9, 0x1d << 16)) is None


def _renamer():
    from types import SimpleNamespace as NS
    from il2cpp import Decompiler
    dec = Decompiler.__new__(Decompiler)
    dec.L = NS(slot_types={}, _var_types={}, _type_hints={})
    dec._var_types = {}
    return dec


def test_rename_locals_skips_body_identifiers():
    # mi 124140: s_8/v4 must not become obj1/obj2 when the body uses
    # those names (params here) -- the shadow decl fed _copy_prop a
    # bogus obj1 = obj2 and dropped an argument.
    dec = _renamer()
    out = dec._rename_locals(['s_8 = v4;',
                              'return F(obj1, obj2);'])
    assert out == ['object obj3 = obj4;',
                   'return F(obj1, obj2);']


def test_rename_locals_skips_unused_param_names():
    # Unused params never appear in the body, so only metadata saves
    # them from shadowing (CS0136): v9 skips obj1 via the method.
    from types import SimpleNamespace as NS
    dec = _renamer()
    dec.L.meta = NS(method_params=lambda m: [NS(name='obj1')])
    assert dec._rename_locals(['v9 = G();', 'return F(v9);'],
                              method=object()) == \
        ['object obj2 = G();', 'return F(obj2);']
    assert _renamer()._rename_locals(['v9 = G();', 'return F(v9);']) == \
        ['object obj1 = G();', 'return F(obj1);']


def test_rename_locals_keeps_param_spellings():
    # mi 113041: a body token matching a metadata parameter is the
    # parameter, never a rename target -- renaming v0 disconnected
    # every use (emitter keeps v0) and left objN unbound.
    from types import SimpleNamespace as NS
    dec = _renamer()
    dec.L.meta = NS(method_params=lambda m: [NS(name='v0'),
                                             NS(name='v1')])
    m = object()
    assert dec._rename_locals(['this.buf[num2] = v0;',
                               'this.buf[num4] = v1;',
                               't9 = v0;'], method=m) == \
        ['this.buf[num2] = v0;',
         'this.buf[num4] = v1;',
         'object obj1 = v0;']


def _iface_il(typedefs):
    from types import SimpleNamespace as NS
    from il2cpp import Il2Cpp
    il = Il2Cpp.__new__(Il2Cpp)
    il.meta = NS(typedefs=typedefs)
    return il


def _iface_td(namespace, name, start=0, count=0):
    from types import SimpleNamespace as NS
    return NS(namespace=namespace, name=name, method_start=start,
              method_count=count)


def test_interface_key_normalizes_arity_suffix():
    # Display spells IEnumerable_1<T> (fix 113/117) while metadata
    # names IEnumerable`1 -- mi 25368 stayed /*indirect*/ on the miss.
    il = _iface_il([_iface_td('System.Collections.Generic',
                              'IEnumerable`1', 100, 1)])
    assert il.interface_method_by_offset(
        'System.Collections.Generic.IEnumerable_1<Fusion.PlayerRef>',
        0) == 100
    assert il.interface_method_by_offset(
        'System.Collections.Generic.IEnumerable_1<Fusion.PlayerRef>',
        1) is None


def test_interface_key_keeps_genuine_underscore_names():
    # Exact key first: a real Foo_2 row still resolves, unknown stays None.
    il = _iface_il([_iface_td('Game', 'Foo_2', 50, 2)])
    assert il.interface_method_by_offset('Game.Foo_2', 0) == 50
    assert il.interface_method_by_offset('Game.Nope', 0) is None


def test_itf_slot_rx_matches_declared_and_bare():
    from il2cpp.cfg import _ITF_SLOT_RX
    m = _ITF_SLOT_RX.match('object obj19 = (x << 4) + 0x138 + y;')
    assert m and m.group(1) == 'obj19'
    m = _ITF_SLOT_RX.match('obj19 = (x << 4) + 0x138 + y;')
    assert m and m.group(1) == 'obj19'
    assert _ITF_SLOT_RX.match('object obj19 = x + y;') is None
