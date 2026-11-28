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
    if (not m or not 0 <= m.return_type < len(il.types) or il._closed_type_key(il.types[m.return_type]) != (1, 0)):
        return None
    path = []; prev = match; k = hit
    while (k not in body and k != miss and k not in path and k not in stop and 0 <= k < len(blocks) and len(path) < 32):
        b = blocks[k]; t = b.term or ()
        if (b.consumed or b.is_entry or k in dec.loop_of_hdr or set(b.preds) != {prev}):
            return None
        path.append(k)
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
            out.extend((result, '}')); dec._brace_pop(blocks, out, depth + 1)
        dec._edge(n, next(s for s in b.succs if s in body), out)
    out.append('}'); dec._brace_pop(blocks, out, depth)
    dec._edge(hdr, miss, out)
    return miss
