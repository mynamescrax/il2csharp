import pytest
from dotnet_case import run_case
from il2cpp.emitter import Emitter
from test_game_shift_shared_flags import shift_runtime

pytestmark=pytest.mark.game


def test_unordered_delay_stores_both_fields_and_skips_the_light(shift_runtime,tmp_path):
    meta,il=shift_runtime;md=meta.methods[23834];lines=[];Emitter(il,str(tmp_path/'out')).emit_method(md,meta.typedefs[md.declaring],lines,'    ')
    prog='''using System;using System.Linq;using System.Collections.Generic;using UnityEngine;
float F(uint b)=>BitConverter.Int32BitsToSingle(unchecked((int)b));int Bits(float f)=>BitConverter.SingleToInt32Bits(f);
foreach(float v in new[]{F(0xffc01234),F(0x7fc06789),F(0x80000000),0f,F(1),-1f,float.NegativeInfinity,float.PositiveInfinity})foreach(string mode in new[]{"ok","lookup","null","set"}){
 var e=new CFX_LightIntensityFade{delay=v,p_lifetime=12f,p_delay=37f};var trace=new List<string>();var err=new ApplicationException();var light=new Light();
 void Step(string s){trace.Add(s);if(mode==s)throw err;}e.Lookup=t=>{if(t!=typeof(Light)||Bits(e.p_delay)!=Bits(v)||Bits(e.p_lifetime)!=0)throw new Exception("bad state at lookup");Step("lookup");e.delay=-8;return mode=="null"?null:light;};
 light.Enabled=x=>{if(x)throw new Exception();Step("set");};Exception fault=null;try{e.Run();}catch(Exception ex){fault=ex;}
 string want=v>0f?(mode is "lookup" or "null"?"lookup":"lookup,set"):"";
 if(string.Join(',',trace)!=want||Bits(e.p_delay)!=Bits(v)||Bits(e.p_lifetime)!=0||(!(v>0f)||mode=="ok"?fault!=null:mode=="null"?fault is not NullReferenceException:!ReferenceEquals(fault,err)))throw new Exception($"{Bits(v):x}/{mode}/{string.Join(',',trace)}",fault);
}
Console.WriteLine("complete light activation: unordered and signed-zero delay, bitwise stores before lookup, fault cutoffs");
namespace UnityEngine{public class Component{public Func<Type,Component> Lookup;public T GetComponent<T>() where T:Component=>(T)Lookup(typeof(T));}public class Light:Component{public Action<bool> Enabled;public bool enabled{set=>Enabled(value);}}}
class CFX_LightIntensityFade:Component{public float p_delay,p_lifetime,delay;public void Run()=>OnEnable();\n'''+ '\n'.join(lines)+'\n}'
    r=tmp_path/'r';r.mkdir();(r/'Program.cs').write_text(prog,encoding='utf8');print(run_case(tmp_path,r))


@pytest.mark.parametrize('bad',['flag writer','different base','other compared reg','signed branch','skip into gap'])
def test_flag_preserving_transfer_window_is_checked(shift_runtime,monkeypatch,bad):
    from iced_x86 import Register as R,Decoder
    from il2cpp import Decompiler,Lifter
    from il2cpp.saved_float_flags import comparison_sites
    meta,il=shift_runtime;m=meta.methods[23834];td=meta.typedefs[m.declaring];d=Decompiler(Lifter(il));d.lift_method(m,td);bs=d.L._blocks
    proof=lambda:comparison_sites(d.L,m,td,bs,());cmp=0x18051535d;assert cmp in proof()
    ip={'flag writer':0x180515360,'different base':0x18051536a,'other compared reg':cmp,'signed branch':0x18051536d,'skip into gap':0x180515340}[bad]
    b,j=next((b,j) for b in bs for j,i in enumerate(b.insns) if i.ip==ip);i=b.insns[j].copy()
    if bad=='flag writer':i=Decoder(64,bytes.fromhex('0b4324'),ip=ip).decode()
    elif bad=='different base':i.memory_base=R.RSI
    elif bad=='other compared reg':i.op0_register=R.XMM2
    elif bad=='signed branch':i=Decoder(64,bytes.fromhex('7e26'),ip=ip).decode()
    else:i.near_branch64=0x180515363
    assert i.len==b.insns[j].len;monkeypatch.setattr(b,'insns',b.insns[:j]+[i]+b.insns[j+1:]);assert cmp not in proof()
