"""The emitted point-to-position slice must transport all three lanes."""
import re

import pytest
from iced_x86 import Decoder

from dotnet_case import run_case
from il2cpp import Decompiler,Lifter
from il2cpp.emitter import Emitter
from il2cpp.joined_sret import joined_srets
from test_game_shift_shared_flags import shift_runtime

pytestmark=pytest.mark.game


def test_point_join_preserves_snapshot_and_full_value(shift_runtime,tmp_path):
    meta,il=shift_runtime;md=meta.methods[25657];td=meta.typedefs[md.declaring];out=tmp_path/'out'
    Emitter(il,str(out))._emit_one_top(td,meta.images[md.image],td.name)
    text=next(out.rglob('InventoryManager.cs')).read_text(encoding='utf8')
    assert 'sub_1808a5780/' not in text
    slices=list(re.finditer(r'(\w+) = this\.(\w+);\s*(\w+) = (\w+)\.point /\* shared getter \*/;\s*'
                            r'(\w+) = \3;\s*\1\.position = \3;',text))
    assert len(slices)==12 and len({s[2] for s in slices})==4
    methods=[];checks=[];fields=set()
    for k,part in enumerate(slices):
        dest,field,point,hit,copy=part.groups();fields.add(field)
        # Keep the actual lines from the emitter, supplying only their enclosing locals.
        methods.append(f'public void Case{k}(RaycastHit {hit}) {{Transform {dest};Vector3 {point},{copy};\n'+part[0]+'\n}')
        checks.append(f'm.Check(m.Case{k},t=>m.{field}=t);')
    source='''using System;
var m=new InventoryManager();\n'''+ '\n'.join(checks)+'''
Console.WriteLine("12 emitted slices: original destination; 3 lanes bit-identical; null and getter-fault order verified");
struct Vector3 {public float X,Y,Z;public Vector3(float x,float y,float z){X=x;Y=y;Z=z;}}
struct RaycastHit {public Vector3 Point,Normal;public Action Read;public Vector3 point{get{Read();return Point;}}}
class Transform {public int Count;public Vector3 Last; public Vector3 position{set{Last=value;Count++;}}}
class InventoryManager {\n'''+ '\n'.join('public Transform '+f+';' for f in sorted(fields))+ '\n'+ '\n'.join(methods)+'''
public void Check(Action<RaycastHit> apply, Action<Transform> set){
    var target=new Transform();var other=new Transform();int reads=0;
    var v=new Vector3(-1.25f,BitConverter.Int32BitsToSingle(unchecked((int)0x80000000)),19.875f);
    var hit=new RaycastHit {Point=v, Normal=new Vector3(9,8,7), Read=()=>{reads++;set(other);}};
    set(target);apply(hit);
    if(reads!=1||target.Count!=1||other.Count!=0||target.Last.X!=v.X||BitConverter.SingleToInt32Bits(target.Last.Y)!=BitConverter.SingleToInt32Bits(v.Y)||target.Last.Z!=v.Z)throw new Exception("corrupt value or stale destination");
    set(null);try{apply(hit);throw new Exception("missing null check");}catch(NullReferenceException){}
    if(reads!=2||other.Count!=0)throw new Exception("reordered getter");
    var failure=new Exception();set(target);hit.Read=()=>throw failure;try{apply(hit);throw new Exception("missing fault");}catch(Exception e) when(ReferenceEquals(e,failure)){}
    if(target.Count!=1)throw new Exception("setter ran on getter failure");
}}'''
    runner=tmp_path/'runner';runner.mkdir();(runner/'Program.cs').write_text(source,encoding='utf8');print(run_case(tmp_path,runner).strip())


@pytest.fixture(scope='module')
def inventory_blocks(shift_runtime):
    meta,il=shift_runtime;d=Decompiler(Lifter(il));m=meta.methods[25657];d.lift_method(m,meta.typedefs[m.declaring]);return d,m


@pytest.mark.parametrize('change',['different out slot','bad result edge','partial z copy','candidate removed','failed raycast edge','result home reread'])
def test_point_join_declines_unproved_home(inventory_blocks,monkeypatch,change):
    d,m=inventory_blocks;il=d.L.il;blocks=d.L._blocks;ip=0x1806fb670
    plan=lambda:joined_srets(d.L,m,blocks,())[2]
    assert plan()[ip]==125659
    if change=='candidate removed':
        target=0x1808a5780;monkeypatch.setitem(il.addr_candidates,target,[x for x in il.addr_candidates[target] if x!=('method',125659)])
    else:
        at={'different out slot':0x1806fab0c,'bad result edge':0x1806fb65b,'partial z copy':0x1806fb687,'failed raycast edge':0x1806fab43,'result home reread':0x180707787}[change]
        b=next(b for b in blocks if any(i.ip==at for i in b.insns));j=next(j for j,i in enumerate(b.insns) if i.ip==at);i=b.insns[j];raw=bytearray(il.bin.read(at,i.len))
        if change=='result home reread':raw[-4:]=(0x1798+256).to_bytes(4,'little')
        elif change=='failed raycast edge':raw[1]^=1
        else:raw[-1]^=4
        patched=list(Decoder(64,bytes(raw),ip=at));assert len(patched)==1 and patched[0].len==i.len
        monkeypatch.setattr(b,'insns',b.insns[:j]+patched+b.insns[j+1:])
    assert ip not in plan()
