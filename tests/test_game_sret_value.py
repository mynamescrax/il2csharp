import pytest
from iced_x86 import Decoder,Register as R
from dotnet_case import run_case
from il2cpp import Lifter,Decompiler
from il2cpp.emitter import Emitter
from il2cpp.sret_value import copied_values
from test_game_shift_shared_flags import shift_runtime

pytestmark=pytest.mark.game


def test_finale_interpolation_keeps_both_values_and_both_receivers(shift_runtime,tmp_path):
    meta,il=shift_runtime;md=meta.methods[25327];lines=[];Emitter(il,str(tmp_path/'out')).emit_method(md,meta.typedefs[md.declaring],lines,'    ')
    src='''using System;using System.Linq;using System.Collections.Generic;using UnityEngine;
string[] normal={"posA","posB","time1","moveA","rotC","rotD","time2","lerp","turnC"};
foreach(var mode in normal.Concat(new[]{"normal","skip","first null","B null","C null","D null"})){
 var c=new FinaleStartCutscene{startedCutscene=mode=="skip"};var a=new Transform();var b=new Transform();var y=new Transform();var z=new Transform();var poison=new Transform();var trace=new List<string>();var fail=new ApplicationException();
 void Step(string s){trace.Add(s);if(mode==s)throw fail;}var from=new Vector3(1.5f,2.75f,-4.0f);var dest=new Vector3(8.5f,-9.25f,-3.5f);var alpha=0.03125f*15f;
 float F(uint bits)=>BitConverter.Int32BitsToSingle(unchecked((int)bits));var l=new Quaternion{x=F(0x80000000),y=1f,z=5f,w=F(0xffc01234)};var r=new Quaternion{x=2f,y=F(0x7fc00123),z=9f,w=F(1)};var ret=new Quaternion{x=4,y=-5,z=6,w=-7};
 bool Eq(Quaternion v,Quaternion q)=>new[]{v.x,v.y,v.z,v.w}.Select(BitConverter.SingleToInt32Bits).SequenceEqual(new[]{q.x,q.y,q.z,q.w}.Select(BitConverter.SingleToInt32Bits));
 c.cam=mode=="first null"?null:a;c.camStartPoint=poison;a.GetP=()=>{Step("posA");c.cam=poison;c.camStartPoint=mode=="B null"?null:b;return from;};
 b.GetP=()=>{Step("posB");return dest;};a.PutP=v=>{Step("moveA");if(v.x!=(dest.x-from.x)*alpha+from.x||v.y!=(dest.y-from.y)*alpha+from.y||v.z!=(dest.z-from.z)*alpha+from.z)throw new Exception("wrong position");c.cam=mode=="C null"?null:y;};
 y.GetQ=()=>{Step("rotC");c.cam=poison;c.camStartPoint=mode=="D null"?null:z;return l;};z.GetQ=()=>{Step("rotD");c.camStartPoint=null;return r;};
 int n=0;Time.Read=()=>{Step("time"+(++n));return n==1?0.03125f:0.125f;};Quaternion.Mix=(v,q,t)=>{Step("lerp");if(!Eq(v,l)||!Eq(q,r)||t!=0.125f*15)throw new Exception("wrong rotation args");c.cam=null;return ret;};
 y.PutQ=q=>{Step("turnC");if(!Eq(q,ret))throw new Exception("wrong setter value");};Exception ex=null;try{c.Run();}catch(Exception e){ex=e;}
 int count=mode switch{"skip" or "first null"=>0,"B null"=>1,"C null"=>4,"D null"=>5,"normal"=>9,_=>Array.IndexOf(normal,mode)+1};
 if(!trace.SequenceEqual(normal.Take(count))||(mode.EndsWith("null")?ex is not NullReferenceException:mode is "normal" or "skip"?ex!=null:!ReferenceEquals(ex,fail)))throw new Exception(mode+":"+string.Join(',',trace),ex);}
Console.WriteLine("complete finale update: distinct getters, exact endpoints, separate time reads, receiver replacements and exceptions passed");
namespace UnityEngine{public struct Vector3{public float x,y,z;public Vector3(float a,float b,float c){x=a;y=b;z=c;}}public struct Quaternion{public float x,y,z,w;public static Func<Quaternion,Quaternion,float,Quaternion> Mix;public static Quaternion Lerp(Quaternion a,Quaternion b,float t)=>Mix(a,b,t);}public static class Time{public static Func<float> Read;public static float deltaTime=>Read();}public class Transform{public Func<Vector3> GetP;public Action<Vector3> PutP;public Func<Quaternion> GetQ;public Action<Quaternion> PutQ;public Vector3 position{get=>GetP();set=>PutP(value);}public Quaternion rotation{get=>GetQ();set=>PutQ(value);}}}
class FinaleStartCutscene{public Transform cam,camStartPoint;public bool startedCutscene;public void Run()=>Update();\n'''+ '\n'.join(lines)+'\n}'
    runner=tmp_path/'runner';runner.mkdir();(runner/'Program.cs').write_text(src,encoding='utf8');print(run_case(tmp_path,runner).strip())


@pytest.mark.parametrize('case',['wrong echo','clobber echo','partial spill','wrong setter receiver','adjacent foreign unwind'])
def test_whole_value_needs_echo_and_whole_uses(shift_runtime,monkeypatch,case):
    meta,il=shift_runtime;md=meta.methods[25327];td=meta.typedefs[md.declaring];d=Decompiler(Lifter(il));d.lift_method(md,td);bs=d.L._blocks
    f=lambda:copied_values(d.L,md,td,bs,());fields,loads=f();a,z=sorted(loads);pos,rot=sorted(fields);assert (len(fields),len(loads))==(2,2)
    if case=='adjacent foreign unwind':
        from bisect import bisect_left
        j=bisect_left(il._eh4_begins,md.addr-il.bin.image_base);ui=il.bin.image_base+il._eh4_entries[j+2][2];h=il.bin.read(ui,4);ref=ui+4+2*((h[2]+1)&~1);read=il.bin.read
        monkeypatch.setattr(il.bin,'read',lambda p,n:b'\xff'*12 if p==ref and n==12 else read(p,n));assert f()==({},{});return
    ip={'wrong echo':a,'clobber echo':a-4}.get(case)
    if case=='wrong setter receiver':ip=next(i.ip for b in bs for i in b.insns if i.ip>0x1806e475d and str(i)=='mov rcx,rdi')
    if case=='partial spill':ip=next(i.ip for b in bs for i in b.insns if str(i)=='movdqa [rsp+40h],xmm8')
    b,j=next((b,j) for b in bs for j,i in enumerate(b.insns) if i.ip==ip);i=b.insns[j].copy()
    if case=='wrong echo':i.memory_base=R.RBX
    elif case=='clobber echo':i.op0_register=R.RAX
    elif case=='partial spill':
        alt=Decoder(64,bytes.fromhex('f2440f11442440'),ip=ip).decode();assert alt.len==i.len;i=alt
    else:i.op1_register=R.RBX
    monkeypatch.setattr(b,'insns',b.insns[:j]+[i]+b.insns[j+1:]);fields,loads=f()
    if case=='wrong setter receiver':assert pos in fields and rot not in fields
    else:assert a not in loads
