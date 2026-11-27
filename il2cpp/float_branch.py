"""Scalar SSE CF/ZF comparisons for a branch that includes unordered.

COMIS[SD] sets CF=ZF=1 for unordered: JB is not C# `<`, and JBE is
not `<=`. Compare once; keep the complement Boolean so that inverting the
edge cannot silently turn it back into an ordered relation.
"""
import re

from il2cpp.prelude import HAVE_ICED
if HAVE_ICED:
    from iced_x86 import Mnemonic as M, OpKind as K

_LITERAL=re.compile(r'-?(?:\d+(?:\.\d*)?|\.\d+)(?:e[+-]?\d+)?[fd]?$',re.I)


def unordered_bound(compare,jump,setter,left,right):
    if (not HAVE_ICED or jump.mnemonic not in (M.JB,M.JBE) or compare.mnemonic!=setter or compare.next_ip!=jump.ip or
            setter not in (M.COMISS,M.UCOMISS,M.COMISD,M.UCOMISD) or compare.op0_kind!=K.REGISTER):return None
    te=12 if setter in (M.COMISS,M.UCOMISS) else 13
    for e in (left,right):
        if not e or e._unk or e.kind!='float' or not e.text or getattr(e,'_slice',None) or getattr(e,'_parts',None):return None
        if e.ty:
            if e.ty[1]&(1<<29) or (e.ty[1]>>16)&0xff!=te:return None
        elif not _LITERAL.fullmatch(e.text) or (te==12)!=e.text.lower().endswith('f'):return None
    op='>' if jump.mnemonic==M.JBE else '>='
    return f'(({left.text}) {op} ({right.text})) == false'
