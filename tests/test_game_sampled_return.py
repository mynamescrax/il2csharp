import pytest
from dotnet_case import run_case
from il2cpp.emitter import Emitter
from test_game_shift_shared_flags import shift_runtime

pytestmark = pytest.mark.game


def test_random_vector_uses_three_ordered_draws(shift_runtime,tmp_path):
    meta,il=shift_runtime;m=meta.methods[28968];lines=[];Emitter(il,str(tmp_path/'out')).emit_method(m,meta.typedefs[m.declaring],lines,'    ')
    src='''using System;using UnityEngine;
float F(uint u)=>BitConverter.Int32BitsToSingle(unchecked((int)u));
foreach (int stop in new[]{0,1,2,3}){
    float lo=F(0x80000000),hi=F(0x7fc0dd55);float[] draws={F(1),F(0xffc00123),F(0x80000000),19f};
    int n=0;var err=new ApplicationException();UnityEngine.Random.Draw=(a,b)=>{
        if(BitConverter.SingleToInt32Bits(a)!=BitConverter.SingleToInt32Bits(lo)||BitConverter.SingleToInt32Bits(b)!=BitConverter.SingleToInt32Bits(hi))throw new Exception("wrong bounds");
        n++;if(n==stop)throw err;return draws[n-1];};
    Vector3 v=default;Exception fault=null;try{v=FVectorMethods.RandomVector(lo,hi);}catch(Exception e){fault=e;}
    if(stop!=0){if(n!=stop||!ReferenceEquals(fault,err))throw new Exception("fault at draw "+stop,fault);continue;}
    if(fault!=null||n!=3||BitConverter.SingleToInt32Bits(v.x)!=BitConverter.SingleToInt32Bits(draws[0])||BitConverter.SingleToInt32Bits(v.y)!=BitConverter.SingleToInt32Bits(draws[1])||BitConverter.SingleToInt32Bits(v.z)!=BitConverter.SingleToInt32Bits(draws[2])||UnityEngine.Random.Range(lo,hi)!=19f)throw new Exception("lost or reordered draw",fault);
}
Console.WriteLine("whole RandomVector: three independent samples, lane bits, next draw and exception cutoffs");
namespace UnityEngine{public struct Vector3{public float x,y,z;}public static class Random{public static Func<float,float,float> Draw;public static float Range(float a,float b)=>Draw(a,b);}}
class FVectorMethods{\n'''+ '\n'.join(lines)+'\n}'
    r=tmp_path/'r';r.mkdir();(r/'Program.cs').write_text(src,encoding='utf8');print(run_case(tmp_path,r))


@pytest.mark.parametrize('change',['wrong input','reused result','different hidden','wrong output stride','read upper lane','ambiguous producer','wrong echo','wrong restore'])
def test_call_samples_require_all_lanes_and_arguments(shift_runtime,monkeypatch,change):
    from iced_x86 import Decoder, Register as R
    from il2cpp import Decompiler,Lifter
    from il2cpp.sampled_return import sampled_returns
    meta,il=shift_runtime;m=meta.methods[28968];td=meta.typedefs[m.declaring];d=Decompiler(Lifter(il));d.lift_method(m,td);bs=d.L._blocks
    plan=lambda:sampled_returns(d.L,m,td,bs,());assert set(plan())=={0x1806432e1,0x1806432f4,0x180643307}
    if change=='ambiguous producer':
        monkeypatch.setitem(il.addr_candidates,0x182be3810,[('method',56177),('method',56178)])
    else:
        ip={'wrong input':0x1806432f0,'reused result':0x18064331b,'different hidden':0x1806432fc,'wrong output stride':0x180643324,'read upper lane':0x1806432f9,'wrong echo':0x180643312,'wrong restore':0x18064331f}[change]
        b,j=next((b,j) for b in bs for j,i in enumerate(b.insns) if i.ip==ip);i=b.insns[j].copy()
        if change=='wrong input':i.op1_register=R.XMM9
        elif change=='reused result':i.op1_register=R.XMM6
        elif change=='different hidden':i.op0_register=i.op1_register=R.R9D
        elif change=='wrong output stride':i.memory_displacement=8
        elif change=='wrong echo':i.op1_register=R.RSI
        elif change=='wrong restore':i.memory_displacement=0x50
        else:i=Decoder(64,bytes.fromhex('0f15f0'),ip=ip).decode()
        assert i.next_ip==b.insns[j].next_ip
        monkeypatch.setattr(b,'insns',b.insns[:j]+[i]+b.insns[j+1:]);assert not plan()
    assert not plan()
