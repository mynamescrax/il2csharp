"""Compile the actual Start overrides and call them through the base type."""
import pytest

from dotnet_case import run_case
from test_game_shift_shared_flags import body, shift_runtime

pytestmark = pytest.mark.game


def test_direct_base_start_runs_once_before_derived_work(body,tmp_path):
    dialogue=body('DialogueInteractable','Start',0x1806c4fc0)
    pickup=body('PickupObject','Start',0x1805872a0)
    for method in (dialogue,pickup):
        # Fail without risking a process stack overflow on a regression.
        assert method.startswith('base.Start();') and method.count('base.Start();')==1 and 'this.Start();' not in method
    runner=tmp_path/'runner';runner.mkdir()
    (runner/'Program.cs').write_text('''using System;
using System.Collections.Generic;
using System.Linq;
var dialogue=new DialogueInteractable(); Interactable viaBase=dialogue;
var report=new EODReportValues(); EODReportValues.Instance=report;
dialogue.OnBase=()=>{dialogue.dialogueId="-37"; dialogue.pathfindScript=new Pathfind {addToReport=true};};
viaBase.Start();
if(dialogue.BaseCalls!=1 || !report.npcID.SequenceEqual(new[]{-37}))throw new Exception("did not resume after base.Start");
var fails=new DialogueInteractable{dialogueId="53",pathfindScript=new Pathfind{addToReport=true},OnBase=()=>throw new ApplicationException()};
try { ((Interactable)fails).Start(); throw new Exception("missing base failure"); }catch(ApplicationException) { }
if(fails.BaseCalls!=1 || report.npcID.Count!=1)throw new Exception("ran override after base threw");
var pickup=new PickupObject();pickup.OnBase=()=>pickup.amountText=new object();((Interactable)pickup).Start();
if(pickup.BaseCalls!=1 || !pickup.cantInteractIfDowned || !pickup.Delays.SequenceEqual(new[]{0.1f,0.2f,0.5f}))throw new Exception("pickup base dispatch");
Console.WriteLine("Dialogue: 1 base call, report [-37]; base throw: 1 call, no append. Pickup: 1 base call, 3 delayed invokes.");
class Interactable {public int BaseCalls;public Action OnBase;public virtual void Start(){BaseCalls++;OnBase();}}
class DialogueInteractable : Interactable {public Authority _object=new();public bool setNameToRandomSteamUser;
    public string dialogueId; public Pathfind pathfindScript;void Rpc_SetName(string name){} public override void Start(){\n'''+dialogue+'''\n}}
class PickupObject : Interactable {public object amountText;public bool cantInteractIfDowned;public List<float> Delays=new();
    public void Invoke(string method,float delay){if(method!="LoadAmountText")throw new Exception();Delays.Add(delay);}
    public override void Start(){\n'''+pickup+'''\n}}
class Pathfind {public bool addToReport;} class Authority {public bool HasStateAuthority;}
class EODReportValues {public static EODReportValues Instance; public List<int> npcID=new();}
class NetPlayerData {public string _Gamertag;}
class PlatformManager {public static PlatformManager __field_Instance; public List_1<NetPlayerData> GetLobbyMembers()=>new();public string GetPlayerGamertag()=>"test";}
namespace System.Collections.Generic { class List_1<T>:List<T>{public int _size=>Count;} }
namespace UnityEngine {class Object {public static bool op_Implicit(Pathfind p)=>p is not null;} class Random {public static int Range(int a,int b)=>a;} }
''',encoding='utf-8')
    print(run_case(tmp_path,runner).strip())


def test_identical_spelling_does_not_prove_an_override(shift_runtime,monkeypatch):
    from il2cpp import Decompiler,Lifter
    meta,il=shift_runtime;d=Decompiler(Lifter(il));md=meta.methods[24853];td=meta.typedefs[md.declaring]
    monkeypatch.setattr(md,'flags',md.flags|0x100)  # newslot, not an override of Interactable.Start
    lines=d.lift_method(md,td)
    assert 'this.Start();' in lines and 'base.Start();' not in lines


def test_pickup_spawned_calls_inherited_slot_before_state_change(body,tmp_path):
    spawned=body('PickupObject','Spawned',0x180587200)
    assert spawned.startswith('base.Spawned() /* shared implementation */;') and 'sub_' not in spawned
    runner=tmp_path/'runner';runner.mkdir()
    (runner/'Program.cs').write_text('''using System;
using System.Collections.Generic;
using System.Linq;
foreach(var mode in new[]{"disable","skip","throw"}) {
    var p=new PickupObject(); NetworkBehaviour dispatch=p;
    p.OnBase=()=>{if(p._spawned)throw new Exception("base after state change");p.Trace.Add("base");
        if(mode=="throw")throw new ApplicationException();p.ignoreAutoDisableInteractable=mode=="skip";p.interactable=true;};
    try {dispatch.Spawned(); if(mode=="throw")throw new Exception("missing failure");}catch(ApplicationException) when(mode=="throw"){}
    if(string.Join(";",p.Trace)!=(mode=="disable"?"base;disable;invoke;invoke":"base") || p._spawned!=(mode!="throw") ||
        p.interactabilityBeforePaused!=(mode=="disable") || p.interactable!=(mode=="skip") ||
        !p.Delays.SequenceEqual(mode=="disable"?new[]{0.1f,0.3f}:Array.Empty<float>()))throw new Exception(mode);
    Console.WriteLine(mode+": "+string.Join(";",p.Trace)+", spawned="+p._spawned);
}
class NetworkBehaviour {public Action OnBase;public virtual void Spawned()=>OnBase();}
class Interactable : NetworkBehaviour { }
class PickupObject : Interactable { public bool _spawned,ignoreAutoDisableInteractable,interactabilityBeforePaused,interactable;
    public List<string> Trace=new();public List<float> Delays=new();
    void ChangeInteractableStatus(bool v){if(!_spawned || !interactabilityBeforePaused || v)throw new Exception();interactable=v;Trace.Add("disable");}
    void Invoke(string method,float delay){if(method!="LoadPendingItems")throw new Exception();Delays.Add(delay);Trace.Add("invoke");}
    public override void Spawned(){\n'''+spawned+'\n}}',encoding='utf-8')
    print(run_case(tmp_path,runner).strip())


@pytest.mark.parametrize('defect',['hidden by parent','wrong parent slot','different effect','live return'])
def test_inherited_spawn_declines_without_equivalence(shift_runtime,monkeypatch,defect):
    from il2cpp import Decompiler,Lifter
    from il2cpp import shared_action
    meta,il=shift_runtime;d=Decompiler(Lifter(il));md=meta.methods[26658];td=meta.typedefs[md.declaring]
    parent=il.types[td.parent][0]; target=0x180507120
    if defect=='hidden by parent':
        # A non-method declaration also stops C# base member lookup.
        fi=next(iter(meta.type_fields(meta.typedefs[parent])))
        from il2cpp.csharp import source_field_name
        source_field_name(il,fi)
        monkeypatch.setitem(il._source_field_names,fi,'Spawned')
    elif defect=='wrong parent slot':
        old=il.vtable_method
        monkeypatch.setattr(il,'vtable_method',lambda t,s:None if (t,s)==(parent,25) else old(t,s))
    elif defect=='different effect':
        read=il.bin.read
        monkeypatch.setattr(il.bin,'read',lambda p,n:b'\x31\xc0\xc3' if (p,n)==(target,3) else read(p,n))
    else:
        old=shared_action._unused_return
        monkeypatch.setattr(shared_action,'_unused_return',lambda l,ip:False if ip==0x18058722f else old(l,ip))
    text='\n'.join(d.lift_method(md,td))
    assert 'base.Spawned()' not in text and 'sub_180507120/*shared body,' in text
