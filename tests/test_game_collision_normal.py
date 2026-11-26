"""Compile the spawn loop's two collision-event reads through LookRotation."""
import re

import pytest

from dotnet_case import run_case
from il2cpp import Decompiler, Lifter
from test_game_shift_shared_flags import shift_runtime

pytestmark = pytest.mark.game


@pytest.fixture(scope='module')
def collision_method(shift_runtime):
    meta, il = shift_runtime
    md = meta.methods[26545]
    td = meta.typedefs[md.declaring]
    assert (td.name, md.name, md.addr) == ('ParticleCollisionSpawner', 'OnParticleCollision', 0x180580f90)
    return il, md, td


def _lift(collision_method):
    il, md, td = collision_method
    return '\n'.join(Decompiler(Lifter(il)).lift_method(md, td))


def _spawn_slice(text):
    look, = re.finditer(r'(\w+) = UnityEngine\.Quaternion\.LookRotation\([^;\n]+\);', text)
    # Bind the list and index from the collision query and loop header,
    # independently of the indexer expressions under test.
    heads = re.finditer(r'\.GetCollisionEvents\([^;\n]*, (\w+)\);\s+int (\w+) = 0;\s+do\s*\{',
                        text[:look.start()])
    head = list(heads)[-1]
    code = text[head.end():look.end()]
    assert code.count('.intersection /* shared getter */') == 1
    assert code.count('.normal /* shared getter */') == 1
    point, = re.findall(r'(\w+) = [^;\n]*\.intersection /\* shared getter \*/;', code)

    # Carry in the emitted types of hoisted locals. Leave every executable
    # statement in the cut intact, including any optional normal copy.
    decls = []
    for name in sorted(set(re.findall(r'^[ \t]*(\w+) =', code, re.M))):
        if re.search(rf'^[ \t]*[\w.]+ {name} =', code, re.M):
            continue
        decl = re.search(rf'^[ \t]*([\w.]+ {name})(?: = [^;]+)?;', text[:head.start()], re.M)
        assert decl, f'missing declaration for {name}'
        decls.append(decl[1] + ';')
    return (f'public static (Vector3, Quaternion) Run(List_1<ParticleCollisionEvent> {head[1]}, int {head[2]}) {{\n'
            + '\n'.join(decls) + code + f'\nreturn ({point}, {look[1]});\n}}')


def test_second_snapshot_normal_reaches_look_rotation(collision_method, tmp_path):
    method = _spawn_slice(_lift(collision_method))
    runner = tmp_path / 'runner'
    runner.mkdir()
    (runner / 'Program.cs').write_text('''using System;
using System.Collections.Generic;
using System.Linq;
using UnityEngine;

var order = new[] { "index1", "first.intersection", "index2", "second.normal", "look" };
foreach (int index in new[] { 0, 2 })
foreach (string stop in order.Append("ok").Append("remove")) {
    var events = new List_1<ParticleCollisionEvent>();
    var trace = new List<string>();
    var fault = new ApplicationException(stop);
    void Step(string stage) {
        trace.Add(stage);
        if (stage == stop) throw fault;
    }
    Vector3 point = new(-1.5f, 2, 3.25f), normal = new(11, -17.5f, 23.75f);
    var second = new ParticleCollisionEvent(new(4, 5, 6), normal, key => Step("second." + key));
    var first = new ParticleCollisionEvent(point, new(7, 8, 9), key => {
        Step("first." + key);
        if (stop == "remove") events.RemoveAt(index); else events[index] = second;
    });
    for (int i = 0; i < index; ++i) events.Add(default);
    events.Add(first);
    int reads = 0;
    events.Read = i => {
        if (i != index) throw new Exception("wrong index: " + i);
        Step("index" + ++reads);
    };
    Quaternion.Look = forward => {
        if (forward != normal) throw new Exception("wrong LookRotation XYZ: " + forward);
        Step("look");
        return new Quaternion(97);
    };
    try {
        var result = Case.Run(events, index);
        if (stop != "ok" || result != (point, new Quaternion(97)))
            throw new Exception("missing fault or wrong intersection/rotation: " + result);
    } catch (ApplicationException ex) when (ReferenceEquals(ex, fault)) { }
      catch (ArgumentOutOfRangeException) when (stop == "remove") { }
    int count = stop switch { "ok" => order.Length, "remove" => 3, _ => Array.IndexOf(order, stop) + 1 };
    if (!trace.SequenceEqual(order.Take(count))) throw new Exception(stop + ": " + string.Join(",", trace));
}
namespace System.Collections.Generic {
    class List_1<T> : List<T> {
        public Action<int> Read;
        public new T this[int i] {
            get { Read(i); T snapshot = base[i]; base[i] = default; return snapshot; }
            set { base[i] = value; }
        }
    }
}
namespace UnityEngine {
    record struct Vector3(float x, float y, float z);
    record struct ParticleCollisionEvent(Vector3 Point, Vector3 Surface, Action<string> Trace) {
        public Vector3 intersection { get { Trace("intersection"); return Point; } }
        public Vector3 normal { get { Trace("normal"); return Surface; } }
    }
    record struct Quaternion(int Id) {
        public static Func<Vector3, Quaternion> Look;
        public static Quaternion LookRotation(Vector3 forward) => Look(forward);
    }
}
class Case {
''' + method + '\n}', encoding='utf-8')
    run_case(tmp_path, runner)


def _mutate_byte(collision_method, monkeypatch, address, old, new):
    il, _, _ = collision_method
    offset = il.bin.va2off(address)
    raw = memoryview(il.bin.d)
    assert raw[offset] == old
    monkeypatch.setattr(il.bin, 'd', b''.join([raw[:offset], bytes([new]), raw[offset + 1:]]))


@pytest.mark.parametrize('address,old,new', [
    pytest.param(0x1805811a9, 0x98, 0x88, id='second-event-copy-repeats-first-tile'),
    pytest.param(0x182b95b67, 0x14, 0x10, id='normal-leaf-reads-y-instead-of-z'),
])
def test_incomplete_event_or_getter_keeps_shared_call(collision_method, monkeypatch, address, old, new):
    _mutate_byte(collision_method, monkeypatch, address, old, new)
    text = _lift(collision_method)
    assert text.count('.intersection /* shared getter */') == 2
    assert '.normal /* shared getter */' not in text
    assert 'sub_182b95b60/*shared body,' in text


def test_changed_z_copy_does_not_forward_whole_normal(collision_method, monkeypatch):
    def forwards_normal(text):
        look, = re.finditer(r'UnityEngine\.Quaternion\.LookRotation\(([^;]+)\);', text)
        prop = '.normal /* shared getter */'
        # Accept a direct argument, a getter result local, or a copy of it.
        aliases = set()
        for name, rhs in re.findall(r'\b(\w+) = ([^;\n]+);', text[:look.start()]):
            if rhs.endswith(prop) or rhs in aliases:
                aliases.add(name)
            else:
                aliases.discard(name)
        return look[1].endswith(prop) or look[1] in aliases

    assert forwards_normal(_lift(collision_method))
    # The getter is intact, but the LookRotation argument now holds X,Y,Y.
    _mutate_byte(collision_method, monkeypatch, 0x1805811d8, 8, 4)
    assert not forwards_normal(_lift(collision_method))
