"""Compare full emitted light callbacks against native evaluation order."""
import re

import pytest
from iced_x86 import Decoder
from dotnet_case import run_case
from il2cpp import Lifter,Decompiler
from il2cpp.emitter import Emitter
from il2cpp.scalar_snapshot import scalar_sites
from test_game_shift_shared_flags import shift_runtime

pytestmark=pytest.mark.game


def test_light_fade_reads_and_writes_at_native_sites(shift_runtime,tmp_path):
    meta,il=shift_runtime;m=meta.methods[28632];td=meta.typedefs[m.declaring];out=tmp_path/'out'
    em=Emitter(il,str(out));em._emit_one_top(td,meta.images[m.image],td.name);s=next(out.rglob('RealFireLightFade.cs')).read_text('utf8')
    methods=[re.search(r'^( +)private void '+name+r'\(\)\n\1\{.*?^\1}',s,re.S|re.M)[0] for name in ('Start','Update')]
    conv=meta.methods[56599];sig=em.method_sig(conv,meta.typedefs[conv.declaring]);assert 'implicit operator bool(' in sig
    param=re.search(r' (\w+)\)$',sig)[1]
    program='''using System;using System.Linq;using System.Collections.Generic;using UnityEngine;using Object=UnityEngine.Object;
foreach(bool start in new[]{true,false}){
    string[] normal=start?new[]{"go1","lookup1","bool","go2","lookup2","new.get"}:new[]{"go1","lookup1","bool","old.get","time","old.set","fresh.get","go2","destroy"};
    foreach(string stop in normal.Concat(new[]{"none","false","null","keep","NaN"})){
        var trace=new List<string>();var error=new ApplicationException(stop);void Step(string s){trace.Add(s);if(s==stop)throw error;}
        var f=new Fade{initIntensity=4,life=3};var guard=new Light();var orig=new Light();var fresh=new Light();var other=new Light();var selected=new Light();
        f.li=orig;int lookups=0,gos=0;var go1=new GameObject();var go2=new GameObject();
        f.GO=()=>{Step("go"+(++gos));return gos==1?go1:go2;};
        go1.Lookup=()=>{Step("lookup"+(++lookups));return stop=="null"?null:guard;};go2.Lookup=()=>{Step("lookup"+(++lookups));return selected;};
        Object.Truth=o=>{if(!ReferenceEquals(o,stop=="null"?null:guard))throw new Exception("wrong guard");Step("bool");return stop!="false"&&stop!="null";};
        selected.Read=()=>{if(!ReferenceEquals(f.li,selected))throw new Exception("getter before field store");Step("new.get");return 17;};
        orig.Read=()=>{Step("old.get");f.li=other;f.initIntensity=6;return 12;};
        Time.Sample=()=>{Step("time");f.initIntensity=90;f.life=4;return 2;};
        orig.Write=x=>{if(x!=9)throw new Exception("wrong field/time snapshots: "+x);Step("old.set");f.li=fresh;f.killAfterLife=stop!="keep";};
        fresh.Read=()=>{Step("fresh.get");return stop=="NaN"?float.NaN:0;};Object.Drop=o=>{if(!ReferenceEquals(o,go2))throw new Exception("stale destruction target");Step("destroy");};
        var want=normal;
        if(stop=="false"||stop=="null")want=normal.Take(3).ToArray();
        else if(!start&&stop=="keep")want=normal.Take(6).ToArray();else if(!start&&stop=="NaN")want=normal.Take(7).ToArray();
        var n=Array.IndexOf(normal,stop);if(n>=0)want=normal.Take(n+1).ToArray();
        try{f.Run(start);if(n>=0)throw new Exception("missing fault");}catch(ApplicationException e) when(ReferenceEquals(e,error)){}
        if(!trace.SequenceEqual(want))throw new Exception(stop+": got "+string.Join(",",trace)+"; expected "+string.Join(",",want));
        if(start){bool stored=trace.Contains("new.get");if(!ReferenceEquals(f.li,stored?selected:orig)||f.initIntensity!=(stored&&stop!="new.get"?17:4))throw new Exception("exception/store order");}
        if(stop=="none")Console.WriteLine((start?"Start: ":"Update: ")+string.Join(",",trace));
    }
}
namespace UnityEngine {
class Object{public static Func<Object,bool> Truth;'''+sig+'=>Truth('+param+''');public static Action<Object> Drop;public static void Destroy(Object x)=>Drop(x);}
class GameObject:Object{public Func<Light> Lookup;public T GetComponent<T>() where T:Object => Lookup() as T;}
class Light:Object{public Func<float> Read;public Action<float> Write;public float intensity{get=>Read();set=>Write(value);}}
class Time{public static Func<float> Sample;public static float deltaTime=>Sample();}}
class Fade{public float life,initIntensity;public bool killAfterLife;public Light li;public Func<GameObject> GO;public GameObject gameObject=>GO();public void Run(bool start){if(start)Start();else Update();}
'''+ '\n'.join(methods)+'\n}'
    runner=tmp_path/'runner';runner.mkdir();(runner/'Program.cs').write_text(program,encoding='utf8');print(run_case(tmp_path,runner).strip())


@pytest.mark.parametrize('address,code',[(0x1806303ba,'488bce'),(0x180630372,'4887cb')])
def test_light_capture_rejects_unproved_receiver(shift_runtime,monkeypatch,address,code):
    from il2cpp.closed_lookup import closed_lookup_sites
    meta,il=shift_runtime;md=meta.methods[28633];td=meta.typedefs[md.declaring];d=Decompiler(Lifter(il));d.lift_method(md,td);bs=d.L._blocks
    b,j=next((b,j) for b in bs for j,i in enumerate(b.insns) if i.ip==address);i=b.insns[j]
    # Change the setter receiver, or replace MOV RCX,RDI before the truth
    # conversion with XCHG RCX,RBX (the saved lookup no longer feeds it).
    alt=list(Decoder(64,bytes.fromhex(code),ip=i.ip));assert len(alt)==1 and alt[0].len==i.len
    monkeypatch.setattr(b,'insns',b.insns[:j]+alt+b.insns[j+1:])
    if address==0x180630372:
        conversions={};closed_lookup_sites(d.L,md,bs,(),conversions=conversions);assert 0x180630375 not in conversions
    else:assert 0x18063039e not in scalar_sites(d.L,md,td,bs,())[1]
