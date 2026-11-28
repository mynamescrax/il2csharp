import pytest
from dotnet_case import run_case
from il2cpp.emitter import Emitter
from test_game_shift_shared_flags import shift_runtime

pytestmark=pytest.mark.game


def test_complete_color_initializers_store_one_four_lane_result(shift_runtime,tmp_path):
    meta,il=shift_runtime;em=Emitter(il,str(tmp_path/'out'));shells=[];config=[]
    for mi,field,extra in ((23837,'color','public float orgAlpha;'),(23889,'original','public Renderer rend;'),
                           (24029,'normalColor','public Material instance;'),(28635,'originalColor','')):
        m=meta.methods[mi];td=meta.typedefs[m.declaring];lines=[];em.emit_method(m,td,lines,'    ')
        shells.append('class '+td.name+' : Component {public Color '+field+';'+extra+'public void Run()=>'+m.name+'();\n'+'\n'.join(lines)+'\n}')
        side='c.orgAlpha' if mi==23837 else '0f';other= 'c.rend' if mi==23889 else 'c.instance' if mi==24029 else 'null'
        config.append('case '+str(mi)+':{var c=new '+td.name+'(); owner=c;run=c.Run; get=()=>c.'+field+';c.'+field+'=seed; prev=()=>'+other+';alpha=()=>'+side+';break;}')
    src='''using System;using System.Linq;using System.Collections.Generic;using UnityEngine;
float F(uint b)=>BitConverter.Int32BitsToSingle(unchecked((int)b));
bool Same(Color a,Color b)=>new[]{a.r,a.g,a.b,a.a}.Select(BitConverter.SingleToInt32Bits).SequenceEqual(new[]{b.r,b.g,b.b,b.a}.Select(BitConverter.SingleToInt32Bits));
var seed=new Color {r=1,g=2,b=3,a=4};var inner=new Color{r=-1,g=4,b=F(1),a=F(0x7fc01234)};var outer=new Color{r=F(0x80000000),g=F(0xffc00567),b=F(2),a=-3.25f};
foreach(int mi in new[]{23837,23889,24029,28635})foreach(string mode in new[]{"ok","null component","null material","lookup","material","read","reenter","outer fault"}){
 if(mi==28635 && mode is "null material" or "material")continue;
 Component owner;Func<Color> get;Func<object> prev;Func<float> alpha;Action run;switch(mi){'''+''.join(config)+'''default:throw new Exception();}
 var trace=new List<string>();var err=new ApplicationException();var mat=new Material();var rend=new Renderer();var light=new Light();bool nested=false;
 void Step(string s){trace.Add(s);if(mode==s)throw err;}
 owner.Lookup=t=>{Step("lookup");if(t!=(mi==28635?typeof(Light):typeof(Renderer)))throw new Exception("wrong component");return mode=="null component"?null:mi==28635?(Component)light:rend;};
 rend.Mat=()=>{Step("material");if(mi==23889&&!ReferenceEquals(prev(),rend))throw new Exception("early color/late renderer");return mode=="null material"?null:mat;};
 Color Read(string key){Step("read");if(key!=(mi==23837?"_TintColor":null))throw new Exception("wrong key");if(mi==24029&&!ReferenceEquals(prev(),mat))throw new Exception("material store too late");
   if(nested)return inner;if(mode is "reenter" or "outer fault"){nested=true;run();nested=false;if(!Same(get(),inner))throw new Exception("missing inner field store");if(mode=="outer fault")throw err;}return outer;}
 mat.Read=Read;light.Get=()=>Read(null);Exception fault=null;try{run();}catch(Exception e){fault=e;}
 string[] path=mi==28635?new[]{"lookup","read"}:new[]{"lookup","material","read"};int last=mode switch{"null component" or "lookup"=>1,"null material" or "material"=>2,_=>path.Length};
 var expected=mode is "reenter" or "outer fault"?path.Concat(path):path.Take(last);bool ok=mode is "ok" or "reenter";Color final=ok?outer:mode=="outer fault"?inner:seed;
 if (!trace.SequenceEqual(expected)||!Same(get(),final)||(ok?fault!=null:mode.StartsWith("null")?fault is not NullReferenceException:!ReferenceEquals(fault,err)))throw new Exception($"{mi}/{mode}: {string.Join(',',trace)}",fault);
 if(mi==23837 && BitConverter.SingleToInt32Bits(alpha())!=BitConverter.SingleToInt32Bits(ok?outer.a:mode=="outer fault"?inner.a:0f))throw new Exception("wrong alpha reload");
}
Console.WriteLine("four complete color captures: all bits, earlier reference stores, nested calls, faults and alpha");
namespace UnityEngine{public struct Color{public float r,g,b,a;} public class Component{public Func<Type,Component> Lookup;public T GetComponent<T>() where T:Component=>(T)Lookup(typeof(T));}
public class Renderer:Component{public Func<Material> Mat;public Material material=>Mat();}public class Light:Component{public Func<Color> Get;public Color color=>Get();}public class Material{public Func<string,Color> Read;public Color color=>Read(null);public Color GetColor(string key)=>Read(key);}}
'''+ '\n'.join(shells)
    r=tmp_path/'r';r.mkdir();(r/'Program.cs').write_text(src,encoding='utf8');print(run_case(tmp_path,r))


@pytest.mark.parametrize('change',['partial store','wrong echo','different lane register','overlapping field','alternate caller'])
def test_full_copy_requires_echo_width_and_exact_destination(shift_runtime,monkeypatch,change):
    from iced_x86 import Decoder,Register as R
    from il2cpp import Decompiler,Lifter
    from il2cpp.echo_field import echo_stores
    meta,il=shift_runtime;m=meta.methods[28635];td=meta.typedefs[m.declaring];d=Decompiler(Lifter(il));d.lift_method(m,td);bs=d.L._blocks
    plan=lambda:echo_stores(d.L,m,td,bs,())
    ip=0x18063067c;assert ip in plan()
    if change=='alternate caller':
        va=0x182bb7c50;monkeypatch.setitem(il.addr_candidates,va,[*il.addr_candidates[va],('method',54740)])
    else:
        target=0x180630679 if change=='wrong echo' else ip
        b,j=next((b,j) for b in bs for j,i in enumerate(b.insns) if i.ip==target);i=b.insns[j].copy()
        if change=='partial store':
            i=Decoder(64,b'\x0f\x13\x43\x38',ip=ip).decode();assert i.len==b.insns[j].len
        elif change=='wrong echo':i.memory_base=R.RCX
        elif change=='different lane register':i.op1_register=R.XMM1
        else:i.memory_displacement+=4
        monkeypatch.setattr(b,'insns',b.insns[:j]+[i]+b.insns[j+1:])
    assert ip not in plan()
