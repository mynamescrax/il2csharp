"""Typed read/modify/write of a particle curve through a biased frame.

Work in post-prologue SP coordinates. Do not give every `s_60` in the method
a new type: only the four non-overlapping live ranges of this copy are proved.
"""
from bisect import bisect_right
import math
import struct
from typing import NamedTuple

from il2cpp.binary import PE
from il2cpp.expr import acc_get
from il2cpp.module_getter import _receiver_use, module_getter
from il2cpp.names import repr_f32
from il2cpp.prelude import HAVE_ICED
from il2cpp.shared_action import _raises_on_null
from il2cpp.sret_copy import _own_field
from il2cpp.text import reg_name, sdisp
from il2cpp.x64 import ARG_REGS, ARG_XMM, VOLATILE

if HAVE_ICED:
    from iced_x86 import (Decoder, FlowControl as F, InstructionInfoFactory, MemorySizeExt,
                          Mnemonic as M, OpAccess, OpKind as K, Register as R, RegisterExt)
    _INFO = InstructionInfoFactory()
    _WRITE = {OpAccess.WRITE, OpAccess.COND_WRITE, OpAccess.READ_WRITE, OpAccess.READ_COND_WRITE}


def _probe_preserves_size(lift, addr):
    """The generic stack-probe fingerprint alone doesn't prove RAX still
    holds the allocation size at the SUB. Check the bounded leaf and its exits."""
    if not lift._is_stack_probe(addr):
        return False
    start,end = lift.il.function_extent(addr)
    if start != addr or not end or not 0 < end-start <= 128:
        return False
    seq = list(Decoder(64,lift.bin.read(addr,end-start) or b'',ip=addr))
    by_ip = {i.ip:i for i in seq}
    work=[(addr,0)]; depths={}; returns=0
    while work:
        ip,depth=work.pop()
        if ip in depths:
            if depth!=depths[ip]:
                return False
            continue
        depths[ip]=depth; i=by_ip.get(ip)
        if i is None or i.is_invalid:
            return False
        if i.mnemonic==M.RET:
            if depth or i.op_count:
                return False
            returns+=1; continue
        if i.mnemonic in (M.SUB,M.ADD) and i.op0_register==R.RSP and i.op1_kind==K.IMMEDIATE8TO64:
            depth += i.immediate(1) * (1 if i.mnemonic==M.SUB else -1)
            if not 0<=depth<=128:
                return False
        elif any(u.access in _WRITE and RegisterExt.full_register(u.register) in (R.RAX,R.RBP,R.RSP,R.RCX)
                 for u in _INFO.info(i).used_registers()):
            return False
        if i.flow_control in (F.CONDITIONAL_BRANCH,F.UNCONDITIONAL_BRANCH) and i.op0_kind==K.NEAR_BRANCH64:
            work.append((i.near_branch_target,depth))
        elif i.flow_control!=F.NEXT:
            return False
        if i.flow_control!=F.UNCONDITIONAL_BRANCH:
            work.append((i.next_ip,depth))
    return returns>0


def probed_frame(lift, m, blocks, pads):
    frame = fixed_frame(lift, m, blocks, pads, immediate=False)
    return frame[:2] if frame else None


def _unwind_matches(il, ui, codes, length, insns):
    """Optional delayed nonvolatile saves may precede the allocation/push
    codes in unwind order. Check every extra code against its instruction."""
    addr = il.bin.image_base + ui
    header = il.bin.read(addr,4) or b''
    if len(header)!=4 or header[0]!=1 or header[3]!=0:
        return False
    raw = il.bin.read(addr+4,2*header[2]) or b''
    if len(raw)!=2*header[2] or not raw.endswith(codes):
        return False
    extra = raw[:len(raw)-len(codes)]
    if not extra:
        return header[1]==length
    if len(extra)%4 or header[1]!=extra[0]:
        return False
    prev=256
    for pos in range(0,len(extra),4):
        end,op=extra[pos:pos+2]; i=insns.get(end)
        if not length<end<prev or i is None or i.memory_base!=R.RSP or i.memory_index!=R.NONE or i.has_segment_prefix:
            return False
        kind=op&15; scale=16 if kind==8 else 8
        if not ((kind==8 and i.mnemonic==M.MOVAPS and R.XMM6<=i.op1_register<=R.XMM15) or
                (kind==4 and i.mnemonic==M.MOV and i.op1_register in (R.RBX,R.RSI,R.RDI,R.RBP,R.R12,R.R13,R.R14,R.R15))):
            return False
        if (i.op0_kind!=K.MEMORY or RegisterExt.number(i.op1_register)!=op>>4 or
                i.memory_displacement!=scale*int.from_bytes(extra[pos+2:pos+4],'little')):
            return False
        prev=end
    return True


def fixed_frame(lift, m, blocks, pads, *, immediate, extended_saves=False):
    """BP bias, allocation size, and entry SP in post-prologue coordinates.
    Validate the push/LEA/allocation against unwind codes and terminal restores."""
    il = lift.il
    if (not HAVE_ICED or not isinstance(getattr(il,'bin',None), PE) or not il.bin.is64 or pads or
            not blocks or blocks[0].preds or not blocks[0].insns or blocks[0].insns[0].ip != m.addr):
        return None
    seq = blocks[0].insns
    j = 0; saves = []
    while j < len(seq) and seq[j].mnemonic == M.PUSH and seq[j].op0_register in (
            R.RBP,R.RBX,R.RDI,R.RSI,R.R12,R.R13,R.R14,R.R15):
        saves.append(seq[j].op0_register); j += 1
    stop = j + (2 if immediate else 4)
    if R.RBP not in saves or len(set(saves)) != j or stop > len(seq):
        return None
    bp, alloc = seq[j], seq[stop-1]
    if (bp.mnemonic != M.LEA or bp.op0_register != R.RBP or bp.memory_base != R.RSP or bp.memory_index != R.NONE or
            bp.has_segment_prefix or alloc.mnemonic != M.SUB or alloc.op0_register != R.RSP):
        return None
    if immediate:
        if alloc.op1_kind not in (K.IMMEDIATE8TO64,K.IMMEDIATE32TO64):
            return None
        size = alloc.immediate(1)
    else:
        imm, probe = seq[j+1:j+3]
        if (imm.mnemonic != M.MOV or imm.op0_register != R.EAX or imm.op1_kind != K.IMMEDIATE32 or
                probe.mnemonic != M.CALL or probe.op0_kind != K.NEAR_BRANCH64 or not _probe_preserves_size(lift,probe.near_branch_target) or
                alloc.op1_register != R.RAX):
            return None
        size = imm.immediate32
    bias = size+sdisp(bp.memory_displacement)
    if not 0 < bias < size <= 0xffff*8 or size % 8 or (size+8*j)%16!=8:
        return None
    rva = m.addr-il.bin.image_base
    n = bisect_right(il._eh4_begins,rva)-1
    if n < 0 or il._eh4_entries[n][0] != rva:
        return None
    length = alloc.next_ip-m.addr
    allocation = (bytes((length, ((size//8-1)<<4)|2)) if size<=128 else bytes((length,1)) + struct.pack('<H',size//8))
    codes = allocation + b''.join(
        bytes((seq[k].next_ip-m.addr, RegisterExt.number(saves[k])<<4)) for k in reversed(range(j)))
    ui=il._eh4_entries[n][2]
    expected = bytes((1,length,len(codes)//2,0))+codes
    if il.bin.read(il.bin.image_base+ui,len(expected)) != expected:
        if not extended_saves or not _unwind_matches(il,ui,codes,length,{
                i.next_ip-m.addr:i for b in blocks for i in b.insns if 0<i.next_ip-m.addr<256}):
            return None
    for b in blocks:
        tail = b.insns[stop:] if b is blocks[0] else b.insns
        for k,i in enumerate(tail):
            if i.flow_control in (F.CALL,F.INDIRECT_CALL,F.RETURN):
                continue
            if any(u.access in _WRITE and RegisterExt.full_register(u.register) in (R.RSP,R.RBP) for u in _INFO.info(i).used_registers()):
                ep = tail[k+1:]
                if (i.mnemonic != M.ADD or i.op0_register != R.RSP or i.op1_kind not in (K.IMMEDIATE8TO64,K.IMMEDIATE32TO64) or
                        i.immediate(1) != size or len(ep) != len(saves)+1 or ep[-1].mnemonic != M.RET or
                        any(x.mnemonic != M.POP or x.op0_register != r for x,r in zip(ep,reversed(saves)))):
                    return None
                break
    return bias,size,size+8*j


def _offset(i, bias):
    if i.has_segment_prefix or i.memory_index != R.NONE or i.memory_base not in (R.RSP,R.RBP):
        return None
    return sdisp(i.memory_displacement) + (bias if i.memory_base == R.RBP else 0)


def _separate(frame, module, output, edit, argument):
    bias, size = frame
    def relative(home):
        return home[1] + (bias if home[0] == R.RBP else 0)
    spans = sorted(((relative(module),8), (relative(output),32), (edit,32), (argument,32)))
    if (spans[0][0] >= 0x20 and spans[-1][0]+spans[-1][1] <= size and
            all(a+n <= z for (a,n),(z,_) in zip(spans,spans[1:]))):
        return spans
    return None


def _copy(seq, bias, echoed=False, literal_ip=None, *, conversion=False):
    """One complete copy of the two sixteen-byte lanes. Keep the LEA
    argument addresses separate from the data transported by the XMMs."""
    regs = {}; writes = {}; refs = {}; zero = value = False
    for i in seq:
        if i.has_segment_prefix or i.memory_index != R.NONE:
            return None
        if i.mnemonic == M.LEA and i.op0_register in (R.RCX,R.RDX) and i.op0_register not in refs:
            off = _offset(i,bias)
            if off is None:
                return None
            refs[i.op0_register] = off
        elif i.mnemonic == M.XOR and i.op0_register == i.op1_register == R.R8D and not zero:
            zero = True
        elif (echoed and R.XMM1 not in regs and not value and
              ((i.mnemonic == M.XORPS and i.op0_register == i.op1_register == R.XMM1) or
               (i.ip == literal_ip and i.mnemonic == M.MOVSS and i.op0_register == R.XMM1 and i.memory_base == R.RIP))):
            value = True
        elif i.mnemonic in (M.MOVAPS,M.MOVUPS) and R.XMM0<=i.op0_register<=R.XMM5 and i.op1_kind == K.MEMORY:
            if i.op0_register in regs or (value and i.op0_register == R.XMM1):
                return None
            off = sdisp(i.memory_displacement) if echoed and i.memory_base==R.RAX else _offset(i,bias) if not echoed else None
            if off is None or (i.mnemonic==M.MOVAPS and (echoed or off%16)):
                return None
            regs[i.op0_register] = off
        elif i.mnemonic in (M.MOVAPS,M.MOVUPS) and i.op0_kind == K.MEMORY and i.op1_register in regs:
            dest = _offset(i,bias)
            if dest is None or dest in writes or (i.mnemonic==M.MOVAPS and dest%16):
                return None
            writes[dest] = regs.pop(i.op1_register)
        else:
            return None
    if regs or len(writes)!=2 or not zero or value != (echoed and not conversion):
        return None
    dest = min(writes); src = writes[dest]
    if writes.get(dest+16) == src+16:
        return src,dest,refs
    return None


def _float_literal(il, ins):
    if ins.memory_base != R.RIP or ins.has_segment_prefix or ins.memory_index != R.NONE:
        return None
    addr = ins.ip_rel_memory_address
    if not any(s.is_data and not s.is_exec and not s.chars & 0x80000000 and
               s.addr <= addr and addr+4 <= s.addr+s.rawsize for s in il.bin.sections):
        return None
    raw = il.bin.read(addr,4)
    if raw and len(raw) == 4:
        value, = struct.unpack('<f',raw)
        if math.isfinite(value):
            return repr_f32(value)
    return None


def _dead_scratch(lift, after, spans, frame, *, method=None, saved_this=None):
    """Bounded void tail, no escaped frame borrows. Follow *both* sides;
    only nonvolatile restorations may read the frame, outside all four homes."""
    method = method or lift._current_method
    if lift.il._closed_type_key(lift.il.types[method.return_type]) != (1,0):
        return False
    bias,size = frame
    by_ip = getattr(lift,'_module_tail_insns',None)
    if by_ip is None:
        by_ip = lift._module_tail_insns = {i.ip:i for b in lift._blocks for i in b.insns}
    # Only low floats in XMM6+ survive the final call. A read of flags or
    # an argument/return register must have a new reaching definition.
    seen = set(); work = [(after, 0xffc0, False, False)]
    while work:
        state = work.pop()
        if state in seen:
            continue
        ip, lanes, flags, null_context = state
        i = by_ip.get(ip)
        if i is None or len(seen)>=96:
            return False
        seen.add(state)
        if i.flow_control == F.RETURN:
            continue
        if i.flow_control in (F.CONDITIONAL_BRANCH,F.UNCONDITIONAL_BRANCH) and i.op0_kind == K.NEAR_BRANCH64:
            if i.flow_control == F.CONDITIONAL_BRANCH and not flags:
                return False
            work.append((i.near_branch_target,lanes,flags,null_context))
            if i.flow_control == F.UNCONDITIONAL_BRANCH:
                continue
        elif i.flow_control == F.CALL and i.op0_kind == K.NEAR_BRANCH64:
            ids=lift.il.addr_candidates.get(i.near_branch_target,())
            if not null_context or len(ids)!=1 or ids[0][0]!='method' or not 0<=ids[0][1]<len(lift.meta.methods):
                return False
            m=lift.meta.methods[ids[0][1]]
            if (m.addr!=i.near_branch_target or not m.is_static or m.param_count or m.generic_container!=-1 or
                    not 0<=m.return_type<len(lift.il.types) or lift.il._closed_type_key(lift.il.types[m.return_type])!=(0x0c,0)):
                return False
            lanes=(lanes & 0xffc0)|1; flags=False; null_context=False
        elif i.mnemonic in (M.MOV,M.MOVAPS) and i.op1_kind==K.MEMORY:
            if saved_this is not None and i.mnemonic == M.MOV and i.op0_register == R.RCX and i.memory_base == saved_this:
                # Heap receiver for an instance call after the curve write.
                # Check all arguments and both exits before resuming the tail
                # walk; neither arm can read the old module/argument slots.
                end = _heap_notification(lift, by_ip, i, method, saved_this, lanes)
                if end is None:
                    return False
                work.append((end,lanes & 0xffc0,False,False)); continue
            off=_offset(i,bias); width=MemorySizeExt.size(i.memory_size)
            if (off is None or i.op0_kind!=K.REGISTER or any(a<off+width and off<a+n for a,n in spans) or
                    i.op0_register not in (R.RBX,R.RDI,R.RSI,R.R12,R.R13,R.R14,R.R15,*range(R.XMM6,R.XMM15+1))):
                return False
        elif i.mnemonic==M.MOVSS and i.memory_base not in (R.RBP,R.RSP) and i.memory_index==R.NONE and not i.has_segment_prefix:
            base=dict.get(lift.regs,reg_name(i.memory_base)) if saved_this is None else None
            if (i.memory_base != saved_this and (not base or base._unk or base.text!='this')) or i.memory_base not in (R.RDI,R.RSI,R.RBX,R.R12,R.R13,R.R14,R.R15):
                return False
            if i.op1_kind==K.MEMORY:
                lanes |= 1 << RegisterExt.number(i.op0_register)
            elif not lanes & (1 << RegisterExt.number(i.op1_register)):
                return False
        elif i.mnemonic==M.ADD and i.op0_register==R.RSP and i.op1_kind==K.IMMEDIATE32TO64 and i.immediate(1)==size:
            pass
        elif i.mnemonic==M.POP and i.op0_register in (R.RBP,R.RBX,R.RDI,R.RSI,R.R12,R.R13,R.R14,R.R15):
            pass
        elif i.mnemonic==M.XOR and i.op0_register==i.op1_register==R.ECX:
            null_context=True; flags=False
        elif saved_this is not None and i.mnemonic == M.MULSS and RegisterExt.is_xmm(i.op0_register) and i.memory_base == R.RIP:
            if not lanes & (1 << RegisterExt.number(i.op0_register)) or _float_literal(lift.il,i) is None:
                return False
        elif i.mnemonic not in (M.MOVAPS,M.COMISS,M.SUBSS) or not RegisterExt.is_xmm(i.op0_register) or not RegisterExt.is_xmm(i.op1_register):
            return False
        else:
            dest,src=1<<RegisterExt.number(i.op0_register),1<<RegisterExt.number(i.op1_register)
            if not lanes&src or (i.mnemonic!=M.MOVAPS and not lanes&dest):
                return False
            if i.mnemonic==M.COMISS:
                flags=True
            else:
                lanes |= dest
        work.append((i.next_ip,lanes,flags,null_context))
    return True


def _heap_notification(lift, by_ip, load, method, saved, lanes):
    """Heap field update followed by a checked instance (string,bool) call.
    This only proves scratch is dead; all these instructions still lift."""
    seq = [load]
    for _ in range(8):
        i = by_ip.get(seq[-1].next_ip)
        if i is None or i.has_segment_prefix:
            return None
        seq.append(i)
    _,add,store,test,null,string,hidden,flag,call = seq
    if (load.has_segment_prefix or load.memory_index != R.NONE or
            add.mnemonic != M.ADDSS or not all(RegisterExt.is_xmm(r) and lanes & (1 << RegisterExt.number(r))
                                              for r in (add.op0_register,add.op1_register)) or
            store.mnemonic != M.MOVSS or store.memory_base != saved or store.memory_index != R.NONE or store.op1_register != add.op0_register or
            test.mnemonic != M.TEST or test.op0_register != test.op1_register or test.op0_register != R.RCX or
            null.mnemonic != M.JE or null.op0_kind != K.NEAR_BRANCH64 or not _raises_on_null(lift,null) or
            string.mnemonic != M.MOV or string.op0_register != R.RDX or string.memory_base != R.RIP or
            (lift.il.decode_slot(string.ip_rel_memory_address) or {}).get('kind') != 5 or
            hidden.mnemonic != M.XOR or hidden.op0_register != R.R9D or hidden.op1_register != R.R9D or
            flag.mnemonic != M.MOV or flag.op0_register != R.R8L or flag.op1_kind != K.IMMEDIATE8 or flag.immediate8 not in (0,1) or
            call.mnemonic != M.CALL or call.op0_kind != K.NEAR_BRANCH64):
        return None
    il = lift.il; td = il.meta.typedefs[method.declaring]
    obj = _own_field(il,td,sdisp(load.memory_displacement),8)
    scalar = _own_field(il,td,sdisp(store.memory_displacement),4)
    ids = il.addr_candidates.get(call.near_branch_target,())
    if not obj or not scalar or il._closed_type_key(scalar[1])!=(0x0c,0) or len(ids)!=1 or ids[0][0]!='method':
        return None
    if not 0<=ids[0][1]<len(il.meta.methods):
        return None
    m=il.meta.methods[ids[0][1]]; ps=il.meta.method_params(m)
    if (m.addr==call.near_branch_target and not m.is_static and m.generic_container==-1 and
            il._closed_type_key(obj[1])==(0x12,m.declaring,0) and len(ps)==m.param_count==2 and
            all(0<=p.type<len(il.types) for p in ps) and [il._closed_type_key(il.types[p.type]) for p in ps]==[(0x0e,0),(2,0)] and
            0<=m.return_type<len(il.types) and il._closed_type_key(il.types[m.return_type])==(1,0)):
        return call.next_ip


def _setter(lift, call, owner, name, param, *, shared=False):
    il = lift.il
    ids = il.addr_candidates.get(call.near_branch_target,())
    if (not shared and len(ids)!=1) or any(k!='method' or not 0<=mi<len(il.meta.methods) for k,mi in ids):
        return False
    matches=[]
    for _,mi in ids:
        m = il.meta.methods[mi]
        if m.declaring!=owner:
            continue
        ps=il.meta.method_params(m)
        if (m.addr!=call.near_branch_target or m.is_static or m.generic_container!=-1 or m.flags&0x40 or m.flags&7!=6 or
                m.param_count!=1 or len(ps)!=1 or not 0<=ps[0].type<len(il.types) or not 0<=m.return_type<len(il.types) or
                il._closed_type_key(il.types[ps[0].type])!=param or
                il._closed_type_key(il.types[m.return_type])!=(1,0) or lift._accessor_prop(mi)!=('set',name,0)):
            return False
        matches.append(mi)
    return len(matches)==1


class _Update(NamedTuple):
    getter: object
    edit: int
    apply: int
    curve_type: tuple
    spans: tuple
    argument: int
    constant: str


def _update_window(lift, b, j, frame):
    """Verify the module spill, both complete copies, and the three curve
    calls in one basic block. Looking ahead must not alter lifter state."""
    return _window(lift,b.insns,j,frame)


def _window(lift, seq, j, frame, edge=None):
    ins=seq[j]; il=lift.il
    if j+22 >= len(seq) or ins.op0_kind!=K.NEAR_BRANCH64 or len(il.addr_candidates.get(ins.near_branch_target,()))<2:
        return None
    use=_receiver_use(seq,j)
    if not use:
        return None
    get,home,refs,clear=use
    if home[0]!=R.RBP or refs.get(R.RDX)!=home or R.RCX not in refs or clear!={'R8'}:
        return None
    k=seq.index(get,j+1); calls=[n for n in range(k+1,min(k+20,len(seq))) if seq[n].mnemonic==M.CALL][:2]
    if len(calls)!=2 or any(seq[n].op0_kind!=K.NEAR_BRANCH64 for n in calls):
        return None
    edit,apply=calls
    if any(a.next_ip!=z.ip and (a.ip,z.ip)!=edge for a,z in zip(seq[k:apply],seq[k+1:apply+1])):
        return None
    bias,_=frame; constant='0f'; literal_ip=None
    literals=[i for i in seq[k+1:edit] if i.mnemonic==M.MOVSS and i.memory_base==R.RIP]
    if literals:
        if len(literals)!=1:
            return None
        literal_ip=literals[0].ip; constant=_float_literal(il,literals[0])
        if constant is None:
            return None
    copy=_copy(seq[k+1:edit],bias,True,literal_ip); send=_copy(seq[edit+1:apply],bias)
    if not copy or not send:
        return None
    zero,work,args=copy; src,arg,ap=send; mod=bias+home[1]
    spans=_separate(frame,home,refs[R.RCX],work,arg)
    if not spans or zero!=0 or src!=work or args!={R.RCX:work} or ap!={R.RCX:mod,R.RDX:arg}:
        return None
    ids=il.addr_candidates.get(get.near_branch_target,())
    if len(ids)!=1 or ids[0][0]!='method' or not 0<=ids[0][1]<len(lift.meta.methods):
        return None
    m=il.meta.methods[ids[0][1]]; rt=il.types[m.return_type] if 0<=m.return_type<len(il.types) else None
    if (m.addr!=get.near_branch_target or m.is_static or m.param_count or m.generic_container!=-1 or
            m.flags&0x40 or m.flags&7!=6 or not rt or il._type_enum(rt)!=0x11 or rt[1] & (1<<29) or not il.returns_sret(rt) or
            il.typedef_full(rt[0])!='UnityEngine.ParticleSystem.MinMaxCurve' or
            il.value_type_size(rt[0])!=32 or lift._accessor_prop(m.index)!=('get','rateOverTime',0) or
            not _setter(lift,seq[apply],m.declaring,'rateOverTime',(0x11,rt[0],0)) or
            not _setter(lift,seq[edit],rt[0],'constant',(0x0c,0),shared=True)):
        return None
    target=seq[edit].near_branch_target
    if il.bin.read(target,6)!=bytes.fromhex('f30f11491c c3'):
        return None
    field=_own_field(il,il.meta.typedefs[rt[0]],0x10+0x1c,4)
    if not field or field[0]!='this.m_ConstantMax' or il._closed_type_key(field[1])!=(0x0c,0):
        return None
    return _Update(get,edit,apply,rt,tuple(spans),arg,constant)


def _chain_spans(first, second):
    """Only the outgoing by-value argument may be reused. _copy() has
    independently proved the complete 16+16 stores in the second update."""
    for a, n in first.spans:
        for b, m in second.spans:
            if a < b+m and b < a+n and not (a == b == first.argument == second.argument and n == m == 32):
                return None
    return sorted(set(first.spans) | set(second.spans))


def _after_pair(lift, block, j, first, frame, recv):
    # The next receiver is loaded from `this` only AFTER the first setter.
    # Its null arm throws without reading the scratch. Its fallthrough must
    # perform a separately verified update before the common void epilogue.
    # This is a liveness check: do not emit or consume the second update here.
    seq = block.insns
    if len(seq) != first.apply+4 or not recv or recv._unk or not recv.ty:
        return False
    setter, load, test, null = seq[first.apply:]
    if (load.mnemonic != M.MOV or load.op0_register != R.RCX or load.op1_kind != K.MEMORY or
            load.memory_base not in (R.RBX,R.RSI,R.RDI,R.R12,R.R13,R.R14,R.R15) or
            load.memory_index != R.NONE or load.has_segment_prefix or
            test.mnemonic != M.TEST or test.op0_register != R.RCX or test.op1_register != R.RCX or
            null.mnemonic != M.JE or null.op0_kind != K.NEAR_BRANCH64 or null.near_branch_target == null.next_ip or
            setter.next_ip != load.ip or load.next_ip != test.ip or test.next_ip != null.ip or
            not _raises_on_null(lift,null)):
        return False
    td = lift._current_td
    base = dict.get(lift.regs,reg_name(load.memory_base))
    if (not base or base._unk or base.text != 'this' or lift.il._closed_type_key(base.ty) != (0x12,td.index,0)):
        return False
    field = _own_field(lift.il,td,sdisp(load.memory_displacement),8)
    if not field or lift.il._closed_type_key(field[1]) != lift.il._closed_type_key(recv.ty):
        return False
    next_block = next((lift._blocks[k] for k in block.succs if 0<=k<len(lift._blocks) and
                       lift._blocks[k].insns and lift._blocks[k].insns[0].ip == null.next_ip), None)
    if not next_block or next_block.preds != [block.bid] or len(next_block.insns)<2:
        return False
    zero, producer = next_block.insns[:2]
    if (zero.mnemonic != M.XOR or zero.op0_register != R.EDX or zero.op1_register != R.EDX or
            zero.next_ip != producer.ip or producer.mnemonic != M.CALL or producer.op0_kind != K.NEAR_BRANCH64 or
            producer.near_branch_target != seq[j].near_branch_target):
        return False
    second = _update_window(lift,next_block,1,frame)
    if not second or second.getter.near_branch_target != first.getter.near_branch_target:
        return False
    spans = _chain_spans(first,second)
    return spans is not None and _dead_scratch(lift,next_block.insns[second.apply].next_ip,spans,frame)


def fold_update(lift, b, j, frame, verified_prefix=None):
    plan = verified_prefix or _update_window(lift,b,j,frame)
    if not plan:
        return None
    seq = b.insns; ins = seq[j]
    if not (verified_prefix or _dead_scratch(lift,seq[plan.apply].next_ip,plan.spans,frame) or
            _after_pair(lift,b,j,plan,frame,dict.get(lift.regs,'RCX'))):
        return None
    member=module_getter(lift,ins,[dict.get(lift.regs,r) for r in ARG_REGS],
                         [dict.get(lift.regs,r) for r in ARG_XMM], biased_frame=frame)
    if not member:
        return None
    emit_update(lift,ins,plan,member,seq[plan.edit],seq[plan.apply])
    return plan.apply


def emit_update(lift, ins, plan, member, edit, apply):
    text,ty=member; module=lift.new_var(); curve=lift.new_var()
    lift._var_types[module]=ty; lift._var_types[curve]=plan.curve_type
    lift.emit(ins.ip,f'var {module} = {text};',None)
    lift.emit(plan.getter.ip,f'var {curve} = {acc_get(module+".rateOverTime")};',None)
    lift.emit(edit.ip,f'{curve}.constant = {plan.constant} /* shared implementation */;',None)
    lift.emit(apply.ip,f'{module}.rateOverTime = {curve};',None)
    for r in (*VOLATILE, *('XMM%d'%n for n in range(6))):
        lift.regs.pop(r,None)
    lift.flags=None; lift._fresh_unknowns()
