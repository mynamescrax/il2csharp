"""P/Invoke marshalling stubs: recover the DllImport declaration from the bytes (fix 145).

A managed `[DllImport] static extern` method has no body. IL2CPP compiles it
to a marshalling stub whose first act is to resolve the native function once
and cache it:

    mov  rax,[rip+CELL]          ; cached function pointer
    test rax,rax
    jne  CALL_IT
    ...fill a PInvokeArguments on the stack...
    lea  rcx,[that struct]
    call il2cpp_codegen_resolve_pinvoke<..>
    mov  [rip+CELL],rax
  CALL_IT: ...marshal the arguments, `call rax`, marshal the result...

The struct is libil2cpp's `PInvokeArguments` (il2cpp-pinvoke-support.h):

    +0x00 moduleName.str   (Il2CppNativeChar*: UTF-16 on Windows)
    +0x08 moduleName.length (characters)
    +0x10 entryPoint.str   (char*)
    +0x18 entryPoint.length
    +0x20 callingConvention  Il2CppCallConvention: 0 default, 1 C, 2 stdcall,
                             3 thiscall, 4 fastcall, 5 vararg
    +0x24 charSet            Il2CppCharSet: 0 ansi, 1 unicode, 2 not specified
    +0x28 parameterSize
    +0x2C isNoMangle         (ExactSpelling)

Reading those eight stores back gives the library name, the entry point and
the attribute arguments of the original `[DllImport(...)]` -- ground truth
from the binary, where the lifted marshalling body is compiler plumbing. The
recovery is structural: the stores are tracked against a model of the frame
(`rsp` moves, `mov r11,rsp` copies, `lea` of a stack slot), the resolver call
is the one whose first argument addresses a fully-populated struct, and the
instruction after it stores RAX into a RIP-relative cell. Anything that does
not prove all eight fields and both strings declines to None.
"""
from il2cpp.prelude import *  # noqa: F401,F403
from il2cpp.text import imm_of, reg_name

MAX_INSNS = 200

# Il2CppCallConvention -> System.Runtime.InteropServices.CallingConvention
# member (None = the DllImport default, Winapi). 5 (vararg) has no member.
CALL_CONV = {0: None, 1: 'Cdecl', 2: 'StdCall', 3: 'ThisCall', 4: 'FastCall'}
# Il2CppCharSet -> CharSet member (None = unspecified).
CHAR_SET = {0: 'Ansi', 1: 'Unicode', 2: None}

_FIELD_OFFSETS = (0x00, 0x08, 0x10, 0x18, 0x20, 0x24, 0x28, 0x2C)
_VOLATILE = ('RAX', 'RCX', 'RDX', 'R8', 'R9', 'R10', 'R11')

def _cs_string(s):
    return '"%s"' % s.replace('\\', '\\\\').replace('"', '\\"')


def dllimport_attribute(args, method_name):
    """The `[DllImport(...)]` line for decoded `PInvokeArguments`, or None.

    Fully qualified: the attribute is spliced outside the type body, where
    the file's `using` set is not consulted. `EntryPoint` only appears when
    it differs from the managed name, and each attribute argument only when
    the binary recorded a value C# can spell (an unknown enum declines the
    whole declaration rather than guessing a convention)."""
    cc = CALL_CONV.get(args['call_conv'], 'decline')
    cs = CHAR_SET.get(args['char_set'], 'decline')
    if cc == 'decline' or cs == 'decline':
        return None
    opts = []
    if args['entry'] != method_name:
        opts.append('EntryPoint = %s' % _cs_string(args['entry']))
    if cc:
        opts.append('CallingConvention = System.Runtime.InteropServices.CallingConvention.%s' % cc)
    if cs:
        opts.append('CharSet = System.Runtime.InteropServices.CharSet.%s' % cs)
    if args['no_mangle']:
        opts.append('ExactSpelling = true')
    head = '[System.Runtime.InteropServices.DllImport(%s' % _cs_string(args['module'])
    if opts:
        head += ', ' + ', '.join(opts)
    return head + ')]'


def _ascii_text(raw):
    if not raw or any(b < 0x20 or b >= 0x7F for b in raw):
        return None
    return raw.decode('ascii')


def _read_wide(binary, ptr, length):
    """`length` UTF-16LE characters at `ptr`, NUL-terminated, printable ASCII."""
    if not 0 < length <= 260:
        return None
    raw = binary.read(ptr, 2 * length + 2)
    if raw is None or len(raw) != 2 * length + 2 or raw[-2:] != b'\x00\x00':
        return None
    body = raw[:-2]
    if body[1::2] != b'\x00' * length:
        return None
    return _ascii_text(body[0::2])


def _read_narrow(binary, ptr, length):
    if not 0 < length <= 512:
        return None
    raw = binary.read(ptr, length + 1)
    if raw is None or len(raw) != length + 1 or raw[-1:] != b'\x00':
        return None
    return _ascii_text(raw[:-1])


def _frame_addr(ins, rsp, regs):
    """`('frame', off)` for a stack memory operand, `('abs', va)` for a
    RIP-relative one, else None. `off` is relative to the entry RSP."""
    if ins.memory_index != IReg.NONE:
        return None
    base = ins.memory_base
    if base == IReg.RIP:
        return ('abs', ins.ip_rel_memory_address)
    disp = ins.memory_displacement
    if disp > 0x7FFFFFFFFFFFFFFF:
        disp -= 1 << 64
    if base == IReg.RSP:
        return ('frame', rsp + disp)
    fam = reg_name(base)
    v = regs.get(fam)
    if v is not None and v[0] == 'frame':
        return ('frame', v[1] + disp)
    return None


def stub_arguments(binary, va, max_insns=MAX_INSNS):
    """`PInvokeArguments` of the marshalling stub at `va`, or None.

    Returns `{'module', 'entry', 'call_conv', 'char_set', 'param_size',
    'no_mangle', 'cell'}` with the decoded strings and raw enum values."""
    if not HAVE_ICED or binary is None:
        return None
    try:
        if not binary.is_exec_va(va):
            return None
        code = binary.read(va, 2048)
        if not code:
            return None
        dec = Decoder(64, code, DecoderOptions.NONE)
        dec.ip = va
        insns = []
        for ins in dec:
            insns.append(ins)
            if len(insns) >= max_insns:
                break
        return _scan(binary, insns)
    except Exception:
        return None


def _scan(binary, insns):
    M = Mnemonic
    rsp = 0
    regs = {}
    frame = {}              # off -> (size, ('imm', v) | ('ptr', va))
    prev = None
    for k, ins in enumerate(insns):
        mn = ins.mnemonic
        op0, op1 = ins.op0_kind, ins.op1_kind
        before, prev = prev, ins
        if mn == M.JNE and before is not None:
            # `test r,r ; jne CACHED`: the arm that falls through is the
            # unresolved one, where the cell register is zero -- and the
            # compiler reuses it as the constant 0 for the struct stores
            if (before.mnemonic == M.TEST and before.op0_kind == OpKind.REGISTER
                    and before.op1_kind == OpKind.REGISTER
                    and before.op0_register == before.op1_register):
                regs[reg_name(before.op0_register)] = ('imm', 0)
            continue
        if mn == M.PUSH:
            rsp -= 8
            frame.pop(rsp, None)
            continue
        if mn == M.POP:
            rsp += 8
            if op0 == OpKind.REGISTER:
                regs.pop(reg_name(ins.op0_register), None)
            continue
        if mn in (M.SUB, M.ADD) and op0 == OpKind.REGISTER and ins.op0_register == IReg.RSP:
            if op1 not in (OpKind.IMMEDIATE8, OpKind.IMMEDIATE8TO16, OpKind.IMMEDIATE8TO32,
                           OpKind.IMMEDIATE8TO64, OpKind.IMMEDIATE16, OpKind.IMMEDIATE32,
                           OpKind.IMMEDIATE32TO64):
                return None
            imm = imm_of(ins, 1)
            rsp += imm if mn == M.ADD else -imm
            continue
        if mn in (M.RET, M.JMP, M.INT3, M.UD2):
            return None
        if mn == M.CALL:
            if ins.op0_kind != OpKind.NEAR_BRANCH64:
                regs.clear()
                frame.clear()
                continue
            res = _resolver_call(binary, insns, k, regs, frame)
            if res is not None:
                return res
            for r in _VOLATILE:
                regs.pop(r, None)
            continue
        if mn == M.LEA and op0 == OpKind.REGISTER:
            fam = reg_name(ins.op0_register)
            a = _frame_addr(ins, rsp, regs)
            if a is None:
                regs.pop(fam, None)
            elif a[0] == 'abs':
                regs[fam] = ('ptr', a[1])
            else:
                regs[fam] = ('frame', a[1])
            continue
        if mn == M.MOV and op0 == OpKind.REGISTER:
            fam = reg_name(ins.op0_register)
            if op1 == OpKind.REGISTER:
                src = reg_name(ins.op1_register)
                if ins.op1_register == IReg.RSP:
                    regs[fam] = ('frame', rsp)
                elif src in regs:
                    regs[fam] = regs[src]
                else:
                    regs.pop(fam, None)
            elif op1 in (OpKind.IMMEDIATE8, OpKind.IMMEDIATE16, OpKind.IMMEDIATE32,
                         OpKind.IMMEDIATE64, OpKind.IMMEDIATE8TO16, OpKind.IMMEDIATE8TO32,
                         OpKind.IMMEDIATE8TO64, OpKind.IMMEDIATE32TO64):
                regs[fam] = ('imm', imm_of(ins, 1) & 0xFFFFFFFFFFFFFFFF)
            else:
                regs.pop(fam, None)
            continue
        if mn == M.XOR and op0 == OpKind.REGISTER and op1 == OpKind.REGISTER \
                and ins.op0_register == ins.op1_register:
            regs[reg_name(ins.op0_register)] = ('imm', 0)
            continue
        if mn == M.MOV and op0 == OpKind.MEMORY:
            a = _frame_addr(ins, rsp, regs)
            size = MemorySizeExt.size(ins.memory_size) or 0
            if a is None:
                frame.clear()
            elif a[0] == 'frame' and size:
                for off in [o for o, (sz, _v) in frame.items()
                            if o < a[1] + size and a[1] < o + sz]:
                    del frame[off]
                val = None
                if op1 == OpKind.REGISTER:
                    val = regs.get(reg_name(ins.op1_register))
                    if val is not None and val[0] == 'imm':
                        val = ('imm', val[1] & ((1 << (8 * size)) - 1))
                    elif val is not None and not (val[0] == 'ptr' and size == 8):
                        val = None
                elif op1 != OpKind.MEMORY:
                    val = ('imm', imm_of(ins, 1) & ((1 << (8 * size)) - 1))
                if val is not None:
                    frame[a[1]] = (size, val)
            elif a[0] == 'frame':
                frame.clear()
            continue
        # anything else: forget what it writes
        if op0 == OpKind.REGISTER:
            regs.pop(reg_name(ins.op0_register), None)
        elif op0 == OpKind.MEMORY:
            a = _frame_addr(ins, rsp, regs)
            if a is None or a[0] == 'frame':
                frame.clear()
    return None


def _field(frame, off, want):
    """The value stored at `off` as a `want`-byte field: an exact store, or a
    slice of a wider immediate store (the compiler fuses adjacent dword
    fields, `mov qword [rsp+44h],1` = charset 1, parameterSize 0)."""
    ent = frame.get(off)
    if ent is not None and ent[0] == want:
        return ent[1]
    for o, (sz, v) in frame.items():
        if o <= off and off + want <= o + sz and v[0] == 'imm':
            return ('imm', (v[1] >> (8 * (off - o))) & ((1 << (8 * want)) - 1))
    return None


def _resolver_call(binary, insns, k, regs, frame):
    """The call at `insns[k]` if RCX addresses a complete PInvokeArguments."""
    rcx = regs.get('RCX')
    if rcx is None or rcx[0] != 'frame':
        return None
    base = rcx[1]
    vals = []
    for off, want in zip(_FIELD_OFFSETS, (8, 8, 8, 8, 4, 4, 4, 1)):
        v = _field(frame, base + off, want)
        if v is None:
            return None
        vals.append(v)
    mod_p, mod_n, ent_p, ent_n, conv, cs, psz, nomangle = vals
    if mod_p[0] != 'ptr' or ent_p[0] != 'ptr':
        return None
    if mod_n[0] != 'imm' or ent_n[0] != 'imm':
        return None
    if any(v[0] != 'imm' for v in (conv, cs, psz, nomangle)):
        return None
    module = _read_wide(binary, mod_p[1], mod_n[1])
    entry = _read_narrow(binary, ent_p[1], ent_n[1])
    if module is None or entry is None:
        return None
    # the resolved pointer is cached in a RIP-relative cell right after the
    # call; the compiler may first copy it to another register
    st = None
    for nxt in insns[k + 1:k + 4]:
        if (nxt.mnemonic == Mnemonic.MOV and nxt.op0_kind == OpKind.MEMORY
                and nxt.memory_base == IReg.RIP and nxt.op1_kind == OpKind.REGISTER
                and nxt.op1_register == IReg.RAX
                and (MemorySizeExt.size(nxt.memory_size) or 0) == 8):
            st = nxt
            break
        if not (nxt.mnemonic == Mnemonic.MOV and nxt.op0_kind == OpKind.REGISTER
                and nxt.op1_kind == OpKind.REGISTER and nxt.op1_register == IReg.RAX):
            return None
    if st is None:
        return None
    return {'module': module, 'entry': entry, 'call_conv': conv[1], 'char_set': cs[1],
            'param_size': psz[1], 'no_mangle': bool(nomangle[1]),
            'cell': st.ip_rel_memory_address}
