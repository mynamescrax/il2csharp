import pytest
from dotnet_case import run_case
from il2cpp.emitter import Emitter
from test_game_shift_shared_flags import shift_runtime

pytestmark=pytest.mark.game


def test_footstep_and_landing_save_receiver_and_array_but_reload_selected_clip(shift_runtime,tmp_path):
    meta,il=shift_runtime;em=Emitter(il,str(tmp_path/'out'));lines=[]
    for mi in (23714,23715):
        m=meta.methods[mi];em.emit_method(m,meta.typedefs[m.declaring],lines,'    ')
    src='''using System;using System.Linq;using System.Collections.Generic;using UnityEngine;
foreach(bool landing in new[]{false,true})foreach(string mode in new[]{"ok","null clip","skip","no array","empty","no receiver","index too big","index negative","both invalid","check fault","draw fault","play fault"}){
 var owner=new Driver();var checkedSource=new AudioSource();var playing=new AudioSource();var poison=new AudioSource();var initial=new AudioClip();var changed=new AudioClip();var clips=new AudioClip[]{initial,initial};
 var err=new ApplicationException();var trace=new List<string>();float volume=BitConverter.Int32BitsToSingle(unchecked((int)0xffc01055));
 void Assign(AudioClip[] x){if(landing)owner.LandClips=x;else owner.StepClips=x;}
 void Step(string tag){trace.Add(tag);if(mode==tag+" fault")throw err;}
 owner.StepSource=checkedSource;Assign(null);
 AudioSource.Eq=(a,b)=>{if(!ReferenceEquals(a,checkedSource)||b is not null)throw new Exception("wrong guard source");Step("check");owner.StepSource=mode is "no receiver" or "both invalid"?null:playing;Assign(mode=="empty"?Array.Empty<AudioClip>():mode=="no array"?null:clips);return mode=="skip";};
 UnityEngine.Random.Pick=(lo,hi)=>{if(lo!=0||hi!=2)throw new Exception("wrong range");Step("draw");owner.StepSource=poison;Assign(new[]{initial});clips[1]=mode=="null clip"?null:changed;return mode=="index too big"||mode=="both invalid"?2:mode=="index negative"?-1:1;};
 playing.Play=(clip,v)=>{if(!ReferenceEquals(clip,mode=="null clip"?null:changed)||BitConverter.SingleToInt32Bits(volume)!=BitConverter.SingleToInt32Bits(v))throw new Exception("wrong element or playback volume");Step("play");};
 poison.Play=(_,_)=>throw new Exception("stale source");Exception fault=null;try{owner.Run(landing,volume);}catch(Exception e){fault=e;}
 var expected=mode is "skip" or "check fault" or "no array" or "empty"?new[]{"check"}:mode is "ok" or "null clip" or "play fault"?new[]{"check","draw","play"}:new[]{"check","draw"};
 if(!trace.SequenceEqual(expected)||(mode is "no array" or "no receiver"?fault is not NullReferenceException:mode is "index too big" or "index negative" or "both invalid"?fault is not IndexOutOfRangeException:mode.EndsWith(" fault")?!ReferenceEquals(err,fault):fault!=null))throw new Exception($"{landing}/{mode}: {string.Join(',',trace)}",fault);
}
Console.WriteLine("both complete audio callbacks: fresh post-check receiver, saved array, post-draw element and fault ordering");
namespace UnityEngine{public class AudioClip{}public class AudioSource{public Action<AudioClip,float> Play;public void PlayOneShot(AudioClip c,float v)=>Play(c,v);public static Func<AudioSource,AudioSource,bool> Eq;public static bool operator ==(AudioSource a,AudioSource b)=>Eq(a,b);public static bool operator !=(AudioSource a,AudioSource b)=>!Eq(a,b);public override bool Equals(object x)=>ReferenceEquals(x,this);public override int GetHashCode()=>base.GetHashCode();}
public static class Random{public static Func<int,int,int> Pick;public static int Range(int a,int b)=>Pick(a,b);}}
class Driver{public AudioSource StepSource;public AudioClip[] StepClips,LandClips;public void Run(bool land,float volume){if(land)PlayLandAudio(volume);else PlayStepAudio(volume);}\n'''+ '\n'.join(lines)+'\n}'
    r=tmp_path/'r';r.mkdir();(r/'Program.cs').write_text(src,encoding='utf8');print(run_case(tmp_path,r))


@pytest.mark.parametrize('bad',['wrong stride','other index','receiver replaced','different length array','unproved sampler'])
def test_parked_array_proof_matches_the_actual_element_at_playback(shift_runtime,monkeypatch,bad):
    from iced_x86 import Register as R
    from il2cpp import Decompiler,Lifter
    from il2cpp.sampled_element import sampled_elements
    meta,il=shift_runtime;md=meta.methods[23714];td=meta.typedefs[md.declaring];d=Decompiler(Lifter(il));d.lift_method(md,td);bs=d.L._blocks
    find=lambda:sampled_elements(d.L,md,td,bs,());assert set(find())=={0x180507910,0x180507926}
    if bad=='unproved sampler':monkeypatch.setitem(il.addr_candidates,0x182be37d0,[('method',56178)])
    else:
        ip={'wrong stride':0x18050794a,'other index':0x18050794a,'receiver replaced':0x180507947,'different length array':0x180507920}[bad]
        b,j=next((b,j) for b in bs for j,i in enumerate(b.insns) if i.ip==ip);i=b.insns[j].copy()
        if bad=='wrong stride':i.memory_index_scale=4
        elif bad=='other index':i.memory_index=R.RAX
        elif bad=='receiver replaced':i.op1_register=R.RSI
        else:i.memory_base=R.RDI
        monkeypatch.setattr(b,'insns',b.insns[:j]+[i]+b.insns[j+1:])
    assert not find()
