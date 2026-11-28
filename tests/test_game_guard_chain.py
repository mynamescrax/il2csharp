import pytest
from dotnet_case import run_case
from il2cpp.emitter import Emitter
from test_game_shift_shared_flags import shift_runtime

pytestmark=pytest.mark.game


def test_blink_reacquires_player_manager_and_blink_object(shift_runtime,tmp_path):
    meta,il=shift_runtime;m=meta.methods[25329];lines=[];Emitter(il,str(tmp_path/'out')).emit_method(m,meta.typedefs[m.declaring],lines,'    ')
    s='''using System;using System.Collections.Generic;using System.Linq;using UnityEngine;
foreach(string mode in new[]{"root","player","object","first read","first root null","first player null","first object null","off","second read","second root null","second player null","second object null","on"}){
 var a=new GameObject();var b=new GameObject();var p=new PlayerManager{smallBlink=a};var initial=new ClientPlayer{playerMan=p};var q=new PlayerManager{smallBlink=b};var next=new ClientPlayer{playerMan=q};var live=initial;
 var trace=new List<string>();var err=new ApplicationException();int reads=0;void Step(string s){trace.Add(s);if(s==mode)throw err;}
 if(mode=="first root null")live=null;else if(mode=="first player null")initial.playerMan=null;else if(mode=="first object null")p.smallBlink=null;
 ClientPlayer.Get=()=>{Step(++reads==1?"first read":"second read");return live;};a.Set=v=>{if(v)throw new Exception("old receiver enabled");Step("off");switch(mode){case "player":initial.playerMan=q;break;case "object":p.smallBlink=b;break;case "second root null":live=null;break;case "second player null":live=new ClientPlayer();break;case "second object null":p.smallBlink=null;break;default:live=next;break;}};b.Set=v=>{if(!v)throw new Exception();Step("on");};
 Exception fault=null;try{new FinaleStartCutscene().Run();}catch(Exception e){fault=e;}int n=mode.StartsWith("first")?1:mode=="off"?2:mode.StartsWith("second")?3:4;
 if(!trace.SequenceEqual(new[]{"first read","off","second read","on"}.Take(n))||(mode.EndsWith(" null")?fault is not NullReferenceException:mode.EndsWith(" read")||mode is "off" or "on"?!ReferenceEquals(fault,err):fault!=null))throw new Exception(mode+":"+string.Join(',',trace),fault);
}
Console.WriteLine("whole blink: all three references reacquired after deactivation; nulls and faults at either stage");
namespace UnityEngine{public class GameObject{public Action<bool> Set;public void SetActive(bool active)=>Set(active);}}
class ClientPlayer{public static Func<ClientPlayer> Get;public static ClientPlayer Instance=>Get();public PlayerManager playerMan;}
class PlayerManager{public GameObject smallBlink;}class FinaleStartCutscene{public void Run()=>SmallBlink();\n'''+ '\n'.join(lines)+'\n}'
    r=tmp_path/'r';r.mkdir();(r/'Program.cs').write_text(s,encoding='utf8');print(run_case(tmp_path,r))


@pytest.mark.parametrize('bad',['other field','other receiver','wrong throw','uncleared info','overwritten argument','wrong deallocation'])
def test_nested_guard_consumer_requires_both_complete_chains(shift_runtime,monkeypatch,bad):
    from iced_x86 import Register as R
    from il2cpp import Decompiler,Lifter
    from il2cpp.inline_static_guard import checked_statics
    meta,il=shift_runtime;m=meta.methods[25329];td=meta.typedefs[m.declaring];d=Decompiler(Lifter(il));d.lift_method(m,td);bs=d.L._blocks
    find=lambda:checked_statics(d.L,m,bs,());assert set(find())=={0x1806e450e,0x1806e4562}
    ip={'other field':0x1806e4576,'other receiver':0x1806e4576,'wrong throw':0x1806e4574,'uncleared info':0x1806e4582,'overwritten argument':0x1806e4585,'wrong deallocation':0x1806e4587}[bad]
    b,j=next((b,j) for b in bs for j,i in enumerate(b.insns) if i.ip==ip);i=b.insns[j].copy()
    if bad=='other field':i.memory_displacement+=1
    elif bad=='other receiver':i.memory_base=R.RDX
    elif bad=='wrong throw':i.near_branch64=0x1806e4582
    elif bad=='uncleared info':i.op0_register=i.op1_register=R.R9D
    elif bad=='wrong deallocation':i.immediate8=0x20
    else:i.immediate8=2
    monkeypatch.setattr(b,'insns',b.insns[:j]+[i]+b.insns[j+1:]);assert not find()
