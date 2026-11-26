"""Compile complete callbacks with two different MethodRefs sharing one native target."""
import re

import pytest
from dotnet_case import run_case
from il2cpp import Decompiler,Lifter
from il2cpp.emitter import Emitter
from il2cpp.closed_lookup import closed_lookup_sites
from test_game_shift_shared_flags import shift_runtime

pytestmark=pytest.mark.game


def test_registered_closed_lookups_in_three_whole_methods(shift_runtime,tmp_path):
    meta,il=shift_runtime;out=tmp_path/'out';em=Emitter(il,str(out));methods=[]
    for j in (27193,23943,24309):
        md=meta.methods[j];td=meta.typedefs[md.declaring];em._emit_one_top(td,meta.images[md.image],td.name)
        src=next(out.rglob(td.name+'.cs')).read_bytes().decode('utf8');methods.append(re.search(r'^    private void '+md.name+r'\(\)\r?\n.*?^    \}',src,re.S|re.M)[0])
    harness='''using System;using System.Collections.Generic;using System.Linq;
var p=new RuntimePathVisualizer();var seeker=new Seeker();var lr=new LineRenderer();
p.Lookup=t=>t==typeof(Seeker)?seeker:t==typeof(LineRenderer)?lr:throw new Exception("wrong specialization");p.Run();
if(!ReferenceEquals(seeker,p.S)||!ReferenceEquals(lr,p.L)||lr.positionCount!=0||lr.widthMultiplier!=2.5f||!lr.useWorldSpace||!p.Log.SequenceEqual(new[]{typeof(Seeker),typeof(LineRenderer)}))throw new Exception("bad visualizer");
var ex=new ApplicationException();var s2=new Seeker();p.Lookup=t=>t==typeof(Seeker)?s2:throw ex;
try{p.Run();throw new Exception("missing fault");}catch(ApplicationException e) when(ReferenceEquals(e,ex)){}
if(!ReferenceEquals(p.S,s2)||!ReferenceEquals(p.L,lr))throw new Exception("stores reordered");
var cursor=new CursorController();var rope=new ObiRope();var c=new ObiRopeCursor();cursor.Lookup=t=>t==typeof(ObiRope)?rope:t==typeof(ObiRopeCursor)?c:throw new Exception();cursor.Run();
if(!ReferenceEquals(cursor.R,rope)||!ReferenceEquals(cursor.C,c)||!cursor.Log.SequenceEqual(new[]{typeof(ObiRope),typeof(ObiRopeCursor)}))throw new Exception("swapped cursor fields");
var f=new CameraFOVChanger();var cam=new Camera();f.Lookup=t=>t==typeof(Camera)?cam:throw new Exception();f.Run();
if(cam.fieldOfView!=70f)throw new Exception("missing default");PlayerPrefs.Value=87f;f.Run();if(cam.fieldOfView!=87f||f.Log.Count!=2)throw new Exception("wrong camera/value");
Console.WriteLine("Awake: Seeker then LineRenderer; second lookup fault preserves first store. OnEnable: rope/cursor and camera/FOV passed.");
class Component{public List<Type> Log=new();public Func<Type,Component> Lookup; public T GetComponent<T>() where T:Component{Log.Add(typeof(T));return (T)Lookup(typeof(T));}}
class Seeker:Component{} class LineRenderer:Component{public int positionCount=3;public float widthMultiplier=-1; public bool useWorldSpace;}
class ObiRope:Component{} class ObiRopeCursor:Component{} class Camera:Component{public float fieldOfView;}
class PlayerPrefs{public static float? Value;public static float GetFloat(string k,float v)=>k=="FOV"?Value??v:throw new Exception();}
class RuntimePathVisualizer:Component {Seeker seeker;LineRenderer lr;float lineWidth=2.5f;public Seeker S=>seeker;public LineRenderer L=>lr;public void Run()=>Awake();
public new T GetComponent<T>() where T:Component=>throw new Exception("dispatched hidden derived member");
'''+methods[0]+'''}class CursorController:Component{ObiRope rope;ObiRopeCursor cursor;public ObiRope R=>rope;public ObiRopeCursor C=>cursor;public void Run()=>OnEnable();
'''+methods[1]+'''}class CameraFOVChanger:Component {public void Run()=>OnEnable();
'''+methods[2]+'}'
    runner=tmp_path/'runner';runner.mkdir();(runner/'Program.cs').write_bytes(harness.encode());print(run_case(tmp_path,runner).strip())


def test_lookup_declines_clobber_and_unregistered_target(shift_runtime,monkeypatch):
    from iced_x86 import Decoder
    m,il=shift_runtime;d=Decompiler(Lifter(il));md=m.methods[27193];d.lift_method(md,m.typedefs[md.declaring]);bs=d.L._blocks
    p=lambda:closed_lookup_sites(d.L,md,bs,());site=0x1805a300b;assert p()[site][0]==174129
    si=174129;mi=il.method_specs[si][0]
    with monkeypatch.context() as mp:
        mp.setitem(il._awaiter_spec_indices[mi],si,-1);assert site not in p()
    for ip in (0x1805a3008,site):
        b,k=next((b,k) for b in bs for k,i in enumerate(b.insns) if i.ip==ip);i=b.insns[k];raw=bytearray(il.bin.read(ip,i.len))
        if ip==site:raw[-4]^=4
        else:raw[:]=bytes.fromhex('488bd3') # mov rdx,rbx, destroys the hidden MethodInfo
        alt=list(Decoder(64,bytes(raw),ip=ip));assert len(alt)==1 and alt[0].len==i.len
        with monkeypatch.context() as mp:
            mp.setattr(b,'insns',b.insns[:k]+alt+b.insns[k+1:]);assert site not in p()
