import pytest
from dotnet_case import run_case
from il2cpp.emitter import Emitter
from test_game_shift_shared_flags import shift_runtime

pytestmark=pytest.mark.game


def test_id_search_exhausts_without_hint_and_stops_at_first_live_active(shift_runtime,tmp_path):
    meta,il=shift_runtime;m=meta.methods[25546];lines=[];Emitter(il,str(tmp_path/'out')).emit_method(m,meta.typedefs[m.declaring],lines,'    ')
    prog='''using System;using System.Linq;using System.Collections.Generic;using UnityEngine;
foreach(string mode in new[]{"bypass","null array","null item","empty","miss","hit","truth","activity","first read","null first","hint","second read","null second","next"}){
 var c=new IDCard{actualIDCard=mode!="bypass"};var trace=new List<string>();var err=new ApplicationException();void Step(string s){trace.Add(s);if(mode==s)throw err;}
 var destroyed=new GameObject();var inactive=new GameObject();var winner=new GameObject();var poison=new GameObject();var slots=new[]{destroyed,inactive,poison,poison};
 c.fakeID=mode switch{"bypass" or "null array"=>null,"null item"=>new GameObject[]{null},"empty"=>Array.Empty<GameObject>(),"miss"=>new[]{destroyed,inactive},_=>slots};
 UnityEngine.Object.Compare=(a,b)=>{if(b is not null)throw new Exception();if(a is null){Step("accept null");return true;}if(ReferenceEquals(a,destroyed)){Step("destroyed");return false;}if(ReferenceEquals(a,inactive)){Step("inactive check");return true;}if(ReferenceEquals(a,winner)){Step("truth");slots[2]=poison;c.fakeID=null;return true;}throw new Exception("replayed or past end");};
 inactive.Read=()=>{Step("inactive get");slots[2]=winner;return false;};winner.Read=()=>{Step("activity");return true;};poison.Read=()=>throw new Exception("used replacement");
 var first=new StoreManager();var second=new StoreManager();StoreManager.Get=()=>{Step("first read");return mode=="null first"?null:first;};first.Hint=s=>{if(s!="Use the Computer to SEARCH names.")throw new Exception("bad hint text:"+s);Step("hint");StoreManager.Get=()=>{Step("second read");return mode=="null second"?null:second;};};second.Advance=()=>Step("next");
 Exception ex=null;try{c.Run();}catch(Exception e){ex=e;}string[] path={"destroyed","inactive check","inactive get","truth","activity","first read","hint","second read","next"};int n=mode switch{"bypass" or "null array" or "empty"=>0,"miss"=>3,"hit"=>9,"null first"=>6,"null second"=>8,_=>Array.IndexOf(path,mode)+1};
 if(!trace.SequenceEqual(mode=="null item"?new[]{"accept null"}:path.Take(n))||(mode.StartsWith("null")?ex is not NullReferenceException:Array.IndexOf(path,mode)>=0?!ReferenceEquals(ex,err):ex!=null))throw new Exception(mode+":"+string.Join(',',trace),ex);
}
Console.WriteLine("complete ID check: bypass/empty/multiple rejections/first match, retained reference, late manager and faults");
namespace UnityEngine{public class Object{public static Func<Object,Object,bool> Compare;public static bool operator !=(Object a,Object b)=>Compare(a,b);public static bool operator ==(Object a,Object b)=>!Compare(a,b);public override bool Equals(object x)=>ReferenceEquals(this,x);public override int GetHashCode()=>base.GetHashCode();}public class GameObject:Object{public Func<bool> Read;public bool activeInHierarchy=>Read();}}
class StoreManager{public static Func<StoreManager> Get;public static StoreManager Instance=>Get();public Action<string> Hint;public Action Advance;public void AddHint(string s)=>Hint(s);public void NextHint()=>Advance();}
class IDCard{public GameObject[] fakeID;public bool actualIDCard;public void Run()=>CheckIfFakeID();\n'''+ '\n'.join(lines)+'\n}'
    r=tmp_path/'r';r.mkdir();(r/'Program.cs').write_text(prog,encoding='utf8');print(run_case(tmp_path,r))
