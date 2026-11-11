"""Metadata v39 (Unity 6.3/6.4) header and row layout.

v38+ replaced the classic (offset, size) header with 12-byte section
descriptors (offset, size, count), dropped the typedef element index,
dropped the string-literal length, and serialized several index columns
at the narrowest width their target table needs.  These tests pin one
complete file: a v39 header, one string literal, one parameter, one
method, one type definition and one image.
"""
import struct

from il2cpp.metadata import HEADER_TABLES, Metadata

MAGIC = 0xFAB11BAF
VERSION = 39


def _index(value, width):
    if width == 1:
        return struct.pack('<B', value & 0xFF)
    if width == 2:
        return struct.pack('<H', value & 0xFFFF)
    return struct.pack('<i', value)


def _build():
    strings = b''
    at = {}
    for name in (b'Bar', b'Foo', b'Baz', b'Test.dll', b'arg'):
        at[name] = len(strings)
        strings += name + b'\x00'

    literal_data = b'hi'
    tables = {}
    counts = {'typeDefinitions': 1, 'parameters': 1, 'genericContainers': 0,
              'interfaceOffsets': 0, 'methods': 1, 'images': 1,
              'stringLiteral': 1}

    td_w, gc_w, p_w = 1, 1, 1          # table sizes 1, 0, 1 -> one byte
    type_w = 4                         # no interface offsets -> 8-byte pair
    typedef = bytearray(68 + 3 * type_w + gc_w)
    struct.pack_into('<ii', typedef, 0, at[b'Foo'], at[b'Bar'])
    struct.pack_into('<3i', typedef, 8, -1, -1, -1)
    typedef[20] = 0xFF                 # generic container
    p = 21
    struct.pack_into('<I', typedef, p, 0); p += 4          # flags
    struct.pack_into('<i', typedef, p, -1); p += 4         # fieldStart
    struct.pack_into('<i', typedef, p, 0); p += 4          # methodStart
    for _ in range(4):                                     # event/property/nested/interfaces
        struct.pack_into('<i', typedef, p, -1); p += 4
    struct.pack_into('<i', typedef, p, 0); p += 4          # vtableStart
    struct.pack_into('<i', typedef, p, -1); p += 4         # interfaceOffsetsStart
    struct.pack_into('<8H', typedef, p, 1, 0, 0, 0, 0, 0, 0, 0); p += 16
    struct.pack_into('<II', typedef, p, 0, 0x02000001)

    method = bytearray(20 + td_w + type_w + p_w + gc_w)
    struct.pack_into('<I', method, 0, at[b'Baz'])
    p = 4
    method[p] = 0; p += td_w
    struct.pack_into('<i', method, p, 7); p += type_w       # return type
    struct.pack_into('<i', method, p, 0x1C000042); p += 4    # returnParameterToken
    method[p] = 0; p += p_w                                  # parameterStart
    method[p] = 0xFF; p += gc_w                              # generic container
    struct.pack_into('<I', method, p, 0x06000001); p += 4
    struct.pack_into('<4H', method, p, 0x10, 0, 3, 1)

    param = struct.pack('<II', at[b'arg'], 0x08000001) + _index(7, type_w)

    image = bytearray(28 + 2 * td_w + 4)
    struct.pack_into('<II', image, 0, at[b'Test.dll'], 0)
    p = 8
    image[p] = 0; p += td_w
    struct.pack_into('<I', image, p, 1); p += 4
    image[p] = 0; p += td_w
    struct.pack_into('<I', image, p, 0); p += 4
    struct.pack_into('<i', image, p, -1); p += 4
    struct.pack_into('<II', image, p, 1, 0); p += 8
    struct.pack_into('<I', image, p, 0)

    blobs = [
        ('string', strings),
        ('parameters', bytes(param)),
        ('methods', bytes(method)),
        ('typeDefinitions', bytes(typedef)),
        ('images', bytes(image)),
        ('stringLiteral', struct.pack('<i', 0)),
        ('stringLiteralData', literal_data),
    ]
    header_end = 8 + 12 * len(HEADER_TABLES)
    off = header_end
    placed = {}
    for name, blob in blobs:
        placed[name] = (off, len(blob))
        off += len(blob)
    buf = bytearray(off)
    struct.pack_into('<Ii', buf, 0, MAGIC, VERSION)
    for i, (name, _) in enumerate(HEADER_TABLES):
        o, size = placed.get(name, (0, 0))
        struct.pack_into('<iii', buf, 8 + 12 * i, o, size, counts.get(name, 0))
    for name, blob in blobs:
        o, _ = placed[name]
        buf[o:o + len(blob)] = blob
    return bytes(buf)


def test_v39_header_and_rows(tmp_path):
    path = tmp_path / 'global-metadata.dat'
    path.write_bytes(_build())

    m = Metadata(str(path))

    assert m.version == VERSION and m.v39
    assert len(m.typedefs) == 1 and len(m.methods) == 1
    assert len(m.params) == 1 and len(m.images) == 1
    assert len(m.string_literals) == 1

    td = m.typedefs[0]
    assert (td.name, td.namespace) == ('Foo', 'Bar')
    assert (td.method_start, td.method_count) == (0, 1)
    assert td.token == 0x02000001
    assert td.element == -1

    md = m.methods[0]
    assert (md.name, md.declaring, md.return_type) == ('Baz', 0, 7)
    assert (md.parameter_start, md.param_count) == (0, 1)
    assert (md.token, md.flags, md.slot) == (0x06000001, 0x10, 3)
    assert md.is_static

    assert m.method_params(md)[0].name == 'arg'
    assert m.images[0].name == 'Test.dll'
    assert m.images[0].type_start == 0 and m.images[0].type_count == 1
    assert m.string_literal(0) == 'hi'
