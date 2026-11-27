"""Save a typed Boolean before its native inversion and branch on the copy."""
from il2cpp.array_origin import _graph,_definitions
from il2cpp.closed_lookup import _receiver
from il2cpp.csharp import FA_INITONLY,source_field_name
from il2cpp.equivalent_binary import _amd64
from il2cpp.expr import Expr,acc_get
from il2cpp.names import safe_ident
from il2cpp.prelude import HAVE_ICED
from il2cpp.shared_field import whole_field_at
from il2cpp.text import reg_name,sdisp

if HAVE_ICED:
    from iced_x86 import InstructionInfoFactory,MemorySizeExt,Mnemonic as M,OpAccess as A,OpKind as K,Register as R,RegisterExt as RX
    _INFO=InstructionInfoFactory()


def _dead(lift,by,succ,start,reg):
    todo=[start];seen=set()
    while todo:
        ip=todo.pop()
        if ip in seen:continue
        if len(seen)>=256:return False
        seen.add(ip);i=by[ip]
        hits=[u for u in _INFO.info(i).used_registers() if RX.full_register(u.register)==reg]
        if hits:
            if len(hits)==1 and hits[0].access==A.WRITE and RX.size(hits[0].register)>=4:continue
            return False
        if i.is_call_near:
            va=i.near_branch_target
            if lift._named_raise_throw(va,lift._call_name(va))=='System.NullReferenceException':continue
            ids=lift.il.addr_candidates.get(va,())
            if reg!=R.RAX or len(ids)!=1 or ids[0][0]!='method':return False
            m=lift.meta.methods[ids[0][1]]
            if m.addr!=va or not 0<=m.return_type<len(lift.il.types):return False
            rt=lift.il._closed_type_key(lift.il.types[m.return_type])
            # A registered managed call does not take RAX as an argument,
            # but a void callee may leave it intact. Follow those paths to
            # the next overwrite rather than treating volatility as a write.
            if rt and rt[0] in (8,9,10,11,14,0x12,0x1c,0x1d) and not rt[-1]:continue
            if rt!=(1,0):return False
        if not succ[ip] and i.mnemonic not in (M.INT3,M.UD2):return False
        todo.extend(succ[ip])
    return True


def _flags_dead(lift,by,succ,start,mask):
    todo=[(start,mask)];seen=set()
    while todo:
        ip,live=todo.pop()
        if not live or (ip,live) in seen:continue
        if len(seen)>=256:return False
        seen.add((ip,live));i=by[ip]
        if i.rflags_read & live:return False
        if i.is_call_near:
            va=i.near_branch_target
            if lift._named_raise_throw(va,lift._call_name(va))=='System.NullReferenceException':continue
            if not lift.il.addr_candidates.get(va):return False
        live &= ~i.rflags_modified
        if live and not succ[ip] and i.mnemonic not in (M.RET,M.INT3,M.UD2):return False
        todo.extend((q,live) for q in succ[ip])
    return True


def toggle_sites(lift,method,blocks,pads,dispatch):
    il=lift.il;out={};windows=[]
    if not HAVE_ICED or pads or method.is_static or not _amd64(getattr(il,'bin',None)) or il.meta.version!=31:return out
    for b in blocks:
        s=b.insns
        for j in range(len(s)-5):
            # At most one zero and one pointer load can intervene. Avoid
            # copying long suffixes on unrelated instructions.
            if len(s)-j>8 or s[j].mnemonic!=M.MOVZX:continue
            w=s[j:];load,test,inv,store=w[:4];r=load.op0_register;base=load.memory_base
            if (load.mnemonic!=M.MOVZX or load.op1_kind!=K.MEMORY or r not in (R.ECX,R.EDX) or not RX.is_gpr64(base) or
                    base in (R.RAX,R.RSP,RX.full_register(r)) or MemorySizeExt.size(load.memory_size)!=1 or
                    test.mnemonic!=M.TEST or test.op0_register!=test.op1_register or test.op0_register!={R.ECX:R.CL,R.EDX:R.DL}[r] or
                    inv.mnemonic!=M.SETE or inv.op0_register!=R.AL or store.mnemonic!=M.MOV or store.op0_kind!=K.MEMORY or
                    store.op1_register!=R.AL or store.memory_base!=base or store.memory_displacement!=load.memory_displacement or
                    any(i.has_lock_prefix or i.has_segment_prefix or i.memory_index!=R.NONE for i in w)):continue
            n=4
            if w[n].mnemonic==M.XOR and w[n].op0_register==w[n].op1_register==R.EDX and r!=R.EDX:n+=1
            if n>=len(w)-1 or w[n].mnemonic!=M.TEST or w[n].op0_register!=w[n].op1_register or w[n].op0_register!=test.op0_register:continue
            kill=n+1
            if kill<len(w)-1 and w[kill].mnemonic==M.MOV and w[kill].op0_register==RX.full_register(r) and w[kill].memory_base==R.RIP:kill+=1
            if kill==len(w)-1 and w[-1].mnemonic in (M.JE,M.JNE):windows.append((w,kill==n+2))
    if not windows:return out
    seq=[i for b in blocks for i in b.insns];g=_graph(il,seq,chained=True,allow_tail=True,runtime_tails=lift.rt_wbarrier)
    if not g or seq[0].ip!=method.addr:return out
    pred,succ=g;by={i.ip:i for i in seq}
    for w,overwritten in windows:
        load=w[0];base=load.memory_base;r=RX.full_register(load.op0_register);source=None;ti=method.declaring
        if any(a.next_ip!=b.ip or pred[b.ip]!=[a.ip] for a,b in zip(w,w[1:])):continue
        if not _receiver(il,method,by,pred,load.ip,ti,initial=base,this_only=True):
            defs=_definitions(by,pred,method.addr,load.ip,base)
            if len(defs)!=1:continue
            source,reg=defs.pop();plan=dispatch.get(source)
            if not plan or plan[2]!='obj' or by[source].op0_register!=reg:continue
            ti=plan[1][0]
        field=whole_field_at(il,ti,sdisp(load.memory_displacement),1)
        if (not field or field[0]!=ti or il._closed_type_key(field[2])!=(2,0) or field[2][1]&FA_INITONLY or
                any(not _dead(lift,by,succ,ip,reg) for ip in succ[w[-1].ip] for reg in ((R.RAX,) if overwritten else (R.RAX,r))) or
                any(not _flags_dead(lift,by,succ,ip,w[1].rflags_modified) for ip in succ[w[-1].ip])):continue
        name=safe_ident(source_field_name(il,field[1]));out[load.ip]=(source,ti,name,field[2])
    return out


def bind_toggle(lift,load,store,plan):
    source,ti,field,ty=plan;base=dict.get(lift.regs,reg_name(load.memory_base))
    if (not base or base._unk or lift.il._closed_type_key(base.ty)!=(0x12,ti,0) or
            (base.text!='this' if source is None else lift._lookup_field_values.get(source) is not base)):return False
    member=base.text+'.'+field;v=lift.new_var();lift._var_types[v]=lift._type_hints[v]=ty
    lift.emit(load.ip,f'var {v} = {acc_get(member)};',None);lift._kill_stale(member)
    lift.emit(store.ip,f'{member} = !{v};',None)
    lift.regs[reg_name(load.op0_register)]=Expr(v,ty,'int');lift.regs.pop('RAX',None);lift.flags=None
    return True
