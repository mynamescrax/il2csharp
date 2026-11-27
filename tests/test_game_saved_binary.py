import pytest
from iced_x86 import Register as R

from dotnet_case import run_case
from il2cpp import Decompiler,Lifter
from il2cpp.saved_binary import binary_arguments
from test_game_shift_shared_flags import shift_runtime

pytestmark=pytest.mark.game


def test_wheel_selection_resamples_only_improving_candidates(shift_runtime,tmp_path):
    meta,il=shift_runtime;m=meta.methods[27625];d=Decompiler(Lifter(il));lines=d.lift_method(m,meta.typedefs[m.declaring]);end=next(j for j,l in enumerate(lines) if '.SetTrigger(' in l)
    code='\n'.join(lines[:end+1]);assert code.count('.position;')==4 and code.count('Vector3.Distance(')==1
    src='''using System;using System.Collections.Generic;using System.Linq;using UnityEngine;
foreach(string mode in new[]{"replace","shrink","asc","desc","tie","first NaN","saved NaN","at bound","infinite","empty","second null","distance fault"}){
 var c=new Case();var log=new List<string>();var fail=new ApplicationException();Vector3 Pos(float x)=>new(){x=8,y=-7,z=x};int arrows=0;
 Transform Tip(int idx=-1)=>new(){Get=()=>{log.Add("a"+ ++arrows);return Pos(0);}};c.arrowTip=Tip();
 Transform Slot(string name,float first,float second,Action<int> after=null){int n=0;return new(){Get=()=>{log.Add(name+ ++n);after?.Invoke(n);return Pos(n==1?first:second);}};}
 Vector3.Compute=(a,b)=>{log.Add("dist");if(a.x!=8||a.y!=-7||a.z!=0||b.x!=8||b.y!=-7)throw new Exception("bad XYZ or order");if(mode=="distance fault")throw fail;return Math.Abs(b.z);};
 var firsts=mode switch{"asc"=>new[]{2f,7f},"desc"=>new[]{7f,2f},"tie"=>new[]{2f,2f},"first NaN"=>new[]{float.NaN,9f},"saved NaN"=>new[]{2f,1f},"at bound"=>new[]{10000f,10001f},"infinite"=>new[]{float.PositiveInfinity},"empty"=>Array.Empty<float>(),_=>new[]{5f,9f,7f}};
 c.wheelObjects=firsts.Select((f,j)=>Slot(j.ToString()+".",f,mode=="saved NaN"?float.NaN:f)).ToArray();
 if(mode=="replace"){var b=new[]{Slot("B0.",13,13),Slot("B1.",9,7),Slot("B2.",7,8)};c.wheelObjects=new[]{Slot("A0.",5,4,n=>c.wheelObjects=b)};}
 if(mode=="shrink"){c.wheelObjects[1]=Slot("1.",11,0,n=>c.wheelObjects=Array.Empty<Transform>());}
 if(mode=="second null")c.wheelObjects[0]=Slot("0.",5,0,n=>c.wheelObjects=null);
 int winner=-99;c.wheelWinIndicator=Enumerable.Range(0,3).Select(j=>new Animator{Trigger=s=>{if(s!="Play")throw new Exception();winner=j;log.Add("selected");}}).ToArray();Exception fault=null;try{c.Select();}catch(Exception e){fault=e;}
 string want=mode switch{
 "replace"=>"a1,A0.1,a2,B0.1,dist,a3,B1.1,a4,B1.2,dist,a5,B2.1,selected",
 "desc"=>"a1,0.1,a2,0.2,dist,a3,1.1,a4,1.2,dist,selected","first NaN"=>"a1,0.1,a2,1.1,a3,1.2,dist,selected",
 "asc" or "tie" or "shrink" or "saved NaN"=>"a1,0.1,a2,0.2,dist,a3,1.1,selected","at bound"=>"a1,0.1,a2,1.1","infinite"=>"a1,0.1","empty"=>"",
 "second null"=>"a1,0.1,a2",_=>"a1,0.1,a2,0.2,dist"};int idx=mode switch{"replace" or "desc" or "first NaN"=>1,"asc" or "tie" or "shrink" or "saved NaN"=>0,_=>-99};
 if(want!=string.Join(',',log)||idx!=winner||(mode is "at bound" or "empty" or "infinite"?fault is not IndexOutOfRangeException:mode=="second null"?fault is not NullReferenceException:mode=="distance fault"?!ReferenceEquals(fault,fail):fault!=null))throw new Exception(mode+":"+string.Join(',',log),fault);}
Console.WriteLine("whole selection loop: first sample compares, second sample sets threshold, live arrays, ties, NaNs and faults passed");
namespace UnityEngine{public class Transform{public Func<Vector3> Get;public Vector3 position=>Get();}public struct Vector3{public float x,y,z;public static Func<Vector3,Vector3,float> Compute;public static float Distance(Vector3 a,Vector3 b)=>Compute(a,b);}public class Animator{public Action<string> Trigger;public void SetTrigger(string s)=>Trigger(s);}}
class Case{public Transform arrowTip;public Transform[] wheelObjects;public Animator[] wheelWinIndicator;public void Select(){\n'''+code+'\n}}'
    runner=tmp_path/'runner';runner.mkdir();(runner/'Program.cs').write_text(src,encoding='utf8');print(run_case(tmp_path,runner).strip())


@pytest.mark.parametrize('defect',['wrong high lane','stale argument home','different twin','overlap','wrong table index','wrong table padding'])
def test_saved_argument_proof_needs_all_paths_and_lanes(shift_runtime,monkeypatch,defect):
    meta,il=shift_runtime;m=meta.methods[27625];d=Decompiler(Lifter(il));d.lift_method(m,meta.typedefs[m.declaring]);bs=d.L._blocks
    f=lambda:binary_arguments(d.L,m,bs,());reads,uses=f();site,=uses
    if defect=='wrong table padding':
        read=il.bin.read;monkeypatch.setattr(il.bin,'read',lambda va,n:b'\x75\x01\xcc' if va==0x1805c9125 and n==3 else read(va,n))
    else:
        b,j=next((b,j) for b in bs for j,i in enumerate(b.insns) if i.ip==site)
        if defect=='wrong table index':b,j=next((b,j) for b in bs for j,i in enumerate(b.insns) if i.ip==0x1805c8f81)
        else:j+={'wrong high lane':-6,'stale argument home':-5,'different twin':0,'overlap':-7}[defect]
        i=b.insns[j].copy()
        if defect=='wrong high lane':i.op1_register=R.EDI
        elif defect=='different twin':i.near_branch64+=16
        elif defect=='wrong table index':i.op1_register=R.EDX
        else:i.memory_displacement=32 if defect=='stale argument home' else 80
        monkeypatch.setattr(b,'insns',b.insns[:j]+[i]+b.insns[j+1:])
    assert site not in f()[1]
