import pytest
from dotnet_case import run_case
from il2cpp.dec.joined_search import joined_search
from test_loop_headers import _block, _decompiler


def flow():
    bs=[_block(0,term=('jmp',1),succs=(1,)),
        _block(1,term=('jcc',6,2),cond='i == items.Length',succs=(6,2),preds=(0,4)),
        _block(2,term=('jcc',4,3),cond='!First(items[i])',succs=(4,3),preds=(1,)),
        _block(3,term=('jcc',5,4),cond='Second(items[i])',succs=(5,4),preds=(2,)),
        _block(4,term=('jmp',1),succs=(1,),preds=(3,2)),
        _block(5,stmts=('Mark("act");',),term=('fall',6),succs=(6,),preds=(3,)),
        _block(6,term=('ret',),succs=(),preds=(1,5))]
    d=_decompiler(bs,1,{1,2,3,4},4);d.phi_copies={(1,6):['Mark("miss");'],(5,6):['Mark("hit");'],
            (2,4):['Mark("reject-a");'],(3,4):['Mark("reject-b");'],(4,1):['i++;']}
    d.reach=set(range(len(bs)))
    return d,bs


def test_joined_search_copies_are_edge_specific(tmp_path):
    d,bs=flow();out=[];assert joined_search(d,bs,1,set(),set(),out,0)==6
    assert not bs[6].consumed and not d._bstack
    src='''using System;using System.Collections.Generic;
foreach(var (items,expected) in new[]{(new int[0],"miss"),(new[]{0,0},"first,reject-a,first,reject-a,miss"),
    (new[]{0,1,2,9},"first,reject-a,first,second,reject-b,first,second,act,hit")}){
 var seen=new List<string>();int i=0;void Mark(string s)=>seen.Add(s);bool First(int x){Mark("first");return x!=0;}bool Second(int x){Mark("second");return x>=2;}
'''+ '\n'.join(out[1:])+'''\nif(string.Join(',',seen)!=expected)throw new Exception(string.Join(',',seen));}
Console.WriteLine("common join: rejection, matched-action and exhausted edges execute only their own transfers");'''
    p=tmp_path/'r';p.mkdir();(p/'Program.cs').write_text(src,encoding='utf8');print(run_case(tmp_path,p))


@pytest.mark.parametrize('invalid',['shared action','outer loop','shared latch','consumed action','extra join predecessor','action is stop','nonlinear cleanup'])
def test_joined_search_fails_before_mutating_the_cfg(invalid):
    d,bs=flow();out=['prefix'];stop=set();outer=set()
    if invalid=='shared action':bs[5].preds.append(0)
    elif invalid=='outer loop':outer.add(0)
    elif invalid=='shared latch':bs[4].preds.append(0)
    elif invalid=='consumed action':bs[5].consumed=True
    elif invalid=='extra join predecessor':bs[6].preds.append(0)
    elif invalid=='action is stop':stop.add(5)
    else:bs[6].term=('jcc',7,8);bs[6].succs=[7,8]
    before=[b.consumed for b in bs];assert joined_search(d,bs,1,stop,outer,out,0) is None
    assert not d._bstack and out==['prefix'] and [b.consumed for b in bs]==before


@pytest.mark.parametrize('bypass',[False,True])
def test_stale_trampoline_is_not_an_external_entry_but_a_real_one_is(bypass):
    d,bs=flow();bs.append(_block(7,term=('jmp',5),succs=(5,)));bs[5].preds.append(7)
    if bypass:
        bs[0].term=('jcc',1,7);bs[0].succs=[1,7];bs[0].cond='scan';bs[7].preds.append(0);d.reach.add(7)
    out=[];assert joined_search(d,bs,1,set(),set(),out,0)==(None if bypass else 6)
    assert bool(out)!=bypass


def test_diamond_inputs_and_final_phi_survive_lexical_scopes(tmp_path):
    d,bs=flow();bs.extend([_block(7,term=('jcc',8,2),cond='side',succs=(8,2),preds=(1,)),_block(8,term=('fall',2),succs=(2,),preds=(7,))]);bs[1].term=('jcc',6,7);bs[1].succs=[6,7];bs[2].preds=[7,8];d.loop_of_hdr[1][0].update((7,8));d.reach.update((7,8))
    bs[2].cond='value < 0';bs[3].cond='value == 17';bs[5].stmts=['selected = value;'];d.phi_copies={(7,2):['value = items[i];'],(8,2):['value = -items[i];'],(1,6):['selected=-37;'],(5,6):['selected++;'],(4,1):['i++;']}
    out=[];assert joined_search(d,bs,1,set(),set(),out,0)==6
    src='''using System;
foreach(bool side in new[]{true,false})foreach(var items in new[]{new[]{-17,1},new[]{17,-1},Array.Empty<int>()}){int i=0;int selected=0;int value;
'''+ '\n'.join(out[1:])+'''\nint expected=Array.IndexOf(items,side?-17:17)>=0?18:-37;if(selected!=expected)throw new Exception($"{selected}/{expected}");}
Console.WriteLine("two diamond inputs and both exit values passed");'''
    p=tmp_path/'r';p.mkdir();(p/'Program.cs').write_text(src,encoding='utf8');print(run_case(tmp_path,p))
