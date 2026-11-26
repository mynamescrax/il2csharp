import json
import re

import pytest

from dotnet_case import run_case
from il2cpp import Decompiler,Lifter
from il2cpp.emitter import Emitter
from test_game_shift_shared_flags import shift_runtime

pytestmark=pytest.mark.game


def test_uid_platform_dictionary_constructor(shift_runtime,tmp_path):
    meta,il=shift_runtime; out=tmp_path/'out'; emit=Emitter(il,str(out)); m=meta.methods[26515]; td=meta.typedefs[m.declaring]
    reader=meta.typedefs[meta.methods[30384].declaring]
    for t in (td,reader): emit._emit_one_top(t,meta.images[m.image],str(t.index))
    source=next(out.rglob(f'{td.index}.cs')).read_text(encoding='utf-8'); decl=next(out.rglob(f'{reader.index}.cs')).read_text(encoding='utf-8')
    prop=re.search(r'    private NetworkDictionary_2<[^\n]+> _fuidToPlatformID\s*\{.*?^    }',source,re.S|re.M)
    typ=re.search(r'internal partial struct (\w+) : IElementReaderWriter_1<',decl); assert prop and typ
    code=prop[0];name=typ[1]; assert code.count(name+'.GetInstance()')==2 and 'NativeSlice' not in code
    runner=tmp_path/'runner';runner.mkdir()
    (tmp_path/'Directory.Build.props').write_text('<Project><PropertyGroup><AllowUnsafeBlocks>true</AllowUnsafeBlocks></PropertyGroup></Project>',encoding='utf8')
    (runner/'Program.cs').write_text('''using System;
using System.Collections.Generic;
using Fusion;
using Fusion.CodeGen;
using Key=Fusion.NetworkString_1<Fusion._64>;
unsafe {
    int* original=stackalloc int[2];int* changed=original+1;var service=new UIDService();
    var key=new Reader();var value=new Reader();
    foreach(string mode in new[]{"ok","null value reader","null pointer","key throws","value throws","ctor throws"}) {
        var log=new List<string>();service.Ptr=mode=="null pointer"?null:original;
        READER.Next=()=>{if(log.Count==0){log.Add("key");service.Ptr=changed;if(mode=="key throws")throw new ApplicationException();return key;}
            log.Add("value");if(mode=="value throws")throw new ApplicationException();return mode=="null value reader"?null:value;};
        NetworkDictionary_2<Key,Key>.Construct=()=>{log.Add("ctor");if(mode=="ctor throws")throw new ApplicationException();};
        string fail=null;
        try {var got=service.Read();if(got.Data!=original || got.Capacity!=7 || got.Key!=key || got.Value!=(mode=="null value reader"?null:value))throw new Exception("wrong ctor args");}
        catch(ApplicationException){fail="initiated";}catch(InvalidOperationException ex){fail=ex.Message;}
        string want=mode switch {"null pointer"=>"","key throws"=>"key","value throws"=>"key;value",_=>"key;value;ctor"};
        if(string.Join(";",log)!=want || fail!=(mode=="null pointer"?MESSAGE:mode.EndsWith("throws")?"initiated":null))throw new Exception(mode);
        Console.WriteLine(mode+": "+(log.Count==0?"guard before readers":string.Join(";",log)));
    }
}
class UIDService:NetworkBehaviour {public NetworkDictionary_2<Key,Key> Read()=>_fuidToPlatformID;
PROPERTY
}
class Reader:IElementReaderWriter_1<Key>{}
namespace Fusion.CodeGen {internal partial struct READER {internal static Func<IElementReaderWriter_1<Key>> Next;public static IElementReaderWriter_1<Key> GetInstance()=>Next();}}
namespace Fusion {
    class NetworkBehaviour {internal unsafe int* Ptr;} struct _64 {} struct NetworkString_1<T> {} interface IElementReaderWriter_1<T> {}
    unsafe struct NetworkDictionary_2<K,V> {public int* Data;public int Capacity;public IElementReaderWriter_1<K> Key;public IElementReaderWriter_1<V> Value;
        public static Action Construct;public NetworkDictionary_2(int* data,int capacity,IElementReaderWriter_1<K> keyReaderWriter,IElementReaderWriter_1<V> valReaderWriter){
            Construct();Data=data;Capacity=capacity;Key=keyReaderWriter;Value=valReaderWriter;}}
}'''.replace('PROPERTY',code).replace('READER',name).replace('MESSAGE',json.dumps(meta.string_literal(18897))),encoding='utf8')
    print(run_case(tmp_path,runner).strip())


@pytest.mark.parametrize('defect',['other class arguments','different pointer','swapped readers','partial default','wrong context','wrong throw'])
def test_dictionary_getter_requires_complete_abi(shift_runtime,monkeypatch,defect):
    from il2cpp.dictionary_ctor import dictionary_constructor_body
    from iced_x86 import Decoder
    m,il=shift_runtime;d=Decompiler(Lifter(il));md=m.methods[26515];td=m.typedefs[md.declaring];d.eh=il.eh_regions(md.addr);seq,_=d._decode(md)
    assert dictionary_constructor_body(d.L,md,td,seq,d.eh)
    if defect=='other class arguments':
        old=il.decode_slot;other=old(0x183c0be50)
        monkeypatch.setattr(il,'decode_slot',lambda a:other if a==0x183c0b7c0 else old(a))
    else:
        ip,byte,delta={'different pointer':(0x180594b0c,-1,1),'swapped readers':(0x180594b00,-1,3),
                       'partial default':(0x180594b17,-1,16),'wrong context':(0x180594b22,-1,8),'wrong throw':(0x180594b8a,1,1)}[defect]
        k=next(k for k,i in enumerate(seq) if i.ip==ip);data=bytearray(il.bin.read(ip,seq[k].len));data[byte]^=delta
        seq=seq[:k]+list(Decoder(64,bytes(data),ip=ip))+seq[k+1:]
    assert dictionary_constructor_body(d.L,md,td,seq,d.eh) is None
