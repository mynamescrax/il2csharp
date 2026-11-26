"""Win64 bit masks formed from managed Boolean fields and the carry from NEG."""
from il2cpp.expr import Expr, _INT_TY
from il2cpp.prelude import HAVE_ICED
from il2cpp.text import _BIN_PREC, imm_of, reg_name, sdisp, strip_outer

if HAVE_ICED:
    from iced_x86 import MemorySizeExt, Mnemonic as M, OpKind as K, Register as R, RegisterExt


def _byte_field(lift, ins, value):
    """A one-byte instance field on this (not a synthetic integer or an accessor)."""
    if (not value or value._unk or not value.ty or lift.il._type_enum(value.ty) != 2 or
            value.ty[1] & (1 << 29) or MemorySizeExt.size(ins.memory_size) != 1 or
            ins.has_segment_prefix or ins.memory_index != R.NONE or not RegisterExt.is_gpr64(ins.memory_base)):
        return False
    base = dict.get(lift.regs, reg_name(ins.memory_base))
    if (not base or base._unk or base.text != 'this' or not base.ty or lift.il._type_enum(base.ty) != 0x12 or
            not 0 <= base.ty[0] < len(lift.meta.typedefs)):
        return False
    fields = lift.il.instance_field_chain(base.ty[0]) or {}
    row = fields.get(sdisp(ins.memory_displacement))
    return bool(row and 0 <= row[1] < len(lift.il.types) and lift.il.types[row[1]] == value.ty and
                value.text == 'this.' + row[0])


def _bit(ins):
    if ins.op1_kind in (K.IMMEDIATE8TO32, K.IMMEDIATE32):
        v = imm_of(ins)
        if 0 < v < 0x80000000 and not v & (v-1):
            return v
    return None


def _contiguous(seq):
    return all(a.next_ip == b.ip for a, b in zip(seq, seq[1:]))


def _part(lift, dst, stage, ins, condition, n):
    e = Expr('(%s ? %d : 0)' % (condition, n), _INT_TY, 'int')
    e._prec = -1  # C# conditional binds below every binary operator
    e._mask_step = stage, ins.next_ip, condition
    lift.set_reg(reg_name(dst), e)
    lift.flags = (e, Expr('0', None, 'int'))


def mask_step(lift, seq, j):
    """Only carry a witness between adjacent instructions in one basic block.
    NEG sets CF iff the original byte is nonzero; SBB d,d ignores the old d.
    Tag the produced Expr, not the register name or a long-lived flag hint.
    """
    block = getattr(lift.out, 'block', None)
    if block is None or block.insns is not seq:
        return False
    ins = seq[j]
    dst = ins.op0_register
    if ins.mnemonic == M.NEG:
        if j < 1 or j + 2 >= len(seq):
            return False
        load, _, borrow, mask = seq[j-1:j+3]
        if (not _contiguous(seq[j-1:j+3]) or load.mnemonic != M.MOVZX or load.op1_kind != K.MEMORY or
                not RegisterExt.is_gpr32(load.op0_register) or not RegisterExt.is_gpr8(dst) or
                dst in (R.AH, R.BH, R.CH, R.DH) or reg_name(dst) != reg_name(load.op0_register) or
                borrow.mnemonic != M.SBB or not RegisterExt.is_gpr32(borrow.op0_register) or
                borrow.op0_register != borrow.op1_register or mask.mnemonic != M.AND or
                borrow.op0_register != mask.op0_register or not _bit(mask)):
            return False
        value = dict.get(lift.regs, reg_name(dst))
        if not _byte_field(lift, load, value):
            return False
        _part(lift, dst, 'neg', ins, value.text, 255)
        return True
    if ins.mnemonic in (M.SBB, M.AND):
        if not j:
            return False
        prev = seq[j-1]
        e = dict.get(lift.regs, reg_name(prev.op0_register))
        stage, ip, condition = getattr(e, '_mask_step', (None, None, None))
        if ip != ins.ip:
            return False
        if ins.mnemonic == M.SBB and stage == 'neg' and prev.mnemonic == M.NEG:
            _part(lift, dst, 'borrow', ins, condition, -1)
            return True
        if ins.mnemonic == M.AND and stage == 'borrow' and prev.mnemonic == M.SBB:
            _part(lift, dst, 'mask', ins, condition, _bit(ins))
            return True
        return False
    # mov d,s; or d,bit; cmp byte [this+field],0; cmove d,s
    # Both choices share s. Factoring it preserves the native order and
    # avoids rendering the preceding flag loads on both sides of a ternary.
    if ins.mnemonic != M.CMOVE or j < 3:
        return False
    move, add, cmp, _ = seq[j-3:j+1]
    src = ins.op1_register
    if (not _contiguous(seq[j-3:j+1]) or not RegisterExt.is_gpr32(src) or not RegisterExt.is_gpr32(dst) or
            dst == src or move.mnemonic != M.MOV or move.op0_register != dst or move.op1_register != src or
            add.mnemonic != M.OR or add.op0_register != dst or not _bit(add) or cmp.mnemonic != M.CMP or
            cmp.op0_kind != K.MEMORY or cmp.op1_kind != K.IMMEDIATE8 or cmp.immediate8 != 0):
        return False
    base = dict.get(lift.regs, reg_name(src))
    lhs, rhs = lift.flags or (None, None)
    stage, end, _ = getattr(base, '_mask_step', (None, None, None))
    if (stage != 'mask' or getattr(lift, '_flags_mn', None) != M.CMP or not rhs or rhs.text != '0' or
            not _byte_field(lift, cmp, lhs)):
        return False
    if end != move.ip:
        # A null check can separate adjacent selections. Only follow its
        # fallthrough, with a single predecessor and no intervening writer.
        if j != 3 or len(block.preds) != 1:
            return False
        pred = lift._blocks[block.preds[0]]
        if len(pred.insns) < 3:
            return False
        test, jump = pred.insns[-2:]
        if (test.ip != end or test.mnemonic != M.TEST or not RegisterExt.is_gpr64(test.op0_register) or
                test.op0_register != test.op1_register or jump.mnemonic != M.JE or jump.near_branch_target == move.ip or
                not _contiguous((test, jump, move)) or (pred.end_state or {}).get(reg_name(src)) is not base):
            return False
    elif j == 3:  # first instruction in this block; mere address adjacency is not dominance
        return False
    e = Expr('%s | (%s ? %d : 0)' % (base.text, lhs.text, _bit(add)), _INT_TY, 'int')
    e._prec = _BIN_PREC['|']
    e._mask_step = 'mask', ins.next_ip, None
    lift.set_reg(reg_name(dst), e)
    return True


def enum_mask(lift, value, ty, text):
    """Cast the computed integer at a proven Int32-backed enum sink only."""
    if (getattr(value, '_mask_step', (None,))[0] != 'mask' or not ty or
            lift.il._type_enum(ty) != 0x11 or ty[1] & (1 << 29) or not 0 <= ty[0] < len(lift.meta.typedefs)):
        return text
    td = lift.meta.typedefs[ty[0]]
    if not td.is_enum or not 0 <= td.element < len(lift.il.types) or lift.il._type_enum(lift.il.types[td.element]) != 0x08:
        return text
    return '(%s)(%s)' % (lift.il.type_name(ty), strip_outer(text))
