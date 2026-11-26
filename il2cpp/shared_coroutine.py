"""Equivalent public coroutine entry after proving the native wrapper's forwarding ABI."""
from il2cpp.binary import PE
from il2cpp.expr import _recv_fold
from il2cpp.sret_copy import _own_field
from il2cpp.prelude import *  # noqa: F401,F403
from il2cpp.text import reg_name, sdisp
from il2cpp.x64 import VOLATILE, _reg_size

_OWNER = 'UnityEngine.MonoBehaviour'
_CHECK = _OWNER + '::IsObjectMonoBehaviour_Injected(System.IntPtr)'
_START = _OWNER + '::StartCoroutineManaged2_Injected(System.IntPtr,System.Collections.IEnumerator)'


def coroutine_null_test(lift,cmp,branch,lhs):
    """A qword comparison with zero tests the managed Coroutine reference,
    without calling an overloaded Unity comparison operator."""
    if (cmp.mnemonic!=Mnemonic.CMP or cmp.next_ip!=branch.ip or branch.mnemonic not in (Mnemonic.JE,Mnemonic.JNE) or
            cmp.op0_kind!=OpKind.MEMORY or cmp.memory_index!=IReg.NONE or cmp.has_segment_prefix or
            MemorySizeExt.size(cmp.memory_size)!=8 or cmp.op1_kind not in (OpKind.IMMEDIATE8TO64,OpKind.IMMEDIATE32TO64) or
            cmp.immediate(1)!=0 or not lhs or not lhs.ty or not lhs.text.startswith('this.')): return None
    il=lift.il; td=lift._current_td; obj=dict.get(lift.regs,reg_name(cmp.memory_base))
    if (not isinstance(getattr(il,'bin',None),PE) or not il.bin.is64 or not obj or obj._unk or obj.text!='this' or
            il._closed_type_key(obj.ty)!=(0x12,td.index,0) or il._type_enum(lhs.ty)!=0x12 or il.type_name(lhs.ty)!='UnityEngine.Coroutine'):
        return None
    row=_own_field(il,td,sdisp(cmp.memory_displacement),8)
    if row and row[0]==lhs.text and il._closed_type_key(row[1])==il._closed_type_key(lhs.ty):
        return lhs.text+(' is null' if branch.mnemonic==Mnemonic.JE else ' is not null')


def _wrapper(lift, va, ptr_offset):
    il = lift.il
    # .pdata describes several fragments for this method. Walk reachable
    # instructions, bounded by the *next registered entry*, not the first
    # unwind fragment or an arbitrary linear scan stopping at the first trap.
    end = il.next_method_start(va)
    if not end or not 0 < end - va <= 1024:
        return False
    ins = {i.ip:i for i in Decoder(64, il.bin.read(va, end-va) or b'', ip=va)}
    incoming = {va: {'RCX':'this', 'RDX':'routine', 'R8':'methodinfo', 'RSP':0}}
    tails = set()
    def send(ip, state):
        if ip not in ins:
            return False
        prev = incoming.get(ip)
        if prev is None:
            incoming[ip] = state.copy()
        else:
            # Incoming MethodInfo must be dead on *every* path before an
            # unknown call can consume R8. Other facts require unanimity.
            merged = {r:v for r,v in state.items() if prev.get(r) == v}
            if 'R8' in prev or 'R8' in state:
                merged['R8'] = 'methodinfo'
            incoming[ip] = merged
        return True
    for ip, i in ins.items():
        state = incoming.pop(ip, None)
        if state is None:
            continue
        mn, a, b = i.mnemonic, i.op0_kind, i.op1_kind
        dst, src = reg_name(i.op0_register), reg_name(i.op1_register)
        sp = state.get('RSP')
        if sp is None or i.has_segment_prefix or i.memory_index != IReg.NONE:
            return False
        zero_r8 = mn == Mnemonic.XOR and i.op0_register == i.op1_register == IReg.R8D
        if not zero_r8 and 'R8' in (dst, src, reg_name(i.memory_base)):
            return False
        if mn == Mnemonic.INT3:
            continue
        if i.flow_control == FlowControl.CONDITIONAL_BRANCH and a == OpKind.NEAR_BRANCH64:
            if i.near_branch_target <= ip or not send(i.near_branch_target, state):
                return False
        elif mn == Mnemonic.JMP:
            if (a != OpKind.REGISTER or state.get(dst) != _START or
                    state.get('RCX') != 'native-this' or state.get('RDX') != 'routine' or sp != 0):
                return False
            tails.add(ip)
            continue
        elif mn == Mnemonic.CALL:
            result = None
            if a == OpKind.REGISTER:
                if state.get(dst) != _CHECK or state.get('RCX') != 'native-this':
                    return False
            elif a == OpKind.NEAR_BRANCH64:
                target = i.near_branch_target
                if va <= target < end:
                    return False
                if target == il.rt_icall_resolve:
                    result = state.get('RCX')
                    if result not in (_START, _CHECK):
                        return False
                else:
                    name = lift._call_name(target)
                    if name not in ('il2cpp_codegen_initialize_runtime_metadata', 'il2cpp_object_new'):
                        # Managed calls on error paths: once R8 is locally
                        # zeroed its contents cannot distinguish the aliases.
                        # The one-parameter static throw helper consumes only
                        # RCX and its own RDX MethodInfo.
                        if 'R8' in state:
                            ids = il.addr_candidates.get(target, ())
                            if (name != 'UnityEngine.Bindings.ThrowHelper.ThrowNullReferenceException' or
                                    len(ids) != 1 or ids[0][0] != 'method'):
                                return False
                            thrower = il.meta.methods[ids[0][1]]
                            if not thrower.is_static or thrower.param_count != 1 or il._type_enum(il.types[thrower.return_type]) != 1:
                                return False
                        if name not in ('System.ArgumentException.ctor', 'System.NullReferenceException.ctor'):
                            nxt = ins.get(i.next_ip)
                            if nxt is None or nxt.mnemonic != Mnemonic.INT3:
                                return False
            else:
                return False
            for r in VOLATILE:
                if r != 'R8':  # a volatile clobber alone is not proof of independence
                    state.pop(r, None)
            if result:
                state['RAX'] = result
        elif mn == Mnemonic.MOV and a == OpKind.REGISTER:
            if dst == 'RSP':
                return False
            fact = None
            if b == OpKind.REGISTER and _reg_size(i.op0_register) == 8:
                fact = state.get(src)
            elif b == OpKind.MEMORY and _reg_size(i.op0_register) == 8:
                base = reg_name(i.memory_base)
                if i.is_ip_rel_memory_operand:
                    fact = il.icall_cells.get(i.ip_rel_memory_address)
                elif state.get(base) == 'this' and i.memory_displacement == ptr_offset:
                    fact = 'native-this'
                elif base != 'RSP' or ('stack', sp+sdisp(i.memory_displacement)) not in state:
                    return False
                else:
                    fact = state['stack', sp+sdisp(i.memory_displacement)]
            else:
                return False
            state.pop(dst, None)
            if fact is not None:
                state[dst] = fact
        elif mn == Mnemonic.MOV and a == OpKind.MEMORY:
            if i.memory_base == IReg.RSP and b == OpKind.REGISTER and _reg_size(i.op1_register) == 8:
                state['stack', sp+sdisp(i.memory_displacement)] = state.get(src, 'saved')
            elif not i.is_ip_rel_memory_operand or not (
                    (b == OpKind.IMMEDIATE8 and i.immediate8 == 1) or
                    (src == 'RAX' and state.get(src) in (_START, _CHECK) and
                     il.icall_cells.get(i.ip_rel_memory_address) == state[src])):
                return False
        elif mn == Mnemonic.LEA and i.op0_register == IReg.RCX and i.is_ip_rel_memory_operand:
            state['RCX'] = il.bin.cstr(i.ip_rel_memory_address, 256) or 'slot'
        elif mn == Mnemonic.PUSH and i.op0_register == IReg.RSI:
            state['RSP'] = sp - 8
        elif mn == Mnemonic.POP and i.op0_register == IReg.RSI:
            state['RSP'] = sp + 8
            state.pop('RSI', None)
        elif mn in (Mnemonic.ADD, Mnemonic.SUB) and i.op0_register == IReg.RSP and b == OpKind.IMMEDIATE8TO64:
            state['RSP'] = sp + (1 if mn == Mnemonic.ADD else -1) * i.immediate8to64
        elif mn == Mnemonic.XOR and i.op0_register == i.op1_register and _reg_size(i.op0_register) == 4:
            state.pop(dst, None)
        elif mn not in (Mnemonic.CMP, Mnemonic.TEST):
            return False
        if not send(i.next_ip, state):
            return False
    return len(tails) == 1 and not incoming


def _proof(lift, va):
    il, meta = lift.il, lift.meta
    cands = il.addr_candidates.get(va, ())
    if len(cands) != 2:
        return None
    methods = [meta.methods[i] for k,i in cands if k == 'method' and 0 <= i < len(meta.methods)]
    if {m.name for m in methods} != {'StartCoroutine', 'StartCoroutine_Auto'}:
        return None
    md, alias = methods
    if (not 0 <= md.declaring < len(meta.typedefs) or not 0 <= md.return_type < len(il.types) or
            md.declaring != alias.declaring or md.return_type != alias.return_type or
            il.typedef_full(md.declaring) != _OWNER):
        return None
    rt = il.types[md.return_type]
    if not rt or rt[1] & (1 << 29) or il.type_name(rt) != 'UnityEngine.Coroutine':
        return None
    param = None
    for m in methods:
        ps = meta.method_params(m)
        if (m.addr != va or m.is_static or m.flags & 0x40 or m.flags & 7 != 6 or
                m.generic_container != -1 or m.param_count != 1 or len(ps) != 1):
            return None
        if not 0 <= ps[0].type < len(il.types):
            return None
        ty = il.types[ps[0].type]
        if (not ty or ty[1] & (1 << 29) or il._type_enum(ty) != 0x12 or
                il.type_name(ty) != 'System.Collections.IEnumerator' or param not in (None, ty[0])):
            return None
        param = ty[0]
    offsets = [off for off,(name,ti) in (il.instance_field_chain(md.declaring) or {}).items()
               if name == 'm_CachedPtr' and il._type_enum(il.types[ti]) == 0x18]
    if len(offsets) == 1 and _wrapper(lift, va, offsets[0]):
        return md.declaring, param
    return None


def shared_coroutine(lift, va, args, values, xmm=None):
    il = lift.il
    if (not isinstance(getattr(il, 'bin', None), PE) or not il.bin.is64 or not va or
            len(args) != 2 or len(values) < 2 or va == getattr(getattr(lift, '_current_method', None), 'addr', None)):
        return None
    cache = il.__dict__.setdefault('_coroutine_aliases', {})
    if va not in cache:
        cache[va] = _proof(lift, va)
    if not cache[va]:
        return None
    owner, iface = cache[va]
    recv, routine = values[:2]
    if any(not e or e._unk or e.kind != 'obj' or not e.ty or e.ty[1] & (1 << 29) or
           il._type_enum(e.ty) != 0x12 or e.text != a for e,a in zip((recv,routine), args)):
        return None
    if any(not 0 <= e.ty[0] < len(il.meta.typedefs) for e in (recv, routine)):
        return None
    chain = il.base_chain_tds(recv.ty[0])
    if owner not in chain:
        return None
    # Do not let a derived class hide or overload the public alias.
    for ti in chain[:chain.index(owner)]:
        if any(il.meta.methods[i].name == 'StartCoroutine' for i in il.meta.type_methods(il.meta.typedefs[ti])):
            return None
    if routine.ty[0] != iface:
        td = il.meta.typedefs[routine.ty[0]]
        if not any(il.td_of_ty(il.types[ii]) == iface for ii in
                   il.meta.interfaces[td.interfaces_start:td.interfaces_start + td.interfaces_count]):
            return None
    if xmm is None:
        xmm = [dict.get(lift.regs, 'XMM%d' % i) for i in range(4)]
    for e in (*values[2:], *xmm):
        if e and not e._unk and not re.fullmatch(r'[A-Za-z_]\w*|0', e.text or ''):
            return None
    return '%s.StartCoroutine(%s) /* shared implementation */' % (_recv_fold(args[0]), args[1])
