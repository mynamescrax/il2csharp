"""A filtered search with a private success prefix and common continuation.

Both rejection edges advance the same latch; exhaustion bypasses the action.
The header and last action have different phi copies into the shared exit.
"""
from il2cpp.cfg import LBL


def joined_search(dec,bs,hdr,stop,outer,out,depth):
    if outer or dec._sw_depth or dec._seh_regions or dec._pad_bids:return None
    body,latch=dec.loop_of_hdr[hdr];h=bs[hdr]
    # _forward_empty redirects reachable edges but retains unreachable
    # trampoline blocks in the list. Their edges are not incoming paths.
    reach=dec.reach
    def parents(n):return set(bs[n].preds)&reach
    if (not body<=reach or not 3<=len(body)<=32 or body&stop or h.stmts or len(parents(hdr)-body)!=1 or
            parents(hdr)&body!={latch}):return None
    def cond(b):return (b.cond and b.term and len(b.term)==3 and b.term[0]=='jcc' and
                        len(b.succs)==2 and set(b.succs)==set(b.term[1:]) and len(set(b.succs))==2)
    def linear(b):return len(b.succs)==1 and b.term in [('jmp',b.succs[0]),('fall',b.succs[0])]
    if not cond(h) or sum(k in body for k in h.succs)!=1:return None
    start=next(k for k in h.succs if k in body);join=next(k for k in h.succs if k not in body)
    if join not in reach or not 0<=join<len(bs) or bs[join].consumed and join not in stop:return None
    if any(bs[n].consumed or n!=hdr and (n in dec.loop_of_hdr or parents(n)-body) for n in body):return None
    if not linear(bs[latch]) or bs[latch].succs!=[hdr]:return None
    # Walk the single progression. A side block may only run on one arm
    # and must flow directly into the same following block as the other.
    steps=[];seen={hdr};reject=[];k=start;hit=None
    while k in body and k not in seen and k!=latch:
        seen.add(k);b=bs[k]
        if linear(b):
            n=b.succs[0];steps.append(('linear',k,n));k=n;continue
        if not cond(b):return None
        left,right=b.succs
        if latch in (left,right):
            more=right if left==latch else left
            if more in body:
                reject.append(k);steps.append(('guard',k,more));k=more;continue
            if k==hdr or more==join or not 0<=more<len(bs):return None
            hit=more;steps.append(('match',k,more));break
        if left not in body or right not in body:return None
        options=[(a,z) for a,z in ((left,right),(right,left)) if a not in seen and z not in seen and linear(bs[a]) and
                 bs[a].succs==[z] and parents(a)=={k} and parents(z)=={k,a}]
        if len(options)!=1:return None
        side,n=options[0];steps.append(('diamond',k,side,n));seen.add(side);k=n
    if hit is None or not reject or seen|{latch}!=body or parents(latch)!={*reject,k}:return None
    # Exact incoming edges throughout, including at the action boundary.
    expected={n:set() for n in body};expected[start].add(hdr)
    for step,n,*args in steps:
        for dest in bs[n].succs:
            if dest in body:expected[dest].add(n)
        if step=='diamond':expected[args[1]].add(args[0])
    if any(parents(n)!=expected[n] for n in body if n!=hdr):return None
    terminating=False
    if parents(join)=={hdr}:
        from il2cpp.dec.search_completion import terminal_hit
        certified=terminal_hit(dec,bs,hdr,k,hit,join,body,stop)
        if certified is None:return None
        terminating=True
    path=[];prev=k;k=hit
    while not terminating and k!=join:
        if (k not in reach or not 0<=k<len(bs) or k in path or k in body or k in stop or k in dec.loop_of_hdr or bs[k].consumed or
                bs[k].is_entry or len(path)>=32 or parents(k)!={prev} or not linear(bs[k])):return None
        path.append(k);prev,k=k,bs[k].succs[0]
    if terminating:path=certified
    elif not path or parents(join)!={hdr,path[-1]}:return None
    # Do not claim a continuation already owned by a sibling. Follow only
    # private linear cleanup, stopping before the parent's own boundary.
    end=join;previous={hdr,path[-1]};used=set()
    while not terminating and end not in stop:
        if (end not in reach or not 0<=end<len(bs) or end in body or end in used or end in path or bs[end].consumed or
                bs[end].is_entry or end in dec.loop_of_hdr or len(used)>=32 or parents(end)!=previous):return None
        z=bs[end]
        if z.term==('ret',) and not z.succs:break
        if not linear(z):return None
        used.add(end);previous={end};end=z.succs[0]
    def test(b,dest):return b.cond if dest==b.term[1] else '!(%s)'%b.cond
    def open_(b,dest):out.extend(('if (%s)'%test(b,dest),'{'));dec._brace_push('if')
    def close():out.append('}');dec._brace_pop(bs,out,depth+1)
    def edge(a,z):dec._edge(a,z,out)
    def block(n):bs[n].consumed=True;out.extend(bs[n].stmts)
    h.consumed=True
    if h.insns:out.append('%sL_%x:'%(LBL,h.insns[0].ip))
    out.extend(('while (true)','{'));dec._brace_push('loop');open_(h,join);edge(hdr,join);out.append('break;');close();edge(hdr,start)
    for step,n,*args in steps:
        block(n);b=bs[n]
        if step=='linear':edge(n,args[0]);continue
        if step=='diamond':
            side,next_=args;open_(b,side);edge(n,side);block(side);edge(side,next_);close()
            if dec.phi_copies.get((n,next_)):
                out.extend(('else','{'));dec._brace_push('else');edge(n,next_);close()
        elif step=='guard':
            open_(b,args[0]);edge(n,args[0])
        else:
            open_(b,hit);edge(n,hit)
            for a in path:block(a);edge(a,bs[a].succs[0])
            out.append('return;' if terminating else 'break;');close();edge(n,latch)
    for n in reversed(reject):
        close()
        if dec.phi_copies.get((n,latch)):
            out.extend(('else','{'));dec._brace_push('else');edge(n,latch);close()
    block(latch);edge(latch,hdr);out.append('}');dec._brace_pop(bs,out,depth)
    return join
