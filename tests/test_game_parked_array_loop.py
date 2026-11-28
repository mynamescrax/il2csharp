import pytest
from dotnet_case import run_case
from il2cpp.emitter import Emitter
from test_game_shift_shared_flags import shift_runtime

pytestmark=pytest.mark.game


def test_inventory_jam_uses_the_old_array_and_live_later_elements(shift_runtime,tmp_path):
    meta,il=shift_runtime;m=meta.methods[25630];out=[];Emitter(il,str(tmp_path/'out')).emit_method(m,meta.typedefs[m.declaring],out,'    ')
    cs='''using System;using System.Linq;using System.Collections.Generic;using UnityEngine;
foreach(string mode in new[]{"null array","empty","first","replace","null second","second"}){
 var c=new InventoryManager();var a=new GameObject();var b=new GameObject();var next=new GameObject();var old=new[]{a,b};var trace=new List<string>();var err=new ApplicationException();
 c.gunVines=mode=="null array"?null:mode=="empty"?Array.Empty<GameObject>():old;void Step(string x,bool on){if(!on||!c.gunJammed)throw new Exception("bad state");trace.Add(x);if(mode==x)throw err;}
 a.Set=on=>{Step("first",on);c.gunVines=Array.Empty<GameObject>();old[1]=mode=="null second"?null:next;};b.Set=_=>throw new Exception("preloaded later element");next.Set=v=>Step("second",v);
 Exception ex=null;try{c.GunJam();}catch(Exception e){ex=e;}int n=mode switch{"null array" or "empty"=>0,"first" or "null second"=>1,_=>2};
 if(!c.gunJammed||!trace.SequenceEqual(new[]{"first","second"}.Take(n))||(mode.StartsWith("null")?ex is not NullReferenceException:mode is "first" or "second"?!ReferenceEquals(ex,err):ex!=null))throw new Exception(mode+":"+string.Join(',',trace),ex);
}
Console.WriteLine("whole jam callback: committed flag, original array, live later element, early and late faults");
namespace UnityEngine{public class GameObject{public Action<bool> Set;public void SetActive(bool on)=>Set(on);}}class InventoryManager{public bool gunJammed;public GameObject[] gunVines;\n'''+ '\n'.join(out)+'\n}'
    p=tmp_path/'r';p.mkdir();(p/'Program.cs').write_text(cs,encoding='utf8');print(run_case(tmp_path,p))


@pytest.mark.parametrize('bad',['other array','wrong stride','wrong header','wrong latch','other field width'])
def test_parked_array_traversal_requires_its_own_source_and_checks(shift_runtime,monkeypatch,bad):
    from il2cpp import Lifter,Decompiler
    from il2cpp.parked_array_loop import parked_arrays
    from iced_x86 import Register as R
    meta,il=shift_runtime;m=meta.methods[25630];td=meta.typedefs[m.declaring];d=Decompiler(Lifter(il));d.lift_method(m,td);bs=d.L._blocks;scan=lambda:parked_arrays(d.L,m,td,bs,());assert set(scan())=={0x18070f21a}
    p={'other array':0x18070f23e,'wrong stride':0x18070f23e,'wrong header':0x18070f236,'wrong latch':0x18070f256,'other field width':0x18070f223}[bad]
    b,j=next((b,j) for b in bs for j,i in enumerate(b.insns) if i.ip==p);i=b.insns[j].copy()
    if bad=='other array':i.memory_base=R.RSI
    elif bad=='wrong stride':i.memory_index_scale=4
    elif bad=='wrong latch':i.near_branch64=0x18070f236
    else:i.memory_displacement+=2
    monkeypatch.setattr(b,'insns',b.insns[:j]+[i]+b.insns[j+1:]);assert not scan()
