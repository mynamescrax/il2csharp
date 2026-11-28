"""Certify a shrink-wrapped GPR save interval around a reference factory.

The append suffix lives in the root frame again. Restores between the call
and TEST RAX do not change the factory result. Witness both ends of the
child interval using the chained unwind record, not the register spelling.
"""
from bisect import bisect_left
from struct import pack
from il2cpp.array_origin import _INFO,_WRITES,_reachable
from il2cpp.prelude import HAVE_ICED
from il2cpp.stack_local_frame import _epilogue,_saves,_slot_move
from il2cpp.text import sdisp

if HAVE_ICED:
    from iced_x86 import Mnemonic as M,OpKind as K,Register as R,RegisterExt as RX,MemorySizeExt as MS


def restored_frame(il,m,s,pred,succ,append):
    if not HAVE_ICED or any(i.next_ip!=z.ip for i,z in zip(s,s[1:])):return None
    image=il.bin.image_base;idx=bisect_left(il._eh4_begins,m.addr-image);rows=il._eh4_entries[idx:idx+3]
    if len(rows)!=3:return None
    root,child,rest=rows
    if root[0]+image!=m.addr or root[1]!=child[0] or child[1]!=rest[0] or rest[0]+image!=append or rest[1]+image!=s[-1].next_ip:return None
    tail=pack('<III',*root)
    if il.bin.read(image+rest[2],16)!=b'\x21\x00\x00\x00'+tail:return None
    ui=image+child[2];h=il.bin.read(ui,4) or b''
    if len(h)!=4 or h[0]!=0x21 or h[3] or h[2]!=4 or il.bin.read(ui+12,12)!=tail:return None
    alt=il.bin.read(ui+4,8) or b'';rh=il.bin.read(image+root[2],4) or b''
    k=next((n for n,i in enumerate(s[:16]) if i.mnemonic==M.SUB and i.op0_register==R.RSP),None)
    if k is None or len(rh)!=4 or rh[0]!=1 or rh[3] or len(alt)!=8:return None
    frame=_saves(s,k,il.bin.read(image+root[2],4+2*rh[2]) or b'')
    if not frame or frame[5]:return None
    size,depth,spans,pushed,moves,_=frame
    middle=[i for i in s if child[0]+image<=i.ip<append];starts={i.ip:i for i in s}
    if len(middle)<8 or middle[0].ip!=child[0]+image or middle[-1].next_ip!=append or not middle[-5].is_call_near:return None
    origins=pred[middle[0].ip]
    if len(origins)!=1 or starts[origins[0]].next_ip!=middle[0].ip:return None
    if (any(pred[z.ip]!=[a.ip] for a,z in zip(middle[-5:],middle[-4:])) or
            any(i.has_segment_prefix or i.has_lock_prefix or i.memory_index!=R.NONE for i in middle)):return None
    saved=tuple(_slot_move(i) for i in middle[:2]);loaded=tuple(_slot_move(i,load=True) for i in middle[-4:-2]);regset={*pushed,*[r for r,o,w in moves]}
    if (None in saved or None in loaded or set(saved)!=set(loaded) or len(set(saved))!=2 or pred[middle[1].ip]!=[middle[0].ip] or
            h[1]!=middle[1].next_ip-middle[0].ip):return None
    for j,i in enumerate(middle[:2]):
        r,off,width=saved[j];ui=4*(1-j)
        if (width!=8 or r in regset or r in (R.RSP,R.RAX,R.RCX,R.RDX,R.R8,R.R9) or not depth+8<=off<=depth+32 or off%8 or
                any(o<off+8 and off<o+w for o,w in spans) or
                alt[ui:ui+4]!=bytes((i.next_ip-middle[0].ip,RX.number(r)*16+4))+int(off//8).to_bytes(2,'little')):return None
    if saved[0][0]==saved[1][0] or saved[0][1]==saved[1][1]:return None
    inside={i.ip for i in middle}
    if any(any(p not in inside for p in pred[i.ip]) for i in middle[1:]) or any(any(q not in inside for q in succ[i.ip]) for i in middle[:-1]):return None
    body=s[k+1:];rets=[j for j,i in enumerate(body) if i.mnemonic==M.RET]
    if len(rets)!=1:return None
    j=rets[0];r=body[j];ep=_epilogue(body,j,size,pushed,moves)
    if ep is None or r.op_count or r.stack_pointer_increment!=8 or body[ep].ip<append:return None
    epi=body[ep:j+1]
    if any(pred[z.ip]!=[a.ip] for a,z in zip(epi,epi[1:])):return None
    restores={i.ip for i in middle[-4:-2]};safe={*(i.ip for i in middle[:2]),*restores,*(i.ip for i in epi)}
    affected=set(saved);reserved=(*spans,(depth,8),*((o,w) for _,o,w in saved));nonvol={r for r,_,_ in affected}
    for i in body:
        if i.ip in safe:continue
        if (i.memory_base==R.ESP or i.memory_index in (R.RSP,R.ESP) or i.stack_pointer_increment and not i.is_call_near or
                any(i.op_kind(j)==K.REGISTER and RX.full_register(i.op_register(j))==R.RSP for j in range(i.op_count))):return None
        if any(u.access in _WRITES and RX.full_register(u.register) in {R.RBX,R.RBP,R.RSI,R.RDI,R.R12,R.R13,R.R14,R.R15} - (regset|nonvol) for u in _INFO.info(i).used_registers()):return None
        if i.memory_base==R.RSP:
            o=sdisp(i.memory_displacement);w=MS.size(i.memory_size)
            if not w or i.memory_index!=R.NONE or i.has_segment_prefix or any(a<o+w and o<a+n for a,n in reserved):return None
        if i.ip not in inside and any(u.access in _WRITES and RX.full_register(u.register) in nonvol for u in _INFO.info(i).used_registers()):return None
    return (size,depth,spans),restores
