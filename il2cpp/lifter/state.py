from il2cpp.prelude import *  # noqa: F401,F403
from il2cpp.expr import Expr, _BINDABLE_KINDS, _RegState, _USE_BIND_MIN, _bind_replace, _is_unresolved_gp, _mentions
from il2cpp.initguard import metadata_init_guards
from il2cpp.metadata import MethodDef, TypeDef
from il2cpp.names import safe_ident
from il2cpp.runtime.core import Il2Cpp
from il2cpp.text import imm_of, reg_name, sdisp, strip_outer
from il2cpp.x64 import ARG_REGS, ARG_XMM, GPRS, GPR_ALIAS, VOLATILE

class _StateMixin:
    """Lift one native method body to pseudo-C# statements."""

    def __init__(self, il2: Il2Cpp, asm_comments=False):
        self.il = il2
        self.bin = il2.bin
        self.meta = il2.meta
        self.asm_comments = asm_comments
        self.dry = False       # decompiler pass 1 suppresses use-binding
        self._cur_ip = 0
        self._copying = False  # a reg-reg move re-homes a value; not a use
        self._init_runtime_ids()

    # Runtime-helper arity: the Win64 register spray pads a call with the
    # leftover GPR/XMM residues, and these helpers legitimately read only
    # the first couple arguments. arity is keyed by the rt_names string,
    # so `_call_name` wiring (which follows jmp thunks too) carries it.
    RT_ARITY = {
        'il2cpp_codegen_initialize_runtime_metadata': 1,
        'il2cpp_object_new': 1,
        'il2cpp_codegen_write_barrier': 2,
        'il2cpp_runtime_class_init': 1,
        'il2cpp_interface_get_method': 3,
        'il2cpp_array_addr': 2,
    }

    @staticmethod
    def _return_value_register(rty):
        """Win64 register carrying a scalar managed return value.

        Single and Double values use XMM0.  Their by-reference forms return
        an address and therefore use RAX despite retaining the R4/R8 element
        enum in metadata.  Other value/reference returns also use RAX; large
        structs are handled separately by the hidden sret-buffer path.
        """
        if isinstance(rty, tuple) and len(rty) >= 2:
            bits = rty[1]
            if ((bits >> 16) & 0xFF) in (0x0c, 0x0d) \
                    and not ((bits >> 29) & 1):
                return 'XMM0'
        return 'RAX'

    def _is_scalar_sqrt_helper(self, target):
        """Recognize the unregistered double sqrt/domain wrapper by proof.

        Unity's Windows player calls a CRT-style helper on the negative/NaN
        arm of an inlined sqrt diamond.  It has no MethodDef or export, so an
        address/name guess would be target-specific.  Require the helper's
        complete local signature instead: XMM0 double spill/return, a scalar
        SQRTSD path, and the RIP-relative error-name literal ``sqrt``.  A
        different runtime stays unrecognized and therefore keeps the honest
        fallback.
        """
        if not HAVE_ICED or not target or not self.bin.is_exec_va(target):
            return False
        if self.il.addr_candidates.get(target) or target in self.bin.exports:
            return False
        start, finish = self.il.function_extent(target)
        if start != target or finish is None or not 0 < finish - target <= 0x400:
            return False
        code = self.bin.read(target, finish - target)
        if not code:
            return False
        try:
            dec = Decoder(64, code, DecoderOptions.NONE)
            dec.ip = target
            insns = list(dec)
        except Exception:
            return False
        spilled = rooted = named = returned = loaded = False
        for ins in insns:
            if (ins.mnemonic == Mnemonic.MOVSD
                    and ins.op0_kind == OpKind.MEMORY
                    and ins.memory_base == IReg.RSP
                    and ins.op1_kind == OpKind.REGISTER
                    and reg_name(ins.op1_register) == 'XMM0'):
                spilled = True
            elif ins.mnemonic == Mnemonic.SQRTSD:
                rooted = True
            elif (ins.mnemonic == Mnemonic.LEA
                    and ins.op0_kind == OpKind.REGISTER
                    and reg_name(ins.op0_register) == 'RCX'
                    and ins.op1_kind == OpKind.MEMORY
                    and ins.memory_base == IReg.RIP):
                named = self.bin.cstr(ins.ip_rel_memory_address, 32) == 'sqrt' or named
            elif (ins.mnemonic == Mnemonic.MOVSD
                    and ins.op0_kind == OpKind.REGISTER
                    and reg_name(ins.op0_register) == 'XMM0'
                    and ins.op1_kind == OpKind.MEMORY
                    and ins.memory_base == IReg.RSP):
                loaded = True
            elif ins.mnemonic == Mnemonic.RET:
                returned = True
        return spilled and rooted and named and loaded and returned

    def _iface_dispatch_arity(self, target):
        """Recognize an interface-offset dispatcher; return its managed
        argument count (0 or 1), or None when the body is not one.

        Unity compiles a call through an interface into a helper that
        searches the receiver class's interface table for the interface
        klass, computes the method entry as
        ``klass + 0x138 + (interfaceOffset + slot) * 16`` and tail-jumps
        into it. The fixture's hot family members (0x180002210 and
        0x180002380 among them) carry different prologues from the byte
        template `_nullary_interface_dispatch` pins, but the same
        arithmetic: exactly one ``movzx ..., word [k+0x12E]`` interface
        count, exactly one ``mov ..., [k+0xB0]`` interface table, exactly
        one ``add ..., 0x138`` and one ``shl ..., 4`` method-entry fold,
        an indirect tail jmp, and a call on the miss path. A read of R9 --
        the register right after the (slot, iface, receiver) triple --
        means the helper forwards one managed argument. A different
        runtime keeps the honest `sub_` fallback.
        """
        if not HAVE_ICED or not target or not self.bin.is_exec_va(target):
            return None
        if self.il.addr_candidates.get(target) or target in self.bin.exports:
            return None
        start, finish = self.il.function_extent(target)
        if start != target or finish is None or not 0x20 < finish - target <= 0x400:
            return None
        code = self.bin.read(target, finish - target)
        if not code:
            return None
        try:
            dec = Decoder(64, code, DecoderOptions.NONE)
            dec.ip = target
            insns = list(dec)
        except Exception:
            return None
        n_count = n_table = n_add = n_shl = n_tail = n_call = 0
        r9_first = None
        for ins in insns:
            if ins.mnemonic == Mnemonic.MOVZX \
                    and ins.op1_kind == OpKind.MEMORY \
                    and ins.memory_displacement == 0x12E:
                n_count += 1
            elif ins.mnemonic == Mnemonic.MOV \
                    and ins.op0_kind == OpKind.REGISTER \
                    and ins.op1_kind == OpKind.MEMORY \
                    and ins.memory_displacement == 0xB0 \
                    and ins.memory_base != IReg.RIP:
                n_table += 1
            elif ins.mnemonic == Mnemonic.ADD \
                    and ins.op1_kind in (OpKind.IMMEDIATE32TO64,
                                         OpKind.IMMEDIATE32) \
                    and ins.immediate32 == 0x138:
                n_add += 1
            elif ins.mnemonic == Mnemonic.SHL \
                    and ins.op1_kind == OpKind.IMMEDIATE8 \
                    and ins.immediate8 == 4:
                n_shl += 1
            elif ins.mnemonic == Mnemonic.JMP \
                    and ins.op0_kind in (OpKind.REGISTER, OpKind.MEMORY):
                n_tail += 1
            elif ins.mnemonic == Mnemonic.CALL \
                    and ins.op0_kind == OpKind.NEAR_BRANCH64:
                n_call += 1
            # a forwarded managed argument is live on entry: the FIRST
            # touch of R9 decides. A read (source operand, memory base /
            # index, CMP/TEST/JMP/CALL/PUSH/XCHG position) proves the
            # caller passed it; a write (MOV/ZERO/LEA/arithmetic dest,
            # POP) manufactures it inside. The byte-template variant's
            # `xor r9d,r9d` and 0x180540f50's `mov r9,[rip]` + klass
            # compare are writes-first: their callers pass one RCX arg,
            # and forwarding would invent a bogus argument.
            if r9_first is None:
                r9_first = self._r9_touch(ins)
        if n_count == 1 and n_table == 1 and n_add == 1 and n_shl == 1 \
                and n_tail and n_call:
            return 1 if r9_first == 'read' else 0
        return None

    @staticmethod
    def _r9_touch(ins):
        """'read' / 'write' / None for R9's role in one instruction.

        Memory base/index registers are always read, even in a store.
        CMP/TEST read both sides; JMP/CALL/PUSH/XCHG read their
        register operand; every other R9 destination writes. Never
        raises (an unreadable instruction is no touch).
        """
        try:
            R9 = IReg.R9
            if getattr(ins, 'memory_base', None) == R9 \
                    or getattr(ins, 'memory_index', None) == R9:
                return 'read'
            o0 = ins.op0_kind == OpKind.REGISTER and ins.op0_register == R9
            o1 = ins.op1_kind == OpKind.REGISTER and ins.op1_register == R9
            if o0 and o1:
                # same-register both sides: zeroing idioms (`xor
                # r9,r9`) manufacture the value, identities read it.
                if ins.mnemonic in (Mnemonic.XOR, Mnemonic.SUB):
                    return 'write'
                return 'read'
            if o0 and ins.mnemonic in (Mnemonic.CMP, Mnemonic.TEST,
                                        Mnemonic.JMP, Mnemonic.CALL,
                                        Mnemonic.PUSH, Mnemonic.XCHG):
                return 'read'
            if o1:
                return 'read'
            if o0:
                return 'write'
        except Exception:
            pass
        return None

    def _iface_arity(self, target):
        """Memoized interface-dispatcher arity (the rt_iface proof on demand).

        The eager sample behind `_init_runtime_ids` is
        Assembly-CSharp-only, so parameterized family members never
        land in `rt_iface`. Callers consult this choke instead of the
        raw dict: cached members answer identically, new members are
        proved structurally once per instance (VAs are binary-local).
        Never raises.
        """
        try:
            if target is None:
                return None
            d = self.__dict__.setdefault('rt_iface', {})
            if target in d:
                return d[target]
            ar = self._iface_dispatch_arity(target)
            if ar is not None:
                d[target] = ar
            return ar
        except Exception:
            return None

    def _is_isinst_helper(self, target):
        """Recognize the IsInst helper `(obj, klass) -> obj-or-null`.

        The fixture's hot thunk 0x180434690 forwards to 0x180479f80, but the
        address is never the proof: the body must have the fixed prologue
        (klass in RDX, object in RCX, null check), the `call` to
        Class::IsAssignableFrom, exactly one indirect `call qword [rax+10h]`
        on the interface fallback, the System.Object short-circuit
        `cmp rbx,[rip]; cmove rax,rdi`, and return. A different runtime keeps
        the honest `sub_` fallback.
        """
        if not HAVE_ICED or not target or not self.bin.is_exec_va(target):
            return False
        if self.il.addr_candidates.get(target) or target in self.bin.exports:
            return False
        start, finish = self.il.function_extent(target)
        if start != target or finish is None or not 0x40 < finish - target <= 0x400:
            return False
        code = self.bin.read(target, finish - target)
        if not code:
            return False
        if not code.startswith(bytes.fromhex(
                '48895c24104889742418574883ec20488bda488bf94885c9')):
            return False
        return (code.count(bytes.fromhex('483b1d')) >= 1
                and code.count(bytes.fromhex('480f44c7')) == 1
                and code.count(bytes.fromhex('ff5010')) == 1
                and code.rstrip(b'\xcc').endswith(b'\xc3'))

    def _is_interlocked_helper(self, target):
        """Recognize the Interlocked.CompareExchange helper.

        Exact body: `lock cmpxchg [rcx],rdx` with the comparand staged in
        RAX from R8, `cmovne` keeping the observed old value, a call (the
        GC write barrier for reference stores), and the old value in RAX.
        Only the write-barrier call displacement varies.
        """
        if not HAVE_ICED or not target or not self.bin.is_exec_va(target):
            return False
        if self.il.addr_candidates.get(target) or target in self.bin.exports:
            return False
        prefix = bytes.fromhex('40534883ec20498bd8498bc0f0480fb111480f45d8e8')
        suffix = bytes.fromhex('488bc34883c4205bc3')
        code = self.bin.read(target, len(prefix) + 4 + len(suffix))
        return code is not None and code.startswith(prefix) \
            and code[len(prefix) + 4:] == suffix

    def _is_class_init_helper(self, target):
        """Recognize the out-of-line class-init helper (56 bytes).

        `push rbx; sub rsp,20h; mov rbx,rcx; call Class::Init` then a
        fast-path return of the klass and a slow path through the
        `[klass+0xD8]` initializer cell. Only the three call displacements
        vary; naming the target `il2cpp_runtime_class_init` lets the
        existing one-argument class-init trim apply.
        """
        if not HAVE_ICED or not target or not self.bin.is_exec_va(target):
            return False
        if self.il.addr_candidates.get(target) or target in self.bin.exports:
            return False
        code = self.bin.read(target, 0x38)
        if code is None:
            return False
        pos = 0
        for lead, chunk, tail in (
                (0, '40534883ec20488bd9e8', 4),
                (0, '4883bbd8000000007509488bc34883c4205bc3488b8bd8000000e8', 0),
                (4, '488bc833d2e8', 4),
                (0, 'cc', 0)):
            pos += lead
            b = bytes.fromhex(chunk)
            if code[pos:pos + len(b)] != b:
                return False
            pos += len(b) + tail
        return True

    def _is_iface_resolve_helper(self, target):
        """Recognize the interface slow-path resolve helper.

        Ground truth: 0x18043dc60 (extent 0x89, 39 insns). The caller
        inlines the fast-path loop and calls here on miss with
        (RCX=receiver object, RDX=iface klass, R8=slot word). The body
        derefs the klass from the object (`mov rdi,[rcx]`), saves the
        iface (`mov rbp,rdx`) and slot (`movzx esi,r8w`), walks the
        interface table through two search calls plus a class-init-ish
        call, and returns the receiver on hit. The fail path calls a
        noreturn raiser and ends in int3. Four internal `call rel32`
        (only displacements vary); zero jmp refs. R9 is never read --
        the printed 4th arg is spray residue from the fast-path loop.
        Naming routes through `il2cpp_interface_get_method` with arity
        3 (obj, iface, slot). A different runtime keeps `sub_`.
        """
        if not HAVE_ICED or not target or not self.bin.is_exec_va(target):
            return False
        if self.il.addr_candidates.get(target) or target in self.bin.exports:
            return False
        start, finish = self.il.function_extent(target)
        if start != target or finish is None or not 0x40 < finish - target <= 0x400:
            return False
        code = self.bin.read(target, finish - target)
        if not code:
            return False
        if not code.startswith(bytes.fromhex(
                '48895c240848896c24104889742418574883ec20488b39488bd9488bcf410fb7f0')):
            return False
        return (code.count(bytes.fromhex('488beae867000000')) == 1
                and code.count(b'\xe8') == 4
                and bytes.fromhex('f6873601000010') in code
                and bytes.fromhex('48394310') in code
                and b'\xc3' in code
                and code.endswith(b'\xcc'))

    def _is_array_addr_helper(self, target):
        """Stride of the bounds-checked element-address helper, else None.

        Ground truth: 0x1803ed830 (stride 0x178 via `imul
        rax,rdx,imm32`) and 0x1803ed860 (stride 0x60 via
        `lea rax,[rdx+rdx*2]; shl rax,5`). Both are
        `(RCX=array, EDX=index) -> RAX = RCX+0x20+index*stride` with
        an unsigned `cmp edx,[rcx+0x18]; jae fail` OOB guard -- the
        Il2CppArray SZARRAY layout (length at +0x18, vector at +0x20).
        The template pins every byte but the two displacements (the
        jae must land exactly on the fail call, whose own displacement
        varies like the write-barrier one in the interlocked proof).
        Only the stride varies semantically; anything else keeps the
        honest `sub_`. Never hardcodes an address.
        """
        if not HAVE_ICED or not target or not self.bin.is_exec_va(target):
            return None
        if self.il.addr_candidates.get(target) or target in self.bin.exports:
            return None
        start, finish = self.il.function_extent(target)
        if start != target or finish is None or finish - target not in (34, 35):
            return None
        code = self.bin.read(target, finish - target)
        if not code or len(code) not in (34, 35):
            return None
        if code[0:7] != bytes.fromhex('4883ec283b5118') or code[7] != 0x73:
            return None
        if len(code) == 34:
            if code[9:12] != bytes.fromhex('4869c2'):
                return None
            stride = int.from_bytes(code[12:16], 'little')
            tail = bytes.fromhex('4883c0204803c14883c428c3e8')
            if code[16:29] != tail or len(code) != 34:
                return None
            call_off = 28
        else:
            if code[9:13] != bytes.fromhex('488d0452'):
                return None
            if code[13:16] != bytes.fromhex('48c1e0'):
                return None
            stride = 3 * (1 << code[16])
            tail = bytes.fromhex('4883c0204803c14883c428c3e8')
            if code[17:30] != tail or len(code) != 35:
                return None
            call_off = 29
        if code[8] != (call_off - 9) & 0xFF or code[call_off] != 0xE8:
            return None
        if code[-1] != 0xCC:
            return None
        if not 0 < stride < 0x100000:
            return None
        return stride

    def _array_addr_name(self, target):
        """Memoized lazy name for the element-address helper.

        The hot-target sample behind `_init_runtime_ids` is
        Assembly-CSharp-only, but these helpers serve TextMeshPro /
        TextCore -- so `_call_name` consults this on every otherwise
        unresolved target (the class-init-twin precedent): one
        structural proof per address, cached per instance (VAs are
        binary-local). Never raises.
        """
        try:
            cache = self.__dict__.setdefault('_array_addr_cache', {})
            if target in cache:
                return cache[target]
            name = None
            try:
                if target and self.bin.is_exec_va(target) \
                        and not (getattr(self.il, 'addr_candidates', None) or {}).get(target) \
                        and target not in (getattr(self.bin, 'exports', None) or {}) \
                        and target not in (getattr(self, 'rt_names', None) or {}):
                    _st = self._is_array_addr_helper(target)
                    if _st:
                        self.rt_names[target] = 'il2cpp_array_addr'
                        self.__dict__.setdefault('rt_array_addr', {})[target] = _st
                        name = 'il2cpp_array_addr'
            except Exception:
                name = None
            cache[target] = name
            return name
        except Exception:
            return None

    # ---- unregistered pure-FP32-unary leaves ---------------------------
    # Ground truth: 0x1804cdb00, the CRT log10f behind AudioVolumeSliders'
    # `sub_1804cdb00(volume)` (mi 23548/23549). The lift sprayed four stale
    # GPR arguments, bound an `object` result in RAX, and dropped the XMM0
    # float the following `mulss` consumes (`real2 = 0f * 20.0f`). The proof
    # below recovers the true shape -- one scalar float in XMM0, scalar
    # float out XMM0, no GPR/stack arguments, no caller-visible effects --
    # while the name stays the honest `sub_X`: the managed identity (e.g.
    # Mathf.Log10, whose registered target differs) is never inferred.
    _FP32_GPR_ARGS = ('RCX', 'RDX', 'R8', 'R9')
    _FP32_XMM_EXTRA = tuple('XMM%d' % i for i in range(1, 16))
    _FP32_XMM_HI = tuple('XMM%d' % i for i in range(6, 16))
    _FP32_NONVOL = ('RBX', 'RBP', 'RDI', 'RSI', 'R12', 'R13', 'R14', 'R15')

    def _fp32_table(self):
        """Operand-access classes for the leaf proof (built once, iced-only).

        Each entry maps a mnemonic to (kind, forms): kind `w1` writes op0
        only, `rw1` reads and writes op0, `rall` reads every operand,
        `vex3` is a 3-operand VEX write of op0, `ctrl` carries no register
        value. Forms use representative immediates; the matcher
        canonicalizes every immediate kind first, since width never changes
        an operand's read/write role. Anything absent declines -- the table
        is an allowlist, so an unknown instruction can only block the
        proof, never weaken it.
        """
        t = getattr(self, '_fp32_access', None)
        if t is not None:
            return t
        t = ({}, {})
        if HAVE_ICED:
            M, O = Mnemonic, OpKind
            R, MM = O.REGISTER, O.MEMORY
            I8, I32 = O.IMMEDIATE8, O.IMMEDIATE32
            RR, RM, MR = (R, R), (R, MM), (MM, R)
            RI8, RI32, MI8, MI32 = (R, I8), (R, I32), (MM, I8), (MM, I32)
            V3 = ((R, R, R), (R, R, MM), (R, R, I8))
            tab = {
                M.MOV: ('w1', (RR, RM, MR, RI8, RI32, MI8, MI32)),
                M.MOVSX: ('w1', (RR, RM)),
                M.MOVZX: ('w1', (RR, RM)),
                M.LEA: ('w1', ((R, MM),)),
                M.MOVSS: ('w1', (RR, RM, MR)),
                M.MOVAPS: ('w1', (RR, RM, MR)),
                M.MOVAPD: ('w1', (RR, RM, MR)),
                M.MOVDQA: ('w1', (RR, RM, MR)),
                M.MOVDQU: ('w1', (RR, RM, MR)),
                M.MOVSD: ('w1', (RR, RM, MR)),
                M.MOVD: ('w1', (RR,)),
                M.MOVQ: ('w1', (RR, RM, MR)),
                M.VMOVSS: ('w1', ((R, MM),)),
                M.VMOVAPS: ('w1', (RR,)),
                M.VMOVAPD: ('w1', ((R, MM),)),
                M.VMOVD: ('w1', (RR,)),
                M.VMOVQ: ('w1', (RR,)),
                M.CVTDQ2PS: ('w1', (RR,)),
                M.VCVTDQ2PS: ('w1', (RR,)),
                M.CVTSI2SS: ('w1', (RR, RM)),
                M.ADD: ('rw1', (RR, RM, RI8, RI32, MI8, MI32)),
                M.SUB: ('rw1', (RR, RM, RI8, RI32, MI8, MI32)),
                M.AND: ('rw1', (RR, RM, MI8, MI32)),
                M.OR: ('rw1', (RR, RM, MI8, MI32)),
                M.XOR: ('rw1', (RR, RM, MI8, MI32)),
                M.SHL: ('rw1', ((R, I8), (R, R))),
                M.SHR: ('rw1', ((R, I8), (R, R))),
                M.SAR: ('rw1', ((R, I8), (R, R))),
                M.NOT: ('rw1', ((R,),)),
                M.NEG: ('rw1', ((R,),)),
                M.INC: ('rw1', ((R,),)),
                M.DEC: ('rw1', ((R,),)),
                M.IMUL: ('rw1', (RR,)),
                M.ADDSS: ('rw1', (RR, RM)),
                M.SUBSS: ('rw1', (RR, RM)),
                M.SUBSD: ('rw1', (RR, RM)),
                M.MULSS: ('rw1', (RR, RM)),
                M.DIVSS: ('rw1', (RR, RM)),
                M.SQRTSS: ('rw1', (RR, RM)),
                M.MAXSS: ('rw1', (RR, RM)),
                M.MINSS: ('rw1', (RR, RM)),
                M.ANDPS: ('rw1', (RR, RM)),
                M.ORPS: ('rw1', (RR, RM)),
                M.XORPS: ('rw1', (RR, RM)),
                M.PAND: ('rw1', (RR, RM)),
                M.POR: ('rw1', (RR, RM)),
                M.PXOR: ('rw1', (RR, RM)),
                M.PSUBD: ('rw1', (RR, RM)),
                M.PADDD: ('rw1', (RR, RM)),
                M.PSRLD: ('rw1', ((R, I8),)),
                M.CMP: ('rall', (RR, RM, MR, RI8, RI32, MI8, MI32)),
                M.TEST: ('rall', (RR, RM)),
                M.COMISS: ('rall', (RR, RM)),
                M.UCOMISS: ('rall', (RR, RM)),
                M.VCOMISS: ('rall', (RR, RM)),
                M.VADDSS: ('vex3', None),
                M.VSUBSS: ('vex3', None),
                M.VMULSS: ('vex3', None),
                M.VDIVSS: ('vex3', None),
                M.VFMADD213SS: ('vex3', None),
                M.VFMADD231SS: ('vex3', None),
                M.VFMSUB213SS: ('vex3', None),
                M.VFMSUB231SS: ('vex3', None),
                M.VPAND: ('vex3', None),
                M.VPOR: ('vex3', None),
                M.VPXOR: ('vex3', None),
                M.VPSUBD: ('vex3', None),
                M.VPADDD: ('vex3', None),
                M.VPSLLD: ('vex3', None),
                M.VPSRLD: ('vex3', None),
                M.VPSRAD: ('vex3', None),
                M.VANDPS: ('vex3', None),
                M.VORPS: ('vex3', None),
                M.VXORPS: ('vex3', None),
                M.NOP: ('ctrl', ((MM,), (R,), ())),
                M.JMP: ('ctrl', ((O.NEAR_BRANCH64,),)),
                M.CALL: ('ctrl', ((O.NEAR_BRANCH64,),)),
                M.RET: ('ctrl', ((),)),
            }
            for _j in ('JA', 'JAE', 'JB', 'JBE', 'JE', 'JNE', 'JG', 'JGE',
                       'JL', 'JLE', 'JP', 'JO', 'JNO', 'JS', 'JNS', 'JNP',
                       'JCXZ', 'JECXZ', 'JRCXZ'):
                if hasattr(M, _j):
                    tab[getattr(M, _j)] = ('ctrl', ((O.NEAR_BRANCH64,),))
            # SETcc writes its byte destination; only flags are read.
            for _s in ('SETE', 'SETNE', 'SETA', 'SETAE', 'SETB', 'SETBE',
                       'SETG', 'SETGE', 'SETL', 'SETLE', 'SETS', 'SETNS',
                       'SETO', 'SETNO', 'SETP', 'SETNP'):
                if hasattr(M, _s):
                    tab[getattr(M, _s)] = ('w1', ((R,),))
            names = {}
            for _k, _v in vars(O).items():
                try:
                    names[int(_v)] = _k
                except Exception:
                    pass
            t = (tab, V3, names)
        self._fp32_access = t
        return t

    @staticmethod
    def _fp32_canon(kind, names):
        try:
            n = names.get(int(kind), '')
        except Exception:
            return kind
        return 'IMM' if 'IMMEDIATE' in n else kind

    def _fp32_forms_match(self, forms, fk, names):
        ck = tuple(self._fp32_canon(k, names) for k in fk)
        for f in forms:
            if tuple(self._fp32_canon(k, names) for k in f) == ck:
                return True
        return False

    @staticmethod
    def _fp32_sdisp(ins):
        # memory_displacement arrives sign-extended to 64 bits here.
        try:
            d = int(ins.memory_displacement)
        except Exception:
            return None
        if d >= 0x8000000000000000:
            d -= 0x10000000000000000
        return d

    def _fp32_rsp_imm(self, ins):
        ck = getattr(ins, 'op1_kind', None)
        O = OpKind
        try:
            if ck == O.IMMEDIATE8:
                return int(ins.immediate8)
            if ck == O.IMMEDIATE32:
                return int(ins.immediate32)
            if ck in (O.IMMEDIATE8TO32, O.IMMEDIATE8TO64,
                      O.IMMEDIATE32TO64):
                return int(ins.immediate32)
        except Exception:
            return None
        return None

    def _is_fp32_unary_leaf(self, target):
        """True when an unregistered target proves the FP32-unary shape.

        The callee must read exactly XMM0 (one scalar float argument),
        never a GPR/stack argument, with no caller-visible effects (the
        `_fp32_inputs` proof); the caller side -- a scalar float consume
        of XMM0 on the next instruction -- is the call site's own check
        in `_call`. Results are memoized per lifter; the address is never
        hardcoded. Anything unprovable keeps today's honest spelling.
        """
        try:
            cache = self._fp32_unary_cache
        except AttributeError:
            cache = self._fp32_unary_cache = {}
        if target in cache:
            return cache[target]
        res = False
        try:
            inputs = self._fp32_inputs(target, 0)
            res = inputs is not None and 'XMM0' in inputs \
                and not (set(inputs) & set(self._FP32_GPR_ARGS)) \
                and not (set(inputs) & set(self._FP32_XMM_EXTRA)) \
                and 'STACKARG' not in inputs \
                and 'SHADOWARG' not in inputs
        except Exception:
            res = False
        cache[target] = res
        return res

    def _fp32_inputs(self, target, depth):
        """Input registers of an unregistered native function, or None.

        Depths 0 (the direct callee) and 1 (its child, for argument
        liveness at the call) run the full proof: CFG by recursive
        descent from the entry VA (never a linear sweep -- a pdata range
        can pack several thunks behind one extent), an operand-access
        allowlist per instruction, an RSP-frame bound on memory, and a
        MUST (must-be-written) fixpoint whose complement of each block's
        reads-before-local-writes is exactly the input set. Depth 2 and
        below require only the unregistered-native identity (no managed
        callbacks one level down); deeper CRT substrate (errno/
        invalid-parameter paths shuttle caller context below the C#
        abstraction) is invisible to the C# dataflow and byte-identical
        under either rendering -- a documented residual, covered
        empirically by reviewing every affected call site.
        """
        if not HAVE_ICED or not target or not self.bin.is_exec_va(target):
            return None
        if self.il.addr_candidates.get(target) \
                or target in self.il.addr_to_method \
                or target in self.bin.exports:
            return None
        if depth >= 2:
            return frozenset()
        tab, V3, names = self._fp32_table()
        if not tab:
            return None
        M, O = Mnemonic, OpKind
        start, finish = self.il.function_extent(target)
        if start != target or finish is None \
                or not 0 < finish - start <= 0x1000:
            return None
        code = self.bin.read(start, finish - start)
        if not code:
            return None
        try:
            dec = Decoder(64, code, DecoderOptions.NONE)
            dec.ip = start
            raw = list(dec)
        except Exception:
            return None
        by_ip = {ins.ip: ins for ins in raw}
        blocks = {}
        work = [start]
        tailkids = []
        branches = set()
        _INT = getattr(M, 'INT', None)
        _UD2 = getattr(M, 'UD2', None)
        _HLT = getattr(M, 'HLT', None)
        while work:
            ip = work.pop()
            if ip in blocks:
                continue
            if ip < start or ip >= finish or ip not in by_ip:
                return None
            cur = []
            while True:
                ins = by_ip.get(ip)
                if ins is None:
                    return None
                cur.append(ins)
                m = ins.mnemonic
                fc = ins.flow_control
                if m == M.RET or (m == _INT and getattr(ins, 'len', 0) == 1) \
                        or m == _UD2 or m == _HLT:
                    succ = []
                    break
                if fc == FlowControl.INDIRECT_BRANCH:
                    return None
                if m == M.CALL:
                    if getattr(ins, 'op0_kind', None) != O.NEAR_BRANCH64:
                        return None
                    try:
                        ct = ins.near_branch_target
                    except Exception:
                        return None
                    nx = ins.next_ip
                    if not (start <= nx < finish and nx in by_ip):
                        return None
                    succ = [nx]
                    tailkids.append((cur[0].ip, ip, ct, True))
                    break
                if fc == FlowControl.UNCONDITIONAL_BRANCH:
                    try:
                        t = ins.near_branch_target
                    except Exception:
                        return None
                    if start <= t < finish:
                        if t not in by_ip:
                            return None
                        succ = [t]
                        branches.add(t)
                    else:
                        succ = []
                        tailkids.append((cur[0].ip, ip, t, False))
                    break
                if fc == FlowControl.CONDITIONAL_BRANCH:
                    try:
                        t = ins.near_branch_target
                    except Exception:
                        return None
                    nx = ins.next_ip
                    if not (start <= t < finish and start <= nx < finish):
                        return None
                    succ = [nx, t]
                    branches.add(t)
                    break
                nx = ins.next_ip
                if nx in blocks:
                    succ = [nx]
                    break
                if not (start <= nx < finish) or nx not in by_ip:
                    return None
                ip = nx
                continue
            blocks[cur[0].ip] = (cur, succ)
            for s2 in succ:
                if s2 not in blocks:
                    work.append(s2)
        if len(blocks) > 256 or sum(len(c) for c, _ in blocks.values()) > 2048:
            return None
        preds = {k: set() for k in blocks}
        for k, (cur, succ) in blocks.items():
            for s2 in succ:
                if s2 in preds:
                    preds[s2].add(k)
        for k in blocks:
            if k != start and not preds[k]:
                return None
        for _blk, _ip, _ct, _is_call in tailkids:
            if not self.bin.is_exec_va(_ct) \
                    or self.il.addr_candidates.get(_ct) \
                    or _ct in self.il.addr_to_method \
                    or _ct in self.bin.exports:
                return None
            if self._fp32_inputs(_ct, depth + 1) is None:
                return None
        tracked = frozenset(self._FP32_GPR_ARGS + ('XMM0',)
                              + self._FP32_XMM_EXTRA)
        ecur = blocks[start][0]
        entry_end = ecur[-1].next_ip
        for t in branches:
            if start < t < entry_end:
                return None
        frame = None
        alias = None
        try:
            for _e in ecur:
                if _e.mnemonic == M.MOV and _e.op_count == 2 \
                        and getattr(_e, 'op0_kind') == O.REGISTER \
                        and getattr(_e, 'op1_kind') == O.REGISTER \
                        and reg_name(_e.op1_register) == 'RSP':
                    _d = reg_name(_e.op0_register)
                    if _d in ('RAX', 'RCX', 'RDX', 'R8', 'R9', 'R10', 'R11'):
                        alias = _d
                _fc = _e.flow_control
                if _e.mnemonic in (M.RET, M.CALL) \
                        or _fc in (FlowControl.UNCONDITIONAL_BRANCH,
                                   FlowControl.CONDITIONAL_BRANCH,
                                   FlowControl.INDIRECT_BRANCH):
                    break
        except Exception:
            alias = None
        if alias is not None:
            _aw = 0
            for _k, (_cc, _ss) in blocks.items():
                for _i2 in _cc:
                    _kd = tab.get(_i2.mnemonic)
                    if _kd is None:
                        continue
                    _kk2 = _kd[0]
                    for _j in range(_i2.op_count):
                        if getattr(_i2, 'op%d_kind' % _j) != O.REGISTER:
                            continue
                        if reg_name(getattr(_i2, 'op%d_register' % _j)) != alias:
                            continue
                        if (_kk2 in ('w1', 'vex3') and _j == 0) \
                                or (_kk2 == 'rw1' and _j == 0):
                            _aw += 1
            if _aw != 1:
                alias = None
        gen = {}
        kill = {}
        sub_seen = False
        has_sub = False
        try:
            for _e in blocks[start][0]:
                if _e.mnemonic == M.SUB and _e.op_count == 2 \
                        and getattr(_e, 'op0_kind') == O.REGISTER \
                        and reg_name(_e.op0_register) == 'RSP':
                    if self._fp32_rsp_imm(_e) is not None:
                        has_sub = True
        except Exception:
            pass
        # Frameless leaves (no entry frame setup, e.g. tiny CRT
        # thunks using the caller home area as scratch) work over
        # the 0x28 shadow store. The shadow holds caller data, so a
        # sub-shadow read is an input (SHADOWARG) unless its home was
        # written in the entry block, which dominates every later
        # read (mid-entry branch targets already decline above).
        frameless = not has_sub
        if frameless:
            frame = 0x28
        entry_homes = set()
        for k, (cur, succ) in blocks.items():
            g, kk = set(), set()
            for ins in cur:
                m = ins.mnemonic
                entry = tab.get(m)
                if entry is None:
                    return None
                kind, forms = entry
                if forms is not None:
                    fk = tuple(getattr(ins, 'op%d_kind' % i)
                               for i in range(ins.op_count))
                    if not self._fp32_forms_match(forms, fk, names):
                        return None
                else:
                    fk = tuple(getattr(ins, 'op%d_kind' % i)
                               for i in range(ins.op_count))
                    if tuple(self._fp32_canon(x, names) for x in fk) not in tuple(
                            tuple(self._fp32_canon(x, names) for x in f) for f in V3):
                        return None
                if k == start and m == M.SUB and ins.op_count == 2 \
                        and getattr(ins, 'op0_kind') == O.REGISTER \
                        and reg_name(ins.op0_register) == 'RSP':
                    if self._fp32_rsp_imm(ins) is not None:
                        frame = self._fp32_rsp_imm(ins)
                        sub_seen = True
                zero_idiom = m in (M.XOR, M.SUB, M.XORPS, M.PXOR) \
                    and ins.op_count == 2 \
                    and getattr(ins, 'op0_kind') == O.REGISTER \
                    and getattr(ins, 'op1_kind') == O.REGISTER \
                    and ins.op0_register == ins.op1_register
                nops = ins.op_count
                for i in range(nops):
                    r = None
                    if getattr(ins, 'op%d_kind' % i) == O.REGISTER:
                        r = reg_name(getattr(ins, 'op%d_register' % i))
                    if r is None:
                        continue
                    if (kind in ('w1', 'vex3') and i == 0) \
                            or (zero_idiom and i == 0):
                        is_r, is_w = False, True
                    elif kind == 'rw1' and i == 0 and not zero_idiom:
                        is_r, is_w = True, True
                    else:
                        is_r, is_w = True, False
                    if is_r and r in tracked and r not in kk:
                        g.add(r)
                    if is_w and r in tracked:
                        kk.add(r)
                    if is_w and r in self._FP32_NONVOL:
                        return None
                    if is_w and r in self._FP32_XMM_HI:
                        return None
                    if is_w and r == 'RSP':
                        if not self._fp32_rsp_ok(m, k == start, succ == [],
                                                 ins, frame):
                            return None
                for i in range(nops):
                    if getattr(ins, 'op%d_kind' % i) != O.MEMORY:
                        continue
                    try:
                        base = reg_name(ins.memory_base)
                    except Exception:
                        base = '?'
                    try:
                        idx = reg_name(ins.memory_index)
                    except Exception:
                        idx = '?'
                    if base not in ('?', 'RIP', 'RSP', alias):
                        if base in tracked and base not in kk:
                            g.add(base)
                    if idx not in ('?', 'RSP'):
                        if idx in tracked and idx not in kk:
                            g.add(idx)
                    disp = self._fp32_sdisp(ins)
                    if disp is None:
                        return None
                    writes_mem = kind in ('w1', 'rw1') and i == 0
                    pre_sub = k == start and has_sub and not sub_seen
                    if writes_mem:
                        if pre_sub:
                            return None
                        if base == 'RSP' and idx in ('?', 'RSP'):
                            if frame is None or not 0 <= disp < frame:
                                return None
                            if k == start:
                                entry_homes.add((base, disp))
                        elif alias is not None and base == alias \
                                and idx in ('?', 'RSP'):
                            if frame is None or not -frame <= disp < 0:
                                return None
                            if k == start:
                                entry_homes.add((base, disp))
                        else:
                            return None
                    else:
                        if base == 'RSP' and idx in ('?', 'RSP'):
                            if pre_sub or frame is None:
                                g.add('STACKARG')
                            elif disp >= frame + 8:
                                g.add('STACKARG')
                            elif frameless and (base, disp) not in entry_homes:
                                g.add('SHADOWARG')
                        elif base == 'RSP':
                            return None
                        elif alias is not None and base == alias:
                            if idx not in ('?', 'RSP') or frame is None \
                                    or not -frame <= disp < 0:
                                return None
                            elif frameless and (base, disp) not in entry_homes:
                                g.add('SHADOWARG')
                # VPXOR same-reg form check needs the vex path above only
            gen[k] = g
            kill[k] = kk
        must_in = {k: (set() if k == start else None) for k in blocks}
        full = set(tracked) | {'STACKARG', 'SHADOWARG'}
        for k in blocks:
            if k != start:
                must_in[k] = set(full)
        for _ in range(500):
            changed = False
            for k, (cur, succ) in blocks.items():
                if k == start:
                    continue
                new = set(full)
                for p in preds[k]:
                    new &= (must_in[p] | kill[p])
                if new != must_in[k]:
                    must_in[k] = new
                    changed = True
            if not changed:
                break
        else:
            return None
        inputs = set()
        for k in blocks:
            inputs |= (gen[k] - must_in[k])
        for _blk, _ip, _ct, _is_call in tailkids:
            sub = self._fp32_inputs(_ct, depth + 1)
            if sub is None:
                return None
            if depth + 1 > 1:
                continue
            live = set(must_in[_blk])
            cur = blocks[_blk][0]
            for ins2 in cur:
                if ins2.ip == _ip:
                    break
                kind2 = tab[ins2.mnemonic][0]
                for i in range(ins2.op_count):
                    r = None
                    if getattr(ins2, 'op%d_kind' % i) == O.REGISTER:
                        r = reg_name(getattr(ins2, 'op%d_register' % i))
                    if r is None:
                        continue
                    if (kind2 in ('w1', 'vex3') and i == 0) \
                            or (kind2 == 'rw1' and i == 0):
                        live.add(r)
            inputs |= (set(sub) - live)
        return frozenset(inputs)

    def _fp32_rsp_ok(self, m, is_entry, is_tail, ins, frame):
        # The entry frame sub, or a bounded epilogue add in a block that
        # returns (dynamic stack shapes decline).
        if m == Mnemonic.SUB and is_entry and self._fp32_rsp_imm(ins) is not None:
            return True
        if m == Mnemonic.ADD and is_tail and frame is not None:
            v = self._fp32_rsp_imm(ins)
            return v is not None and 0 < v <= frame
        return False

    def _is_fence_body(self, target):
        """Recognize the unregistered full-fence helper by proof. -- fix 107

        Exactly `lock or dword ptr [rsp],0; ret`: a locked RMW of its own
        stack slot (the full barrier MSVC emits where the source calls
        `Thread.MemoryBarrier`) then return. The store preserves the
        slot (`x|0 == x`), no register is read or written, and the
        immediate must be zero (anything else would corrupt the return
        address slot it touches); `ret` terminates the extent, so no
        bounds analysis is needed. Registered/exported owners decline,
        as does anything unreadable. Ground truth:
        `System.Threading.Thread.MemoryBarrier`'s own recovered body is
        one call to 0x1804429c0 (RVA 0x1D1F380). Results are memoized;
        never hardcode an address.
        """
        cache = getattr(self, "_fence_cache", None)
        if cache is None:
            cache = self._fence_cache = {}
        if target in cache:
            return cache[target]
        res = self._is_fence_body_inner(target)
        cache[target] = res
        return res

    def _is_fence_body_inner(self, target):
        try:
            if not HAVE_ICED or not target:
                return False
            if self.il.addr_candidates.get(target):
                return False
            if target in self.bin.exports:
                return False
            if not self.bin.is_exec_va(target):
                return False
            code = self.bin.read(target, 16)
            if not code:
                return False
            dec = Decoder(64, code, DecoderOptions.NONE)
            dec.ip = target
            ii = [next(iter(dec)) for _ in range(2)]
        except Exception:
            return False
        try:
            i0 = ii[0]
            if i0.mnemonic != Mnemonic.OR or not i0.has_lock_prefix:
                return False
            if i0.op0_kind != OpKind.MEMORY or i0.memory_base != IReg.RSP:
                return False
            if i0.memory_displacement != 0:
                return False
            if MemorySizeExt.size(i0.memory_size) != 4:
                return False
            if i0.op1_kind in (OpKind.IMMEDIATE8,
                               OpKind.IMMEDIATE8TO32):
                if getattr(i0, "immediate8", 1) != 0:
                    return False
            elif i0.op1_kind == OpKind.IMMEDIATE32:
                if getattr(i0, "immediate32", 1) != 0:
                    return False
            else:
                return False
            return ii[1].mnemonic == Mnemonic.RET
        except Exception:
            return False

    def _fence_target(self, va):
        """Fence VA reached from `va` (itself or <=3 jmp hops), else None."""
        try:
            if not va:
                return None
            if self._is_fence_body(va):
                return va
            cur = va
            for _ in range(3):
                if not self.bin.is_exec_va(cur):
                    return None
                code = self.bin.read(cur, 8)
                if not code:
                    return None
                try:
                    dec = Decoder(64, code, DecoderOptions.NONE)
                    dec.ip = cur
                    ins = next(iter(dec))
                except Exception:
                    return None
                if ins.mnemonic != Mnemonic.JMP \
                        or ins.op0_kind != OpKind.NEAR_BRANCH64 \
                        or ins.len > 6:
                    return None
                cur = ins.near_branch_target
                if self._is_fence_body(cur):
                    return cur
            return None
        except Exception:
            return None

    def _init_runtime_ids(self):
        """Identify il2cpp runtime helper functions by structural signature."""
        self.rt_init_meta = None
        b = self.bin
        # find the dominant callee of (lea rcx,[rip] ; call) across a sample of methods
        from collections import Counter
        cnt = Counter()
        img = next((i for i, im in enumerate(self.meta.images)
                    if im.name == 'Assembly-CSharp.dll'), 0)
        im = self.meta.images[img]
        dec_ip_base = []
        for ti in range(im.type_start, min(im.type_start + im.type_count, len(self.meta.typedefs))):
            td = self.meta.typedefs[ti]
            for mi in self.meta.type_methods(td):
                m = self.meta.methods[mi]
                if not m.addr:
                    continue
                code = b.read(m.addr, 512)
                if not code:
                    continue
                dec = Decoder(64, code, DecoderOptions.NONE)
                dec.ip = m.addr
                last_lea = False
                for ins in dec:
                    if ins.mnemonic == Mnemonic.LEA and ins.op0_register == IReg.RCX \
                            and ins.memory_base == IReg.RIP:
                        last_lea = True
                    elif ins.mnemonic == Mnemonic.CALL and ins.op0_kind == OpKind.NEAR_BRANCH64:
                        if last_lea:
                            cnt[ins.near_branch_target] += 1
                        last_lea = False
                    elif ins.mnemonic == Mnemonic.RET:
                        break
                if sum(cnt.values()) > 4000:
                    break
        self.rt_init_meta = cnt.most_common(1)[0][0] if cnt else None
        # box helper: identified by export name, not hardcoded address
        self.rt_value_box = next(
            (va for va, nm in b.exports.items() if nm == 'il2cpp_value_box'), None)

        # classify hot unknown helpers by the instruction feeding rcx at the call:
        #   mov rcx,[slot->TypeInfo]   -> alloc family (object/array new)
        #   lea rcx,[obj+disp]         -> GC write barrier store
        stats = {}  # target -> [total, arg_klass, arg_addr, sample_type_name]
        img = next((i for i, im in enumerate(self.meta.images)
                    if im.name == 'Assembly-CSharp.dll'), 0)
        im = self.meta.images[img]
        budget = 6000
        for ti in range(im.type_start, min(im.type_start + im.type_count, len(self.meta.typedefs))):
            td = self.meta.typedefs[ti]
            for mi in self.meta.type_methods(td):
                m = self.meta.methods[mi]
                if not m.addr:
                    continue
                code = b.read(m.addr, 512)
                if not code:
                    continue
                dec = Decoder(64, code, DecoderOptions.NONE)
                dec.ip = m.addr
                pend = []  # (ip, kind, sample) rcx writers pending
                for ins in dec:
                    if (ins.mnemonic == Mnemonic.MOV or ins.mnemonic == Mnemonic.MOVZX)                             and ins.op0_kind == OpKind.REGISTER                             and reg_name(ins.op0_register) == 'RCX':
                        if ins.op1_kind == OpKind.MEMORY and ins.memory_base == IReg.RIP:
                            usg = self.il.decode_slot(ins.ip_rel_memory_address)
                            if usg and usg.get('kind') in (1, 2):
                                pend.append(('klass', usg.get('text')))
                            else:
                                pend.append((None, None))
                        else:
                            pend.append((None, None))
                    elif ins.mnemonic == Mnemonic.LEA and ins.op0_register == IReg.RCX:
                        pend.append(('addr' if ins.memory_base != IReg.RIP else None, None))
                    elif ins.mnemonic == Mnemonic.CALL and ins.op0_kind == OpKind.NEAR_BRANCH64:
                        t = ins.near_branch_target
                        if t not in self.il.addr_to_method and t not in self.il.bin.exports:
                            argk = pend[-1] if pend else (None, None)
                            st = stats.setdefault(t, [0, 0, 0, argk[1]])
                            st[0] += 1
                            if argk[0] == 'klass':
                                st[1] += 1
                            elif argk[0] == 'addr':
                                st[2] += 1
                            if st[3] is None and argk[1]:
                                st[3] = argk[1]
                        pend = []
                    elif ins.mnemonic == Mnemonic.RET:
                        break
                budget -= 1
                if budget <= 0:
                    break
            if budget <= 0:
                break
        self.rt_alloc = None
        self.rt_arrnew = set()
        self.rt_wbarrier = set()
        self.rt_names = {}
        if self.rt_init_meta:
            self.rt_names[self.rt_init_meta] = 'il2cpp_codegen_initialize_runtime_metadata'
            # the wrapper's own callee is the same routine (and the 86k-site
            # jmp-thunk band points at that inner address too): name it the
            # same instead of leaving it `sub_...`.
            code = b.read(self.rt_init_meta, 32)
            if code:
                try:
                    dec4 = Decoder(64, code, DecoderOptions.NONE)
                    dec4.ip = self.rt_init_meta
                    for ins in dec4:
                        if ins.mnemonic in (Mnemonic.CALL, Mnemonic.JMP) \
                                and ins.op0_kind == OpKind.NEAR_BRANCH64:
                            self.rt_names[ins.near_branch_target] = \
                                'il2cpp_codegen_initialize_runtime_metadata'
                            break
                        if ins.ip - self.rt_init_meta > 24:
                            break
                except Exception:
                    pass
        for t, (total, nkl, naddr, sample) in sorted(stats.items(), key=lambda kv: -kv[1][0])[:40]:
            if t == self.rt_init_meta or total < 8:
                continue
            if nkl >= total * 0.6:
                if sample and '[' in sample:
                    self.rt_arrnew.add(t)
                    self.rt_names[t] = 'il2cpp_array_new'
                else:
                    if self.rt_alloc is None:
                        self.rt_alloc = t
                        self.rt_names[t] = 'il2cpp_object_new'
            elif naddr >= total * 0.6:
                self.rt_wbarrier.add(t)
                self.rt_names[t] = 'il2cpp_codegen_write_barrier'
        self._helper_stats = stats
        # interface-offset dispatchers: the same slot arithmetic under a
        # different prologue (the fixture's 0x180002210/0x180002380).
        # Only members that never read R9 are nullary; the recognizer in
        # `calls.py` admits exactly those structurally.
        self.rt_iface = {}
        for _t in sorted(set(cnt) | set(stats)):
            _ar = self._iface_dispatch_arity(_t)
            if _ar is not None:
                self.rt_iface[_t] = _ar
        sqrt_helpers = [target for target in stats
                        if self._is_scalar_sqrt_helper(target)]
        self.rt_sqrt = sqrt_helpers[0] if len(sqrt_helpers) == 1 else None
        self._thunk_cache = {}
        self._twin_cache = {}
        # IsInst intrinsic (obj, klass): the hot thunk 0x180434690
        # forwards to 0x180479f80. `typeof(T)` sites render `obj as T`;
        # opaque klass expressions keep the honest `sub_` fallback.
        self.rt_isinst = set()
        for _t in sorted(set(cnt) | set(stats)):
            _fin = self._thunk_final(_t)
            if self._is_isinst_helper(_t) or (_fin and _fin != _t
                                              and self._is_isinst_helper(_fin)):
                self.rt_isinst.add(_t)
                if _fin:
                    self.rt_isinst.add(_fin)
        # Interlocked.CompareExchange helper (lock cmpxchg [loc],value with
        # the comparand in R8): 21 AC sites on the fixture, events/state.
        self.rt_interlocked = set()
        for _t in sorted(set(cnt) | set(stats)):
            _fin = self._thunk_final(_t)
            if self._is_interlocked_helper(_t) or (
                    _fin and _fin != _t and self._is_interlocked_helper(_fin)):
                self.rt_interlocked.add(_t)
                if _fin:
                    self.rt_interlocked.add(_fin)
        # Out-of-line class-init helper (861 tree-wide sites): naming it
        # routes the site through the existing `il2cpp_runtime_class_init`
        # arity trim (one argument).
        for _t in sorted(set(cnt) | set(stats)):
            _fin = self._thunk_final(_t)
            if self._is_class_init_helper(_t) or (
                    _fin and _fin != _t and self._is_class_init_helper(_fin)):
                self.rt_names[_t] = 'il2cpp_runtime_class_init'
                if _fin:
                    self.rt_names[_fin] = 'il2cpp_runtime_class_init'
        # Interface slow-path resolve helper (0x18043dc60, 2,446 sites):
        # the miss-path of the inlined fast-path loop. (obj, iface,
        # slot) in RCX/RDX/R8; R9 residue is spray. Name + arity 3
        # drops the duplicated 4th arg. Return stays the native
        # method-entry pair pointer (honest residual -- no `as`/dispatch
        # fold without pair-struct provenance).
        for _t in sorted(set(cnt) | set(stats)):
            _fin = self._thunk_final(_t)
            if self._is_iface_resolve_helper(_t) or (
                    _fin and _fin != _t and self._is_iface_resolve_helper(_fin)):
                self.rt_names[_t] = 'il2cpp_interface_get_method'
                if _fin:
                    self.rt_names[_fin] = 'il2cpp_interface_get_method'
        # Bounds-checked element-address helpers (0x1803ed830/860,
        # 745 tree-wide sites): naming routes the sites through the
        # `il2cpp_array_addr` arity trim (array, index). The stride
        # rides in `rt_array_addr` for the indexed render follow-up.
        self.__dict__.setdefault('rt_array_addr', {})
        for _t in sorted(set(cnt) | set(stats)):
            _fin = self._thunk_final(_t)
            for _c in (_t,) if _fin in (None, _t) else (_t, _fin):
                try:
                    _st = self._is_array_addr_helper(_c)
                except Exception:
                    _st = None
                if _st:
                    self.rt_names[_c] = 'il2cpp_array_addr'
                    self.__dict__.setdefault('rt_array_addr', {})[_c] = _st
        self._cls_init_export = next(
            (va for va, nm0 in b.exports.items()
             if nm0 == 'il2cpp_runtime_class_init'), None)

        # noreturn raiser family: MSVC thunks `sub rsp,X; call T; int3` that
        # unconditionally build one specific managed exception (the chain
        # lea's its class name into the exception ctor) and raise it. Name
        # the thunk by that exception -- it is the codegen-level
        # "throw new <Exc>()" word, parameterless by construction. Also the
        # class-init inline twin: `cmp dword [rcx+0E4h],0; je <export>` is
        # the out-of-line copy of the fast path the compiler usually
        # inlines; it returns the klass itself.
        try:
            cls_init_export = next(
                (va for va, nm0 in b.exports.items()
                 if nm0 == 'il2cpp_runtime_class_init'), None)
            for t in sorted(set(cnt) | set(stats)):
                if t in self.rt_names or t in b.exports:
                    continue
                if t in self.il.addr_to_method:
                    continue
                if cnt.get(t, 0) < 2 and t not in stats:
                    continue
                code = b.read(t, 16)
                if not code:
                    continue
                try:
                    dec5 = Decoder(64, code, DecoderOptions.NONE)
                    dec5.ip = t
                    ins0 = next(iter(dec5))
                    if ins0.mnemonic == Mnemonic.CMP \
                            and ins0.op0_kind == OpKind.MEMORY \
                            and ins0.memory_base == IReg.RCX \
                            and ins0.memory_displacement == 0xE4 \
                            and ins0.op1_kind in (OpKind.IMMEDIATE8,
                                                  OpKind.IMMEDIATE8TO16,
                                                  OpKind.IMMEDIATE8TO32,
                                                  OpKind.IMMEDIATE8TO64,
                                                  OpKind.IMMEDIATE16,
                                                  OpKind.IMMEDIATE32,
                                                  OpKind.IMMEDIATE64):
                        ins1 = next(iter(dec5))
                        if cls_init_export and ins1.mnemonic in (Mnemonic.JE, Mnemonic.JNE) \
                                and ins1.op0_kind == OpKind.NEAR_BRANCH64 \
                                and ins1.near_branch_target == cls_init_export:
                            self.rt_names[t] = 'il2cpp_runtime_class_init'
                            continue
                except Exception:
                    pass
                exc = None
                if t != self.rt_init_meta:
                    hops, cur = 0, t
                    while hops < 4:
                        code = b.read(cur, 32)
                        if not code:
                            break
                        try:
                            dec5 = Decoder(64, code, DecoderOptions.NONE)
                            dec5.ip = cur
                            ii = [next(iter(dec5)) for _ in range(2)]
                        except Exception:
                            break
                        if ii[0].mnemonic != Mnemonic.SUB \
                                or ii[0].op0_kind != OpKind.REGISTER \
                                or reg_name(ii[0].op0_register) != 'RSP' \
                                or ii[1].mnemonic != Mnemonic.CALL \
                                or ii[1].op0_kind != OpKind.NEAR_BRANCH64:
                            break
                        nxt = ii[1].near_branch_target
                        if exc is None:
                            exc = self._scan_exc_refs(nxt, 2)
                        cur = nxt
                        hops += 1
                if exc:
                    self.RT_ARITY = dict(self.RT_ARITY)
                    self.rt_names[t] = 'raise_%s' % exc
                    self.RT_ARITY['raise_%s' % exc] = 0
        except Exception:
            pass

    def _scan_exc_refs(self, va, depth):
        """Best-effort name scan for the noreturn raise helpers: any
        RIP-relative lea in the wrapper chain referencing a C string ending
        in 'Exception' is the managed exception that chain raises."""
        if depth < 0:
            return None
        code = self.bin.read(va, 256)
        if not code:
            return None
        try:
            dec5 = Decoder(64, code, DecoderOptions.NONE)
            dec5.ip = va
            found = None
            calls = []
            for i, ins in enumerate(dec5):
                if i >= 40:
                    break
                if ins.mnemonic == Mnemonic.LEA and ins.memory_base == IReg.RIP \
                        and ins.op0_kind == OpKind.REGISTER:
                    o = self.bin.va2off(ins.ip_rel_memory_address)
                    if o is not None:
                        s = self.bin.d[o:o + 64].split(b'\x00')[0]
                        try:
                            s = s.decode('utf-8')
                        except Exception:
                            s = ''
                        if s.endswith('Exception'):
                            found = s
                elif ins.mnemonic == Mnemonic.CALL and ins.op0_kind == OpKind.NEAR_BRANCH64:
                    calls.append(ins.near_branch_target)
                elif ins.mnemonic == Mnemonic.RET:
                    break
            if found:
                return found.rsplit('.', 1)[-1]
            for c in calls:
                f2 = self._scan_exc_refs(c, depth - 1)
                if f2:
                    return f2
        except Exception:
            pass
        return None

    # ------------------------------------------------------------------
    def lift(self, m: MethodDef, td: TypeDef) -> List[str]:
        b = self.bin
        va = m.addr
        nxt = self.il.next_method_start(va) if hasattr(self.il, 'next_method_start') else None
        end = min(nxt or (va + 0x10000), va + 0x10000)
        code = b.read(va, end - va)
        if not code:
            return ['/* no code */']
        self.cur_va = va
        dec = Decoder(64, code, DecoderOptions.NONE)
        dec.ip = va
        fmt = None
        if self.asm_comments:
            fmt = Formatter(FormatterSyntax.NASM)
            fmt.digit_separator = ''

        self.regs = self._new_regs()
        self.dry = False   # a mid-lift_method exception can leave this set
        self._memory_rhs_loop_guard = False  # flat lift preserves native labels
        self._array_allocation_loop_guard = False
        self._cur_ip = 0
        self.rsp_delta = 0
        # this method established no frame pointer until it runs `mov rbp,rsp`.
        # lift() resets its own per-method state, separate from _setup_entry,
        # so the frame fact has to be cleared here too or it leaks into every
        # method this Lifter touches next.
        self._rbp_frame = False
        self.stack_map: Dict[int, str] = {}   # slot offset from entry rsp -> var name
        self.slot_types: Dict[str, tuple] = {}  # stack var -> il2cpp type (sret buffers)
        self.stack_values: Dict[str, Expr] = {}  # current simple value parked in a stack slot
        self.vt_recv_slot = None
        self.vt_recv = None
        self.addr_of = {}
        self.var_n = 0
        self.flags = None                      # (lhs, rhs, cmpop)
        self.out: List[Tuple[int, str, Optional[str]]] = []  # (ip, code, asm)
        self.targets = set()

        # decode everything, then find logical end: first ret / unconditional
        # indirect jump; direct jmp-out handled at emission
        raw = []
        for ins in dec:
            raw.append(ins)
            if len(raw) >= 20000:
                break
        term_idx = len(raw)
        for i, ins in enumerate(raw):
            fc = ins.flow_control
            if fc == FlowControl.RETURN:
                term_idx = i + 1
                break
            if fc == FlowControl.UNCONDITIONAL_BRANCH and ins.op0_kind != OpKind.NEAR_BRANCH64:
                term_idx = i + 1
                break
        insns = raw[:term_idx]
        last_ip = insns[-1].next_ip if insns else va
        for ins in insns:
            fc = ins.flow_control
            if fc in (FlowControl.CONDITIONAL_BRANCH, FlowControl.UNCONDITIONAL_BRANCH)                     and ins.op0_kind == OpKind.NEAR_BRANCH64:
                t = ins.near_branch_target
                if va <= t < last_ip:
                    self.targets.add(t)

        # peephole: swallow metadata-init guards
        #   cmp byte [rip+X],0 ; <benign movs> ; jcc T ; <lea/call init... + movs> ;
        #   mov byte [rip+X],1 ; T:
        # only the cmp/jcc/lea+call-init/mov-flag-store are skipped; other movs run.
        self.skip_ips = metadata_init_guards(insns, self.rt_init_meta)
        # peephole: swallow class-init guards
        #   mov rA,[rip slot->TypeInfo] ; cmp dword [rA+E4],0 ; jne T ;
        #   mov rcx,rA ; call class_init ; mov rA,[rip slot] ; T:
        _ci_ip_idx = {x.ip: xi for xi, x in enumerate(insns)}
        for i, ins in enumerate(insns):
            if ins.mnemonic == Mnemonic.MOV and ins.op0_kind == OpKind.REGISTER                     and ins.op1_kind == OpKind.MEMORY and ins.memory_base == IReg.RIP:
                usg = self.il.decode_slot(ins.ip_rel_memory_address)
                if not (usg and usg.get('kind') in (1, 2)):
                    continue
                regA = reg_name(ins.op0_register)
                k = i + 1
                if k >= len(insns):
                    continue
                w = insns[k]
                if not (w.mnemonic == Mnemonic.CMP and w.op0_kind == OpKind.MEMORY
                        and reg_name(w.memory_base) == regA and w.memory_displacement == 0xE4):
                    continue
                k += 1
                if k >= len(insns):
                    continue
                w = insns[k]
                if w.flow_control != FlowControl.CONDITIONAL_BRANCH or w.op0_kind != OpKind.NEAR_BRANCH64:
                    continue
                T = w.near_branch_target
                k += 1
                # T is the guard's own merge point (the fast `jne T` path
                # jumps straight past the call, whatever the slow path does
                # before reaching it) -- a provable bound, unlike a fixed
                # instruction-count lookahead, which can run past T and
                # swallow real code when no slot-reload mov exists to stop
                # it early (batch 21: `mov rcx,rA` direct reuse instead of
                # a second `mov rA,[slot]`, e.g. AmbientMusicSystem.Awake).
                t_idx = _ci_ip_idx.get(T)
                if t_idx is None or t_idx < k:
                    continue
                # find the class-init call within the guard body (i+1..t_idx)
                ok2 = False
                for m3 in range(k, t_idx):
                    w3 = insns[m3]
                    if w3.mnemonic == Mnemonic.CALL and w3.op0_kind == OpKind.NEAR_BRANCH64:
                        tgt = w3.near_branch_target
                        nm3 = self._call_name(tgt)
                        if 'class_init' in nm3 or 'ClassInit' in nm3 or tgt not in self.il.addr_to_method:
                            # the whole guard body is bounded by T; nothing
                            # in [i+1, t_idx) can be real code (see above)
                            for q in range(i + 1, t_idx):
                                self.skip_ips.add(insns[q].ip)
                            ok2 = True
                        break
                if ok2:
                    continue
        # peephole: swallow icall thunk-cache guards
        #   mov rA,[rel CELL->method] ; test rA,rA ; jne T ;
        #   lea rcx,[rel sig] ; call helper ; mov [rel CELL],rax ; T:
        for i, ins in enumerate(insns):
            if ins.mnemonic == Mnemonic.MOV and ins.op0_kind == OpKind.REGISTER \
                    and ins.op1_kind == OpKind.MEMORY and ins.memory_base == IReg.RIP:
                usg = self.il.decode_slot(ins.ip_rel_memory_address)
                if not (usg and usg.get('kind') == 3):
                    continue
                k = i + 1
                regA = reg_name(ins.op0_register)
                # the test may sit a few instructions out (thunk prologues
                # park register saves between the load and the test); nothing
                # in between may overwrite regA
                t_idx = None
                for k2 in range(k, min(k + 7, len(insns))):
                    w = insns[k2]
                    if (w.mnemonic == Mnemonic.TEST and w.op0_kind == OpKind.REGISTER
                            and reg_name(w.op0_register) == regA):
                        t_idx = k2
                        break
                    if (w.mnemonic == Mnemonic.CMP and w.op0_kind == OpKind.REGISTER
                            and reg_name(w.op0_register) == regA and imm_of(w, 1) == 0):
                        t_idx = k2
                        break
                    if w.flow_control != FlowControl.NEXT or \
                            (w.op0_kind == OpKind.REGISTER
                             and reg_name(w.op0_register) == regA):
                        break
                if t_idx is None:
                    continue
                k = t_idx + 1
                if k >= len(insns):
                    continue
                w = insns[k]
                if w.flow_control != FlowControl.CONDITIONAL_BRANCH or w.op0_kind != OpKind.NEAR_BRANCH64:
                    continue
                T = w.near_branch_target
                range_ips = []
                saw_store = False
                for q in range(k, min(k + 10, len(insns))):
                    wq = insns[q]
                    if wq.ip >= T:
                        break
                    range_ips.append(wq.ip)
                    if wq.mnemonic == Mnemonic.MOV and wq.op0_kind == OpKind.MEMORY \
                            and wq.memory_base == IReg.RIP \
                            and wq.ip_rel_memory_address == ins.ip_rel_memory_address:
                        saw_store = True
                        break
                if saw_store:
                    self.skip_ips.update(range_ips)

        self.targets -= self.skip_ips

        self._u = 0
        for _r in GPRS + ['XMM%d' % _k for _k in range(16)]:
            if _r == 'RSP':
                continue
            self._u += 1
            _e = Expr('v%d' % self._u, None, '?')
            _e._unk = True            # fix 58: never written yet
            self.regs[_r] = _e
        self._setup_entry(m, td)

        for i, ins in enumerate(insns):
            if ins.ip in self.skip_ips:
                continue
            if ins.ip in self.targets and self.out:
                self.emit(ins.ip, '', None)  # label marker
            self._insn(ins, insns, i, fmt, end)
        return self._render()

    # ------------------------------------------------------------------
    def _setup_entry(self, m: MethodDef, td: TypeDef):
        # Constructor call rendering needs the caller identity: `this` plus a
        # same-type target is `: this(...)`; an ancestor target is `: base(...)`.
        self._current_method = m
        self._current_td = td
        # reset per method/pass: t-names repeat across methods and v-names
        # differ between the two analysis passes, so leftovers mis-type
        self._var_types = {}
        # this method executed `mov rbp,rsp`: a per-method FACT, so unlike
        # the register value it survives the pass-2 phi merge's Expr('?').
        self._rbp_frame = False
        if not hasattr(self, 'stack_map'):
            self.stack_map = {}
        if not hasattr(self, 'slot_types'):
            self.slot_types = {}
        if not hasattr(self, 'rsp_delta'):
            self.rsp_delta = 0
        # per-method (per-pass) type evidence: token -> Il2CppType tuple,
        # gathered at calls/stores/returns and consumed live by _field_expr
        self._type_hints = {}
        # fix 140: object text -> type proven by an inlined castclass /
        # isinst hierarchy check (`klass.typeHierarchy[T.depth-1] == T`)
        self._cast_narrow = {}
        # tokens whose _bind-time type was withheld specifically because it
        # was an unresolved generic parameter (fix 21f) -- a later type hint
        # for one of these means the token's DECLARATION text was rescued
        # from a bare `T`, so the RHS call/index that produced it lost its
        # own `<T>` too and is worth re-annotating (_rename_locals).
        self._gp_blocked = set()
        # slots proved constructed by an emitted `.ctor()` call below
        # (calls.py) -- a whole-struct reload of one is the home
        # itself, never a stale scalar or first-field slice
        # (aggregates.py; 18054/34279). Reset per method/pass like
        # _type_hints: slot names repeat across methods.
        self._ctor_slots = set()
        # hidden-sret buffer homes reuse one temp per address: both
        # `lea rcx,[rsp+30h]` + call sites fill the SAME native buffer,
        # so the second result is a reassignment, not a fresh temp
        # (32174 `primitiveValue1 = ...(1)`). Reassignment is exactly
        # faithful -- the callee overwrites the buffer. Reset per
        # method/pass with the rest: addresses repeat across methods.
        self._sret_home_buf = {}
        self._last_tabread = None
        self.stack_values = {}
        byval_bits = (0x12 << 16)
        this_ty = (td.index, byval_bits)
        args = self.meta.method_params(m)
        # fix 57: ONE shared Win64 positional counter, the same walk
        # _positional_args (fix 42b) and _hint_arg_types (fix 53) do on
        # the caller side -- argument N takes register slot N, as RCX/
        # RDX/R8/R9 when integral and XMM0-3 when float, never a
        # per-class ordinal. `this` is argument 0 of an instance method,
        # so `double DateTime.AddDays(double)` reads its parameter from
        # XMM1 (disasm-proven at 0x181c94c40 and three more, see
        # work/probe_b50_entryfloat.py). Two independent counters seated
        # it in XMM0 and left every read of the real register rendering
        # as an undefined temp.
        # fix 59b (todo lead 5b): a valuetype return that does not fit a
        # register takes a hidden buffer in the FIRST slot, so `this` is
        # RDX and every parameter moves one register right. This is the
        # CALLEE side of the shift `_hint_arg_types` has always modelled
        # on the caller side; batch 50 deliberately left it alone for
        # want of an exact size, which `returns_sret` now is. 11,046
        # methods return sret, 7,633 of them with parameters
        # (work/probe_b51_sretsize.py).
        rt0 = self.il.types[m.return_type] \
            if 0 <= m.return_type < len(self.il.types) else None
        self._return_reg = self._return_value_register(rt0)
        base = 1 if self.il.returns_sret(rt0) else 0
        if base:
            # the hidden return buffer itself arrives in RCX: seed it as
            # the address of the method's own result local, so stores
            # through it fold onto `__ret.field` (the &s_N valuetype path
            # in _field_expr) and the `mov rax,rcx` echo returns it.
            # Unseeded, every such method read an undefined register
            # (`((byte*)obj2 + 0x0)[0] = obj1; return obj2;`).
            self.slot_types['__ret'] = rt0
            self.regs[ARG_REGS[0]] = Expr('&__ret', rt0, 'ptr')
        if not m.is_static:
            self.regs[ARG_REGS[base]] = Expr(
                'this', (td.index, 0x12 << 16), 'obj')
            base += 1
        for pi, p in enumerate(args):
            pt = self.il.types[p.type] if 0 <= p.type < len(self.il.types) else None
            bits = pt[1] if pt else 0
            te = (bits >> 16) & 0xFF
            # byref is pointer-class even when the pointee is float: the
            # machine passes an address in a GPR (mirrors _hint_arg_types)
            is_float = te in (0x0c, 0x0d) and not ((bits >> 29) & 1)
            slot = base + pi
            pname = safe_ident(p.name)
            if slot > 3:
                # Win64 stack parameters begin above the return address and
                # the 32-byte shadow space. Track them by their real source
                # names/types so later [rsp+disp] reads do not degrade to
                # anonymous `s_N` locals once rsp_delta follows frame allocs.
                off = 0x28 + 8 * (slot - 4)
                self.stack_map.setdefault(off, pname)
                if pt is not None:
                    self.slot_types.setdefault(pname, pt)
                    self._type_hints.setdefault(pname, pt)
                self.stack_values.setdefault(pname, Expr(pname, pt,
                    'float' if is_float else ('arr' if te in (0x1d, 0x14)
                    else ('obj' if te >= 0x10 else 'int'))))
                continue
            if is_float:
                self.regs[ARG_XMM[slot]] = Expr(pname, pt, 'float')
            else:
                # array-typed parameters carry kind 'arr' (the same kind
                # new-arrays and spill reloads already produce), so
                # [arr+0x18] folds to .Length and [arr+0x20+i*S] to
                # elements instead of raw pointer arithmetic.
                self.regs[ARG_REGS[slot]] = Expr(
                    pname, pt, 'arr' if te in (0x1d, 0x14)
                    else ('obj' if te >= 0x10 else 'int'))
        if m.generic_container != -1:
            self.hidden_method_info = True
        else:
            self.hidden_method_info = False

    # fix 60: `flags` records WHICH instruction wrote it. The six
    # flag-specific jumps have no comparison operator to splice, but
    # their meaning follows from the setter (arithmetic parks its
    # result in the lhs slot; `test a,a` puts the tested value there;
    # an SSE compare's parity flag means an unordered/NaN operand).
    # A property keeps this impossible to desync: every existing
    # `self.flags = ...` site stamps the mnemonic `_insn` is running.
    @property
    def flags(self):
        return self._flags

    @flags.setter
    def flags(self, v):
        self._flags = v
        self._flags_mn = getattr(self, '_cur_mn', None) if v else None

    def reg(self, name) -> Optional[Expr]:
        base = GPR_ALIAS.get(name, name)
        if base.startswith('XMM'):
            return self.regs.get(base)
        return self.regs.get(base)

    def set_reg(self, name, expr):
        base = GPR_ALIAS.get(name, name)
        if base in ('RSP',):
            return
        if base == 'RBP' and expr is not None:
            # A real write to RBP ends the frame-pointer fact. `mov rbp,rsp`
            # stores None (RSP is never tracked) and re-arms it on the next
            # line, so this only fires once RBP holds an actual value.
            self._rbp_frame = False
        self.regs[base] = expr

    # ------------------------------------------------------------------
    def _new_regs(self, init=None) -> _RegState:
        return _RegState(self, init)

    def _stamp(self, e):
        """Record where a register value was defined, so a later use-bind
        inserts `var tN = ...;` right after the defining instruction instead
        of at the (later) point the second use happened. First stamp wins:
        a copy re-stamping the same expression would move the declaration
        past uses that already rendered."""
        if e._defpos is not None:
            return
        t = e.text
        if not t or len(t) < _USE_BIND_MIN:
            return
        o = self.out
        if o is None:
            return
        blk = getattr(o, 'block', None)
        if blk is not None:
            e._defpos = (blk, len(blk.stmts))
        else:
            e._defpos = (None, len(o))

    def _note_use(self, e):
        """Count one rendering of a register value. Registers hold text that
        re-renders at each use, so the second rendering of an expensive
        expression binds it to a temp: the value prints once at its
        definition and every use -- including the statement being composed
        right now -- reads the temp. Counting is per expression object, not
        per text: two calls with identical text are two values, and each
        binds on its own uses."""
        if self.dry or self._copying or e is None or e._no_bind \
                or e.kind == 'sfblob' \
                or (e.kind == 'klass' and e.text.startswith('typeof(')):
            return
        t = e.text
        if len(t) < _USE_BIND_MIN or t[0] == '&':
            return
        if e.kind not in _BINDABLE_KINDS:
            return
        # calls/typeof/arithmetic bind from 16 chars; a bare member chain
        # (this.doorCollider) re-renders cheaply, so only long ones pay
        if '(' not in t and ('.' not in t or len(t) < 24):
            return
        if e._use_ip == self._cur_ip:
            return   # same instruction already counted (test r,r / add r,r)
        e._use_ip = self._cur_ip
        u = e._uses
        e._uses = 1 if u is None else u + 1
        # batch 38: remember where this rendering lands so _bind can
        # rewrite CROSS-block uses (the def-block window alone leaves
        # a use in a later block as the full text -- backlog #4's
        # duplicate impure render). A cond/ret/switch render records
        # len(stmts), which no later stmt occupies (those renders are
        # terminal in their block), so it cannot collide with a twin
        # text from another expression object.
        blk = getattr(self.out, 'block', None)
        st = e._sites
        if st is None:
            st = e._sites = []
        st.append((blk, len(blk.stmts) if blk is not None else len(self.out)))
        if e._uses == 2:
            self._bind(e)

    def _stmt_sink(self, blk):
        return blk.stmts if blk is not None else self.out

    def _last_stmt_text(self):
        st = self._stmt_sink(getattr(self.out, 'block', None))
        if not st:
            return None
        s = st[-1]
        return s if type(s) is str else (s[1] if type(s) is tuple else None)

    def _bind(self, e):
        """Materialize `e` to a temp declared at its definition (or, when no
        definition site was recorded, immediately before the first rendered
        use), then rename the expression so every later rendering -- and
        every register still holding it -- reads the temp. Earlier renderings
        in the declaration's block are found by content, not position:
        positional anchors go stale the moment a declaration shifts lines.
        Renderings in blocks that precede the declaration are left as the
        full text: rewriting them would use the temp before it exists. A
        materialization line whose whole RHS is the old text (`var k =
        old;`, e.g. a kill-on-write temp) freezes the value at its own point
        and keeps it."""
        old = e.text
        v = self.new_var()
        # an address-of expression carries its pointee's type; the temp it
        # binds to holds the ADDRESS, so the type must not rename it.
        # byte* payload cursors are the proved exception: arithmetic on
        # byte* is always byte-exact, so the declaration is honest.
        if isinstance(e.ty, tuple) and (e.kind != 'ptr' or self._is_byte_cursor(e)) \
                and not old.startswith('&'):
            if _is_unresolved_gp(e.ty):
                self._gp_blocked.add(v)
            else:
                vt = getattr(self, '_var_types', None)
                if vt is None:
                    vt = self._var_types = {}
                vt.setdefault(v, e.ty)
        line = 'var %s = %s;' % (v, strip_outer(old))
        dp = e._defpos
        if dp is not None:
            dblk, didx = dp
            sink = self._stmt_sink(dblk)
            # several expressions can share one definition slot (defined
            # between the same two statements): skip past declarations
            # already parked there, but stop before one that reads us --
            # either through our old text or through the temp we just chose
            while didx < len(sink):
                s = sink[didx]
                c = s if type(s) is str else (s[1] if type(s) is tuple else None)
                if c is None or not c.startswith('var '):
                    break
                if old in c or _mentions(c, v):
                    break
                didx += 1
            if dblk is not None:
                dblk.stmts.insert(didx, line)
            else:
                self.out.insert(didx, (self._cur_ip, line, None))
        else:
            # no definition site: declare right before the first statement
            # that renders the text
            dblk = getattr(self.out, 'block', None)
            st = self._stmt_sink(dblk)
            didx = len(st)
            for i in range(len(st)):
                s = st[i]
                c = s if type(s) is str else (s[1] if type(s) is tuple else '')
                if old in c and not (c.startswith('var ')
                                     and c.rstrip().endswith('= %s;' % old)):
                    didx = i
                    break
            if dblk is not None:
                dblk.stmts.insert(didx, line)
            else:
                self.out.insert(didx, (self._cur_ip, line, None))
        st = self._stmt_sink(dblk)
        # the rewrite window is bounded: uses that render far below the
        # declaration are rare, and skipping them only leaves the full text
        # in place (which re-renders correctly) -- while scanning an unbounded
        # tail costs quadratically on the wide blocks of flat-lifted methods
        # fix 58b: a statement that is EXACTLY `old;` is a standalone
        # side-effecting emission -- a distinct instruction's own call,
        # not a re-render of this value. Rewriting it yields `objN;`
        # (not a C# expression statement) and collapses several separate
        # allocations into one identity. The cross-block pass below
        # already reasons per-object for exactly this reason; this window
        # was still per-text. Ground truth: SaveManager 0x1805AA260, five
        # `new List<int>();` at five IPs (work/probe_b58b_bindbare.py).
        bare = '%s;' % old
        # fix 58c: indices of THIS expression object's own render sites in
        # the declaration's block, shifted past the declaration just
        # inserted at didx. A bare `old;` at one of these is this value's
        # own emission -- subsumed by `var v = old;` -- so it is dropped;
        # a bare `old;` anywhere else belongs to a different instruction
        # and is left untouched (fix 58b).
        own = set()
        for _sb, _si in (e._sites or ()):
            if _sb is dblk:
                own.add(_si + 1 if _si >= didx else _si)
        for i in range(didx, min(len(st), didx + 64)):
            s = st[i]
            if type(s) is str:
                if s == line or old not in s:
                    continue
                if s.strip() == bare:
                    if i in own:
                        st[i] = ''
                    continue
                if s.startswith('var ') and s.rstrip().endswith('= %s;' % old):
                    continue
                st[i] = _bind_replace(s, old, v)
            elif type(s) is tuple:
                c = s[1]
                if old not in c or c == line:
                    continue
                if c.strip() == bare:
                    if i in own:
                        st[i] = (s[0], '', s[2])
                    continue
                if c.startswith('var ') and c.rstrip().endswith('= %s;' % old):
                    continue
                st[i] = (s[0], _bind_replace(c, old, v), s[2])
        # a use #1 may have rendered into the block's condition / return /
        # switch index rather than a statement: those are plain strings on
        # the block, rewritten the same way
        if dblk is not None:
            if dblk.cond and old in dblk.cond:
                dblk.cond = _bind_replace(dblk.cond, old, v)
            if dblk.ret and old in dblk.ret:
                dblk.ret = _bind_replace(dblk.ret, old, v)
            if dblk.switch_idx and old in dblk.switch_idx:
                dblk.switch_idx = _bind_replace(dblk.switch_idx, old, v)
        # cross-block render sites (batch 38): the window above covers
        # only the declaration's own block, so a use that rendered in a
        # LATER block kept the full text -- the duplicate impure render
        # (`obj10 = Allocate(...)` decl plus the same call inline one
        # block down). Rewrite the recorded sites of THIS expression
        # object -- per object, not per text, so a real second identical
        # call is never touched -- and only in blocks reachable from
        # the declaration's (a path around the declaration must keep
        # the full text: the temp would not exist there). A site whose
        # index no longer holds our text (shifted by another bind's
        # inserted declaration) is skipped -- the full text re-renders
        # correctly, which is the pre-batch-38 behavior.
        sites = e._sites
        blocks = getattr(self, '_blocks', None)
        reach = None
        if sites and blocks is not None and dblk is not None:
            reach = set()
            stk = list(dblk.succs or ())
            while stk:
                x = stk.pop()
                if x in reach or not (0 <= x < len(blocks)):
                    continue
                reach.add(x)
                stk.extend(blocks[x].succs or ())
        for sblk, sidx in sites or ():
            if sblk is None:
                continue
            si = sidx
            if sblk is dblk:
                # window covered [didx, didx+64); before didx renders
                # before the declaration; past the window, shift +1
                if sidx < didx or didx <= sidx < didx + 64:
                    continue
                si = sidx + 1
            elif reach is None or sblk.bid not in reach:
                continue
            stt = sblk.stmts
            if 0 <= si < len(stt):
                s = stt[si]
                c = s if type(s) is str else (s[1] if type(s) is tuple else None)
                # fix 58c: this list is per-OBJECT, so a bare `old;` here
                # is this value's own emission -- the declaration already
                # performs it, and rewriting it would render `objN;`
                if c is not None and c.strip() == bare:
                    stt[si] = '' if type(s) is str else (s[0], '', s[2])
                    continue
                if c and old in c and not (c.startswith('var ')
                                           and c.rstrip().endswith('= %s;' % old)):
                    if type(s) is str:
                        stt[si] = _bind_replace(c, old, v)
                    else:
                        stt[si] = (s[0], _bind_replace(c, old, v), s[2])
            if sblk.cond and old in sblk.cond:
                sblk.cond = _bind_replace(sblk.cond, old, v)
            if sblk.ret and old in sblk.ret:
                sblk.ret = _bind_replace(sblk.ret, old, v)
            if sblk.switch_idx and old in sblk.switch_idx:
                sblk.switch_idx = _bind_replace(sblk.switch_idx, old, v)
        e._sites = None
        # Packed phi provenance is keyed by rendered token.  Binding renames
        # that token, so keep the same proof reachable under the temp name;
        # otherwise a later high-lane read silently loses every predecessor.
        aps = getattr(self, '_aggregate_phi_sources', None)
        if aps is not None and old in aps:
            aps.setdefault(v, aps[old])
        apt = getattr(self, '_aggregate_phi_types', None)
        if apt is not None and old in apt:
            apt.setdefault(v, apt[old])
        e.text = v
        e._prec = None   # the temp name is an atom

    # ------------------------------------------------------------------
    def _flush_pending_calls(self, phi_copies=None):
        """Emit ignored non-void call results as bare statements."""
        pending = getattr(self, '_pending_calls', None)
        self._pending_calls = []
        if not pending or getattr(self, 'dry', False):
            return
        by_blk = {}
        seen = set()
        for e, ip, asm in pending:
            dp = getattr(e, '_defpos', None)
            if dp is not None and dp[0] is not None:
                seen.update(dp[0].stmts)
        if isinstance(self.out, list):
            seen.update(s[1] for s in self.out if isinstance(s, tuple))
        if phi_copies:
            for cps in phi_copies.values():
                seen.update(cps)
        for e, ip, asm in pending:
            if e is None or getattr(e, '_uses', None):
                continue
            # A derived copy (movzx mask, phi value) may already carry
            # the text into a statement without counting a use on this
            # object. Flushing again would twin the call.
            if any(e.text in s for s in seen):
                continue
            dp = getattr(e, '_defpos', None)
            if dp is None or dp[0] is None:
                if isinstance(self.out, list):
                    self.out.append((ip, e.text + ';', asm))
                continue
            by_blk.setdefault(id(dp[0]), (dp[0], []))[1].append((dp[1], e, ip, asm))
        for blk, items in by_blk.values():
            # stable descending by defpos; ties (which crashed the old
            # bare-tuple sort on Expr compare) iterate in reverse
            # discovery order so the insert-at-idx lands them in native
            # execution order.
            for idx, e, ip, asm in sorted(reversed(items), key=lambda t: t[0], reverse=True):
                blk.stmts.insert(min(idx, len(blk.stmts)), e.text + ';')

    def emit(self, ip, code, asm):
        if getattr(self, 'dry', False):
            return
        self.out.append((ip, code, asm))

    def new_var(self):
        v = 't%d' % self.var_n
        self.var_n += 1
        return v

    def _fresh_unknowns(self):
        """give clobbered volatile regs fresh unknown names so later reads
        render as vN instead of '?'"""
        if getattr(self, '_u', 0) > 200000:
            return
        for r in VOLATILE:
            if r in self.regs:
                continue
            self._u = getattr(self, '_u', 0) + 1
            e = Expr('v%d' % self._u, None, '?')
            e._unk = True             # fix 58: clobbered, not re-written
            self.regs[r] = e

    def _fp_operand(self, e):
        """A missing register operand in an FP/SSE operation is an
        unknown, never a fabricated `0f` zero. Only the NAME is
        unknown; the arithmetic around it still renders."""
        if e is not None:
            return e
        u = getattr(self, '_u', 0) + 1
        self._u = u
        e = Expr('v%d' % u, None, '?')
        e._unk = True
        return e

    def _mk(self, text, ty=None, kind='?', cap=240):
        """Build an Expr, materializing oversized expressions into a temp var
        to prevent exponential text growth from self-referential folds."""
        if len(text) > cap:
            v = self.new_var()
            if getattr(self, 'dry', False):
                return Expr(v, ty, kind)
            # fix 134: the comment is opaque to textpass, so a load-
            # width marker (`(__w_int)`) would leak into it verbatim
            ct = text
            if '(__w_' in ct:
                ct = re.sub(r'\(__w_(?:sbyte|short|ushort|int)\)', '', ct)
            self.emit(0, 'var %s = 0; // %s' % (v, ct[:cap] + ('...' if len(ct) > cap else '')), None)
            return Expr(v, ty, kind)
        return Expr(text, ty, kind)

    def _rbp_is_frame(self) -> bool:
        """Whether [rbp+X] addresses a stack slot right now.

        RBP is a frame pointer only when it cannot be a live scratch
        value: unreadable (a `mov rbp,rsp` frame -- RSP is never
        tracked), an `&s_xx` slot address (an `lea rbp,[rsp+C]` frame),
        `?addr` from an untracked rsp-derived base (`mov rax,rsp;
        lea rbp,[rax-C]`), or never-written (EH pads inherit the
        dispatcher's established frame). Params, objects and composites
        are scratch and resolve through the register value instead of
        aliasing stack slot s_X (InventoryManager.
        Rpc_CMD_UpdateInventoryForHost 0x180704750 keeps param 1 in
        RBP, so [rbp+0x18] is inventoryIds_.Length). `_rbp_frame` is the
        tracked fact "RBP is the frame pointer right now": set by
        `mov rbp,rsp`, cleared by any other write to RBP, and deliberately
        NOT derived from the register value, which the pass-2 merge
        rewrites."""
        e = self.reg('RBP')
        if e is None:
            return True
        t = e.text or ''
        if t == '?addr':
            return True
        if getattr(e, '_unk', False):
            return True
        if getattr(self, '_rbp_frame', False):
            # RBP IS the frame pointer, tracked as a fact because the pass-2
            # merge rewrites the register value out from under every arm
            # above: it replaces a never-written RBP = None with Expr('?'),
            # and _bind then rewrites that to a temp name, so the merged
            # region matched nothing and every [rbp+N] in it fabricated
            # pointer arithmetic on the seed (`((byte*)obj9 - 0x30)[0] =
            # vector31` where obj9 is not a pointer). Set by `mov rbp,rsp`,
            # cleared by any other write to RBP (see set_reg), and untouched
            # by the merge, which writes L.regs directly.
            return True
        return t.startswith('&s_')

    def slot_var(self, off):
        # Normalize HERE, at the single choke point, because callers hand us
        # three sign conventions: the RSP-copy path passes an already
        # sign-extended `_stack_address`, while the RSP/RBP direct paths and
        # the LEA path pass iced-x86's raw 0xffffffffffffffd0 for [rbp-0x30].
        # One method then held two coordinate systems for one native home, so
        # a [copy+N] write and an [rsp+M] read of the same slot became two C#
        # locals, and the name came out as `s_ffffffffffffffd0`. `sdisp` is
        # idempotent on an already-negative value, so every caller's existing
        # name is unchanged; only the raw paths move -- onto the key space
        # `_stack_address` and the entry-parameter classifier already use.
        off = sdisp(off)
        key = off + self.rsp_delta
        if key not in self.stack_map:
            self.stack_map[key] = 's_%x' % abs(off)
        return self.stack_map[key]

    @staticmethod
    def _copy_expr(e):
        if e is None:
            return None
        c = Expr(e.text, e.ty, e.kind, e.recv)
        for name in ('_prec', '_unk', '_usg_idx', '_mi', '_td',
                     '_no_bind', '_alloc', '_slice', '_stack_offset', '_bytes', '_parts',
                     '_newarr', '_arr_klass', '_dry_proof', '_ifm'):
            val = getattr(e, name, None)
            if val is not None and not (name == '_unk' and not val):
                setattr(c, name, val)
        return c
