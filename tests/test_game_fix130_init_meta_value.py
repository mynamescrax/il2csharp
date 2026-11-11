"""Fix 130: the initialize_runtime_metadata jmp thunk returns its slot item.

Ground truth (disasm, EnumBuilder.GetMembers 0x181BD4E80): `lea rcx,[slot];
call 0x180435420; mov rcx,rax; call il2cpp_object_new`.  The thunk is
`InitializeRuntimeMetadata(slot, true)` and RAX is the slot's TypeInfo, so
the allocation is `new T()`, not `il2cpp_object_new(objN)` over a temp bound
to `il2cpp_codegen_initialize_runtime_metadata(typeof(T))`.  The array
allocation reached through the same shape binds one identity instead of
re-printing `new object[1]` at every use.
"""
import re

import pytest

from test_game_goldens import game_decompiler

pytestmark = pytest.mark.game


def _lift(il, dec, ns, tname, mname):
    for td in il.meta.typedefs:
        if td.name == tname and td.namespace == ns:
            for mi in range(td.method_start, td.method_start + td.method_count):
                m = il.meta.methods[mi]
                if m.name == mname:
                    return '\n'.join(dec.lift_method(m, td))
    raise AssertionError('%s.%s.%s not found' % (ns, tname, mname))


def test_win_io_error_allocates_exceptions_directly(game_decompiler):
    il, dec = game_decompiler
    text = _lift(il, dec, 'System.IO', '__Error', 'WinIOError')
    assert 'il2cpp_codegen_initialize_runtime_metadata(typeof(' not in text
    assert 'il2cpp_object_new(' not in text
    assert 'new System.IO.FileNotFoundException(' in text
    assert 'new System.IO.DirectoryNotFoundException()' in text


def test_win_io_error_array_has_one_identity(game_decompiler):
    il, dec = game_decompiler
    text = _lift(il, dec, 'System.IO', '__Error', 'WinIOError')
    # every `new object[1]` is a bound declaration, never an inline argument
    for line in text.splitlines():
        if 'new object[1]' in line:
            assert re.match(r'\s*(var|object\[\])\s+\w+ = new object\[1\];\s*$', line), line
