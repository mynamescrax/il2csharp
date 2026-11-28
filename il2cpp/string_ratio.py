"""A normalized scalar score uses a signed sample and the full string lengths.

Proof covers the terminal max/clamp, conversion and Single subtraction;
leave the input guards and distance call at their original sites.
"""
import math,struct
from il2cpp.array_origin import _definitions,_graph
from il2cpp.equivalent_binary import _amd64
from il2cpp.expr import Expr,acc_get,_INT_TY,_R4_TY
from il2cpp.metadata import source_params
from il2cpp.names import safe_ident,repr_f32
from il2cpp.prelude import HAVE_ICED
from il2cpp.sret_copy import _own_field
from il2cpp.terminal_effect import _terminal_frame
from il2cpp.text import reg_name,sdisp
if HAVE_ICED:
    from iced_x86 import Mnemonic as M,OpKind as K,Register as R,RegisterExt as RX,MemorySizeExt as MS
    from il2cpp.array_origin import _INFO,_SAVED,_WRITES


def _parameter(by,pred,entry,site,r,expect,*,low32=False):
    todo=[(site,r)];seen=set();ok=False
    while todo:
        ip,reg=todo.pop()
        if (ip,reg) in seen:continue
        if len(seen)>256:return False
        seen.add((ip,reg))
        if ip==entry:
            if pred[ip] or reg!=expect:return False
            ok=True;continue
        if not pred[ip]:return False
        for p in pred[ip]:
            i=by[p]
            if i.is_call_near and reg not in _SAVED:return False
            if i.mnemonic==M.MOV and i.op0_register==reg and RX.is_gpr64(i.op1_register):todo.append((p,i.op1_register))
            elif (low32 and i.mnemonic==M.MOV and RX.is_gpr32(i.op0_register) and RX.is_gpr32(i.op1_register) and RX.full_register(i.op0_register)==reg):todo.append((p,RX.full_register(i.op1_register)))
            elif any(u.access in _WRITES and RX.full_register(u.register)==reg for u in _INFO.info(i).used_registers()):return False
            else:todo.append((p,reg))
    return ok


def _length_layout(il,disp):
    ids=[td for td in il.meta.typedefs if td.namespace=='System' and td.name=='String'];
    if len(ids)!=1:return False
    t=ids[0];field=_own_field(il,t,disp,4)
    if not field or il._closed_type_key(field[1])!=(8,0):return False
    for n in range(t.property_count):
        p=il.meta.properties[t.property_start+n];j=p[1]
        if il.meta.getstr(p[0])!='Length' or j is None or not 0<=j<t.method_count:continue
        m=il.meta.methods[t.method_start+j]
        if (m.is_static or m.param_count or not m.addr or m.flags&7!=6 or m.flags&0x40 or not 0<=m.return_type<len(il.types) or
                il._closed_type_key(il.types[m.return_type])!=(8,0) or ('method',m.index) not in il.addr_candidates.get(m.addr,())):return False
        from iced_x86 import Decoder
        s=list(Decoder(64,il.bin.read(m.addr,12) or b'',ip=m.addr))
        return (len(s)>=2 and s[0].mnemonic==M.MOV and s[0].op0_register==R.EAX and s[0].memory_base==R.RCX and
                s[0].memory_index==R.NONE and not s[0].has_segment_prefix and sdisp(s[0].memory_displacement)==disp and s[1].mnemonic==M.RET and not s[1].op_count)
    return False


def string_ratios(lift,m,td,blocks,pads):
    il=lift.il;out={};samples={}
    if (not HAVE_ICED or pads or m.is_static or m.param_count!=2 or td.is_valuetype or td.generic_container!=-1 or m.generic_container!=-1 or
            not 0<=m.return_type<len(il.types) or il._closed_type_key(il.types[m.return_type])!=(12,0)):return out,samples
    ps=source_params(il.meta,m)
    if (len(ps)!=2 or any(not 0<=p.type<len(il.types) or il._closed_type_key(il.types[p.type])!=(14,0) for p in ps)):return out,samples
    names=[safe_ident(p.name) for p in ps]
    if len(set(names))!=2 or any(n.startswith('t') and n[1:].isdigit() for n in names):return out,samples
    hits=[]
    for b in blocks:
        s=b.insns
        for j in range(len(s)-11):
            if (s[j].mnemonic==M.CMP and s[j+2].mnemonic==M.CMOVLE and s[j+4].mnemonic==M.CMOVL and s[j+9].mnemonic==M.DIVSS and s[j+11].mnemonic==M.SUBSS):hits.append((b,j))
    if not hits or not _amd64(getattr(il,'bin',None)) or il.meta.version!=31:return out,samples
    seq=[i for b in blocks for i in b.insns];by={i.ip:i for i in seq};g=_graph(il,seq);key=il._closed_type_key
    if not g or seq[0].ip!=m.addr:return out,samples
    pred,_=g
    for b,j in hits:
        s=b.insns;w=s[j:j+12];cmp,one,sel,c2,s2,top,den,fc1,fc2,div,base,sub=w
        if (any(i.has_lock_prefix or i.has_segment_prefix or i.memory_index!=R.NONE for i in w) or
                any(a.next_ip!=z.ip or pred[z.ip]!=[a.ip] for a,z in zip(w,w[1:])) or not _terminal_frame(il,seq,by,pred,sub.ip,b,j+11)):continue
        dr=cmp.op0_register;rr=cmp.memory_base;nr=one.op0_register
        if (not RX.is_gpr32(dr) or not RX.is_gpr32(nr) or dr in (R.EAX,R.ESP) or nr in (dr,R.EAX,R.ESP) or rr not in _SAVED or
                MS.size(cmp.memory_size)!=4 or one.mnemonic!=M.MOV or one.op1_kind!=K.IMMEDIATE32 or one.immediate32!=1 or
                sel.op0_register!=dr or sel.memory_base!=rr or sel.memory_displacement!=cmp.memory_displacement or MS.size(sel.memory_size)!=4 or
                (c2.mnemonic,c2.op0_register,c2.op1_register)!=(M.CMP,dr,nr) or (s2.op0_register,s2.op1_register)!=(dr,nr) or
                (top.mnemonic,top.op1_register,den.mnemonic,den.op1_register)!=(M.MOVD,R.EAX,M.MOVD,dr) or
                not R.XMM0<=top.op0_register<=R.XMM5 or not R.XMM0<=den.op0_register<=R.XMM5 or top.op0_register==den.op0_register or
                (fc1.mnemonic,fc1.op0_register,fc1.op1_register)!=(M.CVTDQ2PS,den.op0_register,den.op0_register) or
                (fc2.mnemonic,fc2.op0_register,fc2.op1_register)!=(M.CVTDQ2PS,top.op0_register,top.op0_register) or
                (div.op0_register,div.op1_register)!=(top.op0_register,den.op0_register) or base.mnemonic!=M.MOVSS or base.op0_register!=R.XMM0 or
                base.memory_base!=R.RIP or top.op0_register==R.XMM0 or (sub.op0_register,sub.op1_register)!=(R.XMM0,top.op0_register)):continue
        defs=_definitions(by,pred,m.addr,cmp.ip,RX.full_register(dr));q=_definitions(by,pred,m.addr,cmp.ip,R.RAX)
        if len(defs)!=1 or len(q)!=1:continue
        ip,r=defs.pop();load=by[ip];p,r=q.pop();call=by[p];offset=sdisp(cmp.memory_displacement)
        if (r!=R.RAX or not call.is_call_near or load.mnemonic!=M.MOV or load.op0_register!=dr or load.memory_base not in _SAVED or
                load.memory_displacement!=cmp.memory_displacement or load.memory_index!=R.NONE or load.has_segment_prefix or
                not p<load.ip<cmp.ip or not _length_layout(il,offset)):continue
        prefix=[i for i in seq if p<=i.ip<=cmp.ip]
        if (len(prefix)!=7 or prefix[3].ip!=load.ip or
                any(u.next_ip!=v.ip or pred[v.ip]!=[u.ip] for u,v in zip(prefix,prefix[1:]))):continue
        for t,br,base_reg in ((prefix[1],prefix[2],load.memory_base),(prefix[4],prefix[5],rr)):
            raiser=by.get(br.near_branch_target)
            if (t.mnemonic!=M.TEST or t.op0_register!=t.op1_register or t.op0_register!=base_reg or br.mnemonic!=M.JE or
                    not raiser or not raiser.is_call_near or lift._named_raise_throw(raiser.near_branch_target,lift._call_name(raiser.near_branch_target))!='System.NullReferenceException'):break
        else:
            raiser=True
        if raiser is not True:continue
        ids=il.addr_candidates.get(call.near_branch_target,());
        if len(ids)!=1 or ids[0][0]!='method' or not 0<=ids[0][1]<len(il.meta.methods):continue
        f=il.meta.methods[ids[0][1]];fp=il.meta.method_params(f)
        if (f.addr!=call.near_branch_target or f.generic_container!=-1 or f.is_static or f.declaring!=td.index or f.param_count!=len(fp) or
                len(fp)!=2 or not 0<=f.return_type<len(il.types) or key(il.types[f.return_type])!=(8,0) or
                any(not 0<=z.type<len(il.types) or key(il.types[z.type])!=(14,0) for z in fp)):continue
        if not all(_parameter(by,pred,m.addr,ip,r,slot) for ip,r,slot in ((load.ip,load.memory_base,R.RDX),(cmp.ip,rr,R.R8),(call.ip,R.RCX,R.RCX),(call.ip,R.RDX,R.RDX),(call.ip,R.R8,R.R8))):continue
        addr=base.ip_rel_memory_address
        if not any(s.addr<=addr<=s.addr+min(s.rawsize,s.size)-4 and not s.chars&0x80000000 for s in il.bin.sections):continue
        raw=il.bin.read(addr,4);v=struct.unpack('<f',raw)[0] if raw and len(raw)==4 else float('nan')
        if not math.isfinite(v) or not v:continue
        out[cmp.ip]=(p,reg_name(rr),names,repr_f32(v));samples[p]=f.index
    return out,samples


def string_score(l,i,plan):
    pos,rr,names,base=plan;x=dict.get(l.regs,'RAX');b=dict.get(l.regs,rr)
    if (not x or x._unk or l._sample_call_values.get(pos) is not x or l.il._closed_type_key(x.ty)!=(8,0) or
            not b or b._unk or b.text!=names[1] or l.il._closed_type_key(b.ty)!=(14,0)):return False
    av,bv,n=l.new_var(),l.new_var(),l.new_var()
    for t in (av,bv,n):l._type_hints[t]=l._var_types[t]=_INT_TY
    l.emit(i.ip,f'var {av} = {acc_get(names[0]+".Length")};',None);l.emit(i.ip,f'var {bv} = {acc_get(names[1]+".Length")};',None)
    l.emit(i.ip,f'var {n} = global::System.Math.Max(1, global::System.Math.Max({av}, {bv}));',None)
    l.set_reg('XMM0',Expr(f'({base} - (float)({x.text}) / (float)({n}))',_R4_TY,'float'));l.flags=None;return True
