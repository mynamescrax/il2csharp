from test_loop_headers import _block,_decompiler


def _case():
    # An outer choice may independently return through R. In C the
    # guarded prefix may return through R or enter the shared body J.
    blocks=[_block(0,term=('jcc',1,2),cond='outer',succs=(1,2)),
            _block(1,term=('jcc',3,5),cond='entry',succs=(3,5),preds=(0,)),
            _block(2,term=('jmp',6),succs=(6,),preds=(0,)),
            _block(3,term=('jcc',6,4),cond='invalid',succs=(6,4),preds=(1,)),
            _block(4,stmts=['Resume();'],term=('jmp',5),succs=(5,),preds=(3,)),
            _block(5,stmts=['Shared();'],term=('ret',),preds=(1,4)),
            _block(6,term=('ret',),preds=(2,3))]
    blocks[5].ret='true';blocks[6].ret='false'
    d=_decompiler(blocks,0,set(),0);d.loop_of_hdr={};d.reach=set(range(7))
    d.phi_copies={(3,6):['Early();'],(3,4):['EnterResume();'],(4,5):['ResumeEdge();'],(1,5):['FirstEdge();']}
    return d,blocks


def test_private_guard_keeps_edge_effects_and_shared_return():
    d,bs=_case();out=[];assert d._guarded_continuation(bs,1,out)==5
    assert out==['if (entry)','{','if (invalid)','{','Early();','return false;','}','EnterResume();','Resume();','ResumeEdge();','}','else','{','FirstEdge();','}']
    assert bs[3].consumed and bs[4].consumed and not bs[5].consumed and not bs[6].consumed


def test_third_entry_or_observable_return_declines_without_consuming():
    for defect in ('side entrance','return work'):
        d,bs=_case()
        if defect=='side entrance':bs[2].term=('jmp',5);bs[2].succs=[5];bs[5].preds.append(2);bs[6].preds.remove(2)
        else:bs[6].stmts.append('BeforeReturn();')
        out=['AlreadyEmitted();'];assert d._guarded_continuation(bs,1,out) is None
        assert out==['AlreadyEmitted();'] and not any(b.consumed for b in bs)


def test_shared_constant_return_can_already_belong_to_earlier_sibling():
    d,bs=_case();bs[6].consumed=True;out=[]
    assert d._guarded_continuation(bs,1,out)==5
    assert out.count('return false;')==1 and out[out.index('Early();')+1]=='return false;'
