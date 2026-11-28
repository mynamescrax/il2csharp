import pytest
from dotnet_case import run_case
from il2cpp.emitter import Emitter
from test_game_shift_shared_flags import shift_runtime

pytestmark = pytest.mark.game


def test_input_callback_requests_keyboard_once(shift_runtime, tmp_path):
    meta,il=shift_runtime;m=meta.methods[27684];lines=[];Emitter(il,str(tmp_path/'out')).emit_method(m,meta.typedefs[m.declaring],lines,'    ')
    assert any('EFloatingGamepadTextInputMode.k_EFloatingGamepadTextInputModeModeSingleLine' in s for s in lines)
    src='''using System;using Steamworks;
var input=new SteamDeckInputField();foreach(var text in new[]{null,"user text"})foreach(int mode in new[]{0,1,2}){
 var error=new ApplicationException();int n=0;SteamUtils.Show=(kind,x,y,w,h)=>{n++;if((int)kind!=0||x!=0||y!=0||w!=500||h!=200)throw new Exception("wrong keyboard args");if(mode==2)throw error;return mode==1;};
 Exception fault=null;try{input.Run(text);}catch(Exception e){fault=e;}if(n!=1||(mode==2?!ReferenceEquals(error,fault):fault!=null))throw new Exception("keyboard request",fault);
}
Console.WriteLine("whole text selection callback: one request, typed enum/stack argument, ignored bool, exact fault");
namespace Steamworks{public enum EFloatingGamepadTextInputMode{k_EFloatingGamepadTextInputModeModeSingleLine=0}
public static class SteamUtils{public static Func<EFloatingGamepadTextInputMode,int,int,int,int,bool> Show;public static bool ShowFloatingGamepadTextInput(EFloatingGamepadTextInputMode mode,int x,int y,int width,int height)=>Show(mode,x,y,width,height);}}
class SteamDeckInputField{public void Run(string text)=>OnInputFieldSelected(text);\n'''+ '\n'.join(lines)+'\n}'
    runner=tmp_path/'r';runner.mkdir();(runner/'Program.cs').write_text(src,encoding='utf8');print(run_case(tmp_path,runner))


def test_voice_row_refresh_runs_at_common_exit_only(shift_runtime,tmp_path):
    meta,il=shift_runtime;m=meta.methods[28419];lines=[];Emitter(il,str(tmp_path/'out')).emit_method(m,meta.typedefs[m.declaring],lines,'    ')
    src='''using System;using System.Linq;using System.Collections.Generic;using System.Threading.Tasks;using UnityEngine;
foreach(bool hasHandler in new[]{false,true})foreach(bool same in new[]{false,true})foreach(string mode in new[]{"no row","null","destroyed","live","faulted task","handlers","compare handler","remove handler","rows","remove row","log","compare row","gameObject","destroy","refresh"}){
 var c=new VoiceVolumeManager();var one=new Map<VoiceVolumeHandler>();var fresh=new Map<VoiceVolumeHandler>();var two=new Map<PerPlayerVolumeRow>();var later=new Map<PerPlayerVolumeRow>();c.voiceHandlers=one;c.playerRows=two;
 var h=new VoiceVolumeHandler();var other=new VoiceVolumeHandler();var row=mode=="null"?null:new PerPlayerVolumeRow();var game=new GameObject();var trace=new List<string>();var want=new List<string>();var ex=new ApplicationException();
 void Step(string s){trace.Add(s);if(s==mode)throw ex;}const string user="Ada";
 one.Get=(string key,ref VoiceVolumeHandler value)=>{if(key!=user)throw new Exception();Step("handlers");value=same?h:other;c.voiceHandlers=fresh;return hasHandler;};
 UnityEngine.Object.Equal=(a,b)=>{if((a is VoiceVolumeHandler)||(b is VoiceVolumeHandler)){Step("compare handler");return ReferenceEquals(a,b);}Step("compare row");return a is null||mode=="destroyed";};
 fresh.Drop=key=>{if(key!=user)throw new Exception();Step("remove handler");return false;};
 two.Get=(string key,ref PerPlayerVolumeRow value)=>{if(key!=user)throw new Exception();Step("rows");c.playerRows=later;value=row;return mode!="no row";};later.Drop=key=>{if(key!=user)throw new Exception();Step("remove row");return false;};
 Debug.Write=(s,context)=>{if(!ReferenceEquals(context,c)||s!="[VoiceVolumeManager] Removing stale local row for 'Ada'.")throw new Exception();Step("log");};if(row is not null)row.Game=()=>{Step("gameObject");return game;};
 UnityEngine.Object.Destroyer=o=>{if(!ReferenceEquals(o,game))throw new Exception();Step("destroy");};var gate=new TaskCompletionSource<bool>();c.Refresh=()=>{Step("refresh");return mode=="faulted task"?Task.FromException(ex):gate.Task;};
 Exception fault=null;try{c.Run(user,h);}catch(Exception e){fault=e;}want.Add("handlers");if(hasHandler){want.Add("compare handler");if(same)want.Add("remove handler");}want.Add("rows");
 if(mode!="no row"){want.AddRange(new[]{"remove row","log","compare row"});if(mode is not ("null" or "destroyed"))want.AddRange(new[]{"gameObject","destroy"});}want.Add("refresh");int cut=want.IndexOf(mode);
 if(!trace.SequenceEqual(cut<0?want:want.Take(cut+1))||(cut<0?fault!=null:!ReferenceEquals(fault,ex))||gate.Task.IsCompleted)throw new Exception(mode+":"+string.Join(',',trace),fault);
}
Console.WriteLine("whole voice row cleanup: both dictionary paths, Unity checks, ordered destroy/refresh and exceptions");
delegate bool Lookup<T>(string key,ref T value);class Map<T>{public Lookup<T> Get;public Func<string,bool> Drop;public bool TryGetValue(string k,ref T v)=>Get(k,ref v);public bool Remove(string k)=>Drop(k);}
namespace UnityEngine{public class Object{public static Func<Object,Object,bool> Equal;public static bool operator ==(Object a,Object b)=>Equal(a,b);public static bool operator !=(Object a,Object b)=>!Equal(a,b);public override bool Equals(object other)=>ReferenceEquals(this,other);public override int GetHashCode()=>base.GetHashCode();public static Action<Object> Destroyer;public static void Destroy(Object o)=>Destroyer(o);}public class GameObject:Object{}public static class Debug{public static Action<string,Object> Write;public static void Log(string s,Object c)=>Write(s,c);}}
class VoiceVolumeHandler:UnityEngine.Object{}class PerPlayerVolumeRow:UnityEngine.Object{public Func<GameObject> Game;public GameObject gameObject=>Game();}
class VoiceVolumeManager:UnityEngine.Object{public Map<VoiceVolumeHandler> voiceHandlers;public Map<PerPlayerVolumeRow> playerRows;public Func<Task> Refresh;private Task RefreshLayoutAsync()=>Refresh();public void Run(string name,VoiceVolumeHandler h)=>RemovePlayerRow(name,h);\n'''+ '\n'.join(lines)+'\n}'
    runner=tmp_path/'r';runner.mkdir();(runner/'Program.cs').write_text(src,encoding='utf8');print(run_case(tmp_path,runner))


@pytest.mark.parametrize('change',['narrow hidden','narrow height','stack slot swapped','wrong receiver','ambiguous callee','return lane read'])
def test_discard_before_return_proves_abi_and_receiver(shift_runtime,monkeypatch,change):
    from il2cpp import Decompiler,Lifter
    from il2cpp.terminal_effect import terminal_effects,_constant_arguments
    from iced_x86 import Decoder,Register as R
    meta,il=shift_runtime;instance=change=='wrong receiver';m=meta.methods[28419 if instance else 27684];td=meta.typedefs[m.declaring];d=Decompiler(Lifter(il));d.lift_method(m,td);bs=d.L._blocks
    scan=lambda:terminal_effects(d.L,m,td,bs,());site=0x18061a277 if instance else 0x1805cc092;assert site in scan()
    if change in ('narrow hidden','narrow height','stack slot swapped'):
        setup=list(bs[0].insns[1:7]);cm=meta.methods[100116];assert _constant_arguments(d.L,cm,setup,(56,))
        off=40 if change=='narrow hidden' else 32
        idx=next(j for j,i in enumerate(setup) if i.memory_displacement==off);i=setup[idx]
        raw={'narrow hidden':'c744242800000000','narrow height':'66c7442420c800','stack slot swapped':'c7442428c8000000'}[change];setup[idx]=Decoder(64,bytes.fromhex(raw),ip=i.ip).decode()
        assert _constant_arguments(d.L,cm,setup,(56,)) is None;return
    if change=='ambiguous callee':
        va=0x18081e450;monkeypatch.setitem(il.addr_candidates,va,[('method',100116),('method',28424)])
    else:
        ip=0x18061a274 if instance else 0x1805cc097
        b,j=next((b,j) for b in bs for j,i in enumerate(b.insns) if i.ip==ip);i=b.insns[j].copy()
        if instance:i.op1_register=R.RDI
        else:i=Decoder(64,bytes.fromhex('4883c001'),ip=ip).decode()  # add rax,1: observes return before RET
        monkeypatch.setattr(b,'insns',b.insns[:j]+[i]+b.insns[j+1:]);assert i.len==b.insns[j].len
    assert site not in scan()


def test_terminal_action_needs_its_own_root_epilogue(shift_runtime,monkeypatch):
    from bisect import bisect_right
    from il2cpp import Decompiler,Lifter
    from il2cpp.terminal_effect import terminal_effects
    meta,il=shift_runtime;m=meta.methods[28419];td=meta.typedefs[m.declaring];d=Decompiler(Lifter(il));d.lift_method(m,td);bs=d.L._blocks
    site=0x18061a277;find=lambda:terminal_effects(d.L,m,td,bs,());assert site in find()
    idx=bisect_right(il._eh4_begins,site-il.bin.image_base)-1
    ui=il.bin.image_base+il._eh4_entries[idx][2];read=il.bin.read
    assert read(ui,4)==b'\x21\0\0\0'
    monkeypatch.setattr(il.bin,'read',lambda a,n:b'\xff'*n if a==ui+4 and n==12 else read(a,n))
    assert not find()
