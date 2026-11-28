import re
import pytest
from dotnet_case import run_case
from il2cpp.emitter import Emitter
from test_game_shift_shared_flags import shift_runtime

pytestmark=pytest.mark.game


def test_server_append_slice_after_factory(shift_runtime,tmp_path):
    meta,il=shift_runtime;m=meta.methods[27397];lines=[];Emitter(il,str(tmp_path/'out')).emit_method(m,meta.typedefs[m.declaring],lines,'    ')
    start=next(j for j,s in enumerate(lines) if ' = UnityEngine.Object.Instantiate<' in s);spawn=re.search(r' (\w+) = ',lines[start])[1];end=next(j for j in range(start+1,len(lines)) if lines[j].strip()=='return;')
    # Contiguous suffix, starting with the live return of the factory. Keep
    # item acquisition, both append arms (if present), sort and return intact.
    prog='''using System;using System.Linq;using System.Collections.Generic;using UnityEngine;
foreach(int cap in new[]{1,2})foreach(bool sort in new[]{false,true})foreach(string mode in new[]{"ok","null result","item","no list","no item","sort"}){
 var shelf=new Shelf();var old=shelf.products=new List<Transform>();var list=new List<Transform>(cap);var a=new Transform();var b=new Transform();list.Add(a);var spawn=new GameObject();int reads=0,sorts=0;var err=new ApplicationException();
 spawn.Read=()=>{reads++;shelf.products=mode=="no list"?null:list;if(mode=="item")throw err;return mode=="no item"?null:b;};shelf.Sort=()=>{sorts++;if(list.Count!=2)throw new Exception("early sort");if(mode=="sort")throw err;};var iter=list.GetEnumerator();Exception ex=null;
 try{shelf.Run(mode=="null result"?null:spawn,sort);}catch(Exception e){ex=e;}bool added=mode is "ok" or "no item" or "sort";bool invalid=false;try{iter.MoveNext();}catch(InvalidOperationException){invalid=true;}
 if(old.Count!=0||list.Count!=(added?2:1)||invalid!=added||reads!=(mode=="null result"?0:1)||sorts!=(sort&&added?1:0)||!ReferenceEquals(list[0],a)||added&&!ReferenceEquals(list[1],mode=="no item"?null:b)||
   (mode=="item"||mode=="sort"&&sort?!ReferenceEquals(ex,err):mode is "no list" or "null result"?ex is not NullReferenceException:ex!=null))throw new Exception(mode+"/"+cap,ex);
}
Console.WriteLine("contiguous server append suffix: old index, resize, getter-driven list replacement and late sort");
namespace UnityEngine{public class GameObject{public Func<Transform> Read;public Transform transform=>Read();}public class Transform{}}
class Shelf{public List<Transform> products;public Action Sort;public void AutoSort()=>Sort();public void Run(GameObject '''+spawn+',bool autoSort){\n'+'\n'.join(lines[start+1:end+1])+'\n}}'
    r=tmp_path/'r';r.mkdir();(r/'Program.cs').write_text(prog,encoding='utf8');print(run_case(tmp_path,r))


@pytest.mark.parametrize('bad',['wrong home','wrong register','clobber result','skip restore','shared entry','unwind offset','reenter first save'])
def test_save_interval_matches_the_unwind_parent_and_factory_return(shift_runtime,monkeypatch,bad):
    from il2cpp import Decompiler,Lifter
    from il2cpp.array_origin import _graph
    from il2cpp.split_restore import restored_frame
    from iced_x86 import Register as R
    from bisect import bisect_right
    meta,il=shift_runtime;m=meta.methods[27397];d=Decompiler(Lifter(il));d.lift_method(m,meta.typedefs[m.declaring]);s=[i for b in d.L._blocks for i in b.insns]
    def proof():
        g=_graph(il,s,chained=True);return restored_frame(il,m,s,*g,0x1805b5f23) if g else None
    assert proof();ip={'wrong home':0x1805b5f10,'wrong register':0x1805b5f15,'clobber result':0x1805b5f10,'skip restore':0x1805b5ef7,'shared entry':0x1805b5ebb,'reenter first save':0x1805b5ef7}.get(bad)
    if ip:
        j=next(j for j,i in enumerate(s) if i.ip==ip);i=s[j].copy()
        if bad=='wrong home':i.memory_displacement=0x40
        elif bad=='wrong register':i.op0_register=R.RDI
        elif bad=='clobber result':i.op0_register=R.RAX
        elif bad=='skip restore':i.near_branch64=0x1805b5f1a
        elif bad=='reenter first save':i.near_branch64=0x1805b5ec1
        else:i.near_branch64=0x1805b5ec6
        s[j]=i
    else:
        a=il._eh4_entries[bisect_right(il._eh4_begins,m.addr-il.bin.image_base)][2]+il.bin.image_base+4;read=il.bin.read
        monkeypatch.setattr(il.bin,'read',lambda p,n:read(p,n)[:2]+b'\x09'+read(p,n)[3:] if p==a and n==8 else read(p,n))
    assert not proof()
