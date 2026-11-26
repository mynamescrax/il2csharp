"""A folded Win64 Transform.SetParent(Transform) and its ordered operands."""
import re
import struct

from il2cpp.binary import PE
from il2cpp.awaiter import _static_reference, _unused_return
from il2cpp.expr import Expr, acc_get
from il2cpp.marshalled_getter import _INIT, _READY, _null_exits
from il2cpp.prelude import HAVE_ICED
from il2cpp.shared_getter import getter_alias
from il2cpp.sret_copy import _own_field
from il2cpp.text import reg_name, sdisp
from il2cpp.x64 import KLASS_STATIC_FIELDS

if HAVE_ICED:
    from iced_x86 import Decoder, FlowControl as F, InstructionInfoFactory, Mnemonic as M, OpAccess, OpKind as K, Register as R, RegisterExt
    _INFO = InstructionInfoFactory()
    _READ = {OpAccess.READ,OpAccess.READ_WRITE,OpAccess.COND_READ,OpAccess.READ_COND_WRITE}
    _WRITE = {OpAccess.WRITE,OpAccess.READ_WRITE,OpAccess.COND_WRITE,OpAccess.READ_COND_WRITE}


def _thread_id_import(b, cell):
    """Check the actual PE64 import lookup entry, not just a pointer to a name."""
    if len(b.d) < 64:
        return False
    pe, = struct.unpack_from('<I',b.d,0x3c)
    if pe+152 > len(b.d):
        return False
    rva, size = struct.unpack_from('<II',b.d,pe+24+120)
    for off in range(0,min(size, 20*512)-19,20):
        row = b.read(b.image_base+rva+off,20)
        if not row or len(row) != 20:
            break
        lookup, _, _, dll, iat = struct.unpack('<5I',row)
        if not iat:
            break
        delta = cell - (b.image_base+iat)
        if not lookup or not 0 <= delta < 8*4096 or delta%8 or (b.cstr(b.image_base+dll) or '').lower() != 'baselib.dll':
            continue
        for j in range(0,delta+1,8):
            name = b.qword(b.image_base+lookup+j)
            if not name:
                break
        else:
            return name < 2**32 and b.cstr(b.image_base+name+2) == '?Baselib_Thread_GetCurrentThreadId@il2cpp_baselib@@YA_JXZ'
    return False


_CTX = re.compile(rb'\x40\x53\x48\x83\xec\x20\x48\x8b\xd9\xe8(.{4})\x48\x8b\xc3\x48\x83\xc4\x20\x5b\xc3',re.S)


def _context_independent(il, target):
    # The optional MethodInfo initialization receives a constant Marshal<T>
    # slot in RCX. Check its cold helper cannot use the *incoming* R8, even
    # if it survives earlier volatile calls. Stop a path on a full write.
    b = il.bin
    s,e = il.function_extent(target)
    if s != target or e-s != 23:
        return False
    stub = _CTX.fullmatch(b.read(s,e-s) or b'')
    if not stub:
        return False
    core = s+stub.end(1)+int.from_bytes(stub[1],'little',signed=True)
    s,e = il.function_extent(core)
    if s != core or not b.is_exec_va(core) or not 0 < e-s <= 512:
        return False
    seq = {i.ip:i for i in Decoder(64,b.read(s,e-s) or b'',ip=s)}
    work,seen = [core],set()
    while work:
        ip=work.pop()
        if ip in seen:
            continue
        seen.add(ip); i=seq.get(ip)
        if i is None or i.is_invalid:
            return False
        uses=[r for r in _INFO.info(i).used_registers() if RegisterExt.full_register(r.register)==R.R8]
        if any(r.access in _READ for r in uses):
            return False
        if any(r.access==OpAccess.WRITE and r.register in (R.R8, R.R8D) for r in uses):
            continue
        fc=i.flow_control
        if fc==F.RETURN:
            continue
        if fc in (F.CONDITIONAL_BRANCH,F.UNCONDITIONAL_BRANCH) and i.op0_kind==K.NEAR_BRANCH64:
            work.append(i.near_branch_target)
        elif fc==F.INDIRECT_CALL and i.memory_base==R.RIP and not i.has_segment_prefix:
            if not _thread_id_import(b,i.ip_rel_memory_address):
                return False
        elif fc!=F.NEXT:
            return False
        if fc!=F.UNCONDITIONAL_BRANCH:
            work.append(i.next_ip)
    return True


_ENTRY = re.compile(rb'\x48\x89\x5c\x24\x10\x57\x48\x83\xec\x20\x80\x3d(.{4})\x00\x48\x8b\xfa\x48\x8b\xd9\x75(.)',re.S)
# Null managed receiver and zero native receiver take distinct throw arms.
_SELF = re.compile(rb'\x48\x85\xdb\x74(.)\x48\x89\x74\x24\x30\x48\x8b\x73(.)\x48\x85\xf6\x74(.)',re.S)
# Non-null parent -> cached pointer, null parent -> zero. No dereference on null.
_PARENT = re.compile(rb'\x48\x8b\x0d(.{4})\x48\x83\x79\x38\x00\x75\x05\xe8(.{4})\x48\x85\xff\x74\x06\x48\x8b\x5f(.)\xeb\x02\x33\xdb',re.S)
# Cache hit and resolver miss join at `mov r8b,1`. Restore the native pointers
# to RDX=parent and RCX=child, unwind, and tail-jump to the injected operation.
_MUTATE = re.compile(rb'\x48\x8b\x05(.{4})\x48\x85\xc0\x75\x13\x48\x8d\x0d(.{4})\xe8(.{4})\x48\x89\x05(.{4})'
                     rb'\x41\xb0\x01\x48\x8b\xd3\x48\x8b\xce\x48\x8b\x74\x24\x30\x48\x8b\x5c\x24\x38\x48\x83\xc4\x20\x5f\x48\xff\xe0',re.S)


def _marshal_slot(il, slot, name, owner):
    use = il.decode_slot(slot) or {}
    si = use.get('idx', -1)
    if use.get('kind') != 6 or not 0 <= si < len(il.method_specs):
        return False
    mi, ci, gi = il.method_specs[si]
    if ci != -1 or not 0 <= mi < len(il.meta.methods):
        return False
    m = il.meta.methods[mi]
    args = il._method_spec_type_args(gi)
    ps = il.meta.method_params(m)
    if (not m.is_static or m.name != name or m.generic_container < 0 or m.param_count != 1 or len(ps) != 1 or
            il.typedef_full(m.declaring) != 'UnityEngine.Object.MarshalledUnityObject' or
            not args or len(args) != 1 or il._closed_type_key(args[0]) != (0x12,owner,0) or
            not 0 <= ps[0].type < len(il.types) or not 0 <= m.return_type < len(il.types)):
        return False
    pt = il.types[ps[0].type]
    return (pt and il._type_enum(pt) == 0x1e and not pt[1] & (1<<29) and
            0 <= pt[0] < len(il.meta.generic_parameters) and
            il.meta.generic_parameters[pt[0]][0] == m.generic_container and il.meta.generic_parameters[pt[0]][4] == 0 and
            il._closed_type_key(il.types[m.return_type]) == (0x18,0))


def _alias(lift, addr):
    il=lift.il
    cands=il.addr_candidates.get(addr,())
    if (len(cands)!=2 or any(k!='method' or not 0<=mi<len(il.meta.methods) for k,mi in cands)):
        return None
    rows=[il.meta.methods[mi] for _,mi in cands]
    owner=rows[0].declaring
    if not 0<=owner<len(il.meta.typedefs) or il.typedef_full(owner)!='UnityEngine.Transform':
        return None
    ty=(0x12,owner,0)
    for m in rows:
        ps=il.meta.method_params(m)
        if (m.addr!=addr or m.declaring!=owner or m.is_static or m.flags&0x40 or m.generic_container!=-1 or
                m.param_count!=1 or len(ps)!=1 or not 0<=ps[0].type<len(il.types) or il._closed_type_key(il.types[ps[0].type])!=ty or
                not 0<=m.return_type<len(il.types) or il._closed_type_key(il.types[m.return_type])!=(1,0)):
            return None
    if {(m.name,m.flags&7) for m in rows}!={('set_parentInternal',3),('SetParent',6)}:
        return None
    end=il.next_method_start(addr)
    if not end or not 0<end-addr<=384 or not il.bin.is_exec_va(addr):
        return None
    data=il.bin.read(addr,end-addr) or b''
    def rel(m,g,trailing=0):
        return addr+m.end(g)+trailing+int.from_bytes(m[g],'little',signed=True)
    entry=_ENTRY.match(data)
    if not entry:
        return None
    pos=entry.end(); slots=[]
    while (init:=_INIT.match(data,pos)):
        if rel(init,2)!=lift.rt_init_meta:
            return None
        slots.append(rel(init,1)); pos=init.end()
    ready=_READY.match(data,pos)
    if not ready or rel(ready,1,1)!=rel(entry,1,1) or rel(entry,2)!=addr+ready.end():
        return None
    child=_SELF.match(data,ready.end()); parent=_PARENT.match(data,child.end()) if child else None
    if (not parent or len(slots) != 2 or rel(parent,1) != slots[1] or child[2]!=parent[3] or
            not _marshal_slot(il,slots[0],'MarshalNotNull',owner) or not _marshal_slot(il,slots[1],'Marshal',owner)):
        return None
    field=(il.instance_field_chain(owner) or {}).get(int.from_bytes(child[2],'little',signed=True))
    if not field or field[0]!='m_CachedPtr' or not 0<=field[1]<len(il.types) or il._closed_type_key(il.types[field[1]])!=(0x18,0):
        return None
    if not _context_independent(il,rel(parent,2)):
        return None
    tail=_MUTATE.match(data,parent.end()); sig='UnityEngine.Transform::SetParent_Injected(System.IntPtr,System.IntPtr,System.Boolean)'
    if (not tail or rel(tail,1)!=rel(tail,4) or rel(tail,3)!=il.rt_icall_resolve or
            il.icall_cells.get(rel(tail,1))!=sig or il.bin.cstr(rel(tail,2),512)!=sig or
            not _null_exits(lift,addr,data,tail.end(),rel(child,1),rel(child,3))):
        return None
    mi=(il._icall_annotation(sig) or {}).get('method',-1)
    if not 0<=mi<len(il.meta.methods):
        return None
    inj=il.meta.methods[mi]; ps=il.meta.method_params(inj)
    if (inj.declaring==owner and inj.name=='SetParent_Injected' and inj.is_static and inj.iflags&0x1000 and
            inj.param_count==len(ps)==3 and all(0<=p.type<len(il.types) for p in ps) and
            [il._closed_type_key(il.types[p.type]) for p in ps]==[(0x18,0),(0x18,0),(2,0)] and
            0<=inj.return_type<len(il.types) and il._closed_type_key(il.types[inj.return_type])==(1,0)):
        return owner


def _result_origin(blocks, b, j, reg, *, array_element=False):
    """Walk back through full-width moves only. A call defines RAX and
    invalidates volatile copies. Do not infer an operand across a merge."""
    seen = set()
    while b.bid not in seen and len(seen) < 8:
        seen.add(b.bid)
        for i in reversed(b.insns[:j]):
            if i.flow_control in (F.CALL, F.INDIRECT_CALL):
                if reg == R.RAX and i.op0_kind == K.NEAR_BRANCH64:
                    return i
                if reg not in (R.RBX,R.RBP,R.RSI,R.RDI,R.R12,R.R13,R.R14,R.R15):
                    return None
            if any(u.access in _WRITE and RegisterExt.full_register(u.register)==reg
                   for u in _INFO.info(i).used_registers()):
                if (array_element and i.mnemonic == M.MOV and i.op0_register == reg and RegisterExt.is_gpr64(reg) and
                        i.op1_kind == K.MEMORY and not i.has_segment_prefix and i.memory_displacement == 0x20 and
                        RegisterExt.is_gpr64(i.memory_index) and i.memory_index_scale == 8):
                    return i
                if i.mnemonic != M.MOV or i.op0_register != reg or not RegisterExt.is_gpr64(i.op1_register):
                    return None
                reg = i.op1_register
        if len(b.preds) != 1 or not 0 <= b.preds[0] < len(blocks):
            break
        b = blocks[b.preds[0]]
        j = len(b.insns)
    return None


def _saved_array_source(blocks, b, j, reg):
    """The same field load must define the array on every edge, including
    the scan's latch. A type inferred from only one predecessor isn't enough."""
    if reg not in (R.RBX,R.RBP,R.RDI,R.RSI,R.R12,R.R13,R.R14,R.R15):
        return None
    work, seen, defs = [(b.bid,j)], set(), set()
    while work:
        bid, end = work.pop()
        if (bid,end) in seen:
            continue
        if not 0 <= bid < len(blocks) or len(seen) >= 64:
            return None
        seen.add((bid,end)); p = blocks[bid]
        for n in range(end-1,-1,-1):
            i = p.insns[n]
            if any(u.access in _WRITE and RegisterExt.full_register(u.register)==reg for u in _INFO.info(i).used_registers()):
                if (i.mnemonic != M.MOV or i.op0_register != reg or i.op1_kind != K.MEMORY or
                        not RegisterExt.is_gpr64(i.memory_base) or i.memory_index != R.NONE or i.has_segment_prefix):
                    return None
                defs.add((bid,n)); break
        else:
            if not p.preds or any(not 0 <= k < len(blocks) for k in p.preds):
                return None
            work.extend((k,len(blocks[k].insns)) for k in p.preds)
    return defs.pop() if len(defs)==1 else None


def _array_operand(lift, blocks, element, owner):
    """SZARRAY class field of a checked static singleton; signed index and
    pointer-stride load. Freeze the element *before* invoking childCount."""
    il = lift.il
    loc = next(((b,j) for b in blocks for j,i in enumerate(b.insns) if i.ip == element.ip), None)
    if loc is None:
        return None
    b,j = loc
    if not j or element.op0_register in (element.memory_base, element.memory_index):
        return None
    ext = b.insns[j-1]
    if (ext.mnemonic != M.MOVSXD or ext.op0_register != element.memory_index or not RegisterExt.is_gpr32(ext.op1_register) or
            ext.next_ip != element.ip or len(b.preds) != 1):
        return None
    guard = blocks[b.preds[0]]
    if len(guard.insns) < 2:
        return None
    cmp, out = guard.insns[-2:]
    if (cmp.mnemonic != M.CMP or cmp.op0_register != ext.op1_register or cmp.memory_base != element.memory_base or
            cmp.memory_index != R.NONE or cmp.memory_displacement != 0x18 or cmp.has_segment_prefix or
            out.mnemonic != M.JAE or cmp.next_ip != out.ip or out.next_ip != ext.ip or out.near_branch_target == ext.ip):
        return None
    src = _saved_array_source(blocks,b,j,element.memory_base)
    if not src:
        return None
    bid,n = src
    source = blocks[bid]
    if n or len(source.preds) != 1:
        return None
    field = source.insns[n]
    seq = blocks[source.preds[0]].insns
    if len(seq) < 5 or seq[-1].next_ip != field.ip or any(a.next_ip != c.ip for a,c in zip(seq,seq[1:])):
        return None
    klass = seq[0]; blob, obj, test, null = seq[-4:]
    if (klass.mnemonic != M.MOV or klass.memory_base != R.RIP or not RegisterExt.is_gpr64(klass.op0_register) or
            any(i.has_segment_prefix or i.memory_index != R.NONE for i in seq) or
            any(i.mnemonic != M.MOV or i.op0_kind != K.MEMORY or i.memory_base != R.RSP or not RegisterExt.is_gpr64(i.op1_register)
                for i in seq[1:-4]) or blob.mnemonic != M.MOV or blob.memory_base != klass.op0_register or
            blob.memory_displacement != KLASS_STATIC_FIELDS or not RegisterExt.is_gpr64(blob.op0_register) or
            obj.mnemonic != M.MOV or obj.op0_register != field.memory_base or obj.memory_base != blob.op0_register or
            test.mnemonic != M.TEST or test.op0_register != obj.op0_register or test.op1_register != obj.op0_register or
            null.mnemonic != M.JE or null.near_branch_target == field.ip):
        return None
    ti = _static_reference(il,klass.ip_rel_memory_address,sdisp(obj.memory_displacement))
    if ti is None:
        return None
    member = _own_field(il,il.meta.typedefs[ti],sdisp(field.memory_displacement),8)
    if member and il._closed_type_key(member[1]) == (0x1d,(0x12,owner,0),0):
        return {field.ip:('array',member[1]), element.ip:('element',field.ip,owner)}
    return None


def bind_array_operand(lift, i, binding):
    dst = reg_name(i.op0_register)
    value = dict.get(lift.regs,dst)
    if not value or value._unk:
        return
    if binding[0] == 'array':
        if value.kind != 'arr' or value.ty != binding[1]:
            return
        text = value.text
    else:
        _, ip, owner = binding
        arr = lift._hierarchy_values.get(ip)
        base = dict.get(lift.regs,reg_name(i.memory_base)); idx = dict.get(lift.regs,reg_name(i.memory_index))
        if (not arr or not base or arr.ty != base.ty or not idx or idx._unk or idx.kind != 'int' or
                value.kind != 'obj' or lift.il._closed_type_key(value.ty) != (0x12,owner,0) or
                value.text != f'{base.text}[{idx.text}]'):
            return
        text = f'{arr.text}[{idx.text}]'
    name = lift.new_var(); lift._var_types[name] = value.ty
    lift.emit(i.ip,f'var {name} = {acc_get(text)};',None)
    snapshot = Expr(name,value.ty,value.kind)
    lift.regs[dst] = snapshot
    lift._hierarchy_values[i.ip] = snapshot


def _unity_property(lift, addr):
    il = lift.il
    c = il.addr_candidates.get(addr, ())
    if len(c) != 1 or c[0][0] != 'method' or not 0 <= c[0][1] < len(il.meta.methods):
        return None
    mi = c[0][1]; m = il.meta.methods[mi]
    if (m.name not in ('get_transform', 'get_gameObject') or m.is_static or m.param_count or m.flags & 0x40 or
            m.addr != addr or not 0 <= m.return_type < len(il.types) or
            il.typedef_full(m.declaring) not in ('UnityEngine.Component','UnityEngine.GameObject') or
            lift._accessor_prop(mi) != ('get',m.name[4:],0)):
        return None
    ty = il.types[m.return_type]
    expected = 'UnityEngine.Transform' if m.name == 'get_transform' else 'UnityEngine.GameObject'
    if ty and il._closed_type_key(ty) == (0x12,ty[0],0) and il.type_name(ty) == expected:
        return mi
    return None


def hierarchy_sites(lift, method, blocks, pads):
    """Bind getter results at their definitions, before hierarchy mutation.
    E.g. child.transform is evaluated BEFORE the getter for the new parent;
    delaying it until SetParent could move a throw or select a different child."""
    il = lift.il
    bindings, sites = {}, {}
    if (not HAVE_ICED or pads or not isinstance(getattr(il,'bin',None), PE) or not il.bin.is64 or getattr(il.meta,'version',None) != 31 or
            not 0 <= method.return_type < len(il.types) or il._closed_type_key(il.types[method.return_type]) != (1,0)):
        return bindings, sites
    cache = il.__dict__.setdefault('_reparent_aliases', {})
    for b in blocks:
        for j,i in enumerate(b.insns):
            if i.mnemonic != M.CALL or i.op0_kind != K.NEAR_BRANCH64:
                continue
            target = i.near_branch_target
            if target == method.addr or len(il.addr_candidates.get(target, ())) != 2:
                continue
            if target not in cache:
                cache[target] = _alias(lift,target)
            owner = cache[target]
            if owner is None or j < 3:
                continue
            hidden, arg, recv = b.insns[j-3:j]
            if (hidden.mnemonic != M.XOR or hidden.op0_register != hidden.op1_register or hidden.op0_register != R.R8D or
                    arg.mnemonic != M.MOV or arg.op0_register != R.RDX or not RegisterExt.is_gpr64(arg.op1_register) or
                    recv.mnemonic != M.MOV or recv.op0_register != R.RCX or not RegisterExt.is_gpr64(recv.op1_register) or
                    any(a.next_ip != c.ip for a,c in zip(b.insns[j-3:j],b.insns[j-2:j+1]))):
                continue
            pair = [_result_origin(blocks,b,j,r,array_element=(r==R.RDX)) for r in (R.RCX,R.RDX)]
            proven = {}
            for producer in pair:
                if producer is None:
                    break
                if producer.mnemonic == M.MOV:
                    elements = _array_operand(lift,blocks,producer,owner)
                    if not elements:
                        break
                    proven.update(elements)
                    continue
                addr = producer.near_branch_target
                mi = _unity_property(lift,addr)
                if mi is not None and il.meta.methods[mi].name == 'get_transform':
                    proven[producer.ip] = ('method',mi)
                elif getter_alias(lift,addr,owner) == ('parent',il.typedef_full(owner)):
                    proven[producer.ip] = ('parent',addr)
                else:
                    break
            else:
                bindings.update(proven)
                sites[i.ip] = (owner,target,pair[0].ip,pair[1].ip)
    if sites:
        # Other parked getters in the same spawn expression, notably
        # template.gameObject before reading the spawner's position.
        for b in blocks:
            for j,i in enumerate(b.insns):
                if i.mnemonic != M.CALL or i.op0_kind != K.NEAR_BRANCH64:
                    continue
                mi = _unity_property(lift,i.near_branch_target)
                if mi is not None and any(x.mnemonic == M.MOV and x.op1_register == R.RAX and
                                          x.op0_register in (R.RBX,R.RBP,R.RSI,R.RDI,R.R12,R.R13,R.R14,R.R15) and
                                          _result_origin(blocks,b,k,R.RAX) == i
                                          for k,x in enumerate(b.insns[j+1:j+5], j+1)):
                    bindings[i.ip] = ('method',mi)
    return bindings, sites


def reparent_call(lift, ins, args, regs, xmm):
    site = getattr(lift, '_reparent_sites', {}).get(ins.ip)
    if not site or len(args) != 2 or len(regs) != 4:
        return None
    owner,target,child,parent = site
    if (target != ins.near_branch_target or not regs[2] or regs[2]._unk or regs[2].text != '0' or
            any(e and not e._unk and not re.fullmatch(r'\w+|-?\d+(?:\.\d+)?[fd]?', e.text or '') for e in (regs[3],*xmm))):
        return None
    for origin,e,text in zip((child,parent),regs,args):
        if (not e or e._unk or lift._hierarchy_values.get(origin) is not e or e.kind != 'obj' or
                lift.il._closed_type_key(e.ty) != (0x12,owner,0) or e.text != text or not re.fullmatch(r't\d+',text)):
            return None
    if _unused_return(lift, ins.next_ip):
        return '%s.SetParent(%s) /* shared implementation */' % tuple(args)
    return None
