"""Resolve a struct accessor on a bounds-checked, full-stride array element."""
import re

from il2cpp.binary import PE
from il2cpp.copied_getter import _copies_prefix, _prefix_getter
from il2cpp.metadata import source_params
from il2cpp.names import safe_ident
from il2cpp.prelude import HAVE_ICED
from il2cpp.sret_copy import _own_field
from il2cpp.text import reg_name, sdisp
from il2cpp.x64 import ARG_REGS

if HAVE_ICED:
    from iced_x86 import InstructionInfoFactory, Mnemonic as M, OpAccess, OpKind as K, Register as R, RegisterExt
    _INFO = InstructionInfoFactory()
    _WRITES = {OpAccess.WRITE,OpAccess.COND_WRITE,OpAccess.READ_WRITE,OpAccess.READ_COND_WRITE}
    _SAVED = (R.RBP,R.RBX,R.RSI,R.RDI,R.R12,R.R13,R.R14,R.R15)


def _entry_copy(blocks, bid, reg, arg):
    """All paths, including a loop back edge, must agree on the entry argument."""
    work=[(bid,reg)]; seen=set(); entry=False
    while work:
        bid,reg=work.pop()
        if (bid,reg) in seen:
            continue
        if not 0<=bid<len(blocks) or len(seen)>=128:
            return False
        seen.add((bid,reg)); b=blocks[bid]
        for i in reversed(b.insns):
            if i.mnemonic==M.CALL and reg not in _SAVED:
                return False
            if any(u.access in _WRITES and RegisterExt.full_register(u.register)==reg for u in _INFO.info(i).used_registers()):
                if i.mnemonic!=M.MOV or i.op0_register!=reg or not RegisterExt.is_gpr64(i.op1_register):
                    return False
                reg=i.op1_register
        if b.is_entry:
            if reg!=arg:
                return False
            entry=True
        elif not b.preds:
            return False
        work.extend((p,reg) for p in b.preds)
    return entry


def _setup(seq, base, index, stride, setter):
    """array + 0x20 + (long)index * sizeof(element). Account separately
    for the hidden arguments and, for the getter, the interleaved XY spill."""
    if len(seq)!=(6 if setter else 8) or any(a.next_ip!=b.ip for a,b in zip(seq,seq[1:])):
        return False
    if setter:
        extend,zero,mul,value,header,add=seq
        if value.mnemonic!=M.XORPS or value.op0_register!=value.op1_register or value.op0_register!=R.XMM1:
            return False
    else:
        load,out,extend,zero,mul,store,header,add=seq
        if (load.mnemonic!=M.MOVSD or load.op1_kind!=K.MEMORY or load.memory_base not in _SAVED or
                not RegisterExt.is_xmm(load.op0_register) or store.mnemonic!=M.MOVSD or store.op1_register!=load.op0_register or
                store.memory_base!=R.RSP or out.mnemonic!=M.LEA or out.op0_register!=R.RCX or out.memory_base!=R.RSP or
                any(i.has_segment_prefix or i.memory_index!=R.NONE for i in (load,store,out))):
            return False
        a,b=sdisp(store.memory_displacement),sdisp(out.memory_displacement)
        if min(a,b)<0x20 or not (a+8<=b or b+12<=a):
            return False
    dest=R.RCX if setter else R.RDX
    return (base in _SAVED and RegisterExt.is_gpr32(index) and RegisterExt.full_register(index) in _SAVED and
            RegisterExt.full_register(index)!=base and extend.mnemonic==M.MOVSXD and extend.op1_register==index and extend.op0_register==R.RAX and
            zero.mnemonic==M.XOR and zero.op0_register==zero.op1_register==R.R8D and
            mul.mnemonic==M.IMUL and mul.op0_register==dest and mul.op1_register==extend.op0_register and
            mul.op2_kind in (K.IMMEDIATE32TO64,K.IMMEDIATE8TO64) and mul.immediate(2)==stride and
            header.mnemonic==M.ADD and header.op0_register==dest and header.op1_kind in (K.IMMEDIATE32TO64,K.IMMEDIATE8TO64) and header.immediate(1)==0x20 and
            add.mnemonic==M.ADD and add.op0_register==dest and add.op1_register==base)


def _lifetime_alias(lift,target,owner):
    il=lift.il; code=il.bin.read(target,6) or b''
    if not il.bin.is_exec_va(target) or len(code)!=6 or code[:4]!=b'\xf3\x0f\x11\x49' or code[-1]!=0xc3:
        return None
    field=_own_field(il,owner,16+int.from_bytes(code[4:5],'little',signed=True),4)
    if not field or field[0]!='this.m_Lifetime' or il._closed_type_key(field[1])!=(0x0c,0):
        return None
    matches={}
    for kind,n in il.addr_candidates.get(target,()):
        if kind=='generic' and 0<=n<len(il.method_specs):
            n=il.method_specs[n][0]
        elif kind!='method':
            return None
        if not 0<=n<len(il.meta.methods):
            return None
        m=il.meta.methods[n]
        if m.declaring!=owner.index:
            continue
        prop=lift._accessor_prop(n); ps=il.meta.method_params(m)
        if (kind!='method' or m.addr!=target or m.is_static or m.flags&7!=6 or m.flags&0x40 or m.generic_container!=-1 or
                not prop or prop[0]!='set' or prop[2] or prop[1] in matches or m.param_count!=1 or len(ps)!=1 or
                not 0<=ps[0].type<len(il.types) or il._closed_type_key(il.types[ps[0].type])!=(0x0c,0) or
                not 0<=m.return_type<len(il.types) or il._closed_type_key(il.types[m.return_type])!=(1,0)):
            return None
        matches[prop[1]]=n
    # `lifetime` is a folded alias. Use the current public spelling.
    if set(matches)<={'lifetime','remainingLifetime'}:
        return matches.get('remainingLifetime')


def indexed_particle(lift, ins, regs):
    il=lift.il
    if (not HAVE_ICED or not isinstance(getattr(il,'bin',None),PE) or not il.bin.is64 or
            ins.op0_kind!=K.NEAR_BRANCH64 or len(regs)<3 or getattr(lift,'_ref_array_pads',())):
        return None
    b=getattr(getattr(lift,'out',None),'block',None)
    if not b or len(b.preds)!=1:
        return None
    target=ins.near_branch_target; setter=not _copies_prefix(il,target)
    j=6 if setter else 8
    if len(b.insns)<=j or b.insns[j].ip!=ins.ip or b.insns[j-1].next_ip!=ins.ip:
        return None
    pred=lift._blocks[b.preds[0]].insns
    if len(pred)<2:
        return None
    cmp,guard=pred[-2:]; base=cmp.memory_base; idx=cmp.op0_register
    if (cmp.mnemonic!=M.CMP or base not in _SAVED or cmp.op1_kind!=K.MEMORY or cmp.memory_displacement!=0x18 or
            cmp.memory_index!=R.NONE or cmp.has_segment_prefix or not RegisterExt.is_gpr32(idx) or
            guard.mnemonic!=M.JAE or guard.op0_kind!=K.NEAR_BRANCH64 or guard.near_branch_target==guard.next_ip or
            cmp.next_ip!=guard.ip or guard.next_ip!=b.insns[0].ip):
        return None
    fail=next((p.insns[0] for p in lift._blocks if p.insns and p.insns[0].ip==guard.near_branch_target),None)
    if (not fail or fail.mnemonic!=M.CALL or fail.op0_kind!=K.NEAR_BRANCH64 or
            lift._named_raise_throw(fail.near_branch_target,lift._call_name(fail.near_branch_target))!='System.IndexOutOfRangeException'):
        return None
    arr=dict.get(lift.regs,reg_name(base)); index=dict.get(lift.regs,reg_name(idx))
    if (not arr or arr._unk or arr.kind!='arr' or not arr.ty or il._type_enum(arr.ty)!=0x1d or arr.ty[1]&(1<<29) or
            not index or index._unk or il._closed_type_key(index.ty)!=(8,0) or not re.fullmatch(r'\w+',index.text) or
            not regs[2] or regs[2]._unk or regs[2].text!='0'):
        return None
    elem=il.type_from_ptr(arr.ty[0]); key=il._closed_type_key(elem)
    if not elem or key!=(0x11,elem[0],0) or not 0<=elem[0]<len(il.meta.typedefs) or il.typedef_full(elem[0])!='UnityEngine.ParticleSystem.Particle':
        return None
    owner=il.meta.typedefs[elem[0]]; stride=il.value_type_size(owner.index)
    if (not owner.is_valuetype or owner.generic_container!=-1 or not stride or stride<12 or
            not _setup(b.insns[:j],base,idx,stride,setter)):
        return None
    method=lift._current_method
    if not 0<=method.return_type<len(il.types):
        return None
    first=int(not method.is_static)+int(il.returns_sret(il.types[method.return_type]))
    incoming=[ARG_REGS[k] for k,p in enumerate(source_params(il.meta,method),first) if k<4 and safe_ident(p.name)==arr.text and
              0<=p.type<len(il.types) and il._closed_type_key(il.types[p.type])==il._closed_type_key(arr.ty)]
    if len(incoming)!=1 or not _entry_copy(lift._blocks,b.preds[0],base,getattr(R,incoming[0])):
        return None
    receiver=f'{arr.text}[{index.text}]'
    if setter:
        mi=_lifetime_alias(lift,target,owner)
        return (True,mi,receiver) if mi is not None else None
    buf=sdisp(b.insns[1].memory_displacement); output=regs[0]
    if (not output or output.kind!='ptr' or getattr(output,'_stack_offset',None)!=lift.rsp_delta+buf or
            buf+12>-lift.rsp_delta or sdisp(b.insns[5].memory_displacement)+8>-lift.rsp_delta):
        return None
    hit=_prefix_getter(lift,target,owner,receiver)
    # The interleaved MOVSD transported two floats, even if the display
    # expression for that load only named x. Restore the high lane of the
    # disjoint stack spill from the verified by-value vector parameter.
    load,store=b.insns[0],b.insns[5]
    xy=dict.get(lift.regs,reg_name(load.memory_base))
    if hit and xy and not xy._unk and load.memory_displacement==0 and il._closed_type_key(xy.ty)==il._closed_type_key(il.types[il.meta.methods[hit[0]].return_type]):
        params=[ARG_REGS[k] for k,p in enumerate(source_params(il.meta,method),first) if k<4 and safe_ident(p.name)==xy.text and
                0<=p.type<len(il.types) and il._closed_type_key(il.types[p.type])==il._closed_type_key(xy.ty)]
        if len(params)==1 and _entry_copy(lift._blocks,b.preds[0],load.memory_base,getattr(R,params[0])):
            lift._stack_store(lift.rsp_delta+sdisp(store.memory_displacement),8,lift._fragment(xy,0,8))
    return (False,*hit) if hit else None
