from il2cpp.prelude import *  # noqa: F401,F403

#!/usr/bin/env python3
"""
il2csharp - IL2CPP to C# recovery tool with real method bodies.

Parses global-metadata.dat + the IL2CPP binary (GameAssembly.dll / libil2cpp.so),
resolves every method's native address, disassembles the native code and lifts it
back into annotated pseudo-C# with:
  * resolved calls        Foo.Bar(arg1, arg2)
  * resolved field access this.health, obj.name (real field offsets)
  * resolved string literals  "Player died"
  * resolved type handles     typeof(List<int>)
  * branch structure          if/else/goto labels
Not an Il2CppDumper fork: original codebase. Metadata formats cross-checked
against the runtime structures (v24.2-v31 and v39, primary target v29/v31).

Usage:
    python il2csharp.py <game-dir | metadata-file> [options]
"""


# ----------------------------------------------------------------------------
# helpers
# ----------------------------------------------------------------------------

def u32(d, o): return struct.unpack_from('<I', d, o)[0]
def i32(d, o): return struct.unpack_from('<i', d, o)[0]
def u16(d, o): return struct.unpack_from('<H', d, o)[0]
def i16(d, o): return struct.unpack_from('<h', d, o)[0]
def u64(d, o): return struct.unpack_from('<Q', d, o)[0]
def i64(d, o): return struct.unpack_from('<q', d, o)[0]
def align(x, a): return (x + a - 1) & ~(a - 1)

def read_compressed_uint(d, off):
    """Unity.IL2CPP.Metadata.MetadataUtils::WriteCompressedUInt32 â€” the
    variable-size encoding of the v29+ default-value blob. Returns
    (value, bytes_consumed)."""
    b = d[off]
    if b < 0x80:
        return b, 1
    if b == 0xF0:  # full uint32 escape
        return u32(d, off + 1), 5
    if b == 0xFF:
        return 0xFFFFFFFF, 1
    if b == 0xFE:
        return 0xFFFFFFFE, 1
    if (b & 0xC0) == 0xC0:  # 3 more bytes
        return ((b & 0x3F) << 24) | (d[off + 1] << 16) | (d[off + 2] << 8) | d[off + 3], 4
    if (b & 0x80) == 0x80:  # 1 more byte
        return ((b & 0x7F) << 8) | d[off + 1], 2
    raise ValueError('invalid compressed uint first byte 0x%02x' % b)

def compressed_int(d, off):
    """libil2cpp ReadCompressedInt32: sign-in-low-bit zigzag over
    read_compressed_uint. Returns (value, bytes_consumed)."""
    u, n = read_compressed_uint(d, off)
    if u == 0xFFFFFFFF:
        return -0x80000000, n
    neg = u & 1
    u >>= 1
    return (-(u + 1)) if neg else u, n

# ----------------------------------------------------------------------------
# C# type-name rendering
# ----------------------------------------------------------------------------

# Exact full-name matches only: System.Int32Enum and friends must survive.
_SYS_CSHARP = {
    'System.SByte': 'sbyte', 'System.Int16': 'short', 'System.Int32': 'int',
    'System.Byte': 'byte', 'System.UInt16': 'ushort', 'System.UInt32': 'uint',
    'System.Int64': 'long', 'System.UInt64': 'ulong', 'System.Char': 'char',
    'System.Single': 'float', 'System.Double': 'double', 'System.Boolean': 'bool',
    'System.String': 'string', 'System.Object': 'object',
}
_GEN_SPLIT_RX = re.compile(r'([<>\[\],]+)')
_BACKTICK_RX = re.compile(r'`\d+')


# `@` that is NOT at the start of an identifier segment (i.e. preceded by
# an identifier character) -- the illegal, mid-token kind.
_MIDAT_RX = re.compile(r'(?<=[A-Za-z0-9_])@')


def csharp_type_name(full: str) -> str:
    """Render a dotted type name the way C# source spells it: System.Int32
    -> int (keywords map inside generic arguments and array suffixes too),
    reflection-style nested names Outer+Inner / Outer/Inner -> Outer.Inner."""
    if not full:
        return full
    if '<' in full or '[' in full or ',' in full:
        parts = _GEN_SPLIT_RX.split(full)
        for k, p in enumerate(parts):
            if p and p.strip('<>[],'):
                parts[k] = csharp_type_name(p)
        full = ''.join(parts)
    key = full.strip()
    if key in _SYS_CSHARP:
        return full[:len(full) - len(key)] + _SYS_CSHARP[key]
    # generic arity (`List`1) renders as the `_1` suffix everywhere, so
    # references spell the same identifier the declaration does
    # (`EqualityComparer_1<byte>` matches `class EqualityComparer_1<T>`);
    # `@` is a verbatim-identifier PREFIX in C# and illegal mid-token, so
    # only a segment-leading one survives (`ReaderWriter@Fusion_NetworkString`
    # is a codegen name, not `@class`)
    out = _BACKTICK_RX.sub(lambda m: '_' + m.group(0)[1:], full).replace('+', '.').replace('/', '.')
    if '@' in out:
        out = _MIDAT_RX.sub('_', out)
    return out

# ----------------------------------------------------------------------------
# global-metadata.dat
# ----------------------------------------------------------------------------
