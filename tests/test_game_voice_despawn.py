"""Verify the complete emitted cleanup + tail callback against observable base/engine calls."""
import pytest

from dotnet_case import run_case
from il2cpp import Decompiler,Lifter
from test_game_shift_shared_flags import body,shift_runtime

pytestmark=pytest.mark.game


def test_voice_manager_despawns_after_cleanup(body,tmp_path):
    method=body('VoiceVolumeManager','Despawned',0x180619510)
    assert method.count('base.Despawned(runner, hasState)')==1 and 'sub_' not in method
    runner=tmp_path/'runner';runner.mkdir()
    (runner/'Program.cs').write_text('''using System;
using System.Collections.Generic;
foreach(bool flag in new[]{false,true}) foreach(bool withRunner in new[]{false,true})
foreach(string mode in new[]{"self","other","replaced","no coroutine","stop throws","compare throws","base throws"}) {
    var trace=new List<string>(); var self=new VoiceVolumeManager();var other=new VoiceVolumeManager();
    var runner=withRunner?new NetworkRunner():null;var routine=mode=="no coroutine"?null:new Coroutine();
    self.discoverHandlersCoroutine=routine;VoiceVolumeManager.__field_Instance=mode=="other"?other:self;
    self.Stop=c=>{trace.Add("stop");if(!ReferenceEquals(c,routine) || !ReferenceEquals(self.discoverHandlersCoroutine,c))throw new Exception("wrong handle");
        if(mode=="stop throws")throw new ApplicationException("stop");
        self.discoverHandlersCoroutine=new Coroutine();if(mode=="replaced")VoiceVolumeManager.__field_Instance=other;};
    VoiceVolumeManager.Compare=(a,b)=>{trace.Add("compare");
        if(!ReferenceEquals(a,VoiceVolumeManager.__field_Instance) || !ReferenceEquals(b,self) || self.discoverHandlersCoroutine is not null)throw new Exception("compared too early");
        if(mode=="compare throws")throw new ApplicationException("compare");return ReferenceEquals(a,b);};
    self.OnBase=(r,s)=>{trace.Add("base");if(!ReferenceEquals(r,runner) || s!=flag || self.discoverHandlersCoroutine is not null ||
        !ReferenceEquals(VoiceVolumeManager.__field_Instance, mode is "replaced" or "other"?other:null))throw new Exception("wrong args or incomplete cleanup");
        if(mode=="base throws")throw new ApplicationException("base");};
    string failure=null;try {((Behaviour)self).Despawned(runner,flag);}catch(ApplicationException e){failure=e.Message;}
    string want=mode switch {"stop throws"=>"stop", "compare throws"=>"stop;compare", "no coroutine"=>"compare;base", _=>"stop;compare;base"};
    if(string.Join(";",trace)!=want || failure!=(mode.EndsWith(" throws")?mode.Split(' ')[0]:null))throw new Exception(mode);
    if(mode=="stop throws" && !ReferenceEquals(self.discoverHandlersCoroutine,routine) ||
        mode is "stop throws" or "compare throws" && !ReferenceEquals(VoiceVolumeManager.__field_Instance,self))throw new Exception("cleanup continued on throw");
    if(withRunner && flag)Console.WriteLine(mode+": "+want);
}
class NetworkRunner { }
class Coroutine { // A managed reference check must not call an overloaded comparison.
    public static bool operator ==(Coroutine a,Coroutine b)=>throw new Exception("wrong coroutine null test");
    public static bool operator !=(Coroutine a,Coroutine b)=>throw new Exception("wrong coroutine null test");
    public override bool Equals(object o)=>ReferenceEquals(this,o);public override int GetHashCode()=>base.GetHashCode();}
class Behaviour {public Action<NetworkRunner,bool> OnBase;public virtual void Despawned(NetworkRunner runner,bool hasState)=>OnBase(runner,hasState);}
class VoiceVolumeManager:Behaviour {public Coroutine discoverHandlersCoroutine; public static VoiceVolumeManager __field_Instance;
    public Action<Coroutine> Stop;void StopCoroutine(Coroutine c)=>Stop(c);
    public static Func<VoiceVolumeManager,VoiceVolumeManager,bool> Compare;
    public static bool operator ==(VoiceVolumeManager a,VoiceVolumeManager b)=>Compare(a,b);
    public static bool operator !=(VoiceVolumeManager a,VoiceVolumeManager b)=>!Compare(a,b);
    public override bool Equals(object o)=>ReferenceEquals(this,o);public override int GetHashCode()=>base.GetHashCode();
    public override void Despawned(NetworkRunner runner,bool hasState){\n'''+method+'\n}}',encoding='utf-8')
    print(run_case(tmp_path,runner).strip())


@pytest.mark.parametrize('defect',['clobbered saved flag','changed runner','wrong restore','branch past reload','other slot','nontrivial callee'])
def test_inexact_cleanup_tail_keeps_fallback(shift_runtime,monkeypatch,defect):
    from iced_x86 import Decoder
    import il2cpp.dec.analyze as analyze
    meta,il=shift_runtime;md=meta.methods[28413];td=meta.typedefs[md.declaring];d=Decompiler(Lifter(il))
    if defect=='other slot': monkeypatch.setattr(md,'slot',25)
    elif defect=='nontrivial callee':
        read=il.bin.read
        monkeypatch.setattr(il.bin,'read',lambda p,n:b'\x89\x01\xc3' if (p,n)==(0x180507120,3) else read(p,n))
    else:
        fold=analyze.shared_action_tail
        def changed(l,ins,seq,args,regs):
            if ins.ip!=0x18061963a: return fold(l,ins,seq,args,regs)
            ip,raw={'clobbered saved flag':(0x180619566,'488db3b8000000'), # LEA into RSI instead of RCX
                    'changed runner':(0x180619620,'488bd3'),             # RDX from RBX, not RBP
                    'wrong restore':(0x180619630,'488b742438'),
                    'branch past reload':(0x1806195d1,'7453')}[defect]
            block=next(b for b in l._blocks if any(i.ip==ip for i in b.insns));k=next(k for k,i in enumerate(block.insns) if i.ip==ip)
            new=Decoder(64,bytes.fromhex(raw),ip=ip).decode();assert new.len==block.insns[k].len
            with monkeypatch.context() as p:
                p.setattr(block,'insns',block.insns[:k]+[new]+block.insns[k+1:]);return fold(l,ins,l.out.block.insns,args,regs)
        monkeypatch.setattr(analyze,'shared_action_tail',changed)
    text='\n'.join(d.lift_method(md,td));assert 'base.Despawned(' not in text and 'sub_180507120/*shared body,' in text


def test_voice_handler_box_and_cleanup_precede_base(body,tmp_path):
    method=body('VoiceVolumeHandler','Despawned',0x180617230)
    assert method.count('base.Despawned(runner, hasState)')==1 and 'sub_180507120' not in method
    runner=tmp_path/'runner';runner.mkdir()
    (runner/'Program.cs').write_text('''using System;
using System.Collections.Generic;
using UnityEngine;
foreach(bool flag in new[]{false,true}) foreach(bool haveRunner in new[]{false,true})
foreach(string mode in new[]{"remote","local","no routine","no manager","replaced with null","log throws","stop throws","unregister throws","base throws"}) {
    var tr=new List<string>();var self=new VoiceVolumeHandler();var runner=haveRunner?new NetworkRunner():null;
    var routine=mode=="no routine"?null:new Coroutine();self.registerCoroutine=routine;self.__field_thisPlayerUsername="before";
    var original=new VoiceVolumeManager();var replacement=new VoiceVolumeManager();var active=mode=="no manager"?null:original;
    Debug.Write=(s,ctx)=>{tr.Add("log");if(s!=$"[VoiceVolumeHandler] Despawned | GO='voice' | Username='before' | HasState={flag}" || !ReferenceEquals(ctx,self))throw new Exception("boxed flag, context or text");
        if(mode=="log throws")throw new ApplicationException("log");self.__field_thisPlayerUsername="after";};
    self.Stop=c=>{tr.Add("stop");if(!ReferenceEquals(c,routine))throw new Exception("wrong coroutine");if(mode=="stop throws")throw new ApplicationException("stop");};
    self.Local=()=>{tr.Add("authority");if(self.registerCoroutine is not null)throw new Exception("uncleared coroutine");return mode=="local";};
    VoiceVolumeManager.Read=()=>{tr.Add("manager");return active;};
    VoiceVolumeManager.Alive=m=>{tr.Add("alive");active=mode=="replaced with null"?null:replacement;return m is not null;};
    original.Unregister=(_,_)=>throw new Exception("stale singleton");
    replacement.Unregister=(user,handler)=>{tr.Add("unregister");if(user!="after" || !ReferenceEquals(handler,self))throw new Exception("wrong unregister");
        if(mode=="unregister throws")throw new ApplicationException("unregister");};
    self.Base=(r,s)=>{tr.Add("base");if(!ReferenceEquals(r,runner) || s!=flag)throw new Exception("wrong base arguments");if(mode=="base throws")throw new ApplicationException("base");};
    string failure=null;try {((Behaviour)self).Despawned(runner,flag);}catch(ApplicationException e){failure=e.Message;}catch(NullReferenceException){failure="null";}
    string wanted=mode switch {"log throws"=>"log","stop throws"=>"log;stop","local"=>"log;stop;authority;base",
        "no manager"=>"log;stop;authority;manager;alive;base","replaced with null"=>"log;stop;authority;manager;alive;manager",
        _=>(mode=="no routine"?"log":"log;stop")+";authority;manager;alive;manager;unregister"+(mode=="unregister throws"?"":";base")};
    if(string.Join(";",tr)!=wanted || failure!=(mode.EndsWith(" throws")?mode.Split(' ')[0]:mode=="replaced with null"?"null":null))throw new Exception(mode+": "+string.Join(";",tr));
    if(mode=="remote" && haveRunner)Console.WriteLine($"hasState={flag}: {wanted}");
}
class NetworkRunner {} class Coroutine {} class GameObject {public string name="voice";}
namespace UnityEngine {class Debug {public static Action<string,object> Write;public static void Log(string s,object o)=>Write(s,o);} }
class Behaviour {public Action<NetworkRunner,bool> Base; public virtual void Despawned(NetworkRunner runner,bool hasState)=>Base(runner,hasState);}
class VoiceVolumeManager {public static Func<VoiceVolumeManager> Read; public static VoiceVolumeManager Instance=>Read();
    public static Func<VoiceVolumeManager,bool> Alive;public static bool operator !=(VoiceVolumeManager a,VoiceVolumeManager b)=>Alive(a);
    public static bool operator ==(VoiceVolumeManager a,VoiceVolumeManager b)=>!Alive(a);public override bool Equals(object o)=>ReferenceEquals(this,o);public override int GetHashCode()=>base.GetHashCode();
    public Action<string,VoiceVolumeHandler> Unregister;public void UnregisterPlayer(string s,VoiceVolumeHandler h)=>Unregister(s,h);}
class VoiceVolumeHandler:Behaviour {public GameObject gameObject=new(); public string __field_thisPlayerUsername; public Coroutine registerCoroutine;
    public Action<Coroutine> Stop;void StopCoroutine(Coroutine c)=>Stop(c);public Func<bool> Local;bool HasLocalInputAuthority()=>Local();
    public override void Despawned(NetworkRunner runner,bool hasState){\n'''+method+'\n}}',encoding='utf-8')
    print(run_case(tmp_path,runner).strip())


@pytest.mark.parametrize('defect',['wrong boxed type','other box helper','jump into borrow','wrong trap'])
def test_voice_handler_requires_bounded_boolean_box(shift_runtime,monkeypatch,defect):
    from il2cpp import shared_action
    meta,il=shift_runtime; d=Decompiler(Lifter(il));m=meta.methods[28386];td=meta.typedefs[m.declaring]
    if defect=='wrong boxed type':
        old=il.decode_slot
        monkeypatch.setattr(il,'decode_slot',lambda slot:{'kind':2,'td':td.index,'text':'typeof(VoiceVolumeHandler)'} if slot==0x183e9f1b8 else old(slot))
    else:
        check=shared_action._cleanup_tail_forward
        def changed(l,b,ins,**kwargs):
            if ins.ip!=0x1806174ee:return check(l,b,ins,**kwargs)
            ip={'other box helper':0x18061738f,'jump into borrow':0x18061736b,'wrong trap':0x1806174f3}[defect]
            dest=next(bb for bb in l._blocks if any(i.ip==ip for i in bb.insns));j=next(j for j,i in enumerate(dest.insns) if i.ip==ip)
            # Redirect the near bounds branch into the store, bypassing the
            # LEA that bound RDX. All instruction boundaries stay the same.
            i=dest.insns[j].copy();i.near_branch64=0x18061738a if defect=='jump into borrow' else 0x1804353d0
            with monkeypatch.context() as p:
                p.setattr(dest,'insns',dest.insns[:j]+[i]+dest.insns[j+1:]);return check(l,b,ins,**kwargs)
        monkeypatch.setattr(shared_action,'_cleanup_tail_forward',changed)
    text='\n'.join(d.lift_method(m,td))
    assert 'base.Despawned(' not in text and 'sub_180507120/*shared body,' in text
