import pytest
from dotnet_case import run_case
from il2cpp.emitter import Emitter
from test_game_shift_shared_flags import shift_runtime

pytestmark=pytest.mark.game


def test_similarity_uses_full_string_lengths_and_converts_before_dividing(shift_runtime,tmp_path):
    meta,il=shift_runtime;md=meta.methods[24613];lines=[];Emitter(il,str(tmp_path/'out')).emit_method(md,meta.typedefs[md.declaring],lines,'    ')
    src='''using System;
var c=new Computer();foreach(var (a,b,n) in new (string,string,int)[]{(null,"abc",1),("abc",null,1),("","x",0),("x","",1),("abc","axc",1),("a",new string('x',257),256),(new string('x',513),"b",27),("abc","a",-1),("x","y",int.MaxValue),("a🕐","a🕑",1)})foreach(bool throws in new[]{false,true}){
 int calls=0;var err=new ApplicationException();c.Distance=(left,right)=>{if(!ReferenceEquals(a,left)||!ReferenceEquals(b,right))throw new Exception("wrong strings");calls++;if(throws)throw err;return n;};
 Exception fault=null;float got=0;try{got=c.Run(a,b);}catch(Exception e){fault=e;}
 bool skip=string.IsNullOrEmpty(a)||string.IsNullOrEmpty(b);float want=skip?0f:1f-(float)n/(float)Math.Max(a.Length,b.Length);
 if(calls!=(skip?0:1)||(!skip&&throws?!ReferenceEquals(fault,err):fault!=null||BitConverter.SingleToInt32Bits(got)!=BitConverter.SingleToInt32Bits(want)))throw new Exception($"{a?.Length}/{b?.Length}/{n}: {got}",fault);
}
Console.WriteLine("whole similarity score: null/empty, unequal and >255 UTF-16 lengths, signed samples and faults");
class Computer{public Func<string,string,int> Distance;private int LevenshteinDistance(string a,string b)=>Distance(a,b);public float Run(string a,string b)=>Similarity(a,b);\n'''+ '\n'.join(lines)+'\n}'
    r=tmp_path/'r';r.mkdir();(r/'Program.cs').write_text(src,encoding='utf8');print(run_case(tmp_path,r))


@pytest.mark.parametrize('bad',['wrong width','changed selector','other divisor','wrong low lane','not a length','different source'])
def test_normalization_cannot_guess_field_width_or_conversion(shift_runtime,monkeypatch,bad):
    from il2cpp import Decompiler,Lifter
    from il2cpp.string_ratio import string_ratios
    from iced_x86 import Register as R, Decoder
    meta,il=shift_runtime;m=meta.methods[24613];td=meta.typedefs[m.declaring];d=Decompiler(Lifter(il));d.lift_method(m,td);bs=d.L._blocks
    scan=lambda:string_ratios(d.L,m,td,bs,());assert set(scan()[0])=={0x1806ab262}
    ip={'wrong width':0x1806ab262,'changed selector':0x1806ab26a,'other divisor':0x1806ab277,'wrong low lane':0x1806ab281,'not a length':0x1806ab25a,'different source':0x1806ab26a}[bad]
    b,j=next((b,j) for b in bs for j,i in enumerate(b.insns) if i.ip==ip);i=b.insns[j].copy()
    if bad=='wrong width':i=Decoder(64,bytes.fromhex('3a5710'),ip=ip).decode()
    elif bad=='changed selector':i=Decoder(64,bytes.fromhex('0f475710'),ip=ip).decode()
    elif bad=='other divisor':i.op1_register=R.ECX
    elif bad=='wrong low lane':i.op1_register=R.XMM1
    elif bad=='not a length':i.memory_displacement=0x14
    else:i.memory_base=R.RBX
    assert i.len==b.insns[j].len;monkeypatch.setattr(b,'insns',b.insns[:j]+[i]+b.insns[j+1:]);assert scan()==({},{})
