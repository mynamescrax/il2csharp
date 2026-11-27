import pytest
from iced_x86 import Register as R
from dotnet_case import run_case
from il2cpp import Decompiler,Lifter
from il2cpp.emitter import Emitter
from il2cpp.scalar_snapshot import scalar_sites
from test_game_shift_shared_flags import shift_runtime

pytestmark=pytest.mark.game


def test_complete_countdown_callbacks(shift_runtime,tmp_path):
    meta,il=shift_runtime;em=Emitter(il,str(tmp_path/'out'));groups={}
    for j in (23764,23765,23794,25374,28144):
        md=meta.methods[j];td=meta.typedefs[md.declaring];em.emit_method(md,td,groups.setdefault(td.name,[]),'    ')
    src='''using System;using System.Collections.Generic;using System.Linq;using UnityEngine;
bool Same(float a,float b)=>BitConverter.SingleToInt32Bits(a)==BitConverter.SingleToInt32Bits(b);
foreach(var mode in new[]{"skip","negative zero","entry NaN","live","equal","cross","NaN delta","clock throws","stop throws","stop null","go null","missing","destroyed","lookup throws","cmp throws","set throws"}){
 var c=new CFX_AutoStopLoopedEffect();var p=new ParticleSystem();var tr=new CFX_Demo_Translate();var g=new GameObject();var log=new List<string>();var ex=new ApplicationException();void Step(string s){log.Add(s);if(mode==s+" throws")throw ex;}
 float start=mode switch{"skip"=>-1,"negative zero"=>-0.0f,"entry NaN"=>BitConverter.Int32BitsToSingle(unchecked((int)0x7fc01234)),_=>2};c.effectDuration=start;c.Enable();if(!Same(start,c.d))throw new Exception("OnEnable");
 float dt=mode switch{"live"=>1,"equal"=>2,"NaN delta"=>float.NaN,_=>3};Time.Read=()=>{c.d=133;Step("clock");return dt;};c.Lookup=t=>{Step("particle");if(t!=typeof(ParticleSystem)||c.d!=start-dt)throw new Exception();return mode=="stop null"?null:p;};p.Do=b=>{if(!b)throw new Exception();Step("stop");c.Go=()=>{Step("go");return mode=="go null"?null:g;};};
 g.Lookup=t=>{Step("lookup");if(t!=typeof(CFX_Demo_Translate))throw new Exception();return mode=="missing"?null:tr;};UnityEngine.Object.Neq=(a,b)=>{Step("cmp");if(b is not null||!ReferenceEquals(a,mode=="missing"?null:tr))throw new Exception();g.Lookup=t=>throw new Exception("replayed lookup");return mode!="missing"&&mode!="destroyed";};tr.Set=b=>{if(b)throw new Exception();Step("set");c.d=-128;};
 Exception f=null;try{c.Run();}catch(Exception e){f=e;}int n=mode switch{"skip" or "negative zero" or "entry NaN"=>0,"live" or "clock throws" or "NaN delta"=>1,"stop null"=>2,"stop throws"=>3,"go null"=>4,"lookup throws"=>5,"missing" or "destroyed" or "cmp throws"=>6,_=>7};
 var want=mode=="clock throws"?133:n==0?start:mode is "cross" or "equal"?-128:start-dt;if(!log.SequenceEqual(new[]{"clock","particle","stop","go","lookup","cmp","set"}.Take(n))||(mode.EndsWith(" throws")?!ReferenceEquals(ex,f):mode is "stop null" or "go null"?f is not NullReferenceException:f!=null)||!(Same(c.d,want)||float.IsNaN(want)&&float.IsNaN(c.d)))throw new Exception(mode+":"+string.Join(',',log),f);
 if(n==0||c.d<=0||float.IsNaN(c.d)){log.Clear();c.Run();if(log.Count!=0)throw new Exception("replayed stop");}}
var gas=new GasCollisionSpawner{spawnEveryXCollisions=2,curTimeBeforeReset=1};int clocks=0;Time.Read=()=>{clocks++;gas.curTimeBeforeReset=100;if(clocks==2){gas.spawnEveryXCollisions=9;gas.timeBeforeReset=3;}return 1;};gas.Run();if(clocks!=1||gas.curTimeBeforeReset!=0||gas.curSpawnEveryXCollisions!=0)throw new Exception("early expiry");gas.Run();if(clocks!=2||gas.curTimeBeforeReset!=3||gas.curSpawnEveryXCollisions!=9)throw new Exception("bad rollover");gas.Run();if(clocks!=2||gas.curTimeBeforeReset!=3||gas.curSpawnEveryXCollisions!=9)throw new Exception("unexpected third tick");
var w=new WFX_Demo_DeleteAfterDelay{delay=1};var go=new GameObject();int deletes=0;w.Go=()=>go;Time.Read=()=>{w.delay=100;return 1;};UnityEngine.Object.Drop=o=>{if(!ReferenceEquals(o,go)||w.delay!=-(deletes+1))throw new Exception();deletes++;};w.Run();w.Run();w.Run();if(deletes!=2)throw new Exception("delete timing");
foreach(var mode in new[]{"off","equal","cross","rpc throws","last throws"}){var c=new ThirdPersonManager{upDownLookRot=37,curUpdateLookRotRate=1};var log=new List<string>();var ex=new ApplicationException();void Step(string s){log.Add(s);if(mode==s+" throws")throw ex;}
 var a=new Transform();var b=new Transform();c.Acquire=()=>{Step("object");return new Fusion.NetworkObject{Read=()=>{Step("auth");return mode!="off";}};};Time.Read=()=>{Step("time");c.curUpdateLookRotRate=87;c.camRot=a;return mode=="equal"?1:2;};
 a.Read=()=>{Step("anglesA");return new Vector3{x=3};};b.Read=()=>{Step("anglesB");return new Vector3{x=8};};c.Rpc=f=>{if(f!=3||c.curUpdateLookRotRate!=-1)throw new Exception();Step("rpc");c.camRot=b;c.updateLookRotRate=9;};c.Apply=f=>{if(f!=(mode=="off"?37:mode=="equal"?3:8))throw new Exception();Step("last");};Exception fault=null;try{c.Run();}catch(Exception e){fault=e;}
 string want=mode switch{"off"=>"object,auth,last","equal"=>"object,auth,time,anglesA,last","rpc throws"=>"object,auth,time,anglesA,rpc",_=>"object,auth,time,anglesA,rpc,anglesB,last"};if(string.Join(',',log)!=want||c.curUpdateLookRotRate!=(mode=="off"?1:mode=="equal"?0:mode=="rpc throws"?-1:9)||(mode.EndsWith(" throws")?!ReferenceEquals(ex,fault):fault!=null))throw new Exception(mode,fault);}
Console.WriteLine("five complete reset/countdown callbacks: distinct thresholds, saved field, stop identity, post-RPC reload, NaNs and faults passed");
namespace Fusion{public class NetworkObject{public Func<bool> Read;public bool HasInputAuthority=>Read();}}
namespace UnityEngine{public class Object{public static Func<Object,Object,bool> Neq;public static Action<Object> Drop;public static void Destroy(Object o)=>Drop(o);public static bool operator !=(Object a,Object b)=>Neq(a,b);public static bool operator ==(Object a,Object b)=>!Neq(a,b);public override bool Equals(object o)=>ReferenceEquals(this,o);public override int GetHashCode()=>base.GetHashCode();}public class Component:Object{public Func<Type,Component> Lookup;public T GetComponent<T>()where T:Component=>(T)Lookup(typeof(T));public Func<GameObject> Go;public GameObject gameObject=>Go();}public class GameObject:Component{}public class ParticleSystem:Component{public Action<bool>Do;public void Stop(bool b)=>Do(b);}public static class Time{public static Func<float> Read;public static float deltaTime=>Read();}public class Transform{public Func<Vector3>Read;public Vector3 localEulerAngles=>Read();}public struct Vector3{public float x,y,z;}}
public class CFX_Demo_Translate:Component{public Action<bool> Set;public bool enabled{set=>Set(value);}}
'''
    pre={'CFX_AutoStopLoopedEffect':'public float d,effectDuration;public void Enable()=>OnEnable();public void Run()=>Update();',
         'WFX_Demo_DeleteAfterDelay':'public float delay;public void Run()=>Update();',
         'GasCollisionSpawner':'public int curSpawnEveryXCollisions,spawnEveryXCollisions;public float curTimeBeforeReset,timeBeforeReset;public void Run()=>FixedUpdate();',
         'ThirdPersonManager':'public Func<Fusion.NetworkObject> Acquire;public Fusion.NetworkObject Object=>Acquire();public Transform camRot;public float curUpdateLookRotRate,updateLookRotRate,upDownLookRot;public Action<float> Rpc,Apply;void Rpc_CMD_UpdateLookRot(float f)=>Rpc(f);void ApplySpineRotation(float f)=>Apply(f);public void Run()=>FixedUpdate();'}
    for owner,lines in groups.items():src+='class '+owner+' : Component{'+pre[owner]+'\n'+'\n'.join(lines)+'\n}\n'
    runner=tmp_path/'runner';runner.mkdir();(runner/'Program.cs').write_text(src,encoding='utf8');print(run_case(tmp_path,runner).strip())


def test_init_arm_cannot_replace_saved_this(shift_runtime,monkeypatch):
    meta,il=shift_runtime;m=meta.methods[23765];td=meta.typedefs[m.declaring];d=Decompiler(Lifter(il));d.lift_method(m,td);bs=d.L._blocks;f=lambda:scalar_sites(d.L,m,td,bs,());assert f()[0]
    from iced_x86 import Decoder
    s=bs[1].insns;i=s[-1];seq=list(Decoder(64,bytes.fromhex('488bda')+b'\x90'*(i.len-3),ip=i.ip));monkeypatch.setattr(bs[1],'insns',s[:-1]+seq);assert not f()[0]
