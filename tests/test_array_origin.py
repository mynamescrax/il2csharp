from types import SimpleNamespace as NS

import pytest
from iced_x86 import Decoder, Register as R

from il2cpp import Il2Cpp
from il2cpp.array_origin import array_origin
from il2cpp.binary import PE
from il2cpp.cfg import Block


ENTRY, ALLOC, OTHER, SLOT = 0x2000, 0x4000, 0x5000, 0x6000
ARRAY = (0x7000, 0x1d << 16)
LOAD = ('488b0d', SLOT)  # mov rcx,[rip+slot]
NEW = ('e8', ALLOC)
SAVE = '488bf8'            # mov rdi,rax


def fixture(*, entry=(), entry_target='type', setup=(LOAD,), before=(), after=('488b0e',), save=SAVE,
            latch=(('e8', OTHER),), back='check', helper=ALLOC):
    # Construct real rel32 operands, independently of which variant is longer.
    # succs/preds model a lifted CFG that dropped the entry's cold/fast branch
    # and the loop back edge. Neither can be taken on trust for this proof.
    layout = [
        ('entry', [*entry, '803900', ('0f85', entry_target)]),
        ('cold', [('e8', OTHER)]),
        ('type', list(setup)),
        ('alloc', [*before, ('e8', helper), *after]),
        ('save', [save]),
        ('check', ['3b5f18', ('0f83', 'exit')]),
        ('loop', [*latch, ('e9', back)]),
        ('exit', ['c3']),
    ]
    labels = {}
    ip = ENTRY
    for name, ops in layout:
        labels[name] = ip
        for op in ops:
            ip += len(bytes.fromhex(op[0])) + 4 if isinstance(op, tuple) else len(bytes.fromhex(op))
    end = ip
    blocks = []
    for name, ops in layout:
        ip = labels[name]
        raw = bytearray()
        for op in ops:
            if isinstance(op, str):
                raw.extend(bytes.fromhex(op))
            else:
                prefix, dest = op
                raw.extend(bytes.fromhex(prefix))
                raw.extend((labels.get(dest, dest) - ip - len(raw) - 4).to_bytes(4, 'little', signed=True))
        block = Block(len(blocks), list(Decoder(64, bytes(raw), ip=ip)))
        blocks.append(block)
        if len(blocks) > 1:
            block.preds.append(block.bid - 1)
            blocks[-2].succs.append(block.bid)

    image = PE.__new__(PE)
    image.is64, image.image_base = True, 0
    image.read = lambda va, n: bytes([1, 0, 0, 0]) if va == 0x8000 and n == 4 else None
    image.is_exec_va = {ALLOC, OTHER}.__contains__
    il = Il2Cpp.__new__(Il2Cpp)
    il.bin, il.types, il.addr_candidates = image, [ARRAY], {}
    il.type_from_ptr = {ARRAY[0]: (0, 8 << 16)}.get
    il.decode_slot = lambda va: {'kind': 1, 'idx': 0, 'type': il.types[0]} if va == SLOT else None
    il.eh_regions = lambda va: None
    il._eh4_begins, il._eh4_entries = [ENTRY], [(ENTRY, end, 0x8000)]
    lift = NS(il=il, _current_method=NS(addr=ENTRY), rt_arrnew={ALLOC}, _ref_array_pads=set())
    return lift, blocks, 5, R.RDI


def test_allocation_survives_init_guard_and_loop_call_without_fill_evidence():
    assert array_origin(*fixture()) == ARRAY


def test_back_edge_cannot_skip_the_check_for_a_new_index():
    args=fixture(back='loop');start=args[1][6].insns[0].ip
    assert array_origin(*args)==ARRAY  # still the same allocation *at* the compare
    assert array_origin(*args,through=start) is None


def test_both_arms_put_the_same_type_into_allocation_argument():
    # The cold and fast paths enter the call block with the same TypeInfo.
    assert array_origin(*fixture(entry=[LOAD], entry_target='alloc')) == ARRAY


def test_full_width_copies_preserve_provenance():
    # Load the type through R11; park the returned RAX in R14 before a
    # volatile call, then copy R14 to the bounds-check's RDI.
    assert array_origin(*fixture(setup=[('4c8b1d', SLOT), '498bcb'],
                                 after=['4c8bf0', ('e8', OTHER)], save='498bfe')) == ARRAY


def test_same_site_with_different_type_arguments_declines():
    lift, blocks, bid, reg = fixture(entry=[('488b0d', SLOT+8)], entry_target='alloc')
    other = (ARRAY[0]+8, ARRAY[1])
    lift.il.types.append(other)
    lift.il.type_from_ptr = {ARRAY[0]: (0, 8 << 16), other[0]: (0, 0xe << 16)}.get
    lift.il.decode_slot = lambda va: {'kind': 1, 'idx': int(va != SLOT), 'type': lift.il.types[int(va != SLOT)]}
    assert array_origin(lift, blocks, bid, reg) is None


@pytest.mark.parametrize('opts', [
    dict(entry_target='alloc'),                   # fast path skips the type load
    dict(entry_target='save'),                    # RAX not always the allocation
    dict(entry_target='check'),                   # base undefined on fast path
    dict(before=['b101']),                        # write CL before allocator
    dict(before=[('e8', OTHER)]),                 # RCX is volatile
    dict(helper=OTHER),
    dict(after=['b001']),                         # only AL overwritten before save
    dict(after=[('e8', OTHER)]),                  # another return, same register
    dict(save='8bf8'),                            # dword save loses the high half
    dict(latch=['40b700']),                       # write DIL on a back edge
    dict(latch=['4887f7']),                       # XCHG: writes operand 1 too
    dict(latch=['48ab']),                         # STOSQ implicitly updates RDI
    dict(latch=[LOAD, NEW, SAVE]),                # same type, different allocation
    dict(back='type'),                            # same site, allocated anew
    dict(setup=[('488d0d', SLOT)]),               # LEA takes slot address
    dict(setup=[('8b0d', SLOT)]),                 # dword read cannot supply klass
    dict(setup=[('65488b0d', SLOT)]),             # GS-relative, not the slot
])
def test_bad_incoming_path_or_nonallocation_declines(opts):
    lift, blocks, bid, reg = fixture(**opts)
    lift._single_array_allocs = {blocks[3].insns[0].ip}  # never enough by itself
    assert array_origin(lift, blocks, bid, reg) is None


@pytest.mark.parametrize('bad', ['pad', 'handler', 'unknown unwind', 'bad extent', 'registered entry',
                                 'local call', 'indirect call', 'indirect jump', 'missing branch target'])
def test_incomplete_or_multiple_entry_cfg_declines(bad):
    opts = {'local call': dict(before=[('e8', 'check')]), 'indirect call': dict(before=['ffd0']),
            'indirect jump': dict(before=['ffe0']), 'missing branch target': dict(entry_target=ENTRY+1)}.get(bad, {})
    lift, blocks, bid, reg = fixture(**opts)
    if bad == 'pad':
        lift._ref_array_pads.add(bid)
    if bad == 'handler':
        lift.il.eh_regions = lambda va: {'pads': [blocks[bid].insns[0].ip]}
    if bad == 'unknown unwind':
        lift.il.bin.read = lambda va, n: b'\x09\0\0\0'
    if bad == 'bad extent':
        lift.il._eh4_entries[0] = (ENTRY, ENTRY+2, 0x8000)
    if bad == 'registered entry':
        lift.il.addr_candidates[blocks[bid].insns[0].ip] = [('method', 1)]
    assert array_origin(lift, blocks, bid, reg) is None


@pytest.mark.parametrize('bad', ['Il2CppType', 'wrong slot row', 'open element', 'byref element',
                                 'generic definition', 'byref array', 'non-array'])
def test_typeinfo_must_supply_a_concrete_szarray_row(bad):
    lift, blocks, bid, reg = fixture()
    il = lift.il
    if bad == 'Il2CppType':
        il.decode_slot = lambda va: {'kind': 2, 'idx': 0, 'type': ARRAY}
    if bad == 'wrong slot row':
        il.decode_slot = lambda va: {'kind': 1, 'idx': -1, 'type': ARRAY}
    if bad == 'open element':
        il.type_from_ptr = lambda ptr: (0, 0x1e << 16)
    if bad == 'byref element':
        il.type_from_ptr = lambda ptr: (0, (1 << 29) | (8 << 16))
    if bad == 'generic definition':
        il.type_from_ptr = lambda ptr: (0, 0x12 << 16)
        il.meta = NS(typedefs=[NS(is_valuetype=False, generic_container=0)])
    if bad == 'byref array':
        il.types[0] = ARRAY[0], ARRAY[1] | 1 << 29
    if bad == 'non-array':
        il.types[0] = (0, 0x12 << 16)
    assert array_origin(lift, blocks, bid, reg) is None
