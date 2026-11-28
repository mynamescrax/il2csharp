import pytest
from dotnet_case import run_case
from il2cpp.emitter import Emitter
from test_game_shift_shared_flags import shift_runtime

pytestmark=pytest.mark.game


def test_camera_shake_and_recoil_keep_split_sret_store_widths(shift_runtime,tmp_path):
    meta,il=shift_runtime;em=Emitter(il,str(tmp_path/'out'));methods=[]
    for mi in (24311,27005):
        m=meta.methods[mi];lines=[];em.emit_method(m,meta.typedefs[m.declaring],lines,'    ');methods.append('\n'.join(lines))
    src='''using System;using System.Linq;using System.Collections.Generic;using UnityEngine;
float F(uint b)=>BitConverter.Int32BitsToSingle(unchecked((int)b));
bool Same(Vector3 a,Vector3 b)=>new[]{a.x,a.y,a.z}.Select(BitConverter.SingleToInt32Bits).SequenceEqual(new[]{b.x,b.y,b.z}.Select(BitConverter.SingleToInt32Bits));
var seed=new Vector3{x=10,y=20,z=30};var sample=new Vector3{x=F(0x80000000),y=F(0xffc06789),z=F(1)};
foreach(bool shake in new[]{true,false})foreach(string mode in new[]{"ok","null","lookup","get","to","positive"}){
    if(!shake&&mode=="lookup"||shake&&mode is "positive" or "to")continue;
    var sh=new CameraShake{originalPos=seed};var rc=new Recoil{originalRotation=seed};var tr=new Transform();var trace=new List<string>();var ex=new ApplicationException();
    void Step(string s){trace.Add(s);if(mode==s)throw ex;}
    sh.Get=()=>{Step("lookup");return mode=="null"?null:tr;};tr.Pos=()=>{Step("get");return sample;};
    var rotation=new Quaternion{x=1,y=2,z=3,w=4};rc.recoilHolder=mode=="null"?null:tr;
    tr.Rot=()=>{Step("get");rc.recoilHolder=null;return rotation;};var radians=new Vector3{x=.125f,y=-1f,z=.5f};
    Quaternion.To=q=>{Step("to");if(q.x!=1||q.y!=2||q.z!=3||q.w!=4)throw new Exception("bad rotation");return radians;};
    Quaternion.Positive=v=>{Step("positive");if(v.x!=radians.x*57.29578f||v.y!=radians.y*57.29578f||v.z!=radians.z*57.29578f)throw new Exception("bad degrees");return sample;};
    Exception fault=null;try{if(shake)sh.Run();else rc.Run();}catch(Exception e){fault=e;}
    var order=shake?new[]{"lookup","get"}:new[]{"get","to","positive"};int n=mode=="null"?(shake?1:0):mode=="ok"?order.Length:Array.IndexOf(order,mode)+1;
    if(!trace.SequenceEqual(order.Take(n))||!Same(shake?sh.originalPos:rc.originalRotation,mode=="ok"?sample:seed)||
      (mode=="ok"?fault!=null:mode=="null"?fault is not NullReferenceException:!ReferenceEquals(fault,ex)))throw new Exception(shake+"/"+mode+":"+string.Join(',',trace),fault);
}
Console.WriteLine("both complete vector field copies: bitwise components, quaternion inputs, faults before stores passed");
namespace UnityEngine{public struct Vector3{public float x,y,z;}public struct Quaternion{public float x,y,z,w;public static Func<Quaternion,Vector3> To;public static Func<Vector3,Vector3> Positive;public static Vector3 Internal_ToEulerRad(Quaternion q)=>To(q);public static Vector3 Internal_MakePositive(Vector3 v)=>Positive(v);}public class Transform{public Func<Vector3> Pos;public Func<Quaternion> Rot;public Vector3 localPosition=>Pos();public Quaternion localRotation=>Rot();}}
class CameraShake{public Func<Transform> Get;public Transform transform=>Get();public Vector3 originalPos;public void Run()=>OnEnable();\n'''+methods[0]+'\n}class Recoil{public Transform recoilHolder;public Vector3 originalRotation;public void Run()=>Start();\n'+methods[1]+'\n}'
    r=tmp_path/'r';r.mkdir();(r/'Program.cs').write_text(src,encoding='utf8');print(run_case(tmp_path,r))


@pytest.mark.parametrize('bad',['wrong echo','wrong Z offset','same register','different destination','foreign store','wrong return','incorrect deallocation','scratch in epilogue'])
def test_field_pair_accepts_only_complete_same_epoch_same_object_copy(shift_runtime,monkeypatch,bad):
    from il2cpp import Lifter,Decompiler
    from il2cpp.split_field import split_field_sites
    from iced_x86 import Register as R
    meta,il=shift_runtime;md=meta.methods[24311];td=meta.typedefs[md.declaring];d=Decompiler(Lifter(il));d.lift_method(md,td);bs=d.L._blocks
    find=lambda:split_field_sites(d.L,md,td,bs,());assert len(find())==4
    if bad=='wrong return':monkeypatch.setitem(il.addr_candidates,0x182c04be0,[('method',54740)])
    else:
        ip={'wrong echo':0x1805fef75,'wrong Z offset':0x1805fef79,'same register':0x1805fef81,'different destination':0x1805fef7c,'foreign store':0x1805fef81,'incorrect deallocation':0x1805fef84,'scratch in epilogue':0x1805fef84}[bad]
        b,j=next((b,j) for b in bs for j,i in enumerate(b.insns) if i.ip==ip);i=b.insns[j].copy()
        if bad=='wrong echo':i.memory_base=R.RDX
        elif bad=='wrong Z offset':i.memory_displacement=4
        elif bad=='same register':i.op1_register=R.EDX
        elif bad=='different destination':i.memory_displacement+=4
        elif bad=='incorrect deallocation':i.immediate8=0x38
        elif bad=='scratch in epilogue':
            from iced_x86 import Decoder
            i=Decoder(64,bytes.fromhex('2e4801cc'),ip=ip).decode();assert i.len==b.insns[j].len
        else:i.memory_base=R.RDI
        monkeypatch.setattr(b,'insns',b.insns[:j]+[i]+b.insns[j+1:])
    assert not find()
