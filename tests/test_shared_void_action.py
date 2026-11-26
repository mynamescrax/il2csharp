"""A ret-only collision still needs a real receiver, signature and unused result."""
from types import SimpleNamespace as NS

from iced_x86 import Decoder, Mnemonic
import pytest

from il2cpp.binary import PE
from il2cpp.expr import Expr
from il2cpp.shared_action import _bool_transfer, _cleanup_tail_forward, _entry_forward, _guarded_helper_forward, _guarded_this_forward, _guarded_ref_bool_forward, shared_action_tail, shared_base_action, shared_bool_tail, shared_void_action
from iced_x86 import Register as R


def recover(change=None):
    # Load the receiver before producing the first argument. Null is checked
    # AFTER that producer, exactly as in a managed instance call expression.
    setup = '4533c9 41b001 488bd0 488bcb e800100000'
    if change == 'wrong getter result':
        setup = setup.replace('488bd0', '488bd7')
    if change == 'not a bool':
        setup = setup.replace('41b001', '41b002')
    use = {'RAX used': '488bc8', 'XMM0 used': 'f30f11442430'}.get(change, '')
    next_code = bytes.fromhex(setup + use + 'c3')
    raw = bytes.fromhex('488b5f40 33d2 488bcf e800200000 4885db 74') + bytes([len(next_code)]) + next_code + bytes.fromhex('e800300000 cc')
    ins = list(Decoder(64, raw, ip=0x1100)); getter, call = ins[3], ins[10]
    blocks = [NS(insns=ins[:6]), NS(insns=ins[6:-2], preds=[0,2] if change=='other edge' else [0]), NS(insns=ins[-2:])]
    image = PE.__new__(PE); image.is_exec_va = lambda p: p == call.near_branch_target
    image.read = lambda p,n: b'\x31\xc0\xc3' if change=='nonempty body' else b'\xc2\x00\x00'
    types = [(0,1<<16),(12,0x12<<16),(0,(8 if change=='int parameter' else 2)<<16),(11,0x12<<16)]
    def method(idx, name, td, params, result, addr):
        return NS(index=idx, name=name, declaring=td, param_count=len(params), params=[NS(type=p) for p in params],
                  return_type=result, is_static=False, addr=addr, flags=6, generic_container=-1)
    methods = [method(0,'Start',11,[1,2],0,call.near_branch_target), method(1,'Pause',11,[],0,call.near_branch_target),
               method(2,'get_Object',10,[],1,getter.near_branch_target), method(3,'Update',10,[],0,0x1100)]
    if change=='ambiguous': methods[1].params=methods[0].params; methods[1].param_count=2
    if change=='returns value': methods[0].return_type=1
    meta = NS(methods=methods, method_params=lambda m:m.params,
              typedefs=[NS(is_valuetype=False, generic_container=-1, parent=-1)] * 13)
    il = NS(bin=image, types=types, meta=meta, base_chain_tds=lambda t:(t,), _closed_type_key=lambda t:
            (0x12,t[0],0) if t[1]>>16==0x12 else (t[1]>>16,0), instance_field_chain=lambda t:{0x40:('rec',3)},
            addr_candidates={getter.near_branch_target:[('method',2)],call.near_branch_target:[('method',0),('method',1)]})
    lift = NS(il=il, out=NS(block=blocks[1]), _blocks=blocks, regs={'RDI': Expr('this',(10,0x12<<16),'obj')},
              _current_method=methods[3], _call_name=lambda t:'raise', _named_raise_throw=lambda *_:
              None if change=='null skips call' else 'System.NullReferenceException')
    regs = [Expr('this.rec',types[3],'obj'),Expr('this.Object',types[1],'obj'),Expr('1'),Expr('0')]
    return shared_void_action(lift,call,regs,[Expr('Evaluate()')] if change=='extra evaluation' else [])


def test_typed_operands_of_noop_select_instance_action():
    assert recover() == ('method',0)


@pytest.mark.parametrize('change',['wrong getter result','not a bool','RAX used','XMM0 used','other edge',
                                    'nonempty body','int parameter','ambiguous','returns value','null skips call',
                                    'extra evaluation'])
def test_unproven_action_is_not_named(change):
    assert recover(change) is None


@pytest.mark.parametrize('change', [None, 'reused receiver', 'other edge', 'wrong conversion argument',
                                    'wrong result byte', 'changed receiver', 'wrong null path', 'live bool clobber'])
def test_bool_tail_requires_original_receiver_and_converted_argument(change):
    raw = bytes.fromhex
    # Four native blocks, not a linear pattern that can ignore a jump into
    # an epilogue. Use different homes/register spills from the game site.
    keep = '488bd8' if change=='reused receiver' else '488bf0'
    field = raw('488b5f40 33d2 488bcf e800100000 488b0d00100000 ' + keep + ' 83b9e400000000 7505')
    init = raw('e810000000')
    arg = '488bcb' if change=='wrong conversion argument' else '488bce'
    conv = raw('33d2 ' + arg + ' e800200000 4885db')
    ext = '0fb6d4' if change=='wrong result byte' else '0fb6d0'
    this = '488bce' if change=='changed receiver' else '488bcb'
    restore = '488b542438' if change=='live bool clobber' else '488b742438'
    tail = raw('4533c0 ' + ext + ' ' + this + ' ' + restore + ' 4883c420 5f e900100000')
    conv += bytes([0x74,len(tail)])
    blocks=[]; ip=0x2000
    for piece, preds in [(field,[]),(init,[0]),(conv,[0,1,4] if change=='other edge' else [0,1]),
                         (tail,[2]),(raw('e800300000 cc'),[2])]:
        blocks.append(NS(bid=len(blocks),insns=list(Decoder(64,piece,ip=ip)),preds=preds,end_state={}))
        ip+=len(piece)
    lift=NS(_blocks=blocks,_call_name=lambda t:'il2cpp_runtime_class_init',
            _named_raise_throw=lambda *_: None if change=='wrong null path' else 'System.NullReferenceException')
    site=_bool_transfer(lift,blocks[3],blocks[3].insns[-1])
    assert (site is not None) == (change is None)


def literal_tail(change=None, boolean=1):
    # Use a different receiver register, field offset, spill and jump target
    # from the game. Only DL is defined; that does not prove an int argument.
    dl = 'b6' if change == 'high byte' else 'b2'
    restore = {'argument clobber':'488b542430', 'receiver clobber':'488b4c2430',
               'work in epilogue':'e800200000'}.get(change, '0f28742430')
    finish = bytes.fromhex('4531c0 ' + dl + f'{boolean:02x} ' + restore + ' 4883c440 5e e900100000')
    src = bytes.fromhex('488b4e50 4885c9 74') + bytes([len(finish)])
    ins = list(Decoder(64,src + finish + bytes.fromhex('e800300000 cc'),ip=0x2000)); jump=ins[-3]
    first=NS(insns=ins[:3], end_state={'RSI':Expr('other' if change=='other instance' else 'this',(3,0x12<<16),'obj')})
    last=NS(bid=1,insns=ins[3:-2],preds=[0,2] if change=='alternate entry' else [0])
    types=[(0,1<<16),(0,(8 if change=='int signature' else 2)<<16),(1,0x12<<16)]
    method=NS(index=0,declaring=1,name='Done',addr=jump.near_branch_target,flags=6,is_static=False,
              generic_container=-1,param_count=1,return_type=0)
    meta=NS(methods=[method,NS(declaring=2)],typedefs=[NS(is_valuetype=False,generic_container=-1,parent=-1)]*4,
            method_params=lambda _:[NS(type=1)])
    image=PE.__new__(PE); image.is_exec_va=lambda _:True; image.read=lambda *_:bytes.fromhex('c20000')
    il=NS(bin=image,meta=meta,types=types,_closed_type_key=lambda t:(0x12,t[0],0) if t and t[1]>>16==0x12 else (t[1]>>16,0),
          addr_candidates={jump.near_branch_target:[('method',0),('method',0 if change=='ambiguous' else 1)]},
          base_chain_tds=lambda n:(n,),instance_field_chain=lambda _:{0x50:('meter',2)})
    lift=NS(il=il,_current_method=NS(is_static=False,declaring=3,return_type=0),out=NS(block=last),
            _blocks=[first,last,NS(insns=ins[-2:])],_call_name=lambda _:'raise',
            _named_raise_throw=lambda *_:None if change=='null skips' else 'System.NullReferenceException')
    regs=[Expr('this.meter',types[2],'obj'),Expr(str(boolean),None,'int'),Expr('0',None,'int')]
    return shared_bool_tail(lift,jump,[e.text for e in regs],regs)


@pytest.mark.parametrize('flag,expected', [(0,'false'),(1,'true')])
def test_literal_bool_tail(flag,expected):
    assert literal_tail(boolean=flag) == f'this.meter.Done({expected}) /* shared implementation */'


@pytest.mark.parametrize('change', ['high byte','argument clobber','receiver clobber','work in epilogue',
                                    'other instance','alternate entry','int signature','ambiguous','null skips'])
def test_unknown_literal_tail_is_not_named(change):
    assert literal_tail(change) is None


def base_forward(change=None, *, nullary=False, tail_jump=False):
    from il2cpp import Lifter

    clear = '31d2' if nullary and change != 'wrong MethodInfo slot' else '4531c9'
    code = f'56 4883ec20 {clear} 488bf1 '
    if change == 'write to flag':
        code += '41b001 '
    code += 'e800100000 '
    if change == 'return consumed':
        code += '488bd0 '
    if change == 'FP return consumed':
        code += 'f30f11442430 '
    code += '33d2 488bce 4883c420 5e e900200000'
    if tail_jump:
        code = ('56 ' if change == 'frame' else '') + clear + ' e900100000'
    seq = list(Decoder(64, bytes.fromhex(code), ip=0x3000))
    call = seq[-1] if tail_jump else next(i for i in seq if i.mnemonic == Mnemonic.CALL)
    target, tail = call.near_branch_target, seq[-1].near_branch_target
    vf, cls = 0xc6, 0x12 << 16
    types = [(0, 1 << 16), (2, cls), (0, 2 << 16), (1, cls)]
    params = [] if nullary else [NS(name='peer', type=1), NS(name='ready', type=2)]
    def method(idx, name, ti, flags, addr, ps):
        return NS(index=idx, name=name, declaring=ti, flags=flags, addr=addr, is_static=False,
                  param_count=len(ps), params=ps, generic_container=-1, slot=5, return_type=0)
    current = method(0,'Removed',0,vf,seq[0].ip,params)
    base = method(1,'Removed',1,vf|0x100,target,params)
    follow = method(2,'Cleanup',0,6,tail,params if change=='unknown tail ABI' else [])
    other = method(3,'Another',1,vf|0x100,target,params if change=='ambiguous' else [])
    if change=='other signature': base.params=[params[0],params[0]]
    if change=='other slot': base.slot=6
    if change=='newslot': current.flags|=0x100
    if change=='private base': base.flags=(base.flags & ~7)|1
    defs = [NS(index=i, is_valuetype=False, generic_container=-1, flags=1, parent=3 if i==0 else -1) for i in range(3)]
    meta = NS(typedefs=defs,methods=[current,base,follow,other],method_params=lambda m:m.params,type_methods=lambda _:[1,3])
    image = PE.__new__(PE); image.is_exec_va=lambda a:a==target
    image.read=lambda *_:bytes.fromhex('31c0c3' if change=='not a bare return' else 'c20000')
    targets = {target:[('method',1),('method',3)], current.addr:[('method',0),('method',3)]}
    if not tail_jump:
        targets[tail] = [('method',2)]
    if change=='different caller row': targets[current.addr] = [('method',3)]
    lift = Lifter.__new__(Lifter)
    lift.il = NS(bin=image,types=types,meta=meta,base_chain_tds=lambda t:(0,1) if t==0 else (t,),
                 addr_candidates=targets,
                 _type_enum=lambda t:t[1]>>16, _closed_type_key=lambda t:(0x12,t[0],0) if t and t[1]>>16==0x12 else (t[1]>>16,0),
                 vtable_method=lambda t,s:t if s==5 and t in (0,1) else None)
    lift.meta, lift._current_method, lift._current_td = meta, current, defs[0]
    blk = NS(is_entry=True, preds=[1] if change=='alternate entry' else [], insns=seq)
    lift.out=NS(block=blk);lift._blocks=[blk]
    regs = [Expr('other' if change=='other receiver' else 'this',(0,cls),'obj'), Expr('peer',types[1],'obj'),
            Expr('ready',types[2],'int'),Expr('0',None,'int')]
    if nullary:
        regs[1:] = [Expr('0',None,'int'), None, None]
        if change == 'base not registered':
            lift.il.addr_candidates[target] = [('method',3),('method',2)]
    if tail_jump:
        lift.regs = dict(zip(['RCX','RDX','R8','R9'], regs))
        return shared_action_tail(lift, call, seq, [e.text for e in regs[:2]], regs[:2])
    return shared_base_action(lift,call,regs,[])


def test_override_forwards_to_folded_base_slot_before_cleanup():
    assert base_forward() == 'base.Removed(peer, ready) /* shared implementation */'


@pytest.mark.parametrize('change',['write to flag','return consumed','unknown tail ABI','ambiguous','other signature',
                                   'other slot','newslot','private base','other receiver','alternate entry'])
def test_inconclusive_base_call_declines(change):
    assert base_forward(change) is None


def test_nullary_noop_alias_names_the_base_slot_not_an_arbitrary_sibling():
    # Both base.Removed and base.Another are registered at the same address.
    assert base_forward(nullary=True) == 'base.Removed() /* shared implementation */'


@pytest.mark.parametrize('change',['return consumed','FP return consumed','other receiver','other slot','newslot',
                                   'wrong MethodInfo slot','not a bare return','base not registered'])
def test_nullary_alias_requires_unused_result_and_matching_base(change):
    assert base_forward(change,nullary=True) is None


def test_nullary_base_tail_uses_superclass_slot():
    assert base_forward(nullary=True,tail_jump=True) == 'base.Removed() /* shared implementation */'


@pytest.mark.parametrize('change',['frame','different caller row','wrong MethodInfo slot','other receiver',
                                   'alternate entry','other slot','newslot','not a bare return','base not registered'])
def test_nullary_base_tail_requires_entry_receiver_and_verified_forwarder(change):
    assert base_forward(change,nullary=True,tail_jump=True) is None


def guarded_helper(change=None, spill='', null_guard=False):
    # Model both edges, including the instructions the structurer omits from
    # the printed metadata-init guard. A call can clobber RCX and RDX.
    va, flag = 0x4000, 0x6000
    def rel(ip, target): return (target - ip).to_bytes(4,'little',signed=True)
    head = bytes.fromhex('48895c2408 57 4883ec30 803d') + rel(va+17,flag) + b'\0'
    head += bytes.fromhex('488bda 488bf9')  # park helper and this
    cold_va = va + len(head) + 2
    cold = bytes.fromhex('488d0d00080000 e8') + rel(cold_va+12,0x7100 if change=='other call' else 0x7000)
    cold += bytes.fromhex('c605') + rel(cold_va+19,flag+int(change=='other flag')) + b'\1'
    head += bytes([0x75, len(cold)])
    move_helper = '488bd7' if change=='wrong source' else '488bd3'
    join = bytes.fromhex('4531c0 ' + spill + move_helper + ' 488bcf e800200000')
    if change=='clobber before branch': head=head.replace(bytes.fromhex('488bda'), bytes.fromhex('488bf2'))
    blocks = []
    incoming = [0,1,3] if change=='other edge' else [0,1]
    arms = [(head,[]),(cold,[0])]
    if null_guard:
        test = '4885ff' if change=='test this' else '4885db'
        branch = '75' if change=='non-null skips' else '74'
        arms.append((bytes.fromhex(test + branch) + bytes([len(join) - int(change=='short skip')]), incoming))
        incoming = [2, 4] if change=='bypass helper check' else [2]
    for raw, preds in arms + [(join,incoming)]:
        ins = list(Decoder(64,raw,ip=va));bid=len(blocks)
        blocks.append(NS(bid=bid,is_entry=not bid,preds=preds,insns=ins));va+=len(raw)
    if null_guard:
        blocks[2].succs, blocks[3].succs = [4,3], [4]
    pad = blocks[2].insns[0].ip
    il = NS(eh_regions=lambda _: {'pads':[pad]} if change=='handler entry' else None)
    lift = NS(il=il,_blocks=blocks,rt_init_meta=0x7000,_current_method=NS(addr=0x4000))
    return _guarded_helper_forward(lift,blocks[-1],blocks[-1].insns[-1])


def test_helper_is_saved_on_both_guard_paths():
    assert guarded_helper()


@pytest.mark.parametrize('setup,ok',[
    ('48895c2408 57 4883ec20',True),             # entry RSP+8: caller-reserved home
    ('48895c2410 4c89642418 57 4883ec20',True), # two disjoint qwords
    ('48891c24 57 4883ec20',False),              # return address
    ('48895c2428 57 4883ec20',False),            # outside home space
    ('48895c240c 57 4883ec20',False),            # unaligned, overlaps two homes
    ('48895c2408 4889742408 57 4883ec20',False), # reused slot
    ('57 4883ec20 48895c2408',False),            # displacement now relative to moved RSP
    ('48894c2408 57 4883ec20',False),            # input argument, not a nonvolatile save
    ('895c2408 57 4883ec20',False),              # partial register
    ('488b4c2408 57 4883ec20',False),            # RCX reload, not a save
])
def test_nullary_forwarder_requires_leading_whole_nonvolatile_homes(setup,ok):
    seq=list(Decoder(64,bytes.fromhex(setup+' 33d2 488bf9 e800100000'),ip=0x4000))
    assert _entry_forward(seq,seq[0].ip,seq[-1],(R.RCX,),R.EDX)==ok


@pytest.mark.parametrize('case',['hot and cold','linearized guard','wrong reload','different initializer','wrong flag','extra predecessor','EH pad'])
def test_nullary_guard_must_reach_call_with_entry_this(case):
    # Save RDI before the flag test's branch. On a cold first use the
    # initializer consumes RCX; only restoring RDI recovers this.
    start=0x1000; flag=0x1234; init=0x5100
    def rel(n): return n.to_bytes(4,'little',signed=True)
    head=bytes.fromhex('57 4883ec20 803d')+rel(flag-(start+12))+bytes.fromhex('00 488bf9 7513')
    p=start+len(head)
    cold=bytes.fromhex('488d0d00010000 e8')+rel(init+int(case=='different initializer')-(p+12))
    cold+=bytes.fromhex('c605')+rel(flag+int(case=='wrong flag')-(p+19))+b'\x01'
    join=bytes.fromhex('31d2 '+('488bcb' if case=='wrong reload' else '488bcf')+' e800200000')
    incoming=[1] if case=='linearized guard' else [0,1]
    blocks=[]; ip=start
    for n,(data,preds,succs) in enumerate([(head,[],[1] if case=='linearized guard' else [2,1]),(cold,[0],[2]),
                                           (join,incoming+([3] if case=='extra predecessor' else []),[])]):
        blocks.append(NS(bid=n,is_entry=n==0,insns=list(Decoder(64,data,ip=ip)),preds=preds,succs=succs));ip+=len(data)
    il=NS(eh_regions=lambda _:{'pads':[p]} if case=='EH pad' else None)
    lift=NS(il=il,_blocks=blocks,_current_method=NS(addr=start),rt_init_meta=init)
    assert _guarded_this_forward(lift,blocks[2],blocks[2].insns[-1])==(case in ('hot and cold','linearized guard'))


@pytest.mark.parametrize('case',['hot and cold','linearized','swapped refs','wrong bool lane','constant flag','wrong context','other edge'])
def test_guarded_reference_and_bool_must_come_from_the_original_arguments(case):
    start=0x2000; flag=0x3200; init=0x4000
    def rel(n): return n.to_bytes(4,'little',signed=True)
    # Use RBP for the bool to avoid tying its proof to the game register DIL.
    head=bytes.fromhex('48895c2408 4889742410 55 4883ec20 803d')
    head+=rel(flag-(start+len(head)+5))+b'\0'
    head+=bytes.fromhex('410fb6e8 488bf2 488bd9 7513');p=start+len(head)
    cold=bytes.fromhex('488d0d00010000 e8')+rel(init-(p+12))+bytes.fromhex('c605')+rel(flag-(p+19))+b'\1'
    join=bytes.fromhex('4531c9 440fb6c5 488bd6 488bcb e800040000')
    if case=='swapped refs':join=join.replace(bytes.fromhex('488bd6 488bcb'),bytes.fromhex('488bd3 488bce'))
    if case=='wrong bool lane':join=join.replace(bytes.fromhex('440fb6c5'),bytes.fromhex('440fb6c7'))
    if case=='constant flag':join=join.replace(bytes.fromhex('440fb6c5'),bytes.fromhex('41b801000000'))
    if case=='wrong context':join=join.replace(bytes.fromhex('4531c9'),bytes.fromhex('4531d2'))
    incoming=[1] if case=='linearized' else [0,1];bs=[];ip=start
    for n,(raw,preds,succs) in enumerate([(head,[],[1] if case=='linearized' else [2,1]),(cold,[0],[2]),(join,incoming+([3] if case=='other edge' else []),[])]):
        bs.append(NS(bid=n,is_entry=n==0,insns=list(Decoder(64,raw,ip=ip)),preds=preds,succs=succs));ip+=len(raw)
    lift=NS(_blocks=bs,_current_method=NS(addr=start),rt_init_meta=init,il=NS(eh_regions=lambda _:None))
    assert _guarded_ref_bool_forward(lift,bs[2],bs[2].insns[-1])==(case in ('hot and cold','linearized'))


@pytest.mark.parametrize('cleanup,ok',[
    ('4883c101',True),       # volatile scratch in an otherwise empty cleanup
    ('488bc2',True),         # caller is void; old RAX does not escape the tail
    ('4080c601',False),      # SIL is part of the saved flag, even a partial write matters
    ('488beb',False),        # overwrite saved runner
    ('48894c2430',False),    # overwrite the caller's saved RBX
    ('488d4c2430',False),    # escape an address in the frame
    ('4883c408',False),      # restores no longer use the entry stack coordinates
    ('ffd0',False),          # opaque indirect transfer
])
def test_cleanup_tail_requires_preserved_arguments_and_homes(cleanup,ok):
    va=0x3000
    # Dummy guard skips a NOP to the test cleanup. No metadata from the
    # private fixture is required to validate the input/epilogue proof.
    head='48895c2408 48896c2410 4889742418 57 4883ec20 803d0001000000 410fb6f0 488bea 488bd9 7501'
    out='4531c9 440fb6c6 488bd5 488bcb 488b5c2430 488b6c2438 488b742440 4883c420 5f e900200000'
    blocks=[];ip=va
    for n,code in enumerate((head,'90',cleanup,out)):
        data=bytes.fromhex(code);blocks.append(NS(bid=n,is_entry=n==0,preds=[] if n==0 else [n-1],succs=[] if n==3 else [n+1],
                                                   insns=list(Decoder(64,data,ip=ip))));ip+=len(data)
    il=NS(function_extent=lambda _:(va,ip),eh_regions=lambda _:None,bin=NS(is_exec_va=lambda _:True))
    lift=NS(_current_method=NS(addr=va),_blocks=blocks,il=il)
    assert _cleanup_tail_forward(lift,blocks[3],blocks[3].insns[-1])==ok


@pytest.mark.parametrize('change',['wrong source','other call','other flag','clobber before branch','other edge','handler entry'])
def test_unproved_guarded_argument_declines(change):
    assert not guarded_helper(change)


def test_stack_save_leaves_both_parked_arguments_intact():
    assert guarded_helper(spill='4889742430 ')       # mov [rsp+30h],rsi
    assert not guarded_helper(spill='488b5c2430 ')   # reload changes the helper
    assert not guarded_helper(spill='48897730 ')     # store through the receiver


@pytest.mark.parametrize('change',[None,'test this','non-null skips','short skip','bypass helper check','wrong source'])
def test_optional_guard_must_test_the_forwarded_helper(change):
    assert guarded_helper(change,null_guard=True) == (change is None)
