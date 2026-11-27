import re
import pytest
from dotnet_case import run_case
from il2cpp import Decompiler,Lifter
from il2cpp.emitter import Emitter
from test_game_shift_shared_flags import shift_runtime

pytestmark=pytest.mark.game


def test_complete_spin_includes_actual_loop_exits(shift_runtime,tmp_path):
    meta,il=shift_runtime;m=meta.methods[27625];lines=[];Emitter(il,str(tmp_path/'out')).emit_method(m,meta.typedefs[m.declaring],lines,'    ')
    src='''using System;using System.Linq;using System.Collections.Generic;using UnityEngine;
foreach(int winning in Enumerable.Range(-1,8))foreach(bool authority in new[]{true,false}){
 var expected=new List<string>();if(winning>=0)expected.Add("trigger:"+winning);switch(winning){case 0:case 4:for(int i=0;i<(winning==0?10:2);i++)expected.Add("invoke:"+BitConverter.SingleToInt32Bits(i*0.13f));break;
 case 1:expected.AddRange(new[]{"off","on"});break;case 2:case 5:expected.Add("hat");break;case 3:expected.AddRange(new[]{"object","authority"});if(authority)expected.AddRange(new[]{"instance","revenue"});break;}
 if(winning is >=0 and <=5 && winning!=1)expected.AddRange(new[]{"particle","sound"});
 foreach(int failAt in Enumerable.Range(-1,expected.Count+1)){var c=new Wheel();var log=new List<string>();var err=new ApplicationException();void Step(string s){log.Add(s);if(log.Count-1==failAt)throw err;}
 int dists=0,shots=0;var point=new Vector3{x=5,y=-3,z=2};c.arrowTip=new Transform{Read=()=>{shots++;return point;}};
 c.wheelObjects=Enumerable.Range(0,7).Select(j=>new Transform{Read=()=>new Vector3{x=5,y=-3,z=(winning>=0&&j==winning?2:winning==3&&j==0?12:10002)}}).ToArray();
 Vector3.Compute=(a,b)=>{dists++;if(a.z!=2||b.z!=(winning==3&&dists==1?12:2))throw new Exception("bad improving operands");return Math.Abs(a.z-b.z);};
 c.wheelWinIndicator=Enumerable.Range(0,7).Select(j=>new Animator{Trigger=s=>{if(s!="Play")throw new Exception();Step("trigger:"+j);}}).ToArray();
 c.Schedule=(s,t)=>{if(s!="Rpc_SpawnToken")throw new Exception();Step("invoke:"+BitConverter.SingleToInt32Bits(t));};c.Hat=()=>Step("hat");
 c.nothingEarnedObj=new GameObject{Set=v=>{if(v)throw new Exception("stale receiver");Step("off");c.nothingEarnedObj=new GameObject{Set=b=>Step(b?"on":"bad")};}};
 c.winParticle=new Particle{Action=()=>{Step("particle");c.winSfx=new Audio{Action=()=>Step("sound")};}};c.winSfx=null;
 c.GetObject=()=>{Step("object");return new Fusion.NetworkObject{Read=()=>{Step("authority");return authority;}};};StoreManager.Read=()=>{Step("instance");return new StoreManager{Change=(s,v)=>{if(s!="Wheel Spin"||v!=10f)throw new Exception();Step("revenue");}};};
 Exception f=null;try{c.Run();}catch(Exception e){f=e;}if(!log.SequenceEqual(expected.Take(failAt<0?expected.Count:failAt+1))||dists!=(winning==3?2:winning>=0?1:0)||shots!=7+dists||
    (winning<0?f is not IndexOutOfRangeException:failAt>=0?!ReferenceEquals(err,f):f!=null))throw new Exception(winning+"/"+authority+"/"+failAt+":"+string.Join(',',log),f);}}
Console.WriteLine("whole CompleteSpin: six rewards, no winner, out-of-range reward, independent authority, all invokes and common tail faults passed");
namespace Fusion{public class NetworkObject{public Func<bool> Read;public bool HasStateAuthority=>Read();}}
namespace UnityEngine{public struct Vector3{public float x,y,z;public static Func<Vector3,Vector3,float> Compute;public static float Distance(Vector3 a,Vector3 b)=>Compute(a,b);}public class Transform{public Func<Vector3> Read;public Vector3 position=>Read();}public class Animator{public Action<string> Trigger;public void SetTrigger(string s)=>Trigger(s);}public class GameObject{public Action<bool> Set;public void SetActive(bool v)=>Set(v);}}
public class Audio{public Action Action;public void Play()=>Action();}public class Particle{public Action Action;public void Play()=>Action();}
public class StoreManager{public static Func<StoreManager> Read;public static StoreManager Instance=>Read();public Action<string,float> Change;public void ChangeRevenue(string s,float f)=>Change(s,f);}
class Wheel{public Func<Fusion.NetworkObject> GetObject;public Fusion.NetworkObject Object=>GetObject();public Transform[] wheelObjects;public Transform arrowTip;public Animator[] wheelWinIndicator;public GameObject nothingEarnedObj;public Audio winSfx;public Particle winParticle;public Action<string,float> Schedule;public void Invoke(string s,float f)=>Schedule(s,f);public Action Hat;public void UnlockRandomHat()=>Hat();public void Run()=>CompleteSpin();\n'''+ '\n'.join(lines)+'\n}'
    runner=tmp_path/'runner';runner.mkdir();(runner/'Program.cs').write_text(src,encoding='utf8');print(run_case(tmp_path,runner).strip())


def test_phone_dialogue_reaches_its_own_rpc_continuation(shift_runtime,tmp_path):
    meta,il=shift_runtime;m=meta.methods[28032];d=Decompiler(Lifter(il));s='\n'.join(d.lift_method(m,meta.typedefs[m.declaring]));
    # Only the scheduling loop and its verified normal continuation.
    part=re.search(r'(float \w+ = 0;\s+while \(true\)\s+\{\s+this\.Invoke\("RunDialogue", \w+ \* 4\.5f\);.*?\}\s*this\.Rpc_CMD_Interact\(playerMan\);\s*this\.Rpc_CMD_ShrineEvent\(playerMan\);)',s,re.S)[1]
    program='''using System;using System.Collections.Generic;using System.Linq;var c=new Case();var player=new Player();foreach(int stop in Enumerable.Range(-1,9)){var log=new List<string>();var err=new ApplicationException();c.Put=s=>{log.Add(s);if(log.Count-1==stop)throw err;};c.Who=player;Exception f=null;try{c.Run(player);}catch(Exception x){f=x;}
string[] want={"RunDialogue0","Rpc_CMD_PlayTelephoneChatterAudio0","RunDialogue4.5","Rpc_CMD_PlayTelephoneChatterAudio4.5","RunDialogue9","Rpc_CMD_PlayTelephoneChatterAudio9","interact","shrine"};if(!log.SequenceEqual(want.Take(stop<0?8:stop+1))||!ReferenceEquals(f,stop<0?null:err))throw new Exception(string.Join(',',log),f);}Console.WriteLine("dialogue loop slice passed");
class Player{}class Case{public Player Who;public Action<string> Put;void Invoke(string s,float t)=>Put(s+t.ToString(System.Globalization.CultureInfo.InvariantCulture));void Rpc_CMD_Interact(Player p)=>Put(ReferenceEquals(p,Who)?"interact":"wrong");void Rpc_CMD_ShrineEvent(Player p)=>Put(ReferenceEquals(p,Who)?"shrine":"wrong");public void Run(Player playerMan){\n'''+part+'\n}}'
    runner=tmp_path/'runner';runner.mkdir();(runner/'Program.cs').write_text(program,encoding='utf8');run_case(tmp_path,runner)
