"""Run the emitted query and emptiness test from each placement branch."""
import re

import pytest
from iced_x86 import Register as R

from dotnet_case import run_case
from il2cpp import Decompiler,Lifter
from il2cpp.array_header import header_sites
from test_game_shift_shared_flags import shift_runtime

pytestmark=pytest.mark.game


@pytest.fixture(scope='module')
def placement(shift_runtime):
    meta,il=shift_runtime;d=Decompiler(Lifter(il));m=meta.methods[25657]
    return d,m,'\n'.join(d.lift_method(m,meta.typedefs[m.declaring]))


def test_full_width_empty_checks_evaluate_each_query_once(placement,tmp_path):
    d,m,text=placement;seq=[i for b in d.L._blocks for i in b.insns];target=0x182c9f9d0
    native={i.ip for i in seq if i.is_call_near and i.near_branch_target==target}
    reads,_=header_sites(d.L,m,d.L._blocks,d._pad_bids)
    assert len(native)==23 and set(reads.values())==native and text.count('.OverlapSphere(')==len(native)
    pairs=list(re.finditer(r'(UnityEngine.Collider\[\] (\w+) = UnityEngine.Physics\.OverlapSphere\((\w+), ([\d.]+f), (\w+)\);)\s*'
                           r'(if \(\2\.LongLength == 0\))',text))
    assert len(pairs)==len(native)
    code=['using System;using UnityEngine;',
          'foreach(var fn in new Func<Vector3,int,bool>[]{'+','.join(f'Cases.Site{n}' for n in range(len(pairs)))+'}){',
          '''foreach(int len in new[]{0,1,256,-1,-2}){int calls=0;var boom=new ApplicationException();var p=new Vector3(7,-11,0.5f);
          Physics.Query=(got,r,mask)=>{if(++calls!=1||got!=p||mask!=19)throw new Exception("query replay or wrong supplied operands");
          return len==-1?null:len==-2?throw boom:new Collider[len];};Exception fault=null;bool empty=false;
          try{empty=fn(p,19);}catch(Exception e){fault=e;}if(calls!=1||(len==-1?fault is not NullReferenceException:len==-2?!ReferenceEquals(fault,boom):fault!=null||empty!=(len==0)))throw new Exception("wrong length/fault");}}
          Console.WriteLine("all 23 placement-query slices: one query per invocation, 0/1/256 hits, null and fault passed");
          namespace UnityEngine {public record struct Vector3(float x,float y,float z);public class Collider {}public class Physics{public static Func<Vector3,float,int,Collider[]> Query;public static Collider[] OverlapSphere(Vector3 p,float r,int mask)=>Query(p,r,mask);}}
          class Cases{''']
    for n,p in enumerate(pairs):code.append(f'public static bool Site{n}(Vector3 {p[3]},int {p[5]}){{\n{p[1]}\n{p[6]} return true; return false;}}')
    runner=tmp_path/'runner';runner.mkdir();(runner/'Program.cs').write_text('\n'.join(code)+'}',encoding='utf8');print(run_case(tmp_path,runner).strip())


@pytest.mark.parametrize('change',['wrong offset','narrow compare','stale zero','other throw','truncated table','reordered cases'])
def test_header_proof_declines_ambiguous_operand_or_dispatch(placement,monkeypatch,change):
    d,m,_=placement;bs=d.L._blocks;get=lambda:header_sites(d.L,m,bs,d._pad_bids)[0];ip=0x1806fad07
    assert ip in get()
    if change=='truncated table':
        binary=d.L.bin;read=binary.read;monkeypatch.setattr(binary,'read',lambda a,n:read(a,n-4) if a==0x18070a890 and n==244 else read(a,n))
    elif change=='reordered cases':
        b=next(b for b in bs if b.switch_targets);slots=list(b.switch_targets)
        k=next(k for k,t in enumerate(slots) if t!=slots[0]);slots[0],slots[k]=slots[k],slots[0]
        monkeypatch.setattr(b,'switch_targets',slots)
    else:
        at=0x1806fad01 if change=='other throw' else ip
        b,k=next((b,k) for b in bs for k,i in enumerate(b.insns) if i.ip==at);i=b.insns[k].copy()
        if change=='wrong offset':i.memory_displacement=16
        elif change=='narrow compare':
            from iced_x86 import Decoder
            raw=d.L.il.bin.read(at,i.len);alt=Decoder(64,raw.replace(b'\x4c',b'\x44',1),ip=at).decode();assert alt.op1_register==R.R15D;i=alt
        elif change=='stale zero':i.op1_register=R.RBX
        else:i.near_branch64=i.next_ip
        monkeypatch.setattr(b,'insns',b.insns[:k]+[i]+b.insns[k+1:])
    assert ip not in get()
