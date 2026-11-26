"""A direct Win64 forwarding call with privately copied by-value arguments.
Track incoming parameter identities and outgoing bytes, not their C# text.
No user code runs between a copy and the single target call."""
from il2cpp.async_start import _adjust
from il2cpp.equivalent_binary import _amd64,_extent
from il2cpp.names import safe_ident
from il2cpp.prelude import HAVE_ICED
from il2cpp.text import sdisp

if HAVE_ICED:
    from iced_x86 import MemorySizeExt, Mnemonic as M, OpKind as K, Register as R, RegisterExt
    _ARG=(R.RCX,R.RDX,R.R8,R.R9)
    _TMP={*_ARG,R.RAX,R.R10,R.R11}


def byval_forward(lift,m,td,s,eh):
    if (not HAVE_ICED or eh or m.is_static or m.param_count<1 or m.param_count>5 or not 7<=len(s)<=48 or
            s[-3].mnemonic!=M.CALL or s[-3].op0_kind!=K.NEAR_BRANCH64 or s[-1].mnemonic!=M.RET or s[-1].op_count):return None
    il=lift.il;key=il._closed_type_key;size=_adjust(s[0],M.SUB)
    if (not size or not 32<=size<=128 or size%16!=8 or _adjust(s[-2],M.ADD)!=size or not _amd64(il.bin) or il.meta.version!=31 or
            td.is_valuetype or td.generic_container!=-1 or m.generic_container!=-1 or not 0<=m.return_type<len(il.types) or key(il.types[m.return_type])!=(1,0) or
            any(i.memory_index!=R.NONE or i.has_segment_prefix or i.has_lock_prefix for i in s) or any(a.next_ip!=b.ip for a,b in zip(s,s[1:]))):return None
    extent=_extent(il,m.addr)
    if not extent or m.addr!=s[0].ip or s[-1].next_ip!=m.addr+extent[0]:return None
    # Exactly one UWOP_ALLOC_SMALL, nothing else to preserve on a throw.
    if il.bin.read(il.bin.image_base+extent[1],6)!=bytes((1,s[0].len,1,0,s[0].len,((size//8-1)<<4)|2)):return None
    target=s[-3].near_branch_target;ids=il.addr_candidates.get(target,())
    if len(ids)!=1 or ids[0][0]!='method' or not 0<=ids[0][1]<len(il.meta.methods):return None
    sink=il.meta.methods[ids[0][1]]
    if (sink.index==m.index or sink.addr!=target or sink.is_static or sink.declaring!=td.index or sink.flags&(0x40|0x800) or
            sink.generic_container!=-1 or sink.param_count!=m.param_count or safe_ident(sink.name)!=sink.name or not sink.name.isidentifier() or
            not 0<=sink.return_type<len(il.types) or key(il.types[sink.return_type])!=(1,0)):return None
    ps=il.meta.method_params(m);qs=il.meta.method_params(sink)
    if (len(ps)!=m.param_count or len(qs)!=len(ps) or any(not 0<=p.type<len(il.types) for p in (*ps,*qs)) or
            [key(il.types[p.type]) for p in ps]!=[key(il.types[p.type]) for p in qs]):return None
    names=['this']+[safe_ident(p.name) for p in ps];regs={R.RCX:('param',0)};incoming={};aggregate={};homes={};writes={}
    if len(set(names))!=len(names) or any(not n.isidentifier() for n in names):return None
    for n,p in enumerate(ps,1):
        ty=il.types[p.type];k=key(ty)
        if not k:return None
        if k[0]==0x11:
            if k!=(0x11,ty[0],0) or not 0<=ty[0]<len(il.meta.typedefs) or il.meta.typedefs[ty[0]].generic_container!=-1:return None
            width=il.value_type_size(ty[0])
            if width not in (12,16):return None
            aggregate[n]=width
        elif k not in ((2,0),(8,0),(9,0),(14,0),(28,0)) and k!=(0x12,ty[0],0):return None
        if n<4:regs[_ARG[n]]=('param',n)
        else:incoming[size+8+8*n]=('param',n)
    if not aggregate:return None
    hidden=len(ps)+1;start=max(32,8*(hidden+1)) if hidden>=4 else 32
    for i in s[1:-3]:
        dst,src=i.op0_register,i.op1_register;off=sdisp(i.memory_displacement);width=MemorySizeExt.size(i.memory_size);base=i.memory_base
        if i.op0_kind==K.MEMORY:
            if base!=R.RSP or off<32 or off+width>size or not width or any(p in writes for p in range(off,off+width)):return None
            if i.mnemonic==M.MOV and i.op1_kind==K.IMMEDIATE32TO64 and i.immediate32to64==0:v=('zero',)
            else:v=regs.get(RegisterExt.full_register(src),None)
            if not v:return None
            if v[0]=='bytes':
                if off<start or (i.mnemonic,width) not in ((M.MOV,4),(M.MOVSD,8),(M.MOVAPS,16),(M.MOVUPS,16)) or width!=v[3]:return None
                if i.mnemonic==M.MOVAPS and off%16:return None
                for k in range(width):writes[off+k]=(v[1],v[2]+k)
            elif width==8 and i.mnemonic==M.MOV and off%8==0 and v[0] in ('home','zero','param'):
                homes[off]=v
                for k in range(8):writes[off+k]=None
            else:return None
            continue
        if i.op0_kind!=K.REGISTER:return None
        r=RegisterExt.full_register(dst)
        if r not in _TMP and not R.XMM0<=dst<=R.XMM5:return None
        if i.mnemonic==M.LEA and RegisterExt.is_gpr64(dst) and base==R.RSP and start<=off<size:regs[r]=('home',off)
        elif i.mnemonic==M.XOR and dst==src and (RegisterExt.is_gpr32(dst) or RegisterExt.is_gpr64(dst)):regs[r]=('zero',)
        elif i.mnemonic==M.MOV and RegisterExt.is_gpr64(dst) and base==R.RSP and off in incoming:regs[r]=incoming[off]
        elif i.op1_kind==K.MEMORY and (i.mnemonic,width) in ((M.MOV,4),(M.MOVSD,8),(M.MOVUPS,16)):
            p=regs.get(base);n=p[1] if p and p[0]=='param' else None
            if n not in aggregate or off<0 or off+width>aggregate[n]:return None
            regs[r]=('bytes',n,off,width)
        else:return None
    arg=lambda k:regs.get(_ARG[k]) if k<4 else homes.get(8*k)
    if arg(0)!=('param',0) or arg(hidden)!=('zero',):return None
    expected=set();bases=set()
    for n in range(1,hidden):
        v=arg(n)
        if n not in aggregate:
            if v!=('param',n):return None
        else:
            if not v or v[0]!='home' or v[1]%16 or v[1] in bases:return None
            bases.add(v[1]);data=range(v[1],v[1]+aggregate[n])
            if any(writes.get(p)!=(n,p-v[1]) for p in data):return None
            expected.update(data)
    for n in range(4,hidden+1):expected.update(range(8*n,8*n+8))
    if expected!=writes.keys():return None
    return [f'this.{sink.name}({", ".join(names[1:])});']
