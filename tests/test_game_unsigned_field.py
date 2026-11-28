import pytest
from iced_x86 import Decoder,Register as R
from dotnet_case import run_case
from test_game_guarded_continuation import emitted_move
from test_game_shift_shared_flags import shift_runtime

pytestmark=pytest.mark.game


def test_finished_particle_iterator_does_not_poll_or_resurrect(shift_runtime,tmp_path):
    meta,il=shift_runtime;move=emitted_move(meta,il,28689,tmp_path/'out')
    src='''using System;using System.Collections;using UnityEngine;
foreach(int initial in new[]{int.MinValue,-1,0,1,2,int.MaxValue})foreach(string mode in new[]{"dead","yield","throw","null"}){
 var f=new Frame{__1__state=initial};var current=f.Current;var e=(IEnumerator)f;var err=new ApplicationException();int polls=0;
 f.particleSystem=mode=="null"?null:new ParticleSystem{Check=children=>{if(!children||f.__1__state!=-1)throw new Exception("bad poll");polls++;if(mode=="throw")throw err;return mode=="yield"&&polls==1;}};
 Exception fault=null;bool result=false;try{result=e.MoveNext();}catch(Exception x){fault=x;}
 bool valid=initial==0||initial==1;bool yielded=valid&&mode=="yield";
 if(result!=yielded||polls!=(valid&&mode!="null"?1:0)||f.__1__state!=(yielded?1:valid?-1:initial)||!ReferenceEquals(f.Current,yielded?null:current)||
    (valid&&mode=="throw"?!ReferenceEquals(fault,err):valid&&mode=="null"?fault is not NullReferenceException:fault!=null))throw new Exception($"entry {initial}/{mode}",fault);
 if(yielded&&(e.MoveNext()||polls!=2||f.__1__state!=-1))throw new Exception("bad end after yield");
 int before=polls;f.particleSystem=new ParticleSystem{Check=_=>throw new Exception("completed iterator polled again")};
 if(e.MoveNext()||polls!=before||!ReferenceEquals(f.Current,yielded?null:current))throw new Exception("replayed finished callback");
}
Console.WriteLine("complete particle wait iterator: unsigned entry, real completion, repeat MoveNext, yield and callback faults passed");
namespace UnityEngine{public class ParticleSystem{public Func<bool,bool> Check;public bool IsAlive(bool children)=>Check(children);}}
class Frame:IEnumerator{public int __1__state;public object __2__current=new();public ParticleSystem particleSystem;public object Current=>__2__current;public void Reset()=>throw new NotSupportedException();
'''+move+'\n}'
    r=tmp_path/'r';r.mkdir();(r/'Program.cs').write_text(src,encoding='utf8');print(run_case(tmp_path,r))


@pytest.mark.parametrize('change',['signed branch','flag writer','wrong base','wrong width','different field','alternate entry'])
def test_unsigned_field_bound_requires_live_dword_comparison(shift_runtime,monkeypatch,change):
    from il2cpp import Decompiler,Lifter
    from il2cpp.unsigned_field import field_bounds
    meta,il=shift_runtime;m=meta.methods[28689];td=meta.typedefs[m.declaring];d=Decompiler(Lifter(il));d.lift_method(m,td);bs=d.L._blocks
    find=lambda:field_bounds(d.L,m,td,bs,());cmp=0x180638856;assert cmp in find()
    ip={'signed branch':0x18063885d,'flag writer':0x18063885a,'alternate entry':0x18063887b}.get(change,cmp)
    b,j=next((b,j) for b in bs for j,i in enumerate(b.insns) if i.ip==ip);i=b.insns[j].copy()
    if change=='flag writer':i=Decoder(64,bytes.fromhex('4885c9'),ip=ip).decode()
    elif change=='signed branch':i=Decoder(64,b'\x7f\x40',ip=ip).decode()
    elif change=='wrong base':i.memory_base=R.RDI
    elif change=='different field':i.memory_displacement=0x18
    elif change=='wrong width':i=Decoder(64,bytes.fromhex('80791001'),ip=ip).decode()
    else:i.near_branch64=0x18063885d
    assert i.len==b.insns[j].len;monkeypatch.setattr(b,'insns',b.insns[:j]+[i]+b.insns[j+1:]);assert cmp not in find()


def test_unsigned_bound_sign_extends_the_encoded_immediate(shift_runtime,monkeypatch):
    from il2cpp import Decompiler,Lifter
    from il2cpp.unsigned_field import field_bounds
    meta,il=shift_runtime;m=meta.methods[28689];td=meta.typedefs[m.declaring];d=Decompiler(Lifter(il));d.lift_method(m,td);bs=d.L._blocks
    ip=0x180638856;b,j=next((b,j) for b in bs for j,i in enumerate(b.insns) if i.ip==ip)
    cmp=Decoder(64,bytes.fromhex('83791080'),ip=ip).decode();assert cmp.len==b.insns[j].len
    monkeypatch.setattr(b,'insns',b.insns[:j]+[cmp]+b.insns[j+1:]);plan=field_bounds(d.L,m,td,bs,())
    assert plan[ip][2:]==(0xffffff80,'>')
