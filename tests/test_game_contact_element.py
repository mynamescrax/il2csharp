"""Exact-build pin for the ContactPoint value copy in ThrownObject.OnCollisionEnter."""
import re

import pytest

from dotnet_case import run_case
from il2cpp import Decompiler, Lifter
from test_game_shift_shared_flags import shift_runtime

pytestmark = pytest.mark.game


@pytest.fixture(scope='module')
def contact_method(shift_runtime):
    meta, il = shift_runtime
    md = meta.methods[28219]
    td = meta.typedefs[md.declaring]
    assert (td.name, md.name, md.addr) == ('ThrownObject', 'OnCollisionEnter', 0x18060ab70)
    return il, md, td


def _lift(contact_method):
    il, md, td = contact_method
    return '\n'.join(Decompiler(Lifter(il)).lift_method(md, td))


def _spawn_slices(text):
    # Delimit by the surrounding guard, independently of the code being tested.
    # The structurer can emit the same native block on more than one path.
    arms = list(re.finditer(r'^(?P<indent>[ \t]*)if \(this\.spawnsExtraObjectOnHit\)\n'
                            r'(?P=indent)\{\n.*?^(?P=indent)\}$', text, re.M | re.S))
    assert arms and len(arms) == text.count('this.Rpc_CMD_SpawnObj(')
    methods = []
    for n, arm in enumerate(arms):
        code = arm[0]
        assert code.count('this.Rpc_CMD_SpawnObj(') == 1
        # Bring in the original types of locals hoisted outside this guard;
        # leave all executable statements inside it untouched.
        decls = []
        for name in sorted(set(re.findall(r'^[ \t]*(\w+) =', code, re.M))):
            decl = rf'^[ \t]*([\w.]+(?:\[\])? {name})(?= =|;)'
            if not re.search(decl, code, re.M):
                found = re.findall(decl, text[:arm.start()], re.M)
                assert found, f'missing declaration for {name}'
                decls.append(found[-1] + ';')
        body = '\n'.join(decls + [code])
        # Accept indexing either the getter or its result local. The runtime
        # trace below checks the source of the array and both getter receivers.
        plain = re.sub(r'\s*/\*[^*]*\*/', '', body)
        snapshots = re.findall(r'\b(\w+) = (?:collision\.contacts|\w+)\[0\];', plain)
        assert len(snapshots) == 1, f'expected one contact snapshot:\n{code}'
        assert re.search(rf'\bContactPoint {snapshots[0]}\b', plain)
        methods.append(f'public void Run{n}(Collision collision) {{\n{body}\n}}')
    return methods


def test_spawn_reads_point_and_normal_from_one_value(contact_method, tmp_path):
    methods = _spawn_slices(_lift(contact_method))
    delegates = ', '.join(f'target.Run{i}' for i in range(len(methods)))
    runner = tmp_path / 'runner'
    runner.mkdir()
    (runner / 'Program.cs').write_text('''using System;
using System.Collections.Generic;
using System.Linq;
using UnityEngine;

var target = new ThrownObject();
var order = new[] { "contacts", "point", "normal", "look", "spawn" };
foreach (var run in new Action<Collision>[] { ''' + delegates + ''' })
foreach (var mode in order.Concat(new[] { "ok", "null collision", "null contacts", "empty" })) {
    var trace = new List<string>();
    var fault = new ApplicationException(mode);
    void Step(string name) { trace.Add(name); if (name == mode) throw fault; }
    Vector3 point = new(-1.25f, 5.5f, 9), normal = new(11, -17.75f, 23.5f);
    Quaternion rotation = new(31, -37.5f, 41.25f, -43);
    var other = new ContactPoint(default, default, key => throw new Exception("wrong element: " + key));
    var contacts = new[] { other, other };
    contacts[0] = new ContactPoint(point, normal, key => {
        Step(key);
        if (key == "point") contacts[0] = other; // a subsequent ref/reload sees the replacement
    });
    var collision = new Collision(() => {
        Step("contacts");
        return mode switch { "empty" => Array.Empty<ContactPoint>(), "null contacts" => null, _ => contacts };
    });
    Quaternion.Look = v => {
        if (v != normal) throw new Exception("wrong normal XYZ: " + v);
        Step("look"); return rotation;
    };
    target.Spawn = (p, q) => {
        if (p != point || q != rotation) throw new Exception($"wrong RPC arguments: {p}, {q}");
        Step("spawn");
    };
    target.spawnsExtraObjectOnHit=false;run(null);target.spawnsExtraObjectOnHit=true;
    target.alreadyHitSomething=true;run(null);target.alreadyHitSomething=false;
    if(trace.Count!=0)throw new Exception("contact read outside its guards");
    try {
        run(mode == "null collision" ? null : collision);
        if (mode != "ok") throw new Exception("missing exception: " + mode);
    } catch (ApplicationException e) when (ReferenceEquals(e, fault)) { }
      catch (NullReferenceException) when (mode == "null collision" || mode == "null contacts") { }
      catch (IndexOutOfRangeException) when (mode == "empty") { }
    int count = mode switch { "ok" => order.Length, "null collision" => 0, "null contacts" or "empty" => 1,
                              _ => Array.IndexOf(order, mode) + 1 };
    if (!trace.SequenceEqual(order.Take(count))) throw new Exception(mode + ": " + string.Join(",", trace));
}
namespace UnityEngine {
    record struct Vector3(float x, float y, float z);
    record struct Quaternion(float x, float y, float z, float w) {
        public static Func<Vector3, Quaternion> Look;
        public static Quaternion LookRotation(Vector3 v) => Look(v);
    }
    record struct ContactPoint(Vector3 P, Vector3 N, Action<string> Read) {
        public Vector3 point { get { Read("point"); return P; } }
        public Vector3 normal { get { Read("normal"); return N; } }
    }
    class Collision(Func<ContactPoint[]> getContacts) {
        public ContactPoint[] contacts => getContacts();
    }
}
class ThrownObject {
    public bool spawnsExtraObjectOnHit = true, alreadyHitSomething = false;
    public Action<Vector3, Quaternion> Spawn;
    void Rpc_CMD_SpawnObj(Vector3 point, Quaternion rotation) => Spawn(point, rotation);
''' + '\n'.join(methods) + '\n}', encoding='utf-8')
    run_case(tmp_path, runner)


@pytest.mark.parametrize('address,old,new,rejected', [
    pytest.param(0x18060adc1, 0x18, 0x1c, ('point', 'normal'), id='check-is-not-array-length'),
    pytest.param(0x18060adeb, 0x40, 0x30, ('point', 'normal'), id='duplicate-final-element-tile'),
    pytest.param(0x18060ae00, 0x60, 0x70, ('normal',), id='normal-receiver-inside-snapshot'),
    pytest.param(0x182b95b67, 0x14, 0x10, ('normal',), id='normal-getter-repeats-y'),
])
def test_changed_native_proof_keeps_shared_getter(contact_method, monkeypatch, address, old, new, rejected):
    il, _, _ = contact_method
    off = il.bin.va2off(address)
    raw = memoryview(il.bin.d)
    assert raw[off] == old
    monkeypatch.setattr(il.bin, 'd', b''.join([raw[:off], bytes([new]), raw[off + 1:]]))
    text = _lift(contact_method)
    for prop in rejected:
        _assert_unresolved(text, prop)


def _assert_unresolved(text, prop):
    target = {'point': '1808a5780', 'normal': '182b95b60'}[prop]
    assert not re.search(rf'\.{prop}\b', text)
    assert f'sub_{target}/*shared body,' in text


def test_same_size_but_different_getter_return_declines(contact_method, monkeypatch):
    il, _, _ = contact_method
    getter = il.meta.methods[125436]
    assert (il.typedef_full(getter.declaring), getter.name) == ('UnityEngine.ContactPoint', 'get_normal')
    other, = (td for td in il.meta.typedefs if (td.namespace, td.name) == ('UnityEngine', 'Vector3Int'))
    assert il.value_type_size(other.index) == 12
    monkeypatch.setattr(getter, 'return_type', other.byval)
    _assert_unresolved(_lift(contact_method), 'normal')


def test_direct_call_to_virtual_sink_requires_dispatch_proof(contact_method,monkeypatch):
    il,_,_=contact_method;target=il.meta.methods[28220]
    monkeypatch.setattr(target,'flags',target.flags|0x40)
    _assert_unresolved(_lift(contact_method),'normal')
