"""Replay a bounded list of compiled behavior gates on an archived source SHA.

This measures the tests selected by the manifest, not all methods or the
whole assembly. A gate may cover several callers. Its failure can precede
C# execution; keep that distinct from a demonstrated runtime mismatch.
"""
import argparse
from collections import Counter
import io
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time
import zipfile

from check_shift_methods import digest,serial
from compare_shift_sample import BINARY,METADATA,_sha


def gates(text):
    rows=[]
    for line in text.splitlines():
        line=line.strip()
        if not line or line.startswith('#'):continue
        parts=line.split()
        if (len(parts)!=3 or parts[0] not in ('whole','slice','variant') or not re.fullmatch(r'\d+(?:,\d+)*',parts[1]) or
                not re.fullmatch(r'tests/test_game_\w+\.py::test_\w+',parts[2])):raise ValueError('invalid gate: '+line)
        rows.append((parts[0],list(map(int,parts[1].split(','))),parts[2]))
    if not 1<=len(rows)<=128 or len({row[2] for row in rows})!=len(rows):raise ValueError('expected 1..128 unique tests')
    return rows


def classify(code,log):
    last=log.strip().splitlines()[-1:] or [''];line=last[0]
    if code==0 and re.fullmatch(r'1 passed in [\d.]+s(?: \([\d:]+\))?',line):return 'pass'
    if re.search(r'\berror CS\d{4}:',log):return 'C# compile failure'
    if 'Unhandled exception.' in log:return 'C# runtime mismatch'
    if code and re.search(r'^E\s+assert ',log,re.M):return 'pre-run assertion'
    if (code==1 and 'dotnet_case.py:' not in log and re.search(r'tests[/\\]test_game_\w+\.py:\d+: in test_',log) and
            re.search(r'^E\s+(?:ValueError: substring not found|StopIteration)\s*$',log,re.M)):return 'pre-run extraction'
    return 'other (inspect log)'


def archive(root,sha,paths,dest):
    raw=subprocess.check_output(['git','archive','--format=zip',sha,*paths],cwd=root)
    with zipfile.ZipFile(io.BytesIO(raw)) as z:z.extractall(dest)


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--source',required=True);ap.add_argument('--gates-at',default='HEAD');ap.add_argument('--selection',type=Path,required=True)
    ap.add_argument('--minutes',type=float,help='time budget, checked between tests');ap.add_argument('--fresh',action='store_true');args=ap.parse_args()
    paths=[os.environ.get('IL2CSHARP_'+v) for v in ('BINARY','METADATA')]
    if not all(paths) or [digest(Path(x)) for x in paths]!=[BINARY,METADATA]:ap.error('set IL2CSHARP_BINARY and IL2CSHARP_METADATA to the matching second Shift pair')
    rows=gates(args.selection.read_text('utf8'));root=Path(__file__).resolve().parents[1];source=_sha(root,args.source);tests=_sha(root,args.gates_at)
    identity=digest(args.selection);out=root/'work'/'shift_gate_replays'/(source[:12]+'-'+tests[:12]+'-'+identity[:10]);out.mkdir(parents=True,exist_ok=True);report=out/'summary.json'
    with serial(root/'work'/'shift_method_checks'), tempfile.TemporaryDirectory(prefix='replay-',dir=out) as tmp:
        t=Path(tmp);archive(root,source,['il2cpp','il2csharp.py','tools','pytest.ini'],t);archive(root,tests,['tests'],t)
        env=dict(os.environ,PYTHONHASHSEED='0',PYTHONPATH=str(t),PYTEST_ADDOPTS='',DOTNET_ADD_GLOBAL_TOOLS_TO_PATH='false',DOTNET_PROCESSOR_COUNT='1',MSBUILDDISABLENODEREUSE='1',UseSharedCompilation='false',IL2CSHARP_BINARY=str(Path(paths[0]).resolve()),IL2CSHARP_METADATA=str(Path(paths[1]).resolve()))
        res={};header=dict(source=source,gates_at=tests,selection_sha256=identity,binary_sha256=BINARY,metadata_sha256=METADATA)
        if not args.fresh and report.exists():
            old=json.loads(report.read_text('utf8'))
            if all(old.get(k)==v for k,v in header.items()):res=old['results']
        start=time.monotonic()
        for label,mis,node in rows:
            if node in res and res[node]['result']!='other (inspect log)':continue
            if args.minutes is not None and time.monotonic()-start>=60*args.minutes:break
            log=out/(node.split('/')[1].replace('::','--')+'.log')
            with log.open('w',encoding='utf8') as f:
                run=subprocess.run([sys.executable,'-m','pytest','-q','--tb=short',node],cwd=t,env=env,stdout=f,stderr=subprocess.STDOUT)
            text=log.read_text('utf8',errors='replace');result=classify(run.returncode,text);res[node]=dict(result=result,scope=label,methods=mis,code=run.returncode)
            print(f'{node}: {result}',flush=True);draft=report.with_suffix('.tmp');draft.write_text(json.dumps(dict(header,results=res),indent=2)+'\n',encoding='utf8');draft.replace(report)
    print(f'{len(res)}/{len(rows)} gates; {dict(Counter(r["result"] for r in res.values()))}; {report}')
    # Expected old-source mismatches are measurements, not runner errors.
    return 0 if len(res)==len(rows) and all(r['result']!='other (inspect log)' for r in res.values()) else 1


if __name__=='__main__':raise SystemExit(main())
