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


def test_uid_actor_dictionary_and_lazy_int_reader(shift_runtime,tmp_path):
    meta,il=shift_runtime;emit=Emitter(il,str(tmp_path/'out'));m=meta.methods[26516];td=meta.typedefs[m.declaring]
    for j in (26516,60411,30384):
        md=meta.methods[j];t=meta.typedefs[md.declaring];emit._emit_one_top(t,meta.images[md.image],str(t.index))
    def source(j): return next((tmp_path/'out').rglob(f'{meta.methods[j].declaring}.cs')).read_text(encoding='utf-8')
    prop=re.search(r'    private NetworkDictionary_2<[^\n]+> _fuidToActorID\s*\{.*?^    }',source(26516),re.S|re.M)
    cache=re.search(r'public static IElementReaderWriter_1<int> GetInstance\(\)\s*\{.*?^        }',source(60411),re.S|re.M)
    key_name=re.search(r'internal partial struct (\w+) : IElementReaderWriter_1<',source(30384))
    assert prop and cache and key_name
    assert 'NativeSlice' not in prop[0] and 'ElementReaderWriterInt32.GetInstance()' in prop[0]
    runner=tmp_path/'runner';runner.mkdir();(tmp_path/'Directory.Build.props').write_text(
        '<Project><PropertyGroup><AllowUnsafeBlocks>true</AllowUnsafeBlocks></PropertyGroup></Project>',encoding='utf8')
    (runner/'Program.cs').write_text('''using System;
using System.Collections.Generic;
using Fusion;
using Fusion.CodeGen;
using Key=Fusion.NetworkString_1<Fusion._64>;
unsafe {
    int* original=stackalloc int[1024]; int* changed=original+1; var s=new UIDService();var k=new KeyReader();var v=new IntReader();
    foreach(string mode in new[]{"cold","warm","replace cache in key","null key","null pointer","key throws","ctor throws"}) {
        ElementReaderWriterInt32.Seed(mode=="warm"?v:null);s.Ptr=mode=="null pointer"?null:original;
        var log=new List<string>();
        READER.Next=()=>{log.Add("key");s.Ptr=changed;
            if(mode!="warm" && ElementReaderWriterInt32.Peek!=null)throw new Exception("value reader fetched first");
            if(mode=="replace cache in key")ElementReaderWriterInt32.Seed(v);
            if(mode=="key throws")throw new ApplicationException("key");return mode=="null key"?null:k;};
        NetworkDictionary_2<Key,int>.OnNew=()=>{log.Add("ctor");if(ElementReaderWriterInt32.Peek==null)throw new Exception("cache unpublished");
            if(mode=="ctor throws")throw new ApplicationException("ctor");};
        string failed=null;
        try {
            var x=s.Read();if(x.Data!=original+927 || x.Capacity!=7 || !ReferenceEquals(x.Key,mode=="null key"?null:k) || !ReferenceEquals(x.Value,ElementReaderWriterInt32.Peek))
                throw new Exception("wrong address, capacity or readers");
            if(mode is "warm" or "replace cache in key"){if(!ReferenceEquals(x.Value,v))throw new Exception("replaced existing reader");}
            else if(x.Value is not ElementReaderWriterInt32 || !ReferenceEquals(x.Value,ElementReaderWriterInt32.GetInstance()))throw new Exception("wrong box type or identity");
        }catch(InvalidOperationException e){failed=e.Message;}catch(ApplicationException e){failed=e.Message;}
        string expected=mode switch {"null pointer"=>MESSAGE,"key throws"=>"key","ctor throws"=>"ctor",_=>null};
        if(failed!=expected || string.Join(";",log)!=(mode=="null pointer"?"":mode=="key throws"?"key":"key;ctor"))throw new Exception(mode);
        if(mode is "null pointer" or "key throws" && ElementReaderWriterInt32.Peek!=null)throw new Exception("early cache init");
        Console.WriteLine(mode+": "+(log.Count==0?"guard before readers":string.Join(";",log)));
    }
}
class UIDService:NetworkBehaviour { public NetworkDictionary_2<Key,int> Read()=>_fuidToActorID;
PROPERTY
}
class KeyReader:IElementReaderWriter_1<Key>{} class IntReader:IElementReaderWriter_1<int>{}
namespace Fusion.CodeGen {internal struct READER {public static Func<IElementReaderWriter_1<Key>> Next;public static IElementReaderWriter_1<Key> GetInstance()=>Next();}}
namespace Fusion {
    class NetworkBehaviour {internal unsafe int* Ptr;} struct _64 {} struct NetworkString_1<T> {} interface IElementReaderWriter_1<T>{}
    internal struct ElementReaderWriterInt32:IElementReaderWriter_1<int> {private static IElementReaderWriter_1<int> _instance;
        internal static IElementReaderWriter_1<int> Peek=>_instance;internal static void Seed(IElementReaderWriter_1<int> v)=>_instance=v;
CACHE
    }
    unsafe struct NetworkDictionary_2<K,V> {public int* Data; public int Capacity;public IElementReaderWriter_1<K> Key;public IElementReaderWriter_1<V> Value;
        public static Action OnNew;public NetworkDictionary_2(int* data,int capacity,IElementReaderWriter_1<K> key,IElementReaderWriter_1<V> value){
            OnNew();Data=data;Capacity=capacity;Key=key;Value=value;}}
}'''.replace('PROPERTY',prop[0]).replace('CACHE',cache[0]).replace('READER',key_name[1]).replace('MESSAGE',json.dumps(meta.string_literal(18896))),encoding='utf8')
    print(run_case(tmp_path,runner).strip())


@pytest.mark.parametrize('defect',['wrong closed spec','other reader type','wrong value slot','wrong cache store','wrong hot branch','different box','reloaded data','wrong factory'])
def test_actor_dictionary_rejects_unproved_factory_or_arguments(shift_runtime,monkeypatch,defect):
    from il2cpp.dictionary_ctor import dictionary_constructor_body
    from iced_x86 import Decoder
    m,il=shift_runtime;d=Decompiler(Lifter(il));md=m.methods[26516];td=m.typedefs[md.declaring];d.eh=il.eh_regions(md.addr);seq,_=d._decode(md)
    assert dictionary_constructor_body(d.L,md,td,seq,d.eh)
    if defect in ('wrong closed spec','other reader type'):
        old=il.decode_slot; a,b=(0x183c0be50,0x183c0b7c0) if defect=='wrong closed spec' else (0x183c1b308,0x183bfc558)
        monkeypatch.setattr(il,'decode_slot',lambda s:old(b) if s==a else old(s))
    elif defect=='wrong factory':
        get=m.methods[60411];old=il.bin.read
        monkeypatch.setattr(il.bin,'read',lambda p,n:old(p,n-1)+b'\xcc' if (p,n)==(get.addr,128) else old(p,n))
    else:
        ip,byte,delta={'wrong value slot':(0x180594a42,-1,8), 'wrong cache store':(0x1805949ea,-1,8),
                       'wrong hot branch':(0x1805949c8,-1,2),'different box':(0x1805949d7,1,16),'reloaded data':(0x18059498c,-1,8)}[defect]
        k=next(k for k,i in enumerate(seq) if i.ip==ip);raw=bytearray(il.bin.read(ip,seq[k].len));raw[byte]^=delta
        seq=seq[:k]+list(Decoder(64,bytes(raw),ip=ip))+seq[k+1:]
    assert dictionary_constructor_body(d.L,md,td,seq,d.eh) is None
