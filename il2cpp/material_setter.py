"""Fold equivalent Renderer material setters, keeping the component lookup at its call."""
import re

from il2cpp.awaiter import _object_new_abi, _unused_return
from il2cpp.binary import PE
from il2cpp.expr import Expr, acc_get
from il2cpp.generic_array import object_shared_entry
from il2cpp.marshalled_getter import _INIT, _READY, _plain_null_exit, _throw_null_object
from il2cpp.prelude import HAVE_ICED
from il2cpp.reparent import _context_independent, _marshal_slot
from il2cpp.shared_action import _raises_on_null
from il2cpp.shared_getter import getter_alias
from il2cpp.sret_copy import _own_field
from il2cpp.text import reg_name, sdisp

if HAVE_ICED:
    from iced_x86 import Mnemonic as M, OpKind as K, Register as R


_ENTRY = re.compile(rb'\x48\x89\x5c\x24\x18\x55\x48\x83\xec\x20\x80\x3d(.{4})\x00\x48\x8b\xea\x48\x8b\xd9\x75(.)',re.S)
# Null managed self throws. A missing cached native self invokes ThrowHelper
# on the original managed object. Null material stays zero on either cache path.
_OBJECTS = re.compile(rb'\x48\x85\xdb\x74(.)\x48\x89\x74\x24\x30\x48\x89\x7c\x24\x38\x48\x8b\x73(.)'
                      rb'\x33\xff\x48\x85\xf6\x75\x0c\x33\xd2\x48\x8b\xcb\xe8(.{4})\x8b\xf7'
                      rb'\x48\x8b\x0d(.{4})\x48\x39\x79\x38\x75\x05\xe8(.{4})\x48\x85\xed\x74\x04\x48\x8b\x7d(.)',re.S)
_TAIL = re.compile(rb'\x48\x8b\x05(.{4})\x48\x85\xc0\x75\x13\x48\x8d\x0d(.{4})\xe8(.{4})\x48\x89\x05(.{4})'
                   rb'\x48\x8b\xd7\x48\x8b\xce\x48\x8b\x7c\x24\x38\x48\x8b\x74\x24\x30\x48\x8b\x5c\x24\x40'
                   rb'\x48\x83\xc4\x20\x5d\x48\xff\xe0',re.S)


def _alias(lift, addr):
    il=lift.il; ids=il.addr_candidates.get(addr,())
    if len(ids)!=3 or any(k!='method' or not 0<=mi<len(il.meta.methods) for k,mi in ids):
        return None
    methods=[il.meta.methods[mi] for _,mi in ids]; owner=methods[0].declaring
    if not 0<=owner<len(il.meta.typedefs) or il.typedef_full(owner)!='UnityEngine.Renderer':
        return None
    args=set(); members=set()
    for m in methods:
        ps=il.meta.method_params(m)
        if (m.declaring!=owner or m.addr!=addr or m.is_static or m.flags&0x40 or m.generic_container!=-1 or
                m.param_count!=1 or len(ps)!=1 or not 0<=ps[0].type<len(il.types) or not 0<=m.return_type<len(il.types) or
                il._closed_type_key(il.types[m.return_type])!=(1,0)):
            return None
        pt=il.types[ps[0].type]; prop=lift._accessor_prop(m.index)
        if not pt or il._closed_type_key(pt)!=(0x12,pt[0],0) or il.type_name(pt)!='UnityEngine.Material':
            return None
        args.add(pt[0]); members.add((m.name,m.flags&7,prop))
    if len(args)!=1 or members!={('SetMaterial',1,None),('set_material',6,('set','material',0)),
                                ('set_sharedMaterial',6,('set','sharedMaterial',0))}:
        return None
    material,=args; end=il.next_method_start(addr)
    if not end or not 0<end-addr<=384 or not il.bin.is_exec_va(addr):
        return None
    data=il.bin.read(addr,end-addr) or b''
    def rel(match,n,trailing=0):
        return addr+match.end(n)+trailing+int.from_bytes(match[n],'little',signed=True)
    entry=_ENTRY.match(data)
    if not entry:
        return None
    pos=entry.end(); slots=[]
    while (init:=_INIT.match(data,pos)):
        if rel(init,2)!=lift.rt_init_meta:
            return None
        slots.append(rel(init,1));pos=init.end()
    ready=_READY.match(data,pos)
    if (len(slots)!=2 or not ready or rel(ready,1,1)!=rel(entry,1,1) or rel(entry,2)!=addr+ready.end() or
            not _marshal_slot(il,slots[0],'MarshalNotNull',owner) or not _marshal_slot(il,slots[1],'Marshal',material)):
        return None
    obj=_OBJECTS.match(data,ready.end()); tail=_TAIL.match(data,obj.end()) if obj else None
    if (not tail or not _plain_null_exit(lift,addr,data,tail.end(),rel(obj,1)) or
            not _throw_null_object(il,rel(obj,3)) or rel(obj,4)!=slots[1] or
            not _context_independent(il,rel(obj,5))):
        return None
    for ti,n in ((owner,2),(material,6)):
        f=(il.instance_field_chain(ti) or {}).get(int.from_bytes(obj[n],'little',signed=True))
        if not f or f[0]!='m_CachedPtr' or not 0<=f[1]<len(il.types) or il._closed_type_key(il.types[f[1]])!=(0x18,0):
            return None
    sig='UnityEngine.Renderer::SetMaterial_Injected(System.IntPtr,System.IntPtr)'
    if (rel(tail,1)!=rel(tail,4) or rel(tail,3)!=il.rt_icall_resolve or il.icall_cells.get(rel(tail,1))!=sig or
            il.bin.cstr(rel(tail,2),512)!=sig):
        return None
    mi=(il._icall_annotation(sig) or {}).get('method',-1)
    if 0<=mi<len(il.meta.methods):
        m=il.meta.methods[mi]; ps=il.meta.method_params(m)
        if (m.declaring==owner and m.name=='SetMaterial_Injected' and m.is_static and m.iflags&0x1000 and m.generic_container==-1 and
                m.param_count==len(ps)==2 and all(0<=p.type<len(il.types) and il._closed_type_key(il.types[p.type])==(0x18,0) for p in ps)
                and 0<=m.return_type<len(il.types) and il._closed_type_key(il.types[m.return_type])==(1,0)):
            return owner,material


def _lookup(lift, pred, renderer):
    seq=pred.insns
    if len(seq)<4:
        return None
    load=seq[-4]; call,test,null=seq[-3:]
    if load.mnemonic==M.MOV and load.op0_register==R.RCX and load.op1_register in (R.RAX,R.RBX,R.RDI,R.RSI,R.RBP,R.R12,R.R13,R.R14,R.R15) and len(seq)>=5:
        if seq[-5].next_ip!=load.ip: return None
        load=seq[-5]
    if (load.mnemonic!=M.MOV or load.op0_register!=R.RDX or load.memory_base!=R.RIP or load.has_segment_prefix or
            call.mnemonic!=M.CALL or call.op0_kind!=K.NEAR_BRANCH64 or test.mnemonic!=M.TEST or test.op0_register!=test.op1_register or
            test.op0_register!=R.RAX or null.mnemonic!=M.JE or null.op0_kind!=K.NEAR_BRANCH64 or not _raises_on_null(lift,null) or
            any(a.next_ip!=b.ip for a,b in zip(seq[-4:],seq[-3:]))):
        return None
    return _component(lift,load,call,renderer,'GetComponent',True)


def _component(lift, load, call, renderer, name, checked):
    il = lift.il
    usage=il.decode_slot(load.ip_rel_memory_address) or {}; si=usage.get('idx',-1)
    if usage.get('kind')!=6 or not 0<=si<len(il.method_specs): return None
    mi,ci,gi=il.method_specs[si]
    if not 0<=mi<len(il.meta.methods) or ci!=-1: return None
    m=il.meta.methods[mi]; actual=il._method_spec_type_args(gi)
    if (m.name!=name or il.typedef_full(m.declaring) not in ('UnityEngine.Component','UnityEngine.GameObject') or
            m.is_static or m.flags&7!=6 or m.flags&0x40 or m.param_count or m.generic_container<0 or
            not actual or len(actual)!=1 or not actual[0] or il._closed_type_key(actual[0])!=(0x12,actual[0][0],0) or
            renderer not in il.base_chain_tds(actual[0][0]) or object_shared_entry(il,mi)!=call.near_branch_target or
            il._closed_type_key(il.candidate_return_type(('generic',si)))!=il._closed_type_key(actual[0])):
        return None
    return call.ip, (si,m.declaring,actual[0],name,checked)


def _factory_after(il, seq):
    """A nullary generic factory entered with its own MethodRef in RCX
    supersedes the setter's return. No incoming RAX or FP argument."""
    if len(seq)<2: return False
    slot,call=seq[:2]
    if (slot.mnemonic!=M.MOV or slot.op0_register!=R.RCX or slot.memory_base!=R.RIP or slot.has_segment_prefix or
            call.mnemonic!=M.CALL or call.op0_kind!=K.NEAR_BRANCH64 or slot.next_ip!=call.ip): return False
    u=il.decode_slot(slot.ip_rel_memory_address) or {}; si=u.get('idx',-1)
    if u.get('kind')!=6 or not 0<=si<len(il.method_specs): return False
    mi,ci,gi=il.method_specs[si]
    if not 0<=mi<len(il.meta.methods) or ci!=-1: return False
    m=il.meta.methods[mi]; args=il._method_spec_type_args(gi)
    return (m.is_static and m.name=='CreateInstance' and il.typedef_full(m.declaring)=='UnityEngine.ScriptableObject' and
            m.generic_container>=0 and m.param_count==0 and args and len(args)==1 and args[0] and
            il._closed_type_key(args[0])==(0x12,args[0][0],0) and il.candidate_return_type(('generic',si))==args[0] and
            object_shared_entry(il,mi)==call.near_branch_target)


def _direct(il,i,owner,name,static,params,rt):
    if i.mnemonic!=M.CALL or i.op0_kind!=K.NEAR_BRANCH64: return False
    ids=il.addr_candidates.get(i.near_branch_target,())
    if len(ids)!=1 or ids[0][0]!='method' or not 0<=ids[0][1]<len(il.meta.methods): return False
    m=il.meta.methods[ids[0][1]]; ps=il.meta.method_params(m)
    return (m.addr==i.near_branch_target and il.typedef_full(m.declaring)==owner and m.name==name and
            m.is_static==static and m.generic_container==-1 and m.flags&7==6 and not m.flags&0x40 and
            m.param_count==len(ps)==len(params) and all(0<=p.type<len(il.types) for p in ps) and
            [il._closed_type_key(il.types[p.type]) for p in ps]==params and 0<=m.return_type<len(il.types) and
            il._closed_type_key(il.types[m.return_type])==rt)


def _constructed(lift,method,blocks,b,owner,material):
    # The field is captured BEFORE Shader.Find, but its null check is AFTER
    # the constructor. Emitting `this.field.sharedMaterial = new ...` or
    # re-reading the field after the constructor loses one of those facts.
    il=lift.il; seq=b.insns; pred=blocks[b.preds[0]]
    if len(seq)!=7 or len(pred.insns)<14 or len(b.succs)!=1 or not 0<=b.succs[0]<len(blocks): return None
    clear,arg,recv,setter,reload,test2,null2=seq
    string,ctx,save,find,klass,save_shader,alloc,ctor_ctx,shader,obj,save_obj,ctor,test,null=pred.insns[-14:]
    if not (_zero(clear,R.R8D) and _move(arg,R.RDX,R.RBP) and _move(recv,R.RCX,R.RSI) and
            string.mnemonic==M.MOV and string.op0_register==R.RCX and string.memory_base==R.RIP and
            (il.decode_slot(string.ip_rel_memory_address) or {}).get('kind')==5 and _zero(ctx,R.EDX) and
            save.mnemonic==M.MOV and save.op0_register==R.RSI and save.memory_base==R.RDI and save.memory_index==R.NONE and
            klass.mnemonic==M.MOV and klass.op0_register==R.RCX and klass.memory_base==R.RIP and
            _move(save_shader,R.RBX,R.RAX) and alloc.mnemonic==M.CALL and alloc.op0_kind==K.NEAR_BRANCH64 and
            _object_new_abi(lift,alloc.near_branch_target) and _zero(ctor_ctx,R.R8D) and _move(shader,R.RDX,R.RBX) and
            _move(obj,R.RCX,R.RAX) and _move(save_obj,R.RBP,R.RAX) and test.mnemonic==M.TEST and test.op0_register==test.op1_register==R.RSI and
            reload.mnemonic==M.MOV and reload.op0_register==R.RCX and reload.memory_base==save.memory_base and
            reload.memory_displacement==save.memory_displacement and reload.memory_index==R.NONE and
            test2.mnemonic==M.TEST and test2.op0_register==test2.op1_register==R.RCX and
            all(i.mnemonic==M.JE and i.op0_kind==K.NEAR_BRANCH64 and _raises_on_null(lift,i) for i in (null,null2))): return None
    full=pred.insns[-14:]+seq
    if any(i.has_segment_prefix for i in full) or any(x.next_ip!=z.ip for x,z in zip(full,full[1:])): return None
    use=il.decode_slot(klass.ip_rel_memory_address) or {}; ids=il.addr_candidates.get(find.near_branch_target,())
    if (use.get('kind')!=1 or il._closed_type_key(use.get('type'))!=(0x12,material,0) or
            len(ids)!=1 or ids[0][0]!='method' or not 0<=ids[0][1]<len(il.meta.methods)): return None
    shader_td=il.meta.methods[ids[0][1]].declaring; shader_type=(0x12,shader_td,0)
    if not (_direct(il,find,'UnityEngine.Shader','Find',True,[(0x0e,0)],shader_type) and
            _direct(il,ctor,'UnityEngine.Material','.ctor',False,[shader_type],(1,0))): return None
    field=_own_field(il,il.meta.typedefs[method.declaring],sdisp(save.memory_displacement),8)
    if not field or not field[1] or il._closed_type_key(field[1])!=(0x12,field[1][0],0) or owner not in il.base_chain_tds(field[1][0]): return None
    # The next nullary getter takes only the freshly reloaded receiver and
    # zero MethodInfo; neither the setter's RAX nor XMM0 is consumed.
    succ=blocks[b.succs[0]]; next_seq=succ.insns
    if len(next_seq)<2 or succ.preds!=[b.bid] or next_seq[0].ip!=null2.next_ip or next_seq[0].next_ip!=next_seq[1].ip or not _zero(next_seq[0],R.EDX): return None
    read=next_seq[1]
    if (read.mnemonic!=M.CALL or read.op0_kind!=K.NEAR_BRANCH64 or
            getter_alias(lift,read.near_branch_target,owner)!=('sharedMaterial',il.typedef_full(owner))): return None
    return ({save.ip:(field,R.RSI,R.RDI),reload.ip:(field,R.RCX,R.RDI)},
            (save.ip,None,material,owner),{read.ip:(reload.ip,owner,'sharedMaterial')})


def _zero(i,r):
    return i.mnemonic==M.XOR and i.op0_register==i.op1_register==r


def _move(i,dst,src):
    return i.mnemonic==M.MOV and i.op0_register==dst and i.op1_register==src


def material_sites(lift, method, blocks, pads):
    lookups, sites, captures, reads={},{},{},{}; il=lift.il
    if (not HAVE_ICED or pads or method.is_static or not isinstance(getattr(il,'bin',None),PE) or not il.bin.is64 or getattr(il.meta,'version',None)!=31 or
            not 0<=method.return_type<len(il.types) or il._closed_type_key(il.types[method.return_type])!=(1,0)):
        return lookups,sites,captures,reads
    cache=il.__dict__.setdefault('_material_aliases',{})
    for b in blocks:
        seq=b.insns
        if len(seq)<4 or len(b.preds)!=1 or not 0<=b.preds[0]<len(blocks): continue
        load,hidden,receiver=seq[:3]
        # Same component lookup followed by the per-renderer material getter.
        # `material` can clone a material; only credit its own injected read,
        # never substitute a `sharedMaterial` read based on the return type.
        if (_zero(load,R.EDX) and _move(hidden,R.RCX,R.RAX) and receiver.mnemonic==M.CALL and
                receiver.op0_kind==K.NEAR_BRANCH64 and load.next_ip==hidden.ip and hidden.next_ip==receiver.ip):
            addr=receiver.near_branch_target; ids=il.addr_candidates.get(addr,())
            if len(ids)==2 and all(k=='method' and 0<=mi<len(il.meta.methods) for k,mi in ids):
                owner=il.meta.methods[ids[0][1]].declaring; pred=blocks[b.preds[0]]
                if (il.typedef_full(owner)=='UnityEngine.Renderer' and pred.insns and pred.insns[-1].next_ip==load.ip and
                        getter_alias(lift,addr,owner)==('material','UnityEngine.Renderer')):
                    lookup=_lookup(lift,pred,owner)
                    if lookup:
                        lookups[lookup[0]]=lookup[1]; reads[receiver.ip]=(lookup[0],owner,'material')
        if _zero(load,R.R8D) and seq[3].mnemonic==M.CALL and seq[3].op0_kind==K.NEAR_BRANCH64:
            addr=seq[3].near_branch_target
            if len(il.addr_candidates.get(addr,()))==3:
                if addr not in cache: cache[addr]=_alias(lift,addr)
                plan=_constructed(lift,method,blocks,b,*cache[addr]) if cache[addr] else None
                if plan:
                    captures.update(plan[0]); sites[seq[3].ip]=plan[1]; reads.update(plan[2])
        if (load.mnemonic!=M.MOV or load.op0_register!=R.RDX or load.op1_kind!=K.MEMORY or load.has_segment_prefix or load.memory_index!=R.NONE or
                load.memory_base not in (R.RBX,R.RDI,R.RSI,R.RBP,R.R12,R.R13,R.R14,R.R15) or hidden.mnemonic!=M.XOR or
                hidden.op0_register!=hidden.op1_register or hidden.op0_register!=R.R8D or receiver.mnemonic!=M.MOV or
                receiver.op0_register!=R.RCX or receiver.op1_register!=R.RAX): continue
        j=3
        if seq[j].mnemonic!=M.CALL:
            if len(seq)!=7: continue
            restore,sp,pop,tail=seq[3:]
            if (restore.mnemonic!=M.MOV or restore.op0_register!=R.RBX or restore.memory_base!=R.RSP or restore.memory_index!=R.NONE or
                    restore.has_segment_prefix or restore.memory_displacement!=0x30 or sp.mnemonic!=M.ADD or sp.op0_register!=R.RSP or
                    sp.op1_kind!=K.IMMEDIATE8TO64 or sp.immediate8to64!=0x20 or
                    pop.mnemonic!=M.POP or pop.op0_register!=R.RDI or tail.mnemonic!=M.JMP or b.succs): continue
            j=6
        i=seq[j]; addr=i.near_branch_target
        if i.op0_kind!=K.NEAR_BRANCH64 or len(il.addr_candidates.get(addr,()))!=3 or any(x.next_ip!=z.ip for x,z in zip(seq[:j],seq[1:j+1])): continue
        if addr not in cache: cache[addr]=_alias(lift,addr)
        ids=cache[addr]; pred=blocks[b.preds[0]]
        if not ids or not pred.insns or pred.insns[-1].next_ip!=load.ip or pred.insns[-1].near_branch_target==load.ip: continue
        lookup=_lookup(lift,pred,ids[0])
        if not lookup or (i.mnemonic==M.CALL and not _unused_return(lift,i.next_ip) and
                          not _factory_after(il,seq[j+1:])): continue
        field=_own_field(il,il.meta.typedefs[method.declaring],sdisp(load.memory_displacement),8)
        if field and il._closed_type_key(field[1])==(0x12,ids[1],0):
            lookups[lookup[0]]=lookup[1]; sites[i.ip]=(lookup[0],field[0],ids[1],ids[0])
    if captures:
        # The new LineRenderer itself comes from a closed generic call. It
        # is assigned into the field before being null-checked: don't invent
        # the eager null check used by the GetComponent -> setter window.
        for b in blocks:
            for j,i in enumerate(b.insns):
                if j<2 or i.mnemonic!=M.CALL or i.op0_kind!=K.NEAR_BRANCH64: continue
                slot,recv=b.insns[j-2:j]
                if (slot.mnemonic!=M.MOV or slot.op0_register!=R.RDX or slot.memory_base!=R.RIP or slot.has_segment_prefix or
                        recv.mnemonic!=M.MOV or recv.op0_register!=R.RCX or recv.op1_kind!=K.REGISTER or
                        slot.next_ip!=recv.ip or recv.next_ip!=i.ip): continue
                for field,_,_ in captures.values():
                    binding=_component(lift,slot,i,field[1][0],'AddComponent',False)
                    if binding: lookups[i.ip]=binding[1]
    return lookups,sites,captures,reads


def snapshot(lift,i):
    (field,ty),dst,reg=lift._material_captures[i.ip]; base=dict.get(lift.regs,reg_name(reg))
    if (not base or base._unk or base.text!='this' or
            lift.il._closed_type_key(base.ty)!=(0x12,lift._current_td.index,0)): return False
    name=lift.new_var();lift._var_types[name]=ty
    lift.emit(i.ip,'var %s = %s;'%(name,acc_get(field)),None)
    value=Expr(name,ty,'obj');lift.regs[reg_name(dst)]=value;lift._material_values[i.ip]=value
    return True


def material_read(lift,ins,values):
    binding=getattr(lift,'_material_reads',{}).get(ins.ip)
    if binding and values and values[0] is not None and lift._material_values.get(binding[0]) is values[0]:
        name=values[0].text
        if re.fullmatch(r't\d+',name):
            return acc_get('((%s)%s).%s'%(lift.il.typedef_full(binding[1]),name,binding[2]))+' /* shared getter */'


def assignment(lift,ins):
    origin,field,mat,owner=lift._material_sites[ins.ip]
    recv,arg,hidden=(dict.get(lift.regs,r) for r in ('RCX','RDX','R8'))
    if (not recv or recv._unk or lift._material_values.get(origin) is not recv or not re.fullmatch(r't\d+',recv.text) or
            not arg or arg._unk or lift.il._closed_type_key(arg.ty)!=(0x12,mat,0) or not hidden or hidden._unk or hidden.text!='0'):
        return None
    if field is not None and arg.text!=field or field is None and not re.fullmatch(r't\d+',arg.text):
        return None
    # Cast a subclass to the declaring type so a hidden property cannot win.
    r=recv.text if recv.ty[0]==owner else '((%s)%s)'%(lift.il.typedef_full(owner),recv.text)
    return '%s.sharedMaterial = %s /* shared implementation */;'%(r,arg.text)
