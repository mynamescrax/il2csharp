"""Whole-method test with distinct time samples and mutable field reads."""
import re

import pytest
from iced_x86 import Decoder
from dotnet_case import run_case
from il2cpp import Lifter,Decompiler
from il2cpp.emitter import Emitter
from il2cpp.scalar_snapshot import scalar_sites
from test_game_shift_shared_flags import shift_runtime

pytestmark=pytest.mark.game


def test_damage_update_reads_each_sample_once_at_native_time(shift_runtime,tmp_path):
    m,il=shift_runtime;md=m.methods[28218];td=m.typedefs[md.declaring];out=tmp_path/'out';em=Emitter(il,str(out));em._emit_one_top(td,m.images[md.image],td.name)
    text=next(out.rglob('ThrownObject.cs')).read_text(encoding='utf8');body=re.search(r'^    private void Update\(\)\n.*?^    }',text,re.M|re.S)[0]
    runner=tmp_path/'runner';runner.mkdir();(runner/'Program.cs').write_text('''using System;
foreach(string mode in new[]{"inactive","zero","NaN","ok","throw first","throw second"}){
 var x=new ThrownObject{hitSomething=mode!="inactive",damage=mode=="zero"?0:mode=="NaN"?float.NaN:1,damageWhenHitPlayer=2};int n=0;
 var failure=new ApplicationException();Time.Sample=()=>{if(++n==1){if(mode=="throw first")throw failure;x.damage=17;x.damageWhenHitPlayer=4;return .125f;}
 if(n!=2||x.damage!=.875f)throw new Exception("replayed first getter or lost store");if(mode=="throw second")throw failure;x.damageWhenHitPlayer=22;return .25f;};
 try{x.Fire();if(mode.StartsWith("throw"))throw new Exception("missing fault");}catch(ApplicationException e)when(ReferenceEquals(e,failure)){}
 if(mode=="ok"&&(n!=2||x.damage!=.875f||x.damageWhenHitPlayer!=3.5f))throw new Exception("late field read or extra getter");
 if(mode=="throw first"&&(n!=1||x.damage!=1||x.damageWhenHitPlayer!=2))throw new Exception("first fault");
 if(mode=="throw second"&&(n!=2||x.damage!=.875f||x.damageWhenHitPlayer!=4))throw new Exception("second fault");
 if((mode=="inactive"||mode=="zero"||mode=="NaN")&&(n!=0||x.damageWhenHitPlayer!=2))throw new Exception("guard");
 Console.WriteLine($"{mode}: reads={n}, damage={x.damage}, player damage={x.damageWhenHitPlayer}");}
class Time{public static Func<float> Sample;public static float deltaTime=>Sample();}
class ThrownObject{public bool hitSomething;public float damage,damageWhenHitPlayer;public void Fire()=>Update();\n'''+body+'\n}',encoding='utf8')
    print(run_case(tmp_path,runner).strip())


def test_scalar_snapshots_require_same_value_and_source(shift_runtime,monkeypatch):
    m,il=shift_runtime;md=m.methods[28218];td=m.typedefs[md.declaring];d=Decompiler(Lifter(il));d.lift_method(md,td);bs=d.L._blocks
    get=lambda:scalar_sites(d.L,md,td,bs,())[1];assert len(get())==2
    for addr,offset in ((0x18060c4dc,3),(0x18060c4cf,3)):
        b,j=next((b,j) for b in bs for j,i in enumerate(b.insns) if i.ip==addr);i=b.insns[j];raw=bytearray(il.bin.read(addr,i.len));raw[offset]^=1
        c=list(Decoder(64,bytes(raw),ip=addr));assert len(c)==1 and c[0].len==i.len
        with monkeypatch.context() as mp:
            mp.setattr(b,'insns',b.insns[:j]+c+b.insns[j+1:]);assert list(get())==[0x18060c4bc]
