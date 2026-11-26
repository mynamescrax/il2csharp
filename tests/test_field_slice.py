from struct import pack_into
from types import SimpleNamespace

import pytest

from il2cpp.binary import PE, Section
from il2cpp.field_slice import field_offset


def image(code, target):
    data = bytearray(0x100) + bytes.fromhex(code)
    pack_into('<I', data, 0x3c, 0x40)
    data[0x40:0x46] = b'PE\0\0\x64\x86'
    b = PE.__new__(PE)
    b.d, b.exports = bytes(data), {}
    size = len(data) - 0x100
    b.sections = [Section('.text', target, size, 0x100, size, 0x60000020)]
    return SimpleNamespace(bin=b, function_extent=lambda a: (a, a + 0x1000),
                           next_method_start=lambda _: None, next_function_start=lambda _: None)


# XMM3, R10D, a nonzero (and unaligned) byte offset. Use the output echo
# as the base for both stores and schedule the tail store first.
LEAF = 'f20f105a15 448b521d 4889c8 44895008 f20f1118 c3'


@pytest.mark.parametrize('target', [0x1800, 0x7fff12345000])
@pytest.mark.parametrize('code,offset', [
    ('f20f1002 8b4208 f20f1101 894108 488bc1 c3', 0),
    (LEAF, 21),
    # Two GPR lanes with independent disp32s. EDX clobbers the input
    # pointer only after the last input memory operand is evaluated.
    ('4c8b8a23010000 8b922b010000 4c8909 895108 488bc1 c3', 291),
    # Read the last four bytes first. ECX may be used as scratch once RAX
    # holds the output address. The scalar float move does no arithmetic.
    ('488bc1 f30f106a30 488b4a28 f30f116808 488908 c3', 40),
])
def test_exact_lanes_and_echo(target, code, offset):
    il = image(code + ' cc c3', target)
    assert field_offset(il, target) == offset


@pytest.mark.parametrize('original,change', [
    ('1d', '1c'),                 # input lanes overlap by one byte
    ('1d', '1e'),                 # input lanes have a one-byte hole
    ('5a15', '5af8'),             # negative receiver offset
    ('5008', '5007'),             # output lanes overlap
    ('5008', '5009'),             # output lanes leave a hole
    ('44895008', '4c895008'),     # qword store from a dword load
    ('44895008', '44895808'),     # store from unrelated volatile register
    ('4889c8', '89c8'),           # partial-width echo
    ('4889c8', '4889d0'),         # echoes input
    ('44895008', '44895208'),     # writes the input
    ('f20f105a15', 'f20f105915'),       # read output, not receiver
    ('f20f105a15', 'f20f105c0a15'),     # indexed address
    ('4889c8', '4889c8 31d2'),           # extra flag/register write
    ('4889c8', '4889c8 e800000000'),     # a call can observe the copy
    ('4889c8', '4889c8 8902'),           # extra memory write
    ('4889c8', '4889c8 eb00'),           # branch
    ('c3', 'c20800'),                   # return pops extra bytes
    ('c3', '90'),                       # unterminated leaf
])
def test_disputed_copy_declines(original, change):
    target = 0x3620
    il = image(LEAF.replace(original, change), target)
    assert field_offset(il, target) is None


@pytest.mark.parametrize('op,prefix', [(1, '64'), (1, '67'), (1, 'f2'), (2, '66'),
                                      (3, 'f0'), (4, 'f2'), (5, 'f3'), (5, '48')])
def test_ignored_or_effectful_prefix_is_not_a_plain_copy(op, prefix):
    parts = LEAF.split()
    parts[op] = prefix + parts[op]
    target = 0xb800
    assert field_offset(image(' '.join(parts), target), target) is None


@pytest.mark.parametrize('code', [
    # The first store may destroy the bytes that the last load needs.
    'f20f1002 f20f1101 8b4208 894108 488bc1 c3',
    # The source pointer, earlier lane or echo has been overwritten.
    '488b12 448b4208 488911 44894108 488bc1 c3',
    '488b02 8b4208 488901 894108 488bc1 c3',
    '488bc1 f20f1002 8b4208 f20f1101 894108 c3',
])
def test_entry_values_must_survive_until_consumed(code):
    target = 0x2400
    assert field_offset(image(code, target), target) is None


@pytest.mark.parametrize('code', [
    LEAF.replace('105a', '1072').replace('1118', '1130'),     # XMM6
    LEAF.replace('8b52', '8b62').replace('8950', '8960'),     # R12D
])
def test_correct_bytes_copied_via_nonvolatile_scratch_decline(code):
    target = 0x3210
    assert field_offset(image(code, target), target) is None


@pytest.mark.parametrize('body', ['4883ec28 4883c428 c3', '488bc1 ' + '90 ' * 48 + 'c3'])
def test_common_misses_skip_function_boundary_queries(body):
    target = 0x2480
    il = image(body, target)
    il.function_extent = lambda _: pytest.fail('ordinary miss reached the slow path')
    assert field_offset(il, target) is None


@pytest.mark.parametrize('boundary', ['extent', 'pdata', 'method', 'generic', 'export', 'raw', 'virtual'])
@pytest.mark.parametrize('cut', [3, len(bytes.fromhex(LEAF)) - 1])
def test_cannot_complete_an_instruction_or_borrow_a_ret_from_a_neighbor(boundary, cut):
    target = 0x6040
    il = image(LEAF, target)
    if boundary == 'extent':
        il.function_extent = lambda a: (a, a + cut)
    elif boundary == 'pdata':
        il.next_function_start = lambda a: a + cut
    elif boundary == 'method':
        il.next_method_start = lambda a: a + cut
    elif boundary == 'generic':
        il.addr_to_method = {target + cut: ('generic', 0)}
    elif boundary == 'export':
        il.bin.exports[target + cut] = 'neighbor'
    elif boundary == 'raw':
        il.bin.sections[0].rawsize = cut
    else:
        il.bin.sections[0].size = cut
    assert field_offset(il, target) is None


@pytest.mark.parametrize('change', ['interior', 'data', 'arm64', '32bit'])
def test_requires_an_executable_win64_entry(change):
    target = 0x5080
    il = image(LEAF, target)
    if change == 'interior':
        il.function_extent = lambda a: (a - 1, a + 100)
    elif change == 'data':
        il.bin.sections[0].chars = 0x40000040
    elif change == 'arm64':
        il.bin.d = il.bin.d.replace(b'PE\0\0\x64\x86', b'PE\0\0\x64\xaa')
    else:
        il.bin.is64 = False
    assert field_offset(il, target) is None
