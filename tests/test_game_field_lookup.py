"""A guarded second lookup must reload its field, even with the same MethodRef."""
import pytest
from iced_x86 import Decoder, Register as R

from dotnet_case import run_case
from il2cpp import Decompiler,Lifter
from il2cpp.closed_lookup import closed_lookup_sites
from il2cpp.closed_lookup import _field_input
from il2cpp.captured_home import _normal_predecessors
from il2cpp.emitter import Emitter
from test_game_shift_shared_flags import shift_runtime

pytestmark=pytest.mark.game


def test_store_attack_reloads_target_only_on_success(shift_runtime,tmp_path):
    meta,il=shift_runtime;method=meta.methods[27705];lines=[]
    Emitter(il,str(tmp_path/'out')).emit_method(method,meta.typedefs[method.declaring],lines,'    ')
    src='''using System;using System.Collections.Generic;using System.Linq;using UnityEngine;
foreach(var mode in new[]{"hit","missing","destroyed","first fault","truth fault","second fault","last fault","new target null","second missing","path false","path cleared","first target null"}){
 var t=new StoreBrowseBehaviour();var trace=new List<string>();var old=new PlayerManager();var guard=new PlayerManager();var value=new PlayerManager();t.targPlayerMan=old;
 var a=new Transform();var b=new Transform();var pathA=new AIPath();var pathB=new AIPath();t.pathfinder=pathA;var fault=new ApplicationException(mode);
 t.Trigger=s=>{if(s!="Zombie Attack"||t.attacking)throw new Exception("trigger order");trace.Add("trigger");};
 t.Schedule=(s,f)=>{if(!t.attacking)throw new Exception("not attacking");if(s=="FinishAttack"&&f==1f){trace.Add("finish");t.target=mode=="first target null"?null:a;return;}
 if(s!="DealDamageToPlayer"||f!=0.23f||!ReferenceEquals(t.targPlayerMan,mode=="second missing"?null:value))throw new Exception("damage schedule/order");trace.Add("damage");if(mode=="last fault")throw fault;};
 a.Lookup=k=>{trace.Add("A");if(k!=typeof(PlayerManager))throw new Exception("specialization");if(mode=="first fault")throw fault;return mode=="missing"?null:guard;};
 b.Lookup=k=>{trace.Add("B");if(k!=typeof(PlayerManager)||!ReferenceEquals(t.targPlayerMan,old))throw new Exception("wrong second lookup");if(mode=="second fault")throw fault;return mode=="second missing"?null:value;};
 UnityEngine.Object.Truth=x=>{if(ReferenceEquals(x,pathA)){trace.Add("path");t.pathfinder=mode=="path cleared"?null:pathB;return mode!="path false";}
 if(!ReferenceEquals(x,mode=="missing"?null:guard))throw new Exception("wrong guard");trace.Add("player");t.target=mode=="new target null"?null:b;
 if(mode=="truth fault")throw fault;return mode!="missing"&&mode!="destroyed";};
 Exception caught=null;try{t.Run();}catch(Exception e){caught=e;}
 string want="trigger,finish,path,A"+(mode=="first fault"?"":",player"+(mode is "missing" or "destroyed" or "truth fault" or "new target null"?"":",B"+(mode=="second fault"?"":",damage")));
 if(mode is "path cleared" or "first target null")want="trigger,finish,path";
 if(string.Join(',',trace)!=want||pathA.maxSpeed!=0||pathB.maxSpeed!=(mode is "path false" or "path cleared"?0f:2f)||!ReferenceEquals(t.targPlayerMan,mode=="second missing"?null:mode is "hit" or "last fault" or "path false"?value:old))throw new Exception(mode+":"+string.Join(',',trace));
 if(mode.EndsWith("fault")?!ReferenceEquals(fault,caught):mode is "new target null" or "path cleared" or "first target null"?caught is not NullReferenceException:caught!=null)throw new Exception("fault: "+mode,caught);
}
Console.WriteLine("Attack: only a live first result schedules the second lookup; stored result, pathfinder reload and faults passed");
namespace UnityEngine{public class Object{public static Func<Object,bool> Truth;public static implicit operator bool(Object x)=>Truth(x);}public class Component:Object{public Func<Type,Component> Lookup;public T GetComponent<T>()where T:Component=>(T)Lookup(typeof(T));}public class Transform:Component{public new T GetComponent<T>()where T:Component=>throw new Exception("hidden member");}}
public class AIPath:Component{public float maxSpeed;}public class PlayerManager:Component{}public class StoreBrowseBehaviour{public Action<string> Trigger;public Action<string,float> Schedule;void Invoke(string s,float f)=>Schedule(s,f);void Rpc_CMD_Trigger(string s)=>Trigger(s);
public bool attacking;public PlayerManager targPlayerMan;public Transform target;public AIPath pathfinder;public void Run()=>Attack();\n'''+ '\n'.join(lines)+'\n}'
    runner=tmp_path/'runner';runner.mkdir();(runner/'Program.cs').write_text(src,encoding='utf8');print(run_case(tmp_path,runner).strip())


@pytest.mark.parametrize('change',['wrong owner','partial field','overlap'])
def test_field_receivers_need_layout_and_reaching_this(shift_runtime,monkeypatch,change):
    meta,il=shift_runtime;md=meta.methods[27705];td=meta.typedefs[md.declaring];d=Decompiler(Lifter(il));d.lift_method(md,td);bs=d.L._blocks
    call,load=0x1805cc2c2,0x1805cc2af
    def proof():
        sites={};closed_lookup_sites(d.L,md,bs,(),field_inputs=sites);return sites
    assert proof()[call][0]==load
    if change=='overlap':
        offsets=list(il.field_offsets[td.index]);other=offsets.index(0x1e0);offsets[other]=0xc8
        monkeypatch.setitem(il.field_offsets,td.index,offsets) if isinstance(il.field_offsets,dict) else monkeypatch.setattr(il,'field_offsets',[offsets if k==td.index else x for k,x in enumerate(il.field_offsets)])
    else:
        b,k=next((b,k) for b in bs for k,i in enumerate(b.insns) if i.ip==load);i=b.insns[k].copy()
        if change=='wrong owner':i.memory_base=R.RDI
        else:i.memory_displacement+=4
        monkeypatch.setattr(b,'insns',b.insns[:k]+[i]+b.insns[k+1:])
    assert call not in proof()


def test_entry_backedge_cannot_supply_original_this(shift_runtime):
    meta,il=shift_runtime;md=meta.methods[27705];owner=next(td.index for td in meta.typedefs if td.name=='Component' and td.namespace=='UnityEngine')
    # mov rbx,rcx; mov rax,[rbx+C8]; test rax,rax; jne use;
    # mov rcx,rdx; jmp entry (or nop; nop); use: mov rcx,rax; call ...
    for edge,expected in [('9090',True),('ebec',False)]:
        seq=list(Decoder(64,bytes.fromhex('4889cb 488b83c8000000 4885c0 7505 4889d1 '+edge+' 4889c1 e800010000'),ip=md.addr))
        pred=_normal_predecessors(seq)
        assert bool(_field_input(il,md,{i.ip:i for i in seq},pred,seq[-1],owner))==expected
