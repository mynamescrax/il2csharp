import pytest
from iced_x86 import Register as R
from dotnet_case import run_case
from il2cpp import Decompiler,Lifter
from il2cpp.dispatch_fields import dispatch_fields
from il2cpp.emitter import Emitter
from il2cpp.toggle import toggle_sites
from test_game_guarded_continuation import emitted_move
from test_game_shift_shared_flags import shift_runtime

pytestmark=pytest.mark.game


def test_complete_reveal_iterator_and_canvas_toggle(shift_runtime,tmp_path):
    meta,il=shift_runtime;move=emitted_move(meta,il,27147,tmp_path/'out');m=meta.methods[28630];lines=[]
    Emitter(il,str(tmp_path/'out')).emit_method(m,meta.typedefs[m.declaring],lines,'    ')
    src='''using System;using System.Collections;using System.Collections.Generic;using System.Linq;using UnityEngine;
foreach(string mode in new[]{"walk","audio fault","setter fault","setup fault","wait fault","resume overflow","resume zero"}){
 var a=new RevealText();var b=new RevealText();var it=new Frame{__4__this=a,txt="ab",_counter_5__3=91,_totalVisibleCharacters_5__2=47};IEnumerator e=it;var first=it.__2__current;var boom=new ApplicationException(mode);var log=new List<string>();
 var selected=new TextNode();var changed=new TextNode();a.Set=t=>{log.Add("setup");if(it.__1__state!=-1||t!="ab")throw new Exception();if(mode=="setup fault")throw boom;it.__4__this=b;a.text=selected;};
 selected.Info=()=>{log.Add("count");return new Info{characterCount=2};};a.justPlayed=mode=="audio fault";
 a.typingAudioArray=new Audio{Play=()=>{log.Add("audioA");if(a.justPlayed)throw new Exception("not toggled before audio");throw boom;}};
 selected.Write=n=>{log.Add("showA:"+n);if(n!=0||!a.justPlayed||it._counter_5__3!=0||it._totalVisibleCharacters_5__2!=2)throw new Exception();if(mode=="setter fault")throw boom;};
 WaitForSeconds.New=t=>{log.Add("wait");if(t!=0.026f||it.__1__state!=-1)throw new Exception();if(mode=="wait fault")throw boom;};
 Exception fault=null;bool yes=false;try{yes=e.MoveNext();}catch(Exception x){fault=x;}
 string want=mode switch{"setup fault"=>"setup","audio fault"=>"setup,count,audioA","setter fault"=>"setup,count,showA:0",_=>"setup,count,showA:0,wait"};
 if(string.Join(',',log)!=want||(mode.EndsWith(" fault")?!ReferenceEquals(fault,boom)||yes||it.__1__state!=-1||!ReferenceEquals(first,e.Current):fault!=null||!yes||it.__1__state!=1||e.Current is not WaitForSeconds))throw new Exception(mode+":"+string.Join(',',log),fault);
 if(!yes){if(e.MoveNext())throw new Exception();continue;}
 var wait=e.Current;b.justPlayed=true;b.typingAudioArray=new Audio{Play=()=>{log.Add("audioB");if(b.justPlayed)throw new Exception();b.justPlayed=true;b.text=changed;it.__4__this=a;}};
 if(mode=="resume overflow"){it._totalVisibleCharacters_5__2=-2;it._counter_5__3=int.MinValue;}if(mode=="resume zero")it._totalVisibleCharacters_5__2=-1;
 changed.Write=n=>{log.Add("showB:"+n);if(n!=1||!b.justPlayed)throw new Exception();it._totalVisibleCharacters_5__2=1;};
 log.Clear();fault=null;try{yes=e.MoveNext();}catch(Exception x){fault=x;}
 if((mode=="resume overflow"?fault is not OverflowException:mode=="resume zero"?fault is not DivideByZeroException:yes||fault!=null)||string.Join(',',log)!=(mode=="walk"?"audioB,showB:1":"audioB")||it.__1__state!=-1||!ReferenceEquals(e.Current,wait)||e.MoveNext())throw new Exception(mode,fault);}
foreach(bool before in new[]{true,false})foreach(string mode in new[]{"skip","ok","find fault","lookup fault","set fault"}){
 var a=new RealFireSceneSelect{GUIHide=before};var trace=new List<string>();var ex=new ApplicationException();void Step(string s){trace.Add(s);if(mode==s+" fault")throw ex;}
 Input.Read=k=>{Step("key");if(k!=KeyCode.L)throw new Exception();return mode!="skip";};GameObject.F=s=>{Step("find");if(s!="CanvasSceneSelect"||a.GUIHide==before)throw new Exception();a.GUIHide=before;return new GameObject();};GameObject.Lookup=t=>{Step("lookup");if(t!=typeof(Canvas))throw new Exception();return new Canvas();};Canvas.Set=v=>{Step("set");if(v!=before)throw new Exception();};
 Exception fault=null;try{a.Run();}catch(Exception x){fault=x;}var order=new[]{"key","find","lookup","set"};if(!trace.SequenceEqual(order.Take(mode switch{"skip"=>1,"find fault"=>2,"lookup fault"=>3,_=>4}))||(mode.EndsWith(" fault")?!ReferenceEquals(ex,fault):fault!=null)||a.GUIHide!=(mode=="find fault"?!before:before))throw new Exception(mode,fault);}
Console.WriteLine("complete reveal iterator and canvas update passed, including old/new Boolean, resume owner, divide and callback faults");
class Info{public int characterCount;}class TextNode{public Func<Info> Info;public Info textInfo=>Info();public Action<int> Write;public int maxVisibleCharacters{set=>Write(value);}}class Audio{public Action Play;public void PlayAudio()=>Play();}
class RevealText{public bool justPlayed;public Action<string> Set;public TextNode text;public Audio typingAudioArray;public void SetText(string s)=>Set(s);}class WaitForSeconds{public static Action<float> New;public WaitForSeconds(float t)=>New(t);}
class Frame:IEnumerator{public int __1__state;public object __2__current=new();public RevealText __4__this;public string txt;public int _totalVisibleCharacters_5__2,_counter_5__3;public object Current=>__2__current;public void Reset()=>throw new NotSupportedException();\n'''+move+'''}
namespace UnityEngine{public enum KeyCode{L}public class Input{public static Func<KeyCode,bool> Read;public static bool GetKeyDown(KeyCode k)=>Read(k);}public class GameObject{public static Func<string,GameObject> F;public static Func<Type,Canvas> Lookup;public static GameObject Find(string s)=>F(s);public T GetComponent<T>()where T:class=>(T)(object)Lookup(typeof(T));}public class Canvas{public static Action<bool> Set;public bool enabled{set=>Set(value);}}}
class RealFireSceneSelect{public bool GUIHide;public void Run()=>Update();\n'''+ '\n'.join(lines)+'\n}'
    runner=tmp_path/'runner';runner.mkdir();(runner/'Program.cs').write_text(src,encoding='utf8');print(run_case(tmp_path,runner).strip())


@pytest.mark.parametrize('defect',['different byte','different receiver','test inverted byte','wrong saved owner','read AH on join'])
def test_toggle_requires_original_byte_and_both_register_lifetimes(shift_runtime,monkeypatch,defect):
    from iced_x86 import Decoder
    meta,il=shift_runtime;m=meta.methods[27147];d=Decompiler(Lifter(il));d.lift_method(m,meta.typedefs[m.declaring]);bs=d.L._blocks
    dispatch=dispatch_fields(d.L,m,bs,());ip=0x1805a7a0d;plan=lambda:toggle_sites(d.L,m,bs,(),dispatch);assert ip in plan()
    if defect=='wrong saved owner':dispatch.clear()
    else:
        at={'different byte':0x1805a7a16,'different receiver':0x1805a7a16,'test inverted byte':0x1805a7a19,'read AH on join':0x1805a7a31}[defect]
        b,j=next((b,j) for b in bs for j,i in enumerate(b.insns) if i.ip==at);i=b.insns[j].copy()
        if defect=='different byte':i.memory_displacement+=1
        elif defect=='different receiver':i.memory_base=R.RDI
        elif defect=='test inverted byte':i.op0_register=i.op1_register=R.AL
        else:
            alt=Decoder(64,bytes.fromhex('0fb6cc'),ip=at).decode();assert alt.len==i.len;i=alt
        monkeypatch.setattr(b,'insns',b.insns[:j]+[i]+b.insns[j+1:])
    assert ip not in plan()
