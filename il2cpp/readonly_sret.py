"""Public property alias for a complete static readonly struct field load."""
from il2cpp.async_start import _frame,_rr
from il2cpp.csharp import FA_INITONLY,FA_LITERAL,FA_STATIC,field_attrs
from il2cpp.equivalent_binary import _extent,_writable
from il2cpp.names import safe_ident
from il2cpp.prelude import HAVE_ICED
from il2cpp.text import sdisp
from il2cpp.x64 import KLASS_STATIC_FIELDS

if HAVE_ICED:
    from iced_x86 import Decoder,Mnemonic as M,OpKind as K,Register as R


def init_guards(lift,seq,j,saved):
    """Each cold arm does only one or more idempotent usage inits. Optional
    receiver park before the first JNE executes on both paths."""
    seen=set();park=None;flags=set()
    while j<len(seq) and seq[j].mnemonic==M.CMP:
        cmp=seq[j];j+=1
        if cmp.memory_base!=R.RIP or cmp.op1_kind!=K.IMMEDIATE8 or cmp.immediate8:return None
        if j<len(seq) and seq[j].mnemonic==M.MOV and not seen and park is None:
            park=seq[j].op0_register
            if park not in saved or not _rr(seq[j],M.MOV,park,R.RCX):return None
            j+=1
        if j>=len(seq) or seq[j].mnemonic!=M.JNE or seq[j].op0_kind!=K.NEAR_BRANCH64:return None
        branch=seq[j];j+=1;start=j
        while j+1<len(seq) and seq[j].mnemonic==M.LEA:
            lea,call=seq[j:j+2]
            if (lea.op0_register!=R.RCX or lea.memory_base!=R.RIP or call.mnemonic!=M.CALL or
                    call.op0_kind!=K.NEAR_BRANCH64 or call.near_branch_target!=lift.rt_init_meta or not lift.il.decode_slot(lea.ip_rel_memory_address)):return None
            seen.add(lea.ip_rel_memory_address);j+=2
        if j==start or j+1>=len(seq):return None
        store=seq[j];j+=1;flag=cmp.ip_rel_memory_address
        if (store.mnemonic!=M.MOV or store.memory_base!=R.RIP or store.ip_rel_memory_address!=flag or store.op1_kind!=K.IMMEDIATE8 or
                store.immediate8!=1 or branch.near_branch_target!=seq[j].ip or flag in flags):return None
        b=lift.il.bin;section=_writable(b,flag,1)
        if not section or flag<section.addr+section.rawsize and b.read(flag,1)!=b'\0':return None
        flags.add(flag)
    if seen and park is not None and not any(s<=f<s+8 for s in seen for f in flags):return j,park,seen


def plain(seq):
    return bool(seq) and all(not i.is_invalid and not i.has_segment_prefix and not i.has_rep_prefix and not i.has_repne_prefix and
                             not i.has_lock_prefix and i.memory_index==R.NONE for i in seq) and all(i.next_ip==k.ip for i,k in zip(seq,seq[1:]))


def _static_read(lift,m):
    il=lift.il;ex=_extent(il,m.addr)
    if not ex or ex[0]>256:return None
    s=list(Decoder(64,il.bin.read(m.addr,ex[0]) or b'',ip=m.addr))
    if not plain(s) or s[-1].next_ip!=m.addr+ex[0] or len(s)<13 or s[0].mnemonic!=M.PUSH:return None
    f=_frame(s[:2],s[-3:]);g=init_guards(lift,s,2,f[1]) if f else None
    if not g:return None
    j,dst,inits=g;body=s[j:-3]
    if len(body)!=7:return None
    klass,blob,xy,z,lo,hi,echo=body
    if (klass.mnemonic!=M.MOV or klass.memory_base!=R.RIP or klass.op0_register!=R.RAX or
            inits!={klass.ip_rel_memory_address} or blob.mnemonic!=M.MOV or blob.op0_register!=R.RAX or blob.memory_base!=R.RAX or
            blob.memory_displacement!=KLASS_STATIC_FIELDS or xy.mnemonic!=M.MOVSD or xy.memory_base!=R.RAX or not R.XMM0<=xy.op0_register<=R.XMM5 or
            z.mnemonic!=M.MOV or z.op0_register!=R.EAX or z.memory_base!=R.RAX or z.memory_displacement!=xy.memory_displacement+8 or
            lo.mnemonic!=M.MOVSD or lo.memory_base!=dst or lo.memory_displacement or lo.op1_register!=xy.op0_register or
            hi.mnemonic!=M.MOV or hi.memory_base!=dst or hi.memory_displacement!=8 or hi.op1_register!=R.EAX or not _rr(echo,M.MOV,R.RAX,dst)):return None
    return klass.ip_rel_memory_address,sdisp(xy.memory_displacement)


def static_value_alias(lift,method,slot,off,ty):
    il=lift.il;key=il._closed_type_key;u=il.decode_slot(slot) or {};own=u.get('td',-1)
    if u.get('kind')!=1 or not 0<=own<len(il.meta.typedefs) or not 0<=own<len(il.field_offsets) or key(u.get('type'))!=(0x11,own,0):return None
    td=il.meta.typedefs[own];width=il._sf_field_size(ty,0)
    if (width!=12 or not td.is_valuetype or td.generic_container!=-1 or td.declaring!=-1 or td.flags&7!=1 or
            td.has_cctor and not td.flags&0x100000):return None
    offsets=il.field_offsets[own];fields=[]
    if not offsets or len(offsets)!=td.field_count:return None
    for pos,fi in zip(offsets,il.meta.type_fields(td)):
        f=il.meta.fields[fi];attr=field_attrs(il,f)
        if not attr&FA_STATIC or attr&FA_LITERAL:continue
        if not 0<=f.type<len(il.types) or pos<0:return None
        ft=il.types[f.type];n=il._sf_field_size(ft,0)
        if not n or n<0:return None
        if off<pos+n and pos<off+width:
            if pos!=off or n!=width or not attr&FA_INITONLY or attr&7!=1 or key(ft)!=key(ty):return None
            fields.append(fi)
    if len(fields)!=1:return None
    getters=[]
    for mi in il.meta.type_methods(td):
        m=il.meta.methods[mi]
        if (m.declaring!=own or not m.addr or m.index==method.index or not m.is_static or m.param_count or m.generic_container!=-1 or
                m.flags&7!=6 or m.flags&0x40 or not 0<=m.return_type<len(il.types) or key(il.types[m.return_type])!=key(ty)):continue
        prop=lift._accessor_prop(mi)
        if prop and prop[0]=='get' and not prop[2] and _static_read(lift,m)==(slot,off):getters.append(safe_ident(prop[1]))
    if len(getters)==1:return il.typedef_full(own)+'.'+getters[0]
