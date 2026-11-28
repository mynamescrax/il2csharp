"""A public nonvirtual getter equivalent to one whole object field load."""
from il2cpp.csharp import declares_member_name
from il2cpp.names import safe_ident
from il2cpp.prelude import HAVE_ICED
from il2cpp.shared_field import whole_field_at
from il2cpp.text import sdisp
if HAVE_ICED:
    from iced_x86 import Decoder,Mnemonic as M,Register as R,OpKind as K,MemorySizeExt as MS


def plain_alias(l,receiver,off,width):
    il=l.il;row=whole_field_at(il,receiver,off,width);hits=[]
    if not row or width not in (4,8):return None
    owner,fi,ty=row;td=il.meta.typedefs[owner];key=il._closed_type_key(ty);chain=il.base_chain_tds(receiver)
    for pr in il.meta.properties[td.property_start:td.property_start+td.property_count]:
        j=pr[1]
        if j is None or not 0<=j<td.method_count:continue
        m=il.meta.methods[td.method_start+j];name=il.meta.getstr(pr[0]);p=l._accessor_prop(m.index)
        if (not p or p[:2]!=('get',name) or p[2] or not name.isidentifier() or safe_ident(name)!=name or m.name!='get_'+name or
                m.declaring!=owner or m.is_static or m.param_count or m.flags&0x40 or m.flags&7!=6 or m.generic_container!=-1 or not m.addr or
                not 0<=m.return_type<len(il.types) or il._closed_type_key(il.types[m.return_type])!=key or il.returns_sret(ty) or
                ('method',m.index) not in il.addr_candidates.get(m.addr,()) or any(declares_member_name(il,il.meta.typedefs[n],name) for n in chain[:chain.index(owner)])):continue
        # No hidden effect, no getter recursion, no nested field. Bound
        # the leaf by section and symbol entries even for frameless getters.
        raw=il.bin.read(m.addr,12) or b'';s=list(Decoder(64,raw,ip=m.addr))
        if len(s)<2:continue
        a,r=s[:2];end=r.next_ip;limit=il.function_extent(m.addr)
        boundaries=(il.next_function_start(m.addr),il.next_method_start(m.addr))
        if (not il.bin.is_exec_va(m.addr) or not any(sec.is_exec and sec.addr<=m.addr and end<=sec.addr+min(sec.size,sec.rawsize) for sec in il.bin.sections) or
                limit[0]!=m.addr or end>limit[1] or any(x is not None and x<end for x in boundaries) or
                any(x in il.addr_to_method or x in il.bin.exports for x in range(m.addr+1,end)) or
                a.mnemonic!=M.MOV or a.op0_register!=(R.EAX if width==4 else R.RAX) or a.op1_kind!=K.MEMORY or
                a.memory_base!=R.RCX or a.memory_index!=R.NONE or sdisp(a.memory_displacement)!=off or MS.size(a.memory_size)!=width or
                a.has_segment_prefix or a.has_lock_prefix or r.mnemonic!=M.RET or r.op_count or raw[r.ip-m.addr:end-m.addr]!=b'\xc3'):continue
        hits.append((name,ty))
    return hits[0] if len(hits)==1 else None
