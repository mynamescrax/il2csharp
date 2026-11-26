"""Recover a nested iterator's inlined Int32 state constructor and capture."""
import re

from il2cpp.awaiter import _object_new_abi
from il2cpp.binary import PE
from il2cpp.prelude import HAVE_ICED
from il2cpp.shared_action import _plain_return
from il2cpp.sret_copy import _own_field

if HAVE_ICED:
    from iced_x86 import Decoder, Mnemonic as M, OpKind as K, Register as R


def _plain(seq):
    return not any(i.has_segment_prefix or i.has_lock_prefix or i.has_rep_prefix or
                   i.has_repne_prefix or i.memory_index!=R.NONE for i in seq)


def _rr(i,mn,dst,src): return i.mnemonic==mn and i.op0_register==dst and i.op1_register==src


def _sp(i,mn):
    return i.mnemonic==mn and i.op0_register==R.RSP and i.op1_kind==K.IMMEDIATE8TO64 and i.immediate8to64==0x20


def _state_ctor(il,td,state_off,base_call):
    chain=il.base_chain_tds(td.index)
    if len(chain)!=2 or il.typedef_full(chain[1])!='System.Object' or not _plain_return(il,base_call): return False
    def ctors(owner): return [il.meta.methods[j] for j in il.meta.type_methods(owner) if il.meta.methods[j].name=='.ctor']
    ct=ctors(td); parent=ctors(il.meta.typedefs[chain[1]])
    if len(ct)!=1 or len(parent)!=1: return False
    ctor,root=ct[0],parent[0]
    if (root.addr!=base_call or root.is_static or root.param_count or ('method',root.index) not in il.addr_candidates.get(base_call,()) or
            ctor.is_static or ctor.generic_container!=-1 or ctor.flags&7!=6 or ctor.param_count!=1 or
            not 0<=ctor.return_type<len(il.types) or il._closed_type_key(il.types[ctor.return_type])!=(1,0) or
            ('method',ctor.index) not in il.addr_candidates.get(ctor.addr,())): return False
    ps=il.meta.method_params(ctor)
    if len(ps)!=1 or not 0<=ps[0].type<len(il.types) or il._closed_type_key(il.types[ps[0].type])!=(8,0): return False
    start,end=il.function_extent(ctor.addr)
    if start!=ctor.addr or not 0<end-start<=64 or not il.bin.is_exec_va(start): return False
    seq=list(Decoder(64,il.bin.read(start,end-start) or b'',ip=start))
    if len(seq)!=12 or not _plain(seq): return False
    spill,push,sub,arg,this,zero,call,write,reload,add,pop,ret=seq
    # Preserve the int across the SAME base call and write it to the same
    # whole field; no other stores, calls or control flow on either path.
    return (spill.mnemonic==M.MOV and spill.memory_base==R.RSP and spill.memory_displacement==8 and spill.op1_register==R.RBX and
            push.mnemonic==M.PUSH and push.op0_register==R.RDI and _sp(sub,M.SUB) and _rr(arg,M.MOV,R.EDI,R.EDX) and
            _rr(this,M.MOV,R.RBX,R.RCX) and _rr(zero,M.XOR,R.EDX,R.EDX) and call.mnemonic==M.CALL and
            call.op0_kind==K.NEAR_BRANCH64 and call.near_branch_target==base_call and write.mnemonic==M.MOV and
            write.memory_base==R.RBX and write.memory_displacement==state_off and write.op1_register==R.EDI and
            reload.mnemonic==M.MOV and reload.op0_register==R.RBX and reload.memory_base==R.RSP and reload.memory_displacement==0x30 and
            _sp(add,M.ADD) and pop.mnemonic==M.POP and pop.op0_register==R.RDI and ret.mnemonic==M.RET and not ret.op_count)


def fold_iterator_creation(lift,owner,blocks,pads):
    il=lift.il
    if not HAVE_ICED or pads or not isinstance(getattr(il,'bin',None),PE) or not il.bin.is64 or il.meta.version!=31: return
    for b in blocks:
        if b.succs or len(b.stmts) not in (3,4) or len(b.insns)<11: continue
        m=re.fullmatch(r'var (t\d+) = new (.+)\(\);',b.stmts[0])
        if not m: continue
        tok,tn=m.groups(); factory=len(b.stmts)==3
        if (b.stmts[1:3]!=[f'{tok}.<>1__state = 0;',f'{tok}.<>4__this = this;'] or
                (factory and (b.term!=('ret',) or b.ret!=tok)) or (not factory and
                 (b.term!=('stop',) or b.stmts[3]!=f'this.StartCoroutine({tok}) /* shared implementation */; return;'))): continue
        seq=b.insns[:11]; klass,alloc,zero,arg,save,base,ref,state,value,capture,barrier=seq
        if any(x.next_ip!=z.ip for x,z in zip(seq,seq[1:])) or not _plain(seq): continue
        if (klass.mnemonic!=M.MOV or klass.op0_register!=R.RCX or klass.memory_base!=R.RIP or
                any(i.mnemonic!=M.CALL or i.op0_kind!=K.NEAR_BRANCH64 for i in (alloc,base,barrier)) or
                not _object_new_abi(lift,alloc.near_branch_target) or barrier.near_branch_target not in lift.rt_wbarrier or
                zero.mnemonic!=M.XOR or zero.op0_register!=zero.op1_register or zero.op0_register!=R.EDX or
                any(i.mnemonic!=M.MOV or i.op0_register!=reg or i.op1_register!=R.RAX for i,reg in ((arg,R.RCX),(save,R.RBX))) or
                ref.mnemonic!=M.LEA or ref.op0_register!=R.RCX or ref.memory_base!=R.RBX or
                state.mnemonic!=M.MOV or state.memory_base!=R.RBX or state.op1_kind!=K.IMMEDIATE32 or state.immediate32!=0 or
                value.mnemonic!=M.MOV or value.op0_register!=R.RDX or value.op1_register!=R.RDI or capture.mnemonic!=M.MOV or
                capture.memory_base!=R.RBX or capture.op1_register!=R.RDI or ref.memory_displacement!=capture.memory_displacement): continue
        usage=il.decode_slot(klass.ip_rel_memory_address) or {}; n=usage.get('td',-1)
        if (usage.get('kind')!=1 or not 0<=n<len(il.meta.typedefs) or il._closed_type_key(usage.get('type'))!=(0x12,n,0) or
                il._nested_owner(n)!=owner.index or il.type_name(usage['type'])!=tn): continue
        td=il.meta.typedefs[n]
        if (td.is_valuetype or not td.flags&0x100 or td.generic_container!=-1 or not re.fullmatch(r'<[^<>]+>d__\d+',td.name)): continue
        st=_own_field(il,td,state.memory_displacement,4); parent=_own_field(il,td,capture.memory_displacement,8)
        if (not st or st[0]!='this.<>1__state' or il._closed_type_key(st[1])!=(8,0) or
                not parent or parent[0]!='this.<>4__this' or il._closed_type_key(parent[1])!=(0x12,owner.index,0) or
                parent[1][1]&0x27!=6 or not _state_ctor(il,td,state.memory_displacement,base.near_branch_target)): continue
        expr=f'new {tn}(0) {{ <>4__this = this }}'
        if factory:
            b.stmts.clear(); b.ret=expr
        else:
            b.stmts[:]=[f'this.StartCoroutine({expr}) /* shared implementation */; return;']
