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
