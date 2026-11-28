"""Two scaled scalar lanes of a returned struct packed into a qword result.

An inlined slice of a private nested value must use the public getter only
when its complete registered body is the same 8+4 field copy.
"""
import math,re,struct
from il2cpp.array_origin import _graph,_definitions
from il2cpp.copied_getter import _field_getter
from il2cpp.field_slice import field_offset
from il2cpp.equivalent_binary import _amd64
from il2cpp.expr import Expr,acc_get,_R4_TY
from il2cpp.metadata import source_params
from il2cpp.names import repr_f32,safe_ident
from il2cpp.packed_call import _float_fields
from il2cpp.packed_projection import _field
from il2cpp.prelude import HAVE_ICED
from il2cpp.saved_binary import _frame_at
from il2cpp.sret_copy import _own_field
from il2cpp.terminal_effect import _terminal_frame
from il2cpp.text import sdisp
if HAVE_ICED:
    from iced_x86 import Mnemonic as M,Register as R,OpKind as K,MemorySizeExt as MS


def _floats(il,owner,a,b):
    match=[]
    for lo in (a,a-4,a-8):
        if lo<0 or a-lo not in (0,4,8) or b-lo not in (0,4,8):continue
        q=_own_field(il,owner,16+lo,12)
        if q and len(names:=_float_fields(il,q[1]) or ())==3:match.append((lo,q[1],names[(a-lo)//4],names[(b-lo)//4]))
    return match[0] if len(match)==1 else None


def _alias(lift,td,off,ty):
    il=lift.il;qs=[]
    for mi in il.meta.type_methods(td):
        m=il.meta.methods[mi];p=lift._accessor_prop(mi)
        if (m.addr and m.declaring==td.index and not m.is_static and not m.param_count and not m.flags&0x40 and m.generic_container==-1 and
                m.flags&7==6 and 0<=m.return_type<len(il.types) and il._closed_type_key(il.types[m.return_type])==il._closed_type_key(ty) and
                p and p[0]=='get' and not p[2] and p[1].isidentifier() and safe_ident(p[1])==p[1] and field_offset(il,m.addr)==off and
                _field_getter(lift,m.addr,td,'value',off)==(mi,'value.'+p[1])):qs.append(p[1])
    return qs[0] if len(qs)==1 else None


def project_sites(lift,m,td,blocks,pads):
    out={};il=lift.il
    if not HAVE_ICED or pads or td.generic_container!=-1 or m.generic_container!=-1 or not 0<=m.return_type<len(il.types):return out
    wins=[]
    for block in blocks:
        s=block.insns
        for j in range(1,len(s)-5):
            a,b,x,y,pack,move=s[j:j+6]
            if (a.mnemonic==b.mnemonic==M.MOVSS and s[j-1].is_call_near and a.memory_base==b.memory_base==R.RAX and
                    x.mnemonic==y.mnemonic==M.MULSS and pack.mnemonic==M.UNPCKLPS and move.mnemonic==M.MOVQ and move.op0_register==R.RAX):wins.append((block,j))
    if not wins or not _amd64(getattr(il,'bin',None)) or il.meta.version!=31:return out
    rt=il.types[m.return_type];key=il._closed_type_key
    if not rt or key(rt)!=(0x11,rt[0],0) or not 0<=rt[0]<len(il.meta.typedefs) or il.value_type_size(rt[0])!=8 or il.returns_sret(rt):return out
    dest=il.meta.typedefs[rt[0]];ds=_float_fields(il,rt)
    if not ds or len(ds)!=2 or dest.generic_container!=-1 or any(n.startswith('t') and n[1:].isdigit() for n in (safe_ident(p.name) for p in source_params(il.meta,m))):return out
    seq=[i for b in blocks for i in b.insns];by={i.ip:i for i in seq};graph=_graph(il,seq,chained=True,nested_chains=True)
    if not graph:return out
    pred,_=graph
    for block,j in wins:
        s=block.insns;call,a,b,x,y,pack,move=s[j-1:j+6];regs=(a.op0_register,b.op0_register)
        if (s[-1].mnemonic!=M.RET or s[-1].op_count or s[-1].stack_pointer_increment!=8 or
                not _terminal_frame(il,seq,by,pred,move.ip,block,j+5) or
                any(i.has_segment_prefix or i.has_lock_prefix or i.memory_index!=R.NONE for i in s[j-1:j+6]) or
                any(u.next_ip!=v.ip or pred[v.ip]!=[u.ip] for u,v in zip(s[j-1:j+5],s[j:j+6])) or
                not all(R.XMM0<=reg<=R.XMM5 for reg in regs) or regs[0]==regs[1] or (x.op0_register,y.op0_register)!=regs or
                (pack.op0_register,pack.op1_register)!=regs or move.op1_register!=regs[0] or
                any(i.op1_kind!=K.MEMORY or MS.size(i.memory_size)!=4 for i in (a,b,x,y)) or x.memory_base!=R.RIP or y.memory_base!=R.RIP):continue
        ids=il.addr_candidates.get(call.near_branch_target,())
        if len(ids)!=1 or ids[0][0]!='method' or not 0<=ids[0][1]<len(il.meta.methods):continue
        md=il.meta.methods[ids[0][1]];p=lift._accessor_prop(md.index)
        if (not p or p[0]!='get' or p[2] or md.addr!=call.near_branch_target or md.generic_container!=-1 or md.param_count or md.is_static or md.flags&0x40 or
                not 0<=md.return_type<len(il.types)):continue
        src=il.types[md.return_type]
        if not src or key(src)!=(0x11,src[0],0) or not 0<=src[0]<len(il.meta.typedefs) or not il.returns_sret(src):continue
        owner=il.meta.typedefs[src[0]];row=_floats(il,owner,sdisp(a.memory_displacement),sdisp(b.memory_displacement))
        if not row:continue
        off,inner,lo,hi=row;alias=_alias(lift,owner,off,inner)
        if not alias:continue
        home=_definitions(by,pred,m.addr,call.ip,R.RCX);frame=_frame_at(il,seq,by,pred,call.ip)
        if len(home)!=1 or not frame:continue
        ip,r=home.pop();h=by[ip];size=il.value_type_size(owner.index);n=sdisp(h.memory_displacement)
        if (h.op0_register!=r or h.mnemonic!=M.LEA or h.memory_base!=R.RSP or h.memory_index!=R.NONE or h.has_segment_prefix or
                not size or not 32<=n<=frame[0]-size or any(start<n+size and n<start+length for start,length in frame[2])):continue
        scales=[]
        for i in (x,y):
            p=i.ip_rel_memory_address
            if not any(t.addr<=p<=t.addr+min(t.rawsize,t.size)-4 and not t.chars&0x80000000 for t in il.bin.sections):break
            data=il.bin.read(p,4)
            if not data or len(data)!=4:break
            v=struct.unpack('<f',data)[0]
            if not math.isfinite(v) or not v:break
            literal=repr_f32(v)
            if struct.pack('<f',float(literal.rstrip('fF')))!=data:break
            scales.append(literal)
        if len(scales)==2:out[a.ip]=(call.ip,src,n-frame[1],alias,inner,lo,hi,scales,rt,ds)
    return out


def project_result(l,i,plan):
    producer,ty,home,prop,inner,a,b,scale,rt,fields=plan;e=dict.get(l.regs,'RAX')
    if (not e or l._last_sret!=(producer,e) or e.kind!='ptr' or e.ty!=ty or not re.fullmatch(r'&t\d+',e.text) or
            getattr(e,'_stack_offset',None)!=home or l.slot_types.get(e.text[1:])!=ty):return False
    name=l.new_var();l._var_types[name]=l._type_hints[name]=inner;l.emit(i.ip,'var %s = %s;'%(name,acc_get(e.text[1:]+'.'+prop)),None)
    tmp=l.new_var();l._var_types[tmp]=l._type_hints[tmp]=rt;l.emit(i.ip,'var %s = default(%s);'%(tmp,l.il.type_name(rt)),None)
    for dest,field,f in zip(fields,(a,b),scale):l.emit(i.ip,f'{tmp}.{dest} = {name}.{field} * {f};',None)
    l.set_reg('RAX',Expr(tmp,rt,'obj'));return True
