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
