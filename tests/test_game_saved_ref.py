import re

import pytest
from iced_x86 import Decoder

from dotnet_case import run_case
from il2cpp import Decompiler,Lifter
from il2cpp.saved_ref import saved_references
from test_game_shift_shared_flags import shift_runtime

pytestmark=pytest.mark.game


def test_profile_and_player_lookup_keep_one_object(shift_runtime,tmp_path):
    meta,il=shift_runtime;d=Decompiler(Lifter(il));methods=[]
    for mi,member,signature in ((28347,'GetPlayerProfilePic','public bool Profile(PlatformManager platformManager1)'),
                                (26574,'GetPlayerObject','public bool Speaker(PlayerRef player)')):
        m=meta.methods[mi];body=d.lift_method(m,meta.typedefs[m.declaring]);assert sum(x.count('.'+member+'(') for x in body)==1
        j=next(j for j,s in enumerate(body) if '.'+member+'(' in s);assert body[j+1].lstrip().startswith('if (')
        methods.append(signature+'{\n'+ '\n'.join(body[j:j+2])+' return true; return false;}')
    runner=tmp_path/'runner';runner.mkdir();(runner/'Program.cs').write_text('''using System;using System.Collections.Generic;using System.Linq;
foreach(bool profile in new[]{false,true})foreach(string mode in new[]{"live","null","gone","produce","compare"}){
 var c=new Case();var log=new List<string>();var error=new ApplicationException();var manager=new Manager();var runner=new Runner();var player=new PlayerRef(67);c._runner=runner;
 UnityEngine.Object original=profile?new UnityEngine.Texture2D():new Fusion.NetworkObject();if(mode=="null")original=null;
 void Record(string t){log.Add(t);if(mode==t)throw error;}
 manager.Produce=v=>{if(v!=ProfilePicSize.Large)throw new Exception();Record("produce");return (UnityEngine.Texture2D)original;};
 runner.Get=p=>{if(p!=player)throw new Exception();Record("produce");return (Fusion.NetworkObject)original;};
 UnityEngine.Object.Test=(o,n)=>{if(!ReferenceEquals(o,original)||n is not null)throw new Exception("wrong comparison operand");Record("compare");return mode!="gone"&&o is not null;};
 try{bool value=profile?c.Profile(manager):c.Speaker(player);if(value!=(mode=="live")||mode=="produce"||mode=="compare")throw new Exception("wrong guard");}catch(ApplicationException e)when(ReferenceEquals(error,e)){}
 if(!log.SequenceEqual(mode=="produce"?new[]{"produce"}:new[]{"produce","compare"}))throw new Exception(string.Join(",",log));
}
Console.WriteLine("both lookup/guard slices: one producer and one Unity comparison with the original reference");
enum ProfilePicSize {Large=2}record struct PlayerRef(int Id);
class PlatformManager{public virtual UnityEngine.Texture2D GetPlayerProfilePic(ProfilePicSize v)=>throw new Exception("wrong dispatch");}
class Manager:PlatformManager{public Func<ProfilePicSize,UnityEngine.Texture2D> Produce;public override UnityEngine.Texture2D GetPlayerProfilePic(ProfilePicSize v)=>Produce(v);}
class Runner{public Func<PlayerRef,Fusion.NetworkObject> Get;public Fusion.NetworkObject GetPlayerObject(PlayerRef v)=>Get(v);}
namespace UnityEngine{class Object{public static Func<Object,Object,bool> Test;public static bool operator !=(Object x,Object y)=>Test(x,y);public static bool operator ==(Object x,Object y)=>!Test(x,y);public override bool Equals(object x)=>ReferenceEquals(this,x);public override int GetHashCode()=>0;}class Texture2D:Object{}}
namespace Fusion{class NetworkObject:UnityEngine.Object{}}class Case{public Runner _runner;\n'''+ '\n'.join(methods)+'}',encoding='utf8');print(run_case(tmp_path,runner).strip())


def test_loop_cursor_and_spawn_sites_match_native_counts(shift_runtime):
    meta,il=shift_runtime;d=Decompiler(Lifter(il))
    for j,member,target,expected in ((28693,'GetEnumerator',0x182c020e0,1),(26961,'SpawnItem',0x18055b7b0,16)):
        m=meta.methods[j];body='\n'.join(d.lift_method(m,meta.typedefs[m.declaring]));ips={i.ip for b in d.L._blocks for i in b.insns if i.is_call_near and i.near_branch_target==target}
        assert len(ips)==expected and ips<=d.L._saved_references.keys();assert body.count('.'+member+'(')==expected
        if j==28693:
            name=re.search(r'System.Collections.IEnumerator (\w+) = this.transform.GetEnumerator\(\);',body)[1]
            assert name+'.MoveNext()' in body and name+'.Current' in body and 'finally' in body


@pytest.mark.parametrize('caller,at,pos',[(28347,0x180615809,3),(28693,0x18062e91a,4)])
def test_changed_companion_or_home_declines(shift_runtime,monkeypatch,caller,at,pos):
    meta,il=shift_runtime;d=Decompiler(Lifter(il));m=meta.methods[caller];d.lift_method(m,meta.typedefs[m.declaring]);blocks=d.L._blocks
    b,j=next((b,j) for b in blocks for j,i in enumerate(b.insns) if i.ip==at);i=b.insns[j];raw=bytearray(il.bin.read(at,i.len));raw[pos]^=8
    alt=Decoder(64,bytes(raw),ip=at).decode();assert alt.len==i.len;monkeypatch.setattr(b,'insns',b.insns[:j]+[alt]+b.insns[j+1:]);assert not saved_references(d.L,blocks)
