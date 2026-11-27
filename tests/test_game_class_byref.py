import re
import pytest
from dotnet_case import run_case
from il2cpp import Decompiler,Lifter,Expr
from il2cpp.class_byref import byref_context
from il2cpp.emitter import Emitter
from test_game_shift_shared_flags import shift_runtime

pytestmark=pytest.mark.game


def test_rank_helpers_and_voice_cache_hit(shift_runtime,tmp_path):
    meta,il=shift_runtime;out=tmp_path/'out';em=Emitter(il,str(out));td=next(t for t in meta.typedefs if t.name=='EndlessGenerationManager')
    em._emit_one_top(td,meta.images[meta.methods[25164].image],td.name)
    text=next(out.rglob(td.name+'.cs')).read_text(encoding='utf8');members=[];names=[]
    for rva in ('6E4E10','6E4B90'):
        body=re.search(r'// RVA: 0x'+rva+r' VA:[^\n]*\n( +)internal int (\w+)\(Npc npc\)\n\1\{.*?^\1\}',text,re.S|re.M)
        assert body;members.append(body[0]);names.append(body[2])
    md=meta.methods[28420];lines=[];em.emit_method(md,meta.typedefs[md.declaring],lines,'    ');s='\n'.join(lines)
    hit=re.search(r'(float (\w+) = 0;).*?(if \(this.playerVolumes.TryGetValue\(username, ref \2\)\))\s*\{\s*\w+ = \2;',s,re.S);assert hit
    src='''using System;using System.Linq;using System.Collections.Generic;
var npc=new Npc();var c=new Case();
foreach(Func<Npc,int> f in new Func<Npc,int>[]{'''+','.join('c.'+x for x in names)+'''})foreach(var mode in new[]{"hit","zero","miss","null","destroyed","lookup fault","truth fault"}){
 var trace=new List<string>();var error=new ApplicationException();c.entertainmentRank=new();npc.entertainment=2;
 Npc.Eq=(a,b)=>{trace.Add("eq");if(b is not null)throw new Exception();if(mode=="truth fault")throw error;npc.entertainment=7;return a is null||mode=="destroyed";};
 c.entertainmentRank.Read=(int k,ref int v)=>{trace.Add("lookup");if(k!=7||v!=0)throw new Exception("wrong key/home");v=mode=="zero"?0:-19;if(mode=="lookup fault")throw error;return mode!="miss";};
 int value=0;Exception fault=null;try{value=f(mode=="null"?null:npc);}catch(Exception e){fault=e;}
 if((mode.EndsWith("fault")?!ReferenceEquals(error,fault):fault!=null||value!=(mode=="hit"?-19:mode=="zero"?0:int.MaxValue))||string.Join(',',trace)!=(mode is "null" or "destroyed" or "truth fault"?"eq":"eq,lookup"))throw new Exception(mode,fault);}
var vcase=new Voice();foreach(var name in new[]{"Ada","Bo"}){float got=name=="Ada"?0.375f:0.8125f;int calls=0;vcase.playerVolumes.Read=(string k,ref float v)=>{if(k!=name||v!=0||++calls!=1)throw new Exception();v=got;return true;};if(vcase.Hit(name)!=got||calls!=1)throw new Exception("cache hit");}
Console.WriteLine("two complete rank methods and volume cache-hit slice returned the written ref values");
class Npc{public int entertainment;public static Func<Npc,Npc,bool>Eq;public static bool operator ==(Npc a,Npc b)=>Eq(a,b);public static bool operator !=(Npc a,Npc b)=>!Eq(a,b);public override bool Equals(object x)=>ReferenceEquals(this,x);public override int GetHashCode()=>base.GetHashCode();}
delegate bool Reader<K,V>(K k,ref V v);class Cache<K,V>{public Reader<K,V> Read;public bool TryGetValue(K k,ref V v)=>Read(k,ref v);}class Case{public Cache<int,int> entertainmentRank;\n'''+ '\n'.join(members)+'\n}class Voice{public Cache<string,float> playerVolumes=new();public float Hit(string username){'+hit[1]+hit[3]+' return '+hit[2]+';throw new Exception("miss");}}'
    runner=tmp_path/'runner';runner.mkdir();(runner/'Program.cs').write_text(src,encoding='utf8');print(run_case(tmp_path,runner).strip())


@pytest.mark.parametrize('defect',['wrong MethodRef position','wrong owner','conflicting entry'])
def test_mixed_class_byref_needs_closed_signature_and_target(shift_runtime,monkeypatch,defect):
    meta,il=shift_runtime;d=Decompiler(Lifter(il));m=meta.methods[28420];s,_=d._decode(m);ins=next(i for i in s if i.near_branch_target==0x1815f7c90)
    f=next(meta.fields[j] for j in meta.type_fields(meta.typedefs[m.declaring]) if meta.fields[j].name=='playerVolumes');si=167684;mi=il.method_specs[si][0]
    slot=Expr('slot',None,'usage');slot._usg_idx=si;recv=Expr('cache',il.types[f.type],'obj');es=[recv,None,None,slot];probe=lambda:byref_context(d.L,ins,('generic',si),es)
    assert any(il._closed_type_key(ty)==(0x0c,1) for ty in probe().values())
    if defect=='wrong MethodRef position':es[2],es[3]=es[3],es[2]
    elif defect=='wrong owner':es[0]=Expr('wrong',(m.declaring,0x12<<16),'obj')
    else:monkeypatch.setitem(il._awaiter_spec_indices[mi],si,-1)
    assert not probe()
