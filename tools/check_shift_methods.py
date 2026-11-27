"""Run the second Shift build's method tests serially, one process per module.

From the repository root, set IL2CSHARP_BINARY and IL2CSHARP_METADATA, then
run `python tools/check_shift_methods.py`. Results and per-module logs stay
under work/. Re-running resumes successful modules at the same clean SHA.
"""
import argparse
import ast
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time


def digest(path):
    with path.open('rb') as f:
        h=hashlib.sha256()
        for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
        return h.hexdigest()


@contextmanager
def serial(folder):
    """OS-held lock: a stopped verification process cannot strand the lock."""
    folder.mkdir(parents=True,exist_ok=True)
    with (folder/'runner.lock').open('a+b') as handle:
        if not handle.tell():handle.write(b' ');handle.flush()
        handle.seek(0)
        if os.name=='nt':
            import msvcrt
            msvcrt.locking(handle.fileno(),msvcrt.LK_NBLCK,1)
        else:
            import fcntl
            fcntl.flock(handle.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        yield


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--fresh',action='store_true');p.add_argument('--minutes',type=float,default=None,help='stop between modules after this many minutes');args=p.parse_args()
    root=Path(__file__).resolve().parents[1]
    def git(*words):return subprocess.check_output(['git',*words],cwd=root,text=True).strip()
    sha=git('rev-parse','HEAD');env=os.environ.copy()
    for name,expected_hash in [('BINARY','163982a57e2e6e4c8f4558f6e968e9ba73e422d9b736cb4efef1e0674d5ab806'),('METADATA','bd92f36e124ec3b236ef6bc3ead42eed3c322b15f403ecdc078f7c8dee5c75e1')]:
        f=Path(env.get('IL2CSHARP_'+name,''));
        if not f.is_file() or digest(f)!=expected_hash:p.error(f'IL2CSHARP_{name} does not identify the matching second v31 build')
        env['IL2CSHARP_'+name]=str(f.resolve())
    # Never launch the SDK ourselves. The compiled gates set a per-test CLI
    # home, including for --version. No changes to PATH or machine settings.
    env.update(PYTHONHASHSEED='0',DOTNET_ADD_GLOBAL_TOOLS_TO_PATH='false',DOTNET_PROCESSOR_COUNT='1',
               MSBUILDDISABLENODEREUSE='1',UseSharedCompilation='false',PYTEST_ADDOPTS='')
    files=[f for f in sorted((root/'tests').glob('test_game_*.py')) if f.stem=='test_game_shift_shared_flags' or
           any(isinstance(n,ast.ImportFrom) and n.module=='test_game_shift_shared_flags' for n in ast.parse(f.read_text(encoding='utf8')).body)]
    if not {'test_game_gas_method','test_game_particle_method','test_game_shift_shared_flags'}<={f.stem for f in files}:p.error('missing required exact-build modules')
    dirty=bool(git('status','--porcelain'));tag=sha[:12]+('-dirty' if dirty else '')
    folder=root/'work'/'shift_method_checks'/tag;folder.mkdir(parents=True,exist_ok=True);report=folder/'summary.json'
    with serial(folder.parent):
        return check(root,git,sha,dirty,files,folder,report,env,args)


def check(root,git,sha,dirty,files,folder,report,env,args):
    selected=[f.name for f in files];rows={}
    if not args.fresh and not dirty and report.exists():
        old=json.loads(report.read_text(encoding='utf8'))
        if old.get('sha')==sha and old.get('selected')==selected and not old.get('dirty'):rows=old['modules']
    def checkpoint():
        data=dict(sha=sha,dirty=dirty,selected=selected,modules=rows);tmp=report.with_suffix('.tmp');tmp.write_text(json.dumps(data,indent=2)+'\n',encoding='utf8');tmp.replace(report)
    checkpoint()
    start=time.monotonic()
    for f in files:
        if rows.get(f.name,{}).get('ok'):continue
        if args.minutes is not None and time.monotonic()-start>=args.minutes*60:break
        t=time.monotonic();log=folder/(f.stem+'.log')
        with log.open('w',encoding='utf8') as output:
            run=subprocess.run([sys.executable,'-m','pytest','-q','--tb=short',f'tests/{f.name}'],cwd=root,env=env,stdout=output,stderr=subprocess.STDOUT)
        text=log.read_text(encoding='utf8',errors='replace').splitlines();summary=text[-1] if text else 'no summary'
        match=re.search(r'\b(\d+) passed\b',summary)
        ok=run.returncode==0 and re.fullmatch(r'\d+ passed in [\d.]+s(?: \([\d:]+\))?',summary) is not None
        if not dirty and (git('rev-parse','HEAD')!=sha or git('status','--porcelain')):
            raise SystemExit('checkout changed during verification; module was not checkpointed')
        rows[f.name]=dict(ok=ok,code=run.returncode,passed=int(match[1]) if match else 0,summary=summary,seconds=round(time.monotonic()-t,1))
        checkpoint()
        print(f'{f.name}: {summary}',flush=True)
    print(f'{sum(r["ok"] for r in rows.values())}/{len(files)} modules passed; {sum(r["passed"] for r in rows.values())} passing test cases. {report}')
    if any(not r['ok'] for r in rows.values()):return 1
    return 3 if len(rows)<len(files) else 0


if __name__=='__main__':raise SystemExit(main())
