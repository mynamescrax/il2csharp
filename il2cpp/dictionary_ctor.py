"""Closed dictionary constructor into a Win64 getter's hidden result buffer."""
import json

from il2cpp.awaiter import _object_new_abi, _spec_entry
from il2cpp.binary import PE
from il2cpp.codegen_ident import codegen_names
from il2cpp.csharp import FA_STATIC, FA_LITERAL, FA_INITONLY, field_attrs, source_field_name
from il2cpp.names import safe_ident, sanitize
from il2cpp.prelude import HAVE_ICED

if HAVE_ICED:
    from iced_x86 import Decoder, Mnemonic as M, OpKind as K, Register as R


def _load(i,dst,base,off,mn=None):
    return i.mnemonic==(mn or M.MOV) and i.op0_register==dst and i.memory_base==base and i.memory_displacement==off


def _store(i,base,off,src,mn=None):
    return i.mnemonic==(mn or M.MOV) and i.memory_base==base and i.memory_displacement==off and i.op1_register==src


def _rr(i,mn,dst,src): return i.mnemonic==mn and i.op0_register==dst and i.op1_register==src


def _sp(i,mn,n): return i.mnemonic==mn and i.op0_register==R.RSP and i.op1_kind==K.IMMEDIATE8TO64 and i.immediate8to64==n


def _call(i): return i.mnemonic==M.CALL and i.op0_kind==K.NEAR_BRANCH64


def _slot(i,reg,mn):
    return i.ip_rel_memory_address if i.mnemonic==mn and i.op0_register==reg and i.memory_base==R.RIP else None


def _method(il,i):
    ids=il.addr_candidates.get(i.near_branch_target,())
    if _call(i) and len(ids)==1 and ids[0][0]=='method' and 0<=ids[0][1]<len(il.meta.methods):
        m=il.meta.methods[ids[0][1]]
        if m.addr==i.near_branch_target: return m


def _constructor(il,rt,slot,call):
    """Resolve ctor(K,V) from the stack MethodRef, including both interface parameters."""
    u=il.decode_slot(slot) or {}; si=u.get('idx',-1)
    if u.get('kind')!=6 or not 0<=si<len(il.method_specs) or not _call(call): return None
    mi,ci,gi=il.method_specs[si]; args=il._method_spec_type_args(ci)
    if gi!=-1 or not 0<=mi<len(il.meta.methods) or not args or len(args)!=2: return None
    md=il.meta.methods[mi];td=il.meta.typedefs[md.declaring]; ps=il.meta.method_params(md); key=il._closed_type_key
    if (il.typedef_full(td.index)!='Fusion.NetworkDictionary`2' or not td.is_valuetype or
            md.name!='.ctor' or md.is_static or md.generic_container!=-1 or md.flags&7!=6 or md.param_count!=len(ps) or len(ps)!=4 or
            not all(0<=p.type<len(il.types) for p in ps) or not 0<=md.return_type<len(il.types) or key(il.types[md.return_type])!=(1,0) or
            not 0<=td.generic_container<len(il.meta.generic_containers) or not all(key(t) for t in args) or
            key(rt)!=(0x15,(0x11,td.index,0),tuple(key(t) for t in args),0) or _spec_entry(il,si,mi)!=call.near_branch_target): return None
    data,capacity,*readers=[il.types[p.type] for p in ps]
    owner,n,is_method,start=il.meta.generic_containers[td.generic_container]
    if key(data)!=(0x0f,(8,0),0) or key(capacity)!=(8,0) or (owner,n,is_method)!=(td.index,2,0): return None
    expected=[]
    for i,reader in enumerate(readers):
        if not reader or il._type_enum(reader)!=0x15 or reader[1]&(1<<29): return None
        ti=il.td_of_ty(reader); vars=il._generic_inst_args(reader)
        if (ti is None or il.typedef_full(ti)!='Fusion.IElementReaderWriter`1' or not il.meta.typedefs[ti].flags&0x20 or
                not vars or len(vars)!=1 or not vars[0] or il._type_enum(vars[0])!=0x13 or vars[0][1]&(1<<29) or vars[0][0]!=start+i): return None
        expected.append((0x15,(0x12,ti,0),(key(args[i]),),0))
    return expected


def _reader(il,caller,i,expected):
    m=_method(il,i)
    if (not m or not m.is_static or m.flags&7!=6 or m.param_count or m.generic_container!=-1 or m.name!='GetInstance' or
            not 0<=m.return_type<len(il.types) or il._closed_type_key(il.types[m.return_type])!=expected): return None
    td=il.meta.typedefs[m.declaring]
    if td.declaring>=0 or td.generic_container!=-1 or td.flags&7!=1 and m.image!=caller.image: return None
    old=safe_ident(sanitize(td.name)); new=codegen_names(il).get((td.namespace,old),old)
    if not new.isidentifier(): return None
    return (td.namespace+'.' if td.namespace else '')+new+'.GetInstance()'


def _error_message(lift,method,seq):
    """Verify the type, untruncated message, allocation, ctor and noreturn helper."""
    if len(seq)!=17: return None
    il=lift.il
    klass,init,obj,alloc,lit,park,read,msg,hid,self_arg,ctor,token,ctx,ctx_arg,ex_arg,raise_call,end=seq
    if not all(_call(i) for i in (init,alloc,read,ctor,ctx,raise_call)) or end.mnemonic!=M.INT3: return None
    if (not _rr(obj,M.MOV,R.RCX,R.RAX) or not _object_new_abi(lift,alloc.near_branch_target) or not _rr(park,M.MOV,R.RBX,R.RAX) or
            not _rr(msg,M.MOV,R.RDX,R.RAX) or not _rr(hid,M.XOR,R.R8D,R.R8D) or not _rr(self_arg,M.MOV,R.RCX,R.RBX) or
            not _rr(ctx_arg,M.MOV,R.RDX,R.RAX) or not _rr(ex_arg,M.MOV,R.RCX,R.RBX)): return None
    if init.near_branch_target!=read.near_branch_target or init.near_branch_target!=ctx.near_branch_target: return None
    core=il.bin.read(init.near_branch_target,5) or b''; wrapper=il.bin.read(lift.rt_init_meta,9) or b''
    if (len(core)!=5 or core[0]!=0xe9 or len(wrapper)!=9 or wrapper[:5]!=bytes.fromhex('4883ec28 e8') or
            init.near_branch_target+5+int.from_bytes(core[1:],'little',signed=True)!=lift.rt_init_meta+9+int.from_bytes(wrapper[5:],'little',signed=True)): return None
    slots=[_slot(i,R.RCX,M.LEA) for i in (klass,lit,token)]
    if not all(slots): return None
    exc,literal,context=[il.decode_slot(s) or {} for s in slots]; md=_method(il,ctor)
    if (not md or md.name!='.ctor' or md.is_static or il.typedef_full(md.declaring)!='System.InvalidOperationException' or
            md.param_count!=1 or exc.get('kind')!=1 or exc.get('td')!=md.declaring or literal.get('kind')!=5 or
            context.get('kind')!=3 or context.get('idx')!=method.index): return None
    ps=il.meta.method_params(md); idx=literal.get('idx',-1)
    if len(ps)!=1 or il._closed_type_key(il.types[ps[0].type])!=(0x0e,0) or not 0<=idx<len(il.meta.string_literals): return None
    # The helper clears the newly constructed exception's two trace fields,
    # then forwards exception + MethodInfo to the core used by the C export.
    addr=raise_call.near_branch_target; lo,hi=il.function_extent(addr)
    if lo!=addr or not 0<hi-lo<=64: return None
    ii=list(Decoder(64,il.bin.read(lo,hi-lo) or b'',ip=lo))
    if len(ii)!=13 or any(x.has_segment_prefix or x.memory_index!=R.NONE for x in ii): return None
    save,push,sp,a,b,offset,c1,other,c2,d,c,throw,trap=ii
    if (not _store(save,R.RSP,8,R.RBX) or push.mnemonic!=M.PUSH or push.op0_register!=R.RDI or not _sp(sp,M.SUB,32) or
            not _rr(a,M.MOV,R.RDI,R.RCX) or not _rr(b,M.MOV,R.RBX,R.RDX) or offset.mnemonic!=M.ADD or offset.op0_register!=R.RCX or
            offset.op1_kind!=K.IMMEDIATE8TO64 or offset.immediate8to64!=0x38 or not _load(other,R.RCX,R.RDI,0x40,M.LEA) or
            not _call(c1) or not _call(c2) or c1.near_branch_target!=c2.near_branch_target or
            il.bin.read(c1.near_branch_target,8)!=bytes.fromhex('48c70100000000c3') or not _rr(d,M.MOV,R.RDX,R.RBX) or not _rr(c,M.MOV,R.RCX,R.RDI) or
            not _call(throw) or trap.mnemonic!=M.INT3): return None
    chain=il.instance_field_chain(md.declaring) or {}
    if [chain.get(off,(None,))[0] for off in (0x38,0x40)]!=['_stackTrace','_stackTraceString']: return None
    exports=[p for p,n in il.bin.exports.items() if n=='il2cpp_raise_exception']
    if len(exports)!=1:return None
    e=exports[0];code=il.bin.read(e,12) or b''
    if (len(code)!=12 or code[:7]!=bytes.fromhex('4883ec28 33d2 e8') or code[-1]!=0xcc or
            e+11+int.from_bytes(code[7:11],'little',signed=True)!=throw.near_branch_target): return None
    return json.dumps(il.meta.string_literal(idx),ensure_ascii=True)


def _metadata_guard(lift,cmp,branch,token,init,ready,join,slot):
    return (cmp.mnemonic==M.CMP and cmp.memory_base==R.RIP and cmp.memory_size==1 and cmp.op1_kind==K.IMMEDIATE8 and cmp.immediate8==0 and
            branch.mnemonic==M.JNE and branch.near_branch_target==join.ip and _slot(token,R.RCX,M.LEA)==slot and
            _call(init) and init.near_branch_target==lift.rt_init_meta and ready.mnemonic==M.MOV and ready.memory_base==R.RIP and
            ready.ip_rel_memory_address==cmp.ip_rel_memory_address and ready.op1_kind==K.IMMEDIATE8 and ready.immediate8==1)


def _cache_flow(lift,seq,slot,inline):
    """Cold: box the zero byte of this reader type, publish it with a write
    barrier. Hot: keep the existing reference. Both reload the static field."""
    if len(seq)!=(17 if inline else 16): return False
    klass,blob,check,hot,addr,zero=seq[:6]; k=6
    klass_reg,blob_reg=(R.RAX,R.RDX) if inline else (R.RCX,R.RAX)
    home=0x40 if inline else 0x38  # unused incoming home above this function's 0x30/0x28 frame
    if inline:
        if not _rr(seq[k],M.MOV,R.RCX,R.RAX): return False
        k+=1
    box,again,stat,store,barrier_arg,again2,dest,barrier,reload,last=seq[k:]
    return (_slot(klass,klass_reg,M.MOV)==slot and _load(blob,blob_reg,klass_reg,0xb8) and
            check.mnemonic==M.CMP and check.memory_base==blob_reg and not check.memory_displacement and
            check.op1_kind==K.IMMEDIATE8TO64 and check.immediate8to64==0 and hot.mnemonic==M.JNE and
            hot.near_branch_target==(last.ip if inline else last.next_ip) and _load(addr,R.RDX,R.RSP,home,M.LEA) and
            zero.mnemonic==M.MOV and zero.memory_base==R.RSP and zero.memory_displacement==home and zero.op1_kind==K.IMMEDIATE8 and zero.immediate8==0 and
            _call(box) and box.near_branch_target==lift.rt_value_box and lift.il.bin.exports.get(box.near_branch_target)=='il2cpp_value_box' and
            _slot(again,R.RCX,M.MOV)==slot and _load(stat,R.RDX,R.RCX,0xb8) and _store(store,R.RDX,0,R.RAX) and
            _rr(barrier_arg,M.MOV,R.RDX,R.RAX) and _slot(again2,R.RCX,M.MOV)==slot and _load(dest,R.RCX,R.RCX,0xb8) and
            _call(barrier) and barrier.near_branch_target in lift.rt_wbarrier and _slot(reload,R.RAX,M.MOV)==slot and _load(last,R.RAX,R.RAX,0xb8))


def _cache_contract(lift,m,td,seq):
    il=lift.il
    if (len(seq)!=25 or not m.is_static or m.name!='GetInstance' or m.param_count or m.generic_container!=-1 or m.flags&7!=6 or
            not td.is_valuetype or td.is_enum or td.has_cctor or td.generic_container!=-1 or td.declaring>=0 or
            il.value_type_size(td.index)!=1 or td.field_count!=1 or td.interfaces_count!=1 or not 0<=m.return_type<len(il.types)): return None
    sub,cmp,branch,token,init,ready=seq[:6];last,add,ret=seq[-3:];slot=_slot(token,R.RCX,M.LEA)
    if (not slot or not _sp(sub,M.SUB,40) or not _metadata_guard(lift,cmp,branch,token,init,ready,seq[6],slot) or
            not _cache_flow(lift,seq[6:22],slot,False) or not _load(last,R.RAX,R.RAX,0) or not _sp(add,M.ADD,40) or ret.mnemonic!=M.RET or ret.op_count):return None
    u=il.decode_slot(slot) or {};fi=td.field_start; field=il.meta.fields[fi]; attrs=field_attrs(il,field)
    if (u.get('kind')!=1 or u.get('td')!=td.index or il._closed_type_key(u.get('type'))!=(0x11,td.index,0) or
            not attrs&FA_STATIC or attrs&(FA_LITERAL|FA_INITONLY) or list(il.field_offsets[td.index])!=[0] or not 0<=field.type<len(il.types)): return None
    rt=il.types[m.return_type]; interface=il.td_of_ty(rt); key=il._closed_type_key(rt)
    ii=il.meta.interfaces[td.interfaces_start]
    if (interface is None or il.typedef_full(interface)!='Fusion.IElementReaderWriter`1' or not key or key[0]!=0x15 or key[-1] or
            not 0<=ii<len(il.types) or key!=il._closed_type_key(il.types[ii]) or key!=il._closed_type_key(il.types[field.type])):return None
    old=safe_ident(sanitize(td.name)); name=codegen_names(il).get((td.namespace,old),old); member=safe_ident(source_field_name(il,fi))
    if not name.isidentifier() or not member.isidentifier(): return None
    return slot,key,(td.namespace+'.' if td.namespace else '')+name,member


def _plain(seq):
    return not any(i.has_segment_prefix or i.has_lock_prefix or i.has_rep_prefix or i.has_repne_prefix or i.memory_index!=R.NONE for i in seq)


def _inlined_reader(lift,slot,expected):
    il=lift.il; u=il.decode_slot(slot) or {};ti=u.get('td',-1)
    if u.get('kind')!=1 or not 0<=ti<len(il.meta.typedefs): return None
    td=il.meta.typedefs[ti]; matches=[]
    for j in il.meta.type_methods(td):
        m=il.meta.methods[j]
        if m.name!='GetInstance' or not m.addr or ('method',j) not in il.addr_candidates.get(m.addr,()):continue
        lo,hi=il.function_extent(m.addr)
        if lo!=m.addr or not il.bin.is_exec_va(lo) or not 0<hi-lo<=192:continue
        seq=list(Decoder(64,il.bin.read(lo,hi-lo) or b'',ip=lo))
        contract=_cache_contract(lift,m,td,seq) if _plain(seq) else None
        if contract and contract[:2]==(slot,expected): matches.append(contract[2]+'.GetInstance()')
    return matches[0] if len(matches)==1 else None


def _inline_value_getter(lift,method,td,rt,seq):
    il=lift.il; save,push,sub,cmp,self0,out,hot,token,init,ready,check,fail,spill,data,zero,reader=seq[:16]
    icmp,park,ihot,itoken,iinit,iready=seq[16:22]; cache=seq[22:39]; cache_slot=_slot(itoken,R.RCX,M.LEA)
    ptr,xor,keyarg,capacity,val,w0,w1,w2,w3,context,stackctx,stackval,dst,ctor,rsi,echo,rbx,sp,pop,ret=seq[39:59]
    slot=_slot(context,R.RAX,M.MOV)
    if (not slot or not _store(save,R.RSP,24,R.RBX) or push.mnemonic!=M.PUSH or push.op0_register!=R.RDI or not _sp(sub,M.SUB,48) or
            not _rr(self0,M.MOV,R.RBX,R.RDX) or not _rr(out,M.MOV,R.RDI,R.RCX) or not _metadata_guard(lift,cmp,hot,token,init,ready,check,slot) or
            check.mnemonic!=M.CMP or check.memory_base!=R.RBX or check.op1_kind!=K.IMMEDIATE8TO64 or check.immediate8to64!=0 or
            fail.mnemonic!=M.JE or fail.near_branch_target!=ret.next_ip or not _store(spill,R.RSP,72,R.RSI) or
            not _load(data,R.RBX,R.RBX,check.memory_displacement) or not _rr(zero,M.XOR,R.ECX,R.ECX) or not _rr(park,M.MOV,R.RSI,R.RAX) or
            not cache_slot or not _metadata_guard(lift,icmp,ihot,itoken,iinit,iready,cache[0],cache_slot) or not _cache_flow(lift,cache,cache_slot,True)):return None
    if (not _load(ptr,R.RDX,R.RBX,ptr.memory_displacement,M.LEA) or not _rr(xor,M.XORPS,R.XMM0,R.XMM0) or not _rr(keyarg,M.MOV,R.R9,R.RSI) or
            capacity.mnemonic!=M.MOV or capacity.op0_register!=R.R8D or capacity.op1_kind!=K.IMMEDIATE32 or not _load(val,R.RCX,R.RAX,0) or
            not all(_store(i,R.RDI,k*16,R.XMM0,M.MOVUPS) for k,i in enumerate((w0,w1,w2,w3))) or not _store(stackctx,R.RSP,40,R.RAX) or
            not _store(stackval,R.RSP,32,R.RCX) or not _rr(dst,M.MOV,R.RCX,R.RDI) or not _load(rsi,R.RSI,R.RSP,72) or
            not _rr(echo,M.MOV,R.RAX,R.RDI) or not _load(rbx,R.RBX,R.RSP,80) or not _sp(sp,M.ADD,48) or pop.mnemonic!=M.POP or pop.op0_register!=R.RDI or
            ret.mnemonic!=M.RET or ret.op_count):return None
    readers=_constructor(il,rt,slot,ctor)
    if not readers:return None
    key=_reader(il,method,reader,readers[0]);value=_inlined_reader(lift,cache_slot,readers[1])
    if not key or not value:return None
    # Native LEA displacement is in bytes, but Ptr is int*. Keep the pointer
    # evaluation before both readers even if the first reader replaces Ptr.
    disp=ptr.memory_displacement
    if not 0<=disp<1<<31 or disp%4:return None
    return _body(lift,method,td,rt,data,capacity,f'unchecked(this.Ptr + {disp//4})',key,value,seq[59:])


def _body(lift,method,td,rt,data,capacity,pointer,key,value,error):
    il=lift.il; field=(il.instance_field_chain(td.index) or {}).get(data.memory_displacement)
    if not field or field[0]!='Ptr' or il._closed_type_key(il.types[field[1]])!=(0x0f,(8,0),0): return None
    message=_error_message(lift,method,error)
    if message is None:return None
    count=int.from_bytes(capacity.immediate32.to_bytes(4,'little'),'little',signed=True)
    return ['unsafe','{','    if (this.Ptr == null)', '    {',f'        throw new System.InvalidOperationException({message});','    }',
            f'    return new {il.type_name(rt)}({pointer}, {count}, {key}, {value});','}']


def dictionary_constructor_body(lift,method,td,seq,eh):
    il=lift.il
    if (not HAVE_ICED or eh or len(seq) not in (25,55,76) or not isinstance(getattr(il,'bin',None),PE) or
            not il.bin.is64 or il.meta.version!=31 or not 0<=method.return_type<len(il.types)):
        return None
    if seq[0].ip!=method.addr or any(a.next_ip!=b.ip for a,b in zip(seq,seq[1:])) or not _plain(seq): return None
    if len(seq)==25:
        cache=_cache_contract(lift,method,td,seq)
        if cache:
            _,_,name,field=cache
            return [f'if ({field} is null)','{',f'    {field} = default({name});','}',f'return {field};']
        return None
    if method.is_static or method.param_count or not method.name.startswith('get_'): return None
    rt=il.types[method.return_type]
    if il._type_enum(rt)!=0x15 or not il.returns_sret(rt) or il._sf_field_size(rt,0)!=64: return None
    if len(seq)==76:return _inline_value_getter(lift,method,td,rt,seq)
    save,push,sub,cmp,self0,out,hot,token,init,ready,check,spill,fail=seq[:13]
    data,zero1,reader1,zero2,park,reader2,xor,keyarg,w0,capacity,ptr,w1,w2,w3,context,stackctx,dst,stackvalue,ctor,rbx,echo,rsi,sp,pop,ret=seq[13:38]
    if (not _store(save,R.RSP,16,R.RSI) or push.mnemonic!=M.PUSH or push.op0_register!=R.RDI or not _sp(sub,M.SUB,48) or
            cmp.mnemonic!=M.CMP or cmp.memory_base!=R.RIP or cmp.memory_size!=1 or cmp.op1_kind!=K.IMMEDIATE8 or cmp.immediate8 or
            not _rr(self0,M.MOV,R.RDI,R.RDX) or not _rr(out,M.MOV,R.RSI,R.RCX) or hot.mnemonic!=M.JNE or hot.near_branch_target!=check.ip or
            not _call(init) or init.near_branch_target!=lift.rt_init_meta or ready.mnemonic!=M.MOV or ready.memory_base!=R.RIP or
            ready.ip_rel_memory_address!=cmp.ip_rel_memory_address or ready.op1_kind!=K.IMMEDIATE8 or ready.immediate8!=1 or
            check.mnemonic!=M.CMP or check.memory_base!=R.RDI or check.op1_kind!=K.IMMEDIATE8TO64 or check.immediate8to64!=0 or
            not _store(spill,R.RSP,0x40,R.RBX) or fail.mnemonic!=M.JE or fail.near_branch_target!=ret.next_ip): return None
    if (not _load(data,R.RDI,R.RDI,check.memory_displacement) or not _rr(zero1,M.XOR,R.ECX,R.ECX) or not _rr(zero2,M.XOR,R.ECX,R.ECX) or
            not _rr(park,M.MOV,R.RBX,R.RAX) or not _rr(xor,M.XORPS,R.XMM0,R.XMM0) or not _rr(keyarg,M.MOV,R.R9,R.RBX) or
            capacity.mnemonic!=M.MOV or capacity.op0_register!=R.R8D or capacity.op1_kind!=K.IMMEDIATE32 or
            not _rr(ptr,M.MOV,R.RDX,R.RDI) or not all(_store(i,R.RSI,k*16,R.XMM0,M.MOVUPS) for k,i in enumerate((w0,w1,w2,w3))) or
            not _store(stackctx,R.RSP,40,R.RCX) or not _rr(dst,M.MOV,R.RCX,R.RSI) or not _store(stackvalue,R.RSP,32,R.RAX) or
            not _load(rbx,R.RBX,R.RSP,64) or not _rr(echo,M.MOV,R.RAX,R.RSI) or not _load(rsi,R.RSI,R.RSP,72) or
            not _sp(sp,M.ADD,48) or pop.mnemonic!=M.POP or pop.op0_register!=R.RDI or ret.mnemonic!=M.RET or ret.op_count): return None
    slot=_slot(context,R.RCX,M.MOV)
    if not slot or slot!=_slot(token,R.RCX,M.LEA): return None
    readers=_constructor(il,rt,slot,ctor)
    if not readers:return None
    factories=[_reader(il,method,i,t) for i,t in zip((reader1,reader2),readers)]
    if not all(factories):return None
    return _body(lift,method,td,rt,data,capacity,'this.Ptr',*factories,seq[38:])
