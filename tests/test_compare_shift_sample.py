from pathlib import Path
import sys

import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from compare_shift_sample import _ids,compare


def entry(k,body):return {'mi':k,'va':'0x123'+str(k),'type':'Thing','name':'Run','return':'void','params':[],'asm':['0x1234 ret'],'body':body}


def test_paired_metrics_count_occurrences_and_distinct_addresses_separately():
    a=entry(3,['object obj1 = unknown;','sub_ff/*shared body, a*/(); sub_ff/*shared body, b*/();']);b=entry(5,['return;'])
    c=entry(3,['Poll();']);r=compare(_ids('5 3'),[b,a],[c,b]);assert r['different']==[3]
    assert r['before']==dict(rows=2,lines=3,return_only=1,shared_markers=2,untyped_locals=1,unknown=1,shared_addresses=1)
    assert r['after']['untyped_locals']==r['after']['shared_addresses']==0
    assert r['review_increases']==[]
    assert compare([3],[c],[a])['review_increases']==[dict(mi=3,increases=dict(unknown=1,untyped_locals=1,shared_markers=2))]


def test_change_in_native_input_or_missing_method_is_not_a_source_improvement():
    x=entry(3,['return;']);other=dict(x,asm=['0x1234 nop','0x1235 ret']);
    with pytest.raises(ValueError,match='native identity'):compare([3],[x],[other])
    with pytest.raises(ValueError,match='inventory'):compare([3,5],[x],[x])
    with pytest.raises(ValueError,match='distinct'):_ids('3 0x3')
