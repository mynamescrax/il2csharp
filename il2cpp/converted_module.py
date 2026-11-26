"""A one-reference module saved across an intervening scalar-to-curve conversion."""
from typing import NamedTuple

from il2cpp.module_curve import _copy, _float_literal, _offset, _setter
from il2cpp.module_getter import _wraps_rcx
from il2cpp.prelude import HAVE_ICED
from il2cpp.runtime.meta import IMM_OPS
from il2cpp.text import sdisp

if HAVE_ICED:
    from iced_x86 import Decoder, MemorySizeExt, Mnemonic as M, OpKind as K, Register as R


class Conversion(NamedTuple):
    module: int             # consuming instance setter's declaring type
    conversion: int          # IP of the unique conversion MethodDef call
    setter: int              # IP of final consumer
    curve_type: tuple
    value: str
    homes: tuple             # (receiver, sret, by-value argument), relative to entry SP


def _writes_only_result(seq, barriers):
    """Prove the intervening conversion writes only its private scratch or
    its full sret buffer, and echoes that buffer in RAX. The actual scalar
    computation and write barriers are preserved by invoking the operator."""
    if len(seq)<8 or seq[0].mnemonic!=M.PUSH or seq[0].op0_register!=R.RBX:
        return False
    sub = seq[1]; add,pop,ret = seq[-3:]
    if (sub.mnemonic!=M.SUB or sub.op0_register!=R.RSP or sub.op1_kind not in IMM_OPS or
            add.mnemonic!=M.ADD or add.op0_register!=R.RSP or add.op1_kind not in IMM_OPS or
            add.immediate(1)!=sub.immediate(1) or pop.mnemonic!=M.POP or pop.op0_register!=R.RBX or
            ret.mnemonic!=M.RET or ret.op_count):
        return False
    size = sub.immediate(1)
    if not 32<=size<=512 or size%16:
        return False
    rcx, saved, echo, null = 'out',False,False,False
    written = 0
    for i in seq[2:-3]:
        if i.has_segment_prefix or i.memory_index!=R.NONE:
            return False
        if i.mnemonic==M.LEA and i.op0_register==R.RCX and i.memory_base==R.RSP:
            rcx = sdisp(i.memory_displacement)
        elif i.mnemonic==M.MOV and i.op0_register==R.RBX and i.op1_register==R.RCX:
            saved = rcx=='out'
        elif i.mnemonic==M.MOV and i.op0_register==R.RAX and i.op1_register==R.RBX:
            echo = saved
        elif i.mnemonic==M.XOR and i.op0_register==i.op1_register==R.EDX:
            null = True
        elif i.mnemonic==M.CALL and i.op0_kind==K.NEAR_BRANCH64:
            if i.near_branch_target not in barriers or not isinstance(rcx,int) or not 0x20<=rcx<=size-8 or not null:
                return False
            rcx,echo,null = None,False,False
        elif i.mnemonic in (M.MOVAPS,M.MOVUPS,M.MOVDQU,M.MOVSS,M.XORPS,M.SHUFPS) or (
                i.mnemonic==M.MOV and i.op0_kind==K.MEMORY and i.op1_kind in IMM_OPS):
            if i.memory_base==R.NONE:
                if not (R.XMM0<=i.op0_register<=R.XMM15 and R.XMM0<=i.op1_register<=R.XMM15):
                    return False
                continue
            off=sdisp(i.memory_displacement); width=MemorySizeExt.size(i.memory_size)
            if width<=0:
                return False
            if i.memory_base==R.RSP and 0x20<=off and off+width<=size:
                continue
            if ((i.memory_base==R.RBX and saved or i.memory_base==R.RCX and rcx=='out') and
                    i.op0_kind==K.MEMORY and 0<=off and off+width<=32):
                written |= ((1<<width)-1)<<off
                continue
            return False
        else:
            return False
    return echo and written==0xffffffff


def _implicit(lift, target):
    il = lift.il
    ids = il.addr_candidates.get(target, ())
    if len(ids) != 1 or ids[0][0] != 'method' or not 0 <= ids[0][1] < len(il.meta.methods):
        return None
    m = il.meta.methods[ids[0][1]]
    if (m.addr != target or m.name != 'op_Implicit' or not m.is_static or m.flags & 7 != 6 or not m.flags & 0x800 or
            m.generic_container != -1 or m.param_count != 1 or not 0 <= m.declaring < len(il.meta.typedefs) or
            not 0 <= m.return_type < len(il.types) or il.typedef_full(m.declaring) != 'UnityEngine.ParticleSystem.MinMaxCurve'):
        return None
    rt = il.types[m.return_type]; ps = il.meta.method_params(m)
    if (il._closed_type_key(rt) != (0x11,m.declaring,0) or not il.returns_sret(rt) or
            il.value_type_size(m.declaring) != 32 or len(ps) != 1 or not 0 <= ps[0].type < len(il.types) or
            il._closed_type_key(il.types[ps[0].type]) != (0x0c,0)):
        return None
    # T t = f is only unambiguous if there is one implicit float -> T.
    for mi in il.meta.type_methods(il.meta.typedefs[m.declaring]):
        other = il.meta.methods[mi]
        if mi != m.index and other.name in ('op_Implicit','op_Explicit') and other.param_count == 1:
            args = il.meta.method_params(other)
            if len(args) != 1 or not 0 <= args[0].type < len(il.types) or il._closed_type_key(il.types[args[0].type]) == (0x0c,0):
                return None
    lo,hi = il.function_extent(target)
    if lo==target and hi and 0<hi-lo<=256 and il.bin.is_exec_va(lo):
        code=il.bin.read(lo,hi-lo) or b''
        if len(code)==hi-lo and _writes_only_result(list(Decoder(64,code,ip=lo)),lift.rt_wbarrier):
            return rt
    return None


def _setup(il, seq, bias):
    module = buf = literal = None
    hidden = False
    for i in seq:
        if i.has_segment_prefix or i.memory_index != R.NONE:
            return None
        if module is None and i.mnemonic == M.MOV and i.op0_kind == K.MEMORY and i.op1_register == R.RAX:
            module = _offset(i,bias)
            if module is None:
                return None
        elif buf is None and i.mnemonic == M.LEA and i.op0_register == R.RCX:
            buf = _offset(i,bias)
            if buf is None:
                return None
        elif not hidden and i.mnemonic == M.XOR and i.op0_register == i.op1_register == R.R8D:
            hidden = True
        elif literal is None and i.mnemonic == M.XORPS and i.op0_register == i.op1_register == R.XMM1:
            literal = '0f'
        elif literal is None and i.mnemonic == M.MOVSS and i.op0_register == R.XMM1:
            literal = _float_literal(il,i)
            if literal is None:
                return None
        elif i.mnemonic == M.XORPS and i.op0_register == i.op1_register and R.XMM6 <= i.op0_register <= R.XMM15:
            continue  # normal instruction handler still executes this nonvolatile write
        else:
            return None
    if None not in (module,buf,literal) and hidden:
        return module,buf,literal


def _distinct(module,buf,arg,size,entry_sp):
    # A qword can also be spilled in one of the *caller's incoming* home
    # slots. Never accept saved registers, the return address or the next
    # call's own shadow space as the module home.
    if not (0x20 <= module <= size-8 or entry_sp+8 <= module <= entry_sp+32 and (module-entry_sp)%8 == 0):
        return False
    spans = sorted(((module,8),(buf,32),(arg,32)))
    return all(0x20 <= a <= size-32 for a in (buf,arg)) and all(a+n<=b for (a,n),(b,_) in zip(spans,spans[1:]))


def conversion_uses(lift, blocks, frame):
    plans = {}
    if not frame or not HAVE_ICED:
        return plans
    il = lift.il; bias,size,entry_sp = frame
    for b in blocks:
        seq = b.insns
        for j,ins in enumerate(seq):
            if (ins.mnemonic != M.CALL or ins.op0_kind != K.NEAR_BRANCH64 or len(il.addr_candidates.get(ins.near_branch_target,()))<2
                    or not _wraps_rcx(lift,ins.near_branch_target)):
                continue
            calls = [k for k in range(j+1,min(j+17,len(seq))) if seq[k].mnemonic == M.CALL][:2]
            if len(calls)!=2 or any(seq[k].op0_kind!=K.NEAR_BRANCH64 for k in calls):
                continue
            conv,end = calls
            if any(a.next_ip!=c.ip for a,c in zip(seq[j:end],seq[j+1:end+1])):
                continue
            rt = _implicit(lift,seq[conv].near_branch_target)
            if not rt:
                continue
            setup = _setup(il,seq[j+1:conv],bias)
            copy = _copy(seq[conv+1:end],bias,echoed=True,conversion=True)
            if not setup or not copy:
                continue
            module,buf,literal = setup; src,arg,refs = copy
            if src!=0 or refs!={R.RCX:module,R.RDX:arg} or not _distinct(module,buf,arg,size,entry_sp):
                continue
            ids = il.addr_candidates.get(seq[end].near_branch_target,())
            if len(ids)!=1 or ids[0][0]!='method' or not 0<=ids[0][1]<len(il.meta.methods):
                continue
            owner = il.meta.methods[ids[0][1]].declaring
            if _setter(lift,seq[end],owner,'rateOverTime',il._closed_type_key(rt)):
                plans[ins.ip] = Conversion(owner,seq[conv].ip,seq[end].ip,rt,literal,
                                          (module-entry_sp,buf-entry_sp,arg-entry_sp))
    return plans
