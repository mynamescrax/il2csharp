"""Fix 134: raw loads keep their native width (`mov eax,[rcx+18h]` is a
4-byte read, not the 1-byte `((byte*)E + 0x18)[0]`)."""
import pytest

from il2cpp.dec.textpass import _TextPassMixin
from il2cpp.expr import Expr


class _TP(_TextPassMixin):
    pass


def _u(s):
    return _TP()._unsafify(s)


def test_marked_load_spells_its_width():
    assert _u('int num1 = (__w_int)*(obj3 + 0x18);') == \
        'int num1 = ((int*)((byte*)obj3 + 0x18))[0];'


def test_marked_indexed_load_and_signed_byte():
    assert _u('x = (__w_int)*(this.points + num18*4 + 0x10);') == \
        'x = ((int*)((byte*)this.points + num18*4 + 0x10))[0];'
    assert _u('y = (__w_sbyte)*(obj1 - 0x4);') == 'y = ((sbyte*)((byte*)obj1 - 0x4))[0];'


def test_marked_bare_deref_and_nesting():
    assert _u('z = (__w_short)*(obj2);') == 'z = ((short*)((byte*)obj2))[0];'
    # an unmarked (8-byte) base deref keeps the byte spelling around the
    # marked inner read
    out = _u('w = (__w_int)*(*(obj1 + 0x10) + 0x18);')
    assert out == 'w = ((int*)((byte*)((byte*)obj1 + 0x10)[0] + 0x18))[0];'


def test_unmarked_deref_unchanged_and_no_marker_survives():
    assert _u('a = *(obj1 + 0x18);') == 'a = ((byte*)obj1 + 0x18)[0];'
    assert '__w_' not in _u('s = "x"; b = (__w_int)c;')
    assert _u('s = "(__w_int)*(q + 1)";') == 's = "(__w_int)*(q + 1)";'


iced = pytest.importorskip('iced_x86')


class _Ins(object):
    def __init__(self, mn, msz, dst_reg=None, mem_ops=(1,)):
        self.mnemonic = getattr(iced.Mnemonic, mn)
        self.memory_size = getattr(iced.MemorySize, msz)
        self.op0_register = dst_reg if dst_reg is not None else iced.Register.EAX
        self._mem = set(mem_ops)
        self.op_count = 2

    def op_kind(self, k):
        return iced.OpKind.MEMORY if k in self._mem else iced.OpKind.REGISTER


def _mark(ins, text='*(obj3 + 0x18)', ty=None, kind='ptr'):
    from il2cpp.lifter.insn import _InsnMixin
    return _InsnMixin._width_mark(_InsnMixin(), ins, Expr(text, ty, kind))


def test_dword_mov_is_marked_int():
    e = _mark(_Ins('MOV', 'UINT32'))
    assert e.text == '(__w_int)*(obj3 + 0x18)' and e.ty == (0, 0x08 << 16) and e.kind == 'int'


def test_widths_by_mnemonic():
    assert _mark(_Ins('MOVZX', 'UINT16')).text.startswith('(__w_ushort)')
    assert _mark(_Ins('MOVSX', 'INT8')).text.startswith('(__w_sbyte)')
    assert _mark(_Ins('MOVSXD', 'INT32', iced.Register.RAX)).text.startswith('(__w_int)')
    assert _mark(_Ins('CMP', 'UINT32', mem_ops=(0,))).text.startswith('(__w_int)')


def test_declines():
    # byte zero-extend is already right; qwords stay raw (references)
    assert _mark(_Ins('MOVZX', 'UINT8')).text == '*(obj3 + 0x18)'
    assert _mark(_Ins('MOV', 'UINT64', iced.Register.RAX)).text == '*(obj3 + 0x18)'
    # typed / named / composite / non-deref values are untouched
    assert _mark(_Ins('MOV', 'UINT32'), ty=(0, 0x08 << 16)).text == '*(obj3 + 0x18)'
    assert _mark(_Ins('MOV', 'UINT32'), text='obj3._size', kind='int').text == 'obj3._size'
    assert _mark(_Ins('MOV', 'UINT32'), text='*(a) + *(b)').text == '*(a) + *(b)'
    # other mnemonics (float/SSE, arithmetic) are out of scope
    assert _mark(_Ins('ADD', 'UINT32')).text == '*(obj3 + 0x18)'


def test_generic_call_paren_survives_member_fold():
    # fix 134e: `(?<![\w.])\((tok)\)\.` treated the generic call's
    # argument paren as a stale receiver group (`Find<T>true.Length`)
    from il2cpp.dec.sugar import _SugarMixin

    class _S(_SugarMixin):
        pass
    s = _S()
    lines = ['for (int i = 0; i < Object.FindObjectsOfType<T>(true).Length; i++)',
             'x = Object.FindObjectsByType<T>(FindObjectsSortMode.None).Length;',
             'y = f()(a).b;',
             'z = (obj1).name;', 'w = ((obj2).name);']
    out = s._member_fold(lines)
    assert out[:3] == lines[:3]
    assert out[3] == 'z = obj1.name;'
    assert out[4] == 'w = (obj2.name);'


def test_oversized_temp_comment_drops_width_markers():
    # fix 134f: the `var vN = 0; // <expr>` spill comment is opaque to
    # textpass, so the lifter strips the marker itself
    from il2cpp.lifter.state import _StateMixin

    class _L:
        dry = False

        def __init__(self):
            self.lines = []

        def new_var(self):
            return 'v9'

        def emit(self, _a, text, _b):
            self.lines.append(text)
    lst = _L()
    e = _StateMixin._mk(lst, '(__w_int)*(v50 + 0x18) + ' + 'a' * 240)
    assert e.text == 'v9'
    assert '__w_' not in lst.lines[0]
    assert lst.lines[0].startswith('var v9 = 0; // *(v50 + 0x18) + aaa')