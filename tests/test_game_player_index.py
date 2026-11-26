"""Receiver homes and unchecked signed semantics for shared player-index reads."""
import re

import pytest

from dotnet_case import run_case
from il2cpp import Lifter
from il2cpp.decrement_getter import _member
from test_game_shift_shared_flags import body, shift_runtime

pytestmark=pytest.mark.game


def test_player_ref_index_comparer_and_captured_field(body,tmp_path):
    compare=body('<>c','<OnSceneLoadDone>b__74_0',0x18056efe0)
    assert compare.count('.AsIndex /* shared getter */')==2 and 'sub_' not in compare
    prop=body('PlayerRef','get_AsIndex',0x1808a4940)
    assert prop==body('PlayerRef','get_PlayerId',0x1808a4940)
    move=body('<OnPlayerJoined>d__68','MoveNext',0x18056dd60)
    sites=re.findall(r'int (\w+) = this\.player\.AsIndex /\* shared getter \*/;',move)
    assert len(sites)==4
    add=body('PerPlayerVolumeUI','TryAddRow',0x1805823a0)
    row=re.search(r'Fusion\.PlayerRef (\w+) = player;\s+int (\w+) = \1\.AsIndex /\* shared getter \*/;',add)
    assert row
    runner=tmp_path/'runner';runner.mkdir()
    (runner/'Program.cs').write_text('''using System;
using Fusion;
int[] raw={int.MinValue,-17,-1,0,1,2,99,int.MaxValue};var state=new State();
foreach(int a in raw){var left=new PlayerRef(a); int id=unchecked(a-1); state.player=left;
    if(left.AsIndex!=id || left.PlayerId!=id || state.Read()!=id || Case.Row(left)!=id)throw new Exception("wrong index");
    foreach(int b in raw)if(Case.Compare(left,new PlayerRef(b))!=id.CompareTo(unchecked(b-1)))throw new Exception("wrong home or compare");
}
Console.WriteLine("64 player comparisons; both properties and captured/parameter reads wrap Int32.MinValue to Int32.MaxValue");
namespace Fusion { struct PlayerRef {private int _index;public PlayerRef(int raw)=>_index=raw;
    public int AsIndex {get {\n'''+prop+'\n}} public int PlayerId {get {\n'+prop+'''\n}} } }
class State {public PlayerRef player; public int Read(){\n'''+
        re.search(r'int '+sites[0]+r' = this\.player\.AsIndex /\* shared getter \*/;',move)[0]+'\nreturn '+sites[0]+''';} }
class Case {public static int Row(PlayerRef player){\n'''+row[0]+'\nreturn '+row[2]+''';}
public static int Compare(PlayerRef a,PlayerRef b){\n'''+compare+'\n}}', encoding='utf-8')
    print(run_case(tmp_path,runner).strip())


@pytest.mark.parametrize('defect',['increment','unsigned storage','extra overlapping field'])
def test_decrement_alias_requires_unambiguous_signed_storage(shift_runtime,monkeypatch,defect):
    meta,il=shift_runtime;l=Lifter(il); m=meta.methods[60938]; owner=m.declaring
    assert _member(l,m.addr,owner)[:2]==('AsIndex','_index')
    if defect=='increment':
        read=il.bin.read
        monkeypatch.setattr(il.bin,'read',lambda a,n:b'\x8b\x01\xff\xc0\xc3' if (a,n)==(m.addr,5) else read(a,n))
    else:
        fs=list(meta.type_fields(meta.typedefs[owner])); signed=next(f for f in fs if meta.fields[f].name=='_index')
        if defect=='unsigned storage':
            uint=next(i for i,t in enumerate(il.types) if t and il._closed_type_key(t)==(9,0) and not t[1]&0x50)
            monkeypatch.setattr(meta.fields[signed],'type',uint)
        else:
            monkeypatch.setattr(meta.fields[fs[0]],'type',meta.fields[signed].type)
    assert _member(l,m.addr,owner) is None
