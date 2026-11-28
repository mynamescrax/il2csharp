import pytest
from dotnet_case import run_case
from il2cpp.emitter import Emitter
from test_game_shift_shared_flags import shift_runtime

pytestmark=pytest.mark.game


def test_puzzle_peg_captures_placement_target_then_reloads_current_slot(shift_runtime,tmp_path):
    meta,il=shift_runtime;m=meta.methods[24017];out=[];Emitter(il,str(tmp_path/'out')).emit_method(m,meta.typedefs[m.declaring],out,'    ')
    src='''using System;using System.Linq;using System.Collections.Generic;using UnityEngine;using Obi;
foreach(string mode in new[]{"ok","destroyed","body","obi","collider","ignore","truth","dest","no dest","slot","no source","get","both fault","set"}){
 var c=new TangledPeg();var first=c.currentSlot=new TangledPegSlot();var second=new TangledPegSlot();var body=new Rigidbody();var obi=new ObiRigidbody();var coll=new Collider();var dest=new Transform();var source=new Transform();var floor=c.floorCollider=new Collider();var log=new List<string>();var err=new ApplicationException();
 void Step(string s){log.Add(s);if(mode==s)throw err;}c.Lookup=t=>{if(t==typeof(Rigidbody)){Step("body");return body;}if(t==typeof(ObiRigidbody)){if(c.__field_rb is null)throw new Exception();Step("obi");return obi;}if(t!=typeof(Collider)||c.__field_orb is null)throw new Exception();Step("collider");return coll;};Physics.Ignore=(a,b)=>{if(!ReferenceEquals(a,coll)||!ReferenceEquals(b,floor))throw new Exception();Step("ignore");};
 UnityEngine.Object.Compare=(a,b)=>{if(!ReferenceEquals(a,first)||b is not null)throw new Exception();Step("truth");return mode!="destroyed";};
 c.Tr=()=>{if(!ReferenceEquals(first.currentPeg,c)||second.currentPeg is not null)throw new Exception("backlink not set");Step("dest");c.currentSlot=second;return mode is "no dest" or "both fault"?null:dest;};first.Tr=()=>throw new Exception("getter on stale slot");second.Tr=()=>{Step("slot");return mode=="no source"?null:source;};
 var pos=new Vector3{x=1.5f,y=-0f,z=-13f};source.Get=()=>{Step("get");if(mode=="both fault")throw err;return pos;};dest.Set=v=>{if(v.x!=pos.x||v.z!=pos.z||BitConverter.SingleToInt32Bits(v.y)!=BitConverter.SingleToInt32Bits(pos.y))throw new Exception();Step("set");};
 Exception ex=null;try{c.Run();}catch(Exception e){ex=e;}string[] order={"body","obi","collider","ignore","truth","dest","slot","get","set"};int p=Array.IndexOf(order,mode);int n=mode switch{"destroyed"=>5,"no dest" or "both fault"=>8,"no source"=>7,"ok"=>9,_=>p+1};
 if(!log.SequenceEqual(order.Take(n))||(p>=0||mode=="both fault"?!ReferenceEquals(err,ex):mode.StartsWith("no ")?ex is not NullReferenceException:ex!=null))throw new Exception(mode+":"+string.Join(',',log),ex);
}
Console.WriteLine("whole peg placement: component lookups and collision setup, saved destination, later slot reload, deferred null fault");
namespace UnityEngine{public struct Vector3{public float x,y,z;}public class Object{public static Func<Object,Object,bool> Compare;public static bool operator !=(Object a,Object b)=>Compare(a,b);public static bool operator ==(Object a,Object b)=>!Compare(a,b);public override bool Equals(object o)=>ReferenceEquals(this,o);public override int GetHashCode()=>base.GetHashCode();}public class Component:Object{public Func<Type,Component> Lookup;public T GetComponent<T>() where T:Component=>(T)Lookup(typeof(T));public Func<Transform> Tr;public Transform transform=>Tr();}public class Rigidbody:Component{}public class Collider:Component{}public class Transform:Component{public Func<Vector3> Get;public Action<Vector3> Set;public Vector3 position{get=>Get();set=>Set(value);}}public static class Physics{public static Action<Collider,Collider> Ignore;public static void IgnoreCollision(Collider a,Collider b)=>Ignore(a,b);}}
namespace Obi{public class ObiRigidbody:Component{}}class TangledPegSlot:Component{public TangledPeg currentPeg;}class TangledPeg:Component{public Collider floorCollider;public TangledPegSlot currentSlot;public Rigidbody __field_rb;public ObiRigidbody __field_orb;public void Run()=>Awake();\n'''+ '\n'.join(out)+'\n}'
    r=tmp_path/'r';r.mkdir();(r/'Program.cs').write_text(src,encoding='utf8');print(run_case(tmp_path,r))


def test_snap_back_checked_destination_slice(shift_runtime,tmp_path):
    from il2cpp import Lifter,Decompiler
    meta,il=shift_runtime;m=meta.methods[25847];d=Decompiler(Lifter(il));body=d.lift_method(m,meta.typedefs[m.declaring]);start=next(j for j,q in enumerate(body) if q.lstrip().startswith('if ('));end=next(j for j,q in enumerate(body[start+1:],start+1) if q=='}')
    src='''using System;using System.Collections.Generic;using System.Linq;using UnityEngine;
foreach(string mode in new[]{"ok","dead","truth","dest","no dest","get","set","null source"}){
 var c=new Caller();var original=c.snapBackToPosition=new Transform();var p=new Transform();var d=new Transform();var err=new ApplicationException();var trace=new List<string>();void Step(string s){trace.Add(s);if(mode==s)throw err;}
 UnityEngine.Object.Truth=o=>{if(!ReferenceEquals(o,original))throw new Exception();Step("truth");return mode!="dead";};c.Fetch=()=>{Step("dest");c.snapBackToPosition=mode=="null source"?null:p;return mode=="no dest"?null:d;};p.Read=()=>{Step("get");return new Vector3{x=-1,y=2,z=-3};};d.Write=v=>{if(v.x!=-1||v.y!=2||v.z!=-3)throw new Exception();Step("set");};
 Exception ex=null;try{c.Run();}catch(Exception e){ex=e;}string[] ops={"truth","dest","get","set"};int n=mode switch{"dead"=>1,"ok"=>4,"no dest"=>3,"null source"=>2,_=>Array.IndexOf(ops,mode)+1};if(!trace.SequenceEqual(ops.Take(n))||(mode is "null source" or "no dest"?ex is not NullReferenceException:mode is "dead" or "ok"?ex!=null:!ReferenceEquals(ex,err)))throw new Exception(mode+":"+string.Join(',',trace),ex);
}
Console.WriteLine("snap-back copy slice snapshots destination before source");namespace UnityEngine{public class Object{public static Func<Object,bool> Truth;public static implicit operator bool(Object x)=>Truth(x);}public class Transform:Object{public Func<Vector3> Read;public Action<Vector3> Write;public Vector3 position{get=>Read();set=>Write(value);}}public struct Vector3{public float x,y,z;}}
class Caller{public Transform snapBackToPosition;public Func<Transform> Fetch;public Transform transform=>Fetch();public void Run(){\n'''+ '\n'.join(body[start:end+1])+'\n}}'
    r=tmp_path/'r';r.mkdir();(r/'Program.cs').write_text(src,encoding='utf8');print(run_case(tmp_path,r))


@pytest.mark.parametrize('bad',['other receiver','other saved reg','different setter','unknown getter'])
def test_destination_is_the_parked_getter_result(shift_runtime,monkeypatch,bad):
    from il2cpp import Lifter,Decompiler
    from il2cpp.parked_destination import destination_reads
    from iced_x86 import Register as R
    meta,il=shift_runtime;m=meta.methods[24017];td=meta.typedefs[m.declaring];d=Decompiler(Lifter(il));d.lift_method(m,td);bs=d.L._blocks
    scan=lambda:destination_reads(d.L,m,td,bs,());site=0x180525f6d;assert set(scan())=={site};ip={'other receiver':0x180525fae,'other saved reg':0x180525f76,'different setter':0x180525fbb,'unknown getter':site}[bad]
    b,j=next((b,j) for b in bs for j,i in enumerate(b.insns) if i.ip==ip);i=b.insns[j].copy()
    if bad=='other receiver':i.op1_register=R.RBX
    elif bad=='other saved reg':i.op0_register=R.RSI
    else:i.near_branch64=0x182bf1bb0
    monkeypatch.setattr(b,'insns',b.insns[:j]+[i]+b.insns[j+1:]);assert not scan()
