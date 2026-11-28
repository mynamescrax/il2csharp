import pytest
from dotnet_case import run_case
from il2cpp.emitter import Emitter
from test_game_shift_shared_flags import shift_runtime

pytestmark=pytest.mark.game


def test_motion_uses_preclock_scales_and_one_clock_for_both_axes(shift_runtime,tmp_path):
    meta,il=shift_runtime;m=meta.methods[28798];lines=[];Emitter(il,str(tmp_path/'out')).emit_method(m,meta.typedefs[m.declaring],lines,'    ')
    src='''using System;using System.Linq;using System.Collections.Generic;using UnityEngine;
foreach(string mode in new[]{"ok","inactive","no animator","delta","clock","no body","velocity","no setter","set"})foreach(float dt in new[]{.125f,0f,-.25f,float.NaN}){
 var c=new ObiCharacter{m_IsGrounded=mode!="inactive",m_MoveSpeedMultiplier=0};var a=new Animator();var first=new Rigidbody();var last=new Rigidbody();var log=new List<string>();var err=new ApplicationException();
 void Step(string s){log.Add(s);if(s==mode)throw err;}float y=BitConverter.Int32BitsToSingle(unchecked((int)0xffc12345));bool Same(float u,float v)=>BitConverter.SingleToInt32Bits(u)==BitConverter.SingleToInt32Bits(v);
 c.m_Animator=mode=="no animator"?null:a;c.m_Rigidbody=null;a.Read=()=>{Step("delta");c.m_MoveSpeedMultiplier=1.75f;return new Vector3{x=-3.25f,y=999,z=7.5f};};
 Time.Read=()=>{Step("clock");Time.Read=()=>throw new Exception("second time sample");c.m_Rigidbody=mode=="no body"?null:first;c.m_MoveSpeedMultiplier=123;return dt;};
 first.Read=()=>{Step("velocity");c.m_MoveSpeedMultiplier=-321;c.m_Rigidbody=mode=="no setter"?null:last;return new Vector3{x=25,y=y,z=-90};};first.Write=_=>throw new Exception("used old receiver");
 last.Write=v=>{if(!Same(v.y,y)||!Same(v.x,-3.25f*1.75f/dt)||!Same(v.z,7.5f*1.75f/dt))throw new Exception("wrong lanes");Step("set");};
 Exception ex=null;try{c.Run();}catch(Exception e){ex=e;}string[] ops={"delta","clock","velocity","set"};int n=mode switch{"inactive" or "no animator"=>0,"no body"=>2,"no setter"=>3,"ok"=>4,_=>Array.IndexOf(ops,mode)+1};
 if(!log.SequenceEqual(ops.Take(n))||(mode.StartsWith("no ")?ex is not NullReferenceException:mode is "ok" or "inactive"?ex!=null:!ReferenceEquals(ex,err)))throw new Exception(mode+":"+string.Join(',',log),ex);
}
Console.WriteLine("whole motion callback: post-animator scale, single clock, later velocity receiver reload, exact axes and fault order");
namespace UnityEngine{public struct Vector3{public float x,y,z;}public class Rigidbody{public Func<Vector3> Read;public Action<Vector3> Write;public Vector3 linearVelocity{get=>Read();set=>Write(value);}}public class Animator{public Func<Vector3> Read;public Vector3 deltaPosition=>Read();}public static class Time{public static Func<float> Read;public static float deltaTime=>Read();}}
class ObiCharacter{public bool m_IsGrounded;public Animator m_Animator;public Rigidbody m_Rigidbody;public float m_MoveSpeedMultiplier;public void Run()=>OnAnimatorMove();\n'''+ '\n'.join(lines)+'\n}'
    p=tmp_path/'r';p.mkdir();(p/'Program.cs').write_text(src,encoding='utf8');print(run_case(tmp_path,p))


@pytest.mark.parametrize('bad',['scale receiver','different float','different divisor','bypass second scale','hidden argument'])
def test_each_product_and_its_single_sample_are_proven(shift_runtime,monkeypatch,bad):
    from il2cpp import Lifter,Decompiler
    from il2cpp.two_lane_scale import operand_samples
    from iced_x86 import Register as R
    meta,il=shift_runtime;m=meta.methods[28798];td=meta.typedefs[m.declaring];d=Decompiler(Lifter(il));d.lift_method(m,td);bs=d.L._blocks;scan=lambda:operand_samples(d.L,m,td,bs,())
    a,p=scan();assert set(a)=={0x18062d4e0,0x18062d4eb} and set(p)=={0x18062d4f2}
    ip={'scale receiver':0x18062d4e0,'different float':0x18062d4e0,'different divisor':0x18062d4fb,'bypass second scale':0x18062d4ad,'hidden argument':0x18062d4f0}[bad]
    b,j=next((b,j) for b in bs for j,i in enumerate(b.insns) if i.ip==ip);i=b.insns[j].copy()
    if bad=='scale receiver':i.memory_base=R.RDI
    elif bad=='different float':i.memory_displacement=0x50
    elif bad=='different divisor':i.op1_register=R.XMM1
    elif bad=='bypass second scale':i.near_branch64=0x18062d4f0
    else:i.op1_register=R.EDX
    monkeypatch.setattr(b,'insns',b.insns[:j]+[i]+b.insns[j+1:]);assert scan()==({},{})


def test_two_independent_scale_fields_during_reentrant_clock(shift_runtime,tmp_path,monkeypatch):
    meta,il=shift_runtime;m=meta.methods[28798];em=Emitter(il,str(tmp_path/'out'));original=em.decompiler._decode
    def decode(md):
        s,skip=original(md)
        if md.index==m.index:
            s=list(s);j=next(j for j,i in enumerate(s) if i.ip==0x18062d4e0);q=s[j].copy();q.memory_displacement=0x38;s[j]=q
        return s,skip
    monkeypatch.setattr(em.decompiler,'_decode',decode);out=[];em.emit_method(m,meta.typedefs[m.declaring],out,'    ')
    src='''using System;using System.Collections.Generic;using UnityEngine;
var c=new C();int phase=0;var writes=new List<Vector3>();c.m_Animator=new Animator();c.m_Rigidbody=new Rigidbody();c.m_Rigidbody.Write=writes.Add;c.m_IsGrounded=true;
c.m_Animator.Read=()=>{c.m_MoveSpeedMultiplier=phase==0?2f:-3f;c.m_AnimSpeedMultiplier=phase==0?-.5f:4f;return new Vector3{x=8,y=9,z=2};};
Time.Read=()=>{if(++phase==1){c.Run();return .25f;}if(phase!=2)throw new Exception("repeated clock");c.m_MoveSpeedMultiplier=0;c.m_AnimSpeedMultiplier=0;return 2f;};c.Run();
if(writes.Count!=2||writes[0].x!=-12f||writes[0].y!=5f||writes[0].z!=4f||writes[1].x!=64f||writes[1].y!=5f||writes[1].z!=-4f)throw new Exception("lost outer or inner samples");Console.WriteLine("reentrant clock preserved independent scales on both activations");
namespace UnityEngine{public struct Vector3{public float x,y,z;}public class Animator{public Func<Vector3> Read;public Vector3 deltaPosition=>Read();}public class Rigidbody{public Action<Vector3> Write;public Vector3 linearVelocity{get=>new Vector3{y=5f};set=>Write(value);}}public static class Time{public static Func<float> Read;public static float deltaTime=>Read();}}
class C{public bool m_IsGrounded;public float m_MoveSpeedMultiplier,m_AnimSpeedMultiplier;public Animator m_Animator;public Rigidbody m_Rigidbody;public void Run()=>OnAnimatorMove();\n'''+ '\n'.join(out)+'\n}'
    r=tmp_path/'r';r.mkdir();(r/'Program.cs').write_text(src,encoding='utf8');print(run_case(tmp_path,r))
