import pytest
from dotnet_case import run_case
from il2cpp.emitter import Emitter
from test_game_shift_shared_flags import shift_runtime

pytestmark=pytest.mark.game


def test_model_sizes_lookup_on_the_checked_prefab(shift_runtime,tmp_path):
    meta,il=shift_runtime;em=Emitter(il,str(tmp_path/'out'));shells=[]
    for mi in (23587,23599):
        m=meta.methods[mi];td=meta.typedefs[m.declaring];out=[];em.emit_method(m,td,out,'    ');shells.append('class '+td.name+':Base{public override Vector2 Run()=>GetRealPeopleModelSize();\n'+'\n'.join(out)+'\n}')
    s='''using System;using System.Collections.Generic;using System.Linq;using UnityEngine;
foreach(Base c in new Base[]{new StandingPeopleConcert(),new StandingPeopleStreet()})foreach(string mode in new[]{"null array","empty","short","null element","lookup","null renderer","bounds","ok"}){
 var item=new GameObject();var poison=new GameObject();var renderer=new MeshRenderer();var trace=new List<string>();var err=new ApplicationException();void Step(string s){trace.Add(s);if(s==mode)throw err;}
 c.peoplePrefabs=mode switch{"null array"=>null,"empty"=>Array.Empty<GameObject>(),"short"=>new[]{poison},_=>new[]{poison,mode=="null element"?null:item,poison}};
 poison.Read=_=>throw new Exception("wrong index");item.Read=t=>{if(t!=typeof(MeshRenderer))throw new Exception("wrong lookup type");Step("lookup");c.peoplePrefabs[1]=poison;c.peoplePrefabs=null;return mode=="null renderer"?null:renderer;};renderer.Read=()=>{Step("bounds");return new Bounds(new Vector3{x=7,y=19,z=4});};
 Exception ex=null;Vector2 size=default;try{size=c.Run();}catch(Exception e){ex=e;}int n=mode is "lookup" or "null renderer"?1:mode is "bounds" or "ok"?2:0;
 if(!trace.SequenceEqual(new[]{"lookup","bounds"}.Take(n))||(mode is "short" or "empty"?ex is not IndexOutOfRangeException:mode.StartsWith("null")?ex is not NullReferenceException:mode=="ok"?ex!=null||size.x!=14||size.y!=8:!ReferenceEquals(ex,err)))throw new Exception(mode+":"+string.Join(',',trace),ex);
}
Console.WriteLine("both complete model-size methods: reference array bounds, selected object identity, closed lookup, bounds and faults");
namespace UnityEngine{public struct Vector2{public float x,y;}public struct Vector3{public float x,y,z;}public readonly struct Bounds{private readonly Vector3 m_Extents;public Bounds(Vector3 e)=>m_Extents=e;public Vector3 extents=>m_Extents;}public class Renderer{public Func<Bounds> Read;public Bounds bounds=>Read();}public class MeshRenderer:Renderer{}public class GameObject{public Func<Type,Renderer> Read;public T GetComponent<T>() where T:Renderer=>(T)Read(typeof(T));}}
abstract class Base{public GameObject[] peoplePrefabs;public abstract Vector2 Run();}
'''+ '\n'.join(shells)
    r=tmp_path/'r';r.mkdir();(r/'Program.cs').write_text(s,encoding='utf8');print(run_case(tmp_path,r))


@pytest.mark.parametrize('bad',['wrong threshold','wrong cell','other array','signed bound','wrong raiser'])
def test_constant_index_matches_the_unsigned_length_gate(shift_runtime,monkeypatch,bad):
    from il2cpp import Lifter,Decompiler
    from il2cpp.indexed_lookup import fixed_lookup_elements
    from iced_x86 import Decoder,Register as R
    meta,il=shift_runtime;m=meta.methods[23587];td=meta.typedefs[m.declaring];d=Decompiler(Lifter(il));d.lift_method(m,td);bs=d.L._blocks
    scan=lambda:fixed_lookup_elements(d.L,m,td,bs,());assert set(scan())=={0x18050d644}
    ip={'wrong threshold':0x18050d63e,'wrong cell':0x18050d644,'other array':0x18050d644,'signed bound':0x18050d642,'wrong raiser':0x18050d642}[bad];b,j=next((b,j) for b in bs for j,i in enumerate(b.insns) if i.ip==ip);i=b.insns[j].copy()
    if bad=='wrong threshold':i.immediate8=0
    elif bad=='wrong cell':i.memory_displacement+=8
    elif bad=='other array':i.memory_base=R.RBX
    elif bad=='signed bound':i=Decoder(64,bytes.fromhex('7e58'),ip=ip).decode()
    else:i.near_branch64=0x18050d696
    monkeypatch.setattr(b,'insns',b.insns[:j]+[i]+b.insns[j+1:]);assert not scan()
