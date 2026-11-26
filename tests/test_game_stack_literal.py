"""Compile the actual recovered virtual-call statement, not the entire handler."""
import re

import pytest
from dotnet_case import run_case
from il2cpp import Lifter,Decompiler
from test_game_shift_shared_flags import shift_runtime

pytestmark=pytest.mark.game


def test_virtual_stack_literals_dispatch_on_original_receiver(shift_runtime,tmp_path):
    meta,il=shift_runtime;d=Decompiler(Lifter(il));md=meta.methods[28219];text='\n'.join(d.lift_method(md,meta.typedefs[md.declaring]))
    calls=list(re.finditer(r'^\s*(\w+)\.Hit\(this.damage, new UnityEngine.Vector3 \{ x = (\w+)\.x, y = \2\.y, z = \2\.z \}, false, true, "Bludgeon"\);',text,re.M))
    assert len(calls)==text.count('.Hit(')>0
    src='''using System;using UnityEngine;
var d=new Derived();var c=new Case();var v=new Vector3{x=3.25f,y=-11,z=24};\n'''+ '\n'.join(f'c.Run{n}(d,v);' for n in range(len(calls)))+f'if(d.Count!={len(calls)})throw new Exception("lost dispatch");'+'''
Console.WriteLine("all Hit slices called the override with false, true, Bludgeon and exact XYZ");
namespace UnityEngine{public record struct Vector3{public float x,y,z;}}
class Target{public virtual void Hit(float f,Vector3 v,bool a,bool b,string s)=>throw new Exception("base call");}
class Derived:Target{public int Count;public override void Hit(float f,Vector3 v,bool a,bool b,string s){Count++;if(f!=5||v.x!=3.25f||v.y!=-11||v.z!=24||a||!b||s!="Bludgeon")throw new Exception("wrong arguments");}}
class Case {float damage=5;\n'''+ '\n'.join(f'public void Run{n}(Target {c[1]},Vector3 {c[2]}) {{\n'+c[0]+'\n}' for n,c in enumerate(calls))+'}'
    runner=tmp_path/'runner';runner.mkdir();(runner/'Program.cs').write_text(src,encoding='utf8');print(run_case(tmp_path,runner).strip())
    other=meta.methods[25436];assert 'true, false, "Normal")' in '\n'.join(d.lift_method(other,meta.typedefs[other.declaring]))
