"""CLI method flags must preserve C# dispatch and abstract body rules."""
from types import SimpleNamespace as NS
import pytest
from test_review113_type_decls import (
    make_emitter, td_base, I_VOID, P, TYPES, SPELL,
)

T_PTR_TUPLE = (9, 0x0F << 16)
if T_PTR_TUPLE not in TYPES:
    TYPES.append(T_PTR_TUPLE)
SPELL[T_PTR_TUPLE] = "byte*"
I_PTR = len(TYPES) - 1


def method(flags, name="Run", addr=0):
    return NS(name=name, flags=flags, is_static=bool(flags & 0x10),
              return_type=I_VOID, generic_container=-1,
              parameter_start=0, ps=[], addr=addr, slot=0xFFFF)


@pytest.mark.parametrize("flags, expected", [
    (6, "public void Run()"),
    (6 | 0x40 | 0x100, "public virtual void Run()"),
    (6 | 0x40, "public override void Run()"),
    (6 | 0x40 | 0x20, "public sealed override void Run()"),
    (6 | 0x40 | 0x20 | 0x100, "public void Run()"),
    (6 | 0x40 | 0x400 | 0x100, "public abstract void Run()"),
    (6 | 0x40 | 0x400, "public abstract override void Run()"),
    (6 | 0x10, "public static void Run()"),
])
def test_dispatch_flags(flags, expected):
    assert make_emitter().method_sig(method(flags), td_base(flags=0x80)) == expected


def test_explicit_interface_implementation_has_no_access_or_virtual_modifier():
    m = method(1 | 0x40 | 0x20 | 0x100, "IFoo.Run")
    assert make_emitter().method_sig(m, td_base()) == "void IFoo.Run()"


@pytest.mark.parametrize("type_flags", [0x80, 0x20 | 0x80])
def test_abstract_method_does_not_lift_or_emit_body(type_flags):
    e = make_emitter()
    calls = []
    e._lift_body = lambda m, td, abstract: calls.append(abstract)
    out = []
    e.emit_method(method(6 | 0x40 | 0x400 | 0x100, addr=123),
                  td_base(flags=type_flags), out, "")
    assert calls == [True]
    assert len(out) == 1 and "; // RVA:" in out[0]
    assert "{" not in out[0]


def test_static_abstract_interface_member():
    assert make_emitter().method_sig(
        method(6 | 0x10 | 0x40 | 0x400 | 0x100),
        td_base(flags=0x20 | 0x80)) == "static abstract void Run()"


def test_generated_dispatch_declarations_compile(tmp_path):
    import shutil
    import subprocess
    from pathlib import Path
    dotnet = shutil.which("dotnet")
    if not dotnet:
        pytest.skip(".NET SDK unavailable")
    root = Path(dotnet).resolve().parent
    compilers = sorted((root / "sdk").glob("*/Roslyn/bincore/csc.dll"))
    refs = sorted((root / "packs/Microsoft.NETCore.App.Ref").glob("*/ref/net*"))
    if not compilers or not refs:
        pytest.skip("Roslyn or reference assemblies unavailable")
    e = make_emitter()
    td = td_base(flags=0x80)
    sig = lambda flags, name="Run": e.method_sig(method(flags, name), td)
    source = "\n".join([
        "public abstract class Base {",
        sig(6 | 0x40 | 0x100 | 0x400) + ";",
        sig(6 | 0x40 | 0x100, "Other") + " {} }",
        "public abstract class Middle : Base {",
        sig(6 | 0x40 | 0x400) + "; }",
        "public class Leaf : Middle {",
        sig(6 | 0x40 | 0x20) + " {}",
        sig(6 | 0x40, "Other") + " {} }",
        "public class Box_1<T> {",
        e.ctor_sig(method(6, ".ctor"), td_base(name="Box`1")) + " {}",
        e.ctor_sig(method(0x10, ".cctor"), td_base(name="Box`1")) + " {} }",
        "public interface IFoo { void Run(); }",
        "public class Implicit : IFoo {",
        sig(6 | 0x40 | 0x20 | 0x100) + " {} }",
        "public class Explicit : IFoo {",
        sig(1 | 0x40 | 0x20 | 0x100, "IFoo.Run") + " {} }",
    ])
    path = tmp_path / "Dispatch.cs"
    path.write_text(source)
    args = [dotnet, str(compilers[-1]), "/nologo", "/target:library",
            "/out:" + str(tmp_path / "Dispatch.dll"), str(path)]
    args.extend("/reference:" + str(p) for p in refs[-1].glob("*.dll"))
    result = subprocess.run(args, capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("name, expected", [("Box`1", "Box_1"), ("Pair`2", "Pair_2"), ("Plain", "Plain")])
def test_constructor_matches_emitted_type_identifier(name, expected):
    e = make_emitter()
    td = td_base(name=name)
    assert e.ctor_sig(method(6, ".ctor"), td) == f"public {expected}()"
    assert e.ctor_sig(method(0x10, ".cctor"), td) == f"static {expected}()"
    assert e.type_decl_line(td)[0].endswith(" " + expected)


def _ptr_method(**kw):
    base = dict(name="Invoker", flags=6 | 0x10, is_static=True,
                return_type=I_VOID, generic_container=-1,
                parameter_start=0, ps=[], addr=0, slot=0xFFFF)
    base.update(kw)
    return NS(**base)


def test_pointer_param_method_is_unsafe():
    e = make_emitter()
    sig = e.method_sig(_ptr_method(ps=[P(I_PTR, "message")]), td_base())
    assert sig == "public static unsafe void Invoker(byte* message)"


def test_pointer_return_method_is_unsafe():
    e = make_emitter()
    m = _ptr_method(return_type=I_PTR)
    assert e.method_sig(m, td_base()) == "public static unsafe byte* Invoker()"


def test_non_pointer_method_stays_safe():
    e = make_emitter()
    assert "unsafe" not in e.method_sig(_ptr_method(), td_base())


def test_pointer_ctor_param_is_unsafe():
    e = make_emitter()
    m = _ptr_method(name=".ctor", flags=6, is_static=False,
                    ps=[P(I_PTR, "p")])
    assert e.ctor_sig(m, td_base()) == "public unsafe Foo(byte* p)"


def test_explicit_impl_pointer_is_unsafe_without_access():
    e = make_emitter()
    m = _ptr_method(name="IFoo.Bar", flags=1 | 0x40 | 0x20 | 0x100,
                    is_static=False, ps=[P(I_PTR, "p")])
    assert e.method_sig(m, td_base()) == "unsafe void IFoo.Bar(byte* p)"
