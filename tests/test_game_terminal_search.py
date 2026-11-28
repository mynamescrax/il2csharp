import pytest
from dotnet_case import run_case
from il2cpp.emitter import Emitter
from test_game_shift_shared_flags import shift_runtime

pytestmark = pytest.mark.game


def test_item_checks_keep_match_miss_and_bypass_effects(shift_runtime, tmp_path):
    meta, il = shift_runtime
    em = Emitter(il, str(tmp_path/'out'))
    bodies = {}
    for mi in (24284, 24655):
        m = meta.methods[mi]; td = meta.typedefs[m.declaring]
        lines = []; em.emit_method(m, td, lines, '    ')
        bodies[mi] = '\n'.join(lines)
    src = '''using System;
using System.Collections.Generic;
using System.Linq;
foreach (bool plank in new[]{false,true})
foreach (bool bypassSeed in new[]{false,true})
foreach (string mode in new[]{"first","last","duplicate","empty","miss","array null","bypass","absent barricade","active fault","null holder hit","null holder miss","activate fault","deactivate fault","stop fault","client fault","null client","null player","null interactor"}) {
    if (!plank && mode is "bypass" or "absent barricade" or "active fault" or "null holder hit" or "null holder miss" or "activate fault" or "deactivate fault") continue;
    if (plank && mode is "client fault" or "null client" or "null player" or "null interactor") continue;
    var hit = mode is "first" or "last" or "duplicate" or "null holder hit" or "activate fault" or "client fault" or "null client" or "null player" or "null interactor";
    var err=new ApplicationException(); var trace=new List<string>(); var expected=new List<string>();
    void Step(string tag){trace.Add(tag);if(mode==tag+" fault")throw err;}
    var original=new object();var inter=new InteractManager{curInteractable=original};var player=new Player{interactMan=mode=="null interactor"?null:inter};
    var client=new ClientPlayer{playerMan=mode=="null player"?null:player};
    ConstrictedInteractable c=plank?new TestBarricade():new TestConstricted();c.constrictionAllows=mode=="bypass"?bypassSeed:!hit;
    var items=mode switch{"empty"=>Array.Empty<int>(),"last"=>new[]{2,4,1},"duplicate"=>new[]{1,2,1},"array null" or "bypass"=>null,_=>new[]{hit?1:3,4}};
    c.allowedItems=plank?null:items;
    c.OnStop=()=>{if(c.constrictionAllows)throw new Exception("stop before flag clear");Step("stop");};
    ClientPlayer.Get=()=>{if(!c.constrictionAllows)throw new Exception("client before flag set");Step("client");return mode=="null client"?null:client;};
    if (plank){var b=(Barricade)c;var fresh=mode.StartsWith("null holder")?null:new Go();b.colliderHolder=new Go{Set=_=>throw new Exception("stale holder")};
        b.barricade=mode=="absent barricade"?null:new Go();if(b.barricade!=null)b.barricade.Active=()=>{Step("active");c.allowedItems=items;b.colliderHolder=fresh;return mode=="bypass";};
        if(fresh!=null)fresh.Set=on=>{if(c.constrictionAllows!=(mode=="bypass"&&bypassSeed))throw new Exception("flag at holder call");Step(on?"activate":"deactivate");};}
    Exception fault=null;try{c.CheckForCurItem(1);}catch(Exception e){fault=e;}
    bool nullFault=mode is "absent barricade" or "array null" or "null holder hit" or "null holder miss" or "null client" or "null player" or "null interactor";
    if (plank && mode!="absent barricade")expected.Add("active");
    if(mode is not ("absent barricade" or "active fault" or "array null")) {
        if(plank && !mode.StartsWith("null holder"))expected.Add(hit?"activate":"deactivate");
        if(hit&&!plank)expected.Add("client");
        if(!hit && mode is not ("bypass" or "null holder miss" or "deactivate fault"))expected.Add("stop");
    }
    bool flagged = hit ? (!plank || mode is not ("null holder hit" or "activate fault")) : mode=="bypass"?bypassSeed:mode is "active fault" or "absent barricade" or "array null";
    if(c.constrictionAllows!=flagged|| !trace.SequenceEqual(expected) ||
       (inter.curInteractable==null)!=(!plank&&hit&&fault==null) ||
       (nullFault?fault is not NullReferenceException:mode.EndsWith(" fault")?!ReferenceEquals(err,fault):fault!=null))
        throw new Exception($"{plank}/{mode}: {string.Join(',',trace)} flag={c.constrictionAllows}",fault);
}
Console.WriteLine("both complete item checks: misses, matches, bypass, nulls, dispatch and callback faults");
class Go{public Func<bool> Active; public Action<bool> Set; public bool activeInHierarchy=>Active();public void SetActive(bool on)=>Set(on);}
class InteractManager{public object curInteractable;}class Player{public InteractManager interactMan;}class ClientPlayer{public Player playerMan;public static Func<ClientPlayer> Get;public static ClientPlayer Instance=>Get();}
class Interactable{public virtual void StopLookAt()=>throw new Exception("wrong virtual target");}
class ConstrictedInteractable:Interactable{public int[] allowedItems; public bool constrictionAllows;public Action OnStop;
''' + bodies[24655] + '\n}\nclass Barricade:ConstrictedInteractable{public Go barricade,colliderHolder;\n' + bodies[24284] + '''
}
class TestConstricted:ConstrictedInteractable{public override void StopLookAt()=>OnStop();}
class TestBarricade:Barricade{public override void StopLookAt()=>OnStop();}
'''
    runner=tmp_path/'runner';runner.mkdir();(runner/'Program.cs').write_text(src,encoding='utf8')
    print(run_case(tmp_path,runner))
