import pytest
from dotnet_case import run_case
from il2cpp.emitter import Emitter
from test_game_shift_shared_flags import shift_runtime

pytestmark=pytest.mark.game


def test_spawn_samples_manager_before_prefab_and_position(shift_runtime,tmp_path):
    meta,il=shift_runtime;m=meta.methods[25213];out=[];Emitter(il,str(tmp_path/'out')).emit_method(m,meta.typedefs[m.declaring],out,'    ')
    s='''using System;using System.Linq;using System.Collections.Generic;using System.Runtime.Loader;using UnityEngine;using Fusion;
foreach(string m in new[]{"ok","cctor","manager","no object","component","null component","no transform","position","no manager","no manager and position throws","identity","spawn"}){var ctx=new AssemblyLoadContext("case",true);try{ctx.LoadFromAssemblyPath(typeof(Host).Assembly.Location).GetType("Host").GetMethod("Test").Invoke(null,new object[]{m});}finally{ctx.Unload();}}
Console.WriteLine("whole spawn: saved manager and component, refreshed position source, explicit init and late null, identity/optional arguments and faults");
public static class Host{public static Action Init;public static Func<FusionNetworkManager> Get;public static void Test(string mode){var c=new EventManager();var net=new NetworkObject();var prefab=new GameObject();var dest=new Transform();var pos=new Vector3{x=4.5f,y=-9f,z=1};var rot=new Quaternion{x=-2,y=.75f,z=3,w=-1};var trace=new List<string>();var err=new ApplicationException();
 void Step(string s){trace.Add(s);if(mode==s||mode=="no manager and position throws"&&s=="position")throw err;}
 Init=()=>Step("cctor");Get=()=>{Step("manager");c.roach=mode=="no object"?null:prefab;if(mode.StartsWith("no manager"))return null;var a=new FusionNetworkManager();a.Factory=(what,p,q,cb)=>{if(!ReferenceEquals(what,mode=="null component"?null:net)||(p.x,p.y,p.z)!=(pos.x,pos.y,pos.z)||(q.x,q.y,q.z,q.w)!=(rot.x,rot.y,rot.z,rot.w)||cb!=null)throw new Exception("wrong arguments");Step("spawn");return new NetworkObject();};return a;};
 prefab.Read=t=>{if(t!=typeof(NetworkObject))throw new Exception("wrong closed lookup");Step("component");Get=()=>throw new Exception("manager replay");c.roach=null;c.playerDoppelgangerSpawnpoint=mode=="no transform"?null:dest;return mode=="null component"?null:net;};dest.Read=()=>{Step("position");c.playerDoppelgangerSpawnpoint=null;return pos;};Quaternion.Get=()=>{Step("identity");return rot;};
 Exception ex=null;try{c.SpawnRoach();}catch(Exception e){ex=e;}string[] seq={"cctor","manager","component","position","identity","spawn"};int n=mode switch{"no object"=>2,"no transform"=>3,"no manager" or "no manager and position throws"=>4,"null component" or "ok"=>6,_=>Array.IndexOf(seq,mode)+1};
 if(!trace.SequenceEqual(seq.Take(n))||(mode=="cctor"?ex is not TypeInitializationException||!ReferenceEquals(ex.InnerException,err):mode is "no object" or "no transform" or "no manager"?ex is not NullReferenceException:mode is "ok" or "null component"?ex!=null:!ReferenceEquals(ex,err)))throw new Exception(mode+":"+string.Join(',',trace),ex);
}}
namespace UnityEngine{public struct Vector3{public float x,y,z;}public struct Quaternion{public float x,y,z,w;public static Func<Quaternion> Get;public static Quaternion identity=>Get();}public class Transform{public Func<Vector3> Read;public Vector3 position=>Read();}public class GameObject{public Func<Type,NetworkObject> Read;public T GetComponent<T>() where T:NetworkObject=>(T)Read(typeof(T));}}
namespace Fusion{public class NetworkObject{}}namespace System{public delegate void Action_1<T>(T x);}public class FusionNetworkManager{static FusionNetworkManager()=>Host.Init();public static FusionNetworkManager Instance=>Host.Get();public Func<NetworkObject,Vector3,Quaternion,Action_1<NetworkObject>,NetworkObject> Factory;public NetworkObject SpawnItem(NetworkObject n,Vector3 p,Quaternion q,Action_1<NetworkObject> a)=>Factory(n,p,q,a);}
class EventManager{public Transform playerDoppelgangerSpawnpoint;public GameObject roach;\n'''+ '\n'.join(out)+'\n}'
    p=tmp_path/'r';p.mkdir();(p/'Program.cs').write_text(s,encoding='utf8');print(run_case(tmp_path,p))
    code='\n'.join(out);assert code.index('RunClassConstructor(')<code.index('FusionNetworkManager.Instance')


@pytest.mark.parametrize('bad',['spilled XY','wrong restore','other manager','other component','stale Z','overwrite optional','wrong methodref','early null','unaligned aggregate','conflicting getter flag'])
def test_factory_witness_ties_every_value_to_its_acquisition(shift_runtime,monkeypatch,bad):
    from il2cpp import Lifter,Decompiler
    from il2cpp.singleton_factory import singleton_factory
    from iced_x86 import Register as R
    meta,il=shift_runtime;m=meta.methods[25213];td=meta.typedefs[m.declaring];d=Decompiler(Lifter(il));s,_=d._decode(m);il.eh_regions(m.addr);check=lambda:singleton_factory(d.L,m,td,s,None);assert check()
    if bad=='unaligned aggregate':
        # Make room without overlap, then move all position references by
        # four bytes. Even matching read/write homes are not 16-byte aligned.
        for n in (38,56,57,62):
            i=s[n].copy();i.memory_displacement+=4;s[n]=i
        assert check() is None;return
    if bad=='conflicting getter flag':
        from il2cpp import static_getter
        md=next(meta.methods[n] for n in meta.type_methods(meta.typedefs[meta.methods[26437].declaring]) if meta.methods[n].name=='get_Instance');lo,hi=il.function_extent(md.addr);read=il.bin.read;raw=read(lo,hi-lo);m0=static_getter._GUARDED.fullmatch(raw);assert m0
        patched=bytearray(raw);flag=s[3].ip_rel_memory_address
        for group in (1,4):patched[m0.start(group):m0.end(group)]=(flag-(lo+m0.end(group)+1)).to_bytes(4,'little',signed=True)
        monkeypatch.setattr(il.bin,'read',lambda a,n:bytes(patched) if (a,n)==(lo,hi-lo) else read(a,n));assert check() is None;return
    p={'spilled XY':0x1806da3ac,'wrong restore':0x1806da3c0,'other manager':0x1806da3fd,'other component':0x1806da3fa,'stale Z':0x1806da405,'overwrite optional':0x1806da3f5,'wrong methodref':0x1806da372,'early null':0x1806da3db}[bad]
    j=next(n for n,i in enumerate(s) if i.ip==p);i=s[j].copy()
    if bad in ('spilled XY','wrong restore'):i.memory_displacement+=8
    elif bad=='other manager':i.op1_register=R.RSI
    elif bad=='other component':i.op1_register=R.RDI
    elif bad=='stale Z':i.op1_register=R.ECX
    elif bad=='overwrite optional':i.memory_displacement=0x20
    elif bad=='wrong methodref':i.memory_displacement=0x183c2a7b0
    else:i.op0_register=i.op1_register=R.RSI
    s[j]=i;assert check() is None
