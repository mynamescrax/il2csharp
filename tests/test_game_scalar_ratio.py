import pytest
from il2cpp.emitter import Emitter
from dotnet_case import run_case
from test_game_shift_shared_flags import shift_runtime

pytestmark=pytest.mark.game


def test_aspect_check_converts_both_signed_dwords_before_division(shift_runtime,tmp_path):
    meta,il=shift_runtime;em=Emitter(il,str(tmp_path/'out'));m=meta.methods[24195];lines=[];em.emit_method(m,meta.typedefs[m.declaring],lines,'    ')
    src='''using System;using System.Collections.Generic;using System.Linq;using UnityEngine;
foreach(var (initial,late,h,reference) in new[]{(1920,1920,1080,1.5f),(1920,500,1080,1f),(-3,-3,2,-1.25f),(0,0,1,float.NaN),(5,5,0,1f),(1,1,-1,0f),(16777216,16777216,16777217,1f)})
foreach(string mode in new[]{"ok","width","height","set","null"}) {
 var c=new AdaptiveFovByAspect{_lastH=42,_lastW=17,referenceAspect=reference,normalFov=90,squashedFov=50};var cam=new Camera();var trace=new List<string>();var ex=new ApplicationException();
 void Step(string s){trace.Add(s);if(mode==s)throw ex;}
 Screen.W=()=>{Step("width");return initial;};Screen.H=()=>{Step("height");if(c._lastW!=initial)throw new Exception("width not recorded before callback");c._lastW=late;c._cam=mode=="null"?null:cam;return h;};
 cam.Put=v=>{if(c._lastH!=h||v!=(reference>(float)late/(float)h?50f:90f))throw new Exception("wrong fieldOfView");Step("set");};Exception fault=null;try{c.Run();}catch(Exception e){fault=e;}
 var expected=mode=="width"?new[]{"width"}:mode=="height"||h<=0||mode=="null"?new[]{"width","height"}:new[]{"width","height","set"};
 if(!trace.SequenceEqual(expected)||c._lastW!=(mode=="width"?17:mode=="height"?initial:late)||c._lastH!=(mode is "width" or "height"?42:h)||
    (mode is "width" or "height" || h>0&&mode=="set"?!ReferenceEquals(fault,ex):h>0&&mode=="null"?fault is not NullReferenceException:fault!=null))throw new Exception($"{initial}/{late}/{h}/{reference}/{mode}: {string.Join(',',trace)}",fault);
}
Console.WriteLine("whole camera aspect callback: fractional ratios, unordered inputs, height mutation, setter fault order");
namespace UnityEngine{public class Camera{public Action<float> Put;public float fieldOfView{set=>Put(value);}}public static class Screen{public static Func<int> W,H;public static int width=>W();public static int height=>H();}}
class AdaptiveFovByAspect{public int _lastW,_lastH;public float referenceAspect,normalFov,squashedFov;public Camera _cam;public void Run()=>ApplyFovIfNeeded();\n'''+ '\n'.join(lines)+'\n}'
    r=tmp_path/'r';r.mkdir();(r/'Program.cs').write_text(src,encoding='utf8');print(run_case(tmp_path,r))


@pytest.mark.parametrize('change',['wrong field','wide source','upper lane read','unknown height','different convert'])
def test_ratio_proof_rejects_lane_or_definition_substitution(shift_runtime,monkeypatch,change):
    from iced_x86 import Register as R, Decoder
    from il2cpp import Decompiler,Lifter
    from il2cpp.scalar_ratio import ratio_sites
    meta,il=shift_runtime;m=meta.methods[24195];td=meta.typedefs[m.declaring];d=Decompiler(Lifter(il));d.lift_method(m,td);bs=d.L._blocks
    find=lambda:ratio_sites(d.L,m,td,bs,());a,c=find();assert len(a)==5 and len(c)==2
    if change=='unknown height':
        va=0x182baf110;monkeypatch.setitem(il.addr_candidates,va,[])
    else:
        ip={'wrong field':0x1805f64a1,'wide source':0x1805f64af,'upper lane read':0x1805f64c2,'different convert':0x1805f64b6}[change]
        b,j=next((b,j) for b in bs for j,i in enumerate(b.insns) if i.ip==ip);i=b.insns[j].copy()
        if change=='wrong field':i.memory_displacement=0x30  # managed reference, not a dword field
        elif change=='wide source':
            # Decode MOVQ on its own boundary; a changed width is not a
            # valid alternate MOVD, even when its source register is RAX.
            i=Decoder(64,bytes.fromhex('f30f7ec0'),ip=ip).decode();assert str(i)=='movq xmm0,xmm0' and i.len==b.insns[j].len
        elif change=='different convert':i.op1_register=R.XMM2
        else:
            # The native branch arm now observes the full quotient, not
            # merely its low scalar. Keep the same instruction boundary.
            code=bytes.fromhex('660f70ca27');assert len(code)==i.len
            i=Decoder(64,code,ip=ip).decode()
        monkeypatch.setattr(b,'insns',b.insns[:j]+[i]+b.insns[j+1:])
    assert find()==({},{})
