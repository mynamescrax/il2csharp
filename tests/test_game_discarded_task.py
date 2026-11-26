"""Compile the complete emitted iterator MoveNext. Instrument only its child."""
import re

import pytest

from dotnet_case import run_case
from il2cpp import Decompiler, Lifter
from il2cpp.emitter import Emitter
from test_game_shift_shared_flags import shift_runtime

pytestmark=pytest.mark.game


def test_iterator_yields_then_discards_live_task(shift_runtime,tmp_path):
    meta,il=shift_runtime;md=meta.methods[26003];td=meta.typedefs[il._nested_owner(md.declaring)]
    out=tmp_path/'out';Emitter(il,str(out))._emit_one_top(td,meta.images[md.image],td.name)
    text=next(out.rglob('LobbyUIManager.cs')).read_text(encoding='utf8')
    iterator=text.split('class _DelayedStart_d__39 :',1)[1]
    method=iterator.split('bool System.Collections.IEnumerator.MoveNext()',1)[1].split('// RVA:',1)[0].strip()
    assert method.endswith('}') and 'sub_' not in method and 'TStateMachine' not in method
    # BCL needs the property read after Start even though the iterator does
    # not await, return or publish the task.
    assert re.search(r'(\w+)\.__t__builder\.Start<LobbyUIManager\._HostLobby_d__43>\(ref \1\);\s*_ = \1\.__t__builder\.Task;',method)
    child=re.search(r'private partial struct _HostLobby_d__43 : IAsyncStateMachine\s*\{\s*public int __1__state;.*?public LobbyUIManager __4__this;',text,re.S)
    assert child
    runner=tmp_path/'runner';runner.mkdir()
    (runner/'Program.cs').write_text('''using System;
using System.Collections;
using System.Runtime.CompilerServices;
using System.Threading.Tasks;
foreach(string mode in new[]{"pending","fault","sync","null"}) {
    var first=new LobbyUIManager();var resumed=new LobbyUIManager {Mode=mode};
    var it=new LobbyUIManager.Frame {__4__this=first};IEnumerator e=it;
    if(!e.MoveNext() || first.Moves!=0 || e.Current is not WaitForSeconds {Seconds:0.3f})throw new Exception("bad first yield");
    var wait=e.Current;it.__4__this=mode=="null"?null:resumed;
    if(mode=="null") {
        try{e.MoveNext();throw new Exception("lost null check");}catch(NullReferenceException){}
        if(e.MoveNext()||first.Moves!=0)throw new Exception("state not reset");
        Console.WriteLine("null: throws on resume, then finished");continue;
    }
    if(e.MoveNext()||first.Moves!=0||resumed.Moves!=1||!ReferenceEquals(wait,e.Current)||e.MoveNext())throw new Exception("lost receiver or yielded Task");
    if(mode=="pending") {if(resumed.Observed.IsCompleted)throw new Exception("waited for child");resumed.Gate.SetResult();}
    if(mode=="fault") {if(!resumed.Observed.IsFaulted||!ReferenceEquals(resumed.Observed.Exception.InnerException,resumed.Error))throw new Exception("lost fault");}
    else if(!resumed.Observed.Wait(3000) || !resumed.Observed.IsCompletedSuccessfully)throw new Exception("lost completion");
    if(resumed.Moves!=(mode=="pending"?2:1))throw new Exception("duplicate Start");
    Console.WriteLine($"{mode}: resumed owner, iterator returned false, child {resumed.Observed.Status}");
}
class WaitForSeconds { public float Seconds;public WaitForSeconds(float seconds)=>Seconds=seconds; }
class LobbyUIManager {
    public string Mode;public int Moves;public Task Observed;public TaskCompletionSource Gate=new();public Exception Error=new();
    public class Frame : IEnumerator {int __1__state;object __2__current;public LobbyUIManager __4__this;
        public object Current=>__2__current;public void Reset()=>throw new NotSupportedException();
        bool System.Collections.IEnumerator.MoveNext()\n'''+method+'\n}\n'+child[0]+'''
    TaskAwaiter waiter;
    public void MoveNext(){var owner=__4__this;owner.Moves++;
        if(__1__state==-1) {
            if(owner.Mode=="pending"){__1__state=0;waiter=owner.Gate.Task.GetAwaiter();__t__builder.AwaitUnsafeOnCompleted(ref waiter,ref this);}
            else if(owner.Mode=="fault")__t__builder.SetException(owner.Error);else __t__builder.SetResult();
            owner.Observed=__t__builder.Task;
        } else if(__1__state==0){waiter.GetResult();__t__builder.SetResult();}else throw new Exception("bad initial state");}
    public void SetStateMachine(IAsyncStateMachine m)=>__t__builder.SetStateMachine(m);
}}''',encoding='utf8')
    print(run_case(tmp_path,runner).strip())


@pytest.mark.parametrize('defect',['different checked receiver','live task return','wrong factory member'])
def test_unproven_discard_is_not_rewritten(shift_runtime,monkeypatch,defect):
    from iced_x86 import Decoder, Mnemonic as M, Register as R
    from il2cpp.inline_task import inline_tasks
    meta,il=shift_runtime;md=meta.methods[26003];td=meta.typedefs[md.declaring];d=Decompiler(Lifter(il));d.lift_method(md,td)
    blocks=d.L._blocks;plans=lambda:inline_tasks(d.L,md,td,blocks,d.eh)[0]
    assert len(plans())==1
    if defect=='wrong factory member':
        addr=0x180da32d0;members=il.addr_candidates[addr]
        monkeypatch.setitem(il.addr_candidates,addr,[(kind,j) for kind,j in members if kind!='method' or meta.methods[j].name!='Create'])
    else:
        find,reg=(M.TEST,R.RBX) if defect=='different checked receiver' else (M.XOR,R.AL)
        b,j=next((b,j) for b in blocks for j,i in enumerate(b.insns) if i.mnemonic==find and i.op0_register==i.op1_register==reg)
        i=b.insns[j];raw=bytearray(il.bin.read(i.ip,i.len))
        if find==M.TEST:raw[-1]=0xff # test RDI,RDI (iterator), not its captured owner in RBX
        else:raw[:]=bytes.fromhex('84c0') # test AL,AL: leaves the low byte of Task live at RET
        replacement=list(Decoder(64,bytes(raw),ip=i.ip));assert len(replacement)==1
        monkeypatch.setattr(b,'insns',b.insns[:j]+replacement+b.insns[j+1:])
    assert not plans()
