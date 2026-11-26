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
