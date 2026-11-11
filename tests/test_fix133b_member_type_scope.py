"""Fix 133b: member types of open generic fields are closed through the
receiver or dropped -- never an unbound/foreign `T` (portable fakes)."""
from il2cpp.lifter.values import _ValuesMixin


def _t(te, data=0, byref=0):
    return (data, (te << 16) | (byref << 29))


class _TD(object):
    def __init__(self, gc):
        self.generic_container = gc


class _Meta(object):
    def __init__(self):
        # generic params: (owner container, name, cs, cc, num, flags)
        self.generic_parameters = [(7, 'T', 0, 0, 0, 0), (9, 'U', 0, 0, 0, 0)]
        self.typedefs = [_TD(7), _TD(-1), _TD(9)]


T_VAR = _t(0x13, 0)          # T of container 7 (List`1)
U_VAR = _t(0x13, 1)          # U of container 9 (some other generic)
M_VAR = _t(0x1e, 0)
GLYPH = _t(0x12, 42)
T_ARR = _t(0x1d, 100)        # T[] (elem ptr 100 -> T)
INT = _t(0x08)
RECV = _t(0x15, 500)         # List<Glyph>
GLYPH_ARR = _t(0x1d, 200)    # binary row Glyph[]
OBJ = _t(0x1c)
OBJ_ARR = _t(0x1d, 300)      # binary row object[]
IFACE = _t(0x12, 43)         # a class with no array row of its own


class _IL(object):
    def __init__(self):
        self.types = [GLYPH_ARR, INT, OBJ_ARR]
        self._ptrs = {100: T_VAR, 200: GLYPH, 300: OBJ}

    def _type_enum(self, ty):
        return (ty[1] >> 16) & 0xFF

    def type_from_ptr(self, p):
        return self._ptrs.get(p)

    def _closed_type_key(self, ty):
        if ty is None or self._type_enum(ty) in (0x13, 0x1e):
            return None
        if self._type_enum(ty) == 0x1d:
            ik = self._closed_type_key(self.type_from_ptr(ty[0]))
            return ('arr', ik) if ik else None
        return ty

    def _subst_closed(self, ty, cargs, margs):
        if self._type_enum(ty) == 0x13:
            return cargs[0]
        return ty if self._closed_type_key(ty) else None


class _L(_ValuesMixin):
    def __init__(self, args=(GLYPH,)):
        self.il = _IL()
        self.meta = _Meta()
        self._args = list(args) if args is not None else None

    def _generic_class_args(self, ty):
        if ty is None or self.il._type_enum(ty) != 0x15:
            return None
        return self._args


def test_closed_field_type_passes_through():
    assert _L()._recv_member_ty(0, RECV, INT) == INT


def test_open_array_closes_through_generic_receiver():
    assert _L()._recv_member_ty(0, RECV, T_ARR) == GLYPH_ARR


def test_open_scalar_closes_through_generic_receiver():
    assert _L()._recv_member_ty(0, RECV, T_VAR) == GLYPH


def test_definition_own_this_keeps_its_parameter():
    # receiver is the CLASS definition itself: `T` is in scope
    assert _L()._recv_member_ty(0, _t(0x12, 0), T_ARR) == T_ARR


def test_foreign_parameter_is_dropped():
    # U belongs to another container (a generic base level): no type
    assert _L()._recv_member_ty(0, RECV, U_VAR) is None
    assert _L()._recv_member_ty(1, _t(0x12, 1), T_VAR) is None


def test_mvar_and_unreadable_args_are_dropped():
    assert _L()._recv_member_ty(0, RECV, M_VAR) is None
    assert _L(args=None)._recv_member_ty(0, RECV, T_VAR) is None
    assert _L(args=(None,))._recv_member_ty(0, RECV, T_VAR) is None


def test_missing_array_row_is_dropped():
    lif = _L(args=(INT,))       # no `int[]` row in the fake table
    assert lif._recv_member_ty(0, RECV, T_ARR) is None


def test_reference_element_without_row_closes_to_object_array():
    # array covariance: `object[] a = list._items` is legal for class T
    assert _L(args=(IFACE,))._recv_member_ty(0, RECV, T_ARR) == OBJ_ARR
