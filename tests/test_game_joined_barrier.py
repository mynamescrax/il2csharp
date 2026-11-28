import pytest
from dotnet_case import run_case
from il2cpp.emitter import Emitter
from test_game_shift_shared_flags import shift_runtime

pytestmark=pytest.mark.game


def test_listener_refresh_stores_only_the_one_getter_result(shift_runtime,tmp_path):
    meta,il=shift_runtime;m=meta.methods[23684];lines=[];Emitter(il,str(tmp_path/'out')).emit_method(m,meta.typedefs[m.declaring],lines,'    ')
    prog='''using System;using System.Linq;using System.Collections.Generic;using UnityEngine;
foreach(string mode in new[]{"ok","null camera","destroyed camera","null game","inactive","null listener","destroyed listener","disabled","null transform","main","camera equality","game","activity","lookup","listener truth","enabled","transform"}){
 var c=new DistanceFade2DAudio();var seed=new Transform();var result=new Transform();c.listenerTransform=seed;var cam=new Camera();var go=new GameObject();var listener=new AudioListener();var trace=new List<string>();var err=new ApplicationException();
 void Step(string s){trace.Add(s);if(mode==s)throw err;}
 Camera.Main=()=>{Step("main");return mode=="null camera"?null:cam;};UnityEngine.Object.Equal=(a,b)=>{if(b is not null||!ReferenceEquals(a,mode=="null camera"?null:cam))throw new Exception();Step("camera equality");return a is null||mode=="destroyed camera";};
 cam.Game=()=>{Step("game");return mode=="null game"?null:go;};go.Active=()=>{Step("activity");return mode!="inactive";};cam.Lookup=t=>{if(t!=typeof(AudioListener))throw new Exception("wrong generic lookup");Step("lookup");return mode=="null listener"?null:listener;};
 UnityEngine.Object.NotEqual=(a,b)=>{if(b is not null||!ReferenceEquals(a,mode=="null listener"?null:listener))throw new Exception();Step("listener truth");return a is not null&&mode!="destroyed listener";};listener.IsEnabled=()=>{Step("enabled");return mode!="disabled";};listener.Get=()=>{Step("transform");listener.Get=()=>throw new Exception("second transform read");return mode=="null transform"?null:result;};
 Exception ex=null;try{c.Run();}catch(Exception e){ex=e;}
 string[] order={"main","camera equality","game","activity","lookup","listener truth","enabled","transform"};int at=Array.IndexOf(order,mode);int n=mode switch{"null camera" or "destroyed camera"=>2,"null game"=>3,"inactive"=>4,"null listener" or "destroyed listener"=>6,"disabled"=>7,_=>at<0?8:at+1};
 if(!trace.SequenceEqual(order.Take(n))||(mode=="null game"?ex is not NullReferenceException:at<0?ex!=null:!ReferenceEquals(err,ex))||!ReferenceEquals(c.listenerTransform,ex!=null?seed:mode=="ok"?result:null))throw new Exception(mode+":"+string.Join(',',trace),ex);
}
Console.WriteLine("whole listener refresh: conditional clear, one transform getter, earlier field preserved on every throwing callback");
namespace UnityEngine{public class Object{public static Func<Object,Object,bool> Equal,NotEqual;public static bool operator ==(Object a,Object b)=>Equal(a,b);public static bool operator !=(Object a,Object b)=>NotEqual(a,b);public override bool Equals(object o)=>ReferenceEquals(this,o);public override int GetHashCode()=>base.GetHashCode();}public class Component:Object{public Func<Type,Component> Lookup;public T GetComponent<T>() where T:Component=>(T)Lookup(typeof(T));public Func<GameObject> Game;public GameObject gameObject=>Game();public Func<Transform> Get;public Transform transform=>Get();}public class Transform:Component{}public class GameObject:Object{public Func<bool> Active;public bool activeInHierarchy=>Active();}public class Camera:Component{public static Func<Camera> Main;public static Camera main=>Main();}public class AudioListener:Component{public Func<bool> IsEnabled;public bool enabled=>IsEnabled();}}
class DistanceFade2DAudio{public Transform listenerTransform;public void Run()=>RefreshListenerFromCameraManager();\n'''+ '\n'.join(lines)+'\n}'
    r=tmp_path/'r';r.mkdir();(r/'Program.cs').write_text(prog,encoding='utf8');print(run_case(tmp_path,r))


@pytest.mark.parametrize('bad',['different destination','different base','different value','no store on miss','restore wrong slot','unrelated helper'])
def test_common_barrier_requires_the_same_actual_store_on_both_paths(shift_runtime,monkeypatch,bad):
    from il2cpp import Decompiler,Lifter
    from il2cpp.joined_barrier import joined_marks
    from iced_x86 import Register as R
    meta,il=shift_runtime;m=meta.methods[23684];td=meta.typedefs[m.declaring];d=Decompiler(Lifter(il));d.lift_method(m,td);bs=d.L._blocks;find=lambda:joined_marks(d.L,m,td,bs,())[0]
    assert 0x180507d15 in find();ip={'different destination':0x180507cf8,'different base':0x180507d03,'different value':0x180507cfc,'no store on miss':0x180507ca1,'restore wrong slot':0x180507d0b,'unrelated helper':0x180507d15}[bad]
    b,j=next((b,j) for b in bs for j,i in enumerate(b.insns) if i.ip==ip);i=b.insns[j].copy()
    if bad in ('different destination','restore wrong slot'):i.memory_displacement+=8
    elif bad=='different base':i.memory_base=R.RDI
    elif bad=='different value':i.op1_register=R.RDI
    elif bad=='no store on miss':i.near_branch64=0x180507d07
    else:i.near_branch64=0x1804fe6e0
    monkeypatch.setattr(b,'insns',b.insns[:j]+[i]+b.insns[j+1:]);assert not find()
