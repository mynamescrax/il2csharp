"""Fix 128: opt-in --raw-addr routes `(byte*)E` bases through `__addr(E)`.

The lifter spells native field/slot accesses off a managed reference as
`((byte*)obj + 0x10)[0]`; C# rejects the cast (CS0030, ~111k on the fixture
gate) and the statement never binds. Under the flag the base goes through a
declared helper whose integer/pointer overloads keep the plain cast and whose
`object` overload throws. Default output is unchanged.
"""
from il2cpp import Emitter
from il2cpp.rawaddr import rewrite_line, rewrite_lines, helper_file_text, CLASS


def test_managed_bases_wrapped_nested_and_after_block_comment():
    src = '((float*)((byte*)((byte*)obj41 + 0x0)[0] + n*4 + 0x20))[0] = r;'
    assert rewrite_line(src) == (
        '((float*)((byte*)__addr(((byte*)__addr(obj41) + 0x0)[0]) + n*4 + 0x20))[0] = r;')
    assert rewrite_line('x = /*vtable slot 6*/ f(((byte*)t.m[i] + 0x1a0)[0]);') == \
        'x = /*vtable slot 6*/ f(((byte*)__addr(t.m[i]) + 0x1a0)[0]);'
    assert rewrite_line('u = ((byte*)a.B(c, (byte*)d) - 0x30)[0];') == \
        'u = ((byte*)__addr(a.B(c, (byte*)__addr(d))) - 0x30)[0];'
    assert rewrite_line('v = ((byte*)(object)a + 8)[0];') == \
        'v = ((byte*)__addr((object)a) + 8)[0];'


def test_literals_keywords_prefix_ops_generics_strings_comments_kept():
    for ln in ('y = ((byte*)16)[0];', 'z = ((byte*)null)[0];',
               'q = ((byte*)-a)[0];', 'w = ((byte*)F<int>(a) + 8)[0];',
               's = "(byte*)obj"; // (byte*)c'):
        assert rewrite_line(ln) == ln


def test_rewrite_is_idempotent_and_reports_change():
    once = rewrite_line('a = ((byte*)obj + 8)[0];')
    assert rewrite_line(once) == once
    lines, changed = rewrite_lines(['// ((byte*)obj)[0]', 'b = 1;'])
    assert not changed and lines == ['// ((byte*)obj)[0]', 'b = 1;']
    assert rewrite_lines(['a = ((byte*)obj)[0];'])[1]


def test_helper_declares_honest_overloads():
    text = helper_file_text()
    assert 'internal static unsafe class %s' % CLASS in text
    assert 'byte* __addr(object o)' in text and 'NotSupportedException' in text
    for sig in ('__addr(void* p) { return (byte*)p; }',
                '__addr(long v) { return (byte*)v; }',
                '__addr(ulong v) { return (byte*)v; }'):
        assert sig in text


def test_flag_defaults_off():
    import inspect
    sig = inspect.signature(Emitter.__init__)
    assert sig.parameters['raw_addr'].default is False
