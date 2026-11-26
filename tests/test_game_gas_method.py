"""Compile the complete emitted callback and execute every distinct branch."""
from pathlib import Path
import re

import pytest
from iced_x86 import Decoder

from dotnet_case import run_case
from il2cpp import Decompiler,Lifter
from il2cpp.aggregate_apply import application_sites
from il2cpp.emitter import Emitter
from test_game_shift_shared_flags import shift_runtime

pytestmark=pytest.mark.game


def test_whole_gas_callback(shift_runtime,tmp_path,monkeypatch):
    meta,il=shift_runtime;md=meta.methods[25375];td=meta.typedefs[md.declaring];out=tmp_path/'out'
    em=Emitter(il,str(out));em._emit_one_top(td,meta.images[md.image],td.name);assert em.failed==em.fallbacks==em.emit_failed==0
    src=next(out.rglob('GasCollisionSpawner.cs')).read_bytes().decode('utf8')
    method=re.search(r'^    private void OnParticleCollision\(GameObject other\)\r?\n.*?^    \}',src,re.M|re.S)[0]
    harness=Path(__file__).with_name('gas_method_case.cs').read_text('utf8');runner=tmp_path/'runner';runner.mkdir()
    (runner/'Program.cs').write_bytes((harness+'\n'+method+'\n}\n').encode())
    monkeypatch.setenv('DOTNET_PROCESSOR_COUNT','1');monkeypatch.setenv('MSBUILDDISABLENODEREUSE','1');monkeypatch.setenv('UseSharedCompilation','false')
    print(run_case(tmp_path,runner).strip())


def test_saved_arguments_decline_unproved_bytes(shift_runtime,monkeypatch):
    meta,il=shift_runtime;m=meta.methods[25375];d=Decompiler(Lifter(il));d.lift_method(m,meta.typedefs[m.declaring]);bs=d.L._blocks
    def plans():return application_sites(d.L,m,bs,d._pad_bids)[0]
    rpc=0x1806efcda;kill=0x1806efcfd;assert rpc in plans() and kill in plans()
    for ip,j in [(0x1806efcc7,-1),(0x1806efcd3,-1),(0x1806efcea,-1),(0x1806efcf0,-1)]:
        b,k=next((b,k) for b in bs for k,i in enumerate(b.insns) if i.ip==ip);i=b.insns[k]
        raw=bytearray(il.bin.read(ip,i.len));raw[j]^=1;changed=list(Decoder(64,bytes(raw),ip=ip));assert len(changed)==1 and changed[0].len==i.len
        with monkeypatch.context() as p:
            p.setattr(b,'insns',b.insns[:k]+changed+b.insns[k+1:]);actions=plans();assert rpc not in actions and kill not in actions
