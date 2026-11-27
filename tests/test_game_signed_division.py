"""Whole leaf results and faults; inputs use both static and instance ABI."""
import pytest
from iced_x86 import Decoder
from dotnet_case import run_case
from il2cpp import Decompiler,Lifter
from il2cpp.emitter import Emitter
from il2cpp.signed_division import signed_div_leaf
from test_game_shift_shared_flags import shift_runtime

pytestmark=pytest.mark.game


def test_complete_signed_division_leaves(shift_runtime,tmp_path):
    meta,il=shift_runtime;em=Emitter(il,str(tmp_path/'out'));members=[];checks=[];d=Decompiler(Lifter(il))
    for j,formula in ((81170,'Q(a,b)+1'),(81171,'(long)a-R(a,b)+b'),(50405,'Q(unchecked(a+b-1),b)'),
                      (66524,'(long)unchecked(a+b-1)-R(unchecked(a+b-1),b)'),
                      (96816,'R(a,b)<0?R(a,b)+b:R(a,b)'),(122752,'Q(a,b)+(R(a,b)!=0?1:0)')):
        m=meta.methods[j];td=meta.typedefs[m.declaring];lines=[]
        assert signed_div_leaf(d.L,m,td,d._decode(m)[0],il.eh_regions(m.addr))
        em.emit_method(m,td,lines,'    ')
        invoke=('' if m.is_static else 'new C'+str(j)+'().')+m.name+'(a,b)'
        members.append('class C'+str(j)+'{\n'+'\n'.join(lines)+'\npublic static int Run(int a,int b)=>'+invoke+';\n}')
        checks.append(f'Test(C{j}.Run,(a,b)=>unchecked((int)({formula})));')
    d=Decompiler(Lifter(il));m=meta.methods[81170];td=meta.typedefs[m.declaring]
    # Same signature, neither output live. The quotient must still fault at
    # IDIV and the reaching constant assignment happens only on success.
    s=list(Decoder(64,bytes.fromhex('448bc2 8bc1 99 41f7f8 b829000000 c3'),ip=m.addr))
    dead=signed_div_leaf(d.L,m,td,s,None);assert dead
    names=[p.name for p in meta.method_params(m)];members.append('class Dead {public static int Run(int '+names[0]+',int '+names[1]+'){\n'+'\n'.join(dead)+'\n}}')
    checks.append('Test(Dead.Run,(a,b)=>{Q(a,b);return 41;});')
    src='''using System;
// A widened oracle determines the native dword quotient, remainder and #DE.
long Q(int a,int b){long q=(long)a/b;return q>int.MaxValue||q<int.MinValue?throw new OverflowException():q;}
long R(int a,int b)=>a-b*Q(a,b);
void Test(Func<int,int,int> actual,Func<int,int,int> oracle){foreach(int a in new[]{-17,0,1,17,int.MaxValue,int.MinValue,int.MinValue+2})foreach(int b in new[]{5,-5,1,-1,0,3,int.MinValue}){
 (int,Type) Run(Func<int,int,int> f){try{return(f(a,b),null);}catch(ArithmeticException e){return(0,e.GetType());}}
 var want=Run(oracle);var got=Run(actual);if(want!=got)throw new Exception($"{actual.Method.DeclaringType}: {a}/{b}: expected {want}, got {got}");}}
'''+ '\n'.join(checks)+'\nConsole.WriteLine("six complete signed quotient/remainder helpers and dead-output faults passed");\n'+'\n'.join(members)
    runner=tmp_path/'runner';runner.mkdir();(runner/'Program.cs').write_text(src,encoding='utf8');print(run_case(tmp_path,runner).strip())


@pytest.mark.parametrize('raw',[
    '448bc2 8bc1 99 6641f7f8 c3', # 16-bit DX:AX
    '448bc2 8bc1 99 49f7f8 c3',   # RDX:RAX, not EDX:EAX
    '448bc2 8bc1 99 41f7f0 c3',   # unsigned division
    '448bc2 8bc1 99 ffc0 41f7f8 c3', # EAX changed since CDQ
    '448bc2 8bc1 99 41f7f8 4885d2 0f48c2 c3', # observes all 64 bits of RDX
    '448bc2 8bc1 85c9 99 41f7f8 0f45c2 c3', # IDIV did not preserve TEST's ZF
])
def test_signed_leaf_declines_wrong_width_or_provenance(shift_runtime,raw):
    meta,il=shift_runtime;m=meta.methods[81170];td=meta.typedefs[m.declaring];s=list(Decoder(64,bytes.fromhex(raw),ip=m.addr))
    assert signed_div_leaf(Lifter(il),m,td,s,None) is None
