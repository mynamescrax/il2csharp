import pytest
from iced_x86 import Register as R
from dotnet_case import run_case
from il2cpp import Decompiler,Lifter
from il2cpp.emitter import Emitter
from il2cpp.saved_ref import parked_properties
from test_game_shift_shared_flags import shift_runtime

pytestmark=pytest.mark.game


def test_computer_selects_on_second_current_system(shift_runtime,tmp_path):
    meta,il=shift_runtime;m=meta.methods[24607];lines=[];Emitter(il,str(tmp_path/'out')).emit_method(m,meta.typedefs[m.declaring],lines,'    ')
    src='''using System;using System.Collections.Generic;using System.Linq;using UnityEngine;using UnityEngine.EventSystems;
foreach(string mode in new[]{"skip","no text","no player","no system","scheme","live","second null","argument null","scheme fault","second fault","argument fault","select fault"}){
 var c=new Computer{interacting=mode!="skip"};var a=new EventSystem();var b=new EventSystem();var input=new InputText();var trigger=new PlayerInput();var actual=new PlayerInput();var selected=new InputText();var go=new GameObject();var log=new List<string>();var boom=new ApplicationException();
 void Step(string s){log.Add(s);if(mode==s+" fault")throw boom;}c.inputText=input;c.playerInput=trigger;
 UnityEngine.Object.Eq=(o,n)=>{if(n is not null)throw new Exception();if(ReferenceEquals(o,input)){Step("text?");return mode=="no text";}if(ReferenceEquals(o,trigger)){Step("player?");return mode=="no player";}if(!ReferenceEquals(o,a))throw new Exception("wrong checked receiver");Step("system?");c.playerInput=actual;return mode=="no system";};
 actual.Scheme=()=>{Step("scheme");return mode=="scheme"?"Mouse":new string("Gamepad".ToCharArray());};int reads=0;EventSystem.Read=()=>{if(++reads==1){Step("first");return a;}Step("second");c.inputText=mode=="argument null"?null:selected;return mode=="second null"?null:b;};
 selected.Read=()=>{Step("argument");EventSystem.Read=()=>throw new Exception("replayed current");return go;};b.Select=o=>{Step("select");if(!ReferenceEquals(o,go))throw new Exception();};Exception f=null;try{c.Fire();}catch(Exception e){f=e;}
 var order=new[]{"text?","player?","first","system?","scheme","second","argument","select"};int n=mode switch{"skip"=>0,"no text"=>1,"no player"=>2,"no system"=>4,"scheme" or "scheme fault"=>5,"second fault" or "argument null"=>6,"argument fault" or "second null"=>7,_=>8};
 if(!log.SequenceEqual(order.Take(n))||(mode.EndsWith(" fault")?!ReferenceEquals(boom,f):mode.EndsWith(" null")?f is not NullReferenceException:f!=null))throw new Exception(mode+":"+string.Join(',',log),f);}
Console.WriteLine("whole computer input selection: checked first system, selected on second, gamepad value equality and fault cutoffs passed");
namespace UnityEngine{public class Object{public static Func<Object,Object,bool> Eq;public static bool operator ==(Object a,Object b)=>Eq(a,b);public static bool operator !=(Object a,Object b)=>!Eq(a,b);public override bool Equals(object o)=>ReferenceEquals(this,o);public override int GetHashCode()=>base.GetHashCode();}public class GameObject:Object{}}
namespace UnityEngine.EventSystems{public class EventSystem:UnityEngine.Object{public static Func<EventSystem> Read;public static EventSystem current=>Read();public Action<GameObject> Select;public void SetSelectedGameObject(GameObject o)=>Select(o);}}
class InputText:UnityEngine.Object{public Func<GameObject> Read;public GameObject gameObject=>Read();}class PlayerInput:UnityEngine.Object{public Func<string> Scheme;public string currentControlScheme=>Scheme();}
class Computer{public bool interacting;public InputText inputText;public PlayerInput playerInput;public void Fire()=>ActuallySelectInputText();\n'''+ '\n'.join(lines)+'\n}'
    runner=tmp_path/'runner';runner.mkdir();(runner/'Program.cs').write_text(src,encoding='utf8');print(run_case(tmp_path,runner).strip())


@pytest.mark.parametrize('change',['wrong saved register','wrong hidden slot','ambiguous target'])
def test_parked_property_requires_abi_and_registered_result(shift_runtime,monkeypatch,change):
    meta,il=shift_runtime;md=meta.methods[24607];d=Decompiler(Lifter(il));d.lift_method(md,meta.typedefs[md.declaring]);bs=d.L._blocks
    plan=lambda:parked_properties(d.L,md,bs,());a,b=sorted(plan())
    if change=='ambiguous target':monkeypatch.setitem(il.addr_candidates,0x182f78bb0,[('method',112180),('method',112181)])
    else:
        block,j=next((block,j) for block in bs for j,i in enumerate(block.insns) if i.ip==b);j+=2 if change=='wrong saved register' else -1;i=block.insns[j].copy()
        if change=='wrong saved register':i.op1_register=R.RDX
        else:i.op0_register=i.op1_register=R.EDX
        monkeypatch.setattr(block,'insns',block.insns[:j]+[i]+block.insns[j+1:])
    assert b not in plan()
