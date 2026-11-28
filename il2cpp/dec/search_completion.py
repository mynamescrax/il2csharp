"""Prove ownership when a filtered search returns on a hit, but a miss
runs a separate acyclic completion path before the common void epilogue."""
from il2cpp.array_origin import _graph
from il2cpp.equivalent_binary import _amd64
from il2cpp.prelude import HAVE_ICED
from il2cpp.terminal_effect import _terminal_frame
if HAVE_ICED:
    from iced_x86 import Mnemonic as M


def terminal_hit(dec,bs,hdr,match,hit,miss,body,stop):
    il=dec.L.il;m=getattr(dec.L,'_current_method',None)
    if not HAVE_ICED or not m or not _amd64(getattr(il,'bin',None)) or not 0<=m.return_type<len(il.types) or il._closed_type_key(il.types[m.return_type])!=(1,0):return None
    parents=lambda k:set(bs[k].preds)&dec.reach
    if miss in stop or parents(miss)!={hdr}:return None
    path=[];prev=match;k=hit
    while k not in body and k!=miss and k not in stop and k not in path and k in dec.reach and len(path)<32:
        b=bs[k]
        if b.consumed or b.is_entry or k in dec.loop_of_hdr:return None
        if b.term==('ret',) and not b.succs and not b.stmts and b.ret=='' and b.insns and b.insns[-1].mnemonic==M.RET:break
        if len(b.succs)!=1 or b.term not in (('jmp',b.succs[0]),('fall',b.succs[0])) or parents(k)!={prev}:return None
        path.append(k);prev,k=k,b.succs[0]
    else:return None
    if not path:return None
    end=k;owned=set();todo=[miss];inc={miss:{hdr}};inc[end]={prev}
    while todo:
        k=todo.pop()
        if k==end or k in owned:continue
        if (k not in dec.reach or k in body or k in path or k in stop or k in dec.loop_of_hdr or bs[k].is_entry or bs[k].consumed or len(owned)>64):return None
        b=bs[k];t=b.term or ()
        if not b.succs or not t or t[0] not in ('fall','jmp','jcc') or set(t[1:])!=set(b.succs) or any(v<=k and v!=end for v in b.succs):return None
        owned.add(k)
        for n in b.succs:inc.setdefault(n,set()).add(k);todo.append(n)
    if any(parents(k)!=inc[k] for k in (*owned,end)):return None
    seq=[i for b in bs for i in b.insns];by={i.ip:i for i in seq};g=_graph(il,seq,chained=True,nested_chains=True)
    if not g or seq[0].ip!=m.addr or bs[end].insns[-1].op_count or not _terminal_frame(il,seq,by,g[0],bs[end].insns[0].ip,bs[end],-1):return None
    return path
