"""Two-exit search: a private successful arm returns from the method.

A break must not send both the match and exhaustion edge to the same
continuation. Move the private terminal arm into the match guard; then
the loop's ordinary condition owns exhaustion, including zero iterations.
"""
from il2cpp.cfg import LBL
from il2cpp.prelude import HAVE_ICED

if HAVE_ICED:
    from iced_x86 import Mnemonic as M


def _owns_miss(blocks, start, hdr, stop, loops):
    """The parent may resume at its own stop, not inside a sibling arm."""
    n = start; previous = hdr; seen = set()
    while n not in stop:
        if not 0 <= n < len(blocks) or n in seen or len(seen) >= 32:
            return False
        b = blocks[n]
        if b.consumed or b.is_entry or n in loops or set(b.preds) != {previous}:
            return False
        if not b.succs:
            # No miss instructions are moved. The ordinary sequencer owns
            # this block, including a virtual call at a native tail jump.
            return (bool(b.insns) and (b.term == ('ret',) and b.insns[-1].mnemonic == M.RET or
                    b.term == ('stop',) and b.insns[-1].mnemonic == M.JMP))
        if len(b.succs) != 1 or b.term not in (('jmp', b.succs[0]), ('fall', b.succs[0])):
            return False
        seen.add(n); previous, n = n, b.succs[0]
    return True


def _null_or_tail(dec, blocks, miss, hdr, stop, hit, caller, rt):
    """A private exhaustion arm returns a native null reference; the hit
    already contains a value-returning tail. Neither arm can fall into the
    other. Verify the return ABI and both actual root-frame epilogues."""
    from types import SimpleNamespace
    from il2cpp.array_origin import _graph
    from il2cpp.equivalent_binary import _amd64
    from il2cpp.terminal_effect import _terminal_frame
    from iced_x86 import OpKind as K, Register as R
    il=dec.L.il; no=blocks[miss]; yes=blocks[hit]
    if (not _amd64(getattr(il,'bin',None)) or il.meta.version!=31 or rt[0]!=0x12 or rt[-1] or
            miss in stop or hit in stop or no.consumed or yes.consumed or set(no.preds)!={hdr} or
            no.term!=('ret',) or no.succs or no.stmts or no.ret not in ('0','null') or not no.insns or
            no.insns[-1].mnemonic!=M.RET or no.insns[-1].op_count or no.insns[-1].stack_pointer_increment!=8 or
            yes.term!=('stop',) or yes.succs or len(yes.stmts)!=1 or not yes.stmts[0].startswith('return ') or
            not yes.stmts[0].endswith('; /* tail */') or not yes.insns):return False
    seq=[i for b in blocks for i in b.insns];g=_graph(il,seq,allow_tail=True,chained=True,nested_chains=True)
    if not g or seq[0].ip!=caller.addr:return False
    by={i.ip:i for i in seq};pred,_=g
    zeros=[i for i in no.insns if i.mnemonic==M.XOR and i.op0_register==i.op1_register==R.EAX]
    if len(zeros)!=1 or any(a.next_ip!=z.ip or pred[z.ip]!=[a.ip] for a,z in zip(no.insns,no.insns[1:])):return False
    restore=[i for i in no.insns if i.ip!=zeros[0].ip]
    if not _terminal_frame(il,seq,by,pred,no.insns[0].ip,SimpleNamespace(insns=restore),-1):return False
    tail=yes.insns[-1];ids=il.addr_candidates.get(tail.near_branch_target,()) if tail.is_jmp_short_or_near else ()
    if len(ids)!=1 or ids[0][0]!='method' or not 0<=ids[0][1]<len(il.meta.methods):return False
    md=il.meta.methods[ids[0][1]]; prop=dec.L._accessor_prop(md.index)
    if (md.addr!=tail.near_branch_target or md.generic_container!=-1 or md.is_static or md.param_count or md.flags&0x40 or
            not prop or prop[0]!='get' or prop[2] or not 0<=md.return_type<len(il.types) or il._closed_type_key(il.types[md.return_type])!=rt):return False
    # The existing resolved tail must stand alone. Validate the setup and
    # terminal stack restoration, never take a textual stop as a return.
    if len(yes.insns)<4:return False
    z,recv=yes.insns[:2]
    if (z.mnemonic!=M.XOR or z.op0_register!=z.op1_register or z.op0_register!=R.EDX or recv.mnemonic!=M.MOV or recv.op0_register!=R.RCX or
            recv.op1_kind!=K.REGISTER or recv.op1_register not in (R.RBX,R.RSI,R.RDI,R.R12,R.R13,R.R14,R.R15) or
            any(a.next_ip!=n.ip or pred[n.ip]!=[a.ip] for a,n in zip(yes.insns,yes.insns[1:]))):return False
    witness=getattr(dec.L,'_element_tail_returns',{}).get(tail.ip)
    if not witness:return False
    ip,mi,value,call=witness
    from il2cpp.array_origin import _definitions
    from il2cpp.csharp import declares_member_name
    from il2cpp.expr import acc_get
    if (mi!=md.index or getattr(dec.L,'_element_samples',{}).get(ip) is not value or not value.ty or
            il._closed_type_key(value.ty)!=(0x12,value.ty[0],0) or call!=acc_get(value.text+'.'+prop[1]) or
            yes.stmts!=['return '+call+'; /* tail */']):return False
    chain=il.base_chain_tds(value.ty[0])
    if md.declaring not in chain or any(declares_member_name(il,il.meta.typedefs[t],prop[1]) for t in chain[:chain.index(md.declaring)]):return False
    source={(ip,by[ip].op0_register)}
    if (_definitions(by,pred,caller.addr,tail.ip,R.RCX)!=source or not any(i.is_call_near and
            i.near_branch_target==md.addr and _definitions(by,pred,caller.addr,i.ip,R.RCX)==source for i in seq)):return False
    return _terminal_frame(il,seq,by,pred,z.ip,yes,1)


def terminal_search(dec, blocks, hdr, stop, outer, out, depth):
    if (not HAVE_ICED or outer or dec._sw_depth or dec._seh_regions or dec._pad_bids):
        return None
    h = blocks[hdr]
    body, latch = dec.loop_of_hdr[hdr]
    if (len(body) < 2 or len(body) > 32 or body & stop or h.stmts or not h.cond or
            len(set(h.preds) - body) != 1 or set(h.preds) & body != {latch} or
            not h.term or h.term[0] != 'jcc' or len(h.succs) != 2):
        return None
    chain = []; arms = []; k = hdr
    while k in body and k not in chain:
        b = blocks[k]; t = b.term or ()
        if (b.consumed or not t or k != hdr and (k in dec.loop_of_hdr or set(b.preds) != {chain[-1]})):
            return None
        inside = [s for s in b.succs if s in body]
        if len(inside) != 1:
            return None
        if t[0] == 'jcc' and b.cond and len(t) == 3 and len(set(b.succs)) == 2 and set(t[1:]) == set(b.succs):
            arms.append((k, next(s for s in b.succs if s not in body)))
        elif t not in (('jmp', inside[0]), ('fall', inside[0])) or len(b.succs) != 1:
            return None
        chain.append(k); k = inside[0]
    if (k != hdr or set(chain) != body or chain[-1] != latch or len(arms) != 2 or arms[0][0] != hdr or
            any(s < 0 or s >= len(blocks) for _, s in arms)):
        return None
    (_, miss), (match, hit) = arms
    if miss == hit or not _owns_miss(blocks, miss, hdr, stop, dec.loop_of_hdr):
        return None
    m = getattr(dec.L, '_current_method', None); il = dec.L.il
    if not m or not 0 <= m.return_type < len(il.types):return None
    rt=il._closed_type_key(il.types[m.return_type])
    returned = rt != (1, 0)
    if returned and (not rt or not _null_or_tail(dec,blocks,miss,hdr,stop,hit,m,rt)):
        return None
    path = []; prev = match; k = hit
    while (k not in body and k != miss and k not in path and k not in stop and 0 <= k < len(blocks) and len(path) < 32):
        b = blocks[k]; t = b.term or ()
        if (b.consumed or b.is_entry or k in dec.loop_of_hdr or set(b.preds) != {prev}):
            return None
        path.append(k)
        if returned and k==hit:
            result=None  # the checked tail is a return statement already
            break
        if t == ('ret',) and not b.succs and b.ret == '' and b.insns and b.insns[-1].mnemonic == M.RET:
            result = 'return;'
            break
        if t == ('stop',) and not b.succs and b.insns:
            # An arbitrary indirect JMP/falloff has no terminal semantics.
            # The lifter already emitted the managed store for a direct
            # write-barrier tail; on normal completion its void caller ends.
            i = b.insns[-1]
            if not i.is_jmp_short_or_near or i.near_branch_target not in dec.L.rt_wbarrier:
                return None
            result = 'return;'; break
        if len(b.succs) != 1 or t not in (('jmp', b.succs[0]), ('fall', b.succs[0])):
            return None
        prev, k = k, b.succs[0]
    else:
        return None

    # Atomic commit: no block has been consumed and no code emitted until
    # the complete cycle, matching successor and terminal chain are proved.
    def guard(b, target):
        return b.cond if b.term[1] == target else '!(%s)' % b.cond

    h.consumed = True
    if h.insns:
        out.append('%sL_%x:' % (LBL, h.insns[0].ip))
    out.extend(('while (%s)' % guard(h, chain[1]), '{')); dec._brace_push('loop')
    dec._edge(hdr, chain[1], out)
    for n in chain[1:]:
        b = blocks[n]; b.consumed = True; out.extend(b.stmts)
        if n == match:
            out.extend(('if (%s)' % guard(b, hit), '{')); dec._brace_push('if')
            dec._edge(n, hit, out)
            for a in path:
                z = blocks[a]; z.consumed = True; out.extend(z.stmts)
                if z.succs:
                    dec._edge(a, z.succs[0], out)
            if result is not None:out.append(result)
            out.append('}'); dec._brace_pop(blocks, out, depth + 1)
        dec._edge(n, next(s for s in b.succs if s in body), out)
    out.append('}'); dec._brace_pop(blocks, out, depth)
    dec._edge(hdr, miss, out)
    if returned:blocks[miss].ret='null'
    return miss
