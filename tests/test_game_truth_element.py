import pytest
from dotnet_case import run_case
from il2cpp.emitter import Emitter
from test_game_shift_shared_flags import shift_runtime

pytestmark=pytest.mark.game


def test_switch_and_death_loop_act_on_the_object_that_passed_the_check(shift_runtime,tmp_path):
    meta,il=shift_runtime;em=Emitter(il,str(tmp_path/'out'));bodies=[]
    for mi in (26532,27034):
        m=meta.methods[mi];lines=[];em.emit_method(m,meta.typedefs[m.declaring],lines,'    ');bodies.append('\n'.join(lines))
    src='''using System;using System.Collections.Generic;using System.Linq;using UnityEngine;
foreach(string mode in new[]{"ok","skip","first check","on","second check","off","event","null enable","null disable"}){
 var c=new NodeSwitch();var a=new GameObject();var b=new GameObject();var y=new GameObject();var dropped=new GameObject();var poison=new GameObject();var trace=new List<string>();var err=new ApplicationException();
 GameObject[] enable={a,dropped},disable={y};c.enableNodes=mode=="null enable"?null:enable;c.disableNodes=null;
 void Step(string s){trace.Add(s);if(mode==s)throw err;}
 UnityEngine.Object.Check=o=>{if(ReferenceEquals(o,a)){Step("first check");enable[0]=poison;enable[1]=b;c.enableNodes=Array.Empty<GameObject>();c.disableNodes=mode=="null disable"?null:disable;return mode!="skip";}
   if(ReferenceEquals(o,b)){Step("later");return false;}if(ReferenceEquals(o,y)){Step("second check");disable[0]=poison;return true;}throw new Exception("stale array element");};
 a.Act=v=>{if(!v)throw new Exception();Step("on");};y.Act=v=>{if(v)throw new Exception();Step("off");};poison.Act=v=>throw new Exception("checked one object and acted on another");c.nodeTriggerEvent=()=>Step("event");
 Exception fault=null;try{c.Run();}catch(Exception e){fault=e;}var want=new List<string>{"first check"};if(mode!="skip")want.Add("on");want.AddRange(new[]{"later","second check","off","event"});int count=mode switch{"null enable"=>0,"null disable"=>want.IndexOf("second check"),_=>want.Contains(mode)?want.IndexOf(mode)+1:want.Count};
 if(!trace.SequenceEqual(want.Take(count))||(mode.StartsWith("null")?fault is not NullReferenceException:want.Contains(mode)?!ReferenceEquals(err,fault):fault!=null))throw new Exception(mode+":"+string.Join(',',trace),fault);
}
foreach(string mode in new[]{"ok","already","check","fade","path","null array","null replacement"}){
 var c=new RegularBrowsingNPC{startedFadingAway=mode=="already"};var a=new MaterialFader();var other=new MaterialFader();var old=new Pathfinder();var fresh=new Pathfinder();c.pathfinder=old;var slots=new[]{a};c.matFaders=mode=="null array"?null:slots;var trace=new List<string>();var ex=new ApplicationException();
 void Step(string s){trace.Add(s);if(mode==s)throw ex;}
 UnityEngine.Object.Check=o=>{if(ReferenceEquals(o,a)){Step("check");slots[0]=other;c.matFaders=null;return true;}if(!ReferenceEquals(o,old))throw new Exception();Step("path");c.pathfinder=mode=="null replacement"?null:fresh;return true;};
 a.Fade=v=>{if(v!=.2f||c.startedFadingAway)throw new Exception();Step("fade");};old.maxSpeed=5;fresh.maxSpeed=6;Exception fault=null;try{c.Run();}catch(Exception e){fault=e;}
 var wanted=mode switch{"null array"=>"","already"=>"path","check"=>"check","fade"=>"check,fade",_=>"check,fade,path"};
 if(string.Join(',',trace)!=wanted||c.startedFadingAway!=(mode is not ("check" or "fade" or "null array"))||old.maxSpeed!=5||fresh.maxSpeed!=(mode is "ok" or "already"?0f:6f)||
   (mode.StartsWith("null")?fault is not NullReferenceException:mode is "check" or "fade" or "path"?!ReferenceEquals(fault,ex):fault!=null))throw new Exception(mode+":"+string.Join(',',trace),fault);
}
Console.WriteLine("two complete loops: retained checked element, fresh later elements, wrong-reload control, event and fault order");
namespace UnityEngine{public class Object{public static Func<Object,bool> Check;public static implicit operator bool(Object a)=>Check(a);}public class GameObject:Object{public Action<bool> Act;public void SetActive(bool b)=>Act(b);}}
class MaterialFader:UnityEngine.Object{public Action<float> Fade;public void PlayFadeOut(float v)=>Fade(v);}class Pathfinder:UnityEngine.Object{public float maxSpeed;}
class NodeSwitch{public GameObject[] enableNodes,disableNodes;public Action nodeTriggerEvent;public void Run()=>TriggerSwitchLocal();\n'''+bodies[0]+'\n}class RegularBrowsingNPC{public MaterialFader[] matFaders;public bool startedFadingAway;public Pathfinder pathfinder;public void Run()=>Die();\n'+bodies[1]+'\n}'
    r=tmp_path/'r';r.mkdir();(r/'Program.cs').write_text(src,encoding='utf8');print(run_case(tmp_path,r))


@pytest.mark.parametrize('bad',['wrong stride','wrong index','other receiver','not the guarded source','wrong handler','signed bounds'])
def test_checked_action_declines_wrong_element_or_reaching_register(shift_runtime,monkeypatch,bad):
    from il2cpp import Decompiler,Lifter
    from il2cpp.truth_element import checked_elements
    from iced_x86 import Register as R,Decoder
    meta,il=shift_runtime;m=meta.methods[26532];td=meta.typedefs[m.declaring];d=Decompiler(Lifter(il));d.lift_method(m,td);bs=d.L._blocks
    def plans():return checked_elements(d.L,m,td,bs,())[1]
    first=0x180580d78;second=0x180580de1;assert set(plans())=={first,second}
    ip={'wrong stride':first,'wrong index':first,'other receiver':0x180580da6,'not the guarded source':0x180580d8c,'wrong handler':0x180580d68,'signed bounds':0x180580d68}[bad]
    b,j=next((b,j) for b in bs for j,i in enumerate(b.insns) if i.ip==ip);i=b.insns[j].copy()
    if bad=='wrong stride':i.memory_index_scale=4
    elif bad=='wrong index':i.memory_index=R.RDI
    elif bad in ('other receiver','not the guarded source'):i.op1_register=R.RBX
    elif bad=='wrong handler':i.near_branch64=0x180580e40
    else:
        raw=bytearray(il.bin.read(ip,i.len));assert raw[:2]==b'\x0f\x83';raw[1]=0x8d;i=Decoder(64,raw,ip=ip).decode()
    monkeypatch.setattr(b,'insns',b.insns[:j]+[i]+b.insns[j+1:]);got=plans();assert first not in got and second in got
