"""Width-preserving 8+4 copies from a Win64 sret echo to an addressable field.

Never print a 12-byte struct as the RHS of an eight-byte move. Only use a
managed dword pair view when row order and emitted layout certify it.
"""
import re
from il2cpp.array_origin import _definitions,_graph
from il2cpp.closed_lookup import _receiver
from il2cpp.csharp import FA_INITONLY
from il2cpp.equivalent_binary import _amd64
from il2cpp.expr import acc_get, _R4_TY
from il2cpp.metadata import source_params
from il2cpp.names import safe_ident
from il2cpp.packed_call import _float_fields
from il2cpp.prelude import HAVE_ICED
from il2cpp.saved_binary import _frame_at
from il2cpp.shared_field import whole_field_at
from il2cpp.sret_copy import _own_field
from il2cpp.terminal_effect import _terminal_frame
from il2cpp.text import reg_name,sdisp

if HAVE_ICED:
    from iced_x86 import Mnemonic as M,OpKind as K,Register as R,RegisterExt as RX,MemorySizeExt as MS

_MM='global::System.Runtime.InteropServices.MemoryMarshal'


def read_piece(src,fields,width):
    if width==8:
        return f'{_MM}.Cast<float, long>({_MM}.CreateReadOnlySpan(ref {src}.{fields[0]}, 2))[0]'
    if width==4:return src+'.'+fields[2]
    raise ValueError('not a split vector piece')


def write_piece(dst,fields,width,src):
    if width==8:
        return f'{_MM}.Cast<float, long>({_MM}.CreateSpan(ref {dst}.{fields[0]}, 2))[0] = {src};'
    if width==4:return f'{dst}.{fields[2]} = {src};'
    raise ValueError('not a split vector piece')


def _load(i):
    if i.op1_kind!=K.MEMORY or i.memory_base!=R.RAX or i.memory_index!=R.NONE or i.has_segment_prefix:return None
    if (i.mnemonic==M.MOVSD and R.XMM0<=i.op0_register<=R.XMM5 and MS.size(i.memory_size)==8 and not i.memory_displacement):return 8
    if (i.mnemonic==M.MOV and i.op0_register in (R.ECX,R.EDX,R.R8D,R.R9D,R.R10D,R.R11D) and MS.size(i.memory_size)==4 and i.memory_displacement==8):return 4


def split_field_sites(lift,method,td,blocks,pads):
    out={};il=lift.il
    if (not HAVE_ICED or pads or method.is_static or td.is_valuetype or td.generic_container!=-1 or method.generic_container!=-1):return out
    windows=[]
    for b in blocks:
        s=b.insns
        if len(s)<7 or s[-1].mnemonic!=M.RET or s[-1].op_count or s[-1].stack_pointer_increment!=8:continue
        k=len(s)-2
        while k>=0 and s[k].mnemonic==M.POP:k-=1
        if k<5 or s[k].mnemonic!=M.ADD or s[k].op0_register!=R.RSP:continue
        call,a,b_,c,d=s[k-5:k];widths=(_load(a),_load(b_))
        if not call.is_call_near or set(widths)!={4,8}:continue
        parts={w:i for w,i in zip(widths,(a,b_))};stores={MS.size(i.memory_size):i for i in (c,d)}
        if (set(stores)!={4,8} or any(i.op0_kind!=K.MEMORY or i.op1_kind!=K.REGISTER or i.memory_index!=R.NONE or i.has_segment_prefix or
                i.has_lock_prefix or i.mnemonic!=parts[w].mnemonic or i.op1_register!=parts[w].op0_register for w,i in stores.items())):continue
        xy,z=stores[8],stores[4]
        if (not RX.is_gpr64(xy.memory_base) or xy.memory_base in (R.RSP,R.RBP) or xy.memory_base!=z.memory_base or
                sdisp(z.memory_displacement)!=sdisp(xy.memory_displacement)+8):continue
        windows.append((b,k-1,call,a,b_,c,d,xy,widths))
    if (not windows or not _amd64(getattr(il,'bin',None)) or il.meta.version!=31 or not 0<=method.return_type<len(il.types) or
            il._closed_type_key(il.types[method.return_type])!=(1,0) or
            any(n.startswith('t') and n[1:].isdigit() for n in (safe_ident(p.name) for p in source_params(il.meta,method)))):return out
    seq=[i for b in blocks for i in b.insns];by={i.ip:i for i in seq};g=_graph(il,seq)
    if not g or seq[0].ip!=method.addr:return out
    pred,_=g
    for block,end,call,a,b,c,d,xy,widths in windows:
        if any(u.next_ip!=v.ip or pred[v.ip]!=[u.ip] for u,v in zip((call,a,b,c),(a,b,c,d))):continue
        if not _terminal_frame(il,seq,by,pred,call.ip,block,end):continue
        ids=il.addr_candidates.get(call.near_branch_target,())
        if len(ids)!=1 or ids[0][0]!='method' or not 0<=ids[0][1]<len(il.meta.methods):continue
        producer=il.meta.methods[ids[0][1]]
        if (producer.addr!=call.near_branch_target or producer.generic_container!=-1 or not 0<=producer.return_type<len(il.types)):continue
        ty=il.types[producer.return_type];fields=_float_fields(il,ty)
        if not fields or len(fields)!=3 or not il.returns_sret(ty):continue
        off=sdisp(xy.memory_displacement);dst=_own_field(il,td,off,12);row=whole_field_at(il,td.index,off,12)
        if (not dst or not row or row[0]!=td.index or row[2][1]&FA_INITONLY or il._closed_type_key(dst[1])!=il._closed_type_key(ty) or
                not _receiver(il,method,by,pred,xy.ip,td.index,initial=xy.memory_base,this_only=True)):continue
        defs=_definitions(by,pred,method.addr,call.ip,R.RCX)
        if len(defs)!=1:continue
        ip,reg=defs.pop();home=by[ip]
        if home.mnemonic!=M.LEA or home.op0_register!=reg or home.memory_base!=R.RSP or home.memory_index!=R.NONE or home.has_segment_prefix:continue
        f=_frame_at(il,seq,by,pred,call.ip);disp=sdisp(home.memory_displacement)
        reserved=8*max(4,2+int(not producer.is_static)+producer.param_count)  # sret, receiver/parameters, MethodInfo
        if not f or not reserved<=disp<=f[0]-12 or any(lo<disp+12 and disp<lo+n for lo,n in f[2]):continue
        out[a.ip]=('first',call.ip,ty,fields,dst[0],reg_name(xy.memory_base),disp,f[1],widths)
        out[b.ip]=('second',a.ip)
        out[c.ip]=('store',a.ip,MS.size(c.memory_size));out[d.ip]=('store',a.ip,MS.size(d.memory_size))
    return out


def split_step(lift,ins,action,copies):
    op,*args=action
    if op=='first':
        call,ty,fields,dst,base,disp,depth,widths=args;echo=dict.get(lift.regs,'RAX');owner=dict.get(lift.regs,base)
        if (not owner or owner._unk or owner.text!='this' or not echo or getattr(lift,'_last_sret',None)!=(call,echo) or echo.ty!=ty or
                echo.kind!='ptr' or not re.fullmatch(r'&t\d+',echo.text) or lift.slot_types.get(echo.text[1:])!=ty or
                lift.rsp_delta!=-depth or getattr(echo,'_stack_offset',None)!=disp-depth):return False
        src=echo.text[1:];pieces={}
        for n,field in enumerate(fields):
            e=lift._stack_piece(disp-depth+n*4,4,_R4_TY)
            if not e or e.text!=src+'.'+field:return False
        copies[ins.ip]=(src,dst,fields,widths,pieces);width=widths[0]
    elif op=='second':
        record=copies.get(args[0]);
        if not record:return False
        src,dst,fields,widths,pieces=record;width=widths[1]
    else:
        first,width=args;record=copies.get(first)
        if not record or len(record[4])!=2:return False
        src,dst,fields,widths,pieces=record
        lift._kill_stale(dst);lift.emit(ins.ip,write_piece(dst,fields,width,pieces[width]),None);return True
    name=lift.new_var();ty=(0,0xa<<16) if width==8 else _R4_TY
    lift._var_types[name]=lift._type_hints[name]=ty
    read=read_piece(src,fields,width);lift.emit(ins.ip,f'var {name} = {acc_get(read)};',None);pieces[width]=name
    # Volatile scratch values have no observations after the two stores.
    lift.regs.pop(reg_name(ins.op0_register),None);return True
