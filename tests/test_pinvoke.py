"""P/Invoke declaration recovery (`il2cpp/pinvoke.py`), synthetic bytes only.

A `[DllImport]` method has no managed body; IL2CPP compiles it to a
marshalling stub that resolves the native function once and caches it in a
RIP-relative cell. The `PInvokeArguments` it passes to the resolver still
carries the library name, the entry point, the calling convention, the
charset and ExactSpelling, so the original declaration can be read back
instead of lifting compiler plumbing.

Every case here assembles the stub by hand (tests/synth_x64.py), so no
fixture is needed and each claimed shape is pinned exactly.
"""
import pytest

from il2cpp.prelude import HAVE_ICED

pytestmark = pytest.mark.skipif(not HAVE_ICED, reason='iced_x86 required')

from il2cpp.pinvoke import dllimport_attribute, stub_arguments  # noqa: E402
from synth_x64 import Asm, BASE  # noqa: E402

CELL = 0x183E73C08
RESOLVER = 0x180435700


class FakeBin:
    """One contiguous blob at BASE: code and the struct's strings."""

    def __init__(self, blob):
        self.blob = blob

    def is_exec_va(self, va):
        return BASE <= va < BASE + len(self.blob)

    def read(self, va, n):
        o = va - BASE
        return self.blob[o:o + n] if 0 <= o < len(self.blob) else None


def _stub(module='steam_api64', entry='SteamAPI_InitFlat', conv=1, cs=2,
          nomangle=0, gap=(), fused=False, store='direct', tail_nops=0,
          module_wide=True):
    """Assemble one marshalling stub; strings are appended after the code."""
    a = Asm()
    a.mov_rax_rip(CELL)
    if gap:
        a.raw(''.join(gap))
    a.test_rax_rax()
    a.jne('CALL')
    a.lea_rax('MODSTR')
    a.mov_rsp_imm(0x28, len(module))
    a.mov_rsp_rax(0x20)
    a.lea_rcx_rsp(0x20)
    a.lea_rax('ENTSTR')
    a.mov_rsp_imm(0x38, len(entry))
    a.mov_rsp_rax(0x30)
    if fused:
        # the compiler fuses charset + parameterSize into one qword store
        a.xor_eax_eax()
        a.mov_rsp_dword(0x40, 0)
        a.mov_rsp_imm(0x44, cs | (0 << 8))
    else:
        a.xor_eax_eax()                     # the source zeroes a register once
        if conv:
            a.mov_rsp_dword(0x40, conv)
        else:
            a.mov_rsp_eax(0x40)             # callingConvention = 0
        a.mov_rsp_dword(0x44, cs)
        a.mov_rsp_dword(0x48, 0)            # parameterSize
    a.mov_rsp_byte(0x4C, nomangle)
    a.call(RESOLVER)
    if store == 'direct':
        a.mov_rip_rax(CELL)
    elif store == 'via_reg':
        a.raw('4989c2')                     # mov r10,rax
        a.mov_rip_rax(CELL)
    elif store == 'wrong_reg':
        a.raw('4989c2')
        a.raw('4c891500000000')             # mov [rip+0],r10
    a.label('CALL')
    for _ in range(tail_nops):
        a.nop()
    a.ret()
    a.label('MODSTR')
    if module_wide:
        a.data(module.encode('ascii').decode('ascii').encode('utf-16-le') + b'\x00\x00')
    else:
        a.data(module.encode('ascii') + b'\x00')
    a.label('ENTSTR')
    a.data(entry.encode('ascii') + b'\x00')
    return a


def _decode(**kw):
    a = _stub(**kw)
    return stub_arguments(FakeBin(a.assemble()), BASE)


def test_recovers_module_entry_and_enums():
    r = _decode(module='steam_api64', entry='SteamAPI_ISteamMatchmaking_LeaveLobby',
                conv=1, cs=2, nomangle=0)
    assert r['module'] == 'steam_api64'
    assert r['entry'] == 'SteamAPI_ISteamMatchmaking_LeaveLobby'
    assert (r['call_conv'], r['char_set'], r['no_mangle']) == (1, 2, False)
    assert r['cell'] == CELL


def test_recovers_stdcall_unicode_exact_spelling():
    r = _decode(module='kernel32.dll', entry='GetFileMUIPath', conv=2, cs=1, nomangle=1)
    assert (r['call_conv'], r['char_set'], r['no_mangle']) == (2, 1, True)
    attr = dllimport_attribute(r, 'GetFileMUIPath')
    assert 'CallingConvention = System.Runtime.InteropServices.CallingConvention.StdCall' in attr
    assert 'CharSet = System.Runtime.InteropServices.CharSet.Unicode' in attr
    assert 'ExactSpelling = true' in attr
    assert 'EntryPoint' not in attr            # same name: nothing to say


def test_fused_charset_and_parameter_size_store():
    r = _decode(conv=0, cs=1, fused=True)
    assert (r['call_conv'], r['char_set']) == (0, 1)


@pytest.mark.parametrize('gap', [['4489cf'], ['0f28742420'], ['48c7c001000000']])
def test_register_saves_in_the_gap_are_transparent(gap):
    assert _decode(gap=gap)['entry'] == 'SteamAPI_InitFlat'


def test_result_copied_through_a_register_before_the_cache_store():
    assert _decode(store='via_reg')['cell'] == CELL


def test_cache_store_of_another_register_declines():
    assert _decode(store='wrong_reg') is None


def test_unknown_charset_still_decodes_but_emits_nothing():
    r = _decode(cs=9)
    assert r is not None and r['char_set'] == 9
    assert dllimport_attribute(r, 'X') is None


def test_vararg_convention_declines_the_attribute():
    r = _decode(conv=5)
    assert r is not None and r['call_conv'] == 5
    assert dllimport_attribute(r, 'X') is None


def test_narrow_module_string_declines():
    # the Windows struct carries UTF-16; a narrow blob is not that struct
    assert _decode(module_wide=False) is None


def test_a_string_without_its_nul_terminator_declines():
    a = _stub()
    blob = bytearray(a.assemble())
    blob[-len(b'SteamAPI_InitFlat\x00')] = ord('X')      # break the entry text
    blob[-1] = ord('X')
    assert stub_arguments(FakeBin(bytes(blob)), BASE) is None


def test_non_printable_strings_decline():
    a = _stub()
    blob = bytearray(a.assemble())
    i = bytes(blob).index(b'SteamAPI_InitFlat')
    blob[i] = 0x01
    assert stub_arguments(FakeBin(bytes(blob)), BASE) is None


def test_an_incomplete_struct_declines():
    # drop the entry-point length store: the resolver argument is not complete
    a = Asm()
    a.mov_rax_rip(CELL).test_rax_rax().jne('CALL')
    a.lea_rax('MODSTR').mov_rsp_imm(0x28, 4).mov_rsp_rax(0x20).lea_rcx_rsp(0x20)
    a.lea_rax('ENTSTR').mov_rsp_rax(0x30)
    a.mov_rsp_eax(0x40).mov_rsp_imm(0x44, 2).mov_rsp_byte(0x4C, 0)
    a.call(RESOLVER).mov_rip_rax(CELL)
    a.label('CALL').ret()
    a.label('MODSTR').data(b'test\x00\x00')
    a.label('ENTSTR').data(b'Init\x00')
    assert stub_arguments(FakeBin(a.assemble()), BASE) is None


def test_a_call_that_does_not_address_the_struct_declines():
    a = Asm()
    a.sub_rsp(0x28).mov_rax_rip(CELL).test_rax_rax().jne('CALL')
    a.xor_eax_eax().mov_rsp_eax(0x40).call(RESOLVER).mov_rip_rax(CELL)
    a.label('CALL').ret()
    assert stub_arguments(FakeBin(a.assemble()), BASE) is None


def test_unreadable_targets_decline():
    a = _stub()
    blob = a.assemble()
    assert stub_arguments(FakeBin(blob), BASE + 0x10000) is None
    assert stub_arguments(None, BASE) is None


def test_rsp_is_tracked_across_the_frame_setup():
    # sub rsp,0x28 then the struct at [rsp+0x20] -- the same frame as no setup
    a = Asm()
    a.sub_rsp(0x28)
    a.mov_rax_rip(CELL).test_rax_rax().jne('CALL')
    a.lea_rax('MODSTR').mov_rsp_imm(0x48, 4).mov_rsp_rax(0x40).lea_rcx_rsp(0x40)
    a.lea_rax('ENTSTR').mov_rsp_imm(0x58, 4).mov_rsp_rax(0x50)
    a.xor_eax_eax().mov_rsp_eax(0x60).mov_rsp_dword(0x64, 2)
    a.mov_rsp_dword(0x68, 0).mov_rsp_byte(0x6C, 0)
    a.call(RESOLVER).mov_rip_rax(CELL)
    a.label('CALL').ret()
    # moduleName is Il2CppNativeChar*: UTF-16 on Windows, as in _stub
    a.label('MODSTR').data(b't\x00e\x00s\x00t\x00\x00\x00')
    a.label('ENTSTR').data(b'Init\x00')
    r = stub_arguments(FakeBin(a.assemble()), BASE)
    assert r and r['module'] == 'test' and r['entry'] == 'Init'


# ------------------------------------------------------------ the attribute

def _args(**kw):
    base = dict(module='steam_api64', entry='SteamAPI_InitFlat', call_conv=1,
                char_set=2, param_size=0, no_mangle=False, cell=CELL)
    base.update(kw)
    return base


def test_attribute_is_fully_qualified_and_escapes_the_module_name():
    attr = dllimport_attribute(_args(module='a"b\\c'), 'X')
    assert attr.startswith('[System.Runtime.InteropServices.DllImport("a\\"b\\\\c"')
    assert attr.endswith(')]') and '\n' not in attr


def test_attribute_omits_every_default():
    assert dllimport_attribute(_args(call_conv=0, char_set=2, entry='M'), 'M') == \
        '[System.Runtime.InteropServices.DllImport("steam_api64")]'


def test_attribute_keeps_ansi_and_thiscall():
    attr = dllimport_attribute(_args(char_set=0, call_conv=3), 'M')
    assert 'CharSet = System.Runtime.InteropServices.CharSet.Ansi' in attr
    assert 'CallingConvention = System.Runtime.InteropServices.CallingConvention.ThisCall' in attr


def test_attribute_declines_an_unknown_convention():
    assert dllimport_attribute(_args(call_conv=9), 'M') is None
