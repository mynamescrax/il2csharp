"""Nested Win64 owner forwarder: protected access, nulls and single evaluation."""
from types import SimpleNamespace as NS

import re

import pytest

from dotnet_case import run_case
from il2cpp import Lifter
from il2cpp.shared_field import nested_field_tail
from test_game_shift_shared_flags import body, shift_runtime

pytestmark = pytest.mark.game


def test_nested_owner_getter_executes(body, tmp_path):
    lifted = body('LegRedirectHelper', 'get_LA', 0x180697ab0)
    assert 'shared field read' in lifted and 'sub_' not in lifted
    runner = tmp_path/'runner'; runner.mkdir()
    (runner/'Program.cs').write_text('''using System;
var original = new Animator();
var replaced = new Animator();
var first = new Module(original); var next = new Module(replaced);
int reads = 0;
var helper = new Module.Helper(() => ++reads == 1 ? first : next);
if (!ReferenceEquals(helper.LA, original) || reads != 1) throw new Exception("evaluated parent twice");
if (!ReferenceEquals(helper.LA, replaced) || reads != 2) throw new Exception("cached parent");
if (new Module.Helper(() => new Module(null)).LA != null) throw new Exception("null owner");
try { _ = new Module.Helper(() => null).LA; throw new Exception("accepted null parent"); }
catch (NullReferenceException) { }
Console.WriteLine("protected Owner: original, replacement, null owner; null parent throws");
class Animator { }
class ModuleBase { protected Animator Owner { get; } public ModuleBase(Animator a) => Owner = a; }
class Module : ModuleBase {
    public Module(Animator a) : base(a) { }
    public class Helper {
        readonly Func<Module> read;
        public Helper(Func<Module> read) => this.read = read;
        Module parent => read();
        public Animator LA { get {\n''' + lifted + '\n} } } }', encoding='utf-8')
    print(run_case(tmp_path, runner).strip())


@pytest.mark.parametrize('change', ['unrelated receiver', 'hidden member', 'different null arm', 'wrong return ABI'])
def test_nested_owner_declines(shift_runtime, monkeypatch, change):
    meta, il = shift_runtime; lift = Lifter(il)
    m = meta.methods[30190]; lift._current_method = m
    ins = NS(ip=m.addr + 19, near_branch_target=0x180513390)
    args = ['this.parent', '0']
    assert nested_field_tail(lift, ins, args)
    if change == 'unrelated receiver':
        monkeypatch.setattr(il, '_nested_owner', lambda ti: None)
    elif change == 'hidden member':
        # A derived field/property/method can hide the base getter even when
        # the leaf still reads the very same native offset.
        derived = meta.typedefs[il._nested_owner(m.declaring)]
        monkeypatch.setattr(meta.methods[next(iter(meta.type_methods(derived)))], 'name', 'Owner')
    elif change == 'different null arm':
        old = il.bin.read
        def read(p, n):
            data = old(p, n)
            return data[:11]+b'\x75'+data[12:] if (p,n)==(m.addr,30) else data
        monkeypatch.setattr(il.bin,'read',read)
    else:
        monkeypatch.setattr(m,'return_type',next(i for i,t in enumerate(il.types) if t and il._closed_type_key(t)==(8,0)))
    assert nested_field_tail(lift, ins, args) is None


def test_shared_owner_copies_all_three_up_components(body, tmp_path):
    getter=body('LegsAnimator','get_Up',0x18066e640)
    caller=body('LAM_AutoGroundAlignBodyMatrix','OnLateUpdatePreApply',0x18068bbc0)
    arm=re.search(r'FIMSpace\.FProceduralAnimation\.LegsAnimator (\w+) = base.Owner;\s+this.averageNormal = \1.Up;',caller)
    assert arm and getter=='return this._worldUpAxisVector;'
    runner=tmp_path/'runner';runner.mkdir()
    (runner/'Program.cs').write_text('''using System;
using FIMSpace.FProceduralAnimation;
var before=new V(-3.25f,7,11); var after=new V(111,222,333);
var m=new Module(); int reads=0;
m.Read=()=>new LegsAnimator(++reads==1?before:after);
m.Copy(); if(reads!=1 || m.Result!=before)throw new Exception("lost snapshot/lane");
m.Copy(); if(reads!=2 || m.Result!=after)throw new Exception("reused snapshot");
m.Read=()=>null;try { m.Copy(); throw new Exception("accepted null"); }catch(NullReferenceException) { }
if(m.Result!=after)throw new Exception("partial write on throw"); Console.WriteLine("Up: (-3.25,7,11), (111,222,333); null leaves destination unchanged");
record struct V(float X,float Y,float Z);
namespace FIMSpace.FProceduralAnimation {
    class LegsAnimator {private V _worldUpAxisVector; public LegsAnimator(V initial)=>_worldUpAxisVector=initial;
        public V Up {get {\n''' + getter + '''\n}} }
}
class Base {public Func<LegsAnimator> Read; protected LegsAnimator Owner=>Read();}
class Module : Base {private V averageNormal; public V Result=>averageNormal; public void Copy(){\n'''+arm[0]+'\n}}',encoding='utf-8')
    print(run_case(tmp_path,runner).strip())


@pytest.mark.parametrize('defect',['returns x twice','noncontiguous destination','virtual override'])
def test_public_vector_copy_declines_other_getters(shift_runtime,monkeypatch,defect):
    from il2cpp.vector_field_copy import vector_field_getter
    meta,il=shift_runtime; lift=Lifter(il); m=meta.methods[29667]
    assert vector_field_getter(lift,m)==('this._worldUpAxisVector','Up',0x474)
    if defect=='virtual override':
        monkeypatch.setattr(m,'flags',m.flags|0x40)
    else:
        original=il.bin.read
        def read(p,n):
            data=original(p,n)
            if (p,n)!=(m.addr,25): return data
            if defect=='returns x twice': return data[:2]+data[10:14]+data[6:]
            return data[:20]+b'\x04'+data[21:]
        monkeypatch.setattr(il.bin,'read',read)
    assert vector_field_getter(lift,m) is None
