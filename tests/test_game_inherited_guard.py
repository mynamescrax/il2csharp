import pytest
from iced_x86 import Register as R
from dotnet_case import run_case
from il2cpp import Decompiler,Lifter
from il2cpp.emitter import Emitter
from il2cpp.inherited_guard import inherited_guards
from test_game_shift_shared_flags import shift_runtime

pytestmark=pytest.mark.game


def test_authority_gates_use_the_loaded_network_object(shift_runtime,tmp_path):
    meta,il=shift_runtime;em=Emitter(il,str(tmp_path/'out'));classes=[]
    cases={26827:('PlayerLeft(default);','void CheckIfAnyoneCanBeRevived()=>Effect();'),
           27794:('ToggleMultiplayerObjects();','void Rpc_CMD_ToggleMultiplayerObjects()=>Effect();'),
           24756:('SecondCheckForAfterCarObjs();','public int curDay;void Rpc_TurnOnAfterCarObjs()=>Effect();'),
           25121:('GoBackToMenu();','void Invoke(string s,float f){if(s!="Rpc_ActuallyGoBackToMenu"||f!=1f)throw new Exception();Effect();}'),
           26612:('FinishEatingFlesh();','public bool currentlyEatingFlesh=true;public GameObject trackedFleshTarget=new();void FindDifferentFleshPiece(){if(currentlyEatingFlesh||trackedFleshTarget!=null)throw new Exception();Effect();}'),
           28444:('Start();','public Path pathfinder=new(); public float speed;void StartNextPathway(){if(pathfinder.maxSpeed!=11.5f)throw new Exception();Effect();}'),
           25057:('FixedUpdate();','public bool tickRevenue,tickDownRevenue; public Action Up,Down;void Rpc_TickRevenue()=>Up();void Rpc_TickDownRevenue()=>Down();')}
    for j,(run,extra) in cases.items():
        m=meta.methods[j];td=meta.typedefs[m.declaring];lines=[];em.emit_method(m,td,lines,'    ')
        assert not any('._object' in s for s in lines) and sum(s.count(' = this.Object;') for s in lines)==(2 if j==25057 else 1)
        classes.append('class '+td.name+':NetworkBehaviour{public override void Run(){'+run+'}'+extra+'\n'+'\n'.join(lines)+'\n}')
    src='''using System;using System.Collections.Generic;using System.Linq;using Fusion;
foreach(NetworkBehaviour c in new NetworkBehaviour[]{new PlayerManager(),new StoreManager(),new CurrentDayManager(),new EndingScene(),new Pet(),new WanderAroundAimlessly()})
foreach(string mode in new[]{"yes","no","early day","null","get fault","auth fault","effect fault"}){
 var trace=new List<string>();var fail=new ApplicationException();bool auth=mode!="no"&&!(c is StoreManager&&mode=="effect fault");bool wanted=(c is StoreManager?!auth:auth)&&!(c is CurrentDayManager&&mode=="early day");
 var pet=c as Pet;if(pet!=null){pet.currentlyEatingFlesh=true;pet.trackedFleshTarget=new();}var wander=c as WanderAroundAimlessly;if(wander!=null){wander.pathfinder=new();wander.speed=-9;}
 var day=c as CurrentDayManager;if(day!=null)day.curDay=0;
 var n=new NetworkObject{Read=()=>{trace.Add("auth");if(mode=="auth fault")throw fail;if(day!=null)day.curDay=mode=="early day"?3:4;if(wander!=null)wander.speed=11.5f;return auth;}};
 c.Acquire=()=>{trace.Add("get");if(mode=="get fault")throw fail;return mode=="null"?null:n;};c.Effect=()=>{trace.Add("effect");if(mode=="effect fault")throw fail;};
 Exception fault=null;try{c.Run();}catch(Exception e){fault=e;}
 string want=mode is "null" or "get fault"?"get":mode=="auth fault"||!wanted?"get,auth":"get,auth,effect";
 if(string.Join(',',trace)!=want||(mode=="null"?fault is not NullReferenceException:mode is "auth fault" or "get fault"||wanted&&mode=="effect fault"?!ReferenceEquals(fault,fail):fault!=null))throw new Exception(c.GetType()+"/"+mode+":"+string.Join(',',trace),fault);
 if(pet!=null&&(pet.currentlyEatingFlesh!=(!trace.Contains("effect"))||(pet.trackedFleshTarget is null)!=trace.Contains("effect")))throw new Exception("early mutation");}
foreach(bool first in new[]{true,false})foreach(bool enabled in new[]{true,false})foreach(bool grantFirst in new[]{true,false})foreach(bool grantSecond in new[]{true,false}){
 var report=new EndOfDayReport{tickRevenue=first,tickDownRevenue=(!first||!grantFirst)&&enabled};var trace=new List<string>();
 var b=new NetworkObject{Read=()=>{trace.Add("B");return grantSecond;}};var current=b;var a=new NetworkObject{Read=()=>{trace.Add("A");current=b;return grantFirst;}};current=first?a:b;
 report.Acquire=()=>{trace.Add("object");return current;};report.Up=()=>{trace.Add("up");report.tickDownRevenue=enabled;current=b;};report.Down=()=>trace.Add("down");report.Run();
 var want=(first?"object,A,"+(grantFirst?"up,":""):"")+(enabled?"object,B,"+(grantSecond?"down,":""):"");if(string.Join(',',trace)!=want.TrimEnd(','))throw new Exception(string.Join(',',trace));}
Console.WriteLine("seven complete authority callbacks: positive/negative routes, independent reloads, field writes, delays and exceptions passed");
namespace Fusion{public record struct PlayerRef(int Id);public class NetworkObject{public Func<bool> Read;public bool HasStateAuthority=>Read();}}
public abstract class SimulationBehaviour{public Func<NetworkObject> Acquire;public NetworkObject Object=>Acquire();}public abstract class NetworkBehaviour:SimulationBehaviour{public Action Effect;public bool HasStateAuthority=>throw new Exception("wrong outer getter");public abstract void Run();}class GameObject{}class Path{public float maxSpeed;}
'''+ '\n'.join(classes)
    runner=tmp_path/'runner';runner.mkdir();(runner/'Program.cs').write_text(src,encoding='utf8');print(run_case(tmp_path,runner).strip())


@pytest.mark.parametrize('defect',['getter reads neighbor','wrong receiver','hidden inherited name'])
def test_authority_alias_relies_on_exact_load_and_binding(shift_runtime,monkeypatch,defect):
    meta,il=shift_runtime;md=meta.methods[26827];d=Decompiler(Lifter(il));d.lift_method(md,meta.typedefs[md.declaring]);bs=d.L._blocks
    prove=lambda:inherited_guards(d.L,md,bs,());ip,=prove()
    if defect=='getter reads neighbor':
        old=il.bin.read;monkeypatch.setattr(il.bin,'read',lambda a,n:bytes.fromhex('488b4148c3') if a==0x180641990 and n==5 else old(a,n))
    elif defect=='hidden inherited name':
        import il2cpp.inherited_guard as mod
        old=mod.declares_member_name;monkeypatch.setattr(mod,'declares_member_name',lambda i,t,n:(t.index==md.declaring and n=='Object') or old(i,t,n))
    else:
        b,j=next((b,j) for b in bs for j,i in enumerate(b.insns) if i.ip==ip);i=b.insns[j].copy();i.memory_base=R.R10
        monkeypatch.setattr(b,'insns',b.insns[:j]+[i]+b.insns[j+1:])
    assert ip not in prove()
