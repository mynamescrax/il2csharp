import pytest
from iced_x86 import Decoder
from dotnet_case import run_case
from il2cpp import Decompiler,Lifter
from il2cpp.emitter import Emitter
from il2cpp.packed_projection import packed_projection
from test_game_shift_shared_flags import shift_runtime

pytestmark=pytest.mark.game


def test_projected_lanes_return_exact_bits(shift_runtime,tmp_path):
    meta,il=shift_runtime;em=Emitter(il,str(tmp_path/'out'));decls=[];checks=[];addrs=set()
    for j in (28927,28974,105761):
        m=meta.methods[j];td=meta.typedefs[m.declaring];lines=[];em.emit_method(m,td,lines,'    ')
        # The pathfinding helper is protected. Expose it from its declaring
        # class in the harness; leave the emitted signature and body intact.
        decls.append('class '+td.name+' {\n'+'\n'.join(lines)+f'\npublic static Vector2 Invoke(Vector3 v)=>{m.name}(v);'+'\n}');checks.append(f'Check({td.name}.Invoke(v),x,z);');addrs.add(m.addr)
    for j in (71455,72131):
        td=meta.typedefs[meta.methods[j].declaring];members=[];lanes='xyz' if td.name=='float3' else 'xyzw'
        for mi in meta.type_methods(td):
            m=meta.methods[mi];pair=m.name.removeprefix('get_')
            if m.name!='get_'+pair or len(pair)!=2 or any(c not in lanes for c in pair):continue
            # Accessor body through the same emitter path as a property.
            body=em._accessor_lines(m,td)
            if body and any('projected' in l for l in body):
                out=[];em._emit_accessor(out,'    ','get',m,body);members.append('public float2 '+pair+' {\n'+'\n'.join(out)+'\n}')
                checks.append(f'Check2(f{len(lanes)}.{pair},{pair[0]},{pair[1]});');addrs.add(m.addr)
        assert len(members)==len(lanes)**2
        decls.append('namespace Unity.Mathematics{public struct '+td.name+' {public float '+','.join(lanes)+';\n'+'\n'.join(members)+'\n}}')
    print(f'{len(checks)} projections at {len(addrs)} distinct native entries')
    src='''using System;using UnityEngine;using Unity.Mathematics;
float Float(uint x)=>BitConverter.Int32BitsToSingle(unchecked((int)x));uint Bits(float v)=>unchecked((uint)BitConverter.SingleToInt32Bits(v));
void Check(Vector2 v,float a,float b){if(Bits(v.x)!=Bits(a)||Bits(v.y)!=Bits(b))throw new Exception("wrong Vector2");}
void Check2(float2 v,float a,float b){if(Bits(v.x)!=Bits(a)||Bits(v.y)!=Bits(b))throw new Exception("wrong float2");}
foreach(var first in new uint[]{0x80000000,0x7fc12345,1,0xff800000}){float x=Float(first),y=Float(0x80000001),z=Float(0xffc54321),w=0.75f;
var v=new Vector3{x=x,y=y,z=z};var f3=new float3{x=x,y=y,z=z};var f4=new float4{x=x,y=y,z=z,w=w};\n'''+ '\n'.join(checks)+'''\n}Console.WriteLine("packed results match field bits including signed zero, subnormals and NaN payloads");
namespace UnityEngine {public struct Vector3{public float x,y,z;}public struct Vector2{public float x,y;public Vector2()=>throw new Exception("unexpected constructor");}}
namespace Unity.Mathematics {public struct float2{public float x,y;public float2()=>throw new Exception("unexpected constructor");}}
'''+ '\n'.join(decls)
    runner=tmp_path/'runner';runner.mkdir();(runner/'Program.cs').write_text(src,encoding='utf8');print(run_case(tmp_path,runner).strip())


@pytest.mark.parametrize('defect',['wrong result register','missing lane','unaligned field','hidden sret'])
def test_projection_declines_missing_bytes_or_wrong_abi(shift_runtime,monkeypatch,defect):
    meta,il=shift_runtime;m=meta.methods[28927];td=meta.typedefs[m.declaring];d=Decompiler(Lifter(il));d.eh=None;seq,_=d._decode(m)
    prove=lambda:packed_projection(d.L,m,td,seq,None);assert prove()
    if defect=='hidden sret':monkeypatch.setattr(m,'return_type',meta.method_params(m)[0].type)
    else:
        j,hexcode={'wrong result register':(3,'66480f7eca'),'missing lane':(2,'0f14ca'),'unaligned field':(0,'f30f104102')}[defect]
        i=seq[j];alt=Decoder(64,bytes.fromhex(hexcode),ip=i.ip).decode();assert alt.len==i.len;seq[j]=alt
    assert prove() is None
