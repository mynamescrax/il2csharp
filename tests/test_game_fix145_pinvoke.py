"""Fix 145: P/Invoke declarations recovered from the marshalling stub.

A `[DllImport]` method has no managed body; IL2CPP compiles it to a stub that
resolves the native function once into a RIP-relative cell and passes a fully
populated `PInvokeArguments`. mscorlib's `Microsoft.Win32.Kernel32` wrappers
(mi 1, 2, 26) are the fixture's ground truth for that shape, so the emitter can
print what the source said instead of the lifted marshalling code. Two other
PInvokeImpl rows here are the shells that must keep their lifted form: a stub
that resolves on the fly with no `PInvokeArguments` (mi 46282, the zlib
family) and a bare forwarder (mi 10434).
"""
import pytest

from il2cpp import Emitter

from test_game_goldens import game_decompiler

pytestmark = pytest.mark.game


def _emitter(il, dec):
    e = Emitter(il, '', with_bodies=False)
    e.with_bodies = True
    e.lifter, e.decompiler = dec.L, dec
    return e


def _emit(e, il, mi, name):
    m = il.meta.methods[mi]
    assert m.name == name
    assert m.flags & 0x2000 and m.addr          # MethodAttributes.PInvokeImpl
    out = []
    e.emit_method(m, il.meta.typedefs[m.declaring], out, '    ')
    return m, '\n'.join(out)


def test_free_library_declaration_comes_from_the_stub(game_decompiler):
    il, dec = game_decompiler
    e = _emitter(il, dec)
    m, text = _emit(e, il, 1, 'FreeLibrary')
    # push rbx; sub rsp,50h; mov rax,[rip+<cell>] -- the caching guard
    assert il.bin.read(m.addr, 8) == bytes.fromhex('40534883ec50488b')
    assert 'DllImport("kernel32.dll"' in text
    assert 'CharSet.Unicode' in text and 'ExactSpelling = true' in text
    assert 'internal static extern bool FreeLibrary(System.IntPtr hModule);' in text
    assert 'VA: 0x181AD3430' in text


def test_load_library_ex_names_the_w_entry_point(game_decompiler):
    il, dec = game_decompiler
    e = _emitter(il, dec)
    _, text = _emit(e, il, 2, 'LoadLibraryEx')
    # the managed name differs from the native one, so EntryPoint is spelled
    assert 'EntryPoint = "LoadLibraryExW"' in text
    assert 'CharSet.Unicode' in text and 'ExactSpelling' not in text
    assert 'internal static extern' in text


def test_unspecified_charset_is_omitted_not_spelled(game_decompiler):
    # SetThreadErrorMode records charSet NOT_SPECIFIED: C# has no such
    # CharSet member, so the argument is left out (ExactSpelling still prints)
    il, dec = game_decompiler
    e = _emitter(il, dec)
    _, text = _emit(e, il, 26, 'SetThreadErrorMode')
    assert 'DllImport("kernel32.dll", ExactSpelling = true)' in text
    assert 'CharSet' not in text
    assert 'internal static extern bool SetThreadErrorMode(uint dwNewMode, ref uint lpOldMode);' in text


def test_a_stub_without_pinvoke_arguments_keeps_its_lifted_form(game_decompiler):
    # CreateZStream resolves the native function on the fly: no PInvokeArguments
    il, dec = game_decompiler
    e = _emitter(il, dec)
    m, text = _emit(e, il, 46282, 'CreateZStream')
    assert il.bin.read(m.addr, 8) == bytes.fromhex('48895c240848896c')
    assert 'DllImport' not in text


def test_a_bare_forwarder_keeps_its_lifted_form(game_decompiler):
    # sub rsp,28h; call ... -- no caching guard and no argument struct
    il, dec = game_decompiler
    e = _emitter(il, dec)
    m, text = _emit(e, il, 10434, 'InitializeUserPreferredCultureInfoInAppX')
    assert il.bin.read(m.addr, 8) == bytes.fromhex('4883ec28e8e70081')
    assert 'DllImport' not in text
