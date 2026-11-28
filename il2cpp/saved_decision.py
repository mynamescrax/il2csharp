"""Keep a Boolean decision across two effectful static property setters.

AND AL,[field] consumes the current field, not its entry parameter. The
native zero extension saves that result, whose complement and original
are passed respectively to a dword enum setter and a Boolean setter.
"""
from il2cpp.array_origin import _graph
from il2cpp.closed_lookup import _receiver
from il2cpp.equivalent_binary import _amd64
from il2cpp.expr import Expr, acc_get, _BOOL_TY
from il2cpp.metadata import source_params
from il2cpp.names import safe_ident
from il2cpp.prelude import HAVE_ICED
from il2cpp.sret_copy import _own_field
from il2cpp.terminal_effect import _terminal_frame
from il2cpp.text import reg_name,sdisp

if HAVE_ICED:
    from il2cpp.array_origin import _INFO,_WRITES,_SAVED
    from iced_x86 import Mnemonic as M, Register as R, RegisterExt as RX, OpKind as K, MemorySizeExt as MS


def _set_arg(lift,i):
    il=lift.il;ids=il.addr_candidates.get(i.near_branch_target,()) if i.is_call_near or i.is_jmp_short_or_near else ()
    if len(ids)!=1 or ids[0][0]!='method' or not 0<=ids[0][1]<len(il.meta.methods):return None
    m=il.meta.methods[ids[0][1]];p=lift._accessor_prop(m.index);ps=il.meta.method_params(m)
    if (m.addr==i.near_branch_target and m.is_static and m.generic_container==-1 and not m.flags&0x40 and m.flags&7==6 and
            p and p[0]=='set' and not p[2] and m.name=='set_'+p[1] and m.param_count==len(ps)==1 and
            0<=m.return_type<len(il.types) and il._closed_type_key(il.types[m.return_type])==(1,0) and 0<=ps[0].type<len(il.types)):
        return il.types[ps[0].type]


def decision_sites(lift,m,td,blocks,pads):
    actions={};sources=set();il=lift.il
    if (not HAVE_ICED or pads or m.is_static or m.param_count!=1 or td.is_valuetype or m.generic_container!=-1 or td.generic_container!=-1):return actions,sources
    windows=[]
    for b in blocks:
        s=b.insns
        if len(s)<10 or not s[-1].is_jmp_short_or_near:continue
        for j in range(1,len(s)-8):
            if s[j].mnemonic==M.AND and s[j].op0_register==R.AL and s[j].op1_kind==K.MEMORY and s[j-1].is_call_near and s[j+5].is_call_near:windows.append((b,j))
    if (not windows or not _amd64(getattr(il,'bin',None)) or il.meta.version!=31 or not 0<=m.return_type<len(il.types) or il._closed_type_key(il.types[m.return_type])!=(1,0)):return actions,sources
    ps=source_params(il.meta,m)
    if len(ps)!=1 or not 0<=ps[0].type<len(il.types) or il._closed_type_key(il.types[ps[0].type])!=(2,0):return actions,sources
    name=safe_ident(ps[0].name)
    if name.startswith('t') and name[1:].isdigit():return actions,sources
    seq=[i for b in blocks for i in b.insns];by={i.ip:i for i in seq};g=_graph(il,seq,allow_tail=True,chained=True)
    if not g or seq[0].ip!=m.addr:return actions,sources
    pred,_=g
    for b,j in windows:
        w=b.insns[j-1:];call,mask,save,mov,z,inv,put,z2,reload=w[:9];tail=w[-1];reg=RX.full_register(save.op0_register)
        if (any(i.has_segment_prefix or i.has_lock_prefix or i.memory_index!=R.NONE for i in w) or
                any(a.next_ip!=v.ip or pred[v.ip]!=[a.ip] for a,v in zip(w,w[1:])) or
                MS.size(mask.memory_size)!=1 or not RX.is_gpr64(mask.memory_base) or
                save.mnemonic!=M.MOVZX or not RX.is_gpr32(save.op0_register) or save.op1_register!=R.AL or reg not in _SAVED or
                mov.mnemonic!=M.MOV or mov.op0_register!=R.ECX or mov.op1_register!=save.op0_register or
                any(i.mnemonic!=M.XOR or i.op0_register!=i.op1_register or i.op0_register!=R.EDX for i in (z,z2)) or
                inv.mnemonic!=M.XOR or inv.op0_register!=R.ECX or inv.op1_kind not in (K.IMMEDIATE8TO32,K.IMMEDIATE32) or inv.immediate(1)!=1 or
                reload.mnemonic!=M.MOVZX or reload.op0_register!=R.ECX or not RX.is_gpr8(reload.op1_register) or
                reload.op1_register in (R.AH,R.CH,R.DH,R.BH) or RX.full_register(reload.op1_register)!=reg or
                not any(i.mnemonic==M.POP and i.op0_register==reg for i in w[9:-1]) or
                not _terminal_frame(il,seq,by,pred,mask.ip,b,j+7) or not _receiver(il,m,by,pred,mask.ip,td.index,initial=mask.memory_base,this_only=True)):continue
        off=sdisp(mask.memory_displacement);row=_own_field(il,td,off,1);enum=_set_arg(lift,put);flag=_set_arg(lift,tail)
        if not row or il._closed_type_key(row[1])!=(2,0) or not enum or il._closed_type_key(enum)!=(0x11,enum[0],0) or not 0<=enum[0]<len(il.meta.typedefs) or il._closed_type_key(flag)!=(2,0):continue
        owner=il.meta.typedefs[enum[0]];members=il.enum_members(owner.index)
        if (not owner.is_enum or owner.generic_container!=-1 or il.value_type_size(owner.index)!=4 or not members or
                any(v not in members or not members[v].isidentifier() or safe_ident(members[v])!=members[v] for v in (0,1))):continue
        # Prove the byte being combined was initialized by this exact value
        # parameter. It must still be loaded again *after* the comparison.
        for n,i in enumerate(seq[:20]):
            if (i.mnemonic==M.MOV and i.op0_kind==K.MEMORY and i.memory_base==R.RCX and i.memory_index==R.NONE and
                    sdisp(i.memory_displacement)==off and i.op1_register==R.DL and not i.has_segment_prefix and
                    all(pred[v.ip]==[u.ip] for u,v in zip(seq[:n],seq[1:n+1])) and
                    not any(v.is_call_near or any(a.access in _WRITES and RX.full_register(a.register) in (R.RCX,R.RDX) for a in _INFO.info(v).used_registers()) for v in seq[:n])):break
        else:continue
        init=i.ip; todo=[mask.ip];seen=set();covered=True
        while todo:
            p=todo.pop()
            if p==init or p in seen:continue
            if not pred[p] or len(seen)>512:covered=False;break
            seen.add(p);todo.extend(pred[p])
        if not covered:continue
        actions[mask.ip]=call.ip,row[0],reg_name(mask.memory_base),enum,'global::'+il.typedef_full(owner.index),members[0],members[1],save.ip,inv.ip,reload.ip,tuple([init]+[i.ip for i in w])
        sources.add(call.ip)
    return actions,sources


def apply_decision(lift,ip,plan,state,skip=()):
    call,field,base,ty,enum,a,b,save,inv,reload,required=plan
    if any(p in skip for p in required):return False
    x=lift._decision_results.get(call);receiver=dict.get(lift.regs,base)
    if (x is None or dict.get(lift.regs,'RAX') is not x or x._unk or lift.il._closed_type_key(x.ty)!=(2,0) or
            not receiver or receiver.text!='this' or receiver._unk or lift.il._closed_type_key(receiver.ty)!=(0x12,lift._current_td.index,0)):return False
    v=lift.new_var();lift._var_types[v]=lift._type_hints[v]=_BOOL_TY
    lift.emit(ip,f'var {v} = {acc_get("("+x.text+" & "+field+")")};',None);flag=Expr(v,_BOOL_TY,'int');lift.regs['RAX']=flag;lift.flags=None
    state[save]=('save',flag);state[inv]=('enum',flag,ty,f'({v} ? {enum}.{a} : {enum}.{b})');state[reload]=('boolean',flag)
    return True


def continue_decision(lift,ins,action):
    op,flag,*args=action;source=reg_name(ins.op1_register) if op!='enum' else 'RCX'
    if dict.get(lift.regs,source) is not flag:return False
    lift.set_reg(reg_name(ins.op0_register),Expr(args[1],args[0],'int') if op=='enum' else flag)
    if op=='enum':lift.flags=None
    return True
