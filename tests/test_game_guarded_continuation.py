"""Compile the nested iterator as emitted, preserving entry/resume effects."""
import re

import pytest
from iced_x86 import Register as R
from dotnet_case import run_case
from il2cpp import Decompiler,Lifter
from il2cpp.dispatch_fields import dispatch_fields
from il2cpp.emitter import Emitter
from test_game_shift_shared_flags import shift_runtime

pytestmark=pytest.mark.game


def emitted_move(meta,il,mid,out):
    md=meta.methods[mid];owner=meta.typedefs[il._nested_owner(md.declaring)]
    Emitter(il,str(out))._emit_one_top(owner,meta.images[md.image],owner.name)
    src=next(out.rglob(owner.name+'.cs')).read_text(encoding='utf8')
    rva=md.addr-il.bin.image_base
    return re.search(r'// RVA: 0x%X VA:[^\n]*\n( +)bool System.Collections.IEnumerator.MoveNext\(\)\n\1\{.*?^\1\}'%rva,src,re.S|re.M)[0]


def test_focus_frame_dispatch_and_receiver_lifetimes(shift_runtime,tmp_path):
    meta,il=shift_runtime;method=emitted_move(meta,il,25898,tmp_path/'out')
    src='''using System;using System.Collections;using System.Collections.Generic;using System.Linq;using UnityEngine;
foreach(var mode in new[]{"live","active","cancel in find","finder throws","current throws","button throws","select throws","null current","null controller"}){
 var a=new KwaleeEULA();var b=new KwaleeEULA();var it=new Frame{__4__this=a};IEnumerator e=it;var sentinel=it.__2__current;var err=new ApplicationException();var trace=new List<string>();
 void Step(string s){trace.Add(s);if(mode==s+" throws")throw err;}
 var first=new ControllerDisconnect();var next=new ControllerDisconnect();var selected=new GameObject();var wanted=new EventSystem();var poison=new EventSystem();int moves=0;
 UnityEngine.Object.Find=(ty,include)=>{Step("finder");if(ty!=typeof(ControllerDisconnect)||include!=FindObjectsInactive.Include||it.__1__state!=-1||!it._running_5__2)throw new Exception("lookup before init");it.__4__this=b;if(mode=="cancel in find")it._running_5__2=false;return mode=="null controller"?null:first;};
 first.Get=()=>{Step("first");return new GameObject{Active=()=>{Step("active?");return mode=="active";}};};next.Get=()=>{Step("next");return new GameObject{Active=()=>false};};
 EventSystem.Get=()=>{Step("current");var btn=new Button{Get=()=>{Step("button");EventSystem.Get=()=>poison;return selected;}};if(moves==0)a.acceptButton=btn;else b.acceptButton=btn;return mode=="null current"?null:wanted;};
 wanted.Select=o=>{Step("select");if(!ReferenceEquals(o,selected))throw new Exception("wrong button");};
 bool yielded=false;Exception fault=null;try{yielded=e.MoveNext();}catch(Exception x){fault=x;}
 var order=new[]{"finder","first","active?","current","button","select"};int n=mode switch{"active"=>3,"cancel in find" or "finder throws" or "null controller"=>1,"current throws"=>4,"button throws" or "null current"=>5,_=>6};
 if(!trace.SequenceEqual(order.Take(n))||yielded!=(mode is "live" or "active")||it.__1__state!=(yielded?1:-1)||!ReferenceEquals(e.Current,yielded?null:sentinel)||
     (mode.Contains("throws")?!ReferenceEquals(err,fault):mode.StartsWith("null")?fault is not NullReferenceException:fault!=null))throw new Exception(mode+":"+string.Join(',',trace),fault);
 if(yielded){if(!ReferenceEquals(it._controllerDisconnect_5__3,first))throw new Exception("finder result never stored");trace.Clear();moves++;it._controllerDisconnect_5__3=next;EventSystem.Get=()=>{Step("resume");b.acceptButton=new Button{Get=()=>selected};return wanted;};a.acceptButton=null;
    if(!e.MoveNext()||!trace.SequenceEqual(new[]{"next","resume","select"}))throw new Exception("stale resume owner or controller");it._running_5__2=false;it.__2__current=sentinel;if(e.MoveNext()||it.__1__state!=-1||!ReferenceEquals(e.Current,sentinel))throw new Exception("lost stop");}
 trace.Clear();if(e.MoveNext()||trace.Count!=0)throw new Exception("replayed finished frame");}
Console.WriteLine("complete focus iterator: entry/resume join, owner/button/event-system identity, yields and faults passed");
namespace UnityEngine{class Object{public static Func<Type,FindObjectsInactive,ControllerDisconnect> Find;public static T FindFirstObjectByType<T>(FindObjectsInactive f)where T:class=>(T)(object)Find(typeof(T),f);}enum FindObjectsInactive{Include=1}}
class GameObject{public Func<bool> Active;public bool activeInHierarchy=>Active();}class ControllerDisconnect{public Func<GameObject> Get;public GameObject gameObject=>Get();}class Button{public Func<GameObject> Get;public GameObject gameObject=>Get();}class EventSystem{public static Func<EventSystem> Get;public static EventSystem current=>Get();public Action<GameObject> Select;public void SetSelectedGameObject(GameObject o)=>Select(o);}class KwaleeEULA{public Button acceptButton;}
class Frame:IEnumerator{public KwaleeEULA __4__this;public int __1__state;public object __2__current=new();public bool _running_5__2;public ControllerDisconnect _controllerDisconnect_5__3;public object Current=>__2__current;public void Reset()=>throw new NotSupportedException();\n'''+method+'\n}'
    runner=tmp_path/'runner';runner.mkdir();(runner/'Program.cs').write_text(src,encoding='utf8');print(run_case(tmp_path,runner).strip())


@pytest.mark.parametrize('change',['wrong owner slot','wrong base','not an entry/resume test','collapsed resume edge'])
def test_dispatch_capture_requires_state_and_owner(shift_runtime,monkeypatch,change):
    meta,il=shift_runtime;d=Decompiler(Lifter(il));md=meta.methods[25898];d.lift_method(md,meta.typedefs[md.declaring]);bs=d.L._blocks
    plan=lambda:dispatch_fields(d.L,md,bs,());reads=plan();assert len(reads)==2
    a,z=sorted(reads);b,j=next((b,j) for b in bs for j,i in enumerate(b.insns) if i.ip==z)
    if change=='wrong base':
        seq=list(b.insns)
        for k in (j-1,j):
            seq[k]=seq[k].copy();seq[k].memory_base=R.R12
        monkeypatch.setattr(b,'insns',seq);assert not plan();return
    if change=='not an entry/resume test':j+=1
    if change=='collapsed resume edge':
        dest=b.insns[-1].near_branch_target;b=next(b for b in bs if b.insns[0].ip==dest);j=1
    i=b.insns[j].copy()
    if change=='collapsed resume edge':i.near_branch64=i.next_ip
    elif change=='wrong owner slot':i.memory_displacement=0x30
    else:i.op0_register=R.EDI
    monkeypatch.setattr(b,'insns',b.insns[:j]+[i]+b.insns[j+1:]);assert not plan()
