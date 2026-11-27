"""Two rendered player arms share one native pair of closed lookup sites."""
import re
import pytest
from iced_x86 import Decoder,Register as R
from dotnet_case import run_case
from il2cpp import Decompiler,Lifter
from il2cpp.closed_lookup import closed_lookup_sites
from test_game_shift_shared_flags import shift_runtime

pytestmark=pytest.mark.game


def test_both_collision_player_arms_use_the_looked_up_player(shift_runtime,tmp_path):
    meta,il=shift_runtime;d=Decompiler(Lifter(il));md=meta.methods[28219];text='\n'.join(d.lift_method(md,meta.typedefs[md.declaring]));slices=list(re.finditer(r'^( *)if \(collision\.gameObject\.CompareTag\("Player"\)\)\n\1\{.*?^\1}',text,re.M|re.S));assert len(slices)==2
    src='''using System;using System.Collections.Generic;using System.Linq;using UnityEngine;
foreach(bool arm in new[]{false,true})foreach(var mode in new[]{"other","off","miss","dead","thrower","network missing","stuck","damage","lookup fault","compare fault","network fault","action fault"}){
 var t=new Case();var trace=new List<string>();var error=new ApplicationException();void Step(string s,string fail="-"){trace.Add(s);if(mode==fail)throw error;}
 var p=new PlayerManager();var other=new PlayerManager();var net=new Fusion.NetworkObject();var tag=new GameObject();var lookup=new GameObject();int reads=0;
 var col=new Collision{Read=()=>{Step("go"+(++reads));return reads==1?tag:lookup;}};tag.Tag=s=>{if(s!="Player")throw new Exception();Step("tag");t.dealDamageToPlayer=mode!="off";return mode!="other";};
 lookup.Lookup=ty=>{if(ty!=typeof(PlayerManager))throw new Exception("wrong player MethodRef");Step("player","lookup fault");return mode=="miss"?null:p;};
 p.Lookup=ty=>{if(ty!=typeof(Fusion.NetworkObject))throw new Exception("wrong network MethodRef");Step("network","network fault");return mode=="network missing"?null:net;};
 int tests=0;UnityEngine.Object.Neq=(a,b)=>{int n=++tests;Step("eq"+n,n==1?"compare fault":"-");if(n==1){if(!ReferenceEquals(a,mode=="miss"?null:p)||b is not null)throw new Exception();t.playerManThrowing=mode=="thrower"?p:other;return mode!="miss"&&mode!="dead";}
 if(n==2){if(!ReferenceEquals(a,p)||!ReferenceEquals(b,t.playerManThrowing))throw new Exception();return !ReferenceEquals(a,b);}if(n!=3||b is not null||!ReferenceEquals(a,mode=="network missing"?null:net))throw new Exception();t.makesPlayerStuck=mode=="stuck";t.damageWhenHitPlayer=6.25f;t.significantDamageAnim=true;return a is not null;};
 p.Damage=(f,b,s)=>{if(f!=6.25f||!b||s!="PLAYER")throw new Exception("wrong arguments");Step("damage","action fault");};p.Stick=f=>{if(f!=5f)throw new Exception();Step("stuck");};
 Exception fault=null;try{t.Run(arm,col);}catch(Exception e){fault=e;}
 string[] order={"go1","tag","go2","player","eq1","eq2","network","eq3",mode=="stuck"?"stuck":"damage"};int len=mode switch{"other" or "off"=>2,"lookup fault"=>4,"miss" or "dead" or "compare fault"=>5,"thrower"=>6,"network fault"=>7,"network missing"=>8,_=>9};
 if(!trace.SequenceEqual(order.Take(len))||(mode.EndsWith(" fault")?!ReferenceEquals(fault,error):fault!=null))throw new Exception(mode+": "+string.Join(',',trace),fault);}
Console.WriteLine("both player arms: lookup identities, three Unity comparisons, damage/stuck args and faults passed");
namespace UnityEngine{public class Object{public static Func<Object,Object,bool> Neq;public static bool operator !=(Object a,Object b)=>Neq(a,b);public static bool operator ==(Object a,Object b)=>!Neq(a,b);public override bool Equals(object o)=>ReferenceEquals(this,o);public override int GetHashCode()=>base.GetHashCode();}
public class Component:Object{public Func<Type,Component> Lookup;public T GetComponent<T>()where T:Component=>(T)Lookup(typeof(T));}public class GameObject:Component{public Func<string,bool> Tag;public bool CompareTag(string s)=>Tag(s);}public class Collision{public Func<GameObject> Read;public GameObject gameObject=>Read();}}
namespace Fusion{public class NetworkObject:Component{}}public class PlayerManager:Component{public Action<float,bool,string> Damage;public Action<float> Stick;public new T GetComponent<T>()where T:Component=>throw new Exception("selected hidden overload");public void GetStuck(float f)=>Stick(f);public void TakeDamage(float f,bool b,string s)=>Damage(f,b,s);}
class Case{public bool dealDamageToPlayer,makesPlayerStuck,significantDamageAnim;public PlayerManager playerManThrowing;public float damageWhenHitPlayer;
public void Run(bool arm, Collision collision){if(arm)One(collision);else Two(collision);}\n'''+ '\n'.join('void '+n+'(Collision collision){\n'+s[0]+'\n}' for s,n in zip(slices,('One','Two')))+'}'
    runner=tmp_path/'runner';runner.mkdir();(runner/'Program.cs').write_text(src,encoding='utf8');print(run_case(tmp_path,runner).strip())


@pytest.mark.parametrize('defect',['wrong companion','wrong stack home','wrong klass','wrong lookup target','wrong second receiver','partial SP'])
def test_vtable_and_reference_chain_need_registered_origins(shift_runtime,monkeypatch,defect):
    meta,il=shift_runtime;d=Decompiler(Lifter(il));md=meta.methods[28219];d.lift_method(md,meta.typedefs[md.declaring]);bs=d.L._blocks
    def probe():
        chained={};edges={};closed_lookup_sites(d.L,md,bs,(),previous_inputs=chained,virtuals=edges);return chained,edges
    assert probe()[0][0x18060b077]==0x18060b000 and probe()[1][0x18060afa3][0]==25441
    ip={'wrong companion':0x18060af80,'wrong stack home':0x18060af87,'wrong klass':0x18060af64,'wrong lookup target':0x18060af2c,'wrong second receiver':0x18060b074,'partial SP':0x18060af98}[defect]
    b,j=next((b,j) for b in bs for j,i in enumerate(b.insns) if i.ip==ip);i=b.insns[j].copy()
    if defect in ('wrong companion','wrong stack home'):i.memory_displacement+=8
    elif defect=='wrong klass':i.memory_base=R.RSI
    elif defect=='wrong lookup target':i.near_branch64=0x180b5d280
    elif defect=='partial SP':
        alt=Decoder(64,bytes.fromhex('664080f410'),ip=ip).decode();assert alt.len==i.len and alt.op0_register==R.SPL;i=alt
    else:i.op1_register=R.RDI
    monkeypatch.setattr(b,'insns',b.insns[:j]+[i]+b.insns[j+1:]);p,e=probe();assert 0x18060b077 not in p
    if defect!='wrong second receiver':assert not e
