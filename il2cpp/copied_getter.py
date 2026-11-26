"""A shared prefix-load getter applied to a by-value struct list element."""
import re

from il2cpp.awaiter import _spec_entry
from il2cpp.binary import PE
from il2cpp.expr import Expr
from il2cpp.module_curve import fixed_frame
from il2cpp.module_getter import _accessor, _receiver_use
from il2cpp.shared_action import _raises_on_null
from il2cpp.prelude import HAVE_ICED
from il2cpp.sret_copy import _own_field
from il2cpp.text import reg_name, sdisp

if HAVE_ICED:
    from iced_x86 import MemorySizeExt, Mnemonic as M, OpKind as K, Register as R, RegisterExt


def _sp_offset(i, bias):
    if i.has_segment_prefix or i.memory_index != R.NONE:
        return None
    if i.memory_base == R.RSP:
        return sdisp(i.memory_displacement)
    if i.memory_base == R.RBP and bias is not None:
        return bias + sdisp(i.memory_displacement)
    return None


def _copied_home(seq, source, size, bias=None):
    """The return slot and the receiver slot are different addresses. Track
    the source offset of every register copy and require exact byte coverage."""
    lanes, stores, refs = {}, {}, {}
    hidden = False
    for i in seq:
        if i.mnemonic == M.XOR and i.op0_register == i.op1_register == R.R8D and not hidden:
            hidden = True
            continue
        off = _sp_offset(i,bias)
        if off is None or off < 0x20:
            return None
        if i.mnemonic == M.LEA and i.op0_register in (R.RCX,R.RDX) and i.op0_register not in refs:
            refs[i.op0_register] = off
            continue
        if i.mnemonic not in (M.MOVUPS,M.MOVAPS,M.MOVSD):
            return None
        width = MemorySizeExt.size(i.memory_size)
        if i.mnemonic == M.MOVAPS and off % 16:
            return None
        if i.op1_kind == K.MEMORY and R.XMM0 <= i.op0_register <= R.XMM5 and i.op0_register not in lanes:
            lanes[i.op0_register] = off-source,width
        elif i.op0_kind == K.MEMORY and i.op1_register in lanes and off not in stores:
            delta,n = lanes.pop(i.op1_register)
            if n != width:
                return None
            stores[off] = delta,n
        else:
            return None
    if lanes or set(refs) != {R.RCX,R.RDX} or not hidden:
        return None
    dest, result = refs[R.RDX], refs[R.RCX]
    copied = 0
    for off,(delta,n) in sorted(stores.items()):
        if off != dest+copied or delta != copied:
            return None
        copied += n
    regions = sorted(((source,size),(dest,size),(result,12)))
    if copied == size and all(a+n <= b for (a,n),(b,_) in zip(regions,regions[1:])):
        return dest,result


def _element_snapshot(lift, seq, p, echo, bias=None):
    il = lift.il
    if p < 4 or il.meta.version != 31:
        return None
    slot,home,index,recv,call = seq[p-4:p+1]
    if (slot.mnemonic != M.MOV or slot.op0_register != R.R9 or slot.memory_base != R.RIP or slot.has_segment_prefix or
            home.mnemonic != M.LEA or home.op0_register != R.RCX or
            index.mnemonic != M.MOV or index.op0_register != R.R8D or not RegisterExt.is_gpr32(index.op1_register) or
            recv.mnemonic != M.MOV or recv.op0_register != R.RDX or recv.op1_register not in (R.RBX,R.RBP,R.RSI,R.RDI,R.R12,R.R13,R.R14,R.R15) or
            call.mnemonic != M.CALL or call.op0_kind != K.NEAR_BRANCH64):
        return None
    off = _sp_offset(home,bias)
    if (off is None or off < 0x20 or echo.kind != 'ptr' or not re.fullmatch(r'&t\d+',echo.text) or lift.slot_types.get(echo.text[1:]) != echo.ty or
            getattr(echo,'_stack_offset',None) != lift.rsp_delta+off):
        return None
    usage = il.decode_slot(slot.ip_rel_memory_address) or {}
    si = usage.get('idx',-1)
    if usage.get('kind') != 6 or not 0 <= si < len(il.method_specs):
        return None
    mi,ci,gi = il.method_specs[si]
    if not 0 <= mi < len(il.meta.methods) or gi != -1 or ci < 0:
        return None
    m = il.meta.methods[mi]; ps = il.meta.method_params(m)
    args = il._method_spec_type_args(ci); obj = dict.get(lift.regs,reg_name(recv.op1_register))
    if (not obj or obj._unk or obj.kind != 'obj' or not args or len(args) != 1 or
            not echo.ty or il._type_enum(echo.ty) != 0x11 or il._closed_type_key(echo.ty) != (0x11,echo.ty[0],0) or
            il._closed_type_key(args[0]) != il._closed_type_key(echo.ty) or
            il._closed_type_key(obj.ty) != (0x15,(0x12,m.declaring,0),(il._closed_type_key(echo.ty),),0) or
            il.typedef_full(m.declaring) != 'System.Collections.Generic.List`1' or m.name != 'get_Item' or m.is_static or
            m.param_count != 1 or len(ps) != 1 or not 0 <= ps[0].type < len(il.types) or il._closed_type_key(il.types[ps[0].type]) != (8,0) or
            il.candidate_return_type(('generic',si)) != echo.ty or not il.returns_sret(echo.ty) or
            _spec_entry(il,si,mi) != call.near_branch_target):
        return None
    return off


def _snapshot_copy(lift, seq, p, j, echo):
    il=lift.il
    if p < 4 or any(x.next_ip != y.ip for x,y in zip(seq[p-4:j],seq[p-3:j+1])):
        return None
    bias=None; limit=-lift.rsp_delta
    if any(i.memory_base==R.RBP for i in seq[p-4:j]):
        # Both sets of LEAs and every tile of the transfer must name the
        # same bytes in physical SP coordinates, not s_abs(displacement).
        if not hasattr(lift,'_copied_frame'):
            lift._copied_frame=fixed_frame(lift,lift._current_method,lift._blocks,lift._ref_array_pads,
                                           immediate=True,extended_saves=True)
        frame=lift._copied_frame
        if not frame:
            return None
        bias,limit,entry_sp=frame
        if -lift.rsp_delta!=entry_sp or getattr(dict.get(lift.regs,'RBP'),'_stack_offset',None)!=bias-entry_sp:
            return None
    source = _element_snapshot(lift,seq,p,echo,bias)
    if source is None or not 0 <= echo.ty[0] < len(il.meta.typedefs):
        return None
    owner = il.meta.typedefs[echo.ty[0]]; size = il.value_type_size(owner.index)
    if not size or size < 12 or size > 128 or not owner.is_valuetype or owner.generic_container != -1:
        return None
    homes = _copied_home(seq[p+1:j],source,size,bias)
    if not homes:
        return None
    dest,result = homes
    if max(source+size,dest+size,result+12)>limit:
        return None
    return owner,source,dest,result,bias


def mixed_copy_stores(lift, seq, first):
    """Reassemble stores to a single mixed-frame receiver. Emit a whole
    value assignment when the final tile arrives; no call/observer can see
    an intermediate copy. Keep native register loads and LEAs in place."""
    last=getattr(lift,'_last_sret',None)
    if not last or first<1 or seq[first-1].ip!=last[0] or dict.get(lift.regs,'RAX') is not last[1]:
        return {}
    j=next((k for k in range(first,min(first+16,len(seq))) if seq[k].mnemonic==M.CALL),None)
    if (j is None or seq[j].op0_kind!=K.NEAR_BRANCH64 or not _copies_prefix(lift.il,seq[j].near_branch_target) or
            not any(i.memory_base==R.RBP for i in seq[first:j])):
        return {}
    proof=_snapshot_copy(lift,seq,first-1,j,last[1])
    if not proof:
        return {}
    owner,source,dest,result,bias=proof
    if bias is None or not _prefix_getter(lift,seq[j].near_branch_target,owner,last[1].text[1:]):
        return {}
    stores=[i for i in seq[first:j] if i.op0_kind==K.MEMORY]
    name=lift.slot_var(dest); ty=last[1].ty
    old=lift.slot_types.get(name)
    if (not re.fullmatch(r's_[0-9a-fA-F]+',name) or old and lift.il._closed_type_key(old)!=lift.il._closed_type_key(ty)):
        return {}
    return {i.ip:(i is stores[-1],dest,name,last[1]) for i in stores}


def write_snapshot(lift,ins,store):
    final,dest,name,echo=store
    if final:
        lift._kill_stale(name)
        value=Expr(echo.text[1:],echo.ty,'obj')
        lift.emit(ins.ip,f'{name} = {value.text};',None)
        # This is the value of this store, not a permanent declared type for
        # a native slot that may be reused on another path. Invalidate old
        # subdivision snapshots just as the individual stores would.
        start=lift.rsp_delta+dest; size=lift.il.value_type_size(echo.ty[0])
        for address,slot in lift.stack_map.items():
            if start<=address<start+size:
                lift.stack_values.pop(slot,None)
        lift._stack_store(start,size,value)
        lift.stack_values[name]=value


def copied_struct_getter(lift, ins, regs):
    """Return (public getter MethodDef, receiver value) only when the bytes
    reaching native RDX are the complete registered indexer result. Win64
    RCX is the destination for the 12-byte return, not the receiver."""
    il = lift.il
    if (not HAVE_ICED or not isinstance(getattr(il,'bin',None),PE) or not il.bin.is64 or
            ins.op0_kind != K.NEAR_BRANCH64 or len(regs)<3 or not _copies_prefix(il,ins.near_branch_target)):
        return None
    b = getattr(getattr(lift,'out',None),'block',None); last = getattr(lift,'_last_sret',None)
    if not b or not last or dict.get(lift.regs,'RAX') is not last[1]:
        return None
    seq=b.insns; echo=last[1]
    j=next((k for k,i in enumerate(seq) if i.ip==ins.ip),-1)
    p=next((k for k in range(max(0,j-16),j) if seq[k].ip==last[0]),-1)
    proof=_snapshot_copy(lift,seq,p,j,echo)
    if not proof:
        return None
    owner,_,dest,result,_=proof
    if (any(not r or r.kind!='ptr' or getattr(r,'_stack_offset',None)!=lift.rsp_delta+n for r,n in zip(regs,(result,dest))) or
            not regs[2] or regs[2]._unk or regs[2].text!='0'):
        return None
    return _prefix_getter(lift,ins.near_branch_target,owner,echo.text[1:])


def _copies_prefix(il,target):
    return il.bin.is_exec_va(target) and il.bin.read(target,18) == bytes.fromhex('f20f1002 8b4208 f20f1101 894108 488bc1 c3')


def _prefix_getter(lift,target,owner,receiver):
    il = lift.il
    field = _own_field(il,owner,0x10,12)
    if not field or il._type_enum(field[1])!=0x11:
        return None
    matches=[]
    for kind,mi in il.addr_candidates.get(target,()):
        if kind!='method' or not 0<=mi<len(il.meta.methods):
            return None
        m=il.meta.methods[mi]
        if m.declaring!=owner.index:
            continue
        if (m.addr!=target or m.is_static or m.generic_container!=-1 or m.flags&7!=6 or m.flags&0x40 or m.param_count or
                not 0<=m.return_type<len(il.types)):
            return None
        rt=il.types[m.return_type]; prop=lift._accessor_prop(mi)
        if (not prop or prop[0]!='get' or prop[2] or il._closed_type_key(rt)!=(0x11,field[1][0],0) or
                not il.returns_sret(rt) or il.value_type_size(rt[0])!=12):
            return None
        matches.append((mi,receiver+'.'+prop[1]))
    return matches[0] if len(matches)==1 else None


def array_fill_sites(lift, blocks, pads, method=None):
    """One allocation followed by one fill before a loop. Both results
    are saved in nonvolatile registers; they must not be re-evaluated by
    a loop phi. Consider only a straight entry prefix with no back edge."""
    allocs, counts = set(), {}
    il = lift.il
    if (not HAVE_ICED or pads or not blocks or not getattr(lift,'_array_allocation_loop_guard',False) or not isinstance(getattr(il,'bin',None),PE) or
            not il.bin.is64 or blocks[0].preds or not getattr(lift,'rt_arrnew',None)):
        return allocs, counts
    reached = set(); cur = 0
    # Unreachable metadata-init arms can still occur in preds. Never use a
    # dry state's lack of a back edge as proof that execution is unique.
    todo = [0]
    while todo:
        k = todo.pop()
        if 0<=k<len(blocks) and k not in reached:
            reached.add(k); todo.extend(blocks[k].succs)
    seen=set(); candidates=[]
    while cur not in seen:
        seen.add(cur); b=blocks[cur]
        if len(b.succs)!=1 or b.succs[0] not in reached:
            break
        nxt=b.succs[0]; use=blocks[nxt]
        if (set(use.preds)&reached)!={cur} or nxt in seen:
            break
        cur=nxt; candidates.append((b,use,False))
    # A size getter and allocation can also be reached through a conditional
    # before a loop. The fill block must be dominated by this allocation,
    # with no path from the fill back to the allocation on a later iteration.
    for bid in sorted(reached-seen):
        b=blocks[bid]
        if len(b.succs)==1 and len(b.insns)>=13 and b.insns[-8].mnemonic==M.CALL:
            use=blocks[b.succs[0]]
            if use.preds==[bid]: candidates.append((b,use,True))
    for b,use,branched in candidates:
        seq=b.insns
        if len(seq)<7 or len(use.insns)<6:
            continue
        klass,dim,alloc,recv,save,test,null=seq[-7:]
        zero,arg,fill=use.insns[:3]
        if (alloc.mnemonic!=M.CALL or alloc.op0_kind!=K.NEAR_BRANCH64 or alloc.near_branch_target not in lift.rt_arrnew or
                klass.mnemonic!=M.MOV or klass.op0_register!=R.RCX or klass.memory_base!=R.RIP or klass.has_segment_prefix or
                dim.mnemonic!=M.MOV or dim.op0_register!=R.EDX or dim.op1_register!=R.EAX or
                recv.mnemonic!=M.MOV or recv.op0_register!=R.RCX or recv.op1_kind!=K.MEMORY or recv.memory_index!=R.NONE or
                save.mnemonic!=M.MOV or save.op1_register!=R.RAX or save.op0_register not in (R.RBX,R.RBP,R.RSI,R.RDI,R.R12,R.R13,R.R14,R.R15) or
                test.mnemonic!=M.TEST or test.op0_register!=test.op1_register or test.op0_register!=R.RCX or
                null.mnemonic!=M.JE or null.near_branch_target==zero.ip or zero.mnemonic!=M.XOR or zero.op0_register!=R.R8D or zero.op1_register!=R.R8D or
                arg.mnemonic!=M.MOV or arg.op0_register!=R.RDX or arg.op1_register not in (R.RAX,save.op0_register) or
                fill.mnemonic!=M.CALL or fill.op0_kind!=K.NEAR_BRANCH64 or
                any(x.next_ip!=y.ip for x,y in zip(seq[-7:]+use.insns[:2],seq[-6:]+use.insns[:3]))):
            continue
        ids=il.addr_candidates.get(fill.near_branch_target,()); slot=il.decode_slot(klass.ip_rel_memory_address) or {}
        if len(ids)!=1 or ids[0][0]!='method' or not 0<=ids[0][1]<len(il.meta.methods) or slot.get('kind')!=1:
            continue
        mi=ids[0][1]; m=il.meta.methods[mi]; ps=il.meta.method_params(m); ty=slot.get('type')
        if (not ty or il._type_enum(ty)!=0x1d or ty[1]&(1<<29) or not il._closed_type_key(ty) or m.addr!=fill.near_branch_target or
                m.is_static or m.generic_container!=-1 or m.flags&0x40 or m.param_count!=1 or len(ps)!=1 or
                not 0<=ps[0].type<len(il.types) or il._closed_type_key(il.types[ps[0].type])!=il._closed_type_key(ty) or
                not 0<=m.return_type<len(il.types) or il._closed_type_key(il.types[m.return_type])!=(8,0)):
            continue
        biased=None
        if method is not None and len(seq)>=13 and m.name=='GetParticles' and il.typedef_full(m.declaring)=='UnityEngine.ParticleSystem':
            j=len(seq)-12; wrapper=seq[j]; read=_receiver_use(seq,j)
            if (wrapper.mnemonic==M.CALL and wrapper.op0_kind==K.NEAR_BRANCH64 and read and read[0].ip==seq[-8].ip and
                    read[1][0]==R.RBP and read[2]=={R.RCX:read[1]} and read[3]=={'RDX'} and _raises_on_null(lift,null)):
                ids=il.addr_candidates.get(read[0].near_branch_target,())
                if len(ids)==1 and ids[0][0]=='method':
                    cap=il.meta.methods[ids[0][1]]
                    if (lift._accessor_prop(cap.index)==('get','maxParticles',0) and
                            il._closed_type_key(il.types[cap.return_type])==(8,0) and
                            _accessor(lift,wrapper.near_branch_target,m.declaring,cap.declaring)):
                        frame=fixed_frame(lift,method,blocks,pads,immediate=True,extended_saves=True)
                        if frame:
                            bias,size,entry=frame; off=bias+read[1][1]
                            if (0x20<=off<=size-8 or off-entry in (8,16,24,32)) and off%8==0:
                                biased=wrapper.ip,frame
        if branched:
            if not biased: continue
            visited=set(); todo=[use.bid]
            while todo:
                n=todo.pop()
                if n in visited: continue
                visited.add(n); todo.extend(blocks[n].succs)
            if b.bid in visited: continue
        # The filled array and count have distinct surviving homes. The
        # compiler may clear a separate register before saving the count.
        for x in use.insns[3:6]:
            nonvol=(R.RBX,R.RBP,R.RSI,R.RDI,R.R12,R.R13,R.R14,R.R15)
            if (not RegisterExt.is_gpr32(x.op0_register) or RegisterExt.full_register(x.op0_register) not in nonvol or
                    RegisterExt.full_register(x.op0_register) == save.op0_register):
                break
            if x.mnemonic == M.MOV and x.op1_register == R.EAX:
                allocs.add(alloc.ip); counts[fill.ip]=mi
                if biased: lift._array_module_frames[biased[0]]=biased[1]
                break
            if x.mnemonic != M.XOR or x.op0_register != x.op1_register:
                break
    return allocs, counts
