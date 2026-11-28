from dotnet_case import run_case
from il2cpp.split_field import read_piece,write_piece
from types import SimpleNamespace as NS
from il2cpp.expr import Expr, _R4_TY
import pytest


@pytest.mark.parametrize('bad',['stale echo','different tile','gap'])
def test_capture_declines_before_emitting_or_suppressing_a_move(bad):
    from il2cpp.split_field import split_step
    from iced_x86 import Decoder
    ty=(17,0x11<<16);e=Expr('&t42',ty,'ptr');e._stack_offset=-24
    ins=Decoder(64,bytes.fromhex('f20f1000'),ip=0x1100).decode()
    vals=[Expr('t42.'+s,_R4_TY,'float') for s in 'xyz'];events=[];copies={}
    if bad=='gap':vals[1]=None
    if bad=='different tile':vals[1]=Expr('t43.y',_R4_TY,'float')
    l=NS(regs={'RAX':e,'RBX':Expr('this')},_last_sret=(0x1040,Expr('&t42',ty,'ptr') if bad=='stale echo' else e),
         slot_types={'t42':ty},rsp_delta=-56,_stack_piece=lambda off,w,t:vals[(off+24)//4],emit=lambda *args:events.append(args))
    assert not split_step(l,ins,('first',0x1040,ty,('x','y','z'),'this.dest','RBX',32,56,(8,4)),copies)
    assert not events and not copies and 'XMM0' not in l.regs


def test_observer_of_destination_sees_only_the_bytes_written_so_far(tmp_path):
    # Exercise the same per-instruction renderer as the complete callers.
    # The probe has an independent reference to the destination, not a
    # copy reconstructed from the source or from symbolic stack tiles.
    fs=('x','y','z')
    xy=write_piece('dst',fs,8,'bits')
    z=write_piece('dst',fs,4,'height')
    program='''using System;using System.Runtime.InteropServices;
float F(uint x)=>BitConverter.Int32BitsToSingle(unchecked((int)x));
bool Same(float a,float b)=>BitConverter.SingleToInt32Bits(a)==BitConverter.SingleToInt32Bits(b);
var initial=new Vec{x=3,y=-9,z=F(0x7fc00123)};var sample=new Vec{x=F(0x80000000),y=F(1),z=F(0xffc04567)};
foreach(bool zFirst in new[]{false,true}) foreach(bool throws in new[]{false,true}){
 var h=new Holder{before=0x62,d=initial,after=0x73};Vec src=sample;ref Vec alias=ref h.d;
 long bits='''+read_piece('src',fs,8)+'''; float height='''+read_piece('src',fs,4)+''';src=new Vec{x=17,y=18,z=19};
 var fault=new ApplicationException();int probes=0;
 void Probe(){probes++;Vec seen=h.d; if(zFirst?(!Same(seen.z,sample.z)||!Same(seen.x,initial.x)||!Same(seen.y,initial.y)):
        (!Same(seen.x,sample.x)||!Same(seen.y,sample.y)||!Same(seen.z,initial.z)))throw new Exception("wrong intermediate bytes");
    if(h.before!=0x62||h.after!=0x73)throw new Exception("canary overwrite");if(throws)throw fault;}
 Exception ex=null;try{Copy(ref alias,bits,height,zFirst,Probe);}catch(Exception e){ex=e;}
 if(probes!=1||!ReferenceEquals(ex,throws?fault:null)||h.before!=0x62||h.after!=0x73)throw new Exception("observer fault/canary",ex);
 if(!Same(alias.x,throws&&zFirst?initial.x:sample.x)||!Same(alias.y,throws&&zFirst?initial.y:sample.y)||!Same(alias.z,throws&&!zFirst?initial.z:sample.z))throw new Exception("wrong final lanes");
}
Console.WriteLine("independently aliased XYZ: both store orders, old Z after XY, canaries, NaN bits and throwing observer");
static void Copy(ref Vec dst,long bits,float height,bool zFirst,Action observe){if(zFirst){
'''+z+'\nobserve();\n'+xy+'\n}else{\n'+xy+'\nobserve();\n'+z+'''
}}
[StructLayout(LayoutKind.Sequential)]struct Vec{public float x,y,z;}
[StructLayout(LayoutKind.Sequential)]class Holder{public int before;public Vec d;public int after;}
'''
    r=tmp_path/'r';r.mkdir();(r/'Program.cs').write_text(program,encoding='utf8');print(run_case(tmp_path,r))
