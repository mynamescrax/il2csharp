"""Compile the emitted method with a mutable unboxed receiver and virtual RNG."""
import re

import pytest
from iced_x86 import Decoder

from dotnet_case import run_case
from il2cpp import Decompiler,Lifter
from il2cpp.affine_return import affine_return
from il2cpp.emitter import Emitter
from test_game_shift_shared_flags import shift_runtime

pytestmark=pytest.mark.game


def test_range_return_has_one_draw_and_two_field_lifetimes(shift_runtime,tmp_path):
    meta,il=shift_runtime;method=meta.methods[29435];td=meta.typedefs[method.declaring];out=tmp_path/'out';em=Emitter(il,str(out))
    em._emit_one_top(td,meta.images[method.image],td.name);text=next(out.rglob('MinMax.cs')).read_text(encoding='utf8')
    body=re.search(r'^( +)public int GetRandom\(\)\n\1\{.*?^\1}',text,re.M|re.S)[0]
    runner=tmp_path/'runner';runner.mkdir();(runner/'Program.cs').write_text('''using System;
using System.Collections.Generic;
using System.Linq;
using FIMSpace.Generating;
using System.Runtime.CompilerServices;
var box=new Box();Hooks.Box=box;
void Check(int lo,int hi,double sample,int want,bool mutate=false){
    bool first=Hooks.Inits==0;Hooks.Trace.Clear();box.Value=new MinMax{Min=lo,Max=hi};
    var source=new Draw(()=>{Hooks.Trace.Add("draw");if(mutate){box.Value.Min=-4;box.Value.Max=11;}return sample;});Hooks.Source=source;
    int got=box.Value.GetRandom();
    if(got!=want||!Hooks.Trace.SequenceEqual(first?new[]{"init","get","draw"}:new[]{"get","draw"}))throw new Exception($"bad sample {got}/{want}: {string.Join(',',Hooks.Trace)}");
}
Check(5,20,0.5,13,true); // cctor AND draw mutate Min; final add uses the original 5
Check(0,9,0.125,1);Check(0,0,1.0-Math.Pow(2,-26),1); // CVTSD2SS before the multiply
Check(int.MinValue,int.MaxValue,0.5,int.MinValue); // wrapped int span = 0
Check(0,0,2147483648.0,int.MinValue);Check(0,0,double.NaN,int.MinValue);Check(0,0,double.NegativeInfinity,int.MinValue);
Check(-3,7,0.125,-1); // truncate toward zero
Hooks.Source=null;Hooks.Trace.Clear();try{box.Value.GetRandom();throw new Exception("lost null");}catch(NullReferenceException){}
if(!Hooks.Trace.SequenceEqual(new[]{"get"}))throw new Exception("read after null");
var e=new ApplicationException();Hooks.Source=new Draw(()=>{Hooks.Trace.Add("draw");throw e;});Hooks.Trace.Clear();
try{box.Value.GetRandom();throw new Exception("lost fault");}catch(ApplicationException caught)when(ReferenceEquals(e,caught)){}
if(!Hooks.Trace.SequenceEqual(new[]{"get","draw"}))throw new Exception("replayed after fault");
Console.WriteLine("one virtual draw; pre-init minimum, post-draw bounds, float rounding, integer wrap, NaN/overflow, null and fault passed");
class Box{public MinMax Value;}
static class Hooks{public static Box Box;public static Random Source;public static int Inits;public static List<string> Trace=new();}
class Draw(Func<double> f):Random{public override double NextDouble()=>f();}
namespace FIMSpace.Generating {static class FGenerators {
    static FGenerators(){Hooks.Inits++;Hooks.Trace.Add("init");Hooks.Box.Value.Min=100;}
    public static Random GlobalRandomInstance {get{Hooks.Trace.Add("get");return Hooks.Source;}}
}struct MinMax {public int Min,Max;\n'''+body+'\n}}',encoding='utf8');print(run_case(tmp_path,runner).strip())


@pytest.mark.parametrize('change',['wrong info','rounding instead of truncation','overwritten basis','wrong class guard','getter ambiguity','interface receiver','wrong unwind'])
def test_unproven_sample_does_not_fold(shift_runtime,monkeypatch,change):
    meta,il=shift_runtime;d=Decompiler(Lifter(il));m=meta.methods[29435];td=meta.typedefs[m.declaring];d.lift_method(m,td)
    seq=[i for b in d.L._blocks for i in b.insns];prove=lambda:affine_return(d.L,m,td,seq,d.eh)
    assert prove()
    if change=='wrong unwind':
        from il2cpp.equivalent_binary import _extent
        addr=il.bin.image_base+_extent(il,m.addr)[1];read=il.bin.read
        def altered(va,n):
            data=read(va,n)
            if va==addr and n>4:
                raw=bytearray(data);raw[-1]^=0x10;return bytes(raw)
            return data
        monkeypatch.setattr(il.bin,'read',altered)
    elif change=='interface receiver':
        r=il.types[meta.methods[29353].return_type][0];owner=meta.typedefs[r];monkeypatch.setattr(owner,'flags',owner.flags|0x20)
    elif change=='getter ambiguity':
        getter=meta.methods[29353];owner=meta.typedefs[getter.declaring];methods=il.meta.type_methods
        monkeypatch.setattr(il.meta,'type_methods',lambda t:list(methods(t))+([getter.index] if t.index==owner.index else []))
    else:
        at,pos,xorv={'wrong info':(0x18066ea01,-4,8),'rounding instead of truncation':(0x18066ea30,2,1),
                     'overwritten basis':(0x18066e9a0,-2,0x38),'wrong class guard':(0x18066e9da,-1,1)}[change]
        j=next(j for j,i in enumerate(seq) if i.ip==at);i=seq[j];raw=bytearray(il.bin.read(at,i.len))
        raw[pos]^=xorv
        alt=list(Decoder(64,bytes(raw),ip=at));assert len(alt)==1 and alt[0].len==i.len;seq[j]=alt[0]
    assert prove() is None
