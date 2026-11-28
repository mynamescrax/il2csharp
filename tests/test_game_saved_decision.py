import pytest
from dotnet_case import run_case
from il2cpp.emitter import Emitter
from test_game_shift_shared_flags import shift_runtime

pytestmark=pytest.mark.game


def test_cursor_mode_and_visibility_share_one_post_poll_decision(shift_runtime,tmp_path):
    meta,il=shift_runtime;m=meta.methods[23627];lines=[];Emitter(il,str(tmp_path/'out')).emit_method(m,meta.typedefs[m.declaring],lines,'    ')
    src='''using System;using System.Collections.Generic;using System.Linq;using UnityEngine;using UnityEngine.InputSystem;
foreach (bool request in new[]{false,true})foreach (string scheme in new[]{"KB+M","Gamepad",null})foreach(string mode in new[]{"normal","clear in poll","set in poll","poll","lock","visible","reenter","null"}){
 var c=new CursorControlSchemeGate();var p=new PlayerInput();c.playerInput=mode=="null"?null:p;var ex=new ApplicationException();var trace=new List<string>();bool inner=false;
 void Step(string s){trace.Add((inner?"inner ":"")+s);if(!inner && mode==s)throw ex;}
 p.Read=()=>{if(c.cursorUnlockRequested!=(inner?false:request))throw new Exception("request not stored before getter");Step("poll");if(!inner&&mode=="clear in poll")c.cursorUnlockRequested=false;if(!inner&&mode=="set in poll")c.cursorUnlockRequested=true;return scheme;};
 bool decision=scheme=="KB+M"&&(mode=="clear in poll"?false:mode=="set in poll"?true:request);
 Cursor.Lock=v=>{if(v!=(inner||!decision?CursorLockMode.Locked:CursorLockMode.None))throw new Exception("wrong lock mode");Step("lock");if(!inner&&mode=="reenter"){inner=true;c.Run(false);inner=false;}else c.cursorUnlockRequested=!decision;};
 Cursor.Set=v=>{if(v!=(inner?false:decision))throw new Exception("wrong visibility after callback");Step("visible");};Exception fault=null;try{c.Run(request);}catch(Exception e){fault=e;}
 var wanted=mode switch{"null"=>"","poll"=>"poll","lock"=>"poll,lock","reenter"=>"poll,lock,inner poll,inner lock,inner visible,visible",_=>"poll,lock,visible"};
 if(string.Join(',',trace)!=wanted||(mode=="null"?fault is not NullReferenceException:mode is "poll" or "lock" or "visible"?!ReferenceEquals(fault,ex):fault!=null)||mode=="poll"&&c.cursorUnlockRequested!=request)throw new Exception(mode+":"+string.Join(',',trace),fault);
}
Console.WriteLine("whole cursor request: late request read, enum complement, saved visible value, reentry and fault cutoffs");
namespace UnityEngine{public enum CursorLockMode{None=0,Locked=1,Confined=2}public static class Cursor{public static Action<CursorLockMode> Lock;public static Action<bool> Set;public static CursorLockMode lockState{set=>Lock(value);}public static bool visible{set=>Set(value);}}}
namespace UnityEngine.InputSystem{public class PlayerInput{public Func<string> Read;public string currentControlScheme=>Read();}}
class CursorControlSchemeGate{public PlayerInput playerInput;public bool cursorUnlockRequested;public void Run(bool request)=>SetCursorUnlockRequested(request);\n'''+ '\n'.join(lines)+'\n}'
    r=tmp_path/'r';r.mkdir();(r/'Program.cs').write_text(src,encoding='utf8');print(run_case(tmp_path,r))


@pytest.mark.parametrize('change',['other field','changed inversion','different saved byte','wrong setter','missing equality','stale equality','skipped use','unsaved register'])
def test_two_setter_proof_needs_the_same_parked_decision(shift_runtime,monkeypatch,change):
    from il2cpp import Decompiler,Lifter
    from il2cpp.saved_decision import decision_sites
    from iced_x86 import Register as R
    meta,il=shift_runtime;m=meta.methods[23627];td=meta.typedefs[m.declaring];d=Decompiler(Lifter(il));d.lift_method(m,td);bs=d.L._blocks
    scan=lambda:decision_sites(d.L,m,td,bs,());actions,sources=scan();assert set(actions)=={0x18050316a} and sources=={0x180503165}
    if change in ('missing equality','stale equality','skipped use'):
        # A text-identical result of another evaluation does not define AL.
        from il2cpp.saved_decision import apply_decision
        from il2cpp.expr import Expr,_BOOL_TY
        captured=Expr('sample',_BOOL_TY,'int');recv=Expr('this',(td.index,0x12<<16),'obj')
        monkeypatch.setattr(d.L,'_decision_results',{} if change=='missing equality' else {0x180503165:captured})
        monkeypatch.setattr(d.L,'regs',{'RBX':recv,'RAX':Expr('sample',_BOOL_TY,'int') if change=='stale equality' else captured})
        out=[];monkeypatch.setattr(d.L,'emit',lambda *a:out.append(a));state={}
        assert not apply_decision(d.L,0x18050316a,actions[0x18050316a],state,{0x18050317e} if change=='skipped use' else ()) and not out and not state;return
    if change=='unsaved register':
        ips={0x18050316d:('op0_register',R.ESI),0x180503170:('op1_register',R.ESI),0x18050317e:('op1_register',R.SIL)}
        for b in bs:
            s=list(b.insns)
            for j,i in enumerate(s):
                if i.ip in ips:
                    i=i.copy();k,v=ips[i.ip];setattr(i,k,v);s[j]=i
            monkeypatch.setattr(b,'insns',s)
        assert scan()==({},set());return
    ip={'other field':0x18050316a,'changed inversion':0x180503174,'different saved byte':0x18050317e,'wrong setter':0x180503186}[change]
    b,j=next((b,j) for b in bs for j,i in enumerate(b.insns) if i.ip==ip);i=b.insns[j].copy()
    if change=='other field':i.memory_displacement+=1
    elif change=='changed inversion':i.immediate8=2
    elif change=='different saved byte':i.op1_register=R.AL
    else:i.near_branch64=0x182bb54b0
    monkeypatch.setattr(b,'insns',b.insns[:j]+[i]+b.insns[j+1:]);assert scan()==({},set())
