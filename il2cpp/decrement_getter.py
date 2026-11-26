"""Equivalent public accessors for the Win64 unboxed int32 load/decrement leaf."""
import re

from il2cpp.binary import PE
from il2cpp.csharp import FA_LITERAL, FA_STATIC, field_attrs, source_field_name
from il2cpp.expr import acc_get
from il2cpp.metadata import source_params
from il2cpp.names import safe_ident
from il2cpp.prelude import HAVE_ICED
from il2cpp.sret_copy import _own_field
from il2cpp.text import reg_name

if HAVE_ICED:
    from iced_x86 import Mnemonic as M, OpKind as K, Register as R, MemorySizeExt


def _member(lift, addr, owner):
    il=lift.il; ids=il.addr_candidates.get(addr,())
    if (len(ids)<2 or not isinstance(getattr(il,'bin',None),PE) or not il.bin.is64 or not il.bin.is_exec_va(addr) or
            il.bin.read(addr,5)!=bytes.fromhex('8b01 ffc8 c3') or not 0<=owner<len(il.meta.typedefs)): return None
    td=il.meta.typedefs[owner]
    if not td.is_valuetype or td.generic_container!=-1 or td.flags&7!=1 or il.value_type_size(owner)!=4: return None
    # Explicit layout is OK only with one nonstatic field covering all four bytes.
    offsets=il.field_offsets[owner] if owner<len(il.field_offsets) else None
    if not offsets or len(offsets)!=td.field_count: return None
    fs=[(fi,pos) for fi,pos in zip(il.meta.type_fields(td),offsets) if not field_attrs(il,il.meta.fields[fi])&(FA_LITERAL|FA_STATIC)]
    if len(fs)!=1 or fs[0][1]!=16: return None
    fi=fs[0][0]; f=il.meta.fields[fi]
    if not 0<=f.type<len(il.types) or il._closed_type_key(il.types[f.type])!=(8,0): return None
    props=[]
    for kind,mi in ids:
        if kind!='method' or not 0<=mi<len(il.meta.methods): return None
        m=il.meta.methods[mi]
        if m.declaring!=owner: continue
        prop=lift._accessor_prop(mi)
        if (m.addr!=addr or m.is_static or m.param_count or m.generic_container!=-1 or m.flags&0x40 or m.flags&7!=6 or
                not prop or prop[0]!='get' or prop[2]!=0 or not 0<=m.return_type<len(il.types) or
                il._closed_type_key(il.types[m.return_type])!=(8,0)): return None
        props.append((prop[1],mi))
    if props: return min(props)[0],safe_ident(source_field_name(il,fi)),{mi for _,mi in props}


def decrement_body(lift,m):
    if not m.name.startswith('get_'): return None
    member=_member(lift,m.addr,m.declaring)
    if member and m.index in member[2]: return 'unchecked(this.%s - 1)'%member[1]


def _parameter_home(lift,ins,lea,name,offset):
    """Check an unescaped register-parameter home in the method prefix.

    Never turn a borrowed reused stack address, an unmodelled RBP frame,
    or a merged local's type hint into a chosen value-type MethodDef.
    """
    m=lift._current_method; il=lift.il
    if (offset not in (8,16,24,32) or il.eh_regions(m.addr) or not 0<=m.return_type<len(il.types) or
            not il._return_abi_is_known(il.types[m.return_type])): return None
    slot=offset//8-1; idx=slot-int(not m.is_static)-int(il.returns_sret(il.types[m.return_type]))
    ps=source_params(il.meta,m)
    if not 0<=idx<len(ps) or not 0<=ps[idx].type<len(il.types): return None
    pt=il.types[ps[idx].type]; value=lift.stack_values.get(name)
    if (not value or value._unk or value.text!=safe_ident(ps[idx].name) or not pt or
            il._closed_type_key(pt)!=(0x11,pt[0],0) or il._closed_type_key(value.ty)!=il._closed_type_key(pt) or
            il._closed_type_key(lift.slot_types.get(name))!=il._closed_type_key(pt)): return None
    blocks=lift._blocks
    # A later branch back into the prefix invalidates a pristine-home proof.
    if any(i.mnemonic==M.JMP and i.op0_kind!=K.NEAR_BRANCH64 or
           m.addr<=i.near_branch_target<=ins.ip<i.ip for b in blocks for i in b.insns): return None
    sequence=sorted((i for b in blocks for i in b.insns if m.addr<=i.ip<ins.ip),key=lambda i:i.ip)
    if not sequence or len(sequence)>192 or sequence[0].ip!=m.addr or sequence[-1].next_ip!=ins.ip or any(
            a.next_ip!=b.ip for a,b in zip(sequence,sequence[1:])): return None
    sp=0; saved=False; frame=False
    for step,i in enumerate(sequence):
        if i.has_segment_prefix or i.memory_index!=R.NONE: return None
        if i.mnemonic==M.PUSH and not frame and i.op0_kind==K.REGISTER:
            sp-=8; continue
        if i.mnemonic==M.SUB and i.op0_register==R.RSP and not frame and i.op1_kind in (K.IMMEDIATE8TO64,K.IMMEDIATE32TO64):
            size=i.immediate(1)
            if not 0x20<=size<=0x1000: return None
            sp-=size; frame=True; continue
        if i.mnemonic==M.MOV and i.op0_kind==K.MEMORY and i.memory_base==R.RSP:
            pos=sp+i.memory_displacement; size=MemorySizeExt.size(i.memory_size)
            if pos<offset+4 and pos+size>offset:
                if (frame or sp or saved or pos!=offset or size!=4 or
                        i.op1_register!=(R.ECX,R.EDX,R.R8D,R.R9D)[slot]): return None
                saved=True
            continue
        if not frame or not saved: return None
        if i.mnemonic==M.LEA and i.memory_base==R.RSP:
            if i.op0_register!=R.RCX: return None
            if i.ip!=lea.ip:
                following=sequence[step+1:step+2]
                if not following or following[0].mnemonic!=M.CALL or following[0].near_branch_target!=ins.near_branch_target: return None
            continue
        if i.mnemonic==M.CALL:
            # Metadata helpers take their metadata/class pointer, never the
            # caller's local address. Another invocation of this exact leaf
            # only reads four bytes. No opaque call may alias the home.
            if i.op0_kind!=K.NEAR_BRANCH64 or (i.near_branch_target!=ins.near_branch_target and lift._call_name(i.near_branch_target) not in (
                    'il2cpp_codegen_initialize_runtime_metadata','il2cpp_runtime_class_init')): return None
            continue
        if i.mnemonic==M.JNE and i.op0_kind==K.NEAR_BRANCH64 and i.ip<i.near_branch_target<=ins.ip: continue
        if i.mnemonic in (M.MOV,M.LEA) and i.is_ip_rel_memory_operand and i.op0_register==R.RCX: continue
        if i.mnemonic==M.MOV and i.is_ip_rel_memory_operand and i.op0_kind==K.MEMORY and i.op1_kind==K.IMMEDIATE8: continue
        if i.mnemonic==M.CMP and (i.is_ip_rel_memory_operand or i.memory_base==R.RCX): continue
        if i.mnemonic==M.MOV and i.op1_register==R.RCX and i.op0_register in (R.RBX,R.RSI,R.RDI): continue
        if i.mnemonic==M.XOR and i.op0_register==i.op1_register==R.EDX: continue
        return None
    if frame and saved and sp==lift.rsp_delta and sp+lea.memory_displacement==offset: return pt


def decrement_read(lift,ins,regs):
    if len(regs)<2: return None
    p,ctx=regs[:2]; il=lift.il
    if (not p or p.kind!='ptr' or p._unk or not p.text.startswith('&') or not ctx or ctx._unk or ctx.text!='0' or
            not isinstance(getattr(il,'bin',None),PE) or not il.bin.is64 or il.bin.read(ins.near_branch_target,5)!=b'\x8b\x01\xff\xc8\xc3'):
        return None
    b=lift.out.block; j=next((j for j,i in enumerate(b.insns) if i.ip==ins.ip),-1)
    clear=lea=None
    for i in reversed(b.insns[max(0,j-6):j]):
        if i.mnemonic==M.LEA and i.op0_register==R.RCX and not lea: lea=i
        elif i.mnemonic==M.XOR and i.op0_register==i.op1_register==R.EDX and not clear: clear=i
        elif not (i.mnemonic==M.MOV and i.op0_kind==K.MEMORY and i.memory_base==R.RSP and
                  i.memory_index==R.NONE and not i.has_segment_prefix and i.op1_kind==K.REGISTER): break
        if clear and lea: break
    if not clear or not lea or lea.has_segment_prefix or lea.memory_index!=R.NONE: return None
    name=p.text[1:]; ty=None
    if lea.memory_base==R.RSP and re.fullmatch(r's_[0-9a-f]+',name):
        ty=_parameter_home(lift,ins,lea,name,getattr(p,'_stack_offset',None))
    elif lea.memory_base in (R.RDI,R.RBX,R.RSI,R.R12,R.R13,R.R14,R.R15):
        base=dict.get(lift.regs,reg_name(lea.memory_base)); td=lift._current_td
        if not base or base._unk or base.text!='this' or not base.ty or base.ty[0]!=td.index: return None
        row=_own_field(il,td,lea.memory_displacement+(16 if td.is_valuetype else 0),4)
        if row and row[0]==name and il._closed_type_key(row[1])==il._closed_type_key(p.ty): ty=row[1]
    if not ty or il._closed_type_key(ty)!=(0x11,ty[0],0): return None
    member=_member(lift,ins.near_branch_target,ty[0])
    if member: return acc_get(name+'.'+member[0])+' /* shared getter */'
