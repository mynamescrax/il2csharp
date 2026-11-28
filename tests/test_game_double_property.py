import pytest
from dotnet_case import run_case
from il2cpp.emitter import Emitter
from test_game_shift_shared_flags import shift_runtime

pytestmark=pytest.mark.game


def test_menu_selection_reacquires_current_after_saving_old_selection(shift_runtime,tmp_path):
    meta,il=shift_runtime;m=meta.methods[26552];out=[];Emitter(il,str(tmp_path/'out')).emit_method(m,meta.typedefs[m.declaring],out,'    ')
    src='''using System;using System.Linq;using System.Collections.Generic;using UnityEngine;using UnityEngine.EventSystems;
foreach(string mode in new[]{"ok","first","null first","old","second","null second","select","null choice"}){
 var c=new PauseMenu();var previous=c.oldSelectedObj=new GameObject();var next=new GameObject();var current=new GameObject();var a=new EventSystem();var b=new EventSystem();var err=new ApplicationException();var log=new List<string>();void Step(string s){log.Add(s);if(s==mode)throw err;}
 EventSystem.Read=()=>{Step("first");return mode=="null first"?null:a;};a.Selected=()=>{Step("old");EventSystem.Read=()=>{if(!ReferenceEquals(c.oldSelectedObj,current))throw new Exception("second read before store");Step("second");return mode=="null second"?null:b;};return current;};a.Select=_=>throw new Exception("stale current");b.Select=o=>{if(!ReferenceEquals(o,mode=="null choice"?null:next)||c.inSubMenu)throw new Exception("wrong choice/order");Step("select");};
 Exception ex=null;try{c.Run(mode=="null choice"?null:next);}catch(Exception e){ex=e;}string[] seq={"first","old","second","select"};bool ok=mode is "ok" or "null choice";int n=mode switch{"null first"=>1,"null second"=>3,_=>ok?4:Array.IndexOf(seq,mode)+1};
 if(!log.SequenceEqual(seq.Take(n))||c.inSubMenu!=ok||!ReferenceEquals(c.oldSelectedObj,n<3?previous:current)||(ok?ex!=null:mode.StartsWith("null")?ex is not NullReferenceException:!ReferenceEquals(ex,err)))throw new Exception(mode+":"+string.Join(',',log),ex);
}
Console.WriteLine("whole menu choice: store old selection, reacquire current, select once and mark submenu last");
namespace UnityEngine{public class GameObject{}}namespace UnityEngine.EventSystems{public class EventSystem{public static Func<EventSystem> Read;public static EventSystem current=>Read();public Func<GameObject> Selected;public GameObject currentSelectedGameObject=>Selected();public Action<GameObject> Select;public void SetSelectedGameObject(GameObject o)=>Select(o);}}
class PauseMenu{public GameObject oldSelectedObj;public bool inSubMenu;public void Run(GameObject next)=>OnMenuOptionSelected(next);\n'''+ '\n'.join(out)+'\n}'
    r=tmp_path/'r';r.mkdir();(r/'Program.cs').write_text(src,encoding='utf8');print(run_case(tmp_path,r))


@pytest.mark.parametrize('bad',['wrong ref field','other slot address','wrong source','other getter','wrong flag width','stale receiver'])
def test_double_acquisition_requires_the_original_field_write(shift_runtime,bad):
    from il2cpp import Decompiler,Lifter
    from il2cpp.double_property import reacquired_after_store
    from iced_x86 import Register as R
    meta,il=shift_runtime;m=meta.methods[26552];td=meta.typedefs[m.declaring];d=Decompiler(Lifter(il));il.eh_regions(m.addr);s,_=d._decode(m);match=lambda:reacquired_after_store(d.L,m,td,s,None);assert match()
    ip={'wrong ref field':0x180581afd,'other slot address':0x180581b01,'wrong source':0x180581b05,'other getter':0x180581b10,'wrong flag width':0x180581b28,'stale receiver':0x180581b20}[bad];j=next(j for j,i in enumerate(s) if i.ip==ip);i=s[j].copy()
    if bad in ('wrong ref field','other slot address','wrong flag width'):i.memory_displacement+=3
    elif bad=='wrong source':i.op1_register=R.RAX
    elif bad=='stale receiver':i.op1_register=R.RBX
    else:i.near_branch64=0x182bf1bb0
    s[j]=i;assert not match()
