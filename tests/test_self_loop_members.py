from test_loop_headers import _block,_decompiler


def test_self_loops_do_not_own_preheaders_or_sibling_cases():
    # entry -> two case preheaders. Loop A also has a second real latch.
    # The unreachable predecessor of that latch is not an extra loop block.
    bs=[_block(0,succs=(1,2)),_block(1,preds=(0,),succs=(3,)),_block(2,preds=(0,),succs=(4,)),
        _block(3,preds=(1,3,5),succs=(3,5,6)),_block(4,preds=(2,4),succs=(4,6)),
        _block(5,preds=(3,7),succs=(3,)),_block(6,preds=(3,4)),_block(7,succs=(5,))]
    d=_decompiler(bs,0,set(),0);reach=set(range(7));dom=d._dominators(bs,d._rpo(bs),reach)
    loops=d._loops(bs,dom,reach);assert {k:v[0] for k,v in loops.items()}=={3:{3,5},4:{4}}


def test_inner_self_edge_leaves_outer_latch_outer_only():
    bs=[_block(0,succs=(1,)),_block(1,preds=(0,3),succs=(2,4)),_block(2,preds=(1,2),succs=(2,3)),
        _block(3,preds=(2,),succs=(1,)),_block(4,preds=(1,))]
    d=_decompiler(bs,0,set(),0);reach=set(range(5));loops=d._loops(bs,d._dominators(bs,d._rpo(bs),reach),reach)
    assert loops[2][0]=={2} and loops[1][0]=={1,2,3}


def test_multi_latch_self_edge_retries_before_work(tmp_path):
    from dotnet_case import run_case
    bs=[_block(0,stmts=['log += "h";'],term=('jcc',0,1),cond='++visits == 1',succs=(0,1),preds=(0,1)),
        _block(1,stmts=['log += "w";'],term=('jcc',0,2),cond='visits < 3',succs=(0,2),preds=(0,)),
        _block(2,term=('ret',),preds=(1,))]
    d=_decompiler(bs,0,{0,1},1);d.phi_copies={(0,0):['log += "r";'],(1,0):['log += "b";']};out=[]
    assert d._emit_loop(bs,0,out,set(),0)==2
    runner=tmp_path/'runner';runner.mkdir();(runner/'Program.cs').write_text('using System;int visits=0;string log="";\n'+'\n'.join(x for x in out if not x.startswith('@@'))+'\nif(log!="hrhwbhw")throw new Exception(log);',encoding='utf8');run_case(tmp_path,runner)
