import pytest
from dotnet_case import run_case
from il2cpp.emitter import Emitter
from test_game_shift_shared_flags import shift_runtime

pytestmark=pytest.mark.game


def test_logged_join_and_leave_use_second_mode_and_original_player(shift_runtime,tmp_path):
    meta,il=shift_runtime;em=Emitter(il,str(tmp_path/'out'));out=[]
    for mi in (28708,28709):
        m=meta.methods[mi];em.emit_method(m,meta.typedefs[m.declaring],out,'    ')
    source='''using System;using System.Linq;using System.Reflection;using System.Runtime.Loader;using System.Collections.Generic;using Fusion;
foreach(bool join in new[]{true,false})foreach(bool logs in new[]{false,true})foreach(int mode in new[]{int.MinValue,-1,0,1,2,3,4,5,int.MaxValue}){
 Case.Run(join,logs,mode,mode,"ok");}
foreach(bool join in new[]{true,false})foreach(string fault in new[]{"none","null","format","log","decision","action","null before logging","mode before logging","format changes mode"})Case.Run(join,true,2,1,fault);
foreach(bool join in new[]{true,false})Case.Run(join,true,1,2,"none");
// Fresh type initialization only for cases that need it; configuring the
// sink callback must not initialize Debug. Log and initialize separately.
foreach(string f in new[]{"cctor","cold format"}){var alc=new AssemblyLoadContext("fresh",true);try{var asm=alc.LoadFromAssemblyPath(typeof(Case).Assembly.Location);asm.GetType("Case").GetMethod("Run").Invoke(null,new object[]{false,true,2,1,f});}finally{alc.Unload();}}
Console.WriteLine("both complete network callbacks: signed extremes, optional typed logging, cold class initialization, post-log mode and original payload");
public static class Case{
 public static Action<string> Init;public static Action<object> Sink;public static Func<string> PlayerString;
 public static void Run(bool join,bool logs,int initial,int later,string fault){var trace=new List<string>();var err=new ApplicationException();var p=new PlayerRef{Raw=int.MinValue+123};var s=new PrefabSpawner{debugLogs=logs};var runner=new NetworkRunner();int reads=0;GameMode mode=(GameMode)initial;
 void Step(string x){trace.Add(x);if(fault==x||fault=="cold format"&&x=="format")throw err;}
 runner.Read=()=>{if(logs&&reads++==0){Step("mode before logging");return mode;}Step("decision");return mode;};PlayerString=()=>{Step("format");if(fault=="format changes mode")mode=(GameMode)later;return "player-token";};
 Init=tag=>{if(fault is "cctor" or "cold format")Step("cctor");};Sink=msg=>{if(msg is not string t||t!="OnPlayer"+(join?"Joined":"Left")+" player-token mode = "+((GameMode)initial).ToString())throw new Exception("wrong boxes: "+msg);Step("log");mode=(GameMode)later;};
 s.Act=(r,ref_)=>{if(!ReferenceEquals(r,runner)||ref_.Raw!=p.Raw)throw new Exception("wrong action inputs");Step("action");return false;};Exception ex=null;try{var cb=(INetworkRunnerCallbacks)s;NetworkRunner arg=fault is "null" or "null before logging"?null:runner;if(join)cb.OnPlayerJoined(arg,p);else cb.OnPlayerLeft(arg,p);}catch(Exception e){ex=e;}
 var want=new List<string>();bool noRunner=fault is "null" or "null before logging";if(!noRunner){if(logs){want.Add("mode before logging");want.Add("format");if(fault=="cctor")want.Add("cctor");want.Add("log");}want.Add("decision");int m=logs?later:initial;if(m==1||m==3||m==4)want.Add("action");}
 int cut=want.IndexOf(fault=="cold format"?"format":fault);if(!trace.SequenceEqual(cut<0?want:want.Take(cut+1))||(noRunner?ex is not NullReferenceException:fault=="cctor"?ex is not TypeInitializationException||!ReferenceEquals(ex.InnerException,err):cut<0?ex!=null:!ReferenceEquals(ex,err)))throw new Exception($"{join}/{logs}/{initial}/{later}/{fault}: {string.Join(',',trace)}",ex);
 }}
namespace UnityEngine{public static class Debug{static Debug()=>Case.Init("cctor");public static void Log(string wrong)=>throw new Exception("wrong overload");public static void Log(object message)=>Case.Sink(message);}}
namespace Fusion{public enum GameMode{Single=1,Shared=2,Server=3,Host=4}public struct PlayerRef{public int Raw;public override string ToString()=>Case.PlayerString();}public class NetworkRunner{public Func<GameMode> Read;public GameMode GameMode=>Read();}public interface INetworkRunnerCallbacks{void OnPlayerJoined(NetworkRunner runner,PlayerRef player);void OnPlayerLeft(NetworkRunner runner,PlayerRef player);}}
public class PrefabSpawner:INetworkRunnerCallbacks{public bool debugLogs;public Func<NetworkRunner,PlayerRef,bool> Act;private bool TryDespawnPlayer(NetworkRunner runner,PlayerRef player)=>Act(runner,player);private void SpawnPlayer(NetworkRunner runner,PlayerRef player)=>Act(runner,player);\n'''+ '\n'.join(out)+'\n}'
    r=tmp_path/'r';r.mkdir();(r/'Program.cs').write_text(source,encoding='utf8');print(run_case(tmp_path,r))
    assert '\n'.join(out).count('RunClassConstructor(typeof(global::UnityEngine.Debug).TypeHandle)')==2


@pytest.mark.parametrize('bad',['miss equality edge','signed range','swapped boxes','wrong argument home','stale enum','action consumes other runner','wrong initialization owner','return observed'])
def test_logged_mode_selection_needs_both_loads_and_all_action_edges(shift_runtime,bad):
    from il2cpp import Decompiler,Lifter
    from il2cpp.logged_selection import logged_selection
    from iced_x86 import Decoder,Register as R
    meta,il=shift_runtime;m=meta.methods[28709];td=meta.typedefs[m.declaring];d=Decompiler(Lifter(il));il.eh_regions(m.addr);s,_=d._decode(m);match=lambda:logged_selection(d.L,m,td,s,None);assert match()
    j={'miss equality edge':51,'signed range':54,'swapped boxes':36,'wrong argument home':30,'stale enum':49,'action consumes other runner':57,'wrong initialization owner':38,'return observed':60}[bad];i=s[j].copy()
    if bad=='miss equality edge':i.near_branch64=s[60].ip
    elif bad=='signed range':i=Decoder(64,bytes((0x7f, s[60].ip-i.next_ip)),ip=i.ip).decode()
    elif bad=='swapped boxes':i.op1_register=R.RAX
    elif bad=='wrong argument home':i.memory_displacement=0x28
    elif bad=='stale enum':i.memory_base=R.RSI
    elif bad=='action consumes other runner':i.op1_register=R.RSI
    elif bad=='wrong initialization owner':i.memory_displacement=s[21].ip_rel_memory_address
    else:i=Decoder(64,bytes.fromhex('4889442448'),ip=i.ip).decode()
    assert i.len==s[j].len;s[j]=i;assert match() is None


def test_mode_field_alias_requires_an_executable_registered_getter(shift_runtime,monkeypatch):
    from il2cpp import Lifter
    from il2cpp.plain_property import plain_alias
    meta,il=shift_runtime;l=Lifter(il);m=meta.methods[28709];t=il.types[meta.method_params(m)[0].type][0];res=plain_alias(l,t,0x1a8,4);assert res and res[0]=='GameMode'
    md=next(meta.methods[n] for n in meta.type_methods(meta.typedefs[t]) if meta.methods[n].name=='get_GameMode');orig=il.bin.is_exec_va
    monkeypatch.setattr(il.bin,'is_exec_va',lambda a:False if a==md.addr else orig(a));assert plain_alias(l,t,0x1a8,4) is None
