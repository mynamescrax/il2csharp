import pytest
from dotnet_case import run_case
from il2cpp.emitter import Emitter
from test_game_shift_shared_flags import shift_runtime

pytestmark=pytest.mark.game


def test_closed_factories_capture_prefab_then_position_and_rotation(shift_runtime,tmp_path):
    meta,il=shift_runtime;em=Emitter(il,str(tmp_path/'out'));shells=[]
    for mi,field in ((25117,'voiceManagerObj'),(27086,'instantiateObj'),(24066,'increaseNuisanceParticle')):
        m=meta.methods[mi];td=meta.typedefs[m.declaring];out=[];em.emit_method(m,td,out,'    ')
        shells.append('class '+td.name+' : Base {public GameObject '+field+';public override void Set(GameObject x)=>this.'+field+'=x;public override void Run()=>'+m.name+'();\n'+'\n'.join(out)+'\n}')
    src='''using System;using System.Collections.Generic;using System.Linq;using System.Reflection;using System.Runtime.Loader;using UnityEngine;
foreach(var k in new[]{0,1,2})foreach(var mode in new[]{"ok","null original","transform","null transform","position","zero","identity","cctor","factory"}){
 if(k==0 && mode is "null transform" or "transform" or "position" || k!=0 && mode=="zero")continue;
 var alc=new AssemblyLoadContext("isolated",isCollectible:true);try {var asm=alc.LoadFromAssemblyPath(typeof(Case).Assembly.Location);asm.GetType("Case").GetMethod("Test").Invoke(null,new object[]{k,mode});}finally{alc.Unload();}
}
Console.WriteLine("closed factories: original reference and all 7 float lanes, getter count/order, exact initialization and callback faults");
public static class Case{
 public static List<string> Trace=new();public static Exception Fail=new ApplicationException();public static string Mode;
 public static void Step(string s){Trace.Add(s);if(Mode==s)throw Fail;}
 public static void Test(int k,string mode){
  Mode=mode;Base c=k==0?new EndingScene():k==1?new RemoteTrap():new NuisanceCustomer();var t=new Transform();
  // The null-original case leaves the real static constructor pending.
  // Ordinary cases create a Unity object first; any class initializer from
  // object creation is independent of the observed caller.
  bool cold=mode is "null original" or "cctor";GameObject a=null,b=null;if(!cold){a=new GameObject();b=new GameObject();}Trace.Clear();c.Set(a);
  float F(uint x)=>BitConverter.Int32BitsToSingle(unchecked((int)x));var pos=new Vector3{x=F(0x80000000),y=F(1),z=F(0xffc01023)};
  var rot=new Quaternion{x=F(0x7fc01234),y=F(2),z=F(0x80000000),w=-1.5f};c.Get=()=>{Step("transform");c.Set(b);return mode=="null transform"?null:t;};t.Pos=()=>{Step("position");c.Set(b);return pos;};
  Vector3.Read=()=>{Step("zero");c.Set(b);return pos;};Quaternion.Read=()=>{Step("identity");c.Set(b);return rot;};
  bool Bits(float u,float v)=>BitConverter.SingleToInt32Bits(u)==BitConverter.SingleToInt32Bits(v);
  Intercept.Factory=(original,p,q)=>{if(!ReferenceEquals(original,a)||!Bits(p.x,pos.x)||!Bits(p.y,pos.y)||!Bits(p.z,pos.z)||!Bits(q.x,rot.x)||!Bits(q.y,rot.y)||!Bits(q.z,rot.z)||!Bits(q.w,rot.w))throw new Exception("wrong original or aggregate argument");Step("factory");};
  Exception fault=null;try{c.Run();}catch(Exception e){fault=e;}var order=k==0?new List<string>{"zero","identity"}:new List<string>{"transform","position","identity"};if(cold)order.Add("cctor");order.Add("factory");int x=order.IndexOf(mode);int n=mode=="null transform"?1:x<0?order.Count:x+1;
  if(!Trace.SequenceEqual(order.Take(n))||(mode=="null transform"?fault is not NullReferenceException:mode=="cctor"?fault is not TypeInitializationException||!ReferenceEquals(fault.InnerException,Fail):x>=0?!ReferenceEquals(fault,Fail):fault!=null))throw new Exception(k+"/"+mode+":"+string.Join(',',Trace),fault);
 }
}
static class Intercept{public static Action<UnityEngine.Object,Vector3,Quaternion> Factory;}
namespace UnityEngine{public class Object{static Object(){Case.Step("cctor");}public static T Instantiate<T>(T original, Vector3 pos, Quaternion rot) where T:Object {Intercept.Factory(original,pos,rot);return original;}}
public class GameObject:Object{}public class Transform{public Func<Vector3> Pos;public Vector3 position=>Pos();}
public struct Vector3{public float x,y,z;public static Func<Vector3> Read;public static Vector3 zero=>Read();}public struct Quaternion{public float x,y,z,w;public static Func<Quaternion> Read;public static Quaternion identity=>Read();}}
abstract class Base{public Func<Transform> Get;public Transform transform=>Get();public abstract void Set(GameObject x);public abstract void Run();}
'''+ '\n'.join(shells)
    p=tmp_path/'r';p.mkdir();(p/'Program.cs').write_text(src,encoding='utf8');print(run_case(tmp_path,p))


@pytest.mark.parametrize('bad',['wrong methodref','inconsistent entry','wrong prefab register','missing Z','overlapping homes','skip initializer','foreign readonly getter','unowned init slot','unpreserved nonvolatile','stale echo','late save overwritten'])
def test_closed_factory_requires_saved_original_full_homes_and_exact_entry(shift_runtime,monkeypatch,bad):
    from il2cpp import Decompiler,Lifter
    from il2cpp.closed_factory import closed_factory
    from il2cpp.awaiter import _spec_entry
    from iced_x86 import Register as R
    meta,il=shift_runtime;m=meta.methods[27086 if bad in ('stale echo','late save overwritten') else 25117];td=meta.typedefs[m.declaring];d=Decompiler(Lifter(il));d._ensure_eh_helper_set();d.eh=il.eh_regions(m.addr);s,_=d._decode(m)
    def plan(seq):
        blocks,_=d._make_blocks(seq,set(),());return closed_factory(d.L,m,td,blocks,seq,())
    assert plan(s)
    if bad=='inconsistent entry':
        _spec_entry(il,175369,56609);monkeypatch.setitem(il._awaiter_spec_indices[56609],175369,-1);assert plan(s) is None;return
    if bad=='foreign readonly getter':
        # The registered property reads only 16 bytes from this exact slot.
        # A differently typed static field at offset 0 cannot be that alias.
        decode=il.decode_slot;monkeypatch.setattr(il,'decode_slot',lambda a:decode(0x183c3ce88) if a==0x183bf8d18 else decode(a));assert plan(s) is None;return
    ip={'wrong methodref':0x1806d3519,'wrong prefab register':0x1806d3530,'missing Z':0x1806d3539,'overlapping homes':0x1806d3520,'skip initializer':0x1806d3512,'unowned init slot':0x1806d3480,'unpreserved nonvolatile':0x1806d3471,'stale echo':0x18059b590,'late save overwritten':0x18059b56f}[bad]
    j=next(n for n,i in enumerate(s) if i.ip==ip);i=s[j].copy()
    if bad=='wrong methodref':i.memory_displacement=0x183c3ce88
    elif bad=='wrong prefab register':i.op1_register=R.RDI
    elif bad=='missing Z':i.memory_displacement+=4
    elif bad=='overlapping homes':i.memory_displacement=0x20
    elif bad=='unowned init slot':i.memory_displacement=0x183c3ce88
    elif bad=='unpreserved nonvolatile':i.op0_register=R.R12
    elif bad=='stale echo':i.memory_base=R.RDI
    elif bad=='late save overwritten':i.op1_register=R.XMM7
    else:i.near_branch64=0x1806d3520
    assert plan([*s[:j],i,*s[j+1:]]) is None
