"""Fix 140: inlined castclass/isinst hierarchy checks narrow a receiver.

Ground truth: ASN1.GetBytes 0x181ACFDD0 at 0x181ad0028..0x181ad0065:
`mov r9,[rax]` (klass), `movzx eax,byte [rdx+130h]` / `cmp [r9+130h],al;
jb THROW` (depth pre-check), `mov rax,[r9+0C8h]` / `cmp [rax+rcx*8-8],rdx;
jne THROW` (hierarchy[T.depth-1] == typeof(ASN1)), then `call [r9+178h]`
(vtable slot 4) on the narrowed object. The `cmp` below is that hierarchy
compare, byte for byte (48 39 54 c8 f8).
"""
import pytest

from il2cpp.prelude import HAVE_ICED

pytestmark = pytest.mark.skipif(not HAVE_ICED, reason='iced_x86 required')

ASN1_TY = (0x183c5ca58, 0x12 << 16)


def _ins(hexcode):
    from iced_x86 import Decoder, DecoderOptions
    d = Decoder(64, bytes.fromhex(hexcode), DecoderOptions.NONE)
    d.ip = 0x181ad0049
    return next(iter(d))


def _fake(hier_text='v62.Current.getClass().typeHierarchy', recv_text='v62.Current'):
    from il2cpp.expr import Expr
    from il2cpp import Lifter

    class _F:
        _note_cast_narrow = Lifter._note_cast_narrow
    f = _F()
    ob = Expr(recv_text, None, 'obj')
    hb = Expr(hier_text, None, 'kmember')
    hb._hobj = ob
    f.regs = {'RAX': hb}
    f._cast_narrow = {}
    return f


def _klass():
    from il2cpp.expr import Expr
    return Expr('typeof(Mono.Security.ASN1)', ASN1_TY, 'klass')


def test_hierarchy_compare_records_the_type():
    f = _fake()
    f._note_cast_narrow(_ins('483954c8f8'), _klass())
    assert f._cast_narrow == {'v62.Current': ASN1_TY}


def test_other_displacement_declines():
    f = _fake()
    # cmp [rax+rcx*8-10h],rdx: not the depth-1 element
    f._note_cast_narrow(_ins('483954c8f0'), _klass())
    assert f._cast_narrow == {}


def test_non_hierarchy_base_declines():
    f = _fake(hier_text='v62.Current.getClass().vtable')
    f._note_cast_narrow(_ins('483954c8f8'), _klass())
    assert f._cast_narrow == {}


def test_non_klass_operand_declines():
    from il2cpp.expr import Expr
    f = _fake()
    f._note_cast_narrow(_ins('483954c8f8'), Expr('num1', None, 'int'))
    assert f._cast_narrow == {}
