"""Win64 instance call with a closed lookup and two saved by-value arguments."""
import re

from il2cpp.captured_home import _normal_predecessors
from il2cpp.awaiter import _spec_entry
from il2cpp.indexed_binary import _saved_pair,_reaching
from il2cpp.copied_getter import _copies_prefix,_sp_offset
from il2cpp.module_curve import fixed_frame
from il2cpp.material_setter import _component
from il2cpp.array_member import element_reads
from il2cpp.float_setter import float_setters
from il2cpp.static_getter import guarded_alias,alias_for_slot
from il2cpp.sret_copy import _own_field
from il2cpp.shared_action import _raises_on_null
from il2cpp.expr import Expr,acc_get
from il2cpp.prelude import HAVE_ICED
from il2cpp.x64 import VOLATILE

if HAVE_ICED:
    from iced_x86 import Mnemonic as M, OpKind as K, Register as R, RegisterExt
    _SAVED={R.RBX,R.RDI,R.RSI,R.R12,R.R13,R.R14,R.R15}


def _rr(i,m,r,s):return i.mnemonic==m and i.op0_register==r and i.op1_register==s


def _unique(il,i):
    if i.mnemonic!=M.CALL or i.op0_kind!=K.NEAR_BRANCH64:return None
    ids=il.addr_candidates.get(i.near_branch_target,())
    if len(ids)==1 and ids[0][0]=='method' and 0<=ids[0][1]<len(il.meta.methods):
        md=il.meta.methods[ids[0][1]]
        if md.addr==i.near_branch_target and md.generic_container==-1:return md


def _public_ref(lift,ty,off):
    """Exposing a private reference via a getter needs the same byte load."""
    il=lift.il;matches=[]
    for ti in il.base_chain_tds(ty[0]):
        td=il.meta.typedefs[ti];row=_own_field(il,td,off,8)
        if not row:continue
        ft=row[1];key=il._closed_type_key(ft)
        if key!=(0x12,ft[0],0) or ft[1]&7!=1:continue
        for j in il.meta.type_methods(td):
            md=il.meta.methods[j];prop=lift._accessor_prop(j)
            if (not prop or prop[0]!='get' or prop[2] or not md.addr or md.is_static or md.param_count or md.flags&7!=6 or md.flags&0x40 or
                    md.generic_container!=-1 or not 0<=md.return_type<len(il.types) or il._closed_type_key(il.types[md.return_type])!=key):continue
            if 0<off<128 and il.bin.read(md.addr,5)==bytes((0x48,0x8b,0x41,off,0xc3)):matches.append((prop[1],ft))
    return matches[0] if len(matches)==1 else None


def _readers(lift,blocks,actions):
    il=lift.il
    for b in blocks:
        if len(b.insns)!=5:continue
        k,blob,ref,test,null=b.insns
        if (k.mnemonic!=M.MOV or k.op0_register!=R.RAX or k.memory_base!=R.RIP or blob.mnemonic!=M.MOV or
                blob.op0_register!=R.RCX or blob.memory_base!=R.RAX or blob.memory_displacement!=0xb8 or ref.mnemonic!=M.MOV or
                ref.op0_register!=R.RAX or ref.memory_base!=R.RCX or not _rr(test,M.TEST,R.RAX,R.RAX) or null.mnemonic!=M.JE or not _raises_on_null(lift,null)):continue
        if len(b.succs)!=1:continue
        q=blocks[b.succs[0]]
        if q.preds!=[b.bid] or len(q.insns)!=3 or len(q.succs)!=1:continue
        r=blocks[q.succs[0]]
        if r.preds!=[q.bid] or len(r.insns)!=3:continue
        obj,test2,null2=q.insns;child,check,fail=r.insns;seq=b.insns+q.insns+r.insns
        if (any(i.has_segment_prefix or i.memory_index!=R.NONE for i in seq) or any(x.next_ip!=y.ip for x,y in zip(seq,seq[1:])) or
                obj.mnemonic!=M.MOV or obj.op0_register!=R.RAX or obj.memory_base!=R.RAX or not _rr(test2,M.TEST,R.RAX,R.RAX) or
                null2.mnemonic!=M.JE or not _raises_on_null(lift,null2) or child.mnemonic!=M.MOV or child.op0_register!=R.RCX or child.memory_base!=R.RAX or
                not _rr(check,M.TEST,R.RCX,R.RCX) or fail.mnemonic!=M.JE or not _raises_on_null(lift,fail)):continue
        alias=alias_for_slot(il,k.ip_rel_memory_address,lift.rt_init_meta,ref.memory_displacement)
        if alias:
            field=_own_field(il,il.meta.typedefs[alias[1][0]],obj.memory_displacement,8)
            if field and il._type_enum(field[1])==0x12 and field[1][1]&7==6:
                public=_public_ref(lift,field[1],child.memory_displacement)
                if public:
                    actions[ref.ip]=('getter',alias,'RAX');actions[child.ip]=('property',public,'RCX',field[1])


def _plan(lift,method,blocks,b,pred,byip,frame):
    il=lift.il;s=b.insns;cb=blocks[b.bid-1];gb=blocks[b.bid-2]
    if (len(cb.insns)!=4 or len(gb.insns)!=6 or b.preds!=[cb.bid] or cb.preds!=[gb.bid]):return None
    seq=gb.insns+cb.insns+s
    if (any(i.has_segment_prefix or i.has_lock_prefix or i.memory_index!=R.NONE for i in seq) or
            any(x.next_ip!=z.ip or pred[z.ip]!={x.ip} for x,z in zip(seq,seq[1:]))):return None
    nullarg,producer,field,save,test,null=gb.insns;slot,lookup,check,fail=cb.insns
    stackinfo,rot,vec,post,prefab,svQ,recv,xy,z,call=s
    owner=_unique(il,call);key=il._closed_type_key
    if (not owner or owner.is_static or owner.flags&7!=6 or owner.flags&0x40 or owner.param_count!=4 or not 0<=owner.return_type<len(il.types)):return None
    ps=il.meta.method_params(owner)
    if len(ps)!=4 or any(not 0<=p.type<len(il.types) for p in ps):return None
    pt,vt,qt,ct=(il.types[p.type] for p in ps);rt=il.types[owner.return_type]
    ck=key(ct)
    if (key(rt)!=(0x12,rt[0],0) or key(pt)!=(0x12,pt[0],0) or not ck or ck[-1] or
            not (ck[0]==0x12 or ck[0]==0x15 and ck[1][0]==0x12) or
            key(vt)!=(0x11,vt[0],0) or key(qt)!=(0x11,qt[0],0) or il.value_type_size(vt[0])!=12 or il.value_type_size(qt[0])!=16):return None
    reg=save.op0_register
    if (not _rr(nullarg,M.XOR,R.ECX,R.ECX) or producer.mnemonic!=M.CALL or producer.op0_kind!=K.NEAR_BRANCH64 or
            reg not in _SAVED or not _rr(save,M.MOV,reg,R.RAX) or field.mnemonic!=M.MOV or field.op0_register!=R.RCX or field.memory_base not in _SAVED or
            not _rr(test,M.TEST,R.RCX,R.RCX) or null.mnemonic!=M.JE or not _raises_on_null(lift,null) or not _rr(check,M.TEST,reg,reg) or fail.mnemonic!=M.JE or not _raises_on_null(lift,fail) or
            slot.mnemonic!=M.MOV or slot.op0_register!=R.RDX or slot.memory_base!=R.RIP or lookup.mnemonic!=M.CALL or lookup.op0_kind!=K.NEAR_BRANCH64):return None
    alias=guarded_alias(il,producer.near_branch_target,lift.rt_init_meta);row=_own_field(il,il.meta.typedefs[method.declaring],field.memory_displacement,8)
    if not alias or owner.declaring!=alias[1][0] or not row or key(row[1])!=(0x12,row[1][0],0):return None
    binding=_component(lift,slot,lookup,pt[0],'GetComponent',False)
    if not binding:return None
    si,decl,actual,name,_=binding[1]
    if (key(actual)!=key(pt) or decl not in il.base_chain_tds(row[1][0]) or
            _spec_entry(il,si,il.method_specs[si][0]) not in (None,0,lookup.near_branch_target)):return None
    zr=post.op1_register;off=lambda i:_sp_offset(i,frame[0]);a=off(vec);q=off(rot)
    if (zr not in _SAVED or any(i.mnemonic!=M.MOV or i.memory_base!=R.RSP or i.op1_register!=zr or i.memory_displacement!=disp for i,disp in ((post,32),(stackinfo,40))) or
            a is None or q is None or not 48<=a<=frame[1]-12 or not 48<=q<=frame[1]-16 or not(a+12<=q or q+16<=a) or
            vec.mnemonic!=M.LEA or vec.op0_register!=R.R8 or rot.mnemonic!=M.LEA or rot.op0_register!=R.R9 or
            not _rr(prefab,M.MOV,R.RDX,R.RAX) or not _rr(recv,M.MOV,R.RCX,reg) or
            xy.mnemonic!=M.MOVSD or off(xy)!=a or not R.XMM6<=xy.op1_register<=R.XMM15 or z.mnemonic!=M.MOV or off(z)!=a+8 or
            not RegisterExt.is_gpr32(z.op1_register) or svQ.mnemonic!=M.MOVDQA or off(svQ)!=q or q%16 or not R.XMM6<=svQ.op1_register<=R.XMM15):return None
    clear=_reaching(byip,pred,post.ip,zr);pair=_saved_pair(byip,pred,xy,z);load=_reaching(byip,pred,svQ.ip,svQ.op1_register)
    if (not clear or clear.mnemonic!=M.XOR or clear.op0_register!=clear.op1_register or not RegisterExt.is_gpr32(clear.op0_register) or
            not pair or not _copies_prefix(il,pair[0].near_branch_target) or not load or load.mnemonic!=M.MOVUPS or load.memory_base!=R.RAX or
            load.memory_index!=R.NONE or load.has_segment_prefix or load.memory_displacement or load.op0_register!=svQ.op1_register):return None
    # The sret echo survives a flag comparison before the 16-byte save.
    if len(pred[load.ip])!=1:return None
    guard=byip[next(iter(pred[load.ip]))]
    if guard.mnemonic!=M.CMP or guard.memory_base!=R.RIP or len(pred[guard.ip])!=1:return None
    transform=byip[next(iter(pred[guard.ip]))];transform_md=_unique(il,transform)
    if not transform_md or key(il.types[transform_md.return_type])!=key(qt) or not il.returns_sret(qt):return None
    return {producer.ip:('getter',alias,'RAX'),lookup.ip:('component',name,actual,row[1]),
            pair[1].ip:('capture',pair[0].ip,vt,True),load.ip:('capture',transform.ip,qt,False),
            svQ.ip:('copy',transform.ip,q,16),xy.ip:('low',pair[0].ip),z.ip:('copy',pair[0].ip,a,12),
            call.ip:('apply',owner.name,pt,vt,qt,rt,pair[0].ip,transform.ip,producer.ip,lookup.ip)}, {pair[0].ip,transform.ip}


def _saved_calls(lift,method,s,pred,byip,frame):
    """An instance call consumes a saved 8+4 value and a fresh 16-byte
    sret. A subsequent static call takes another by-value copy of the first.
    Keep all memory stores; rebind only the actual by-value arguments."""
    il=lift.il;key=il._closed_type_key
    make,hidden,lo,qarg,hi,parg,selfarg,loadq,storeq,call,scalar,lo2,count,hi2,array,mi,arg2,nextcall=s
    sink=_unique(il,call);following=_unique(il,nextcall);transform=_unique(il,make)
    if (not all((sink,following,transform)) or not transform.is_static or sink.is_static or not following.is_static or
            method.is_static or sink.declaring!=method.declaring or sink.flags&0x40 or
            sink.param_count!=2 or following.param_count!=4 or not 0<=transform.return_type<len(il.types)):return None
    def types(m):return [il.types[p.type] for p in il.meta.method_params(m) if 0<=p.type<len(il.types)]
    ps=types(sink);fs=types(following)
    if len(ps)!=2 or len(fs)!=4:return None
    v,q=ps;ret=il.types[transform.return_type]
    if (not all(0<=m.return_type<len(il.types) and key(il.types[m.return_type])==(1,0) for m in (sink,following)) or
            key(v)!=(0x11,v[0],0) or key(q)!=(0x11,q[0],0) or key(ret)!=key(q) or not il.returns_sret(q) or
            il.value_type_size(v[0])!=12 or il.value_type_size(q[0])!=16 or key(fs[0])!=key(v) or
            il._type_enum(fs[1])!=0x1d or fs[1][1]&(1<<29) or key(fs[2])!=(8,0) or key(fs[3])!=(0x0c,0)):return None
    if (any(i.has_segment_prefix or i.has_lock_prefix or i.memory_index!=R.NONE for i in s) or
            any(x.next_ip!=y.ip or pred[y.ip]!={x.ip} for x,y in zip(s,s[1:]))):return None
    off=lambda i:_sp_offset(i,frame[0]);a=off(parg);b=off(qarg);c=off(arg2)
    if (None in (a,b,c) or not 32<=a<=frame[1]-12 or not 32<=b<=frame[1]-16 or not 40<=c<=frame[1]-12 or
            not (a+12<=b or b+16<=a) or not _rr(hidden,M.XOR,R.R9D,R.R9D) or
            any(i.mnemonic!=M.LEA or i.op0_register!=r for i,r in ((qarg,R.R8),(parg,R.RDX),(arg2,R.RCX))) or
            selfarg.mnemonic!=M.MOV or selfarg.op0_register!=R.RCX or selfarg.op1_register not in _SAVED or
            loadq.mnemonic!=M.MOVUPS or loadq.memory_base!=R.RAX or loadq.memory_displacement or not R.XMM0<=loadq.op0_register<=R.XMM5 or
            storeq.mnemonic not in (M.MOVAPS,M.MOVUPS) or storeq.op1_register!=loadq.op0_register or off(storeq)!=b or
            storeq.mnemonic==M.MOVAPS and b%16 or scalar.mnemonic!=M.MOVAPS or scalar.op0_register!=R.XMM3 or not R.XMM6<=scalar.op1_register<=R.XMM15 or
            count.mnemonic!=M.MOV or count.op0_register!=R.R8D or RegisterExt.full_register(count.op1_register) not in _SAVED or
            array.mnemonic!=M.MOV or array.op0_register!=R.RDX or array.op1_register not in _SAVED or
            mi.mnemonic!=M.MOV or mi.memory_base!=R.RSP or mi.memory_displacement!=32 or mi.op1_kind!=K.IMMEDIATE32TO64 or mi.immediate32to64!=0):return None
    if (any(x.mnemonic!=M.MOVSD or x.op1_register!=lo.op1_register or off(x)!=dest for x,dest in ((lo,a),(lo2,c))) or
            any(x.mnemonic!=M.MOV or x.op1_register!=hi.op1_register or off(x)!=dest+8 for x,dest in ((hi,a),(hi2,c))) or
            not R.XMM6<=lo.op1_register<=R.XMM15 or not RegisterExt.is_gpr32(hi.op1_register)):return None
    pair=_saved_pair(byip,pred,lo,hi)
    if not pair or not _copies_prefix(il,pair[0].near_branch_target):return None
    # The first argument is stored before the quaternion is read from RAX.
    # Require the transform's separate RCX home; don't silently turn an
    # overlapping write into a pristine quaternion snapshot.
    ip=make.ip;out=None
    for _ in range(12):
        if len(pred[ip])!=1:break
        prev=byip[next(iter(pred[ip]))];ip=prev.ip
        if prev.mnemonic==M.LEA and prev.op0_register==R.RCX:
            out=off(prev);break
        if prev.mnemonic not in (M.MOVSD,M.MOV,M.LEA,M.XOR) or RegisterExt.full_register(prev.op0_register)==R.RCX:break
    if out is None or not 32<=out<=frame[1]-16 or not(a+12<=out or out+16<=a):return None
    src=pair[0].ip
    return ({pair[1].ip:('capture',src,v,True),loadq.ip:('capture',make.ip,q,False),
             lo.ip:('low',src),hi.ip:('copy',src,a,12),storeq.ip:('copy',make.ip,b,16),
             lo2.ip:('low',src),hi2.ip:('copy',src,c,12),call.ip:('byval',('RDX',a,src),('R8',b,make.ip)),
             nextcall.ip:('byval',('RCX',c,src))}, {src,make.ip})


def _additional_reads(lift,method,blocks,pred,actions):
    il=lift.il
    for b in blocks:
        # An inherited private reference read from this via its simple
        # public getter. The pruned null edge still throws at the next use.
        if len(b.insns)==3:
            ld,test,null=b.insns
            if (ld.mnemonic==M.MOV and ld.op0_register==R.RCX and ld.memory_base in _SAVED and not ld.has_segment_prefix and
                    ld.memory_index==R.NONE and _rr(test,M.TEST,R.RCX,R.RCX) and null.mnemonic==M.JE and _raises_on_null(lift,null) and
                    pred[test.ip]=={ld.ip} and pred[null.ip]=={test.ip}):
                public=_public_ref(lift,(method.declaring,0x12<<16),ld.memory_displacement)
                if public:actions[ld.ip]=('self_property',public,ld.memory_base,method.declaring)
        if len(b.insns)<3:continue
        for slot,recv,call in zip(b.insns,b.insns[1:],b.insns[2:]):
            if (slot.mnemonic!=M.MOV or slot.op0_register!=R.RDX or slot.memory_base!=R.RIP or slot.has_segment_prefix or
                    recv.mnemonic!=M.MOV or recv.op0_register!=R.RCX or recv.op1_register not in _SAVED or call.mnemonic!=M.CALL or
                    call.op0_kind!=K.NEAR_BRANCH64 or slot.next_ip!=recv.ip or recv.next_ip!=call.ip or
                    pred[call.ip]!={recv.ip} or pred[recv.ip]!={slot.ip}):continue
            u=il.decode_slot(slot.ip_rel_memory_address) or {};si=u.get('idx',-1)
            if u.get('kind')!=6 or not 0<=si<len(il.method_specs):continue
            ty=il.candidate_return_type(('generic',si))
            if not ty or il._closed_type_key(ty)!=(0x12,ty[0],0):continue
            binding=_component(lift,slot,call,ty[0],'GetComponentInParent',False)
            if not binding or _spec_entry(il,si,il.method_specs[si][0]) not in (None,0,call.near_branch_target):continue
            _,decl,actual,name,_=binding[1];actions[call.ip]=('component',name,actual,il.types[il.meta.typedefs[decl].byval])


def application_sites(lift,method,blocks,pads):
    actions={};fresh=set();counts={};il=lift.il
    if not HAVE_ICED or pads:return actions,fresh,counts
    for b in blocks:
        for j in range(3,len(b.insns)):
            call,load,park,spill=b.insns[j-3:j+1]
            if (park.mnemonic!=M.MOV or park.op1_register!=R.EAX or not RegisterExt.is_gpr32(park.op0_register) or
                    RegisterExt.full_register(park.op0_register) not in _SAVED or spill.mnemonic!=M.MOV or spill.op1_register!=R.EAX or
                    spill.memory_base not in (R.RBP,R.RSP) or load.mnemonic!=M.MOV or load.op0_register!=R.RCX or load.op1_kind!=K.MEMORY):continue
            md=_unique(il,call)
            if md and il._closed_type_key(il.types[md.return_type])==(8,0):counts[call.ip]=md.index
    candidates=[b for b in blocks if b.bid>=2 and len(b.insns)==10 and b.insns[0].memory_base==R.RSP and b.insns[1].op0_register==R.R9]
    pairs=[b.insns[j-9:j+9] for b in blocks for j in range(9,len(b.insns)-8) if b.insns[j].mnemonic==M.CALL and
           b.insns[j+8].mnemonic==M.CALL and b.insns[j-9].mnemonic==M.CALL]
    if candidates or pairs:
        frame=fixed_frame(lift,method,blocks,pads,immediate=True,extended_saves=True);seq=[i for b in blocks for i in b.insns];pred=_normal_predecessors(seq)
        if frame and pred and all(a.next_ip==z.ip for a,z in zip(seq,seq[1:])):
            byip={i.ip:i for i in seq}
            for b in candidates:
                got=_plan(lift,method,blocks,b,pred,byip,frame)
                if got:actions.update(got[0]);fresh.update(got[1])
            matched_pair=False
            for s in pairs:
                got=_saved_calls(lift,method,s,pred,byip,frame)
                if got:actions.update(got[0]);fresh.update(got[1]);matched_pair=True
            if matched_pair:_additional_reads(lift,method,blocks,pred,actions)
    if actions:_readers(lift,blocks,actions)
    actions.update(element_reads(lift,method,blocks,pads))
    actions.update(float_setters(lift,method,blocks,pads))
    return actions,fresh,counts


def application_step(lift,ins,action,values):
    op,*args=action
    def bind(expr,ty,reg,kind='obj'):
        name=lift.new_var();lift._var_types[name]=ty;lift.emit(ins.ip,'var %s = %s;'%(name,expr),None)
        e=Expr(name,ty,kind);lift.regs[reg]=e;values[ins.ip]=e
    def clear():
        for r in (*VOLATILE,*('XMM%d'%n for n in range(6))):lift.regs.pop(r,None)
        lift.flags=None;lift._fresh_unknowns()
    if op=='capture':
        ip,ty,accessor=args;e=dict.get(lift.regs,'RAX')
        if (e and getattr(lift,'_last_sret',None)==(ip,e) and (not accessor or getattr(lift,'_last_accessor_sret',None)==(ip,e)) and
                lift.il._closed_type_key(e.ty)==lift.il._closed_type_key(ty) and re.fullmatch(r'&t\d+',e.text)):
            values[ip]=Expr(e.text[1:],ty,'obj')
        return False
    if op=='low':return args[0] in values
    if op=='field_value':
        (name,ty),reg,kind=args;bind(acc_get(name),ty,reg,kind);return True
    if op=='make_float':
        fn,ty,lo,hi=args
        if lo in values and hi in values:
            expr=f'{fn}({values[lo].text}, {values[hi].text})';clear();bind(expr,ty,'XMM0','float');return True
    if op=='set_float':
        ref,value,member,tail=args
        if ref in values and value in values:
            lift.emit(ins.ip,f'{values[ref].text}.{member} = {values[value].text} /* shared implementation */;'+(' return;' if tail else ''),None)
            clear();return True
    if op=='element':
        br,ir,ty,prop,rt,dst=args;a=dict.get(lift.regs,br);idx=dict.get(lift.regs,ir);key=lift.il._closed_type_key
        if (a and idx and not a._unk and not idx._unk and re.fullmatch(r'\w+',a.text or '') and re.fullmatch(r'\w+',idx.text or '') and
                (lift.dry or key(a.ty)==key(ty) and key(idx.ty)==(8,0))):
            clear();bind(acc_get(f'{a.text}[{idx.text}].{prop}'),rt,dst,'float' if dst=='XMM0' else 'obj')
            lift._type_hints.setdefault(values[ins.ip].text,rt)
            return True
    if op=='byval' and all(ip in values and getattr(dict.get(lift.regs,r),'_stack_offset',None)==lift.rsp_delta+off for r,off,ip in args):
        for r,off,ip in args:
            v=values[ip];e=Expr('&'+v.text,v.ty,'ptr');e._stack_offset=lift.rsp_delta+off;lift.regs[r]=e
        return False  # render the registered call normally
    if op=='copy' and args[0] in values:
        # Keep the writes to outgoing stack storage, even if the same
        # physical slots are used again after this call. Only this reaching
        # value is typed; do not retype the frame home for the entire method.
        src,off,width=args;value=values[src];slot=lift.slot_var(off);start=lift.rsp_delta+off
        lift._kill_stale(slot);lift.emit(ins.ip,f'{slot} = {value.text};',None)
        for addr,old in lift.stack_map.items():
            if start<=addr<start+width:lift.stack_values.pop(old,None)
        lift._stack_store(start,width,value);lift.stack_values[slot]=value
        return True
    if op=='getter':
        (name,ty),reg=args
        if ins.mnemonic==M.CALL:clear()
        bind(acc_get(name),ty,reg);return True
    if op=='property':
        (name,ty),reg,base=args;e=dict.get(lift.regs,'RAX')
        if e and (lift.dry or lift.il._closed_type_key(e.ty)==lift.il._closed_type_key(base)):
            bind(acc_get(e.text+'.'+name),ty,reg);return True
    if op=='self_property':
        from il2cpp.text import reg_name
        (name,ty),base,ti=args;e=dict.get(lift.regs,reg_name(base))
        if e and e.text=='this' and (lift.dry or lift.il._closed_type_key(e.ty)==(0x12,ti,0)):
            bind(acc_get('this.'+name),ty,'RCX');return True
    if op=='component':
        name,ty,base=args;e=dict.get(lift.regs,'RCX')
        if e and (lift.dry or lift.il._closed_type_key(e.ty)==lift.il._closed_type_key(base)):
            expr=f'{e.text}.{name}<{lift.il.type_name(ty)}>()';clear();bind(expr,ty,'RAX')
            lift._type_hints.setdefault(values[ins.ip].text,ty)  # a base-type comparison does not widen the result
            return True
    if op=='apply':
        name,pt,vt,qt,rt,*keys=args
        if all(k in values for k in keys):
            v,q,obj,p=(values[k].text for k in keys)
            clear();bind(f'{obj}.{name}({p}, {v}, {q}, null)',rt,'RAX');return True
    return False
