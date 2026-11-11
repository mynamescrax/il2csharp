"""Portable unit tests for the declaration gate (no fixture needed)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from diff_decls import (
    _mkey,
    _strip_genargs,
    _top_commas,
    canon_full,
    canon_member,
    canon_owner,
    canon_short,
    diff_dump_extracted,
)


def test_canon_owner_plain():
    assert canon_owner("System.String") == "System.String"
    assert canon_owner("NS.Outer+Inner") == "NS.Outer.Inner"


def test_canon_owner_generated():
    assert canon_owner("NS.Outer+<Foo>d__13") == "NS.Outer._Foo_d__13"
    assert canon_owner("A.<>c") == "A.__c"


def test_canon_member_plain():
    assert canon_member("Add") == "Add"
    assert canon_member(".ctor") == ".ctor"
    assert canon_member("event") == "event_"


def test_canon_member_explicit():
    assert canon_member("System.IDisposable.Dispose") == \
        "System.IDisposable.Dispose"
    assert canon_member("<.cctor>b__271_0") == "__cctor_b__271_0"


def test_canon_short():
    assert canon_short("System.IntPtr") == "IntPtr"
    assert canon_short("global::System.String") == "String"
    assert canon_short("System.Collections.Generic.List<T>") == "List"
    assert canon_short("ICollection_1") == "ICollection"
    assert canon_short("-") is None


def test_top_commas():
    assert _top_commas("a,b") == ["a", "b"]
    assert _top_commas("Dictionary<K,V>,int") == ["Dictionary<K,V>", "int"]
    assert _top_commas("A<B<C,D>,E>,F") == ["A<B<C,D>,E>", "F"]
    assert _top_commas("") == [""]


def test_strip_genargs():
    assert _strip_genargs("List<T>") == "List"
    assert _strip_genargs("A<B<C>>") == "A"
    assert _strip_genargs("plain") == "plain"


def test_mkey_orders_none_first():
    a = ("M", "Foo", None, 0, 0, 1)
    b = ("M", "Foo", "Bar", 0, 0, 1)
    assert sorted([b, a], key=_mkey)[0] == a


DUMP_BASE = [
    "A mscorlib.dll",
    "T System.Widget kind=class base=- ebase=- ifaces=System.IDisposable",
    "M System.Widget..ctor s=0 g=0 f=0x1886 ()->void",
    "M System.Widget.Dispose s=0 g=0 f=0x1c6 ()->void",
    "F System.Widget._count s=0 int",
]


def test_diff_clean():
    ext = [
        "A mscorlib.dll",
        "T System.Widget kind=class base=- ebase=- ifaces=IDisposable",
        "M System.Widget..ctor s=0 g=0 n=0",
        "M System.Widget.Dispose s=0 g=0 n=0",
        "F System.Widget._count s=0 g=0 n=0",
    ]
    assert diff_dump_extracted(DUMP_BASE, ext) == []


def test_diff_missing_extra():
    ext = [
        "A mscorlib.dll",
        "T System.Widget kind=class base=- ebase=- ifaces=-",
        "M System.Widget..ctor s=0 g=0 n=0",
        "M System.Widget.Bogus s=1 g=0 n=2",
    ]
    probs = diff_dump_extracted(DUMP_BASE, ext)
    assert any("base mismatch" in p for p in probs)
    assert any("missing emitted member" in p and "Dispose" in p for p in probs)
    assert any("extra emitted member" in p and "Bogus" in p for p in probs)


def test_diff_ifaces_rest():
    ext = [
        "A mscorlib.dll",
        "T System.Widget kind=class base=- ebase=- ifaces=System.IDisposable,System.ICloneable",
        "M System.Widget..ctor s=0 g=0 n=0",
        "M System.Widget.Dispose s=0 g=0 n=0",
        "F System.Widget._count s=0 g=0 n=0",
    ]
    probs = diff_dump_extracted(DUMP_BASE, ext)
    assert any("ifaces mismatch" in p for p in probs)
    assert not any("missing emitted member" in p for p in probs)
    assert not any("extra emitted member" in p for p in probs)


def test_diff_field_static():
    dump = [
        "A mscorlib.dll",
        "T System.Widget kind=class base=- ebase=- ifaces=-",
        "F System.Widget._count s=1 int",
    ]
    ext0 = [
        "A mscorlib.dll",
        "T System.Widget kind=class base=- ebase=- ifaces=-",
        "F System.Widget._count s=0 g=0 n=0",
    ]
    assert diff_dump_extracted(dump, ext0) != []
    ext1 = [
        "A mscorlib.dll",
        "T System.Widget kind=class base=- ebase=- ifaces=-",
        "F System.Widget._count s=1 g=0 n=0",
    ]
    assert diff_dump_extracted(dump, ext1) == []


def test_diff_property():
    dump = [
        "A mscorlib.dll",
        "T N.W kind=class base=- ebase=- ifaces=-",
        "P N.W.P s=0 get=1 set=1 string",
    ]
    ext = [
        "A mscorlib.dll",
        "T N.W kind=class base=- ebase=- ifaces=-",
        "P N.W.P s=0 g=0 n=3",
    ]
    assert diff_dump_extracted(dump, ext) == []
    ext2 = [
        "A mscorlib.dll",
        "T N.W kind=class base=- ebase=- ifaces=-",
        "P N.W.P s=0 g=0 n=1",
    ]
    assert diff_dump_extracted(dump, ext2) != []


def test_diff_event():
    dump = [
        "A mscorlib.dll",
        "T N.W kind=class base=- ebase=- ifaces=-",
        "E N.W.E s=0 add=1 rem=1 System.Action",
    ]
    ext = [
        "A mscorlib.dll",
        "T N.W kind=class base=- ebase=- ifaces=-",
        "E N.W.E s=0 g=0 n=3",
    ]
    assert diff_dump_extracted(dump, ext) == []
    ext2 = [
        "A mscorlib.dll",
        "T N.W kind=class base=- ebase=- ifaces=-",
        "E N.W.E s=1 g=0 n=3",
    ]
    assert diff_dump_extracted(dump, ext2) != []


def test_diff_indexer():
    dump = [
        "A mscorlib.dll",
        "T N.W kind=class base=- ebase=- ifaces=-",
        "P N.W.this s=0 get=1 set=1 int",
    ]
    ext = [
        "A mscorlib.dll",
        "T N.W kind=class base=- ebase=- ifaces=-",
        "P N.W.this s=0 g=0 n=3",
    ]
    assert diff_dump_extracted(dump, ext) == []


def test_extract_property_event_indexer(tmp_path):
    from extract_decls import extract_tree
    src = ("namespace N { class W { public int P { get; set; } "
           "public event System.Action E; "
           "public int this[int i] => i; "
           "public static string S { get; } } }")
    (tmp_path / "W.cs").write_text(src, encoding="utf-8")
    lines, nfiles, skipped = extract_tree(str(tmp_path), "X.dll")
    assert "P N.W.P s=0 g=0 n=3 int" in lines
    assert "E N.W.E s=0 g=0 n=3 System.Action" in lines
    assert "P N.W.this s=0 g=0 n=1 int" in lines
    assert "P N.W.S s=1 g=0 n=1 string" in lines


def test_diff_invoke():
    dump = [
        "A mscorlib.dll",
        "T N.Cb kind=delegate base=- ebase=- ifaces=-",
        "M N.Cb.Invoke s=0 g=0 f=0x1c6 (int)->void",
    ]
    ext = [
        "A mscorlib.dll",
        "T N.Cb kind=delegate base=- ebase=- ifaces=-",
        "M N.Cb.Invoke s=0 g=0 n=1",
    ]
    assert diff_dump_extracted(dump, ext) == []
    ext2 = [
        "A mscorlib.dll",
        "T N.Cb kind=delegate base=- ebase=- ifaces=-",
        "M N.Cb.Invoke s=0 g=0 n=2",
    ]
    assert diff_dump_extracted(dump, ext2) != []


def test_strict_clean_and_fires():
    dump = [
        "A mscorlib.dll",
        "T N.W kind=class base=- ebase=- ifaces=-",
        "M N.W.Add s=0 g=0 f=0x1c6 (int,string)->void",
        "F N.W._count s=0 int",
    ]
    ext = [
        "A mscorlib.dll",
        "T N.W kind=class base=- ebase=- ifaces=-",
        "M N.W.Add s=0 g=0 n=2 (int,string)->void",
        "F N.W._count s=0 g=0 n=0 int",
    ]
    assert diff_dump_extracted(dump, ext) == []
    assert diff_dump_extracted(dump, ext, strict=True) == []
    ext2 = [
        "A mscorlib.dll",
        "T N.W kind=class base=- ebase=- ifaces=-",
        "M N.W.Add s=0 g=0 n=2 (string,int)->void",
        "F N.W._count s=0 g=0 n=0 string",
    ]
    assert diff_dump_extracted(dump, ext2) == []
    probs = diff_dump_extracted(dump, ext2, strict=True)
    assert any("type spelling mismatch" in p for p in probs)


def test_extract_delegate_invoke(tmp_path):
    from extract_decls import extract_tree
    src = ("namespace N { public delegate void Cb(int x); "
           "public delegate int D2(string a, string b); }")
    (tmp_path / "D.cs").write_text(src, encoding="utf-8")
    lines, nfiles, skipped = extract_tree(str(tmp_path), "X.dll")
    assert "M N.Cb.Invoke s=0 g=0 n=1 (int)->void" in lines
    assert "M N.D2.Invoke s=0 g=0 n=2 (string,string)->int" in lines


def test_canon_full():
    assert canon_full("System.String") == canon_full("string") == "String"
    assert canon_full("global::System.Int32") == "Int32"
    assert canon_full("System.Collections.Generic.List<int>") == \
        canon_full("List<Int32>")
    assert canon_full("int[]") == "Int32[]"
    assert canon_full("int?") == "Int32?"
    assert canon_full("System.Collections.Generic.Dictionary<string,System.Collections.Generic.List<int>>") == \
        "Dictionary<String,List<Int32>>"
    assert canon_full("int") != canon_full("string")
    assert canon_full("(int,string)") != canon_full("(string,int)")
    assert canon_full("(System.Type)->System.Exception") == \
        canon_full("(Type)->Exception")
    assert canon_full("(System.Threading.Thread)->void") == \
        canon_full("(Thread)->Void")
    assert canon_full("()->void") == "()->Void"
    assert canon_full(
        "Interop.Kernel32.TIME_DYNAMIC_ZONE_INFORMATION.<DaylightName>e__FixedBuffer") == \
        canon_full(
        "Interop.Kernel32.TIME_DYNAMIC_ZONE_INFORMATION._DaylightName_e__FixedBuffer") == \
        "_DaylightName_e__FixedBuffer"
    assert canon_full(
        "System.Threading.SparselyPopulatedArray_1<System.Threading.CancellationCallbackInfo>[]") == \
        canon_full("SparselyPopulatedArray_1<CancellationCallbackInfo>[]") == \
        "SparselyPopulatedArray<CancellationCallbackInfo>[]"
    assert canon_full(
        "System.Collections.Generic.Dictionary<string,System.Collections.Generic.List<int>>") == \
        canon_full("Dictionary<String,List<Int32>>") == \
        "Dictionary<String,List<Int32>>"
    assert canon_full("") == ""


def test_strict_pairs_spell_first():
    dump = [
        "A mscorlib.dll",
        "T N.W kind=class base=- ebase=- ifaces=-",
        "M N.W.M s=0 g=0 f=0x1c6 (System.String)->void",
        "M N.W.M s=0 g=0 f=0x1c6 (System.Int32)->void",
    ]
    ext = [
        "A mscorlib.dll",
        "T N.W kind=class base=- ebase=- ifaces=-",
        "M N.W.M s=0 g=0 n=1 (String)->void",
        "M N.W.M s=0 g=0 n=1 (Int32)->void",
    ]
    assert diff_dump_extracted(dump, ext, strict=True) == []


def test_diff_qualifier_compatible():
    dump = [
        "A m.dll",
        "T N.W kind=class base=- ebase=- ifaces=-",
        "M N.W.System.IDisposable.Dispose s=0 g=0 f=0x1c6 ()->void",
    ]
    ext = [
        "A m.dll",
        "T N.W kind=class base=- ebase=- ifaces=-",
        "M N.W.Dispose s=0 g=0 n=0",
    ]
    assert diff_dump_extracted(dump, ext) == []


def test_diff_qualifier_mismatch():
    dump = [
        "A m.dll",
        "T N.W kind=class base=- ebase=- ifaces=-",
        "M N.W.System.IDisposable.Dispose s=0 g=0 f=0x1c6 ()->void",
    ]
    ext = [
        "A m.dll",
        "T N.W kind=class base=- ebase=- ifaces=-",
        "M N.W.System.ICloneable.Dispose s=0 g=0 n=0",
    ]
    probs = diff_dump_extracted(dump, ext)
    assert any("qualifier mismatch" in p for p in probs)


def test_diff_kind_base_ebase():
    dump = [
        "A m.dll",
        "T N.E kind=enum base=- ebase=uint ifaces=-",
    ]
    ext_ok = [
        "A m.dll",
        "T N.E kind=enum base=- ebase=uint ifaces=-",
    ]
    assert diff_dump_extracted(dump, ext_ok) == []
    ext_bad = [
        "A m.dll",
        "T N.E kind=class base=- ebase=- ifaces=-",
    ]
    probs = diff_dump_extracted(dump, ext_bad)
    assert any("kind mismatch" in p for p in probs)
    assert any("ebase mismatch" in p for p in probs)
