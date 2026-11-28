"""A virtual receiver saved before two aggregate getters. At the virtual
call RCX holds a return buffer, and *RDX* still holds that original object.
Snapshot the reference at its real load; do not check it prematurely."""
from il2cpp.accessor_chain import _property
from il2cpp.array_origin import _graph,_definitions,_reachable,_SAVED
from il2cpp.closed_lookup import _receiver
from il2cpp.equivalent_binary import _amd64
from il2cpp.metadata import source_params
from il2cpp.names import safe_ident
from il2cpp.packed_call import _float_fields
from il2cpp.sret_copy import _own_field
from il2cpp.saved_binary import _frame_at
from il2cpp.prelude import HAVE_ICED
from il2cpp.text import sdisp
from il2cpp.virtual_edges import _entries
from il2cpp.x64 import KLASS_VTABLE
if HAVE_ICED:
    from iced_x86 import Mnemonic as M,OpKind as K,Register as R,RegisterExt as RX,MemorySizeExt as MS


def buffered_receivers(l,m,td,blocks,pads):
    il=l.il;out={}
    if not HAVE_ICED or pads or m.is_static or td.is_valuetype or td.generic_container!=-1 or m.generic_container!=-1:return out
    s=[i for b in blocks for i in b.insns];virtual=[i for i in s if i.is_call_near_indirect]
    if len(virtual)!=1 or len(s)>128 or sum(i.is_call_near and len(il.addr_candidates.get(i.near_branch_target,()))==1 for i in s)!=2 or not _amd64(il.bin) or il.meta.version!=31 or any(n.startswith('t') and n[1:].isdigit() for n in (safe_ident(p.name) for p in source_params(il.meta,m))):return out
    call=virtual[0];disp=sdisp(call.memory_displacement);base=call.memory_base
    if (call.op0_kind!=K.MEMORY or not RX.is_gpr64(base) or call.has_segment_prefix or call.memory_index!=R.NONE or
            disp<KLASS_VTABLE or (disp-KLASS_VTABLE)%16):return out
    def prove(i,by,pred,extent):
        defs=lambda ip,r:_definitions(by,pred,m.addr,ip,r)
        def one(ip,r):
            ds=defs(ip,r)
            if len(ds)==1:
                p,reg=ds.pop();src=by[p]
                if src.op0_register==reg:return src
        klass=one(i.ip,base)
        if not klass or klass.mnemonic!=M.MOV or klass.memory_base not in _SAVED or klass.memory_index!=R.NONE or klass.memory_displacement:return False
        field=one(klass.ip,klass.memory_base)
        if (not field or field.mnemonic!=M.MOV or field.op0_register not in _SAVED or field.has_segment_prefix or field.memory_index!=R.NONE or
                field.op1_kind!=K.MEMORY or not _receiver(il,m,by,pred,field.ip,td.index,initial=field.memory_base,this_only=True) or
                defs(i.ip,R.RDX)!={(field.ip,field.op0_register)}):return False
        row=_own_field(il,td,sdisp(field.memory_displacement),8);slot=(disp-KLASS_VTABLE)//16
        if not row or il._closed_type_key(row[1])!=(0x12,row[1][0],0):return False
        mi=il.vtable_method(row[1][0],slot)
        if mi is None or not 0<=mi<len(il.meta.methods):return False
        md=il.meta.methods[mi]
        def sig(md):
            ps=il.meta.method_params(md)
            if md.param_count!=2 or len(ps)!=2 or not 0<=md.return_type<len(il.types) or not all(0<=p.type<len(il.types) for p in ps):return None
            return tuple(il._closed_type_key(il.types[t]) for t in (md.return_type,ps[0].type,ps[1].type))
        key=sig(md)
        if (not key or md.is_static or not md.flags&0x40 or md.flags&7!=6 or md.slot!=slot or md.generic_container!=-1 or
                not il.returns_sret(il.types[md.return_type]) or il.meta.typedefs[md.declaring].generic_container!=-1):return False
        # The fifth argument is this slot's MethodInfo. Restrict its entire
        # setup to local scratch stores and register copies. No unknown call
        # or extra predecessor can furnish another context/receiver here.
        ip=i.ip;ctx=None
        while ip!=klass.ip:
            if len(pred[ip])!=1:return False
            p=pred[ip][0];x=by[p]
            if p<klass.ip or x.next_ip!=ip or x.mnemonic not in (M.MOV,M.MOVSS,M.MOVSD,M.MOVAPS,M.MOVUPS,M.LEA) or x.has_segment_prefix or x.memory_index!=R.NONE:return False
            if x.op0_kind==K.MEMORY:
                off=sdisp(x.memory_displacement);width=MS.size(x.memory_size)
                if x.memory_base!=R.RSP or off<32 or not width:return False
                if off<40:
                    if off!=32 or width!=8 or ctx or not RX.is_gpr64(x.op1_register):return False
                    ctx=one(x.ip,x.op1_register)
                    if not ctx or ctx.mnemonic!=M.MOV or ctx.memory_base!=base or ctx.memory_displacement!=disp+8 or defs(ctx.ip,base)!=defs(i.ip,base):return False
            ip=p
        if ctx is None:return False
        sources=[x for x in s if x.is_call_near and field.ip<x.ip<klass.ip];props=[_property(l,x) for x in sources]
        if len(props)!=2 or not all(props) or [il._closed_type_key(q[2]) for q in props]!=list(key[1:]) or any(len(_float_fields(il,q[2]) or ()) not in (3,4) for q in props):return False
        frame=_frame_at(il,s,by,pred,i.ip)
        if not frame:return False
        regs=(R.RCX,R.R8,R.R9);areas=[]
        for r,k in zip(regs,[il.types[md.return_type],props[0][2],props[1][2]]):
            home=one(i.ip,r);width=il._sf_field_size(k,0)
            if not home or home.mnemonic!=M.LEA or home.memory_base!=R.RSP or home.memory_index!=R.NONE or not width:return False
            off=sdisp(home.memory_displacement)
            if off<40 or off+width>frame[0] or any(a<off+width and off<a+n for a,n in frame[2]) or any(a<off+width and off<b for a,b in areas):return False
            areas.append((off,off+width))
        rows={field.ip:row};epochs=[]
        for c,prop in zip(sources,props):
            src=one(c.ip,R.RDX)
            if not src or src.mnemonic!=M.MOV or src.op1_kind!=K.MEMORY or src.has_segment_prefix or src.memory_index!=R.NONE or not _receiver(il,m,by,pred,src.ip,td.index,initial=src.memory_base,this_only=True):return False
            f=_own_field(il,td,sdisp(src.memory_displacement),8)
            if not f or il._closed_type_key(f[1])!=(0x12,prop[0].declaring,0):return False
            zeros=defs(c.ip,R.R8)
            if len(zeros)!=1:return False
            zp,zr=zeros.pop();hidden=by[zp]
            if zr!=R.R8 or hidden.mnemonic!=M.XOR or hidden.op0_register!=hidden.op1_register or hidden.op0_register!=R.R8D:return False
            rows[src.ip]=f;epochs.append(src.ip)
        if not epochs[0]<field.ip<sources[0].ip<epochs[1]<sources[1].ip<klass.ip:return False
        for a,z in ((m.addr,field.ip),(field.ip,sources[0].ip),(sources[0].ip,epochs[1]),(epochs[1],sources[1].ip),(sources[1].ip,klass.ip)):
            ip=z
            while ip!=a:
                if len(pred[ip])!=1:return False
                p=pred[ip][0];x=by[p]
                if p>=ip or x.next_ip!=ip or x.mnemonic==M.CALL and p!=a:return False
                if x.is_jcc_short_or_near:
                    raiser=by.get(x.near_branch_target)
                    if not raiser or not raiser.is_call_near or l._named_raise_throw(raiser.near_branch_target,l._call_name(raiser.near_branch_target))!='System.NullReferenceException':return False
                ip=p
        entries=_entries(il,row[1][0],slot)
        if not entries or not all(sig(il.meta.methods[e])==key and not extent[0]<=il.meta.methods[e].addr<extent[1] for e in entries):return False
        out.update(rows);return True
    return out if _graph(il,s,chained=True,nested_chains=True,virtual_edges=prove) else {}
