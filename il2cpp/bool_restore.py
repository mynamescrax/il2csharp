"""Track an actual static Boolean property read, override and later write.
Keep the setter on its original CFG edge. Stack carriers are live homes;
register carriers require the same byte on every path into the reload."""
from il2cpp.array_origin import _graph,_definitions
from il2cpp.copied_getter import _sp_offset
from il2cpp.module_curve import fixed_frame
from il2cpp.prelude import HAVE_ICED
from il2cpp.text import reg_name,sdisp
from il2cpp.equivalent_binary import _amd64

if HAVE_ICED:
    from iced_x86 import Mnemonic as M, Register as R, RegisterExt, OpKind as K, MemorySizeExt
    _SAVED={R.RBX,R.RBP,R.RDI,R.RSI,R.R12,R.R13,R.R14,R.R15}


def _property(lift,i,kind):
    il=lift.il
    if i.mnemonic!=M.CALL or i.op0_kind!=K.NEAR_BRANCH64:return None
    ids=il.addr_candidates.get(i.near_branch_target,())
    if len(ids)!=1 or ids[0][0]!='method' or not 0<=ids[0][1]<len(il.meta.methods):return None
    m=il.meta.methods[ids[0][1]];is_get=kind=='get'
    if (not m.is_static or m.flags&7!=6 or m.generic_container!=-1 or m.addr!=i.near_branch_target or
            m.param_count!=int(not is_get) or not 0<=m.return_type<len(il.types) or
            il._closed_type_key(il.types[m.return_type])!=((2 if is_get else 1),0)):return None
    if not is_get:
        ps=il.meta.method_params(m)
        if len(ps)!=1 or not 0<=ps[0].type<len(il.types) or il._closed_type_key(il.types[ps[0].type])!=(2,0):return None
    p=lift._accessor_prop(m.index)
    if not p or p[0]!=kind or p[2] or il.meta.typedefs[m.declaring].generic_container!=-1:return None
    return m,(m.declaring,p[1])


def _byte_home(seq,frame,store,load):
    """Only a reserved incoming home outside the allocation, never shadow
    space for an outgoing call. Normalize explicit byte reads/writes and
    decline ambiguous overlaps. The load uses the *home*, not its old RHS."""
    off=_sp_offset(store,frame[0]);depth=frame[2]
    if off not in tuple(depth+x for x in (8,16,24,32)) or _sp_offset(load,frame[0])!=off:return None
    for i in seq:
        if i.memory_base not in (R.RSP,R.RBP):continue
        pos=_sp_offset(i,frame[0])
        if pos is None:return None
        if i.memory_base==R.RBP and sdisp(i.memory_displacement)==off:return None  # colliding legacy slot spelling
        if i.mnemonic==M.LEA:
            if off<=pos<off+8:return None
            continue
        n=MemorySizeExt.size(i.memory_size)
        if not n or pos<=off<pos+n and i.ip not in (store.ip,load.ip):return None
    return off


def bool_state_sites(lift,method,blocks,pads):
    actions={};il=lift.il
    if not HAVE_ICED or pads or not _amd64(getattr(il,'bin',None)) or getattr(il.meta,'version',None)!=31:return actions
    sites=[];seq=[i for b in blocks for i in b.insns]
    for j in range(1,len(seq)-4):
        call,zero,x,y,setter=seq[j:j+5]
        if (call.mnemonic!=M.CALL or setter.mnemonic!=M.CALL or zero.mnemonic!=M.XOR or zero.op0_register!=R.EDX or zero.op1_register!=R.EDX or
                seq[j-1].mnemonic!=M.XOR or seq[j-1].op0_register!=R.ECX or seq[j-1].op1_register!=R.ECX):continue
        store,flag=(x,y) if y.op0_register==R.CL else (y,x)
        if flag.mnemonic!=M.MOV or flag.op0_register!=R.CL or flag.op1_kind!=K.IMMEDIATE8 or flag.immediate8 not in (0,1) or store.op1_register!=R.AL:continue
        mem=store.mnemonic==M.MOV and store.op0_kind==K.MEMORY and store.memory_base in (R.RBP,R.RSP)
        reg=store.mnemonic==M.MOVZX and RegisterExt.is_gpr32(store.op0_register) and RegisterExt.full_register(store.op0_register) in _SAVED
        if ((mem or reg) and not any(i.has_segment_prefix or i.has_lock_prefix for i in seq[j-1:j+5]) and
                (get:=_property(lift,call,'get')) and (put:=_property(lift,setter,'set')) and get[1]==put[1]):sites.append((j,get,store,mem,setter))
    if not sites:return actions
    graph=_graph(il,seq,chained=True,allow_tail=True,runtime_tails=lift.rt_wbarrier)
    if not graph:return actions
    pred,_=graph;by={i.ip:i for i in seq};frame=None
    for j,(getter,member),store,mem,setter in sites:
        w=seq[j-1:j+5];call=w[1]
        if any(pred[b.ip]!=[a.ip] or a.next_ip!=b.ip for a,b in zip(w,w[1:])):continue
        for k in range(j+7,len(seq)):
            sink=seq[k];a,b=seq[k-2:k]
            if sink.mnemonic!=M.CALL or sink.op0_kind!=K.NEAR_BRANCH64 or sink.near_branch_target!=setter.near_branch_target:continue
            load,zero=(a,b) if a.mnemonic==M.MOVZX else (b,a)
            if (load.mnemonic!=M.MOVZX or load.op0_register!=R.ECX or zero.mnemonic!=M.XOR or zero.op0_register!=R.EDX or zero.op1_register!=R.EDX or
                    pred[sink.ip]!=[b.ip] or pred[b.ip]!=[a.ip] or b.next_ip!=sink.ip or a.next_ip!=b.ip):continue
            if mem:
                if load.op1_kind!=K.MEMORY or MemorySizeExt.size(load.memory_size)!=1:continue
                frame=frame or fixed_frame(lift,method,blocks,pads,immediate=True,extended_saves=True)
                off=_byte_home(seq,frame,store,load) if frame else None
                if off is None:continue
                # A home declaration needs an initializing store along every
                # path. Reloading the local preserves its own storage identity.
                seen=set();todo=[load.ip]
                while todo:
                    ip=todo.pop()
                    if ip in seen or ip==store.ip:continue
                    seen.add(ip);todo.extend(pred[ip])
                if method.addr in seen:continue
                actions[store.ip]=('bool_home_store',call.ip,off)
                actions[load.ip]=('bool_home_load',store.ip,off)
            else:
                r=RegisterExt.full_register(store.op0_register)
                if (not RegisterExt.is_gpr8(load.op1_register) or load.op1_register in (R.AH,R.BH,R.CH,R.DH) or
                        RegisterExt.full_register(load.op1_register)!=r or _definitions(by,pred,method.addr,load.ip,r)!={(store.ip,r)}):continue
                actions[store.ip]=('bool_park',call.ip,reg_name(store.op0_register))
                actions[load.ip]=('bool_park',call.ip,'RCX')
            actions[call.ip]=('bool_get',il.typedef_full(member[0])+'.'+member[1],il.types[getter.return_type])
    return actions
