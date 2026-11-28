import pytest
from dotnet_case import run_case
from il2cpp.emitter import Emitter
from test_game_shift_shared_flags import shift_runtime

pytestmark=pytest.mark.game


def test_teleport_dispatch_keeps_actor_before_sampling_target(shift_runtime,tmp_path):
    meta,il=shift_runtime;m=meta.methods[23919];out=[];Emitter(il,str(tmp_path/'out')).emit_method(m,meta.typedefs[m.declaring],out,'    ')
    s='''using System;using System.Collections.Generic;using System.Linq;using UnityEngine;using Obi;
foreach(string mode in new[]{"ok","null actor","null first","position","null next","rotation","virtual","originally null then installed"}){
 var c=new ObiActorTeleport();var p=new Transform();var q=new Transform();var a=new Derived();var b=new Derived();var trace=new List<string>();var err=new ApplicationException();void Step(string where){trace.Add(where);if(mode==where)throw err;}
 c.actor=mode is "null actor" or "originally null then installed"?null:a;c.target=mode=="null first"?null:p;float negZero=BitConverter.Int32BitsToSingle(int.MinValue);float z=BitConverter.Int32BitsToSingle(unchecked((int)0xffc12345));
 p.Pos=()=>{Step("position");if(mode!="null actor")c.actor=b;c.target=mode=="null next"?null:q;return new Vector3{x=negZero,y=1.25f,z=z};};p.Rot=()=>throw new Exception("stale transform");q.Rot=()=>{Step("rotation");return new Quaternion{x=3,y=4,z=5,w=-.25f};};
 a.Go=(v,r)=>{if(BitConverter.SingleToInt32Bits(v.x)!=int.MinValue||v.y!=1.25f||BitConverter.SingleToInt32Bits(v.z)!=BitConverter.SingleToInt32Bits(z)||(r.x,r.y,r.z,r.w)!=(3f,4f,5f,-.25f))throw new Exception("wrong arguments");Step("virtual");return default;};b.Go=(_,__)=>throw new Exception("used replacement actor");
 Exception ex=null;try{c.Run();}catch(Exception e){ex=e;}string[] ops={"position","rotation","virtual"};int n=mode switch{"null first"=>0,"position" or "null next"=>1,"null actor" or "originally null then installed" or "rotation"=>2,_=>3};
 if(!trace.SequenceEqual(ops.Take(n))||(mode.StartsWith("null")||mode=="originally null then installed"?ex is not NullReferenceException:mode=="ok"?ex!=null:!ReferenceEquals(ex,err)))throw new Exception(mode+":"+string.Join(',',trace),ex);
}
Console.WriteLine("whole actor teleport: prepared receiver, late target reloads, virtual override and faults");
namespace UnityEngine{public struct Vector3{public float x,y,z;}public struct Quaternion{public float x,y,z,w;}[System.Runtime.InteropServices.StructLayout(System.Runtime.InteropServices.LayoutKind.Sequential,Size=64)]public struct Matrix4x4{}public class Transform{public Func<Vector3> Pos;public Func<Quaternion> Rot;public Vector3 position=>Pos();public Quaternion rotation=>Rot();}}
namespace Obi{public class ObiActor{public virtual Matrix4x4 Teleport(Vector3 p,Quaternion q)=>throw new Exception("lost dispatch");}}class Derived:ObiActor{public Func<Vector3,Quaternion,Matrix4x4> Go;public override Matrix4x4 Teleport(Vector3 p,Quaternion q)=>Go(p,q);}
class ObiActorTeleport{public ObiActor actor;public Transform target;public void Run()=>Teleport();\n'''+ '\n'.join(out)+'\n}'
    p=tmp_path/'r';p.mkdir();(p/'Program.cs').write_text(s,encoding='utf8');print(run_case(tmp_path,p))


@pytest.mark.parametrize('bad',['other sret','out of frame','stale info','wrong info home','wrong receiver','use other class','wrong hidden arg'])
def test_dispatch_receipts_require_slot_pair_and_shifted_receiver(shift_runtime,monkeypatch,bad):
    from il2cpp import Lifter,Decompiler
    from il2cpp.buffered_dispatch import buffered_receivers
    from iced_x86 import Register as R
    meta,il=shift_runtime;m=meta.methods[23919];td=meta.typedefs[m.declaring];d=Decompiler(Lifter(il));d.lift_method(m,td);bs=d.L._blocks
    scan=lambda:buffered_receivers(d.L,m,td,bs,());assert set(scan())=={0x180521392,0x180521399,0x1805213b3};ip={'other sret':0x1805213ff,'out of frame':0x1805213ff,'stale info':0x18052140a,'wrong info home':0x180521411,'wrong receiver':0x1805213f7,'use other class':0x1805213e1,'wrong hidden arg':0x1805213a6}[bad]
    b,j=next((b,j) for b in bs for j,i in enumerate(b.insns) if i.ip==ip);i=b.insns[j].copy()
    if bad=='other sret':i.memory_displacement=0x40
    elif bad=='out of frame':i.memory_displacement=0x90
    elif bad=='wrong hidden arg':i.op0_register=i.op1_register=R.R9D
    elif bad in ('stale info','wrong info home'):i.memory_displacement+=8
    elif bad=='wrong receiver':i.op1_register=R.RBX
    else:i.memory_base=R.RBX
    monkeypatch.setattr(b,'insns',b.insns[:j]+[i]+b.insns[j+1:]);assert not scan()
