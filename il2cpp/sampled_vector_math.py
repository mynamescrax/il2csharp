"""A scalar broadcast sampled between two return-buffer getters, and an
unordered branch on a later component of a complete return value."""
from il2cpp.accessor_chain import _property
from il2cpp.array_origin import _graph
from il2cpp.closed_lookup import _receiver
from il2cpp.equivalent_binary import _amd64
from il2cpp.metadata import source_params
from il2cpp.names import safe_ident
from il2cpp.packed_call import _float_fields
from il2cpp.prelude import HAVE_ICED
from il2cpp.sret_copy import _own_field
from il2cpp.text import sdisp
if HAVE_ICED:
    from iced_x86 import Mnemonic as M,OpKind as K,Register as R,RegisterExt as RX,MemorySizeExt as MS


def vector_polls(l,m,td,blocks,pads):
    fields={};branches={};il=l.il
    if not HAVE_ICED or pads or m.is_static or td.is_valuetype or m.generic_container!=-1 or td.generic_container!=-1:return fields,branches
    s=[i for b in blocks for i in b.insns];hits=[];tests=[]
    for j,i in enumerate(s):
        if j+13<len(s) and i.is_call_near and s[j+13].is_call_near and s[j+13].near_branch_target==i.near_branch_target and s[j+10].mnemonic==M.MULSS:hits.append(s[j:j+14])
        if j+3<len(s) and i.is_call_near and s[j+1].mnemonic==M.XORPS and s[j+2].mnemonic in (M.COMISS,M.UCOMISS) and s[j+3].mnemonic==M.JBE:tests.append(s[j:j+4])
    if not (hits or tests) or not _amd64(il.bin) or il.meta.version!=31 or any(n.startswith('t') and n[1:].isdigit() for n in (safe_ident(p.name) for p in source_params(il.meta,m))):return fields,branches
    g=_graph(il,s,chained=True,nested_chains=True,allow_tail=True,runtime_tails=l.rt_wbarrier);by={i.ip:i for i in s}
    if not g or s[0].ip!=m.addr:return fields,branches
    pred,_=g
    def chain(w):return not any(i.has_lock_prefix or i.has_segment_prefix or i.memory_index!=R.NONE for i in w) and all(a.next_ip==b.ip and pred[b.ip]==[a.ip] for a,b in zip(w,w[1:]))
    for w in hits:
        a,gain,xy,z,cp,shuffle,cp2,my,mx,spill,mz,zero,home,b=w;ids=il.addr_candidates.get(a.near_branch_target,())
        if not chain(w) or len(ids)!=1 or ids[0][0]!='method' or not 0<=ids[0][1]<len(il.meta.methods):continue
        q=il.meta.methods[ids[0][1]];prop=l._accessor_prop(q.index)
        if (q.addr!=a.near_branch_target or not q.is_static or q.param_count or q.generic_container!=-1 or not prop or prop[0]!='get' or prop[2] or
                not 0<=q.return_type<len(il.types) or len(_float_fields(il,il.types[q.return_type]) or ())!=3 or not il.returns_sret(il.types[q.return_type])):continue
        f=gain.op0_register;tmp=xy.op0_register;zr=z.op0_register;yr=cp.op0_register;xr=cp2.op0_register
        if (gain.mnemonic!=M.MOVSS or gain.op1_kind!=K.MEMORY or not RX.is_xmm(f) or not _receiver(il,m,by,pred,gain.ip,td.index,initial=gain.memory_base,this_only=True) or
                xy.mnemonic!=M.MOVSD or xy.memory_base!=R.RAX or xy.memory_displacement or z.mnemonic!=M.MOVSS or z.memory_base!=R.RAX or z.memory_displacement!=8 or
                not RX.is_xmm(tmp) or not all(R.XMM6<=r<=R.XMM15 for r in (zr,xr,yr)) or len({f,tmp,zr,yr,xr})!=5 or
                cp.mnemonic!=M.MOVAPS or cp.op1_register!=tmp or cp2.mnemonic!=M.MOVAPS or cp2.op1_register!=tmp or
                shuffle.mnemonic!=M.SHUFPS or shuffle.op0_register!=yr or shuffle.op1_register!=yr or shuffle.immediate8!=0x55 or
                any(i.mnemonic!=M.MULSS or i.op0_register!=r or i.op1_register!=f for i,r in ((my,yr),(mx,xr),(mz,zr))) or
                spill.mnemonic!=M.MOVSD or spill.op0_kind!=K.MEMORY or spill.memory_base!=R.RSP or spill.op1_register!=tmp or
                zero.mnemonic!=M.XOR or zero.op0_register!=zero.op1_register or zero.op0_register!=R.EDX or
                home.mnemonic!=M.LEA or home.op0_register!=R.RCX or home.memory_base!=R.RSP or home.memory_displacement!=spill.memory_displacement):continue
        killed=by.get(b.next_ip)
        if not killed or pred[killed.ip]!=[b.ip] or killed.mnemonic!=M.MOVSD or killed.op0_register!=f or killed.memory_base!=R.RAX or killed.memory_displacement:continue
        fld=_own_field(il,td,sdisp(gain.memory_displacement),4)
        if fld and il._closed_type_key(fld[1])==(12,0):fields[gain.ip]=fld
    for w in tests:
        call,z,cmp,j=w;get=_property(l,call);off=sdisp(cmp.memory_displacement)
        if (not chain(w) or not get or not il.returns_sret(get[2]) or z.op0_register!=z.op1_register or not RX.is_xmm(z.op0_register) or
                cmp.op0_register!=z.op0_register or cmp.memory_base!=R.RAX or cmp.op1_kind!=K.MEMORY or MS.size(cmp.memory_size)!=4 or off<0 or off%4):continue
        fs=_float_fields(il,get[2])
        if fs and off//4<len(fs):branches[j.ip]=(call.ip,get[2],fs[off//4])
    return fields,branches


def unordered_component(l,plan,lhs,rhs):
    ip,ty,field=plan;e=dict.get(l.regs,'RAX')
    if (e and l._last_sret==(ip,e) and e.ty==ty and e.kind=='ptr' and e.text.startswith('&t') and e.text[2:].isdigit() and
            lhs and not lhs._unk and lhs.text in ('0.0f','0f') and rhs and not rhs._unk and rhs.text==e.text[1:]+'.'+field and
            l.il._closed_type_key(rhs.ty)==(12,0)):
        return f'(({rhs.text}) < 0f) == false'
