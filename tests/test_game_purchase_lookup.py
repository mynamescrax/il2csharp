"""Compile the whole purchase-node Spawned override, including the list tail."""
import pytest

from dotnet_case import run_case
from il2cpp import Decompiler,Lifter
from test_game_shift_shared_flags import body,shift_runtime

pytestmark=pytest.mark.game


def test_purchase_spawn_resolves_animator_once_after_base(body,tmp_path):
    method=body('PurchaseNode','Spawned',0x180595e80)
    assert method.startswith('base.Spawned() /* shared implementation */;')
    assert method.count('GetComponentInParent<UnityEngine.Animator>')==1 and 'sub_' not in method
    runner=tmp_path/'runner'; runner.mkdir()
    (runner/'Program.cs').write_text('''using System;
using System.Collections.Generic;
using System.Linq;
using UnityEngine;
foreach(string mode in new[]{"add","present","null","destroyed","base throws","lookup throws","comparison throws"}){
    var trace=new List<string>();var found=new Animator(19);var other=new Animator(-2);var replacement=new PurchaseManager();
    var original=new PurchaseManager();original.existingNodes.Add(other);replacement.existingNodes.Add(other);
    var active=original;PurchaseManager.Read=()=>{trace.Add("manager");return active;};
    var p=new PurchaseNode();p.OnBase=()=>{trace.Add("base");if(mode=="base throws")throw new ApplicationException();};
    p.Lookup=t=>{trace.Add("lookup");if(t!=typeof(Animator))throw new Exception("wrong closed type");
        if(mode=="lookup throws")throw new ApplicationException();found.Destroyed=mode=="destroyed";return mode=="null"?null:found;};
    other.Compare=o=>{trace.Add("contains");if(!ReferenceEquals(o,found))throw new Exception("lost lookup result");
        active=replacement;if(mode=="comparison throws")throw new ApplicationException();return mode=="present";};
    bool threw=false;try{((Behaviour)p).Spawned();}catch(ApplicationException){threw=true;}
    var expected=mode switch {"base throws"=>"base", "lookup throws" or "destroyed" or "null"=>"base;lookup",
        "add"=>"base;lookup;manager;contains;manager", _=>"base;lookup;manager;contains"};
    if(threw!=mode.EndsWith("throws") || string.Join(";",trace)!=expected || original.existingNodes.Count!=1 ||
       replacement.existingNodes.Count!=(mode=="add"?2:1) || mode=="add"&&!ReferenceEquals(replacement.existingNodes[1],found))throw new Exception(mode);
    Console.WriteLine(mode+": "+expected);
}
class PurchaseManager {public List<Animator> existingNodes=new(1);public static Func<PurchaseManager> Read;public static PurchaseManager Instance=>Read();}
class Behaviour:Component {public Action OnBase; public virtual void Spawned()=>OnBase();}
class PurchaseNode:Behaviour { public override void Spawned(){\n'''+method+'''\n}}
namespace UnityEngine {
    class Object {public bool Destroyed;static bool Absent(Object x)=>x is null || x.Destroyed;
        public static bool operator ==(Object a,Object b)=>Absent(a)?Absent(b):ReferenceEquals(a,b);
        public static bool operator !=(Object a,Object b)=>!(a==b); public override bool Equals(object o)=>ReferenceEquals(this,o); public override int GetHashCode()=>base.GetHashCode();}
    class Component:Object {public Func<Type,Component> Lookup; public T GetComponentInParent<T>() where T:Component =>(T)Lookup(typeof(T));}
    class Animator:Component {readonly int id;public Func<object,bool> Compare;public Animator(int id)=>this.id=id;
        public override bool Equals(object o)=>Compare!=null?Compare(o):ReferenceEquals(this,o);public override int GetHashCode()=>id; }
}''',encoding='utf-8')
    print(run_case(tmp_path,runner).strip())


@pytest.mark.parametrize('change',['incoming RAX','incoming XMM0','different Add write barrier','other MethodRef'])
def test_purchase_lookup_declines_inexact_proofs(shift_runtime,monkeypatch,change):
    meta,il=shift_runtime; d=Decompiler(Lifter(il));md=meta.methods[26973]; td=meta.typedefs[md.declaring]
    if change=='other MethodRef':
        old=il.decode_slot; other=old(0x183c70200)
        monkeypatch.setattr(il,'decode_slot',lambda p:other if p==0x183c02db8 else old(p))
    else:
        read=il.bin.read
        def changed(p,n):
            data=read(p,n)
            if p==0x180b5d000 and n==173:
                if change=='incoming RAX':return b'\x48\x89\x44\x24\x08'+data[5:]
                if change=='incoming XMM0':return b'\xf2\x0f\x11\x04\x24'+data[5:]
            if change=='different Add write barrier' and p==0x180002410 and n==97:
                # Same instructions and local branches, different external JMP.
                assert data[80]==0xe9
                return data[:81]+bytes([data[81]^8])+data[82:]
            return data
        monkeypatch.setattr(il.bin,'read',changed)
    text='\n'.join(d.lift_method(md,td))
    if change=='different Add write barrier':
        assert 'base.Spawned()' in text and 'sub_180002410(' in text
    else:
        assert 'base.Spawned()' not in text and 'sub_180507120/*shared body,' in text
