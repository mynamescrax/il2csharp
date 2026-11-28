"""Bind the scalar calls which fill a homogeneous sret, in producer order.

The frame and the low float lanes form a short straight-line dataflow:
XMM1/XMM2 are the entry arguments after hidden RCX; each CALL produces
one new XMM0 value. Equal callee/argument spellings do not identify it.
"""
from bisect import bisect_left

from il2cpp.array_origin import _graph
from il2cpp.equivalent_binary import _amd64
from il2cpp.metadata import source_params
from il2cpp.names import safe_ident
from il2cpp.packed_projection import _field
from il2cpp.prelude import HAVE_ICED
from il2cpp.stack_local_frame import _saves,_slot_move
from il2cpp.text import sdisp

if HAVE_ICED:
    from iced_x86 import Mnemonic as M, OpKind as K, Register as R, RegisterExt as RX


def sampled_returns(lift,method,td,blocks,pads):
    if (not HAVE_ICED or pads or len(blocks)!=1 or method.param_count!=2 or not method.is_static or
            method.generic_container!=-1 or td.generic_container!=-1):return {}
    seq=blocks[0].insns;il=lift.il
    if not (8<=len(seq)<=96 and seq[0].ip==method.addr and seq[-1].mnemonic==M.RET and not seq[-1].op_count and
            seq[-1].stack_pointer_increment==8 and 3<=sum(i.is_call_near for i in seq)<=4 and
            _amd64(getattr(il,'bin',None)) and il.meta.version==31 and 0<=method.return_type<len(il.types)):return {}
    if (('method',method.index) not in il.addr_candidates.get(method.addr,()) or not _graph(il,seq) or
            any(i.has_segment_prefix or i.has_lock_prefix or i.memory_index!=R.NONE for i in seq)):return {}
    ty=il.types[method.return_type];key=il._closed_type_key;ps=source_params(il.meta,method)
    if (not ty or key(ty)!=(0x11,ty[0],0) or not 0<=ty[0]<len(il.meta.typedefs) or not il.returns_sret(ty) or len(ps)!=2 or
            any(not 0<=p.type<len(il.types) or key(il.types[p.type])!=(12,0) for p in ps)):return {}
    dst=il.meta.typedefs[ty[0]];size=il.value_type_size(dst.index)
    if (size not in (12,16) or dst.generic_container!=-1 or not dst.is_valuetype or dst.is_enum or
            any(not _field(il,dst,o,True) for o in range(0,size,4))):return {}
    names={safe_ident(p.name) for p in ps}
    if '__ret' in names or len(names)!=2 or any(n.startswith('t') and n[1:].isdigit() for n in names):return {}
    k=next((n for n,i in enumerate(seq) if i.mnemonic==M.SUB and i.op0_register==R.RSP),None)
    if k is None or seq[k].op1_kind not in (K.IMMEDIATE8TO64,K.IMMEDIATE32TO64):return {}
    base=il.bin.image_base;ix=bisect_left(il._eh4_begins,method.addr-base)
    if ix==len(il._eh4_entries) or il._eh4_entries[ix][0]+base!=method.addr:return {}
    addr=il._eh4_entries[ix][2]+base;h=il.bin.read(addr,4)
    if not h or len(h)!=4 or h[0]!=1 or h[3]:return {}
    raw=il.bin.read(addr,4+2*h[2]) or b''
    if len(raw)!=4+2*h[2]:return {}
    frame=_saves(seq,k,raw)
    if not frame:return {}
    alloc,depth,spans,pushed,moves,late=frame
    # Every instruction before allocation is a validated push, not an
    # escaped sret pointer or a scalar parameter overwritten by a home.
    if alloc<32 or any(i.mnemonic!=M.PUSH for i in seq[:k]):return {}
    epi=len(seq)-2-len(pushed);end=seq[epi]
    if (end.mnemonic!=M.ADD or end.op0_register!=R.RSP or end.op1_kind not in (K.IMMEDIATE8TO64,K.IMMEDIATE32TO64) or end.immediate(1)!=alloc or
            any(i.mnemonic!=M.POP or i.op0_register!=r for i,r in zip(seq[epi+1:-1],reversed(pushed)))):return {}
    lanes={R.XMM1:'a',R.XMM2:'b'};buffers={R.RCX};saved=set(pushed);pending=set();calls={};stored={};hidden=False
    for i in seq[k+1:epi]:
        dstreg,src=i.op0_register,i.op1_register
        if i.ip in late:
            slot=late[i.ip]
            if slot in pending or slot[0] in saved:return {}
            pending.add(slot);saved.add(slot[0]);continue
        restore=_slot_move(i,load=True)
        if restore is not None:
            if restore not in pending:return {}
            pending.remove(restore);saved.remove(restore[0]);lanes.pop(restore[0],None);buffers.discard(restore[0]);continue
        if i.mnemonic==M.MOV and RX.is_gpr64(dstreg) and src in buffers and (dstreg==R.RAX or dstreg in pushed):
            buffers.add(dstreg);continue
        if i.mnemonic==M.XOR and dstreg==src==R.R8D:
            hidden=True;continue
        if i.mnemonic==M.MOVAPS and RX.is_xmm(dstreg) and i.op1_kind==K.REGISTER and src in lanes:
            if dstreg>=R.XMM6 and dstreg not in saved:return {}
            lanes[dstreg]=lanes[src];continue
        if i.is_call_near:
            if stored or not hidden or (lanes.get(R.XMM0),lanes.get(R.XMM1))!=('a','b'):return {}
            ids=il.addr_candidates.get(i.near_branch_target,())
            if len(ids)!=1 or ids[0][0]!='method' or not 0<=ids[0][1]<len(il.meta.methods):return {}
            m=il.meta.methods[ids[0][1]];args=il.meta.method_params(m)
            if (m.index!=ids[0][1] or m.addr!=i.near_branch_target or m.generic_container!=-1 or not m.is_static or m.flags&(0x40|0x800) or
                    m.flags&7!=6 or not 0<=m.declaring<len(il.meta.typedefs) or
                    il.meta.typedefs[m.declaring].generic_container!=-1 or not 0<=m.return_type<len(il.types) or key(il.types[m.return_type])!=(12,0) or
                    m.param_count!=len(args) or len(args)!=2 or any(not 0<=p.type<len(il.types) or key(il.types[p.type])!=(12,0) for p in args)):return {}
            calls[i.ip]=m.index;lanes={r:v for r,v in lanes.items() if r>=R.XMM6};lanes[R.XMM0]=i.ip
            buffers.intersection_update(pushed);hidden=False;continue
        if (i.mnemonic==M.MOVSS and i.op0_kind==K.MEMORY and i.memory_base in buffers and i.op1_kind==K.REGISTER and
                lanes.get(src) in calls):
            off=sdisp(i.memory_displacement)
            if off in stored or off not in range(0,size,4):return {}
            stored[off]=lanes[src];continue
        return {}
    if R.RAX not in buffers or pending or len(calls)!=size//4 or set(stored.values())!=set(calls):return {}
    return calls
