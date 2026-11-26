"""Run the recovered hit reads with a getter which replaces an array element."""
import re

import pytest
from iced_x86 import Decoder
from dotnet_case import run_case
from il2cpp import Lifter,Decompiler
from il2cpp.array_member import element_reads
from test_game_shift_shared_flags import shift_runtime

pytestmark=pytest.mark.game


def test_returned_struct_array_reads_are_live(shift_runtime,tmp_path):
    m,il=shift_runtime;cases=[]
    for j in (25688,25689):
        md=m.methods[j];d=Decompiler(Lifter(il));s='\n'.join(d.lift_method(md,m.typedefs[md.declaring]))
        source=re.search(r'UnityEngine.RaycastHit\[\] (\w+) = UnityEngine.Physics.RaycastAll\(',s)[1]
        check=re.search(r'for \(int (\w+) = 0; \1 < '+source+r'\.Length; \1\+\+\)\s*\{\s*(UnityEngine.Collider (\w+) = '+source+r'\[\1\]\.collider;)',s)
        assert check;idx,read,collider=check.groups()
        result=re.search(r'float (\w+) = '+source+r'\['+idx+r'\]\.distance;',s)
        if j==25688:
            guard=re.search(r'bool (\w+) = \('+collider+r' == null\);',s[check.end():]);assert result and guard and 'if (!('+guard[1]+'))' in s[check.end():result.start()]
            code=read+'\n'+guard[0]+'\nif (!('+guard[1]+')){'+result[0]+'return '+result[1]+';}return -1f;'
        else:code=read+'\nreturn '+collider+';'
        cases.append(f'public static {"float A" if result else "UnityEngine.Collider B"}(UnityEngine.RaycastHit[] {source},int {idx}) {{'+code+'}')
    runner=tmp_path/'runner';runner.mkdir();(runner/'Program.cs').write_text('''using System;
using UnityEngine;
var c=new Collider();var a=new RaycastHit[2];int reads=0;
a[0]=new(){Get=()=>throw new Exception("wrong index")};
a[1]=new(){Get=()=>{reads++;a[1]=new(){D=23.5f};return c;},D=7};
if(Case.A(a,1)!=23.5f||reads!=1)throw new Exception("stale struct or repeated collider");
a[1]=new(){Get=()=>null,Fail=true};if(Case.A(a,1)!=-1)throw new Exception("unexpected distance");
a[1]=new(){Get=()=>c};if(Case.B(a,1)!=c)throw new Exception("wrong receiver");
try{Case.B(a,2);throw new Exception("missing bounds");}catch(IndexOutOfRangeException){}
Console.WriteLine("RaycastAll slices: collider read once at index 1; null skips distance; replacement distance=23.5");
namespace UnityEngine{public class Collider{} public struct RaycastHit{public Func<Collider> Get;public float D;public bool Fail;public Collider collider=>Get();public float distance=>Fail?throw new Exception("early distance"):D;}}
class Case{\n'''+ '\n'.join(cases)+'}',encoding='utf8');print(run_case(tmp_path,runner).strip())


@pytest.mark.parametrize('change',['stride','index','element producer','offset'])
def test_decline_bad_element_evidence(shift_runtime,monkeypatch,change):
    m,il=shift_runtime;md=m.methods[25688];d=Decompiler(Lifter(il));d.lift_method(md,m.typedefs[md.declaring]);bs=d.L._blocks
    p=lambda:element_reads(d.L,md,bs,());dst=0x18070d2af;assert dst in p()
    if change=='element producer':monkeypatch.setitem(il.addr_candidates,0x182c9fed0,[])
    elif change=='offset':
        read=il.bin.read;monkeypatch.setattr(il.bin,'read',lambda a,n: read(a,n).replace(bytes.fromhex('10411c'),bytes.fromhex('10411b')) if a==0x182c90960 else read(a,n))
    else:
        addr=0x18070d2a4 if change=='stride' else 0x18070d29f
        b,k=next((b,k) for b in bs for k,i in enumerate(b.insns) if i.ip==addr);i=b.insns[k];raw=bytearray(il.bin.read(addr,i.len));raw[-1]^=1
        alt=list(Decoder(64,bytes(raw),ip=addr));assert len(alt)==1 and alt[0].len==i.len;monkeypatch.setattr(b,'insns',b.insns[:k]+alt+b.insns[k+1:])
    assert dst not in p()
