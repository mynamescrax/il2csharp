"""Compile the emitted kickoff against the real BCL builder and an observable MoveNext."""
import re

import pytest

from dotnet_case import run_case
from il2cpp import Decompiler,Lifter
from il2cpp.emitter import Emitter
from test_game_shift_shared_flags import shift_runtime

pytestmark=pytest.mark.game


def test_uid_join_starts_concrete_machine_with_all_captures(shift_runtime,tmp_path):
    meta,il=shift_runtime;md=meta.methods[26520];td=meta.typedefs[md.declaring];out=tmp_path/'out'
    emit=Emitter(il,str(out));emit._emit_one_top(td,meta.images[md.image],td.name)
    source=next(out.rglob('UIDService.cs')).read_text(encoding='utf-8')
    method=re.search(r'public void OnUserJoined\(string fuid, string platformID, int actorID\)\s*\{.*?^    }',source,re.S|re.M)
    sm=re.search(r'private partial struct (\w+) : IAsyncStateMachine\s*\{\s*public int __1__state;.*?private TaskAwaiter __u__1;',source,re.S)
    assert method and sm and sm[1]=='_OnUserJoined_d__15' and 'TStateMachine' not in method[0]
    runner=tmp_path/'runner';runner.mkdir()
    (runner/'Program.cs').write_text('''using System;
using System.Collections.Generic;
using System.Runtime.CompilerServices;
using System.Threading;
foreach((string user,string platform,int actor) in new[]{("user","platform",17), (null,"other",int.MinValue),("",null,int.MaxValue)}) {
    var c=new Context();SynchronizationContext.SetSynchronizationContext(c);var u=new UIDService();
    UIDService.Observe=(owner,f,p,a,state,awaiter)=>{
        c.Log.Add("move");if(!ReferenceEquals(u,owner)||!ReferenceEquals(user,f)||!ReferenceEquals(platform,p)||actor!=a||state!=-1||!awaiter.Equals(default(TaskAwaiter)))
            throw new Exception("wrong field, state or initialization");};
    u.OnUserJoined(user,platform,actor);
    if(string.Join(";",c.Log)!="create;move;complete")throw new Exception("wrong order or builder copy");
    Console.WriteLine($"actor={actor}: create;move(state=-1, captures OK);complete");
}
var fails=new Context {Fail=true};SynchronizationContext.SetSynchronizationContext(fails);
try {new UIDService().OnUserJoined("key","value",3);throw new Exception("Create should throw");}catch(ApplicationException){}
if(string.Join(";",fails.Log)!="create")throw new Exception("started after Create failed");
SynchronizationContext.SetSynchronizationContext(null);
class Context:SynchronizationContext {public List<string> Log=new(); public bool Fail;
    public override void OperationStarted(){Log.Add("create");if(Fail)throw new ApplicationException();}
    public override void OperationCompleted()=>Log.Add("complete");}
class UIDService {
    public static Action<UIDService,string,string,int,int,TaskAwaiter> Observe;
'''+method[0]+'\n'+sm[0]+'''
        public void MoveNext(){Observe(__4__this,fuid,platformID,actorID,__1__state,__u__1);__t__builder.SetResult();}
        public void SetStateMachine(IAsyncStateMachine s)=>__t__builder.SetStateMachine(s);
    }
}''',encoding='utf-8')
    print(run_case(tmp_path,runner).strip())


@pytest.mark.parametrize('change',['different closed target','wrong machine ref','wrong builder ref','partial zero','wrong builder chunk','swapped capture source',
                                   'wrong barrier address','overwritten capture','wrong state','wrong restore'])
def test_async_start_requires_exact_homes_and_abi(shift_runtime,monkeypatch,change):
    from iced_x86 import Decoder
    from il2cpp.async_start import async_void_start
    meta,il=shift_runtime;d=Decompiler(Lifter(il));m=meta.methods[26520];td=meta.typedefs[m.declaring];d.eh=il.eh_regions(m.addr);seq,_=d._decode(m)
    assert async_void_start(d.L,m,td,seq,d.eh)
    if change=='different closed target':
        old=il.decode_slot;other=old(0x183c66328) # another Start<TStateMachine>
        monkeypatch.setattr(il,'decode_slot',lambda slot:other if slot==0x183c675d8 else old(slot))
    else:
        ip,ix,xor={ 'wrong machine ref':(0x1805948b4,-1,8),'wrong builder ref':(0x1805948b9,-1,8),
            'partial zero':(0x180594848,-1,16),'wrong builder chunk':(0x18059486d,-1,16),
            'swapped capture source':(0x18059488c,2,8),'wrong barrier address':(0x180594891,-1,8),
            'overwritten capture':(0x1805948be,-4,0x08),'wrong state':(0x1805948c5,-1,1),'wrong restore':(0x1805948de,-1,8)}[change]
        k=next(k for k,i in enumerate(seq) if i.ip==ip);raw=bytearray(il.bin.read(ip,seq[k].len));raw[ix]^=xor
        seq=seq[:k]+list(Decoder(64,bytes(raw),ip=ip))+seq[k+1:]
    assert async_void_start(d.L,m,td,seq,d.eh) is None


def test_solo_returns_the_task_of_the_started_builder(shift_runtime,tmp_path):
    meta,il=shift_runtime;md=meta.methods[26428];td=meta.typedefs[md.declaring];out=tmp_path/'out'
    Emitter(il,str(out))._emit_one_top(td,meta.images[md.image],td.name)
    source=next(out.rglob('FusionNetworkManager.cs')).read_text(encoding='utf-8')
    method=re.search(r'public Task_1<bool> StartAsSolo\(\)\s*\{.*?^    }',source,re.S|re.M)
    sm=re.search(r'private partial struct _StartAsSolo_d__42 : IAsyncStateMachine\s*\{\s*public int __1__state;.*?private TaskAwaiter_1<bool> __u__1;',source,re.S)
    assert method and sm and 'TStateMachine' not in method[0]
    runner=tmp_path/'runner';runner.mkdir()
    # Adapters give the BCL types the recovered `_1<T>` spellings. Start,
    # SetResult, SetException and task identity come from the real BCL builder.
    (runner/'Program.cs').write_text('''using System;
using System.Collections.Generic;
using System.Runtime.CompilerServices;
using System.Threading.Tasks;
foreach(var mode in new[]{"pending","false","true","fault"}) {
    var manager=new FusionNetworkManager();Check.Mode=mode;Check.Manager=manager;Check.Log.Clear();Check.Seen=null;Check.Finish=null;
    var returned=manager.StartAsSolo();
    string trace=(mode=="pending"?"class-init;":"")+"create;start;move;task;task";
    if(string.Join(";",Check.Log)!=trace || !ReferenceEquals(Check.Seen,returned))throw new Exception(mode+": "+string.Join(";",Check.Log));
    if(mode=="pending") {if(returned.Inner.IsCompleted)throw new Exception("completed too early");Check.Finish();}
    if(mode=="fault") {try {returned.Inner.GetAwaiter().GetResult();throw new Exception("missing fault");} catch(ApplicationException){} }
    else if(!returned.Inner.IsCompletedSuccessfully || returned.Inner.Result!=(mode!="false"))throw new Exception("wrong completion");
    Console.WriteLine(mode+": same task; "+trace);
}
static class Check {public static string Mode;public static FusionNetworkManager Manager;public static Task_1<bool> Seen;
    public static Action Finish;public static List<string> Log=new();}
class Task_1<T> {internal Task<T> Inner;static ConditionalWeakTable<Task<T>,Task_1<T>> wrappers=new();
    public static Task_1<T> From(Task<T> t)=>wrappers.GetValue(t,x=>new Task_1<T>{Inner=x});}
struct TaskAwaiter_1<T> {public int Probe;}
struct AsyncTaskMethodBuilder_1<T> {
    AsyncTaskMethodBuilder<T> inner;public int Tag;
    static AsyncTaskMethodBuilder_1(){Check.Log.Add("class-init");}
    public static AsyncTaskMethodBuilder_1<T> Create(){Check.Log.Add("create");return new(){inner=AsyncTaskMethodBuilder<T>.Create(),Tag=1};}
    public void Start<TMachine>(ref TMachine m) where TMachine:IAsyncStateMachine {Check.Log.Add("start");if(Tag!=1)throw new Exception("lost Create");Tag=2;inner.Start(ref m);}
    public void SetResult(T value)=>inner.SetResult(value);public void SetException(Exception e)=>inner.SetException(e);
    public Task_1<T> Task {get{Check.Log.Add("task");if(Tag!=3)throw new Exception("detached builder");return Task_1<T>.From(inner.Task);}}
}
class FusionNetworkManager {
'''+method[0]+'\n'+sm[0]+'''
        public void MoveNext(){Check.Log.Add("move");if(__1__state!=-1 || !ReferenceEquals(__4__this,Check.Manager) || __u__1.Probe!=0 || __t__builder.Tag!=2)throw new Exception("wrong machine");
            __t__builder.Tag=3;if(Check.Mode=="fault")__t__builder.SetException(new ApplicationException());
            else if(Check.Mode!="pending")__t__builder.SetResult(Check.Mode=="true");
            Check.Seen=__t__builder.Task;var after=__t__builder;if(Check.Mode=="pending")Check.Finish=()=>after.SetResult(true);}
        public void SetStateMachine(IAsyncStateMachine sm) {throw new NotSupportedException();}
    }
}''',encoding='utf-8')
    print(run_case(tmp_path,runner).strip())


@pytest.mark.parametrize('change',['other start','other create','other getter','other class','clobbered default','short builder copy',
                                   'wrong owner','wrong start receiver','other task receiver','changed return'])
def test_solo_requires_three_closed_bindings_and_live_task_result(shift_runtime,monkeypatch,change):
    from iced_x86 import Decoder
    from il2cpp.async_start import async_task_start
    meta,il=shift_runtime;d=Decompiler(Lifter(il));md=meta.methods[26428];td=meta.typedefs[md.declaring];d.eh=il.eh_regions(md.addr);seq,_=d._decode(md)
    assert async_task_start(d.L,md,td,seq,d.eh)
    if change in ('other start','other create','other getter','other class'):
        a,b={'other start':(0x183c76060,0x183c76148),'other create':(0x183c78db0,0x183c79150),
             'other getter':(0x183c79150,0x183c78db0),'other class':(0x183c46790,0x183c78db0)}[change]
        old=il.decode_slot;other=old(b);monkeypatch.setattr(il,'decode_slot',lambda p:other if p==a else old(p))
    else:
        k=next(k for k,i in enumerate(seq) if i.ip=={'clobbered default':0x18055c2fc,'short builder copy':0x18055c338,'wrong owner':0x18055c343,
            'wrong start receiver':0x18055c361,'other task receiver':0x18055c37a,'changed return':0x18055c388}[change]);i=seq[k];raw=bytearray(il.bin.read(i.ip,i.len))
        if change=='changed return':raw[-1]=0x58 # POP RAX clobbers get_Task's result
        elif change=='wrong owner':raw[-1]^=1
        else:raw[-1]^=8
        seq=seq[:k]+list(Decoder(64,bytes(raw),ip=i.ip))+seq[k+1:]
    assert async_task_start(d.L,md,td,seq,d.eh) is None
