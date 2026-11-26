"""Compile the complete cleanup override; make each dictionary reload observable."""
import pytest

from dotnet_case import run_case
from il2cpp import Decompiler,Lifter
from test_game_shift_shared_flags import body,shift_runtime

pytestmark=pytest.mark.game


def test_uid_service_clears_before_tail_dispatch(body,tmp_path):
    method=body('UIDService','Despawned',0x180593d60)
    assert 'sub_' not in method and method.count('base.Despawned(runner, hasState)')==1
    runner=tmp_path/'runner';runner.mkdir()
    (runner/'Program.cs').write_text('''using System;
using System.Collections.Generic;
using Fusion;
using Key=Fusion.NetworkString_1<Fusion._64>;
foreach(bool flag in new[]{false,true}) foreach(bool haveRunner in new[]{false,true})
foreach(string mode in new[]{"both","not spawned","empty platform","empty actor","count throws","clear throws","base throws"}) {
    var log=new List<string>();var runner=haveRunner?new NetworkRunner():null;
    var service=new UIDService {_spawned=mode!="not spawned"};
    NetworkDictionary_2<Key,T> Make<T>(string tag,bool initial)=>new(()=>{
        if(!initial || !service._spawned)throw new Exception("Count on wrong snapshot");log.Add("count "+tag);
        if(mode=="count throws" && tag=="actor")throw new ApplicationException("count");
        return mode=="empty "+tag?0:2;
    },()=>{if(initial || !service._spawned)throw new Exception("Clear without fresh getter");log.Add("clear "+tag);
        if(mode=="clear throws" && tag=="platform")throw new ApplicationException("clear");});
    int platforms=0,actors=0;
    service.Platform=()=>Make<Key>("platform",platforms++==0);service.Actor=()=>Make<int>("actor",actors++==0);
    service.OnBase=(r,s)=>{if(service._spawned || !ReferenceEquals(r,runner) || s!=flag)throw new Exception("early base or wrong arguments");
        log.Add("base");if(mode=="base throws")throw new ApplicationException("base");};
    string failure=null;try{((NetworkBehaviour)service).Despawned(runner,flag);}catch(ApplicationException e){failure=e.Message;}
    var want=mode switch {"not spawned"=>"base", "empty platform"=>"count platform;count actor;clear actor;base",
        "empty actor"=>"count platform;clear platform;count actor;base", "count throws"=>"count platform;clear platform;count actor",
        "clear throws"=>"count platform;clear platform", _=>"count platform;clear platform;count actor;clear actor;base"};
    if(string.Join(";",log)!=want || service._spawned!=(mode is "count throws" or "clear throws") ||
        failure!=(mode.EndsWith(" throws")?mode.Split(' ')[0]:null))throw new Exception(mode+": "+string.Join(";",log));
    if(flag && haveRunner)Console.WriteLine(mode+": "+want);
}
namespace Fusion {
    struct _64 {} struct NetworkString_1<T> {} class NetworkRunner {}
    struct NetworkDictionary_2<K,V> {readonly Func<int> count; readonly Action clear;
        public NetworkDictionary_2(Func<int> c,Action a){count=c;clear=a;}public int Count=>count();public void Clear()=>clear();}
    class NetworkBehaviour { public Action<NetworkRunner,bool> OnBase; public virtual void Despawned(NetworkRunner runner,bool hasState)=>OnBase(runner,hasState); }
}
class UIDService:NetworkBehaviour {public bool _spawned;public Func<NetworkDictionary_2<Key,Key>> Platform;public Func<NetworkDictionary_2<Key,int>> Actor;
    NetworkDictionary_2<Key,Key> _fuidToPlatformID=>Platform();NetworkDictionary_2<Key,int> _fuidToActorID=>Actor();
    public override void Despawned(NetworkRunner runner,bool hasState){\n'''+method+'\n}}',encoding='utf-8')
    print(run_case(tmp_path,runner).strip())


@pytest.mark.parametrize('defect',['wrong anchor','other runner','shifted home','partial copy','crossed buffers','wrong instantiation','alternate entry'])
def test_r11_tail_does_not_hide_changed_cleanup(shift_runtime,monkeypatch,defect):
    from iced_x86 import Decoder
    from il2cpp import shared_action

    meta,il=shift_runtime;d=Decompiler(Lifter(il));m=meta.methods[26518];td=meta.typedefs[m.declaring]; check=shared_action.framed_cleanup_tail
    def changed(l,b,jump):
        if jump.ip!=0x180593f32:return check(l,b,jump)
        ip={'wrong anchor':0x180593f1a,'other runner':0x180593f14,'shifted home':0x180593f22,'partial copy':0x180593e37,
            'crossed buffers':0x180593e1c,'wrong instantiation':0x180593e15,'alternate entry':0x180593e00}[defect]
        bl=next(bl for bl in l._blocks if any(i.ip==ip for i in bl.insns));idx=next(k for k,i in enumerate(bl.insns) if i.ip==ip)
        i=bl.insns[idx];code=bytearray(il.bin.read(i.ip,i.len))
        if defect=='wrong anchor':code[-4]=0xd0   # lea r11,[rsp+0xd0] instead of +0xe0
        elif defect=='other runner':code[-1]=0xd3 # mov rdx,rbx instead of rsi
        elif defect=='shifted home':code[-1]+=8
        elif defect=='partial copy':code[-1]-=16
        elif defect=='crossed buffers':code[-1]=0x17
        elif defect=='wrong instantiation':code[-4:]=(0x183c0c3d8-i.next_ip).to_bytes(4,'little',signed=True)
        else:code[-4:]=(0x180593e10-i.next_ip).to_bytes(4,'little',signed=True)
        mutant=Decoder(64,bytes(code),ip=i.ip).decode();assert mutant.len==i.len
        with monkeypatch.context() as p:
            p.setattr(bl,'insns',bl.insns[:idx]+[mutant]+bl.insns[idx+1:]);return check(l,b,jump)
    monkeypatch.setattr(shared_action,'framed_cleanup_tail',changed)
    s='\n'.join(d.lift_method(m,td));assert 'base.Despawned(' not in s and 'sub_180507120/*shared body,' in s
