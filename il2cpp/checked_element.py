"""Snapshot of element zero of a checked SZARRAY. Track native byte ranges
and the two getter receivers; the fields and consuming methods come from
registration and metadata rather than the name of the element type."""
from dataclasses import dataclass
import re

from il2cpp.captured_home import _normal_predecessors
from il2cpp.copied_getter import _field_getter
from il2cpp.expr import Expr
from il2cpp.field_slice import field_offset
from il2cpp.indexed_binary import _echo_copy,echo_at,store_value
from il2cpp.prelude import HAVE_ICED
from il2cpp.text import reg_name,sdisp

if HAVE_ICED:
    from iced_x86 import MemorySizeExt, Mnemonic as M, OpKind as K, Register as R, RegisterExt
    _SAVED={R.RBX,R.RBP,R.RSI,R.RDI,R.R12,R.R13,R.R14,R.R15}


def _rr(i,m,r,s):return i.mnemonic==m and i.op0_register==r and i.op1_register==s


def _home(i):
    if i.memory_base==R.RSP and i.memory_index==R.NONE and not i.has_segment_prefix:return sdisp(i.memory_displacement)


def _lea(i,r):return _home(i) if i.mnemonic==M.LEA and i.op0_register==r else None


def _tiles(seq,size):
    """Require every payload byte exactly once at its natural offset. Return
    the two homes plus the loads/stores used to reassemble the whole value."""
    pieces={};moves=[];stores=[];dest=out=None;hidden=False
    for i in seq:
        if i.memory_index!=R.NONE or i.has_lock_prefix or i.has_rep_prefix or i.has_repne_prefix or i.has_segment_prefix:return None
        if not hidden and _rr(i,M.XOR,R.R8D,R.R8D):hidden=True;continue
        if dest is None and _lea(i,R.RDX) is not None:dest=_home(i);continue
        if out is None and _lea(i,R.RCX) is not None:out=_home(i);continue
        if i.mnemonic not in (M.MOVUPS,M.MOVDQU,M.MOVSD,M.MOVSS):return None
        w=MemorySizeExt.size(i.memory_size)
        if i.op1_kind==K.MEMORY and i.memory_base==R.RAX and R.XMM0<=i.op0_register<=R.XMM5:
            rel=sdisp(i.memory_displacement)-32
            if not 0<=rel<=size-w or i.op0_register in pieces:return None
            pieces[i.op0_register]=(rel,w);moves.append((i.ip,reg_name(i.op0_register),rel,w))
        elif i.op0_kind==K.MEMORY and _home(i) is not None and i.op1_register in pieces:
            rel,n=pieces.pop(i.op1_register)
            if n!=w:return None
            stores.append((rel,w,_home(i),i.ip))
        else:return None
    if not hidden or pieces or out is None or dest is None or not moves or moves[0][0]!=seq[0].ip:return None
    end=0
    for rel,w,at,_ in sorted(stores):
        if rel!=end or at!=dest+rel:return None
        end+=w
    if end==size:return dest,out,moves,[ip for _,_,_,ip in stores]


def _method(il,i):
    if i.mnemonic!=M.CALL or i.op0_kind!=K.NEAR_BRANCH64:return None
    ids=il.addr_candidates.get(i.near_branch_target,())
    if len(ids)==1 and ids[0][0]=='method' and 0<=ids[0][1]<len(il.meta.methods):
        m=il.meta.methods[ids[0][1]]
        if m.addr==i.near_branch_target and m.generic_container<0 and 0<=m.return_type<len(il.types):return m


def _raiser(lift,byip,jump,exc):
    i=byip.get(jump.near_branch_target)
    if i and i.mnemonic==M.CALL and i.op0_kind==K.NEAR_BRANCH64:
        t=i.near_branch_target;return lift._named_raise_throw(t,lift._call_name(t))==exc
    return False


def _disjoint(a,n,b,w):return a+n<=b or b+w<=a


@dataclass
class Plan:
    array:tuple
    elem:tuple
    size:int
    receiver:int
    loads:dict
    stores:tuple
    getters:dict
    point_save:int
    normal_save:int
    rotation_save:int
    normal_store:int
    normal_arg:int
    rotate:int
    point_stores:tuple
    point_arg:int
    rotation_store:int
    rotation_arg:int
    sink:int
    result_ty:tuple


def _site(lift,md,b,blocks,stack,byip,pred):
    s=b.insns;bid=b.bid;il=lift.il;extent,depth,saves=stack
    calls=[k for k,i in enumerate(s) if i.mnemonic==M.CALL]
    if len(calls)!=4 or bid<2:return None
    g,h,t,u=calls
    if not (g>=5 and h==g+6 and t==h+8 and u==t+9):return None
    if any(i.has_segment_prefix or i.has_lock_prefix or i.has_rep_prefix or i.has_repne_prefix or i.memory_index!=R.NONE for i in s[:u+1]):return None
    guard=blocks[bid-1].insns;prev=blocks[bid-2].insns
    if len(guard)!=2 or len(prev)<5:return None
    zero,recv,producer,test,null=prev[-5:];length,bounds=guard
    win=prev[-5:]+guard+s[:u+1]
    if any(a.next_ip!=z.ip or pred[z.ip]!={a.ip} for a,z in zip(win,win[1:])):return None
    if (not _rr(zero,M.XOR,R.EDX,R.EDX) or recv.mnemonic!=M.MOV or recv.op0_register!=R.RCX or recv.op1_register not in _SAVED or
            not _rr(test,M.TEST,R.RAX,R.RAX) or null.mnemonic!=M.JE or not _raiser(lift,byip,null,'System.NullReferenceException') or
            length.mnemonic!=M.CMP or length.memory_base!=R.RAX or length.memory_displacement!=24 or length.op0_kind!=K.MEMORY or
            length.op1_kind!=K.IMMEDIATE8TO32 or length.immediate8to32!=0 or length.memory_index!=R.NONE or length.has_segment_prefix or
            bounds.mnemonic!=M.JBE or not _raiser(lift,byip,bounds,'System.IndexOutOfRangeException')):return None
    m=_method(il,producer)
    if not m or m.is_static or m.param_count or m.flags&0x40:return None
    prop=lift._accessor_prop(m.index);array=il.types[m.return_type]
    if not prop or prop[0]!='get' or prop[2] or il._type_enum(array)!=0x1d:return None
    elem=il.type_from_ptr(array[0]);key=il._closed_type_key
    if not elem or key(elem)!=(0x11,elem[0],0) or not 0<=elem[0]<len(il.meta.typedefs) or key(array)!=(0x1d,key(elem),0):return None
    owner=il.meta.typedefs[elem[0]];size=il.value_type_size(owner.index)
    if not owner.is_valuetype or owner.generic_container>=0 or not size:return None
    copy=_tiles(s[:g],size)
    if not copy:return None
    home,first,moves,stores=copy
    if (not _rr(s[g+1],M.XOR,R.R8D,R.R8D) or _lea(s[g+2],R.RDX)!=home or _lea(s[g+3],R.RCX) is None):return None
    second=_home(s[g+3]);xy,z=s[h-2:h]
    if (xy.mnemonic!=M.MOVSD or xy.memory_base!=R.RAX or xy.memory_displacement or not R.XMM6<=xy.op0_register<=R.XMM15 or
            z.mnemonic!=M.MOV or z.memory_base!=R.RAX or z.memory_displacement!=8 or not RegisterExt.is_gpr32(z.op0_register) or
            RegisterExt.full_register(z.op0_register) not in _SAVED-{R.RBP}):return None
    reads={};vkey=None
    for i,out in ((s[g],first),(s[h],second)):
        if i.op0_kind!=K.NEAR_BRANCH64:return None
        target=i.near_branch_target;off=field_offset(il,target)
        hit=None if off is None else _field_getter(lift,target,owner,'v',off)
        if not hit:return None
        mi=hit[0];k=key(il.types[il.meta.methods[mi].return_type]);reads[i.ip]=(mi,lift._accessor_prop(mi)[1],out)
        if vkey is not None and vkey!=k:return None
        vkey=k
    homes=_echo_copy(s[h+1:t+1],(None,extent),into_second=True);transform=_method(il,s[t]);sink=_method(il,s[u])
    if (not homes or not transform or not transform.is_static or transform.param_count!=1 or not sink or sink.is_static or sink.flags&0x40 or sink.param_count!=2 or
            key(il.types[sink.return_type])!=(1,0)):return None
    def params(m):return [key(il.types[p.type]) if 0<=p.type<len(il.types) else None for p in il.meta.method_params(m)]
    result=il.types[transform.return_type]
    if (not result or key(result)!=(0x11,result[0],0) or not il.returns_sret(result) or il._sf_field_size(result,0)!=16 or
            params(transform)!=[vkey] or params(sink)!=[vkey,key(result)]):return None
    a,n=homes
    hidden,store,r8,tail,r2,r1,load,wide=s[t+1:u];p=_home(store);q=_lea(r8,R.R8)
    if (not _rr(hidden,M.XOR,R.R9D,R.R9D) or p is None or q is None or store.mnemonic!=M.MOVSD or store.op1_register!=xy.op0_register or
            tail.mnemonic!=M.MOV or tail.op1_register!=z.op0_register or _home(tail)!=p+8 or _lea(r2,R.RDX)!=p or
            r1.mnemonic!=M.MOV or r1.op0_register!=R.RCX or r1.op1_register not in _SAVED or r1.op1_register==RegisterExt.full_register(z.op0_register) or
            load.mnemonic!=M.MOVUPS or load.memory_base!=R.RAX or load.memory_displacement or not R.XMM0<=load.op0_register<=R.XMM5 or
            wide.mnemonic not in (M.MOVUPS,M.MOVAPS) or wide.op1_register!=load.op0_register or _home(wide)!=q or wide.mnemonic==M.MOVAPS and q%16):return None
    ranges=((home,size),(first,12),(second,12),(a,16),(n,12),(p,12),(q,16))
    if any(not 32<=x<=extent-w or any(not _disjoint(x,w,y,l) for y,l in saves) for x,w in ranges):return None
    # Lifetimes, not global slot types: normal may overwrite point after its
    # two lanes are saved; the new transform may reuse the old normal home.
    if (not _disjoint(home,size,first,12) or not _disjoint(home,size,second,12) or not _disjoint(n,12,a,16) or
            not _disjoint(n,12,second,12) or not _disjoint(p,12,a,16) or not _disjoint(p,12,q,16)):return None
    return Plan(array,elem,size,home,{ip:(r,off,w) for ip,r,off,w in moves},tuple(stores),reads,
                s[g+1].ip,s[h+1].ip,s[t+1].ip,s[t-2].ip,n,s[t].ip,(store.ip,tail.ip),p,wide.ip,q,s[u].ip,result)


def element_sites(lift,method,blocks,pads):
    if not HAVE_ICED or pads:return {}
    candidates=[b for b in blocks if len(b.insns)>=29 and b.insns[0].mnemonic in (M.MOVUPS,M.MOVDQU) and b.insns[0].memory_base==R.RAX and b.insns[0].memory_displacement==32]
    if not candidates:return {}
    from il2cpp.stack_local_frame import stack_local_frame
    frame=stack_local_frame(lift,method,blocks,pads)
    if not frame:return {}
    seq=[i for b in blocks for i in b.insns];pred=_normal_predecessors(seq);byip={i.ip:i for i in seq}
    if not pred:return {}
    return {b.bid:(p,frame[1]) for b in candidates if (p:=_site(lift,method,b,blocks,frame,byip,pred))}


def element_step(lift,site,state,i):
    """Replace only proved value copies. Leave native calls, saved-register
    loads, and unrelated memory effects to ordinary instruction lifting."""
    plan,depth=site;ip=i.ip
    if not state and ip==next(iter(plan.loads)):
        arr=dict.get(lift.regs,'RAX')
        if (not arr or arr._unk or not re.fullmatch(r'[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*',arr.text or '') or
                (arr.ty is None and not lift.dry) or arr.ty and lift.il._closed_type_key(arr.ty)!=lift.il._closed_type_key(plan.array) or
                -lift.rsp_delta!=depth):return False
        arr=lift.regs['RAX']  # count this use only after accepting the rewrite
        name=lift.new_var();lift._var_types[name]=plan.elem
        lift.emit(ip,f'var {name} = {arr.text}[0];',None);state['element']=Expr(name,plan.elem,'obj')
    if not state:return False
    elem=state['element']
    if ip in plan.loads:
        reg,off,w=plan.loads[ip];lift.regs[reg]=lift._fragment(elem,off,w);return True
    if ip in plan.stores:
        if ip==plan.stores[-1]:store_value(lift,ip,plan.receiver,elem,plan.size)
        return True
    if ip in plan.getters:
        mi,prop,out=plan.getters[ip]
        if all(getattr(dict.get(lift.regs,r),'_stack_offset',None)==lift.rsp_delta+off for r,off in (('RCX',out),('RDX',plan.receiver))):
            lift._checked_element_getters[ip]=(mi,elem.text+'.'+prop)
    if ip in (plan.point_save,plan.normal_save):
        index=0 if ip==plan.point_save else 1
        state[('point','normal')[index]]=echo_at(lift,list(plan.getters)[index])
    if ip==plan.rotation_save:
        e=dict.get(lift.regs,'RAX')
        if e and getattr(lift,'_last_sret',None)==(plan.rotate,e) and e.ty==plan.result_ty and re.fullmatch(r'&t\d+',e.text):state['rotation']=Expr(e.text[1:],e.ty,'obj')
    def arg(reg,value,off):
        a=Expr('&'+value.text,value.ty,'ptr');a._stack_offset=lift.rsp_delta+off;lift.regs[reg]=a
    normal=state.get('normal');point=state.get('point');rotation=state.get('rotation')
    if normal and ip==plan.normal_store:
        store_value(lift,ip,plan.normal_arg,normal);state['skip']=i.next_ip;return True
    if ip==state.get('skip'):return True
    if normal and ip==plan.rotate:arg('RDX',normal,plan.normal_arg)
    if point and ip in plan.point_stores:
        if ip==plan.point_stores[1]:store_value(lift,ip,plan.point_arg,point)
        return True
    if rotation and ip==plan.rotation_store:
        store_value(lift,ip,plan.rotation_arg,rotation,16);return True
    if ip==plan.sink:
        if point:arg('RDX',point,plan.point_arg)
        if rotation:arg('R8',rotation,plan.rotation_arg)
    return False
