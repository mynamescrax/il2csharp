import pytest
from dotnet_case import run_case
from il2cpp.emitter import Emitter
from test_game_shift_shared_flags import shift_runtime

pytestmark=pytest.mark.game


def test_tutorial_searches_schedule_on_hit_and_finish_on_exhaustion(shift_runtime,tmp_path):
    meta,il=shift_runtime;em=Emitter(il,str(tmp_path/'out'));out=[]
    for mi in (28331,28332):
        m=meta.methods[mi];em.emit_method(m,meta.typedefs[m.declaring],out,'    ')
    s='''using System;using System.Collections.Generic;using System.Linq;using UnityEngine;using UnityEngine.UI;using UnityEngine.Events;
foreach(bool limbs in new[]{false,true})foreach(var mode in new[]{"hit","invoke","empty","miss","dead truth","winner getter","null array","null truthy","null target","write","blood","eq0","shelf","eq1","limbs","eq2","reject0","reject1","reject2","objective","disable","show","hide"}){
 var t=new TutorialManager();var log=new List<string>();var err=new ApplicationException();void Step(string a){log.Add(a);if(mode==a)throw err;}
 var dead=new GameObject();var inactive=new GameObject();var winner=new GameObject();var poison=new GameObject();var arr=new[]{dead,inactive,winner,poison};var checks=new[]{"dead truth","inactive truth","inactive getter","winner truth","winner getter","invoke"};var end=new[]{"write","blood","eq0","shelf","eq1","limbs","eq2","objective","disable","show","hide"};
 bool empty=mode!="hit" && mode!="invoke" && mode!="winner getter" && mode!="dead truth" && mode!="miss";var use=mode=="null array"?null:mode=="null truthy"?new GameObject[]{null}:empty?Array.Empty<GameObject>():mode=="miss"?new[]{dead,inactive}:arr;
 if(limbs)t.limbs=use;else t.blood=use;
 UnityEngine.Object.Truth=o=>{if(o is null){Step("accepted null");return true;}if(ReferenceEquals(o,dead)){Step("dead truth");return false;}if(ReferenceEquals(o,inactive)){Step("inactive truth");return true;}if(!ReferenceEquals(o,winner))throw new Exception("touched poison");Step("winner truth");arr[2]=poison;t.limbs=t.blood=null;return true;};
 inactive.Read=()=>{Step("inactive getter");return false;};winner.Read=()=>{Step("winner getter");return true;};t.Schedule=(name,v)=>{if(v!=1f||name!=(limbs?"CheckForLimbsDone":"CheckForBloodDone"))throw new Exception("bad timer");Step("invoke");};
 var initial=t.checkboxSprite=new Sprite();var b=t.finishedBlood=new Image();var l=t.finishedLimbs=new Image();var shelf=t.finishedShelf=new Image();if(mode=="null target"){if(limbs)t.finishedLimbs=null;else t.finishedBlood=null;}
 Action<Sprite> set=x=>{if(!ReferenceEquals(x,initial))throw new Exception();Step("write");t.checkboxSprite=new Sprite();};b.Put=l.Put=set;int eq=0;Sprite expected=null;void Read(string n){Step(n);expected=t.checkboxSprite;}
 b.Fetch=()=>{Read("blood");return expected;};shelf.Fetch=()=>{Read("shelf");return expected;};l.Fetch=()=>{Read("limbs");return expected;};UnityEngine.Object.Equal=(x,y)=>{if(!ReferenceEquals(x,expected)||!ReferenceEquals(y,expected))throw new Exception("old checkbox");var j=eq++;Step("eq"+j);t.checkboxSprite=new Sprite();return mode!="reject"+j;};
 t.Start=()=>{Step("objective");t.disableShelfOutline=new UnityEvent{Go=()=>{Step("disable");t.instructions=new GameObject{Active=x=>{if(!x)throw new Exception();Step("show");t.tutorialObjCanvasHolder=new GameObject{Active=y=>{if(y)throw new Exception();Step("hide");}};}};}};};
 Exception ex=null;try{t.Run(limbs);}catch(Exception e){ex=e;}IEnumerable<string> want=mode switch{"null array" or "null target"=>Array.Empty<string>(),"null truthy"=>new[]{"accepted null"},"dead truth"=>checks.Take(1),"winner getter"=>checks.Take(5),"hit" or "invoke"=>checks,"miss"=>checks.Take(3).Concat(end),_=>end.Take(mode.StartsWith("reject")?2+2*(mode[^1]-'0')+1:Array.IndexOf(end,mode)<0?end.Length:Array.IndexOf(end,mode)+1)};
 bool shouldThrow=mode.StartsWith("null")||Array.IndexOf(end,mode)>=0||mode is "invoke" or "dead truth" or "winner getter";
 if(!log.SequenceEqual(want)||(mode.StartsWith("null")?ex is not NullReferenceException:shouldThrow?!ReferenceEquals(ex,err):ex!=null))throw new Exception($"{limbs}/{mode}: {string.Join(',',log)}",ex);
}
Console.WriteLine("two complete tutorial searches: hit and exhaustion are disjoint, checked element is retained, completion callbacks and fault cutoffs");
namespace UnityEngine{public class Object{public static Func<Object,bool> Truth;public static Func<Object,Object,bool> Equal;public static implicit operator bool(Object o)=>Truth(o);public static bool operator ==(Object x,Object y)=>Equal(x,y);public static bool operator !=(Object x,Object y)=>!Equal(x,y);public override bool Equals(object o)=>ReferenceEquals(this,o);public override int GetHashCode()=>base.GetHashCode();}public class Sprite:Object{}public class GameObject:Object{public Func<bool> Read;public bool activeInHierarchy=>Read();public Action<bool> Active;public void SetActive(bool x)=>Active(x);}}
namespace UnityEngine.Events{public class UnityEvent{public Action Go;public void Invoke()=>Go();}}namespace UnityEngine.UI{public class Image{public Func<Sprite> Fetch;public Action<Sprite> Put;public Sprite sprite{get=>Fetch();set=>Put(value);}}}
class TutorialManager{public GameObject[] blood,limbs;public Sprite checkboxSprite;public Image finishedLimbs,finishedBlood,finishedShelf;public Action<string,float> Schedule;public void Invoke(string n,float v)=>Schedule(n,v);public Action Start;public void StartObjective()=>Start();public UnityEvent disableShelfOutline;public GameObject instructions,tutorialObjCanvasHolder;public void Run(bool b){if(b)CheckForLimbsDone();else CheckForBloodDone();}\n'''+ '\n'.join(out)+'\n}'
    p=tmp_path/'r';p.mkdir();(p/'Program.cs').write_text(s,encoding='utf8');print(run_case(tmp_path,p))


@pytest.mark.parametrize('change',['extra completion parent','alternate exit','observable cleanup','success predecessor','other field access'])
def test_completion_only_owns_private_paths_to_plain_return(shift_runtime,monkeypatch,change):
    from il2cpp import Decompiler,Lifter
    from il2cpp.dec import search_completion
    from il2cpp.guarded_ref_alias import compared_fields
    from iced_x86 import Register as R
    meta,il=shift_runtime;m=meta.methods[28331];td=meta.typedefs[m.declaring];d=Decompiler(Lifter(il));old=search_completion.terminal_hit;calls=[]
    def check(dec,bs,hdr,match,hit,miss,body,stop):
        r=old(dec,bs,hdr,match,hit,miss,body,stop);assert r
        end=bs[r[-1]].succs[0]
        if change=='other field access':
            scan=lambda:compared_fields(dec.L,m,td,bs,());ip=0x180612c2e;assert ip in scan()
            b,j=next((b,j) for b in bs for j,i in enumerate(b.insns) if i.ip==ip);i=b.insns[j].copy();i.memory_base=R.RCX
            with monkeypatch.context() as mp:
                mp.setattr(b,'insns',b.insns[:j]+[i]+b.insns[j+1:]);assert ip not in scan()
        else:
            with monkeypatch.context() as mp:
                if change=='extra completion parent':mp.setattr(bs[miss],'preds',bs[miss].preds+[hit])
                elif change=='alternate exit':mp.setattr(bs[miss],'term',('ret',));mp.setattr(bs[miss],'succs',[])
                elif change=='observable cleanup':mp.setattr(bs[end],'stmts',['Observe();'])
                else:mp.setattr(bs[hit],'preds',bs[hit].preds+[hdr])
                assert old(dec,bs,hdr,match,hit,miss,body,stop) is None
        calls.append(True);return r
    monkeypatch.setattr(search_completion,'terminal_hit',check);d.lift_method(m,td);assert calls
