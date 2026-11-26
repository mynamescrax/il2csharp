"""Keep a singleton reference-to-bool operator's declaration and uses in sync."""


def truth_owner(il,m):
    if (not m or m.name!='op_Implicit' or not m.is_static or m.flags&7!=6 or not m.flags&0x800 or m.flags&(0x40|0x400|0x2000) or
            m.generic_container!=-1 or m.param_count!=1 or not 0<=m.return_type<len(il.types) or
            il._closed_type_key(il.types[m.return_type])!=(2,0) or not 0<=m.declaring<len(il.meta.typedefs)):return None
    t=il.meta.typedefs[m.declaring];ps=il.meta.method_params(m)
    if (t.is_valuetype or t.flags&0x20 or t.generic_container!=-1 or len(ps)!=1 or not 0<=ps[0].type<len(il.types) or
            il._closed_type_key(il.types[ps[0].type])!=(0x12,t.index,0) or il.types[ps[0].type][1]&0x1010):return None
    for j in il.meta.type_methods(t):
        if j==m.index:continue
        other=il.meta.methods[j]
        if other.name=='op_Implicit':return None
        if other.name=='op_Explicit' and other.param_count==1 and 0<=other.return_type<len(il.types) and il._closed_type_key(il.types[other.return_type])==(2,0):
            params=il.meta.method_params(other)
            if len(params)!=1 or not 0<=params[0].type<len(il.types) or il._closed_type_key(il.types[params[0].type])==(0x12,t.index,0):return None
    return il.type_name(il.types[ps[0].type])


def truth_cast(owner,arg):return f'((bool)(({owner})({arg})))'
