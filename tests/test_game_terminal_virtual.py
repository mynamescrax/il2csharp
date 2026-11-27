import pytest
from iced_x86 import Register as R
from dotnet_case import run_case
from il2cpp import Lifter,Decompiler
from il2cpp.emitter import Emitter
from il2cpp.virtual_edges import terminal_homes
from test_game_shift_shared_flags import shift_runtime

pytestmark=pytest.mark.game


def test_complete_guarded_and_nested_virtual_hits(shift_runtime,tmp_path):
    meta,il=shift_runtime;em=Emitter(il,str(tmp_path/'out'));parts=[]
    for j in (27868,25198):
        m=meta.methods[j];td=meta.typedefs[m.declaring];lines=[];em.emit_method(m,td,lines,'    ')
        fields='public Hittable frontDoorBarricade;' if j==27868 else 'public StoreBrowseBehaviour vanessa;'
        parts.append('public class '+td.name+':Behaviour{'+fields+'public void Run()=>'+m.name+'();\n'+'\n'.join(lines)+'\n}')
    program='''using System;using System.Collections.Generic;using System.Linq;using UnityEngine;
foreach(bool nested in new[]{false,true})foreach(string mode in new[]{"live","inactive","missing","transform throws","position throws","hit throws"}){
 if(nested&&mode=="inactive")continue;
 var store=new StoreManager();var evt=new EventManager();Behaviour self=nested?evt:store;var original=new Target();var captured=new Target();var replacement=new Target();var pt=new Vector3{x=13,y=-8,z=0.25f};var log=new List<string>();var fail=new ApplicationException();
 store.frontDoorBarricade=original;evt.vanessa=new StoreBrowseBehaviour{hittable=mode=="missing"?null:captured};
 original.GO=()=>{log.Add("go");return new GameObject{Active=()=>{log.Add("active");store.frontDoorBarricade=mode=="missing"?null:captured;return mode!="inactive";}};};
 self.Get=()=>{log.Add("transform");if(nested&&!captured.cancelSpawnNextNpc)throw new Exception("flag written too late");
     store.frontDoorBarricade=replacement;evt.vanessa.hittable=replacement;evt.vanessa=new StoreBrowseBehaviour{hittable=replacement};if(mode=="transform throws")throw fail;
     return new Transform{Read=()=>{log.Add("position");store.frontDoorBarricade=null;evt.vanessa=null;if(mode=="position throws")throw fail;return pt;}};};
 captured.Take=(f,p,a,b,s)=>{log.Add("hit");if(f!=(nested?5000:500)||p.x!=pt.x||p.y!=pt.y||p.z!=pt.z||a||!b||s!="Normal")throw new Exception("wrong arguments");if(mode=="hit throws")throw fail;};
 Exception caught=null;try{if(nested)evt.Run();else store.Run();}catch(Exception e){caught=e;}
 var want=(nested?"":"go,active,")+(mode=="missing"&&nested||mode=="inactive"?"":mode=="transform throws"?"transform":"transform,position"+(mode is "missing" or "position throws"?"":",hit"));
 if(string.Join(',',log)!=want.TrimEnd(',')||replacement.cancelSpawnNextNpc||original.cancelSpawnNextNpc||captured.cancelSpawnNextNpc!=(nested&&mode!="missing")||
    (mode.EndsWith(" throws")?!ReferenceEquals(fail,caught):mode=="missing"?caught is not NullReferenceException:caught!=null))throw new Exception(mode+"/"+nested+":"+string.Join(',',log),caught);}
Console.WriteLine("whole virtual hits: guard, pre-getter receiver, override, XYZ, stored flag and exceptions passed");
namespace UnityEngine{public struct Vector3{public float x,y,z;}public class Transform{public Func<Vector3> Read;public Vector3 position=>Read();}public class GameObject{public Func<bool> Active;public bool activeInHierarchy=>Active();}}
public class Behaviour{public Func<Transform> Get;public Transform transform=>Get();}public class StoreBrowseBehaviour{public Hittable hittable;}
public class Hittable{public bool cancelSpawnNextNpc;public Func<GameObject> GO;public GameObject gameObject=>GO();public virtual void Hit(float f,Vector3 p,bool a,bool b,string s)=>throw new Exception("wrong override");}public class Target:Hittable{public Action<float,Vector3,bool,bool,string> Take;public override void Hit(float f,Vector3 p,bool a,bool b,string s)=>Take(f,p,a,b,s);}
'''+ '\n'.join(parts)
    runner=tmp_path/'runner';runner.mkdir();(runner/'Program.cs').write_text(program,encoding='utf8');print(run_case(tmp_path,runner).strip())


def test_terminal_hidden_home_cannot_be_read_on_exit(shift_runtime,monkeypatch):
    meta,il=shift_runtime;d=Decompiler(Lifter(il));md=meta.methods[27868];d.lift_method(md,meta.typedefs[md.declaring]);plans=d.L._terminal_virtuals
    ip,=plans;mi,off,depth,fields=plans[ip];bs=d.L._blocks;get=lambda:terminal_homes(d.L,md,bs,(),{ip:(mi,off,fields)})
    assert ip in get();b,k=next((b,j) for b in bs for j,i in enumerate(b.insns) if i.ip==ip);nxt=b.insns[k].next_ip
    # Keep the actual restore and end of the method; use the final five
    # bytes of call setup as a synthetic call followed by a hidden-home
    # read, so frame validation independently still succeeds.
    from iced_x86 import Decoder
    from il2cpp.stack_local_frame import stack_local_frame
    seq=b.insns;start=seq[k-1].ip;n=nxt-start
    added=list(Decoder(64,bytes.fromhex('e800010000 488b442430')+b'\x90'*(n-10),ip=start));assert n>=10 and added[-1].next_ip==nxt
    monkeypatch.setattr(b,'insns',seq[:k-1]+added+seq[k+1:]);assert stack_local_frame(d.L,md,bs,())
    assert not terminal_homes(d.L,md,bs,(),{start:(mi,off,fields)})
