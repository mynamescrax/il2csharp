from il2cpp.prelude import *  # noqa: F401,F403
from il2cpp.binary import ELF
from il2cpp.lifter import Lifter

def is_arm64_binary(bin_):
    """True for ARM64 ELFs (Android libil2cpp.so, e_machine 183)."""
    return isinstance(bin_, ELF) and getattr(bin_, 'e_machine', 0) == 183


class AInsn:
    """Capstone AArch64 instruction with the iced-shaped attributes the
    shared CFG layer reads (.ip/.next_ip/.flow_control/.op0_kind/
    .near_branch_target/.mnemonic). Anything else reads as None, so
    x64-specific pattern matches safely miss instead of crashing."""
    __slots__ = ('ip', 'size', 'next_ip', 'mnemonic', 'op_str', 'kind',
                 'target', 'flow_control', 'op0_kind', 'near_branch_target')

    def __init__(self, ip, size, mnemonic, op_str, kind, target,
                 flow_control, op0_kind):
        self.ip = ip
        self.size = size
        self.next_ip = ip + size
        self.mnemonic = mnemonic
        self.op_str = op_str
        self.kind = kind
        self.target = target
        self.flow_control = flow_control
        self.op0_kind = op0_kind
        self.near_branch_target = target

    def __getattr__(self, name):
        if name.startswith('__'):
            raise AttributeError(name)
        return None


class Arm64Lifter(Lifter):
    """ARM64 bodies. Scaffold milestone: capstone decode + linear
    asm-comment lift; Arm64Decompiler drives real-CFG structured lifts
    next, then per-mnemonic symbolic execution replaces the comments."""

    def __init__(self, il2, asm_comments=False):
        self.il = il2
        self.bin = il2.bin
        self.meta = il2.meta
        self.asm_comments = asm_comments
        self.dry = False
        self._cur_ip = 0
        self._copying = False
        self._init_runtime_ids_arm64()

    def _init_runtime_ids_arm64(self):
        self.rt_init_meta = None
        b = self.bin
        self.rt_value_box = next(
            (va for va, nm in b.exports.items() if nm == 'il2cpp_value_box'), None)

    # AAPCS64 argument slots (x0-x7; the sret hidden PtrOut in x8 is
    # modelled when call semantics land)
    ARG_REGS64 = ['X%d' % i for i in range(8)]

    def _setup_entry(self, m, td):
        # scaffold: shared per-method state only; register binding lands
        # with the symbolic-execution milestone
        self._var_types = {}
        self._type_hints = {}
        self._gp_blocked = set()
        self._last_tabread = None
        self.hidden_method_info = m.generic_container != -1

    def _decode_method(self, m):
        """Capstone AArch64 decode of [m.addr, next_method_start)."""
        from capstone import Cs, CS_ARCH_ARM64, CS_MODE_LITTLE_ENDIAN, CS_OP_IMM
        from iced_x86 import FlowControl, OpKind
        b = self.bin
        va = m.addr
        nxt = None
        if hasattr(self.il, 'next_method_start'):
            try:
                nxt = self.il.next_method_start(va)
            except Exception:
                nxt = None
        hard = va + 0x40000
        bound = min(nxt or hard, hard)
        end = min(bound, va + 0x10000)
        code = b.read(va, end - va)
        if not code:
            return []
        cs = Cs(CS_ARCH_ARM64, CS_MODE_LITTLE_ENDIAN)
        cs.detail = True
        out = []
        for ins in cs.disasm(code, va):
            out.append(self._a_insn(ins, FlowControl, OpKind, CS_OP_IMM))
            if len(out) >= 20000:
                break
        return out

    @staticmethod
    def _branch_target(ins, idx, CS_OP_IMM):
        try:
            ops = ins.operands
            if idx < len(ops) and ops[idx].type == CS_OP_IMM:
                return ops[idx].imm
        except Exception:
            pass
        return None

    def _a_insn(self, ins, FlowControl, OpKind, CS_OP_IMM):
        mn = ins.mnemonic
        op = ins.op_str
        NB = OpKind.NEAR_BRANCH64
        RG = OpKind.REGISTER
        if mn == 'ret':
            return AInsn(ins.address, ins.size, mn, op, 'ret', None,
                         FlowControl.RETURN, RG)
        if mn in ('cbz', 'cbnz'):
            t = self._branch_target(ins, 1, CS_OP_IMM)
            return AInsn(ins.address, ins.size, mn, op, 'cb', t,
                         FlowControl.CONDITIONAL_BRANCH, NB if t is not None else RG)
        if mn in ('tbz', 'tbnz'):
            t = self._branch_target(ins, 2, CS_OP_IMM)
            return AInsn(ins.address, ins.size, mn, op, 'tb', t,
                         FlowControl.CONDITIONAL_BRANCH, NB if t is not None else RG)
        if mn.startswith('b.'):
            t = self._branch_target(ins, 0, CS_OP_IMM)
            return AInsn(ins.address, ins.size, mn, op, 'bc', t,
                         FlowControl.CONDITIONAL_BRANCH, NB if t is not None else RG)
        if mn == 'b':
            t = self._branch_target(ins, 0, CS_OP_IMM)
            if t is not None:
                return AInsn(ins.address, ins.size, mn, op, 'b', t,
                             FlowControl.UNCONDITIONAL_BRANCH, NB)
            return AInsn(ins.address, ins.size, mn, op, 'br', None,
                         FlowControl.INDIRECT_BRANCH, RG)
        if mn == 'bl':
            t = self._branch_target(ins, 0, CS_OP_IMM)
            return AInsn(ins.address, ins.size, mn, op, 'bl', t,
                         FlowControl.CALL, NB if t is not None else RG)
        if mn == 'blr':
            return AInsn(ins.address, ins.size, mn, op, 'blr', None,
                         FlowControl.INDIRECT_CALL, RG)
        if mn == 'br':
            return AInsn(ins.address, ins.size, mn, op, 'br', None,
                         FlowControl.INDIRECT_BRANCH, RG)
        return AInsn(ins.address, ins.size, mn, op, 'fall', None,
                     FlowControl.NEXT, RG)

    def lift(self, m, td):
        """Linear fallback: native asm as comment lines (always succeeds)."""
        try:
            inss = self._decode_method(m)
        except Exception as ex:
            return ['// lift failed: %s' % ex]
        return ['// %#x: %s %s' % (a.ip, a.mnemonic, a.op_str) for a in inss] or ['// empty']

