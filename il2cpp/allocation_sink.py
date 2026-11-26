"""Preserve a fresh constructor's type when its sole use stores it as object."""
from collections import Counter
import re

from il2cpp.csharp import FA_LITERAL, FA_STATIC, field_attrs, source_field_name


def allocation_sinks(lift, method, lines, tokens):
    fresh = getattr(lift, '_bound_constructor_types', {})
    if not fresh or method is None or method.is_static: return {}
    il=lift.il; meta=il.meta; td=meta.typedefs[method.declaring]
    stores = set()
    for fi in meta.type_fields(td):
        f=meta.fields[fi]
        if (0<=f.type<len(il.types) and il._closed_type_key(il.types[f.type])==(0x1c,0) and
                not field_attrs(il,f)&(FA_LITERAL|FA_STATIC)):
            stores.add('this.'+source_field_name(il,fi))
    if not stores: return {}
    counts=Counter(tokens); selected={}
    for line,following in zip(lines,lines[1:]):
        definition=re.fullmatch(r'\s*var (t\d+) = new ([\w.]+)\((.*)\);\s*',line)
        if not definition: continue
        tok,tn,argtext=definition.groups(); ty=fresh.get(tok)
        if not ty or counts[tok]!=2 or il.type_name(ty)!=tn: continue
        # Input lines already have strings and comments masked. Ensure the
        # constructor finishes the RHS, not `new T().GetSomethingElse()`.
        depth=0
        for c in argtext:
            if c=='(': depth+=1
            elif c==')':
                depth-=1
                if depth<0: break
        if depth!=0: continue
        lhs,sep,rhs=following.strip().partition(' = ')
        if sep and lhs in stores and rhs==tok+';': selected[tok]=tn
    return selected
