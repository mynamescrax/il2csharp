import re

import pytest
from iced_x86 import Decoder

from dotnet_case import run_case
from il2cpp import Decompiler,Lifter
from il2cpp.bool_restore import bool_state_sites
from test_game_shift_shared_flags import shift_runtime

pytestmark=pytest.mark.game


def test_backface_restore_on_reached_edge(shift_runtime,tmp_path):
    meta,il=shift_runtime;d=Decompiler(Lifter(il));members=[]
    for mi,name in ((25688,'Spill'),(25689,'Hose')):
        m=meta.methods[mi];lines=d.lift_method(m,meta.typedefs[m.declaring]);updates=[s.strip() for s in lines if '.queriesHitBackfaces' in s]
        assert len(updates)==3 and not d.eh
        temp=re.fullmatch(r'bool (\w+) = UnityEngine.Physics.queriesHitBackfaces;',updates[0])[1]
        assert updates[1:] == ['UnityEngine.Physics.queriesHitBackfaces = true;',f'UnityEngine.Physics.queriesHitBackfaces = {temp};']
        ray=next(j for j,s in enumerate(lines) if '.RaycastAll(' in s);assert lines.index(updates[1])<ray<lines.index(updates[2]);assert not any(s.strip()=='finally' for s in lines)
        members.append('public static void '+name+'(Action work){'+'\n'.join([*updates[:2],'work();',updates[2]])+'}')
    runner=tmp_path/'runner';runner.mkdir();(runner/'Program.cs').write_text('''using System;using UnityEngine;
foreach(Action<Action> run in new Action<Action>[]{Calls.Spill,Calls.Hose})foreach(bool initial in new[]{false,true})foreach(string fail in new[]{"","get","first","work","last"}){
 Physics.State=initial;Physics.Trace="";Physics.Fail=fail;Physics.Writes=0;var error=Physics.Err;
 try{run(()=>{if(!Physics.State)throw new Exception("override too late");Physics.Trace+="work;";if(fail=="work")throw error;Physics.State=!initial;});if(fail!="")throw new Exception("lost fault");}catch(ApplicationException e)when(ReferenceEquals(e,error)){}
 string expected="get;"+(fail=="get"?"":"set:True;"+(fail=="first"?"":"work;"+(fail=="work"?"":"set:"+initial+";")));
 if(expected!=Physics.Trace||Physics.State!=(fail=="last"?!initial:fail=="work"?true:initial))throw new Exception(Physics.Trace);
}
Console.WriteLine("saved Boolean restored on normal path; throwing getter, override, work and restore checked");
namespace UnityEngine{class Physics{public static bool State;public static string Trace,Fail;public static int Writes;public static ApplicationException Err=new();public static bool queriesHitBackfaces{get{Trace+="get;";if(Fail=="get")throw Err;return State;}set{Trace+="set:"+value+";";if(Fail==(++Writes==1?"first":"last"))throw Err;State=value;}}}}
class Calls{\n'''+ '\n'.join(members)+'}',encoding='utf8');print(run_case(tmp_path,runner).strip())


@pytest.mark.parametrize('mi,ip,raw',[(25689,0x18070cee4,'410fb6cd'),(25688,0x18070d2f9,'0fb64d41')])
def test_unrelated_reload_is_not_a_restore(shift_runtime,monkeypatch,mi,ip,raw):
    meta,il=shift_runtime;d=Decompiler(Lifter(il));md=meta.methods[mi];d.lift_method(md,meta.typedefs[md.declaring]);bs=d.L._blocks
    b,j=next((b,j) for b in bs for j,i in enumerate(b.insns) if i.ip==ip);i=b.insns[j];data=bytes.fromhex(raw)
    alt=Decoder(64,data,ip=ip).decode();assert alt.len==i.len;monkeypatch.setattr(b,'insns',b.insns[:j]+[alt]+b.insns[j+1:]);assert ip not in bool_state_sites(d.L,md,bs,())
