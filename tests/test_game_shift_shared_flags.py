"""Pins specific to the second Shift v31 build, independent of review84."""
import os

import pytest

from il2cpp import Decompiler, Lifter
from il2cpp.cli import _load_runtime
from tools.corpus_common import sha256


pytestmark = pytest.mark.game


_PUMP_CS = '''
class Pump : SynchronizationContext {
    public int Posts; private Action next;
    public override void Post(SendOrPostCallback action, object state) {
        if (next != null) throw new Exception("duplicate post");
        Posts++; next = () => action(state);
    }
    public void Drain() { var work = next; next = null; work(); }
}'''


@pytest.fixture(scope='module')
def shift_runtime():
    metadata, binary = [os.getenv('IL2CSHARP_' + name) for name in ('METADATA', 'BINARY')]
    if (not metadata or not binary or
            sha256(metadata) != 'bd92f36e124ec3b236ef6bc3ead42eed3c322b15f403ecdc078f7c8dee5c75e1' or
            sha256(binary) != '163982a57e2e6e4c8f4558f6e968e9ba73e422d9b736cb4efef1e0674d5ab806'):
        pytest.skip('requires the second Shift v31 build')
    return _load_runtime(metadata, binary, False)


@pytest.fixture(scope='module')
def body(shift_runtime):
    meta, il = shift_runtime
    dec = Decompiler(Lifter(il))

    def lift(owner, name, va=None):
        m, = (m for m in meta.methods if m.name == name and meta.typedefs[m.declaring].name == owner
              and (va is None or m.addr == va))
        return '\n'.join(dec.lift_method(m, meta.typedefs[m.declaring]))
    return lift


def test_shared_input_and_range(body):
    update = body('CraneController', 'Update')
    for key in 'WSAD':
        assert update.count(f'Input.GetKey(UnityEngine.KeyCode.{key})') == 1
    switch_tracks = body('AmbientMusicSystem', 'SwitchTracks')
    assert switch_tracks.count('Random.Range(0, this.ambientTracks.Length)') == 1


def test_simd_zero_does_not_override_the_branch(body):
    assert 'if (this.chasingNonPlayerObject)' in body('BabyDoll', 'GoToTarget')
    assert 'if (!this.DebugWSAD)' in body('DEMO_LegsAnim_RedirectExampleJoy', 'UpdateInputs')


def test_crane_speed_negation(body):
    update = body('CraneController', 'Update')
    assert '-this.speed * UnityEngine.Time.deltaTime' in update
    assert '^ (float2)' not in update


def test_scalar_timer_getters(body):
    for getter, field in [('get_InAirTime', 'GroundedTime'), ('get_StoppedTime', 'MovingTime')]:
        assert body('LegsAnimator', getter) == 'return -this.__field_%s;' % field


def test_fps_rate_uses_saved_module_across_conversion(body, tmp_path):
    import re
    from dotnet_case import run_case

    text = body('FPSController','UpdateLocalVisuals',0x1806dff00)
    # Compile the actual call sequence and both sides of the following
    # animation decision, including any evaluation between these operations.
    cut = re.search(r'this\.playerMan\.isRunning = true;\s+UnityEngine\.ParticleSystem\.EmissionModule (\w+) = '
                    r'this\.runParticles\.emission /\* shared getter \*/;\s+(\w+) = '
                    r'\(UnityEngine\.ParticleSystem\.MinMaxCurve\)13\.0f;\s+\1\.rateOverTime = \2;'
                    r'.*?this\.headbobAnim\.SetBool\("Walking", false\);',text,re.S)
    assert cut and re.search(r'UnityEngine\.ParticleSystem\.MinMaxCurve '+cut[2]+r';',text)
    runner=tmp_path/'runner'; runner.mkdir()
    (runner/'Program.cs').write_text('''using System;
using System.Collections.Generic;
using UnityEngine;
foreach (var mode in new[]{"ok","no bob","null","getter throws","conversion throws","setter throws"}) {
    var original=new ParticleSystem(); var replacement=new ParticleSystem(); var log=new List<string>();
    var fps=new FPS { runParticles=mode=="null"?null:original, grounded=true };
    var expected=new ParticleSystem.MinMaxCurve(17,2.5f,new object(),new object(),-4.5f,13f);
    original.OnGet=()=>{log.Add("emission"); if(mode=="getter throws") throw new InvalidOperationException();};
    ParticleSystem.MinMaxCurve.Convert=f=>{
        log.Add("convert"); if(f!=13f || !fps.playerMan.isRunning) throw new Exception("order or value");
        fps.runParticles=replacement;
        if(mode=="conversion throws") throw new InvalidOperationException(); return expected;
    };
    original.Write=v=>{log.Add("set"); if(v!=expected) throw new Exception("lost curve bytes");
        if(mode=="setter throws") throw new InvalidOperationException();};
    replacement.OnGet=()=>throw new Exception("second getter"); replacement.Write=_=>throw new Exception("wrong module");
    PlayerPrefs.Read=(key,n)=>{if(key!="CamBobbing" || n!=1)throw new Exception("prefs");log.Add("prefs");return mode=="no bob"?0:1;};
    fps.headbobAnim.Set=(key,on)=>log.Add(key+"="+on);
    try {fps.Run();} catch(InvalidOperationException) when(mode.EndsWith("throws")) {log.Add("throw");}
    catch(NullReferenceException) when(mode=="null") {log.Add("null");}
    var want=mode switch {"ok"=>"emission;convert;set;prefs;Running=True;Walking=False", "no bob"=>"emission;convert;set;prefs;Walking=False",
        "null"=>"null", "getter throws"=>"emission;throw", "conversion throws"=>"emission;convert;throw", _=>"emission;convert;set;throw"};
    if(string.Join(";",log)!=want || !fps.playerMan.isRunning) throw new Exception(mode+": "+string.Join(";",log));
    Console.WriteLine(mode+": "+want);
}
namespace UnityEngine {
    class ParticleSystem {
        public Action OnGet; public Action<MinMaxCurve> Write;
        public EmissionModule emission {get{OnGet();return new EmissionModule(this);}}
        public struct EmissionModule { readonly ParticleSystem owner; public EmissionModule(ParticleSystem p){owner=p;}
            public MinMaxCurve rateOverTime {set=>owner.Write(value);} }
        public record struct MinMaxCurve(int Mode,float Multiplier,object Low,object High,float Min,float Max) {
            public static Func<float,MinMaxCurve> Convert; public static implicit operator MinMaxCurve(float f)=>Convert(f); }
    }
    static class PlayerPrefs {public static Func<string,int,int> Read; public static int GetInt(string k,int n)=>Read(k,n);}
    class Animator {public Action<string,bool> Set; public void SetBool(string k,bool b)=>Set(k,b);}
}
class Player { public bool isRunning; }
class FPS { public Player playerMan=new(); public ParticleSystem runParticles; public Animator headbobAnim=new(); public bool grounded;
    public void Run() {
''' + 'ParticleSystem.MinMaxCurve ' + cut[2] + ';\n' + cut[0] + '\n}\n}',encoding='utf-8')
    print(run_case(tmp_path,runner).strip())


def test_fps_conversion_declines_changed_receiver_or_copy(shift_runtime):
    from iced_x86 import Decoder
    from il2cpp.converted_module import conversion_uses
    from il2cpp.module_curve import fixed_frame

    meta,il=shift_runtime; md=meta.methods[25284]; lift=Lifter(il); dec=Decompiler(lift)
    dec.eh=il.eh_regions(md.addr); seq,skip=dec._decode(md)
    dec.entry_ip=md.addr; dec.last_ip=seq[-1].next_ip
    dec._flat_insns=seq; dec._flat_ip_idx={i.ip:j for j,i in enumerate(seq)}
    blocks,_=dec._make_blocks(seq,skip,dec._scan_jump_table_leaders(seq))
    frame=fixed_frame(lift,md,blocks,set(),immediate=True)
    assert frame==(0x79,0xc0,0xd8)
    key=0x1806e0122; plan=conversion_uses(lift,blocks,frame)[key]
    assert plan.value=='13.0f' and plan.homes==(8,-136,-168) and plan.setter==0x1806e0159
    for ip,code in [(0x1806e0136,'48894577'),     # spilled somewhere else
                    (0x1806e0146,'488d4d77'),     # setter takes another receiver
                    (0x1806e012f,'488d4d67'),     # sret buffer aliases saved module
                    (0x1806e014d,'0f104808'),     # upper half of argument is wrong
                    (0x1806e0133,'4531c9')]:      # wrong conversion MethodInfo slot
        b,j=next((b,j) for b in blocks for j,i in enumerate(b.insns) if i.ip==ip)
        original=b.insns[j]; new=Decoder(64,bytes.fromhex(code),ip=ip).decode()
        assert new.next_ip==original.next_ip; b.insns[j]=new
        assert key not in conversion_uses(lift,blocks,frame),hex(ip)
        b.insns[j]=original


def test_gas_spawner_uses_each_collision_intersection(body, tmp_path):
    from dotnet_case import run_case

    method = body('GasCollisionSpawner','KillCollidedParticles',0x1806ef780)
    assert 'sub_1808a5780' not in method and method.count('.intersection /* shared getter */') == 1
    runner=tmp_path/'runner'; runner.mkdir()
    (runner/'Program.cs').write_text('''using System;
using System.Collections.Generic;
using UnityEngine;
foreach (var (count,stop) in new[]{(0,"ok"),(1,"ok"),(2,"ok"),(3,"ok"),(3,"index"),(3,"getter"),(3,"helper")}) {
    var ps = new ParticleSystem(); var other = new GameObject(); var events = new List<int>(); var indices = new List<int>();
    int queried=0, kills=0; var spawner=new GasCollisionSpawner { ps=ps };
    ParticlePhysicsExtensions.Query=(p,o,list)=>{
        if (++queried!=1 || p!=ps || o!=other) throw new Exception("wrong collision query");
        for (int i=0;i<count;i++) list.Add(new ParticleCollisionEvent(i,new(i+1,i+10,-i-100),new(91,92,93),new(31,32,33)));
        return count;
    };
    List_1<ParticleCollisionEvent>.Read=i=>{ indices.Add(i); if (stop=="index" && i==1) throw new InvalidOperationException(stop); };
    ParticleCollisionEvent.Read=i=>{ events.Add(i); if (stop=="getter" && i==1) throw new InvalidOperationException(stop); };
    GasCollisionSpawner.Visit=(point,particles,alive,threshold)=>{
        int i=kills++;
        if(point!=new Vector3(i+1,i+10,-i-100) || particles!=ps.Buffer || particles[0].Hits!=i || alive!=2 || threshold!=0.1f)
            throw new Exception("position lanes, array identity or scalar arguments");
        if (stop=="helper" && i==1) throw new InvalidOperationException(stop);
        particles[0].Hits++;
    };
    bool threw=false;
    try { spawner.Run(other); } catch(InvalidOperationException ex) when (ex.Message==stop) {threw=true;}
    var nr=threw?2:count; var ng=stop=="index"?1:nr; var nk=(stop=="getter" || stop=="index")?1:nr;
    if(threw!=(stop!="ok") || queried!=1 || ps.MainReads!=1 || ps.SizeReads!=1 || ps.Fills!=1 || ps.Writes!=(threw?0:1) ||
       kills!=nk || indices.Count!=nr || events.Count!=ng) throw new Exception("wrong counts: "+stop);
    for(int i=0;i<indices.Count;i++) if(indices[i]!=i) throw new Exception("wrong index");
    for(int i=0;i<events.Count;i++) if(events[i]!=i) throw new Exception("wrong receiver");
    Console.WriteLine($"{count} events, {stop}: indices=[{string.Join(",",indices)}], intersections=[{string.Join(",",events)}], fills={ps.Fills}, writebacks={ps.Writes}");
}
namespace System.Collections.Generic {
    class List_1<T> : List<T> { public static Action<int> Read; public new T this[int i] { get { Read(i); return base[i]; } } }
}
namespace UnityEngine {
    class GameObject { }
    record struct Vector3(float x,float y,float z);
    record struct ParticleCollisionEvent(int Id,Vector3 Point,Vector3 Normal,Vector3 Velocity) {
        public static Action<int> Read; public Vector3 intersection { get { Read(Id); return Point; } }
    }
    static class ParticlePhysicsExtensions {
        public static Func<ParticleSystem,GameObject,List_1<ParticleCollisionEvent>,int> Query;
        public static int GetCollisionEvents(ParticleSystem p,GameObject o,List_1<ParticleCollisionEvent> list)=>Query(p,o,list);
    }
    class ParticleSystem {
        public struct Particle { public int Hits; }
        public struct MainModule { public ParticleSystem Owner; public int maxParticles {get { Owner.SizeReads++; return 8; }} }
        public int MainReads,SizeReads,Fills,Writes; public Particle[] Buffer;
        public MainModule main { get { MainReads++; return new MainModule {Owner=this}; } }
        public int GetParticles(Particle[] a) { if(a.Length!=8) throw new Exception("capacity"); Fills++; Buffer=a; return 2; }
        public void SetParticles(Particle[] a,int alive) { if(Buffer!=a || alive!=2) throw new Exception("wrong writeback"); Writes++; }
    }
}
class GasCollisionSpawner {
    public ParticleSystem ps; public static Action<Vector3,ParticleSystem.Particle[],int,float> Visit;
    static void KillClosestParticleAt(Vector3 pos,ParticleSystem.Particle[] particles,int alive,float threshold) => Visit(pos,particles,alive,threshold);
    public void Run(GameObject other) {
''' + method + '\n}\n}',encoding='utf-8')
    print(run_case(tmp_path,runner).strip())


def test_gas_spawner_searches_indexed_particle_positions(body, tmp_path):
    from dotnet_case import run_case

    method = body('GasCollisionSpawner','KillClosestParticleAt',0x1806ef5e0)
    assert 'sub_' not in method and method.count('.position /* shared getter */') == 1
    runner = tmp_path/'runner'; runner.mkdir()
    (runner/'Program.cs').write_text('''using System;
using System.Collections.Generic;
using UnityEngine;
using P=UnityEngine.ParticleSystem.Particle;
var hit=new Vector3(3,13,-7);
void Check(string name,Vector3[] points,int alive,float radius,int visits,int chosen,Type failure=null) {
    var arr=Array.ConvertAll(points, v=>new P { Point=v, Life=8f }); for(int i=0;i<arr.Length;i++) arr[i].Id=i;
    var reads=new List<int>(); int writes=0; Type thrown=null;
    P.Read=id=>{ reads.Add(id); if(name=="getter throws" && id==1) throw new InvalidOperationException(); };
    P.Write=(id,v)=>{ if(id!=chosen || BitConverter.SingleToInt32Bits(v)!=0 || ++writes!=1) throw new Exception("wrong lifetime setter"); };
    try { GasCollisionSpawner.Run(hit,arr,alive,radius); } catch(Exception ex) {thrown=ex.GetType();}
    if(thrown!=failure || reads.Count!=visits || writes!=(chosen<0?0:1)) throw new Exception(name+": "+thrown+", reads="+string.Join(",",reads)+", writes="+writes);
    for(int i=0;i<reads.Count;i++) if(reads[i]!=i) throw new Exception("repeated/wrong element");
    for(int i=0;i<arr.Length;i++) if(arr[i].Life!=(i==chosen?0f:8f) || arr[i].Point!=points[i]) throw new Exception("wrong array writeback");
    Console.WriteLine($"{name}: indices=[{string.Join(",",reads)}], cleared={chosen}");
}
// The first three miss on just x, y, or z. Element 3 is in range; the
// exact hit at index 4 must not replace it. The threshold-equal one misses.
var candidates=new[]{new Vector3(4,13,-7),new Vector3(3,16,-7),new Vector3(3,13,-10),new Vector3(3.25f,13.5f,-7.125f),hit};
Check("first in range",candidates,5,1,4,3);
Check("last live",candidates,4,1,4,3);
Check("no live match",candidates,3,1,3,-1);
Check("strict threshold",new[]{candidates[0]},1,1,1,-1);
Check("NaN",new[]{new Vector3(float.NaN,13,-7),hit},2,1,2,1);
Check("zero live",Array.Empty<Vector3>(),0,1,0,-1);
Check("bounds",new[]{candidates[0]},2,1,1,-1,typeof(IndexOutOfRangeException));
Check("getter throws",candidates,5,1,2,-1,typeof(InvalidOperationException));
GasCollisionSpawner.Run(hit,null,-1,1); // native alive guard precedes null check
try { GasCollisionSpawner.Run(hit,null,1,1); throw new Exception("missing null check"); } catch(NullReferenceException) { }
namespace UnityEngine {
    record struct Vector3(float x,float y,float z);
    class ParticleSystem { public struct Particle {
        public int Id; public Vector3 Point; public float Life; public static Action<int> Read; public static Action<int,float> Write;
        public Vector3 position { get {Read(Id); return Point;} } public float remainingLifetime { set { Write(Id,value); Life=value; } }
    } }
}
class GasCollisionSpawner { public static void Run(Vector3 hitPos,P[] particles,int alive,float threshold) {
''' + method + '\n}\n}', encoding='utf-8')
    print(run_case(tmp_path,runner).strip())


def test_particle_address_requires_matching_stride_guard_and_return_home(shift_runtime,monkeypatch):
    from iced_x86 import Decoder

    meta,il=shift_runtime; md=meta.methods[25377]
    for ip,code,marker in [
        (0x1806ef649,'4869d080000000','sub_1808a5780'),  # wrong element size
        (0x1806ef630,'3b5f1c','sub_1808a5780'),          # not the SZARRAY length
        (0x1806ef63e,'488d4c2430','sub_1808a5780'),      # output overwrites the hitPos spill
        (0x1806ef750,'4869c881000000','sub_18092f3f0'),  # different element at the store
    ]:
        dec=Decompiler(Lifter(il)); decode=dec._decode
        def changed(method):
            seq,skip=decode(method)
            j,=(k for k,i in enumerate(seq) if i.ip==ip)
            new=Decoder(64,bytes.fromhex(code),ip=ip).decode(); assert new.next_ip==seq[j].next_ip
            seq[j]=new
            return seq,skip
        monkeypatch.setattr(dec,'_decode',changed)
        text='\n'.join(dec.lift_method(md,meta.typedefs[md.declaring]))
        assert marker+'/*shared body,' in text


def test_collision_getter_requires_registered_producer_and_field(shift_runtime,monkeypatch):
    from iced_x86 import Decoder
    from types import SimpleNamespace as NS
    from il2cpp import Expr
    from il2cpp.copied_getter import copied_struct_getter

    meta,il=shift_runtime; lift=Lifter(il); md=meta.methods[25376]
    start=0x1806ef8ba; stop=0x1806ef909
    seq=list(Decoder(64,il.bin.read(start,stop-start),ip=start)); block=NS(insns=seq)
    spec=il.decode_slot(seq[0].ip_rel_memory_address)['idx']; event=il.candidate_return_type(('generic',spec))
    base=il.decode_slot(0x183c18e78)['type']; lift.out=NS(block=block); lift.rsp_delta=-0xd8
    echo=Expr('&t7',event,'ptr'); echo._stack_offset=lift.rsp_delta+0x78
    lift.slot_types={'t7':event}; lift.regs={'RAX':echo,'RBX':Expr('events',base,'obj')}
    lift._last_sret=0x1806ef8cc,echo
    result,receiver=Expr('&out',None,'ptr'),Expr('&copy',None,'ptr')
    result._stack_offset=lift.rsp_delta+0x40; receiver._stack_offset=lift.rsp_delta+0x50
    def proof():
        return copied_struct_getter(lift,seq[-1],[result,receiver,Expr('0'),None])
    assert proof()==(128004,'t7.intersection')
    for ip,hexbytes in [(0x1806ef8de,'0f108c2480000000'), # reads the wrong middle of the event
                        (0x1806ef8cc,'e800010000'),       # address doesn't match MethodSpec registration
                        (0x1806ef8e6,'488d4c2450')]:      # return buffer aliases the receiver
        j,=(j for j,i in enumerate(seq) if i.ip==ip); old=seq[j]
        seq[j]=Decoder(64,bytes.fromhex(hexbytes),ip=ip).decode();assert seq[j].next_ip==old.next_ip
        assert proof() is None
        seq[j]=old
    read=il.bin.read
    monkeypatch.setattr(il.bin,'read',lambda p,n:read(p,n).replace(b'\x8b\x42\x08',b'\x8b\x42\x04') if p==0x1808a5780 else read(p,n))
    assert proof() is None  # returning x,y,y isn't the Vector3 property


def test_particle_collision_spawner_reads_indexed_event(body,tmp_path):
    import re
    from dotnet_case import run_case

    lifted=body('ParticleCollisionSpawner','OnParticleCollision',0x180580f90)
    # A spill becomes dead once all consumers use typed event snapshots.
    arms=re.findall(r'((\w+) = (\w+)\[(\w+)\];\s+(?:(\w+) = \2;\s+)?UnityEngine\.Vector3 (\w+) = \2\.intersection /\* shared getter \*/;)',lifted)
    assert len(arms)==2 and lifted.count('.intersection /* shared getter */')==2
    members=[]
    for n,(code,event,collection,index,copy,point) in enumerate(arms):
        decl=re.search(r'UnityEngine\.ParticleCollisionEvent '+event+';',lifted)
        spill=re.search(r'object '+copy+r'(?: = 0f)?;',lifted) if copy else None
        assert decl and (not copy or spill)
        members.append(f'public static Vector3 Read{n}(Events {collection},int {index}) {{\n'+decl[0]+'\n'+(spill[0] if spill else '')+'\n'+code+'\nreturn '+point+';\n}')
    runner=tmp_path/'runner';runner.mkdir()
    (runner/'Program.cs').write_text('''using System;
using System.Collections.Generic;
using UnityEngine;
foreach (Func<Events,int,Vector3> read in new Func<Events,int,Vector3>[]{Case.Read0,Case.Read1}) {
    var values=new Events(); var log=new List<string>();
    var replacement=new ParticleCollisionEvent(new(101,102,103),new(201,202,203),new(301,302,303),null);
    values.Add(replacement); values.Add(new(new(7,-11,23),new(-3,5,9),new(41,42,43),()=>log.Add("intersection")));
    values.AfterRead=i=>{log.Add("index:"+i);values.Items[i]=replacement;};
    var p=read(values,1); if(p!=new Vector3(7,-11,23) || string.Join(";",log)!="index:1;intersection") throw new Exception("wrong field, receiver or index");
    Console.WriteLine($"{string.Join(";",log)} -> ({p.x},{p.y},{p.z})");
    try {read(values,2);throw new Exception("missing bounds check");} catch(ArgumentOutOfRangeException) { }
    values.Items[0]=new(default,default,default,()=>throw new InvalidOperationException());
    try {read(values,0);throw new Exception("missing getter failure");} catch(InvalidOperationException) { }
}
class Events {
    public List<ParticleCollisionEvent> Items=new(); public Action<int> AfterRead;
    public void Add(ParticleCollisionEvent e)=>Items.Add(e);
    public ParticleCollisionEvent this[int index] { get {var saved=Items[index]; AfterRead(index); return saved;} }
}
namespace UnityEngine {
    record struct Vector3(float x,float y,float z);
    record struct ParticleCollisionEvent(Vector3 Point,Vector3 Normal,Vector3 Velocity,Action OnRead) {
        public Vector3 intersection {get { OnRead(); return Point; } }
    }
}
class Case {
''' + '\n'.join(members)+'\n}',encoding='utf-8')
    print(run_case(tmp_path,runner).strip())


def test_particle_iterator_uses_original_emission_module(shift_runtime, tmp_path):
    import re
    from dotnet_case import run_case
    from il2cpp.emitter import Emitter

    meta, il = shift_runtime
    handler, = (td for td in meta.typedefs if (td.namespace, td.name) == ('PilotoStudio', 'ParticleHandler'))
    emitter = Emitter(il, str(tmp_path / 'out'))
    emitter._emit_one_top(handler, meta.images[meta.methods[28683].image], 'ParticleHandler')
    assert emitter.failed == emitter.fallbacks == emitter.emit_failed == 0
    src, = (tmp_path / 'out').rglob('ParticleHandler.cs')
    section = src.read_text(encoding='utf-8').split('// RVA: 0x638500 ', 1)[1]
    method = re.search(r'(?m)^( +)bool System\.Collections\.IEnumerator\.MoveNext\(\)\s*\{.*?^\1}',section,re.S)[0]
    assert 'sub_18088e4a0' not in method and method.count('.emission /* shared getter */') == 1
    runner = tmp_path / 'runner'; runner.mkdir()
    (runner / 'Program.cs').write_text('''using System;
using System.Collections;
using UnityEngine;
foreach (var mode in new[]{"normal","null","getter throws","setter throws"}) {
    var ps = new ParticleSystem(); var other = new ParticleSystem();
    var it = new Iterator { particleSystem = mode == "null" ? null : ps, duration = 1.75f };
    IEnumerator run = it;
    ps.OnGet = () => { it.particleSystem = other; if (mode == "getter throws") throw new InvalidOperationException("get"); };
    ps.FailSet = mode == "setter throws";
    if (!run.MoveNext() || run.Current is not WaitForSeconds wait || wait.Duration != 1.75f || ps.Gets != 0 || ps.Sets != 0)
        throw new Exception("initial move did not yield without touching emission");
    var result = "false";
    try { if (run.MoveNext()) throw new Exception("unexpected yield"); }
    catch (NullReferenceException) when (mode == "null") { result = "null"; }
    catch (InvalidOperationException ex) { result = ex.Message; }
    if (run.MoveNext() || !ReferenceEquals(wait,run.Current) || other.Gets != 0 || other.Sets != 0 ||
        (result,ps.Gets,ps.Sets) != (mode switch { "normal"=>"false", "getter throws"=>"get", "setter throws"=>"set", _=>"null" },
                                    mode == "null" ? 0 : 1, mode is "normal" or "setter throws" ? 1 : 0) ||
        ps.Last != (mode == "normal" ? 0f : 9f)) throw new Exception("wrong module, state, setter value, or count");
    Console.WriteLine($"{mode}: waited {wait.Duration}s, resume={result}, emission reads={ps.Gets}, writes={ps.Sets}");
}
namespace UnityEngine {
    record WaitForSeconds(float Duration);
    class ParticleSystem {
        public int Gets, Sets; public bool FailSet; public float Last=9f; public Action OnGet;
        public EmissionModule emission { get { ++Gets; OnGet?.Invoke(); return new EmissionModule(this); } }
        public struct EmissionModule {
            readonly ParticleSystem ps;
            public EmissionModule(ParticleSystem owner) { ps=owner; }
            public float rateOverTimeMultiplier { set { ps.Sets++; if (ps.FailSet) throw new InvalidOperationException("set"); ps.Last=value; } }
        }
    }
}
class Iterator : IEnumerator {
    int __1__state; object __2__current; public ParticleSystem particleSystem; public float duration;
    public object Current => __2__current; public void Reset() => throw new NotSupportedException();
''' + method + '\n}', encoding='utf-8')
    print(run_case(tmp_path,runner).strip())


def test_particle_module_consumers_preserve_type_and_evaluation(body, tmp_path):
    import re
    from dotnet_case import run_case

    scalar = body('GasCollisionSpawner','KillCollidedParticles',0x1806ef780)
    main = re.search(r'UnityEngine\.ParticleSystem\.MainModule (\w+) = this\.ps\.main /\* shared getter \*/;\s+'
                     r'int (\w+) = \1\.maxParticles;', scalar)
    assert main and scalar.count('.maxParticles') == 1
    sret = body('ThirdPersonManager','Rpc_ChangeGasPumpParticles',0x1805f21b0)
    # Each arm has one RAX module followed by one by-address MinMaxCurve
    # result. The two distinct native homes include RBP+0x20 and RBP-0x20.
    arms = re.findall(r'(UnityEngine\.ParticleSystem\.EmissionModule (\w+) = this\.gasPumpParticles\.emission /\* shared getter \*/;\s+'
                      r'(\w+) = \2;\s+(\w+) = \2\.rateOverTime;)',sret)
    assert arms and len(arms) == sret.count('.emission /* shared getter */') == sret.count('.rateOverTime;')
    copies = []
    for n,(arm,_,module,curve) in enumerate(arms):
        assert re.search(r'UnityEngine\.ParticleSystem\.EmissionModule '+module+r';',sret)
        assert re.search(r'UnityEngine\.ParticleSystem\.MinMaxCurve '+curve+r';',sret)
        copies.append(f'public int Curve{n}() {{ ParticleSystem.EmissionModule {module}; ParticleSystem.MinMaxCurve {curve};\n' +
                      arm + f'\nreturn {curve}.Value; }}')
    runner = tmp_path/'runner'; runner.mkdir()
    (runner/'Program.cs').write_text('''using System;
using UnityEngine;
var probe=new Probe(); if (probe.Size()!=37 || probe.ps.MainReads!=1 || probe.ps.SizeReads!=1) throw new Exception("scalar result");
int expected=0;
foreach(Func<int> read in new Func<int>[]{''' + ','.join('probe.Curve%d'%n for n in range(len(arms))) + '''}) {
    ++expected;
    if (read()!=13*expected || probe.gasPumpParticles.EmissionReads!=expected || probe.gasPumpParticles.CurveReads!=expected)
        throw new Exception("value-type receiver or sret replay");
}
Console.WriteLine($"MainModule.maxParticles read once; {expected} emission/curve slices each read once");
namespace UnityEngine {
    class ParticleSystem {
        public int MainReads,SizeReads,EmissionReads,CurveReads;
        public struct MainModule { public ParticleSystem ps; public int maxParticles => 37 * ++ps.SizeReads; }
        public struct EmissionModule { public ParticleSystem ps; public MinMaxCurve rateOverTime => new(13 * ++ps.CurveReads, 99); }
        public record struct MinMaxCurve(long First,long Second) { public int Value => (int)First; }
        public MainModule main { get { ++MainReads; return new() { ps=this }; } }
        public EmissionModule emission { get { ++EmissionReads; return new() { ps=this }; } }
    }
}
class Probe {
    public ParticleSystem ps = new(), gasPumpParticles = new();
    public int Size() {
''' + main[0] + f'\nreturn {main[2]};\n}}\n' + '\n'.join(copies) + '\n}',encoding='utf-8')
    print(run_case(tmp_path,runner).strip())


def test_inventory_gas_and_smoke_curves_use_spilled_modules(body, tmp_path):
    import re
    from dotnet_case import run_case

    update = body('InventoryManager','Update',0x1806f92a0)
    window = (
        r'UnityEngine\.ParticleSystem\.EmissionModule (\w+) = this\.%s\.emission /\* shared getter \*/;\s+'
        r'UnityEngine\.ParticleSystem\.MinMaxCurve (\w+) = \1\.rateOverTime;\s+'
        r'\2\.constant = 0f /\* shared implementation \*/;\s+\1\.rateOverTime = \2;')
    gas = re.search(window % 'gasPumpGasParticles', update)
    smoke = re.search(window % 'gasPumpSmokeParticles', update[gas.end():]) if gas else None
    assert gas and smoke and not update[gas.end():gas.end()+smoke.start()].strip()
    pair = update[gas.start():gas.end()+smoke.end()]
    # A different decision joins at 0x1806fda73: the >= arm supplies
    # zero; the other supplies ten. Compile the actual two emitted curve
    # sequences under that decision, leaving unrelated RPC/audio calls out.
    branch = re.search(r'if \(this\.gasPumpCurDistance >= (\w+)\)\s*\{', update)
    assert branch
    cond = branch[0].split('{')[0].strip()
    zero = re.search(window % 'gasPumpSmokeParticles',update[branch.end():])
    ten = re.search(window.replace('0f',r'10\.0f') % 'gasPumpSmokeParticles',update[branch.end():])
    assert zero and ten and zero.end() < ten.start() and re.search(
        r'}\s*else\s*{',update[branch.end()+zero.end():branch.end()+ten.start()])
    joined = f'public void Joined(float {branch[1]}) {{\n{cond} {{\n{zero[0]}\n}} else {{\n{ten[0]}\n}}\n}}'
    active = re.match(r'.*?}\s*else\s*{',update[branch.end():],re.S)
    assert active and 'constant = 35.0f /* shared implementation */;' in active[0]
    gas35 = update[branch.start():branch.end()] + active[0].rsplit('else',1)[0]
    runner = tmp_path / 'runner'; runner.mkdir()
    (runner / 'Program.cs').write_text('''using System;
using System.Collections.Generic;
using UnityEngine;
foreach (string stop in new[]{"ok","null","emission","curve","constant","write"}) {
    var log=new List<string>(); var old=new ParticleSystem(); var other=new ParticleSystem();
    var inv=new Inventory { gasPumpSmokeParticles=stop=="null" ? null : old };
    var before=new ParticleSystem.MinMaxCurve(2,-7.25f,new object(),new object(),8.5f,19f);
    old.Stored=before;
    old.Step = stage => {
        log.Add(stage); if(stage=="emission") inv.gasPumpSmokeParticles=other;
        if(stage==stop) throw new InvalidOperationException(stage);
    };
    ParticleSystem.MinMaxCurve.Edit=()=>old.Step("constant");
    try { inv.UpdateSlice(); } catch(NullReferenceException) when(stop=="null") {log.Add("null");}
    catch(InvalidOperationException ex) when(ex.Message==stop) {log.Add("throw");}
    var order=stop switch { "ok"=>"emission;curve;constant;write", "null"=>"null", "emission"=>"emission;throw",
        "curve"=>"emission;curve;throw", "constant"=>"emission;curve;constant;throw", _=>"emission;curve;constant;write;throw" };
    if(string.Join(";",log)!=order || other.Writes!=0 || old.Writes!=(stop=="ok"?1:0) ||
       old.Stored!=(stop=="ok"?before with { Max=0f }:before) || BitConverter.SingleToInt32Bits(old.Stored.Max)!=(stop=="ok"?0:BitConverter.SingleToInt32Bits(19f)))
        throw new Exception(stop+": "+string.Join(";",log));
    Console.WriteLine(stop+": "+order+"; writes to original="+old.Writes);
}
foreach (string stop in new[]{"ok","gas write throws","smoke null","smoke write throws"}) {
    var gas=new ParticleSystem(); var smoke=new ParticleSystem(); var unused=new ParticleSystem();
    var inv=new Inventory { gasPumpGasParticles=gas, gasPumpSmokeParticles=unused };
    var g=new ParticleSystem.MinMaxCurve(3,4,new object(),new object(),5,6);
    var s=new ParticleSystem.MinMaxCurve(7,8,new object(),new object(),9,10);
    gas.Stored=g; smoke.Stored=s; var log=new List<string>(); string current="";
    gas.Step = stage => {
        current="gas"; log.Add("g."+stage);
        if(stage=="emission") inv.gasPumpGasParticles=unused;
        if(stage=="write") {
            if(stop=="gas write throws") throw new InvalidOperationException();
            inv.gasPumpSmokeParticles=stop=="smoke null" ? null : smoke;
        }
    };
    smoke.Step = stage => {
        current="smoke"; log.Add("s."+stage);
        if(stage=="emission") inv.gasPumpSmokeParticles=unused;
        if(stage=="write" && stop=="smoke write throws") throw new InvalidOperationException();
    };
    unused.Step = _ => throw new Exception("stale or repeated module read");
    ParticleSystem.MinMaxCurve.Edit=()=>log.Add(current=="gas"?"g.constant":"s.constant");
    try { inv.UpdatePair(); } catch (InvalidOperationException) when (stop.EndsWith("throws")) {log.Add("throw");}
    catch (NullReferenceException) when (stop=="smoke null") {log.Add("null");}
    var expected="g.emission;g.curve;g.constant;g.write" + (stop switch {
        "gas write throws"=>";throw", "smoke null"=>";null", "smoke write throws"=>";s.emission;s.curve;s.constant;s.write;throw",
        _=>";s.emission;s.curve;s.constant;s.write" });
    if(string.Join(";",log)!=expected || gas.Writes!=(stop=="gas write throws"?0:1) || smoke.Writes!=(stop=="ok"?1:0) ||
       gas.Stored!=(gas.Writes==1?g with {Max=0f}:g) || smoke.Stored!=(smoke.Writes==1?s with {Max=0f}:s)) throw new Exception(stop+": "+string.Join(";",log));
    Console.WriteLine(stop+": "+expected+"; writes="+gas.Writes+","+smoke.Writes);
}
foreach (var distance in new[]{1f,2f,3f}) foreach (var stop in new[]{"ok","curve","constant","write"}) {
    var original=new ParticleSystem(); var replacement=new ParticleSystem();
    var inv=new Inventory { gasPumpSmokeParticles=original, gasPumpCurDistance=distance };
    var before=new ParticleSystem.MinMaxCurve(7,2.25f,new object(),new object(),-8f,13f); original.Stored=before;
    var log=new List<string>(); original.Step=stage=>{
        log.Add(stage); if(stage=="emission") inv.gasPumpSmokeParticles=replacement;
        if(stage==stop) throw new InvalidOperationException(stage);
    };
    replacement.Step=_=>throw new Exception("setter read a different module");
    ParticleSystem.MinMaxCurve.Edit=()=>original.Step("constant");
    try { inv.Joined(2f); } catch(InvalidOperationException ex) when(ex.Message==stop) {log.Add("throw");}
    float value=distance<2f?10f:0f;
    var expected=stop switch {"ok"=>"emission;curve;constant;write", "curve"=>"emission;curve;throw",
        "constant"=>"emission;curve;constant;throw", _=>"emission;curve;constant;write;throw"};
    if(string.Join(";",log)!=expected || original.Writes!=(stop=="ok"?1:0) || replacement.Writes!=0 ||
        original.Stored!=(stop=="ok"?before with {Max=value}:before)) throw new Exception("joined update: "+string.Join(";",log));
    if(stop=="ok") Console.WriteLine($"distance {distance}, threshold 2: {expected}; original constant={original.Stored.Max}, writes={original.Writes}");
}
foreach (string stop in new[]{"ok","null","curve","gas write","notification","smoke write"}) {
    var gas=new ParticleSystem(); var smoke=new ParticleSystem(); var decoy=new ParticleSystem();
    var g=new ParticleSystem.MinMaxCurve(1,11,new object(),new object(),-4,3);
    var s=new ParticleSystem.MinMaxCurve(2,-6,new object(),new object(),7,8); gas.Stored=g; smoke.Stored=s;
    var inv=new Inventory {gasPumpCurDistance=6,gasPumpGasParticles=stop=="null"?null:gas,gasPumpSmokeParticles=decoy};
    var log=new List<string>(); decoy.Step=_=>throw new Exception("wrong receiver");
    inv.OnDistanceSet=()=>inv.gasPumpGasParticles=decoy;
    gas.Step=stage=>{log.Add("g."+stage); if(stage=="emission") inv.gasPumpGasParticles=decoy;
        if((stage=="curve" && stop==stage) || (stage=="write" && stop=="gas write")) throw new InvalidOperationException(stop);};
    smoke.Step=stage=>{log.Add("s."+stage); if(stage=="write" && stop=="smoke write") throw new InvalidOperationException(stop);};
    ParticleSystem.MinMaxCurve.Edit=()=>log.Add("edit");
    inv.thirdPersonMan.Change=on=>{
        log.Add("notify"); if(!on || gas.Stored!=(g with {Max=35f}) || gas.Writes!=1) throw new Exception("late or incomplete gas write");
        if(stop=="notification") throw new InvalidOperationException(stop); inv.gasPumpSmokeParticles=smoke;
    };
    Time.Read=()=>{ log.Add("dt"); return 0.0625f; };
    inv.gasPumpShootSfx.Step=stage=>{log.Add("shoot."+stage); if(stage=="get") inv.gasPumpShootSfx=null;};
    inv.gasPumpEmptySfx.Step=stage=>{log.Add("empty."+stage); if(stage=="get") inv.gasPumpEmptySfx=null;};
    try { inv.Active(2f); } catch(InvalidOperationException ex) when(ex.Message==stop) {log.Add("throw");}
    catch(NullReferenceException) when(stop=="null") {log.Add("null");}
    string trace="g.emission;g.curve;edit;g.write;notify;shoot.get;dt;shoot.set;empty.get;dt;empty.set;s.emission;s.curve;edit;s.write";
    var expected=stop switch {"null"=>"null", "curve"=>"g.emission;g.curve;throw", "gas write"=>"g.emission;g.curve;edit;g.write;throw",
        "notification"=>trace.Split(";shoot.")[0]+";throw", "smoke write"=>trace+";throw", _=>trace};
    bool wroteGas=stop is "ok" or "notification" or "smoke write";
    if(string.Join(";",log)!=expected || inv.gasPumpCurDistance!=2f || gas.Stored!=(wroteGas?g with {Max=35f}:g) ||
        smoke.Stored!=(stop=="ok"?s with {Max=0f}:s) || gas.Writes!=(wroteGas?1:0) || smoke.Writes!=(stop=="ok"?1:0))
        throw new Exception(stop+": "+string.Join(";",log));
    Console.WriteLine($"35f gas arm [{stop}]: original constant={gas.Stored.Max}, writes={gas.Writes},{smoke.Writes}");
}
namespace UnityEngine {
    class ThirdPersonManager { public Action<bool> Change; public void ChangeGasPumpParticles(bool on)=>Change(on); }
    class AudioSource { public Action<string> Step; float stored=1f; public float volume {
        get { Step("get"); return stored; } set { Step("set"); stored=value; } } }
    static class Time { public static Func<float> Read; public static float deltaTime=>Read(); }
    static class Mathf { public static float Lerp(float a,float b,float t)=>a+(b-a)*Math.Clamp(t,0,1); }
    class ParticleSystem {
        public Action<string> Step; public int Writes; public MinMaxCurve Stored;
        public EmissionModule emission { get { Step("emission"); return new EmissionModule(this); } }
        public struct EmissionModule {
            readonly ParticleSystem owner; public EmissionModule(ParticleSystem p) {owner=p;}
            public MinMaxCurve rateOverTime { get { owner.Step("curve"); return owner.Stored; }
                set { owner.Step("write"); owner.Stored=value; ++owner.Writes; } }
        }
        public record struct MinMaxCurve(int Mode,float Multiplier,object CurveMin,object CurveMax,float Min,float Max) {
            public static Action Edit; public float constant { set { Edit(); Max=value; } }
        }
    }
}
class Inventory {
    public ParticleSystem gasPumpGasParticles, gasPumpSmokeParticles;
    public ThirdPersonManager thirdPersonMan=new(); public AudioSource gasPumpShootSfx=new(), gasPumpEmptySfx=new();
    public Action OnDistanceSet; float dist;
    public float gasPumpCurDistance {get=>dist;set { dist=value; OnDistanceSet?.Invoke(); }}
    public void UpdateSlice() {
''' + smoke[0] + '\n}\npublic void UpdatePair() {\n' + pair + '\n}\n' + joined +
        f'\npublic void Active(float {branch[1]}) {{\n' + gas35 + '\n}\n}',encoding='utf-8')
    print(run_case(tmp_path,runner).strip())


@pytest.mark.parametrize('site,code', [
    (0x1806fd864, '488d55b8'),       # first getter borrows the other arm's module
    (0x1806fd8a7, '488d4db8'),       # first arm sends the other receiver to the join
    (0x1806fda68, '488d4da8'),       # fallthrough sends the first receiver
    (0x1806fda80, '0f29442470'),     # shared store copies the low half twice
    (0x1806fda8a, 'f30f10b5a8ffffff'), # continuation reads the first native home
])
def test_inventory_curve_join_rejects_incomplete_edge(shift_runtime,site,code):
    from iced_x86 import Decoder
    from il2cpp.curve_join import joined_updates
    from il2cpp.module_curve import probed_frame

    meta,il=shift_runtime; md=meta.methods[25657]; l=Lifter(il); d=Decompiler(l)
    d.eh=il.eh_regions(md.addr); insns,skip=d._decode(md)
    d.entry_ip=md.addr; d.last_ip=insns[-1].next_ip
    # Include the native switch targets: without those block boundaries
    # the epilogue appears to fall through into an unrelated switch case.
    d._flat_insns=insns; d._flat_ip_idx={i.ip:j for j,i in enumerate(insns)}
    blocks,_=d._make_blocks(insns,skip,d._scan_jump_table_leaders(insns)); l._blocks=blocks
    frame=probed_frame(l,md,blocks,set()); assert frame==(0x100,0x2878)
    td=meta.typedefs[md.declaring]
    arms,consumed=joined_updates(l,md,td,blocks,frame)
    assert {0x1806fd858,0x1806fda1e} <= arms.keys() and 0x1806fda73 in consumed
    block,j=next((b,j) for b in blocks for j,i in enumerate(b.insns) if i.ip==site)
    replacement=Decoder(64,bytes.fromhex(code),ip=site).decode()
    assert replacement.next_ip==block.insns[j].next_ip
    block.insns[j]=replacement; l._module_tail_insns=None
    arms,consumed=joined_updates(l,md,td,blocks,frame)
    assert not ({0x1806fd858,0x1806fda1e} & arms.keys()) and 0x1806fda73 not in consumed


def test_inventory_active_gas_rejects_bad_spill_and_stack_callback(shift_runtime):
    from iced_x86 import Decoder
    from il2cpp.curve_bridge import prefixes_before_join
    from il2cpp.curve_join import joined_updates
    from il2cpp.module_curve import probed_frame

    meta,il=shift_runtime; md=meta.methods[25657]; l=Lifter(il); d=Decompiler(l)
    d.eh=il.eh_regions(md.addr); seq,skip=d._decode(md)
    d.entry_ip=md.addr; d.last_ip=seq[-1].next_ip
    d._flat_insns=seq; d._flat_ip_idx={i.ip:j for j,i in enumerate(seq)}
    blocks,_=d._make_blocks(seq,skip,d._scan_jump_table_leaders(seq)); l._blocks=blocks
    td=meta.typedefs[md.declaring]; frame=probed_frame(l,md,blocks,set()); arms,_=joined_updates(l,md,td,blocks,frame)
    key=0x1806fd8d1; plans,loads=prefixes_before_join(l,md,td,blocks,frame,arms); plan=plans[key]
    assert 0x1806fd8b7 in loads
    assert plan.constant=='35.0f' and (0xb0,8) in plan.spans and plan.argument==0x60
    for site,code in [
        (0x1806fd8dd,'488d55a8'),            # getter reads a different module
        (0x1806fd92f,'488d4da8'),            # setter uses a different module
        (0x1806fd90c,'f30f108d50000000'),    # float comes from a mutable stack slot
        (0x1806fd938,'0f29442470'),          # both stores copy the low half
        (0x1806fd942,'488b8db0ffffff'),      # callback receiver reads the old spill
        (0x1806fd955,'b101'),                # RCX partially overwritten instead of DL supplied
    ]:
        b,j=next((b,j) for b in blocks for j,i in enumerate(b.insns) if i.ip==site)
        orig=b.insns[j]; new=Decoder(64,bytes.fromhex(code),ip=site).decode(); assert new.next_ip==orig.next_ip
        b.insns[j]=new; l._module_tail_insns[site]=new
        assert key not in prefixes_before_join(l,md,td,blocks,frame,arms)[0],hex(site)
        b.insns[j]=orig; l._module_tail_insns[site]=orig


def test_actor_spawner_sets_clone_parent_in_native_order(body, tmp_path):
    from dotnet_case import run_case

    lifted = body('ActorSpawner', 'Update', 0x180514790)
    assert lifted.count('.SetParent(') == 1 and 'sub_182c03c70' not in lifted
    runner = tmp_path / 'runner'; runner.mkdir()
    (runner / 'Program.cs').write_text('''using System;
using System.Collections.Generic;
using UnityEngine;
foreach (string mode in new[]{"attach","detach","null child","parent throws","set throws"}) {
    var s = new ActorSpawner(); var log = new List<string>();
    var dest = new Transform { Local=100 }; var old = new Transform { Local=20 };
    var child = new Transform { Link=old, Local=3 }; var other = new Transform(); old.Children.Add(child);
    var source = new Component(); var original = new GameObject(); var clone = new GameObject();
    var position = new Transform(); var pivot = new Transform();
    s.template=source; source.Original=()=>{log.Add("original");return original;};
    s.Spatial=()=>{log.Add("spawn.transform");return position;};
    position.Position=()=>{log.Add("position");source.Original=()=>throw new Exception("late template read");return new(3,4,5);};
    UnityEngine.Object.Factory=(obj,pos,rot)=>{
        if(!ReferenceEquals(obj,original) || pos!=new Vector3(3,4,5) || rot!=Quaternion.identityQuaternion) throw new Exception("bad clone inputs");
        log.Add("clone"); return clone;
    };
    clone.Spatial=()=>{log.Add("child");s.Spatial=()=>{log.Add("spawner");return pivot;};return mode=="null child" ? null : child;};
    pivot.Parent=()=>{
        log.Add("parent"); clone.Spatial=()=>other;
        if(mode=="parent throws") throw new InvalidOperationException();
        return mode=="detach" ? null : dest;
    };
    child.BeforeSet=()=>{log.Add("set"); if(mode=="set throws") throw new InvalidOperationException();};
    try { s.Run(); } catch(NullReferenceException) when(mode=="null child") {log.Add("null");}
    catch(InvalidOperationException) when(mode.EndsWith("throws")) {log.Add("throw");}
    bool success=mode=="attach" || mode=="detach";
    var expected="original;spawn.transform;position;clone;child;spawner;parent;"+
        (success?"set":mode=="null child"?"null":mode=="set throws"?"set;throw":"throw");
    if(string.Join(";",log)!=expected || child.World!=23 || other.Link!=null ||
       !ReferenceEquals(child.Link,success ? (mode=="attach" ? dest : null) : old) ||
       old.Children.Contains(child)==success || dest.Children.Contains(child)!=(mode=="attach") ||
       s.instances!=(success?1:0) || s.timeFromLastSpawn!=(success?0f:2f)) throw new Exception(mode+": "+string.Join(";",log));
    Console.WriteLine($"{mode}: {string.Join(";",log)}; world={child.World}, count={s.instances}");
}
class ActorSpawner : Component {
    public Component template; public int instances, maxInstances=1; public float timeFromLastSpawn=1,spawnDelay=1;
    public void Run() {
''' + lifted + '''
    }
}
namespace UnityEngine {
    class Object {
        public static Func<GameObject,Vector3,Quaternion,GameObject> Factory;
        public static T Instantiate<T>(T original,Vector3 position,Quaternion rotation) where T : GameObject => (T)Factory(original,position,rotation);
    }
    class GameObject : Object { public Func<Transform> Spatial; public Transform transform=>Spatial(); }
    class Component : Object { public Func<Transform> Spatial; public Transform transform=>Spatial();
                               public Func<GameObject> Original; public GameObject gameObject=>Original(); }
    class Transform : Object {
        public int Local; public int World => Local+(Link?.World??0); public HashSet<Transform> Children=new();
        public Transform Link; public Func<Transform> Parent; public Transform parent=>Parent();
        public Func<Vector3> Position; public Vector3 position=>Position(); public Action BeforeSet;
        public void SetParent(Transform p) { BeforeSet(); int world=World; Link?.Children.Remove(this); Link=p;
            p?.Children.Add(this); Local=world-(p?.World??0); }
    }
    record struct Vector3(float x,float y,float z);
    record struct Quaternion(float x,float y,float z,float w) { public static Quaternion identityQuaternion=>new(0,0,0,1); }
    static class Time { public static float deltaTime=>1; }
    static class Input { public static bool GetMouseButtonDown(int i)=>i==0; }
}''',encoding='utf-8')
    print(run_case(tmp_path,runner).strip())


@pytest.mark.parametrize('site', [0x182c03cfa, 0x182c03cfd, 0x182c03cd9, 0x182c03cee])
def test_parent_setter_rejects_altered_hierarchy_effects(shift_runtime,monkeypatch,site):
    from il2cpp.reparent import _alias
    _, il = shift_runtime; lift = Lifter(il); addr=0x182c03c70
    read=il.bin.read; data=bytearray(read(addr,il.next_method_start(addr)-addr))
    # Change respectively: preserve-world flag, parent pointer register,
    # null-parent mapping, or the resolver's call target.
    delta={0x182c03cfa:2,0x182c03cfd:2,0x182c03cd9:1,0x182c03cee:1}[site]
    data[site-addr+delta]^=1
    monkeypatch.setattr(il.bin,'read',lambda p,n:bytes(data[:n]) if p==addr else read(p,n))
    assert _alias(lift,addr) is None


def test_uni_rotate_normalize_writes_both_vectors(body, tmp_path):
    import re
    from dotnet_case import run_case

    text = body('UniRotateBone','RotateCustomAxis',0x1806536f0)
    assert 'sub_182be7ea0' not in text and text.count('OrthoNormalize(ref ') == 2
    # Start with the preceding operator's Vector3 return and compile through
    # the first consumer of BOTH normalized outputs. No hand-replaced args.
    part = re.search(r'UnityEngine\.Vector3 \w+ = (\w+);\s+UnityEngine\.Vector3 \w+ = oRef\.__field_upReference;\s+'
                     r'UnityEngine\.Vector3\.OrthoNormalize\(ref .*?UnityEngine\.Quaternion\.LookRotation\([^;]*\);',text,re.S)
    assert part
    runner = tmp_path / 'runner'; runner.mkdir()
    (runner / 'Program.cs').write_text('''using System;
using UnityEngine;
foreach(int failAt in new[]{0,1,2}) {
    var bone=new Bone(); var source=new Bone(); var product=new Vector3(1,2,3); source.__field_upReference=new(4,5,6);
    int calls=0, reads=0; Quaternion.Look = (a,b)=>{
        if (++reads!=1 || calls!=2 || a!=new Vector3(21,22,23) || b!=new Vector3(24,25,26)) throw new Exception("stale LookRotation inputs");
    };
    Vector3.Normalize=(ref Vector3 a,ref Vector3 b)=>{
        ++calls;
        if (calls==1) {
            if(a!=product || b!=source.__field_upReference) throw new Exception("wrong input homes");
            a=new(11,12,13); b=new(14,15,16);
            if (source.__field_upReference!=new Vector3(4,5,6) || bone.dynamicUpReference!=default) throw new Exception("first call aliased a field");
        } else if(calls==2) {
            if(a!=new Vector3(11,12,13) || b!=new Vector3(14,15,16) || bone.dynamicUpReference!=b) throw new Exception("missing first writeback");
            a=new(21,22,23); b=new(24,25,26);
            if(bone.dynamicUpReference!=b) throw new Exception("second ref is not the actual field");
        } else throw new Exception("extra normalize");
        if(calls==failAt) throw new InvalidOperationException();
    };
    try { bone.Run(product,source); } catch (InvalidOperationException) when (failAt!=0) { }
    if (calls!=(failAt==1?1:2) || reads!=(failAt==0?1:0) || source.__field_upReference!=new Vector3(4,5,6) ||
        bone.dynamicUpReference!=(failAt==1?default:new Vector3(24,25,26))) throw new Exception("wrong order after call");
    Console.WriteLine(failAt==0?"two ref calls; LookRotation received (21,22,23) and (24,25,26)":$"throw in call {failAt}: observed field and call count match");
}
namespace UnityEngine {
    record struct Vector3(float x,float y,float z) {
        public delegate void Pair(ref Vector3 normal,ref Vector3 tangent); public static Pair Normalize;
        public static void OrthoNormalize(ref Vector3 normal,ref Vector3 tangent) => Normalize(ref normal,ref tangent);
    }
    struct Quaternion { public static Action<Vector3,Vector3> Look;
        public static Quaternion LookRotation(Vector3 a,Vector3 b) { Look(a,b); return default; } }
    class Transform { public Transform parent=>this; public Quaternion rotation=>default; }
}
class Bone {
    public Vector3 dynamicUpReference, __field_upReference; Transform __field_transform = new();
''' + f'    public void Run(Vector3 {part[1]}, Bone oRef) {{\n' + part[0] + '\n}\n}',encoding='utf-8')
    print(run_case(tmp_path,runner).strip())


def test_uni_rotate_quaternion_scratch_does_not_replay_calls(body, tmp_path):
    import re
    from dotnet_case import run_case

    lifted = body('UniRotateBone', 'RotateCustomAxis', 0x1806536f0)
    assert 'sub_182c02190' not in lifted and lifted.count('.parent /* shared getter */') == 2
    # Compile the contiguous affected slice with stand-ins for the vector
    # inputs. Keep BOTH rotation reads and LookRotation in native order.
    match = re.search(r'(UnityEngine\.Transform \w+ = this\.__field_transform;\s+'
                      r'UnityEngine\.Transform \w+ = [^;]+\.parent /\* shared getter \*/;\s+'
                      r'UnityEngine\.Quaternion (\w+) = \w+\.rotation;\s+'
                      r'(?:(\w+) = this\.dynamicUpReference;\s+)?'
                      r'UnityEngine\.Quaternion (\w+) = UnityEngine\.Quaternion\.LookRotation\(new UnityEngine\.Vector3 \{ x = (\w+)\.x,[^;]+;\s+'
                      r'(?:float \w+ = [^;]+;\s+)*UnityEngine\.Transform \w+ = this\.__field_transform;\s+'
                      r'UnityEngine\.Transform \w+ = [^;]+\.parent /\* shared getter \*/;\s+'
                      r'UnityEngine\.Quaternion (\w+) = \w+\.rotation;)', lifted)
    assert match and len({match[2], match[4], match[6]}) == 3
    runner = tmp_path / 'runner'; runner.mkdir()
    (runner / 'Program.cs').write_text('''using System;
using UnityEngine;
foreach (var mode in new[] {"ok", "look throws", "replacement null", "getter throws"}) {
    var bone = new Bone(); string log = "";
    var a = new Transform { Parent = () => {log += "old.parent;"; return new Transform { Rotation = () => { log += "first.rotation;"; return new Quaternion(1); } };} };
    var b = new Transform { Parent = () => {log += "new.parent;"; if(mode == "getter throws") throw new InvalidOperationException();
        return new Transform { Rotation = () => {log += "second.rotation;"; return new Quaternion(3);} };} };
    bone.Current = a; bone.OnRead = () => log += "read;";
    Quaternion.Calculate = (forward,up) => {
        log += "look;"; if(mode == "look throws") throw new InvalidOperationException();
        bone.Current = mode == "replacement null" ? null : b; return new Quaternion(2);
    };
    try { var q = bone.Run(default); if(q!=(1,2,3)) throw new Exception("snapshots lost"); }
    catch (NullReferenceException) when (mode=="replacement null") { log += "null;"; }
    catch (InvalidOperationException) when (mode.EndsWith("throws")) { log += "throw;"; }
    var expected = "read;old.parent;first.rotation;look;" + (mode == "look throws" ? "throw;" : mode == "replacement null" ? "read;null;" :
        mode == "getter throws" ? "read;new.parent;throw;" : "read;new.parent;second.rotation;");
    if(log!=expected) throw new Exception(mode+": "+log);
    Console.WriteLine(mode+": "+log);
}
namespace UnityEngine {
    struct Vector3 { public float x,y,z; }
    record struct Quaternion(int Id) {
        public float x => Id; public float y => -Id; public float z => Id+1; public float w => Id+2;
        public static Func<Vector3,Vector3,Quaternion> Calculate;
        public static Quaternion LookRotation(Vector3 forward,Vector3 up) => Calculate(forward,up);
    }
    class Transform { public Func<Transform> Parent; public Transform parent => Parent();
                      public Func<Quaternion> Rotation; public Quaternion rotation => Rotation(); }
}
class Bone {
    public Transform Current; public Action OnRead; public Vector3 dynamicUpReference;
    Transform __field_transform { get { OnRead(); return Current; } }
''' + f'public (int,int,int) Run(Vector3 {match[5]}) {{ ' + (f'Vector3 {match[3]}; ' if match[3] else '') + '\n' + match[1] +
        f'\nreturn ({match[2]}.Id, {match[4]}.Id, {match[6]}.Id);\n}}\n}}', encoding='utf-8')
    print(run_case(tmp_path, runner).strip())


def test_purchase_node_attaches_to_original_array_element(body, tmp_path):
    from dotnet_case import run_case

    lifted = body('PurchaseNode','AttachToFirstAvailableNode',0x180594dc0)
    assert 'sub_182c03c70' not in lifted and lifted.count('.SetParent(') == 1
    runner = tmp_path/'runner'; runner.mkdir()
    (runner/'Program.cs').write_text('''using System;
using System.Collections.Generic;
using UnityEngine;
foreach(string mode in new[]{"selected", "empty", "all occupied", "null element", "childCount throws", "SetParent throws"}) {
    var log = new List<string>(); var mgr=new PurchaseManager(); PurchaseManager.__field_Instance=mgr;
    var node=new PurchaseNode(); var owner=new Transform(); var child=new Transform { Local=7 };
    var oldParent=new Transform { Local=3 }; child.Link=oldParent; oldParent.Children.Add(child);
    var busy=new Transform(); var chosen=new Transform { Local=100 }; var swapped=new Transform();
    var nodes = mode=="empty" ? Array.Empty<Transform>() : new[]{busy, mode=="null element" ? null : chosen};
    mgr.nodePositions=nodes;
    busy.Count=()=>{log.Add("busy");mgr.nodePositions=new[]{swapped};return 1;};
    chosen.Count=()=>{log.Add("candidate");nodes[1]=swapped;
        if(mode=="childCount throws") throw new InvalidOperationException();return mode=="all occupied" ? 1 : 0;};
    node.Transform=()=>{log.Add("node");return owner;}; owner.Parent=()=>{log.Add("parent");return child;};
    child.BeforeSet=()=>{log.Add("attach");if(mode=="SetParent throws")throw new InvalidOperationException();};
    child.Reset=s=>log.Add(s);
    try { node.Attach(); } catch(InvalidOperationException) when(mode.EndsWith("throws")) { log.Add("throw"); }
    catch(NullReferenceException) when(mode=="null element") { log.Add("null"); }
    string expected=mode switch { "empty"=>"", "all occupied"=>"busy;candidate", "null element"=>"busy;null",
        "childCount throws"=>"busy;candidate;throw", "SetParent throws"=>"busy;candidate;node;parent;attach;throw",
        _=>"busy;candidate;node;parent;attach;node;parent;position;node;parent;rotation" };
    bool ok=mode=="selected";
    if (string.Join(";",log)!=expected || !ReferenceEquals(child.Link,ok ? chosen : oldParent) ||
        chosen.Children.Contains(child)!=ok || swapped.Children.Count!=0 || oldParent.Children.Contains(child)==ok ||
        (ok && (child.AtAttach!=10 || child.World!=100 || child.Rotation!=Quaternion.identityQuaternion)))
        throw new Exception(mode+": "+string.Join(";",log));
    Console.WriteLine(mode+": "+(expected=="" ? "no calls" : expected));
}
class PurchaseNode {
    public Func<Transform> Transform; public Transform transform=>Transform();
    public void Attach() {
''' + lifted + '''
    }
}
class PurchaseManager { public static PurchaseManager __field_Instance; public Transform[] nodePositions; }
namespace UnityEngine {
    record struct Vector3(float x,float y,float z) { public static Vector3 zeroVector=>default; }
    record struct Quaternion(float x,float y,float z,float w) { public static Quaternion identityQuaternion=>new(0,0,0,1); }
    class Transform {
        public Func<int> Count; public int childCount=>Count(); public Func<Transform> Parent;
        public Transform parent=>Parent(); public Transform transform=>this; public Action BeforeSet; public Action<string> Reset;
        public Transform Link; public HashSet<Transform> Children=new(); public float Local, AtAttach; public Quaternion Rotation;
        public float World=>Local+(Link?.World??0);
        public void SetParent(Transform p) { BeforeSet(); AtAttach=World; Link?.Children.Remove(this);
            Link=p; p?.Children.Add(this); Local=AtAttach-(p?.World??0); }
        public Vector3 localPosition { set { if(value!=default)throw new Exception("not zero"); Local=value.x; Reset("position"); } }
        public Quaternion localRotation { set { Rotation=value; Reset("rotation"); } }
    }
}''',encoding='utf-8')
    print(run_case(tmp_path,runner).strip())


@pytest.mark.parametrize('site,code',[(0x180594e36,'488b748720'), # scale four, not a reference slot
                                     (0x180594e0d,'488bbff8000000'), # no proven Transform[] field
                                     (0x180594e94,'488bd7')])       # forwards array base, not selected element
def test_purchase_parent_rejects_unproven_load(shift_runtime,monkeypatch,site,code):
    from iced_x86 import Decoder
    meta,il=shift_runtime; dec=Decompiler(Lifter(il)); decode=dec._decode
    def changed(md):
        seq,skip=decode(md)
        j,= (n for n,i in enumerate(seq) if i.ip==site)
        replacement=Decoder(64,bytes.fromhex(code),ip=site).decode()
        assert replacement.next_ip==seq[j].next_ip
        seq[j]=replacement
        return seq,skip
    monkeypatch.setattr(dec,'_decode',changed)
    md=meta.methods[26983]
    assert 'sub_182c03c70/*shared body,' in '\n'.join(dec.lift_method(md,meta.typedefs[md.declaring]))


def test_uni_rotate_complete_quaternion_return(body, tmp_path):
    from dotnet_case import run_case

    lifted = body('UniRotateBone', 'RotateCustomAxis', 0x1806536f0)
    assert 'unknown' not in lifted and '__ret = new UnityEngine.Quaternion {' in lifted
    runner = tmp_path / 'runner'; runner.mkdir()
    # Compile the entire recovered body. The external Unity calls return
    # labeled, noncommuting quaternions. Check their inputs as well as the
    # output so a duplicated buffer, lost spill, or transposed lane fails.
    (runner / 'Program.cs').write_text('''using System;
using UnityEngine;
var subject = new Bone(); var source = new Bone();
source.__field_upReference = new(1,2,3); source.__field_forwardReference = new(4,5,6);
subject.__field_rightCrossReference = new(7,8,9);
int angles=0, looks=0, parents=0, rotations=0, orthos=0;
subject.__field_transform = new Transform { Parent = () => {
    parents++; return new Transform { Rotation = () => ++rotations == 1 ? new(3,-1,4,2) : new(1,-4,3,2) };
} };
Quaternion.Angle = (angle,axis) => (++angles,angle,axis) switch {
    (1,22,(1,2,3)) => new(1,2,3,4), (2,11,(7,8,9)) => new(-2,5,7,3), _ => throw new Exception("AngleAxis inputs") };
Quaternion.Apply = (q,v) => (q,v) == (new Quaternion(-6,13,46,-17),new Vector3(4,5,6)) ? new(10,20,30) : throw new Exception("angle product");
Vector3.Normalize = (ref Vector3 a,ref Vector3 b) => {
    orthos++;
    if (orthos==1 && (a,b)!=(new Vector3(10,20,30),new Vector3(1,2,3))) throw new Exception("first pair");
    if (orthos==2 && (a,b)!=(new Vector3(11,22,33),new Vector3(5,7,9))) throw new Exception("second pair");
    a = new(a.x+1,a.y+2,a.z+3); b = new(b.x+4,b.y+5,b.z+6);
};
Quaternion.Look = (forward,up) => {
    if (++looks==1 && (forward,up)==(new Vector3(12,24,36), new Vector3(9,12,15))) {
        source.__field_forwardReference=new(8,3,-4); source.__field_upReference=new(-7,4,1);
        return new(2,6,-3,5);
    }
    if (looks==2 && (forward,up)==(source.__field_forwardReference,source.__field_upReference)) return new(5,2,-7,3);
    throw new Exception("LookRotation inputs");
};
Quaternion.Inv = q => q == new Quaternion(35,14,17,30) ? new(2,-3,5,7) : throw new Exception("inverse input");
var actual = subject.RotateCustomAxis(11,22,source);
// Hamilton product (-2,24,34,22) * (2,-3,5,7); all inputs and results
// are small integers, so there is no rounding tolerance to hide a lane swap.
if (actual != new Quaternion(252,180,306,60) || (angles,looks,parents,rotations,orthos)!=(2,2,2,2,2))
    throw new Exception("returned " + actual);
Console.WriteLine($"complete RotateCustomAxis: x={actual.x}, y={actual.y}, z={actual.z}, w={actual.w}");
namespace UnityEngine {
    record struct Vector3(float x,float y,float z) {
        public delegate void Pair(ref Vector3 a,ref Vector3 b); public static Pair Normalize;
        public static void OrthoNormalize(ref Vector3 a,ref Vector3 b) => Normalize(ref a,ref b);
    }
    record struct Quaternion(float x,float y,float z,float w) {
        public static Func<float,Vector3,Quaternion> Angle; public static Func<Quaternion,Vector3,Vector3> Apply;
        public static Func<Vector3,Vector3,Quaternion> Look; public static Func<Quaternion,Quaternion> Inv;
        public static Quaternion AngleAxis(float a,Vector3 v) => Angle(a,v);
        public static Vector3 operator *(Quaternion q,Vector3 v) => Apply(q,v);
        public static Quaternion LookRotation(Vector3 a,Vector3 b) => Look(a,b);
        public static Quaternion Inverse(Quaternion q) => Inv(q);
    }
    class Transform { public Func<Transform> Parent; public Func<Quaternion> Rotation;
        public Transform parent => Parent(); public Quaternion rotation => Rotation(); }
}
class Bone {
    public Transform __field_transform; public Vector3 __field_upReference,__field_forwardReference,__field_rightCrossReference,dynamicUpReference;
    public Quaternion RotateCustomAxis(float x,float y,Bone oRef) {
''' + lifted + '\n}\n}', encoding='utf-8')
    print(run_case(tmp_path,runner).strip())


@pytest.mark.parametrize('site,code', [
    (0x180653716,'488bf2'),       # RSI holds this (RDX), not the entry sret pointer
    (0x180653c81,'f3440f104d44'), # different stack dword from the saved z component
    (0x180653dab,'450fc6c000'),   # final shuffle broadcasts instead of packing four values
])
def test_quaternion_sret_declines_incomplete_trace(shift_runtime, monkeypatch,site,code):
    from iced_x86 import Decoder

    meta, il = shift_runtime
    dec = Decompiler(Lifter(il)); decode = dec._decode
    def changed(md):
        ii, skip = decode(md)
        j, = (j for j,i in enumerate(ii) if i.ip == site)
        new = Decoder(64, bytes.fromhex(code), ip=site).decode()
        assert new.next_ip == ii[j].next_ip
        ii[j] = new
        return ii, skip
    monkeypatch.setattr(dec, '_decode', changed)
    md = meta.methods[29260]
    assert '__ret = new UnityEngine.Quaternion {' not in '\n'.join(dec.lift_method(md,meta.typedefs[md.declaring]))


def test_uni_rotate_bone_copies_vector_before_second_parent(body, tmp_path):
    import re
    from dotnet_case import run_case

    lifted = body('UniRotateBone','RefreshCustomAxis',0x180651f70)
    assert 'sub_182c02190' not in lifted and lifted.count('.parent /* shared getter */') == 2
    first = re.search(r'UnityEngine\.Transform (\w+) = this\.__field_transform;\s+'
                      r'UnityEngine\.Transform \w+ = \(\(UnityEngine\.Transform\)\1\)\.parent /\* shared getter \*/;',lifted)
    # Compile the actual product, whole field store, fresh receiver read,
    # parent getter and rotation getter. The enclosing method's earlier
    # quaternion math is not part of this regression.
    copy = re.search(r'(\w+) = (\w+) \* (\w+);\s+this\.__field_forwardReference = \1;\s+'
                     r'UnityEngine\.Transform (\w+) = this\.__field_transform;\s+'
                     r'UnityEngine\.Transform (\w+) = \(\(UnityEngine\.Transform\)\4\)\.parent /\* shared getter \*/;\s+'
                     r'\2 = \5\.rotation;',lifted)
    assert first and copy and first.end() < copy.start()
    runner = tmp_path / 'runner'; runner.mkdir()
    (runner / 'Program.cs').write_text('''using System;
using UnityEngine;
foreach (string mode in new[]{"normal","null receiver","getter throws","product throws"}) {
    string log=""; var bone=new Bone(); bone.Record=s=>log+=s+";";
    var parent=new Transform { Rotation=()=>{bone.Record("rotation"); return default;} };
    var old=new Transform { Parent=()=>{bone.Record("old.parent"); return parent;} };
    var next=new Transform { Parent=()=>{bone.Record("new.parent"); if(mode=="getter throws") throw new InvalidOperationException(); return parent;} };
    bone.Current=old;
    var q=new Quaternion { Op=()=>{
        bone.Record("product"); bone.Current=mode=="null receiver" ? null : next;
        if(mode=="product throws") throw new InvalidOperationException();
    }};
    var v=new Vector3(-0.0f, 17.25f, BitConverter.Int32BitsToSingle(0x7fc12345));
    try { bone.Run(q,v); } catch (NullReferenceException) when (mode=="null receiver") { bone.Record("null"); }
    catch (InvalidOperationException) when (mode.EndsWith("throws")) { bone.Record("throw"); }
    var expected="reload;old.parent;product;" + (mode=="product throws" ? "throw;" : "store;reload;" +
        (mode=="null receiver" ? "null;" : "new.parent;" + (mode=="normal" ? "rotation;" : "throw;")));
    if(log!=expected || (mode!="product throws" && !bone.Stored.SameBits(v))) throw new Exception(mode+": "+log);
    Console.WriteLine(mode+": "+log);
}
namespace UnityEngine {
    record struct Vector3(float X,float Y,float Z) {
        public bool SameBits(Vector3 v) => Bits(X)==Bits(v.X) && Bits(Y)==Bits(v.Y) && Bits(Z)==Bits(v.Z);
        static int Bits(float f) => BitConverter.SingleToInt32Bits(f);
    }
    struct Quaternion { public Action Op; public static Vector3 operator *(Quaternion q,Vector3 v) { q.Op(); return v; } }
    class Transform {
        public Func<Transform> Parent; public Transform parent => Parent();
        public Func<Quaternion> Rotation; public Quaternion rotation => Rotation();
    }
}
class Bone {
    public Action<string> Record; public Transform Current; public Vector3 Stored;
    Transform __field_transform { get {Record("reload"); return Current;} }
    Vector3 __field_forwardReference { set {Stored=value; Record("store");} }
''' + f'    public void Run(Quaternion {copy[2]}, Vector3 {copy[3]}) {{\nVector3 {copy[1]};\n'
        + first[0] + '\n' + copy[0] + '\n}\n}', encoding='utf-8')
    print(run_case(tmp_path,runner).strip())


def test_skeleton_child_loop_uses_array_then_actual_parent(body, tmp_path):
    from dotnet_case import run_case

    lifted = body('SkeletonRecognize', 'GetBottomMostChildTransform', 0x18064e5f0)
    assert 'sub_182c02190' not in lifted and lifted.count('.parent /* shared getter */') == 3
    assert lifted.count('GetComponentsInChildren<UnityEngine.Transform>(true)') == 1
    runner = tmp_path / 'runner'; runner.mkdir()
    (runner / 'Program.cs').write_text('''using System;
using System.Collections.Generic;
using UnityEngine;
var root = new Transform("root"); var joint = new Transform("joint",root);
var mid = new Transform("mid",joint); var deep = new Transform("deep",mid);
var shallow = new Transform("shallow",joint); var tie = new Transform("tie",mid);
void Check(Transform expected, string trace, params Transform[] items) {
    root.Children = items; Transform.Reads.Clear(); root.Queries=0;
    var result = GetBottomMostChildTransform(root);
    if (!ReferenceEquals(expected, result) || root.Queries != 1 || string.Join(",",Transform.Reads) != trace)
        throw new Exception("result="+result.Name+" trace="+string.Join(",",Transform.Reads)+" queries="+root.Queries);
}
Check(root, "");
Check(deep,"deep,deep,deep,mid,mid,mid,joint,shallow,shallow,shallow,joint,tie,tie,tie,mid,mid,mid,joint",root,deep,shallow,tie);
Console.WriteLine("deepest kept over later shallow and tied candidates; one array query, ordered reads on entry and back edge");
var changing = new Transform("changing", joint); int reads=0;
changing.Read = () => ++reads==1 ? joint : null;
Check(root,"changing,changing",changing);
changing.Read = () => throw new InvalidOperationException();
try { GetBottomMostChildTransform(root); throw new Exception("missing getter exception"); } catch (InvalidOperationException) { }
root.Children = new Transform[] { null };
try { GetBottomMostChildTransform(root); throw new Exception("missing null receiver failure"); } catch (NullReferenceException) { }
Console.WriteLine("changed parent observed on second read; getter exception and null receiver preserved");
static Transform GetBottomMostChildTransform(Transform parent) {
''' + lifted + '''
}
namespace UnityEngine {
    class Object { }
    class Transform : Object {
        public static List<string> Reads = new(); public int Queries; public string Name;
        public Func<Transform> Read; public Transform[] Children;
        public Transform(string name,Transform p=null) { Name=name; Read=()=>p; }
        public Transform parent { get { Reads.Add(Name); return Read(); } }
        public T[] GetComponentsInChildren<T>(bool includeInactive) where T : Object {
            if (typeof(T)!=typeof(Transform) || !includeInactive) throw new Exception("wrong specialization or flag");
            Queries++; return (T[])(object)Children;
        }
    }
}''', encoding='utf-8')
    print(run_case(tmp_path, runner).strip())


@pytest.mark.parametrize('site,encoding', [(0x18064e6ca,'498b5c9e20'),  # index*4 cannot load a Transform slot
                                          (0x18064e74c,'488bde')])     # back edge takes the counter, not getter RAX
def test_skeleton_parent_needs_both_incoming_types(shift_runtime, monkeypatch, site, encoding):
    from iced_x86 import Decoder

    meta, il = shift_runtime
    dec = Decompiler(Lifter(il)); decode = dec._decode
    def changed(md):
        ii, skip = decode(md)
        j, = (j for j,i in enumerate(ii) if i.ip == site)
        replacement = Decoder(64, bytes.fromhex(encoding), ip=site).decode()
        assert replacement.next_ip == ii[j].next_ip
        ii[j] = replacement
        return ii, skip
    monkeypatch.setattr(dec, '_decode', changed)
    md = meta.methods[29313]
    text = '\n'.join(dec.lift_method(md, meta.typedefs[md.declaring]))
    assert 'sub_182c02190/*shared body,' in text


def test_set_bones_reads_end_parent_once(body, tmp_path):
    import re
    from dotnet_case import run_case

    lifted = body('FimpIK_Limb', 'SetBones', 0x180647450)
    assert 'sub_182c02190' not in lifted and lifted.count('endBone.parent') == 1
    upper_leg = body('LegsAnimator', 'Finding_FindUpperLeg', 0x18065fdf0)
    widened, dst, src = re.search(r'(UnityEngine\.Object (\w+) = \(\(UnityEngine\.Transform\)(\w+)\)\.parent /\* shared getter \*/;)', upper_leg).groups()
    runner = tmp_path / 'runner'; runner.mkdir()
    (runner / 'Program.cs').write_text('''using System;
using UnityEngine;
var limb = new Limb(); var start = new Transform(); var parent = new Transform();
foreach (var expected in new[] {parent, null}) {
    var end = new Transform { Next = expected };
    limb.SetBones(start, end);
    if (end.Reads != 1 || !ReferenceEquals(limb.First, start) ||
        !ReferenceEquals(limb.Middle, expected) || !ReferenceEquals(limb.Last, end)) throw new Exception("wrong parent or arguments");
}
var lost = new Transform { Lost = true };
try { limb.SetBones(start, lost); throw new Exception("missing getter failure"); } catch (InvalidOperationException) { }
try { limb.SetBones(start, null); throw new Exception("missing null receiver failure"); } catch (NullReferenceException) { }
if (lost.Reads != 1 || limb.Calls != 2) throw new Exception("duplicate read or late failure");
var wider = new Transform { Next = start };
if (!ReferenceEquals(limb.ReadWidened(wider), start) || wider.Reads != 1) throw new Exception("wrong receiver cast");
Console.WriteLine("parent and null parent: one read, forwarded (start, parent, end); throwing getter and null receiver: no SetBones call");
namespace UnityEngine {
    class Object { }
    class Transform : Object {
        public int Reads; public bool Lost; public Transform Next;
        public Transform parent { get { Reads++; if (Lost) throw new InvalidOperationException(); return Next; } }
    }
}
class Limb {
    public UnityEngine.Object ReadWidened(UnityEngine.Object ''' + src + ') {\n' + widened + '\nreturn ' + dst + '''; }
    public Transform First, Middle, Last; public int Calls;
    void SetBones(Transform a, Transform b, Transform c) { Calls++; First = a; Middle = b; Last = c; }
    public void SetBones(Transform startBone, Transform endBone) {
''' + lifted + '\n}\n}', encoding='utf-8')
    print(run_case(tmp_path, runner).strip())


@pytest.mark.parametrize('change', ['hidden argument', 'different cache', 'wrong result spec', 'wrong return target'])
def test_parent_alias_needs_the_same_forwarder_on_both_paths(shift_runtime, monkeypatch, change):
    from iced_x86 import Decoder, Mnemonic as M, Register as R
    from il2cpp.shared_getter import _public_alias

    meta, il = shift_runtime
    addr = 0x182c02190
    owner = meta.methods[57017].declaring
    lift = Lifter(il)
    read = il.bin.read
    code = bytearray(read(addr, il.next_method_start(addr)-addr))
    ins = list(Decoder(64,bytes(code),ip=addr))
    if change == 'hidden argument':
        # Pass incoming RDX, not the cached native receiver, on an icall hit.
        call = next(j for j,i in enumerate(ins) if i.mnemonic == M.CALL and i.op0_register == R.RAX)
        at = ins[call-1].ip - addr
        code[at:at+3] = bytes.fromhex('48 8b ca')
    elif change == 'different cache':
        store = next(i for i in ins if i.is_ip_rel_memory_operand and i.op1_register == R.RAX)
        code[store.next_ip-addr-4] ^= 8
    elif change == 'wrong result spec':
        load = next(i for i in ins if i.is_ip_rel_memory_operand and i.op0_register == R.RDX)
        slot = next(i.ip_rel_memory_address for i in ins if i.mnemonic == M.LEA)
        code[load.next_ip-addr-4:load.next_ip-addr] = (slot-load.next_ip).to_bytes(4,'little',signed=True)
    else:
        jump = next(i for i in ins if i.mnemonic == M.JMP)
        code[jump.next_ip-addr-4] ^= 0x10
    monkeypatch.setattr(il.bin, 'read', lambda p,n:bytes(code[:n]) if p==addr else read(p,n))
    assert _public_alias(lift,addr,owner) is None


def test_height_stabilizer_base_init_precedes_variable_requests(body, tmp_path):
    from dotnet_case import run_case

    lifted = body('LAM_HeightStabilizer', 'OnInit', 0x180692a70)
    assert lifted.startswith('base.OnInit(helper) /* shared implementation */;')
    assert lifted.count('base.OnInit(') == 1 and 'sub_180507120' not in lifted
    runner = tmp_path / 'runner'; runner.mkdir()
    (runner / 'Program.cs').write_text('''using System;
using System.Collections.Generic;
using FIMSpace.FProceduralAnimation;
var module = new HeightStabilizer(); ModuleBase callback = module;
var helper = new LegsAnimator.LegsAnimatorCustomModuleHelper(); callback.OnInit(helper);
string trace = string.Join(";", helper.Events);
if (module.BaseCalls != 1 || !ReferenceEquals(module.Seen,helper) ||
    trace != "base;Blend;Reaction Speed;Blend Y;Extra Push Down Blend") throw new Exception(trace);
Console.WriteLine(trace);
try { callback.OnInit(null); throw new Exception("expected null helper failure"); }
catch (NullReferenceException) { }
if (module.BaseCalls != 2 || module.Seen != null) throw new Exception("null helper was not forwarded first");
Console.WriteLine("null helper: base once before first request threw");
namespace FIMSpace.FProceduralAnimation {
    class LegsAnimator {
        public class Variable { }
        public class LegsAnimatorCustomModuleHelper {
            public List<string> Events = new();
            public Variable RequestVariable(string name, object value) { Events.Add(name); return new(); }
        }
    }
    class ModuleBase {
        public int BaseCalls; public LegsAnimator.LegsAnimatorCustomModuleHelper Seen;
        public virtual void OnInit(LegsAnimator.LegsAnimatorCustomModuleHelper helper) {
            BaseCalls++; Seen = helper; helper?.Events.Add("base");
        }
    }
    class HeightStabilizer : ModuleBase {
        LegsAnimator.Variable _powerV, _reactV, _thresV, _extrV;
        public override void OnInit(LegsAnimator.LegsAnimatorCustomModuleHelper helper) {
''' + lifted + '\n}\n}\n}', encoding='utf-8')
    print(run_case(tmp_path, runner).strip())


def test_ik_switch_base_init_precedes_processor_allocation(body, tmp_path):
    from dotnet_case import run_case

    lifted = body('LAM_IKAlgorithmSwitch', 'OnInit', 0x18069a130)
    assert lifted.count('base.OnInit(helper) /* shared implementation */;') == 1 and 'sub_180507120' not in lifted
    lines = lifted.splitlines()
    owner = next(j for j,line in enumerate(lines) if '= base.Owner;' in line)
    prefix = '\n'.join(lines[:owner+1]); assert 'this.playmodeIKProcessors = ' in prefix
    runner = tmp_path / 'runner'; runner.mkdir()
    (runner / 'Program.cs').write_text('''using System;
using FIMSpace.FProceduralAnimation;
var module = new IKSwitch(); ModuleBase callback = module;
var helper = new LegsAnimator.LegsAnimatorCustomModuleHelper(); callback.OnInit(helper);
if (Log.Events != "base;allocate;owner;" || !ReferenceEquals(module.Seen, helper) ||
    !ReferenceEquals(module.playmodeIKProcessors, Log.Allocation)) throw new Exception(Log.Events);
Console.WriteLine(Log.Events + " same helper and processor list");
Log.Events = ""; module.Fail = true;
try { callback.OnInit(null); throw new Exception("base didn't throw"); } catch (InvalidOperationException) { }
if (Log.Events != "base;" || module.Seen != null) throw new Exception("allocation after failure");
Console.WriteLine("base threw: no subsequent allocation or Owner read");
static class Log { public static string Events = ""; public static object Allocation; }
namespace System.Collections.Generic {
    class List_1<T> { public List_1() { Log.Events += "allocate;"; Log.Allocation = this; } }
}
namespace FIMSpace.FProceduralAnimation {
    class AxisLockableIK { }
    class LegsAnimator { public class LegsAnimatorCustomModuleHelper { } }
    class ModuleBase {
        public bool Fail; public LegsAnimator.LegsAnimatorCustomModuleHelper Seen;
        protected LegsAnimator Owner { get {
            if (!ReferenceEquals(((IKSwitch)this).playmodeIKProcessors, Log.Allocation)) throw new Exception("early Owner read");
            Log.Events += "owner;"; return new LegsAnimator();
        } }
        public virtual void OnInit(LegsAnimator.LegsAnimatorCustomModuleHelper helper) {
            Log.Events += "base;"; Seen = helper; if (Fail) throw new InvalidOperationException();
        }
    }
    class IKSwitch : ModuleBase {
        public System.Collections.Generic.List_1<AxisLockableIK> playmodeIKProcessors;
        public override void OnInit(LegsAnimator.LegsAnimatorCustomModuleHelper helper) {
''' + prefix + '\n}\n}\n}', encoding='utf-8')
    print(run_case(tmp_path, runner).strip())


def test_ik_switch_validate_forwards_only_non_null_helper(body, tmp_path):
    from dotnet_case import run_case

    lifted = body('LAM_IKAlgorithmSwitch','OnValidateAfterManualChanges',0x18069a340)
    assert 'sub_180507120' not in lifted and lifted.count('base.OnValidateAfterManualChanges(') == 1
    guard, _ = lifted.split('if (this.playmodeIKProcessors', 1)
    assert guard.strip().splitlines() == ['if (helper != null)', '{',
        '    base.OnValidateAfterManualChanges(helper) /* shared implementation */;', '}']
    runner = tmp_path / 'runner'; runner.mkdir()
    (runner / 'Program.cs').write_text('''using System;
foreach (bool present in new[]{true, false}) {
    var module = new IKSwitch(); ModuleBase callback = module;
    var helper = present ? new Helper() : null;
    callback.OnValidateAfterManualChanges(helper);
    if (module.Trace != (present ? "base;join;" : "join;") || !ReferenceEquals(module.Seen, helper))
        throw new Exception("wrong call count, order or helper");
    Console.WriteLine((present ? "non-null: " : "null: ") + module.Trace);
}
class Helper { }
class ModuleBase {
    public string Trace = ""; public Helper Seen;
    public virtual void OnValidateAfterManualChanges(Helper helper) { Trace += "base;"; Seen = helper; }
}
class IKSwitch : ModuleBase {
    public override void OnValidateAfterManualChanges(Helper helper) {
''' + guard + '\nTrace += "join;";\n}\n}', encoding='utf-8')
    print(run_case(tmp_path, runner).strip())


def test_ik_axis_lock_all_eight_masks(body, tmp_path):
    from dotnet_case import run_case

    get_lock = body('LAM_IKAlgorithmSwitch', 'GetLock', 0x18069a100)
    validate = body('LAM_IKAlgorithmSwitch', 'OnValidateAfterManualChanges', 0x18069a340)
    runner = tmp_path / 'runner'; runner.mkdir()
    # Compile both complete lifted bodies. Instrument the three reads so a
    # duplicated or reordered evaluation cannot pass just by getting the bits right.
    (runner / 'Program.cs').write_text('''using System;
using System.Collections.Generic;
using FIMSpace.FProceduralAnimation;
int[] expected = { 0, 2, 4, 6, 8, 10, 12, 14 };
var module = new Switch(); var a = new AxisLockableIK(); var b = new AxisLockableIK();
module.playmodeIKProcessors = new() { a, b };
for (int i=0; i<8; i++) {
    module.Axes=i; module.Trace="";
    int got=(int)module.GetLock();
    if (got != expected[i] || module.Trace != "XYZ") throw new Exception("getter: " + i);
    module.Trace=""; module.OnValidateAfterManualChanges(new Helper());
    if (module.Trace != "base;XYZXYZ" || (int)a.FirstBoneAxisLock != got || (int)b.FirstBoneAxisLock != got)
        throw new Exception("validation: " + i);
    Console.WriteLine($"X={i&1} Y={(i>>1)&1} Z={(i>>2)&1}: GetLock={got}, both stores={got}");
}
module.Trace=""; module.playmodeIKProcessors=null; module.OnValidateAfterManualChanges(null);
if (module.Trace != "") throw new Exception("unexpected work on null list/helper");
namespace System.Collections.Generic {
    class List_1<T> : List<T> { public int _size => Count; }
}
namespace FIMSpace.FProceduralAnimation {
    class AxisLockableIK {
        public enum EIKAxisLock { None=0, X=2, Y=4, Z=8 }
        public EIKAxisLock FirstBoneAxisLock;
    }
    class Helper { }
    class ModuleBase {
        public string Trace;
        public virtual void OnValidateAfterManualChanges(Helper helper) { Trace += "base;"; }
    }
    class Switch : ModuleBase {
        public List_1<AxisLockableIK> playmodeIKProcessors; public int Axes;
        bool lockX { get { Trace += "X"; return (Axes & 1) != 0; } }
        bool lockY { get { Trace += "Y"; return (Axes & 2) != 0; } }
        bool lockZ { get { Trace += "Z"; return (Axes & 4) != 0; } }
        public AxisLockableIK.EIKAxisLock GetLock() {
''' + get_lock + '\n}\n public override void OnValidateAfterManualChanges(Helper helper) {\n'
        + validate + '\n}\n}\n}', encoding='utf-8')
    print(run_case(tmp_path, runner).strip())


def test_creating_poster_despawn_calls_base_once_then_cancel(body, tmp_path):
    from dotnet_case import run_case

    lifted = body('CreatingPoster', 'Despawned', 0x1806b2e00)
    assert lifted.splitlines() == ['base.Despawned(runner, hasState) /* shared implementation */;',
                                   'this.CancelCreating(); return;']
    runner = tmp_path / 'runner'; runner.mkdir()
    (runner / 'Program.cs').write_text('''using System;
var poster = new CreatingPoster(); NetworkBehaviour callback = poster;
foreach (bool hasState in new[] {false,true}) {
    var runner = hasState ? new NetworkRunner() : null;
    poster.Trace = "";
    callback.Despawned(runner,hasState);
    if (poster.Trace != "base;cancel;" || !ReferenceEquals(poster.Runner,runner) || poster.State != hasState)
        throw new Exception("incorrect dispatch, arguments, count or order");
    Console.WriteLine($"hasState={hasState}: {poster.Trace} same runner");
}
class NetworkRunner { }
class NetworkBehaviour {
    public string Trace; public NetworkRunner Runner; public bool State;
    public virtual void Despawned(NetworkRunner runner, bool hasState) {
        Trace += "base;"; Runner=runner; State=hasState;
    }
}
class CreatingPoster : NetworkBehaviour {
    private void CancelCreating() { Trace += "cancel;"; }
    public override void Despawned(NetworkRunner runner, bool hasState) {
''' + lifted + '\n}\n}', encoding='utf-8')
    print(run_case(tmp_path, runner).strip())


def test_creating_poster_spawn_calls_base_before_poster_checks(body, tmp_path):
    from dotnet_case import run_case

    lifted = body('CreatingPoster', 'Spawned', 0x1806b3b50)
    assert lifted.count('base.Spawned() /* shared implementation */;') == 1
    assert 'sub_180507120' not in lifted
    runner = tmp_path / 'runner'; runner.mkdir()
    (runner / 'Program.cs').write_text('''using System;
foreach (var (init, pending, expected) in new[] {
    (true, "poster", "base;load:poster;"), (false, "poster", "base;"),
    (true, "", "base;"), (true, (string)null, "base;") }) {
    var p = new CreatingPoster();
    // Both fields start empty. The callback must see the values set by base.
    p.InBase = () => { p._initialized = init; p._pendingPosterString = pending; };
    NetworkBehaviour callback = p; callback.Spawned();
    if (p.Log != expected || p._pendingPosterString != (expected.Contains("load:") ? null : pending))
        throw new Exception("wrong dispatch, count or order: " + p.Log);
    Console.WriteLine($"initialized={init}, pending={pending ?? "<null>"}: {p.Log}");
}
class NetworkBehaviour {
    public string Log = ""; public Action InBase;
    public virtual void Spawned() { Log += "base;"; InBase(); }
}
class CreatingPoster : NetworkBehaviour {
    public bool _initialized; public string _pendingPosterString;
    private void Rpc_LoadPoster(string poster) {
        if (poster != _pendingPosterString) throw new Exception("cleared too early");
        Log += "load:" + poster + ";";
    }
    public override void Spawned() {
''' + lifted + '\n}\n}', encoding='utf-8')
    print(run_case(tmp_path, runner).strip())


def test_remote_trap_spawn_tail_dispatches_to_base_once(body, tmp_path):
    from dotnet_case import run_case

    lifted = body('RemoteTrap', 'Spawned', 0x180501870)
    assert lifted == 'base.Spawned() /* shared implementation */; return;'
    runner = tmp_path / 'runner'; runner.mkdir()
    (runner / 'Program.cs').write_text('''using System;
var trap = new ObservedTrap(); NetworkBehaviour receiver = trap;
receiver.Spawned();
if (trap.Entries != 1 || trap.BaseCalls != 1) throw new Exception("wrong dispatch count");
Console.WriteLine($"virtual entries={trap.Entries}, base calls={trap.BaseCalls}");
class NetworkBehaviour {
    public int BaseCalls;
    public virtual void Spawned() { BaseCalls++; }
}
class RemoteTrap : NetworkBehaviour {
    public override void Spawned() {
''' + lifted + '''
    }
}
class ObservedTrap : RemoteTrap {
    public int Entries;
    public override void Spawned() {
        if (++Entries != 1) throw new Exception("recursive virtual redispatch");
        base.Spawned();
    }
}''', encoding='utf-8')
    print(run_case(tmp_path, runner).strip())


def test_demo_performance_start_preserves_receiver_before_getter(body, tmp_path):
    from dotnet_case import run_case

    sites = []
    for owner, va, field in [('DEMO_LegsAnim_CharacterControllerTest', 0x180683060, 'performanceTest'),
                             ('DEMO_LegsAnim_SpiderMover', 0x180688410, 'perf')]:
        text = body(owner, 'Update', va)
        line, = (s.strip() for s in text.splitlines() if '.Start(this.gameObject,' in s)
        assert line == f'this.{field}.Start(this.gameObject, true) /* shared implementation */;'
        assert 'this.gameObject' not in text[:text.index(line)]
        sites.append(line)
    runner = tmp_path / 'runner'; runner.mkdir()
    (runner / 'Program.cs').write_text('''using System;
foreach (bool spider in new[] {false,true}) {
    var probe = new Demo(); var original = new Meter();
    probe.performanceTest = probe.perf = original;
    probe.Run(spider);
    if (probe.Reads != 1 || original.Calls != 1 || probe.Next.Calls != 0 || !original.Selected ||
        !ReferenceEquals(original.Received, probe.Object)) throw new Exception("wrong receiver, args or count");
    // A null receiver still evaluates the getter, even though it changes
    // the field to non-null. The native guard raises after that evaluation.
    probe.performanceTest = probe.perf = null;
    try { probe.Run(spider); throw new Exception("missing null check"); } catch (NullReferenceException) { }
    if (probe.Reads != 2 || probe.Next.Calls != 0) throw new Exception("wrong null path");
    Console.WriteLine((spider ? "SpiderMover" : "CharacterControllerTest") +
        ": getter once, original receiver started once with (gameObject, true); null checked after getter");
}
class GameObject { }
class Meter {
    public int Calls; public GameObject Received; public bool Selected;
    public void Start(GameObject value, bool selected) { ++Calls; Received = value; Selected = selected; }
}
class Demo {
    public Meter performanceTest, perf, Next = new(); public int Reads; public GameObject Object = new();
    GameObject gameObject { get { ++Reads; performanceTest = perf = Next; return Object; } }
    public void Run(bool spider) {
        if (spider) {\n''' + sites[1] + '\n} else {\n' + sites[0] + '\n}\n}\n}', encoding='utf-8')
    print(run_case(tmp_path, runner).strip())


def test_controller_performance_finish_tail(body, tmp_path):
    from dotnet_case import run_case

    text = body('DEMO_LegsAnim_CharacterControllerTest', 'Update', 0x180683060)
    # Include ALL statements after Move: extracting just the last call would
    # miss an independently flushed, duplicate evaluation of the conversion.
    tail = text.split('CharacterController.Move(',1)[1].split('\n',1)[1].strip()
    assert tail.count('this.gameObject') == 1 and 'op_Implicit' not in tail and 'sub_' not in tail
    assert 'this.performanceTest.Finish(' in tail
    runner = tmp_path / 'runner'; runner.mkdir()
    (runner / 'Program.cs').write_text('''using System;
foreach (var (label, present, value, failAt, expected) in new[] {
    ("selected",true,true,"","get;convert;finish:True;"), ("not selected",true,false,"","get;convert;finish:False;"),
    ("null receiver",false,true,"","get;convert;null;"), ("getter throws",false,true,"get","get;failed;"),
    ("conversion throws",false,true,"convert","get;convert;failed;") }) {
    Log.Text = ""; Log.Fail = failAt;
    var original = new Meter(); var probe = new Controller { performanceTest = present ? original : null };
    probe.Value.Selected = value;
    try { probe.Run(); }
    catch (NullReferenceException) { Log.Text += "null;"; }
    catch (InvalidOperationException) { Log.Text += "failed;"; }
    if (Log.Text != expected || probe.Next.Calls != 0 || original.Calls != (present ? 1 : 0))
        throw new Exception(label + ": " + Log.Text);
    Console.WriteLine(label + ": " + Log.Text);
}
static class Log { public static string Text, Fail; }
namespace UnityEngine {
    class Object {
        public bool Selected;
        public static implicit operator bool(Object value) {
            Log.Text += "convert;";
            if (Log.Fail == "convert") throw new InvalidOperationException();
            return value.Selected;
        }
    }
    class GameObject : Object { }
}
class Meter {
    public int Calls;
    public void Finish(bool onlyIfSelected) { Calls++; Log.Text += "finish:" + onlyIfSelected + ";"; }
}
class Controller {
    public Meter performanceTest, Next = new(); public UnityEngine.GameObject Value = new();
    UnityEngine.GameObject gameObject { get {
        Log.Text += "get;"; performanceTest = Next;
        if (Log.Fail == "get") throw new InvalidOperationException();
        return Value;
    } }
    public void Run() {
''' + tail + '\n}\n}', encoding='utf-8')
    print(run_case(tmp_path,runner).strip())


def test_spider_performance_finish_after_position_setter(body, tmp_path):
    import re
    from dotnet_case import run_case

    text = body('DEMO_LegsAnim_SpiderMover', 'Update', 0x180688410)
    setter, position, finish = re.findall(
        r'(this\.transform\.position = (\w+);)\s+(this\.perf\.Finish\(true\) /\* shared implementation \*/; return;)', text)[0]
    assert text.count('this.perf.Finish(') == 1 and 'sub_180507120' not in text
    runner = tmp_path / 'runner'; runner.mkdir()
    (runner / 'Program.cs').write_text('''using System;
foreach (bool clear in new[] { false, true }) {
    var mover = new Mover(); var old = mover.perf; var next = new Meter();
    mover.transform.Set = p => { if (p != 17) throw new Exception("wrong position"); mover.perf = clear ? null : next; };
    try { mover.Run(17); if (clear) throw new Exception("missing null check"); }
    catch (NullReferenceException) when (clear) { }
    if (mover.transform.Writes != 1 || old.Calls != 0 || next.Calls != (clear ? 0 : 1)) throw new Exception("finish order or count");
    Console.WriteLine(clear ? "position set; null receiver threw; Finish calls=0" : "position set; replacement.Finish(true) calls=1; old calls=0");
}
class Meter {
    public int Calls;
    public void Finish(bool selected) { if (!selected) throw new Exception("wrong flag"); ++Calls; }
}
class Transform {
    public Action<int> Set; public int Writes;
    public int position { set { ++Writes; Set(value); } }
}
class Mover {
    public Meter perf = new(); public Transform transform = new();
    public void Run(int ''' + position + ') {\n' + setter + '\n' + finish + '\n}\n}', encoding='utf-8')
    print(run_case(tmp_path,runner).strip())


def test_computer_search_awaiter_completion_paths(body, tmp_path):
    import re

    text = body('<Search>d__81', 'MoveNext', 0x1806bdc60)
    assert 'sub_1811f7db0' not in text and text.count('.IsCompleted') == 1
    assign, slot, task, guard = re.search(r'(\b(\w+) = (\w+)\.GetAwaiter\(\);)\s+'
                                         r'(if \(!\(\2\.IsCompleted\)\))', text).groups()
    # Verify which native successor each arm renders. Compile the recovered
    # decision with the host TaskAwaiter; no timer or game loop is required.
    slow, fast = text.split(guard,1)[1].split('else',1)
    assert f'this.<>u__1 = {slot};' in slow and f'AwaitUnsafeOnCompleted(ref {slot}, this);' in slow
    get_result = f'{slot}.GetResult();'
    assert get_result in fast and get_result not in slow
    _run_awaiter_paths(tmp_path, assign, slot, task, guard, suspend_if_true=True)


def test_fusion_shutdown_awaiter_after_join(body, tmp_path):
    import re

    text = body('<ShutdownSession>d__61', 'MoveNext', 0x180590020)
    assert 'sub_1811f7db0' not in text
    # 0x1805904b1: TEST AL; JNE to GetResult. The suspension path is the
    # fall-through, unlike the earlier Computer case. Check both destinations.
    m = re.search(r'Task (\w+) = [\w.]+\.CleanUpRunner\(\);\s+'
                  r'((\w+) = \1\.GetAwaiter\(\);)\s+(if \(\3\.IsCompleted\))\s*'
                  r'\{[^{}]*?goto (L_\w+);\s*\}', text)
    assert m is not None
    task, assign, slot, guard, label = m.groups()
    assert re.search(rf'{label}:\s*{slot}\.GetResult\(\);', text)
    assert re.match(rf'\s*(\w+)\.<>1__state = 0;\s*\1\.<>u__1 = {slot};\s*'
                    rf'\(\1\.<>t__builder\)\.AwaitUnsafeOnCompleted\(ref {slot}, \1\);', text[m.end():])
    _run_awaiter_paths(tmp_path, assign, slot, task, guard, suspend_if_true=False)


def test_fusion_shutdown_yield_schedules_once(body, tmp_path):
    import re
    from dotnet_case import run_case

    text = body('<ShutdownSession>d__61', 'MoveNext', 0x180590020)
    # Compile the recovered producers, receiver copy and exact condition.
    # Verify the ref passed to the builder on that edge is the copied awaiter.
    m = re.search(r'(?P<setup>[\w.]+ (?P<outer>\w+) = System\.Threading\.Tasks\.Task\.Yield\(\) /\* shared implementation \*/;\s+'
                  r'[\w.]+ (?P<value>\w+) = (?P=outer)\.GetAwaiter\(\) /\* shared implementation \*/;\s+'
                  r'(?P<slot>\w+) = (?P=value);\s+if \(!\((?P=value)\.IsCompleted\)\))\s*\{(?P<slow>[^{}]*)\}', text)
    assert m and 'sub_180641940' not in m['setup']
    assert f'.<>u__2 = {m["value"]};' in m['slow'] and f'AwaitUnsafeOnCompleted(ref {m["slot"]},' in m['slow']
    # The structurer makes two mutually exclusive copies of one native
    # GetResult site. The pending arm schedules and exits; the resumed arm
    # restores the saved byte and consumes it before starting the next task.
    assert '.GetResult()' not in m['slow']
    resume = text.split('else if (this.<>1__state == 1)', 1)[1].split('Task.Delay(50)', 1)[0]
    assert f'{m["slot"]} = this.<>u__2;' in resume and 'this.<>u__2 = default;' in resume
    result, = re.findall(rf'^\s*({m["slot"]}\.GetResult\(\);)$', resume, flags=re.M)
    assert text.count(result) == 2 and 'sub_180507120/*shared body' not in resume
    runner = tmp_path / 'runner'
    runner.mkdir()
    (runner / 'Program.cs').write_text('''using System;
using System.Runtime.CompilerServices;
using System.Threading;
var queue = new Pump();
var previous = SynchronizationContext.Current;
try {
    SynchronizationContext.SetSynchronizationContext(queue);
    int suspended = 0, resumed = 0;
    var calls = new Counter();
    YieldAwaitable.YieldAwaiter ''' + m['slot'] + ''' = default;
''' + m['setup'] + ''' {
        suspended++;
        ''' + m['slot'] + '.UnsafeOnCompleted(() => { resumed++; Resume(new Observed(' + m['slot'] + ''', calls)); });
    } else { throw new Exception("yield took the synchronous path"); }
    if (suspended != 1 || queue.Posts != 1 || resumed != 0 || calls.Results != 0) throw new Exception("did not suspend once");
    queue.Drain();
    if (resumed != 1 || queue.Posts != 1 || calls.Results != 1) throw new Exception("did not consume the result once");
    Console.WriteLine("suspended=1, queued=1, resumed=1; GetResult before drain=0, after drain=1");
} finally { SynchronizationContext.SetSynchronizationContext(previous); }
static void Resume(Observed ''' + m['slot'] + ''') {
''' + result + '''
}
class Counter { public int Results; }
readonly struct Observed {
    readonly YieldAwaitable.YieldAwaiter inner;
    readonly Counter counter;
    public Observed(YieldAwaitable.YieldAwaiter inner, Counter counter) { this.inner = inner; this.counter = counter; }
    public void GetResult() { counter.Results++; inner.GetResult(); }
}''' + _PUMP_CS, encoding='utf-8')
    print(run_case(tmp_path, runner).strip())


def test_gamer_tags_consumes_result_before_virtual_query(body, tmp_path):
    import re
    from dotnet_case import run_case

    text = body('<OnEnable>d__4', 'MoveNext', 0x1806f8c50)
    assert 'sub_180507120' not in text
    resume = text.split('if (this.<>1__state == 0)', 1)[1]
    match = re.search(r'(\w+) = this\.<>u__1;\s+this\.<>u__1 = default;\s+this\.<>1__state = -1;\s+'
                      r'((?:\1)\.GetResult\(\);\s+PlatformManager (\w+) = PlatformManager\.__field_Instance;\s+'
                      r'[\w.]+<NetPlayerData> \w+ = \3\.GetLobbyMembers\(\);)', resume)
    assert match and text.count(match[1] + '.GetResult();') == 1
    # Run the emitted GetResult and the following virtual dispatch verbatim.
    # The observer counts real .NET YieldAwaiter.GetResult invocations.
    runner = tmp_path / 'runner'; runner.mkdir()
    (runner / 'Program.cs').write_text('''using System;
using System.Collections.Generic;
using System.Runtime.CompilerServices;
using System.Threading;
var previous = SynchronizationContext.Current;
var queue = new Pump(); SynchronizationContext.SetSynchronizationContext(queue);
try {
    var awaiter = System.Threading.Tasks.Task.Yield().GetAwaiter();
    var platform = new Derived(); PlatformManager.__field_Instance = platform;
    if (awaiter.IsCompleted) throw new Exception("expected suspension");
    awaiter.UnsafeOnCompleted(() => Resume(new Observed(awaiter)));
    if (queue.Posts != 1 || Trace.Events.Count != 0) throw new Exception("ran before resumption");
    queue.Drain();
    if (queue.Posts != 1 || string.Join(",", Trace.Events) != "GetResult,GetLobbyMembers")
        throw new Exception("wrong count or order");
    Console.WriteLine("queued=1, before resume: no calls; after resume: GetResult, GetLobbyMembers");
} finally { SynchronizationContext.SetSynchronizationContext(previous); }
static void Resume(Observed ''' + match[1] + ') {\n' + match[2] + '''
}
static class Trace { public static List<string> Events = new(); }
readonly struct Observed {
    readonly YieldAwaitable.YieldAwaiter inner;
    public Observed(YieldAwaitable.YieldAwaiter inner) { this.inner = inner; }
    public void GetResult() { Trace.Events.Add("GetResult"); inner.GetResult(); }
}
class NetPlayerData { }
namespace System.Collections.Generic { class List_1<T> : List<T> { } }
abstract class PlatformManager {
    public static PlatformManager __field_Instance;
    public abstract List_1<NetPlayerData> GetLobbyMembers();
}
class Derived : PlatformManager {
    public override List_1<NetPlayerData> GetLobbyMembers() { Trace.Events.Add("GetLobbyMembers"); return new(); }
}''' + _PUMP_CS, encoding='utf-8')
    print(run_case(tmp_path, runner).strip())


def _run_awaiter_paths(tmp_path, assign, slot, task, guard, *, suspend_if_true):
    from dotnet_case import run_case

    suspend = f'Suspends++; {slot}.UnsafeOnCompleted(Finish);'
    yes, no = (suspend, 'Finish();') if suspend_if_true else ('Finish();', suspend)
    runner = tmp_path / 'runner'
    runner.mkdir()
    (runner / 'Program.cs').write_text('''using System;
using System.Runtime.CompilerServices;
using System.Threading.Tasks;
var p = new Probe();
var immediate = p.Check(Task.CompletedTask);
if (!immediate.IsCompletedSuccessfully || p.Suspends != 0 || p.Finishes != 1) throw new Exception("ready");
Console.WriteLine("completed: suspended=0, finished=1");
var source = new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);
p = new Probe(); var deferred = p.Check(source.Task);
if (deferred.IsCompleted || p.Suspends != 1 || p.Finishes != 0) throw new Exception("not ready");
source.SetResult(true); await deferred.WaitAsync(TimeSpan.FromSeconds(5));
if (p.Suspends != 1 || p.Finishes != 1) throw new Exception("resume");
Console.WriteLine("pending: suspended=1, finished=0 before release, finished=1 after");
p = new Probe(); var faulted = p.Check(Task.FromException(new InvalidOperationException()));
try { await faulted; throw new Exception("missing fault"); } catch (InvalidOperationException) { }
if (p.Suspends != 0 || p.Finishes != 1) throw new Exception("faulted task was not complete");
Console.WriteLine("faulted: suspended=0, GetResult propagated the fault");
class Probe {
    public int Suspends, Finishes;
''' + f'    public Task Check(Task {task}) {{\n        TaskAwaiter {slot};\n        {assign}\n' + '''
        var done = new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);
        void Finish() {
            Finishes++;
            try { ''' + f'{slot}.GetResult();' + ''' done.SetResult(true); } catch (Exception e) { done.SetException(e); }
        }
''' + guard + ' { ' + yes + ' } else { ' + no + ' }\n'
        + '        return done.Task;\n    }\n}\n', encoding='utf-8')
    print(run_case(tmp_path, runner).strip())


def test_transaction_coroutine_after_cleanup(body, tmp_path):
    from dotnet_case import run_case

    text = body('TransactionManager', 'Rpc_StartTransaction', 0x18060e640)
    line, = (s.strip() for s in text.splitlines() if 'SpawnItems()' in s)
    assert 'this.StartCoroutine(this.SpawnItems()) /* shared implementation */;' in line
    runner = tmp_path / 'runner'
    runner.mkdir()
    (runner / 'Program.cs').write_text('''using System;
using System.Collections;
var tx = new Transaction(); var other = new Transaction();
tx.AfterCleanup();
if (tx.Trace != "build;start;" || other.Trace != "" || !ReferenceEquals(tx.Routine, tx.Started))
    throw new Exception("wrong receiver, iterator, order or count");
Console.WriteLine("same receiver and iterator; " + tx.Trace);
tx.Fail = true;
try { tx.AfterCleanup(); throw new Exception("factory returned"); } catch (InvalidOperationException) { }
if (tx.Trace != "build;start;build;") throw new Exception("start after factory failure");
namespace UnityEngine { class Coroutine {} }
class Transaction {
    public bool Fail; public string Trace = "";
    public IEnumerator Started; public IEnumerator Routine = new int[1].GetEnumerator();
    IEnumerator SpawnItems() { Trace += "build;"; if (Fail) throw new InvalidOperationException(); return Routine; }
    UnityEngine.Coroutine StartCoroutine(IEnumerator it) { Trace += "start;"; Started = it; return new(); }
    public void AfterCleanup() {
''' + line + '\n}\n}', encoding='utf-8')
    print(run_case(tmp_path, runner).strip())


def test_computer_coroutine_starts_on_captured_instance(tmp_path):
    import re
    from dotnet_case import run_case
    from il2cpp.cli import main

    metadata, binary = [os.getenv('IL2CSHARP_' + n) for n in ('METADATA', 'BINARY')]
    if not (binary and metadata and sha256(binary) == '163982a57e2e6e4c8f4558f6e968e9ba73e422d9b736cb4efef1e0674d5ab806'
            and sha256(metadata) == 'bd92f36e124ec3b236ef6bc3ead42eed3c322b15f403ecdc078f7c8dee5c75e1'):
        pytest.skip('requires the second Shift v31 build')
    out = tmp_path / 'out'
    assert main(['il2csharp','--metadata',metadata,'--binary',binary,'--only','Assembly-CSharp',
                 '--types','Computer','--strict','-o',str(out)]) == 0
    source = (out / 'Assembly-CSharp/Computer.cs').read_text(encoding='utf-8')
    method = source.split('// RVA: 0x6BDC60 VA: 0x1806BDC60',1)[1].split('// RVA:',1)[0]
    capture, name = re.findall(r'(Computer (\w+) = this\.__4__this;)', method)[0]
    assert method.index(capture) < method.index('if (this.__1__state') < method.index('Task.Delay(')
    starts = re.findall(r'(Coroutine \w+ = ' + name + r'\.StartCoroutine\((\w+)\.CheckStringForProfanityAsync\((\w+)\.m_action, (\w+)\)\) /\* shared implementation \*/;)', method)
    assert len(starts) == 1 and method.count('.CheckStringForProfanityAsync(') == 1 and 'sub_182bf4460' not in method
    call, factory, closure, action = starts[0]
    runner = tmp_path / 'runner'; runner.mkdir()
    (runner / 'Program.cs').write_text('''using System;
using System.Collections;
foreach (bool cleanup in new[] {false, true}) {
  foreach (bool fail in new[] {false, true}) {
    var saved = new Computer(); var replacement = new Computer(); var state = new State {__4__this = saved};
    var api = new Platform {Fail = fail};
    try { state.Run(cleanup, replacement, api); if (fail) throw new Exception("missing factory failure"); }
    catch (InvalidOperationException) when (fail) { }
    if (api.Builds != 1 || saved.Starts != (fail ? 0 : 1) || replacement.Starts != 0 ||
        (!fail && !ReferenceEquals(saved.Started, api.Routine)) || state.__4__this != replacement)
      throw new Exception("receiver, routine or count mismatch");
    Console.WriteLine($"{(cleanup ? "cleanup" : "normal")}: factory={api.Builds}, original starts={saved.Starts}, replacement starts={replacement.Starts}");
  }
}
class Coroutine { }
class Computer {
  public int Starts; public IEnumerator Started;
  public Coroutine StartCoroutine(IEnumerator it) { Starts++; Started = it; return new Coroutine(); }
}
class Args { public string m_action = "search"; }
class Platform {
  public bool Fail; public int Builds; public IEnumerator Routine = new int[1].GetEnumerator();
  public IEnumerator CheckStringForProfanityAsync(string text, object callback) {
    Builds++; if (Fail) throw new InvalidOperationException(); return Routine;
  }
}
struct State {
  public Computer __4__this;
  public void Run(bool cleanup, Computer replacement, Platform ''' + factory + ''') {
''' + capture + '''
    try { if (cleanup) throw new ApplicationException(); this.__4__this = replacement; }
    catch (ApplicationException) { this.__4__this = replacement; }
''' + f'    var {closure} = new Args(); object {action} = new object();\n' + call + '\n  }\n}', encoding='utf-8')
    print(run_case(tmp_path, runner).strip())


def test_shelf_cleanup_starts_fresh_captured_receiver_once(tmp_path):
    import re
    from dotnet_case import run_case
    from il2cpp.cli import main

    metadata, binary = [os.getenv('IL2CSHARP_' + name) for name in ('METADATA', 'BINARY')]
    if not binary or not metadata or sha256(binary) != '163982a57e2e6e4c8f4558f6e968e9ba73e422d9b736cb4efef1e0674d5ab806':
        pytest.skip('requires second Shift v31 build')
    out = tmp_path / 'out'
    assert main(['il2csharp','--metadata',metadata,'--binary',binary,'--only','Assembly-CSharp',
                 '--types','ShelfManager','--strict','-o',str(out)]) == 0
    source = (out / 'Assembly-CSharp/ShelfManager.cs').read_text(encoding='utf-8')
    text = source.split('private void InitObjectQueue()', 1)[1].split('private void Update()', 1)[0]
    assert 'sub_182bf4460' not in text
    lines = text.splitlines()
    idx, = [i for i,s in enumerate(lines) if 'this.StartCoroutine(' in s]
    snippet = '\n'.join(lines[idx-2:idx+1])
    assert 'this.StopCoroutine(' in lines[idx-3] and snippet.count('new ShelfManager.') == 1
    state = re.search(r'new ShelfManager\.(\w+)\(0\)', snippet)[1]
    runner = tmp_path / 'runner'; runner.mkdir()
    (runner / 'Program.cs').write_text('''using System;
using System.Collections;
using UnityEngine;
var shelf = new ShelfManager(); shelf.Run();
if (shelf.Trace != "capture;start;" || ShelfManager.STATE.Allocated != 1 ||
    !ReferenceEquals(ShelfManager.STATE.Created, shelf.Started))
    throw new Exception("iterator identity or order");
Console.WriteLine("one new iterator; captured original shelf; same iterator started once");
namespace UnityEngine { class Coroutine {} }
class ShelfManager {
    public string Trace = ""; public IEnumerator Started;
    public class STATE : IEnumerator {
        public static int Allocated; public static STATE Created;
        public ShelfManager __4__this { set { Owner = value; Owner.Trace += "capture;"; } }
        public ShelfManager Owner; public STATE(int state) { if (state != 0) throw new Exception(); Allocated++; Created = this; }
        public object Current => null; public bool MoveNext() => false; public void Reset() { }
    }
    Coroutine StartCoroutine(IEnumerator e) { if (((STATE)e).Owner != this) throw new Exception(); Trace += "start;"; Started = e; return new(); }
    public void Run() {
'''.replace('STATE', state) + snippet + '\n}\n}', encoding='utf-8')
    print(run_case(tmp_path, runner).strip())


def test_purchase_coroutine_preserves_both_instance_reads(body, tmp_path):
    import re
    from dotnet_case import run_case

    text = body('PurchaseManager', 'Rpc_PurchaseObj', 0x18058c960)
    assert 'sub_182bf4460' not in text
    # Both textual copies must capture the two native reads, in order.
    slices = re.findall(r'(SaveManager (\w+) = SaveManager\.Instance;\s+'
                        r'SaveManager (\w+) = SaveManager\.Instance;\s+'
                        r'UnityEngine\.Coroutine \w+ = \2\.StartCoroutine\(\3\.WaitForArraysThenSetArsenal\(\)\) /\* shared implementation \*/;)', text)
    assert len(slices) == 2
    runner = tmp_path / 'runner'
    runner.mkdir()
    (runner / 'Program.cs').write_text('''using System;
using System.Collections;
using System.Collections.Generic;
foreach (bool first in new[] { true, false }) {
    var receiver = new SaveManager(); var factory = new SaveManager();
    SaveManager.Inputs.Enqueue(receiver); SaveManager.Inputs.Enqueue(factory);
    Purchase(first);
    if (SaveManager.Inputs.Count != 0 || receiver.Starts != 1 || receiver.Builds != 0 ||
        factory.Starts != 0 || factory.Builds != 1 || !ReferenceEquals(receiver.Started,factory.Routine))
        throw new Exception("receiver, iterator, count or order mismatch");
    Console.WriteLine("two singleton reads; second built once; first started the same iterator once");
}
static void Purchase(bool first) {
    if (first) {
''' + slices[0][0] + '\n} else {\n' + slices[1][0] + '''
}}
namespace UnityEngine { class Coroutine {} }
class SaveManager {
    public static Queue<SaveManager> Inputs = new(); public static SaveManager Instance => Inputs.Dequeue();
    public int Starts, Builds; public IEnumerator Started; public IEnumerator Routine = new int[1].GetEnumerator();
    public IEnumerator WaitForArraysThenSetArsenal() { Builds++; return Routine; }
    public UnityEngine.Coroutine StartCoroutine(IEnumerator value) { Starts++; Started = value; return new(); }
}
''', encoding='utf-8')
    print(run_case(tmp_path, runner).strip())


def test_car_coroutine_forwarding_once(body, tmp_path):
    from dotnet_case import run_case

    for name in ('StartCoroutine', 'StartCoroutine_Auto'):
        wrapper = body('MonoBehaviour', name, 0x182bf4460)
        assert wrapper.count('StartCoroutineManaged2_Injected(this.m_CachedPtr, routine)') == 1
    call, = [s.strip() for s in body('CarComputer','SearchOnAllClients',0x180600dd0).splitlines()
             if ' /* shared implementation */' in s]
    tail, = [s.strip() for s in body('CarComputer','Search',0x180600f60).splitlines()
             if ' /* shared implementation */' in s]
    assert call.count('this.StartCoroutine(') == tail.count('this.StartCoroutine(') == 1
    result = call.split(' = ')[0].split()[-1]
    runner = tmp_path / 'runner'
    runner.mkdir()
    (runner / 'Program.cs').write_text('''using System;
using System.Collections;
var a = new Car(); var b = new Car();
var handle = a.Call(); b.Tail();
if (!ReferenceEquals(handle, a.Handle)) throw new Exception("lost return");
foreach (var receiver in new[]{a,b}) {
    if (receiver.Starts != 1 || receiver.platformManager1.Calls != 1 ||
        !ReferenceEquals(receiver.Started, receiver.platformManager1.Routine)) throw new Exception("dispatch");
}
Console.WriteLine("call and tail: each built 1 iterator, started it once on the correct receiver");
namespace UnityEngine { class Coroutine { } }
class Source {
    public int Calls; public IEnumerator Routine = new int[1].GetEnumerator();
    public IEnumerator CheckStringForProfanityAsync(string text, object callback) { Calls++; return Routine; }
}
class Query { public string text = "query", searched = "query"; }
class Car {
    public Source platformManager1 = new Source(); Query searchField = new Query(), obj9 = new Query();
    object action11 = new object(); public UnityEngine.Coroutine Handle = new UnityEngine.Coroutine();
    public IEnumerator Started; public int Starts;
    UnityEngine.Coroutine StartCoroutine(IEnumerator r) { Starts++; Started = r; return Handle; }
    public UnityEngine.Coroutine Call() {
''' + call + '\nreturn ' + result + ';\n}\npublic void Tail() {\n' + tail + '\n}\n}', encoding='utf-8')
    print(run_case(tmp_path, runner).strip())


def test_sanitise_text_three_ordered_reads(body, tmp_path):
    from dotnet_case import run_case

    lifted = body('TMPForceSingleLine', 'SanitiseText', 0x180637210)
    assert 'sub_182aab550' not in lifted
    assert lifted.count('= this.inputField.caretPosition /* shared getter */;') == 3
    runner = tmp_path / 'runner'
    runner.mkdir()
    (runner / 'Program.cs').write_text(r'''using System;
using System.Collections.Generic;
foreach (var (label, input, active, changes) in new[] {
    ("LF", "a\nb", false, true), ("CR", "a\rb", false, true),
    ("CRLF", "a\r\nb", false, true), ("plain", "abc", false, false),
    ("reentrant", "a\nb", true, false)}) {
    var probe = new Probe {isSanitising = active};
    probe.SanitiseText(input);
    string trace = string.Join(",", probe.inputField.Events);
    if (trace != (changes ? "read:99,text:a b,caret:3,read:7,anchor:7,read:8,focus:8" : "") || probe.isSanitising != active)
        throw new Exception(label + ": " + trace);
    Console.WriteLine(label + ": " + (trace == "" ? "no reads" : trace));
}
class Field {
    public List<string> Events = new();
    private Queue<int> values = new(new[] {99, 7, 8});
    public int Read() { int n = values.Dequeue(); Events.Add("read:" + n); return n; }
    public void SetTextWithoutNotify(string text) => Events.Add("text:" + text);
    public int caretPosition { get => Read(); set => Events.Add("caret:" + value); }
    public int selectionAnchorPosition { set => Events.Add("anchor:" + value); }
    public int selectionFocusPosition { set => Events.Add("focus:" + value); }
}
class Probe {
    public bool isSanitising; public Field inputField = new();
    public void SanitiseText(string text) {
''' + lifted + '\n}\n}', encoding='utf-8')
    print(run_case(tmp_path, runner).strip())


def test_tmp_caret_aliases_have_identical_behaviour(body, tmp_path):
    from dotnet_case import run_case

    props = ('caretSelectPositionInternal', 'caretPosition', 'selectionFocusPosition')
    bodies = [body('TMP_InputField', 'get_' + prop, 0x182aab550) for prop in props]
    assert len(set(bodies)) == 1
    runner = tmp_path / 'runner'
    runner.mkdir()
    (runner / 'Program.cs').write_text('''using System;
var f = new Field();
foreach (bool readOnly in new[] {true, false}) {
    f.m_ReadOnly = readOnly; f.reads = 0;
    foreach (var n in new[] {f.caretSelectPositionInternal, f.caretPosition, f.selectionFocusPosition})
        if (n != (readOnly ? 11 : 14)) throw new Exception("wrong position");
    if (f.reads != (readOnly ? 0 : 3)) throw new Exception("composition reads");
}
Console.WriteLine("3 equivalent getters: read-only=11, composing=14");
class Field {
    public bool m_ReadOnly; public int reads; public int m_CaretSelectPosition = 11;
    public string compositionString { get { reads++; return "abc"; } }
''' + '\n'.join(f'public int {p} {{ get {{\n{b}\n}} }}' for p,b in zip(props,bodies)) +
        '\n}', encoding='utf-8')
    print(run_case(tmp_path, runner).strip())


def test_rotation_stability_cloned_owner_read_order(body, tmp_path):
    import re
    from dotnet_case import run_case

    text = body('LAM_RotationStability', 'OnPreLateUpdate', 0x180694cc0)
    pairs = re.findall(r'(float (real\d+) = this\._forwV\.GetFloat\(\);\s+'
                       r'(?:[\w.]+\.)?LegsAnimator (legsAnimator\d+) = base\.Owner;)', text)
    assert len(pairs) == 2 and pairs[0][1:] != pairs[1][1:]
    assert not re.search(r'object obj\d+ = base\.Owner;', text)
    arms = [statements + f'\nreturn ({number}, {owner});' for statements, number, owner in pairs]
    runner = tmp_path / 'runner'
    runner.mkdir()
    (runner / 'Program.cs').write_text('''using System;
using FIMSpace.FProceduralAnimation;
foreach (bool first in new[] { true, false }) {
    var next = new LegsAnimator();
    var module = new Module();
    module._forwV.Read = () => { module.Log += "float;"; module.Stored = next; return 7.5f; };
    var (value, owner) = module.Read(first);
    if (module.Log != "float;owner;" || value != 7.5f || !ReferenceEquals(owner, next))
        throw new Exception("lost type or changed order");
    Console.WriteLine((first ? "original" : "copy") + ": " + module.Log + " replacement captured");
}
namespace FIMSpace.FProceduralAnimation {
    class LegsAnimator { }
    class Variable { public Func<float> Read; public float GetFloat() => Read(); }
    class ModuleBase {
        public LegsAnimator Stored = new LegsAnimator(); public string Log = "";
        protected LegsAnimator Owner { get { Log += "owner;"; return Stored; } }
    }
    class Module : ModuleBase {
        public Variable _forwV = new Variable();
        public (float, LegsAnimator) Read(bool first) {
            if (first) {
''' + arms[0] + '\n} else {\n' + arms[1] + '\n}\n}\n}\n}', encoding='utf-8')
    print(run_case(tmp_path, runner).strip())


def test_saved_float_precedes_second_owner_read(body, tmp_path):
    from dotnet_case import run_case

    update = body('LAM_ParamChanger_UnglueOnAngle', 'OnUpdate', 0x1806946b0)
    assert 'sub_180513390' not in update and update.count('GetFloat()') == 1
    assert update.count('base.Owner') == 2
    runner = tmp_path / 'runner'
    runner.mkdir()
    (runner / 'Program.cs').write_text('''using System;
using FIMSpace.FProceduralAnimation;
var old = new LegsAnimator { __field_IsMovingBlend = 0.75f, UnglueOn = -99f };
var next = new LegsAnimator { __field_IsMovingBlend = 0.25f, UnglueOn = -99f };
var module = new Module { Storage = old }; int calls = 0;
module._UnglueAngleOnMoving.Read = () => { ++calls; module.Storage = next; return 30f; };
module.Update();
if (calls != 1 || module.Reads != 2 || old.UnglueOn != 15f || next.UnglueOn != -99f)
    throw new Exception("changed value or evaluation order");
Console.WriteLine("GetFloat calls=1, Owner reads=2, old.UnglueOn=15, replacement unchanged");
module._UnglueAngleOnMoving.Read = () => throw new InvalidOperationException();
try { module.Update(); throw new Exception("missing exception"); } catch (InvalidOperationException) { }
if (module.Reads != 3 || next.UnglueOn != -99f) throw new Exception("read after throw");
namespace FIMSpace.FProceduralAnimation {
    class LegsAnimator {
        public float __field_IsMovingBlend, UnglueOn;
        public class Variable { public Func<float> Read; public float GetFloat() => Read(); }
    }
    class ModuleBase {
        public LegsAnimator Storage; public int Reads;
        protected LegsAnimator Owner { get { ++Reads; return Storage; } }
    }
    class Module : ModuleBase {
        private float initialUnglueOn = 10f;
        public LegsAnimator.Variable _UnglueAngleOnMoving = new LegsAnimator.Variable();
        public void Update() {
''' + update + '\n}\n}\n}', encoding='utf-8')
    print(run_case(tmp_path, runner).strip())


def test_module_update_captures_shared_owner_reference(body, tmp_path):
    import re
    from dotnet_case import run_case

    update = body('LAM_ImpulsesOnStopAndOnLand', 'OnUpdate', 0x180693420)
    assert 'sub_180513390' not in update
    read, local = re.search(r'((?:[\w.]+\.)?LegsAnimator (\w+) = base\.Owner;)', update).groups()
    getter = body('LegsAnimatorControlModuleBase', 'get_Owner', 0x180513390)
    assert getter == 'return this.__field_Owner;'
    runner = tmp_path / 'runner'
    runner.mkdir()
    (runner / 'Program.cs').write_text('''using System;
using FIMSpace.FProceduralAnimation;
var a = new LegsAnimator(); var b = new LegsAnimator(); var module = new Module();
if (module.ReadAndSwap(a) != null || !ReferenceEquals(module.ReadAndSwap(b), a) ||
    !ReferenceEquals(module.ReadAndSwap(null), b) || module.ReadAndSwap(null) != null)
    throw new Exception("field identity or load order");
Console.WriteLine("Owner read: null, first object, second object, null");
namespace FIMSpace.FProceduralAnimation {
    class LegsAnimator { }
    class ModuleBase {
        private LegsAnimator __field_Owner;
        protected LegsAnimator Owner { get { ''' + getter + ''' } }
        protected void Replace(LegsAnimator next) => __field_Owner = next;
    }
    class Module : ModuleBase {
        public LegsAnimator ReadAndSwap(LegsAnimator next) {
''' + read + '\nReplace(next); return ' + local + ';\n}\n}\n}', encoding='utf-8')
    output = run_case(tmp_path, runner)
    assert 'Owner read: null, first object, second object, null' in output
    print(output.strip())


def test_long_virtual_comparer_evaluates_result_once(body):
    text = body('TagValue', 'Equals', 0x182ced8f0)
    assert text.count('.Equals(new UnityEngine.Color') == 1
    assert 'EqualityComparer`' not in text and '= 0; //' not in text


def test_null_guard_retains_write_null_fallback(body):
    text = body('JProperty', 'WriteTo', 0x181e09990)
    assert '?.WriteTo' not in text
    assert 'if (this._content._token != null)' in text and 'writer.WriteNull();' in text


def test_visitor_fallback_calls_base_once(body, tmp_path):
    from dotnet_case import run_case

    text = body('NoThrowExpressionVisitor', 'VisitConditional', 0x181db7f60)
    assert 'if (node.IfFalse.NodeType == ExpressionType.Throw)' in text
    fallback = text.splitlines()[-1].strip()
    assert fallback == 'return base.VisitConditional(node); /* tail */'

    # Compile the lifted fallback verbatim against the host ExpressionVisitor.
    # Count entries at both levels so a recursive override fails immediately.
    runner = tmp_path / 'runner'
    runner.mkdir()
    (runner / 'Program.cs').write_text('''using System.Linq.Expressions;
var probe = new Probe();
var node = Expression.Condition(Expression.Constant(true), Expression.Constant(11), Expression.Constant(22));
if (probe.Visit(node) != node || probe.Entries != 1 || probe.BaseCalls != 1)
    throw new System.Exception("wrong fallback dispatch");
System.Console.WriteLine($"override={probe.Entries}, base={probe.BaseCalls}");
class CountingVisitor : ExpressionVisitor {
    public int BaseCalls;
    protected override Expression VisitConditional(ConditionalExpression node) {
        ++BaseCalls;
        return base.VisitConditional(node);
    }
}
class Probe : CountingVisitor {
    public int Entries;
    protected override Expression VisitConditional(ConditionalExpression node) {
        if (++Entries > 1) throw new System.Exception("recursive fallback");
''' + fallback + '\n    }\n}\n', encoding='utf-8')
    assert 'override=1, base=1' in run_case(tmp_path, runner)


def test_save_system_clears_both_caller_values(body, tmp_path):
    from dotnet_case import run_case

    lines = body('SaveSystem', 'TryGetDayAndMoney', 0x1805b13a0).splitlines()
    start = next(i for i, line in enumerate(lines) if line.strip() == 'day = 0;')
    stores = lines[start:start + 2]
    assert [s.strip() for s in stores] == ['day = 0;', 'money = 0f;']
    assert not any(('(byte*)day' in s or '(byte*)money' in s) and s.endswith(' = 0;') for s in lines)
    runner = tmp_path / 'runner'
    runner.mkdir()
    (runner / 'Program.cs').write_text('''int day = 19;
float money = -27.5f;
Clear(ref day, ref money);
if (day != 0 || System.BitConverter.SingleToInt32Bits(money) != 0) throw new System.Exception();
System.Console.WriteLine("day=0, moneyBits=0");
static void Clear(ref int day, ref float money) {
''' + '\n'.join(stores) + '\n}', encoding='utf-8')
    assert 'day=0, moneyBits=0' in run_case(tmp_path, runner)


def test_save_system_checked_cast_all_paths(body, tmp_path):
    from dotnet_case import run_case

    recovered = body('SaveSystem', 'TryGetDayAndMoney', 0x1805b13a0)
    assert 'SaveData saveData = obj11 as SaveData;' in recovered
    assert 'day = saveData.curDay;' in recovered and 'money = saveData.money;' in recovered
    assert 'typeHierarchy' not in recovered and '(byte*)' not in recovered
    runner = tmp_path / 'runner'
    runner.mkdir()
    # Compile the entire lifted body verbatim. Supply only the Unity path and
    # a controlled deserializer; File.Exists, FileStream and Close are real.
    (runner / 'Program.cs').write_text('''using System;
using System.IO;
using Formatter = System.Runtime.Serialization.Formatters.Binary.BinaryFormatter;
File.WriteAllBytes(Path.Combine(UnityEngine.Application.persistentDataPath, "7save.data"), new byte[1]);
void Check(string label, object input, bool ok, int wantDay, float wantMoney) {
    Formatter.Value = input;
    int count = Formatter.Calls, day = -1;
    float money = -999f;
    bool result = TryGetDayAndMoney(7, ref day, ref money);
    if (result != ok || day != wantDay || BitConverter.SingleToInt32Bits(money) != BitConverter.SingleToInt32Bits(wantMoney)
        || Formatter.Calls != count + 1 || Formatter.Last.CanRead) throw new Exception(label);
    Console.WriteLine($"{label}: {result}, {day}, {money.ToString(System.Globalization.CultureInfo.InvariantCulture)}");
}
Check("null", null, false, 0, 0f);
Check("wrong type", new object(), false, 0, 0f);
Check("save", new SaveData { curDay = 37, money = 123.75f }, true, 37, 123.75f);
Check("subclass", new ExtendedSave { curDay = -8, money = -19.25f }, true, -8, -19.25f);
static bool TryGetDayAndMoney(int saveSlot, ref int day, ref float money) {
''' + recovered + '''
}
class SaveData { public int curDay; public float money; }
class ExtendedSave : SaveData { }
namespace UnityEngine { static class Application { public static string persistentDataPath = Environment.CurrentDirectory; } }
namespace System.Runtime.Serialization.Formatters.Binary {
    class BinaryFormatter {
        public static object Value;
        public static Stream Last;
        public static int Calls;
        public object Deserialize(Stream s) { Calls++; Last = s; return Value; }
    }
}''', encoding='utf-8')
    result = run_case(tmp_path, runner)
    for line in ('null: False, 0, 0', 'wrong type: False, 0, 0', 'save: True, 37, 123.75', 'subclass: True, -8, -19.25'):
        assert line in result
        print(line)


def test_typed_exception_from_initialized_slot(body, tmp_path):
    from dotnet_case import run_case

    reset = body('<LerpToNormal>d__7', 'System.Collections.IEnumerator.Reset', 0x180609c70)
    assert 'throw notSupportedException' in reset
    runner = tmp_path / 'runner'
    runner.mkdir()
    (runner / 'Program.cs').write_text('''try { Reset(); throw new System.Exception("returned"); }
catch (System.NotSupportedException) { System.Console.WriteLine("typed throw OK"); }
static void Reset() {
''' + reset + '\n}', encoding='utf-8')
    assert 'typed throw OK' in run_case(tmp_path, runner)


def test_hittable_damage_comparisons_use_string_values(body, tmp_path):
    from dotnet_case import run_case

    text = body('Hittable', 'Rpc_Hit', 0x1806f6c30)
    line, = (s.strip() for s in text.splitlines() if 'this.bludgeonDamageMultiplier' in s
             and 'this.fireDamageMultiplier' in s and 'this.normalDamageMultiplier' in s)
    for kind in ('Normal', 'Fire', 'Bludgeon'):
        assert f'damageType == "{kind}"' in line
    assert 'sub_181b0a390' not in text
    runner = tmp_path / 'runner'
    runner.mkdir()
    (runner / 'Program.cs').write_text('''using System;
var hit = new Hit();
foreach (var (label, expected) in new[] {("Normal", 6f), ("Fire", 10f), ("Bludgeon", 14f), ("fire", 2f), ("Other", 2f)}) {
    string value = new string(label.ToCharArray());
    if (object.ReferenceEquals(value, label) || hit.Apply(2f, value) != expected) throw new Exception(label);
    Console.WriteLine($"{label}: {expected}");
}
if (hit.Apply(2f, null) != 2f) throw new Exception("null");
Console.WriteLine("null: 2");
class Hit {
    float normalDamageMultiplier = 3f, fireDamageMultiplier = 5f, bludgeonDamageMultiplier = 7f;
    public float Apply(float damage, string damageType) {
''' + line + '\nreturn ' + line.split()[1] + ';\n}\n}', encoding='utf-8')
    print(run_case(tmp_path, runner).strip())


def test_inventory_item_type_uses_value_equality(body, tmp_path):
    import re
    from dotnet_case import run_case

    text = body('<Rpc_CMD_PlaceItem>d__290', 'MoveNext', 0x18053f990)
    assert 'ComputeStringHash(this.type)' in text and 'sub_181b0a390' not in text
    comparison, = re.findall(r'if \((this\.type == "atm")\)', text)
    runner = tmp_path / 'runner'
    runner.mkdir()
    (runner / 'Program.cs').write_text('''using System;
var label = new string("atm".ToCharArray());
if (ReferenceEquals(label, "atm")) throw new Exception("test needs distinct strings");
foreach (var (name, value, expected) in new[] {
    ("distinct equal", label, true), ("case differs", "ATM", false),
    ("different item", "books", false), ("null", (string)null, false)}) {
    var actual = new Placement { type = value }.IsAtm();
    if (actual != expected) throw new Exception(name);
    Console.WriteLine($"{name}: {actual}");
}
struct Placement {
    public string type;
    public bool IsAtm() => ''' + comparison + ';\n}', encoding='utf-8')
    print(run_case(tmp_path, runner).strip())


def test_computer_search_token_uses_string_equality(body, tmp_path):
    import re
    from dotnet_case import run_case

    text = body('Computer', 'GetAdvancedSearchScore', 0x1806a59b0)
    assert 'sub_181b0a390' not in text
    decl,token,array,index,comparison = re.search(r'(string (\w+) = (\w+)\[(\w+)\];)\s+if \((\2 == search)\)',text).groups()
    assert f'string[] {array} = candidate.Split(' in text
    assert text.count('.Split(')==2  # separate query and candidate arrays, including the loop bounds
    second, = re.findall(r'bool \w+ = (text\d+ == text\d+);', text)
    left, right = second.split(' == ')
    runner = tmp_path / 'runner'
    runner.mkdir()
    (runner / 'Program.cs').write_text('''using System;
var a = new string("milk".ToCharArray());
var b = new string("milk".ToCharArray());
if (ReferenceEquals(a, b)) throw new Exception("test needs distinct objects");
foreach (var (label, token, query, want) in new[] {
    ("distinct equal", a, b, true), ("case differs", a, "Milk", false),
    ("query null", a, null, false), ("token null", null, a, false),
    ("both null", (string)null, (string)null, true)}) {
    if (First(new[] {"unused", token}, 1, query) != want || Second(token, query) != want)
        throw new Exception(label);
    Console.WriteLine($"{label}: {want}");
}
''' + f'static bool First(string[] {array}, int {index}, string search) {{ {decl} {array}[{index}]="replacement"; return {comparison}; }}\n' +
        f'static bool Second(string {left}, string {right}) => {second};\n', encoding='utf-8')
    print(run_case(tmp_path, runner).strip())
