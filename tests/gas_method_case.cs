using System;
using System.Collections.Generic;
using System.Linq;
using UnityEngine;
using Fusion;

foreach(bool gated in new[]{false,true}) foreach(bool auth in new[]{false,true})
foreach(string terrain in new[]{"dry","water absent","water tank","water destroyed"})
foreach(int counter in new[]{0,1,2}) Probe.Run(gated,auth,terrain,counter,2,2);
Probe.Run(true,true,"dry",2,0,2);
Probe.Run(false,false,"water absent",2,2,0);
foreach(string stage in new[]{"object","authority","layer name","layer","lookup","compare","events","main","capacity","fill","intersection:0","normal:0","look:0","rpc:1","closest:1","writeback"})
    Probe.Run(true,true,"water absent",2,2,1,stage);
Probe.Run(false,false,"water tank",2,1,1,"pump");
Console.WriteLine("Gas callback: 96 gate/water/counter combinations, zero events/live, and 17 exception boundaries passed");

static class Probe {
    public static GameObject Other;public static GasCollisionSpawner Gas;public static ParticleSystem.Particle[] Filled;
    public static int N,Live,Index;public static bool Authority;public static string Terrain,Stop;public static ApplicationException Failure;
    public static List<string> Trace;public static List_1<ParticleCollisionEvent> Events;
    public static Vector3 P(int i)=>new(3+i, -11-i, 5*i+1);public static Vector3 Nrm(int i)=>new(-13+i, 19-i, 7*i+3);
    public static Quaternion Q(int i)=>new(Nrm(i).Z,Nrm(i).X,Nrm(i).Y,-29-i);
    public static void Step(string s){Trace.Add(s);if(s==Stop)throw Failure;}
    public static void Run(bool gate,bool auth,string terrain,int before,int events,int live,string stop=null){
        Authority=auth;Terrain=terrain;Stop=stop;Failure=new(stop);N=events;Live=live;Index=-1;Trace=new();Filled=null;
        Gas=new GasCollisionSpawner(gate,before);Other=new GameObject();var want=new List<string>();int counter=before;
        if(gate)want.AddRange(new[]{"object","authority"});
        if(!gate||auth){want.AddRange(new[]{"layer name","layer"});if(terrain!="dry")want.AddRange(new[]{"lookup","compare"});
            if(terrain=="water tank")want.AddRange(new[]{"pump","kill collided"});
            else if(++counter<=2)want.Add("kill collided");
            else{counter=0;want.AddRange(new[]{"events","main","capacity","fill"});
                for(int i=0;i<N;i++)want.AddRange(new[]{$"index:{i}",$"intersection:{i}",$"index:{i}",$"normal:{i}",$"look:{i}",$"rpc:{i}",$"closest:{i}"});
                want.Add("writeback");}}
        if(stop!=null){int at=want.IndexOf(stop);if(at<0)throw new Exception("bad test case: "+stop);want.RemoveRange(at+1,want.Count-at-1);
            if(!want.Contains("events")&&!want.Contains("kill collided"))counter=before;}
        try{Gas.Fire(Other);if(stop!=null)throw new Exception("missing fault");}catch(ApplicationException e) when(ReferenceEquals(e,Failure)){}
        if(!want.SequenceEqual(Trace)||counter!=Gas.Counter)throw new Exception($"{terrain}/{gate}/{auth}/{before}/{stop}: expected {string.Join(',',want)} counter {counter}; got {string.Join(',',Trace)} counter {Gas.Counter}");
        if(!gate&&!auth&&terrain=="water absent"&&before==2&&stop==null&&live==2)Console.WriteLine("water lookup miss, over threshold: "+string.Join(",",Trace));
    }
}
namespace UnityEngine {
    class Object {public bool Destroyed;public static bool operator !=(Object a,Object b){Probe.Step("compare");if(!ReferenceEquals(b,null))throw new Exception("not compared with null");return !ReferenceEquals(a,null)&&!a.Destroyed;}
        public static bool operator ==(Object a,Object b)=>!(a!=b);public override bool Equals(object x)=>ReferenceEquals(x,this);public override int GetHashCode()=>base.GetHashCode();}
    static class LayerMask {public static int NameToLayer(string s){Probe.Step("layer name");if(s!="Water")throw new Exception("layer name");return 7;}}
    class GameObject:Object {public int layer {get{Probe.Step("layer");return Probe.Terrain=="dry"?2:7;}}
        public T GetComponentInParent<T>() where T:Object {Probe.Step("lookup");if(typeof(T)!=typeof(PetrolTank)||!ReferenceEquals(this,Probe.Other))throw new Exception("lookup type/receiver");return (Probe.Terrain=="water absent"?null:new PetrolTank{Destroyed=Probe.Terrain=="water destroyed"}) as T;}}
    record struct Vector3(float X,float Y,float Z);
    record struct Quaternion(float X,float Y,float Z,float W){public static Quaternion LookRotation(Vector3 n){int i=Probe.Index;Probe.Step("look:"+i);if(n!=Probe.Nrm(i))throw new Exception("wrong forward XYZ");return Probe.Q(i);}}
    record struct ParticleCollisionEvent(int I,bool Second){public Vector3 intersection{get{Probe.Step("intersection:"+I);Probe.Index=I;Probe.Events[I]=new(I,true);return Probe.P(I);}}
        public Vector3 normal{get{Probe.Step("normal:"+I);if(!Second)throw new Exception("stale event");return Probe.Nrm(I);}}}
    class ParticleSystem {public struct Particle{public int Tag;} public readonly struct MainModule{public int maxParticles{get{Probe.Step("capacity");return 4;}}}
        public MainModule main{get{Probe.Step("main");return default;}}public int GetParticles(Particle[] a){Probe.Step("fill");if(a.Length!=4)throw new Exception("capacity");Probe.Filled=a;return Probe.Live;}
        public void SetParticles(Particle[] a,int live){Probe.Step("writeback");if(!ReferenceEquals(a,Probe.Filled)||live!=Probe.Live||a[0].Tag!=Probe.N)throw new Exception("lost array, writes or live count");}}
    static class ParticlePhysicsExtensions{public static int GetCollisionEvents(ParticleSystem ps,GameObject other,List_1<ParticleCollisionEvent> list){Probe.Step("events");if(!ReferenceEquals(other,Probe.Other))throw new Exception();Probe.Events=list;for(int i=0;i<Probe.N;i++)list.Add(new(i,false));return list.Count;}}
}
namespace System.Collections.Generic {class List_1<T>:List<T>{public new T this[int i]{get{Probe.Step("index:"+i);return base[i];}set=>base[i]=value;}}}
namespace Fusion {class NetworkObject {public bool HasStateAuthority {get{Probe.Step("authority");return Probe.Authority;}}}
    class NetworkBehaviour {private NetworkObject _object=new();public NetworkObject Object{get{Probe.Step("object");return _object;}}}}
class PetrolTank:UnityEngine.Object {public void PetrolPumped()=>Probe.Step("pump");}
class GasCollisionSpawner:NetworkBehaviour {
    private bool onlySpawnParticleIfServer;private ParticleSystem ps=new();private int curSpawnEveryXCollisions,spawnEveryXCollisions=2;
    public int Counter=>curSpawnEveryXCollisions;public GasCollisionSpawner(bool gate,int c){onlySpawnParticleIfServer=gate;curSpawnEveryXCollisions=c;}
    public void Fire(GameObject other)=>OnParticleCollision(other);
    void KillCollidedParticles(GameObject other){Probe.Step("kill collided");if(!ReferenceEquals(other,Probe.Other))throw new Exception("wrong collision");}
    public void Rpc_CMD_SpawnParticle(Vector3 pos,Quaternion rot){int i=Probe.Index;Probe.Step("rpc:"+i);if(!ReferenceEquals(this,Probe.Gas)||pos!=Probe.P(i)||rot!=Probe.Q(i))throw new Exception("wrong RPC arguments");}
    static void KillClosestParticleAt(Vector3 hitPos,ParticleSystem.Particle[] particles,int alive,float threshold){int i=Probe.Index;Probe.Step("closest:"+i);
        if(hitPos!=Probe.P(i)||!ReferenceEquals(particles,Probe.Filled)||alive!=Probe.Live||threshold!=0.1f)throw new Exception("wrong kill arguments");particles[0].Tag++;}
