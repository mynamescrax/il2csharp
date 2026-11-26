"""Compile the three emitted pitch callbacks with an observable draw and setter."""
import re

import pytest
from iced_x86 import Decoder
from dotnet_case import run_case
from il2cpp import Lifter,Decompiler
from il2cpp.emitter import Emitter
from il2cpp.float_setter import _alias,float_setters
from test_game_shift_shared_flags import shift_runtime

pytestmark=pytest.mark.game


def test_pitch_uses_one_draw_and_original_receiver(shift_runtime,tmp_path):
    m,il=shift_runtime;md=m.methods[24420];td=m.typedefs[md.declaring];out=tmp_path/'out'
    em=Emitter(il,str(out));em._emit_one_top(td,m.images[md.image],td.name);s=next(out.rglob('ChangePitchPerLoop.cs')).read_text(encoding='utf8')
    methods=[re.search(r'^    (?:public|private) void '+n+r'\(\)\n.*?^    }',s,re.S|re.M)[0] for n in ('ForceChangePitch','OnEnable','FixedUpdate')]
    assert all('sub_' not in method for method in methods)
    runner=tmp_path/'runner';runner.mkdir();(runner/'Program.cs').write_text('''using System;using System.Linq;using System.Collections.Generic;using UnityEngine;using Random=UnityEngine.Random;
foreach(var which in new[]{"force","enable","tick"})
foreach(var mode in new[]{"ok","range throws","setter throws","null","no loop","play throws"}){
    var log=new List<string>();var c=new ChangePitchPerLoop();var a=new AudioSource();var b=new AudioSource();var fault=new ApplicationException(mode);
    void Step(string s){log.Add(s);if(mode==s+" throws")throw fault;}
    c.audio=which=="enable"?null:a;c.changePitchAtStart=true;c.minPitch=0.75f;c.maxPitch=1.25f;
    c.Lookup=()=>{Step("lookup");return mode=="null"?null:a;};
    a.Write=v=>{if(v!=0.9375f)throw new Exception("wrong float");Step("setter");c.dontLoop=mode=="no loop";};b.Played=()=>Step("play");
    Random.Draw=(lo,hi)=>{if(lo!=0.75f||hi!=1.25f)throw new Exception("wrong range");Step("range");c.audio=b;return 0.9375f;};
    if(which=="tick"){
        a.Read=()=>{Step("playing");return false;};c.Tick();if(c.Latch||log.Count!=1)throw new Exception("premature draw");
        a.Read=()=>{Step("playing");return true;};c.Tick();if(!c.Latch||log.Count!=2)throw new Exception("no latch");
        a.Read=()=>{Step("playing");return false;};log.Clear();}
    if(mode=="null"&&which!="enable")c.audio=null;
    string[] expected=which switch {"force"=>new[]{"range","setter"},"enable"=>new[]{"lookup","range","setter"},_=>new[]{"playing","range","setter","play"}};
    Type error=null;
    if(mode=="null"){expected=which=="tick"?Array.Empty<string>():expected.TakeWhile(x=>x!="setter").ToArray();error=typeof(NullReferenceException);}
    else if(mode=="no loop" && which=="tick")expected=expected.Take(3).ToArray();
    else if(mode.EndsWith(" throws")){int j=Array.IndexOf(expected,mode.Split(' ')[0]);if(j>=0){expected=expected.Take(j+1).ToArray();error=typeof(ApplicationException);}}
    Exception thrown=null;try{if(which=="force")c.ForceChangePitch();else if(which=="enable")c.Enable();else c.Tick();}catch(Exception ex){thrown=ex;}
    if(thrown?.GetType()!=error||error==typeof(ApplicationException)&&!ReferenceEquals(fault,thrown)||!log.SequenceEqual(expected)||c.Latch!=(which=="tick"&&error!=null))throw new Exception(which+"/"+mode+": "+string.Join(",",log)+" "+thrown);
    if(mode=="ok")Console.WriteLine(which+": "+string.Join(",",log)+"; one draw to original receiver");
}
namespace UnityEngine {
class Component{public Func<AudioSource> Lookup;public T GetComponent<T>()where T:Component=>Lookup() as T;}
class AudioSource:Component {public Action<float> Write;public Func<bool> Read;public Action Played;
public bool isPlaying=>Read();public float pitch{set=>Write(value);}public void Play()=>Played();}
class Random{public static Func<float,float,float> Draw;public static float Range(float lo,float hi)=>Draw(lo,hi);}}
class ChangePitchPerLoop:Component{public AudioSource audio;public float minPitch,maxPitch;public bool dontLoop,changePitchAtStart;private bool justStopPlaying;
public bool Latch=>justStopPlaying;public void Enable()=>OnEnable();public void Tick()=>FixedUpdate();\n'''+ '\n'.join(methods)+'\n}',encoding='utf8')
    print(run_case(tmp_path,runner).strip())


@pytest.mark.parametrize('defect',['wrong injected signature','different cache cell','wrong float lane','different null receiver','cctor'])
def test_float_setter_needs_icall_and_caller_agreement(shift_runtime,monkeypatch,defect):
    m,il=shift_runtime;d=Decompiler(Lifter(il));md=m.methods[24420];d.lift_method(md,m.typedefs[md.declaring]);bs=d.L._blocks
    target=0x182b8eb50;sink=0x18069b64f;plans=lambda:float_setters(d.L,md,bs,())
    assert sink in plans()
    if defect=='cctor':
        td=m.typedefs[m.methods[127198].declaring];monkeypatch.setattr(td,'bitfield',td.bitfield | (1<<3))
    elif defect=='different null receiver':
        b=bs[0];i=b.insns[-2];alt=Decoder(64,bytes.fromhex('4885f6'),ip=i.ip).decode();assert alt.len==i.len
        monkeypatch.setattr(b,'insns',b.insns[:-2]+[alt]+b.insns[-1:])
    elif defect=='wrong injected signature':monkeypatch.setitem(il.icall_cells,0x183e98538,'Different::Call(System.IntPtr,System.Single)')
    else:
        read=il.bin.read
        def changed(a,n):
            raw=read(a,n)
            if a==target:
                raw=bytearray(raw);raw[(0x182b8ebc9 if defect=='different cache cell' else 0x182b8ebcf)-a]^=1;return bytes(raw)
            return raw
        monkeypatch.setattr(il.bin,'read',changed)
    assert sink not in plans()
