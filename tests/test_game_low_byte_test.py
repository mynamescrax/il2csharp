"""A low-byte TEST checks intersection, not equality of its operands."""
from pathlib import Path

import pytest

from dotnet_case import run_case
from il2cpp import Decompiler, Lifter
from il2cpp.emitter import Emitter
from test_game_shift_shared_flags import shift_runtime


pytestmark = pytest.mark.game


def test_focus_reads_console_even_on_loss_and_selects_only_on_both(shift_runtime, tmp_path):
    meta, il = shift_runtime
    method = meta.methods[24571]
    lines = []
    Emitter(il, str(tmp_path / 'out')).emit_method(method, meta.typedefs[method.declaring], lines, '    ')
    program = '''using System;
using System.Collections.Generic;
using System.Linq;
foreach (bool focus in new[]{false,true}) foreach (bool console in new[]{false,true})
foreach (string mode in new[]{"normal","busy","other tab","platform fault","deactivate fault","select fault","missing"}) {
    var c = new Computer(); var field = new InputField(); var trace = new List<string>();
    var fault = new ApplicationException();
    void Record(string step) { trace.Add(step); if (mode == step + " fault") throw fault; }
    UnityEngine.Application.Read = () => {
        Record("platform"); c.inputText = mode == "missing" ? null : field;
        c.interacting = mode != "busy"; c.selectedTabIndex = mode == "other tab" ? 1 : 0;
        return console;
    };
    field.Deactivate = keep => {
        if (keep || field.m_OnFocusSelectAll) throw new Exception("wrong deactivate arguments/state");
        Record("deactivate");
    };
    c.Select = () => Record("select");
    Exception ex = null; try {c.Run(focus);} catch (Exception e) {ex = e;}
    bool acts = focus && console && mode is not ("busy" or "other tab" or "platform fault");
    var wanted = new List<string>{"platform"};
    if (acts && mode != "missing") {
        wanted.Add("deactivate"); if (mode != "deactivate fault") wanted.Add("select");
    }
    bool expectedThrow = mode == "platform fault" || acts && mode.EndsWith(" fault");
    if (!trace.SequenceEqual(wanted) || field.m_OnFocusSelectAll == (acts && mode != "missing") ||
        (expectedThrow ? !ReferenceEquals(ex,fault) : acts && mode == "missing" ? ex is not NullReferenceException : ex != null))
        throw new Exception($"focus={focus},console={console},{mode}: {string.Join(',',trace)}",ex);
}
Console.WriteLine("whole focus callback: platform read, branch, field update, selection and faults");
namespace UnityEngine { public static class Application { public static Func<bool> Read; public static bool isConsolePlatform=>Read(); } }
class InputField { public bool m_OnFocusSelectAll=true; public Action<bool> Deactivate; public void DeactivateInputField(bool reset)=>Deactivate(reset); }
class Computer { public InputField inputText; public bool interacting; public int selectedTabIndex; public Action Select;
    void SelectInputTextIfNotAlreadySelected()=>Select(); public void Run(bool focus)=>OnApplicationFocus(focus);
''' + '\n'.join(lines) + '\n}'
    _run(tmp_path, program)


@pytest.mark.parametrize('first_mask', [7, 0x80, 0xff])
def test_two_mask_decisions_use_one_sample_and_ignore_high_bits(shift_runtime, tmp_path, first_mask, monkeypatch):
    # Only test the decision slice. All three continuations are opaque here;
    # packet construction is unrelated to the caller's TEST/Jcc arithmetic.
    meta, il = shift_runtime
    method = meta.methods[23693]
    dec = Decompiler(Lifter(il))
    if first_mask != 7:
        # Keep the native width and branch, vary only the literal byte.
        decode = dec._decode
        def change_mask(m):
            seq, rest = decode(m)
            seq = list(seq)
            j = next(j for j, i in enumerate(seq) if i.ip == 0x1805082c0)
            ins = seq[j].copy()
            assert ins.immediate8 == 7
            ins.immediate8 = first_mask
            seq[j] = ins
            return seq, rest
        monkeypatch.setattr(dec, '_decode', change_mask)
    body = dec.lift_method(method, meta.typedefs[method.declaring])
    read = next(i for i, s in enumerate(body) if 'GetLocalAuthorityMask()' in s)
    branch = next(i for i in range(read + 1, len(body)) if body[i].strip().startswith('else if ('))
    assert body[read + 1].strip().startswith('if (')
    assert 'NotifyLocalSimulationNotAllowed' in '\n'.join(body[read + 2:branch])
    assert 'this.Rpc_EventWhenLookedAt()' in body[branch + 2]
    slice_ = '\n'.join((body[read], body[read + 1], 'return 0;', body[branch], 'return 1;', 'return 2;'))
    program = '''using System;
var c=new Case(); int count=0;
foreach (int hi in new[]{int.MinValue,0x600,0x7fffff00,-256,0}) for (int lo=0;lo<256;lo++) {
    int sample=hi|lo; int before=count;
    c._object.Sample=()=>{count++;return sample;}; int actual=c.Decide();
    if (count!=before+1 || actual!=((lo&MASK)==0 ? 0 : (lo&1)!=0 ? 1 : 2)) throw new Exception($"{sample}: {actual}");
}
var fault=new ApplicationException();c._object.Sample=()=>throw fault;
try {c.Decide();throw new Exception("lost getter fault");} catch (ApplicationException e) when(ReferenceEquals(e,fault)) {}
Console.WriteLine("two decision heads: 1280 inputs and getter exception");
class Source {public Func<int> Sample;public int GetLocalAuthorityMask()=>Sample();}
class Case {public Source _object=new(); public int Decide(){\n''' + slice_ + '\n}}'
    _run(tmp_path, program.replace('lo&MASK', f'lo&{first_mask}'))


def _run(root: Path, program: str):
    runner = root / 'runner'
    runner.mkdir()
    (runner / 'Program.cs').write_text(program, encoding='utf8')
    print(run_case(root, runner).strip())


@pytest.fixture(scope='module')
def plans(shift_runtime):
    from il2cpp.low_byte_test import mask_sites
    meta, il = shift_runtime
    cases = {}
    for mi in (24571, 25334, 23937):
        m = meta.methods[mi]
        d = Decompiler(Lifter(il))
        d.lift_method(m, meta.typedefs[m.declaring])
        blocks = d.L._blocks
        cases[mi] = (blocks, lambda m=m, d=d, b=blocks: mask_sites(d.L, m, b, ()))
    return cases


def test_saved_mask_is_from_the_same_registered_call(plans):
    _, scan = plans[25334]
    sites, calls = scan()
    assert sites[0x1806e5893][1:] == (0x1806e588c, 8, 1)
    assert sites[0x1806e5933][1:] == (0x1806e588c, 8, 7)
    assert set(calls) == {0x1806e588c}
    # Raycast and button are two effectful producers. Do not reorder them
    # by treating the saved raycast as a freely re-evaluable Boolean arg.
    assert not plans[23937][1]()[0]


def test_parameter_named_like_a_snapshot_is_not_conflated(plans, shift_runtime, monkeypatch):
    meta, _ = shift_runtime
    p, = meta.method_params(meta.methods[24571])
    scan = plans[24571][1]
    assert scan()[0]
    monkeypatch.setattr(p, 'name', 't1000')
    assert scan() == ({}, {})


@pytest.mark.parametrize('case', ['saved wrong register', 'high byte', 'cmp', 'wrong Boolean slot', 'ambiguous producer'])
def test_declines_missing_operand_or_call_provenance(plans, shift_runtime, monkeypatch, case):
    from iced_x86 import Decoder, Register as R
    _, il = shift_runtime
    blocks, scan = plans[24571 if case == 'wrong Boolean slot' else 25334]
    if case == 'ambiguous producer':
        va = 0x1808a2490
        ids = il.addr_candidates[va]
        monkeypatch.setitem(il.addr_candidates, va, [*ids, *ids])
        assert scan() == ({}, {})
        return
    ip = {'saved wrong register': 0x1806e5891, 'high byte': 0x1806e5933,
          'cmp': 0x1806e5893, 'wrong Boolean slot': 0x1806a7581}[case]
    b, j = next((b, j) for b in blocks for j, i in enumerate(b.insns) if i.ip == ip)
    ins = b.insns[j].copy()
    if case == 'saved wrong register':
        ins.op1_register = R.ECX
    elif case == 'high byte':
        ins = Decoder(64, b'\x66\xf6\xc4\x07', ip=ip).decode()
        assert ins.op0_register == R.AH and ins.len == b.insns[j].len
    elif case == 'cmp':
        ins = Decoder(64, b'\x3c\x01', ip=ip).decode()
        assert ins.len == b.insns[j].len
    else:
        ins.op1_register = R.CL
    monkeypatch.setattr(b, 'insns', [*b.insns[:j], ins, *b.insns[j+1:]])
    sites, _ = scan()
    if case == 'saved wrong register':
        assert 0x1806e5893 in sites and 0x1806e5933 not in sites
    else:
        assert (0x1806a75b8 if case == 'wrong Boolean slot' else ip) not in sites
