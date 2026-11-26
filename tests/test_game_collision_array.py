"""The array passed to GetParticles is the array allocated using the original module."""
import re

import pytest

from dotnet_case import run_case
from test_game_shift_shared_flags import body, shift_runtime

pytestmark=pytest.mark.game


def test_branched_collision_allocation_and_fill(body,tmp_path):
    cases=[]
    pattern=(r'UnityEngine\.ParticleSystem\.MainModule (\w+) = this\.(\w+)\.main /\* shared getter \*/;\s*'
             r'int (\w+) = \1\.maxParticles;\s*'
             r'UnityEngine\.ParticleSystem\.Particle\[\] (\w+) = new UnityEngine\.ParticleSystem\.Particle\[\3\];\s*'
             r'int (\w+) = this\.\2\.GetParticles\(\4\);')
    for name,va in [('GasCollisionSpawner',0x1806ef990),('ParticleCollisionSpawner',0x180580f90)]:
        text=body(name,'OnParticleCollision',va)
        assert 'sub_18088e4a0/*' not in text and 'GetParticles(new ' not in text
        arms=list(re.finditer(pattern,text)); assert arms
        for m in arms:
            n=len(cases)
            cases.append(f'public (ParticleSystem.Particle[],int) Run{n}() {{\n'+m[0]+f'\nreturn ({m[4]},{m[5]});\n}}')
    runner=tmp_path/'runner';runner.mkdir()
    (runner/'Program.cs').write_text('''using System;
using System.Collections.Generic;
using UnityEngine;
var c=new Case();
foreach(var run in new Func<(ParticleSystem.Particle[],int)>[]{'''+','.join(f'c.Run{i}' for i in range(len(cases)))+'''}) {
    var original=new ParticleSystem(); var replacement=new ParticleSystem();var log=new List<string>();
    c.ps=c.particleSystem=original; ParticleSystem.Particle[] filled=null;
    original.Open=()=>{log.Add("main");c.ps=c.particleSystem=replacement;};
    original.Capacity=()=>{log.Add("max");return 3;};
    replacement.Fill=a=>{log.Add("fill");filled=a; a[1].Tag=127;return 2;};
    var (result,n)=run();if(!ReferenceEquals(result,filled) || result.Length!=3 || result[1].Tag!=127 || n!=2 || string.Join(";",log)!="main;max;fill")
        throw new Exception("wrong receiver, new array or repeated fill");
    c.ps=c.particleSystem=original;log.Clear();original.Capacity=()=>{log.Add("max");throw new ApplicationException();};
    try {run();throw new Exception("missing getter failure");}catch(ApplicationException){}
    if(string.Join(";",log)!="main;max")throw new Exception("filled on size failure");
}
Console.WriteLine("original module read once; replacement particle system filled the same three-element array, count 2");
class Case {public ParticleSystem ps,particleSystem;\n'''+ '\n'.join(cases)+'''\n}
namespace UnityEngine {class ParticleSystem {
    public Action Open; public Func<int> Capacity; public Func<Particle[],int> Fill;
    public MainModule main {get {Open();return new MainModule(this);} }
    public readonly struct MainModule {readonly ParticleSystem ps;public MainModule(ParticleSystem ps)=>this.ps=ps;public int maxParticles=>ps.Capacity();}
    public struct Particle {public int Tag;}
    public int GetParticles(Particle[] a)=>Fill(a);
}}''',encoding='utf-8')
    print(run_case(tmp_path,runner).strip())


def test_conditional_fill_requires_no_return_to_allocation(shift_runtime,monkeypatch):
    from il2cpp import Decompiler, Lifter
    from il2cpp.copied_getter import array_fill_sites
    meta,il=shift_runtime; md=meta.methods[25375]; d=Decompiler(Lifter(il));l=d.L
    d.lift_method(md,meta.typedefs[md.declaring]); blocks=l._blocks
    producer=next(b for b in blocks if any(i.ip==0x1806efba9 for i in b.insns))
    use,=producer.succs
    assert l._array_module_frames.get(0x1806efba9)
    # Model a new loop edge from the fill back to the allocating block.
    monkeypatch.setattr(blocks[use],'succs',blocks[use].succs+[producer.bid])
    monkeypatch.setattr(producer,'preds',producer.preds+[use])
    monkeypatch.setattr(l,'_array_module_frames',{})
    allocs,counts=array_fill_sites(l,blocks,d._pad_bids,md)
    assert 0x1806efba9 not in l._array_module_frames
    assert not ({i.ip for i in producer.insns}&allocs or {i.ip for i in blocks[use].insns}&counts.keys())
