"""Compile the real material-selection bodies against instrumented Unity operations."""
import pytest

from dotnet_case import run_case
from test_game_shift_shared_flags import body, shift_runtime

pytestmark = pytest.mark.game


def test_material_selection_and_saved_renderer(body,tmp_path):
    demo = body('WFX_Demo', 'selectMaterial', 0x18052d160)
    newer = body('WFX_Demo_New', 'selectMaterial', 0x18052aa60)
    rope = body('RopeSweepCut', 'AddMouseLine', 0x180523780)
    hook = body('GrapplingHook','Awake',0x18051a900)
    for text in (demo,newer):
        assert text.count('GetComponent<UnityEngine.Renderer>') == text.count('.sharedMaterial =') == 12
    assert all('sub_182bcb460' not in s for s in (demo,newer,rope,hook))
    assert 'sub_182bcb180' not in rope and 'AddComponent<UnityEngine.LineRenderer>()' in rope
    runner = tmp_path/'runner'; runner.mkdir()
    (runner/'Program.cs').write_text('''using System;
using System.Collections.Generic;
using UnityEngine;
foreach(bool revised in new[]{false,true}) foreach(string key in new[]{"Concrete","Wood","Metal","Checker","Other"}) {
    var d=new Demo {groundTextureStr=key}; var log=new List<string>();
    var wall=new Material(); var floor=new Material();
    d.Value=name=>{log.Add("read:"+name);return name.EndsWith("Wall")?wall:floor;};
    var r0=new Renderer(); var r1=new Renderer(); var r2=new Renderer();
    Func<Renderer> source=()=>{log.Add("floor");return r0;}; if(revised)d.ground.Lookup=source;else d.Lookup=source;
    GameObject Walls(int n,Renderer r)=>new GameObject { Root=new Transform { Child=i=>{
        if(i!=n)throw new Exception("wrong or cached wall");log.Add("child"+i);return new Transform { Lookup=()=>r }; } } };
    r0.Set=v=>{if(v!=floor)throw new Exception("floor value");d.walls=Walls(0,r1);log.Add("write0");};
    r1.Set=v=>{if(v!=wall)throw new Exception("wall value");d.walls=Walls(1,r2);log.Add("write1");};
    r2.Set=v=>{if(v!=wall)throw new Exception("wall value");log.Add("write2");};
    if(revised)d.New();else d.Old();
    var f=key.ToLowerInvariant();var want=key=="Other"?"":$"floor;read:{f};write0;child0;read:{f}Wall;write1;child1;read:{f}Wall;write2";
    if(string.Join(";",log)!=want)throw new Exception(key+": "+string.Join(";",log));
}
var missing=new Demo {groundTextureStr="Wood",Lookup=()=>null,Value=_=>throw new Exception("early material read")};
try { missing.Old();throw new Exception("null renderer accepted"); }catch(NullReferenceException){}
Console.WriteLine("both material selectors: four surfaces, unmatched name, ordered ground/wall writes; null renderer before argument");
foreach(string mode in new[]{"ok","null material","find throws","ctor throws","write throws"}) {
    var log=new List<string>(); var r=new Rope(); var before=new LineRenderer(); var during=new LineRenderer();var after=new LineRenderer();
    var colorTarget=new Material();var shader=new Shader(); Material created=null;
    GameObject.Make=()=>{log.Add("add");return before;};
    Shader.Resolve=name=>{if(name!="Unlit/Color")throw new Exception("shader name");log.Add("find"); r.lineRenderer=during;
        if(mode=="find throws")throw new InvalidOperationException();return shader;};
    Material.Init=(obj,s)=>{if(s!=shader)throw new Exception("shader identity");created=obj; log.Add("ctor");
        if(mode=="ctor throws")throw new InvalidOperationException();};
    before.Set=v=>{log.Add("saved.set"); if(v!=created || v==null)throw new Exception("material identity");
        if(mode=="write throws")throw new InvalidOperationException();r.lineRenderer=after;};
    after.Get=()=>{log.Add("fresh.get"); return mode=="null material"?null:colorTarget;};
    colorTarget.Paint=v=>{log.Add("color");if(v!=Color.cyan)throw new Exception("color"); r.lineRenderer=during;};
    during.Enable=v=>{log.Add("disable");if(v)throw new Exception("enabled");};
    try { r.Add(); } catch(InvalidOperationException) when(mode.EndsWith("throws")) {log.Add("throw");}
    catch(NullReferenceException) when(mode=="null material") {log.Add("null");}
    string expected=mode switch {"ok"=>"add;find;ctor;saved.set;fresh.get;color;disable", "null material"=>"add;find;ctor;saved.set;fresh.get;null",
        "find throws"=>"add;find;throw", "ctor throws"=>"add;find;ctor;throw", _=>"add;find;ctor;saved.set;throw"};
    if(string.Join(";",log)!=expected || before.startWidth!=0.005f || before.endWidth!=0.005f || before.numCapVertices!=2)
        throw new Exception(mode+": "+string.Join(";",log));
    Console.WriteLine(mode+": "+expected);
}
namespace UnityEngine {
    class Component {public Func<Renderer> Lookup; public T GetComponent<T>() where T:Renderer => (T)Lookup();}
    class Transform : Component {public Func<int,Transform> Child; public Transform GetChild(int i)=>Child(i);}
    class GameObject {public GameObject(){} public GameObject(string name){if(name!="Mouse Line")throw new Exception("line name");}
        public Transform Root; public Transform transform=>Root; public Func<Renderer> Lookup; public T GetComponent<T>() where T:Renderer => (T)Lookup();
        public static Func<LineRenderer> Make; public T AddComponent<T>() where T:Renderer => (T)(Renderer)Make();}
    class Renderer : Component {public Func<Material> Get; public Action<Material> Set;
        public Material sharedMaterial {get=>Get();set=>Set(value);} }
    class LineRenderer : Renderer {public float startWidth,endWidth;public int numCapVertices; public Action<bool> Enable; public bool enabled {set=>Enable(value);} }
    class Shader {public static Func<string,Shader> Resolve; public static Shader Find(string name)=>Resolve(name);}
    record struct Color {public static Color cyan=>default;}
    class Material {public Material(){} public Material(Shader s){Init(this,s);}public static Action<Material,Shader> Init;
        public Action<Color> Paint; public Color color {set=>Paint(value);} }
}
class Demo : Component {
    public string groundTextureStr; public GameObject walls,ground=new(); public Func<string,Material> Value;
''' + '\n'.join(f'Material {name}=>Value("{name}");' for name in ('concrete','wood','metal','checker','concreteWall','woodWall','metalWall','checkerWall')) +
        '\npublic void Old(){\n'+demo+'\n}\npublic void New(){\n'+newer+'\n}\n}\nclass Rope { public LineRenderer lineRenderer; public void Add(){\n'+rope+'\n}\n}',encoding='utf-8')
    print(run_case(tmp_path,runner).strip())


def test_material_instance_read_and_mesh_assignment(body,tmp_path):
    import re

    awake=body('Wrappable','Awake',0x18052ea00)
    blink=body('Blinker','Blink',0x180514a90)
    hook=body('GrapplingHook','Awake',0x18051a900)
    write=re.search(r'UnityEngine\.MeshRenderer \w+ = [^;]*GetComponent<UnityEngine\.MeshRenderer>\(\);\s*'
                    r'if \([^;]+; }\s*[^;]+\.sharedMaterial = this\.material /\* shared implementation \*/;',hook)
    assert write and 'sub_' not in awake and 'sub_' not in blink
    runner=tmp_path/'runner';runner.mkdir()
    (runner/'Program.cs').write_text('''using System;
using UnityEngine;
var shared=new Material(); var instance=new Material(); var renderer=new MeshRenderer { Shared=shared, Instance=instance };
var w=new Wrapper { Found=renderer }; w.Awake();
if(w.localMaterial!=instance || renderer.InstanceReads!=1 || renderer.SharedReads!=0) throw new Exception("wrong getter");
var b=new Blinker {rend=renderer, highlightColor=new(1,2,3,4)}; b.Blink();
if(instance.color!=b.highlightColor || shared.color!=default || renderer.InstanceReads!=2) throw new Exception("wrong color target");
var h=new Hook {rope=w,material=null}; h.Assign();
if(renderer.Writes!=1 || renderer.Shared!=null || renderer.SharedReads!=0 || renderer.InstanceReads!=2) throw new Exception("setter read or cloned the material");
Console.WriteLine("two instance reads; null shared-material assignment on the MeshRenderer, no extra read");
class Wrapper : Component {public Material localMaterial; public void Awake(){
''' + awake + '''
}}
class Blinker { public Renderer rend; public Color highlightColor; public void Blink(){
''' + blink + '''
}}
class Hook { public Component rope; public Material material; public void Assign(){
''' + write[0] + '''
}}
namespace UnityEngine {
    record struct Color(float r,float g,float b,float a);
    class Material {public Color color;}
    class Component {public Renderer Found; public T GetComponent<T>() where T : Renderer => (T)Found;}
    class Renderer : Component {public Material Shared,Instance; public int Writes,SharedReads,InstanceReads;
        public Material sharedMaterial {get {SharedReads++; return Shared;} set {Writes++; Shared=value;} }
        public Material material {get {InstanceReads++;return Instance;}} }
    class MeshRenderer : Renderer { }
}''',encoding='utf-8')
    print(run_case(tmp_path,runner).strip())


@pytest.mark.parametrize('needle,change',[
    ('48 8b ea 48 8b d9','48 8b e9 48 8b da'),  # swapped managed inputs
    ('48 85 ed 74 04','48 85 ed 75 04'),        # dereference on null material
    ('48 8b d7 48 8b ce','48 8b d6 48 8b cf'),  # reversed injected arguments
    ('48 8b 7d 10','48 8b 7d 18'),              # wrong native field
])
def test_material_equivalence_rejects_other_effects(shift_runtime,monkeypatch,needle,change):
    from il2cpp import Lifter
    from il2cpp.material_setter import _alias
    _,il=shift_runtime; l=Lifter(il); va=0x182bcb460
    assert _alias(l,va) is not None
    read=il.bin.read; data=read(va,il.next_method_start(va)-va); old=bytes.fromhex(needle)
    assert data.count(old)==1; mutated=data.replace(old,bytes.fromhex(change))
    monkeypatch.setattr(il.bin,'read',lambda p,n:mutated[:n] if p==va else read(p,n))
    assert _alias(l,va) is None
