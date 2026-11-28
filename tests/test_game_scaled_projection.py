import pytest
from dotnet_case import run_case
from il2cpp.emitter import Emitter
from test_game_shift_shared_flags import shift_runtime

pytestmark=pytest.mark.game


def test_plane_dimensions_project_scaled_xz_from_one_bounds_result(shift_runtime,tmp_path):
    meta,il=shift_runtime;em=Emitter(il,str(tmp_path/'out'));shells=[]
    for mi in (23586,23598):
        m=meta.methods[mi];td=meta.typedefs[m.declaring];lines=[];em.emit_method(m,td,lines,'    ');shells.append('class '+td.name+' {public GameObject surface;public Vector2 Run()=>GetRealPlaneSize();\n'+'\n'.join(lines)+'\n}')
    src='''using System;using System.Linq;using System.Collections.Generic;using UnityEngine;
foreach(bool street in new[]{true,false})foreach(string mode in new[]{"ok","zero","null surface","lookup","null renderer","bounds"}){
 var go=new GameObject();var renderer=new MeshRenderer();var a=new StandingPeopleStreet();var b=new StandingPeopleConcert();a.surface=b.surface=mode=="null surface"?null:go;Func<Vector2> run=street?a.Run:b.Run;var trace=new List<string>();var err=new ApplicationException();
 void Step(string tag){trace.Add(tag);if(mode==tag)throw err;}
 var v=mode=="zero"?new Vector3{x=BitConverter.Int32BitsToSingle(int.MinValue),y=17,z=BitConverter.Int32BitsToSingle(1)}:new Vector3{x=1.25f,y=9,z=3.5f};
 go.Lookup=t=>{if(t!=typeof(MeshRenderer))throw new Exception("incorrect lookup type");Step("lookup");a.surface=b.surface=null;return mode=="null renderer"?null:renderer;};renderer.Read=()=>{Step("bounds");return new Bounds(new Vector3{x=100,y=200,z=300},v);};
 Vector2 got=default;Exception fault=null;try{got=run();}catch(Exception e){fault=e;}string wanted=mode switch{"null surface"=>"","lookup" or "null renderer"=>"lookup",_=>"lookup,bounds"};
 bool ok=mode is "ok" or "zero";if(string.Join(',',trace)!=wanted||(ok?fault!=null:mode.StartsWith("null")?fault is not NullReferenceException:!ReferenceEquals(err,fault))||ok&&(BitConverter.SingleToInt32Bits(got.x)!=BitConverter.SingleToInt32Bits(v.x*2)||BitConverter.SingleToInt32Bits(got.y)!=BitConverter.SingleToInt32Bits(v.z*2)))throw new Exception(mode+":"+string.Join(',',trace),fault);
}
Console.WriteLine("both whole plane-size helpers: public bounds/extent path, scaled X and Z, one lookup, one sample, fault order");
namespace UnityEngine{public struct Vector3{public float x,y,z;}public struct Vector2{public float x,y;}public struct Bounds{private Vector3 m_Center,m_Extents;public Bounds(Vector3 center,Vector3 extent){m_Center=center;m_Extents=extent;}public Vector3 extents=>m_Extents;}
public class Component{}public class GameObject{public Func<Type,Component> Lookup;public T GetComponent<T>() where T:Component=>(T)Lookup(typeof(T));}public class Renderer:Component{public Func<Bounds> Read;public Bounds bounds=>Read();}public class MeshRenderer:Renderer{}}
'''+ '\n'.join(shells)
    r=tmp_path/'r';r.mkdir();(r/'Program.cs').write_text(src,encoding='utf8');print(run_case(tmp_path,r))


@pytest.mark.parametrize('bad',['wrong base','bad offset','wrong factor source','wrong unpack inputs','wrong return lane'])
def test_projection_declines_unproved_echo_or_packed_lane(shift_runtime,monkeypatch,bad):
    from il2cpp import Lifter,Decompiler
    from il2cpp.scaled_projection import project_sites
    from iced_x86 import Register as R
    meta,il=shift_runtime;m=meta.methods[23598];td=meta.typedefs[m.declaring];d=Decompiler(Lifter(il));d.lift_method(m,td);bs=d.L._blocks
    plan=lambda:project_sites(d.L,m,td,bs,());keys=plan();assert len(keys)==1;site=next(iter(keys));
    b,j=next((b,j) for b in bs for j,i in enumerate(b.insns) if i.ip==site);j+=dict(zip(('wrong base','bad offset','wrong factor source','wrong unpack inputs','wrong return lane'),(0,1,2,4,5)))[bad];i=b.insns[j].copy()
    if bad=='wrong base':i.memory_base=R.RBX
    elif bad=='bad offset':i.memory_displacement=10
    elif bad=='wrong factor source':i.memory_displacement=il.bin.image_base+next(s.addr-il.bin.image_base for s in il.bin.sections if s.chars&0x80000000)
    elif bad=='wrong unpack inputs':i.op1_register=i.op0_register
    else:i.op1_register=R.XMM5
    monkeypatch.setattr(b,'insns',b.insns[:j]+[i]+b.insns[j+1:]);assert not plan()


def test_two_distinct_readonly_factors_stay_on_their_own_lanes(shift_runtime,tmp_path,monkeypatch):
    from iced_x86 import Mnemonic as M
    import struct
    meta,il=shift_runtime;m=meta.methods[23598];td=meta.typedefs[m.declaring];em=Emitter(il,str(tmp_path/'out'));d=em.decompiler;orig=d._decode
    seq,_=orig(m);multipliers=[i for i in seq if i.mnemonic==M.MULSS];assert len(multipliers)==2
    addr=multipliers[0].ip_rel_memory_address;factors={addr:struct.pack('<f',.25),addr+4:struct.pack('<f',-3)}
    def alt(md):
        seq,skip=orig(md)
        if md.index!=m.index:return seq,skip
        seq=list(seq);j=next(j for j,i in enumerate(seq) if i.ip==multipliers[1].ip);i=seq[j].copy();i.memory_displacement=addr+4;seq[j]=i;return seq,skip
    read=il.bin.read;monkeypatch.setattr(il.bin,'read',lambda a,n:factors[a] if n==4 and a in factors else read(a,n));monkeypatch.setattr(d,'_decode',alt)
    lines=[];em.emit_method(m,td,lines,'    ')
    s='''using System;using UnityEngine;
var c=new C();var v=c.Get();if(v.x!=.3125f||v.y!=-10.5f)throw new Exception($"{v.x},{v.y}");Console.WriteLine("two distinct scale factors");
namespace UnityEngine{public struct Vector2{public float x,y;}public struct Vector3{public float x,y,z;}public struct Bounds{public Vector3 extents=>new Vector3{x=1.25f,y=9,z=3.5f};}public class Renderer{public Bounds bounds=>default;}public class MeshRenderer:Renderer{}public class GameObject{public T GetComponent<T>() where T:Renderer,new()=>new T();}}
class C{public GameObject surface=new();public Vector2 Get()=>GetRealPlaneSize();\n'''+ '\n'.join(lines)+'\n}'
    p=tmp_path/'r';p.mkdir();(p/'Program.cs').write_text(s,encoding='utf8');print(run_case(tmp_path,p))
