"""Compile all three array-query loops, retaining both genuine lookups."""
import pytest
from iced_x86 import Register as R
from dotnet_case import run_case
from il2cpp import Decompiler,Lifter
from il2cpp.emitter import Emitter
from il2cpp.array_member import checked_ref_elements
from test_game_shift_shared_flags import shift_runtime

pytestmark=pytest.mark.game


def test_complete_saved_query_loops(shift_runtime,tmp_path):
    meta,il=shift_runtime;em=Emitter(il,str(tmp_path/'out'));methods=[]
    for j in (25646,25647,25648):
        m=meta.methods[j];em.emit_method(m,meta.typedefs[m.declaring],methods,'    ')
    src='''using System;using System.Linq;using System.Collections.Generic;using UnityEngine;
var inv=new InventoryManager();
foreach(string kind in new[]{"Landmine","Bear Trap","StunMine"})foreach(bool on in new[]{false,true})foreach(var mode in new[]{"all","empty","null array","null element","missing","fault"}){
 var trace=new List<string>();var boom=new ApplicationException();var a=new GameObject();var b=new GameObject();var live=new GameObject();var wrong=new GameObject();
 GameObject[] arr=mode=="empty"?Array.Empty<GameObject>():mode=="null array"?null:new[]{mode=="null element"?null:a,b};
 GameObject.Query=tag=>{if(tag!=kind||trace.Count!=0)throw new Exception("wrong/replayed query");trace.Add("find");return arr;};
 bool pair=kind!="Landmine";Trap Make(string id,bool caught){Trap t=kind=="Landmine"?new Landmine():kind=="Bear Trap"?new BearTrap():new StunMine();t.caught=caught;t.Action=x=>trace.Add(id+":"+x);return t;}
 int n=0;a.Lookup=type=>{trace.Add("a"+(++n));if(type!=Make("",false).GetType())throw new Exception("wrong spec");
    arr[0]=wrong;arr[1]=live;
    if(mode=="fault"&&(!pair||n==2))throw boom;if(mode=="missing")return null;return Make(n==1?"first":"second",false);};
 live.Lookup=t=>{trace.Add("next");return Make("last",true);};
 Exception error=null;try{inv.Run(kind,on);}catch(Exception e){error=e;}
 string want=mode switch{"empty" or "null array" or "null element"=>"find","missing"=>"find,a1","fault"=>pair?"find,a1,a2":"find,a1",_=>pair?"find,a1,a2,second:"+on+",next":"find,a1,first:"+on+",next,last:"+on};
 bool nullFault=mode.StartsWith("null")||mode=="missing";
 if(string.Join(',',trace)!=want||(mode=="fault"?!ReferenceEquals(error,boom):nullFault?error is not NullReferenceException:error!=null))throw new Exception(kind+"/"+mode+":"+string.Join(',',trace)+" "+error);
}
Console.WriteLine("three full tag-query loops: one query, live next element, preserved current receiver, true/false/caught and faults passed");
namespace UnityEngine {public class GameObject{public static Func<string,GameObject[]> Query;public static GameObject[] FindGameObjectsWithTag(string tag)=>Query(tag);public Func<Type,Trap> Lookup;public T GetComponent<T>()where T:Trap=>(T)Lookup(typeof(T));}}
public class Trap {public bool caught;public Action<bool> Action;public void EnableRadius()=>Action(true);public void DisableRadius()=>Action(false);} public class Landmine:Trap{}public class BearTrap:Trap{}public class StunMine:Trap{}
public class InventoryManager{public void Run(string kind,bool on){if(kind=="Landmine")ToggleLandmineRadii(on);else if(kind=="Bear Trap")ToggleBearTrapRadii(on);else ToggleStunMineRadii(on);}\n'''+ '\n'.join(methods)+'\n}'
    runner=tmp_path/'runner';runner.mkdir();(runner/'Program.cs').write_text(src,encoding='utf8');print(run_case(tmp_path,runner).strip())


@pytest.mark.parametrize('change',['header offset','index scale','extended index','wrong throw'])
def test_shared_array_element_proof_needs_checked_path(shift_runtime,monkeypatch,change):
    meta,il=shift_runtime;md=meta.methods[25647];d=Decompiler(Lifter(il));d.lift_method(md,meta.typedefs[md.declaring]);bs=d.L._blocks
    get=lambda:checked_ref_elements(d.L,md,bs,());ip,=get();b,k=next((b,k) for b in bs for k,i in enumerate(b.insns) if i.ip==ip);check=bs[b.preds[0]]
    target,j={'header offset':(check,-2),'index scale':(b,k),'extended index':(b,k-1),'wrong throw':(check,-1)}[change];j%=len(target.insns);i=target.insns[j].copy()
    if change=='header offset':i.memory_displacement=16
    elif change=='index scale':i.memory_index_scale=4
    elif change=='extended index':i.op1_register=R.ESI
    else:i.near_branch64=i.next_ip
    monkeypatch.setattr(target,'insns',target.insns[:j]+[i]+target.insns[j+1:]);assert ip not in get()
