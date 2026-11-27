import pytest
from iced_x86 import Register as R

from dotnet_case import run_case
from il2cpp import Decompiler,Lifter
from il2cpp.emitter import Emitter
from il2cpp.packed_call import packed_calls
from test_game_shift_shared_flags import shift_runtime

pytestmark=pytest.mark.game


def test_rope_begin_passes_snapshot_pairs_then_clears_cut(shift_runtime,tmp_path):
    meta,il=shift_runtime;md=meta.methods[23994];lines=[];Emitter(il,str(tmp_path/'out')).emit_method(md,meta.typedefs[md.declaring],lines,'    ')
    src='''using System;using System.Collections.Generic;using UnityEngine;
float F(uint n)=>BitConverter.Int32BitsToSingle(unchecked((int)n));uint B(float f)=>unchecked((uint)BitConverter.SingleToInt32Bits(f));
var c=new RopeSweepCut();var ex=new ApplicationException();int calls=0;bool fail=true;
void Reset(){c.cutStartPosition=new Vector3{x=F(0x80000000),y=F(0x7fc01234),z=F(0x22222222)};c.cutEndPosition=new Vector3{x=F(1),y=F(0xffc54321),z=F(0x44444444)};}
Reset();c.Sink=(a,b)=>{calls++;if(!c.cut)throw new Exception("cleared before call");c.cutStartPosition=default;c.cutEndPosition=default;
 if(B(a.x)!=0x80000000||B(a.y)!=0x7fc01234||B(b.x)!=1||B(b.y)!=0xffc54321)throw new Exception("wrong lanes");if(fail)throw ex;};
c.Run();if(calls!=0)throw new Exception("false branch");c.cut=true;Exception fault=null;try{c.Run();}catch(Exception e){fault=e;}
if(!ReferenceEquals(fault,ex)||!c.cut||calls!=1)throw new Exception("wrong fault prefix",fault);Reset();fail=false;c.Run();c.Run();if(c.cut||calls!=2)throw new Exception("retry/clear");
Console.WriteLine("whole rope callback: exact XY bits, call order, clear and retry passed");
namespace Obi{public class ObiActor{}}namespace UnityEngine{public struct Vector3{public float x,y,z;}public struct Vector2{public float x,y;public Vector2()=>throw new Exception("constructor");}}
class RopeSweepCut{public Vector3 cutStartPosition,cutEndPosition;public bool cut;public Action<Vector2,Vector2> Sink;
 public void Run()=>Rope_OnBeginSimulation(null,3.75f,-88f);void ScreenSpaceCut(Vector2 a,Vector2 b)=>Sink(a,b);\n'''+ '\n'.join(lines)+'\n}'
    runner=tmp_path/'runner';runner.mkdir();(runner/'Program.cs').write_text(src,encoding='utf8');print(run_case(tmp_path,runner).strip())


@pytest.mark.parametrize('defect',['unknown lane','wrong register','lost context zero','wide overrun','different receiver','mixed target','caller sret'])
def test_packed_arguments_need_both_lane_origins(shift_runtime,monkeypatch,defect):
    meta,il=shift_runtime;d=Decompiler(Lifter(il));md=meta.methods[23994];td=meta.typedefs[md.declaring];d.lift_method(md,td);bs=d.L._blocks
    prove=lambda:packed_calls(d.L,md,td,bs,());assert prove()
    if defect=='caller sret':monkeypatch.setattr(md,'return_type',meta.methods[57011].return_type)
    elif defect=='mixed target':monkeypatch.setitem(il.addr_candidates,0x180523f90,[('method',23994),('method',23996)])
    else:
        ip={'unknown lane':0x180523f57,'wrong register':0x180523f70,'lost context zero':0x180523f6a,'wide overrun':0x180523f4f,'different receiver':0x180523f5b}[defect]
        b,k=next((b,k) for b in bs for k,i in enumerate(b.insns) if i.ip==ip);i=b.insns[k].copy()
        if defect=='unknown lane':i.immediate8=0xff
        if defect=='wrong register':i.op0_register=R.RDX
        if defect=='lost context zero':i.op1_register=R.EDX
        if defect=='wide overrun':i.memory_displacement+=8
        if defect=='different receiver':i.memory_base=R.RDI
        monkeypatch.setattr(b,'insns',b.insns[:k]+[i]+b.insns[k+1:])
    assert not prove()
