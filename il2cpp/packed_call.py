"""Win64 by-value float-pair arguments sourced by qword field reads.

SHUFPS selects dwords; it does not convert a double to a float. Track the
origin of each lane through the final MOVQs. Read each source pair as one
64-bit value, in native order, then project its bits into a typed local.
"""
from il2cpp.array_origin import _graph
from il2cpp.closed_lookup import _receiver
from il2cpp.csharp import FA_INITONLY, FA_LITERAL, FA_STATIC, field_attrs, source_field_name
from il2cpp.equivalent_binary import _amd64
from il2cpp.expr import Expr
from il2cpp.names import safe_ident
from il2cpp.packed_projection import _field
from il2cpp.prelude import HAVE_ICED
from il2cpp.shared_field import whole_field_at
from il2cpp.text import reg_name,sdisp

if HAVE_ICED:
    from iced_x86 import MemorySizeExt,Mnemonic as M,OpKind as K,Register as R


def _float_fields(il,ty):
    if not ty or il._closed_type_key(ty)!=(0x11,ty[0],0) or not 0<=ty[0]<len(il.meta.typedefs):return None
    td=il.meta.typedefs[ty[0]];size=il.value_type_size(td.index)
    if (not td.is_valuetype or td.is_enum or td.generic_container!=-1 or td.declaring!=-1 or td.flags&0x18!=8 or
            size not in (8,12,16)):return None
    # Use managed field addresses, not object-relative pointer arithmetic.
    # Only sequential all-Single storage with no holes or rearrangement is
    # eligible. The emitted struct declares its instance fields in row order.
    fis=[fi for fi in il.meta.type_fields(td) if not field_attrs(il,il.meta.fields[fi])&(FA_LITERAL|FA_STATIC)]
    if 4*len(fis)!=size:return None
    names=[_field(il,td,4*k,write=True) for k in range(len(fis))]
    if (None in names or len(set(names))!=len(names) or names!=[source_field_name(il,fi) for fi in fis]):return None
    return names


def _source(il,td,off):
    if td.index>=len(il.field_offsets):return None
    offsets=il.field_offsets[td.index]
    if not offsets or len(offsets)!=td.field_count:return None
    for fi,start in zip(il.meta.type_fields(td),offsets):
        delta=off-start;f=il.meta.fields[fi]
        if delta not in (0,4,8) or not 0<=f.type<len(il.types) or field_attrs(il,f)&(FA_STATIC|FA_LITERAL|FA_INITONLY):continue
        ty=il.types[f.type];names=_float_fields(il,ty)
        if not names or delta+8>4*len(names) or whole_field_at(il,td.index,start,4*len(names))!=(td.index,fi,ty):continue
        name=safe_ident(source_field_name(il,fi))
        if name.isidentifier():return 'this.'+name+'.'+names[delta//4]


def _pack(il,td,w):
    regs={};pairs={};reads=[];zero=False
    for i in w:
        if i.has_segment_prefix or i.has_lock_prefix or i.memory_index!=R.NONE:return None
        dst,src=i.op0_register,i.op1_register
        if (i.mnemonic==M.XOR and dst==src==R.R9D):zero=True;continue
        if i.mnemonic==M.MOVQ and dst in (R.RDX,R.R8) and src in regs:
            pairs[dst]=regs[src][:2];continue
        if not R.XMM0<=dst<=R.XMM5:return None
        if i.mnemonic==M.MOVSD and i.op1_kind==K.MEMORY and i.memory_base==R.RCX and MemorySizeExt.size(i.memory_size)==8:
            member=_source(il,td,sdisp(i.memory_displacement))
            if not member:return None
            n=len(reads);reads.append(member);regs[dst]=((n,0),(n,1),None,None)
        elif src in regs and i.mnemonic==M.MOVAPS:regs[dst]=regs[src]
        elif dst in regs and src in regs and i.mnemonic==M.SHUFPS and i.op2_kind==K.IMMEDIATE8:
            a,b=regs[dst],regs[src];c=i.immediate8;regs[dst]=(a[c&3],a[(c>>2)&3],b[(c>>4)&3],b[c>>6])
        elif dst in regs and src in regs and i.mnemonic==M.UNPCKLPS:
            a,b=regs[dst],regs[src];regs[dst]=(a[0],b[0],a[1],b[1])
        else:return None
    if not zero or set(pairs)!={R.RDX,R.R8} or any(None in p for p in pairs.values()) or len(reads)!=2:return None
    return reads,pairs


def packed_calls(lift,method,td,blocks,pads):
    il=lift.il;plans={}
    if (not HAVE_ICED or pads or method.is_static or td.is_valuetype or method.generic_container!=-1 or td.generic_container!=-1 or
            not _amd64(getattr(il,'bin',None)) or il.meta.version!=31):return plans
    if (not 0<=method.return_type<len(il.types) or il._closed_type_key(il.types[method.return_type])!=(1,0) or
            ('method',method.index) not in il.addr_candidates.get(method.addr,())):return plans
    graph=None
    for b in blocks:
        if not b.insns or b.insns[0].mnemonic!=M.MOVSD:continue
        end=next((n for n,i in enumerate(b.insns[:22]) if i.is_call_near),0);w=b.insns[:end]
        if not 5<=end<=20 or not any(i.mnemonic==M.MOVQ and i.op0_register==R.R8 for i in w):continue
        call=b.insns[end];ids=il.addr_candidates.get(call.near_branch_target,())
        if len(ids)!=1 or ids[0][0]!='method' or not 0<=ids[0][1]<len(il.meta.methods):continue
        sink=il.meta.methods[ids[0][1]]
        if (sink.addr!=call.near_branch_target or sink.declaring!=td.index or sink.is_static or sink.flags&(0x40|0x800) or
                sink.generic_container!=-1 or sink.param_count!=2 or not 0<=sink.return_type<len(il.types) or il._closed_type_key(il.types[sink.return_type])!=(1,0)):continue
        ps=il.meta.method_params(sink);types=[il.types[p.type] for p in ps if 0<=p.type<len(il.types)];fields=[_float_fields(il,t) for t in types]
        if len(types)!=2 or any(not fs or len(fs)!=2 for fs in fields):continue
        pack=_pack(il,td,w)
        if not pack:continue
        if graph is None:
            seq=[i for z in blocks for i in z.insns];by={i.ip:i for i in seq};graph=_graph(il,seq)
            if not graph or seq[0].ip!=method.addr:return {}
        pred,_=graph
        if (any(a.next_ip!=z.ip or pred[z.ip]!=[a.ip] for a,z in zip(w,w[1:]+[call])) or
                not _receiver(il,method,by,pred,w[0].ip,td.index,this_only=True)):continue
        names={safe_ident(p.name) for p in il.meta.method_params(method)}
        plans[w[0].ip]=(end,td.index,*pack,types,fields,names)
    return plans


def apply_packed_call(lift,ip,plan):
    _,owner,reads,pairs,types,fields,params=plan;recv=dict.get(lift.regs,'RCX')
    if not recv or recv.text!='this' or lift.il._closed_type_key(recv.ty)!=(0x12,owner,0):return False
    mm='global::System.Runtime.InteropServices.MemoryMarshal';bits=[]
    def fresh():
        v=lift.new_var()
        while v in params:v=lift.new_var()
        return v
    for member in reads:
        v=fresh();lift._var_types[v]=lift._type_hints[v]=(0,0x0a<<16)
        lift.emit(ip,f'var {v} = {mm}.Cast<float, long>({mm}.CreateReadOnlySpan(ref {member}, 2))[0];',None);bits.append(v)
    for r,ty,names in zip((R.RDX,R.R8),types,fields):
        v=fresh();lift._var_types[v]=lift._type_hints[v]=ty
        lift.emit(ip,f'var {v} = default(global::{lift.il.typedef_full(ty[0])});',None)
        for name,(n,hi) in zip(names,pairs[r]):
            expr=bits[n]+(' >> 32' if hi else '')
            lift.emit(ip,f'{v}.{name} = global::System.BitConverter.Int32BitsToSingle(unchecked((int)({expr})));',None)
        lift.regs[reg_name(r)]=Expr(v,ty,'obj')
    for n in range(6):lift.regs.pop('XMM%d'%n,None)
    lift.regs['R9']=Expr('0',None,'int');lift.flags=None;return True
