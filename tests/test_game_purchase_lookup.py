"""Compile the purchase-node lifecycle callbacks, including the list operations."""
import pytest

from dotnet_case import run_case
from il2cpp import Decompiler,Lifter
from test_game_shift_shared_flags import body,shift_runtime

pytestmark=pytest.mark.game


def test_purchase_callbacks_resolve_animator_once_after_base(body,tmp_path):
    method=body('PurchaseNode','Spawned',0x180595e80)
    despawn=body('PurchaseNode','Despawned',0x180594fc0)
    assert method.startswith('base.Spawned() /* shared implementation */;')
    assert method.count('GetComponentInParent<UnityEngine.Animator>')==1 and 'sub_' not in method
    assert despawn.startswith('base.Despawned(runner, hasState) /* shared implementation */;')
    assert despawn.count('GetComponentInParent<UnityEngine.Animator>')==1 and 'sub_' not in despawn
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
foreach(bool flag in new[]{false,true}) foreach(bool withRunner in new[]{false,true}) foreach(string mode in new[]{"remove","missing","null","destroyed","base throws","lookup throws","comparison throws"}) {
    var trace=new List<string>(); var node=new PurchaseNode(); var runner=withRunner?new NetworkRunner():null;
    var found=new Animator(7);var original=new PurchaseManager();var selected=new PurchaseManager();
    var probe=new Animator(3);original.existingNodes.Add(found);selected.existingNodes.Add(probe);selected.existingNodes.Add(found);
    if(mode=="missing")selected.existingNodes.RemoveAt(1);
    PurchaseManager active=original;PurchaseManager.Read=()=>{trace.Add("manager");return active;};
    node.OnDespawn=(r,s)=>{trace.Add("base");if(!ReferenceEquals(r,runner) || s!=flag)throw new Exception("changed call arguments");
        if(mode=="base throws")throw new ApplicationException();active=selected;};
    node.Lookup=t=>{trace.Add("lookup");if(t!=typeof(Animator))throw new Exception("lookup type");
        if(mode=="lookup throws")throw new ApplicationException();found.Destroyed=mode=="destroyed";return mode=="null"?null:found;};
    probe.Compare=o=>{trace.Add("remove");if(!ReferenceEquals(found,o))throw new Exception("wrong item");
        if(mode=="comparison throws")throw new ApplicationException();return false;};
    bool threw=false;try{((Behaviour)node).Despawned(runner,flag);}catch(ApplicationException){threw=true;}
    var expected=mode switch {"base throws"=>"base", "lookup throws" or "destroyed" or "null"=>"base;lookup", _=>"base;lookup;manager;remove"};
    if(string.Join(";",trace)!=expected || threw!=mode.EndsWith("throws") || selected.existingNodes.Count!=(mode=="remove"||mode=="missing"?1:2) ||
       !ReferenceEquals(selected.existingNodes[0],probe) || !ReferenceEquals(original.existingNodes.Single(),found))throw new Exception(mode);
    if(mode=="remove")Console.WriteLine($"Despawned(runner={(withRunner?"same":"null")}, hasState={flag}): {expected}");
}
class PurchaseManager {public List<Animator> existingNodes=new(1);public static Func<PurchaseManager> Read;public static PurchaseManager Instance=>Read();}
class NetworkRunner { }
class Behaviour:Component {public Action OnBase;public Action<NetworkRunner,bool> OnDespawn; public virtual void Spawned()=>OnBase();
    public virtual void Despawned(NetworkRunner runner,bool hasState)=>OnDespawn(runner,hasState);}
class PurchaseNode:Behaviour { public override void Spawned(){\n'''+method+'\n}\npublic override void Despawned(NetworkRunner runner,bool hasState){\n'+despawn+'''\n}}
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


@pytest.mark.parametrize('defect',['different slot','observable callee','return read'])
def test_purchase_despawn_declines_other_base_effects(shift_runtime,monkeypatch,defect):
    from il2cpp import shared_action
    meta,il=shift_runtime; md=meta.methods[26974];d=Decompiler(Lifter(il));td=meta.typedefs[md.declaring]
    if defect=='different slot':
        monkeypatch.setattr(md,'slot',25)
    elif defect=='observable callee':
        read=il.bin.read
        monkeypatch.setattr(il.bin,'read',lambda p,n:b'\x89\x01\xc3' if (p,n)==(0x180507120,3) else read(p,n))
    else:
        old=shared_action._unused_return
        monkeypatch.setattr(shared_action,'_unused_return',lambda lift,after:False if after==0x18059501f else old(lift,after))
    method='\n'.join(d.lift_method(md,td))
    assert 'base.Despawned(' not in method and 'sub_180507120/*shared body,' in method
