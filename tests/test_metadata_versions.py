"""The metadata method-table parser across format versions.

Pre-v31 rows are 32 bytes / six int32 (no returnParameterToken); v31
rows are 36 bytes / seven int32.  The pre-v31 branch bound the return
type as `rt` while the shared MethodDef call read `rtok`, so every
real file with metadata < v31 (Megabonk ships v29) died with
UnboundLocalError before the binary was even loaded.  These tests pin
both layouts, including the return-type field and the token offset.
"""
import struct

import pytest

from il2cpp.metadata import HEADER_TABLES, V_TABLES_MIN, Metadata

SENTINEL_RT = 42
SENTINEL_RP = 0x1C000042
SENTINEL_TOKEN = 0x06000001


def _build(version, name=b'Foo', return_type=SENTINEL_RT,
           token=SENTINEL_TOKEN):
    """A minimal but real global-metadata.dat: header, one method row,
    one string.  Every other table is present (per version) with size 0,
    which is exactly what a v29 file's parser walks first."""
    strings = name + b'\x00'
    tables = []
    off = 8
    for tname, _struct_size in HEADER_TABLES:
        if version < V_TABLES_MIN.get(tname, 0):
            continue
        tables.append((tname, off))
        off += 8
    header_end = off

    mstride = 36 if version >= 31 else 32
    method_off = header_end
    if version >= 31:
        row = struct.pack('<7i', 0, 0, return_type, SENTINEL_RP, 0, -1, token) \
            + struct.pack('<4H', 0x10, 0, 3, 0)
    else:
        row = struct.pack('<6i', 0, 0, return_type, 0, -1, token) \
            + struct.pack('<4H', 0x10, 0, 3, 0)
    assert len(row) == mstride

    string_off = method_off + mstride
    buf = bytearray(string_off + len(strings))
    struct.pack_into('<I', buf, 0, 0xFAB11BAF)
    struct.pack_into('<i', buf, 4, version)
    for tname, toff in tables:
        offset, size = 0, 0
        if tname == 'methods':
            offset, size = method_off, mstride
        elif tname == 'string':
            offset, size = string_off, len(strings)
        struct.pack_into('<i', buf, toff, offset)
        struct.pack_into('<i', buf, toff + 4, size)
    buf[method_off:method_off + mstride] = row
    buf[string_off:string_off + len(strings)] = strings
    return bytes(buf)


@pytest.mark.parametrize('version', [24, 27, 29, 30, 31])
def test_method_table_return_type_parses(tmp_path, version):
    path = tmp_path / 'global-metadata.dat'
    path.write_bytes(_build(version))

    m = Metadata(str(path))

    assert len(m.methods) == 1
    md = m.methods[0]
    assert md.name == 'Foo'
    assert md.declaring == 0
    assert md.return_type == SENTINEL_RT
    assert md.parameter_start == 0
    assert md.generic_container == -1
    assert md.token == SENTINEL_TOKEN
    assert md.flags == 0x10 and md.is_static
    assert md.slot == 3
    assert md.param_count == 0


def test_v31_row_carries_return_parameter_token(tmp_path):
    """v31's extra int32 shifts the row to 36 bytes; the shared parser
    must read the same name/return-type/token fields there too."""
    path = tmp_path / 'global-metadata.dat'
    path.write_bytes(_build(31))

    m = Metadata(str(path))

    md = m.methods[0]
    assert (md.name, md.return_type, md.token) == (
        'Foo', SENTINEL_RT, SENTINEL_TOKEN)
    strided = _build(31)
    # 36-byte stride: the string table sits right after the row.
    assert len(strided) == 8 + 31 * 8 + 36 + len(b'Foo\x00')
