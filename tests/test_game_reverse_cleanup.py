import pytest
from iced_x86 import Register as R

from dotnet_case import run_case
from il2cpp import Lifter,Decompiler
from il2cpp.emitter import Emitter
from il2cpp.indexed_class import indexed_class_sites
from il2cpp.closed_class_read import _class_entry
from test_game_shift_shared_flags import shift_runtime

pytestmark=pytest.mark.game


def test_reverse_cleanup_reads_live_list_and_decrements(shift_runtime,tmp_path):
    meta,il=shift_runtime;md=meta.methods[23808];td=meta.typedefs[md.declaring];lines=[]
    Emitter(il,str(tmp_path/'out')).emit_method(md,td,lines,'    ')
    # The final removal independently uses its own closed List<GameObject>
    # specialization in R8. Sharing the indexer receiver's type is not proof.
    d=Decompiler(Lifter(il));seq,_=d._decode(md);k=next(k for k,i in enumerate(seq) if i.ip==0x18052a8c8)
    slot,index,call=seq[k-2:k+1];assert slot.op0_register==R.R8 and slot.ip_rel_memory_address==0x183c8db58 and index.op0_register==R.EDX and index.op1_register==R.EBX
    u=il.decode_slot(slot.ip_rel_memory_address);mi,ci,gi=il.method_specs[u['idx']];remove=meta.methods[mi]
    assert u['kind']==6 and _class_entry(il,u['idx'])==call.near_branch_target==0x180e12840 and remove.name=='RemoveAt' and gi==-1
    fi=next(fi for fi in meta.type_fields(td) if meta.fields[fi].name=='onScreenParticles')
    assert il._closed_type_key(il.types[meta.fields[fi].type])==(0x15,(0x12,remove.declaring,0),tuple(il._closed_type_key(t) for t in il._method_spec_type_args(ci)),0)
    src='''using System;using System.Collections.Generic;using System.Linq;using UnityEngine;
foreach(string mode in new[]{"empty","singleton","all","replace", "null list","count fault","get fault","compare fault","second fault","destroy fault","remove fault","list cleared"}){
 var c=new Case();var log=new List<string>();var boom=new ApplicationException();void At(string s,string fail){log.Add(s);if(mode==fail)throw boom;}
 var A=new GameObject("A");var B=new GameObject("B");var X=new GameObject("X");var Y=new GameObject("Y");var Z=new GameObject("Z");
 var a=new List_1<GameObject>("a",mode=="empty"?new GameObject[0]:mode=="singleton"?new[]{A}:mode=="all"?new[]{A,null,new GameObject("gone"),B}:new[]{A,B});
 var b=new List_1<GameObject>("b",new[]{X,Y,Z});var last=new List_1<GameObject>("c",new[]{X,Y,Z});c.onScreenParticles=mode=="null list"?null:a;
 int gets=0;List_1<GameObject>.Op=(n,k,i)=>At(n+k+(k=="count"?"":i.ToString()),k switch{"count"=>"count fault","get"=>++gets==1?"get fault":"second fault",_=>"remove fault"});
 UnityEngine.Object.Neq=(o,n)=>{if(n is not null)throw new Exception("not null comparison");At("test:"+(o?.Id??"null"),"compare fault");if(mode=="replace"&&ReferenceEquals(o,B))c.onScreenParticles=b;return o is not null&&o.Id!="gone";};
 UnityEngine.Object.Drop=o=>{At("destroy:"+o.Id,"destroy fault");if(mode=="replace"&&ReferenceEquals(o,Y))c.onScreenParticles=last;if(mode=="list cleared")c.onScreenParticles=null;};
 Exception fault=null;try{c.Run();}catch(Exception e){fault=e;}
 var initial=new[]{"acount","aget1","test:B","aget1","destroy:B","aremove1"};string[] expected=mode switch{
 "empty"=>new[]{"acount"},"singleton"=>new[]{"acount","aget0","test:A","aget0","destroy:A","aremove0"},
 "all"=>new[]{"acount","aget3","test:B","aget3","destroy:B","aremove3","aget2","test:gone","aremove2","aget1","test:null","aremove1","aget0","test:A","aget0","destroy:A","aremove0"},
 "replace"=>new[]{"acount","aget1","test:B","bget1","destroy:Y","cremove1","cget0","test:X","cget0","destroy:X","cremove0"},
 "null list"=>new string[0],_=>initial.Take(mode switch{"count fault"=>1,"get fault"=>2,"compare fault"=>3,"second fault"=>4,"remove fault"=>6,_=>5}).ToArray()};
 if(!expected.SequenceEqual(log)||(mode.EndsWith(" fault")?!ReferenceEquals(fault,boom):mode is "null list" or "list cleared"?fault is not NullReferenceException:fault!=null))throw new Exception(mode+": "+string.Join(',',log),fault);
 if(mode=="replace"&&(!a.Items.SequenceEqual(new[]{A,B})||!b.Items.SequenceEqual(new[]{X,Y,Z})||!last.Items.SequenceEqual(new[]{Z})))throw new Exception("wrong surviving list");
 if(mode is "all" or "empty" or "singleton"&&a.Items.Count!=0)throw new Exception("leftover entries");}
Console.WriteLine("reverse cleanup: live index, conditional second lookup, independent removal receiver, unity-null and faults passed");
namespace System.Collections.Generic{public class List_1<T>{public readonly List<T> Items;readonly string name;public static Action<string,string,int> Op;public List_1(string n,T[] xs){name=n;Items=new List<T>(xs);}public int Count{get{Op(name,"count",0);return Items.Count;}}public T this[int i]{get{Op(name,"get",i);return Items[i];}}public void RemoveAt(int i){Op(name,"remove",i);Items.RemoveAt(i);}public static bool operator ==(List_1<T> a,List_1<T> b)=>throw new Exception("native pointer test became equality");public static bool operator !=(List_1<T> a,List_1<T> b)=>throw new Exception();public override bool Equals(object b)=>ReferenceEquals(this,b);public override int GetHashCode()=>base.GetHashCode();}}
namespace UnityEngine{public class Object{public string Id;public static Func<Object,Object,bool> Neq;public static Action<Object> Drop;public static bool operator !=(Object o,Object n)=>Neq(o,n);public static bool operator ==(Object o,Object n)=>!Neq(o,n);public override bool Equals(object o)=>ReferenceEquals(this,o);public override int GetHashCode()=>base.GetHashCode();public static void Destroy(Object o)=>Drop(o);}public class GameObject:Object{public GameObject(string n){Id=n;}}}
class Case{public List_1<GameObject> onScreenParticles;public void Run()=>destroyParticles();\n'''+ '\n'.join(lines)+'\n}'
    runner=tmp_path/'runner';runner.mkdir();(runner/'Program.cs').write_text(src,encoding='utf8');print(run_case(tmp_path,runner).strip())


@pytest.mark.parametrize('change',['wrong slot','wrong field','target conflict','wrong count'])
def test_index_result_needs_own_receiver_and_closed_entry(shift_runtime,monkeypatch,change):
    meta,il=shift_runtime;d=Decompiler(Lifter(il));m=meta.methods[23808];d.lift_method(m,meta.typedefs[m.declaring]);bs=d.L._blocks
    check=lambda:indexed_class_sites(d.L,m,bs,());ip=0x18052a849;count=0x18052a822;assert ip in check() and count in check()
    if change=='target conflict':
        mi=il.method_specs[170528][0];monkeypatch.setitem(il._awaiter_spec_indices[mi],170528,-1)
    else:
        at={'wrong slot':0x18052a840,'wrong field':0x18052a830,'wrong count':count}[change]
        b,j=next((b,j) for b in bs for j,i in enumerate(b.insns) if i.ip==at);i=b.insns[j].copy()
        if change=='wrong slot':i.op0_register=R.R9
        else:i.memory_displacement+=4
        monkeypatch.setattr(b,'insns',b.insns[:j]+[i]+b.insns[j+1:])
    assert (count if change=='wrong count' else ip) not in check()
