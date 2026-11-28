import pytest
from dotnet_case import run_case
from il2cpp.emitter import Emitter
from test_game_shift_shared_flags import shift_runtime

pytestmark=pytest.mark.game


def test_purchase_hint_reloads_manager_after_each_callback(shift_runtime,tmp_path):
    meta,il=shift_runtime;m=meta.methods[25018];lines=[];Emitter(il,str(tmp_path/'out')).emit_method(m,meta.typedefs[m.declaring],lines,'    ')
    src='''using System;using System.Collections.Generic;using System.Linq;using UnityEngine;
foreach(string mode in new[]{"ok","no tooltip","show","first","null first","hint","second","null second","advance"}){
    var c=new EggDiffuser();var trace=new List<string>();var fault=new ApplicationException();int gets=0;
    void Step(string s){trace.Add(s);if(mode==s)throw fault;}
    StoreManager.Fetch=()=>throw new Exception("read before activation");var a=new StoreManager();var b=new StoreManager();
    c.purchaseTooltip=mode=="no tooltip"?null:new GameObject{Set=on=>{
        if(!on)throw new Exception();Step("show");StoreManager.Fetch=()=>{Step(++gets==1?"first":"replayed first");return mode=="null first"?null:a;};}};
    a.Hint=s=>{if(s!="Now purchase a trap from the wall.")throw new Exception();Step("hint");StoreManager.Fetch=()=>{Step("second");return mode=="null second"?null:b;};};
    a.Next=()=>throw new Exception("stale manager");b.Next=()=>Step("advance");Exception ex=null;try{c.Run();}catch(Exception e){ex=e;}
    string[] all={"show","first","hint","second","advance"};int count=mode switch{"ok"=>5,"no tooltip"=>0,"null first"=>2,"null second"=>4,_=>Array.IndexOf(all,mode)+1};
    if(!trace.SequenceEqual(all.Take(count))||(mode=="ok"?ex!=null:mode.StartsWith("null")||mode=="no tooltip"?ex is not NullReferenceException:!ReferenceEquals(ex,fault)))throw new Exception(mode+":"+string.Join(',',trace),ex);
}
Console.WriteLine("purchase hint uses two independently acquired managers and stops at each fault");
namespace UnityEngine{public class GameObject{public Action<bool> Set;public void SetActive(bool on)=>Set(on);}}
public class StoreManager{public static Func<StoreManager> Fetch;public static StoreManager Instance=>Fetch();public Action<string> Hint;public Action Next;public void AddHint(string s)=>Hint(s);public void NextHint()=>Next();}
class EggDiffuser{public GameObject purchaseTooltip;public void Run()=>PurchaseHint();\n'''+ '\n'.join(lines)+'\n}'
    runner=tmp_path/'r';runner.mkdir();(runner/'Program.cs').write_text(src,encoding='utf8');print(run_case(tmp_path,runner))


def test_car_and_id_hint_callbacks_deliver_to_replacement(shift_runtime,tmp_path):
    meta,il=shift_runtime;em=Emitter(il,str(tmp_path/'out'));types={}
    for mi in (24348,25554,25555):
        m=meta.methods[mi];td=meta.typedefs[m.declaring];em.emit_method(m,td,types.setdefault(td.name,[]),'    ')
    src='''using System;using System.Linq;using System.Collections.Generic;
var car=new Car();var id=new IDCard();var cases=new (Action run,string text)[]{(car.Run,"New topic unlocked. You can now ask the driver about this."),(id.Check,"Now check the computer."),(id.Pay,"Pay attention to info you are given at the start of the day.")};
foreach(var (run,text) in cases)foreach(var mode in new[]{"normal","first","null first","add","second","null second","next"}){
 var a=new StoreManager();var b=new StoreManager();var trace=new List<string>();var ex=new ApplicationException();
 void Step(string s){trace.Add(s);if(s==mode)throw ex;}
 StoreManager.Get=()=>{Step("first");return mode=="null first"?null:a;};a.Add=value=>{if(value!=text)throw new Exception("wrong title");Step("add");StoreManager.Get=()=>{Step("second");return mode=="null second"?null:b;};};b.Next=()=>Step("next");
 Exception fault=null;try{run();}catch(Exception e){fault=e;}string[] order={"first","add","second","next"};int n=mode switch{"normal"=>4,"null first"=>1,"null second"=>3,_=>Array.IndexOf(order,mode)+1};
 if(!trace.SequenceEqual(order.Take(n))||(mode=="normal"?fault!=null:mode.StartsWith("null")?fault is not NullReferenceException:!ReferenceEquals(fault,ex)))throw new Exception(mode+":"+string.Join(',',trace),fault);
}
Console.WriteLine("three complete hint callbacks: messages, two independent reads and exceptions");
class StoreManager{public static Func<StoreManager> Get;public static StoreManager Instance=>Get();public Action<string> Add;public Action Next;public void AddHint(string s)=>Add(s);public void NextHint()=>Next();}
class Car{public void Run()=>NewQuestioningTopicHint();\n'''+ '\n'.join(types['Car'])+'\n}class IDCard{public void Check()=>CheckComputerHint();public void Pay()=>PayAttentionHint();\n'+'\n'.join(types['IDCard'])+'\n}'
    runner=tmp_path/'r';runner.mkdir();(runner/'Program.cs').write_text(src,encoding='utf8');print(run_case(tmp_path,runner))


@pytest.mark.parametrize('change',['second flag byte','second slot','overlap from below','alternate middle entry','getter touches string flag'])
def test_incomplete_peer_vetoes_repeated_guard(shift_runtime,monkeypatch,change):
    from il2cpp import Decompiler,Lifter
    from il2cpp.inline_static_guard import checked_statics
    meta,il=shift_runtime;m=meta.methods[25018];d=Decompiler(Lifter(il));d.lift_method(m,meta.typedefs[m.declaring]);bs=d.L._blocks
    plan=lambda:checked_statics(d.L,m,bs,());assert set(plan())=={0x1806ca539,0x1806ca57a}
    if change=='getter touches string flag':
        from il2cpp.static_getter import _SHAPE
        getter=0x1805e2d40;flag=0x183e88cfd;read=il.bin.read;raw=bytearray(read(getter,54));match=_SHAPE.fullmatch(raw);assert match
        for group in (1,4):
            lo,hi=match.span(group);raw[lo:hi]=(flag-(getter+hi+1)).to_bytes(4,'little',signed=True)
        monkeypatch.setattr(il.bin,'read',lambda p,n:bytes(raw[p-getter:p-getter+n]) if getter<=p<=getter+len(raw)-n else read(p,n))
        assert not plan();return
    ip={'second flag byte':0x1806ca565,'second slot':0x1806ca559,'overlap from below':0x1806ca541,'alternate middle entry':0x1806ca557}[change]
    b,j=next((b,j) for b in bs for j,i in enumerate(b.insns) if i.ip==ip);i=b.insns[j].copy()
    if change=='alternate middle entry':i.near_branch64=0x1806ca573
    elif change=='overlap from below':i.memory_displacement=0x183e87fe1-4
    else:i.memory_displacement+=8
    monkeypatch.setattr(b,'insns',b.insns[:j]+[i]+b.insns[j+1:]);assert not plan()
