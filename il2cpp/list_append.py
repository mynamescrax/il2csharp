"""Recover complete Win64 List<int>.Add diamonds, including the resize arm.

The helper alone is *not* Add: the caller already bumped _version. Compare
both paths, the closed MethodInfo passed to the helper, and the receiver and
item evaluation order against the registered public Add implementation.
"""
import re

from il2cpp.awaiter import _spec_entry
from il2cpp.binary import PE
from il2cpp.prelude import HAVE_ICED
from il2cpp.shared_icall import shared_icall
from il2cpp.expr import Expr, acc_get
from il2cpp.static_getter import alias_for_slot
from il2cpp.sret_copy import _own_field
from il2cpp.text import reg_name, sdisp

if HAVE_ICED:
    from iced_x86 import Decoder, FlowControl as F, Mnemonic as M, OpKind as K, Register as R, MemorySizeExt, RegisterExt, InstructionInfoFactory, OpAccess


def _sp(i,mn,size):
    return i.mnemonic==mn and i.op0_register==R.RSP and i.op1_kind==K.IMMEDIATE8TO64 and i.immediate8to64==size


def _plain(i):
    return not (i.has_segment_prefix or i.has_lock_prefix or i.has_rep_prefix or i.has_repne_prefix or i.has_xacquire_prefix or i.has_xrelease_prefix)


def _reference(il,entry):
    """Version increment, unsigned room test, size/store and RGCTX tail.
    All targets are read from the public closed method, not the address index."""
    if not entry or not il.bin.is_exec_va(entry): return None
    start,end=il.function_extent(entry)
    if start!=entry or not 0<end-start<=128: return None
    seq=list(Decoder(64,il.bin.read(start,end-start) or b'',ip=start))
    if len(seq)!=24 or not all(_plain(i) for i in seq): return None
    sp,inc,items,size,test,null,room,fast,method,ctx,slot,restore,slow=seq[:13]
    plus,setsize,check,bound,store,back,ret,nre,trap1,ior,trap2=seq[13:]
    if (not _sp(sp,M.SUB,0x28) or not _mem(inc,M.INC,R.RCX,0x1c,4) or not _load(items,M.MOV,R.R10,R.RCX,0x10,8) or
            not _load(size,M.MOVSXD,R.R9,R.RCX,0x18,4) or not _rr(test,M.TEST,R.R10,R.R10) or not _jump(null,M.JE,nre.ip) or
            not _load(room,M.CMP,R.R9D,R.R10,0x18,4) or not _jump(fast,M.JB,plus.ip) or
            not _load(method,M.MOV,R.RAX,R.R8,0x20,8) or not _load(ctx,M.MOV,R.R8,R.RAX,0xc0,8) or
            not _load(slot,M.MOV,R.R8,R.R8,0x70,8) or not _sp(restore,M.ADD,0x28) or
            slow.mnemonic!=M.JMP or slow.op0_kind!=K.NEAR_BRANCH64 or not _load(plus,M.LEA,R.EAX,R.R9,1,0) or
            not _mem(setsize,M.MOV,R.RCX,0x18,4) or setsize.op1_register!=R.EAX or not _load(check,M.CMP,R.R9D,R.R10,0x18,4) or
            not _jump(bound,M.JAE,ior.ip) or not _mem(store,M.MOV,R.R10,0x20,4,R.R9,4) or store.op1_register!=R.EDX or
            not _sp(back,M.ADD,0x28) or ret.mnemonic!=M.RET or ret.op_count or trap1.mnemonic!=M.INT3 or trap2.mnemonic!=M.INT3 or
            any(i.mnemonic!=M.CALL or i.op0_kind!=K.NEAR_BRANCH64 for i in (nre,ior))): return None
    return slow.near_branch_target,nre.near_branch_target,ior.near_branch_target


def _contract(lift, slot):
    il=lift.il; u=il.decode_slot(slot) or {}; si=u.get('idx',-1)
    if u.get('kind')!=6 or not 0<=si<len(il.method_specs): return None
    mi,ci,gi=il.method_specs[si]
    if gi!=-1 or not 0<=mi<len(il.meta.methods): return None
    add=il.meta.methods[mi]; td=il.meta.typedefs[add.declaring]; args=il._method_spec_type_args(ci)
    if (add.name!='Add' or il.typedef_full(td.index)!='System.Collections.Generic.List`1' or
            td.generic_container<0 or not args or len(args)!=1 or il._closed_type_key(args[0])!=(8,0)):
        return None
    owner,n,ismethod,param=il.meta.generic_containers[td.generic_container]
    if (owner,n,ismethod)!=(td.index,1,0): return None
    def signature(m,vis):
        ps=il.meta.method_params(m)
        return (m.declaring==td.index and not m.is_static and m.generic_container==-1 and m.flags&7==vis and
                m.param_count==len(ps)==1 and 0<=ps[0].type<len(il.types) and
                il.types[ps[0].type][0]==param and il._type_enum(il.types[ps[0].type])==0x13 and
                not il.types[ps[0].type][1]&(1<<29) and 0<=m.return_type<len(il.types) and
                il._closed_type_key(il.types[m.return_type])==(1,0))
    if not signature(add,6) or (add.flags&0x40 and not add.flags&0x20): return None
    entry=_spec_entry(il,si,mi)
    ref=_reference(il,entry)
    if not ref: return None
    slow,null,bounds=ref
    resize=[j for j in il.meta.type_methods(td) if il.meta.methods[j].name=='AddWithResize' and signature(il.meta.methods[j],1)]
    if len(resize)!=1: return None
    try: ri=il.method_specs.index((resize[0],ci,-1))
    except ValueError: return None
    if _spec_entry(il,ri,resize[0])!=slow or not il.bin.is_exec_va(slow): return None
    return (0x15,(0x12,td.index,0),((8,0),),0), slow, null, bounds


def _mem(i, mn, base, off, size, index=None, scale=1):
    return (i.mnemonic==mn and i.memory_base==base and i.memory_displacement==off and
            i.memory_index==(R.NONE if index is None else index) and i.memory_index_scale==scale and
            (not size or MemorySizeExt.size(i.memory_size)==size))


def _load(i,mn,reg,base,off,size):
    return i.op0_register==reg and i.op1_kind==K.MEMORY and _mem(i,mn,base,off,size)


def _rr(i,mn,dst,src): return i.mnemonic==mn and i.op0_register==dst and i.op1_register==src


def _jump(i,mn,target): return i.mnemonic==mn and i.op0_kind==K.NEAR_BRANCH64 and i.near_branch_target==target


def _raise_at(by_ip, ip, helper):
    i=by_ip.get(ip)
    return i is not None and _jump(i,M.CALL,helper) and i.next_ip in by_ip and by_ip[i.next_ip].mnemonic==M.INT3


def _epilogue(seq):
    return (len(seq)==3 and _load(seq[0],M.MOV,R.RDI,R.RSP,0x30,8) and
            seq[1].mnemonic==M.ADD and seq[1].op0_register==R.RSP and seq[1].op1_kind==K.IMMEDIATE8TO64 and
            seq[1].immediate8to64==0x20 and seq[2].mnemonic==M.POP and seq[2].op0_register==R.RBX)


def _diamond(blocks,head):
    i=head.bid
    if len(blocks)<i+6: return None
    version,cap,slow,fast,store=blocks[i+1:i+6]
    if (head.succs==[i+1] and version.preds==[i] and version.succs==[i+2] and cap.preds==[i+1] and
            cap.succs==[i+4,i+3] and fast.preds==slow.preds==[i+2] and fast.succs==[i+5] and store.preds==[i+4]):
        return version,cap,slow,fast,store


def _fast_path(v,c,f,write,held,array,index,idx32,item,methodinfo,null):
    """Same increments, unsigned branches and scaled dword write as the public Add."""
    slot,bump,items,size,arrtest,arrnull=v
    return (slot.mnemonic==M.MOV and slot.op0_register==methodinfo and slot.memory_base==R.RIP and
            _mem(bump,M.INC,held,0x1c,4) and _load(items,M.MOV,array,held,0x10,8) and
            _load(size,M.MOVSXD,index,held,0x18,4) and _rr(arrtest,M.TEST,array,array) and
            _jump(arrnull,M.JE,null.near_branch_target) and _load(c[0],M.CMP,idx32,array,0x18,4) and
            _jump(c[1],M.JB,f[0].ip) and _load(f[0],M.LEA,R.EAX,index,1,0) and
            _mem(f[1],M.MOV,held,0x18,4) and f[1].op1_register==R.EAX and
            _load(f[2],M.CMP,idx32,array,0x18,4) and f[3].mnemonic==M.JAE and
            _mem(write,M.MOV,array,0x20,4,index,4) and write.op1_register==item)


def _arm(lift,td,blocks,head,by_ip):
    # Six blocks: argument evaluation, version/size, capacity comparison,
    # resize arm, fast size update/bounds check, fast element write.
    i=head.bid
    region=_diamond(blocks,head)
    if not region or len(head.insns)<8: return None
    version,cap,slow,fast,store=region
    h=head.insns[-8:]; field,clear,hi,lo,rng,move,test,null=h
    v=version.insns; c=cap.insns; s=slow.insns; f=fast.insns; w=store.insns
    terminal=not slow.succs and not store.succs
    if (len(v)!=6 or len(c)!=2 or len(f)!=4 or len(s)!=(9 if terminal else 7) or len(w)!=(5 if terminal else 1)): return None
    seq=h+v+c+s+f+w
    if any(a.next_ip!=b.ip for a,b in zip(seq,seq[1:])) or not all(_plain(x) for x in seq): return None
    held=field.op0_register
    if (held not in (R.RBX,R.RDI) or not _load(field,M.MOV,held,R.RBX,field.memory_displacement,8) or
            not _rr(clear,M.XOR,R.R8D,R.R8D) or not _load(hi,M.LEA,R.EDX,R.R8,hi.memory_displacement,0) or
            not _load(lo,M.LEA,R.ECX,R.RDX,lo.memory_displacement,0) or rng.mnemonic!=M.CALL or rng.op0_kind!=K.NEAR_BRANCH64 or
            not _rr(move,M.MOV,R.R9D,R.EAX) or not _rr(test,M.TEST,held,held) or null.mnemonic!=M.JE): return None
    if not _fast_path(v,c,f,w[1 if terminal else 0],held,R.RDX,R.RCX,R.ECX,R.R9D,R.RAX,null): return None
    row=_own_field(lift.il,td,field.memory_displacement,8); contract=_contract(lift,v[0].ip_rel_memory_address)
    if not row or not contract or lift.il._closed_type_key(row[1])!=contract[0]: return None
    _,resize,nre,ior=contract
    if (not _raise_at(by_ip,null.near_branch_target,nre) or not _load(s[0],M.MOV,R.RAX,R.RAX,0x20,8) or
            not _rr(s[1],M.MOV,R.EDX,R.R9D) or not _rr(s[2],M.MOV,R.RCX,held) or
            not _load(s[3],M.MOV,R.R8,R.RAX,0xc0,8) or not _load(s[4],M.MOV,R.R8,R.R8,0x70,8) or
            not _raise_at(by_ip,f[3].near_branch_target,ior)): return None
    write=w[1 if terminal else 0]
    if terminal:
        if (not _epilogue(s[5:8]) or not _epilogue([w[0],*w[2:4]]) or not _jump(s[-1],M.JMP,resize) or
                w[-1].mnemonic!=M.RET or w[-1].op_count): return None
    elif (not _jump(s[5],M.CALL,resize) or not _jump(s[6],M.JMP,write.next_ip) or
          slow.succs!=store.succs or store.succs!=[i+6]): return None
    # Close the expression on both sides. The evaluated receiver must still
    # be this exact field, and the final bound result the very int in R9D.
    recv=head.end_state.get(reg_name(held)); value=head.end_state.get('R9')
    if (not recv or recv._unk or recv.text!=row[0] or not recv.ty or lift.il._closed_type_key(recv.ty)!=contract[0] or
            not value or not re.fullmatch(r't\d+',value.text) or not head.stmts): return None
    high=sdisp(hi.memory_displacement); low=high+sdisp(lo.memory_displacement)
    if not all(-(1<<31)<=n<1<<31 for n in (low,high)): return None
    args=list(map(str,(low,high)))
    call=shared_icall(lift,rng.near_branch_target,args,[Expr(a,kind='int') for a in args])
    if not call or head.stmts[-1]!='var %s = %s;'%(value.text,call): return None
    return '%s.Add(%s);'%(row[0],call), terminal, field.ip


def _saved_this(blocks,stop):
    # The entry argument is captured in RBX before any branch; no PC on the
    # way to the final capture can redefine it. Win64 calls preserve RBX.
    seq=blocks[0].insns
    if (len(seq)<3 or seq[0].mnemonic!=M.PUSH or seq[0].op0_register!=R.RBX or seq[1].mnemonic!=M.SUB or
            seq[1].op0_register!=R.RSP or seq[1].op1_kind!=K.IMMEDIATE8TO64 or seq[1].immediate8to64!=0x20): return False
    fac=InstructionInfoFactory(); saved=False; spill=None
    writes={OpAccess.WRITE,OpAccess.READ_WRITE,OpAccess.COND_WRITE,OpAccess.READ_COND_WRITE}
    for b in blocks:
        for ins in b.insns:
            if ins.ip==stop:
                if not saved or spill is None: return False
                # A bypass around the RDI save cannot share its epilogue.
                todo=[0]; seen=set()
                while todo:
                    n=todo.pop()
                    if n==spill or n in seen: continue
                    if n==b.bid: return False
                    seen.add(n); todo.extend(blocks[n].succs)
                return True
            if ins.ip>stop: return False
            if b is blocks[0] and not saved and _rr(ins,M.MOV,R.RBX,R.RCX): saved=True; continue
            if not saved and ins.flow_control!=F.NEXT: return False
            if (ins.op0_kind==K.MEMORY and _mem(ins,M.MOV,R.RSP,0x30,8) and ins.op1_register==R.RDI):
                if spill is not None: return False
                spill=b.bid
            if any(r.access in writes and RegisterExt.full_register(r.register) in ((R.RBX,) if saved else (R.RBX,R.RCX))
                   for r in fac.info(ins).used_registers()): return False
    return False


def _field_frame(blocks,head):
    """Pair the two home saves and the push with the terminal restores.
    Check only paths reaching this arm; other switch arms can already have
    restored RBX and returned. Unreachable init arms supply no provenance.
    """
    entry=blocks[0]; seq=entry.insns
    if (len(seq)<6 or not all(_plain(i) for i in seq[:6]) or
            not _mem(seq[0],M.MOV,R.RSP,8,8) or seq[0].op1_register!=R.RBX or
            not _mem(seq[1],M.MOV,R.RSP,16,8) or seq[1].op1_register!=R.RSI or
            seq[2].mnemonic!=M.PUSH or seq[2].op0_register!=R.RDI or not _sp(seq[3],M.SUB,32) or
            seq[4].mnemonic!=M.CMP or not _rr(seq[5],M.MOV,R.RBX,R.RCX) or entry.preds): return False
    seen=set(); todo=list(head.preds); writes={OpAccess.WRITE,OpAccess.READ_WRITE,OpAccess.COND_WRITE,OpAccess.READ_COND_WRITE}
    fac=InstructionInfoFactory()
    while todo:
        n=todo.pop()
        if n in seen: continue
        seen.add(n); b=blocks[n]; todo.extend(b.preds)
        for i in (b.insns[6:] if b is entry else b.insns):
            if i.flow_control in (F.CALL,F.INDIRECT_CALL): continue
            info=fac.info(i)
            if any(r.access in writes and RegisterExt.full_register(r.register) in (R.RSP,R.RBX) for r in info.used_registers()): return False
            if i.memory_base==R.RSP and (i.memory_index!=R.NONE or i.mnemonic==M.LEA or any(
                    a.access in writes and sdisp(i.memory_displacement)+MemorySizeExt.size(i.memory_size)>0x20 for a in info.used_memory())): return False
    return 0 in seen


def _singleton_read(b,slot,nre,by_ip):
    """One bound, null-checked reference from [klass.static_fields+0]."""
    if len(b.insns)!=5 or len(b.stmts)!=1 or not all(_plain(i) for i in b.insns): return None
    klass,blob,ref,test,null=b.insns; dest=ref.op0_register
    if (klass.mnemonic!=M.MOV or klass.op0_register!=R.RAX or klass.memory_base!=R.RIP or klass.ip_rel_memory_address!=slot or
            not _load(blob,M.MOV,R.RCX,R.RAX,0xb8,8) or dest not in (R.RCX,R.RDX) or not _load(ref,M.MOV,dest,R.RCX,0,8) or
            not _rr(test,M.TEST,dest,dest) or null.mnemonic!=M.JE or not _raise_at(by_ip,null.near_branch_target,nre)): return None
    obj=(b.end_state or {}).get(reg_name(dest))
    if (obj and not obj._unk and re.fullmatch(r't\d+',obj.text) and
            re.fullmatch(r'var '+obj.text+r' = [\w.<>]+;',b.stmts[0])): return obj


def _owner_field_append(lift,td,blocks,head,by_ip):
    # RCX already holds the list and EDX the signed item. Neither input is
    # reloaded on the resize arm, which restores the frame and tail-jumps.
    if len(head.insns)!=4 or len(head.preds)!=1 or len(head.stmts)!=1: return False
    region=_diamond(blocks,head)
    if not region: return False
    version,cap,slow,fast,store=region; prev=blocks[head.preds[0]]
    v,c,s,f,w=(b.insns for b in region)
    if (slow.succs or store.succs or list(map(len,(v,c,s,f,w)))!=[6,2,8,4,6] or not prev.insns or
            prev.insns[-1].next_ip!=head.insns[0].ip): return False
    seq=head.insns+v+c+s+f+w
    if any(a.next_ip!=b.ip for a,b in zip(seq,seq[1:])) or not all(_plain(x) for x in seq): return False
    field,item,test,null=head.insns
    if (not _load(field,M.MOV,R.RCX,R.RCX,field.memory_displacement,8) or not _load(item,M.MOV,R.EDX,R.RBX,item.memory_displacement,4) or
            not _rr(test,M.TEST,R.RCX,R.RCX) or null.mnemonic!=M.JE or
            not _fast_path(v,c,f,w[2],R.RCX,R.R9,R.R8,R.R8D,R.EDX,R.R10,null)): return False
    contract=_contract(lift,v[0].ip_rel_memory_address)
    if not contract: return False
    list_key,resize,nre,ior=contract
    if (not _raise_at(by_ip,null.near_branch_target,nre) or not _raise_at(by_ip,f[3].near_branch_target,ior) or
            not _load(s[0],M.MOV,R.RAX,R.R10,0x20,8) or not _load(s[1],M.MOV,R.R8,R.RAX,0xc0,8) or
            not _load(s[2],M.MOV,R.R8,R.R8,0x70,8) or not _jump(s[-1],M.JMP,resize) or w[-1].mnemonic!=M.RET or w[-1].op_count): return False
    for bx,si,sp,di in (s[3:-1],w[:2]+w[3:-1]):
        if (not _load(bx,M.MOV,R.RBX,R.RSP,0x30,8) or not _load(si,M.MOV,R.RSI,R.RSP,0x38,8) or
                not _sp(sp,M.ADD,32) or di.mnemonic!=M.POP or di.op0_register!=R.RDI): return False
    if not _field_frame(blocks,head): return False

    il=lift.il; slot=prev.insns[0].ip_rel_memory_address
    obj=_singleton_read(prev,slot,nre,by_ip); prop=alias_for_slot(il,slot,lift.rt_init_meta) if obj else None
    if (not prop or obj is not prev.end_state.get('RCX') or il._closed_type_key(obj.ty)!=il._closed_type_key(prop[1])): return False
    row=_own_field(il,il.meta.typedefs[prop[1][0]],field.memory_displacement,8); arg=_own_field(il,td,item.memory_displacement,4)
    if not row or il._closed_type_key(row[1])!=list_key or row[1][1]&7!=6 or not arg or il._closed_type_key(arg[1])!=(8,0): return False
    recv=head.end_state.get('RCX'); value=head.end_state.get('RDX'); this=head.end_state.get('RBX')
    if (not this or this._unk or this.text!='this' or il._closed_type_key(this.ty)!=(0x12,td.index,0) or
            not recv or recv._unk or il._closed_type_key(recv.ty)!=list_key or not re.fullmatch(r't\d+',recv.text) or
            head.stmts!=['var %s = %s%s;'%(recv.text,obj.text,row[0][4:])] or not value or value._unk or
            value.text!=arg[0] or il._closed_type_key(value.ty)!=(8,0)): return False
    # Keep identical native reloads as distinct snapshots. A store/callback
    # between the animation selection and the append may replace the owner.
    for b in blocks:
        read=_singleton_read(b,slot,nre,by_ip)
        if read and il._closed_type_key(read.ty)==il._closed_type_key(prop[1]):
            b.stmts[0]='var %s = %s;'%(read.text,acc_get(prop[0]))
    head.stmts.append('%s.Add(%s);'%(recv.text,arg[0]))
    version.preds.remove(head.bid); head.succs=[]; head.term=('ret',); head.cond=head.ret=None
    return True


def fold_terminal_appends(lift,method,td,blocks,pads):
    """Fold a terminal append or an adjoining pair; no later consumer can
    observe discarded scratch registers. Never let an unmatched join enter
    the middle of a folded group. Keep all code before the receiver load."""
    il=lift.il
    if (not HAVE_ICED or pads or not isinstance(getattr(il,'bin',None),PE) or not il.bin.is64 or method.is_static or
            il.meta.version!=31 or len(blocks)<6 or not 0<=method.return_type<len(il.types) or
            il._closed_type_key(il.types[method.return_type])!=(1,0)): return
    by_ip=None
    for head in blocks[:-5]:
        if len(head.insns)==4 and head.insns[0].mnemonic==M.MOV and head.insns[0].op0_register==R.RCX and head.insns[-1].mnemonic==M.JE:
            if by_ip is None: by_ip={x.ip:x for b in blocks for x in b.insns}
            if _owner_field_append(lift,td,blocks,head,by_ip): return
        if len(head.insns)<8 or head.insns[-8].mnemonic!=M.MOV or head.insns[-4].mnemonic!=M.CALL: continue
        if by_ip is None: by_ip={x.ip:x for b in blocks for x in b.insns}
        arm=_arm(lift,td,blocks,head,by_ip)
        if not arm: continue
        lines=[arm[0]]; last=arm
        if not arm[1]:
            i=head.bid
            if i+6>=len(blocks): continue
            nxt=blocks[i+6]
            if (len(nxt.insns)!=8 or len(nxt.stmts)!=1 or set(nxt.preds)!={i+3,i+5} or
                    head.insns[-8].op0_register==R.RBX): continue
            last=_arm(lift,td,blocks,nxt,by_ip)
            if not last or not last[1]: continue
            lines.append(last[0])
        if not _saved_this(blocks,last[2]): continue
        head.stmts[-1:]=lines
        blocks[head.bid+1].preds.remove(head.bid)
        head.succs=[]; head.term=('ret',); head.ret=None; head.cond=None
        return
