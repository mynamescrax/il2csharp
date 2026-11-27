import pytest
from dotnet_case import run_case
from il2cpp import Decompiler,Lifter
from il2cpp.emitter import Emitter
from il2cpp.inline_static_guard import checked_statics
from test_game_shift_shared_flags import shift_runtime

pytestmark=pytest.mark.game


def test_complete_event_callbacks_reacquire_public_singletons(shift_runtime,tmp_path):
    meta,il=shift_runtime;em=Emitter(il,str(tmp_path/'out'));groups={}
    for j in (24841,24842,24843,25356):
        md=meta.methods[j];td=meta.typedefs[md.declaring];em.emit_method(md,td,groups.setdefault(td.name,[]),'    ')
    src='''using System;using System.Collections.Generic;using System.Linq;using UnityEngine;
var trigger=new DelayedEventTrigger();var forest=new ForestLimbsEvent();foreach(string which in new[]{"run","walk","ambient","forest"})foreach(string mode in new[]{"ok","read fault","null","action fault","forest null","set fault"}){
 var trace=new List<string>();var ex=new ApplicationException();var mgr=new StoreManager();var ambient=new AmbientMusicSystem();var late=new GameObject();forest.forestObjects=null;
 void Step(string s){trace.Add(s);if(mode==s+" fault")throw ex;}
 StoreManager.Fetch=()=>{Step("read");return mode=="null"?null:mgr;};AmbientMusicSystem.Fetch=()=>{Step("read");return mode=="null"?null:ambient;};
 mgr.Act=s=>{Step("action");if(s!=which)throw new Exception("wrong manager dispatch");forest.forestObjects=mode=="forest null"?null:late;};late.Put=b=>{if(!b)throw new Exception();Step("set");};
 Exception fault=null;try{if(which=="forest")forest.Run();else trigger.Run(which);}catch(Exception e){fault=e;}
 bool nre=mode=="null"||which=="forest"&&mode=="forest null";bool error=mode=="read fault"||mode=="action fault"&&which!="ambient"||mode=="set fault"&&which=="forest";
 string want=which=="ambient"||mode is "read fault" or "null"?"read":which=="forest"&&mode!="action fault"&&mode!="forest null"?"read,action,set":"read,action";
 if(string.Join(',',trace)!=want||(nre?fault is not NullReferenceException:error?!ReferenceEquals(fault,ex):fault!=null)||ambient.pauseAmbience!=(which=="ambient"&&!error&&!nre))throw new Exception(which+"/"+mode+":"+string.Join(',',trace),fault);}
Console.WriteLine("four complete callbacks: fresh singleton reads, distinct NPC actions, ambience and post-objective forest reload passed");
public class StoreManager{public static Func<StoreManager> Fetch;public static StoreManager Instance=>Fetch();public Action<string> Act;public void AllBrowsingNPCsRunAway()=>Act("run");public void AllBrowsingNPCsWalkAway()=>Act("walk");public void NewObjective(string s,string t){if(s!="Objectives"||t!="Head to the Forest")throw new Exception();Act("forest");}}
public class AmbientMusicSystem{public static Func<AmbientMusicSystem> Fetch;public static AmbientMusicSystem Instance=>Fetch();public bool pauseAmbience;}
namespace UnityEngine{public class GameObject{public Action<bool> Put;public void SetActive(bool b)=>Put(b);}}
class DelayedEventTrigger{public void Run(string s){if(s=="run")NPCsRunAway();else if(s=="walk")NPCsWalkAway();else PauseAmbience();}\n'''+ '\n'.join(groups['DelayedEventTrigger'])+'\n}class ForestLimbsEvent{public GameObject forestObjects;public void Run()=>OnEnable();\n'+'\n'.join(groups['ForestLimbsEvent'])+'\n}'
    runner=tmp_path/'runner';runner.mkdir();(runner/'Program.cs').write_text(src,encoding='utf8');print(run_case(tmp_path,runner).strip())


@pytest.mark.parametrize('change',['guard slot','different store flag','overlapping getter flag','no registration'])
def test_singleton_guard_requires_same_usage_and_pure_closed_getter(shift_runtime,monkeypatch,change):
    meta,il=shift_runtime;m=meta.methods[24842];d=Decompiler(Lifter(il));d.lift_method(m,meta.typedefs[m.declaring]);bs=d.L._blocks
    plan=lambda:checked_statics(d.L,m,bs,());assert len(plan())==1;getter=0x1805e2d40;slot=0x183c1c748
    if change=='no registration':monkeypatch.setitem(il.addr_candidates,getter,[])
    elif change=='overlapping getter flag':
        orig=il.bin.read;monkeypatch.setattr(il.bin,'read',lambda addr,n:(slot-getter-11).to_bytes(4,'little',signed=True) if addr==getter+6 and n==4 else orig(addr,n))
    else:
        b=bs[1];j=0 if change=='guard slot' else 2;i=b.insns[j].copy();i.memory_displacement+=8;monkeypatch.setattr(b,'insns',b.insns[:j]+[i]+b.insns[j+1:])
    assert not plan()
