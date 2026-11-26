import os
from dataclasses import replace
from struct import pack, pack_into
from types import SimpleNamespace as NS

import pytest

from il2cpp import Il2Cpp, Lifter, Metadata
from il2cpp.binary import PE, Section
from il2cpp.equivalent_binary import equivalent_binary
from il2cpp.metadata import MethodDef, ParamDef


BASE = 0x140000000
HELPER, METHOD, THIRD = (BASE + r for r in (0x1020, 0x1140, 0x1220))
INIT, OTHER = BASE + 0x1300, BASE + 0x1308
FLAG, USAGE, SCALE = BASE + 0x2010, BASE + 0x2050, BASE + 0x2080
TY = (0, 0x11 << 16)


def code(addr, flag, *, init=INIT, slot=USAGE, scale=SCALE, store=None, op=0x5c,
         branch=0x75, gap=b'\x48\x89\xd7', cold_skip=19, callee=OTHER, skip=3):
    buf = bytearray.fromhex('56 57 48 83 ec 28 48 89 ce')  # save RSI/RDI; RSI <- RCX

    def rel(prefix, target, tail=b''):
        buf.extend(prefix)
        buf.extend(pack('<i', target - (addr + len(buf) + 4 + len(tail))))
        buf.extend(tail)

    rel(b'\x80\x3d', flag, b'\x00')
    buf.extend(gap + bytes((branch, cold_skip)))  # RDI <- RDX, preserve cmp flags
    rel(b'\x48\x8d\x0d', slot)
    rel(b'\xe8', init)
    rel(b'\xc6\x05', flag if store is None else store, b'\x01')
    rel(b'\xe8', callee)
    # A different operation, owner and frame from the game. Use a shared
    # float constant, two saved parameters, and return through XMM0.
    buf.extend(bytes.fromhex('f3 0f 10 06') + bytes((0xf3, 0x0f, op, 7)))
    rel(bytes.fromhex('f3 0f 59 05'), scale)
    buf.extend(bytes.fromhex('0f 2e c0 7b') + bytes((skip,)) + bytes.fromhex('0f 57 c0 48 83 c4 28 5f 5e c3'))
    return buf


def fixture(*, helper=None, method=None, both=None, ambiguous=False):
    b = PE.__new__(PE)
    b.is64, b.image_base, b.d = True, BASE, bytearray(0x2800)
    pack_into('<I', b.d, 0x3c, 0x80)
    b.d[0x80:0x86] = b'PE\0\0\x64\x86'
    _, data, pd = b.sections = [Section(n, BASE+rva, size, off, size, flags) for n, rva, size, off, flags in (
        ('.text', 0x1000, 0x400, 0x200, 0x60000020), ('.data', 0x2000, 0x400, 0x800, 0xc0000040),
        ('.pdata', 0x3000, 12*(2+ambiguous), 0x1000, 0x40000040))]
    for va in (INIT, OTHER, OTHER+8):
        b.d[b.va2off(va)] = 0xc3
    il = Il2Cpp.__new__(Il2Cpp)
    il.bin = b
    meta = il.meta = Metadata.__new__(Metadata)
    td = NS(index=0, is_valuetype=True, generic_container=-1, method_start=0, method_count=1+ambiguous)
    il.types = [TY, (0, 0x0c << 16), (0, 0x11 << 16 | 1 << 29), (0, 0x0d << 16)]
    meta.typedefs, meta.params = [td], [ParamDef(n, 0, 0) for n in ('p', 'q')]
    m = MethodDef(0, 'Measure', 0, 1, 0, -1, 0x06000001, 0x16, 0, 0xffff, 2, addr=METHOD)
    meta.methods = [m] + ([replace(m, index=1, name='AlsoMeasure', addr=THIRD)] if ambiguous else [])
    il.addr_to_method = {row.addr: ('method', row.index) for row in meta.methods}
    il.addr_candidates = {a: [row] for a, row in il.addr_to_method.items()}
    # push rsi; push rdi; sub rsp,28h. Correct plain unwind record.
    ui = 0x2100
    unwind = bytes.fromhex('01 06 03 00 06 42 02 70 01 60 00 00')
    b.d[data.offset+0x100:data.offset+0x100+len(unwind)] = unwind
    pack_into('<Q', b.d, b.va2off(USAGE), 0x20000001)
    pack_into('<Q', b.d, b.va2off(USAGE+8), 0x20000001)  # valid but *different* slot, even same token
    for n, (addr, flag, options) in enumerate([(HELPER, FLAG, helper), (METHOD, FLAG+1, method)] +
                                               ([(THIRD, FLAG+2, None)] if ambiguous else [])):
        buf = code(addr, flag, **{**(both or {}), **(options or {})})
        off = b.va2off(addr)
        b.d[off:off+len(buf)] = buf
        pack_into('<III', b.d, pd.offset+12*n, addr-BASE, addr-BASE+len(buf), ui)
    il.load_function_bounds()
    return NS(il=il, rt_init_meta=INIT)


def test_relocated_copy_identifies_the_registered_methoddef():
    lift = fixture()
    assert equivalent_binary(lift, HELPER, TY) is lift.il.meta.methods[0]


@pytest.mark.parametrize('change', [dict(op=0x58), dict(init=OTHER), dict(callee=OTHER+8), dict(skip=0), dict(slot=USAGE+8),
    dict(scale=SCALE+4), dict(store=FLAG+7), dict(cold_skip=18)])
def test_changed_arithmetic_call_data_store_or_branch_declines(change):
    assert equivalent_binary(fixture(helper=change), HELPER, TY) is None


@pytest.mark.parametrize('both', [dict(init=OTHER), dict(branch=0x74), dict(cold_skip=7),
    dict(gap=bytes.fromhex('48 85 d2')), dict(slot=SCALE), dict(scale=FLAG)])
def test_equal_looking_non_guards_cannot_hide_distinct_writable_addresses(both):
    assert equivalent_binary(fixture(both=both), HELPER, TY) is None


def test_even_identical_branches_may_not_enter_an_instruction_operand():
    assert equivalent_binary(fixture(both=dict(skip=1)), HELPER, TY) is None


def test_flag_must_start_clear_and_unwind_identity_and_extent_are_required():
    lift = fixture()
    b = lift.il.bin
    b.d[b.va2off(FLAG)] = 1
    assert equivalent_binary(lift, HELPER, TY) is None
    b.d[b.va2off(FLAG)] = 0
    pd = b.sections[-1]
    b.d[pd.offset+12+8] ^= 4  # change the registered copy's unwind RVA
    assert equivalent_binary(lift, HELPER, TY) is None
    b.d[pd.offset+12+8] ^= 4
    b.d[pd.offset+4] ^= 1  # inconsistent .pdata end
    assert equivalent_binary(lift, HELPER, TY) is None
    assert equivalent_binary(lift, HELPER+1, TY) is None


def test_registration_and_ambiguity():
    assert equivalent_binary(fixture(ambiguous=True), HELPER, TY) is None
    lift = fixture()
    assert equivalent_binary(lift, METHOD, TY) is None
    lift.il.addr_to_method[HELPER] = ('thunk', (0, 1))
    assert equivalent_binary(lift, HELPER, TY) is None
    del lift.il.addr_to_method[HELPER]
    lift.il.addr_candidates[METHOD].append(('generic', 2))
    assert equivalent_binary(lift, HELPER, TY) is None


@pytest.mark.parametrize(('obj', 'field', 'value'), [
    ('param', 'type', 2), ('param', 'type', 3), ('method', 'return_type', 3),
    ('method', 'generic_container', 0), ('method', 'flags', 0x11), ('method', 'flags', 6),
    ('method', 'declaring', 2), ('method', 'param_count', 1), ('type', 'generic_container', 2),
    ('type', 'is_valuetype', False)])
def test_closed_public_by_value_signature_is_required(obj, field, value):
    lift = fixture()
    meta = lift.il.meta
    setattr({'param': meta.params[1], 'method': meta.methods[0], 'type': meta.typedefs[0]}[obj], field, value)
    assert equivalent_binary(lift, HELPER, TY) is None


@pytest.mark.game
def test_exact_downstream_helper():
    from il2cpp.cli import _load_runtime
    from tools.corpus_common import sha256

    metadata, binary = (os.getenv('IL2CSHARP_'+v) for v in ('METADATA', 'BINARY'))
    if (not metadata or not binary or sha256(metadata) != 'bd92f36e124ec3b236ef6bc3ead42eed3c322b15f403ecdc078f7c8dee5c75e1'
            or sha256(binary) != '163982a57e2e6e4c8f4558f6e968e9ba73e422d9b736cb4efef1e0674d5ab806'):
        pytest.skip('requires the second Shift v31 build')
    meta, il = _load_runtime(metadata, binary, False)
    method = meta.methods[55788]
    ty = il.types[meta.typedefs[method.declaring].byval]
    assert equivalent_binary(Lifter(il), 0x1804fe6e0, ty) is method
