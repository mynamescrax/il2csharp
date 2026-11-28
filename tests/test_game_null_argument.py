import pytest
from dotnet_case import run_case
from il2cpp.emitter import Emitter
from test_game_shift_shared_flags import shift_runtime

pytestmark=pytest.mark.game


def test_detach_clears_blueprint_before_finding_the_renderer(shift_runtime,tmp_path):
    meta,il=shift_runtime;m=meta.methods[23951];lines=[];Emitter(il,str(tmp_path/'out')).emit_method(m,meta.typedefs[m.declaring],lines,'    ')
    src='''using System;using System.Collections.Generic;using System.Linq;using Obi;using UnityEngine;
foreach(string mode in new[]{"ok","null initial","clear","null after clear","lookup","null renderer","disable"}){
 var c=new ExtendableGrapplingHook();var a=new ObiRope();var b=new ObiRope();var r=new ObiRopeExtrudedRenderer();var trace=new List<string>();var err=new ApplicationException();void Step(string s){trace.Add(s);if(mode==s)throw err;}
 c.rope=mode=="null initial"?null:a;a.Put=v=>{if(v is not null)throw new Exception("blueprint not null");Step("clear");c.rope=mode=="null after clear"?null:b;};a.Lookup=t=>throw new Exception("stale receiver");b.Lookup=t=>{if(t!=typeof(ObiRopeExtrudedRenderer))throw new Exception();Step("lookup");return mode=="null renderer"?null:r;};r.Set=v=>{if(v)throw new Exception();Step("disable");};
 Exception fault=null;try{c.Run();}catch(Exception e){fault=e;}string[] steps={"clear","lookup","disable"};int n=mode switch{"ok"=>3,"null initial"=>0,"null after clear"=>1,"null renderer"=>2,_=>Array.IndexOf(steps,mode)+1};
 if(!trace.SequenceEqual(steps.Take(n))||(mode.StartsWith("null")?fault is not NullReferenceException:mode=="ok"?fault!=null:!ReferenceEquals(err,fault)))throw new Exception(mode+":"+string.Join(',',trace),fault);
}
Console.WriteLine("complete rope detach: typed null assignment, post-setter receiver and faults");
namespace UnityEngine{public class Component{public Func<Type,Component> Lookup;public T GetComponent<T>() where T:Component=>(T)Lookup(typeof(T));}}
namespace Obi{public class ObiRopeBlueprint{}public class ObiRope:Component{public Action<ObiRopeBlueprint> Put;public ObiRopeBlueprint ropeBlueprint{set=>Put(value);}}public class ObiRopeExtrudedRenderer:Component{public Action<bool> Set;public bool enabled{set=>Set(value);}}}
class ExtendableGrapplingHook{public ObiRope rope;public void Run()=>DetachHook();\n'''+ '\n'.join(lines)+'\n}'
    r=tmp_path/'r';r.mkdir();(r/'Program.cs').write_text(src,encoding='utf8');print(run_case(tmp_path,r))


def test_dialogue_call_distinguishes_register_and_stack_null_from_true(shift_runtime,tmp_path):
    from il2cpp import Lifter,Decompiler
    meta,il=shift_runtime;m=meta.methods[24702];td=meta.typedefs[m.declaring];body=Decompiler(Lifter(il)).lift_method(m,td)
    # Only the dialogue call. Public access to either singleton, or the
    # entire event handler, is not implied by its five arguments.
    i=next(j for j,s in enumerate(body) if '.NewDialogueBranch(' in s);line=body[i].strip();name=line.split('.',1)[0]
    assert name.isidentifier() and line.endswith(';')
    prog='''using System;
var s=new SpeakingManager();var c=new Gate();var fault=new ApplicationException();int calls=0;
foreach(bool fail in new[]{false,true}){s.Callback=(speaker,what,name,obj,flag)=>{if(speaker!="Cow"||what!="Greeting"||name is not null||obj is not null||!flag)throw new Exception("bad args");calls++;if(fail)throw fault;};Exception ex=null;try{c.Run(s);}catch(Exception e){ex=e;}if(!ReferenceEquals(ex,fail?fault:null))throw new Exception("wrong fault",ex);}if(calls!=2)throw new Exception("lost dialogue");
Console.WriteLine("dialogue argument slice: two strings, two typed nulls, one true boolean");
class DialogueInteractable{}class SpeakingManager{public Action<string,string,string,DialogueInteractable,bool> Callback;public void NewDialogueBranch(string who,string what,string name,DialogueInteractable obj,bool b)=>Callback(who,what,name,obj,b);}
class Gate{public void Run(SpeakingManager '''+name+'){\n'+line+'\n}}'
    r=tmp_path/'r';r.mkdir();(r/'Program.cs').write_text(prog,encoding='utf8');print(run_case(tmp_path,r))


@pytest.mark.parametrize('bad',['partial register zero','ambiguous target','not zero','shift stack home','truncate reference store'])
def test_null_arguments_need_full_native_zeros_and_exact_slot(shift_runtime,monkeypatch,bad):
    from iced_x86 import Register as R,Decoder
    from il2cpp import Decompiler,Lifter
    from il2cpp.null_argument import null_sites
    meta,il=shift_runtime;m=meta.methods[24702];d=Decompiler(Lifter(il));d.lift_method(m,meta.typedefs[m.declaring]);bs=d.L._blocks
    find=lambda:null_sites(d.L,m,bs,());site=0x1806b22c0;assert find()[site][1]=={3,4}
    if bad=='ambiguous target':monkeypatch.setitem(il.addr_candidates,0x1805bfcb0,[('method',27504),('method',27505)]);assert site not in find();return
    ip={'partial register zero':0x1806b22ae,'not zero':0x1806b22a5,'shift stack home':0x1806b22bb,'truncate reference store':0x1806b22bb}[bad]
    b,j=next((b,j) for b in bs for j,i in enumerate(b.insns) if i.ip==ip);i=b.insns[j].copy()
    if bad=='partial register zero':i=Decoder(64,bytes.fromhex('4530c9'),ip=ip).decode()
    elif bad=='not zero':i.op1_register=R.ECX
    elif bad=='shift stack home':i.memory_displacement+=8
    else:i=Decoder(64,bytes.fromhex('2e89442420'),ip=ip).decode()
    assert i.len==b.insns[j].len;monkeypatch.setattr(b,'insns',b.insns[:j]+[i]+b.insns[j+1:]);assert (3 if bad=='partial register zero' else 4) not in find().get(site,(None,set()))[1]
