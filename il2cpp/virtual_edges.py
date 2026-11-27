"""Certify the normal-return edge of an indirect Win64 VirtualInvokeData call.
The raw graph may only use that edge after proving the klass/receiver, all
registered concrete implementations, and the separate hidden MethodInfo.
This does not select any one of the overrides for managed dispatch.
"""
from il2cpp.array_origin import _definitions
from il2cpp.closed_lookup import _receiver,spec_lookup
from il2cpp.csharp import field_attrs,source_field_name
from il2cpp.equivalent_binary import _amd64
from il2cpp.names import safe_ident
from il2cpp.prelude import HAVE_ICED
from il2cpp.shared_field import reference_field_at
from il2cpp.stack_local_frame import stack_local_frame
from il2cpp.text import sdisp
from il2cpp.x64 import KLASS_VTABLE

if HAVE_ICED:
    from iced_x86 import FlowControl as F, MemorySizeExt, Mnemonic as M, OpKind as K, Register as R,RegisterExt


def _one(by,pred,entry,site,reg):
    defs=_definitions(by,pred,entry,site,reg)
    if len(defs)==1:return defs.pop()


def _obj_source(il,method,by,pred,at,r,depth=0):
    if depth>3:return None
    if _receiver(il,method,by,pred,at,method.declaring,initial=r,this_only=True):return method.declaring,()
    got=_one(by,pred,method.addr,at,r)
    if not got:return None
    ip,reg=got;i=by[ip]
    if i.is_call_near and reg==R.RAX:
        ids=il.addr_candidates.get(i.near_branch_target,())
        if len(ids)==1 and ids[0][0]=='method':
            m=il.meta.methods[ids[0][1]];t=il.types[m.return_type] if 0<=m.return_type<len(il.types) else None
            if (m.addr==i.near_branch_target and m.generic_container==-1 and t and il._closed_type_key(t)==(0x12,t[0],0) and
                    0<=t[0]<len(il.meta.typedefs) and not il.meta.typedefs[t[0]].is_valuetype):return t[0],()
        hidden=_one(by,pred,method.addr,ip,R.RDX)
        if not hidden or hidden[1]!=R.RDX:return None
        spec=spec_lookup(il,by[hidden[0]],i)
        if not spec:return None
        owner=_obj_source(il,method,by,pred,ip,R.RCX,depth+1)
        if owner and spec[1].declaring in il.base_chain_tds(owner[0]):return spec[2][0],()
    elif (i.mnemonic==M.MOV and i.op0_register==reg and RegisterExt.is_gpr64(reg) and i.op1_kind==K.MEMORY and
            RegisterExt.is_gpr64(i.memory_base) and i.memory_index==R.NONE and not i.has_segment_prefix and not i.has_lock_prefix):
        owner=_obj_source(il,method,by,pred,i.ip,i.memory_base,depth+1)
        if not owner:return None
        ti,chain=owner
        field=reference_field_at(il,ti,sdisp(i.memory_displacement))
        if not field or field[0]!=ti:return None
        _,fi,ty=field
        if (not 0<=ty[0]<len(il.meta.typedefs) or il.meta.typedefs[ty[0]].is_valuetype or
                ti!=method.declaring and field_attrs(il,il.meta.fields[fi])&7!=6):return None
        # Only capture a path rooted in actual entry this; other registered
        # references can prove dispatch without authorizing a new field read.
        if not chain and not _receiver(il,method,by,pred,i.ip,method.declaring,initial=i.memory_base,this_only=True):return ty[0],()
        return ty[0],(*chain,(i.ip,safe_ident(source_field_name(il,fi)),ty))


def _entries(il,owner,slot):
    key=(owner,slot);cache=il.__dict__.setdefault('_certified_virtual_entries',{})
    if key not in cache:
        methods=[]
        for td in il.meta.typedefs:
            if td.flags&(0x20|0x80) or td.is_valuetype or owner not in il.base_chain_tds(td.index):continue
            if td.generic_container!=-1 or not 0<=slot<td.vtable_count:break
            raw=il.meta.vtable_methods[td.vtable_start+slot];mi=(raw&0x1ffffffe)>>1
            if raw>>29!=3 or not 0<mi<len(il.meta.methods):break
            m=il.meta.methods[mi]
            if (not m.addr or not il.bin.is_exec_va(m.addr) or m.slot!=slot or m.is_static or not m.flags&0x40 or
                    m.flags&0x400 or m.generic_container!=-1 or ('method',mi) not in il.addr_candidates.get(m.addr,())):break
            methods.append(mi)
        else:cache[key]=tuple(set(methods))
        cache.setdefault(key,())
    return cache[key]


def certified_edge(lift,method,call,by,pred,extent):
    il=lift.il;base=call.memory_base;disp=sdisp(call.memory_displacement)
    if (not _amd64(getattr(il,'bin',None)) or il.meta.version!=31 or not call.is_call_near_indirect or call.op0_kind!=K.MEMORY or
            call.memory_index!=R.NONE or not RegisterExt.is_gpr64(base) or
            call.has_segment_prefix or disp<KLASS_VTABLE or (disp-KLASS_VTABLE)%16):return None
    klass=_one(by,pred,method.addr,call.ip,base)
    if not klass:return None
    load=by[klass[0]];holder=load.memory_base
    if (load.mnemonic!=M.MOV or load.op0_register!=klass[1] or load.op1_kind!=K.MEMORY or load.memory_index!=R.NONE or
            not RegisterExt.is_gpr64(holder) or load.has_segment_prefix or load.memory_displacement):return None
    receiver=_one(by,pred,method.addr,load.ip,holder)
    if not receiver or receiver!=_one(by,pred,method.addr,call.ip,R.RCX):return None
    obj=_obj_source(il,method,by,pred,load.ip,holder)
    if not obj:return None
    owner,fields=obj;slot=(disp-KLASS_VTABLE)//16;mi=il.vtable_method(owner,slot)
    if mi is None or not 0<=mi<len(il.meta.methods):return None
    m=il.meta.methods[mi]
    if not 3<=m.param_count<=12 or m.slot!=slot or m.is_static or not m.flags&0x40 or m.generic_container!=-1:return None
    def signature(md):
        if not 0<=md.return_type<len(il.types):return None
        ps=il.meta.method_params(md)
        if len(ps)!=md.param_count or any(not 0<=p.type<len(il.types) for p in ps):return None
        return tuple(il._closed_type_key(t) for t in [il.types[md.return_type],*(il.types[p.type] for p in ps)])
    sig=signature(m)
    if not sig or sig[0]!=(1,0) or None in sig:return None
    off=8*(m.param_count+1);ip=call.ip
    for _ in range(24):
        if len(pred[ip])!=1:return None
        i=by[pred[ip][0]]
        if (i.next_ip!=ip or i.flow_control!=F.NEXT or i.has_lock_prefix or i.has_segment_prefix or
                i.mnemonic not in (M.MOV,M.LEA,M.MOVSD,M.MOVSS,M.MOVAPS,M.XOR) or i.memory_index!=R.NONE):return None
        ip=i.ip
        if i.op0_kind==K.MEMORY:
            p=sdisp(i.memory_displacement);size=MemorySizeExt.size(i.memory_size)
            if i.memory_base!=R.RSP or not size:return None
            if p>=off+8 or p+size<=off:continue
            if p!=off or size!=8 or i.mnemonic!=M.MOV or not RegisterExt.is_gpr64(i.op1_register):return None
            orig=_one(by,pred,method.addr,ip,i.op1_register)
            if not orig:return None
            src=by[orig[0]]
            if (src.mnemonic==M.MOV and src.op0_register==orig[1] and src.op1_kind==K.MEMORY and src.memory_index==R.NONE and
                    not src.has_segment_prefix and src.memory_displacement==disp+8 and src.memory_base==base and
                    _one(by,pred,method.addr,src.ip,base)==klass):
                # Enumerate overrides only after both words and the exact
                # hidden argument home have qualified.
                ids=_entries(il,owner,slot)
                if ids and all(signature(il.meta.methods[j])==sig and not extent[0]<=il.meta.methods[j].addr<extent[1] for j in ids):return mi,off,fields
            return None
        if RegisterExt.full_register(i.op0_register)==R.RSP:return None


def terminal_homes(lift,method,blocks,pads,virtuals):
    """A proved hidden argument followed solely by the caller's restore.
    Keep the native store. Do not export its RHS as a value to replay in a
    phi at a shared exit. Only a dead outgoing tile can be forgotten here."""
    if not virtuals or method.is_static or not 0<=method.return_type<len(lift.il.types) or lift.il._closed_type_key(lift.il.types[method.return_type])!=(1,0):return {}
    frame=stack_local_frame(lift,method,blocks,pads)
    if not frame:return {}
    size,depth,saves=frame;by={i.ip:i for b in blocks for i in b.insns};out={}
    for ip,(mi,off,fields) in virtuals.items():
        if not 32<=off<=size-8 or any(a<off+8 and off<a+n for a,n in saves):continue
        p=by[ip].next_ip
        for _ in range(24):
            i=by.get(p)
            if not i or i.has_segment_prefix or i.has_lock_prefix or i.memory_index!=R.NONE:break
            p=i.next_ip
            if i.mnemonic==M.RET and not i.op_count:
                out[ip]=(mi,off,depth,fields);break
            if i.mnemonic==M.ADD and i.op0_register==R.RSP and i.op1_kind in (K.IMMEDIATE8TO64,K.IMMEDIATE32TO64) and i.immediate(1)==size:continue
            if i.mnemonic==M.POP and i.op0_register in (R.RBX,R.RDI,R.RSI,R.RBP,R.R12,R.R13,R.R14,R.R15):continue
            if (i.mnemonic not in (M.MOV,M.MOVAPS,M.MOVUPS) or i.op0_kind!=K.REGISTER or i.op1_kind!=K.MEMORY or
                    i.memory_base!=R.RSP or (sdisp(i.memory_displacement),MemorySizeExt.size(i.memory_size)) not in saves):break
    return out
