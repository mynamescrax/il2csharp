import re

import pytest
from iced_x86 import Decoder

from dotnet_case import run_case
from il2cpp import Decompiler,Lifter
from il2cpp.emitter import Emitter
from il2cpp.virtual_forward import virtual_forward
from test_game_shift_shared_flags import shift_runtime

pytestmark=pytest.mark.game


def test_complete_stun_callback_dispatches_to_override(shift_runtime,tmp_path):
    meta,il=shift_runtime;m=meta.methods[25436];td=meta.typedefs[m.declaring];out=tmp_path/'out';em=Emitter(il,str(out))
    em._emit_one_top(td,meta.images[m.image],td.name);s=next(out.rglob('Hittable.cs')).read_text(encoding='utf8')
    method=re.search(r'^    private void DealStunDamage\(\)\n.*?^    }',s,re.S|re.M)[0];assert 'getClass' not in method
    runner=tmp_path/'runner';runner.mkdir();(runner/'Program.cs').write_text('''using System;
var instance=new Derived();instance.Fire();if(instance.Count!=1||Vector3.Reads!=1)throw new Exception("wrong evaluation count");
Vector3.Fail=true;try{instance.Fire();throw new Exception("missing getter fault");}catch(ApplicationException e)when(ReferenceEquals(e,Vector3.Error)){}
if(instance.Count!=1||Vector3.Reads!=2)throw new Exception("call executed after fault");
Console.WriteLine("DealStunDamage: one public value read, override received all lanes, both flags and string; getter fault prevents dispatch");
record struct Vector3(float x,float y,float z){private static readonly Vector3 zeroVector=new(-11,3.5f,25);
public static int Reads;public static bool Fail;public static ApplicationException Error=new();
public static Vector3 zero{get{Reads++;if(Fail)throw Error;return zeroVector;}}}
class Derived:Hittable{public int Count;public override void Hit(float f,Vector3 p,bool a,bool b,string s){
 if(f!=3||p!=new Vector3(-11,3.5f,25)||!a||b||s!="Normal")throw new Exception("wrong arguments");Count++;}}
class Hittable{public virtual void Hit(float f,Vector3 p,bool a,bool b,string s)=>throw new Exception("base implementation");
public void Fire()=>DealStunDamage();\n'''+method+'}',encoding='utf8');print(run_case(tmp_path,runner).strip())


@pytest.mark.parametrize('change',['other companion','alias hidden home','partial field','other receiver','ambiguous getter'])
def test_terminal_forward_needs_exact_virtual_and_property_proofs(shift_runtime,monkeypatch,change):
    m,il=shift_runtime;d=Decompiler(Lifter(il));md=m.methods[25436];td=m.typedefs[md.declaring];d.lift_method(md,td);bs=d.L._blocks
    prove=lambda:virtual_forward(d.L,md,td,bs,[i for b in bs for i in b.insns],d._pad_bids)
    assert prove()
    if change=='ambiguous getter':
        other=next(j for j in m.type_methods(m.typedefs[7271]) if m.methods[j].name=='get_one');monkeypatch.setattr(m.methods[other],'addr',m.methods[55796].addr)
    else:
        ip,byte={'other companion':(0x1806f3ab0,3),'alias hidden home':(0x1806f3ab7,-1),'partial field':(0x1806f3aa9,-1),'other receiver':(0x1806f3a9b,-1)}[change]
        b,j=next((b,j) for b in bs for j,i in enumerate(b.insns) if i.ip==ip);i=b.insns[j];raw=bytearray(il.bin.read(ip,i.len));raw[byte]^=8 if change!='other receiver' else 1
        repl=list(Decoder(64,bytes(raw),ip=ip));assert len(repl)==1 and repl[0].len==i.len
        monkeypatch.setattr(b,'insns',b.insns[:j]+repl+b.insns[j+1:])
    assert not prove()
