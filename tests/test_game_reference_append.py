"""Exercise the complete shelf method on both native List.Add arms."""
import pytest
from iced_x86 import Register as R

from dotnet_case import run_case
from il2cpp import Decompiler,Lifter
from il2cpp.emitter import Emitter
from test_game_shift_shared_flags import shift_runtime

pytestmark=pytest.mark.game


def test_shelf_add_uses_old_index_and_reloaded_list(shift_runtime,tmp_path):
    meta,il=shift_runtime;m=meta.methods[27395];lines=[]
    Emitter(il,str(tmp_path/'out')).emit_method(m,meta.typedefs[m.declaring],lines,'    ')
    src='''using System;using System.Linq;using System.Collections.Generic;using UnityEngine;
foreach(int capacity in new[]{1,2})foreach(bool sort in new[]{false,true})foreach(var mode in new[]{"ok","null item","parent throws","create throws","no spawn","item throws","null list","sort throws"}){
 var c=new Shelf();var old=new List<Transform>();var list=new List<Transform>(capacity);var sentinel=new Transform();list.Add(sentinel);c.products=old;
 var prefab=c.productObj=new GameObject();var spawn=new GameObject();var item=new Transform();var par=new Transform();var log=new List<string>();var boom=new ApplicationException();
 void Step(string s){log.Add(s);if(mode==s+" throws")throw boom;}
 c.Parent=()=>{Step("parent");c.productObj=new GameObject();return par;};UnityEngine.Object.Make=(obj,parent)=>{Step("create");if(!ReferenceEquals(obj,prefab)||!ReferenceEquals(parent,par))throw new Exception("wrong Instantiate args");return mode=="no spawn"?null:spawn;};
 spawn.Get=()=>{Step("item");c.products=mode=="null list"?null:list;return mode=="null item"?null:item;};
 c.Sort=()=>{if(list.Count!=2||!ReferenceEquals(list[0],sentinel)||!ReferenceEquals(list[1],mode=="null item"?null:item))throw new Exception("sort before append");Step("sort");};
 var cursor=list.GetEnumerator();Exception fault=null;try{c.LocalAddItem(sort);}catch(Exception e){fault=e;}
 bool added=mode is "ok" or "null item" or "sort throws";var steps=new[]{"parent","create","item","sort"};int n=mode switch{"parent throws"=>1,"create throws" or "no spawn"=>2,_=>added&&sort?4:3};
 if(!log.SequenceEqual(steps.Take(n))||old.Count!=0||list.Count!=(added?2:1)||!ReferenceEquals(list[0],sentinel)||added&&(!ReferenceEquals(list[1],mode=="null item"?null:item)||(list.Capacity>capacity)!=(capacity==1))||
    (mode is "no spawn" or "null list"?fault is not NullReferenceException:mode.EndsWith(" throws")&&(mode!="sort throws"||sort)?!ReferenceEquals(fault,boom):fault!=null))throw new Exception(mode+":"+string.Join(',',log),fault);
 bool invalid=false;try{cursor.MoveNext();}catch(InvalidOperationException){invalid=true;}if(invalid!=added)throw new Exception("wrong mutation");}
Console.WriteLine("whole shelf append: spare capacity and resize, item/list order, conditional sort, identity and faults passed");
namespace UnityEngine{public class Object{public static Func<GameObject,Transform,GameObject> Make;public static T Instantiate<T>(T obj,Transform parent)where T:GameObject=>(T)Make(obj,parent);}public class GameObject:Object{public Func<Transform> Get;public Transform transform=>Get();}public class Transform:Object{}}
public class Shelf{public GameObject productObj;public List<Transform> products;public Func<Transform> Parent;public Transform transform=>Parent();public Action Sort;private void AutoSort()=>Sort();\n'''+ '\n'.join(lines)+'\n}'
    runner=tmp_path/'runner';runner.mkdir();(runner/'Program.cs').write_text(src,encoding='utf8');print(run_case(tmp_path,runner).strip())


@pytest.mark.parametrize('defect',['new index','wrong barrier value','wrong barrier target','wrong resize','wrong context','live edge','factory slot clobber','other continuation byte','side entrance'])
def test_reference_append_declines_inexact_diamond(shift_runtime,monkeypatch,defect):
    meta,il=shift_runtime;d=Decompiler(Lifter(il));m=meta.methods[27395];td=meta.typedefs[m.declaring]
    import il2cpp.reference_append as module
    orig=module.fold_reference_append;ran=[]
    def alter(dec,md,t,bs,pads):
        if defect=='live edge':
            dec.phi_copies[(10,11)]=['v97 = t1001;']
        elif defect in ('factory slot clobber','other continuation byte','side entrance'):
            if defect=='factory slot clobber':
                i=bs[4].insns[0].copy();i.op0_register=R.R9;bs[4].insns[0]=i
            elif defect=='other continuation byte':
                i=bs[11].insns[0].copy();i.op0_register=i.op1_register=R.BH;bs[11].insns[0]=i
            else:
                i=bs[0].insns[-1].copy();i.near_branch64=bs[5].insns[0].ip;bs[0].insns[-1]=i
        else:
            at={'new index':0x1805b47f0,'wrong barrier value':0x1805b47fd,'wrong barrier target':0x1805b4800,'wrong resize':0x1805b47dd,'wrong context':0x1805b47d9}[defect]
            b,j=next((b,j) for b in bs for j,i in enumerate(b.insns) if i.ip==at);i=b.insns[j].copy()
            if defect=='new index':i.memory_index=R.RAX
            elif defect=='wrong barrier value':i.op1_register=R.R9
            elif defect=='wrong context':i.memory_displacement+=8
            else:i.near_branch64+=16
            b.insns[j]=i
        orig(dec,md,t,bs,pads);ran.append(True);assert bs[5].succs==[6]
    monkeypatch.setattr(module,'fold_reference_append',alter);d.lift_method(m,td);assert ran
