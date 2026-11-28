import pytest
from dotnet_case import run_case
from il2cpp.emitter import Emitter
from test_game_shift_shared_flags import shift_runtime

pytestmark=pytest.mark.game


def test_active_camera_search_preserves_array_element_and_result_lifetimes(shift_runtime,tmp_path):
    meta,il=shift_runtime;md=meta.methods[26059];lines=[];Emitter(il,str(tmp_path/'out')).emit_method(md,meta.typedefs[md.declaring],lines,'    ')
    program='''using System;using System.Linq;using System.Collections.Generic;using UnityEngine;
foreach(string mode in new[]{"empty","null array","array","miss","hit","null camera","null game","null result","first getter","active","second getter"}){
 var trace=new List<string>();var ex=new ApplicationException();var inactive=new Camera();var winner=new Camera();var poison=new Camera();var old=new GameObject();var first=new GameObject();var result=new GameObject();
 void Step(string s){trace.Add(s);if(s==mode)throw ex;}
 Camera[] list=mode switch{"empty"=>Array.Empty<Camera>(),"null array"=>null,"miss"=>new[]{inactive},"null camera"=>new Camera[]{null},_=>new[]{inactive,poison,poison}};
 Camera.Read=()=>{Step("array");Camera.Read=()=>throw new Exception("duplicate array query");return list;};
 inactive.Get=()=>{Step("inactive");return old;};old.Active=()=>{Step("check inactive");if(list.Length>1)list[1]=winner;return false;};
 int count=0;winner.Get=()=>{if(++count==1){Step("first getter");return mode=="null game"?null:first;}Step("second getter");return mode=="null result"?null:result;};
 first.Active=()=>{Step("active");list[1]=poison;return true;};poison.Get=()=>throw new Exception("wrong camera");
 Exception fault=null;GameObject found=null;try{found=new CameraManager().Run();}catch(Exception e){fault=e;}
 string[] full={"array","inactive","check inactive","first getter","active","second getter"};int n=mode switch{"empty" or "null array" or "array" or "null camera"=>1,"miss"=>3,"null game" or "first getter"=>4,"active"=>5,_=>6};
 bool callback=mode is "array" or "first getter" or "second getter" or "active";bool npe=mode is "null camera" or "null game" or "null array";
 if(!trace.SequenceEqual(full.Take(n))||!ReferenceEquals(found,mode=="hit"?result:null)||(callback?!ReferenceEquals(ex,fault):npe?fault is not NullReferenceException:fault!=null))throw new Exception(mode+":"+string.Join(',',trace),fault);
}
Console.WriteLine("whole camera search: one array, separate match and miss, two game objects on the same winning camera, exceptions");
namespace UnityEngine{public class Component{public Func<GameObject> Get;public GameObject gameObject=>Get();}public class Camera:Component{public static Func<Camera[]> Read;public static Camera[] allCameras=>Read();}public class GameObject{public Func<bool> Active;public bool activeInHierarchy=>Active();}}
class CameraManager{public GameObject Run()=>GetActiveCamera();\n'''+ '\n'.join(lines)+'\n}'
    r=tmp_path/'r';r.mkdir();(r/'Program.cs').write_text(program,encoding='utf8');print(run_case(tmp_path,r))


@pytest.mark.parametrize('bad',['wrong receiver','lost return expression','missing producer','wrong restore','nonzero miss'])
def test_null_search_needs_the_real_tail_and_zero_return(shift_runtime,monkeypatch,bad):
    from iced_x86 import Register as R
    from il2cpp import Decompiler,Lifter
    from il2cpp.dec.search_loop import _null_or_tail
    meta,il=shift_runtime;m=meta.methods[26059];d=Decompiler(Lifter(il));d.lift_method(m,meta.typedefs[m.declaring]);bs=d.L._blocks
    bid=lambda ip:next(b.bid for b in bs if b.insns[0].ip==ip)
    hdr,hit,miss=map(bid,(0x180541b62,0x180541b9c,0x180541bb5));rt=il._closed_type_key(il.types[m.return_type])
    for n in (hit,miss):monkeypatch.setattr(bs[n],'consumed',False)
    scan=lambda:_null_or_tail(d,bs,miss,hdr,set(),hit,m,rt)
    assert scan()
    if bad=='lost return expression':monkeypatch.setattr(bs[hit],'stmts',['return null; /* tail */'])
    elif bad=='missing producer':monkeypatch.delitem(d.L._element_samples,0x180541b6f)
    else:
        ip={'wrong receiver':0x180541b9e,'wrong restore':0x180541ba6,'nonzero miss':0x180541bba}[bad]
        b,j=next((b,j) for b in bs for j,i in enumerate(b.insns) if i.ip==ip);i=b.insns[j].copy()
        if bad=='wrong receiver':i.op1_register=R.RDI
        elif bad=='wrong restore':i.memory_displacement+=8
        else:i.op1_register=R.ECX
        monkeypatch.setattr(b,'insns',b.insns[:j]+[i]+b.insns[j+1:])
    assert not scan()
