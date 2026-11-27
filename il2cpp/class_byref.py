"""Close root class VAR& formals for a registered Win64 instance call."""
from il2cpp.closed_class_read import _class_entry
from il2cpp.equivalent_binary import _amd64
from il2cpp.prelude import HAVE_ICED

if HAVE_ICED:
    from iced_x86 import OpKind as K


def byref_context(lift,ins,info,es):
    il=lift.il
    if (not HAVE_ICED or not _amd64(getattr(il,'bin',None)) or il.meta.version!=31 or not info or info[0]!='generic' or
            ins.op0_kind!=K.NEAR_BRANCH64 or not 0<=info[1]<len(il.method_specs)):return {}
    si=info[1];mi,ci,gi=il.method_specs[si]
    if ci<0 or gi!=-1 or not 0<=mi<len(il.meta.methods):return {}
    m=il.meta.methods[mi];slot=m.param_count+1
    if (m.is_static or not 1<=m.param_count<=2 or slot>=len(es) or getattr(es[slot],'_usg_idx',None)!=si or
            m.generic_container!=-1 or m.flags&0x400 or m.flags&0x40 and not m.flags&0x20 or
            not 0<=m.declaring<len(il.meta.typedefs) or not 0<=m.return_type<len(il.types) or
            il._closed_type_key(il.types[m.return_type])!=(2,0)):return {}
    td=il.meta.typedefs[m.declaring];recv=es[0];key=il._closed_type_key
    if not recv or recv._unk or recv.kind!='obj' or td.is_valuetype or not 0<=td.generic_container<len(il.meta.generic_containers):return {}
    types=[il.types[p.type] for p in il.meta.method_params(m) if 0<=p.type<len(il.types)]
    refs=[t for t in types if t and il._type_enum(t)==0x13 and t[1]&(1<<29)]
    if len(types)!=m.param_count or not refs:return {}
    owner,argc,is_method,first=il.meta.generic_containers[td.generic_container];args=il._method_spec_type_args(ci)
    if (owner!=m.declaring or is_method or not args or argc!=len(args) or any(not key(a) or key(a)[-1] for a in args) or
            key(recv.ty)!=(0x15,(0x12,td.index,0),tuple(key(a) for a in args),0) or _class_entry(il,si)!=ins.near_branch_target):return {}
    result={}
    for t in refs:
        v=t[0]
        if not first<=v<first+argc or not 0<=v<len(il.meta.generic_parameters) or il.meta.generic_parameters[v][4]!=v-first:return {}
        a=args[v-first];result[t]=(a[0],a[1]|(1<<29))
    return result
