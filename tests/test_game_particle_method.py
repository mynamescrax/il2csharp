"""Compile the *entire* emitted method, signature and both branches intact."""
from pathlib import Path
import re

import pytest

from dotnet_case import run_case
from il2cpp.emitter import Emitter
from test_game_shift_shared_flags import shift_runtime

pytestmark=pytest.mark.game


def test_whole_particle_collision_method(shift_runtime,tmp_path,monkeypatch):
    meta,il=shift_runtime;md=meta.methods[26545];td=meta.typedefs[md.declaring]
    out=tmp_path/'out';em=Emitter(il,str(out));em._emit_one_top(td,meta.images[md.image],td.name)
    assert em.failed==em.fallbacks==em.emit_failed==0
    text=next(out.rglob('ParticleCollisionSpawner.cs')).read_bytes().decode('utf8')
    method=re.search(r'^    private void OnParticleCollision\(GameObject other\)\r?\n.*?^    \}',text,re.M|re.S)[0]
    harness=Path(__file__).with_name('particle_method_case.cs').read_text('utf8')
    runner=tmp_path/'runner';runner.mkdir();(runner/'Program.cs').write_bytes((harness+'\n'+method+'\n}\n').encode('utf8'))
    monkeypatch.setenv('DOTNET_PROCESSOR_COUNT','1');monkeypatch.setenv('MSBUILDDISABLENODEREUSE','1');monkeypatch.setenv('UseSharedCompilation','false')
    print(run_case(tmp_path,runner).strip())


def test_spawn_proof_rejects_changed_arguments(shift_runtime,monkeypatch):
    from iced_x86 import Decoder
    from il2cpp import Decompiler,Lifter
    from il2cpp.aggregate_apply import application_sites
    meta,il=shift_runtime;m=meta.methods[26545];d=Decompiler(Lifter(il));d.lift_method(m,meta.typedefs[m.declaring]);bs=d.L._blocks
    plans=lambda:application_sites(d.L,m,bs,d._pad_bids)[0]
    sink=0x1805812b3;assert plans()[sink][0]=='apply'
    for addr,at,mask in [(0x1805812af,-1,4), # position tail repeats/overlaps XY
                         (0x1805811ed,-1,1), # saved rotation no longer from the echoed address
                         (0x180581299,-1,8), # callback home disagrees with 5th ABI position
                         (0x180581277,-4,8)]: # a different hidden lookup slot
        b,j=next((b,j) for b in bs for j,i in enumerate(b.insns) if i.ip==addr);i=b.insns[j];raw=bytearray(il.bin.read(addr,i.len));raw[at]^=mask
        changed=list(Decoder(64,bytes(raw),ip=addr));assert len(changed)==1 and changed[0].len==i.len
        with monkeypatch.context() as mp:
            mp.setattr(b,'insns',b.insns[:j]+changed+b.insns[j+1:]);assert sink not in plans()
