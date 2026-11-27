"""Both particle loops in MethodDef 26545 read position from the filled array."""
import re

import pytest
from iced_x86 import Decoder

from dotnet_case import run_case
from il2cpp import Decompiler, Lifter
from test_game_shift_shared_flags import shift_runtime

pytestmark = pytest.mark.game

_VECTOR = r'(?:UnityEngine\.)?Vector3'
_FILL = re.compile(r'\.GetParticles\((\w+)\);')
_POSITION = re.compile(
    rf'^[ \t]*(?:(?P<type>{_VECTOR}) )?(?P<result>\w+) = '
    r'(?P<array>\w+)\[(?P<index>\w+)\]\.position /\* shared getter \*/;', re.M)


def _filled_aliases(segment,root):
    """Only copies of the filled array, including loop-carried copy cycles.
    Require every write to every accepted name to be a bare reference copy;
    a later reassignment to another producer invalidates the entire chain."""
    writes={};decls=[];ty=r'UnityEngine\.ParticleSystem\.Particle\[\]'
    rx=re.compile(r'^(?:('+ty+r') )?(\w+) = ([^;]+);$')
    for line in segment.splitlines():
        m=rx.fullmatch(line.strip())
        if not m:continue
        dst,src=m[2],m[3];writes.setdefault(dst,set()).add(src)
        if m[1]:decls.append((dst,src,line.strip()))
    assert root not in writes
    known={root};prefix={root:[]}
    for dst,src,line in decls:
        if src in prefix:known.add(dst);prefix[dst]=prefix[src]+[line]
    while True:
        bad={n for n in known-{root} if not writes[n]<=known}
        if not bad:break
        known-=bad
    return {n:prefix[n] for n in known}


@pytest.fixture(scope='module')
def collision_method(shift_runtime):
    meta, il = shift_runtime
    md = meta.methods[26545]
    td = meta.typedefs[md.declaring]
    assert (td.name, md.name) == ('ParticleCollisionSpawner', 'OnParticleCollision')
    return il, md, td


def test_indexed_positions_on_the_filled_arrays(collision_method, tmp_path):
    il, md, td = collision_method
    text = '\n'.join(Decompiler(Lifter(il)).lift_method(md, td))
    fills = list(_FILL.finditer(text))
    assert len(fills) == len(list(_POSITION.finditer(text))) == 2
    methods = []
    for n, fill in enumerate(fills):
        end = fills[n + 1].start() if n + 1 < len(fills) else len(text)
        getter, = _POSITION.finditer(text, fill.end(), end)
        # Bind the inputs independently of the read under test. In particular,
        # the outer collision-event loop has a different, live index here.
        latch = re.search(r'^\s*(\w+) \+= 1;', text[getter.end():end], re.M)
        aliases=_filled_aliases(text[fill.end():end],fill[1]);assert getter['array'] in aliases
        assert latch and getter['index']==latch[1]
        result = getter['result']
        decl = ''
        if not getter['type']:
            separate = re.search(rf'\b{_VECTOR} {re.escape(result)}\b', text[:getter.start()])
            assert separate, f'missing Vector3 declaration for {result}'
            decl = separate[0] + ';'
        methods.append(f'public static Vector3 Read{n}(Particle[] {fill[1]}, int {latch[1]}) {{\n'
                       + '\n'.join(aliases[getter['array']]) + f'\n{decl}\n{getter[0]}\nreturn {result};\n}}')

    runner = tmp_path / 'runner'
    runner.mkdir()
    (runner / 'Program.cs').write_text('''using System;
using UnityEngine;
using Particle = UnityEngine.ParticleSystem.Particle;
foreach (var read in new Func<Particle[], int, Vector3>[] { Case.Read0, Case.Read1 }) {
    Vector3 a = new(1.25f, -2, 3), b = new(-7, 11.5f, 23), c = new(41, 42, -43.75f);
    var first = new Particle[] { new(a), new(b) };
    var other = new Particle[] { new(b), new(c) };
    if (read(first, 1) != b || read(other, 1) != c || read(first, 0) != a)
        throw new Exception("wrong array, index or XYZ");

    foreach (int index in new[] { -1, first.Length }) {
        try { read(first, index); throw new Exception("missing array bounds check"); }
        catch (IndexOutOfRangeException) { }
    }
    try { read(null, 0); throw new Exception("missing null check"); }
    catch (NullReferenceException) { }
    var fault = new ApplicationException("position");
    other[0].Fault = fault;
    try { read(other, 0); throw new Exception("missing getter failure"); }
    catch (ApplicationException ex) when (ReferenceEquals(ex, fault)) { }
    if ((first[0].Reads, first[1].Reads, other[0].Reads, other[1].Reads) != (1, 1, 1, 1))
        throw new Exception("getter must run once on each selected array element");
}
Console.WriteLine("Both position slices preserved array identity, index, XYZ and faults");
namespace UnityEngine {
    record struct Vector3(float X, float Y, float Z);
    class ParticleSystem {
        public struct Particle {
            readonly Vector3 value;
            public int Reads;
            public Exception Fault;
            public Particle(Vector3 value) { this.value = value; }
            public Vector3 position { get { ++Reads; if (Fault != null) throw Fault; return value; } }
        }
    }
}
class Case {
''' + '\n'.join(methods) + '\n}', encoding='utf-8')
    print(run_case(tmp_path, runner).strip())


@pytest.mark.parametrize('ip, replacement', [
    pytest.param(0x1805812e0, '48 69 d0 80 00 00 00', id='stride-128-instead-of-132'),
    pytest.param(0x180581490, '3b 5f 1c', id='check-non-length-field'),
    pytest.param(0x18058149c, '48 8d 4d 7f', id='out-beyond-frame'),
])
def test_indexed_position_declines_changed_native_setup(collision_method, monkeypatch, ip, replacement):
    il, md, td = collision_method
    dec = Decompiler(Lifter(il))
    decode = dec._decode

    def changed(method):
        seq, skip = decode(method)
        j, = (j for j, ins in enumerate(seq) if ins.ip == ip)
        patched, = Decoder(64, bytes.fromhex(replacement), ip=ip)
        assert not patched.is_invalid and patched.next_ip == seq[j].next_ip
        return seq[:j] + [patched] + seq[j + 1:], skip

    monkeypatch.setattr(dec, '_decode', changed)
    text = '\n'.join(dec.lift_method(md, td))
    # One loop still resolves. Check the fallback on the other particle array,
    # not the unrelated collision-event getter calls that share this address.
    good, = _POSITION.finditer(text);fills=list(_FILL.finditer(text));assert len(fills)==2
    # 0x5812fc is the later spawn arm in structured order; 0x5814bc
    # is the earlier cleanup arm. Check each array separately, even if the
    # structurer retained an independent local on the loop backedge.
    for n,fill in enumerate(fills):
        end=fills[n+1].start() if n==0 else len(text);part=text[fill.end():end];aliases=_filled_aliases(part,fill[1])
        if n==int(ip==0x1805812e0):
            assert not _POSITION.search(part) and any(re.search(r'sub_1808a5780/\*shared body,[^;\n]*\b'+re.escape(name)+r'\b',part) for name in aliases)
        else:assert fill.end()<good.start()<end and good['array'] in aliases
