"""Two closed machines share native homes. Compile the emitted kickoff and
awaiter slices with both child types private and the actual LeaveGame wrapper."""
import re

import pytest
from iced_x86 import Decoder

from dotnet_case import run_case
from il2cpp import Decompiler,Lifter
from il2cpp.emitter import Emitter
from il2cpp.inline_task import inline_tasks
from test_game_shift_shared_flags import shift_runtime

pytestmark=pytest.mark.game


def test_reused_kickoff_tasks_are_independent(shift_runtime,tmp_path):
    meta,il=shift_runtime;out=tmp_path/'out';emit=Emitter(il,str(out))
    for ix in (26224,26431):
        m=meta.methods[ix];td=meta.typedefs[il._nested_owner(m.declaring) if ix==26224 else m.declaring]
        emit._emit_one_top(td,meta.images[m.image],td.name)
    platform=next(out.rglob('PlatformManager_Steam.cs')).read_text(encoding='utf8');fusion=next(out.rglob('FusionNetworkManager.cs')).read_text(encoding='utf8')
    body=platform.split('struct _HandleEndSessionReturn_d__51 :',1)[1].split('void IAsyncStateMachine.SetStateMachine',1)[0]
    assert 'sub_180da32d0' not in body and 'TStateMachine' not in body and '._LeaveGame_d__45' not in body
    first=re.search(r'UnityEngine.Object (\w+) = FusionNetworkManager.Instance;',body)
    leave=re.search(r'FusionNetworkManager (\w+) = FusionNetworkManager.Instance;\s*Task (\w+) = \1.LeaveGame\(\);\s*(\w+) = \2.GetAwaiter\(\);',body)
    waits=list(re.finditer(r'PlatformManager_Steam\._WaitForFrames_d__46 (\w+) = default;.*?Task (\w+) = \1.__t__builder.Task;\s*(\w+) = \2.GetAwaiter\(\);',body,re.S))
    assert first and leave and len(waits)==2 and first.end()<body.index('SteamLog("HandleEndSessionReturn - Fusion Leave Game")')<leave.start()
    wrapper=re.search(r'public Task LeaveGame\(\)\s*\{.*?^    }',fusion,re.S|re.M);assert wrapper
    sm=lambda text,name,last:re.search(r'private partial struct '+name+r' : IAsyncStateMachine\s*\{\s*public int __1__state;.*?'+last+';',text,re.S)[0]
    waitstate=sm(platform,'_WaitForFrames_d__46','public int frameCount');leavestate=sm(fusion,'_LeaveGame_d__45','public FusionNetworkManager __4__this')
    child='''TaskAwaiter pending;
        public void MoveNext(){var c=CONTROL;c.Moves++;
            if(__1__state==-1){CAPTURE
                if(c.Mode=="pending"){__1__state=0;pending=c.Gate.Task.GetAwaiter();__t__builder.AwaitUnsafeOnCompleted(ref pending,ref this);}
                else if(c.Mode=="fault")__t__builder.SetException(c.Error);else __t__builder.SetResult();
                c.Seen=__t__builder.Task;
            }else if(__1__state==0){pending.GetResult();__t__builder.SetResult();}else throw new Exception("bad state");}
        public void SetStateMachine(IAsyncStateMachine m)=>__t__builder.SetStateMachine(m); }'''
    def use(name,part):return 'public static (Task,TaskAwaiter) '+name+'(){TaskAwaiter '+part[3]+';\n'+part[0]+'\nreturn ('+part[2]+','+part[3]+');}'
    case='''using System;using System.Runtime.CompilerServices;using System.Threading.Tasks;
foreach(string mode in new[]{"pending","fault","sync"}) {
    var stale=new FusionNetworkManager();var fresh=new FusionNetworkManager();fresh.C.Mode=mode;
    FusionNetworkManager.Current=stale;FusionNetworkManager.Reads=0;
    PlatformManager_Steam.CheckFirst();FusionNetworkManager.Current=fresh;
    var left=PlatformManager_Steam.Leave();
    if(FusionNetworkManager.Reads!=2||stale.C.Moves!=0||!ReferenceEquals(fresh.C.Seen,left.Item1))throw new Exception("used stale getter result");
    var w=new Control {Mode=mode};PlatformManager_Steam.W=w;
    var right=mode=="pending"?PlatformManager_Steam.ResumedWait():PlatformManager_Steam.InlineWait();
    if(w.Frames!=10||!ReferenceEquals(w.Seen,right.Item1)||w.Moves!=1)throw new Exception("wrong frame storage");
    if(mode=="pending"){if(left.Item2.IsCompleted||right.Item2.IsCompleted||ReferenceEquals(left.Item1,right.Item1))throw new Exception("shared task");
        w.Gate.SetResult();right.Item2.GetResult();if(left.Item2.IsCompleted)throw new Exception("resumed wrong child");fresh.C.Gate.SetResult();}
    foreach(var (pair,ctl) in new[]{(left,fresh.C),(right,w)}){
        if(mode=="fault"){try{pair.Item2.GetResult();throw new Exception("missing fault");}catch(ApplicationException e) when(ReferenceEquals(ctl.Error,e)){} }
        else pair.Item2.GetResult(); if(ctl.Moves!=(mode=="pending"?2:1))throw new Exception("wrong resumption");}
    Console.WriteLine($"{mode}: fresh manager, {w.Frames} frames, both tasks {right.Item1.Status}");
}
namespace UnityEngine { public class Object {} }
class Control {public string Mode;public int Frames,Moves;public Task Seen;public TaskCompletionSource Gate=new();public ApplicationException Error=new();}
class FusionNetworkManager:UnityEngine.Object {public Control C=new();public static FusionNetworkManager Current;public static int Reads;
public static FusionNetworkManager Instance{get{Reads++;return Current;}}
'''+wrapper[0]+'\n'+leavestate+'\n'+child.replace('CONTROL','__4__this.C').replace('CAPTURE','')+''' }
class PlatformManager_Steam {public static Control W;public static void CheckFirst(){'''+first[0]+'if('+first[1]+'==null)throw new Exception();}\n'+use('Leave',leave)+use('ResumedWait',waits[0])+use('InlineWait',waits[1])+waitstate+'\n'+child.replace('CONTROL','W').replace('CAPTURE','c.Frames=frameCount;')+'}'
    runner=tmp_path/'runner';runner.mkdir();(runner/'Program.cs').write_text(case,encoding='utf8');print(run_case(tmp_path,runner).strip())


@pytest.mark.parametrize('defect',['partial peer','late overlapping read','changed formatting borrow','different getter reload','incompatible scalar field','new exception entry'])
def test_peer_windows_must_be_accepted_together(shift_runtime,monkeypatch,defect):
    meta,il=shift_runtime;d=Decompiler(Lifter(il));m=meta.methods[26224];td=meta.typedefs[m.declaring];d.lift_method(m,td);bs=d.L._blocks
    plans=lambda:inline_tasks(d.L,m,td,bs,d.eh)[0]
    assert len(plans())==2
    if defect=='new exception entry':monkeypatch.setitem(d.eh,'pads',d.eh['pads']+[0x18056cc4a])
    elif defect=='different getter reload':
        read=il.bin.read
        def changed(a,n):
            raw=read(a,n)
            if a==0x1804fe000 and n==79:
                raw=bytearray(raw);raw[0x3b]^=8;return bytes(raw)
            return raw
        monkeypatch.setattr(il.bin,'read',changed)
    else:
        from iced_x86 import Mnemonic as M,Register as R
        if defect=='partial peer':match=lambda i:0x18056cc4a<i.ip<0x18056cc80 and i.mnemonic==M.MOVSD and i.memory_base==R.RAX
        elif defect=='late overlapping read':match=lambda i:i.ip==0x18056cdd2
        elif defect=='changed formatting borrow':match=lambda i:i.ip==0x18056c96f
        else:match=lambda i:0x18056cc4a<i.ip<0x18056cca9 and i.mnemonic==M.MOV and i.memory_base==R.RSP and i.immediate32==10
        b,j=next((b,j) for b in bs for j,i in enumerate(b.insns) if match(i));i=b.insns[j];raw=bytearray(il.bin.read(i.ip,i.len))
        if defect=='partial peer':raw[-1]-=8
        elif defect=='late overlapping read':raw[-4:]=(0x58).to_bytes(4,'little')
        elif defect=='changed formatting borrow':raw[-1]+=8
        else:raw[-5]-=8
        monkeypatch.setattr(b,'insns',b.insns[:j]+list(Decoder(64,bytes(raw),ip=i.ip))+b.insns[j+1:])
    assert not plans()
