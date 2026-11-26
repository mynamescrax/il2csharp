"""Compile the emitted Spawned, iterator factory and state constructor together."""
import os
import re

import pytest

from dotnet_case import run_case
from il2cpp.cli import main
from test_game_shift_shared_flags import shift_runtime

pytestmark=pytest.mark.game


def test_base_spawn_precedes_iterator_construction_and_scheduling(shift_runtime,tmp_path):
    out=tmp_path/'out';runner=tmp_path/'runner';runner.mkdir()
    assert main(['il2csharp','--metadata',os.environ['IL2CSHARP_METADATA'],'--binary',os.environ['IL2CSHARP_BINARY'],
                 '--only','Assembly-CSharp','--types','StoryModeManager','--strict','-o',str(out)])==0
    src=next(out.rglob('StoryModeManager.cs')).read_text(encoding='utf-8')
    spawn=re.search(r'public override void Spawned\(\)\s*\{.*?^    }',src,re.S|re.M)
    factory=re.search(r'private (?:System\.Collections\.)?IEnumerator LoadStatsNextFrame\(\)\s*\{.*?^    }',src,re.S|re.M)
    assert spawn and factory and 'base.Spawned() /* shared implementation */;' in spawn[0] and 'sub_' not in spawn[0]
    it=re.search(r'new (?:StoryModeManager\.)?(\w+)\(0\) \{ (\w+) = this \}',spawn[0]);assert it
    name,owner=it.groups()
    ctor=re.search(r'public '+name+r'\(int (\w+)\) : base\(\)\s*\{\s*this\.(\w+) = \1;\s*}',src);assert ctor
    state=ctor[2]; fields=[re.search(r'private int '+state+r';',src),re.search(r'public StoryModeManager '+owner+r';',src)]
    assert all(fields)
    (runner/'Program.cs').write_text('''using System;
using System.Collections;
using System.Collections.Generic;
using System.Linq;
var s=new StoryModeManager();NetworkBehaviour dispatch=s;
foreach(string mode in new[]{"ok","base throws","constructor throws","scheduler throws"}) {
    var trace=new List<string>();IEnumerator scheduled=null;bool threw=false;
    s.OnBase=()=>{trace.Add("base");if(mode=="base throws")throw new ApplicationException();};
    StoryModeManager.OnNew=()=>{trace.Add("new");if(mode=="constructor throws")throw new ApplicationException();return 0;};
    s.Schedule=it=>{trace.Add("start");scheduled=it;if(!s.Valid(it))throw new Exception("wrong state or owner");if(mode=="scheduler throws")throw new ApplicationException();};
    try {dispatch.Spawned();}catch(ApplicationException){threw=true;}
    string expected=mode switch {"base throws"=>"base","constructor throws"=>"base;new",_=>"base;new;start"};
    if(string.Join(";",trace)!=expected || threw!=(mode!="ok"))throw new Exception(mode+": "+string.Join(";",trace));
    Console.WriteLine(mode+": "+expected);
    if(mode=="ok"){var second=s.FromFactory();if(!s.Valid(second) || ReferenceEquals(scheduled,second) || trace.Count!=4 || trace.Last()!="new")throw new Exception("factory");}
}
class NetworkBehaviour {public Action OnBase;public Action<IEnumerator> Schedule; public virtual void Spawned()=>OnBase();
    protected void StartCoroutine(IEnumerator it)=>Schedule(it);}
class StoryModeManager : NetworkBehaviour {
    public static Func<int> OnNew;
''' + spawn[0]+'\n'+factory[0]+f'''
    public IEnumerator FromFactory()=>LoadStatsNextFrame();
    public bool Valid(IEnumerator it)=>it is {name} value && value.InitialState==0 && ReferenceEquals(value.{owner},this);
    private sealed class {name}:IEnumerator {{
        readonly int probe=OnNew();
'''+'\n'.join(f[0] for f in fields)+'\n'+ctor[0]+f'''
        public int InitialState=>{state}; public object Current=>null;public bool MoveNext()=>false;public void Reset(){{}}
    }}
}}''',encoding='utf-8')
    print(run_case(tmp_path,runner).strip())


@pytest.mark.parametrize('defect',['different constructor field','different base target','different captured owner','different barrier'])
def test_iterator_constructor_requires_matching_effects(shift_runtime,monkeypatch,defect):
    from iced_x86 import Decoder
    from il2cpp import Decompiler,Lifter
    from il2cpp.dec import build
    from il2cpp.iterator_ctor import fold_iterator_creation

    meta,il=shift_runtime;d=Decompiler(Lifter(il));m=meta.methods[27944];td=meta.typedefs[m.declaring]
    monkeypatch.setattr(build,'fold_iterator_creation',lambda *args:None)
    d.lift_method(m,td);blocks=d.L._blocks
    if defect in ('different constructor field','different base target'):
        ctor=meta.methods[27967]; read=il.bin.read
        def changed(p,n):
            data=read(p,n)
            if p==ctor.addr and n==36:
                off=24 if defect=='different constructor field' else 18
                return data[:off]+bytes([data[off]^4])+data[off+1:]
            return data
        monkeypatch.setattr(il.bin,'read',changed)
    else:
        ip=0x1805e69f7 if defect=='different captured owner' else 0x1805e69fb
        b=next(b for b in blocks if any(i.ip==ip for i in b.insns));j=next(j for j,i in enumerate(b.insns) if i.ip==ip)
        code=bytearray(il.bin.read(ip,b.insns[j].len));code[2 if defect=='different captured owner' else 1]^=8
        monkeypatch.setattr(b,'insns',b.insns[:j]+list(Decoder(64,bytes(code),ip=ip))+b.insns[j+1:])
    before=[(list(b.stmts),b.ret) for b in blocks]
    fold_iterator_creation(d.L,td,blocks,d._pad_bids)
    assert before==[(b.stmts,b.ret) for b in blocks]
