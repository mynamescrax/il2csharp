"""A zero dword register write zero-extends to a Win64 null reference.

Recover null only at the exact closed by-value parameter position, not
from the spelling of an immediate. Stack references need all eight bytes.
"""
from il2cpp.array_origin import _graph
from il2cpp.equivalent_binary import _amd64
from il2cpp.prelude import HAVE_ICED
from il2cpp.stack_local_frame import stack_local_frame
from il2cpp.text import sdisp

if HAVE_ICED:
    from iced_x86 import Mnemonic as M, Register as R, RegisterExt as RX, FlowControl as F, OpKind as K, MemorySizeExt as MS
    from il2cpp.array_origin import _INFO,_WRITES


def _zero(seq,k,reg):
    for i in reversed(seq[max(k-20,0):k]):
        if i.flow_control!=F.NEXT or i.has_segment_prefix or i.has_lock_prefix:return False
        if not any(u.access in _WRITES and RX.full_register(u.register)==reg for u in _INFO.info(i).used_registers()):continue
        if i.op0_kind!=K.REGISTER or RX.full_register(i.op0_register)!=reg or RX.size(i.op0_register) not in (4,8):return False
        if i.mnemonic==M.XOR:return i.op1_register==i.op0_register
        if i.mnemonic!=M.MOV:return False
        if i.op1_kind in (K.IMMEDIATE32,K.IMMEDIATE32TO64,K.IMMEDIATE64):return i.immediate(1)==0
        if i.op1_kind!=K.REGISTER or not RX.is_gpr64(i.op1_register):return False
        reg=i.op1_register
    return False


def _null_slot(seq,j,off):
    for n in range(j-1,max(-1,j-21),-1):
        i=seq[n]
        if i.flow_control!=F.NEXT or i.has_segment_prefix or i.has_lock_prefix:return False
        if any(u.access in _WRITES and RX.full_register(u.register)==R.RSP for u in _INFO.info(i).used_registers()):return False
        for mem in _INFO.info(i).used_memory():
            if mem.access not in _WRITES:continue
            if (mem.base!=R.RSP or mem.index!=R.NONE or i.memory_base!=R.RSP or i.memory_index!=R.NONE or i.op0_kind!=K.MEMORY or
                    i.mnemonic in (M.BT,M.BTC,M.BTR,M.BTS)):return False
            o=sdisp(i.memory_displacement);width=MS.size(i.memory_size)
            if not width:return False
            if o>=off+8 or o+width<=off:continue
            if i.mnemonic!=M.MOV or o!=off or width!=8:return False
            if i.op1_kind==K.IMMEDIATE32TO64:return i.immediate32to64==0
            return i.op1_kind==K.REGISTER and RX.is_gpr64(i.op1_register) and _zero(seq,n,i.op1_register)
    return False


def _reference(il,t):
    k=il._closed_type_key(t)
    if not k or k[-1]:return False
    if k in ((0xe,0),(0x1c,0)):return True
    return k[0]==0x12 and 0<=k[1]<len(il.meta.typedefs) and il.meta.typedefs[k[1]].generic_container==-1 and not il.meta.typedefs[k[1]].is_valuetype


def null_sites(lift,caller,blocks,pads):
    sites={};il=lift.il
    if not HAVE_ICED or pads or not _amd64(getattr(il,'bin',None)) or il.meta.version!=31:return sites
    maybe=[];regs=(R.RCX,R.RDX,R.R8,R.R9)
    for b in blocks:
        for n,i in enumerate(b.insns):
            if not n or not i.is_call_near:continue
            ids=il.addr_candidates.get(i.near_branch_target,())
            if len(ids)!=1 or ids[0][0]!='method' or not 0<=ids[0][1]<len(il.meta.methods):continue
            md=il.meta.methods[ids[0][1]]
            if (md.addr!=i.near_branch_target or md.generic_container!=-1 or not md.param_count or not 0<=md.declaring<len(il.meta.typedefs) or
                    il.meta.typedefs[md.declaring].generic_container!=-1 or md.name.startswith(('.','op_','add_','remove_')) or
                    not 0<=md.return_type<len(il.types) or il._closed_type_key(il.types[md.return_type])!=(1,0)):continue
            ps=il.meta.method_params(md);start=int(not md.is_static)
            if len(ps)!=md.param_count:continue
            pos=[k for k,p in enumerate(ps,start) if 0<=p.type<len(il.types) and _reference(il,il.types[p.type]) and
                 (_zero(b.insns,n,regs[k]) if k<4 else _null_slot(b.insns,n,32+8*(k-4)))]
            if pos:maybe.append((b,i,md,pos))
    if not maybe:return sites
    seq=[i for b in blocks for i in b.insns];g=_graph(il,seq,allow_tail=True,chained=True,nested_chains=True,runtime_tails=lift.rt_wbarrier)
    if not g or seq[0].ip!=caller.addr:return sites
    frame=stack_local_frame(lift,caller,blocks,pads) if any(k>=4 for *_,pos in maybe for k in pos) else None
    for b,i,md,ps in maybe:
        # C# literal null must resolve to the registered overload. Reject
        # other declarations with the same source name across the owner
        # hierarchy rather than adding a guessed cast or changing overloads.
        if any(il.meta.methods[n].name==md.name and n!=md.index for owner in il.base_chain_tds(md.declaring) for n in il.meta.type_methods(il.meta.typedefs[owner])):continue
        valid={k for k in ps if k<4 or (frame and (k+1)*8<=frame[0] and all(not (a<(k+1)*8 and k*8<a+w) for a,w in frame[2]))}
        if valid:sites[i.ip]=(md.index,valid)
    return sites
