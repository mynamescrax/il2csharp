"""Negative witnesses for the stack home and Boolean forwarding proof."""
from types import SimpleNamespace as NS

from iced_x86 import Decoder
import pytest

from il2cpp.awaiter import _forwarded_bool, _home_and_suspend, _saved_awaiter, _yield_home, _yield_bool
from il2cpp.expr import Expr


def block(code):
    return NS(insns=list(Decoder(64, bytes.fromhex(code), ip=0x1000)))


@pytest.mark.parametrize('store,zero,addr,should_match', [
    ('4889442430', '33d2', '488d4c2430', True),
    ('89442430', '33d2', '488d4c2430', False),    # only half the return stored
    ('4889442430', '33d2', '488d4c2438', False),  # points into a different local
    ('4889442430', '33d2', '488d4c4430', False),  # indexed address
    ('4889442430', '33d2 89442434', '488d4c2430', False),  # partial overwrite
])
def test_receiver_is_address_of_the_whole_fresh_return(store, zero, addr, should_match):
    b = block('e800010000 ' + store + ' ' + zero + ' ' + addr + ' e800020000 84c0 7406')
    ip = b.insns[-3].ip
    got = _home_and_suspend(b, ip)
    assert got == ((0x30, b.insns[-1].near_branch_target) if should_match else None)
    # Another predecessor may bypass the store if the getter starts a new block.
    assert _home_and_suspend(NS(insns=b.insns[-3:]), ip) is None


@pytest.mark.parametrize('prefix,field,expected', [
    ('c7442428 00000000', (3, 0x11 << 16), True),
    ('c7442434 00000000', (3, 0x11 << 16), False),   # overlaps the saved word
    ('488bf3', (3, 0x11 << 16), False),              # receiver register changed
    ('', (4, 0x11 << 16), False),                    # another awaiter's field
])
def test_suspend_spill_requires_matching_declared_awaiter(prefix, field, expected):
    b = block(prefix + ' 488b442430 48894318')
    lift = NS(il=NS(types=[field], _type_enum=lambda t:t[1] >> 16 & 255,
                    instance_field_chain=lambda _: {0x28:('<>u__1', 0)}),
              regs={'RBX':Expr('this', (9, 0x12 << 16), 'obj')}, _current_td=NS(index=9,is_valuetype=True))
    assert _saved_awaiter(lift, b, 0x30, 3) == expected


@pytest.mark.parametrize('change', ['none', 'other field', 'wrong tail', 'wrong null path', 'wrong exception'])
def test_native_forwarder_reads_task_and_returns_its_bool(change):
    import struct

    addr, tail, fail = 0x1000, 0x3300, 0x4400
    displacement = lambda dest,ip: struct.pack('<i',dest-ip)
    code = (bytes.fromhex('4883ec28 488b09 4885c9 740b 33d2 4883c428 e9') + displacement(tail,addr+23)
            + b'\xe8' + displacement(fail,addr+28) + b'\xcc')
    if change == 'wrong null path':
        code = code[:11] + bytes([10]) + code[12:]
    ty = (1, 0x12 << 16)
    defs = [NS(index=i, property_start=i,property_count=1,method_start=i) for i in (0,1)]
    methods = [NS(declaring=i,addr=a,name='get_IsCompleted',is_static=False,param_count=0,
                  flags=0x886,generic_container=-1,return_type=1) for i,a in enumerate((addr,tail))]
    if change == 'wrong tail':
        methods[1].name = 'get_IsCanceled'
    il = NS(meta=NS(methods=methods, typedefs=defs, properties=[('IsCompleted',0,-1)]*2,getstr=lambda x:x),
            types=[ty,(0,2<<16)], _type_enum=lambda t:t[1] >> 16,
            addr_candidates={addr:[('method',0),('generic',10)],tail:[('method',1)]},
            bin=NS(is_exec_va=lambda _:True,read=lambda a,n:code), function_extent=lambda a:(a,a+len(code)),
            instance_field_chain=lambda _: {0x18 if change=='other field' else 0x10:('task',0)},
            value_type_size=lambda _:8, typedef_full=lambda _:'System.Threading.Tasks.Task')
    lift = NS(il=il,_call_name=lambda _: 'throw', _named_raise_throw=lambda a,n:
              'System.NullReferenceException' if a==fail and change!='wrong exception' else None)
    assert _forwarded_bool(lift,addr,0) == (il.types[1] if change == 'none' else None)


def builder_borrow(*, home='30', op='05', state_reg='c6', inst_awaiter=3, byref=True,
                   target_matches=True, conflict=False, barrier_ok=True, class_ok=True):
    # Nonvolatile RSI has a merged name. Distinct type, method and code
    # addresses force the proof to use the actual MethodRef registration.
    ins = block('c70601000000 488b442430 48894618 488d4e18 31d2 e800010000 '
                '488b0d00100000 83b9e400000000 75' + op + ' e800020000 '
                '4c8b0d00200000 4c8b' + state_reg + ' 488d5424' + home + ' 488d4e08 e800030000').insns
    slow = NS(bid=0, insns=ins[:9])
    blocks = [slow, NS(insns=ins[9:10]), NS(insns=ins[10:])]
    types = [(3,0x11<<16), (2,0x11<<16), (0,1<<16), (0,(0x1e<<16)|(int(byref)<<29)), (1,(0x1e<<16)|(1<<29))]
    method = NS(name='AwaitUnsafeOnCompleted',is_static=False,generic_container=1,param_count=2,return_type=2,declaring=2)
    meta = NS(version=31, methods=[method], generic_parameters=[(1,'A',0,0,0,0),(1,'S',0,0,1,0)],
              method_params=lambda _: [NS(type=3), NS(type=4)])
    target = ins[-1].near_branch_target
    uses = {ins[6].ip_rel_memory_address: {'kind':1,'type': types[1] if class_ok else types[0]},
            ins[10].ip_rel_memory_address: {'kind':6,'idx':0}}
    def type_key(t):
        return (1,0) if t==types[2] else (t[1]>>16 & 255,t[0],t[1]>>29 & 1)
    il = NS(meta=meta, types=types, _type_enum=lambda t:t[1]>>16 & 255, _closed_type_key=type_key,
            method_specs=[(0,-1,6)], decode_slot=uses.get, td_of_ty=lambda t:t[0],
            generic_method_table_list=[(0,4,0,0)] + ([(0,5,0,0)] if conflict else []),
            generic_method_pointers=0x9000, generic_method_pointers_count=10,
            bin=NS(is_exec_va=lambda addr:addr==target, qword=lambda addr: target if target_matches and addr==0x9020 else 0),
            typedef_full=lambda _: 'System.Runtime.CompilerServices.AsyncTaskMethodBuilder',
            _method_spec_type_args=lambda _: ((inst_awaiter,0x11<<16),(9,0x11<<16)),
            instance_field_chain=lambda _: {0x28:('<>u__1',0),0x18:('<>t__builder',1)})
    base = Expr('v12',(9,0x12<<16),'?')
    lift = NS(il=il,regs={'RSI':base},_blocks=blocks,_current_td=NS(index=9,is_valuetype=True),
              rt_wbarrier={ins[5].near_branch_target} if barrier_ok else set(),
              _call_name=lambda addr:'il2cpp_runtime_class_init' if addr==ins[9].near_branch_target else '')
    got = _saved_awaiter(lift, slow, 0x30, 3)
    assert lift.regs['RSI'] is base and base.text == 'v12'
    return got


def test_type_from_registered_builder_borrow():
    assert builder_borrow()


@pytest.mark.parametrize('changes', [dict(home='38'), dict(state_reg='c7'), dict(op='04'), dict(byref=False),
                                     dict(inst_awaiter=4), dict(target_matches=False), dict(conflict=True),
                                     dict(barrier_ok=False), dict(class_ok=False)])
def test_builder_witness_must_describe_this_exact_borrow(changes):
    assert not builder_borrow(**changes)


@pytest.mark.parametrize('change', ['none', 'dword store', 'other slot', 'extra predecessor', 'wrong klass', 'wrong guard'])
def test_byte_home_matches_the_guarded_yield_receiver(change):
    store = '89442430' if change == 'dword store' else '88442430'
    home = '38' if change == 'other slot' else '30'
    jne = '7504' if change == 'wrong guard' else '7505'
    ins = block('e810010000 ' + store + ' 488b0d00100000 83b9e400000000 ' + jne +
                ' e800020000 33d2 488d4c24' + home + ' e800030000 84c0 7405').insns
    before = NS(bid=0,insns=ins[:5]); cold = NS(bid=1,insns=ins[5:6],preds=[0]);
    check = NS(bid=2,insns=ins[6:],preds=[0,1,3] if change=='extra predecessor' else [0,1])
    klass = (0x11, 8 if change == 'wrong klass' else 2, 0)
    lift = NS(_blocks=[before,cold,check],_call_name=lambda _: 'il2cpp_runtime_class_init',
              il=NS(decode_slot=lambda _: {'kind':1,'type':klass}, _closed_type_key=lambda t:t))
    got = _yield_home(lift, check, ins[-3].ip, 2)
    assert got == ((0x30,ins[-1].near_branch_target) if change=='none' else None)


@pytest.mark.parametrize('load,store,expected', [('0fb6442430','884318',True), ('8b442430','884318',False),
                                                 ('0fb6442430','894318',False), ('0fb6442438','884318',False)])
def test_suspend_writes_only_the_proved_yield_byte(load, store, expected):
    b = block('c70301000000 ' + load + ' ' + store)
    lift = NS(il=NS(types=[(2,0x11<<16)], _type_enum=lambda t:t[1]>>16,
                    instance_field_chain=lambda _: {0x28:('<>u__2',0)}),
              regs={'RBX':Expr('this',(9,0x12<<16),'obj')},_current_td=NS(index=9,is_valuetype=True))
    assert _saved_awaiter(lift,b,0x30,2,width=1) == expected


@pytest.mark.parametrize('code,ret,expected', [('32c0c3',2,True), ('b001c3',2,False),
                                               ('32c0cc',2,False), ('32c0c3',8,False)])
def test_zero_al_is_not_a_general_shared_call_proof(code,ret,expected):
    addr = 0x1234
    md = NS(name='get_IsCompleted',declaring=0,addr=addr,is_static=False,flags=0x886,param_count=0,
            generic_container=-1,return_type=0)
    td = NS(method_start=0,property_start=0,property_count=1)
    il = NS(meta=NS(methods=[md],typedefs=[td],properties=[('IsCompleted',0,-1)],getstr=lambda x:x),
            addr_candidates={addr:[('generic',2),('method',0)]},value_type_size=lambda _:1,
            types=[(0,ret<<16)],_type_enum=lambda t:t[1]>>16,
            bin=NS(read=lambda a,n:bytes.fromhex(code),is_exec_va=lambda _:True))
    assert bool(_yield_bool(NS(il=il), addr, 0)) == expected


@pytest.mark.parametrize('change', ['none', 'unknown base', 'overlap', 'wrong field', 'changed receiver'])
def test_resumed_byte_is_the_saved_awaiter(change):
    from il2cpp.awaiter import _resume_byte
    reset = 'c703ffffffff' if change != 'changed receiver' else 'c707ffffffff'
    temp = 'c7442430ffffffff' if change == 'overlap' else 'c7442420ffffffff'
    seq = block('0fb64328 88442430 31c0 884328 ' + temp + ' ' + reset).insns
    ft = (5 if change == 'wrong field' else 8,0x11<<16)
    il = NS(instance_field_chain=lambda _: {0x38:('<>u__2',0)}, types=[ft],
            _closed_type_key=lambda t:(t[1]>>16,t[0],0), _type_enum=lambda t:t[1]>>16&255)
    state = Expr('v1' if change == 'unknown base' else 'this',(3,0x12<<16),'obj')
    lift = NS(il=il,_current_td=NS(index=3,is_valuetype=True))
    assert _resume_byte(lift,seq,{'RBX':state},0x30,8) == (change == 'none')


@pytest.mark.parametrize('code,ok', [('c20000', True), ('c20400', False), ('31c0c3', False)])
def test_getresult_requires_a_void_noop(code,ok):
    from il2cpp.awaiter import _yield_result_member
    target = 0x2345
    md = NS(addr=target,declaring=0,name='GetResult',is_static=False,param_count=0,flags=6,
            generic_container=-1,return_type=0)
    il = NS(bin=NS(is_exec_va=lambda _:True,read=lambda *_:bytes.fromhex(code)),
            types=[(0,1<<16)],_closed_type_key=lambda t:(t[1]>>16,0),meta=NS(methods=[md]),
            addr_candidates={target:[('method',0),('generic',2)]})
    assert bool(_yield_result_member(il,target,0)) == ok


@pytest.mark.parametrize('code,ok', [('c3', True), ('89c2c3', False), ('740289c2c3', False),
                                     ('f30f11442430c3', False), ('b00189c2c3', False), ('31c089c2c3', True)])
def test_getresult_cannot_discard_a_used_return(code,ok):
    from il2cpp.awaiter import _unused_return
    assert _unused_return(NS(_blocks=[block(code)]),0x1000) == ok


def dispatch_liveness(change=None):
    from il2cpp.awaiter import _unused_return

    # A type slot, a static object field at +0x18, and a VirtualInvokeData
    # pair for slot 2. Consume the *new* RAX after the virtual call.
    ptr, method = ('58', '60') if change != 'wrong methodinfo' else ('58','70')
    arm = bytes.fromhex('488b11 488b82' + ptr + '010000 488b92' + method + '010000 ffd0 488bc8 c3')
    tail = 'f30f11442420 c3' if change == 'null reads xmm0' else 'c3'
    code = '488b0500100000 488b88b8000000 488b4918 4885c9 74' + bytes([len(arm)]).hex() + arm.hex() + tail
    if change == 'partial overwrite':
        code = code.replace('488b05', '668b05', 1)
    if change == 'side entry':
        code = '7517 ' + code  # jump directly to the dispatch with no proved receiver
    b = block(code)
    klass, ft, rt = (0, 0x12 << 16), (1, (0x12 << 16) | 0x10), (2, 0x12 << 16)
    defs = [NS(generic_container=-1, flags=1, is_valuetype=False,field_count=2),
            NS(generic_container=-1, is_valuetype=False,vtable_start=0,vtable_count=3)]
    m = NS(slot=2,is_static=change=='static',flags=0x40,param_count=int(change=='has argument'),
           generic_container=-1,declaring=1,return_type=2)
    meta = NS(version=31, typedefs=defs, vtable_methods=[1]*3,fields=[NS(type=1), NS(type=1)],
              type_fields=lambda td:[0,1],methods=[m])
    il = NS(meta=meta, types=[klass,ft,rt],field_offsets=[[0x18,0x14 if change=='overlap' else 0x20]],
            decode_slot=lambda p: {'kind':1,'td':0,'type':klass} if change!='unknown type' else None,
            _sf_field_size=lambda t,d:8, _type_enum=lambda t:t[1]>>16&255,
            _closed_type_key=lambda t:(0x12,t[0],0),vtable_method=lambda td,s:0 if s==2 and td==1 else None,
            base_chain_tds=lambda td:(td,),_return_abi_is_known=lambda _:True,returns_sret=lambda _:change=='sret')
    return _unused_return(NS(il=il,_blocks=[b]),0x1000)


def test_old_returns_dead_before_checked_instance_dispatch():
    assert dispatch_liveness()


@pytest.mark.parametrize('change', ['wrong methodinfo','null reads xmm0','partial overwrite','side entry',
                                    'static','has argument','overlap','unknown type','sret'])
def test_unchecked_indirect_call_is_not_a_liveness_boundary(change):
    assert not dispatch_liveness(change)


def alloc_liveness(monkeypatch, *, change=None, use=''):
    from struct import pack
    from il2cpp import awaiter
    from il2cpp.binary import PE

    start, alloc, core, export = 0x1000, 0x2000, 0x3000, 0x4000
    before = bytes.fromhex(use + ' 488b0d00100000')
    code = before + b'\xe8' + pack('<i', alloc - (start+len(before)+5)) + bytes.fromhex('488bc8 c3')
    insts = list(Decoder(64, code, ip=start))
    data = {alloc:b'\xe9' + pack('<i', core - (alloc+5)),
            export:bytes.fromhex('4883ec28 e8') + pack('<i', core + (change=='different core') - (export+9)) +
                   bytes.fromhex('eb02 33c0 4883c428 c3')}
    if change == 'transforms arguments':
        data[export] = bytes.fromhex('4883c101') + data[export][4:]  # add rcx,1
    if change == 'not a forwarder':
        data[alloc] = b'\xe8' + data[alloc][1:]
    image = PE.__new__(PE)
    image.exports = {export: 'OtherExport' if change=='name only' else 'il2cpp_object_new'}
    image.read = lambda p,n: data.get(p,b'')[:n]
    image.is_exec_va = lambda p:p in (alloc,export,core)
    il = NS(bin=image,addr_candidates={})
    lift = NS(il=il,rt_alloc=alloc,_blocks=[NS(insns=insts)],_call_name=lambda _: 'il2cpp_object_new')
    monkeypatch.setattr(awaiter, 'entry_live_args', lambda *_: ('gx',)*4)
    return awaiter._unused_return(lift,start)


def test_allocator_with_exported_core_defines_a_new_result(monkeypatch):
    assert alloc_liveness(monkeypatch)


@pytest.mark.parametrize('change', ['different core','transforms arguments','not a forwarder','name only'])
def test_allocator_label_does_not_prove_the_wrapper_abi(monkeypatch, change):
    assert not alloc_liveness(monkeypatch,change=change)


@pytest.mark.parametrize('use',['488bd0','f30f11442420'])
def test_prior_read_of_return_lane_is_not_hidden_by_allocation(monkeypatch,use):
    assert not alloc_liveness(monkeypatch,use=use)


@pytest.mark.parametrize('change', [None,'callee reads xmm','caller reads xmm later','indirect call',
                                    'jump outside','untested error helper','old rax still live'])
def test_integer_shared_call_follows_live_xmm_back_to_caller(monkeypatch,change):
    from struct import pack
    from il2cpp import awaiter
    from il2cpp.binary import PE

    start, target, error = 0x1000, 0x3000, 0x5000
    # Both arms are checked. On the cold arm the registered nullary throw
    # helper cannot take an FP argument. On success the caller reads the
    # new RAX; the shared callee hasn't overwritten the old XMM0.
    cold = b'\xe8' + pack('<i',error-(target+4+5))
    if change=='indirect call': cold=b'\xff\xd0'
    elif change=='jump outside': cold=b'\xeb\x60'
    elif change=='callee reads xmm': cold=bytes.fromhex('f30f11442410')
    body = bytes.fromhex('85d2 74') + bytes([len(cold)]) + cold + bytes.fromhex('488b01 c3')
    head = b'' if change=='old rax still live' else bytes.fromhex('488b4160')
    use = bytes.fromhex('f30f11442410') if change=='caller reads xmm later' else b''
    code = head + b'\xe8' + pack('<i', target - (start+len(head)+5)) + bytes.fromhex('488bd0') + use + b'\xc3'
    image = PE.__new__(PE); image.is_exec_va=lambda p:p in (target,error); image.read=lambda p,n:body[:n] if p==target else None
    m = NS(name='ThrowIndex',addr=error,declaring=0,is_static=True,param_count=int(change=='untested error helper'),generic_container=-1,return_type=0)
    il = NS(bin=image,meta=NS(methods=[m]),types=[(0,1<<16)],_closed_type_key=lambda t:(1,0),
            addr_candidates={target:[('generic',7),('generic',8)],error:[('method',0)]},typedef_full=lambda _: 'System.ThrowHelper',
            function_extent=lambda p:(target,target+len(body)))
    lift=NS(il=il,_blocks=[NS(insns=list(Decoder(64,code,ip=start)))],_named_raise_throw=lambda *_:None,_call_name=lambda _: 'unresolved')
    monkeypatch.setattr(awaiter,'entry_live_args',lambda *_: ('gx',)*4)
    assert awaiter._unused_return(lift,start) == (change is None)
