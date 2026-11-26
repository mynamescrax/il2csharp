using System;
using System.Linq;
using System.Collections.Generic;
using UnityEngine;
using Fusion;

foreach(bool spawn in new[]{false,true}) {
    Probe.Run("no events",spawn,true,0,2);
    Probe.Run("zero live",spawn,true,1,0);
    Probe.Run("last live",spawn,true,1,2);
    Probe.Run("no match",spawn,true,1,2);
    Probe.Run("first match",spawn,true,1,3);
    Probe.Run("multiple events",spawn,true,2,2);
}
Probe.Run("no authority",true,false,1,2);
foreach(string fault in new[]{"events","max","fill","intersection0","normal0","look","authority","manager","component","spawn","read1","clear1","set"})
    Probe.Run("fault",true,true,1,2,fault);
Probe.Run("null manager",true,true,1,2);
Probe.Run("bounds",false,true,1,4);
Console.WriteLine("Both branches: counter, call order, exact spawn arguments, array identity, live counts and exception boundaries passed.");

static class Probe {
    public static List<string> Trace; public static string Stop;public static ApplicationException Failure;
    public static void Step(string s){Trace.Add(s);if(s==Stop)throw Failure;}
    public static GameObject Other,Prefab;public static NetworkObject Component;public static bool Authority;
    public static FusionNetworkManager Manager;public static ParticleCollisionEvent[] Events;public static ParticleSystem.Particle[] Particles;
    public static List_1<ParticleCollisionEvent> List;public static int Live,Current;public static string Mode;
    public static Vector3 Point(int i)=>i==0?new(3,-7,19):new(-11,13,5);
    public static Vector3 Normal(int i)=>new(17+i,-23-i,31+i);
    public static Quaternion Rotation(Vector3 n)=>new(n.X,n.Y,n.Z,-37);
    public static void Run(string mode,bool spawn,bool authority,int events,int live,string stop=null){
        Trace=new();Stop=stop;Failure=new(stop);Mode=mode;Authority=authority;Live=live;Current=-1;
        Other=new();Prefab=new();Component=new();Manager=mode=="null manager"?null:new();
        Events=Enumerable.Range(0,events).Select(i=>new ParticleCollisionEvent(i,false)).ToArray();
        Particles=null;var ps=new ParticleSystem();var target=new ParticleCollisionSpawner(ps,Prefab,spawn?1:0);
        var expected=new List<string>{"events","main","max","fill"};var visits=new List<int>();var cleared=new List<int>();
        Type error=null;
        for(int i=0;i<events && error==null;i++){
            expected.Add("index"+i);expected.Add("intersection"+i);
            if(spawn){expected.Add("index"+i);expected.Add("normal"+i);expected.Add("look");expected.Add("client");expected.Add("object");expected.Add("authority");
                if(authority){expected.Add("manager");expected.Add("component");if(mode=="null manager"){error=typeof(NullReferenceException);break;}expected.Add("spawn");}}
            for(int j=0;j<live;j++){
                if(j==3){error=typeof(IndexOutOfRangeException);break;}
                visits.Add(j);expected.Add("read"+j);expected.Add("distance");
                if(TargetIndex(mode,i)==j){cleared.Add(j);expected.Add("clear"+j);break;}
            }
        }
        if(error==null)expected.Add("set");
        if(stop!=null){int j=expected.IndexOf(stop);if(j<0)throw new Exception("bad fault case");expected.RemoveRange(j+1,expected.Count-j-1);error=typeof(ApplicationException);}
        Exception thrown=null;try{target.Fire(Other);}catch(Exception ex){thrown=ex;}
        if(thrown?.GetType()!=error || (stop!=null&&!ReferenceEquals(thrown,Failure)) || !Trace.SequenceEqual(expected) ||target.Counter!=(spawn?0:1))
            throw new Exception($"{mode}/{spawn}/{stop}: got {thrown}, {string.Join(',',Trace)}; expected {error}, {string.Join(',',expected)}");
        if(error==null){for(int i=0;i<Particles.Length;i++)if(Particles[i].Life!=(cleared.Contains(i)?0f:8f))throw new Exception("write not on filled array");
            Console.WriteLine($"{mode} spawn={spawn && authority}: visits=[{string.Join(',',visits)}] cleared=[{string.Join(',',cleared)}] SetParticles(same,{live})");}
    }
    static int TargetIndex(string m,int i)=>m=="bounds"||m=="no match"?-1:m=="first match"||i==1?0:1;
    public static Vector3 At(int j)=>Mode=="first match"&&j<=1?Point(0):Mode!="bounds"&&Mode!="no match"&&j==1?Point(0):j==0&&Mode=="multiple events"?Point(1):new(101,102,103);
}
namespace System.Collections.Generic {class List_1<T>:List<T>{public new T this[int i]{get{Probe.Step("index"+i);return base[i];}set=>base[i]=value;}}}
namespace UnityEngine {
    record struct Vector3(float X,float Y,float Z){public static float Distance(Vector3 a,Vector3 b){Probe.Step("distance");if(b!=Probe.Point(Probe.Current))throw new Exception("wrong saved intersection");return MathF.Sqrt((a.X-b.X)*(a.X-b.X)+(a.Y-b.Y)*(a.Y-b.Y)+(a.Z-b.Z)*(a.Z-b.Z));}}
    record struct Quaternion(float X,float Y,float Z,float W){public static Quaternion LookRotation(Vector3 n){Probe.Step("look");if(n!=Probe.Normal(Probe.Current))throw new Exception("wrong normal");return Probe.Rotation(n);}}
    record struct ParticleCollisionEvent(int Id,bool Replaced){public Vector3 intersection{get{Probe.Step("intersection"+Id);Probe.Current=Id;Probe.List[Id]=new(Id,true);return Probe.Point(Id);}}
        public Vector3 normal{get{Probe.Step("normal"+Id);if(!Replaced)throw new Exception("not second list read");return Probe.Normal(Id);}}}
    class GameObject {public T GetComponent<T>() where T:class{Probe.Step("component");if(this!=Probe.Prefab)throw new Exception("wrong prefab");Probe.Manager=new();return Probe.Component as T;}}
    class ParticleSystem {
        public readonly struct MainModule{public int maxParticles{get{Probe.Step("max");return 3;}}}
        public MainModule main{get{Probe.Step("main");return default;}}
        public struct Particle{public int Id;public float Life;public Vector3 position{get{Probe.Step("read"+Id);return Probe.At(Id);}}
            public float remainingLifetime{set{Probe.Step("clear"+Id);if(BitConverter.SingleToInt32Bits(value)!=0)throw new Exception("wrong lifetime");Life=value;}}}
        public int GetParticles(Particle[] a){Probe.Step("fill");if(a.Length!=3)throw new Exception("capacity");Probe.Particles=a;for(int i=0;i<a.Length;i++)a[i]=new(){Id=i,Life=8};return Probe.Live;}
        public void SetParticles(Particle[] a,int n){Probe.Step("set");if(!ReferenceEquals(a,Probe.Particles)||n!=Probe.Live)throw new Exception("array or count changed");}
    }
    static class ParticlePhysicsExtensions{public static int GetCollisionEvents(ParticleSystem ps,GameObject other,List_1<ParticleCollisionEvent> list){Probe.Step("events");if(other!=Probe.Other)throw new Exception("wrong collision");Probe.List=list;list.AddRange(Probe.Events);return list.Count;}}
}
namespace Fusion {class NetworkObject {public bool HasStateAuthority{get{Probe.Step("authority");return Probe.Authority;}}}}
class PlayerManager{private NetworkObject _object=new();public NetworkObject Object{get{Probe.Step("object");return _object;}}}
class ClientPlayer{private static ClientPlayer __field_Instance=new();public PlayerManager playerMan=new();public static ClientPlayer Instance{get{Probe.Step("client");return __field_Instance;}}}
class FusionNetworkManager {static FusionNetworkManager seen;public static FusionNetworkManager Instance{get{Probe.Step("manager");return seen=Probe.Manager;}}
    public NetworkObject SpawnItem(NetworkObject prefab,Vector3 p,Quaternion q,Action<NetworkObject> post){Probe.Step("spawn");if(this!=seen||prefab!=Probe.Component||p!=Probe.Point(Probe.Current)||q!=Probe.Rotation(Probe.Normal(Probe.Current))||post!=null)throw new Exception("bad spawn");return prefab;}}
class ParticleCollisionSpawner {
    public int spawnEveryXCollisions=2;private int curSpawnEveryXCollisions;private ParticleSystem particleSystem;public GameObject objectToSpawn;
    public ParticleCollisionSpawner(ParticleSystem ps,GameObject prefab,int counter){particleSystem=ps;objectToSpawn=prefab;curSpawnEveryXCollisions=counter;}
    public int Counter=>curSpawnEveryXCollisions;public void Fire(GameObject other)=>OnParticleCollision(other);
