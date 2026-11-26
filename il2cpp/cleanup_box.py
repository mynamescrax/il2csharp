"""Recover the boxed logging argument and public singleton reads on a proved cleanup tail."""
import re

from il2cpp.expr import acc_get
from il2cpp.metadata import source_params
from il2cpp.names import safe_ident
from il2cpp.prelude import HAVE_ICED
from il2cpp.shared_action import _cleanup_tail_forward, _raises_on_null
from il2cpp.static_getter import alias_for_slot
from il2cpp.text import reg_name

if HAVE_ICED:
    from iced_x86 import Mnemonic as M, OpKind as K, Register as R


def _format_flag(il,blocks,b,box_ip,param):
    # In a single block the only thing between the box and Format is its
    # constant format string and normal argument setup. Move the boxing to
    # the C# argument, not an arbitrary consumer of the reused stack slot.
    pos=next((j for j,i in enumerate(b.insns) if i.ip==box_ip),None)
    if pos is None or pos<2 or len(b.insns)<pos+5: return
    string,zero,arg,call=b.insns[pos+1:pos+5]
    if (string.mnemonic!=M.MOV or string.op0_register!=R.RCX or string.memory_base!=R.RIP or
            (il.decode_slot(string.ip_rel_memory_address) or {}).get('kind')!=5 or
            zero.mnemonic!=M.XOR or zero.op0_register!=zero.op1_register or zero.op0_register!=R.R8D or
            arg.mnemonic!=M.MOV or arg.op0_register!=R.RDX or arg.op1_register!=R.RAX or
            call.mnemonic!=M.CALL or call.op0_kind!=K.NEAR_BRANCH64): return
    ids=il.addr_candidates.get(call.near_branch_target,())
    if len(ids)!=1 or ids[0][0]!='method' or not 0<=ids[0][1]<len(il.meta.methods): return
    fmt=il.meta.methods[ids[0][1]]; ps=il.meta.method_params(fmt)
    if (fmt.addr!=call.near_branch_target or not fmt.is_static or fmt.name!='Format' or il.typedef_full(fmt.declaring)!='System.String' or
            fmt.generic_container!=-1 or fmt.param_count!=len(ps) or len(ps)!=2 or not all(0<=p.type<len(il.types) for p in ps) or
            [il._closed_type_key(il.types[p.type]) for p in ps]!=[(0x0e,0),(0x1c,0)]): return
    literal=il.decode_slot(string.ip_rel_memory_address)['text']; slot='s_%x'%b.insns[pos-2].memory_displacement
    copy=f'{slot} = {param} & 0xFF/*z*/;'; use=f'string.Format({literal}, (object)({slot}))'
    token=re.compile(r'\b'+slot+r'\b')
    if sum(len(token.findall(s)) for bb in blocks for s in (*bb.stmts,bb.cond or '',bb.ret or ''))!=2: return
    for j,(a,c) in enumerate(zip(b.stmts,b.stmts[1:])):
        if a==copy and re.fullmatch(r'var t\d+ = '+re.escape(use)+r';',c):
            b.stmts[j:j+2]=[c.replace('(object)('+slot+')','(object)'+param)]
            return


def _public_snapshots(lift,blocks):
    for b in blocks:
        if len(b.insns) not in (5,6) or len(b.stmts)!=1: continue
        klass,blob,field=b.insns[:3]; dest=field.op0_register
        if (klass.mnemonic!=M.MOV or klass.memory_base!=R.RIP or klass.op0_register!=R.RAX or
                blob.mnemonic!=M.MOV or blob.op0_register!=R.RCX or blob.memory_base!=R.RAX or blob.memory_displacement!=0xb8 or
                field.mnemonic!=M.MOV or dest not in (R.RBX,R.RCX) or field.memory_base!=R.RCX or field.memory_displacement or
                any(i.memory_index!=R.NONE or i.has_segment_prefix for i in b.insns)): continue
        checked=len(b.insns)==5
        if checked:
            test,null=b.insns[3:]
            if (test.mnemonic!=M.TEST or test.op0_register!=dest or test.op1_register!=dest or null.mnemonic!=M.JE or
                    null.op0_kind!=K.NEAR_BRANCH64 or not _raises_on_null(lift,null)): continue
        else:
            k,cmp,skip=b.insns[3:]
            if (dest!=R.RBX or k.mnemonic!=M.MOV or k.op0_register!=R.RCX or k.memory_base!=R.RIP or
                    cmp.mnemonic!=M.CMP or cmp.memory_base!=R.RCX or cmp.memory_displacement!=0xe4 or skip.mnemonic!=M.JNE): continue
        prop=alias_for_slot(lift.il,klass.ip_rel_memory_address,lift.rt_init_meta); obj=(b.end_state or {}).get(reg_name(dest))
        if (not prop or not obj or obj._unk or lift.il._closed_type_key(obj.ty)!=lift.il._closed_type_key(prop[1]) or
                not re.fullmatch(r't\d+',obj.text) or not re.fullmatch(r'var '+obj.text+r' = [\w.<>]+;',b.stmts[0])): continue
        b.stmts[0]=f'var {obj.text} = {acc_get(prop[0])};'
        if checked: b.stmts.append(f'if ({obj.text} is null) {{ throw new System.NullReferenceException(); }}')


def fold_boxed_cleanup(lift,m,blocks,pads):
    if not HAVE_ICED or pads or m.param_count!=2 or m.is_static or m.slot==0xffff: return
    for b in blocks:
        if len(b.insns)!=10 or not b.stmts or not b.stmts[-1].startswith('base.'+m.name+'('): continue
        boxes=[]
        if not _cleanup_tail_forward(lift,b,b.insns[-1],boxes=boxes) or len(boxes)!=1: continue
        param=safe_ident(source_params(lift.meta,m)[1].name); addr,call=boxes[0]
        box=next((bb for bb in blocks if any(i.ip==addr for i in bb.insns)),None)
        if box: _format_flag(lift.il,blocks,box,call,param)
        _public_snapshots(lift,blocks)
