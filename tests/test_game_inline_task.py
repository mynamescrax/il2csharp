"""Compile the recovered inlined kickoff and its awaiter consumer under the BCL."""
import re

import pytest

from dotnet_case import run_case
from il2cpp import Lifter,Decompiler
from il2cpp.emitter import Emitter
from test_game_shift_shared_flags import shift_runtime

pytestmark=pytest.mark.game


@pytest.mark.parametrize('parent,child,logs',[('_AbortStartGame_d__57','_CleanUpRunner_d__60',True),
                                             ('_LeaveGame_d__45','_ShutdownSession_d__61',False)])
def test_nested_task_uses_original_manager(shift_runtime,tmp_path,parent,child,logs):
    meta,il=shift_runtime;td=meta.typedefs[meta.methods[26445].declaring];out=tmp_path/'out'
    Emitter(il,str(out))._emit_one_top(td,meta.images[meta.methods[26445].image],td.name)
    source=next(out.rglob('FusionNetworkManager.cs')).read_text(encoding='utf8')
    body=source.split('struct '+parent+' : IAsyncStateMachine',1)[1].split('void IAsyncStateMachine.SetStateMachine',1)[0]
    assert 'sub_180da32d0' not in body and 'TStateMachine' not in body
    capture=re.search(r'FusionNetworkManager (\w+) = this\.(__4__this);',body)
    assert capture
    prefix=r'FusionNetworkManager\.FusionLog\("[^"\n]+"\);\s+'+capture[1]+r'\._isShuttingDown = true;\s*' if logs else ''
    arm=re.search(prefix+r'FusionNetworkManager\.(\w+) (\w+) = default;.*?Task (\w+) = \2\.__t__builder\.Task;\s*(\w+) = \3\.GetAwaiter\(\);',body,re.S)
    assert arm and arm[1]==child and '.Start<FusionNetworkManager.'+arm[1]+'>(ref '+arm[2]+');' in arm[0]
    state=re.search(r'private partial struct '+arm[1]+r' : IAsyncStateMachine\s*\{\s*public int __1__state;.*?private TaskAwaiter __u__1;',source,re.S)
    assert state
    runner=tmp_path/'runner';runner.mkdir()
    (runner/'Program.cs').write_text('''using System;
using System.Collections.Generic;
using System.Runtime.CompilerServices;
using System.Threading.Tasks;
bool logs='''+str(logs).lower()+''';
foreach(string mode in new[]{"sync","pending","fault","log throws"}) {
    if(!logs && mode=="log throws")continue;
    var original=new FusionNetworkManager {Mode=mode};var replacement=new FusionNetworkManager();
    var frame=new FusionNetworkManager.Case {__4__this=original};
    FusionNetworkManager.Log=()=>{original.Trace.Add("log");frame.__4__this=replacement;if(mode=="log throws")throw new ApplicationException("log");};
    if(mode=="log throws") {
        try{frame.Arm();throw new Exception("expected log failure");}catch(ApplicationException e) when(e.Message=="log"){}
        if(original._isShuttingDown || original.Moves!=0)throw new Exception("started after log failure");continue;
    }
    var (task,awaiter)=frame.Arm();
    if(!ReferenceEquals(task,original.Seen)||original._isShuttingDown!=logs||replacement._isShuttingDown||original.Moves!=1||replacement.Moves!=0||
       string.Join(";",original.Trace)!=(logs?"log;move":"move"))throw new Exception("wrong manager, order or task identity");
    if(mode=="pending"){if(task.IsCompleted||awaiter.IsCompleted)throw new Exception("finished early");original.Gate.SetResult();}
    if(mode=="fault"){try{awaiter.GetResult();throw new Exception("missing fault");}catch(ApplicationException e) when(ReferenceEquals(e, original.Failure)){} }
    else {awaiter.GetResult();if(!task.IsCompletedSuccessfully)throw new Exception("lost completion");}
    Console.WriteLine(mode+": original manager; same task; "+task.Status);
}
class FusionNetworkManager {
    public bool _isShuttingDown;public string Mode;public int Moves;public Task Seen;public TaskCompletionSource Gate=new();public ApplicationException Failure=new();
    public static Action Log;public static void FusionLog(string s)=>Log(); public List<string> Trace=new();
    public class Case {public FusionNetworkManager __4__this; public (Task,TaskAwaiter) Arm(){
'''+capture[0]+f'\nTaskAwaiter {arm[4]};\n'+arm[0]+f'\nreturn ({arm[3]}, {arm[4]});\n}}}}\n'+state[0]+'''
    public void MoveNext(){var owner=__4__this;owner.Moves++;owner.Trace.Add("move");
        if(__1__state==-1){if(!__u__1.Equals(default(TaskAwaiter)))throw new Exception("wrong initial fields");
            if(owner.Mode=="pending"){__1__state=0;__u__1=owner.Gate.Task.GetAwaiter();__t__builder.AwaitUnsafeOnCompleted(ref __u__1,ref this);}
            else if(owner.Mode=="fault")__t__builder.SetException(owner.Failure);else __t__builder.SetResult();
            owner.Seen=__t__builder.Task;
        }else if(__1__state==0){__u__1.GetResult();__t__builder.SetResult();}else throw new Exception("wrong state");}
    public void SetStateMachine(IAsyncStateMachine m)=>__t__builder.SetStateMachine(m);
}}''',encoding='utf8')
    print(run_case(tmp_path,runner).strip())


@pytest.mark.parametrize('defect',['other Start','partial builder','extra Create write','wrong capture width','interior entry','another EH boundary','overlapping later read'])
def test_nested_kickoff_requires_intact_local_window(shift_runtime,monkeypatch,defect):
    from iced_x86 import Decoder
    from il2cpp.inline_task import inline_tasks
    meta,il=shift_runtime;d=Decompiler(Lifter(il));m=meta.methods[26484];td=meta.typedefs[m.declaring];d.lift_method(m,td);blocks=d.L._blocks
    ip=0x18056b2ed
    assert ip in inline_tasks(d.L,m,td,blocks,d.eh)[0]
    if defect=='other Start':
        original=il.decode_slot;other=original(0x183c5d840)
        monkeypatch.setattr(il,'decode_slot',lambda p:other if p==0x183c5d758 else original(p))
    elif defect=='extra Create write':
        read=il.bin.read
        def altered(p,n):
            data=read(p,n)
            return data[:15]+bytes.fromhex('48894118c3')+data[20:] if p==0x180da32d0 and n==128 else data
        monkeypatch.setattr(il.bin,'read',altered)
    elif defect=='another EH boundary':
        monkeypatch.setitem(d.eh,'pads',d.eh['pads']+[0x18056b343])
    else:
        at={'partial builder':0x18056b306,'wrong capture width':0x18056b318,'interior entry':0x18056b26e,'overlapping later read':0x18056b3c3}[defect]
        b=next(b for b in blocks if any(i.ip==at for i in b.insns));j=next(j for j,i in enumerate(b.insns) if i.ip==at);i=b.insns[j]
        raw=bytearray(il.bin.read(at,i.len))
        if defect=='partial builder':raw[-1]-=8
        elif defect=='wrong capture width':raw[0]=0x40
        elif defect=='interior entry':raw[-4:]=(0x18056b343-i.next_ip).to_bytes(4,'little',signed=True)
        else:raw[-4:]=(0x50).to_bytes(4,'little')
        monkeypatch.setattr(b,'insns',b.insns[:j]+list(Decoder(64,bytes(raw),ip=at))+b.insns[j+1:])
    assert ip not in inline_tasks(d.L,m,td,blocks,d.eh)[0]


def test_shutdown_class_guard_needs_reaching_zero(shift_runtime,monkeypatch):
    from iced_x86 import Decoder, Mnemonic as M, Register as R
    from il2cpp.inline_task import inline_tasks
    meta,il=shift_runtime;d=Decompiler(Lifter(il));m=meta.methods[26494];td=meta.typedefs[m.declaring];d.lift_method(m,td);blocks=d.L._blocks
    assert len(inline_tasks(d.L,m,td,blocks,d.eh)[0])==1
    b=next(b for b in blocks if any(i.mnemonic==M.CMP and i.memory_base==R.RCX and i.op1_register==R.EAX for i in b.insns))
    # A plausible guard against ECX, overwritten by the class load. Keep
    # all addresses, metadata, stack zero stores and instruction lengths.
    j=next(j for j,i in enumerate(b.insns) if i.mnemonic==M.CMP and i.op1_register==R.EAX);i=b.insns[j]
    raw=bytearray(il.bin.read(i.ip,i.len));raw[1]|=8
    changed=list(Decoder(64,bytes(raw),ip=i.ip));assert len(changed)==1 and changed[0].op1_register==R.ECX
    monkeypatch.setattr(b,'insns',b.insns[:j]+changed+b.insns[j+1:])
    assert not inline_tasks(d.L,m,td,blocks,d.eh)[0]
