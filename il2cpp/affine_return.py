"""An integral affine return driven by one virtual double sample. Preserve
the pre-call integer snapshot, post-call reads and the scalar SSE rounding."""
from il2cpp.async_start import _frame,_rr
from il2cpp.equivalent_binary import _amd64,_extent,_writable
from il2cpp.inline_task import _kickoff_frame
from il2cpp.names import safe_ident
from il2cpp.prelude import HAVE_ICED
from il2cpp.readonly_sret import init_guards,plain
from il2cpp.shared_action import _init_arm
from il2cpp.sret_copy import _own_field
from il2cpp.static_getter import guarded_reference_property
from il2cpp.text import sdisp
from il2cpp.x64 import KLASS_INITIALIZED,KLASS_STATIC_FIELDS,KLASS_VTABLE

if HAVE_ICED:
    from iced_x86 import Mnemonic as M, OpKind as K, Register as R, RegisterExt


def _init(seq,slot):
    k,cmp,jump,call=seq
    return (k.mnemonic==M.MOV and k.op0_register==R.RCX and k.memory_base==R.RIP and k.ip_rel_memory_address==slot and
            cmp.mnemonic==M.CMP and cmp.memory_base==R.RCX and cmp.memory_displacement==KLASS_INITIALIZED and cmp.op1_kind==K.IMMEDIATE8TO32 and not cmp.immediate8to32 and
            jump.mnemonic==M.JNE and jump.op0_kind==K.NEAR_BRANCH64 and jump.near_branch_target==call.next_ip and call.mnemonic==M.CALL and call.op0_kind==K.NEAR_BRANCH64)


def affine_return(lift,m,td,seq,eh):
    if (not HAVE_ICED or eh or not td.is_valuetype or m.is_static or m.param_count or m.generic_container!=-1 or td.generic_container!=-1 or
            not 30<=len(seq)<=80 or not any(i.mnemonic==M.CVTSD2SS for i in seq)):return None
    il=lift.il;key=il._closed_type_key
    if il.meta.version!=31 or not _amd64(il.bin) or not 0<=m.return_type<len(il.types) or key(il.types[m.return_type])!=(8,0) or not plain(seq):return None
    extent=_extent(il,m.addr)
    if not extent or seq[0].ip!=m.addr or seq[-1].next_ip!=m.addr+extent[0]:return None
    p=next((j for j,i in enumerate(seq) if i.mnemonic==M.CMP),-1)
    if p<1 or seq[-2].mnemonic!=M.CALL or seq[-1].mnemonic!=M.INT3:return None
    unwind=il.bin.image_base+extent[1];header=il.bin.read(unwind,4) or b''
    if len(header)!=4 or not _kickoff_frame(seq[:p],il.bin.read(unwind,4+header[2]*2) or b'',plain=True):return None
    # One home save is restored early, after the final use of the unboxed this.
    tail=seq[-21:-2]
    if len(tail)!=19:return None
    klass,ptr,info,invoke,high,low,restore,inc,narrow,wi,wf,bi,bf,mul,add,trunc,adjust,pop,ret=tail
    frame=_frame(seq[:p],[restore,adjust,pop,ret]);g=init_guards(lift,seq,p,frame[1]) if frame else None
    if not g or len(g[2])!=1:return None
    j,park,slots=g;slot=next(iter(slots));pre=seq[j:-21]
    if len(pre)!=19:return None
    k,base,cmp,branch,ci,flag,hot,lea,init,ready,k2,cmp2,br2,ci2,t,b,ref,test,null=pre
    if (not _init((k,cmp,branch,ci),slot) or not _init((k2,cmp2,br2,ci2),slot) or
            il.bin.exports.get(ci.near_branch_target)!='il2cpp_runtime_class_init' or ci2.near_branch_target!=ci.near_branch_target or
            flag.mnemonic!=M.CMP or flag.memory_base!=R.RIP or flag.op1_kind!=K.IMMEDIATE8 or flag.immediate8 or hot.mnemonic!=M.JNE or
            hot.near_branch_target!=k2.ip or not _init_arm([lea,init,ready],lift.rt_init_meta,flag.ip_rel_memory_address) or lea.ip_rel_memory_address!=slot):return None
    sec=_writable(il.bin,flag.ip_rel_memory_address,1)
    if not sec or (flag.ip_rel_memory_address<sec.addr+sec.rawsize and il.bin.read(flag.ip_rel_memory_address,1)!=b'\0') or slot<=flag.ip_rel_memory_address<slot+8:return None
    r=base.op0_register
    if (base.mnemonic!=M.MOV or base.memory_base!=park or not RegisterExt.is_gpr32(r) or RegisterExt.full_register(r) not in frame[1]-{park} or
            t.mnemonic!=M.MOV or t.memory_base!=R.RIP or t.ip_rel_memory_address!=slot or t.op0_register!=R.RAX or
            b.mnemonic!=M.MOV or b.memory_base!=t.op0_register or b.memory_displacement!=KLASS_STATIC_FIELDS or b.op0_register!=R.RCX or
            ref.mnemonic!=M.MOV or ref.memory_base!=R.RCX or ref.op0_register!=R.RCX or not _rr(test,M.TEST,R.RCX,R.RCX) or null.mnemonic!=M.JE or
            null.near_branch_target!=seq[-2].ip or seq[-2].op0_kind!=K.NEAR_BRANCH64 or
            lift._named_raise_throw(seq[-2].near_branch_target,lift._call_name(seq[-2].near_branch_target))!='System.NullReferenceException'):return None
    alias=guarded_reference_property(lift,m,slot,sdisp(ref.memory_displacement))
    disp=sdisp(ptr.memory_displacement);n=(disp-KLASS_VTABLE)//16
    if (not alias or disp<KLASS_VTABLE or (disp-KLASS_VTABLE)%16 or klass.mnemonic!=M.MOV or klass.memory_base!=R.RCX or klass.memory_displacement or
            klass.op0_register!=R.RDX or ptr.mnemonic!=M.MOV or ptr.memory_base!=R.RDX or ptr.op0_register!=R.RAX or
            info.mnemonic!=M.MOV or info.op0_register!=R.RDX or info.memory_base!=R.RDX or info.memory_displacement!=disp+8 or
            invoke.mnemonic!=M.CALL or invoke.op0_register!=R.RAX):return None
    receiver=alias[2][0]
    if not 0<=receiver<len(il.meta.typedefs) or il.meta.typedefs[receiver].flags&0x20:return None
    mi=il.vtable_method(receiver,n)
    if mi is None or not 0<=mi<len(il.meta.methods):return None
    draw=il.meta.methods[mi]
    if (draw.slot!=n or draw.declaring!=alias[2][0] or draw.is_static or draw.param_count or draw.flags&7!=6 or not draw.flags&0x40 or
            draw.flags&0x800 or draw.generic_container!=-1 or not 0<=draw.return_type<len(il.types) or key(il.types[draw.return_type])!=(0x0d,0) or safe_ident(draw.name)!=draw.name):return None
    if (high.mnemonic!=M.MOV or high.op0_register!=R.EAX or high.memory_base!=park or low.mnemonic!=M.SUB or low.op0_register!=R.EAX or
            low.memory_base!=park or restore.op0_register!=park or inc.mnemonic!=M.INC or inc.op0_register!=R.EAX or
            not _rr(narrow,M.CVTSD2SS,R.XMM0,R.XMM0) or wi.mnemonic!=M.MOVD or wi.op1_register!=R.EAX or bi.mnemonic!=M.MOVD or bi.op1_register!=r or
            any(not R.XMM1<=i.op0_register<=R.XMM5 for i in (wi,bi)) or wi.op0_register==bi.op0_register or
            not _rr(wf,M.CVTDQ2PS,wi.op0_register,wi.op0_register) or not _rr(bf,M.CVTDQ2PS,bi.op0_register,bi.op0_register) or
            not _rr(mul,M.MULSS,wi.op0_register,R.XMM0) or not _rr(add,M.ADDSS,wi.op0_register,bi.op0_register) or
            not _rr(trunc,M.CVTTSS2SI,R.EAX,wi.op0_register)):return None
    fields=[_own_field(il,td,16+sdisp(i.memory_displacement),4) for i in (base,high,low)]
    if not all(f and key(f[1])==(8,0) and f[0][5:].isidentifier() and safe_ident(f[0][5:])==f[0][5:] for f in fields):return None
    before,upper,lower=(f[0] for f in fields);owner,member,_=alias
    return [f'int initial = {before};',f'global::System.Runtime.CompilerServices.RuntimeHelpers.RunClassConstructor(typeof(global::{owner}).TypeHandle);',
            f'double sample = global::{owner}.{member}.{draw.name}();',f'int span = unchecked({upper} - {lower} + 1);',
            'float product = (float)span * (float)sample;', 'float scaled = product + (float)initial;',
            'return scaled >= -2147483648f && scaled < 2147483648f ? (int)scaled : int.MinValue;']
