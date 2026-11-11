"""Fix 133: open generic class levels get IL2CPP-style reconstructed
instance offsets instead of the all-zero table (portable: fake metadata)."""
import il2cpp.runtime.fields as fields_mod
from il2cpp.runtime.fields import _FieldsMixin

STATIC = 0x10


class _TD(object):
    def __init__(self, field_start, field_count, parent, valuetype=False, flags=0):
        self.field_start = field_start
        self.field_count = field_count
        self.parent = parent
        self.is_valuetype = valuetype
        self.flags = flags


class _F(object):
    def __init__(self, ty, attrs=0):
        self.type = ty
        self.attrs = attrs


class _Meta(object):
    pass


def _t(te, data=0):
    return (data, te << 16)


# type table
OBJ, INT, SZARR, VAR, BASE_T, GEN_T, LONG = range(7)
TYPES = [_t(0x1c), _t(0x08), _t(0x1d), _t(0x13), _t(0x12, 0), _t(0x15, 1), _t(0x0a)]


class _IL(_FieldsMixin):
    def __init__(self):
        self.meta = _Meta()
        # td0 Base (real): int @0x10, recorded size 8 (0x10..0x18)
        # td1 Gen`1 (open): T[] , int, int, static int
        # td2 Gen2`1 : Base (open): long
        # td3 Bad`1 (open): T by value
        # td4 Gen3`1 : Gen`1<T> (open): int
        # td5 Explicit`1 (open, explicit layout): int
        self.meta.typedefs = [
            _TD(0, 1, OBJ), _TD(1, 4, OBJ), _TD(5, 1, BASE_T), _TD(6, 1, OBJ),
            _TD(7, 1, GEN_T), _TD(8, 1, OBJ, flags=0x10)]
        self.meta.fields = [
            _F(INT), _F(SZARR), _F(INT), _F(INT), _F(INT, STATIC), _F(LONG),
            _F(VAR), _F(INT), _F(INT)]
        self.types = TYPES
        self.field_offsets = [[0x10], [0, 0, 0, 0], [0], [0], [0], [0]]
        self.type_sizes = [8, None, None, None, None, None]

    def td_of_ty(self, ty):
        return ty[0] if ty and ((ty[1] >> 16) & 0xFF) in (0x11, 0x12, 0x15) else None

    def _sf_ty_size_align(self, ty, args, depth):
        te = (ty[1] >> 16) & 0xFF
        return {0x08: (4, 4), 0x0a: (8, 8), 0x1d: (8, 8), 0x12: (8, 8), 0x1c: (8, 8)}.get(te)


def _il(monkeypatch):
    monkeypatch.setattr(fields_mod, 'field_attrs', lambda il, f: f.attrs)
    return _IL()


def test_real_table_is_returned_unchanged(monkeypatch):
    il = _il(monkeypatch)
    fo = il.field_offsets[0]
    assert il._class_level_offsets(0, fo) is fo


def test_open_generic_level_is_laid_out_in_declaration_order(monkeypatch):
    il = _il(monkeypatch)
    # List<T> shape: _items 0x10, _size 0x18, _version 0x1c; static untouched
    assert il._class_level_offsets(1, il.field_offsets[1]) == [0x10, 0x18, 0x1c, 0]


def test_level_starts_at_the_recorded_parent_instance_size(monkeypatch):
    il = _il(monkeypatch)
    assert il._class_level_offsets(2, il.field_offsets[2]) == [0x18]


def test_open_generic_parent_end_rounds_to_eight(monkeypatch):
    il = _il(monkeypatch)
    # Gen`1 ends at 0x20 (0x1c + 4) -> child starts at 0x20
    assert il._class_level_offsets(4, il.field_offsets[4]) == [0x20]


def test_argument_dependent_or_explicit_levels_decline(monkeypatch):
    il = _il(monkeypatch)
    assert il._class_level_offsets(3, il.field_offsets[3]) is None
    assert il._class_level_offsets(5, il.field_offsets[5]) is None
