import re

import pytest
from iced_x86 import Register as R
from dotnet_case import run_case
from il2cpp import Decompiler,Lifter
from il2cpp.emitter import Emitter
from il2cpp.field_remainder import field_divisions
from test_game_shift_shared_flags import shift_runtime

pytestmark=pytest.mark.game


def test_remainder_setter_and_post_callback_threshold(shift_runtime,tmp_path):
    meta,il=shift_runtime;m=meta.methods[27147];out=tmp_path/'out';em=Emitter(il,str(out));td=next(t for t in meta.typedefs if t.name=='RevealText')
    em._emit_one_top(td,meta.images[m.image],td.name);s=next(out.rglob('RevealText.cs')).read_text(encoding='utf8')
    code=re.search(r'(int \w+ = this\._totalVisibleCharacters_5__2;\s+int \w+ = this\._counter_5__3;.*?if \(\w+ < this\._totalVisibleCharacters_5__2\))',s,re.S)[1]
    src='''using System;
    foreach(var (n,total,after) in new[]{(-17,4,-1),(-17,4,-3),(17,4,2),(17,4,3),(0,0,1),(3,int.MaxValue,2),(13,-1,1),(int.MinValue,-2,0)}){
        var c=new Case{_counter_5__3=n,_totalVisibleCharacters_5__2=total};int writes=0;long divisor=unchecked(total+1);
        c.__4__this.text.Set=x=>{writes++;if(x!=(long)n%divisor)throw new Exception("wrong saved remainder");c._counter_5__3=101;c._totalVisibleCharacters_5__2=after;};
        Exception fault=null;bool result=false;try{result=c.Step();}catch(Exception e){fault=e;}
        if(divisor==0?fault is not DivideByZeroException||writes!=0:divisor==-1&&n==int.MinValue?fault is not OverflowException||writes!=0:
              fault!=null||writes!=1||result!=((long)n%divisor<after))throw new Exception("bad divide/check",fault);
    }
    Console.WriteLine("signed field remainder, divide faults before setter, and post-set threshold passed");
    public class TMP_Text{public Action<int> Set;public int maxVisibleCharacters{set=>Set(value);}} public class Owner{public TMP_Text text=new();}
    public class Case{public Owner __4__this=new();public int _counter_5__3,_totalVisibleCharacters_5__2;public bool Step(){\n'''+code+' return true;return false;}}'
    runner=tmp_path/'runner';runner.mkdir();(runner/'Program.cs').write_text(src,encoding='utf8');print(run_case(tmp_path,runner).strip())


@pytest.mark.parametrize('defect',['wrong dividend base','other divisor','wrong saved lane','wide saved observation','bad receiver'])
def test_field_division_proof_requires_actual_uses(shift_runtime,monkeypatch,defect):
    meta,il=shift_runtime;d=Decompiler(Lifter(il));m=meta.methods[27147];d.lift_method(m,meta.typedefs[m.declaring]);bs=d.L._blocks
    def plan():return field_divisions(d.L,m,bs,d._pad_bids)
    ip=0x1805a7a3a;assert ip in plan()
    b,j=next((b,j) for b in bs for j,i in enumerate(b.insns) if i.ip==ip);j+={'wrong dividend base':-3,'other divisor':0,'wrong saved lane':2,'wide saved observation':2,'bad receiver':1}[defect];i=b.insns[j].copy()
    if defect=='wrong dividend base':i.memory_base=R.RSI
    elif defect=='other divisor':i.op0_register=R.EDI
    elif defect=='wrong saved lane':i.op1_register=R.EAX
    elif defect=='bad receiver':i.memory_displacement=0x38  # a byte field, not the text reference
    else:i.op0_register=R.RSI;i.op1_register=R.RDX
    monkeypatch.setattr(b,'insns',b.insns[:j]+[i]+b.insns[j+1:]);assert ip not in plan()
