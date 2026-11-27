import pytest
from iced_x86 import Decoder
from dotnet_case import run_case
from il2cpp import Expr
from il2cpp.emitter import Emitter
from il2cpp.float_branch import unordered_bound
from test_game_shift_shared_flags import shift_runtime

pytestmark=pytest.mark.game


def test_volume_controls_keep_unordered_inputs(shift_runtime,tmp_path):
    meta,il=shift_runtime;em=Emitter(il,str(tmp_path/'out'));members={}
    for j in (26563,28420,28439):
        m=meta.methods[j];td=meta.typedefs[m.declaring];em.emit_method(m,td,members.setdefault(td.name,[]),'    ')
    src='''using System;using System.Collections.Generic;using System.Linq;using UnityEngine;
float Bits(uint n)=>BitConverter.Int32BitsToSingle(unchecked((int)n));bool Same(float a,float b)=>BitConverter.SingleToInt32Bits(a)==BitConverter.SingleToInt32Bits(b);
foreach(float v in new[]{Bits(0xffc01234),Bits(0x7fc12345),Bits(0x80000000),0f,float.NegativeInfinity,-1f,0.375f,MathF.BitDecrement(1f),1f,MathF.BitIncrement(1f),2f,MathF.BitIncrement(2f),float.PositiveInfinity}){
 float Want(float max)=>v<0f?0f:v>max?max:v;
 var manager=new VoiceVolumeManager();var a=manager.playerVolumes;var b=new Cache();var trace=new List<string>();string key=new string("Ada".ToCharArray());var ex=new ApplicationException();
 foreach(var stop in new[]{"none","hit","lookup","pref","set"}){trace.Clear();manager.playerVolumes=a;void Step(string s){trace.Add(s);if(s==stop)throw ex;}
 a.Lookup=(string k,ref float f)=>{Step("lookup");if(!ReferenceEquals(k,key)||f!=0f)throw new Exception();f=stop=="hit"?v:123.75f;return stop=="hit";};
 PlayerPrefs.Get=(k,f)=>{Step("pref");if(k!="VOICE_VOLUME/Ada"||f!=1f)throw new Exception();manager.playerVolumes=b;return v;};
 b.Put=(k,f)=>{if(!ReferenceEquals(k,key)||!Same(f,Want(1)))throw new Exception("wrong cache write");Step("set");};
 if(manager.GetPlayerVolume(null)!=1f||manager.GetPlayerVolume("  ")!=1f||trace.Count!=0)throw new Exception("guard");
 Exception fault=null;float result=0;try{result=manager.GetPlayerVolume(key);}catch(Exception e){fault=e;}
 string want=stop switch{"lookup" or "hit"=>"lookup","pref"=>"lookup,pref",_=>"lookup,pref,set"};if(string.Join(',',trace)!=want||(stop is "hit" or "none"?!Same(result,stop=="hit"?v:Want(1))||fault!=null:!ReferenceEquals(fault,ex)))throw new Exception("get "+stop,fault);}
 var mic=new VoiceVolumeController();int logs=0;Debug.Write=s=>{if(!Same(mic.micGain,Want(2))||s!=string.Format("Outgoing mic volume set to {0}",Want(2)))throw new Exception("mic gain/log");logs++;};mic.SetMicVolume(v);if(logs!=1)throw new Exception();
 foreach(var mode in new[]{"live","destroyed","null","clear","fault"}){var row=new PerPlayerVolumeRow();var before=new Slider();var after=new Slider();row.volumeSlider=mode=="null"?null:before;int tests=0,sets=0;
 Slider.Neq=(x,n)=>{tests++;if(!row.isConfiguring||!ReferenceEquals(x,mode=="null"?null:before)||n is not null)throw new Exception();row.volumeSlider=mode=="clear"?null:after;return mode!="destroyed"&&mode!="null";};
 after.Set=f=>{sets++;if(!row.isConfiguring||!Same(f,Want(1)))throw new Exception("slider value");if(mode=="fault")throw ex;};
 Exception fault=null;try{row.SetVolumeWithoutNotification(v);}catch(Exception e){fault=e;}if(tests!=1||sets!=(mode is "live" or "fault"?1:0)||row.isConfiguring!=(mode is "clear" or "fault")||(mode=="clear"?fault is not NullReferenceException:mode=="fault"?!ReferenceEquals(ex,fault):fault!=null))throw new Exception("row "+mode,fault);}}
Console.WriteLine("three complete volume methods: NaN payloads, signed zero, both bounds, callbacks and faults passed");
public delegate bool LookupFn(string k,ref float f);public class Cache{public LookupFn Lookup;public Action<string,float> Put;public bool TryGetValue(string s,ref float v)=>Lookup(s,ref v);public float this[string s]{set=>Put(s,value);}}
namespace UnityEngine {public static class PlayerPrefs{public static Func<string,float,float> Get;public static float GetFloat(string k,float f)=>Get(k,f);}public static class Debug{public static Action<string> Write;public static void Log(object s)=>Write((string)s);}}
public class Slider{public static Func<Slider,Slider,bool> Neq;public static bool operator !=(Slider a,Slider b)=>Neq(a,b);public static bool operator ==(Slider a,Slider b)=>!Neq(a,b);public override bool Equals(object o)=>ReferenceEquals(this,o);public override int GetHashCode()=>base.GetHashCode();public Action<float> Set;public virtual void SetValueWithoutNotify(float v)=>Set(v);}
'''
    fields={'VoiceVolumeController':'public float micGain;','VoiceVolumeManager':'public Cache playerVolumes=new();','PerPlayerVolumeRow':'public Slider volumeSlider;public bool isConfiguring;'}
    for name,lines in members.items():src+='public class '+name+'{'+fields[name]+'\n'+'\n'.join(lines)+'\n}\n'
    runner=tmp_path/'runner';runner.mkdir();(runner/'Program.cs').write_text(src,encoding='utf8');print(run_case(tmp_path,runner).strip())


@pytest.mark.parametrize('code,te,expect',[('0f2fc17600',12,'>'),('660f2fc17200',13,'>='),('39c87600',8,None),('0f2fc1f97600',12,None),('660f2fc17600',12,None)])
def test_unordered_compare_needs_unbroken_flags_and_scalar_width(code,te,expect):
    seq=list(Decoder(64,bytes.fromhex(code),ip=0x1000));a=Expr('A()', (0,te<<16),'float');b=Expr('B()',(0,te<<16),'float');cond=unordered_bound(seq[0],seq[-1],seq[0].mnemonic,a,b)
    if expect:assert ' '+expect+' ' in cond and cond.endswith(' == false') and cond.count('A()')==cond.count('B()')==1
    else:assert cond is None
