"""Park a checked reference-array element once per native iteration.

The truth conversion is a call. If it replaces the slot, the later
instance action still receives the previously loaded object. Do not move
the capture to the preheader or apply this to fields reloaded after it.
"""
from il2cpp.array_origin import _definitions,_graph,_reachable
from il2cpp.closed_lookup import _receiver
from il2cpp.csharp import source_field_name
from il2cpp.equivalent_binary import _amd64
from il2cpp.expr import Expr,acc_get
from il2cpp.metadata import source_params
from il2cpp.names import safe_ident
from il2cpp.prelude import HAVE_ICED
from il2cpp.saved_ref import reference_vector
from il2cpp.shared_field import whole_field_at
from il2cpp.text import reg_name,sdisp
from il2cpp.truth_operator import truth_owner

if HAVE_ICED:
    from iced_x86 import Mnemonic as M,OpKind as K,Register as R,RegisterExt as RX,MemorySizeExt as MS
    _SAVED={R.RBX,R.RSI,R.RDI,R.RBP,R.R12,R.R13,R.R14,R.R15}


def _unique(il,call):
    if not call.is_call_near:return None
    ids=il.addr_candidates.get(call.near_branch_target,())
    if len(ids)!=1 or ids[0][0]!='method' or not 0<=ids[0][1]<len(il.meta.methods):return None
    m=il.meta.methods[ids[0][1]]
    return m if m.addr==call.near_branch_target else None


def _null_pair(il,md):
    if (not md or md.name!='op_Inequality' or not md.is_static or not md.flags&0x800 or md.flags&7!=6 or
            not 0<=md.declaring<len(il.meta.typedefs) or md.generic_container!=-1 or md.param_count!=2 or
            not 0<=md.return_type<len(il.types) or il._closed_type_key(il.types[md.return_type])!=(2,0)):return False
    ps=il.meta.method_params(md)
    return len(ps)==2 and all(0<=p.type<len(il.types) and il._closed_type_key(il.types[p.type])==(0x12,md.declaring,0) for p in ps)


def checked_elements(lift,method,td,blocks,pads):
    il=lift.il;fields={};sites={};candidates=[]
    if not HAVE_ICED or pads or method.is_static or td.is_valuetype or method.generic_container!=-1 or td.generic_container!=-1:return fields,sites
    seq=[i for b in blocks for i in b.insns];by={i.ip:i for i in seq}
    for j in range(4,len(seq)-7):
        call=seq[j];test,branch,null,throw=seq[j+1:j+5]
        if (not call.is_call_near or test.mnemonic!=M.TEST or test.op0_register!=test.op1_register or test.op0_register!=R.AL or
                branch.mnemonic!=M.JE or null.mnemonic!=M.TEST or null.op0_register!=null.op1_register or null.op0_register not in _SAVED or throw.mnemonic!=M.JE):continue
        action=next((n for n in range(j+5,min(j+11,len(seq))) if seq[n].is_call_near),None)
        if action is None:continue
        truth=_unique(il,call);m=_unique(il,seq[action])
        if not m or m.is_static or m.flags&0x40 or m.generic_container!=-1 or not 0<=m.return_type<len(il.types):continue
        if _null_pair(il,truth) or truth_owner(il,truth) and il._closed_type_key(il.types[m.return_type])==(2,0):
            prop=lift._accessor_prop(m.index);last=seq[action]
            if (not prop or prop[0]!='get' or prop[2] or m.param_count or il._closed_type_key(il.types[m.return_type])!=(2,0) or
                    action+2>=len(seq) or seq[action+1].mnemonic!=M.TEST or seq[action+1].op0_register!=seq[action+1].op1_register or
                    seq[action+1].op0_register!=R.AL or seq[action+2].mnemonic!=M.JNE or seq[action+2].next_ip!=branch.near_branch_target):continue
        elif (seq[action].next_ip!=branch.near_branch_target or not truth_owner(il,truth) or m.flags&0x800 or
                il._closed_type_key(il.types[m.return_type])!=(1,0)):continue
        candidates.append((j,action,truth,m))
    if (not candidates or not _amd64(getattr(il,'bin',None)) or il.meta.version!=31 or
            any(n.startswith('t') and n[1:].isdigit() for n in (safe_ident(p.name) for p in source_params(il.meta,method)))):return fields,sites
    g=_graph(il,seq,chained=True,nested_chains=True,allow_tail=True,runtime_tails=lift.rt_wbarrier)
    if not g or seq[0].ip!=method.addr:return fields,sites
    pred,succ=g;ordinal={i.ip:n for n,i in enumerate(seq)}
    for j,k,truth,m in candidates:
        call,consumer=seq[j],seq[k];reg=seq[j+3].op0_register
        if _null_pair(il,truth):
            ok=True
            for reg,dword in ((R.RDX,R.EDX),(R.R8,R.R8D)):
                defs=_definitions(by,pred,method.addr,call.ip,reg)
                if len(defs)!=1:ok=False;break
                z=by[defs.pop()[0]]
                if z.mnemonic!=M.XOR or z.op0_register!=z.op1_register or z.op0_register!=dword:ok=False;break
            if not ok:continue
            reg=seq[j+3].op0_register
        w=seq[j:k+3] if il._closed_type_key(il.types[m.return_type])==(2,0) else seq[j:k+1]
        if any(a.next_ip!=b.ip or pred[b.ip]!=[a.ip] for a,b in zip(w,w[1:])):continue
        throw=by.get(seq[j+4].near_branch_target)
        if not throw or not throw.is_call_near or lift._named_raise_throw(throw.near_branch_target,lift._call_name(throw.near_branch_target))!='System.NullReferenceException':continue
        defs=_definitions(by,pred,method.addr,call.ip,R.RCX)
        if (len(defs)!=1 or defs!=_definitions(by,pred,method.addr,consumer.ip,R.RCX) or
                defs!=_definitions(by,pred,method.addr,seq[j+3].ip,reg)):continue
        ip,r=defs.pop();load=by[ip];base=load.memory_base;idx=load.memory_index
        if reg==R.RBP:
            from il2cpp.stack_local_frame import stack_local_frame
            if not stack_local_frame(lift,method,blocks,pads):continue
        if (load.mnemonic!=M.MOV or load.op0_register!=reg or r!=reg or load.op1_kind!=K.MEMORY or
                base not in _SAVED or base==reg or not RX.is_gpr64(idx) or load.memory_index_scale!=8 or load.memory_displacement!=32 or
                load.has_segment_prefix or load.has_lock_prefix or MS.size(load.memory_size)!=8):continue
        idxdefs=_definitions(by,pred,method.addr,ip,idx)
        if len(idxdefs)!=1:continue
        si,sr=idxdefs.pop();ext=by[si]
        if ext.mnemonic!=M.MOVSXD or ext.op0_register!=sr or not RX.is_gpr32(ext.op1_register):continue
        n=ordinal[ip];start=next((p for p in range(n-1,max(-1,n-9),-1) if seq[p].mnemonic==M.JAE),None)
        if start is None or not start:continue
        cmp,jae=seq[start-1:start+1];span=seq[start-1:n+1];fail=by.get(jae.near_branch_target)
        if (cmp.mnemonic!=M.CMP or cmp.op0_register!=ext.op1_register or cmp.op1_kind!=K.MEMORY or cmp.memory_base!=base or
                MS.size(cmp.memory_size)!=4 or cmp.memory_displacement!=24 or cmp.memory_index!=R.NONE or not fail or not fail.is_call_near or
                lift._named_raise_throw(fail.near_branch_target,lift._call_name(fail.near_branch_target))!='System.IndexOutOfRangeException' or
                sum(i.ip==si for i in span)!=1 or any(i.has_lock_prefix or i.has_segment_prefix for i in span) or
                any(a.next_ip!=b.ip or pred[b.ip]!=[a.ip] for a,b in zip(span,span[1:]))):continue
        # There may be a load/check of the class-init guard between the
        # bounds check and the read; it must not write the dword index.
        from il2cpp.array_origin import _INFO,_WRITES
        if any(any(u.access in _WRITES and RX.full_register(u.register)==RX.full_register(cmp.op0_register) for u in _INFO.info(i).used_registers()) for i in span[2:-1]):continue
        orig=_definitions(by,pred,method.addr,ip,base)
        if len(orig)!=1 or orig!=_definitions(by,pred,method.addr,cmp.ip,base):continue
        pos,ar=orig.pop();f=by[pos]
        if pos in _reachable(succ,succ[pos]):continue
        if (f.mnemonic!=M.MOV or f.op0_register!=ar or f.op1_kind!=K.MEMORY or f.memory_index!=R.NONE or f.has_segment_prefix or
                not _receiver(il,method,by,pred,pos,td.index,initial=f.memory_base,this_only=True)):continue
        row=whole_field_at(il,td.index,sdisp(f.memory_displacement),8)
        if not row or row[0]!=td.index or not reference_vector(il,row[2]):continue
        array=row[2];elem=il.type_from_ptr(array[0]);key=il._closed_type_key(elem)
        if not key or key[0]!=0x12 or key[-1] or m.declaring!=elem[0] or truth.declaring not in il.base_chain_tds(elem[0]):continue
        fields[pos]=('this.'+safe_ident(source_field_name(il,row[1])),array,'arr');sites[ip]=(pos,reg_name(base),reg_name(idx),array,elem)
    return fields,sites


def park_element(lift,i,plan,values):
    orig,br,ir,at,et=plan;arr=dict.get(lift.regs,br);idx=dict.get(lift.regs,ir)
    witness=values.get(orig)
    if (arr is None or witness is None or witness._unk or witness.kind!='arr' or lift.il._closed_type_key(witness.ty)!=lift.il._closed_type_key(at) or arr.kind!='arr' or lift.il._closed_type_key(arr.ty)!=lift.il._closed_type_key(at) or
            idx is None or idx._unk or not idx.text.isidentifier() or lift.il._closed_type_key(idx.ty)!=(8,0)):return False
    # This instruction is the per-iteration read, not a pre-loop capture.
    n=lift.new_var();lift._var_types[n]=lift._type_hints[n]=et;lift.emit(i.ip,f'var {n} = {acc_get(witness.text+"["+idx.text+"]")};',None)
    lift.set_reg(reg_name(i.op0_register),Expr(n,et,'obj'));return True
