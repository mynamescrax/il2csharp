"""The structurer prints this native overflow tail twice. Run both copies."""
import re

import pytest
from iced_x86 import Decoder
from dotnet_case import run_case
from il2cpp import Decompiler,Lifter
from il2cpp.closed_class_read import closed_class_reads
from test_game_shift_shared_flags import shift_runtime

pytestmark=pytest.mark.game


def test_dequeue_snapshot_in_both_overflow_arms(shift_runtime,tmp_path):
    meta,il=shift_runtime;md=meta.methods[27515];d=Decompiler(Lifter(il));lines=d.lift_method(md,meta.typedefs[md.declaring]);s='\n'.join(lines)
    cases=list(re.finditer(r'^( *)System.Collections.Generic.Queue_1<ChatLogNode> (\w+) = this.chatQueue;\n\1if \(\2.Count > 20\)\n\1\{.*?^\1}',s,re.M|re.S));assert len(cases)==2
    src='''using System;using System.Linq;using System.Collections.Generic;using UnityEngine;
foreach(bool copy in new[]{false,true})foreach(var mode in new[]{"under","live","destroyed","null","comparison throws","getter throws","reenter"}) {
 var head=mode=="null"?null:new ChatLogNode{Id=1,Dead=mode=="destroyed"};var next=new ChatLogNode{Id=2};var final=new ChatLogNode{Id=3};var c=new Case();
 c.chatQueue.Enqueue(head);c.chatQueue.Enqueue(next);c.chatQueue.Enqueue(final);for(int j=3;j<(mode=="under"?20:mode=="reenter"?22:21);j++)c.chatQueue.Enqueue(new ChatLogNode());
 var trace=new List<string>();var fail=new ApplicationException();
 UnityEngine.Object.Compare=(a,b)=>{if(b is not null)throw new Exception("not null comparison");trace.Add("neq "+(a?.Id??0));if(mode=="comparison throws")throw fail;
     if(mode=="reenter"&&ReferenceEquals(a,head))c.Run(copy);return a is not null&&!a.Dead;};
 Component.Get=c=>{trace.Add("get "+c.Id);if(mode=="getter throws")throw fail;return c.Game;};UnityEngine.Object.Drop=g=>trace.Add("drop "+(ReferenceEquals(g,head?.Game)?1:ReferenceEquals(g,next.Game)?2:-1));
 bool fault=false;try{c.Run(copy);}catch(ApplicationException e)when(ReferenceEquals(fail,e)){fault=true;}
 string want=mode switch{"under"=>"","live"=>"neq 1,get 1,drop 1","destroyed" or "comparison throws"=>"neq 1","null"=>"neq 0","getter throws"=>"neq 1,get 1",_=>"neq 1,neq 2,get 2,drop 2,get 1,drop 1"};
 if(fault!=mode.EndsWith(" throws")||string.Join(',',trace)!=want||c.chatQueue.Count!=20||!ReferenceEquals(c.chatQueue.Peek(),mode=="under"?head:mode=="reenter"?final:next))throw new Exception(mode+": "+string.Join(',',trace));
}
Console.WriteLine("both overflow arms: head identity, runner-up retained, Unity-null, comparison/getter faults and reentry passed");
namespace UnityEngine{class Object {public int Id;public bool Dead;public static Func<Object,Object,bool> Compare;public static bool operator !=(Object a,Object b)=>Compare(a,b);public static bool operator ==(Object a,Object b)=>!Compare(a,b);public override bool Equals(object b)=>ReferenceEquals(this,b);public override int GetHashCode()=>Id;public static Action<Object> Drop;public static void Destroy(Object g)=>Drop(g);}
class GameObject:Object{}class Component:Object{public GameObject Game=new();public static Func<Component,GameObject> Get;public GameObject gameObject=>Get(this);}}
namespace System.Collections.Generic{class Queue_1<T>:Queue<T>{}}
class ChatLogNode:Component{}class Case{public Queue_1<ChatLogNode> chatQueue=new();public void Run(bool copy){if(copy)One();else Two();}
'''+ '\n'.join('void '+name+'(){\n'+match[0]+'\n}' for name,match in zip(('One','Two'),cases))+'}'
    runner=tmp_path/'runner';runner.mkdir();(runner/'Program.cs').write_text(src,encoding='utf8');print(run_case(tmp_path,runner).strip())


@pytest.mark.parametrize('change',['wrong hidden lane','wrong receiver','conflicting entry','bad count leaf','other origin'])
def test_closed_class_proof_needs_independent_facts(shift_runtime,monkeypatch,change):
    meta,il=shift_runtime;d=Decompiler(Lifter(il));md=meta.methods[27515];d.lift_method(md,meta.typedefs[md.declaring]);bs=d.L._blocks
    prove=lambda:closed_class_reads(d.L,md,bs,d._pad_bids);prod=0x1805c04f9;cmp=0x1805c04e5
    assert prove()[prod][3]=='Dequeue' and prove()[cmp][2]=='Count'
    if change=='conflicting entry':monkeypatch.setitem(il._awaiter_spec_indices[11577],172606,-1)
    elif change=='bad count leaf':
        orig=il.bin.read;monkeypatch.setattr(il.bin,'read',lambda a,n:bytes.fromhex('8b4124c3') if a==0x1805b0d40 and n==4 else orig(a,n))
    else:
        at,code={'wrong hidden lane':(0x1805c04ef,'4c8b05'),'wrong receiver':(0x1805c04f6,'488bcb'),'other origin':(0x1805bffc9,'488bfa')}[change]
        b,j=next((b,j) for b in bs for j,i in enumerate(b.insns) if i.ip==at);i=b.insns[j];data=bytes.fromhex(code)+il.bin.read(at,i.len)[3:];alt=Decoder(64,data,ip=at).decode();assert alt.len==i.len
        monkeypatch.setattr(b,'insns',b.insns[:j]+[alt]+b.insns[j+1:])
    plan=prove()
    if change=='bad count leaf':assert cmp not in plan and prod in plan
    else:assert prod not in plan
