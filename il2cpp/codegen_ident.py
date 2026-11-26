"""Source names for monomorphic codegen TypeDefs with literal angle brackets."""
import re

from il2cpp.names import safe_ident, sanitize
from il2cpp.text import mask_literals


def codegen_names(il):
    cache=il.__dict__.get('_codegen_literal_names')
    if cache is not None: return cache
    types=il.meta.typedefs
    candidates=[t for t in types if getattr(t,'generic_container',None)==-1 and
                re.fullmatch(r'\w+@\w+`1<\w+>',t.name) and t.declaring<0]
    result={}
    for td in candidates:
        old=safe_ident(sanitize(td.name));head=old.split('<')[0]
        siblings=[safe_ident(sanitize(t.name)) for t in types if t is not td and t.namespace==td.namespace and t.declaring<0]
        if old in siblings or head in siblings: continue
        new=old.replace('<','_').rstrip('>'); base=new
        while new in siblings or new in result.values(): new=base+'_'+str(td.index) if new==base else new+'_'
        result[(td.namespace,old)]=new
    il._codegen_literal_names=result
    return result


def render_codegen_idents(il,namespace,lines):
    # Before using-shortening: foreign references still have their namespace.
    # Only rewrite identifier spans, never reflection strings or comments.
    for (ns,old),new in codegen_names(il).items():
        if not any(old in line for line in lines): continue
        qualifier=re.escape(ns+'.') if ns else ''
        if ns and ns==namespace: qualifier='(?:'+qualifier+')?'
        token=re.compile(r'(?<![\w.])('+qualifier+')'+re.escape(old)+r'(?!\w)')
        result=[];comment=False
        for line in lines:
            shadow,comment=mask_literals(line,comment)
            for m in reversed(list(token.finditer(shadow))):line=line[:m.start()]+m[1]+new+line[m.end():]
            result.append(line)
        lines=result
    return lines
