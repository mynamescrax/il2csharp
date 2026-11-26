"""Structured-loop regressions: header replay and legal shared tails."""
import sys
from pathlib import Path

from iced_x86 import Decoder

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_native_values import lifter

from il2cpp import Block, Decompiler


def _insn(ip):
    return Decoder(64, b"\x90", ip=ip).decode()


def _block(bid, *, stmts=(), term=("stop",), cond=None, succs=(), preds=()):
    block = Block(bid, [_insn(0x1000 + bid * 0x10)])
    block.stmts = list(stmts)
    block.term = term
    block.cond = cond
    block.succs = list(succs)
    block.preds = list(preds)
    return block


def _decompiler(blocks, header, body, latch):
    dec = Decompiler(lifter())
    dec.loop_of_hdr = {header: (set(body), latch)}
    dec.rpo = list(range(len(blocks)))
    dec.pdom = dec._postdominators(blocks, dec.rpo, set(range(len(blocks))))
    dec.phi_copies = {}
    dec._sw_depth = 0
    dec._seh_regions = []
    dec._bstack = []
    dec._pclose = []
    dec._pad_bids = set()
    dec.eh = None
    dec.ip2bid = {block.insns[0].ip: block.bid for block in blocks}
    return dec


def test_header_work_and_refill_arm_execute_inside_each_iteration():
    # header: value = source; if (value != 0) join; else refill; join...
    blocks = [
        _block(0, stmts=["var t0 = source;"], term=("jcc", 2, 1),
               cond="t0 != 0", succs=(2, 1), preds=(3,)),
        _block(1, stmts=["t0 = Refill();"], term=("fall", 2),
               succs=(2,), preds=(0,)),
        _block(2, term=("jcc", 4, 3), cond="t0 == 0",
               succs=(4, 3), preds=(0, 1)),
        _block(3, stmts=["Tick();"], term=("jmp", 0),
               succs=(0,), preds=(2,)),
        _block(4, term=("ret",), preds=(2,)),
    ]
    dec = _decompiler(blocks, 0, {0, 1, 2, 3}, 3)
    output = []

    assert dec._emit_loop(blocks, 0, output, set(), 0) == 4
    text = "\n".join(output)

    assert text.count("var t0 = source;") == 1
    assert text.index("while (true)") < text.index("var t0 = source;")
    assert text.index("var t0 = source;") < text.index("t0 = Refill();")
    assert text.index("t0 = Refill();") < text.index("Tick();")
    assert "goto " not in text


def test_two_stage_entry_gate_folds_to_one_short_circuit_exit():
    # if (state == 1) body;
    # else if (state != Connecting) exit;
    # else body;
    blocks = [
        _block(0, term=("jcc", 2, 1), cond="state == 1",
               succs=(2, 1), preds=(2,)),
        _block(1, term=("jcc", 3, 2), cond="state != Connecting",
               succs=(3, 2), preds=(0,)),
        _block(2, stmts=["Work();"], term=("jmp", 0),
               succs=(0,), preds=(0, 1)),
        _block(3, term=("ret",), preds=(1,)),
    ]
    dec = _decompiler(blocks, 0, {0, 1, 2}, 2)
    output = []

    assert dec._emit_loop(blocks, 0, output, set(), 0) == 3
    text = "\n".join(output)

    assert "if ((state != 1) && (state != Connecting))" in text
    assert text.count("Work();") == 1
    assert "goto " not in text


def test_bottom_guard_is_not_retested_after_counter_copy():
    blocks=[_block(0,term=('jmp',1),succs=(1,),preds=(1,)),
            _block(1,stmts=['Visit(v2);'],term=('jcc',0,2),cond='v2 + 1 < limit',succs=(0,2),preds=(0,)),
            _block(2,term=('ret',),preds=(1,))]
    dec=_decompiler(blocks,0,{0,1},1); dec.phi_copies[(1,0)]=['v2 = v2 + 1;']
    out=[]; assert dec._emit_loop(blocks,0,out,set(),0)==2
    text='\n'.join(out)
    assert text.count('v2 + 1 < limit')==1 and text.index('break;') < text.index('v2 = v2 + 1;')
    assert text.endswith('while (true);')


def test_nested_search_keeps_exit_work_and_checks_backedge_once():
    blocks=[_block(0,term=('fall',1),succs=(1,),preds=(2,)),
            _block(1,term=('jcc',3,2),cond='Found(i)',succs=(3,2),preds=(0,)),
            _block(2,term=('jcc',0,4),cond='i + 1 < count',succs=(0,4),preds=(1,)),
            _block(3,stmts=['Mark(i);'],term=('fall',5),succs=(5,),preds=(1,)),
            _block(4,term=('jmp',5),succs=(5,),preds=(2,)),_block(5,preds=(3,4))]
    dec=_decompiler(blocks,0,{0,1,2},2);dec.phi_copies={(2,0):['i = i + 1;'],(4,5):['reason = exhausted;'],(3,5):['reason = matched;']}
    out=[];assert dec._emit_loop(blocks,0,out,set(range(6)),0)==5
    text='\n'.join(out)
    assert 'if (Found(i))\n{\nMark(i);\nreason = matched;\nbreak;' in text
    assert 'if (!(i + 1 < count))\n{\nreason = exhausted;\nbreak;\n}\ni = i + 1;' in text
    assert text.count('i + 1 < count')==1


def test_empty_search_returns_while_match_reaches_action():
    blocks = [
        _block(0, term=('jcc',3,1), cond='i >= count', succs=(3,1), preds=(2,)),
        _block(1, stmts=['item = Read(i);'], term=('jcc',4,2), cond='Matches(item)', succs=(4,2), preds=(0,)),
        _block(2, stmts=['i++;'], term=('jmp',0), succs=(0,), preds=(1,)),
        _block(3, term=('ret',), preds=(0,4)),
        _block(4, stmts=['Act(item);'], term=('jmp',3), succs=(3,), preds=(1,)),
    ]
    blocks[3].ret = ''
    dec = _decompiler(blocks,0,{0,1,2},2); out=[]
    dec.phi_copies[(0,3)] = ['left = Capture();']
    assert dec._emit_loop(blocks,0,out,set(),0) == 4
    assert out.index('if (i >= count)') < out.index('left = Capture();') < out.index('return;') < out.index('item = Read(i);')
    assert out.index('if (Matches(item))') < out.index('break;') < out.index('i++;')


def test_bottom_tested_search_returns_through_its_exhausted_epilogue():
    blocks = [
        _block(0,term=('jmp',1),succs=(1,),preds=(2,)),
        _block(1,stmts=['item = Read(i);'],term=('jcc',5,2),cond='Matches(item)',succs=(5,2),preds=(0,)),
        _block(2,term=('jcc',0,3),cond='i + 1 < n',succs=(0,3),preds=(1,)),
        _block(3,term=('fall',4),succs=(4,),preds=(2,5)),
        _block(4,term=('ret',),preds=(3,)),
        _block(5,stmts=['Act(item);'],term=('jmp',3),succs=(3,),preds=(1,)),
    ]
    blocks[4].ret = ''
    dec = _decompiler(blocks,0,{0,1,2},2); out=[]
    dec.phi_copies[(2,0)] = ['i = i + 1;']
    dec.phi_copies[(3,4)] = ['left = Capture();']
    assert dec._emit_loop(blocks,0,out,set(),0) == 5
    assert out.index('break;') < out.index('left = Capture();') < out.index('return;') < out.index('i = i + 1;')
    assert out[-1] == 'while (true);' and sum('i + 1 < n' in s for s in out) == 1


def test_consumed_linear_tail_replays_only_to_the_current_join():
    blocks = [
        _block(0),
        _block(1, stmts=["var t0 = Value();"], term=("fall", 2),
               succs=(2,)),
        _block(2, stmts=["Use(t0);"], term=("jmp", 3),
               succs=(3,), preds=(1,)),
        _block(3, preds=(2,)),
    ]
    blocks[1].consumed = blocks[2].consumed = True
    dec = _decompiler(blocks, 0, {0}, 0)
    dec.phi_copies[(1, 2)] = ["v1 = t0;"]
    output = []

    assert dec._replay_consumed_linear_to_stop(
        blocks, 1, {3}, set(), output
    )
    assert output == ["var t0 = Value();", "v1 = t0;", "Use(t0);"]

    # A conditional path is not a proven straight-line tail. Failure is
    # atomic: the helper must not emit a partial duplicate.
    blocks[2].term = ("jcc", 3, 0)
    blocks[2].succs = [3, 0]
    rejected = []
    assert not dec._replay_consumed_linear_to_stop(
        blocks, 1, {3}, set(), rejected
    )
    assert rejected == []


def test_shared_entry_gate_rejects_edge_specific_phi_state():
    blocks = [
        _block(0, term=("jcc", 2, 1), cond="state == 1",
               succs=(2, 1), preds=(2,)),
        _block(1, term=("jcc", 3, 2), cond="state != Connecting",
               succs=(3, 2), preds=(0,)),
        _block(2, stmts=["Work();"], term=("jmp", 0),
               succs=(0,), preds=(0, 1)),
        _block(3, term=("ret",), preds=(1,)),
    ]
    dec = _decompiler(blocks, 0, {0, 1, 2}, 2)
    dec.phi_copies[(1, 2)] = ["v1 = fromGate;"]

    assert dec._loop_shared_entry_gate(blocks, 0, {0, 1, 2}) is None
