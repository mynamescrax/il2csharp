import re
import pytest
from dotnet_case import run_case
from iced_x86 import Register as R
from il2cpp import Decompiler,Lifter
from il2cpp.accessor_chain import reacquired_accessors
from test_game_shift_shared_flags import shift_runtime

pytestmark=pytest.mark.game


def test_spill_camera_queries_read_the_current_field_at_both_sites(shift_runtime,tmp_path):
    meta,il=shift_runtime;d=Decompiler(Lifter(il));parts=[]
    for j in (25688,25689):
        m=meta.methods[j];lines=d.lift_method(m,meta.typedefs[m.declaring]);end=next(i for i,s in enumerate(lines) if s.strip().endswith('.forward;'))
        # Scoped receiver/getter statements, before either physics query.
        keep=[s.strip() for s in lines[:end+1] if re.fullmatch(r'(?:UnityEngine\.(?:Transform|Vector3) )?\w+ = (?:this\.playerCam|\w+\.(?:transform|position|forward));',s.strip())]
        assert len(keep)==6;parts.append('public void '+m.name+'(){\n'+'\n'.join(keep)+'\n}')
    src='''using System;using System.Collections.Generic;using System.Linq;using UnityEngine;
foreach(bool hose in new[]{false,true})foreach(string mode in new[]{"replace","same","outer null","second null","no P","no F","A fault","P fault","B fault","F fault"}){
 var c=new Case();var a=new Transform();var b=new Transform();var p=new Transform();var f=new Transform();var trace=new List<string>();var boom=new ApplicationException();
 void Step(string s){trace.Add(s);if(s+" fault"==mode)throw boom;}c.playerCam=mode=="outer null"?null:a;int calls=0;a.G=()=>{if(calls++==0){Step("A");return mode=="no P"?null:p;}Step("B");return f;};b.G=()=>{Step("B");return mode=="no F"?null:f;};
 p.P=()=>{Step("P");c.playerCam=mode=="same"?a:mode=="second null"?null:b;return new Vector3();};f.F=()=>{Step("F");return new Vector3();}; Exception ex=null;try{if(hose)c.CleanSpillHose();else c.CleanSpill();}catch(Exception e){ex=e;}
 int n=mode switch{"outer null"=>0,"no P" or "A fault"=>1,"second null" or "P fault"=>2,"no F" or "B fault"=>3,_=>4};bool nulls=mode.Contains("null")||mode.StartsWith("no ");if(!trace.SequenceEqual(new[]{"A","P","B","F"}.Take(n))||(nulls?ex is not NullReferenceException:mode.EndsWith(" fault")?!ReferenceEquals(boom,ex):ex!=null))throw new Exception(mode+":"+string.Join(',',trace),ex);}
Console.WriteLine("spill receiver slices: two transform calls per method, fresh receiver after position, distinct values and fault order passed");
namespace UnityEngine{class Transform{public Func<Transform> G;public Func<Vector3>P,F;public Transform transform=>G();public Vector3 position=>P();public Vector3 forward=>F();}struct Vector3{public float x,y,z;}}
class Case{public Transform playerCam;\n'''+ '\n'.join(parts)+'\n}'
    runner=tmp_path/'runner';runner.mkdir();(runner/'Program.cs').write_text(src,encoding='utf8');print(run_case(tmp_path,runner).strip())


@pytest.mark.parametrize('defect',['wrong sret receiver','wrong first hidden lane','nonfield source','different return owner'])
def test_chain_needs_two_independent_closed_reads(shift_runtime,monkeypatch,defect):
    meta,il=shift_runtime;m=meta.methods[25688];td=meta.typedefs[m.declaring];d=Decompiler(Lifter(il));d.lift_method(m,td);bs=d.L._blocks
    f=lambda:reacquired_accessors(d.L,m,td,bs,());fields,calls=f();assert len(fields)==2 and len(calls)==4
    if defect=='different return owner':
        md=meta.methods[calls[0x18070d035]];monkeypatch.setattr(md,'return_type',td.byval)
    else:
        pos=0x18070d035;b,j=next((b,j) for b in bs for j,i in enumerate(b.insns) if i.ip==pos);ip=sorted(fields)[1] if defect=='nonfield source' else b.insns[j-1].ip if defect=='wrong first hidden lane' else pos
        if defect=='wrong sret receiver':
            seq=[i for b in bs for i in b.insns];ip=seq[next(k for k,i in enumerate(seq) if i.ip==pos)+5].ip
        b,j=next((b,j) for b in bs for j,i in enumerate(b.insns) if i.ip==ip);i=b.insns[j].copy()
        if defect=='nonfield source':i.memory_base=R.R10
        elif defect=='wrong first hidden lane':i.op0_register=R.R8D
        else:i.op1_register=R.RBX
        monkeypatch.setattr(b,'insns',b.insns[:j]+[i]+b.insns[j+1:])
    assert f()==({},{})
