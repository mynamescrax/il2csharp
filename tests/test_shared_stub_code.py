"""Shared-body stubs show SOME code: first native insns as comments.

The throwing `__SharedBodyStubs` body stays (the managed owner is still
unresolved); where the VA decodes, the stub now lists the real bytes'
disassembly so readers see what the shared body does instead of no
code at all. Every failure declines to the old throw-only shape.
"""

from types import SimpleNamespace as NS

from il2cpp.emitter import Emitter


def _emitter(bin_ns, cands=None):
    e = Emitter.__new__(Emitter)
    e.il = NS(bin=bin_ns, addr_candidates=cands or {},
              generic_method_name=lambda si: "G.M<int>")
    e.meta = NS(methods=[], typedefs=[])
    return e


def test_asm_lines_identity_leaf():
    bin_ns = NS(is_exec_va=lambda va: True,
                read=lambda va, n: bytes([0x48, 0x89, 0xC8, 0xC3, 0xCC]))
    e = _emitter(bin_ns)
    assert e._stub_asm_lines("18063ac90") == [
        "    // 0x18063ac90: mov rax,rcx",
        "    // 0x18063ac93: ret",
    ]


def test_asm_lines_decline():
    def _boom(va, n):
        raise AssertionError("must not read a non-exec VA")

    e = _emitter(NS(is_exec_va=lambda va: False, read=_boom))
    assert e._stub_asm_lines("18063ac90") == []
    e2 = _emitter(NS(is_exec_va=lambda va: True, read=lambda va, n: None))
    assert e2._stub_asm_lines("18063ac90") == []
    assert e2._stub_asm_lines("zz") == []
    assert e2._stub_asm_lines("") == []


def test_asm_lines_cap_and_no_sub_tokens():
    bin_ns = NS(is_exec_va=lambda va: True, read=lambda va, n: b"\x90" * 64)
    e = _emitter(bin_ns)
    lines = e._stub_asm_lines("1000")
    assert len(lines) == 16
    assert lines[0] == "    // 0x1000: nop"
    assert all("sub_" not in ln for ln in lines)


def test_stub_file_text_shows_code_and_still_throws():
    bin_ns = NS(is_exec_va=lambda va: True,
                read=lambda va, n: bytes([0x48, 0x89, 0xC8, 0xC3, 0xCC]))
    e = _emitter(bin_ns)
    text = e._stub_file_text({"18063ac90"})
    assert "internal static object sub_18063ac90(params object[] args)" in text
    assert "mov rax,rcx" in text
    assert "NotImplementedException" in text
    assert text.count("{") == text.count("}")


def test_stub_file_text_guarded_keeps_throw_only():
    e = Emitter.__new__(Emitter)
    e.il = NS(addr_candidates=None)
    e.meta = NS(methods=[], typedefs=[])
    text = e._stub_file_text({"1a2b"})
    assert "internal static object sub_1a2b(params object[] args)" in text
    assert "NotImplementedException" in text
    assert "native code at this address" not in text
