import pytest
from dotnet_case import run_case
from il2cpp.emitter import Emitter
from test_game_shift_shared_flags import shift_runtime

pytestmark=pytest.mark.game


def test_scheduled_delay_and_fx_clocks_use_the_parked_field(shift_runtime,tmp_path):
    meta,il=shift_runtime;em=Emitter(il,str(tmp_path/'out'));bodies=[]
    for mi in (24846,28572,28580):
        m=meta.methods[mi];lines=[];em.emit_method(m,meta.typedefs[m.declaring],lines,'    ');bodies.append('\n'.join(lines))
    src='''using System;using System.Linq;using System.Collections.Generic;using UnityEngine;
foreach(bool enabled in new[]{false,true})foreach(bool random in new[]{false,true})foreach(string mode in new[]{"ok","cancel","draw","invoke"}){
 var c=new Delete{turnOffAfterTime=enabled,time=2,randomTime=!random};var err=new ApplicationException();var trace=new List<string>();void Step(string x){trace.Add(x);if(mode==x)throw err;}
 c.Cancel=s=>{if(s!="TurnOff")throw new Exception();Step("cancel");c.time=4;c.randomTime=random;};UnityEngine.Random.Draw=(a,b)=>{if(a!=-.9f||b!=.9f)throw new Exception();Step("draw");c.time=90;return .25f;};
 c.Schedule=(s,delay)=>{if(s!="TurnOff"||delay!=(random?4.25f:4f))throw new Exception("wrong delay "+delay);Step("invoke");};Exception fault=null;try{c.Run();}catch(Exception e){fault=e;}
 string[] order=!enabled?Array.Empty<string>():random?new[]{"cancel","draw","invoke"}:new[]{"cancel","invoke"};int cut=Array.IndexOf(order,mode);if(!trace.SequenceEqual(cut<0?order:order.Take(cut+1))||(cut<0?fault!=null:!ReferenceEquals(fault,err)))throw new Exception(mode+":"+string.Join(',',trace),fault);
}
foreach(bool second in new[]{false,true})foreach(string mode in new[]{"key","less","equal","greater","unordered","poll fault","clock fault","change fault"}){
 var a=new ChangeFX();var b=new ChangeFX2();Action run=second?b.Run:a.Run;void TimeSet(float t,float w){if(second){b.time=t;b.waitTime=w;}else{a.time=t;a.waitTime=w;}}float Value()=>second?b.time:a.time;
 var trace=new List<string>();var err=new ApplicationException();void Step(string s){trace.Add(s);if(mode==s+" fault")throw err;}float n=mode=="greater"?5:mode is "equal" or "change fault"?4:mode=="unordered"?float.NaN:2;
 Input.Up=k=>{if(k!=KeyCode.Tab)throw new Exception();Step("poll");TimeSet(n,4);return mode=="key";};Time.Read=()=>{Step("clock");TimeSet(99,0);return .5f;};a.Change=b.Change=()=>Step("change");
 Exception fault=null;try{run();}catch(Exception e){fault=e;}string want=mode is "unordered" or "poll fault"?"poll":mode is "less" or "clock fault"?"poll,clock":"poll,change";
  if(string.Join(',',trace)!=want||(mode.EndsWith(" fault")?!ReferenceEquals(fault,err):fault!=null)||mode=="less"&&Value()!=2.5f||mode=="clock fault"&&Value()!=n)throw new Exception($"{second}/{mode}: {string.Join(',',trace)} {Value()}",fault);
}
Console.WriteLine("complete scheduling callback and two FX updates: post-cancel base, pre-poll addends, branch effects and exceptions");
namespace UnityEngine{public static class Random{public static Func<float,float,float> Draw;public static float Range(float lo,float hi)=>Draw(lo,hi);}public enum KeyCode{Tab=9}public static class Input{public static Func<KeyCode,bool> Up;public static bool GetKeyUp(KeyCode k)=>Up(k);}public static class Time{public static Func<float> Read;public static float deltaTime=>Read();}}
class Delete{public float time;public bool randomTime,turnOffAfterTime;public Action<string> Cancel;public Action<string,float> Schedule;public void CancelInvoke(string s)=>Cancel(s);public void Invoke(string s,float f)=>Schedule(s,f);public void Run()=>OnEnable();\n'''+bodies[0]+'\n}'+''.join('class '+name+'{public float time,waitTime;public Action Change;public void Run()=>Update();void DoChangeFX()=>Change();\n'+body+'\n}' for name,body in zip(('ChangeFX','ChangeFX2'),bodies[1:]))
    r=tmp_path/'r';r.mkdir();(r/'Program.cs').write_text(src,encoding='utf8');print(run_case(tmp_path,r))


@pytest.mark.parametrize('bad',['wrong scalar','different parked lane','not radius constant','unknown producer','packed observation','intervening call'])
def test_saved_float_operand_requires_the_native_source(shift_runtime,monkeypatch,bad):
    from il2cpp import Lifter,Decompiler
    from il2cpp.precall_addend import addend_sites
    from iced_x86 import Register as R
    meta,il=shift_runtime;m=meta.methods[24846];td=meta.typedefs[m.declaring];d=Decompiler(Lifter(il));d.lift_method(m,td);bs=d.L._blocks
    plan=lambda:addend_sites(d.L,m,td,bs,());a,c=plan();assert set(a)=={0x1806c0881} and set(c)=={0x1806c08a3}
    if bad=='unknown producer':monkeypatch.setitem(il.addr_candidates,0x182be3810,[])
    else:
        ip={'wrong scalar':0x1806c0881,'different parked lane':0x1806c08a8,'not radius constant':0x1806c089b,'packed observation':0x1806c08bb,'intervening call':0x1806c0893}[bad]
        b,j=next((b,j) for b in bs for j,i in enumerate(b.insns) if i.ip==ip);i=b.insns[j].copy()
        if bad=='wrong scalar':i.memory_displacement=0x28
        elif bad=='different parked lane':i.op1_register=R.XMM7
        elif bad=='not radius constant':
            from iced_x86 import Decoder
            i=Decoder(64,bytes.fromhex('f30f108300100000'),ip=ip).decode();assert i.len==b.insns[j].len
        elif bad=='intervening call':
            from iced_x86 import Decoder
            i=Decoder(64,b'\xe8'+(0x182bffcf0-ip-5).to_bytes(4,'little',signed=True),ip=ip).decode();assert i.len==b.insns[j].len
        else:
            from iced_x86 import Decoder
            i=Decoder(64,bytes.fromhex('0f15d0'),ip=ip).decode()  # UNPCKHPS observes the upper lanes
            assert i.len==b.insns[j].len
        monkeypatch.setattr(b,'insns',b.insns[:j]+[i]+b.insns[j+1:])
    assert plan()==({},{})
