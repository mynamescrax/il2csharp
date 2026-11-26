import pytest
from iced_x86 import Mnemonic as M, Register as R

from dotnet_case import run_case
from il2cpp import Decompiler,Lifter
from il2cpp.byval_forward import byval_forward
from il2cpp.emitter import Emitter
from test_game_shift_shared_flags import shift_runtime

pytestmark=pytest.mark.game


def test_complete_placement_particle_and_rope_forwarders(shift_runtime,tmp_path):
    meta,il=shift_runtime;em=Emitter(il,str(tmp_path/'out'));members={}
    for j in (25668,25378,25387,25390,25393):
        m=meta.methods[j];td=meta.typedefs[m.declaring];em.emit_method(m,td,members.setdefault(td.name,[]),'    ')
    runner=tmp_path/'runner';runner.mkdir();src='''using System;using System.Collections.Generic;using System.Linq;using UnityEngine;
var p=new Vector3(1.25f,BitConverter.Int32BitsToSingle(unchecked((int)0xffc04321)), -0.0f);var q=new Quaternion(2.75f,-101,1e-20f,42);var who=new PlayerManager();string type="case";
var calls=new List<string>();var failure=new ApplicationException();bool fail=false;
void Record(string name,Vector3 actual){if(BitConverter.SingleToInt32Bits(actual.x)!=BitConverter.SingleToInt32Bits(p.x)||BitConverter.SingleToInt32Bits(actual.y)!=BitConverter.SingleToInt32Bits(p.y)||BitConverter.SingleToInt32Bits(actual.z)!=BitConverter.SingleToInt32Bits(p.z))throw new Exception("wrong position");calls.Add(name);if(fail)throw failure;}
var inv=new InventoryManager{Hook=(a,b,v,r)=>{if(!ReferenceEquals(a,who)||!ReferenceEquals(b,type)||r!=q)throw new Exception("placement arguments");Record("place",v);}};
var gas=new GasCollisionSpawner{Hook=(v,r)=>{if(r!=q)throw new Exception("rotation");Record("spawn",v);}};
var hose=new GasPumpHoses{Hook=Record};var steps=new Action[]{()=>inv.Run(who,type,p,q),()=>gas.Run(p,q),()=>hose.ConnectRope(p),()=>hose.ChangeRopeBulge(p,false),()=>hose.ChangeRopeBulge(p,true),()=>hose.DisconnectRope(p)};
foreach(var step in steps)step();var expected=new[]{"place","spawn","connect","bulge:False","bulge:True","disconnect"};if(!calls.SequenceEqual(expected))throw new Exception("wrong calls");
calls.Clear();fail=true;foreach(var step in steps){try{step();throw new Exception("lost exception");}catch(ApplicationException e)when(ReferenceEquals(e,failure)){}}if(!calls.SequenceEqual(expected))throw new Exception("call replayed");
Console.WriteLine("five complete wrappers: exact aggregate bits, player/type identity, both bools, normal and throwing sinks passed");
namespace UnityEngine {public record struct Vector3(float x,float y,float z);public record struct Quaternion(float x,float y,float z,float w);}
public class PlayerManager{}
'''
    stubs={'InventoryManager':'public Action<PlayerManager,string,Vector3,Quaternion> Hook;public void Run(PlayerManager a,string b,Vector3 v,Quaternion q)=>PlaceItem(a,b,v,q); void Rpc_CMD_PlaceItem(PlayerManager a,string b,Vector3 v,Quaternion q)=>Hook(a,b,v,q);',
           'GasCollisionSpawner':'public Action<Vector3,Quaternion> Hook;public void Run(Vector3 v,Quaternion q)=>SpawnParticle(v,q);void Rpc_CMD_SpawnParticle(Vector3 v,Quaternion q)=>Hook(v,q);',
           'GasPumpHoses':'public Action<string,Vector3> Hook;void Rpc_CMD_ConnectRope(Vector3 v)=>Hook("connect",v);void Rpc_CMD_DisconnectRope(Vector3 v)=>Hook("disconnect",v);void Rpc_CMD_ChangeRopeBulge(Vector3 v,bool b)=>Hook("bulge:"+b,v);'}
    for owner,lines in members.items():src+=f'public class {owner} {{'+stubs[owner]+'\n'+'\n'.join(lines)+'\n}\n'
    (runner/'Program.cs').write_text(src,encoding='utf8');print(run_case(tmp_path,runner).strip())


@pytest.mark.parametrize('defect',['repeated lane','overlapping homes','wrong hidden slot','wrong stack input','other target'])
def test_forward_declines_incomplete_or_aliased_copy(shift_runtime,monkeypatch,defect):
    meta,il=shift_runtime;d=Decompiler(Lifter(il));m=meta.methods[25668];td=meta.typedefs[m.declaring];d.eh=None;s,_=d._decode(m)
    prove=lambda:byval_forward(d.L,m,td,s,None);assert prove()
    if defect=='other target':monkeypatch.setitem(il.addr_candidates,s[-3].near_branch_target,[('method',m.index)])
    else:
        j=next(j for j,i in enumerate(s) if {'repeated lane':i.op0_register==R.EAX and i.memory_base==R.R9,
                'overlapping homes':i.mnemonic==M.LEA and i.op0_register==R.RAX,'wrong hidden slot':i.mnemonic==M.MOV and i.memory_displacement==0x28,
                'wrong stack input':i.op0_register==R.RAX and i.memory_displacement==0x80}[defect]);i=s[j];alt=i.copy()
        alt.memory_displacement={'repeated lane':0,'overlapping homes':0x30,'wrong hidden slot':0x20,'wrong stack input':0x88}[defect];s[j]=alt
    assert prove() is None
