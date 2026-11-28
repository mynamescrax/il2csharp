import pytest
from dotnet_case import run_case
from il2cpp.emitter import Emitter
from test_game_shift_shared_flags import shift_runtime

pytestmark=pytest.mark.game


def test_ngram_set_uses_full_utf16_length_and_keeps_add_order(shift_runtime,tmp_path):
    meta,il=shift_runtime;m=meta.methods[24616];out=[];Emitter(il,str(tmp_path/'out')).emit_method(m,meta.typedefs[m.declaring],out,'    ')
    source='''using System;using System.Linq;using System.Collections.Generic;
foreach(var (text,n) in new (string,int)[]{(null,-1),("",-1),("ab",0),("ab",-1),("ab",int.MinValue),("ab",2),("ab",3),(new string('a',256),2),(new string('a',256)+"b",2),(new string('a',65536)+"b",65536),("é🙂a",2)})foreach(int stop in new[]{0,1,2}){
 var c=new Computer();var calls=new List<string>();var expected=new List<string>();Exception want=null;var err=new ApplicationException();
 try{if(!string.IsNullOrEmpty(text)){if(text.Length<n)Expect(text);else for(int i=0;i<=unchecked(text.Length-n);i++)Expect(text.Substring(i,n));}}catch(Exception ex){want=ex;}
 void Expect(string item){expected.Add(item);if(expected.Count==stop)throw err;}
 HashSet_1<string>.At=s=>{calls.Add(s);if(calls.Count==stop)throw err;};Exception fault=null;HashSet<string> got=null;try{got=c.Run(text,n);}catch(Exception ex){fault=ex;}
 if(!calls.SequenceEqual(expected)||(want==err?!ReferenceEquals(fault,err):fault?.GetType()!=want?.GetType())||fault==null&&(got==null||!got.SetEquals(expected)))throw new Exception($"len={text?.Length}, n={n}, stop={stop}",fault);
}
Console.WriteLine("whole ngram set: dword string length, ordered attempted adds incl duplicates, wrapped bound and substring faults");
namespace System.Collections.Generic{public class HashSet_1<T>:HashSet<T>{public static Action<T> At;public new bool Add(T item){At(item);return base.Add(item);}}}
class Computer{public HashSet<string> Run(string text,int n)=>BuildNGrams(text,n);\n'''+ '\n'.join(out)+'\n}'
    r=tmp_path/'r';r.mkdir();(r/'Program.cs').write_text(source,encoding='utf8');print(run_case(tmp_path,r))


@pytest.mark.parametrize('bad',['byte','wrong length field','pointer alias','wrong count','unsigned','truncated count'])
def test_length_branch_proves_both_parameters_and_native_width(shift_runtime,monkeypatch,bad):
    from il2cpp import Decompiler,Lifter
    from il2cpp.string_length_bound import bound_sites
    from iced_x86 import Decoder,Register as R
    meta,il=shift_runtime;m=meta.methods[24616];d=Decompiler(Lifter(il));d.lift_method(m,meta.typedefs[m.declaring]);bs=d.L._blocks
    scan=lambda:bound_sites(d.L,m,bs,());site=0x1806a474f;assert scan()=={site:('text','n')}
    ip={'unsigned':0x1806a4752,'truncated count':0x1806a46e6}.get(bad,site);b,j=next((b,j) for b in bs for j,i in enumerate(b.insns) if i.ip==ip);i=b.insns[j].copy()
    if bad=='byte':i=Decoder(64,bytes.fromhex('386f10'),ip=ip).decode()
    elif bad=='wrong length field':i.memory_displacement=0x18
    elif bad=='pointer alias':i.memory_base=R.RBX
    elif bad=='wrong count':i.op1_register=R.EDI
    elif bad=='unsigned':i=Decoder(64,bytes.fromhex('7240'),ip=ip).decode()
    else:i=Decoder(64,bytes.fromhex('418ae8'),ip=ip).decode()
    assert i.len==b.insns[j].len;monkeypatch.setattr(b,'insns',b.insns[:j]+[i]+b.insns[j+1:]);assert not scan()
