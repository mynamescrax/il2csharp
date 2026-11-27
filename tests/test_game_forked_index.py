import re
import pytest
from iced_x86 import Register as R
from dotnet_case import run_case
from il2cpp import Decompiler,Lifter
from il2cpp.emitter import Emitter
from il2cpp.forked_index import forked_indices
from test_game_shift_shared_flags import shift_runtime

pytestmark=pytest.mark.game


def test_showcase_and_change_effect_use_one_index_result_per_arm(shift_runtime,tmp_path):
    meta,il=shift_runtime;em=Emitter(il,str(tmp_path/'out'));md=meta.methods[28695];lines=[];em.emit_method(md,meta.typedefs[md.declaring],lines,'    ')
    d=Decompiler(Lifter(il));other=meta.methods[28573];s=d.lift_method(other,meta.typedefs[other.declaring]);prefix=next(x for x in s if ' = this.FX;' in x);n=next(j for j,x in enumerate(s) if '.FindIndex(' in x)
    predicate=re.search(r'\.FindIndex\((\w+)\)',s[n])[1];stage=prefix+'\n'+'\n'.join(s[n:]);assert stage.count('.FindIndex(')==1
    src='''using System;using System.Collections.Generic;using System.Linq;using UnityEngine;
foreach(bool search in new[]{true,false})foreach(var mode in new[]{"advance","wrap","null list","index fault","search fault","count fault","off fault","on fault","post fault","mutate","overflow","null reload"}){
 if(search&&mode is "post fault" or "overflow"||!search&&mode=="search fault")continue;
 var c=new Case();var fx=new FXCase();int old=mode=="wrap"?2:mode=="index fault"?-1:0;var a=new List_1<GameObject>();var b=new List_1<GameObject>();var z=new List_1<GameObject>();var off=new GameObject();var on=new GameObject();var trace=new List<string>();var err=new ApplicationException();
 void Step(string s){trace.Add(s);if(mode==s+" fault")throw err;}c.particles=mode=="null list"?null:b;fx.FX=mode=="null list"?null:a;c.currentlyActive=old;
 Predicate<GameObject> pred=x=>true;a.Find=p=>{if(!ReferenceEquals(p,pred))throw new Exception("wrong predicate");Step("search");fx.FX=b;return old;};
 b.Size=()=>{Step("count");if(mode=="mutate")c.currentlyActive=7;return 3;};b.At=i=>{if(i!=old)throw new Exception("stale or replayed index");Step("getOld");if(i<0)throw new ArgumentOutOfRangeException();return off;};
 int expected=mode=="wrap"?0:mode=="overflow"?int.MinValue:mode=="mutate"&&!search?5:old+1;off.Act=active=>{if(active)throw new Exception();Step("off");if(!search){c.particles=mode=="null reload"?null:z;c.currentlyActive=mode=="overflow"?int.MaxValue:mode=="mutate"?4:old;}else fx.FX=mode=="null reload"?null:z;};
 z.At=i=>{Step("getNew");if(i!=expected||!search&&c.currentlyActive!=expected)throw new Exception("wrong updated index");if(i<0)throw new ArgumentOutOfRangeException();return on;};on.Act=active=>{if(!active)throw new Exception();Step("on");};c.Post=()=>Step("post");Exception fault=null;try{if(search)fx.Select(pred);else c.ActivateNext();}catch(Exception e){fault=e;}
 var order=(search?new[]{"search","count","getOld","off","getNew","on"}:new[]{"count","getOld","off","getNew","on","post"});string last=mode switch{"search fault"=>"search","count fault"=>"count","index fault"=>"getOld","off fault" or "null reload"=>"off","on fault"=>"on","overflow"=>"getNew",_=>order.Last()};
 var want=mode=="null list"?Array.Empty<string>():order.Take(Array.IndexOf(order,last)+1);if(!trace.SequenceEqual(want)||(mode is "null list" or "null reload"?fault is not NullReferenceException:mode is "index fault" or "overflow"?fault is not ArgumentOutOfRangeException:mode.EndsWith(" fault")?!ReferenceEquals(fault,err):fault!=null))throw new Exception(search+"/"+mode+":"+string.Join(',',trace),fault);}
Console.WriteLine("whole ActivateNext and effect selection slice: both arms, one lookup, replacements, wrapping and faults passed");
namespace UnityEngine{public class GameObject{public Action<bool> Act;public void SetActive(bool b)=>Act(b);}}
namespace System.Collections.Generic{public class List_1<T>{public Func<Predicate<T>,int> Find;public Func<int,T> At;public Func<int> Size;public int FindIndex(Predicate<T> p)=>Find(p);public T this[int i]=>At(i);public int Count=>Size();}}
class Case{public List_1<GameObject> particles;public int currentlyActive;public Action Post;private void PostUpdateLogic()=>Post();\n'''+ '\n'.join(lines)+'\n}class FXCase{public List_1<GameObject> FX;public void Select(Predicate<GameObject> '+predicate+'){\n'+stage+'\n}}'
    runner=tmp_path/'runner';runner.mkdir();(runner/'Program.cs').write_text(src,encoding='utf8');print(run_case(tmp_path,runner).strip())


@pytest.mark.parametrize('change',['different arm target','wrong index field','wrong hidden slot','unregistered index producer'])
def test_forked_index_bindings_are_jointly_proven(shift_runtime,monkeypatch,change):
    meta,il=shift_runtime;j=28573 if change=='unregistered index producer' else 28695;m=meta.methods[j];d=Decompiler(Lifter(il));d.lift_method(m,meta.typedefs[m.declaring]);bs=d.L._blocks
    f=lambda:forked_indices(d.L,m,bs,(),{});p=f();assert len([a for a in p.values() if a[0]=='fork_index'])==2
    if change=='unregistered index producer':
        mi,_,_=il.method_specs[170518];monkeypatch.setitem(il._awaiter_spec_indices[mi],170518,-1)
    else:
        site={'different arm target':0x18062e61c,'wrong index field':0x18062e5ea,'wrong hidden slot':0x18062e5e3}[change];b,k=next((b,k) for b in bs for k,i in enumerate(b.insns) if i.ip==site);i=b.insns[k].copy()
        if change=='different arm target':i.near_branch64+=16
        elif change=='wrong index field':i.memory_displacement+=4
        else:i.op0_register=R.R9
        monkeypatch.setattr(b,'insns',b.insns[:k]+[i]+b.insns[k+1:])
    assert not f()
