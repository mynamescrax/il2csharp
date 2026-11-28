import pytest
from dotnet_case import run_case
from il2cpp import Lifter,Decompiler
from test_game_shift_shared_flags import shift_runtime

pytestmark=pytest.mark.game


def test_pool_creation_prefix_uses_one_key_and_one_membership_check(shift_runtime,tmp_path):
    meta,il=shift_runtime;m=meta.methods[23861];d=Decompiler(Lifter(il));b=d.lift_method(m,meta.typedefs[m.declaring]);start=next(j for j,s in enumerate(b) if s not in ('unsafe','{'));end=next(j for j,s in enumerate(b) if s.strip().startswith('if (number '));prefix=b[start:end]
    src='''using System;using System.Linq;using System.Collections.Generic;using UnityEngine;using Lists=System.Collections.Generic.List_1<UnityEngine.GameObject>;
foreach(string mode in new[]{"hit","miss","null source","key","no map","probe","allocate","insert","cursor"}){
 var c=new Pool();var trace=new List<string>();var err=new ApplicationException();void Step(string s){trace.Add(s);if(mode==s)throw err;}
 var p=new Watch();var q=new Watch();var h=new Watch();var before=new Dictionary_2<int,Lists>(p);var after=new Dictionary_2<int,Lists>(q);var spare=new Dictionary_2<int,Lists>();var curs=new Dictionary_2<int,int>(h);var original=new Lists();before.Add(mode=="hit"?37:99,original);after.Add(91,original);curs.Add(91,2);
 c.instantiatedObjects=spare;c.poolCursors=new();var go=new GameObject();go.Read=()=>{Step("key");c.instantiatedObjects=mode=="no map"?null:before;return 37;};p.Observe=()=>{Step("probe");c.instantiatedObjects=after;};Lists.Born=()=>{Step("allocate");c.instantiatedObjects=spare;};q.Observe=()=>{Step("insert");c.poolCursors=curs;};h.Observe=()=>Step("cursor");
 Exception ex=null;try{c.Run(mode=="null source"?null:go);}catch(Exception e){ex=e;}p.Observe=q.Observe=h.Observe=Lists.Born=null;
 string[] steps={"key","probe","allocate","insert","cursor"};int n=mode switch{"hit"=>2,"miss"=>5,"null source"=>0,"no map"=>1,_=>Array.IndexOf(steps,mode)+1};
 if(!trace.SequenceEqual(steps.Take(n))||(mode is "null source" or "no map"?ex is not NullReferenceException:mode is "hit" or "miss"?ex!=null:!ReferenceEquals(ex,err))||before.Count!=1||spare.Count!=0||after.ContainsKey(37)!=(mode is "miss" or "cursor")||curs.ContainsKey(37)!=(mode=="miss"))throw new Exception(mode+":"+string.Join(',',trace),ex);
}
Console.WriteLine("pool registration prefix: one ID, one membership hash, map replacement on miss, allocation and two writes in order");
class Watch:IEqualityComparer<int>{public Action Observe;public bool Equals(int a,int b)=>a==b;public int GetHashCode(int x){Observe?.Invoke();return x;}}
namespace System.Collections.Generic{public class List_1<T>:List<T>{public static Action Born;public List_1()=>Born?.Invoke();}public class Dictionary_2<K,V>:Dictionary<K,V>{public Dictionary_2(){}public Dictionary_2(IEqualityComparer<K> cmp):base(cmp){}}}
namespace UnityEngine{public class GameObject{public Func<int> Read;public int GetInstanceID()=>Read();}}
class Pool{public Dictionary_2<int,List_1<GameObject>> instantiatedObjects;public Dictionary_2<int,int> poolCursors;public void Run(GameObject sourceObject){\n'''+ '\n'.join(prefix)+'\n}}'
    p=tmp_path/'r';p.mkdir();(p/'Program.cs').write_text(src,encoding='utf8');print(run_case(tmp_path,p))


@pytest.mark.parametrize('fault',['other context','wrong key register','other map','missing park','branch signed'])
def test_pool_membership_requires_registered_key_and_reload(shift_runtime,monkeypatch,fault):
    from iced_x86 import Register as R,Decoder
    from il2cpp.sampled_membership import membership_samples
    meta,il=shift_runtime;m=meta.methods[23861];td=meta.typedefs[m.declaring];d=Decompiler(Lifter(il));d.lift_method(m,td);bs=d.L._blocks;scan=lambda:membership_samples(d.L,m,td,bs,());f,c=scan();assert set(c)=={0x180515fd7,0x180515ff5} and set(f)=={0x180515fdc,0x180516005}
    ip={'other context':0x180515fec,'wrong key register':0x180515ff3,'other map':0x180516005,'missing park':0x180515fe0,'branch signed':0x180515ffc}[fault];b,j=next((b,j) for b in bs for j,i in enumerate(b.insns) if i.ip==ip);i=b.insns[j].copy()
    if fault=='other context':i.memory_displacement=0x183c2d078
    elif fault=='wrong key register':i.op1_register=R.ECX
    elif fault=='other map':i.memory_displacement+=8
    elif fault=='missing park':i.op0_register=R.ECX
    else:i=Decoder(64,bytes.fromhex('7f5f'),ip=ip).decode()
    monkeypatch.setattr(b,'insns',b.insns[:j]+[i]+b.insns[j+1:]);assert scan()==({},{})
