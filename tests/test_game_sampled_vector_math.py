import pytest
from dotnet_case import run_case
from il2cpp.emitter import Emitter
from test_game_shift_shared_flags import shift_runtime

pytestmark=pytest.mark.game


def test_airborne_force_uses_the_first_scale_and_the_later_velocity(shift_runtime,tmp_path):
    meta,il=shift_runtime;m=meta.methods[28795];out=[];Emitter(il,str(tmp_path/'out')).emit_method(m,meta.typedefs[m.declaring],out,'    ')
    s='''using System;using System.Linq;using System.Collections.Generic;using UnityEngine;
foreach(float vy in new[]{-1f,-0f,0f,2f,float.NaN,float.NegativeInfinity})foreach(string mode in new[]{"ok","first","second","no body","force","no next","velocity"}){
 var c=new ObiCharacter();var one=new Rigidbody();var two=new Rigidbody();var trace=new List<string>();var err=new ApplicationException();void Step(string tag){trace.Add(tag);if(mode==tag)throw err;}
 c.m_GroundCheckDistance=-9;c.m_OrigGroundCheckDistance=-11;int reads=0;Physics.Read=()=>{if(++reads==1){Step("first");c.m_GravityMultiplier=2;return new Vector3{x=1,y=2,z=3};}
 if(reads!=2)throw new Exception("third gravity");Step("second");c.m_GravityMultiplier=10;c.m_Rigidbody=mode=="no body"?null:one;return new Vector3{x=7,y=11,z=17};};
 one.Force=v=>{if(v.x!=-5||v.y!=-7||v.z!=-11)throw new Exception("wrong force");Step("force");c.m_Rigidbody=mode=="no next"?null:two;};two.Read=()=>{Step("velocity");c.m_OrigGroundCheckDistance=.5f;return new Vector3{y=vy};};
 Exception ex=null;try{c.Run();}catch(Exception e){ex=e;}string[] order={"first","second","force","velocity"};int n=mode switch{"ok"=>4,"no body"=>2,"no next"=>3,_=>Array.IndexOf(order,mode)+1};
 if(!trace.SequenceEqual(order.Take(n))||(mode=="ok"?ex!=null:mode.StartsWith("no ")?ex is not NullReferenceException:!ReferenceEquals(ex,err))||c.m_GroundCheckDistance!=(mode=="ok"?(vy<0?.5f:.01f):-9f))throw new Exception(mode+"/"+vy+":"+string.Join(',',trace),ex);
}
Console.WriteLine("whole airborne motion: two distinct gravity samples, single pre-second scale, reloaded velocity receiver and unordered ground check");
namespace UnityEngine{public struct Vector3{public float x,y,z;}public static class Physics{public static Func<Vector3> Read;public static Vector3 gravity=>Read();}public class Rigidbody{public Action<Vector3> Force;public void AddForce(Vector3 v)=>Force(v);public Func<Vector3> Read;public Vector3 linearVelocity=>Read();}}
class ObiCharacter{public float m_GravityMultiplier,m_OrigGroundCheckDistance,m_GroundCheckDistance;public Rigidbody m_Rigidbody;public void Run()=>HandleAirborneMovement();\n'''+ '\n'.join(out)+'\n}'
    p=tmp_path/'r';p.mkdir();(p/'Program.cs').write_text(s,encoding='utf8');print(run_case(tmp_path,p))


@pytest.mark.parametrize('bad',['other field owner','shuffle','multiply with other factor','truncated echo','ordered branch','different result register'])
def test_vector_poll_and_unordered_lane_are_separately_certified(shift_runtime,monkeypatch,bad):
    from il2cpp import Lifter,Decompiler
    from il2cpp.sampled_vector_math import vector_polls
    from iced_x86 import Register as R,Decoder
    meta,il=shift_runtime;m=meta.methods[28795];td=meta.typedefs[m.declaring];d=Decompiler(Lifter(il));d.lift_method(m,td);bs=d.L._blocks;scan=lambda:vector_polls(d.L,m,td,bs,());a,b=scan();assert set(a)=={0x18062cc86} and set(b)=={0x18062cd20}
    p={'other field owner':0x18062cc86,'shuffle':0x18062cc98,'multiply with other factor':0x18062cca3,'truncated echo':0x18062cd1c,'ordered branch':0x18062cd20,'different result register':0x18062cd19}[bad]
    bk,j=next((b,j) for b in bs for j,i in enumerate(b.insns) if i.ip==p);i=bk.insns[j].copy()
    if bad=='other field owner':i.memory_base=R.RSI
    elif bad=='shuffle':i.immediate8=0xaa
    elif bad=='multiply with other factor':i.op1_register=R.XMM5
    elif bad=='truncated echo':i.memory_displacement=10
    elif bad=='ordered branch':i=Decoder(64,bytes.fromhex('7707'),ip=p).decode()
    else:i.op0_register=i.op1_register=R.XMM2
    monkeypatch.setattr(bk,'insns',bk.insns[:j]+[i]+bk.insns[j+1:]);assert scan()==(({},b) if bad in ('other field owner','shuffle','multiply with other factor') else (a,{}))
