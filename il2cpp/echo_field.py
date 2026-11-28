"""A complete returned float4, copied directly into a same-type instance field.

Recover only the destination store. Do not give a packed register a whole
struct display value: a later partial MOVSD must still write eight bytes.
"""
import re
from il2cpp.array_origin import _definitions,_graph
from il2cpp.closed_lookup import _receiver
from il2cpp.csharp import FA_INITONLY
from il2cpp.equivalent_binary import _amd64
from il2cpp.metadata import source_params
from il2cpp.names import safe_ident
from il2cpp.prelude import HAVE_ICED
from il2cpp.saved_binary import _frame_at
from il2cpp.shared_field import whole_field_at
from il2cpp.simd_getter import _float4,_packed_return
from il2cpp.sret_copy import _own_field
from il2cpp.text import reg_name,sdisp

if HAVE_ICED:
    from iced_x86 import Mnemonic as M,OpKind as K,Register as R,MemorySizeExt as MS,RegisterExt as RX


def echo_stores(lift,method,td,blocks,pads):
    plans={}; il=lift.il
    if not HAVE_ICED or pads or method.is_static or td.is_valuetype or td.generic_container!=-1:
        return plans
    windows=[]
    for b in blocks:
        for j,load in enumerate(b.insns[1:-1],1):
            if load.mnemonic!=M.MOVUPS or not _packed_return(load) or not b.insns[j-1].is_call_near:
                continue
            st=b.insns[j+1]
            if (st.mnemonic==M.MOVUPS and st.op0_kind==K.MEMORY and st.op1_register==load.op0_register and
                    RX.is_gpr64(st.memory_base) and st.memory_base not in (R.RSP,R.RBP) and
                    st.memory_index==R.NONE and not st.has_segment_prefix and not st.has_lock_prefix and MS.size(st.memory_size)==16):
                windows.append((b.insns[j-1],load,st))
    if (not windows or not _amd64(getattr(il,'bin',None)) or il.meta.version!=31 or method.generic_container!=-1 or
            any(n.startswith('t') and n[1:].isdigit() for n in (safe_ident(p.name) for p in source_params(il.meta,method)))):
        return plans
    seq=[i for b in blocks for i in b.insns];by={i.ip:i for i in seq};g=_graph(il,seq,chained=True,nested_chains=True,allow_tail=True,runtime_tails=lift.rt_wbarrier)
    if not g or seq[0].ip!=method.addr:return plans
    pred,_=g
    for call,load,st in windows:
        ty=_float4(lift,call)
        if (not ty or call.next_ip!=load.ip or load.next_ip!=st.ip or pred[load.ip]!=[call.ip] or pred[st.ip]!=[load.ip] or
                not _receiver(il,method,by,pred,st.ip,td.index,initial=st.memory_base,this_only=True)):
            continue
        off=sdisp(st.memory_displacement);dst=_own_field(il,td,off,16);row=whole_field_at(il,td.index,off,16)
        if (not dst or not row or row[0]!=td.index or row[2][1]&FA_INITONLY or il._closed_type_key(dst[1])!=il._closed_type_key(ty)):
            continue
        defs=_definitions(by,pred,method.addr,call.ip,R.RCX)
        if len(defs)!=1:continue
        ip,r=defs.pop();home=by[ip]
        if (home.mnemonic!=M.LEA or home.op0_register!=r or home.memory_base!=R.RSP or
                home.memory_index!=R.NONE or home.has_segment_prefix):continue
        frame=_frame_at(il,seq,by,pred,call.ip);disp=sdisp(home.memory_displacement)
        if (not frame or not 32<=disp<=frame[0]-16 or
                any(lo<disp+16 and disp<lo+n for lo,n in frame[2])):continue
        plans[st.ip]=(call.ip,load,ty,dst[0],disp,frame[1])
    return plans


def emit_copy(lift,ins,plan):
    call,load,ty,dest,disp,depth=plan
    echo=dict.get(lift.regs,'RAX');base=dict.get(lift.regs,reg_name(ins.memory_base))
    if (not base or base.text!='this' or base._unk or not echo or getattr(lift,'_last_sret',None)!=(call,echo) or
            echo.kind!='ptr' or echo.ty!=ty or not re.fullmatch(r'&t\d+',echo.text) or lift.slot_types.get(echo.text[1:])!=ty or
            lift.rsp_delta!=-depth or getattr(echo,'_stack_offset',None)!=disp-depth):return False
    text=echo.text[1:];f=lift._aggregate_load(load);parts=getattr(f,'_parts',None)
    layout=lift.il.instance_field_chain(ty[0]);expected=[(n,text+'.'+layout[16+n][0],0,4) for n in (0,4,8,12)]
    if not parts or [(lo,v.text,off,w) for lo,v,off,w in parts]!=expected:return False
    lift._kill_stale(dest);lift.emit(ins.ip,f'{dest} = {text};',None);return True
