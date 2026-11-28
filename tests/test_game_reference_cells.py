import pytest
from dotnet_case import run_case
from il2cpp.emitter import Emitter
from test_game_shift_shared_flags import shift_runtime

pytestmark=pytest.mark.game


def test_cleanability_writes_and_reloads_live_byref_outputs(shift_runtime,tmp_path):
    meta,il=shift_runtime;m=meta.methods[25687];out=[];Emitter(il,str(tmp_path/'out')).emit_method(m,meta.typedefs[m.declaring],out,'    ')
    prog='''using System;using System.Collections.Generic;using System.Linq;using UnityEngine;
foreach(string mode in new[]{"no collider","first","truth","spill wins","mop wins","both missing","second","check spill","check mop","replace refs"}){
 var slots=new Slots();var initialS=slots.S=new Spill();var initialM=slots.M=new Moppable();var s=new Spill();var m=new Moppable();var replacementS=new Spill();var replacementM=new Moppable();var c=new Collider();var trace=new List<string>();var fault=new ApplicationException();void Step(string tag){trace.Add(tag);if(tag==mode)throw fault;}
 c.Search=t=>{if(t==typeof(Spill)){Step("first");return s;}if(t!=typeof(Moppable)||!ReferenceEquals(slots.S,mode=="replace refs"?replacementS:s)||!ReferenceEquals(slots.M,initialM))throw new Exception("second lookup inputs");Step("second");return mode=="both missing"?null:m;};
 UnityEngine.Object.Live=o=>{if(!ReferenceEquals(o,s)||!ReferenceEquals(slots.S,s)||!ReferenceEquals(slots.M,initialM))throw new Exception("truth used pre-store reference");Step("truth");if(mode=="replace refs")slots.S=replacementS;return mode=="spill wins";};
 UnityEngine.Object.Neq=(o,z)=>{if(z is not null)throw new Exception();if(o is Spill){if(!ReferenceEquals(o,slots.S)||!ReferenceEquals(slots.M,mode is "spill wins" or "both missing"?null:m))throw new Exception("stale spill/output");Step("check spill");if(mode=="replace refs")slots.M=replacementM;return mode=="spill wins";}
 if(!ReferenceEquals(o,slots.M)||mode=="replace refs"&&!ReferenceEquals(o,replacementM))throw new Exception("stale mop");Step("check mop");return o is not null;};
 bool got=false;Exception ex=null;try{got=InventoryManager.Run(mode=="no collider"?null:c,ref slots.S,ref slots.M);}catch(Exception e){ex=e;}
 var steps=new List<string>{"first","truth"};if(mode!="spill wins")steps.Add("second");steps.Add("check spill");if(mode!="spill wins")steps.Add("check mop");int cut=steps.IndexOf(mode);int n=mode=="no collider"?0:cut<0?steps.Count:cut+1;
 if(!trace.SequenceEqual(steps.Take(n))||(mode=="no collider"?ex is not NullReferenceException:cut>=0?!ReferenceEquals(ex,fault):ex!=null)||ex==null&&got!=(mode!="both missing")||
   !ReferenceEquals(slots.S,mode is "no collider" or "first"?initialS:mode=="replace refs"?replacementS:s)||!ReferenceEquals(slots.M,mode is "no collider" or "first" or "truth" or "second"?initialM:mode=="replace refs"?replacementM:mode is "spill wins" or "both missing"?null:m))throw new Exception(mode+":"+string.Join(',',trace),ex);
}
Console.WriteLine("complete spill lookup helper: caller-owned ref outputs, actual closed lookups, mutations, partial writes and fault timing");
namespace UnityEngine{public class Object{public static Func<Object,bool> Live;public static Func<Object,Object,bool> Neq;public static implicit operator bool(Object o)=>Live(o);public static bool operator !=(Object a,Object b)=>Neq(a,b);public static bool operator ==(Object a,Object b)=>!Neq(a,b);public override bool Equals(object o)=>ReferenceEquals(o,this);public override int GetHashCode()=>base.GetHashCode();}
public class Component:Object{public Func<Type,Component> Search;public T GetComponentInParent<T>() where T:Component=>(T)Search(typeof(T));}public class Collider:Component{}}
class Spill:Component{}class Moppable:Component{}class Slots{public Spill S;public Moppable M;}class InventoryManager{public static bool Run(Collider c,ref Spill s,ref Moppable m)=>TryGetCleanable(c,ref s,ref m);\n'''+ '\n'.join(out)+'\n}'
    p=tmp_path/'r';p.mkdir();(p/'Program.cs').write_text(prog,encoding='utf8');print(run_case(tmp_path,p))


@pytest.mark.parametrize('change',['none','partial load','neighbor slot','pointer publication','forward to lookup','read before first store'])
def test_ref_slot_is_a_bounded_pointee_not_a_managed_object(shift_runtime,monkeypatch,change):
    from il2cpp import Decompiler,Lifter
    from il2cpp.reference_cells import ref_loads
    from iced_x86 import Decoder,Register as R
    meta,il=shift_runtime;m=meta.methods[25687];td=meta.typedefs[m.declaring];d=Decompiler(Lifter(il));d.lift_method(m,td);bs=d.L._blocks
    find=lambda:ref_loads(d.L,m,td,bs,());before=find();assert {0x18071a55e,0x18071a5aa,0x18071a5e5}==set(before)
    if change=='none':return
    ip={'partial load':0x18071a55e,'neighbor slot':0x18071a55e,'pointer publication':0x18071a54c,'forward to lookup':0x18071a53c,'read before first store':0x18071a54c}[change]
    b,j=next((b,j) for b in bs for j,i in enumerate(b.insns) if i.ip==ip);i=b.insns[j].copy()
    if change=='partial load':i=Decoder(64,bytes.fromhex('408b2e'),ip=ip).decode()
    elif change=='neighbor slot':i.memory_displacement=8
    elif change=='pointer publication':i.op1_register=R.RSI
    elif change=='forward to lookup':i.op1_register=R.RSI
    else:i=Decoder(64,bytes.fromhex('488b06'),ip=ip).decode()
    assert i.len==b.insns[j].len;monkeypatch.setattr(b,'insns',b.insns[:j]+[i]+b.insns[j+1:]);assert 0x18071a55e not in find()
