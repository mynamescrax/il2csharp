"""Nested Win64 owner forwarder: protected access, nulls and single evaluation."""
from types import SimpleNamespace as NS

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
