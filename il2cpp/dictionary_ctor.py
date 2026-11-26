"""Closed dictionary constructor into a Win64 getter's hidden result buffer."""
import json

from il2cpp.awaiter import _object_new_abi, _spec_entry
from il2cpp.binary import PE
from il2cpp.codegen_ident import codegen_names
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


def dictionary_constructor_body(lift,method,td,seq,eh):
    il=lift.il
    if (not HAVE_ICED or eh or len(seq)!=55 or method.is_static or method.param_count or not method.name.startswith('get_') or
            not isinstance(getattr(il,'bin',None),PE) or not il.bin.is64 or il.meta.version!=31 or not 0<=method.return_type<len(il.types)):
        return None
    if (seq[0].ip!=method.addr or any(a.next_ip!=b.ip for a,b in zip(seq,seq[1:])) or
            any(i.has_segment_prefix or i.has_lock_prefix or i.has_rep_prefix or i.has_repne_prefix or i.memory_index!=R.NONE for i in seq)): return None
    rt=il.types[method.return_type]
    if il._type_enum(rt)!=0x15 or not il.returns_sret(rt) or il._sf_field_size(rt,0)!=64: return None
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
    field=(il.instance_field_chain(td.index) or {}).get(data.memory_displacement)
    if not field or field[0]!='Ptr' or il._closed_type_key(il.types[field[1]])!=(0x0f,(8,0),0): return None
    message=_error_message(lift,method,seq[38:])
    if message is None:return None
    count=int.from_bytes(capacity.immediate32.to_bytes(4,'little'),'little',signed=True)
    return ['unsafe','{','    if (this.Ptr == null)', '    {',f'        throw new System.InvalidOperationException({message});','    }',
            f'    return new {il.type_name(rt)}(this.Ptr, {count}, {factories[0]}, {factories[1]});','}']
