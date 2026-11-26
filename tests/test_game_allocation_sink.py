"""Compile the emitted iterator's yield block with the actual Current and state fields."""
import os
import re

import pytest

from dotnet_case import run_case
from il2cpp.cli import main
from test_game_shift_shared_flags import shift_runtime

pytestmark=pytest.mark.game


def test_yield_binds_one_typed_wait_before_publishing_current(shift_runtime,tmp_path):
    out=tmp_path/'out'; runner=tmp_path/'runner';runner.mkdir()
    assert main(['il2csharp','--metadata',os.environ['IL2CSHARP_METADATA'],'--binary',os.environ['IL2CSHARP_BINARY'],
                 '--only','Assembly-CSharp','--types','CFX_AutoDestructShuriken','--strict','-o',str(out)])==0
    src=next(out.rglob('CFX_AutoDestructShuriken.cs')).read_text(encoding='utf-8')
    block=re.search(r'WaitForSeconds (\w+) = new WaitForSeconds\(0\.5f\);\s*'
                    r'this\.(\w+) = \1;\s*this\.(\w+) = 1;\s*return true;',src)
    assert block
    current,state=block[2],block[3]
    current_decl=re.search(r'\bobject '+current+r';',src); state_decl=re.search(r'\bint '+state+r';',src)
    assert current_decl and state_decl
    (runner/'Program.cs').write_text('''using System;
var iterator=new Iterator(); var marker=new object(); iterator.Current=marker; iterator.State=-1;
WaitForSeconds.Hook=(_,s)=>{if(s!=0.5f || iterator.Current!=marker || iterator.State!=-1)throw new Exception("early publish"); throw new ApplicationException();};
try { iterator.Yield(); throw new Exception("missing constructor failure"); }catch(ApplicationException) { }
if(iterator.Current!=marker || iterator.State!=-1)throw new Exception("overwrote on failure");
WaitForSeconds made=null;int n=0;
WaitForSeconds.Hook=(w,s)=>{if(s!=0.5f)throw new Exception("duration");made=w;n++;};
if(!iterator.Yield() || iterator.Current!=made || iterator.State!=1 || n!=1)throw new Exception("constructor identity");
var first=made; if(!iterator.Yield() || made==first || iterator.Current!=made || n!=2)throw new Exception("reused allocation");
Console.WriteLine("two distinct half-second waits; failing constructor leaves Current and state unchanged");
class WaitForSeconds {public static Action<WaitForSeconds,float> Hook; public WaitForSeconds(float s)=>Hook(this,s);}
class Iterator {\n'''+current_decl[0]+state_decl[0]+f'public object Current {{get=>{current};set=>{current}=value;}} public int State {{get=>{state};set=>{state}=value;}}\n'+
        'public bool Yield(){\n'+block[0]+'\n}}',encoding='utf-8')
    print(run_case(tmp_path,runner).strip())
