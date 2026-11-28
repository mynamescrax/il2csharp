"""Compare a bounded, explicit list of MethodDefs at two committed source revisions.

Each revision gets its own Python process. Verify the native instructions
before counting emitted-body differences. The retained report contains
hashes, counts and row IDs only; full lifts stay in a temporary directory.
"""
import argparse
from collections import Counter
import hashlib
import io
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import zipfile

from check_shift_methods import digest, serial

BINARY='163982a57e2e6e4c8f4558f6e968e9ba73e422d9b736cb4efef1e0674d5ab806'
METADATA='bd92f36e124ec3b236ef6bc3ead42eed3c322b15f403ecdc078f7c8dee5c75e1'


def _ids(text):
    rows=[int(n,0) for n in text.split()]
    if not 1<=len(rows)<=4096 or min(rows)<0 or len(set(rows))!=len(rows):
        raise ValueError('expected 1..4096 distinct nonnegative MethodDef rows')
    return sorted(rows)


def _counts(rows):
    counts=Counter();addresses=set()
    for r in rows:
        body=r['body'];text='\n'.join(body)
        marked=re.findall(r'\bsub_([0-9a-f]+)\s*/\*shared body,',text)
        counts['rows']+=1;counts['lines']+=len(body);counts['return_only']+=int(body==['return;'])
        counts['shared_markers']+=len(marked);addresses.update(marked)
        counts['untyped_locals']+=len(re.findall(r'\bobject\s+obj\d+\b',text));counts['unknown']+=len(re.findall(r'\bunknown\b',text))
    counts['shared_addresses']=len(addresses)
    return dict(counts)


def compare(ids,before,after):
    def index(rows):
        m={r['mi']:r for r in rows}
        if len(m)!=len(rows) or set(m)!=set(ids):raise ValueError('decoded row inventory differs from selection')
        return m
    a,b=index(before),index(after);changed=[];watch=[];h=hashlib.sha256()
    for k in sorted(ids):
        p,q=a[k],b[k];keys=('type','name','return','params','va','asm')
        if any(p.get(n)!=q.get(n) for n in keys):raise ValueError(f'native identity or instructions changed at MethodDef {k}')
        h.update(json.dumps([k,*[p[n] for n in keys]],ensure_ascii=True,separators=(',',':')).encode('ascii')+b'\n')
        if p['body']!=q['body']:
            changed.append(k);old,new=_counts([p]),_counts([q]);more={name:new[name]-old[name] for name in ('unknown','untyped_locals','shared_markers','return_only') if new[name]>old[name]}
            if more:watch.append(dict(mi=k,increases=more))
    return dict(before=_counts(before),after=_counts(after),different=changed,review_increases=watch,native_id_sha256=h.hexdigest(),rows=sorted(ids))


def _sha(root,rev):
    if not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_./-]{0,150}',rev):raise ValueError('expected a commit SHA or branch name')
    return subprocess.check_output(['git','rev-parse','--verify',rev+'^{commit}'],cwd=root,text=True).strip()


def lift(root,tmp,sha,ids,binary,metadata):
    path=tmp/sha;path.mkdir();raw=subprocess.check_output(['git','archive','--format=zip',sha,'il2cpp','il2csharp.py'],cwd=root)
    with zipfile.ZipFile(io.BytesIO(raw)) as z:z.extractall(path)
    report=path/'selected.json';env=dict(os.environ,PYTHONHASHSEED='0',DOTNET_ADD_GLOBAL_TOOLS_TO_PATH='false',DOTNET_PROCESSOR_COUNT='1')
    subprocess.run([sys.executable,str(root/'tools/inspect_methods.py'),'--source',str(path),'--metadata',str(metadata),
        '--binary',str(binary),'--mi',*map(str,ids),'--save',str(report)],cwd=root,env=env,check=True)
    return json.loads(report.read_text('utf8'))


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--before',required=True);ap.add_argument('--after',default='HEAD')
    ap.add_argument('--binary',required=True,type=Path);ap.add_argument('--metadata',required=True,type=Path)
    grp=ap.add_mutually_exclusive_group(required=True);grp.add_argument('--selection',type=Path);grp.add_argument('--mi',nargs='+')
    ap.add_argument('--save',type=Path,help='write the aggregate report without native or emitted code')
    args=ap.parse_args();root=Path(__file__).resolve().parents[1];b=args.binary.resolve();m=args.metadata.resolve()
    if digest(b)!=BINARY or digest(m)!=METADATA:ap.error('requires the matching second Windows x64/v31 Shift fixture')
    ids=_ids(args.selection.read_text('ascii') if args.selection else ' '.join(args.mi));before=_sha(root,args.before);after=_sha(root,args.after)
    if before==after:ap.error('specify two different commits')
    folder=root/'work';folder.mkdir(exist_ok=True)
    with serial(folder/'shift_method_checks'), tempfile.TemporaryDirectory(prefix='paired-',dir=folder) as t:
        a=lift(root,Path(t),before,ids,b,m);z=lift(root,Path(t),after,ids,b,m)
        result=compare(ids,a,z);result.update(before_sha=before,after_sha=after,binary_sha256=BINARY,metadata_sha256=METADATA,pythonhashseed=0)
    print(json.dumps({k:v for k,v in result.items() if k!='rows'},indent=2))
    if args.save:args.save.write_text(json.dumps(result,indent=2)+'\n',encoding='utf8')


if __name__=='__main__':main()
