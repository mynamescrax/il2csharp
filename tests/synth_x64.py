"""Tiny x64 assembler for synthetic-byte peephole tests (no fixture).

A peephole claims one exact instruction shape. Feeding it hand-built bytes
pins that shape in milliseconds, where a full build costs minutes: assemble
a few instructions, decode them with iced, call the function under test,
assert on the result.

Every helper emits one fixed encoding, so addresses are known up front and
labels/RIP-relative displacements resolve in a single second pass.
"""
import struct

BASE = 0x180001000


class Asm:
    def __init__(self, base=BASE):
        self.base = base
        self.items = []     # (kind, payload)

    # -- structure
    def label(self, name):
        self.items.append(('label', name))
        return self

    def raw(self, hexstr):
        self.items.append(('raw', bytes.fromhex(hexstr.replace(' ', ''))))
        return self

    # -- fixed-encoding instructions (RIP-relative operands take absolute VAs)
    def cmp_b(self, slot, imm=0):           # cmp byte [rip+slot],imm8
        self.items.append(('rip', (bytes.fromhex('803d'), slot, bytes([imm & 0xFF]))))
        return self

    def cmp_d(self, slot, imm=0):           # cmp dword [rip+slot],imm8
        self.items.append(('rip', (bytes.fromhex('833d'), slot, bytes([imm & 0xFF]))))
        return self

    def st_b(self, slot, val=1):            # mov byte [rip+slot],imm8
        self.items.append(('rip', (bytes.fromhex('c605'), slot, bytes([val & 0xFF]))))
        return self

    def lea_rcx(self, slot):                # lea rcx,[rip+slot]
        self.items.append(('rip', (bytes.fromhex('488d0d'), slot, b'')))
        return self

    def lea_rax(self, target):              # lea rax,[rip+target]  (slot VA or label)
        self.items.append(('rip', (bytes.fromhex('488d05'), target, b'')))
        return self

    def lea_rcx_rsp(self, disp):            # lea rcx,[rsp+disp8]
        self.items.append(('raw', bytes.fromhex('488d4c24') + bytes([disp & 0xFF])))
        return self

    def mov_rax_rip(self, slot):            # mov rax,[rip+slot]
        self.items.append(('rip', (bytes.fromhex('488b05'), slot, b'')))
        return self

    def mov_rip_rax(self, slot):            # mov [rip+slot],rax
        self.items.append(('rip', (bytes.fromhex('488905'), slot, b'')))
        return self

    def mov_rsp_imm(self, disp, imm):       # mov qword [rsp+disp8],imm32 (sign-extended)
        self.items.append(('raw', bytes.fromhex('48c74424') + bytes([disp & 0xFF])
                           + struct.pack('<i', imm)))
        return self

    def mov_rsp_rax(self, disp):            # mov [rsp+disp8],rax
        self.items.append(('raw', bytes.fromhex('48894424') + bytes([disp & 0xFF])))
        return self

    def mov_rsp_eax(self, disp):            # mov [rsp+disp8],eax
        self.items.append(('raw', bytes.fromhex('894424') + bytes([disp & 0xFF])))
        return self

    def mov_rsp_dword(self, disp, imm):     # mov dword [rsp+disp8],imm32
        self.items.append(('raw', bytes.fromhex('c74424') + bytes([disp & 0xFF])
                           + struct.pack('<i', imm)))
        return self

    def mov_rsp_byte(self, disp, value):    # mov byte [rsp+disp8],imm8
        self.items.append(('raw', bytes.fromhex('c64424') + bytes([disp & 0xFF, value & 0xFF])))
        return self

    def test_rax_rax(self):                 # test rax,rax
        return self.raw('4885c0')

    def xor_eax_eax(self):                  # xor eax,eax
        return self.raw('31c0')

    def sub_rsp(self, n):                   # sub rsp,imm8
        return self.raw('4883ec' + '%02x' % (n & 0xFF))

    def data(self, blob):
        self.items.append(('raw', blob if isinstance(blob, bytes) else bytes.fromhex(blob)))
        return self

    def call(self, target):                 # call rel32 to an absolute VA
        self.items.append(('rel32', (bytes.fromhex('e8'), target)))
        return self

    def jne(self, label):                   # jne rel32
        self.items.append(('rel32', (bytes.fromhex('0f85'), label)))
        return self

    def je(self, label):
        self.items.append(('rel32', (bytes.fromhex('0f84'), label)))
        return self

    def jmp(self, label):
        self.items.append(('rel32', (bytes.fromhex('e9'), label)))
        return self

    def ret(self):
        return self.raw('c3')

    def nop(self):
        return self.raw('90')

    def int3(self):
        return self.raw('cc')

    def assemble(self):
        # pass 1: addresses
        addr = self.base
        labels = {}
        sizes = []
        for kind, p in self.items:
            if kind == 'label':
                labels[p] = addr
                sizes.append(0)
                continue
            if kind == 'raw':
                n = len(p)
            elif kind == 'rip':
                n = len(p[0]) + 4 + len(p[2])
            else:
                n = len(p[0]) + 4
            sizes.append(n)
            addr += n
        # pass 2: bytes
        out = bytearray()
        addr = self.base
        for (kind, p), n in zip(self.items, sizes):
            if kind == 'label':
                continue
            nxt = addr + n
            if kind == 'raw':
                out += p
            elif kind == 'rip':
                tgt = labels[p[1]] if isinstance(p[1], str) else p[1]
                out += p[0] + struct.pack('<i', tgt - nxt) + p[2]
            else:
                tgt = labels[p[1]] if isinstance(p[1], str) else p[1]
                out += p[0] + struct.pack('<i', tgt - nxt)
            addr = nxt
        self.labels = labels
        return bytes(out)

    def insns(self):
        from iced_x86 import Decoder, DecoderOptions
        code = self.assemble()
        dec = Decoder(64, code, DecoderOptions.NONE)
        dec.ip = self.base
        return list(dec)

    def addr_of(self, label):
        self.assemble()
        return self.labels[label]
