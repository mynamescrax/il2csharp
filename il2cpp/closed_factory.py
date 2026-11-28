"""Closed Win64 factories taking a saved reference and two by-value aggregates.

This is a whole-wrapper proof. Follow preserved GPRs, actual R9 MethodRef,
and all outgoing argument bytes. Only the accepted input reads and calls
are observable; the two private copies cannot acquire a different lifetime.
"""
from bisect import bisect_right
from struct import pack
from il2cpp.array_origin import _graph
from il2cpp.awaiter import _spec_entry
from il2cpp.csharp import declares_member_name,source_field_name
from il2cpp.equivalent_binary import _amd64,_extent,_writable
from il2cpp.generic_array import object_shared_entry
from il2cpp.names import safe_ident
from il2cpp.packed_call import _float_fields
from il2cpp.prelude import HAVE_ICED
from il2cpp.readonly_sret import static_value_alias,_static_read
from il2cpp.shared_field import reference_field_at
from il2cpp.stack_local_frame import _saves,_epilogue,_slot_move
from il2cpp.text import sdisp
from il2cpp.x64 import KLASS_STATIC_FIELDS,KLASS_INITIALIZED

if HAVE_ICED:
    from iced_x86 import Decoder,Mnemonic as M,OpKind as K,Register as R,RegisterExt as RX,MemorySizeExt as MS
    from il2cpp.array_origin import _INFO,_WRITES,_SAVED


def _signature(il,methodref,va):
    info=il.decode_slot(methodref) or {};spec=info.get('idx',-1)
    if info.get('kind')!=6 or not 0<=spec<len(il.method_specs):return None
    mi,ci,gi=il.method_specs[spec]
    if ci!=-1 or not 0<=mi<len(il.meta.methods) or gi<0:return None
    f=il.meta.methods[mi];ps=il.meta.method_params(f);args=il._method_spec_type_args(gi);key=il._closed_type_key
    if (not f.is_static or f.flags&7!=6 or f.flags&(0x40|0x800) or not f.name.isidentifier() or safe_ident(f.name)!=f.name or
            not 0<=f.generic_container<len(il.meta.generic_containers) or not 0<=f.declaring<len(il.meta.typedefs) or
            not 0<=f.return_type<len(il.types) or len(ps)!=f.param_count or len(ps)!=3 or not all(0<=p.type<len(il.types) for p in ps) or len(args or ())!=1):return None
    ret=il.types[f.return_type];original,a,b=(il.types[p.type] for p in ps);owner=il.meta.typedefs[f.declaring]
    if not all((ret,original,a,b,args[0])):return None
    gp=ret[0]
    if (owner.generic_container!=-1 or owner.flags&7!=1 or owner.declaring!=-1 or not 0<=gp<len(il.meta.generic_parameters) or
            tuple(il.meta.generic_containers[f.generic_container])!=(mi,1,1,gp) or il.meta.generic_parameters[gp][0]!=f.generic_container or
            il.meta.generic_parameters[gp][4]!=0 or il._type_enum(ret)!=0x1e or il._type_enum(original)!=0x1e or original[0]!=gp or
            (ret[1]|original[1])&(1<<29) or key(args[0])!=(0x12,args[0][0],0) or not 0<=args[0][0]<len(il.meta.typedefs) or
            il.meta.typedefs[args[0][0]].generic_container!=-1 or len(_float_fields(il,a) or ())!=3 or len(_float_fields(il,b) or ())!=4):return None
    direct=_spec_entry(il,spec,mi)
    if (direct!=va if spec in il._awaiter_spec_indices[mi] else object_shared_entry(il,mi)!=va):return None
    return spec,f,args[0],a,b


def _frame(il,m,s):
    base=il.bin.image_base;index=bisect_right(il._eh4_begins,m.addr-base)-1;k=next((n for n,i in enumerate(s[:8]) if i.mnemonic==M.SUB and i.op0_register==R.RSP),None)
    if index<0 or k is None or s[k].op1_kind not in (K.IMMEDIATE32TO64,K.IMMEDIATE8TO64):return None
    row=il._eh4_entries[index];a,e,u=row;h=il.bin.read(base+u,4)
    if base+a!=m.addr or not h or h[0]!=1 or h[3]:return None
    raw=il.bin.read(base+u,4+h[2]*2);f=_saves(s,k,raw) if raw and len(raw)==4+2*h[2] else None
    if not f:return None
    size,depth,spans,push,moves,late=f;spans=list(spans);moves=list(moves);late=dict(late);end=s[-1].next_ip-base
    while e<end:
        index+=1
        if index==len(il._eh4_entries):return None
        a,z,u=il._eh4_entries[index];h=il.bin.read(base+u,4) or b''
        if (a!=e or not a<z<=end or len(h)!=4 or h[0]!=0x21 or h[3] or h[2]%2 or
                il.bin.read(base+u+4+h[2]*2,12)!=pack('<III',*row)):return None
        tail=il.bin.read(base+u+4,h[2]*2) or b'';prev=256
        if len(tail)!=2*h[2] or (h[1]!=(tail[0] if tail else 0)):return None
        for j in range(0,len(tail),4):
            n,tag=tail[j:j+2];off=int.from_bytes(tail[j+2:j+4],'little')*16
            found=next((i for i in s if i.next_ip==base+a+n),None)
            if not found or not 0<n<prev or tag&15!=8:return None
            reg=R.XMM0+(tag>>4);move=(reg,off,16)
            if (_slot_move(found)!=move or not R.XMM6<=reg<=R.XMM15 or off%16 or not 32<=off<=size-16 or
                    any(reg==x[0] for x in moves) or any(t<off+16 and off<t+w for t,w in spans)):return None
            prev=n;moves.append(move);spans.append((off,16));late[found.ip]=move
        e=z
    if e!=end:return None
    returns=[n for n,i in enumerate(s) if i.mnemonic==M.RET]
    if len(returns)!=1 or s[returns[0]].op_count or s[returns[0]].stack_pointer_increment!=8:return None
    epi=_epilogue(s,returns[0],size,push,moves)
    if epi is None:return None
    return k,epi,returns[0],size,spans,late,set(push)|{r for r,_,_ in moves}


def _usage_guards(lift,s,pred):
    """Only erase the flag protocol; intervening hot-path reads still run."""
    il=lift.il;skip=set();ready={};flags={}
    for j,i in enumerate(s):
        if not (i.mnemonic==M.CMP and i.memory_base==R.RIP and MS.size(i.memory_size)==1 and i.op1_kind==K.IMMEDIATE8 and not i.immediate8):continue
        flag=i.ip_rel_memory_address;sec=_writable(il.bin,flag,1)
        if not sec or flag in flags or flag<sec.addr+sec.rawsize and il.bin.read(flag,1)!=b'\0':return None
        n=j+1
        while n<len(s) and n<=j+8 and s[n].mnemonic in (M.MOV,M.MOVAPS,M.MOVUPS,M.MOVSD):n+=1
        if n>=len(s) or s[n].mnemonic!=M.JNE:return None
        jump=s[n];cold=[];slots=[];n+=1
        while n+1<len(s) and s[n].mnemonic==M.LEA:
            get,call=s[n:n+2];v=get.ip_rel_memory_address
            if (get.op0_register!=R.RCX or get.memory_base!=R.RIP or not call.is_call_near or call.near_branch_target!=lift.rt_init_meta or
                    (il.decode_slot(v) or {}).get('kind') not in (1,6)):return None
            slots.append(v);cold.extend((get.ip,call.ip));n+=2
        if not slots or len(slots)!=len(set(slots)) or n>=len(s):return None
        z=s[n]
        if (z.mnemonic!=M.MOV or z.memory_base!=R.RIP or z.ip_rel_memory_address!=flag or z.op1_kind!=K.IMMEDIATE8 or z.immediate8!=1 or
                z.next_ip!=jump.near_branch_target):return None
        chain=[jump.ip,*cold,z.ip]
        if (any(pred[v]!=[u] for u,v in zip(chain,chain[1:])) or set(pred[z.next_ip])!={jump.ip,z.ip} or
                any(pred[s[nn].ip]!=[s[nn-1].ip] for nn in range(j+1,j+1+next(k for k,ins in enumerate(s[j+1:]) if ins.ip==jump.ip)+1))):return None
        skip.update([i.ip,jump.ip,*cold,z.ip]);ready[z.next_ip]=set(slots);flags[flag]=set(slots)
    if any(any(v<=f<v+8 for v in us) for f in flags for us in ready.values()):return None
    return skip,ready,flags


def _alias(lift,m,slot,off,ty,flags):
    il=lift.il;alias=static_value_alias(lift,m,slot,off,ty)
    if not alias:return None
    td=il.meta.typedefs[ty[0]];matches=[]
    for mi in il.meta.type_methods(td):
        q=il.meta.methods[mi];p=lift._accessor_prop(mi)
        if (not p or p[0]!='get' or p[2] or il.typedef_full(td.index)+'.'+safe_ident(p[1])!=alias or
                not q.addr or not q.is_static or q.param_count or _static_read(lift,q)!=(slot,off)):continue
        extent=_extent(il,q.addr);gs=list(Decoder(64,il.bin.read(q.addr,extent[0]),ip=q.addr))
        used=[i.ip_rel_memory_address for i in gs if i.mnemonic==M.CMP and i.memory_base==R.RIP]
        if len(used)!=1:return None
        flag=used[0]
        if flag in flags and flags[flag]!={slot}:return None
        if any(p<=flag<p+8 for group in flags.values() for p in group):return None
        matches.append(alias)
    return matches[0] if len(matches)==1 else None


def _ref_getter(lift,call,recvty,rt):
    il=lift.il;ids=il.addr_candidates.get(call.near_branch_target,())
    if len(ids)!=1 or ids[0][0]!='method' or not 0<=ids[0][1]<len(il.meta.methods):return None
    m=il.meta.methods[ids[0][1]];p=lift._accessor_prop(m.index);chain=il.base_chain_tds(recvty[0])
    if (m.addr!=call.near_branch_target or m.is_static or m.param_count or m.flags&7!=6 or m.flags&0x40 or m.generic_container!=-1 or
            not 0<=m.return_type<len(il.types) or not p or p[0]!='get' or p[2] or m.name!='get_'+p[1] or
            not p[1].isidentifier() or safe_ident(p[1])!=p[1] or m.declaring not in chain or
            any(declares_member_name(il,il.meta.typedefs[t],p[1]) for t in chain[:chain.index(m.declaring)])):return None
    ty=il.types[m.return_type];key=il._closed_type_key(ty)
    if (rt is not None and key!=il._closed_type_key(rt) or rt is None and key!=(0x12,ty[0],0)):return None
    return p[1],ty


def _class_init(il,target):
    b=il.bin;exports=[a for a,n in b.exports.items() if n=='il2cpp_runtime_class_init']
    if len(exports)!=1:return False
    def final(p):
        raw=b.read(p,5) if b.is_exec_va(p) else None
        return p+5+int.from_bytes(raw[1:],'little',signed=True) if raw and len(raw)==5 and raw[0]==0xe9 else p
    return b.is_exec_va(target) and final(target)==final(exports[0])


def closed_factory(lift,m,td,blocks,s,pads):
    if (not HAVE_ICED or pads or m.is_static or m.param_count or m.generic_container!=-1 or td.is_valuetype or td.generic_container!=-1 or
            not 25<=len(s)<=90 or not _amd64(getattr(lift.il,'bin',None)) or lift.il.meta.version!=31):return None
    il=lift.il;key=il._closed_type_key
    if (not 0<=m.return_type<len(il.types) or key(il.types[m.return_type])!=(1,0) or
            not any(i.op0_register==R.R9 and i.mnemonic==M.MOV and i.memory_base==R.RIP for i in s) or
            any(i.is_invalid or i.has_segment_prefix or i.has_lock_prefix or i.memory_index!=R.NONE for i in s) or
            any(a.next_ip!=b.ip for a,b in zip(s,s[1:]))):return None
    graph=_graph(il,s,chained=True,nested_chains=True)
    if not graph:return None
    frame=_frame(il,m,s)
    if not frame:return None
    k,epi,ret,size,spans,late,saved=frame
    if epi<=k+5 or not s[epi-1].is_call_near:return None
    call=s[epi-1];load9=next((i for i in reversed(s[k+1:epi-1]) if i.op0_register==R.R9),None)
    if not load9 or load9.mnemonic!=M.MOV or load9.memory_base!=R.RIP:return None
    sig=_signature(il,load9.ip_rel_memory_address,call.near_branch_target)
    if not sig:return None
    spec,f,original,pos,rot=sig
    guards=_usage_guards(lift,s,graph[0])
    if not guards:return None
    skip,ready,flags=guards;decl=il.typedef_full(f.declaring);names=[il.type_name(t) for t in (original,pos,rot)]
    if any(not all(p.isidentifier() and safe_ident(p)==p for p in n.split('.')) for n in (*names,decl)):return None
    # In a generic factory wrapper no incoming stack pointer is allowed to
    # escape. The sole visible parameter is entry RCX (this); code below
    # recognizes every instruction on both cold and normal paths.
    regs={R.RCX:('ref','this',(td.index,0x12<<16))}; lines=[];init=set();stores={};borrows={};guard_at=None;null_exit=None
    inputs={};aliases={};class_init=False;stages=[];echo_loads=set();available=saved-{r for r,_,_ in late.values()}
    def reg(r):return regs.get(RX.full_register(r))
    def put(r,v):regs[RX.full_register(r)]=v
    def validhome(off,n):return off%16==0 and 32<=off<=size-n and all(base>=off+n or off>=base+w for base,w in spans)
    def clobber():
        for r in (R.RAX,R.RCX,R.RDX,R.R8,R.R9,R.R10,R.R11,*range(R.XMM0,R.XMM0+6)):regs.pop(RX.full_register(r),None)
    def value(ty,name,order,expr):
        if name in inputs:return False
        inputs[name]=ty;stages.append(order);lines.append('global::%s %s = %s;'%(il.type_name(ty),name,expr));return True
    for n in range(k+1,epi):
        i=s[n];op=i.mnemonic;a,b=i.op0_register,i.op1_register;off=sdisp(i.memory_displacement);base=reg(i.memory_base) if i.memory_base!=R.NONE else None
        init.update(ready.get(i.ip,()))
        if i.ip in skip:
            if i.is_call_near:
                # Cold path destroys volatile registers; the admitted
                # hot path must not depend on any such old value later.
                clobber()
            continue
        if i.ip in late:available.add(late[i.ip][0]);continue
        for u in _INFO.info(i).used_registers():
            if u.access not in _WRITES:continue
            r=RX.full_register(u.register)
            if (r==R.RSP and not i.is_call_near or
                    (r in _SAVED or R.ZMM6<=r<=R.ZMM15) and not any(RX.full_register(t)==r for t in available)):return None
        if guard_at is not None:
            # The only cold call here is the exported class initialization
            # on the receiver loaded immediately before its initialized bit.
            if n==guard_at+1:
                if op!=M.JNE or n+2>=len(s) or i.near_branch_target!=s[n+2].ip:return None
                continue
            if n==guard_at+2:
                if (not i.is_call_near or not _class_init(il,i.near_branch_target) or
                        regs.get(R.RCX)!=('klass',f.declaring,guard_slot)):return None
                lines.append(f'global::System.Runtime.CompilerServices.RuntimeHelpers.RunClassConstructor(typeof(global::{decl}).TypeHandle);');clobber();class_init=True;guard_at=None;continue
        if op==M.CMP and i.op0_kind==K.MEMORY and i.memory_base==R.RCX and off==KLASS_INITIALIZED and MS.size(i.memory_size)==4 and i.op1_kind==K.IMMEDIATE8TO32 and not i.immediate8to32:
            if not base or base[:2]!=('klass',f.declaring) or class_init or stages not in ([0,1,2],[0,3,1,2]):return None
            guard_slot=base[2];guard_at=n;continue
        if op==M.TEST and a==b==R.RAX and reg(a) and reg(a)[0]=='ref' and reg(a)[1]=='component':
            j=s[n+1]
            if j.mnemonic!=M.JE or ret+2!=len(s)-1 or j.near_branch_target!=s[ret+1].ip:return None
            raiser=s[ret+1];trap=s[ret+2]
            if (not raiser.is_call_near or trap.mnemonic!=M.INT3 or lift._named_raise_throw(raiser.near_branch_target,lift._call_name(raiser.near_branch_target))!='System.NullReferenceException'):return None
            if null_exit:return None
            null_exit=j.ip;lines.append('if (component is null) { throw new global::System.NullReferenceException(); }');continue
        if null_exit==i.ip:continue
        if i.is_call_near:
            if i.ip==call.ip:
                rc,rd,r8,r9=(reg(r) for r in (R.RCX,R.RDX,R.R8,R.R9))
                if (not class_init or guard_at or rc!=('ref','original',original) or not rd or not r8 or rd[0]!='addr' or r8[0]!='addr' or
                        r9!=('spec',spec) or set(inputs)-{'original','position','rotation','component'} or
                        stages not in ([0,1,2],[0,3,1,2])):return None
                a1,b1=rd[1],r8[1]
                if not validhome(a1,12) or not validhome(b1,16) or not (a1+12<=b1 or b1+16<=a1):return None
                for h,w,name in ((a1,12,'position'),(b1,16,'rotation')):
                    if [stores.get(x) for x in range(h,h+w)]!=[(name,d) for d in range(w)]:return None
                if (set(stores)!=set(range(a1,a1+12))|set(range(b1,b1+16)) or
                        set(borrows)-{a1,b1} or (ret+1<len(s))!=bool(null_exit)):return None
                if init!={load9.ip_rel_memory_address,guard_slot,*[v[0][2] for v in aliases.values()]}:return None
                lines.append(f'global::{decl}.{f.name}<global::{names[0]}>(original, position, rotation);');lines.append('return;');return lines
            # Only an instance nullary reference getter on this and its
            # instance nullary sret getter can precede the constant loads.
            x,y,z=reg(R.RCX),reg(R.RDX),reg(R.R8)
            if x and x[:2]==('ref','this') and y==('zero',) and stages==[0]:
                q=_ref_getter(lift,i,x[2],None)
                if not q or not value(q[1],'component',3,'this.'+q[0]):return None
                clobber();put(R.RAX,('ref','component',q[1]));continue
            if (x and x[0]=='addr' and y and y[:2]==('ref','component') and z==('zero',) and null_exit and
                    stages==[0,3] and validhome(x[1],12) and list(borrows)==[x[1]]):
                # Capture both pieces from the *live* RAX echo before its
                # home can be overwritten or its pointer copied elsewhere.
                start=n+1
                if start<len(s) and s[start].ip in skip and s[start].mnemonic==M.CMP:start+=1
                if start+1>=epi:return None
                a_,z_=s[start:start+2]
                if (a_.mnemonic!=M.MOVSD or z_.mnemonic!=M.MOV or a_.memory_base!=R.RAX or z_.memory_base!=R.RAX or
                        a_.op1_kind!=K.MEMORY or z_.op1_kind!=K.MEMORY or a_.memory_displacement or z_.memory_displacement!=8 or
                        MS.size(a_.memory_size)!=8 or MS.size(z_.memory_size)!=4):return None
                echo_loads={a_.ip,z_.ip};q=_ref_getter(lift,i,y[2],pos)
                if not q or not value(pos,'position',1,'component.'+q[0]):return None
                clobber();put(R.RAX,('echo','position',x[1]));continue
            return None
        if op==M.LEA and i.memory_base==R.RSP and a in (R.RCX,R.RDX,R.R8) and validhome(off,12):
            if (a==R.RCX and (borrows or stages!=[0,3])) or (a!=R.RCX and not class_init):return None
            borrows[off]=1+borrows.get(off,0);put(a,('addr',off));continue
        if op==M.XOR and a==b and a in (R.ECX,R.EDX,R.R8D,R.R9D):put(a,('zero',));continue
        if op==M.MOV and i.op0_kind==i.op1_kind==K.REGISTER and RX.is_gpr64(a) and RX.is_gpr64(b) and reg(b):
            if reg(b)[0]=='echo' or a in (R.RSP,R.RBP) or a not in (R.RAX,R.RCX,R.RDX,R.R8,R.R9) and a not in saved:return None
            put(a,reg(b));continue
        if op==M.MOV and RX.is_gpr64(a) and i.memory_base==R.RIP and MS.size(i.memory_size)==8:
            slot=i.ip_rel_memory_address;us=il.decode_slot(slot) or {}
            if slot not in init:return None
            if us.get('kind')==1 and us.get('td',-1)>=0:put(a,('klass',us['td'],slot));continue
            if us.get('kind')==6 and a==R.R9 and us.get('idx')==spec:put(a,('spec',spec));continue
            return None
        if (op==M.MOV and RX.is_gpr64(a) and i.op1_kind==K.MEMORY and base and base[0]=='ref' and base[1]=='this' and a in saved and not stages):
            row=reference_field_at(il,td.index,off)
            if not row or row[0]!=td.index or key(row[2])!=key(original):return None
            name=source_field_name(il,row[1]);
            if not name.isidentifier() or safe_ident(name)!=name or not value(original,'original',0,'this.'+name):return None
            put(a,('ref','original',original));continue
        if op==M.MOV and RX.is_gpr64(a) and base and base[0]=='klass' and off==KLASS_STATIC_FIELDS:
            put(a,('blob',base[1],base[2]));continue
        if (i.op1_kind==K.MEMORY and base and base[0] in ('blob','echo') and i.op0_kind==K.REGISTER and
                (op==M.MOVSD and MS.size(i.memory_size)==8 and RX.is_xmm(a) or op==M.MOV and RX.is_gpr32(a) or
                 op==M.MOVUPS and MS.size(i.memory_size)==16 and RX.is_xmm(a))):
            width=MS.size(i.memory_size)
            if a not in saved and RX.full_register(a) not in saved:return None
            if base[0]=='blob':
                arg,name,arity=(rot,'rotation',16) if width==16 else (pos,'position',12)
                if key(arg)!=(0x11,base[1],0) or (width==4 and (name not in aliases or base!=aliases[name][0] or off!=aliases[name][1]+8)):return None
                if width!=4:
                    alias=_alias(lift,m,base[2],off,arg,flags)
                    if not alias or not value(arg,name,2 if width==16 else 1,'global::'+alias):return None
                    aliases[name]=base,off
                delta=off-aliases[name][1]
            else:
                if i.ip not in echo_loads or base[1]!='position' or (width,off) not in ((8,0),(4,8)):return None
                name='position';delta=off
            put(a,('piece',name,delta,width));continue
        if i.op0_kind==K.MEMORY and i.memory_base==R.RSP and i.op1_kind==K.REGISTER and class_init:
            part=reg(b);width=MS.size(i.memory_size)
            if not part or part[0]!='piece' or part[3]!=width or (op,width) not in ((M.MOVDQA,16),(M.MOVSD,8),(M.MOV,4)):return None
            if not 32<=off<=size-width or op==M.MOVDQA and off%16 or any(off<x+w and x<off+width for x,w in spans):return None
            for t in range(width):
                if off+t in stores:return None
                stores[off+t]=(part[1],part[2]+t)
            continue
        return None
