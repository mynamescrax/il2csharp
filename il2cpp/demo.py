"""Build a tiny, original v31/x64 input for the CLI. No Unity SDK or game data.

Only the on-disk tables needed by the example are populated. The PE has no
entry point or imports: it is input to the reader, never loaded as a library.
"""
from pathlib import Path
from struct import pack, pack_into

from il2cpp.metadata import HEADER_TABLES


BASE = 0x180000000
TEXT, RDATA, PDATA = 0x1000, 0x2000, 0x3000
INT, BOOL, VOID = 3, 4, 5  # Il2CppType indices after the three classes

# (image, type, optional int field, methods). Each method is
# (name, return type, int argument names, static, Win64 instructions).
TYPES = (
    ('Assembly-CSharp.dll', 'ScoreRules', None, (
        ('StartingScore', INT, (), True, 'b8 0a000000 c3'),   # mov eax,10; ret
        ('AddBonus', INT, ('score', 'bonus'), True, '8b c1 03 c2 c3'),
        ('IsWinning', BOOL, ('score',), True, '83 f9 64 0f 9d c0 c3'),  # score >= 100
        ('DecodeNetworkScore', INT, ('packed',), True, '8b c1 0f c8 c3'),  # bswap eax
        ('ClampAtZero', INT, ('points',), True, '85 c9 7f 03 31 c0 c3 8b c1 c3'),
    )),
    ('Assembly-CSharp.dll', 'ScoreBoard', 'score', (
        ('SetScore', VOID, ('points',), False, '89 51 10 c3'),
        ('ReadScore', INT, (), False, '8b 41 10 c3'),
    )),
    ('Demo.Clock.dll', 'RoundTimer', 'remaining', (
        ('SecondsLeft', INT, (), False, '8b 41 10 c3'),
        ('HasExpired', BOOL, (), False, '83 79 10 00 0f 9e c0 c3'),  # remaining <= 0
    )),
)
IMAGES = tuple(dict.fromkeys(t[0] for t in TYPES))


def _metadata():
    tables = {name: bytearray() for name, _ in HEADER_TABLES}
    strings = {}

    def string(s):
        if s not in strings:
            strings[s] = len(tables['string'])
            tables['string'] += s.encode() + b'\0'
        return strings[s]

    string('')
    fi = mi = pi = 0
    for image_index, image in enumerate(IMAGES):
        indices = [i for i, td in enumerate(TYPES) if td[0] == image]
        tables['images'] += pack('<10i', string(image), image_index, indices[0],
                                 len(indices), -1, 0, -1, 1, -1, 0)
        rid = 1  # method tokens are image-local
        field_rid = param_rid = 1
        for type_rid, ti in enumerate(indices, 1):
            _, name, field, methods = TYPES[ti]
            tables['typeDefinitions'] += pack(
                '<16i8HII', string(name), string('Demo'), ti, -1, -1, ti, -1,
                1 if field else 0x181, fi if field else -1, mi, *([-1] * 6),
                len(methods), 0, int(bool(field)), 0, 0, 0, 0, 0, 0, 0x02000000 | type_rid)
            if field:
                tables['fields'] += pack('<3i', string(field), INT, 0x04000000 | field_rid)
                fi += 1
                field_rid += 1
            for name, ret, args, static, _ in methods:
                tables['methods'] += pack('<7i4H', string(name), ti, ret, 0,
                                          pi if args else -1, -1, 0x06000000 | rid,
                                          0x16 if static else 6, 0, 0xffff, len(args))
                rid += 1
                mi += 1
                for arg in args:
                    tables['parameters'] += pack('<3i', string(arg), 0x08000000 | param_rid, INT)
                    pi += 1
                    param_rid += 1

    literal = b'Round complete!'
    tables['stringLiteral'] += pack('<II', len(literal), 0)
    tables['stringLiteralData'] += literal
    header = bytearray(pack('<II', 0xfab11baf, 31))
    body = bytearray()
    start = 8 + len(HEADER_TABLES) * 8
    for name, _ in HEADER_TABLES:
        body.extend(bytes(-len(body) % 4))
        header += pack('<II', start + len(body), len(tables[name]))
        body += tables[name]
    return header + body


def _sections():
    text, data, pdata = bytearray(), bytearray(), bytearray()

    def put(blob):
        data.extend(bytes(-len(data) % 8))
        va = BASE + RDATA + len(data)
        data.extend(blob)
        return va

    def words(*values):
        return put(pack('<%dQ' % len(values), *values))

    module_vas = []
    unwind = put(b'\x01\x00\x00\x00')  # version 1, no unwind codes
    for image in IMAGES:
        ptrs = []
        for owner, _, _, methods in TYPES:
            if owner != image:
                continue
            for _, _, _, _, hex_bytes in methods:
                text.extend(b'\xcc' * (-len(text) % 16))
                rva = TEXT + len(text)
                text.extend(bytes.fromhex(hex_bytes))
                ptrs.append(BASE + rva)
                pdata.extend(pack('<III', rva, TEXT + len(text), unwind - BASE))
        module_vas.append(words(put(image.encode() + b'\0'), len(ptrs), words(*ptrs),
                                *([0] * 11)))
    words(*([0] * 17), len(IMAGES), words(*module_vas))  # CodeRegistration

    # Il2CppType {data, bits}; the int descriptor also carries public field visibility.
    types = [words(i, 0x12 << 16) for i in range(len(TYPES))]
    types.extend(words(0, bits) for bits in ((0x08 << 16) | 6, 0x02 << 16, 0x01 << 16))
    offsets = words(*(put(pack('<I', 0x10)) if t[2] else 0 for t in TYPES))
    sizes = words(*(put(pack('<IiII', 24 if t[2] else 16, -1, 0, 0)) for t in TYPES))
    words(0, 0, 0, 0, 0, 0, len(types), words(*types), 0, 0,
          len(TYPES), offsets, len(TYPES), sizes, 0, 0)  # MetadataRegistration
    return ((b'.text', TEXT, text, 0x60000020), (b'.rdata', RDATA, data, 0x40000040),
            (b'.pdata', PDATA, pdata, 0x40000040))


def _pe():
    sections = _sections()
    pe = 0x80
    opt = pe + 24
    opt_size = 0xf0
    buf = bytearray(0x200)  # file alignment; all section headers fit here
    buf[:2] = b'MZ'
    pack_into('<I', buf, 0x3c, pe)
    pack_into('<4sHHIIIHH', buf, pe, b'PE\0\0', 0x8664, len(sections), 0, 0, 0,
              opt_size, 0x2022)
    pack_into('<H', buf, opt, 0x20b)
    pack_into('<IQII', buf, opt + 20, TEXT, BASE, 0x1000, 0x200)
    pack_into('<II', buf, opt + 56, PDATA + 0x1000, len(buf))
    pack_into('<H', buf, opt + 68, 3)  # console subsystem
    pack_into('<I', buf, opt + 108, 16)
    pack_into('<II', buf, opt + 112 + 3 * 8, PDATA, len(sections[2][2]))
    for i, (name, rva, content, flags) in enumerate(sections):
        raw_size = (len(content) + 0x1ff) & ~0x1ff
        pack_into('<8sIIII12xI', buf, opt + opt_size + i * 40, name, len(content),
                  rva, raw_size, len(buf), flags)
        buf.extend(content)
        buf.extend(bytes(raw_size - len(content)))
    return buf


def write_demo(root):
    """Populate a fresh temporary directory using Unity's usual file layout."""
    root = Path(root)
    metadata_dir = root / 'Demo_Data' / 'il2cpp_data' / 'Metadata'
    metadata_dir.mkdir(parents=True)
    (metadata_dir / 'global-metadata.dat').write_bytes(_metadata())
    (root / 'GameAssembly.dll').write_bytes(_pe())
