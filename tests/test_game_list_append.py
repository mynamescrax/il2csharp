"""Compile the recovered append sites and exercise ordered, conditional list growth."""
import re
import pytest

from dotnet_case import run_case
from il2cpp import Decompiler, Lifter
from test_game_shift_shared_flags import body, shift_runtime

pytestmark=pytest.mark.game


def test_goal_appends_use_original_receiver_and_one_version_bump(body,tmp_path):
    method=body('RegularBrowsingNPC','OnEnable',0x1805987a0)
    assert method.count('.Add(')==2 and not any(s in method for s in ('._version','._size','._items','sub_'))
    runner=tmp_path/'runner';runner.mkdir()
    (runner/'Program.cs').write_text('''using System;
using System.Collections.Generic;
using System.Linq;
using System.Reflection;
using UnityEngine;
var version=typeof(List<int>).GetField("_version",BindingFlags.NonPublic|BindingFlags.Instance);
foreach(int initialCapacity in new[]{1,2,4}) foreach(bool replace in new[]{false,true}) {
    var log=new List<string>(); var original=new List<int>(initialCapacity){-7}; var replacement=new List<int>(4){90};
    var c=new Case {generatedGoals=original,Flags=31,Log=log};
    Fusion.InternalLogStreams.LogTraceObject=new Fusion.TraceLogStream(log);
    int start=(int)version.GetValue(original),other=(int)version.GetValue(replacement),n=0;
    UnityEngine.Random.Next=(lo,hi)=>{ if(lo!=2||hi!=14)throw new Exception("range");
        log.Add("arg"+(++n)); if(n==1 && replace)c.generatedGoals=replacement;
        if(n==2 && !original.SequenceEqual(new[]{-7,3}))throw new Exception("late first append");return n==1?3:11;};
    c.Run();
    if(c.Flags!=15 || string.Join(";",log)!="log;invoke;arg1;arg2" ||
        !original.SequenceEqual(replace?new[]{-7,3}:new[]{-7,3,11}) || !replacement.SequenceEqual(replace?new[]{90,11}:new[]{90}) ||
        (int)version.GetValue(original)!=start+(replace?1:2) || (int)version.GetValue(replacement)!=other+(replace?1:0))throw new Exception("list identity/version");
    if(initialCapacity==1 && original.Capacity<=1 || initialCapacity==4 && original.Capacity!=4)throw new Exception("capacity path");
}
foreach(bool failSecond in new[]{false,true}) {
    var c=new Case{generatedGoals=new(),Log=new()};var saved=c.generatedGoals;int n=0;
    UnityEngine.Random.Next=(_,_)=>{if(++n==(failSecond?2:1))throw new ApplicationException();return 4;};
    try {c.Run();throw new Exception("missing throw");}catch(ApplicationException){}
    if(!saved.SequenceEqual(failSecond?new[]{4}:Array.Empty<int>()) || (int)version.GetValue(saved)!=saved.Count)throw new Exception("write on argument failure");
}
var absent=new Case{Log=new()};int calls=0;UnityEngine.Random.Next=(_,_)=>{calls++;absent.generatedGoals=new();return 5;};
try { absent.Run();throw new Exception("missing null check"); }catch(NullReferenceException){}
if(calls!=1 || absent.generatedGoals.Count!=0)throw new Exception("null check moved before argument");
Console.WriteLine("spare capacity, grow on first/second add, replacement, argument throws, null list: contents and versions OK");
class Case {public int Flags; public List<int> generatedGoals; public List<string> Log;
    void Invoke(string name,float delay){if(name!="DelayedStart" || delay!=0.1f || (Flags&16)!=0)throw new Exception("prefix"); Log.Add("invoke");}
    public void Run(){\n'''+method+'''\n}}
namespace UnityEngine { class Random {public static Func<int,int,int> Next; public static int Range(int lo,int hi)=>Next(lo,hi);} }
namespace Fusion {
    class TraceLogStream {readonly List<string> trace; public TraceLogStream(List<string> t)=>trace=t;public TraceLogStream InfoStream=>this;
        public void Log(Case c, string name){if(name!="OnEnable")throw new Exception();trace.Add("log");} }
    class InternalLogStreams {public static TraceLogStream LogTraceObject;}
}''',encoding='utf-8')
    print(run_case(tmp_path,runner).strip())


@pytest.mark.parametrize('defect',['signed capacity','wrong item','other RGCTX slot','wrong terminal helper','different canonical Add'])
def test_append_diamonds_reject_other_effects(shift_runtime,monkeypatch,defect):
    from iced_x86 import Decoder
    from il2cpp import list_append
    from il2cpp.dec import build

    meta,il=shift_runtime;d=Decompiler(Lifter(il));m=meta.methods[27016];td=meta.typedefs[m.declaring]
    fold=list_append.fold_terminal_appends
    monkeypatch.setattr(build,'fold_terminal_appends',lambda *args:None)
    d.lift_method(m,td);blocks=d.L._blocks
    if defect=='different canonical Add':
        read=il.bin.read
        def changed(p,n):
            data=read(p,n)
            if p==0x180e0a540 and n==85:
                assert data[24]==0x72
                return data[:24]+b'\x7c'+data[25:]
            return data
        monkeypatch.setattr(il.bin,'read',changed)
    else:
        # Damage the terminal site, so neither a standalone terminal fold nor
        # a composition of the two can hide the changed native operation.
        ip,before,after={
            'signed capacity':(0x18059892e,'72','7c'),
            'wrong item':(0x180598964,'44','40'),
            'other RGCTX slot':(0x180598941,'70','68'),
            'wrong terminal helper':(0x18059894f,None,None),
        }[defect]
        dest=next(b for b in blocks if any(i.ip==ip for i in b.insns));j=next(j for j,i in enumerate(dest.insns) if i.ip==ip)
        ins=dest.insns[j]; raw=il.bin.read(ip,ins.len)
        if before is None: raw=raw[:1]+(ins.near_branch_target+16-ins.next_ip).to_bytes(4,'little',signed=True)
        else:
            needle=bytes.fromhex(before); assert raw.count(needle)==1; raw=raw.replace(needle,bytes.fromhex(after))
        monkeypatch.setattr(dest,'insns',dest.insns[:j]+list(Decoder(64,raw,ip=ip))+dest.insns[j+1:])
    old=[(list(bl.stmts),bl.term,list(bl.succs),list(bl.preds)) for bl in blocks]
    fold(d.L,m,td,blocks,d._pad_bids)
    assert old==[(bl.stmts,bl.term,bl.succs,bl.preds) for bl in blocks]


def test_nuisance_animation_then_append(body,tmp_path):
    method=body('NuisanceCustomer','SelectNuisanceType',0x18051fe80)
    assert 'sub_180e09d60' not in method
    # Compile the complete shared switch tail, starting at the original
    # animation lookup. Keep the generated local bindings unchanged.
    tail=re.search(r'NuisanceCustomerManager (\w+) = NuisanceCustomerManager.Instance;\s*'
                   r'string\[\] (\w+) = \1\.nuisanceAnimations;\s*string (\w+) = \2\[this.nuisanceType\];\s*'
                   r'this.curNuisanceAnimation = \3;\s*NuisanceCustomerManager (\w+) = NuisanceCustomerManager.Instance;\s*'
                   r'System.Collections.Generic.List_1<int> (\w+) = \4\.nuisancesAlreadyBeingDone;\s*\5\.Add\(this.nuisanceType\);\s*return;',method)
    assert tail
    runner=tmp_path/'runner';runner.mkdir()
    (runner/'Program.cs').write_text('''using System;
using System.Collections.Generic;
using System.Linq;
using System.Reflection;
var version=typeof(List<int>).GetField("_version",BindingFlags.Instance|BindingFlags.NonPublic);
foreach(string mode in new[]{"spare","grow","null list","null manager","bad animation","item throws"}) {
    var old=new NuisanceCustomerManager {nuisanceAnimations=new[]{"zero","selected"}};
    var current=new NuisanceCustomerManager(); var untouched=new List_1<int>(0); var sink=new List_1<int>(mode=="grow"?1:4){9};
    int initial=(int)version.GetValue(sink),reads=0; var log=new List<string>();
    old.ReadList=()=>throw new Exception("used stale manager");
    current.ReadList=()=>{log.Add("list");return mode=="null list"?null:sink;};
    var manager=old; NuisanceCustomerManager.Read=()=>{log.Add("manager");return manager;};
    var c=new Case();c.Type=()=>{
        log.Add("item");if(++reads==1)return mode=="bad animation"?2:1;
        current.ReadList=()=>untouched;
        if(mode=="item throws")throw new ApplicationException();return -19;};
    c.Store=s=>{if(s!="selected")throw new Exception("wrong animation");log.Add("store");manager=mode=="null manager"?null:current;};
    string failure="none";
    try { c.Tail(); } catch(NullReferenceException) {failure="null";} catch(IndexOutOfRangeException) {failure="bounds";} catch(ApplicationException){failure="item";}
    bool success=mode=="grow" || mode=="spare";
    string order=mode switch {"bad animation"=>"manager;item", "null manager"=>"manager;item;store;manager", _=>"manager;item;store;manager;list;item"};
    string expected=success?"none":mode=="bad animation"?"bounds":mode=="item throws"?"item":"null";
    if(string.Join(";",log)!=order || failure!=expected || untouched.Count!=0 ||
        !sink.SequenceEqual(success?new[]{9,-19}:new[]{9}) || (int)version.GetValue(sink)!=initial+(success?1:0) ||
        mode=="grow" && sink.Capacity<=1 || mode=="spare" && sink.Capacity!=4)throw new Exception(mode+": "+string.Join(";",log));
}
Console.WriteLine("spare and resize: [9,-19], one version increment; replacement and exception order OK");
class NuisanceCustomerManager {public string[] nuisanceAnimations;public static Func<NuisanceCustomerManager> Read;
    public static NuisanceCustomerManager Instance=>Read();public Func<List_1<int>> ReadList;public List_1<int> nuisancesAlreadyBeingDone=>ReadList();}
class Case {public Func<int> Type;public Action<string> Store;int nuisanceType=>Type();string curNuisanceAnimation {set=>Store(value);}
    public void Tail(){\n'''+tail[0]+'''\n}}
namespace System.Collections.Generic {class List_1<T>:List<T>{public List_1(int capacity):base(capacity){} } }''',encoding='utf-8')
    print(run_case(tmp_path,runner).strip())


@pytest.mark.parametrize('defect',['wrong list field','different item','unsigned-to-signed branch','wrong restore','second entry','different manager getter'])
def test_nuisance_append_requires_exact_field_paths(shift_runtime,monkeypatch,defect):
    from iced_x86 import Decoder
    from il2cpp.dec import build
    from il2cpp.list_append import fold_terminal_appends

    m,il=shift_runtime;d=Decompiler(Lifter(il));md=m.methods[24062];td=m.typedefs[md.declaring]
    monkeypatch.setattr(build,'fold_terminal_appends',lambda *args:None);d.lift_method(md,td);blocks=d.L._blocks
    if defect=='different manager getter':
        read=il.bin.read
        def changed(p,n):
            data=read(p,n)
            if p==0x180605860 and n==54: return data[:-1]+b'\xcc'
            return data
        monkeypatch.setattr(il.bin,'read',changed)
    elif defect=='second entry':
        fast=next(b for b in blocks if b.insns[0].ip==0x1805204c8)
        monkeypatch.setattr(fast,'preds',fast.preds+[0])
    else:
        ip,index,byte={'wrong list field':(0x180520471,-1,0x28),'different item':(0x1805204e3,2,0x4c),
                       'unsigned-to-signed branch':(0x1805204a3,0,0x7c),'wrong restore':(0x1805204b4,-1,0x38)}[defect]
        dest=next(b for b in blocks if any(i.ip==ip for i in b.insns));j=next(j for j,i in enumerate(dest.insns) if i.ip==ip)
        data=bytearray(il.bin.read(ip,dest.insns[j].len));data[index]=byte
        monkeypatch.setattr(dest,'insns',dest.insns[:j]+list(Decoder(64,bytes(data),ip=ip))+dest.insns[j+1:])
    old=[(list(b.stmts),b.term,list(b.succs),list(b.preds)) for b in blocks]
    fold_terminal_appends(d.L,md,td,blocks,d._pad_bids)
    assert old==[(b.stmts,b.term,b.succs,b.preds) for b in blocks]
