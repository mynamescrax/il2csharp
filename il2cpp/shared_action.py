"""Folded void instance actions with caller-proven arguments."""
import re

from il2cpp.awaiter import _unused_return
from il2cpp.binary import PE
from il2cpp.framed_cleanup import framed_cleanup_tail
from il2cpp.metadata import source_params
from il2cpp.names import safe_ident
from il2cpp.prelude import HAVE_ICED
from il2cpp.text import reg_name, sdisp

if HAVE_ICED:
    from iced_x86 import FlowControl as F, InstructionInfoFactory, Mnemonic as M, OpAccess, OpKind as K, Register as R, RegisterExt
    _NONVOL = (R.RBX, R.RBP, R.RSI, R.RDI, R.R12, R.R13, R.R14, R.R15)


def _frame_save(i):
    return (i.memory_base == R.RSP and i.memory_index == R.NONE and not i.has_segment_prefix
            and i.op0_kind == K.MEMORY and sdisp(i.memory_displacement) >= 0x20
            and ((i.mnemonic == M.MOV and i.op1_register in _NONVOL) or
                 (i.mnemonic == M.MOVAPS and R.XMM6 <= i.op1_register <= R.XMM15)))


def _setup(lift, ins):
    block = getattr(getattr(lift, 'out', None), 'block', None)
    if block is None or len(block.preds) != 1 or not 0 <= block.preds[0] < len(lift._blocks):
        return None
    pred = lift._blocks[block.preds[0]]
    # Only a normal fallthrough of the explicit null test. Use native order:
    # the field is captured *before* calling the managed argument getter.
    left = pred.insns
    right = [i for i in block.insns if i.ip <= ins.ip]
    seq = left + right
    if not right or any(a.next_ip != b.ip for a, b in zip(seq, seq[1:])):
        return None
    before = [i for i in left if not _frame_save(i)]
    after = [i for i in right if not _frame_save(i)]
    if len(before) != 6 or len(after) != 5:
        return None
    field, zero, self_arg, getter, test, null = before
    hidden, flag, arg, receiver, call = after
    obj, saved = field.memory_base, field.op0_register
    if (field.mnemonic != M.MOV or field.op1_kind != K.MEMORY or field.has_segment_prefix or
            field.memory_index != R.NONE or obj not in _NONVOL or saved not in _NONVOL or obj == saved or
            zero.mnemonic != M.XOR or zero.op0_register != R.EDX or zero.op1_register != R.EDX or
            self_arg.mnemonic != M.MOV or self_arg.op0_register != R.RCX or self_arg.op1_register != obj or
            getter.mnemonic != M.CALL or getter.op0_kind != K.NEAR_BRANCH64 or
            test.mnemonic != M.TEST or test.op0_register != saved or test.op1_register != saved or
            null.mnemonic != M.JE or null.op0_kind != K.NEAR_BRANCH64 or
            hidden.mnemonic != M.XOR or hidden.op0_register != R.R9D or hidden.op1_register != R.R9D or
            flag.mnemonic != M.MOV or flag.op0_register != R.R8L or flag.op1_kind != K.IMMEDIATE8 or flag.immediate8 not in (0, 1) or
            arg.mnemonic != M.MOV or arg.op0_register != R.RDX or arg.op1_register != R.RAX or
            receiver.mnemonic != M.MOV or receiver.op0_register != R.RCX or receiver.op1_register != saved or
            call.ip != ins.ip or call.mnemonic != M.CALL or call.op0_kind != K.NEAR_BRANCH64):
        return None
    # Preserve the null path as C#'s receiver null check. A branch that
    # quietly skips the invocation has different observable behavior.
    if not _raises_on_null(lift, null):
        return None
    return obj, sdisp(field.memory_displacement), getter.near_branch_target, flag.immediate8


def _raises_on_null(lift, null):
    dest = next((b for b in lift._blocks if b.insns and b.insns[0].ip == null.near_branch_target), None)
    if not dest or dest.insns[0].mnemonic != M.CALL or dest.insns[0].op0_kind != K.NEAR_BRANCH64:
        return False
    helper = dest.insns[0].near_branch_target
    return lift._named_raise_throw(helper, lift._call_name(helper)) == 'System.NullReferenceException'


def _plain_return(il, addr):
    code = il.bin.read(addr, 3) if il.bin.is_exec_va(addr) else None
    return bool(code and (code.startswith(b'\xc3') or code == b'\xc2\x00\x00'))


def _init_arm(cold, init, flag):
    if len(cold)<3 or len(cold)%2!=1: return False
    for lea,call in zip(cold[:-1:2],cold[1:-1:2]):
        if (lea.mnemonic!=M.LEA or lea.op0_register!=R.RCX or lea.memory_base!=R.RIP or
                call.mnemonic!=M.CALL or call.op0_kind!=K.NEAR_BRANCH64 or call.near_branch_target!=init): return False
    store=cold[-1]
    return (store.mnemonic==M.MOV and store.memory_base==R.RIP and store.memory_size==1 and
            store.ip_rel_memory_address==flag and store.op1_kind==K.IMMEDIATE8 and store.immediate8==1)


def _guard_entry(lift, block, ins, saves, restores):
    """Shared outer shape: no other entry into the saves, cold metadata
    setup, or argument reloads. Either native guard edge may be linearized."""
    blocks=getattr(lift,'_blocks',())
    if len(blocks)<3 or blocks[2] is not block: return None
    head,cold=blocks[:2]; ops=block.insns[:restores]
    if (not head.is_entry or head.preds or len(head.insns)!=saves or len(ops)!=restores or ops[-1].ip!=ins.ip or
            head.insns[0].ip!=lift._current_method.addr or cold.succs!=[block.bid] or
            not head.succs or not set(head.succs)<={cold.bid,block.bid} or
            cold.preds!=([head.bid] if cold.bid in head.succs else []) or
            set(block.preds)!=({head.bid,cold.bid} if block.bid in head.succs else {cold.bid})): return None
    seq=head.insns+cold.insns+ops
    if (any(a.next_ip!=b.ip for a,b in zip(seq,seq[1:])) or
            any(i.has_segment_prefix or i.has_lock_prefix or i.has_rep_prefix or i.has_repne_prefix for i in seq)): return None
    branch=head.insns[-1]; cmp=next((i for i in head.insns if i.mnemonic==M.CMP),None)
    if (not cmp or cmp.memory_base!=R.RIP or cmp.memory_size!=1 or cmp.op1_kind!=K.IMMEDIATE8 or cmp.immediate8!=0 or
            branch.mnemonic!=M.JNE or branch.op0_kind!=K.NEAR_BRANCH64 or branch.near_branch_target!=ops[0].ip): return None
    eh=lift.il.eh_regions(lift._current_method.addr) or {}
    if not any(seq[0].ip<=p<=ins.ip for p in eh.get('pads',())) and _init_arm(cold.insns,lift.rt_init_meta,cmp.ip_rel_memory_address):
        return head.insns,ops


def _guarded_this_forward(lift, block, ins):
    witness=_guard_entry(lift,block,ins,5,3)
    if not witness: return False
    (push,sub,cmp,save,_),(zero,reload,_)=witness; parked=push.op0_register
    return (push.mnemonic==M.PUSH and parked in _NONVOL and sub.mnemonic==M.SUB and sub.op0_register==R.RSP and
            sub.op1_kind==K.IMMEDIATE8TO64 and sub.immediate8to64==0x20 and cmp.mnemonic==M.CMP and
            save.mnemonic==M.MOV and save.op0_register==parked and save.op1_register==R.RCX and
            zero.mnemonic==M.XOR and zero.op0_register==zero.op1_register==R.EDX and
            reload.mnemonic==M.MOV and reload.op0_register==R.RCX and reload.op1_register==parked)


def _guarded_ref_bool_forward(lift, block, ins):
    """Two distinct reference saves plus the low-byte bool parked before
    init. Zero extension on both moves preserves exactly that bool byte."""
    witness=_guard_entry(lift,block,ins,9,5)
    if not witness: return False
    (home1,home2,push,sub,cmp,flag,arg,recv,_),(zero,flag2,arg2,recv2,call)=witness
    a,b,c=recv.op0_register,arg.op0_register,push.op0_register
    if len({a,b,c})!=3 or not {a,b,c}<=set(_NONVOL): return False
    for home,r,off in ((home1,a,8),(home2,b,16)):
        if (home.mnemonic!=M.MOV or home.op0_kind!=K.MEMORY or home.op1_register!=r or home.memory_base!=R.RSP or
                home.memory_index!=R.NONE or home.memory_displacement!=off): return False
    return (push.mnemonic==M.PUSH and sub.mnemonic==M.SUB and sub.op0_register==R.RSP and
            sub.op1_kind==K.IMMEDIATE8TO64 and sub.immediate8to64==32 and cmp.mnemonic==M.CMP and
            flag.mnemonic==M.MOVZX and RegisterExt.is_gpr32(flag.op0_register) and RegisterExt.full_register(flag.op0_register)==c and
            flag.op1_register==R.R8L and arg.mnemonic==M.MOV and arg.op1_register==R.RDX and
            recv.mnemonic==M.MOV and recv.op1_register==R.RCX and zero.mnemonic==M.XOR and zero.op0_register==zero.op1_register==R.R9D and
            flag2.mnemonic==M.MOVZX and flag2.op0_register==R.R8D and RegisterExt.is_gpr8(flag2.op1_register) and
            flag2.op1_register not in (R.AH,R.BH,R.CH,R.DH) and RegisterExt.full_register(flag2.op1_register)==c and
            arg2.mnemonic==M.MOV and arg2.op0_register==R.RDX and arg2.op1_register==b and
            recv2.mnemonic==M.MOV and recv2.op0_register==R.RCX and recv2.op1_register==a and
            call.mnemonic==M.CALL and call.op0_kind==K.NEAR_BRANCH64)


def _boxed_flag_borrow(lift,window,flag_reg,frame):
    """One nonescaping value_box(bool, &local) borrow. Its entire input
    byte lies above outgoing shadow space and below the saved registers."""
    if len(window)!=4: return False
    klass,addr,store,box=window; il=lift.il
    off=sdisp(addr.memory_displacement)
    if (klass.mnemonic!=M.MOV or klass.op0_register!=R.RCX or klass.memory_base!=R.RIP or
            addr.mnemonic!=M.LEA or addr.op0_register!=R.RDX or addr.memory_base!=R.RSP or addr.memory_index!=R.NONE or
            not 0x20<=off<frame or store.mnemonic!=M.MOV or store.memory_base!=R.RSP or store.memory_index!=R.NONE or
            sdisp(store.memory_displacement)!=off or store.op1_register!=flag_reg or
            not RegisterExt.is_gpr8(flag_reg) or flag_reg in (R.AH,R.BH,R.CH,R.DH) or
            box.mnemonic!=M.CALL or box.op0_kind!=K.NEAR_BRANCH64 or box.near_branch_target!=getattr(lift,'rt_value_box',None) or
            il.bin.exports.get(box.near_branch_target)!='il2cpp_value_box' or il.addr_candidates.get(box.near_branch_target)): return False
    u=il.decode_slot(klass.ip_rel_memory_address) or {}; ti=u.get('td',-1)
    if u.get('kind') not in (1,2) or not 0<=ti<len(il.meta.typedefs): return False
    td=il.meta.typedefs[ti]
    return (td.is_valuetype and not td.is_enum and il.typedef_full(ti)=='System.Boolean' and
            0<=td.byval<len(il.types) and il._closed_type_key(il.types[td.byval])==(2,0) and il.value_type_size(ti)==1)


def _cleanup_tail_forward(lift, block, jump, *, boxes=None):
    """Follow saved Win64 inputs through cleanup to a shared void tail.

    Use the original instruction stream: some metadata-init/throw edges have
    been removed from the structured CFG. No alternate entry, write to a
    parked argument, or frame/home alias can precede the argument reloads.
    """
    blocks=getattr(lift,'_blocks',()); method=lift._current_method
    if block is not None and len(block.insns)==11:
        return framed_cleanup_tail(lift,block,jump)
    if (not blocks or block is None or not 0<=block.bid<len(blocks) or blocks[block.bid] is not block or len(block.insns)!=10 or block.succs or
            not blocks[0].is_entry or blocks[0].preds or len(blocks[0].insns)!=10): return False
    start=blocks[0].insns; out=block.insns
    # A compiler may put the nonreturning null/bounds exits after the
    # epilogue. Only allow entry at the CALL of an exact raise; INT3 pair.
    traps=set()
    for dead in blocks[block.bid+1:]:
        if len(dead.insns)!=2 or dead.succs: return False
        call,trap=dead.insns
        if (call.mnemonic!=M.CALL or call.op0_kind!=K.NEAR_BRANCH64 or trap.mnemonic!=M.INT3 or
                lift._named_raise_throw(call.near_branch_target,lift._call_name(call.near_branch_target)) not in
                ('System.NullReferenceException','System.IndexOutOfRangeException')): return False
        traps.add(call.ip)
    if (start[0].ip!=method.addr or out[-1].ip!=jump.ip or jump.mnemonic!=M.JMP or jump.op0_kind!=K.NEAR_BRANCH64 or
            lift.il.function_extent(method.addr)!=(method.addr,blocks[-1].insns[-1].next_ip) or lift.il.eh_regions(method.addr)):
        return False
    one,two,three,push,sub,cmp,flag,arg,recv,branch=start
    zero,flag2,arg2,recv2,r1,r2,r3,add,pop,_=out
    saved=[i.op1_register for i in (one,two,three)]; pushed=push.op0_register
    if (len(set(saved+[pushed]))!=4 or not set(saved+[pushed])<=set(_NONVOL) or push.mnemonic!=M.PUSH or
            sub.mnemonic!=M.SUB or sub.op0_register!=R.RSP or sub.op1_kind!=K.IMMEDIATE8TO64 or sub.immediate8to64 not in (0x20,0x30) or
            add.mnemonic!=M.ADD or add.op0_register!=R.RSP or add.op1_kind!=K.IMMEDIATE8TO64 or add.immediate8to64!=sub.immediate8to64 or
            pop.mnemonic!=M.POP or pop.op0_register!=pushed): return False
    for spill,reload,reg,off in zip((one,two,three),(r1,r2,r3),saved,(8,16,24)):
        if (spill.mnemonic!=M.MOV or spill.memory_base!=R.RSP or spill.memory_index!=R.NONE or spill.memory_displacement!=off or
                reload.mnemonic!=M.MOV or reload.op0_register!=reg or reload.memory_base!=R.RSP or reload.memory_index!=R.NONE or
                reload.memory_displacement!=off+8+sub.immediate8to64): return False
    if (cmp.mnemonic!=M.CMP or cmp.memory_base!=R.RIP or cmp.memory_size!=1 or cmp.op1_kind!=K.IMMEDIATE8 or cmp.immediate8!=0 or
            branch.mnemonic!=M.JNE or branch.op0_kind!=K.NEAR_BRANCH64 or flag.mnemonic!=M.MOVZX or flag.op1_register!=R.R8L or
            not RegisterExt.is_gpr32(flag.op0_register) or arg.mnemonic!=M.MOV or arg.op1_register!=R.RDX or
            recv.mnemonic!=M.MOV or recv.op1_register!=R.RCX): return False
    parked={recv.op0_register,arg.op0_register,RegisterExt.full_register(flag.op0_register)}
    if len(parked)!=3 or not parked<=set(saved+[pushed]): return False
    if (zero.mnemonic!=M.XOR or zero.op0_register!=zero.op1_register or zero.op0_register!=R.R9D or
            flag2.mnemonic!=M.MOVZX or flag2.op0_register!=R.R8D or not RegisterExt.is_gpr8(flag2.op1_register) or
            flag2.op1_register in (R.AH,R.BH,R.CH,R.DH) or RegisterExt.full_register(flag2.op1_register)!=RegisterExt.full_register(flag.op0_register) or
            arg2.mnemonic!=M.MOV or arg2.op0_register!=R.RDX or arg2.op1_register!=arg.op0_register or
            recv2.mnemonic!=M.MOV or recv2.op0_register!=R.RCX or recv2.op1_register!=recv.op0_register): return False
    seq=[i for b in blocks for i in b.insns]
    if any(a.next_ip!=b.ip for a,b in zip(seq,seq[1:])) or any(i.has_segment_prefix or i.has_lock_prefix or i.has_rep_prefix or i.has_repne_prefix for i in seq): return False
    middle=[i for b in blocks[1:block.bid] for i in b.insns]; ips={i.ip for i in middle}|{zero.ip}
    # Only the start of a boxing sequence is an admissible jump target.
    # This excludes paths into the call with a stale pointer or class.
    borrows=[]; stack_ops=set()
    for k,i in enumerate(middle):
        if i.mnemonic==M.LEA and i.memory_base==R.RSP:
            if k==0 or not _boxed_flag_borrow(lift,middle[k-1:k+3],flag2.op1_register,sub.immediate8to64): return False
            borrows.append((i.ip,middle[k+2].ip));stack_ops.update((i.ip,middle[k+1].ip))
            ips.difference_update(x.ip for x in middle[k:k+3])
    if branch.near_branch_target not in ips: return False
    fac=InstructionInfoFactory(); writes={OpAccess.WRITE,OpAccess.READ_WRITE,OpAccess.COND_WRITE,OpAccess.READ_COND_WRITE}
    for i in middle:
        if i.ip in stack_ops: continue # bounded LEA and one-byte store, no change to a parked register
        if i.flow_control==F.CALL and i.op0_kind==K.NEAR_BRANCH64:
            if method.addr<=i.near_branch_target<seq[-1].next_ip or not lift.il.bin.is_exec_va(i.near_branch_target): return False
            continue  # Win64 direct callees preserve the parked registers and restore RSP.
        if i.flow_control in (F.CONDITIONAL_BRANCH,F.UNCONDITIONAL_BRANCH):
            if i.op0_kind!=K.NEAR_BRANCH64 or i.near_branch_target not in ips and i.near_branch_target not in traps: return False
        elif i.flow_control!=F.NEXT: return False
        # No other intervening stack reference (including LEA) or stack-pointer
        # copy; the saved nonvolatiles/return address remain in their homes.
        for u in fac.info(i).used_registers():
            r=RegisterExt.full_register(u.register)
            if r==R.RSP or (r in parked and u.access in writes): return False
    if boxes is not None: boxes.extend(borrows)
    return True


def _guarded_helper_forward(lift, block, ins):
    """RCX=this and RDX=helper parked across an entry metadata-init diamond.

    Inspect the native blocks, including the cold arm even when its bookkeeping
    was skipped in the lift. A parameter name surviving in the join's register
    map isn't proof that it survived those calls.
    """
    blocks = getattr(lift, '_blocks', ())
    if block is None or len(blocks) < 3:
        return False
    head, cold, joined = blocks[:3]
    # The hot and cold paths may join at `test saved_helper,saved_helper`
    # instead of at the argument setup. Only its non-null fallthrough can
    # execute the base call; leave the conditional itself to the structurer.
    gated = block is not joined
    if gated and (len(blocks) < 4 or block is not blocks[3] or block.preds != [joined.bid] or
                  len(joined.insns) != 2 or len(joined.succs) != 2):
        return False
    if (not head.is_entry or head.preds or not head.insns or head.insns[0].ip != lift._current_method.addr or
            cold.preds != [head.bid] or not joined.preds or not set(joined.preds) <= {head.bid, cold.bid}):
        return False
    join = [i for i in block.insns if i.ip <= ins.ip]
    seq = head.insns + cold.insns + (joined.insns if gated else []) + join
    if (not join or any(a.next_ip != b.ip for a, b in zip(seq, seq[1:])) or any(i.has_segment_prefix for i in seq)):
        return False
    ops = [i for i in join if not _frame_save(i)]
    if len(ops) != 4 or ops[-1].ip != ins.ip:
        return False
    zero, arg, recv, _ = ops
    src, obj = arg.op1_register, recv.op1_register
    if (zero.mnemonic != M.XOR or not zero.op0_register == zero.op1_register == R.R8D or
            arg.mnemonic != M.MOV or arg.op0_register != R.RDX or src not in _NONVOL or
            recv.mnemonic != M.MOV or recv.op0_register != R.RCX or obj not in _NONVOL or obj == src):
        return False
    if gated:
        test, skip = joined.insns
        if (test.mnemonic != M.TEST or test.op0_register != src or test.op1_register != src or
                skip.mnemonic != M.JE or skip.op0_kind != K.NEAR_BRANCH64 or skip.near_branch_target != ins.next_ip or
                block.insns[-1].ip != ins.ip or len(block.succs) != 1 or block.bid in block.succs or
                set(joined.succs) != {block.bid, block.succs[0]}):
            return False
    branch = head.insns[-1]
    if branch.mnemonic != M.JNE or branch.op0_kind != K.NEAR_BRANCH64 or branch.near_branch_target != joined.insns[0].ip:
        return False
    flag = None
    saved = {}
    for i in head.insns[:-1]:
        if (i.mnemonic == M.MOV and i.op0_register in (src, obj) and i.op1_register in (R.RCX, R.RDX)):
            saved[i.op0_register] = i.op1_register
        elif (flag is None and i.mnemonic == M.CMP and i.memory_base == R.RIP and i.memory_size == 1 and
              i.op1_kind == K.IMMEDIATE8 and i.immediate8 == 0):
            flag = i.ip_rel_memory_address
        elif flag is None and (
            i.mnemonic == M.PUSH and i.op0_register in _NONVOL or
            i.mnemonic == M.SUB and i.op0_register == R.RSP and i.op1_kind in (K.IMMEDIATE8TO64, K.IMMEDIATE32TO64) and sdisp(i.immediate(1)) > 0 or
            i.mnemonic == M.MOV and i.memory_base == R.RSP and i.memory_index == R.NONE and
            i.memory_displacement in (8, 16, 24, 32) and i.op1_register in _NONVOL
        ):
            continue
        else:
            return False
    if flag is None or saved != {src:R.RDX, obj:R.RCX}:
        return False
    eh = lift.il.eh_regions(lift._current_method.addr) or {}
    if any(seq[0].ip <= pad <= ins.ip for pad in eh.get('pads', ())):
        return False  # exceptional entry wouldn't inherit the saved arguments
    return _init_arm(cold.insns,lift.rt_init_meta,flag)


def _entry_forward(prefix, ip, ins, inputs, hidden_reg):
    """Straight-line prologue with untouched argument registers and a fresh hidden zero."""
    zero = False
    entry_homes = set()
    for i in prefix:
        if i.ip != ip or i.has_segment_prefix:
            return False
        if i.ip == ins.ip:
            return zero
        ip = i.next_ip
        # Before any stack adjustment, [entry RSP+8..+32] are the four
        # caller-reserved Win64 homes. Parking a nonvolatile qword there
        # changes neither RCX nor the hidden MethodInfo. Only admit leading
        # saves in distinct homes on the nullary path (no stack arguments).
        if (entry_homes is not None and len(inputs) == 1 and i.mnemonic == M.MOV and
                i.op0_kind == K.MEMORY and i.memory_base == R.RSP and i.memory_index == R.NONE and
                i.op1_register in _NONVOL and i.memory_displacement in (8,16,24,32) and
                i.memory_displacement not in entry_homes and not (i.has_lock_prefix or i.has_rep_prefix or i.has_repne_prefix)):
            entry_homes.add(i.memory_displacement)
            continue
        entry_homes = None
        if (i.mnemonic == M.PUSH and i.op0_register in _NONVOL or
                i.mnemonic == M.SUB and i.op0_register == R.RSP and i.op1_kind in (K.IMMEDIATE8TO64, K.IMMEDIATE32TO64) and sdisp(i.immediate(1)) > 0 or
                i.mnemonic == M.MOV and i.op0_register in _NONVOL and i.op1_register in inputs):
            continue
        if i.mnemonic != M.XOR or not i.op0_register == i.op1_register == hidden_reg or zero:
            return False
        zero = True
    return False


def _member(il, addr, owner, param_keys, *, base_mi=None):
    cache = il.__dict__.setdefault('_shared_void_actions', {})
    key = addr, owner, param_keys, base_mi
    if key in cache:
        return cache[key]
    cache[key] = None
    if not _plain_return(il, addr):
        return None
    chain = il.base_chain_tds(owner)
    if not chain or chain[0] != owner or il.meta.typedefs[chain[-1]].parent >= 0:
        return None
    matches = []
    for kind, index in il.addr_candidates.get(addr, ()):
        if kind == 'generic' and 0 <= index < len(il.method_specs):
            mi = il.method_specs[index][0]
        elif kind == 'method':
            mi = index
        else:
            return None
        if not 0 <= mi < len(il.meta.methods):
            return None
        m = il.meta.methods[mi]
        if m.declaring not in chain or m.param_count != len(param_keys) or m.is_static:
            continue
        # Reject competing methods of this arity on the receiver's chain,
        # even if different spellings could also fit the observed registers.
        if (kind != 'method' or matches or m.addr != addr or m.generic_container != -1 or
                (m.declaring != owner if base_mi is None else mi != base_mi)):
            return None
        matches.append(m)
    if len(matches) != 1:
        return None
    m, = matches
    ps = il.meta.method_params(m)
    # Virtual is legal only through a separately proved `base` lookup.
    if (m.flags & 7 != 6 or m.flags & 0x800 or (base_mi is None and m.flags & 0x40) or not re.fullmatch(r'[A-Za-z_]\w*', m.name) or
            il.meta.typedefs[owner].is_valuetype or il.meta.typedefs[owner].generic_container != -1 or
            not 0 <= m.return_type < len(il.types) or il._closed_type_key(il.types[m.return_type]) != (1, 0) or
            len(ps) != len(param_keys) or any(not 0 <= p.type < len(il.types) for p in ps) or
            tuple(il._closed_type_key(il.types[p.type]) for p in ps) != param_keys):
        return None
    cache[key] = ('method', m.index)
    return cache[key]


def shared_base_action(lift, ins, regs, xmm, *, tail_body=None):
    """An override passes its untouched entry arguments to a folded void
    implementation of the immediate base slot. Keep the call at its native
    site; `this.M` would re-dispatch to the override."""
    il = lift.il
    m = getattr(lift, '_current_method', None)
    td = getattr(lift, '_current_td', None)
    b = getattr(getattr(lift, 'out', None), 'block', None)
    if (not isinstance(getattr(il, 'bin', None), PE) or not il.bin.is64 or not m or not td or
            m.is_static or td.is_valuetype or m.slot == 0xffff or not 0 <= m.param_count <= 2 or
            not 0 <= m.return_type < len(il.types) or il._closed_type_key(il.types[m.return_type]) != (1, 0) or
            ins.op0_kind != K.NEAR_BRANCH64 or not 0 <= td.parent < len(il.types) or
            len(regs) != 4):
        return None
    # The R11 tail's stack-copy lanes can reach the join as phi locals.
    # Bare locals have no deferred evaluation. Accept them only with the
    # framed cleanup proof below and the registered return-only base slot.
    if any(e and not e._unk and not (tail_body is not None and len(tail_body)==11 and
           e.kind=='float' and re.fullmatch(r'v\d+',e.text or '')) for e in xmm):
        return None
    guarded = False
    prefix = None
    if tail_body is None:
        if ins.mnemonic != M.CALL or b is None or not b.insns:
            return None
        if getattr(b, 'is_entry', False) and not b.preds:
            prefix = b.insns
        elif m.param_count == 0 and _guarded_this_forward(lift, b, ins):
            guarded = True
        elif m.param_count == 1 and _guarded_helper_forward(lift, b, ins):
            guarded = True
        elif m.param_count == 2 and _guarded_ref_bool_forward(lift,b,ins):
            guarded = True
        else:
            return None
    elif m.param_count==2 and ins.mnemonic==M.JMP and b is not None and tail_body is b.insns and _cleanup_tail_forward(lift,b,ins):
        if m.addr==ins.near_branch_target or ('method',m.index) not in il.addr_candidates.get(m.addr,()): return None
        guarded=True
    else:
        # A frameless, nullary override can transfer straight to the base
        # implementation. Prove the COMPLETE prefix: even a push before
        # the jump would change which return address the leaf consumes.
        if (m.param_count or ins.mnemonic != M.JMP or len(tail_body) != 2 or
                (b is not None and (not getattr(b, 'is_entry', False) or b.preds)) or
                tail_body[0].mnemonic != M.XOR or tail_body[-1].ip != ins.ip or
                tail_body[0].next_ip != ins.ip or m.addr == ins.near_branch_target or
                ('method', m.index) not in il.addr_candidates.get(m.addr, ())):
            return None
        prefix = tail_body
    parent = il.types[td.parent]
    if not parent or il._type_enum(parent) != 0x12 or not 0 <= parent[0] < len(il.meta.typedefs):
        return None
    base = il.vtable_method(parent[0], m.slot)
    if (base is None or not 0 <= base < len(il.meta.methods) or
            not lift._base_slot_matches(base, regs[0], inherited=(m.param_count == 0))):
        return None

    # Inspect a contiguous entry prefix. Stack setup and parking argument
    # registers in callee-saves do not redefine the incoming managed values.
    # Require the hidden zero in the actual Win64 position, not a stale temp.
    inputs = (R.RCX, R.RDX, R.R8)[:1 + m.param_count]
    hidden_reg = (R.EDX, R.R8D, R.R9D)[m.param_count]
    if prefix is not None and not _entry_forward(prefix, m.addr, ins, inputs, hidden_reg):
        return None
    hidden = regs[len(inputs)]
    if (not hidden or hidden._unk or hidden.text != '0' or
            any(e and not e._unk for e in regs[len(inputs)+1:])):
        return None
    params = source_params(il.meta, m)
    if len(params) != m.param_count:
        return None
    names, keys = [], []
    for j,(p,e) in enumerate(zip(params, regs[1:])):
        ty = il.types[p.type] if 0 <= p.type < len(il.types) else None
        name = safe_ident(p.name); spellings = (name,)
        if guarded and m.param_count == 2:
            if not ty or il._type_enum(ty) != (0x12,0x02)[j]: return None
            if j==1: spellings=(name, '((%s & 0xFF/*z*/) & 0xFF/*z*/)' % name)
        if (not ty or ty[1] & (1 << 29) or il._type_enum(ty) not in (0x02, 0x12) or
                not e or e._unk or e.kind != ('int' if il._type_enum(ty) == 2 else 'obj') or
                e.text not in spellings or il._closed_type_key(e.ty) != il._closed_type_key(ty)):
            return None
        names.append(name)
        keys.append(il._closed_type_key(ty))
    target = ins.near_branch_target
    if not keys or (guarded and keys[0][0] == 0x12):
        # Multiple callbacks with the same signature can be indistinguishable. The
        # slot check above proves what `base.M()` calls; prove those exact
        # bytes and the unused result, rather than choosing an original name
        # by counting candidates. In particular, C# cannot call Finalize().
        bm = il.meta.methods[base]
        cands = il.addr_candidates.get(target, ())
        if (len(cands) < 2 or ('method', base) not in cands or bm.addr != target or
                bm.name == 'Finalize' or not re.fullmatch(r'[A-Za-z_]\w*', bm.name) or
                safe_ident(bm.name) != bm.name or not _plain_return(il, target)):
            return None
    elif not _member(il, target, td.index, tuple(keys), base_mi=base):
        return None
    # A terminal jump in a void override has no continuation reading a
    # result. For an ordinary call the original liveness proof still applies.
    if tail_body is None and not _unused_return(lift, ins.next_ip):
        return None
    return 'base.%s(%s) /* shared implementation */' % (il.meta.methods[base].name, ', '.join(names))


def shared_action_tail(lift, ins, body, args, regs):
    if (args == ['this', '0'] and len(body) == 2 or len(args)==4 and args[0]=='this' and args[-1]=='0' and len(body) in (10,11)):
        # Use the actual register file, not only the trimmed tail arguments.
        # In particular, don't hide a surplus expression with side effects.
        full = [dict.get(lift.regs, r) for r in ('RCX', 'RDX', 'R8', 'R9')]
        xmm = [dict.get(lift.regs, r) for r in ('XMM0', 'XMM1', 'XMM2', 'XMM3')]
        base = shared_base_action(lift, ins, full, xmm, tail_body=body)
        if base is not None:
            return base
    return shared_bool_tail(lift, ins, args, regs)


def shared_void_action(lift, ins, regs, xmm):
    il = lift.il
    caller = getattr(lift, '_current_method', None)
    if (not isinstance(getattr(il, 'bin', None), PE) or not il.bin.is64 or not caller or caller.is_static or
            not 0 <= caller.return_type < len(il.types) or il._closed_type_key(il.types[caller.return_type]) != (1, 0) or
            not 0 <= caller.declaring < len(il.meta.typedefs) or il.meta.typedefs[caller.declaring].is_valuetype or
            len(regs) != 4 or any(not e or e._unk for e in regs) or
            any(e and not e._unk for e in xmm)):
        return None
    recv, arg, flag, hidden = regs
    if (recv.kind != 'obj' or arg.kind != 'obj' or not recv.ty or not arg.ty or
            not all(0 <= e.ty[0] < len(il.meta.typedefs) for e in (recv, arg)) or
            il._closed_type_key(recv.ty) != (0x12, recv.ty[0], 0) or il._closed_type_key(arg.ty) != (0x12, arg.ty[0], 0) or
            flag.text not in ('0','1') or hidden.text != '0'):
        return None
    setup = _setup(lift, ins)
    if setup is None:
        return None
    obj, disp, producer, imm = setup
    base = dict.get(lift.regs, reg_name(obj))
    field = (il.instance_field_chain(caller.declaring) or {}).get(disp)
    producers = il.addr_candidates.get(producer, ())
    if (not base or base._unk or base.text != 'this' or not base.ty or base.ty[0] != caller.declaring or
            not field or not 0 <= field[1] < len(il.types) or recv.text != 'this.' + field[0] or
            il._closed_type_key(il.types[field[1]]) != il._closed_type_key(recv.ty) or str(imm) != flag.text or
            len(producers) != 1 or producers[0][0] != 'method' or not 0 <= producers[0][1] < len(il.meta.methods)):
        return None
    getter = il.meta.methods[producers[0][1]]
    if (getter.addr != producer or getter.is_static or getter.flags & 0x40 or getter.param_count or getter.generic_container != -1 or
            getter.declaring not in il.base_chain_tds(caller.declaring) or not getter.name.startswith('get_') or
            arg.text != 'this.' + getter.name[4:] or not 0 <= getter.return_type < len(il.types) or
            il._closed_type_key(il.types[getter.return_type]) != il._closed_type_key(arg.ty)):
        return None
    action = _member(il, ins.near_branch_target, recv.ty[0], ((0x12, arg.ty[0], 0), (2, 0)))
    return action if action and _unused_return(lift, ins.next_ip) else None


def _frame_exit(code):
    """Only stack restores of nonvolatile registers, deallocation and pops.
    In particular no instruction here may change RCX, DL or R8."""
    teardown = False
    for i in code:
        if i.has_segment_prefix:
            return False
        if (not teardown and i.op1_kind == K.MEMORY and i.memory_base == R.RSP and
                i.memory_index == R.NONE and sdisp(i.memory_displacement) >= 0 and
                ((i.mnemonic == M.MOV and i.op0_register in _NONVOL) or
                 (i.mnemonic == M.MOVAPS and R.XMM6 <= i.op0_register <= R.XMM15))):
            continue
        if (not teardown and i.mnemonic == M.ADD and i.op0_register == R.RSP and
                i.op1_kind in (K.IMMEDIATE8TO64, K.IMMEDIATE32TO64) and sdisp(i.immediate(1)) > 0):
            teardown = True
        elif not (teardown and i.mnemonic == M.POP and i.op0_register in _NONVOL):
            return False
    return teardown


def _bool_transfer(lift, tail, ins):
    """Field snapshot -> getter -> implicit bool -> null check -> void tail.
    Only callee-save restores and stack teardown may follow the RCX move."""
    if not 3 <= tail.bid < len(lift._blocks) or len(tail.insns) < 5 or tail.insns[-1].ip != ins.ip:
        return None
    left, cold, conv = lift._blocks[tail.bid-3:tail.bid]
    if (len(left.insns) < 8 or len(cold.insns) != 1 or len(conv.insns) != 5 or cold.preds != [left.bid] or
            not conv.preds or not set(conv.preds) <= {left.bid, cold.bid} or tail.preds != [conv.bid]):
        return None
    seq = left.insns[-8:] + cold.insns + conv.insns + tail.insns
    if any(a.next_ip != b.ip for a,b in zip(seq,seq[1:])) or any(i.has_segment_prefix for i in seq):
        return None
    field, zero, objarg, getter, klass, keep, cmp, jne = left.insns[-8:]
    init, = cold.insns
    clear, first, op, test, null = conv.insns
    hidden, flag, recv = tail.insns[:3]
    origin, saved, value = field.memory_base, field.op0_register, keep.op0_register
    def mov(i, dst, src):
        return i.mnemonic == M.MOV and i.op0_register == dst and i.op1_register == src
    def zeroes(i, reg):
        return i.mnemonic == M.XOR and i.op0_register == i.op1_register == reg
    def call(i):
        return i.mnemonic == M.CALL and i.op0_kind == K.NEAR_BRANCH64
    if (origin not in _NONVOL or saved not in _NONVOL or value not in _NONVOL or saved in (origin,value) or
            field.mnemonic != M.MOV or field.op1_kind != K.MEMORY or field.memory_index != R.NONE or
            not zeroes(zero,R.EDX) or not mov(objarg,R.RCX,origin) or not call(getter) or
            klass.mnemonic != M.MOV or klass.op0_register != R.RCX or klass.memory_base != R.RIP or
            not mov(keep,value,R.RAX) or cmp.mnemonic != M.CMP or cmp.memory_base != R.RCX or
            cmp.memory_index != R.NONE or cmp.memory_displacement != 0xe4 or cmp.op1_kind not in (K.IMMEDIATE8TO32,K.IMMEDIATE32) or
            cmp.immediate(1) != 0 or jne.mnemonic != M.JNE or jne.near_branch_target != clear.ip or
            not call(init) or lift._call_name(init.near_branch_target) != 'il2cpp_runtime_class_init' or
            not zeroes(clear,R.EDX) or not mov(first,R.RCX,value) or not call(op) or
            test.mnemonic != M.TEST or test.op0_register != saved or test.op1_register != saved or
            null.mnemonic != M.JE or null.op0_kind != K.NEAR_BRANCH64 or not _raises_on_null(lift,null) or
            not zeroes(hidden,R.R8D) or flag.mnemonic != M.MOVZX or flag.op0_register != R.EDX or flag.op1_register != R.AL or
            not mov(recv,R.RCX,saved) or ins.mnemonic != M.JMP or ins.op0_kind != K.NEAR_BRANCH64):
        return None
    if _frame_exit(tail.insns[3:-1]):
        return field, getter, klass, op, dict.get(conv.end_state or {}, reg_name(value))
    return None


def _literal_bool_tail(lift, tail, ins, recv, flag):
    if (len(tail.preds) != 1 or not 0 <= tail.preds[0] < len(lift._blocks) or len(tail.insns) < 4 or
            ins.ip != tail.insns[-1].ip or ins.mnemonic != M.JMP or ins.op0_kind != K.NEAR_BRANCH64):
        return None
    pred = lift._blocks[tail.preds[0]]
    if len(pred.insns) < 3:
        return None
    field, test, null = pred.insns[-3:]
    seq = pred.insns[-3:] + tail.insns
    hidden, literal = tail.insns[:2]
    if (any(a.next_ip != b.ip for a,b in zip(seq, seq[1:])) or any(i.has_segment_prefix for i in seq) or
            field.mnemonic != M.MOV or field.op0_register != R.RCX or field.op1_kind != K.MEMORY or
            field.memory_base not in _NONVOL or field.memory_index != R.NONE or
            test.mnemonic != M.TEST or test.op0_register != R.RCX or test.op1_register != R.RCX or
            null.mnemonic != M.JE or null.op0_kind != K.NEAR_BRANCH64 or not _raises_on_null(lift, null) or
            hidden.mnemonic != M.XOR or hidden.op0_register != R.R8D or hidden.op1_register != R.R8D or
            literal.mnemonic != M.MOV or literal.op0_register != R.DL or literal.op1_kind != K.IMMEDIATE8 or
            literal.immediate8 not in (0, 1) or flag.text != str(literal.immediate8) or
            not _frame_exit(tail.insns[2:-1])):
        return None
    # Consult the field base before the epilogue restores it. A type hint on
    # the tail's RCX alone cannot establish which instance supplied the field.
    il = lift.il
    caller_td = lift._current_method.declaring
    base = (pred.end_state or {}).get(reg_name(field.memory_base))
    entry = (il.instance_field_chain(caller_td) or {}).get(sdisp(field.memory_displacement))
    if (not base or base._unk or base.kind != 'obj' or base.text != 'this' or
            il._closed_type_key(base.ty) != (0x12, caller_td, 0) or not entry or
            not 0 <= entry[1] < len(il.types) or il._closed_type_key(il.types[entry[1]]) != il._closed_type_key(recv.ty) or
            recv.text != 'this.' + entry[0]):
        return None
    member = _member(il, ins.near_branch_target, recv.ty[0], ((2,0),))
    if member:
        boolean = 'true' if literal.immediate8 else 'false'
        return '%s.%s(%s) /* shared implementation */' % (recv.text, il.meta.methods[member[1]].name, boolean)
    return None


def shared_bool_tail(lift, ins, args, regs):
    il, caller = lift.il, getattr(lift, '_current_method', None)
    tail = getattr(getattr(lift, 'out', None), 'block', None)
    if (not isinstance(getattr(il,'bin',None), PE) or not il.bin.is64 or not caller or not tail or caller.is_static or
            not 0 <= caller.return_type < len(il.types) or il._closed_type_key(il.types[caller.return_type]) != (1,0) or
            not 0 <= caller.declaring < len(il.meta.typedefs) or il.meta.typedefs[caller.declaring].is_valuetype or
            len(args) != len(regs) or len(args) != 3 or args[2] != '0' or any(not e or e._unk for e in regs)):
        return None
    recv, flag, _ = regs
    if (recv.kind != 'obj' or not recv.ty or not 0 <= recv.ty[0] < len(il.meta.typedefs) or
            il._closed_type_key(recv.ty) != (0x12,recv.ty[0],0) or args != [e.text for e in regs]):
        return None
    if flag.kind == 'int' and flag.text in ('0', '1'):
        return _literal_bool_tail(lift, tail, ins, recv, flag)
    if il._closed_type_key(flag.ty) != (2,0):
        return None
    site = _bool_transfer(lift, tail, ins)
    if not site:
        return None
    field, get, klass, op, value = site
    entry = (il.instance_field_chain(caller.declaring) or {}).get(sdisp(field.memory_displacement))
    if (not entry or not 0 <= entry[1] < len(il.types) or recv.text != args[0] or recv.text != 'this.' + entry[0] or
            il._closed_type_key(il.types[entry[1]]) != il._closed_type_key(recv.ty) or
            not value or value._unk or value.kind != 'obj' or not value.ty or not 0 <= value.ty[0] < len(il.meta.typedefs) or
            il._closed_type_key(value.ty) != (0x12,value.ty[0],0)):
        return None
    def unique(target):
        c = il.addr_candidates.get(target, ())
        return il.meta.methods[c[0][1]] if len(c) == 1 and c[0][0] == 'method' and 0 <= c[0][1] < len(il.meta.methods) else None
    getter, conversion = unique(get.near_branch_target), unique(op.near_branch_target)
    if (not getter or getter.addr != get.near_branch_target or getter.is_static or getter.flags & 0x40 or
            getter.param_count or getter.generic_container != -1 or getter.declaring not in il.base_chain_tds(caller.declaring) or
            not getter.name.startswith('get_') or value.text != 'this.' + getter.name[4:] or
            not 0 <= getter.return_type < len(il.types) or il._closed_type_key(il.types[getter.return_type]) != il._closed_type_key(value.ty)):
        return None
    if (not conversion or conversion.addr != op.near_branch_target or conversion.name != 'op_Implicit' or not conversion.is_static or
            conversion.generic_container != -1 or conversion.flags & 7 != 6 or not conversion.flags & 0x800 or conversion.param_count != 1 or
            not 0 <= conversion.return_type < len(il.types) or il._closed_type_key(il.types[conversion.return_type]) != (2,0)):
        return None
    owner = conversion.declaring
    ps = il.meta.method_params(conversion)
    usage = il.decode_slot(klass.ip_rel_memory_address) or {}
    if (owner not in il.base_chain_tds(value.ty[0]) or len(ps) != 1 or not 0 <= ps[0].type < len(il.types) or
            il._closed_type_key(il.types[ps[0].type]) != (0x12,owner,0) or usage.get('kind') != 1 or
            il._closed_type_key(usage.get('type')) != (0x12,owner,0)):
        return None
    member = _member(il, ins.near_branch_target, recv.ty[0], ((2,0),))
    result = dict.get(lift.regs, 'RAX')
    tn = il.type_name(il.types[ps[0].type])
    if (not member or not result or result._unk or il._closed_type_key(result.ty) != (2,0) or
            result.text != '%s.op_Implicit(%s)' % (tn, value.text) or args[1] != flag.text or
            flag.text != '(%s & 0xFF/*z*/)' % result.text):
        return None
    if not lift.dry:
        # MOVZX derives a masked Expr and doesn't count a use on the call
        # that produced AL. Consume *only that producer's* pending emission;
        # flushing it as well would evaluate the getter and conversion twice.
        pending = getattr(lift, '_pending_calls', [])
        own = [p for p in pending if p[0] is result and p[1] == op.ip]
        if len(own) != 1 or result._uses:
            return None
        pending.remove(own[0])
    return '%s.%s((bool)(%s)%s) /* shared implementation */' % (recv.text, il.meta.methods[member[1]].name, tn, value.text)
