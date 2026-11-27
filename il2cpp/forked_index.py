"""An indexer MethodRef can be prepared before the branch selecting its
two distinct call sites. Resolve each actual call on its own incoming edge."""
from il2cpp.array_origin import _definitions,_graph
from il2cpp.closed_class_read import _count_property,_class_entry
from il2cpp.closed_lookup import _receiver
from il2cpp.csharp import source_field_name
from il2cpp.equivalent_binary import _amd64
from il2cpp.indexed_class import _member
from il2cpp.names import safe_ident
from il2cpp.prelude import HAVE_ICED
from il2cpp.shared_field import reference_field_at,whole_field_at
from il2cpp.text import reg_name,sdisp

if HAVE_ICED:
    from iced_x86 import Mnemonic as M,OpKind as K,Register as R,RegisterExt as RX


def forked_indices(lift,method,blocks,pads,producers=None):
    il=lift.il;out={};forks=[]
    if (not HAVE_ICED or pads or method.is_static or not _amd64(getattr(il,'bin',None)) or il.meta.version!=31 or
            not 0<=method.declaring<len(il.meta.typedefs) or not 0<=method.return_type<len(il.types) or
            il._closed_type_key(il.types[method.return_type])!=(1,0)):return out
    for b in blocks:
        if not b.term or b.term[0]!='jcc' or len(b.succs)!=2 or min(b.succs)<0:continue
        arms=[blocks[i] for i in b.succs]
        if (all(z.preds==[b.bid] and z.insns and z.insns[0].is_call_near for z in arms) and
                arms[0].insns[0].near_branch_target==arms[1].insns[0].near_branch_target):forks.append((b,arms))
    if not forks:return out
    seq=[i for b in blocks for i in b.insns];g=_graph(il,seq,chained=True,allow_tail=True,runtime_tails=lift.rt_wbarrier)
    if not g or seq[0].ip!=method.addr:return out
    pred,_=g;by={i.ip:i for i in seq};entry=method.addr;key=il._closed_type_key
    def definition(site,r):
        defs=_definitions(by,pred,entry,site,r)
        if len(defs)==1:
            ip,reg=defs.pop();i=by[ip]
            if i.mnemonic==M.MOV and i.op0_register==reg and i.op1_kind==K.MEMORY and not i.has_segment_prefix and i.memory_index==R.NONE:return i
    def own(i):return _receiver(il,method,by,pred,i.ip,method.declaring,initial=i.memory_base,this_only=True)
    def i4load(i):
        if i.mnemonic!=M.MOV or i.op1_kind!=K.MEMORY or not RX.is_gpr32(i.op0_register) or not RX.is_gpr64(i.memory_base) or not own(i):return None
        f=whole_field_at(il,method.declaring,sdisp(i.memory_displacement),4)
        if f and f[0]==method.declaring and key(f[2])==(8,0):return 'this.'+safe_ident(source_field_name(il,f[1])),f[2]
    for b,arms in forks:
        s=b.insns;first,last=[z.insns[0] for z in arms];branch=s[-1]
        if branch.mnemonic not in (M.JL,M.JGE) or any(pred[i.ip]!=[branch.ip] for i in (first,last)):continue
        # No late masking: the setup and Count observation must all be in
        # the same linear block, with a single native incoming definition.
        if any(a.next_ip!=i.ip or pred[i.ip]!=[a.ip] for a,i in zip(s,s[1:])) or any(i.has_segment_prefix or i.has_lock_prefix or i.memory_index!=R.NONE for i in s):continue
        slot=definition(first.ip,R.R8);receiver=definition(first.ip,R.RCX)
        if (not slot or slot.memory_base!=R.RIP or not s[0].ip<=slot.ip<branch.ip or not receiver or not own(receiver)):continue
        u=il.decode_slot(slot.ip_rel_memory_address) or {};si=u.get('idx',-1);member=_member(lift,si,first) if u.get('kind')==6 else None
        if not member:continue
        td,ci,arg=member;row=reference_field_at(il,method.declaring,sdisp(receiver.memory_displacement),constructed=True)
        if not row or row[0]!=method.declaring or key(row[2])!=(0x15,(0x12,td.index,0),(key(arg),),0):continue
        ref='this.'+safe_ident(source_field_name(il,row[1])),row[2];actions={};
        if len(s)==6:
            old,inc,_,idx,cmp,_=s
            field=i4load(old);fld2=i4load(idx)
            if (not field or fld2!=field or not RX.is_gpr32(old.op0_register) or inc.mnemonic!=M.INC or inc.op0_register!=old.op0_register or
                    idx.op0_register!=R.EDX or old.op0_register in (R.EDX,R.ECX,R.R8D) or cmp.mnemonic!=M.CMP or cmp.op0_register!=old.op0_register or
                    cmp.op1_kind!=K.MEMORY or cmp.memory_base!=R.RCX or slot.ip!=s[2].ip):continue
            prop=_count_property(lift,td,ci,sdisp(cmp.memory_displacement))
            if not prop:continue
            actions[cmp.ip]=('fork_count_cmp',receiver.ip,prop,reg_name(cmp.op0_register));actions[idx.ip]=('field_value',field,'RDX','int')
            actions[old.ip]=('field_value',field,reg_name(old.op0_register),'int');actions[inc.ip]=('fork_inc',old.ip,reg_name(old.op0_register))
            for arm in arms:
                if len(arm.succs)!=1:continue
                use=blocks[arm.succs[0]];u=use.insns
                if len(u)<8 or u[-2].mnemonic!=M.TEST or u[-2].op0_register!=u[-2].op1_register or u[-2].op0_register!=R.RCX or u[-1].mnemonic!=M.JE:continue
                off=next((k for k,i in enumerate(u) if i.is_call_near),None)
                if off is None:continue
                w=u[off+1:-2]
                if len(w)==4:
                    n,ls,plus,put=w
                    if (i4load(n)!=field or n.op0_register!=R.EDX or plus.mnemonic!=M.INC or plus.op0_register!=R.EDX or
                            put.mnemonic!=M.MOV or put.op1_register!=R.EDX or sdisp(put.memory_displacement)!=sdisp(old.memory_displacement) or not own(put)):continue
                elif len(w)==2:
                    ls,put=w
                    if (put.mnemonic!=M.MOV or put.op0_kind!=K.MEMORY or put.op1_kind!=K.IMMEDIATE32 or put.immediate32 or
                            put.memory_displacement!=old.memory_displacement or not own(put)):continue
                else:continue
                if (ls.mnemonic!=M.MOV or ls.op0_register!=R.RCX or ls.op1_kind!=K.MEMORY or ls.memory_displacement!=receiver.memory_displacement or not own(ls) or
                        any(i.has_segment_prefix or i.has_lock_prefix or i.memory_index!=R.NONE for i in w) or
                        any(pred[z.ip]!=[a.ip] for a,z in zip(u[off:],u[off+1:]))):continue
                actions[ls.ip]=('field_value',ref,'RCX','obj')
                if len(w)==4:actions[n.ip]=('field_value',field,'RDX','int');actions[plus.ip]=('fork_inc',n.ip,'RDX')
        elif len(s)==8:
            save,cnt,dec,sl,cmp,restore,idx,_=s
            if (save.mnemonic!=M.MOV or save.op1_register!=R.RCX or save.op0_register!=R.RAX or
                    cnt.mnemonic!=M.MOV or cnt.memory_base!=R.RCX or cnt.op0_register!=R.ECX or dec.mnemonic!=M.DEC or dec.op0_register!=R.ECX or
                    sl.ip!=slot.ip or cmp.mnemonic!=M.CMP or cmp.op0_register not in (R.EBX,R.EBP,R.EDI,R.ESI,R.R12D,R.R13D,R.R14D,R.R15D) or cmp.op1_register!=R.ECX or
                    restore.mnemonic!=M.MOV or restore.op0_register!=R.RCX or restore.op1_register!=R.RAX or
                    idx.mnemonic!=M.MOV or idx.op0_register!=R.EDX or idx.op1_register!=cmp.op0_register):continue
            prop=_count_property(lift,td,ci,sdisp(cnt.memory_displacement))
            if not prop or producers is None:continue
            # The index itself came from a closed class call. Bind it before
            # the receiver field is reloaded: invoking a predicate can replace
            # the list. Its old receiver likewise predates delegate setup.
            earlier=by.get(next(iter(pred[receiver.ip]))) if len(pred[receiver.ip])==1 else None
            if not earlier or not earlier.is_call_near or earlier.next_ip!=receiver.ip:continue
            ctx=definition(earlier.ip,R.R8);source=definition(earlier.ip,R.RCX)
            if not ctx or ctx.memory_base!=R.RIP or not source or source.memory_displacement!=receiver.memory_displacement or not own(source):continue
            usage=il.decode_slot(ctx.ip_rel_memory_address) or {};spec=usage.get('idx',-1)
            if usage.get('kind')!=6 or not 0<=spec<len(il.method_specs):continue
            mi,cls,gi=il.method_specs[spec]
            if cls!=ci or gi!=-1 or not 0<=mi<len(il.meta.methods):continue
            result=il.meta.methods[mi]
            if (result.declaring!=td.index or result.param_count!=1 or result.is_static or result.generic_container!=-1 or
                    result.flags&0x40 and not result.flags&0x20 or not 0<=result.return_type<len(il.types) or key(il.types[result.return_type])!=(8,0) or
                    _class_entry(il,spec)!=earlier.near_branch_target):continue
            if pred[earlier.next_ip]!=[earlier.ip]:continue
            post=by.get(receiver.next_ip)
            if (not post or post.mnemonic!=M.MOV or post.op0_register!=cmp.op0_register or post.op1_register!=R.EAX or
                    _definitions(by,pred,entry,cmp.ip,RX.full_register(cmp.op0_register))!={(post.ip,RX.full_register(cmp.op0_register))}):continue
            actions[source.ip]=('field_value',ref,reg_name(source.op0_register),'obj');producers[earlier.ip]=mi
            actions[cnt.ip]=('count_value',receiver.ip,prop,'RCX','RCX')
            actions[dec.ip]=('fork_dec',cnt.ip,'RCX')
        else:continue
        actions[receiver.ip]=('field_value',ref,reg_name(receiver.op0_register),'obj')
        for i in (first,last):actions[i.ip]=('fork_index',receiver.ip,si,arg)
        out.update(actions)
    return out
