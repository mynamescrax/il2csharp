"""The mark-only half of the exported reference-store operation on Win64."""
from il2cpp.equivalent_binary import _amd64,_writable


def _direct(b,p):
    seen=set()
    for _ in range(4):
        if p in seen or not b.is_exec_va(p):return None
        seen.add(p);code=b.read(p,5) or b''
        if len(code)!=5:return None
        if code[0]!=0xe9:return p
        p+=5+int.from_bytes(code[1:],'little',signed=True)
    return None


def mark_only(il,target):
    b=il.bin
    if not _amd64(b):return False
    exports=[v for v,n in b.exports.items() if n=='il2cpp_gc_wbarrier_set_field']
    if len(exports)!=1:return False
    # C ABI (owner,slot,value) -> store(slot,value). Only two register
    # moves before the direct tail. The next routine stores that exact
    # qword and dispatches its residual bookkeeping to the checked leaf.
    entry=_direct(b,exports[0]);end=_direct(b,target)
    if entry is None or end is None:return False
    raw=b.read(entry,11) or b''
    if len(raw)!=11 or raw[:7]!=bytes.fromhex('488bca498bd0e9'):return False
    store=_direct(b,entry+11+int.from_bytes(raw[7:],'little',signed=True))
    if store is None:return False
    raw=b.read(store,8) or b''
    if len(raw)!=8 or raw[:4]!=bytes.fromhex('488911e9') or _direct(b,store+8+int.from_bytes(raw[4:],'little',signed=True))!=end:return False
    # The only write is the atomic card-table update. Slot address bits
    # select a word in an image-owned table. Neither RCX nor RDX is ever
    # dereferenced as the managed field. Both exits and the retry are fixed.
    seq=b.read(end,66) or b''
    middle=bytes.fromhex('004c8bc1743549c1e80c488d0d')
    tail=bytes.fromhex('4181e0ffff1f00 418bc0 48c1e806 4183e03f 488d14c1 0f0d0a 488b02 488bc8 4c0fabc1 f0480fb10a 75ef c3')
    if (len(seq)!=66 or seq[:2]!=b'\x83\x3d' or seq[6:19]!=middle or seq[23:]!=tail):return False
    flag=end+7+int.from_bytes(seq[2:6],'little',signed=True);cards=end+23+int.from_bytes(seq[19:23],'little',signed=True)
    return bool(not cards%8 and _writable(b,flag,4) and _writable(b,cards,(1<<21)//8) and not (cards<flag+4 and flag<cards+(1<<21)//8))
