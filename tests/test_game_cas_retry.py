import pytest
from dotnet_case import run_case
from il2cpp.emitter import Emitter
from test_game_shift_shared_flags import shift_runtime

pytestmark=pytest.mark.game


def test_event_accessors_retry_on_equal_but_distinct_delegate(shift_runtime,tmp_path):
    meta,il=shift_runtime;td=meta.typedefs[meta.methods[26426].declaring];ev=next(e for e in meta.events[td.event_start:td.event_start+td.event_count] if td.method_start+e[3]==26426)
    em=Emitter(il,str(tmp_path/'out'));event=[];assert em.emit_event(td,event,'    ',ev)
    # Forward to the real BCL CAS from a separate assembly. The collaborator
    # only schedules the first attempted exchange; it never fakes its outcome.
    lib=tmp_path/'cas';lib.mkdir();project=lib/'Real.csproj';project.write_text('<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><TargetFramework>net8.0</TargetFramework></PropertyGroup></Project>');(lib/'Real.cs').write_text('public static class Real {public static T Cas<T>(ref T x,T val,T expected) where T:class=>System.Threading.Interlocked.CompareExchange(ref x,val,expected);public static T Swap<T>(ref T x,T val) where T:class=>System.Threading.Interlocked.Exchange(ref x,val);}')
    src='''using System;using System.Collections.Generic;using Photon.Voice.Unity;using Handler=System.Action_1<Photon.Voice.Unity.VoiceConnection>;
foreach(bool add in new[]{false,true})foreach(var mode in new[]{"plain","collision","competing listener","synchronous fault","different listener","null"}){
 int invoked=0;Handler a=_=>invoked++;Handler b=(Handler)a.Clone(); Handler other=_=>invoked+=10;
 if(ReferenceEquals(a,b)||a!=b)throw new Exception("bad contention setup");FusionNetworkManager.Set(mode=="null"?null:a);var err=new ApplicationException();
 var rival=mode=="collision"?b:other;bool race=mode is "collision" or "competing listener";
 System.Threading.Interlocked.Count=0;System.Threading.Interlocked.At=old=>{if(!ReferenceEquals(old,System.Threading.Interlocked.Count==1?(mode=="null"?null:a):rival))throw new Exception("wrong comparand identity");if(System.Threading.Interlocked.Count!=1)return;if(race)FusionNetworkManager.Set(rival);if(mode=="synchronous fault")throw err;};
 Exception fault=null;try{if(add)FusionNetworkManager.OnVoiceConnectionReady+=mode=="different listener"?other:a;else FusionNetworkManager.OnVoiceConnectionReady-=mode=="different listener"?other:a;}catch(Exception e){fault=e;}
 int calls=System.Threading.Interlocked.Count;if(calls!=(race?2:1)||(mode=="synchronous fault"?!ReferenceEquals(fault,err):fault!=null))throw new Exception($"{add}/{mode}:CAS {calls}",fault);
 FusionNetworkManager.Invoke();int expected=mode=="synchronous fault"?1:mode=="competing listener"?(add?11:10):add?(mode=="null"?1:mode=="different listener"?11:2):mode=="different listener"?1:0;
 if(invoked!=expected)throw new Exception($"{add}/{mode}: invoked {invoked}, expected {expected}");
}
Console.WriteLine("whole event accessors: genuine CAS retries for equal invocation lists and distinct reference identity");
namespace System{public delegate void Action_1<T>(T arg);}namespace Photon.Voice.Unity{public class VoiceConnection{}}
namespace System.Threading{public static class Interlocked{public static int Count;public static Action<object> At;public static T CompareExchange<T>(ref T dest,T next,T old) where T:class{++Count;At(old);if(Count>3)throw new Exception("bad retry");return Real.Cas(ref dest,next,old);}}}
class FusionNetworkManager{private static Handler __field_OnVoiceConnectionReady;public static void Set(Handler h)=>Real.Swap(ref __field_OnVoiceConnectionReady,h);public static void Invoke()=>__field_OnVoiceConnectionReady?.Invoke(new VoiceConnection());\n'''+ '\n'.join(event)+'\n}'
    r=tmp_path/'r';r.mkdir();(r/'Program.cs').write_text(src,encoding='utf8');print(run_case(tmp_path,r,[project]))


@pytest.mark.parametrize('bad',['different expected','low compared','wrong retry','wrong field offset','different helper','different save','wrong barrier'])
def test_reference_retry_is_bound_to_the_actual_qword_cas(shift_runtime,monkeypatch,bad):
    from il2cpp import Decompiler,Lifter
    from il2cpp.cas_retry import retry_sites
    from iced_x86 import Register as R,Decoder
    meta,il=shift_runtime;m=meta.methods[26426];td=meta.typedefs[m.declaring];d=Decompiler(Lifter(il));d.lift_method(m,td);bs=d.L._blocks
    find=lambda:retry_sites(d.L,m,td,bs,());site=0x18055d5c4;assert site in find()
    if bad=='wrong barrier':
        at=0x1804405e0+22;read=il.bin.read;new=(0x180436160-(at+4)).to_bytes(4,'little',signed=True)
        def redirect(p,n):
            raw=read(p,n)
            if raw and p<=at and at+4<=p+n:
                q=at-p;raw=raw[:q]+new+raw[q+4:]
            return raw
        monkeypatch.setattr(il.bin,'read',redirect);assert d.L._is_interlocked_helper(0x1804405e0) and site not in find();return
    p={'different expected':0x18055d5cc,'low compared':0x18055d5cc,'wrong retry':0x18055d5cf,'wrong field offset':0x18055d5bd,'different helper':site,'different save':0x18055d569}[bad]
    b,j=next((b,j) for b in bs for j,i in enumerate(b.insns) if i.ip==p);i=b.insns[j].copy()
    if bad=='different expected':i.op1_register=R.RSI
    elif bad=='low compared':i=Decoder(64,bytes.fromhex('413bc6'),ip=p).decode()  # cmp eax,r14d
    elif bad=='wrong retry':i.near_branch64=0x18055d56c
    elif bad=='wrong field offset':i.immediate8=0x18
    elif bad=='different helper':i.near_branch64=0x1804353d0
    else:i.op1_register=R.R15
    assert i.len==b.insns[j].len
    monkeypatch.setattr(b,'insns',b.insns[:j]+[i]+b.insns[j+1:]);assert site not in find()
