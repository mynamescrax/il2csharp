import pytest
from dotnet_case import run_case
from il2cpp.emitter import Emitter
from test_game_shift_shared_flags import shift_runtime

pytestmark = pytest.mark.game


def test_three_complete_audio_callbacks_keep_source_volume_and_clock(shift_runtime,tmp_path):
    meta,il=shift_runtime;em=Emitter(il,str(tmp_path/'out'));shells=[]
    for mi,field,flag in [(24337,'carEngineRunning','fadeOutAudio'),(24460,'chaseAudio','chasing'),(26646,'petrolFillSfx','pumping')]:
        m=meta.methods[mi];td=meta.typedefs[m.declaring];lines=[];em.emit_method(m,td,lines,'    ')
        shells.append('class '+td.name+' {public AudioSource '+field+';public bool '+flag+';public void Run()=>FixedUpdate();\n'+'\n'.join(lines)+'\n}')
    src='''using System;using System.Linq;using System.Collections.Generic;using UnityEngine;
foreach (string kind in new[]{"car","chase","petrol"}) foreach(bool active in new[]{false,true})
foreach(float dt in new[]{-.25f,.03125f,2f,float.NaN}) foreach(float volume in new[]{-.375f,.75f}) foreach(string mode in new[]{"normal","null","get","clock","set"}) {
    var a=new AudioSource();var poison=new AudioSource();var trace=new List<string>();var err=new ApplicationException();
    Action<AudioSource> Put;Action Run;
    if(kind=="car"){var c=new Car{fadeOutAudio=active};Put=x=>c.carEngineRunning=x;Run=c.Run;}
    else if(kind=="chase"){var c=new ChaseWhenNear{chasing=active};Put=x=>c.chaseAudio=x;Run=c.Run;}
    else {var c=new PetrolTank{pumping=active};Put=x=>c.petrolFillSfx=x;Run=c.Run;}
    void Step(string s){trace.Add(s);if(mode==s)throw err;}
    float live=volume;
    a.Get=()=>{Step("get");Put(poison);return live;};
    Time.Read=()=>{Step("clock");Put(null);live=91f;return dt;};
    float t=kind=="car"?dt/5f:kind=="petrol"&&!active?dt*10f:dt;
    t=t<0?0:t>1?1:t;float target=active?(kind=="petrol"?.6f:kind=="chase"?.27f:0f):0f;
    float want=(target-volume)*t+volume;
    a.Set=v=>{if(BitConverter.SingleToInt32Bits(v)!=BitConverter.SingleToInt32Bits(want)&&!(float.IsNaN(v)&&float.IsNaN(want)))throw new Exception("wrong volume"); Step("set");};
    Put(mode=="null"?null:a);Exception fault=null;try{Run();}catch(Exception e){fault=e;}
    bool skip=kind=="car"&&!active;int count=skip||mode=="null"?0:mode=="get"?1:mode=="clock"?2:3;
    if(!trace.SequenceEqual(new[]{"get","clock","set"}.Take(count)) || (skip||mode=="normal"?fault!=null:mode=="null"?fault is not NullReferenceException:!ReferenceEquals(fault,err)))
        throw new Exception($"{kind}/{active}/{dt}/{mode}: {string.Join(',',trace)}",fault);
}
Console.WriteLine("three complete audio callbacks: original receiver, per-path captures, bounds and callback failures");
namespace UnityEngine{public class AudioSource{public Func<float> Get;public Action<float> Set;public float volume{get=>Get();set=>Set(value);}}public static class Time{public static Func<float> Read;public static float deltaTime=>Read();}}
'''+ '\n'.join(shells)
    r=tmp_path/'r';r.mkdir();(r/'Program.cs').write_text(src,encoding='utf8');print(run_case(tmp_path,r))


@pytest.mark.parametrize('change',['different park source','extra clock predecessor','different setter receiver'])
def test_scalar_pair_needs_its_own_getter_and_same_setter_receiver(shift_runtime,monkeypatch,change):
    from iced_x86 import Decoder, Register as R
    from il2cpp import Decompiler,Lifter
    from il2cpp.parked_scalar_pair import scalar_pairs
    meta,il=shift_runtime;m=meta.methods[24460];td=meta.typedefs[m.declaring];d=Decompiler(Lifter(il))
    d.lift_method(m,td);bs=d.L._blocks
    def plan():return scalar_pairs(d.L,m,td,bs,())
    fields,calls=plan();assert len(fields)==1 and len(calls)==4
    ip={'different park source':0x18069e340,'extra clock predecessor':0x18069e398,'different setter receiver':0x18069e395}[change]
    b,j=next((b,j) for b in bs for j,i in enumerate(b.insns) if i.ip==ip);i=b.insns[j].copy()
    if change=='different park source':i.op1_register=R.XMM1
    elif change=='extra clock predecessor':i.near_branch64=0x18069e343
    else:
        i=Decoder(64,b'\x48\x89\xfb',ip=ip).decode();assert i.len==b.insns[j].len and i.op0_register==R.RBX
    monkeypatch.setattr(b,'insns',b.insns[:j]+[i]+b.insns[j+1:]);after,cs=plan()
    if change=='different setter receiver':assert (after,cs)==({},{})
    else:assert after==fields and set(cs)=={0x18069e371,0x18069e37b}
