"""An inline string length comparison reads a dword, not a byte.

Resolve the read at the CMP, only for unchanged string and Int32 arguments
and an immediately consuming signed branch. The ordinary branch and the
full-width substring loop use the same length semantics.
"""
from il2cpp.array_origin import _graph
from il2cpp.equivalent_binary import _amd64
from il2cpp.metadata import source_params
from il2cpp.names import safe_ident
from il2cpp.prelude import HAVE_ICED
from il2cpp.string_ratio import _parameter,_length_layout
from il2cpp.text import sdisp,reg_name

if HAVE_ICED:
    from iced_x86 import Mnemonic as M,OpKind as K,Register as R,RegisterExt as RX,MemorySizeExt as MS


def bound_sites(l,m,blocks,pads):
    il=l.il;out={}
    if (not HAVE_ICED or pads or not 2<=m.param_count<=4 or m.generic_container!=-1 or
            not 0<=m.return_type<len(il.types) or not 0<=m.declaring<len(il.meta.typedefs)):return out
    ps=source_params(il.meta,m);td=il.meta.typedefs[m.declaring]
    if td.generic_container!=-1 or td.is_valuetype or len(ps)!=m.param_count:return out
    homes=(R.RCX,R.RDX,R.R8,R.R9);start=int(not m.is_static)+int(il.returns_sret(il.types[m.return_type]))
    ss=[];ns=[]
    for k,p in enumerate(ps,start):
        if k>=4 or not 0<=p.type<len(il.types):continue
        key=il._closed_type_key(il.types[p.type]);name=safe_ident(p.name)
        if key==(14,0):ss.append((homes[k],name))
        elif key==(8,0):ns.append((homes[k],name))
    if len(ss)!=1 or len(ns)!=1:return out
    windows=[]
    for b in blocks:
        if len(b.insns)<2:continue
        cmp,br=b.insns[-2:]
        if (cmp.mnemonic==M.CMP and br.mnemonic in (M.JL,M.JLE,M.JG,M.JGE) and br.op0_kind==K.NEAR_BRANCH64 and
                cmp.op0_kind==K.MEMORY and cmp.op1_kind==K.REGISTER and RX.is_gpr32(cmp.op1_register) and
                MS.size(cmp.memory_size)==4 and RX.is_gpr64(cmp.memory_base) and not cmp.has_segment_prefix and not cmp.has_lock_prefix and
                cmp.memory_index==R.NONE and cmp.next_ip==br.ip):windows.append((cmp,br))
    if not windows or not _amd64(il.bin) or il.meta.version!=31:return out
    seq=[i for b in blocks for i in b.insns];by={i.ip:i for i in seq};g=_graph(il,seq,chained=True,nested_chains=True)
    if not g or seq[0].ip!=m.addr:return out
    pred,_=g
    for i,j in windows:
        sr,s=ss[0];nr,n=ns[0]
        if (pred[j.ip]!=[i.ip] or not _parameter(by,pred,m.addr,i.ip,i.memory_base,sr) or
                not _parameter(by,pred,m.addr,i.ip,RX.full_register(i.op1_register),nr,low32=True)):continue
        off=sdisp(i.memory_displacement)
        if _length_layout(il,off):out[i.ip]=(s,n)
    return out


def difference_sites(l,m,blocks,bounds):
    if not bounds:return {}
    seq=[i for b in blocks for i in b.insns];by={i.ip:i for i in seq};pred,_=_graph(l.il,seq,chained=True,nested_chains=True);out={}
    for site,names in bounds.items():
        origin=by[site];base=int(not m.is_static)+int(l.il.returns_sret(l.il.types[m.return_type]));args=source_params(l.il.meta,m)
        if len({safe_ident(p.name) for p in args})!=len(args):continue
        slots={safe_ident(p.name):r for p,r in zip(args,(R.RCX,R.RDX,R.R8,R.R9)[base:])}
        for b in blocks:
            if len(b.insns)<4:continue
            load,sub,cmp,j=b.insns[-4:];r=load.op0_register
            if (load.mnemonic!=M.MOV or load.op1_kind!=K.MEMORY or load.memory_index!=R.NONE or load.has_segment_prefix or
                    load.memory_base!=origin.memory_base or load.memory_displacement!=origin.memory_displacement or not RX.is_gpr32(r) or
                    sub.mnemonic!=M.SUB or sub.op0_register!=r or sub.op1_register!=origin.op1_register or
                    cmp.mnemonic!=M.CMP or not RX.is_gpr32(cmp.op0_register) or cmp.op1_register!=r or j.mnemonic not in (M.JG,M.JGE) or
                    any(a.next_ip!=v.ip or pred[v.ip]!=[a.ip] for a,v in ((load,sub),(sub,cmp),(cmp,j)))):continue
            if (_parameter(by,pred,m.addr,load.ip,load.memory_base,slots[names[0]]) and
                    _parameter(by,pred,m.addr,sub.ip,RX.full_register(sub.op1_register),slots[names[1]],low32=True)):
                out[sub.ip]=names
    return out
