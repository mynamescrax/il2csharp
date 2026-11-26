"""Compile the two indexed position + distance predicates as emitted."""
import re

from iced_x86 import Decoder
import pytest

from dotnet_case import run_case
from il2cpp import Decompiler,Lifter
from il2cpp.indexed_binary import binary_sites
from test_game_shift_shared_flags import body,shift_runtime

pytestmark=pytest.mark.game


def test_both_distance_predicates_use_the_saved_intersection(body,tmp_path):
    source=body('ParticleCollisionSpawner','OnParticleCollision',0x180580f90)
    pattern=(r'(?P<read>UnityEngine.Vector3 (?P<p>\w+) = (?P<a>\w+)\[(?P<i>\w+)\]\.position /\* shared getter \*/;)\s*'
             r'(?:(?P<copy>\w+) = (?P=p);\s*)?(?P<call>float (?P<f>\w+) = UnityEngine.Vector3.Distance\((?P=p), (?P<v>\w+)\);)\s*'
             r'if \((?P<test>0\.1f > (?P=f))\)')
    sites=list(re.finditer(pattern,source));assert len(sites)==2
    methods=[]
    for n,s in enumerate(sites):
        assert re.search(r'UnityEngine.Vector3 '+s['v']+r' = \w+\.intersection /\* shared getter \*/;',source[:s.start()])
        methods.append(f'public static bool Check{n}(Particle[] {s["a"]},int {s["i"]},Vector3 {s["v"]}) {{\n'+
                       s['read']+'\n'+s['call']+f'\nreturn {s["test"]};}}')
    runner=tmp_path/'runner';runner.mkdir();(runner/'Program.cs').write_text('''using System;
using UnityEngine;
var saved=new Vector3(6f,-19f,4f);var a=new[]{new Particle{P=new Vector3(-8f,3f,39f)},new Particle{P=saved}};
foreach(var test in new Func<Particle[],int,Vector3,bool>[]{Case.Check0,Case.Check1}) {
    bool Eval(int index,Vector3 other){Vector3.N=0;var result=test(a,index,other);
        if(Vector3.N!=1 || !Vector3.A.Equals(a[index].P) || !Vector3.B.Equals(other))throw new Exception("wrong operands or evaluation count");return result;}
    if(Eval(0,saved)||!Eval(1,saved)||Eval(1,saved with{Y=-18f})||Eval(1,saved with{Z=5f}))throw new Exception("wrong lanes");
    a[1].P=default;if(Eval(1,new Vector3(0f,0f,0.1f)) || Eval(1,new Vector3(float.NaN,0,0)))throw new Exception("wrong comparison");a[1].P=saved;
    Console.WriteLine("fresh position + saved intersection; x/y/z, threshold equality and NaN verified");
}
namespace UnityEngine {public record struct Vector3(float X,float Y,float Z) {
public static int N;public static Vector3 A,B;public static float Distance(Vector3 a,Vector3 b){N++;A=a;B=b;
float x=a.X-b.X,y=a.Y-b.Y,z=a.Z-b.Z;return MathF.Sqrt(x*x+y*y+z*z);}}
public struct Particle {public Vector3 P;public Vector3 position=>P;}}
class Case {\n'''+ '\n'.join(methods)+'}',encoding='utf8');print(run_case(tmp_path,runner).strip())


@pytest.mark.parametrize('ip,delta',[(0x1805814d2,4),(0x180581472,4),(0x1805814c4,8)])
def test_disjoint_complete_distance_arguments_required(shift_runtime,monkeypatch,ip,delta):
    m,il=shift_runtime;md=m.methods[26545];d=Decompiler(Lifter(il));d.lift_method(md,m.typedefs[md.declaring]);bs=d.L._blocks
    plans=lambda:binary_sites(d.L,md,bs,d._pad_bids)[2]
    assert len(plans())==2
    b,j=next((b,j) for b in bs for j,i in enumerate(b.insns) if i.ip==ip);i=b.insns[j];raw=bytearray(il.bin.read(ip,i.len));raw[-1]^=delta
    replacement=list(Decoder(64,bytes(raw),ip=ip));assert len(replacement)==1 and replacement[0].len==i.len
    monkeypatch.setattr(b,'insns',b.insns[:j]+replacement+b.insns[j+1:]);assert list(plans())==[0x180581301]
