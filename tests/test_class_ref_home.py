from types import SimpleNamespace as NS

from il2cpp import Expr
from test_stack_args import make_call_lifter,INT,FLOAT


def test_closed_float_reference_kills_only_its_four_bytes():
    var=(4,(0x13<<16)|(1<<29));ref_float=(0,(0xc<<16)|(1<<29));home=Expr('&s_20',None,'ptr');home._stack_offset=32
    l,_=make_call_lifter([INT,var],{'R8':home,'XMM2':Expr('wrong',FLOAT,'float')},static=False)
    l._call_class_args=(FLOAT,);l._call_class_refs={var:ref_float};l.il._sf_field_size=lambda t,depth:4 if t==FLOAT else None
    l.meta.generic_parameters=[None]*4+[(0,None,0,0,0,0)];l.stack_map={32:'s_20',36:'s_24'};l.stack_values={'s_20':Expr('old',FLOAT,'float')}
    for off,text in ((32,'old'),(36,'keep')):l._stack_store(off,4,Expr(text,FLOAT,'float'))
    es=[Expr('this',None,'obj'),Expr('k',INT,'int'),home,None];args=['this','k','&s_20','_','wrong'];l._xmm_pending=[(2,l.regs['XMM2'])]
    l._hint_arg_types(args,es,0,INT);assert l._positional_args(args,l.meta.methods[0],INT)==['this','k','ref s_20'] and l.slot_types['s_20']==FLOAT
    l._kill_byref_slots(0,INT,es);assert 's_20' not in l.stack_values and '!mem:32:4' not in l.regs and l.regs['!mem:36:4'].text=='keep'


def test_reloaded_ref_to_open_home_cannot_leave_stale_zero_or_alias():
    var=(0,(0x13<<16)|(1<<29));p=Expr('&s_20',None,'ptr');l,_=make_call_lifter([var],{'RDX':p},static=False)
    l.il._sf_field_size=lambda t,depth:4 if t==INT else None
    l.stack_map={20:'s_14',32:'s_20',36:'s_24'};l.addr_of['s_24']='other'
    for off,nm in l.stack_map.items():
        v=Expr('0',INT,'int');l.stack_values[nm]=v;l._stack_store(off,4,v)
    l._kill_byref_slots(0,INT,[None,p]);assert l.stack_values.keys()=={'s_14'} and not l.addr_of
    assert sorted(k for k in l.regs if k.startswith('!mem:'))==['!mem:20:4']


def test_partial_byref_overwrite_does_not_invent_high_dword():
    ref=(0,(8<<16)|(1<<29));p=Expr('&s_20',None,'ptr');p._stack_offset=32
    l,_=make_call_lifter([ref],{'RDX':p},static=False);l.il._sf_field_size=lambda t,depth:4 if t==INT else 8
    l.stack_map[32]='s_20';l._stack_store(32,8,Expr('7',(0,0xa<<16),'int'))
    l._kill_byref_slots(0,INT,[None,p]);assert l._stack_piece(36,4) is None
